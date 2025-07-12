# AI_sandbox/pco/output_parser.py
import json
import re
from typing import Union, Dict, Any

from langchain_core.agents import AgentAction, AgentFinish
from langchain_core.outputs import Generation
from langchain.agents import AgentOutputParser
from langchain_core.exceptions import OutputParserException # AgentOutputParserError の代わりにこれをインポート

class CustomAgentOutputParser(AgentOutputParser):
    """
    LLMの出力からAction/Action InputまたはFinal Answerを解析するカスタムパーサー。
    OllamaなどのLLMが生成する出力のバリエーションに対応するため、より堅牢にします。
    """
    def parse(self, text: str) -> Union[AgentAction, AgentFinish]:
        # Final Answer のパターン
        if "Final Answer:" in text:
            final_answer_match = re.search(r"Final Answer:\s*(.*)", text, re.DOTALL)
            if final_answer_match:
                return AgentFinish(return_values={"output": final_answer_match.group(1).strip()}, log=text)
            else:
                # Final Answer のパターンだが、内容が見つからない場合
                return AgentFinish(return_values={"output": text.strip()}, log=text)

        # Action / Action Input のパターンを検索
        # LLMが出力する可能性のある複数の形式に対応
        # re.DOTALL は . が改行にもマッチするようにする
        action_match = re.search(r"Action:\s*(.*?)\nAction Input:\s*(\{.*\})", text, re.DOTALL)

        if action_match:
            action = action_match.group(1).strip()
            action_input_str = action_match.group(2).strip() # ここでJSON部分のみを厳密にキャプチャ

            # Action Input の JSON を堅牢にパース
            try:
                action_input = json.loads(action_input_str)

                # 過去のネストしたJSONエラー (llm_agent_id内にJSONがある) にも引き続き対応
                if (
                    isinstance(action_input, dict) and
                    len(action_input) == 1 and
                    'llm_agent_id' in action_input and
                    isinstance(action_input['llm_agent_id'], str) and
                    action_input['llm_agent_id'].strip().startswith('{') and
                    action_input['llm_agent_id'].strip().endswith('}')
                ):
                    try:
                        action_input = json.loads(action_input['llm_agent_id'])
                    except json.JSONDecodeError as e:
                        raise OutputParserException(f"Failed to parse nested JSON in Action Input: {action_input['llm_agent_id']} - {e}\nFull text: {text}")

            except json.JSONDecodeError as e:
                # JSONパースエラーの場合、エラーメッセージに「Extra data」が含まれることがある
                # これは正規表現でJSONブロックをより厳密にキャプチャすることで防ぐ
                raise OutputParserException(f"Could not parse Action Input as valid JSON: {action_input_str} - {e}\nFull text: {text}")
            except Exception as e:
                raise OutputParserException(f"Unexpected error during Action Input parsing: {e}\nFull text: {text}")

            # ツールに渡す引数を構築
            return AgentAction(tool=action, tool_input=action_input, log=text)

        # どちらのパターンにもマッチしない場合
        # AIがThoughtだけを言ったり、Actionのフォーマットを間違えたりした場合にここに到達する
        # この場合、LLMに直接応答を返すか、再試行を促す
        # LangChainのエージェントExecutorは、OutputParserExceptionを受け取ると通常は再試行する
        raise OutputParserException(f"Could not parse LLM output: No valid Action/Action Input or Final Answer found. Full text:\n{text}")

    @property
    def _type(self) -> str:
        return "custom_output_parser"
# program_builder/pco/output_parser.py
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
        action_match = re.search(r"Action:\s*(.*?)\nAction Input:\s*(.*)", text, re.DOTALL)

        if action_match:
            action = action_match.group(1).strip()
            action_input_str = action_match.group(2).strip()

            # Action Input の JSON を堅牢にパース
            try:
                # ```json ... ``` のようなコードブロックで囲まれている場合を考慮
                json_block_match = re.search(r"```json\n(.*)\n```", action_input_str, re.DOTALL)
                if json_block_match:
                    action_input_json_str = json_block_match.group(1).strip()
                else:
                    action_input_json_str = action_input_str

                action_input = json.loads(action_input_json_str)

                # LLMが不正確なJSONを吐き出し、それがネストしている場合（過去のエラーログを考慮）
                # 例: {'llm_agent_id': '{"code": "...", "base_image": "..."}'}
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
                raise OutputParserException(f"Could not parse Action Input as JSON: {action_input_str} - {e}\nFull text: {text}")
            except Exception as e:
                raise OutputParserException(f"Unexpected error during Action Input parsing: {e}\nFull text: {text}")

            # ツールに渡す引数を構築
            return AgentAction(tool=action, tool_input=action_input, log=text)

        # どちらのパターンにもマッチしない場合
        raise OutputParserException(f"Could not parse LLM output: {text}")

    @property
    def _type(self) -> str:
        return "custom_output_parser"
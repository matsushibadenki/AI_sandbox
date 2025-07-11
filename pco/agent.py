# program_builder/pco/agent.py
from langchain_ollama import ChatOllama
from langchain.agents import AgentExecutor
from langchain_core.prompts import PromptTemplate, MessagesPlaceholder, ChatPromptTemplate
from langchain_core.tools import Tool # <-- これをインポートして利用
from langchain_core.messages import AIMessage, HumanMessage
from typing import List, Dict, Any

from pco.tools import SandboxTool
from pco.output_parser import CustomAgentOutputParser
from config import config

class ProgramConstructionAgent:
    def __init__(self, sandbox_tool: SandboxTool):
        # LLMの初期化
        self.llm = ChatOllama(
            base_url=config.LLM_BASE_URL,
            model=config.LLM_MODEL_NAME,
            temperature=0.7
        )

        # ツールリスト
        # SandboxTool のインスタンスを Tool() でラップして渡す
        # ◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️↓修正開始◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️
        self.tools: List[Tool] = [
            Tool(
                name=sandbox_tool.name,
                description=sandbox_tool.description,
                func=sandbox_tool._run, # _run メソッドを渡す
                args_schema=sandbox_tool.args_schema, # args_schema を渡す
                coroutine=sandbox_tool._arun # 非同期版も渡す（オプション）
            )
        ]
        # ◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️↑修正終わり◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️

        # プロンプトテンプレートの定義
        self.prompt_template = ChatPromptTemplate.from_messages([
            ("system", "You are an autonomous program construction agent. Your goal is to write, test, and debug Python or Node.js programs based on user requirements."),
            ("system", "You have access to the following tools: {tools}"),
            ("system", "To use a tool, you must output your thought process, then explicitly state the Action and Action Input. The Action Input must be a valid JSON string that contains all the arguments for the tool. Ensure the JSON string is properly formatted without extra characters or malformed brackets."),
            ("system", """Here is the exact format to use for tool calls:
Thought: I need to use the run_code_in_sandbox tool to execute the generated code.
Action: run_code_in_sandbox
Action Input: {{"llm_agent_id": "{llm_agent_id}", "code": "print('Hello, World!')", "base_image": "python:3.10-slim-bookworm"}}
"""),
            ("system", "You must ensure the Action Input is a valid JSON string. The `llm_agent_id` for this task is always: {llm_agent_id}. You must always include `llm_agent_id` in your Action Input."),
            ("system", "If the code fails, analyze the error message and modify the code. If the output is not as expected, debug and iterate. When you have successfully created the program that meets the requirements, output the final code in a markdown code block and signal completion with 'Final Answer: [Your Final Code]'."),
            ("system", "Available tool names: {tool_names}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
            HumanMessage(content="{input}"),
        ])

        # RunnableAgent の構築
        self.agent_runnable = (
            self.prompt_template.partial(
                tools=self.tools,
                tool_names=", ".join([t.name for t in self.tools]),
            )
            | self.llm
            | CustomAgentOutputParser()
        )
        
        self.agent = AgentExecutor(
            agent=self.agent_runnable,
            tools=self.tools,
            verbose=True,
        )

    def run_program_construction(self, user_requirement: str, llm_agent_id: str) -> str:
        print(f"ProgramConstructionAgent: Starting program construction for requirement: {user_requirement}")
        result = self.agent.invoke(
            {
                "input": user_requirement,
                "llm_agent_id": llm_agent_id,
                "agent_scratchpad": [],
            }
        )
        print(f"ProgramConstructionAgent: Program construction finished. Result: {result['output']}")
        return result['output']
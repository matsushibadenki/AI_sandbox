# program_builder/pco/agent.py
from langchain_ollama import ChatOllama
from langchain.agents import AgentExecutor
from langchain_core.prompts import PromptTemplate, MessagesPlaceholder, ChatPromptTemplate
from langchain_core.tools import Tool, BaseTool
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
        self.tools: List[BaseTool] = [
            sandbox_tool
        ]

        # プロンプトテンプレートの定義
        # ◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️↓修正開始◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️
        self.prompt_template = ChatPromptTemplate.from_messages([
            ("system", "You are an autonomous program construction agent. Your goal is to write, test, and debug Python or Node.js programs based on user requirements. Prioritize Python unless Node.js is explicitly requested or clearly more suitable."),
            ("system", "You have access to the following tools: {tools}"),
            ("system", "To use a tool, you must output your thought process, then explicitly state the Action and Action Input. The Action Input must be a valid JSON string that contains all the arguments for the tool. Ensure the JSON string is properly formatted without extra characters or malformed brackets."),
            ("system", """Here is the exact format to use for tool calls:
Thought: I need to write a Python program that prints a specific message and the current date/time.
Action: run_code_in_sandbox
Action Input: {{"llm_agent_id": "{llm_agent_id}", "code": "import datetime\\nprint('Hello, Autonomous AI Program Builder!')\\nprint(datetime.datetime.now())", "base_image": "python:3.10-slim-bookworm"}}
"""),
            ("system", "You must ensure the Action Input is a valid JSON string. The `llm_agent_id` for this task is always: {llm_agent_id}. You must always include `llm_agent_id` in your Action Input."),
            ("system", "Your primary goal is to fulfill the *original user requirement* completely and efficiently. Do not perform unnecessary 'Hello, World!' tests or similar generic steps unless they are explicitly part of the requirement or absolutely necessary for initial environment validation. Use the `agent_scratchpad` to track your progress, learn from past actions (both successes and failures), and avoid repeating steps that have already been completed or proven ineffective. Iterate on your code and approach based on observations."),
            ("system", "If the code fails, analyze the error message and modify the code. If the output is not as expected, debug and iterate. When you have successfully created the program that meets *all parts* of the requirements, output *only* the final code in a markdown code block and signal completion with 'Final Answer: [Your Final Code]'. Do not include any further thoughts or actions after the Final Answer."),
            ("system", "Available tool names: {tool_names}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
            HumanMessage(content="{input}"),
        ])
        # ◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️↑修正終わり◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️

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

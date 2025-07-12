# AI_sandbox/pco/agent.py
from langchain_ollama import ChatOllama
from langchain.agents import AgentExecutor
from langchain_core.prompts import PromptTemplate, MessagesPlaceholder, ChatPromptTemplate
from langchain_core.tools import Tool, BaseTool
from langchain_core.messages import AIMessage, HumanMessage
from typing import List, Dict, Any

from pco.tools import SandboxTool, ReadFileTool, WriteFileTool, ListInstalledPackagesTool, ListProcessesTool, CheckSyntaxTool, DiagnoseSandboxExecutionTool, ListDiskSpaceTool, DownloadFileTool, UploadFileTool, DownloadWebpageRecursivelyTool, FindFilesInSandboxTool, GrepFileContentInSandboxTool, GetSystemInfoTool
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
        # sandbox_tool はDIで渡される
        self.tools: List[BaseTool] = [
            sandbox_tool,
            ReadFileTool(sandbox_manager_service=sandbox_tool.sandbox_manager_service), # 同じサービスインスタンスを共有
            WriteFileTool(sandbox_manager_service=sandbox_tool.sandbox_manager_service), # 同じサービスインスタンスを共有
            ListInstalledPackagesTool(sandbox_manager_service=sandbox_tool.sandbox_manager_service), # 同じサービスインスタンスを共有
            ListProcessesTool(sandbox_manager_service=sandbox_tool.sandbox_manager_service), # 同じサービスインスタンスを共有
            CheckSyntaxTool(sandbox_manager_service=sandbox_tool.sandbox_manager_service), # 同じサービスインスタンスを共有
            DiagnoseSandboxExecutionTool(sandbox_manager_service=sandbox_tool.sandbox_manager_service), # 同じサービスインスタンスを共有
            ListDiskSpaceTool(sandbox_manager_service=sandbox_tool.sandbox_manager_service), # 同じサービスインスタンスを共有
            DownloadFileTool(sandbox_manager_service=sandbox_tool.sandbox_manager_service), # 新しいダウンロードツール
            UploadFileTool(sandbox_manager_service=sandbox_tool.sandbox_manager_service), # 新しいアップロードツール
            DownloadWebpageRecursivelyTool(sandbox_manager_service=sandbox_tool.sandbox_manager_service), # 新しいウェブページ再帰ダウンロードツール
            FindFilesInSandboxTool(sandbox_manager_service=sandbox_tool.sandbox_manager_service), # 新しいファイル検索ツール
            GrepFileContentInSandboxTool(sandbox_manager_service=sandbox_tool.sandbox_manager_service), # 新しいファイル内容検索ツール
            GetSystemInfoTool(sandbox_manager_service=sandbox_tool.sandbox_manager_service), # 新しいシステム情報取得ツール
        ]

        # プロンプトテンプレートの定義 (ReActフレームワークに基づき再構成)
        self.prompt_template = ChatPromptTemplate.from_messages([
            ("system", 
             "You are an autonomous program construction agent. Your primary goal is to fulfill the user's request by thinking step-by-step and using the available tools. "
             "Follow the ReAct (Reason+Act) framework: Thought, Action, Action Input, Observation.\n\n"
             "**INSTRUCTIONS:**\n"
             "1. **Analyze the Request**: Carefully understand the user's goal.\n"
             "2. **Think Step-by-Step (Thought)**: Before taking any action, you MUST use the 'Thought' field to explain your reasoning. Your thought process should include:\n"
             "   - Your understanding of the user's goal.\n"
             "   - A plan to achieve the goal, broken down into small, manageable steps.\n"
             "   - The specific tool you will use for the *next* step and why.\n"
             "3. **Choose an Action**: Select ONE tool from the available tools list: {tool_names}.\n"
             "4. **Provide Action Input**: Provide the required arguments for the chosen tool in a valid JSON format.\n"
             "5. **Wait for Observation**: After your action, you will receive an 'Observation' with the result of the tool's execution. Use this observation to inform your next thought and action.\n"
             "6. **Iterate**: Repeat the Thought-Action-Observation cycle until the user's request is fully completed.\n"
             "7. **Final Answer**: Once the goal is achieved, you MUST use the 'Final Answer:' prefix to provide the final result or code to the user. Do not include any 'Thought' or 'Action' after the 'Final Answer:'.\n\n"
             "**IMPORTANT RULES:**\n"
             "- **One Action at a Time**: You can only perform one action at a time.\n"
             "- **Use `llm_agent_id`**: Always include the `llm_agent_id`: `{llm_agent_id}` in your `Action Input`.\n"
             "- **Use Shared Directory**: All file operations are relative to the shared directory: `{shared_dir_path}`. Use this path when executing scripts (e.g., `python {shared_dir_path}/my_script.py`).\n"
             "- **Conversational Replies**: If the user's request is a simple greeting or a question that doesn't require tools, respond directly in a conversational manner using the 'Final Answer:' prefix (e.g., 'Final Answer: Hello! How can I help you today?').\n\n"
             "**AVAILABLE TOOLS:**\n{tools}\n"
             ),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
            HumanMessage(content="{input}"),
        ])

        # RunnableAgent の構築
        self.agent_runnable = (
            self.prompt_template.partial(
                tools=self.tools,
                tool_names=", ".join([t.name for t in self.tools]),
                shared_dir_path=config.SHARED_DIR_CONTAINER_PATH,
            )
            | self.llm
            | CustomAgentOutputParser()
        )

        self.agent = AgentExecutor(
            agent=self.agent_runnable,
            tools=self.tools,
            verbose=True,
            handle_parsing_errors=True, # パースエラーをハンドルして再試行させる
            max_iterations=15 # エージェントの無限ループを防ぐための反復回数制限
        )

    def run_program_construction(self, user_requirement: str, llm_agent_id: str) -> str:
        print(f"ProgramConstructionAgent: Starting program construction for requirement: {user_requirement}")
        try:
            result = self.agent.invoke(
                {
                    "input": user_requirement,
                    "llm_agent_id": llm_agent_id,
                    "agent_scratchpad": [],
                }
            )
            print(f"ProgramConstructionAgent: Program construction finished. Result: {result['output']}")
            return result['output']
        except Exception as e:
            print(f"ProgramConstructionAgent: An unhandled error occurred in AgentExecutor: {e}")
            return f"I'm sorry, an internal error occurred. Please try your request again. Details: {e}"
# AI_sandbox/pco/agent.py
from langchain_ollama import ChatOllama
from langchain.agents import AgentExecutor
from langchain_core.prompts import PromptTemplate, MessagesPlaceholder, ChatPromptTemplate
from langchain_core.tools import Tool, BaseTool
from langchain_core.messages import AIMessage, HumanMessage
from typing import List, Dict, Any

# ◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️↓修正開始◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️
from pco.tools import SandboxTool, ReadFileTool, WriteFileTool, ListInstalledPackagesTool, ListProcessesTool, CheckSyntaxTool, DiagnoseSandboxExecutionTool, ListDiskSpaceTool # 新しいツールをインポート
# ◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️↑修正終わり◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️
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

        # ◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️↓修正開始◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️
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
        ]
        # ◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️↑修正終わり◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️

        # プロンプトテンプレートの定義
        self.prompt_template = ChatPromptTemplate.from_messages([
            ("system", "You are an autonomous program construction agent. Your goal is to write, test, and debug Python or Node.js programs based on user requirements. Prioritize Python unless Node.js is explicitly requested or clearly more suitable."),
            ("system", "You have access to the following tools: {tools}"),
            ("system", "To use a tool, you must output your thought process, then explicitly state the Action and Action Input. The Action Input must be a valid JSON string that contains all the arguments for the tool. Ensure the JSON string is properly formatted without extra characters or malformed brackets."),
            # 修正: プロンプトの例を、永続的なサンドボックスでのファイル操作とコード実行のより複雑なシナリオを反映するように更新
            ("system", """Here is the exact format to use for tool calls:
Thought: I need to create a Python file, write some code into it, and then execute it using the persistent sandbox.
Action: write_file_in_sandbox
Action Input: {{"llm_agent_id": "{llm_agent_id}", "file_path": "my_program.py", "content": "import datetime\\nprint(\\"Hello, Persistent Sandbox!\\")\\nprint(datetime.datetime.now())"}}
Thought: Now that the file is created, I need to read its content to verify it.
Action: read_file_in_sandbox
Action Input: {{"llm_agent_id": "{llm_agent_id}", "file_path": "my_program.py"}}
Thought: I have verified the file content. Now I will execute the script using the run_code_in_sandbox tool.
Action: run_code_in_sandbox
Action Input: {{"llm_agent_id": "{llm_agent_id}", "code": "python {shared_dir_path}/my_program.py", "base_image": "python:3.10-slim-bookworm"}}
"""),
            ("system", "You must ensure the Action Input is a valid JSON string. The `llm_agent_id` for this task is always: {llm_agent_id}. You must always include `llm_agent_id` in your Action Input."),
            ("system", "Your primary goal is to fulfill the *original user requirement* completely and efficiently. Do not perform unnecessary 'Hello, World!' tests or similar generic steps unless they are explicitly part of the requirement or absolutely necessary for initial environment validation. Use the `agent_scratchpad` to track your progress, learn from past actions (both successes and failures), and avoid repeating steps that have already been completed or proven ineffective. Iterate on your code and approach based on observations."),
            ("system", "If the code fails, analyze the error message and modify the code. If the output is not as expected, debug and iterate. When you have successfully created the program that meets *all parts* of the requirements, output *only* the final code in a markdown code block and signal completion with 'Final Answer: [Your Final Code]'. Do not include any further thoughts or actions after the Final Answer."),
            # ◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️↓修正開始◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️
            ("system", "Available tool names: {tool_names}. Use `read_file_in_sandbox` to get file content and `write_file_in_sandbox` to create/modify files. Use `list_installed_packages_in_sandbox` to check installed language packages and `list_processes_in_sandbox` to view running processes. Use `check_syntax_in_sandbox` to perform syntax checking on a file. Use `list_disk_space_in_sandbox` to check disk usage. If a sandbox execution fails, use `diagnose_sandbox_execution_result` with the exit code, error message, output, and optionally the language to get debugging suggestions. For executing general shell commands or Python/Node.js scripts, use `run_code_in_sandbox`."),
            # ◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️↑修正終わり◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾
            # 修正: 共有ディレクトリと永続性に関する指示を強調
            ("system", "You have access to a shared directory mounted at `{shared_dir_path}` inside the sandbox. This directory is for you to manage project files, download external code, and persist changes. **Crucially, the sandbox session for your `llm_agent_id` is persistent across `run_code_in_sandbox` calls. This means any files you create, packages you install, or changes you make within the sandbox will persist for subsequent executions.** You can use standard shell commands (e.g., `ls`, `cd`, `cat`, `echo`, `mkdir`, `rm`, `cp`, `mv`, `pip install`, `npm install`) within the `run_code_in_sandbox` tool to interact with files and directories and manage your environment in this shared space. Remember to always specify paths relative to `{shared_dir_path}` when operating within this directory."),
            ("system", "For GitHub operations like cloning repositories, you should use shell commands suchs as `git clone <repository_url> {shared_dir_path}/<destination_folder>` inside the `run_code_in_sandbox` tool. Please ensure that the `base_image` you select for the sandbox (e.g., `ubuntu/git` or a custom image you know contains `git`) has the `git` command installed if you intend to perform `git` operations. If `git` is not available in the chosen `base_image`, you should inform the user."),
            ("system", "When you need to examine the content of the shared directory, you can use `ls -F {shared_dir_path}`. To read a file, use `cat {shared_dir_path}/path/to/file.py`. To modify or create a file, you might use `echo 'new content' > {shared_dir_path}/path/to/file.py` or a more complex script depending on the modification. To install Python packages, use `pip install <package_name>`. To install Node.js packages, use `npm install <package_name>`."),
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
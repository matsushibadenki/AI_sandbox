# AI_sandbox/pco/tools.py
import json
import uuid # <-- 先頭に移動: here-document のユニークなマーカー生成用
from typing import Any, Dict, Optional, Type, Union

from langchain.tools import BaseTool
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field, ValidationError

from config import config
from database.models import SandboxStatus
from sandbox_manager.service import SandboxManagerService


# LLMからの入力スキーマ
class RunCodeInSandboxInput(BaseModel):
    llm_agent_id: str = Field(description="The unique ID of the LLM agent requesting the sandbox operation.")
    code: str = Field(description="The Python or Node.js code to execute in the sandbox.")
    base_image: Optional[str] = Field(default=None, description="Optional. The Docker image to use for the sandbox (e.g., 'python:3.10-slim-bookworm', 'node:18'). Defaults to system config if not provided.")


class ReadFileInput(BaseModel):
    llm_agent_id: str = Field(description="The unique ID of the LLM agent for the persistent sandbox session.")
    file_path: str = Field(description="The path to the file to read, relative to the shared directory (e.g., 'my_program.py').")

class WriteFileInput(BaseModel):
    llm_agent_id: str = Field(description="The unique ID of the LLM agent for the persistent sandbox session.")
    file_path: str = Field(description="The path to the file to write, relative to the shared directory (e.g., 'my_program.py').")
    content: str = Field(description="The content to write to the file. For multi-line content, ensure newlines are properly escaped (e.g., '\\n').")
    append: bool = Field(default=False, description="If true, content will be appended to the file. Otherwise, the file will be overwritten.")


class ListInstalledPackagesInput(BaseModel):
    llm_agent_id: str = Field(description="The unique ID of the LLM agent for the persistent sandbox session.")
    language: Optional[str] = Field(default=None, description="Optional. The programming language to list packages for (e.g., 'python', 'nodejs'). If not specified, attempts to list for common languages.")

class ListProcessesInput(BaseModel):
    llm_agent_id: str = Field(description="The unique ID of the LLM agent for the persistent sandbox session.")


class CheckSyntaxInput(BaseModel):
    llm_agent_id: str = Field(description="The unique ID of the LLM agent for the persistent sandbox session.")
    file_path: str = Field(description="The path to the file to check, relative to the shared directory (e.g., 'my_script.py').")
    language: str = Field(description="The programming language of the file ('python' or 'nodejs').")


class DiagnoseSandboxExecutionInput(BaseModel):
    llm_agent_id: str = Field(description="The unique ID of the LLM agent for the persistent sandbox session.")
    exit_code: int = Field(description="The exit code of the sandbox execution.")
    error_message: Optional[str] = Field(default=None, description="The error message from the sandbox execution (stderr).")
    execution_output: Optional[str] = Field(default=None, description="The standard output from the sandbox execution (stdout).")
    language: Optional[str] = Field(default=None, description="Optional. The programming language context of the executed code (e.g., 'python', 'nodejs').")

class ListDiskSpaceInput(BaseModel):
    llm_agent_id: str = Field(description="The unique ID of the LLM agent for the persistent sandbox session.")


class SandboxTool(BaseTool):
    name: str = "run_code_in_sandbox"
    # Description updated to reflect persistence
    description: str = "Executes Python or Node.js code in an isolated, *persistent* Docker sandbox session for the given `llm_agent_id`. The sandbox state (files, installed packages) persists across calls. Provide the full code string."
    args_schema: Type[BaseModel] = RunCodeInSandboxInput
    sandbox_manager_service: SandboxManagerService # DIを通じて注入される

    def _run(self, llm_agent_id: str, code: str, base_image: Optional[str] = None, run_manager: Optional[RunnableConfig] = None) -> str:
        """サンドボックスでコードを実行し、結果を返します。永続的なセッションを利用/管理します。"""
        print(f"SandboxTool: LLM agent {llm_agent_id} requested sandbox execution (persistent session).")
        try:
            # 変更点: 新しいサービスメソッドを呼び出す
            sandbox_entry = self.sandbox_manager_service.provision_and_execute_sandbox_session(
                llm_agent_id=llm_agent_id,
                code=code,
                base_image=base_image
            )

            if sandbox_entry.status == SandboxStatus.SUCCESS:
                return f"Sandbox execution succeeded.\nOutput:\n{sandbox_entry.execution_result}"
            else:
                error_detail = sandbox_entry.error_message if sandbox_entry.error_message else "No specific error message."
                output_detail = sandbox_entry.execution_result if sandbox_entry.execution_result else "No specific output."
                return (f"Sandbox execution failed with exit code {sandbox_entry.exit_code}.\n"
                        f"Error:\n{error_detail}\n"
                        f"Output:\n{output_detail}")
        except Exception as e:
            return f"Error managing or running persistent sandbox: {str(e)}"

    async def _arun(self, llm_agent_id: str, code: str, base_image: Optional[str] = None, run_manager: Optional[RunnableConfig] = None) -> str:
        """非同期サンドボックスでコードを実行し、結果を返します。永続的なセッションを利用/管理します。"""
        return self._run(llm_agent_id=llm_agent_id, code=code, base_image=base_image, run_manager=run_manager)


class ReadFileTool(BaseTool):
    name: str = "read_file_in_sandbox"
    description: str = "Reads the content of a file from the persistent sandbox's shared directory. Provide the path to the file relative to the shared directory."
    args_schema: Type[BaseModel] = ReadFileInput
    sandbox_manager_service: SandboxManagerService

    def _run(self, llm_agent_id: str, file_path: str, run_manager: Optional[RunnableConfig] = None) -> str:
        full_path = f"{config.SHARED_DIR_CONTAINER_PATH}/{file_path.lstrip('/')}"
        command = f"cat {full_path}"
        print(f"ReadFileTool: LLM agent {llm_agent_id} requested to read file: {full_path}")
        try:
            sandbox_entry = self.sandbox_manager_service.provision_and_execute_sandbox_session(
                llm_agent_id=llm_agent_id,
                code=command # catコマンドを実行
            )
            if sandbox_entry.status == SandboxStatus.SUCCESS:
                return f"File content:\n{sandbox_entry.execution_result}"
            else:
                error_detail = sandbox_entry.error_message if sandbox_entry.error_message else "No specific error message."
                output_detail = sandbox_entry.execution_result if sandbox_entry.execution_result else "No specific output."
                return (f"Failed to read file {file_path}.\n"
                        f"Error:\n{error_detail}\n"
                        f"Output:\n{output_detail}")
        except Exception as e:
            return f"Error reading file from persistent sandbox: {str(e)}"

    async def _arun(self, llm_agent_id: str, file_path: str, run_manager: Optional[RunnableConfig] = None) -> str:
        return self._run(llm_agent_id=llm_agent_id, file_path=file_path, run_manager=run_manager)

class WriteFileTool(BaseTool):
    name: str = "write_file_in_sandbox"
    description: str = "Writes content to a file in the persistent sandbox's shared directory. Provide the path to the file relative to the shared directory and the content to write. Use `append=True` to append."
    args_schema: Type[BaseModel] = WriteFileInput
    sandbox_manager_service: SandboxManagerService

    def _run(self, llm_agent_id: str, file_path: str, content: str, append: bool = False, run_manager: Optional[RunnableConfig] = None) -> str:
        full_path = f"{config.SHARED_DIR_CONTAINER_PATH}/{file_path.lstrip('/')}"
        
        # 使用するリダイレクト演算子を決定
        redirect_operator = ">>" if append else ">"
        
        # ◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️↓修正開始◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️
        # here-document を使用して、安全にマルチラインのコンテンツをファイルに書き込む
        # EOF マーカーをユニークにするために UUID を利用（衝突リスクをさらに減らすため）
        eof_marker = "EOF_" + str(uuid.uuid4()).replace('-', '') # ユニークなEOFマーカーを生成

        # f-string を完全に避け、純粋な文字列連結でコマンドを構築
        command = (
            "bash -c 'cat <<" + eof_marker + "\n"
            + content + "\n" +
            eof_marker + " " + redirect_operator + " " + full_path + "'"
        )
        # ◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️↑修正終わり◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️
        
        print(f"WriteFileTool: LLM agent {llm_agent_id} requested to write to file: {full_path}, append: {append}")
        try:
            sandbox_entry = self.sandbox_manager_service.provision_and_execute_sandbox_session(
                llm_agent_id=llm_agent_id,
                code=command
            )
            if sandbox_entry.status == SandboxStatus.SUCCESS:
                return f"Successfully {'appended to' if append else 'wrote to'} file {file_path}. Output:\n{sandbox_entry.execution_result}"
            else:
                error_detail = sandbox_entry.error_message if sandbox_entry.error_message else "No specific error message."
                output_detail = sandbox_entry.execution_result if sandbox_entry.execution_result else "No specific output."
                return (f"Failed to {'append to' if append else 'write to'} file {file_path}.\n"
                        f"Error:\n{error_detail}\n"
                        f"Output:\n{output_detail}")
        except Exception as e:
            return f"Error writing to file in persistent sandbox: {str(e)}"

    async def _arun(self, llm_agent_id: str, file_path: str, content: str, append: bool = False, run_manager: Optional[RunnableConfig] = None) -> str:
        return self._run(llm_agent_id=llm_agent_id, file_path=file_path, content=content, append=append, run_manager=run_manager)


class ListInstalledPackagesTool(BaseTool):
    name: str = "list_installed_packages_in_sandbox"
    description: str = "Lists installed packages in the persistent sandbox environment. Specify 'python' or 'nodejs' for language."
    args_schema: Type[BaseModel] = ListInstalledPackagesInput
    sandbox_manager_service: SandboxManagerService

    def _run(self, llm_agent_id: str, language: Optional[str] = None, run_manager: Optional[RunnableConfig] = None) -> str:
        command = ""
        if language == "python":
            command = "pip list"
        elif language == "nodejs":
            command = "npm list --depth=0" # 依存関係の深さを0に制限して、トップレベルのパッケージのみを表示
        else:
            # 言語が指定されていない場合、両方を試みるか、エラーを返す
            # ここでは両方を試みる例を示す
            return self._run(llm_agent_id, "python") + "\n---\n" + self._run(llm_agent_id, "nodejs")

        if not command:
            return "Error: Please specify 'python' or 'nodejs' as the language to list installed packages."

        print(f"ListInstalledPackagesTool: LLM agent {llm_agent_id} requested to list packages for {language or 'all'}.")
        try:
            sandbox_entry = self.sandbox_manager_service.provision_and_execute_sandbox_session(
                llm_agent_id=llm_agent_id,
                code=command
            )
            if sandbox_entry.status == SandboxStatus.SUCCESS:
                return f"Installed {language or 'all'} packages:\n{sandbox_entry.execution_result}"
            else:
                error_detail = sandbox_entry.error_message if sandbox_entry.error_message else "No specific error message."
                output_detail = sandbox_entry.execution_result if sandbox_entry.execution_result else "No specific output."
                return (f"Failed to list installed {language or 'all'} packages.\n"
                        f"Error:\n{error_detail}\n"
                        f"Output:\n{output_detail}")
        except Exception as e:
            return f"Error listing installed packages from persistent sandbox: {str(e)}"

    async def _arun(self, llm_agent_id: str, language: Optional[str] = None, run_manager: Optional[RunnableConfig] = None) -> str:
        return self._run(llm_agent_id=llm_agent_id, language=language, run_manager=run_manager)

class ListProcessesTool(BaseTool):
    name: str = "list_processes_in_sandbox"
    description: str = "Lists running processes within the persistent sandbox environment using 'ps aux'."
    args_schema: Type[BaseModel] = ListProcessesInput
    sandbox_manager_service: SandboxManagerService

    def _run(self, llm_agent_id: str, run_manager: Optional[RunnableConfig] = None) -> str:
        command = "ps aux"
        print(f"ListProcessesTool: LLM agent {llm_agent_id} requested to list processes.")
        try:
            sandbox_entry = self.sandbox_manager_service.provision_and_execute_sandbox_session(
                llm_agent_id=llm_agent_id,
                code=command
            )
            if sandbox_entry.status == SandboxStatus.SUCCESS:
                return f"Running processes:\n{sandbox_entry.execution_result}"
            else:
                error_detail = sandbox_entry.error_message if sandbox_entry.error_message else "No specific error message."
                output_detail = sandbox_entry.execution_result if sandbox_entry.execution_result else "No specific output."
                return (f"Failed to list processes.\n"
                        f"Error:\n{error_detail}\n"
                        f"Output:\n{output_detail}")
        except Exception as e:
            return f"Error listing processes from persistent sandbox: {str(e)}"

    async def _arun(self, llm_agent_id: str, run_manager: Optional[RunnableConfig] = None) -> str:
        return self._run(llm_agent_id=llm_agent_id, run_manager=run_manager)


class CheckSyntaxTool(BaseTool):
    name: str = "check_syntax_in_sandbox"
    description: str = "Checks the syntax of a specified file in the persistent sandbox. Supports 'python' (using py_compile) and 'nodejs' (using 'node -c')."
    args_schema: Type[BaseModel] = CheckSyntaxInput
    sandbox_manager_service: SandboxManagerService

    def _run(self, llm_agent_id: str, file_path: str, language: str, run_manager: Optional[RunnableConfig] = None) -> str:
        full_path = f"{config.SHARED_DIR_CONTAINER_PATH}/{file_path.lstrip('/')}"
        command = ""

        if language == "python":
            command = f"python -m py_compile {full_path}"
        elif language == "nodejs":
            command = f"node -c {full_path}"
        else:
            return f"Error: Unsupported language '{language}'. Please specify 'python' or 'nodejs'."

        print(f"CheckSyntaxTool: LLM agent {llm_agent_id} requested syntax check for {full_path} ({language}).")
        try:
            sandbox_entry = self.sandbox_manager_service.provision_and_execute_sandbox_session(
                llm_agent_id=llm_agent_id,
                code=command
            )
            
            # 終了コードが0なら成功、そうでなければエラー
            if sandbox_entry.exit_code == 0:
                return f"Syntax check for {file_path} ({language}) succeeded. No syntax errors found."
            else:
                error_detail = sandbox_entry.error_message if sandbox_entry.error_message else "No specific error message."
                output_detail = sandbox_entry.execution_result if sandbox_entry.execution_result else "No specific output."
                return (f"Syntax check for {file_path} ({language}) failed with exit code {sandbox_entry.exit_code}.\n"
                        f"Error:\n{error_detail}\n"
                        f"Output:\n{output_detail}")
        except Exception as e:
            return f"Error performing syntax check in persistent sandbox: {str(e)}"

    async def _arun(self, llm_agent_id: str, file_path: str, language: str, run_manager: Optional[RunnableConfig] = None) -> str:
        return self._run(llm_agent_id=llm_agent_id, file_path=file_path, language=language, run_manager=run_manager)


class DiagnoseSandboxExecutionTool(BaseTool):
    name: str = "diagnose_sandbox_execution_result"
    description: str = "Provides common debugging suggestions based on the exit code, error message, and output of a failed sandbox execution. Useful when the `run_code_in_sandbox` tool returns a non-zero exit code."
    args_schema: Type[BaseModel] = DiagnoseSandboxExecutionInput
    sandbox_manager_service: SandboxManagerService # このツールはサンドボックスを実行しないが、一貫性のため DI に含める

    def _run(self, llm_agent_id: str, exit_code: int, error_message: Optional[str] = None, execution_output: Optional[str] = None, language: Optional[str] = None, run_manager: Optional[RunnableConfig] = None) -> str:
        diagnosis_results = [f"Diagnosis for sandbox execution (Agent ID: {llm_agent_id}, Exit Code: {exit_code}):"]

        if exit_code != 0:
            diagnosis_results.append(f"  - Execution failed with a non-zero exit code ({exit_code}). This indicates an error during execution.")

        if error_message:
            indented_error = error_message.strip().replace("\n", "\n    ")
            diagnosis_results.append(f"  - Error Message (stderr):\n    {indented_error}")


        if execution_output:
            indented_output = execution_output.strip().replace("\n", "\n    ")
            diagnosis_results.append(f"  - Standard Output (stdout):\n    {indented_output}")
        
        # 一般的なエラーパターンに基づく診断
        if error_message:
            error_message_lower = error_message.lower()
            if "command not found" in error_message_lower or "not found" in error_message_lower and (exit_code == 127 or exit_code == 1):
                diagnosis_results.append("  - **Suggestion**: The command or executable might not be installed in the sandbox, or it's not in the system's PATH. Consider installing it (e.g., `pip install <package>` for Python, `npm install <package>` for Node.js) or verifying the command name/path.")
            elif "permission denied" in error_message_lower:
                diagnosis_results.append("  - **Suggestion**: This indicates a file/directory permission issue. Check if the script has execute permissions (`chmod +x script.sh`) or if the target directory is writable.")
            elif "no such file or directory" in error_message_lower:
                diagnosis_results.append("  - **Suggestion**: The specified file or directory does not exist or the path is incorrect. Verify the file path and ensure it's relative to the shared directory if applicable.")
            elif "memory limit" in error_message_lower or "killed" in error_message_lower:
                diagnosis_results.append("  - **Suggestion**: The sandbox might have run out of memory or other resources. Consider optimizing the code's resource usage or if necessary, inform the user about resource limitations.")
            elif "exit code 137" == error_message_lower or (exit_code == 137): # Docker killed container due to OOM/timeout
                diagnosis_results.append("  - **Suggestion**: Exit code 137 often indicates the container was killed (e.g., due to an Out-Of-Memory error or timeout). Check resource usage of your code and sandbox limits.")
            elif "timeout" in error_message_lower or "max time" in error_message_lower:
                diagnosis_results.append("  - **Suggestion**: The execution exceeded the maximum allowed time. Optimize the code for performance or break down complex tasks.")
            
            # 言語固有のヒント
            if language == "python":
                if "syntaxerror" in error_message_lower:
                    diagnosis_results.append("  - **Python Specific**: SyntaxError. Check for mismatched parentheses, colons, or invalid syntax. Use `check_syntax_in_sandbox`.")
                elif "nameerror" in error_message_lower:
                    diagnosis_results.append("  - **Python Specific**: NameError. A variable or function name was used before it was defined. Check for typos.")
                elif "modulenotfounderror" in error_message_lower:
                    diagnosis_results.append("  - **Python Specific**: ModuleNotFoundError. A required library is not installed. Use `pip install <module_name>`.")
                elif "importerror" in error_message_lower:
                    diagnosis_results.append("  - **Python Specific**: ImportError. Similar to ModuleNotFoundError, but might be an issue with a specific import within a package.")
            elif language == "nodejs":
                if "syntaxerror" in error_message_lower:
                    diagnosis_results.append("  - **Node.js Specific**: SyntaxError. Check for common JavaScript syntax mistakes like missing semicolons, unmatched braces, or invalid keywords. Use `check_syntax_in_sandbox`.")
                elif "referenceerror" in error_message_lower:
                    diagnosis_results.append("  - **Node.js Specific**: ReferenceError. A variable or function was accessed but not defined. Check variable scope and typos.")
                elif "typeerror" in error_message_lower:
                    diagnosis_results.append("  - **Node.js Specific**: TypeError. An operation was performed on a value that is not of the expected type (e.g., calling a non-function).")
                elif "cannot find module" in error_message_lower:
                    diagnosis_results.append("  - **Node.js Specific**: Cannot find module. A required npm package is not installed. Use `npm install <package_name>`.")
            
            if not any(suggestion.startswith("  - **Suggestion**") or suggestion.startswith("  - **Python Specific**") or suggestion.startswith("  - **Node.js Specific**") for suggestion in diagnosis_results[1:]):
                diagnosis_results.append("  - **General Suggestion**: Analyze the full error message and output carefully. Break down the task into smaller steps and execute them incrementally to isolate the problem.")
        else:
            diagnosis_results.append("  - No specific error message provided. Check the standard output for clues.")

        return "\n".join(diagnosis_results)

    async def _arun(self, llm_agent_id: str, exit_code: int, error_message: Optional[str] = None, execution_output: Optional[str] = None, language: Optional[str] = None, run_manager: Optional[RunnableConfig] = None) -> str:
        return self._run(llm_agent_id=llm_agent_id, exit_code=exit_code, error_message=error_message, execution_output=execution_output, language=language, run_manager=run_manager)


class ListDiskSpaceTool(BaseTool):
    name: str = "list_disk_space_in_sandbox"
    description: str = "Lists the disk space usage of the shared directory in the persistent sandbox environment using 'df -h'."
    args_schema: Type[BaseModel] = ListDiskSpaceInput
    sandbox_manager_service: SandboxManagerService

    def _run(self, llm_agent_id: str, run_manager: Optional[RunnableConfig] = None) -> str:
        command = f"df -h {config.SHARED_DIR_CONTAINER_PATH}"
        print(f"ListDiskSpaceTool: LLM agent {llm_agent_id} requested to list disk space.")
        try:
            sandbox_entry = self.sandbox_manager_service.provision_and_execute_sandbox_session(
                llm_agent_id=llm_agent_id,
                code=command
            )
            if sandbox_entry.status == SandboxStatus.SUCCESS:
                return f"Disk space usage in {config.SHARED_DIR_CONTAINER_PATH}:\n{sandbox_entry.execution_result}"
            else:
                error_detail = sandbox_entry.error_message if sandbox_entry.error_message else "No specific error message."
                output_detail = sandbox_entry.execution_result if sandbox_entry.execution_result else "No specific output."
                return (f"Failed to list disk space.\n"
                        f"Error:\n{error_detail}\n"
                        f"Output:\n{output_detail}")
        except Exception as e:
            return f"Error listing disk space from persistent sandbox: {str(e)}"

    async def _arun(self, llm_agent_id: str, run_manager: Optional[RunnableConfig] = None) -> str:
        return self._run(llm_agent_id=llm_agent_id, run_manager=run_manager)
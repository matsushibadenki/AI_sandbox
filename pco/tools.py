# AI_sandbox/pco/tools.py
import json
import uuid
import os 
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

class DownloadFileInput(BaseModel):
    llm_agent_id: str = Field(description="The unique ID of the LLM agent for the persistent sandbox session.")
    url: str = Field(description="The URL of the file to download (e.g., 'https://example.com/data.json').")
    destination_path: str = Field(description="The path in the shared directory where the file should be saved (e.g., 'downloaded_data/data.json').")
    headers: Optional[str] = Field(default=None, description="Optional. A JSON string of HTTP headers to include (e.g., '{{\"Authorization\": \"Bearer token\"}}').")
    method: str = Field(default="GET", description="Optional. The HTTP method to use (e.g., 'GET', 'POST'). Defaults to 'GET'.")
    base_image: Optional[str] = Field(default=None, description="Optional. The Docker image to use for the sandbox. It should include `curl`. Defaults to system config if not provided.")

class UploadFileInput(BaseModel):
    llm_agent_id: str = Field(description="The unique ID of the LLM agent for the persistent sandbox session.")
    file_path: str = Field(description="The path to the file in the shared directory to upload (e.g., 'my_results.txt').")
    destination_url: str = Field(description="The URL to upload the file to (e.g., 'https://api.example.com/upload').")
    headers: Optional[str] = Field(default=None, description="Optional. A JSON string of HTTP headers to include (e.g., '{{\"Content-Type\": \"application/json\"}}').")
    method: str = Field(default="POST", description="Optional. The HTTP method to use (e.g., 'POST', 'PUT'). Defaults to 'POST'.")
    base_image: Optional[str] = Field(default=None, description="Optional. The Docker image to use for the sandbox. It should include `curl`. Defaults to system config if not provided.")

class DownloadWebpageRecursivelyInput(BaseModel):
    llm_agent_id: str = Field(description="The unique ID of the LLM agent for the persistent sandbox session.")
    url: str = Field(description="The base URL of the webpage to download (e.g., 'https://example.com/blog').")
    destination_dir: str = Field(description="The path in the shared directory where the downloaded content should be saved (e.g., 'downloaded_blog').")
    max_depth: int = Field(default=5, description="Optional. Maximum recursion depth for downloading linked resources. Defaults to 5. Set to 0 for just the base page.")
    accept_regex: Optional[str] = Field(default=None, description="Optional. A regex pattern to filter files to download (e.g., '.(html|css|js|png|jpg|gif)$').")
    base_image: Optional[str] = Field(default=None, description="Optional. The Docker image to use for the sandbox. It should include `wget`. Defaults to system config if not provided.")

class FindFilesInSandboxInput(BaseModel):
    llm_agent_id: str = Field(description="The unique ID of the LLM agent for the persistent sandbox session.")
    search_path: str = Field(description="The path within the shared directory to start the search (e.g., '.', 'my_project/src').")
    name_pattern: Optional[str] = Field(default=None, description="Optional. A pattern to match file names (e.g., '*.py', 'test_*.js').")
    file_type: Optional[str] = Field(default=None, description="Optional. Type of file to search for ('f' for file, 'd' for directory, 'l' for symbolic link).")
    max_depth: Optional[int] = Field(default=None, description="Optional. Maximum depth of directories to search.")

class GrepFileContentInSandboxInput(BaseModel):
    llm_agent_id: str = Field(description="The unique ID of the LLM agent for the persistent sandbox session.")
    file_path: str = Field(description="The path to the file or directory (relative to shared directory) to search within. If a directory, `recursive` must be true.")
    pattern: str = Field(description="The string or regex pattern to search for.")
    recursive: bool = Field(default=False, description="If true, searches recursively within directories.")
    case_insensitive: bool = Field(default=False, description="If true, performs a case-insensitive search.")
    line_numbers: bool = Field(default=False, description="If true, prints line numbers with output.")

class GetSystemInfoInput(BaseModel):
    llm_agent_id: str = Field(description="The unique ID of the LLM agent for the persistent sandbox session.")
    info_type: str = Field(
        description="Type of system information to retrieve: 'os_and_cpu' (OS type, kernel, CPU info), 'memory' (memory usage)."
    )


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
        command = f"cat \"{full_path}\"" # パスをダブルクォートで囲む
        print(f"ReadFileTool: LLM agent {llm_agent_id} requested to read file: {full_path}")
        try:
            sandbox_entry = self.sandbox_manager_service.provision_and_execute_sandbox_session(
                llm_agent_id=llm_agent_id,
                code=command
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
        
        redirect_operator = ">>" if append else ">"
        
        # ディレクトリが存在しない場合は作成するコマンドを前置
        dest_dir = os.path.dirname(full_path)
        mkdir_cmd = ""
        if dest_dir and dest_dir != config.SHARED_DIR_CONTAINER_PATH:
            mkdir_cmd = f"mkdir -p \"{dest_dir}\" && "

        # contentを16進数でエンコードし、xxd -r -p でデコードしてファイルに書き込む
        # これが最もシェル特殊文字に対して堅牢な方法
        encoded_content = content.encode('utf-8').hex()
        
        command_script = (
            f"{mkdir_cmd}echo '{encoded_content}' | xxd -r -p {redirect_operator} \"{full_path}\""
        )
            
        print(f"WriteFileTool: LLM agent {llm_agent_id} requested to write to file: {full_path}, append: {append}")
        try:
            sandbox_entry = self.sandbox_manager_service.provision_and_execute_sandbox_session(
                llm_agent_id=llm_agent_id,
                code=command_script,
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
            command = f"python -m py_compile \"{full_path}\""
        elif language == "nodejs":
            command = f"node -c \"{full_path}\""
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
        command = f"df -h \"{config.SHARED_DIR_CONTAINER_PATH}\"" # パスをダブルクォートで囲む
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

class DownloadFileTool(BaseTool):
    name: str = "download_file_from_internet"
    description: str = "Downloads a file from a specified URL to a path within the persistent sandbox's shared directory. Allows custom HTTP headers and methods. Requires a base image with `curl` installed. Returns HTTP status code upon completion."
    args_schema: Type[BaseModel] = DownloadFileInput
    sandbox_manager_service: SandboxManagerService

    def _run(self, llm_agent_id: str, url: str, destination_path: str, headers: Optional[str] = None, method: str = "GET", base_image: Optional[str] = None, run_manager: Optional[RunnableConfig] = None) -> str:
        full_dest_path = f"{config.SHARED_DIR_CONTAINER_PATH}/{destination_path.lstrip('/')}"
        
        # まずディレクトリが存在するか確認し、なければ作成する
        dest_dir = os.path.dirname(full_dest_path) # os.path.dirname を使用
        if dest_dir and dest_dir != config.SHARED_DIR_CONTAINER_PATH: # ルートディレクトリ自体でなければ
            mkdir_command = f"mkdir -p \"{dest_dir}\"" # ダブルクォートで囲む
            print(f"DownloadFileTool: Ensuring directory {dest_dir} exists.")
            mkdir_entry = self.sandbox_manager_service.provision_and_execute_sandbox_session(
                llm_agent_id=llm_agent_id,
                code=mkdir_command,
                base_image=base_image
            )
            if mkdir_entry.exit_code != 0:
                return f"Failed to create destination directory {dest_dir}. Error: {mkdir_entry.error_message}. Output: {mkdir_entry.execution_result}"

        # ヘッダーをパースしてcurlコマンドに追加
        header_commands = []
        if headers:
            try:
                headers_dict = json.loads(headers)
                for key, value in headers_dict.items():
                    header_commands.append(f"-H '{key}: {value}'")
            except json.JSONDecodeError:
                return f"Error: Invalid JSON format for headers: {headers}"
        header_str = " ".join(header_commands)

        # curl を使用してファイルをダウンロード
        # -sSL: silent, show errors, follow redirects
        # -X {method}: HTTPメソッドを指定
        # -o {full_dest_path}: 出力ファイルパス (ダブルクォートで囲む)
        # -w "HTTP_STATUS:%{http_code}": HTTPステータスコードをstdoutの最後に出力
        command = (
            f"curl -sSL -X {method} {header_str} -o \"{full_dest_path}\" "
            f"-w 'HTTP_STATUS:%{{http_code}}' '{url}'"
        )
        print(f"DownloadFileTool: LLM agent {llm_agent_id} requested to download from {url} to {full_dest_path} with method {method} and headers: {headers}.")
        try:
            sandbox_entry = self.sandbox_manager_service.provision_and_execute_sandbox_session(
                llm_agent_id=llm_agent_id,
                code=command,
                base_image=base_image
            )
            
            # HTTPステータスコードの抽出
            http_status = "N/A"
            clean_output = sandbox_entry.execution_result
            if "HTTP_STATUS:" in sandbox_entry.execution_result:
                parts = sandbox_entry.execution_result.split("HTTP_STATUS:")
                clean_output = parts[0].strip()
                http_status = parts[-1].strip()

            if sandbox_entry.status == SandboxStatus.SUCCESS and sandbox_entry.exit_code == 0:
                return (f"Successfully downloaded file from {url} to {destination_path}. "
                        f"HTTP Status: {http_status}.\nOutput:\n{clean_output}")
            else:
                error_detail = sandbox_entry.error_message if sandbox_entry.error_message else "No specific error message."
                output_detail = clean_output if clean_output else "No specific output."
                return (f"Failed to download file from {url} to {destination_path}. "
                        f"HTTP Status: {http_status}. Exit code: {sandbox_entry.exit_code}\n"
                        f"Error:\n{error_detail}\n"
                        f"Output:\n{output_detail}")
        except Exception as e:
            return f"Error downloading file in persistent sandbox: {str(e)}"

    async def _arun(self, llm_agent_id: str, url: str, destination_path: str, headers: Optional[str] = None, method: str = "GET", base_image: Optional[str] = None, run_manager: Optional[RunnableConfig] = None) -> str:
        return self._run(llm_agent_id=llm_agent_id, url=url, destination_path=destination_path, headers=headers, method=method, base_image=base_image, run_manager=run_manager)

class UploadFileTool(BaseTool):
    name: str = "upload_file_to_internet"
    description: str = "Uploads a file from the persistent sandbox's shared directory to a specified URL. Allows custom HTTP headers and methods. Requires a base image with `curl` installed. Returns HTTP status code upon completion."
    args_schema: Type[BaseModel] = UploadFileInput
    sandbox_manager_service: SandboxManagerService

    def _run(self, llm_agent_id: str, file_path: str, destination_url: str, headers: Optional[str] = None, method: str = "POST", base_image: Optional[str] = None, run_manager: Optional[RunnableConfig] = None) -> str:
        full_file_path = f"{config.SHARED_DIR_CONTAINER_PATH}/{file_path.lstrip('/')}"
        
        # ヘッダーをパースしてcurlコマンドに追加
        header_commands = []
        content_type_from_headers = None
        if headers:
            try:
                headers_dict = json.loads(headers)
                for key, value in headers_dict.items():
                    if key.lower() == 'content-type':
                        content_type_from_headers = value
                    header_commands.append(f"-H '{key}: {value}'")
            except json.JSONDecodeError:
                return f"Error: Invalid JSON format for headers: {headers}"
        header_str = " ".join(header_commands)

        # Content-Typeに基づき、-d (raw data) または -F (form-data) を使用
        # PUT/PATCHの場合は、Content-Typeが明示的にmultipartでなければ-dを優先
        data_upload_part = ""
        # ファイルパスもダブルクォートで囲む
        if content_type_from_headers and "multipart/form-data" not in content_type_from_headers.lower():
            # Content-Typeがmultipart/form-data以外の場合、ファイルをリクエストボディとして送信
            data_upload_part = f"-d \"@{full_file_path}\""
        elif method.upper() in ["PUT", "PATCH"]:
            # PUT/PATCHリクエストの場合、Content-Typeが指定されていないか、
            # 特にmultipart/form-dataでない場合は、ファイルをリクエストボディとして送信
            data_upload_part = f"-d \"@{full_file_path}\""
        else:
            # それ以外の場合（POSTなど）、デフォルトでファイルをフォームデータとして送信
            data_upload_part = f"-F \"file=@{full_file_path}\""
            
        command = (
            f"curl -sSL -X {method} {header_str} {data_upload_part} "
            f"-w 'HTTP_STATUS:%{{http_code}}' '{destination_url}'"
        )
        print(f"UploadFileTool: LLM agent {llm_agent_id} requested to upload {full_file_path} to {destination_url} with method {method} and headers: {headers}.")
        try:
            sandbox_entry = self.sandbox_manager_service.provision_and_execute_sandbox_session(
                llm_agent_id=llm_agent_id,
                code=command,
                base_image=base_image
            )

            # HTTPステータスコードの抽出
            http_status = "N/A"
            clean_output = sandbox_entry.execution_result
            if "HTTP_STATUS:" in sandbox_entry.execution_result:
                parts = sandbox_entry.execution_result.split("HTTP_STATUS:")
                clean_output = parts[0].strip()
                http_status = parts[-1].strip()

            if sandbox_entry.status == SandboxStatus.SUCCESS and sandbox_entry.exit_code == 0:
                return (f"Successfully uploaded file {file_path} to {destination_url}. "
                        f"HTTP Status: {http_status}.\nOutput:\n{clean_output}")
            else:
                error_detail = sandbox_entry.error_message if sandbox_entry.error_message else "No specific error message."
                output_detail = clean_output if clean_output else "No specific output."
                return (f"Failed to upload file {file_path} to {destination_url}. "
                        f"HTTP Status: {http_status}. Exit code: {sandbox_entry.exit_code}\n"
                        f"Error:\n{error_detail}\n"
                        f"Output:\n{output_detail}")
        except Exception as e:
            return f"Error uploading file in persistent sandbox: {str(e)}"

    async def _arun(self, llm_agent_id: str, file_path: str, destination_url: str, headers: Optional[str] = None, method: str = "POST", base_image: Optional[str] = None, run_manager: Optional[RunnableConfig] = None) -> str:
        return self._run(llm_agent_id=llm_agent_id, file_path=file_path, destination_url=destination_url, headers=headers, method=method, base_image=base_image, run_manager=run_manager)

class DownloadWebpageRecursivelyTool(BaseTool):
    name: str = "download_webpage_recursively"
    description: str = "Downloads a webpage and its linked resources (images, CSS, JS, etc.) recursively to a specified directory. Useful for offline browsing or analyzing a site structure. Requires a base image with `wget` installed."
    args_schema: Type[BaseModel] = DownloadWebpageRecursivelyInput
    sandbox_manager_service: SandboxManagerService

    def _run(self, llm_agent_id: str, url: str, destination_dir: str, max_depth: int = 5, accept_regex: Optional[str] = None, base_image: Optional[str] = None, run_manager: Optional[RunnableConfig] = None) -> str:
        full_dest_dir = f"{config.SHARED_DIR_CONTAINER_PATH}/{destination_dir.lstrip('/')}"
        
        # まずディレクトリが存在するか確認し、なければ作成する
        mkdir_command = f"mkdir -p \"{full_dest_dir}\"" # ダブルクォートで囲む
        print(f"DownloadWebpageRecursivelyTool: Ensuring directory {full_dest_dir} exists.")
        mkdir_entry = self.sandbox_manager_service.provision_and_execute_sandbox_session(
            llm_agent_id=llm_agent_id,
            code=mkdir_command,
            base_image=base_image
        )
        if mkdir_entry.exit_code != 0:
            return f"Failed to create destination directory {full_dest_dir}. Error: {mkdir_entry.error_message}. Output: {mkdir_entry.execution_result}"

        # wget -r --level=N --no-parent --directory-prefix=PATH --convert-links --page-requisites URL
        # -r: 再帰的ダウンロード
        # --level=N: 再帰深度
        # --no-parent: 親ディレクトリに遡らない
        # --directory-prefix=PATH: 出力ディレクトリ (ダブルクォートで囲む)
        # --convert-links: ローカルパスに変換
        # --page-requisites: HTML表示に必要な全てのファイル（画像、CSS、JS）をダウンロード
        command_parts = [
            "wget -r",
            f"--level={max_depth}",
            f"--directory-prefix=\"{full_dest_dir}\"", # ダブルクォートで囲む
            "--convert-links",
            "--page-requisites",
            "--no-parent",
            "-nv" # no verbose output, only errors and progress
        ]
        
        if accept_regex:
            command_parts.append(f"--accept-regex='{accept_regex}'") # シェルインジェクション対策でシングルクォートで囲む

        command_parts.append(f"'{url}'") # 最後にURL

        command = " ".join(command_parts)

        print(f"DownloadWebpageRecursivelyTool: LLM agent {llm_agent_id} requested recursive download of {url} to {full_dest_dir}.")
        try:
            sandbox_entry = self.sandbox_manager_service.provision_and_execute_sandbox_session(
                llm_agent_id=llm_agent_id,
                code=command,
                base_image=base_image
            )
            if sandbox_entry.status == SandboxStatus.SUCCESS and sandbox_entry.exit_code == 0:
                # wget -nv の場合、成功時は出力が少ないか、進行状況バーのみになることが多い。
                # ユーザーへの情報として、ダウンロードされたファイルのリストやディレクトリ内容を提供すると良いかもしれないが、
                # ここでは簡潔に成功を伝える。
                return (f"Successfully downloaded webpage and resources from {url} to {destination_dir}. "
                        f"Check the directory {destination_dir} for content.\nOutput:\n{sandbox_entry.execution_result}")
            else:
                error_detail = sandbox_entry.error_message if sandbox_entry.error_message else "No specific error message."
                output_detail = sandbox_entry.execution_result if sandbox_entry.execution_result else "No specific output."
                return (f"Failed to download webpage recursively from {url} to {destination_dir}. Exit code: {sandbox_entry.exit_code}\n"
                        f"Error:\n{error_detail}\n"
                        f"Output:\n{output_detail}")
        except Exception as e:
            return f"Error downloading webpage recursively in persistent sandbox: {str(e)}"

    async def _arun(self, llm_agent_id: str, url: str, destination_dir: str, max_depth: int = 5, accept_regex: Optional[str] = None, base_image: Optional[str] = None, run_manager: Optional[RunnableConfig] = None) -> str:
        return self._run(llm_agent_id=llm_agent_id, url=url, destination_dir=destination_dir, max_depth=max_depth, accept_regex=accept_regex, base_image=base_image, run_manager=run_manager)

class FindFilesInSandboxTool(BaseTool):
    name: str = "find_files_in_sandbox"
    description: str = "Searches for files and directories in the persistent sandbox's shared directory. You can specify a starting path, file name pattern, file type, and maximum search depth."
    args_schema: Type[BaseModel] = FindFilesInSandboxInput
    sandbox_manager_service: SandboxManagerService

    def _run(self, llm_agent_id: str, search_path: str, name_pattern: Optional[str] = None, file_type: Optional[str] = None, max_depth: Optional[int] = None, run_manager: Optional[RunnableConfig] = None) -> str:
        full_search_path = f"{config.SHARED_DIR_CONTAINER_PATH}/{search_path.lstrip('/')}"
        command_parts = ["find", f"\"{full_search_path}\""] # パスをダブルクォートで囲む

        if max_depth is not None:
            command_parts.append(f"-maxdepth {max_depth}")
        if file_type:
            command_parts.append(f"-type {file_type}")
        if name_pattern:
            # -name のパターンはシェルによって展開されないようシングルクォートのまま
            command_parts.append(f"-name '{name_pattern}'")

        command = " ".join(command_parts)
        print(f"FindFilesInSandboxTool: LLM agent {llm_agent_id} requested file search: {command}")

        try:
            sandbox_entry = self.sandbox_manager_service.provision_and_execute_sandbox_session(
                llm_agent_id=llm_agent_id,
                code=command
            )
            if sandbox_entry.status == SandboxStatus.SUCCESS and sandbox_entry.exit_code == 0:
                # Remove the shared directory prefix for cleaner output for the agent
                results = sandbox_entry.execution_result.strip().split('\n')
                cleaned_results = [
                    res.replace(f"{config.SHARED_DIR_CONTAINER_PATH}/", "").lstrip('/')
                    for res in results if res
                ]
                if not cleaned_results:
                    return f"No files found matching the criteria in {search_path}."
                return f"Files found in {search_path}:\n" + "\n".join(cleaned_results)
            else:
                error_detail = sandbox_entry.error_message if sandbox_entry.error_message else "No specific error message."
                output_detail = sandbox_entry.execution_result if sandbox_entry.execution_result else "No specific output."
                return (f"Failed to find files in sandbox.\n"
                        f"Error:\n{error_detail}\n"
                        f"Output:\n{output_detail}")
        except Exception as e:
            return f"Error searching files in persistent sandbox: {str(e)}"

    async def _arun(self, llm_agent_id: str, search_path: str, name_pattern: Optional[str] = None, file_type: Optional[str] = None, max_depth: Optional[int] = None, run_manager: Optional[RunnableConfig] = None) -> str:
        return self._run(llm_agent_id=llm_agent_id, search_path=search_path, name_pattern=name_pattern, file_type=file_type, max_depth=max_depth, run_manager=run_manager)

class GrepFileContentInSandboxTool(BaseTool):
    name: str = "grep_file_content_in_sandbox"
    description: str = "Searches for a specified pattern within the content of files in the persistent sandbox's shared directory. Can search recursively and case-insensitively."
    args_schema: Type[BaseModel] = GrepFileContentInSandboxInput
    sandbox_manager_service: SandboxManagerService

    def _run(self, llm_agent_id: str, file_path: str, pattern: str, recursive: bool = False, case_insensitive: bool = False, line_numbers: bool = False, run_manager: Optional[RunnableConfig] = None) -> str:
        full_file_path = f"{config.SHARED_DIR_CONTAINER_PATH}/{file_path.lstrip('/')}"
        command_parts = ["grep"]

        if recursive:
            command_parts.append("-r")
        if case_insensitive:
            command_parts.append("-i")
        if line_numbers:
            command_parts.append("-n")
        
        # Pattern and path must be last
        command_parts.append(f"'{pattern}'") # Escape pattern to prevent shell interpretation
        command_parts.append(f"\"{full_file_path}\"") # パスをダブルクォートで囲む

        command = " ".join(command_parts)
        print(f"GrepFileContentInSandboxTool: LLM agent {llm_agent_id} requested grep: {command}")

        try:
            sandbox_entry = self.sandbox_manager_service.provision_and_execute_sandbox_session(
                llm_agent_id=llm_agent_id,
                code=command
            )
            if sandbox_entry.status == SandboxStatus.SUCCESS and (sandbox_entry.exit_code == 0 or sandbox_entry.exit_code == 1): # exit code 1 means no lines selected
                if sandbox_entry.execution_result.strip():
                    # Remove the shared directory prefix for cleaner output for the agent
                    results = sandbox_entry.execution_result.strip().split('\n')
                    cleaned_results = [
                        res.replace(f"{config.SHARED_DIR_CONTAINER_PATH}/", "").lstrip('/')
                        for res in results if res
                    ]
                    return f"Pattern '{pattern}' found in files:\n" + "\n".join(cleaned_results)
                else:
                    return f"Pattern '{pattern}' not found in {file_path}."
            else:
                error_detail = sandbox_entry.error_message if sandbox_entry.error_message else "No specific error message."
                output_detail = sandbox_entry.execution_result if sandbox_entry.execution_result else "No specific output."
                return (f"Failed to grep file content in sandbox.\n"
                        f"Error:\n{error_detail}\n"
                        f"Output:\n{output_detail}")
        except Exception as e:
            return f"Error searching file content in persistent sandbox: {str(e)}"

    async def _arun(self, llm_agent_id: str, file_path: str, pattern: str, recursive: bool = False, case_insensitive: bool = False, line_numbers: bool = False, run_manager: Optional[RunnableConfig] = None) -> str:
        return self._run(llm_agent_id=llm_agent_id, file_path=file_path, pattern=pattern, recursive=recursive, case_insensitive=case_insensitive, line_numbers=line_numbers, run_manager=run_manager)

class GetSystemInfoTool(BaseTool):
    name: str = "get_system_info_in_sandbox"
    description: str = "Retrieves detailed system information from the persistent sandbox, such as OS and CPU details, or memory usage."
    args_schema: Type[BaseModel] = GetSystemInfoInput
    sandbox_manager_service: SandboxManagerService

    def _run(self, llm_agent_id: str, info_type: str, run_manager: Optional[RunnableConfig] = None) -> str:
        command = ""
        if info_type == "os_and_cpu":
            # OS type and kernel, then CPU info
            command = "uname -a && cat /proc/cpuinfo | grep 'model name' | uniq && cat /proc/cpuinfo | grep 'processor' | wc -l"
        elif info_type == "memory":
            # Memory usage in human-readable format
            command = "cat /proc/meminfo" # 'free -h' is simpler but 'cat /proc/meminfo' gives more raw details
        else:
            return "Error: Invalid info_type. Please choose 'os_and_cpu' or 'memory'."

        print(f"GetSystemInfoTool: LLM agent {llm_agent_id} requested system info: {info_type}")
        try:
            sandbox_entry = self.sandbox_manager_service.provision_and_execute_sandbox_session(
                llm_agent_id=llm_agent_id,
                code=command
            )
            if sandbox_entry.status == SandboxStatus.SUCCESS:
                if info_type == "os_and_cpu":
                    output_lines = sandbox_entry.execution_result.strip().split('\n')
                    uname_output = output_lines[0].strip() if output_lines else "N/A"
                    cpu_model = output_lines[1].strip() if len(output_lines) > 1 else "N/A"
                    num_cpus = output_lines[2].strip() if len(output_lines) > 2 else "N/A"
                    return (f"System Information (OS & CPU):\n"
                            f"  OS/Kernel: {uname_output}\n"
                            f"  CPU Model: {cpu_model}\n"
                            f"  Number of CPUs: {num_cpus}")
                elif info_type == "memory":
                    return f"System Information (Memory):\n{sandbox_entry.execution_result.strip()}"
                else:
                    return f"System Information ({info_type}):\n{sandbox_entry.execution_result.strip()}"
            else:
                error_detail = sandbox_entry.error_message if sandbox_entry.error_message else "No specific error message."
                output_detail = sandbox_entry.execution_result if sandbox_entry.execution_result else "No specific output."
                return (f"Failed to get system info for {info_type}.\n"
                        f"Error:\n{error_detail}\n"
                        f"Output:\n{output_detail}")
        except Exception as e:
            return f"Error getting system info in persistent sandbox: {str(e)}"

    async def _arun(self, llm_agent_id: str, info_type: str, run_manager: Optional[RunnableConfig] = None) -> str:
        return self._run(llm_agent_id=llm_agent_id, info_type=info_type, run_manager=run_manager)
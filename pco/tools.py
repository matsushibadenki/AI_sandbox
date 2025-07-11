# AI_sandbox/pco/tools.py
from langchain.tools import BaseTool
from typing import Type, Dict, Any, Optional, Union
from pydantic import BaseModel, Field, ValidationError
import json
from langchain_core.runnables import RunnableConfig

from sandbox_manager.service import SandboxManagerService
from database.models import SandboxStatus

# LLMからの入力スキーマ
class RunCodeInSandboxInput(BaseModel):
    llm_agent_id: str = Field(description="The unique ID of the LLM agent requesting the sandbox operation.")
    code: str = Field(description="The Python or Node.js code to execute in the sandbox.")
    base_image: Optional[str] = Field(default=None, description="Optional. The Docker image to use for the sandbox (e.g., 'python:3.10-slim-bookworm', 'node:18'). Defaults to system config if not provided.")


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
# program_builder/pco/tools.py
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
    base_image: Optional[str] = Field(default=None, description="Optional. The Docker image to use for the sandbox (e.g., 'python:3.10-slim-bookworm', 'node:18'). Defaults to system config if not provided.") # <-- 修正


class SandboxTool(BaseTool):
    name: str = "run_code_in_sandbox"
    description: str = "Executes Python or Node.js code in a isolated Docker sandbox and returns the output. Provide the full code string."
    args_schema: Type[BaseModel] = RunCodeInSandboxInput
    sandbox_manager_service: SandboxManagerService # DIを通じて注入される

    def _run(self, tool_input: Union[str, Dict[str, Any]], run_manager: Optional[RunnableConfig] = None) -> str:
        """サンドボックスでコードを実行し、結果を返します。"""
        parsed_data = {}
        
        if isinstance(tool_input, str):
            try:
                parsed_data = json.loads(tool_input)
            except json.JSONDecodeError:
                return f"Error: Failed to parse tool input as JSON string: {tool_input}"
        elif isinstance(tool_input, dict):
            parsed_data = tool_input
        else:
            return f"Error: Unexpected tool input type: {type(tool_input)}. Expected string or dict."

        # エラーログが示す「ネストされたJSON文字列」のケースを処理
        if (
            isinstance(parsed_data, dict) and
            'llm_agent_id' in parsed_data and
            isinstance(parsed_data['llm_agent_id'], str) and
            parsed_data['llm_agent_id'].strip().startswith('{') and
            parsed_data['llm_agent_id'].strip().endswith('}')
        ):
            try:
                parsed_data = json.loads(parsed_data['llm_agent_id'])
            except json.JSONDecodeError as e:
                return f"Error: Failed to parse nested JSON string in Action Input: {parsed_data['llm_agent_id']} - {e}\nFull text: {tool_input}" # <-- 修正
        
        try:
            validated_input = RunCodeInSandboxInput.model_validate(parsed_data)
            llm_agent_id = validated_input.llm_agent_id
            code = validated_input.code
            base_image = validated_input.base_image
            
            if llm_agent_id is None:
                print("Warning: llm_agent_id was not provided by LLM. Using a dummy ID.")
                llm_agent_id = "dummy-llm-agent"
                
        except ValidationError as e:
            return f"Error: Invalid tool input format. Validation failed: {e}. Received input: {parsed_data}"
        except Exception as e:
            return f"Error: Unexpected issue during tool input validation: {e}. Received input: {parsed_data}"

        print(f"SandboxTool: LLM agent {llm_agent_id} requested sandbox execution.")
        try:
            sandbox_entry = self.sandbox_manager_service.create_and_run_sandbox(
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
            return f"Error creating or running sandbox: {str(e)}"

    async def _arun(self, tool_input: Union[str, Dict[str, Any]], run_manager: Optional[RunnableConfig] = None) -> str:
        """_run が同期なので、_arun は NotImplementedError のまま"""
        raise NotImplementedError("Asynchronous execution not implemented for SandboxTool")
# AI_sandbox/sandbox_manager/service.py
import time
from typing import Any, Dict, Optional, Tuple

from database.crud import CRUD
from database.models import Sandbox, SandboxStatus
from sandbox_manager.docker_client import DockerClient
from config import config


class SandboxManagerService:
    def __init__(self, db_crud: CRUD, docker_client: DockerClient,
                 resource_limits: Dict[str, Any], network_mode: str,
                 default_base_image: str, sandbox_timeout_seconds: int) -> None:
        self._crud = db_crud
        self._docker_client = docker_client
        self._resource_limits = resource_limits
        self._network_mode = network_mode
        self._default_base_image = default_base_image
        self._sandbox_timeout_seconds = sandbox_timeout_seconds

    def provision_and_execute_sandbox_session(self, llm_agent_id: str, code: str, base_image: Optional[str] = None) -> Sandbox:
        """
        LLMエージェントIDに基づいて永続的なサンドボックスセッションを管理し、コードを実行します。
        既存のセッションがあればそれを利用し、なければ新規にプロビジョニングします。
        """
        if base_image is None:
            base_image = self._default_base_image

        container_name = f"sandbox-{llm_agent_id}"
        sandbox_entry: Optional[Sandbox] = None
        container_id: Optional[str] = None

        # 1. アクティブなサンドボックスセッションをDBから検索
        active_sandboxes = self._crud.get_active_sandboxes()
        for sb in active_sandboxes:
            if sb.llm_agent_id == llm_agent_id and sb.status in [SandboxStatus.PENDING, SandboxStatus.RUNNING]:
                docker_container_status = None
                if sb.container_id:
                    docker_container_status = self._docker_client.get_container_status(str(sb.container_id))
                
                if docker_container_status == "running":
                    sandbox_entry = sb
                    container_id = str(sb.container_id)
                    print(f"SandboxManagerService: Found existing active sandbox session {sb.id} for agent {llm_agent_id}")
                    break
                else:
                    print(f"SandboxManagerService: Deactivating stale sandbox entry {sb.id} (Docker status: {docker_container_status})")
                    self._crud.deactivate_sandbox(str(sb.id))
                    # ◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️↓修正開始◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️
                    if sb.container_id is not None:
                        container_id_str = str(sb.container_id) # Assign to a new variable and ensure it's str
                        try:
                            self._docker_client.stop_and_remove_container(container_id_str)
                            print(f"SandboxManagerService: Removed stale container {container_id_str}.")
                        except Exception as ce:
                            print(f"SandboxManagerService: Could not remove stale container {container_id_str}: {ce}")
                    # ◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️↑修正終わり◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️
        
        # 2. コンテナのプロvisioning または再利用
        if container_id is None:
            print(f"SandboxManagerService: No active sandbox found for agent {llm_agent_id}. Provisioning new one.")

            existing_docker_container = self._docker_client.find_container_by_name(container_name)
            if existing_docker_container:
                print(f"SandboxManagerService: Found existing Docker container with name {container_name}. Stopping and removing it to prevent conflict.")
                self._docker_client.stop_and_remove_container(existing_docker_container.id)

            if not self._docker_client.pull_image(base_image):
                raise ValueError(f"Failed to pull Docker image: {base_image}")

            sandbox_entry = self._crud.create_sandbox(
                llm_agent_id=llm_agent_id,
                code_to_execute=code,
                base_image=base_image,
                resource_limits=self._resource_limits
            )
            if sandbox_entry is None:
                raise ValueError("Failed to create new sandbox entry in the database.")
            sandbox_id = str(sandbox_entry.id)

            volumes = {
                config.SHARED_DIR_HOST_PATH: {
                    'bind': config.SHARED_DIR_CONTAINER_PATH,
                    'mode': 'rw'
                }
            }

            try:
                current_container_obj = self._docker_client.start_container(
                    image=base_image,
                    name=container_name,
                    resource_limits=self._resource_limits,
                    network_mode=self._network_mode,
                    volumes=volumes
                )
                container_id = current_container_obj.id
                updated_entry = self._crud.update_sandbox_status(
                    sandbox_id=sandbox_id,
                    status=SandboxStatus.RUNNING,
                    container_id=container_id,
                    execution_result="Sandbox session started.",
                    error_message=None,
                    exit_code=0
                )
                if updated_entry is None:
                    raise ValueError(f"Failed to update sandbox {sandbox_entry.id} with container ID.")
                sandbox_entry = updated_entry

            except Exception as e:
                print(f"SandboxManagerService: Error during initial sandbox provisioning for {llm_agent_id}: {e}")
                if sandbox_entry:
                    self._crud.update_sandbox_status(
                        sandbox_id=str(sandbox_entry.id),
                        status=SandboxStatus.FAILED,
                        error_message=f"Provisioning error: {str(e)}"
                    )
                raise
        else:
            if sandbox_entry is None:
                raise ValueError("Sandbox entry is unexpectedly None for an existing container.")

            print(f"SandboxManagerService: Reusing existing sandbox session {sandbox_entry.id} for agent {llm_agent_id}. Container ID: {container_id}")
            if self._docker_client.get_container_status(container_id) != "running":
                 raise Exception(f"Existing container {container_id} for agent {llm_agent_id} is not running.")
        
        # 3. コンテナ内でコードを実行
        print(f"SandboxManagerService: Executing code in sandbox {container_id}: {code[:100]}...")
        if container_id is None:
            raise ValueError("Container ID is unexpectedly None when attempting to execute code.")

        output, error, exit_code = self._docker_client.exec_code_in_container(
            container_id=container_id,
            code_string=code,
            base_image=base_image,
            timeout=self._sandbox_timeout_seconds
        )

        final_status = SandboxStatus.SUCCESS if exit_code == 0 and not error else SandboxStatus.FAILED
        final_error_message: Optional[str] = error if error else None
        final_execution_result: str = output if output else "No output."

        if sandbox_entry is None:
            raise ValueError("Sandbox entry is unexpectedly None before updating with execution results.")

        updated_entry = self._crud.update_sandbox_status(
            sandbox_id=str(sandbox_entry.id),
            status=final_status,
            execution_result=final_execution_result,
            error_message=final_error_message,
            exit_code=exit_code
        )
        if updated_entry is None:
            print(f"SandboxManagerService: WARNING: Failed to update sandbox {sandbox_entry.id} with execution results.")
            sandbox_entry.status = final_status
            sandbox_entry.execution_result = final_execution_result # type: ignore
            sandbox_entry.error_message = final_error_message # type: ignore
            sandbox_entry.exit_code = exit_code # type: ignore
        else:
            sandbox_entry = updated_entry

        return sandbox_entry

    def get_sandbox_status(self, sandbox_id: str) -> Sandbox:
        """指定されたサンドボックスの状態を取得します。"""
        sandbox = self._crud.get_sandbox(sandbox_id)
        if sandbox is None:
            raise ValueError(f"Sandbox with id '{sandbox_id}' not found")
        return sandbox

    def monitor_and_regenerate_broken_sandboxes(self):
        """
        破綻した（FAILED）状態のサンドボックスを監視し、必要に応じて再生成を試みます。
        PCOの外部で定期的に実行されることを想定。
        """
        print("SandboxManagerService: Monitoring for broken sandboxes...")
        broken_sandboxes = self._crud.get_broken_sandboxes()
        for sandbox in broken_sandboxes:
            print(f"SandboxManagerService: Detected broken sandbox {sandbox.id}. Attempting regeneration.")
            try:
                if sandbox.container_id:
                    try:
                        self._docker_client.stop_and_remove_container(str(sandbox.container_id))
                        print(f"SandboxManagerService: Removed broken container {sandbox.container_id}.")
                    except Exception as ce:
                        print(f"SandboxManagerService: Could not remove container {sandbox.container_id}: {ce}")

                self._crud.deactivate_sandbox(str(sandbox.id))
                print(f"SandboxManagerService: Deactivated old broken sandbox DB entry {sandbox.id}.")

                self.provision_and_execute_sandbox_session(
                    llm_agent_id=sandbox.llm_agent_id,
                    code=sandbox.code_to_execute,
                    base_image=sandbox.base_image
                )
                print(f"SandboxManagerService: Successfully regenerated sandbox for {sandbox.id}.")
            except Exception as e:
                print(f"SandboxManagerService: Failed to regenerate sandbox for {sandbox.id}: {e}")
        print("SandboxManagerService: Monitoring complete.")

    def cleanup_inactive_sandboxes(self):
        """
        非アクティブなサンドボックスのDBエントリを削除し、関連するDockerコンテナを停止・削除します。
        """
        print("SandboxManagerService: Cleaning up inactive sandboxes...")
        all_sandboxes = self._crud.get_all_sandboxes()
        for sandbox in all_sandboxes:
            if not sandbox.is_active:
                print(f"SandboxManagerService: Deleting inactive DB entry {sandbox.id}")
                self._crud.delete_sandbox(str(sandbox.id))
                if sandbox.container_id:
                    try:
                        self._docker_client.stop_and_remove_container(str(sandbox.container_id))
                        print(f"SandboxManagerService: Removed inactive container {sandbox.container_id}.")
                    except Exception as e:
                        print(f"SandboxManagerService: Could not remove inactive container {sandbox.container_id}: {e}")
        print("SandboxManagerService: Cleanup complete.")
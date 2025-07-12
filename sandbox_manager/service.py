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
        current_container_id: Optional[str] = None # DBとDockerのコンテナIDを追跡

        # 1. DBからllm_agent_idに対応するサンドボックスエントリを検索
        # is_active=Trueのものだけではなく、llm_agent_idとbase_imageが一致するものを優先
        # 最新のものを取得
        all_agent_sandboxes = [
            sb for sb in self._crud.get_all_sandboxes() 
            if sb.llm_agent_id == llm_agent_id and sb.base_image == base_image
        ]
        # 最も新しい（last_updated_atが新しい）エントリを優先
        if all_agent_sandboxes:
            all_agent_sandboxes.sort(key=lambda x: x.last_updated_at, reverse=True)
            sandbox_entry = all_agent_sandboxes[0]
            current_container_id = str(sandbox_entry.container_id) if sandbox_entry.container_id else None
            print(f"SandboxManagerService: Found existing DB entry {sandbox_entry.id} for agent {llm_agent_id}.")
        
        # 2. Dockerコンテナの状態を確認し、必要に応じて起動・再利用
        if current_container_id:
            docker_container_status = self._docker_client.get_container_status(current_container_id)
            if docker_container_status == "running":
                print(f"SandboxManagerService: Reusing existing running container {current_container_id} for agent {llm_agent_id}.")
                # 既存のDBエントリを最新の状態に更新 (ステータスはRUNNING)
                updated_entry = self._crud.update_sandbox_status(
                    sandbox_id=str(sandbox_entry.id), # type: ignore
                    status=SandboxStatus.RUNNING,
                    container_id=current_container_id,
                    error_message=None,
                    exit_code=0
                )
                if updated_entry:
                    sandbox_entry = updated_entry
                else:
                    print(f"SandboxManagerService: WARNING: Failed to update existing sandbox {sandbox_entry.id} status in DB.") # type: ignore

            elif docker_container_status in ["exited", "created", "dead", "paused", "restarting", "removing"]:
                # コンテナが停止している場合、再起動を試みる
                print(f"SandboxManagerService: Existing container {current_container_id} is {docker_container_status}. Attempting to restart.")
                try:
                    self._docker_client.start_existing_container(current_container_id)
                    print(f"SandboxManagerService: Successfully restarted container {current_container_id}.")
                    updated_entry = self._crud.update_sandbox_status(
                        sandbox_id=str(sandbox_entry.id), # type: ignore
                        status=SandboxStatus.RUNNING,
                        container_id=current_container_id,
                        error_message=None,
                        exit_code=0
                    )
                    if updated_entry:
                        sandbox_entry = updated_entry
                    else:
                        print(f"SandboxManagerService: WARNING: Failed to update existing sandbox {sandbox_entry.id} status after restart.") # type: ignore
                except Exception as e:
                    print(f"SandboxManagerService: Failed to restart container {current_container_id}: {e}. Will provision a new one.")
                    # 再起動に失敗した場合、既存のDBエントリを非アクティブ化し、新しいコンテナをプロビジョニングするフローに進む
                    if sandbox_entry:
                        self._crud.deactivate_sandbox(str(sandbox_entry.id)) # type: ignore
                    current_container_id = None # 新規プロビジョニングを強制
                    sandbox_entry = None # 新規プロビジョニングを強制

            else: # None (コンテナが存在しない) またはその他の不明な状態
                print(f"SandboxManagerService: Container {current_container_id} is {docker_container_status}. Will provision a new one.")
                if sandbox_entry:
                    self._crud.deactivate_sandbox(str(sandbox_entry.id)) # type: ignore
                    try:
                        # Dockerにコンテナが存在しない、または状態がおかしい場合、DBエントリもクリーンアップを試みる
                        self._docker_client.stop_and_remove_container(current_container_id)
                        print(f"SandboxManagerService: Cleaned up problematic container {current_container_id}.")
                    except Exception as ce:
                        print(f"SandboxManagerService: Could not remove problematic container {current_container_id}: {ce}")
                current_container_id = None # 新規プロビジョニングを強制
                sandbox_entry = None # 新規プロビジョニングを強制

        # 3. 新しいコンテナのプロビジョニング (既存のものが利用できなかった場合)
        if current_container_id is None:
            print(f"SandboxManagerService: Provisioning new sandbox for agent {llm_agent_id}.")

            # 既存のDockerコンテナ名と衝突しないことを保証
            existing_docker_container_by_name = self._docker_client.find_container_by_name(container_name)
            if existing_docker_container_by_name:
                print(f"SandboxManagerService: Found existing Docker container with name {container_name} (ID: {existing_docker_container_by_name.id}). Stopping and removing it to prevent conflict.")
                try:
                    self._docker_client.stop_and_remove_container(existing_docker_container_by_name.id)
                except Exception as e:
                    print(f"SandboxManagerService: Error removing conflicting container {existing_docker_container_by_name.id}: {e}")

            if not self._docker_client.pull_image(base_image):
                raise ValueError(f"Failed to pull Docker image: {base_image}")

            # 新しいDBエントリを作成
            sandbox_entry = self._crud.create_sandbox(
                llm_agent_id=llm_agent_id,
                code_to_execute=code, # 初期コードとして記録
                base_image=base_image,
                resource_limits=self._resource_limits
            )
            if sandbox_entry is None:
                raise ValueError("Failed to create new sandbox entry in the database.")
            
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
                current_container_id = current_container_obj.id
                updated_entry = self._crud.update_sandbox_status(
                    sandbox_id=str(sandbox_entry.id),
                    status=SandboxStatus.RUNNING,
                    container_id=current_container_id,
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
        
        # 4. コンテナ内でコードを実行
        print(f"SandboxManagerService: Executing code in sandbox {current_container_id}: {code[:100]}...")
        if current_container_id is None:
            raise ValueError("Container ID is unexpectedly None when attempting to execute code.")

        output, error, exit_code = self._docker_client.exec_code_in_container(
            container_id=current_container_id,
            code_string=code,
            base_image=base_image, # base_imageはexec_code_in_containerのインタプリタ選択に必要
            timeout=self._sandbox_timeout_seconds
        )

        final_error_message: Optional[str] = error if error else None
        final_execution_result: str = output if output else "No output."

        # exec_code_in_container が返した exit_code が非ゼロ、または stderr にエラーがあれば FAILED
        # そうでなければ、コンテナ自体は稼働し続けるので RUNNING のまま
        # IMPORTANT: _docker_client.get_container_status(current_container_id) で
        # 実行後のコンテナの状態を確認することが最も重要
        post_exec_container_status = self._docker_client.get_container_status(current_container_id)
        
        # コンテナが実行中である限り、DB上はRUNNINGを維持し、実行に失敗した場合のみFAILEDに更新
        if post_exec_container_status != "running" or (exit_code != 0 or error):
            db_status_after_exec = SandboxStatus.FAILED
            print(f"SandboxManagerService: Sandbox {sandbox_entry.id} execution resulted in FAILED status (Container status: {post_exec_container_status}, Exit Code: {exit_code}, Error: {final_error_message}).")
        else:
            db_status_after_exec = SandboxStatus.RUNNING
            print(f"SandboxManagerService: Sandbox {sandbox_entry.id} execution resulted in SUCCESS and remains RUNNING.")

        if sandbox_entry is None:
            raise ValueError("Sandbox entry is unexpectedly None before updating with execution results.")

        updated_entry = self._crud.update_sandbox_status(
            sandbox_id=str(sandbox_entry.id),
            status=db_status_after_exec,
            execution_result=final_execution_result,
            error_message=final_error_message,
            exit_code=exit_code
        )
        if updated_entry is None:
            print(f"SandboxManagerService: WARNING: Failed to update sandbox {sandbox_entry.id} with execution results.")
            sandbox_entry.status = db_status_after_exec
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
        # activeだがFAILEDになっているサンドボックスを対象にする
        broken_sandboxes = [
            sb for sb in self._crud.get_active_sandboxes()
            if sb.status == SandboxStatus.FAILED
        ]

        for sandbox in broken_sandboxes:
            print(f"SandboxManagerService: Detected broken sandbox {sandbox.id} (Agent: {sandbox.llm_agent_id}). Attempting to diagnose/fix.")
            
            # Dockerコンテナの状態を直接確認
            container_status = None
            if sandbox.container_id:
                container_status = self._docker_client.get_container_status(str(sandbox.container_id))
            
            if container_status == "running":
                # Dockerコンテナは稼働しているのにDBはFAILEDの場合
                print(f"SandboxManagerService: Container {sandbox.container_id} is running but DB status is FAILED. Correcting DB status to RUNNING.")
                self._crud.update_sandbox_status(
                    sandbox_id=str(sandbox.id),
                    status=SandboxStatus.RUNNING,
                    error_message=None,
                    exit_code=0
                )
                # 既に実行中のコンテナを再利用できるので、新たなプロビジョニングは不要
                continue # 次のbroken sandboxへ

            # コンテナが停止しているか、存在しない場合
            print(f"SandboxManagerService: Container {sandbox.container_id} is {container_status}. Deactivating DB entry and cleaning up Docker.")
            if sandbox.container_id:
                try:
                    self._docker_client.stop_and_remove_container(str(sandbox.container_id))
                    print(f"SandboxManagerService: Removed old container {sandbox.container_id}.")
                except Exception as ce:
                    print(f"SandboxManagerService: Could not remove old container {sandbox.container_id}: {ce}")

            # DBエントリを非アクティブにする（もう使わない）
            self._crud.deactivate_sandbox(str(sandbox.id))
            print(f"SandboxManagerService: Deactivated old broken sandbox DB entry {sandbox.id}.")

            # ここで llm_agent_id の新しいセッションが次回要求されたときに、
            # provision_and_execute_sandbox_session が新しいコンテナを起動するようにする。
            # monitor_and_regenerate_broken_sandboxes 内で直接 provision を呼び出すと、
            # コード実行も伴い、新たな問題を引き起こす可能性があるため、ここでは呼び出さない。
            # プロビジョニングはあくまでユーザーからのリクエスト時のみ行われるべき。

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
                if sandbox.container_id:
                    try:
                        # find_container_by_name を使ってコンテナが実際に存在するか確認してから削除
                        container_obj = self._docker_client.find_container_by_name(f"sandbox-{sandbox.llm_agent_id}")
                        if container_obj and container_obj.id == sandbox.container_id:
                            self._docker_client.stop_and_remove_container(str(sandbox.container_id))
                            print(f"SandboxManagerService: Removed inactive container {sandbox.container_id}.")
                        else:
                            print(f"SandboxManagerService: Container {sandbox.container_id} not found in Docker for cleanup (might already be removed).")
                    except Exception as e:
                        print(f"SandboxManagerService: Could not remove inactive container {sandbox.container_id}: {e}")
                self._crud.delete_sandbox(str(sandbox.id))
        print("SandboxManagerService: Cleanup complete.")
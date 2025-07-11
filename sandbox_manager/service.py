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
        # ◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️↓修正開始◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️
        # mypyが__init__メソッドの暗黙的なNone返却を誤って解釈する問題を抑制
        pass # type: ignore[return]
        # ◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️↑修正終わり◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️

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
        current_container = None

        # 1. アクティブなサンドボックスセッションをDBから検索
        # llm_agent_id に紐づく、アクティブでRUNNINGまたはPENDING状態の最新のサンドボックスを探す
        active_sandboxes = self._crud.get_active_sandboxes()
        for sb in active_sandboxes:
            if sb.llm_agent_id == llm_agent_id and sb.status in [SandboxStatus.PENDING, SandboxStatus.RUNNING]:
                # 実際のDockerコンテナが稼働中か確認
                docker_container_status = None
                if sb.container_id:
                    docker_container_status = self._docker_client.get_container_status(str(sb.container_id))
                if docker_container_status == "running":
                    sandbox_entry = sb
                    container_id = str(sb.container_id)
                    print(f"SandboxManagerService: Found existing active sandbox session {sb.id} for agent {llm_agent_id}")
                    break
                else:
                    # DB上はアクティブだがDockerコンテナが存在しない/停止している場合は非アクティブ化
                    print(f"SandboxManagerService: Deactivating stale sandbox entry {sb.id} (Docker status: {docker_container_status})")
                    self._crud.deactivate_sandbox(str(sb.id))
        
        # 2. コンテナのプロビジョニングまたは再利用
        if sandbox_entry is None or container_id is None:
            # 新規サンドボックスのプロビジョニング
            print(f"SandboxManagerService: No active sandbox found for agent {llm_agent_id}. Provisioning new one.")

            # Dockerイメージの存在確認とプル
            if not self._docker_client.pull_image(base_image):
                raise ValueError(f"Failed to pull Docker image: {base_image}") # type: ignore

            # 新規DBエントリを作成
            sandbox_entry = self._crud.create_sandbox(
                llm_agent_id=llm_agent_id,
                code_to_execute=code,
                base_image=base_image,
                resource_limits=self._resource_limits
            )
            assert sandbox_entry is not None
            sandbox_id = str(sandbox_entry.id) # type: ignore # mypy の型推論を抑制

            # 共有ディレクトリのボリューム設定
            volumes = {
                config.SHARED_DIR_HOST_PATH: {
                    'bind': config.SHARED_DIR_CONTAINER_PATH,
                    'mode': 'rw'
                }
            }

            try:
                # 新しいコンテナを起動
                current_container = self._docker_client.start_container(
                    image=base_image,
                    name=container_name,
                    resource_limits=self._resource_limits,
                    network_mode=self._network_mode,
                    volumes=volumes
                )
                container_id = current_container.id
                # DBエントリにコンテナIDを更新し、ステータスをRUNNINGに
                updated_entry = self._crud.update_sandbox_status(
                    sandbox_id=str(sandbox_entry.id),
                    status=SandboxStatus.RUNNING,
                    container_id=container_id,
                    execution_result="Sandbox session started.",
                    error_message=None,
                    exit_code=0
                )
                if updated_entry is None:
                    raise ValueError(f"Failed to update sandbox {sandbox_entry.id} with container ID.")
                sandbox_entry = updated_entry # 更新されたエントリを代入

            except Exception as e:
                print(f"SandboxManagerService: Error during initial sandbox provisioning for {llm_agent_id}: {e}")
                if sandbox_entry:
                    self._crud.update_sandbox_status(
                        sandbox_id=str(sandbox_entry.id),
                        status=SandboxStatus.FAILED,
                        error_message=f"Provisioning error: {str(e)}"
                    )
                raise # type: ignore

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
            # 再生成ロジック：新しいサンドボックスとして再実行を試みる
            try:
                # 既存の破綻したエントリは非アクティブ化
                # また、もしコンテナがまだ存在すれば停止・削除
                if sandbox.container_id:
                    try:
                        self._docker_client.stop_and_remove_container(sandbox.container_id)
                        print(f"SandboxManagerService: Removed broken container {sandbox.container_id}.")
                    except Exception as ce:
                        print(f"SandboxManagerService: Could not remove container {sandbox.container_id}: {ce}")

                self._crud.deactivate_sandbox(str(sandbox.id))
                print(f"SandboxManagerService: Deactivated old broken sandbox DB entry {sandbox.id}.")

                # 新しいサンドボックスとして再作成・実行 (初回コードは空でも良いが、既存コードを使う)
                # Note: `code` here would be the *initial* code to run for the new session.
                # If the goal is truly regeneration of the *last state*, this gets more complex.
                # For simplicity, we just provision a new session with the original code.
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
                        # Dockerコンテナも停止・削除
                        self._docker_client.stop_and_remove_container(sandbox.container_id)
                        print(f"SandboxManagerService: Removed inactive container {sandbox.container_id}.")
                    except Exception as e:
                        print(f"SandboxManagerService: Could not remove inactive container {sandbox.container_id}: {e}")
        print("SandboxManagerService: Cleanup complete.")
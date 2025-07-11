# program_builder/sandbox_manager/service.py
import time
from typing import Dict, Any, Tuple, Optional

from database.crud import CRUD
from database.models import Sandbox, SandboxStatus
from sandbox_manager.docker_client import DockerClient
from config import config

class SandboxManagerService:
    def __init__(self, db_crud: CRUD, docker_client: DockerClient,
                 resource_limits: Dict[str, Any], network_mode: str,
                 default_base_image: str, sandbox_timeout_seconds: int):
        self._crud = db_crud
        self._docker_client = docker_client
        self._resource_limits = resource_limits
        self._network_mode = network_mode
        self._default_base_image = default_base_image
        self._sandbox_timeout_seconds = sandbox_timeout_seconds

    def create_and_run_sandbox(self, llm_agent_id: str, code: str, base_image: Optional[str] = None) -> Sandbox:
        """
        サンドボックスをデータベースに登録し、Dockerコンテナとして起動します。
        """
        if base_image is None:
            base_image = self._default_base_image

        # 1. データベースにサンドボックス情報を登録 (PENDINGステータス)
        sandbox_entry = self._crud.create_sandbox(
            llm_agent_id=llm_agent_id,
            code_to_execute=code,
            base_image=base_image,
            resource_limits=self._resource_limits # 保存用
        )
        sandbox_id = sandbox_entry.id
        container_name = f"sandbox-{sandbox_id}"

        print(f"SandboxManagerService: Created DB entry for sandbox {sandbox_id}")

        # 2. Dockerイメージの存在確認とプル
        if not self._docker_client.pull_image(base_image):
            # イメージが見つからないかプルに失敗した場合
            self._crud.update_sandbox_status(
                str(sandbox_id),
                SandboxStatus.FAILED, # <-- 修正
                error_message=f"Failed to pull image: {base_image}"
            )
            raise ValueError(f"Failed to pull Docker image: {base_image}") # type: ignore

        # 3. Dockerコンテナを起動し、コードを実行
        # コードはファイルとしてマウントするか、直接コマンドとして渡すか。
        # ここではbash -cで直接渡す簡易的な方法を使用。
        # 実際の運用ではコードをボリュームマウントする方が安全かつ確実。

        # f-string内でバックスラッシュのエスケープが複雑になるのを避けるため、
        # まずコード文字列内のシングルクォートをエスケープしたものを変数に格納する
        escaped_code = code.replace("'", "'\\''") # シングルクォートを \' に置換
                                                  # bash -c の中でさらにエスケープされるため、'' を ''\'' にする

        if "python" in base_image.lower():
            command_to_run = f"python -c '{escaped_code}'"
        elif "node" in base_image.lower(): # Node.jsの処理を追加
            command_to_run = f"node -e '{escaped_code}'"
        else:
            # デフォルトまたは不明なイメージの場合の処理。エラーとするか、一般的なコマンドを実行するか。
            # ここではエラーとしています。
            self._crud.update_sandbox_status(
                str(sandbox_id),
                SandboxStatus.FAILED, # <-- 修正
                error_message=f"Unsupported base image for code execution: {base_image}"
            )
            raise ValueError(f"Unsupported base image for code execution: {base_image}. Only Python and Node.js are explicitly supported in this example.") # type: ignore

        try:
            output, error, exit_code = self._docker_client.run_container(
                image=base_image,
                command=command_to_run,
                name=container_name,
                resource_limits=self._resource_limits,
                network_mode=self._network_mode,
                timeout=self._sandbox_timeout_seconds
            )

            status = SandboxStatus.SUCCESS if exit_code == 0 else SandboxStatus.FAILED
            error_message = error if error else None
            execution_result = output if output else "No output."

            # 4. 実行結果をデータベースに更新
            updated_sandbox = self._crud.update_sandbox_status(
                sandbox_id=str(sandbox_entry.id), # <-- ここで Column オブジェクトではなく、sandbox_entry.id (str) を渡す
                status=status,
                container_id=None,
                execution_result=execution_result,
                error_message=error_message,
                exit_code=exit_code
            )
            if updated_sandbox is None:
                raise ValueError(f"Failed to update sandbox {sandbox_id} in database")
            print(f"SandboxManagerService: Sandbox {sandbox_id} finished with status {status}")
            return updated_sandbox

        except Exception as e:
            print(f"SandboxManagerService: Error running sandbox {sandbox_id}: {e}")
            self._crud.update_sandbox_status(
                sandbox_id=str(sandbox_id),
                status=SandboxStatus.FAILED, # <-- 修正
                error_message=f"Execution error: {str(e)}"
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
            # この例では、同じコードで新しいエントリを作成し直すシンプルな再生成
            try:
                # 既存の破綻したエントリは非アクティブ化
                self._crud.deactivate_sandbox(str(sandbox.id)) # <-- 修正
                print(f"SandboxManagerService: Deactivated old broken sandbox {sandbox.id}.")
                # 新しいサンドボックスとして再作成・実行
                self.create_and_run_sandbox(
                    llm_agent_id=sandbox.llm_agent_id,
                    code=sandbox.code_to_execute,
                    base_image=sandbox.base_image
                )
                print(f"SandboxManagerService: Successfully regenerated sandbox for {sandbox.id}.")
            except Exception as e:
                print(f"SandboxManagerService: Failed to regenerate sandbox for {sandbox.id}: {e}")
        print("SandboxManagerService: Monitoring complete.")

    def cleanup_inactive_sandboxes(self):
        """不要になった非アクティブなサンドボックスのDBエントリを削除します。（省略）"""
        pass
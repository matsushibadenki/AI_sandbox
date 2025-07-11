# AI_sandbox/sandbox_manager/docker_client.py
import time
from typing import Any, Dict, Optional, Tuple

import docker
from docker.errors import APIError, ContainerError, ImageNotFound, NotFound
from docker.models.containers import Container


class DockerClient:
    def __init__(self, docker_client: docker.client.DockerClient, sandbox_labels: Dict[str, str]):
        self._client = docker_client
        self._sandbox_labels = sandbox_labels

    def pull_image(self, image_name: str) -> bool:
        try:
            print(f"DockerClient: Pulling image {image_name}...")
            self._client.images.pull(image_name)
            print(f"DockerClient: Image {image_name} pulled successfully.")
            return True
        except ImageNotFound:
            print(f"DockerClient: Image {image_name} not found.")
            return False
        except APIError as e:
            print(f"DockerClient: Error pulling image {image_name}: {e}")
            return False

    def start_container(self, image: str, name: str,
                        resource_limits: Dict[str, Any], network_mode: str,
                        volumes: Optional[Dict[str, Dict[str, str]]] = None) -> Container:
        """
        新しいDockerコンテナを起動し、そのコンテナオブジェクトを返します。
        このメソッドはコンテナを自動的に削除しません。
        """
        labels_with_name = self._sandbox_labels.copy()
        labels_with_name["sandbox_name"] = name
        try:
            print(f"DockerClient: Starting new container {name} with image {image}")
            container = self._client.containers.run(
                image,
                detach=True,
                name=name,
                labels=labels_with_name,
                read_only=False, # 共有ディレクトリに書き込むためFalse
                network_mode=network_mode,
                volumes=volumes,
                **resource_limits
            )
            print(f"DockerClient: Container {name} (ID: {container.id}) started.")
            return container
        except APIError as e:
            raise Exception(f"Failed to start container {name}: {e}")

    def exec_command_in_container(self, container_id: str, command: str, timeout: int) -> Tuple[Optional[str], Optional[str], Optional[int]]:
        """
        既存の実行中コンテナ内でコマンドを実行し、その結果を返します。
        """
        output = None
        error = None
        exit_code = None
        try:
            container = self._client.containers.get(container_id)
            print(f"DockerClient: Executing command in container {container_id}: {command}")
            # exec_run はコマンド実行と出力を取得する
            # ◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️↓修正開始◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️
            exec_result = container.exec_run(
                cmd=f"bash -c \"{command}\"",
                stream=False, # Trueにするとストリームで受け取るが、ここではシンプルに
                demux=True, # stdoutとstderrを分離
                tty=False, # TTYを割り当てない
                detach=False,
                # timeout=timeout # exec_run は timeout 引数をサポートしていません
            )
            # ◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️↑修正終わり◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️
            stdout_bytes, stderr_bytes = exec_result.output
            exit_code = exec_result.exit_code
            output = stdout_bytes.decode('utf-8') if stdout_bytes else None
            error = stderr_bytes.decode('utf-8') if stderr_bytes else None

            print(f"DockerClient: Command in {container_id} finished with exit code {exit_code}")
            if output:
                print(f"DockerClient: Output: {output.strip()}")
            if error:
                print(f"DockerClient: Error: {error.strip()}")
            return output, error, exit_code
        except NotFound:
            error = f"Container {container_id} not found."
            print(f"DockerClient: {error}")
            return None, error, -1
        except APIError as e:
            error = f"Docker API error executing command in {container_id}: {e}"
            print(f"DockerClient: {error}")
            return None, error, -1
        except Exception as e:
            error = f"Unexpected error executing command in {container_id}: {e}"
            print(f"DockerClient: {error}")
            return None, error, -2

    def get_container_status(self, container_id: str) -> Optional[str]:
        try:
            container = self._client.containers.get(container_id)
            return container.status
        except docker.errors.NotFound:
            return None
        except APIError as e:
            print(f"DockerClient: Error getting container status for {container_id}: {e}")
            return None

    def find_container_by_name(self, name: str) -> Optional[Container]:
        """指定された名前のコンテナを見つけ、存在すれば返します。（停止中含む）"""
        try:
            return self._client.containers.get(name)
        except NotFound:
            return None

    def list_sandbox_containers(self) -> list[Container]:
        """サンドボックスラベルを持つ稼働中のコンテナをリストします。"""
        # labels filter needs to be exact, so this might need adjustment if only one label is used
        # For now, it seems fine as _sandbox_labels should contain all labels
        return self._client.containers.list(filters={"label": list(self._sandbox_labels.items())[0]})

    def stop_and_remove_container(self, container_id: str):
        try:
            container = self._client.containers.get(container_id)
            # if self._is_sandbox_container(container): # _is_sandbox_container は不要かもしれない
            print(f"DockerClient: Stopping and removing container {container_id}")
            container.stop(timeout=5)
            container.remove(v=True, force=True)
            # else:
            #     print(f"DockerClient: Not a sandbox container, skipping removal for {container_id}")
        except docker.errors.NotFound:
            print(f"DockerClient: Container {container_id} not found for stop/remove.")
        except APIError as e:
            print(f"DockerClient: Error stopping/removing container {container_id}: {e}")

    # _is_sandbox_container method is still useful for verification but not strictly necessary for stop_and_remove_container logic if we trust the caller.
    def _is_sandbox_container(self, container: Container) -> bool:
        """指定されたコンテナがサンドボックスラベルを持っているか確認します。"""
        for key, value in self._sandbox_labels.items():
            if container.labels.get(key) == value:
                return True
        return False
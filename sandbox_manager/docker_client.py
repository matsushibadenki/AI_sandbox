# program_builder/sandbox_manager/docker_client.py
import docker
from docker.models.containers import Container
from docker.errors import ImageNotFound, ContainerError, APIError
from typing import Dict, Any, Tuple, Optional
import time

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

    def run_container(self, image: str, command: str,
                      name: str,
                      resource_limits: Dict[str, Any],
                      network_mode: str,
                      timeout: int) -> Tuple[Optional[str], Optional[str], Optional[int]]:
        """
        指定されたコマンドを実行するサンドボックスコンテナを起動します。
        出力、エラー、終了コードを返します。
        """
        container = None
        output = None
        error = None
        exit_code = None

        labels_with_name = self._sandbox_labels.copy()
        labels_with_name["sandbox_name"] = name

        try:
            print(f"DockerClient: Running container {name} with image {image} and command: {command}")
            container = self._client.containers.run(
                image,
                command=f"bash -c \"{command}\"", # シェルでコマンドを実行
                detach=True,
                name=name,
                labels=labels_with_name,
                read_only=True, # ファイルシステムを読み取り専用に
                network_mode=network_mode,
                **resource_limits # メモリ、CPUなどの制限
            )

            # コンテナの実行終了を待機
            # timeoutパラメータは run() に渡せるが、コンテナの内部処理タイムアウトを正確に制御するため、
            # ここでは wait() を使って明示的にタイムアウトを管理
            result = container.wait(timeout=timeout) # seconds
            exit_code = result['StatusCode']

            output = container.logs(stdout=True, stderr=False).decode('utf-8')
            error = container.logs(stdout=False, stderr=True).decode('utf-8')

            print(f"DockerClient: Container {name} finished with exit code {exit_code}")
            print(f"DockerClient: Output: {output.strip()}")
            if error:
                print(f"DockerClient: Error: {error.strip()}")

        except ContainerError as e:
            print(f"DockerClient: Container {name} exited with error: {e}")
            exit_code = e.exit_status
            output = e.stdout.decode('utf-8')
            error = e.stderr.decode('utf-8')
        except APIError as e:
            print(f"DockerClient: Docker API error for container {name}: {e}")
            error = str(e)
            exit_code = -1 # APIエラーを示すコード
        except Exception as e:
            print(f"DockerClient: Unexpected error for container {name}: {e}")
            error = str(e)
            exit_code = -2 # その他のエラー
        finally:
            if container:
                # コンテナを停止・削除
                print(f"DockerClient: Stopping and removing container {name} (ID: {container.id})")
                try:
                    container.stop(timeout=5)
                    container.remove(v=True, force=True) # ボリュームも削除、強制削除
                except APIError as e:
                    print(f"DockerClient: Error stopping/removing container {name}: {e}")
        return output, error, exit_code

    def get_container_status(self, container_id: str) -> Optional[str]:
        try:
            container = self._client.containers.get(container_id)
            return container.status
        except docker.errors.NotFound:
            return None # コンテナが存在しない
        except APIError as e:
            print(f"DockerClient: Error getting container status for {container_id}: {e}")
            return None

    def list_sandbox_containers(self) -> list[Container]:
        """サンドボックスラベルを持つ稼働中のコンテナをリストします。"""
        return self._client.containers.list(filters={"label": list(self._sandbox_labels.items())[0]})

    def stop_and_remove_container(self, container_id: str):
        try:
            container = self._client.containers.get(container_id)
            if self._is_sandbox_container(container): # サンドボックスか確認
                print(f"DockerClient: Stopping and removing container {container_id}")
                container.stop(timeout=5)
                container.remove(v=True, force=True)
            else:
                print(f"DockerClient: Not a sandbox container, skipping removal for {container_id}")
        except docker.errors.NotFound:
            print(f"DockerClient: Container {container_id} not found for stop/remove.")
        except APIError as e:
            print(f"DockerClient: Error stopping/removing container {container_id}: {e}")

    def _is_sandbox_container(self, container: Container) -> bool:
        """指定されたコンテナがサンドボックスラベルを持っているか確認します。"""
        for key, value in self._sandbox_labels.items():
            if container.labels.get(key) == value:
                return True
        return False
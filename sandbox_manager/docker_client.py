# AI_sandbox/sandbox_manager/docker_client.py
import time
from typing import Any, Dict, Optional, Tuple

import docker
from docker.errors import APIError, ContainerError, ImageNotFound, NotFound
from docker.models.containers import Container
# ◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️↓修正開始◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️
import os
import uuid
# ◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️↑修正終わり◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️


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

    # ◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️↓修正開始◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️
    def exec_code_in_container(self, container_id: str, code_string: str, base_image: str, timeout: int) -> Tuple[Optional[str], Optional[str], Optional[int]]:
        """
        既存の実行中コンテナ内で提供されたコードを実行し、その結果を返します。
        コードは一時ファイルに書き込まれ、適切なインタプリタで実行されます。
        """
        output = None
        error = None
        exit_code = None
        temp_filename = f"temp_script_{uuid.uuid4().hex}"
        
        # Determine the interpreter and file extension based on the base_image
        interpreter = ""
        file_extension = ""
        if "python" in base_image:
            interpreter = "python"
            file_extension = ".py"
        elif "node" in base_image:
            interpreter = "node"
            file_extension = ".js"
        else:
            # Fallback to bash for generic images, but warn
            print(f"DockerClient: Warning: Unknown base image '{base_image}'. Attempting to execute with bash.")
            interpreter = "bash"
            file_extension = ".sh" # or no extension, depending on the script nature

        script_path_in_container = os.path.join("/share_area", temp_filename + file_extension)

        try:
            container = self._client.containers.get(container_id)
            print(f"DockerClient: Preparing to execute code in container {container_id} using {interpreter}...")

            # 1. Write the code to a temporary file in the container's shared directory
            # Use printf for better handling of newlines and special characters than echo
            # Escape single quotes in the code_string for shell command
            escaped_code_string = code_string.replace("'", "'\\''")
            write_command = f"printf '%s' '{escaped_code_string}' > {script_path_in_container}"
            
            print(f"DockerClient: Writing code to {script_path_in_container}...")
            write_result = container.exec_run(
                cmd=f"bash -c \"{write_command}\"",
                demux=True,
                tty=False,
                detach=False
            )
            if write_result.exit_code != 0:
                stdout_bytes, stderr_bytes = write_result.output
                write_error = stderr_bytes.decode('utf-8') if stderr_bytes else "Unknown write error."
                return None, f"Failed to write script to container: {write_error}", write_result.exit_code

            # 2. Execute the temporary file
            execution_command = ""
            if interpreter == "python":
                execution_command = f"{interpreter} {script_path_in_container}"
            elif interpreter == "node":
                execution_command = f"{interpreter} {script_path_in_container}"
            elif interpreter == "bash":
                # For generic bash, ensure it's executable first, then run
                chmod_cmd = f"chmod +x {script_path_in_container}"
                chmod_result = container.exec_run(cmd=f"bash -c \"{chmod_cmd}\"", demux=True)
                if chmod_result.exit_code != 0:
                    return None, f"Failed to make script executable: {chmod_result.output[1].decode('utf-8')}", chmod_result.exit_code
                execution_command = f"bash {script_path_in_container}" # Explicitly run with bash

            print(f"DockerClient: Executing script in container {container_id}: {execution_command}")
            exec_result = container.exec_run(
                cmd=f"bash -c \"{execution_command}\"",
                stream=False,
                demux=True,
                tty=False,
                detach=False,
                # timeout=timeout # exec_run does not support timeout argument directly
            )
            stdout_bytes, stderr_bytes = exec_result.output
            exit_code = exec_result.exit_code
            output = stdout_bytes.decode('utf-8') if stdout_bytes else None
            error = stderr_bytes.decode('utf-8') if stderr_bytes else None

            print(f"DockerClient: Script execution in {container_id} finished with exit code {exit_code}")
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
        finally:
            # Clean up the temporary script file
            if script_path_in_container:
                try:
                    container = self._client.containers.get(container_id)
                    cleanup_command = f"rm -f {script_path_in_container}"
                    print(f"DockerClient: Cleaning up temporary script: {cleanup_command}")
                    container.exec_run(cmd=f"bash -c \"{cleanup_command}\"", demux=True)
                except Exception as e:
                    print(f"DockerClient: Error during temporary script cleanup: {e}")

    # Old exec_command_in_container is no longer used for code execution,
    # but might be kept for general shell commands if needed.
    # For now, it is replaced by exec_code_in_container.
    def exec_command_in_container(self, container_id: str, command: str, timeout: int) -> Tuple[Optional[str], Optional[str], Optional[int]]:
        """
        既存の実行中コンテナ内で汎用シェルコマンドを実行し、その結果を返します。
        このメソッドは、exec_code_in_container とは異なり、渡されたコマンドを直接 bash で実行します。
        """
        output = None
        error = None
        exit_code = None
        try:
            container = self._client.containers.get(container_id)
            print(f"DockerClient: Executing generic command in container {container_id}: {command}")
            exec_result = container.exec_run(
                cmd=f"bash -c \"{command}\"",
                stream=False,
                demux=True,
                tty=False,
                detach=False,
            )
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
    # ◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️↑修正終わり◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️

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
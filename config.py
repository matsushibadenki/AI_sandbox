# AI_sandbox/config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./sandbox_manager.db")
    LLM_MODEL_NAME: str = os.getenv("LLM_MODEL_NAME", "gemma3:latest")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "http://localhost:11434")
    SANDBOX_BASE_IMAGE: str = os.getenv("SANDBOX_BASE_IMAGE", "python:3.10-slim-bookworm")

    # サンドボックスのDocker設定
    # ◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️↓修正開始◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️
    SANDBOX_RESOURCE_LIMITS = {
        "mem_limit": "2g", # メモリ制限を1gから2gに増量 (デバッグのため一時的に)
    # ◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️↑修正終わり◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️
        "cpu_period": 100000,
        "cpu_quota": 50000, # 0.5 CPU
        "pids_limit": 50,
    }
    SANDBOX_NETWORK_MODE: str = "sandbox_network" # 'none' または 'sandbox_network'
    SANDBOX_CONTAINER_LABELS = {"com.example.type": "sandbox"}
    SANDBOX_TIMEOUT_SECONDS: int = 60 # サンドボックス実行の最大時間

    # ユーザーとの共有ディレクトリ設定
    # ホストOS上のパスとコンテナ内のマウントポイント
    SHARED_DIR_HOST_PATH: str = os.getenv("SHARED_DIR_HOST_PATH", os.path.abspath(os.path.join(os.path.dirname(__file__), "shared_files")))
    SHARED_DIR_CONTAINER_PATH: str = "/share_area" # コンテナ内のマウントポイント

config = Config()
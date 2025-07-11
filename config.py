# program_builder/config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./sandbox_manager.db")
    LLM_MODEL_NAME: str = os.getenv("LLM_MODEL_NAME", "gemma3:latest") # Ollamaで使うモデル名
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "http://localhost:11434") # OllamaのデフォルトURL
    SANDBOX_BASE_IMAGE: str = os.getenv("SANDBOX_BASE_IMAGE", "python:3.10-slim-bookworm") # デフォルトのサンドボックスベースイメージ

    # サンドボックスのDocker設定
    SANDBOX_RESOURCE_LIMITS = {
        "mem_limit": "256m",
        "cpu_period": 100000,
        "cpu_quota": 50000, # 0.5 CPU
        "pids_limit": 50,
    }
    SANDBOX_NETWORK_MODE: str = "none" # 'none' または 'sandbox_network'
    SANDBOX_CONTAINER_LABELS = {"com.example.type": "sandbox"}
    SANDBOX_TIMEOUT_SECONDS: int = 60 # サンドボックス実行の最大時間

config = Config()
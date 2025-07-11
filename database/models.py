# program_builder/database/models.py
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Enum
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import enum
from typing import Type # Type を追加 (Base を型ヒントで使う場合)

Base = declarative_base()

class SandboxStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    STOPPED = "stopped"
    REGENERATING = "regenerating" # 破綻時の再生成中

class Sandbox(Base):
    __tablename__ = "sandboxes"

    id = Column(String, primary_key=True) # サンドボックスのユニークID (UUIDなど)
    container_id = Column(String, nullable=True) # 実際のDockerコンテナID
    # Enum の型ヒントを修正
    status: SandboxStatus = Column(Enum(SandboxStatus), default=SandboxStatus.PENDING, nullable=False) # <-- 修正
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    last_updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    llm_agent_id = Column(String, nullable=False) # どのLLMエージェントが利用しているか
    code_to_execute = Column(Text, nullable=False)
    execution_result = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    resource_limits_applied = Column(Text, nullable=True) # JSON形式で保存
    is_active = Column(Boolean, default=True, nullable=False) # 現在アクティブなサンドボックスか
    base_image = Column(String, nullable=False) # 使用したベースイメージ
    exit_code = Column(Integer, nullable=True) # コンテナの終了コード

    def __repr__(self):
        return f"<Sandbox(id='{self.id}', status='{self.status}', container_id='{self.container_id}')>"
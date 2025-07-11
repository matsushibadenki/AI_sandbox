# program_builder/di_container.py
from injector import Injector, Module, singleton, provider

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine # <-- Engine を追加
from sqlalchemy.orm import sessionmaker, Session

import docker
from docker.client import DockerClient as DockerPyClient # <-- 型衝突を避けるために別名でインポート
from typing import Generator # <-- Generator を追加

from config import config
from database.models import Base
from database.crud import CRUD
from sandbox_manager.docker_client import DockerClient # 自作のDockerClientクラス
from sandbox_manager.service import SandboxManagerService # <-- 追加

class CoreModule(Module):
    @singleton
    @provider
    def provide_db_engine(self) -> Engine: # <-- create_engine を Engine に修正
        return create_engine(config.DATABASE_URL)

    @singleton
    @provider
    def provide_db_session_maker(self, engine: Engine) -> sessionmaker: # <-- create_engine を Engine に修正
        Base.metadata.create_all(engine) # データベース初期化
        return sessionmaker(autocommit=False, autoflush=False, bind=engine)

    @provider
    def provide_db_session(self, session_maker: sessionmaker) -> Generator[Session, None, None]: # <-- Generator 型を修正
        with session_maker() as session:
            yield session

    @singleton
    @provider
    def provide_docker_client(self) -> DockerClient:
        # Dockerデーモンとの接続を確立
        return DockerClient(
            docker_client=docker.from_env(),
            sandbox_labels=config.SANDBOX_CONTAINER_LABELS
        )

    @singleton
    @provider
    def provide_sandbox_manager_service(self, crud: CRUD, docker_client: DockerClient) -> SandboxManagerService:
        return SandboxManagerService(
            db_crud=crud,
            docker_client=docker_client,
            resource_limits=config.SANDBOX_RESOURCE_LIMITS,
            network_mode=config.SANDBOX_NETWORK_MODE,
            default_base_image=config.SANDBOX_BASE_IMAGE,
            sandbox_timeout_seconds=config.SANDBOX_TIMEOUT_SECONDS
        )

    @singleton
    @provider
    def provide_crud(self, session_maker: sessionmaker) -> CRUD:
        return CRUD(session_maker)

main_injector = Injector([CoreModule()])
# AI_sandbox/database/crud.py
import json
import uuid
from typing import Dict, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from database.models import Sandbox, SandboxStatus


class CRUD:
    def __init__(self, session_maker: sessionmaker):
        self.SessionLocal = session_maker

    def create_sandbox(self, llm_agent_id: str, code_to_execute: str, base_image: str, resource_limits: Dict) -> Sandbox:
        sandbox_id = str(uuid.uuid4())
        with self.SessionLocal() as session:
            db_sandbox = Sandbox(
                id=sandbox_id,
                llm_agent_id=llm_agent_id,
                code_to_execute=code_to_execute,
                base_image=base_image,
                resource_limits_applied=json.dumps(resource_limits)
            )
            session.add(db_sandbox)
            session.commit()
            session.refresh(db_sandbox)
            return db_sandbox

    def get_sandbox(self, sandbox_id: str) -> Optional[Sandbox]:
        with self.SessionLocal() as session:
            return session.query(Sandbox).filter(Sandbox.id == sandbox_id).first()

    def update_sandbox_status(self, sandbox_id: str, status: SandboxStatus,
                              container_id: Optional[str] = None,
                              execution_result: Optional[str] = None,
                              error_message: Optional[str] = None,
                              exit_code: Optional[int] = None) -> Optional[Sandbox]:
        with self.SessionLocal() as session:
            db_sandbox = session.query(Sandbox).filter(Sandbox.id == sandbox_id).first()
            if db_sandbox:
                db_sandbox.status = status
                if container_id:
                    db_sandbox.container_id = container_id
                if execution_result:
                    db_sandbox.execution_result = execution_result
                if error_message:
                    db_sandbox.error_message = error_message
                if exit_code is not None:
                    db_sandbox.exit_code = exit_code
                session.commit()
                session.refresh(db_sandbox)
            return db_sandbox

    def deactivate_sandbox(self, sandbox_id: str) -> Optional[Sandbox]:
        with self.SessionLocal() as session:
            db_sandbox = session.query(Sandbox).filter(Sandbox.id == sandbox_id).first()
            if db_sandbox:
                db_sandbox.is_active = False
                session.commit()
                session.refresh(db_sandbox)
            return db_sandbox

    def get_active_sandboxes(self) -> list[Sandbox]:
        with self.SessionLocal() as session:
            # Active means is_active=True AND status is not FAILED/SUCCESS/STOPPED (i.e., still potentially usable)
            return session.query(Sandbox).filter(
                Sandbox.is_active == True,
                # ◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️↓修正開始◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️
                Sandbox.status.in_([SandboxStatus.PENDING, SandboxStatus.RUNNING, SandboxStatus.REGENERATING]) # type: ignore[attr-defined]
                # ◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️↑修正終わり◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️
            ).all()

    def get_broken_sandboxes(self) -> list[Sandbox]:
        with self.SessionLocal() as session:
            return session.query(Sandbox).filter(Sandbox.status == SandboxStatus.FAILED, Sandbox.is_active == True).all()

    def get_all_sandboxes(self) -> list[Sandbox]:
        with self.SessionLocal() as session:
            return session.query(Sandbox).all()

    def delete_sandbox(self, sandbox_id: str) -> bool:
        with self.SessionLocal() as session:
            db_sandbox = session.query(Sandbox).filter(Sandbox.id == sandbox_id).first()
            if db_sandbox:
                session.delete(db_sandbox)
                session.commit()
                return True
            return False
# AI_sandbox/main.py

import asyncio
import time
import uuid

from di_container import main_injector
from pco.agent import ProgramConstructionAgent
from pco.tools import SandboxTool
from sandbox_manager.service import SandboxManagerService
from database.crud import CRUD
from sqlalchemy.orm import sessionmaker # sessionmaker をインポート

# DIコンテナから依存関係を解決して取得
def get_pco_agent() -> ProgramConstructionAgent:
    sandbox_manager_service = main_injector.get(SandboxManagerService)
    crud = main_injector.get(CRUD) # crud is injected into SandboxManagerService

    # SandboxToolのインスタンスを作成し、依存性を注入
    sandbox_tool_instance = SandboxTool(sandbox_manager_service=sandbox_manager_service)

    # ProgramConstructionAgentのインスタンスを作成し、ツールを注入
    pco_agent = ProgramConstructionAgent(sandbox_tool=sandbox_tool_instance)
    return pco_agent

async def run_periodic_monitor_and_cleanup(sandbox_manager_service: SandboxManagerService):
    """定期的に破綻サンドボックスを監視し、再生成を試み、非アクティブなサンドボックスをクリーンアップするバックグラウンドタスク"""
    while True:
        await asyncio.sleep(30) # 30秒ごとに監視
        print("\n--- Running periodic sandbox monitor and cleanup ---")
        sandbox_manager_service.monitor_and_regenerate_broken_sandboxes()
        sandbox_manager_service.cleanup_inactive_sandboxes() # クリーンアップも実行
        print("--- Periodic sandbox monitor and cleanup finished ---\n")

async def main():
    print("Starting Program Construction System...")

    # DB初期化のため、一度セッションファクトリを解決
    _ = main_injector.get(sessionmaker)

    # サンドボックスマネージャーサービスを取得して、バックグラウンド監視を開始
    sandbox_manager_service = main_injector.get(SandboxManagerService)

    # 非同期タスクとしてバックグラウンド監視を開始
    monitor_cleanup_task = asyncio.create_task(run_periodic_monitor_and_cleanup(sandbox_manager_service))

    # PCOエージェントを取得
    pco_agent = get_pco_agent()

    # 例：LLMに簡単なプログラムを構築させる
    llm_agent_id_1 = str(uuid.uuid4()) # LLMエージェントのIDを模倣
    llm_agent_id_2 = str(uuid.uuid4()) # 別のLLMエージェントのIDを模倣

    print(f"LLM Agent ID 1: {llm_agent_id_1}")
    print(f"LLM Agent ID 2: {llm_agent_id_2}")

    # Task 1: Python program, illustrating persistence
    user_requirement_1 = "Create a Python file named 'my_script.py' in the shared directory that prints 'Hello from persistent Python!' and the current date/time. Then execute this script."
    print(f"\n--- LLM Agent {llm_agent_id_1} is starting task 1 (Python persistent session) ---")
    final_output_1 = await pco_agent.run_program_construction(user_requirement_1, llm_agent_id_1)
    print(f"\n--- LLM Agent {llm_agent_id_1} finished task 1 ---")
    print(f"Final Program Output:\n{final_output_1}")

    # Task 1.1: Execute another command in the *same* persistent Python sandbox
    user_requirement_1_1 = "Now, list the files in the shared directory and then modify 'my_script.py' to also print 'This is an update!' before running it again. Ensure the date/time is still printed."
    print(f"\n--- LLM Agent {llm_agent_id_1} is starting task 1.1 (Python persistent session update) ---")
    final_output_1_1 = await pco_agent.run_program_construction(user_requirement_1_1, llm_agent_id_1)
    print(f"\n--- LLM Agent {llm_agent_id_1} finished task 1.1 ---")
    print(f"Final Program Output:\n{final_output_1_1}")


    # Task 2: Node.js program, demonstrating separate persistent sandbox for another agent
    user_requirement_2 = "Create a Node.js file named 'node_script.js' in the shared directory that prints 'Hello from persistent Node.js!' and then tries to divide by zero. Execute it. Then modify it to print 'Division by zero is not allowed' instead of the error, and execute it again. Ensure previous content is removed or overwritten before writing."
    print(f"\n--- LLM Agent {llm_agent_id_2} is starting task 2 (Node.js persistent session) ---")
    final_output_2 = await pco_agent.run_program_construction(user_requirement_2, llm_agent_id_2)
    print(f"\n--- LLM Agent {llm_agent_id_2} finished task 2 ---")
    print(f"Final Program Output:\n{final_output_2}")

    # バックグラウンドタスクをキャンセルして終了
    monitor_cleanup_task.cancel()
    try:
        await monitor_cleanup_task
    except asyncio.CancelledError:
        print("Monitor and cleanup task cancelled.")

    print("System shutting down.")

if __name__ == "__main__":
    asyncio.run(main())
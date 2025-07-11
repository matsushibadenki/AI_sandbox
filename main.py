# program_builder/main.py

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
    crud = main_injector.get(CRUD)

    # SandboxToolのインスタンスを作成し、依存性を注入
    sandbox_tool_instance = SandboxTool(sandbox_manager_service=sandbox_manager_service)

    # ProgramConstructionAgentのインスタンスを作成し、ツールを注入
    pco_agent = ProgramConstructionAgent(sandbox_tool=sandbox_tool_instance)
    return pco_agent

async def run_periodic_monitor(sandbox_manager_service: SandboxManagerService):
    """定期的に破綻サンドボックスを監視し、再生成を試みるバックグラウンドタスク"""
    while True:
        await asyncio.sleep(30) # 30秒ごとに監視
        print("\n--- Running periodic sandbox monitor ---")
        sandbox_manager_service.monitor_and_regenerate_broken_sandboxes() # monitor_and_regenerate_broken_sandboxes が同期関数なので注意
        print("--- Periodic sandbox monitor finished ---\n")

# ◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️↓修正開始◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️
async def main():
    print("Starting Program Construction System...")

    # DB初期化のため、一度セッションファクトリを解決
    _ = main_injector.get(sessionmaker)

    # サンドボックスマネージャーサービスを取得して、バックグラウンド監視を開始
    sandbox_manager_service = main_injector.get(SandboxManagerService)

    # 非同期タスクとしてバックグラウンド監視を開始
    monitor_task = asyncio.create_task(run_periodic_monitor(sandbox_manager_service))

    # PCOエージェントを取得
    pco_agent = get_pco_agent()

    # 例：LLMに簡単なプログラムを構築させる
    llm_agent_id = str(uuid.uuid4()) # LLMエージェントのIDを模倣

    print(f"LLM Agent ID: {llm_agent_id}")
    user_requirement_1 = "Write a Python program that prints 'Hello, Autonomous AI Program Builder!' to standard output. Then make it print the current date and time."

    print(f"\n--- LLM Agent {llm_agent_id} is starting task 1 ---")
    # ここでエージェントの実行は同期的に行われる
    final_output_1 = pco_agent.run_program_construction(user_requirement_1, llm_agent_id)
    print(f"\n--- LLM Agent {llm_agent_id} finished task 1 ---")
    print(f"Final Program Output:\n{final_output_1}")

    # 別のタスク (例えば、エラーを出すようなコードを試す)
    user_requirement_2 = "Write a Node.js program that tries to divide by zero and print the error. Then modify it to print 'Division by zero is not allowed' instead of the error."
    print(f"\n--- LLM Agent {llm_agent_id} is starting task 2 ---")
    final_output_2 = pco_agent.run_program_construction(user_requirement_2, llm_agent_id)
    print(f"\n--- LLM Agent {llm_agent_id} finished task 2 ---")
    print(f"Final Program Output:\n{final_output_2}")

    # バックグラウンドタスクをキャンセルして終了
    # ここでモニタータスクが完全に終了するまで待つ（少し時間を置く）
    monitor_task.cancel()
    try:
        await monitor_task # await を追加
    except asyncio.CancelledError:
        print("Monitor task cancelled.")

    print("System shutting down.")

if __name__ == "__main__":
    asyncio.run(main()) # main 関数を非同期で実行
# ◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️↑修正終わり◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️◾️
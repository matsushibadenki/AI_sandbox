# AI_sandbox/main.py
import asyncio
import time
import uuid

from di_container import main_injector
from pco.agent import ProgramConstructionAgent
from pco.tools import SandboxTool
from sandbox_manager.service import SandboxManagerService
from database.crud import CRUD
from sqlalchemy.orm import sessionmaker

# DIコンテナから依存関係を解決して取得
def get_pco_agent() -> ProgramConstructionAgent:
    sandbox_manager_service = main_injector.get(SandboxManagerService)
    # crudはSandboxManagerServiceに注入されるので、ここで取得する必要はありません

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
        sandbox_manager_service.cleanup_inactive_sandboxes() # 非アクティブなものもクリーンアップ
        print("--- Periodic sandbox monitor and cleanup finished ---\n")

async def main():
    print("Starting Program Construction System...")

    # DB初期化のため、一度セッションファクトリを解決
    _ = main_injector.get(sessionmaker)

    # サンドボックスマネージャーサービスを取得
    sandbox_manager_service = main_injector.get(SandboxManagerService)
    
    # --- 初期化フェーズの開始 ---
    print("Initializing system... Cleaning up old sandboxes.")
    # 既存の非アクティブ/破綻したサンドボックスを起動時に一度だけクリーンアップ
    sandbox_manager_service.cleanup_inactive_sandboxes()
    sandbox_manager_service.monitor_and_regenerate_broken_sandboxes()
    print("Initialization complete.")
    # --- 初期化フェーズの終了 ---

    # 非同期タスクとしてバックグラウンド監視を開始
    monitor_cleanup_task = asyncio.create_task(run_periodic_monitor_and_cleanup(sandbox_manager_service))

    # PCOエージェントを取得
    pco_agent = get_pco_agent()

    # チャットセッション用の単一のLLMエージェントIDを生成
    llm_agent_id = str(uuid.uuid4()) 
    print(f"\nYour LLM Agent ID for this session: {llm_agent_id}")
    print("Type your requests. Type 'exit' or 'quit' to end the session.")

    while True:
        try:
            # ユーザーの入力を待つ
            user_input = await asyncio.to_thread(input, "\nUser: ") # 同期I/Oを非同期コンテキストで実行
            if user_input.lower() in ["exit", "quit"]:
                print("Ending session.")
                break

            if not user_input.strip():
                continue

            print(f"\nAI: Thinking... (Processing your request for agent ID: {llm_agent_id})")
            # AIエージェントにユーザーの要求を処理させる
            final_output = await pco_agent.run_program_construction(user_input, llm_agent_id)
            print(f"\nAI: {final_output}")
        except Exception as e:
            print(f"\nAI: An error occurred: {e}")
            print("AI: Please try rephrasing your request or check the system logs for more details.")

    # バックグラウンドタスクをキャンセルして終了
    monitor_cleanup_task.cancel()
    try:
        await monitor_cleanup_task
    except asyncio.CancelledError:
        print("Monitor and cleanup task cancelled.")

    print("System shutting down.")

if __name__ == "__main__":
    asyncio.run(main())
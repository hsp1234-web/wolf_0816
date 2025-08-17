# e2e_tests/test_multi_stage_task_lifecycle.py
import os
import uuid
import json
import requests
from pathlib import Path
import pytest
from playwright.sync_api import Page, expect

# --- Test Setup ---
# 移除了所有在模組層級的設定和匯入，改為使用 Pytest Fixtures

# --- Test Fixture for Setup and Teardown ---
@pytest.fixture(scope="function")
def multi_stage_task_chain(db_client): # <-- db_client 現在透過 fixture 注入
    """
    建立一個多階段任務鏈 (youtube_download -> gemini_process) 並在測試後清理。
    """
    # 1. Setup: 建立假任務鏈
    download_task_id = str(uuid.uuid4())
    process_task_id = str(uuid.uuid4())
    fake_url = f"https://www.youtube.com/watch?v=test_{download_task_id}"

    # 任務 A: youtube_download
    db_client.add_task(
        task_id=download_task_id,
        payload=json.dumps({"url": fake_url, "video_title": "生命週期測試影片"}),
        task_type='youtube_download'
    )
    # 它的預設狀態是 'pending'，我們手動更新為 'processing' 來模擬它正在被執行的情況
    db_client.update_task_status(download_task_id, "processing")

    # 任務 B: gemini_process (依賴於 A)
    db_client.add_task(
        task_id=process_task_id,
        payload=json.dumps({"model": "gemini-pro"}),
        task_type='gemini_process',
        depends_on=download_task_id
    )
    # 任務 B 的初始狀態預設就是 'pending'，這正是我們想要的，所以不需更新。
    print(f"已建立任務鏈: {download_task_id} -> {process_task_id}")

    yield {
        "download_task_id": download_task_id,
        "process_task_id": process_task_id,
        "video_title": "生命週期測試影片",
        "fake_url": fake_url
    }

    # 2. Teardown: 測試結束後清理
    print(f"正在清理任務 {download_task_id} 和 {process_task_id}...")
    try:
        db_client.delete_task(task_id=download_task_id)
        db_client.delete_task(task_id=process_task_id)
        print("已從資料庫刪除任務鏈")
    except Exception as e:
        print(f"清理過程中發生錯誤: {e}")

def notify_frontend_of_update(api_url: str, task_id: str, status: str, result: dict):
    """
    一個輔助函式，用於呼叫後端內部 API 來觸發 WebSocket 廣播。
    """
    notification_url = f"{api_url}/api/internal/notify_task_update"
    try:
        response = requests.post(notification_url, json={
            "task_id": task_id,
            "status": status,
            "result": result
        })
        response.raise_for_status()
        print(f"已成功通知前端任務更新: {task_id} -> {status}")
    except requests.RequestException as e:
        print(f"警告：通知前端失敗: {e}")
        # 在 CI/CD 環境中，我們不希望因為這個通知失敗而中斷測試，
        # 因為我們的測試邏輯主要是依賴頁面重載來驗證最終狀態。
        pass


# --- Test Case ---
def test_multi_stage_task_lifecycle_ui_update(page: Page, live_server, db_client, multi_stage_task_chain):
    """
    驗證前端 UI 能否正確處理一個多階段任務的完整生命週期。
    此測試根據目前前端的實際行為進行調整：
    - 任務完成後會從「進行中」移至「已完成」。
    - 任務的顯示名稱始終是其 task_id。
    """
    page.on("console", lambda msg: print(f"BROWSER LOG: {msg}"))

    download_task_id = multi_stage_task_chain["download_task_id"]
    process_task_id = multi_stage_task_chain["process_task_id"]
    video_title = multi_stage_task_chain["video_title"]

    # --- Part 1: 驗證初始狀態 ---
    print("\n--- 階段 1: 驗證初始狀態 ---")
    page.goto(live_server)

    ongoing_tasks_list = page.locator("#ongoing-tasks")
    completed_tasks_list = page.locator("#completed-tasks")

    # 初始時，兩個任務都應該在「進行中」列表
    expect(ongoing_tasks_list.locator(".task-item", has_text=download_task_id)).to_be_visible(timeout=10000)
    expect(ongoing_tasks_list.locator(".task-item", has_text=process_task_id)).to_be_visible(timeout=10000)
    print("✅ 初始的下載和分析任務都成功顯示在「進行中」列表")

    # --- Part 2: 模擬第一階段 (下載) 完成 ---
    print("\n--- 階段 2: 模擬下載任務完成 ---")
    download_result = {"output_path": "/fake/path.mp3", "video_title": video_title}
    db_client.update_task_status(download_task_id, "completed", json.dumps(download_result))
    notify_frontend_of_update(live_server, download_task_id, "completed", download_result)
    page.wait_for_timeout(1000)

    # 驗證 UI 更新：下載任務應該移動到「已完成」列表，並顯示正確的標題
    expect(ongoing_tasks_list.locator(".task-item", has_text=download_task_id)).not_to_be_visible()
    # [JULES'S FIX 2025-08-17] Bug修復後，完成的任務應顯示其 video_title
    expect(completed_tasks_list.locator(".task-item", has_text=video_title)).to_be_visible()
    print("✅ 下載任務已成功從「進行中」移至「已完成」列表，並顯示正確標題")
    # 分析任務應該還在「進行中」，且因為還沒有 result，所以繼續顯示 task_id
    expect(ongoing_tasks_list.locator(".task-item", has_text=process_task_id)).to_be_visible()
    print("✅ 分析任務仍保留在「進行中」列表")


    # --- Part 3: 模擬第二階段 (分析) 完成 ---
    print("\n--- 階段 3: 模擬分析任務完成 ---")
    final_result = {"output_path": "/fake/report.html", "video_title": video_title}
    db_client.update_task_status(process_task_id, "completed", json.dumps(final_result))
    notify_frontend_of_update(live_server, process_task_id, "completed", final_result)
    page.wait_for_timeout(1000)

    # 驗證 UI 更新：分析任務也應該移動到「已完成」列表
    expect(ongoing_tasks_list.locator(".task-item", has_text=process_task_id)).not_to_be_visible()
    # [JULES'S FIX 2025-08-17] 現在兩個任務都完成了，它們都應該顯示 video_title
    final_task_items = completed_tasks_list.locator(".task-item", has_text=video_title)

    # [JULES'S FIX 2025-08-17] 驗證現在應該有兩個同名的已完成任務
    expect(final_task_items).to_have_count(2)
    print("✅ 「已完成」列表中成功顯示了兩個同名的任務項目")

    # 從多個項目中選取最後一個（即分析任務）來驗證按鈕
    final_task_item = final_task_items.last
    expect(final_task_item).to_be_visible()
    print("✅ 分析任務已成功從「進行中」移至「已完成」列表")

    # 驗證最終按鈕是否出現
    expect(final_task_item.locator("a.btn-preview")).to_be_visible()
    expect(final_task_item.locator("a.btn-download")).to_be_visible()
    print("✅ 最終的「預覽」和「下載」按鈕已顯示")

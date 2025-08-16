# 系統架構重構研究報告

**日期：** 2025年8月16日
**作者:** Jules (AI Software Engineer)
**狀態:** 提案

---

## 1. 摘要 (Executive Summary)

本報告旨在分析當前系統架構的核心問題，並為未來的發展提出一個更穩健、可擴展且易於維護的架構方案。

經過對程式碼的深入分析，我們發現當前的核心痛點在於**前後端職責劃分不清**：後端透過 WebSocket 傳送低階、細碎的狀態更新，迫使前端承擔了過於複雜的狀態管理和渲染邏輯，導致前端程式碼極度脆弱、難以除錯且不易擴展。

為了解決此問題，本報告強烈建議採用 **「前端的後端 (Backend for Frontend, BFF) + 伺服器驅動UI (Server-Driven UI, SDUI)」** 的現代化架構模式。這個方案的核心是將所有業務邏輯和狀態判斷收攏到後端 BFF，由 BFF 產生一份描述 UI 狀態的「藍圖 (JSON)」，前端則簡化為一個純粹的「渲染器」。這種模式將徹底解耦前後端，大幅提升系統的穩定性、可擴展性和可維護性。

## 2. 當前架構瓶頸分析

我們目前的架構主要存在以下兩個互相依賴的問題：

### 2.1. 過於「健談」且低階的後端 API

後端的 `api_server.py` 在處理長時間執行的任務（如 YouTube 影片處理）時，會透過 WebSocket 向前端廣播一系列**低階的狀態更新**。例如，一個任務鏈會觸發多個獨立的訊息：

*   `{"type": "YOUTUBE_STATUS", "payload": {"task_id": "abc", "status": "downloading"}}`
*   `{"type": "YOUTUBE_STATUS", "payload": {"task_id": "abc", "status": "completed"}}` (這僅代表下載完成)
*   `{"type": "YOUTUBE_STATUS", "payload": {"task_id": "def", "status": "processing"}}` (另一個任務 ID 開始處理)
*   `{"type": "YOUTUBE_STATUS", "payload": {"task_id": "def", "status": "completed"}}` (最終完成)

這種作法等同於將後端的**內部狀態機**直接暴露給了前端，是一種不良的設計。

### 2.2. 過於「聰明」且脆弱的前端

前端的 `mp3.html` 中包含了一個超過千行的巨型 JavaScript，它被迫成為一個「聰明」的客戶端，其主要職責包括：

*   **監聽並解釋低階訊息：** 前端需要理解 `downloading`、`processing` 等狀態的業務含義。
*   **管理複雜的任務鏈狀態：** 前端需要自己維護一個對應表，將任務 ID `abc` 和 `def` 關聯起來，才能正確地更新同一個 UI 項目。這正是「幽靈任務」等 Bug 的根源。
*   **手動操作 DOM：** 程式碼中充斥著 `getElementById` 和 `createElement`，根據複雜的 `if/else` 判斷來手動新增、移動和刪除 DOM 元素，這種作法極易出錯且難以維護。

總結來說，我們目前的架構將沉重的負擔壓在了最不應該承擔它的地方——前端。

## 3. 推薦架構方案：BFF + SDUI

為了從根本上解決問題，我們建議進行一次前瞻性的架構重構，其核心是結合 BFF 和 SDUI 兩種設計模式。

### 3.1. 核心理念

*   **後端成為「大腦」(BFF)：** 後端將包含所有業務邏輯。它負責決定「在什麼時候、應該顯示什麼內容」。
*   **前端成為「渲染器」：** 前端只負責「如何渲染」指定的內容，不再關心業務邏輯。

### 3.2. 運作流程

1.  **使用者操作：** 前端將使用者操作（例如，點擊按鈕）以簡單的事件形式發送給後端 BFF。
2.  **BFF 處理邏輯：** BFF 接收到事件後，執行所有相關的業務邏輯（例如，開始一個任務鏈、與資料庫互動、判斷任務鏈的整體狀態）。
3.  **BFF 產生 UI 藍圖：** 在業務邏輯執行完畢後，BFF 會產生一份描述**整個 UI 介面**的 JSON 藍圖。
4.  **BFF 推送藍圖：** BFF 透過 WebSocket 將這份完整的 JSON 藍圖推送給所有連接的前端。
5.  **前端渲染 UI：** 前端接收到 JSON 後，會清空現有的 UI，並根據這份新的藍圖，像搭積木一樣重新渲染整個介面。

### 3.3. API 契約範例 (SDUI JSON)

這將是我們新的 WebSocket 訊息格式。後端不再發送零散的狀態，而是直接發送一份完整的任務列表 UI 描述：

```json
{
  "type": "UPDATE_UI",
  "payload": {
    "screen_id": "task_dashboard",
    "ongoing_tasks": [
      {
        "component_type": "TaskItem",
        "props": {
          "id": "task_abc",
          "icon": "▶️",
          "title": "一個正在處理的 YouTube 影片",
          "status_text": "AI 分析中 (Gemini)...",
          "progress": 75
        }
      }
    ],
    "completed_tasks": [
      {
        "component_type": "TaskItem",
        "props": {
          "id": "task_xyz",
          "icon": "🎵",
          "title": "一個已完成的音訊檔",
          "status_text": "已完成",
          "actions": [
            {
              "component_type": "Button",
              "props": {
                "label": "預覽",
                "event": "PREVIEW_TASK",
                "payload": { "task_id": "task_xyz" }
              }
            },
            {
              "component_type": "Button",
              "props": {
                "label": "下載",
                "event": "DOWNLOAD_TASK",
                "payload": { "task_id": "task_xyz" }
              }
            }
          ]
        }
      }
    ]
  }
}
```

前端的邏輯將會極度簡化，大致如下：

```javascript
// 偽代碼
socket.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'UPDATE_UI') {
    renderScreen(data.payload);
  }
};

function renderScreen(payload) {
  const ongoingContainer = document.getElementById('ongoing-tasks');
  const completedContainer = document.getElementById('completed-tasks');

  ongoingContainer.innerHTML = '';
  completedContainer.innerHTML = '';

  payload.ongoing_tasks.forEach(component => {
    ongoingContainer.appendChild(renderComponent(component));
  });

  payload.completed_tasks.forEach(component => {
    completedContainer.appendChild(renderComponent(component));
  });
}

function renderComponent(component) {
  if (component.component_type === 'TaskItem') {
    return new TaskItem(component.props);
  }
  // ... 其他元件
}
```

## 4. 曾考慮的替代方案

我們曾考慮過一個較為簡單的方案：**透過 WebSocket 進行伺服器端渲染 (SSR)**。該方案讓後端直接渲染 HTML 片段並發送給前端進行替換。

我們最終**不推薦**此方案，主要原因如下：
*   **高度耦合：** 它將後端邏輯與前端的視覺呈現（HTML/CSS）緊密綁定，違反了關注點分離原則。
*   **擴展性差：** 如果未來要開發原生 App，此方案完全無法複用。
*   **頻寬效率低：** 傳輸 HTML 通常比傳輸優化的 JSON 效率更低。

## 5. 結論與後續步驟

採用 **BFF + SDUI** 架構是對我們系統的一次戰略性投資。它能從根本上解決當前架構的脆弱性，建立一個職責清晰、高度解耦、易於擴展和維護的系統。雖然初期需要投入時間來設計契約和重構，但這將為我們未來的快速迭代和長期穩定性奠定堅實的基礎。

**建議的後續步驟：**
1.  團隊審閱並批准此架構報告。
2.  規劃一個衝刺 (Sprint)，專門用於實施此架構重構，可分階段進行：
    *   **階段一：** 重構後端，使其能夠產生並透過新端點提供上述的 UI 藍圖 JSON。
    *   **階段二：** 重構前端，移除舊的邏輯，改為讀取 UI 藍圖 JSON 來進行渲染。
3.  在一個獨立的功能分支上進行開發，並確保有足夠的測試來驗證新架構的穩定性。

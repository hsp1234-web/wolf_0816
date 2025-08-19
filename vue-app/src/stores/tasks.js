import { defineStore } from 'pinia'
import axios from 'axios'

// 在 Vue App 中，API 的基本 URL 通常是相對路徑，指向同一個主機
const API_BASE_URL = '/api'

export const useTasksStore = defineStore('tasks', {
  state: () => ({
    // 進行中的任務列表
    pendingTasks: [],
    // 已完成的任務列表
    completedTasks: [],
    // WebSocket 實例
    socket: null,
    // WebSocket 連線狀態
    socketConnected: false,
    // 系統狀態
    systemStats: {},
    // 工作者狀態
    workerStatuses: {},
    // JULES'S FIX: 新增模型下載狀態
    modelDownloadStatus: {
      model: null,
      status: 'idle', // 'idle', 'starting', 'downloading', 'completed', 'failed'
      progress: 0,
      message: ''
    },
  }),
  actions: {
    /**
     * 從後端獲取所有任務的歷史紀錄，並根據狀態分類。
     */
    async fetchTasks() {
      try {
        const response = await axios.get(`${API_BASE_URL}/tasks`);
        const tasks = response.data;

        // 清空現有列表
        this.pendingTasks = [];
        this.completedTasks = [];

        // JULES'S FIX (2025-08-18): 增加一個防禦性檢查，確保 tasks 是一個陣列。
        if (Array.isArray(tasks)) {
          // 遍歷 API 回傳的任務
          tasks.forEach(task => {
            // [JULES'S FIX 2025-08-17] 將標題複製邏輯也應用於初始載入
            if (task.result) {
              const newTitle = task.result.video_title || task.result.original_filename;
              if (newTitle) {
                if (!task.payload) task.payload = {};
                task.payload.video_title = newTitle;
                task.payload.original_filename = newTitle;
              }
            }

            if (task.status === 'completed' || task.status === 'failed') {
              this.completedTasks.push(task);
            } else {
              this.pendingTasks.push(task);
            }
          });
        } else {
          console.warn('/api/tasks did not return an array, received:', tasks);
        }
        console.log('任務歷史紀錄已載入:', { pending: this.pendingTasks.length, completed: this.completedTasks.length });
      } catch (error) {
        console.error('獲取任務歷史紀錄時發生錯誤:', error);
      }
    },

    /**
     * 上傳檔案並建立一個或多個轉錄任務。
     * @param {FormData} formData - 包含檔案和轉錄選項的表單資料。
     */
    async startTranscription(formData) {
      try {
        const response = await axios.post(`${API_BASE_URL}/transcribe`, formData, {
          headers: {
            'Content-Type': 'multipart/form-data'
          }
        });

        const task = response.data; // 後端現在只會回傳單一任務

        // 根據後端回傳的任務類型，觸發對應的 WebSocket 事件
        if (task.type === 'transcribe') {
          // 如果模型已存在，直接開始轉錄
          this.sendSocketMessage({ type: 'START_TRANSCRIPTION', payload: { task_id: task.task_id } });
        } else if (task.type === 'download') {
          // 如果模型不存在，開始下載任務鏈
          this.sendSocketMessage({ type: 'START_DOWNLOAD', payload: { task_id: task.task_id } });
        }

        // JULES'S FIX (2025-08-18): 移除 fetchTasks() 呼叫以避免競爭條件。
        // 新建立的任務將由後續的 WebSocket 訊息處理，以確保狀態同步的唯一來源。

      } catch (error) {
        console.error('開始轉錄時發生錯誤:', error);
        // 可以拋出錯誤或設定錯誤狀態，讓 UI 元件知道
        throw error;
      }
    },

    /**
     * 初始化 WebSocket 連線。
     */
    connectWebSocket() {
      // 防止重複連線
      if (this.socket && this.socket.readyState === WebSocket.OPEN) {
        console.log('WebSocket 已連線，無需重複操作。');
        return;
      }

      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${wsProtocol}//${window.location.host}/api/ws`;

      this.socket = new WebSocket(wsUrl);

      this.socket.onopen = () => {
        console.log('WebSocket 連線成功。');
        this.socketConnected = true;
      };

      this.socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          this.handleSocketMessage(message);
        } catch (error) {
          console.error('處理 WebSocket 訊息時發生錯誤:', error);
        }
      };

      this.socket.onclose = () => {
        console.log('WebSocket 連線已關閉。');
        this.socket = null;
        this.socketConnected = false;
        // 可以加入自動重連的邏輯
      };

      this.socket.onerror = (error) => {
        console.error('WebSocket 發生錯誤:', error);
      };
    },

    /**
     * 處理從 WebSocket 收到的訊息。
     * @param {object} message - 已解析的 JSON 訊息。
     */
    handleSocketMessage(message) {
      console.log('收到 WebSocket 訊息:', message);
      const { type, payload } = message;

      if (type === 'ALL_WORKERS_STATUS_UPDATE') {
        // JULES'S FIX (2025-08-19): 處理來自後端的完整狀態更新。
        // 這會直接用後端傳來的完整物件替換掉前端的狀態，確保同步。
        this.workerStatuses = payload;
        console.log('已接收並初始化所有工作者的狀態:', this.workerStatuses);
        return; // 訊息已處理
      }

      if (type === 'WORKER_STATUS_UPDATE') {
        const { worker, status, last_error } = payload;
        if (this.workerStatuses[worker]) {
          this.workerStatuses[worker].status = status;
          this.workerStatuses[worker].last_error = last_error;
        } else {
          // 如果物件不存在，則建立它
          this.workerStatuses[worker] = { status, last_error };
        }
        console.log(`工作者狀態更新: ${worker} -> ${status}`);
        return; // 訊息已處理
      }

      // JULES'S FIX: 處理模型下載狀態更新
      if (type === 'DOWNLOAD_STATUS') {
        this.modelDownloadStatus.model = payload.model;
        this.modelDownloadStatus.status = payload.status;
        // JULES'S FIX: 從多個可能的鍵名中安全地獲取進度值
        this.modelDownloadStatus.progress = payload.percent || payload.progress || 0;
        this.modelDownloadStatus.message = payload.description || payload.error || payload.status;
        // 如果下載完成或失敗，設定一個計時器來重置狀態，以便下次下載
        if (payload.status === 'completed' || payload.status === 'failed') {
          setTimeout(() => {
            this.modelDownloadStatus.status = 'idle';
            this.modelDownloadStatus.message = '';
          }, 5000);
        }
        return; // 訊息已處理
      }


      if (!payload || !payload.task_id) {
        // 處理沒有 task_id 的訊息，例如模型下載進度
        // 已由上面的 DOWNLOAD_STATUS 處理，這裡可以保持原樣或移除 TODO
        return;
      }

      // 尋找任務在 pendingTasks 列表中的索引
      const taskIndex = this.pendingTasks.findIndex(t => t.task_id === payload.task_id);

      if (taskIndex !== -1) {
        // 如果找到任務
        const task = this.pendingTasks[taskIndex];

        // 將 payload 的內容更新到任務物件上
        // 這樣可以更新 status, progress, message, result 等等
        Object.assign(task, payload);
        // 確保 payload 中的 status 會覆蓋舊的 status
        if (payload.status) {
            task.status = payload.status;
        }

        // [JULES'S FIX] 根據 `DOC/bug.md` 的分析，修復任務標題顯示問題。
        // 當後端傳來任務更新時，`video_title` 或 `original_filename` 位於 `payload.result` 中。
        // 前端 UI 元件預期從 `task.payload` 中讀取這些值。
        // 因此，我們需要將這些值從 `result` 複製到 `payload`。
        if (payload.result) {
          const newTitle = payload.result.video_title || payload.result.original_filename;
          if (newTitle) {
            // 確保 task.payload 物件存在
            if (!task.payload) {
              task.payload = {};
            }
            // 將新標題同時更新到兩個欄位，以確保 UI 的一致性
            task.payload.video_title = newTitle;
            task.payload.original_filename = newTitle;
          }
        }

        // 檢查任務是否完成或失敗
        if (task.status === 'completed' || task.status === 'failed') {
          // 從 pendingTasks 列表中移除
          const [completedTask] = this.pendingTasks.splice(taskIndex, 1);
          // 加入到 completedTasks 列表
          this.completedTasks.push(completedTask);
        } else {
          // 如果任務仍在進行中，則直接更新
          // Pinia 的響應式系統會自動偵測到陣列中物件的屬性變更
           this.pendingTasks[taskIndex] = { ...task };
        }
      } else {
        // 如果在 pendingTasks 中找不到，可能它是一個全新的任務，或者是一個已經完成的任務的更新
        // 為避免重複，我們在這裡先不做任何事，依賴 fetchTasks 來獲取最新列表
        console.warn(`在 pendingTasks 中找不到任務 ID: ${payload.task_id}，可能任務已完成或尚未同步。`);
      }
    },

    /**
     * 透過 WebSocket 發送訊息。
     * @param {object} message - 要發送的訊息物件。
     */
    sendSocketMessage(message) {
      if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
        console.error('WebSocket 未連線，無法發送訊息。');
        return;
      }
      this.socket.send(JSON.stringify(message));
    },

    /**
     * 發送請求以下載指定的 Whisper 模型。(此功能已棄用)
     * @param {string} modelName - 要下載的模型名稱 (例如 'medium')。
     */
    downloadModel(modelName) {
      // 這個流程已被新的自動化依賴管理取代。
      // 當使用者試圖轉錄一個不存在的模型時，下載會自動開始。
      // 保留此函式以避免 UI 元件出錯，但給予警告。
      console.warn(`[已棄用] downloadModel('${modelName}') 被呼叫，但此流程已被自動化。`);
    },

    /**
     * 重新命名一個已完成的任務。
     * @param {string} taskId - 要重新命名的任務 ID。
     * @param {string} newFilename - 新的檔案名稱 (不含副檔名)。
     */
    async renameTask(taskId, newFilename) {
      try {
        const response = await axios.post(`${API_BASE_URL}/rename/${taskId}`, { new_filename: newFilename });
        const result = response.data;

        // 在 completedTasks 列表中尋找並更新任務
        const taskIndex = this.completedTasks.findIndex(t => t.task_id === taskId);
        if (taskIndex !== -1) {
          // 更新檔案名稱
          // 注意：後端回傳的 new_filename 可能不包含副檔名，我們需要從原始檔名中保留副檔名
          const oldFilename = this.completedTasks[taskIndex].payload.original_filename || '';
          const extension = oldFilename.slice(oldFilename.lastIndexOf('.'));
          this.completedTasks[taskIndex].payload.original_filename = result.new_filename + extension;
        }
      } catch (error) {
        console.error('重新命名任務時發生錯誤:', error);
        throw new Error(error.response?.data?.detail || '重新命名失敗');
      }
    },

    /**
     * 獲取後端系統狀態。
     */
    async fetchSystemStats() {
      try {
        const response = await axios.get(`${API_BASE_URL}/system_stats`);
        this.systemStats = response.data;
      } catch (error) {
        // 不在控制台顯示錯誤，因為這會頻繁發生在開發伺服器重啟時
        // console.error('獲取系統狀態時發生錯誤:', error);
      }
    },

    /**
     * 開始一個或多個媒體下載任務。
     * @param {object} options - 包含下載所需資訊的物件。
     * @param {string[]} options.urls - 要下載的 URL 列表。
     * @param {string} options.downloadType - 'audio' 或 'video'。
     */
    async startDownload(options) {
      const { urls, downloadType } = options;
      const requests = urls.map(url => ({ url: url, filename: '' }));
      const payload = {
          requests: requests,
          download_only: true,
          model: null,
          download_type: downloadType
      };

      try {
        const response = await axios.post(`${API_BASE_URL}/youtube/process`, payload);
        const result = response.data;

        // 觸發 WebSocket 開始監控
        result.tasks.forEach(task => {
            this.sendSocketMessage({ type: 'START_YOUTUBE_PROCESSING', payload: { task_id: task.task_id }});
        });
        // JULES'S FIX (2025-08-18): 移除 fetchTasks() 呼叫以避免競爭條件。
        // 新任務的狀態將透過 WebSocket 更新。

      } catch (error) {
        console.error('建立下載任務時發生錯誤:', error);
        throw new Error(error.response?.data?.detail || '建立下載任務失敗');
      }
    },

    /**
     * 驗證 Google API 金鑰。
     * @param {string} apiKey - 要驗證的金鑰。
     * @returns {Promise<object>} - 回傳包含 { valid: boolean, detail: string } 的物件。
     */
    async validateApiKey(apiKey) {
      try {
        const response = await axios.post(`${API_BASE_URL}/youtube/validate_api_key`, { api_key: apiKey });
        return response.data;
      } catch (error) {
        return {
          valid: false,
          detail: error.response?.data?.detail || '無法連線至後端進行驗證'
        };
      }
    },

    /**
     * 獲取可用的 Gemini 模型列表。
     * @param {string} apiKey - 用於驗證的 Google API 金鑰。
     * @returns {Promise<Array>} - 回傳模型列表。
     */
    async fetchGeminiModels(apiKey) {
      try {
        const response = await axios.post(`${API_BASE_URL}/youtube/models`, { api_key: apiKey });
        return response.data.models || [];
      } catch (error) {
        console.error('獲取 Gemini 模型列表時發生錯誤:', error);
        throw new Error(error.response?.data?.detail || '無法載入模型列表');
      }
    },

    /**
     * 處理 YouTube 報告生成請求。
     * @param {object} options - 包含請求所需資訊的物件。
     */
    async processYoutubeRequest(options) {
        try {
            const response = await axios.post(`${API_BASE_URL}/youtube/process`, options);
            const result = response.data;

            result.tasks.forEach(task => {
                this.sendSocketMessage({ type: 'START_YOUTUBE_PROCESSING', payload: { task_id: task.task_id }});
            });
            // JULES'S FIX (2025-08-18): 移除 fetchTasks() 呼叫以避免競爭條件。
        } catch (error) {
            console.error('處理 YouTube 請求時發生錯誤:', error);
            throw new Error(error.response?.data?.detail || '建立 YouTube 分析任務失敗');
        }
    },

    async fetchWorkerStatuses() {
      try {
        const response = await axios.get(`${API_BASE_URL}/workers/status`);
        this.workerStatuses = response.data;
        console.log('工作者狀態已更新:', this.workerStatuses);
      } catch (error) {
        console.error('獲取工作者狀態時發生錯誤:', error);
      }
    },

    async launchWorker(workerName) {
      try {
        console.log(`正在請求啟動工作者: ${workerName}`);
        await axios.post(`${API_BASE_URL}/workers/launch/${workerName}`);
        // 狀態更新將透過 WebSocket 推播，此處無需做任何事
      } catch (error) {
        console.error(`啟動工作者 ${workerName} 時發生錯誤:`, error);
        // 可以選擇性地在這裡更新狀態為 FAILED
        if (this.workerStatuses[workerName]) {
          this.workerStatuses[workerName].status = 'FAILED';
          this.workerStatuses[workerName].last_error = '啟動請求失敗';
        }
      }
    },
  }
})

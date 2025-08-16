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
  }),
  actions: {
    /**
     * 從後端獲取所有任務的歷史紀錄，並根據狀態分類。
     */
    async fetchTasks() {
      try {
        const response = await axios.get(`${API_BASE_URL}/tasks`)
        const tasks = response.data

        // 清空現有列表
        this.pendingTasks = []
        this.completedTasks = []

        // 遍歷 API 回傳的任務
        tasks.forEach(task => {
          if (task.status === 'completed' || task.status === 'failed') {
            this.completedTasks.push(task)
          } else {
            this.pendingTasks.push(task)
          }
        })
        console.log('任務歷史紀錄已載入:', { pending: this.pendingTasks.length, completed: this.completedTasks.length });
      } catch (error) {
        console.error('獲取任務歷史紀錄時發生錯誤:', error)
        // 在真實應用中，你可能會想在這裡設定一個錯誤狀態
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

        const result = response.data;
        // API 可能回傳單一任務或一個任務陣列
        const tasks = Array.isArray(result.tasks) ? result.tasks : [result];

        tasks.forEach(task => {
          // 只有轉錄任務需要透過 WebSocket 觸發
          if (task.type === 'transcribe') {
            this.sendSocketMessage({ type: 'START_TRANSCRIPTION', payload: { task_id: task.task_id } });
          }
          // 下載任務由 worker 自動處理，前端只需等待狀態更新
        });

        // 刷新任務列表以顯示新建立的任務
        await this.fetchTasks();

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

      // TODO: 在這裡根據訊息類型 (type) 更新 state
      // 例如：找到對應的 task，更新其狀態或進度
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
     * 發送請求以下載指定的 Whisper 模型。
     * @param {string} modelName - 要下載的模型名稱 (例如 'medium')。
     */
    downloadModel(modelName) {
      this.sendSocketMessage({
        type: 'DOWNLOAD_MODEL',
        payload: { model: modelName }
      });
    }
  }
})

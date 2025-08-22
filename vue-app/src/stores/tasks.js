import { defineStore } from 'pinia'
import axios from 'axios'
import { applyPatch } from 'fast-json-patch'

const API_BASE_URL = '/api'

// 輔助函式：提供一個結構完整的、乾淨的初始狀態物件。
// 這能確保元件在第一次渲染時就有一個可預測的狀態結構。
const getInitialState = () => ({
  appState: {
    pending_tasks: [],
    completed_tasks: [],
    worker_statuses: {},
    operation_status: { in_progress: false, message: '', progress: 0 },
    local_models: { available: [], checking: true },
  },
  socket: null,
  socketConnected: false,
});

export const useTasksStore = defineStore('tasks', {
  state: () => getInitialState(),

  // Getters to provide convenient access to the nested appState
  getters: {
    // 由於 state 現在結構完整，我們不再需要 || [] 作為後備
    pendingTasks: (state) => state.appState.pending_tasks,
    completedTasks: (state) => state.appState.completed_tasks,
    workerStatuses: (state) => state.appState.worker_statuses,
    operationStatus: (state) => state.appState.operation_status,
    localModels: (state) => state.appState.local_models,
  },

  actions: {
    initializeSystem() {
      if (!this.socket || this.socket.readyState === WebSocket.CLOSED) {
        this.connectToWebSocket('/ws'); // API Gateway 的 WebSocket 代理
      }
    },

    connectToWebSocket(endpoint) {
      if (this.socket && this.socket.readyState === WebSocket.OPEN) {
        console.log('WebSocket 已連線，無需重複操作。');
        return;
      }

      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${wsProtocol}//${window.location.host}${endpoint}`;
      console.log(`正在嘗試連接至: ${wsUrl}`);

      this.socket = new WebSocket(wsUrl);

      this.socket.onopen = () => {
        console.log(`WebSocket 連線成功: ${endpoint}`);
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
        console.log(`WebSocket 連線已關閉: ${endpoint}`);
        // 使用 this.$reset() 來恢復到 getInitialState() 定義的初始狀態
        this.$reset();
        setTimeout(() => {
          console.log("正在嘗試重新連線...");
          this.initializeSystem();
        }, 5000);
      };

      this.socket.onerror = (error) => {
        console.error(`WebSocket 發生錯誤: ${endpoint}`, error);
      };
    },

    handleSocketMessage(message) {
      const { type, payload } = message;

      if (type === 'full_state') {
        console.log("接收到完整狀態，正在更新...");
        // 使用 $patch 來確保響應性
        this.$patch({ appState: payload });
      } else if (type === 'patch') {
        try {
          // 直接在 document 上操作，因為 this.appState 是一個 proxy
          const newDoc = applyPatch(this.appState, payload, true).newDocument;
          this.$patch({ appState: newDoc });
        } catch (e) {
          console.error("應用補丁失敗:", e);
        }
      } else {
        console.warn(`收到未知的訊息類型: ${type}`);
      }
    },

    // --- 保留觸發後端操作的 Actions ---
    async uploadForTranscription(formData) {
      try {
        await axios.post(`/upload_for_transcription`, formData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        });
      } catch (error) {
        console.error('上傳檔案以進行轉錄時發生錯誤:', error);
        throw error;
      }
    },

    async processYoutubeRequest(youtubeUrl) {
        try {
            await axios.post(`/transcribe_youtube`, { youtube_url: youtubeUrl });
        } catch (error) {
            console.error('處理 YouTube 請求時發生錯誤:', error);
            throw error;
        }
    },
  }
})

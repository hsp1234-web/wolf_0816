import { defineStore } from 'pinia'
import axios from 'axios'
import { applyPatch } from 'fast-json-patch'
import { useNotificationStore } from './notifications'
import { logAction } from '@/utils/logging'

// 輔助函式：提供一個結構完整的、乾淨的初始狀態物件。
const getInitialState = () => ({
  taskPool: [], // 用於存放待處理任務的佇列
  appState: {
    pending_tasks: [],
    completed_tasks: [],
    worker_statuses: {},
    // JULES'S FIX: 為系統狀態提供一個初始的、結構完整的物件，以防止前端渲染錯誤
    system_stats: {
      cpu_usage: null,
      ram_usage: null,
      gpu_name: null,
      gpu_usage: null,
      active_model: null
    },
    operation_status: { in_progress: false, message: '', progress: 0 },
    local_models: { available: [], checking: true },
  },
  socket: null,
  socketConnected: false,
  // JULES'S FIX: 用於追蹤透過 WebSocket 發送的請求
  pendingRequests: new Map(),
});

export const useTasksStore = defineStore('tasks', {
  state: () => getInitialState(),

  getters: {
    pendingTasks: (state) => state.appState.pending_tasks,
    completedTasks: (state) => state.appState.completed_tasks,
    workerStatuses: (state) => state.appState.worker_statuses,
    // JULES'S FIX: 新增 systemStats getter 以修復儀表板的錯誤
    systemStats: (state) => state.appState.system_stats,
    operationStatus: (state) => state.appState.operation_status,
    localModels: (state) => state.appState.local_models,
  },

  actions: {
    // --- 任務池管理 Actions ---
    addTaskToPool(task) {
      const taskWithId = { ...task, poolId: Date.now() + Math.random() };
      this.taskPool.push(taskWithId);
    },
    removeTaskFromPool(poolId) {
      this.taskPool = this.taskPool.filter(task => task.poolId !== poolId);
    },
    clearTaskPool() {
      this.taskPool = [];
    },

    // --- WebSocket Actions ---
    initializeSystem() {
      if (!this.socket || this.socket.readyState === WebSocket.CLOSED) {
        this.connectToWebSocket('/ws/status');
      }
    },
    sendMessage(type, payload = {}) {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify({ type, payload }));
        } else {
            console.error('WebSocket is not connected.');
        }
    },
    // JULES'S NEW FEATURE: 一個更穩健的、基於 Promise 的 WebSocket 請求/回應模式
    sendRequest(type, payload = {}, timeout = 10000) {
        return new Promise((resolve, reject) => {
            if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
                return reject(new Error('WebSocket is not connected.'));
            }
            const request_id = `req_${Date.now()}_${Math.random()}`;
            this.pendingRequests.set(request_id, { resolve, reject });

            // 設定超時
            setTimeout(() => {
                if (this.pendingRequests.has(request_id)) {
                    this.pendingRequests.delete(request_id);
                    reject(new Error(`Request timed out after ${timeout / 1000}s`));
                }
            }, timeout);

            this.socket.send(JSON.stringify({ type, payload: { ...payload, request_id } }));
        });
    },
    connectToWebSocket(endpoint) {
      if (this.socket && this.socket.readyState === WebSocket.OPEN) return;
      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${wsProtocol}//${window.location.host}${endpoint}`;
      this.socket = new WebSocket(wsUrl);
      this.socket.onopen = () => {
        this.socketConnected = true;
        // The checkLocalModels call is now handled by a watcher in App.vue
        // to ensure a proper sequence of initialization.
      };
      this.socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          this.handleSocketMessage(message);
        } catch (error) { console.error('處理 WebSocket 訊息時發生錯誤:', error); }
      };
      this.socket.onclose = () => {
        this.socketConnected = false;
        this.$reset();
        setTimeout(() => { this.initializeSystem(); }, 5000);
      };
      this.socket.onerror = (error) => { console.error(`WebSocket 發生錯誤: ${endpoint}`, error); };
    },
    handleSocketMessage(message) {
      const { type, payload, request_id } = message;

      // 新增日誌：記錄所有收到的 WebSocket 訊息
      console.log('[WebSocket Recv]', {
        type: type,
        has_payload: !!payload,
        payload_keys: payload ? Object.keys(payload) : [],
        has_request_id: !!request_id,
        timestamp: new Date().toISOString()
      });


      // JULES'S FIX: 優先處理帶有 request_id 的、點對點的回應
      if (request_id && this.pendingRequests.has(request_id)) {
          console.log(`[WebSocket] 正在處理 request_id: ${request_id}`);
          const { resolve, reject } = this.pendingRequests.get(request_id);
          if (payload && (payload.success === false || payload.valid === false)) {
              reject(payload);
          } else {
              resolve(payload);
          }
          this.pendingRequests.delete(request_id);
          return; // 處理完畢，直接返回
      }

      // 處理廣播或無特定目標的訊息
      switch (type) {
        case 'full_state':
          console.log('[WebSocket] 正在處理 full_state...');
          // 新增日誌：將收到的完整狀態物件轉為字串印出，以便在 E2E 測試中驗證
          console.log('收到的 full_state payload:', JSON.stringify(payload, null, 2));
          this.$patch({ appState: payload });
          console.log('[WebSocket] full_state 已應用。');
          break;
        case 'patch':
          console.log('[WebSocket] 正在處理 patch...');
          try {
            const newDoc = applyPatch(this.appState, payload, true).newDocument;
            this.$patch({ appState: newDoc });
            console.log('[WebSocket] patch 已應用。');
          } catch (e) { console.error("應用補丁失敗:", e); }
          break;
        case 'LOCAL_MODELS_STATUS':
           console.log('[WebSocket] 正在處理 LOCAL_MODELS_STATUS...');
          this.$patch(state => {
            state.appState.local_models.available = payload.models || [];
            state.appState.local_models.checking = false;
          });
          break;
        // JULES'S FIX: 新增一個 case 來處理來自後端的系統狀態更新
        case 'SYSTEM_STATS':
           console.log('[WebSocket] 正在處理 SYSTEM_STATS...');
          this.appState.system_stats.cpu_usage = payload.cpu_usage;
          this.appState.system_stats.ram_usage = payload.ram_usage;
          break;
        default:
          console.warn(`[WebSocket] 未知的訊息類型: ${type}`);
          break;
      }
    },

    // --- 後端 API Actions ---
    async checkLocalModels() {
      const notificationStore = useNotificationStore();
      this.$patch(state => {
        state.appState.local_models.checking = true;
      });
      logAction('check-local-models-start');

      try {
        const response = await this.sendRequest('CHECK_LOCAL_MODELS', {}, 15000);
        this.$patch(state => {
          state.appState.local_models.available = response.models || [];
          state.appState.local_models.checking = false;
        });
        logAction('check-local-models-success', `found: ${(response.models || []).length}`);
      } catch (error) {
        console.error('檢查本地模型時發生錯誤:', error);
        notificationStore.addNotification('無法檢查本地模型狀態', 'error');
        this.$patch(state => {
          state.appState.local_models.checking = false;
        });
        logAction('check-local-models-failed', error.message || 'unknown error');
      }
    },
    downloadModel(model) {
      console.log(`正在透過 WebSocket 請求下載模型: ${model}`);
      this.sendMessage('DOWNLOAD_MODEL', { model });
    },
    fetchLogs() {
      console.log("正在執行模擬的 fetchLogs...");
      return [];
    },
    async stageFile(file) {
      const formData = new FormData();
      formData.append('file', file);
      try {
        const response = await axios.post('/api/stage-file', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
        return response.data;
      } catch (error) {
        console.error('暫存檔案時發生錯誤:', error);
        throw error;
      }
    },
    async submitTaskPool(tasks) {
      if (!tasks || tasks.length === 0) return;
      try {
        const tasksToSubmit = tasks.map(({ poolId, ...rest }) => rest);
        const response = await axios.post('/api/batch-tasks', {
          tasks: tasksToSubmit,
        });
        this.clearTaskPool();
        return response.data;
      } catch (error) {
        console.error('提交任務池時發生錯誤:', error);
        throw error;
      }
    },

    // --- (舊的，可能已棄用) ---
    async uploadForTranscription(formData) {
      try {
        await axios.post(`/upload_for_transcription`, formData, { headers: { 'Content-Type': 'multipart/form-data' } });
      } catch (error) { console.error('上傳檔案以進行轉錄時發生錯誤:', error); throw error; }
    },
    async processYoutubeRequest(youtubeUrl) {
        try {
            await axios.post(`/transcribe_youtube`, { youtube_url: youtubeUrl });
        } catch (error) { console.error('處理 YouTube 請求時發生錯誤:', error); throw error; }
    },

    // --- 新增的下載 Action ---
    async startDownload(payload) {
      const { urls, downloadType } = payload;
      const requests = urls.map(url => ({ url, filename: null }));
      try {
        const response = await axios.post('/api/youtube/process', {
          requests,
          download_only: true,
          download_type: downloadType,
        });
        return response.data;
      } catch (error) {
        console.error('啟動下載任務時發生錯誤:', error);
        if (error.response && error.response.data && error.response.data.detail) {
          throw new Error(error.response.data.detail);
        }
        throw error;
      }
    },

    // --- YouTube Reporter Actions (WebSocket Refactor) ---
    async validateApiKey(apiKey) {
      try {
        // 使用新的 WebSocket 請求/回應模式
        const response = await this.sendRequest('VALIDATE_API_KEY', { api_key: apiKey });
        return response; // 後端直接回傳 { valid: true/false, detail: '...' }
      } catch (error) {
        return { valid: false, detail: error.detail || error.message || '驗證時發生未知錯誤' };
      }
    },

    async fetchGeminiModels(apiKey) {
      try {
        // 使用新的 WebSocket 請求/回應模式
        const response = await this.sendRequest('FETCH_GEMINI_MODELS', { api_key: apiKey });
        // 後端成功時回傳 { success: true, models: [...] }
        return response.models || [];
      } catch (error) {
        console.error('獲取 Gemini 模型時發生錯誤:', error.detail || error.message);
        throw new Error(error.detail || '無法獲取 Gemini 模型列表');
      }
    },

    async runHealthCheck() {
      try {
        console.log('[Health Check] Sending HEALTH_CHECK_REQUEST...');
        const response = await this.sendRequest('HEALTH_CHECK_REQUEST', {}, 5000); // 5-second timeout
        console.log('[Health Check] Received response:', response);
        return { success: true, response };
      } catch (error) {
        console.error('[Health Check] Health check failed:', error);
        return { success: false, error };
      }
    },
  }
})

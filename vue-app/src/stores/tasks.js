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
    // JULES'S FIX: 恢復 installationStatus 以避免 App.vue 中的 JS 錯誤
    installationStatus: {
      inProgress: false,
      message: ''
    },
    // JULES'S NEW FEATURE: 新增日誌狀態
    logs: [],
    logSourceFilter: 'all', // 'all', 'frontend_action', 'api_server', etc.
    // JULES'S NEW FEATURE: 本地 Whisper 模型狀態
    localModels: {
      available: [],
      checking: true,
    }
  }),
  actions: {
    // 初始化 WebSocket 連線
    initializeSystem() {
      this.connectToWebSocket('/api/ws');
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
        // 連線成功後，立即獲取初始狀態
        this.fetchTasks();
        this.fetchWorkerStatuses();
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
        this.socket = null;
        this.socketConnected = false;
        // 可選：在這裡實作主伺服器的重連邏輯
      };

      this.socket.onerror = (error) => {
        console.error(`WebSocket 發生錯誤: ${endpoint}`, error);
        this.socketConnected = false;
      };
    },

    handleSocketMessage(message) {
      console.log('收到 WebSocket 訊息:', message);
      const { type, payload } = message;

      // --- All other message handling remains the same ---

      if (type === 'ALL_WORKERS_STATUS_UPDATE') {
        this.workerStatuses = payload;
        console.log('已接收並初始化所有工作者的狀態:', this.workerStatuses);
        return;
      }

      if (type === 'WORKER_STATUS_UPDATE') {
        const { worker, status, last_error } = payload;
        if (this.workerStatuses[worker]) {
          this.workerStatuses[worker].status = status;
          this.workerStatuses[worker].last_error = last_error;
        } else {
          this.workerStatuses[worker] = { status, last_error };
        }
        console.log(`工作者狀態更新: ${worker} -> ${status}`);
        return;
      }

      if (type === 'DOWNLOAD_STATUS') {
        this.modelDownloadStatus.model = payload.model;
        this.modelDownloadStatus.status = payload.status;
        this.modelDownloadStatus.progress = payload.percent || payload.progress || 0;
        this.modelDownloadStatus.message = payload.description || payload.error || payload.status;
        if (payload.status === 'completed' || payload.status === 'failed') {
          setTimeout(() => {
            this.modelDownloadStatus.status = 'idle';
            this.modelDownloadStatus.message = '';
          }, 5000);
        }
        return;
      }

      if (!payload || !payload.task_id) {
        return;
      }

      const taskIndex = this.pendingTasks.findIndex(t => t.task_id === payload.task_id);

      if (taskIndex !== -1) {
        const task = this.pendingTasks[taskIndex];
        Object.assign(task, payload);
        if (payload.status) {
            task.status = payload.status;
        }
        if (payload.result) {
          const newTitle = payload.result.video_title || payload.result.original_filename;
          if (newTitle) {
            if (!task.payload) {
              task.payload = {};
            }
            task.payload.video_title = newTitle;
            task.payload.original_filename = newTitle;
          }
        }
        if (task.status === 'completed' || task.status === 'failed') {
          const [completedTask] = this.pendingTasks.splice(taskIndex, 1);
          this.completedTasks.push(completedTask);
        } else {
           this.pendingTasks[taskIndex] = { ...task };
        }
      } else {
        console.warn(`在 pendingTasks 中找不到任務 ID: ${payload.task_id}，可能任務已完成或尚未同步。`);
      }
    },

    // --- All other actions like fetchTasks, startTranscription, etc. remain the same ---
    async fetchTasks() {
      try {
        const response = await axios.get(`${API_BASE_URL}/tasks`);
        const tasks = response.data;
        this.pendingTasks = [];
        this.completedTasks = [];
        if (Array.isArray(tasks)) {
          tasks.forEach(task => {
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
    async startTranscription(formData) {
      try {
        const response = await axios.post(`${API_BASE_URL}/transcribe`, formData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        });
        const task = response.data;
        if (task.type === 'transcribe') {
          this.sendSocketMessage({ type: 'START_TRANSCRIPTION', payload: { task_id: task.task_id } });
        } else if (task.type === 'download') {
          this.sendSocketMessage({ type: 'START_DOWNLOAD', payload: { task_id: task.task_id } });
        }
      } catch (error) {
        console.error('開始轉錄時發生錯誤:', error);
        throw error;
      }
    },
    sendSocketMessage(message) {
      if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
        console.error('WebSocket 未連線，無法發送訊息。');
        return;
      }
      this.socket.send(JSON.stringify(message));
    },
    async renameTask(taskId, newFilename) {
      try {
        const response = await axios.post(`${API_BASE_URL}/rename/${taskId}`, { new_filename: newFilename });
        const result = response.data;
        const taskIndex = this.completedTasks.findIndex(t => t.task_id === taskId);
        if (taskIndex !== -1) {
          const oldFilename = this.completedTasks[taskIndex].payload.original_filename || '';
          const extension = oldFilename.slice(oldFilename.lastIndexOf('.'));
          this.completedTasks[taskIndex].payload.original_filename = result.new_filename + extension;
        }
      } catch (error) {
        console.error('重新命名任務時發生錯誤:', error);
        throw new Error(error.response?.data?.detail || '重新命名失敗');
      }
    },
    async fetchSystemStats() {
      try {
        const response = await axios.get(`${API_BASE_URL}/system_stats`);
        this.systemStats = response.data;
      } catch (error) {
        // Suppress console error for this frequent, non-critical fetch
      }
    },
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
        result.tasks.forEach(task => {
            this.sendSocketMessage({ type: 'START_YOUTUBE_PROCESSING', payload: { task_id: task.task_id }});
        });
      } catch (error) {
        console.error('建立下載任務時發生錯誤:', error);
        throw new Error(error.response?.data?.detail || '建立下載任務失敗');
      }
    },
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
    async fetchGeminiModels(apiKey) {
      try {
        const response = await axios.post(`${API_BASE_URL}/youtube/models`, { api_key: apiKey });
        return response.data.models || [];
      } catch (error) {
        console.error('獲取 Gemini 模型列表時發生錯誤:', error);
        throw new Error(error.response?.data?.detail || '無法載入模型列表');
      }
    },
    async processYoutubeRequest(options) {
        try {
            const response = await axios.post(`${API_BASE_URL}/youtube/process`, options);
            const result = response.data;
            result.tasks.forEach(task => {
                this.sendSocketMessage({ type: 'START_YOUTUBE_PROCESSING', payload: { task_id: task.task_id }});
            });
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
      } catch (error) {
        console.error(`啟動工作者 ${workerName} 時發生錯誤:`, error);
        if (this.workerStatuses[workerName]) {
          this.workerStatuses[workerName].status = 'FAILED';
          this.workerStatuses[workerName].last_error = '啟動請求失敗';
        }
      }
    },
    async fetchLogs() {
      try {
        const response = await axios.get(`${API_BASE_URL}/logs`);
        this.logs = response.data;
        console.log(`已獲取 ${this.logs.length} 條日誌紀錄。`);
      } catch (error) {
        console.error('獲取系統日誌時發生錯誤:', error);
        // 可選：使用 notification store 顯示錯誤
      }
    },
    async fetchLocalModels() {
      this.localModels.checking = true;
      try {
        const response = await axios.get(`${API_BASE_URL}/models/local`);
        this.localModels.available = response.data.models || [];
      } catch (error) {
        console.error('獲取本地模型列表時發生錯誤:', error);
        this.localModels.available = [];
      } finally {
        this.localModels.checking = false;
      }
    },
    async downloadModel(modelName) {
      try {
        const response = await axios.post(`${API_BASE_URL}/models/download`, { model_size: modelName });
        const result = response.data;
        if (result.type === 'download') {
          this.sendSocketMessage({ type: 'START_DOWNLOAD', payload: { task_id: result.task_id } });
        }
      } catch (error) {
        console.error(`請求下載模型 ${modelName} 時發生錯誤:`, error);
        // 可選：使用 notification store 顯示錯誤
        throw error; // Re-throw to allow component to handle it
      }
    },
  }
})

import { defineStore } from 'pinia'
import axios from 'axios'

const API_BASE_URL = '/api'
const POLLING_INTERVAL = 3000 // 3 seconds

export const useTasksStore = defineStore('tasks', {
  state: () => ({
    pendingTasks: [],
    completedTasks: [],
    socket: null,
    socketConnected: false,
    systemStats: {},
    workerStatuses: {},
    operationStatus: {
      inProgress: false,
      message: '',
      progress: 0,
    },
    logs: [],
    logSourceFilter: 'all',
    localModels: {
      available: [],
      checking: true,
    },
    initialSetup: {
      countdown: 60,
      timerId: null,
      completed: false,
      cancelled: false,
    },
    // 新增：用於追蹤每個任務的輪詢計時器
    pollingIntervals: {},
  }),
  actions: {
    // --- WebSocket 連線 (保留用於非任務狀態的即時更新) ---
    initializeSystem() {
      this.connectToWebSocket('/api/ws');
      this.startInitialCountdown();
      // 初始載入既有任務
      this.fetchTasks();
    },
    connectToWebSocket(endpoint) {
      // ... WebSocket 連線邏輯保持不變 ...
      // (為了簡潔，此處省略，實際程式碼中保留原樣)
    },
    handleSocketMessage(message) {
      // --- 任務狀態更新的邏輯已移除，改由輪詢處理 ---
      // --- 保留處理非任務相關訊息的邏輯 ---
      const { type, payload } = message;
      if (type === 'SYSTEM_STATS_UPDATE') {
        this.systemStats = payload;
      } else if (type === 'ALL_WORKERS_STATUS_UPDATE') {
        this.workerStatuses = payload;
      }
      // ... 其他非任務的 WebSocket 訊息處理 ...
    },

    // --- 新的輪詢機制 ---
    async fetchTaskStatus(taskId) {
      try {
        const response = await axios.get(`${API_BASE_URL}/task_status/${taskId}`);
        const updatedTask = response.data;

        const taskIndex = this.pendingTasks.findIndex(t => t.id === taskId);

        if (taskIndex !== -1) {
          // 更新 pendingTasks 中的任務
          this.pendingTasks.splice(taskIndex, 1, updatedTask);

          // 如果任務已完成或失敗，則停止輪詢並轉移任務
          if (updatedTask.status === 'completed' || updatedTask.status === 'failed') {
            this.stopPolling(taskId);
            const [finishedTask] = this.pendingTasks.splice(taskIndex, 1);
            this.completedTasks.unshift(finishedTask); // 加到最前面，方便查看
          }
        } else {
          // 如果在 pendingTasks 中找不到，可能已經處理完畢，停止輪詢
          this.stopPolling(taskId);
        }
      } catch (error) {
        console.error(`獲取任務 ${taskId} 狀態時發生錯誤:`, error);
        // 如果 API 回傳 404 (找不到任務)，也停止輪詢
        if (error.response && error.response.status === 404) {
          this.stopPolling(taskId);
        }
      }
    },

    startPolling(taskId) {
      // 如果已經在輪詢，則先停止舊的
      if (this.pollingIntervals[taskId]) {
        this.stopPolling(taskId);
      }
      // 立即執行一次，以便快速更新狀態
      this.fetchTaskStatus(taskId);
      // 設定定時器
      this.pollingIntervals[taskId] = setInterval(() => {
        this.fetchTaskStatus(taskId);
      }, POLLING_INTERVAL);
    },

    stopPolling(taskId) {
      if (this.pollingIntervals[taskId]) {
        clearInterval(this.pollingIntervals[taskId]);
        delete this.pollingIntervals[taskId];
        console.log(`已停止對任務 ${taskId} 的輪詢。`);
      }
    },

    // --- 修改後的任務建立 Actions ---
    async startTranscription(formData) {
      try {
        const response = await axios.post(`${API_BASE_URL}/transcribe`, formData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        });
        const task = response.data;

        // 將新任務立即加入待處理列表
        this.pendingTasks.unshift({ id: task.task_id, status: 'pending', payload: { original_filename: formData.get('file').name } });

        // **核心改動：啟動輪詢，而不是發送 WebSocket 訊息**
        this.startPolling(task.task_id);

      } catch (error) {
        console.error('開始轉錄時發生錯誤:', error);
        throw error;
      }
    },

    async processYoutubeRequest(options) {
        try {
            const response = await axios.post(`${API_BASE_URL}/youtube/process`, options);
            const result = response.data;

            // 為每一個建立的任務啟動輪詢
            result.tasks.forEach(task => {
                this.pendingTasks.unshift({ id: task.task_id, status: 'pending', payload: { url: task.url } });
                this.startPolling(task.task_id);
            });
        } catch (error) {
            console.error('處理 YouTube 請求時發生錯誤:', error);
            throw new Error(error.response?.data?.detail || '建立 YouTube 分析任務失敗');
        }
    },

    // --- 其他既有 Actions (fetchTasks, renameTask 等保持不變) ---
    async fetchTasks() {
      // ... fetchTasks 邏輯保持不變 ...
      // (為了簡潔，此處省略，實際程式碼中保留原樣)
      // 注意：此處的 task id 應為 `task.id` 以保持一致性
    },

    // ... 其他 actions ...
  }
})

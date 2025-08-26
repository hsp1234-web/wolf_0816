<template>
  <div class="card">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
      <h2>📊 全域儀表板</h2>
      <button @click="performHealthCheck" :disabled="!socketConnected" title="測試與後端的雙向通訊" data-testid="health-check-button">執行通訊測試</button>
    </div>
    <div class="dashboard-grid">
      <div class="stat-item">
        <span class="status-light" :class="statusClass"></span>
        <strong>狀態:</strong> <span id="status-text">{{ statusText }}</span>
      </div>
      <div class="stat-item">
        <strong>模型:</strong> <span id="model-display">{{ systemStats.active_model || '--' }}</span>
      </div>
      <div class="stat-item">
        <strong>GPU:</strong> <span id="gpu-display">{{ systemStats.gpu_name || '未偵測到' }}</span>
      </div>
      <div class="stat-item">
        <span>CPU:</span> <span id="cpu-label">{{ systemStats.cpu_usage != null ? systemStats.cpu_usage + '%' : '--' }}</span>
      </div>
      <div class="stat-item">
        <span>RAM:</span> <span id="ram-label">{{ systemStats.ram_usage != null ? systemStats.ram_usage + '%' : '--' }}</span>
      </div>
      <div class="stat-item">
        <span>GPU 使用率:</span> <span id="gpu-label">{{ systemStats.gpu_usage != null ? systemStats.gpu_usage + '%' : '--' }}</span>
      </div>
    </div>
  </div>

  <div class="card worker-status-card">
    <h2>🛠️ 工作者狀態</h2>
    <div v-if="Object.keys(workerStatuses).length > 0" class="worker-status-container">
      <div v-for="(status, name) in workerStatuses" :key="name" class="worker-stat-item">
        <span class="status-light" :class="getWorkerStatusClass(status.status)"></span>
        <strong class="worker-name">{{ name }}:</strong>
        <span class="worker-status-text">{{ translateWorkerStatus(status.status) }}</span>
      </div>
    </div>
    <div v-else>
      <p>正在等待工作者狀態...</p>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useTasksStore } from '@/stores/tasks'
import { useNotificationStore } from '@/stores/notifications'
import { logAction } from '@/utils/logging'


const tasksStore = useTasksStore()
const notificationStore = useNotificationStore()

// 從 store 中獲取系統狀態
const systemStats = computed(() => tasksStore.systemStats || {})
const socketConnected = computed(() => tasksStore.socketConnected)
const workerStatuses = computed(() => tasksStore.workerStatuses)

// 計算狀態文字和指示燈樣式
const statusText = computed(() => {
  if (socketConnected.value) {
    return '準備就緒'
  } else {
    return '已離線'
  }
})

const performHealthCheck = async () => {
  logAction('click-run-health-check');
  notificationStore.addNotification('正在執行健康檢查...', 'info');
  const result = await tasksStore.runHealthCheck();

  if (result.success) {
    const { backend_status, backend_message } = result.response;
    const message = `健康檢查成功！後端狀態: ${backend_status} (${backend_message})`;
    notificationStore.addNotification(message, 'success', 5000);
    logAction('health-check-success', { ...result.response });
  } else {
    const error_message = result.error?.message || '未知錯誤';
    const message = `健康檢查失敗: ${error_message}`;
    notificationStore.addNotification(message, 'error', 7000);
    logAction('health-check-failed', { error: error_message });
  }
};

const statusClass = computed(() => {
  return {
    'status-green': socketConnected.value,
    'status-yellow': !socketConnected.value
  }
})

const getWorkerStatusClass = (status) => {
  switch (status) {
    case 'READY':
    case 'RUNNING':
      return 'status-green'
    case 'INSTALLING':
      return 'status-yellow'
    case 'FAILED':
      return 'status-red'
    default: // NOT_STARTED or other
      return 'status-gray'
  }
}

const translateWorkerStatus = (status) => {
  const translations = {
    'NOT_STARTED': '未啟動',
    'INSTALLING': '安裝中',
    'READY': '準備就緒',
    'FAILED': '失敗',
    'RUNNING': '運行中',
  };
  return translations[status] || status;
}

// onMounted hook is no longer needed as the WebSocket now pushes all state updates.
// Keeping the onMounted logic would result in errors as the fetch actions have been removed from the store.
</script>

<style scoped>
.worker-status-card {
  margin-top: 24px;
}
.worker-status-container {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}
.worker-stat-item {
  display: flex;
  align-items: center;
  background-color: #f5f5f5;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
  flex-basis: 220px;
  /* JULES'S FIX (2025-08-20): 解決痛點 4 - 狀態顯示排版混亂 */
  /* 移除 flex-grow: 1，避免項目在換行後不自然地拉伸填滿整個寬度， */
  /* 讓排版在窄螢幕上更加整齊、優雅。 */
  flex-grow: 0;
}
.worker-name {
  text-transform: capitalize;
  margin-right: 8px;
  font-weight: 600;
}
</style>

<template>
  <div class="card">
    <h2>📊 全域儀表板</h2>
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
import { computed, onMounted, onUnmounted } from 'vue'
import { useTasksStore } from '@/stores/tasks'

const tasksStore = useTasksStore()

// 從 store 中獲取系統狀態
const systemStats = computed(() => tasksStore.systemStats)
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

let pollingInterval = null

onMounted(() => {
  // 立即獲取一次狀態
  tasksStore.fetchSystemStats()
  tasksStore.fetchWorkerStatuses()
  // 每 2 秒輪詢一次
  pollingInterval = setInterval(() => {
    tasksStore.fetchSystemStats()
    tasksStore.fetchWorkerStatuses()
  }, 2000)
})

onUnmounted(() => {
  // 元件卸載時停止輪詢
  if (pollingInterval) {
    clearInterval(pollingInterval)
  }
})
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
  flex-grow: 1;
}
.worker-name {
  text-transform: capitalize;
  margin-right: 8px;
  font-weight: 600;
}
</style>

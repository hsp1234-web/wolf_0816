<template>
  <div class="card">
    <h2>📊 全域儀表板</h2>
    <div class="dashboard-grid">
      <div class="stat-item">
        <span class="status-light" :class="statusClass"></span>
        <strong>狀態:</strong> <span id="status-text">{{ statusText }}</span>
      </div>
      <div class="stat-item"><strong>模型:</strong> <span id="model-display">--</span></div>
      <div class="stat-item"><strong>GPU:</strong> <span id="gpu-display">--</span></div>
    </div>
    <div class="dashboard-grid" style="margin-top: 16px;">
      <div class="stat-item"><span>CPU:</span> <span id="cpu-label">{{ systemStats.cpu_usage || '--' }}%</span></div>
      <div class="stat-item"><span>RAM:</span> <span id="ram-label">{{ systemStats.ram_usage || '--' }}%</span></div>
      <div class="stat-item"><span>GPU:</span> <span id="gpu-label">{{ systemStats.gpu_usage || '--' }}%</span></div>
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

let pollingInterval = null

onMounted(() => {
  // 立即獲取一次狀態
  tasksStore.fetchSystemStats()
  // 每 2 秒輪詢一次
  pollingInterval = setInterval(() => {
    tasksStore.fetchSystemStats()
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
/* Scoped styles for the dashboard */
</style>

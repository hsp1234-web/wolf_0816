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
    <h2>🚦 系統狀態總覽 (紅綠燈)</h2>
    <div class="worker-status-container">
      <!-- WebSocket / Database -->
      <div class="worker-stat-item">
        <span class="status-light" :class="statusClass"></span>
        <strong class="worker-name">核心通訊:</strong>
        <span class="worker-status-text">{{ socketConnected ? '連線正常' : '已斷線' }}</span>
      </div>
      <!-- Transcription Worker -->
      <div class="worker-stat-item">
        <span class="status-light" :class="getWorkerStatusClass(workerStatuses.transcription?.status || 'NOT_STARTED')"></span>
        <strong class="worker-name">轉錄服務:</strong>
        <span class="worker-status-text">{{ translateWorkerStatus(workerStatuses.transcription?.status || 'NOT_STARTED') }}</span>
      </div>
      <!-- Hardware Monitor -->
      <div class="worker-stat-item">
         <span class="status-light" :class="systemStats.cpu_usage != null ? 'status-green' : 'status-gray'"></span>
        <strong class="worker-name">硬體監控:</strong>
        <span class="worker-status-text">{{ systemStats.cpu_usage != null ? '運作中' : '未啟動' }}</span>
      </div>
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
  notificationStore.addNotification('正在執行全方位健康檢查...', 'info', 2000);
  const result = await tasksStore.runHealthCheck();

  let report_lines = ["<strong>全方位健康檢查報告:</strong>"];
  let final_status = 'success';

  // 1. 檢查後端子系統
  if (result.success) {
    const backend_response = result.response;
    report_lines.push(`- ✅ 後端 API (總體): ${backend_response.status}`);
    for (const [key, sub_status] of Object.entries(backend_response.subsystems || {})) {
      const icon = sub_status.status === 'ok' ? '✅' : '❌';
      report_lines.push(`  - ${icon} ${key}: ${sub_status.status}`);
    }
  } else {
    final_status = 'error';
    const error_message = result.error?.message || '未知錯誤';
    report_lines.push(`- ❌ 後端 API: 檢查失敗 (${error_message})`);
  }

  // 2. 檢查前端 WebSocket 連線狀態
  const ws_icon = socketConnected.value ? '✅' : '❌';
  if (!socketConnected.value) final_status = 'error';
  report_lines.push(`- ${ws_icon} 前端 WebSocket: ${socketConnected.value ? '已連線' : '已斷線'}`);

  // 3. 檢查關鍵按鈕狀態 (以「下載模型」按鈕為例)
  // 由於此檢查在儀表板元件中，我們無法直接存取其他元件的 DOM。
  // 更穩健的方式是檢查其背後的響應式狀態。
  const isModelReady = tasksStore.localModels.available.includes('tiny'); // 假設我們關心 'tiny' 模型
  const isModelChecking = tasksStore.localModels.checking;
  const isDownloadButtonDisabled = isModelReady || isModelChecking;
  report_lines.push(`- ℹ️ 前端按鈕狀態 (下載模型): ${isDownloadButtonDisabled ? '已禁用 (正常)' : '可啟用'}`);

  const report_html = report_lines.join('<br>');
  notificationStore.addNotification(report_html, final_status, 10000); // 顯示 10 秒
  logAction('health-check-completed', { report: report_lines.join('; '), status: final_status });
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

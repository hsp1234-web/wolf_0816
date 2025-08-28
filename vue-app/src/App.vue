<template>
  <div id="app" class="container">
    <!-- v16 新增：初始安裝狀態覆蓋層 -->
    <div v-if="installationStatus.inProgress || installationStatus.failed" class="installation-overlay">
      <div class="overlay-content">
        <div v-if="installationStatus.inProgress" class="spinner"></div>
        <div v-if="installationStatus.failed" class="status-icon-failed">❌</div>
        <p>{{ installationStatus.message }}</p>
        <div class="log-container" v-if="installationStatus.log.length > 0">
          <pre><code>{{ installationStatus.log.slice(-10).join('\n') }}</code></pre>
        </div>
        <button v-if="installationStatus.failed" @click="() => window.location.reload()">重新載入</button>
      </div>
    </div>

    <!-- 只有在安裝完成後才顯示主應用程式 -->
    <template v-if="installationStatus.completed">
      <!-- 全域操作狀態覆蓋層 (用於轉錄等操作) -->
      <div v-if="operationStatus.inProgress" class="installation-overlay">
        <div class="overlay-content">
          <div class="spinner"></div>
          <p>{{ operationStatus.message }}</p>
          <div v-if="operationStatus.progress > 0" class="progress-bar-container">
            <div class="progress-bar" :style="{ width: operationStatus.progress + '%' }"></div>
          </div>
        </div>
      </div>

      <!-- 全域通知組件 -->
      <NotificationHost />

      <!-- 初始自動下載提示 -->
      <div v-if="!initialSetup.completed" class="initial-setup-banner card">
        <p>
          為了優化您的初次使用體驗，系統將在 <strong>{{ initialSetup.countdown }}</strong> 秒後自動下載基礎模型 (tiny)。
        </p>
        <button @click="tasksStore.cancelInitialCountdown()">取消自動下載</button>
      </div>

      <!-- 標題 -->
      <header class="card" style="display: flex; justify-content: space-between; align-items: center;">
        <h1>音訊轉錄儀 (Vue)</h1>
      </header>

      <!-- 全域儀表板 -->
      <Dashboard />

      <!-- 功能分頁導覽 -->
      <div class="card" :class="{ 'disabled-content': operationStatus.inProgress }">
        <div class="tab-container">
          <button
            class="tab-button"
            :class="{ active: activeTab === 'transcribe' }"
            @click="setActiveTab('transcribe')"
            :disabled="operationStatus.inProgress"
          >
            📁 本機檔案轉錄
            <span :class="getWorkerStatusInfo('transcription').class" class="status-indicator">
              {{ getWorkerStatusInfo('transcription').text }}
            </span>
          </button>
          <button
            class="tab-button"
            :class="{ active: activeTab === 'downloader' }"
            @click="setActiveTab('downloader')"
            :disabled="operationStatus.inProgress"
          >
            📥 媒體下載器
            <span :class="getWorkerStatusInfo('youtube').class" class="status-indicator">
              {{ getWorkerStatusInfo('youtube').text }}
            </span>
          </button>
          <button
            class="tab-button"
            :class="{ active: activeTab === 'youtube' }"
            @click="setActiveTab('youtube')"
            :disabled="operationStatus.inProgress"
          >
            ▶️ YouTube 轉報告
            <span :class="getWorkerStatusInfo('youtube').class" class="status-indicator">
              {{ getWorkerStatusInfo('youtube').text }}
            </span>
          </button>
          <button
            class="tab-button"
            :class="{ active: activeTab === 'logs' }"
            @click="setActiveTab('logs')"
            :disabled="operationStatus.inProgress"
          >
            📜 系統日誌
          </button>
        </div>
      </div>

      <!-- 分頁內容 -->
      <main :class="{ 'disabled-content': operationStatus.inProgress }">
        <!-- 本機檔案轉錄分頁 -->
        <div v-show="activeTab === 'transcribe'">
          <TaskUploader />
        </div>

        <!-- 媒體下載器分頁 -->
        <div v-show="activeTab === 'downloader'">
          <Downloader />
        </div>

        <!-- YouTube 轉報告分頁 -->
        <div v-show="activeTab === 'youtube'">
          <YouTubeReporter />
        </div>

        <!-- 系統日誌分頁 -->
        <div v-show="activeTab === 'logs'">
          <LogViewer />
        </div>

        <!-- 任務佇列 -->
        <TaskPool />

        <!-- 任務列表 (所有分頁共用) -->
        <div class="grid-2-col" style="margin-top: 24px;">
          <PendingTasks />
          <CompletedTasks />
        </div>

        <!-- 即時轉錄輸出 -->
        <TranscriptOutput v-if="activeTab === 'transcribe'" />
      </main>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { useTasksStore } from './stores/tasks'
import { useSystemStore } from './stores/system'
import { useNotificationStore } from './stores/notifications'
import { logAction } from './utils/logging'
import Dashboard from './components/Dashboard.vue'
import TaskUploader from './components/TaskUploader.vue'
import Downloader from './components/Downloader.vue'
import YouTubeReporter from './components/YouTubeReporter.vue'
import LogViewer from './components/LogViewer.vue'
import PendingTasks from './components/PendingTasks.vue'
import CompletedTasks from './components/CompletedTasks.vue'
import TranscriptOutput from './components/TranscriptOutput.vue'
import NotificationHost from './components/NotificationHost.vue'
import TaskPool from './components/TaskPool.vue'

// 獲取 Pinia store 的實例
const tasksStore = useTasksStore()
const systemStore = useSystemStore()
const notificationStore = useNotificationStore()

// --- 狀態管理 ---
const activeTab = ref('transcribe')

// v16 新增：從 store 獲取安裝狀態
const installationStatus = computed(() => tasksStore.installationStatus)

const workerStatuses = computed(() => tasksStore.workerStatuses)
const operationStatus = computed(() => tasksStore.operationStatus)
const initialSetup = computed(() => tasksStore.initialSetup || { completed: true })
const socketConnected = computed(() => tasksStore.socketConnected);


// --- 方法 ---

// 根據工作者狀態回傳顯示資訊
const getWorkerStatusInfo = (workerName) => {
  if (operationStatus.value.inProgress) {
      return { text: '準備中', class: 'status-yellow' };
  }
  const status = workerStatuses.value[workerName]?.status || 'NOT_STARTED';
  switch (status) {
    case 'READY':
      return { text: '就緒', class: 'status-green' };
    case 'INSTALLING':
      return { text: '準備中...', class: 'status-yellow' };
    case 'FAILED':
      return { text: '失敗', class: 'status-red' };
    default:
      return { text: '未啟動', class: 'status-grey' };
  }
};

// 設定當前頁籤，並按需啟動工作者
const setActiveTab = (tabName) => {
  if (operationStatus.value.inProgress) return;
  activeTab.value = tabName
  logAction('click-tab', tabName)

  const workerMap = {
    transcribe: 'transcription',
    youtube: 'youtube',
    downloader: 'youtube' // 下載器也依賴 youtube 工作者
  };

  const workerName = workerMap[tabName];
  if (workerName) {
    const status = workerStatuses.value[workerName]?.status;
    // 如果工作者未啟動或失敗，則嘗試啟動它
    if (status === 'NOT_STARTED' || status === 'FAILED') {
      tasksStore.launchWorker(workerName);
    }
  }
}

// --- 啟動時健康檢查 ---
const runStartupHealthCheckWithRetries = async () => {
  const maxRetries = 2; // 總共嘗試 1+2=3 次
  for (let attempt = 1; attempt <= maxRetries + 1; attempt++) {
    notificationStore.addNotification(`(第 ${attempt} 次) 正在執行啟動健康檢查...`, 'info', 3000);
    const result = await tasksStore.runHealthCheck();

    if (result.success && result.response.backend_status === 'ok') {
      notificationStore.addNotification('✅ 啟動健康檢查成功！系統已就緒。', 'success', 5000);
      logAction('startup-health-check-success', { attempt });
      return; // 成功，退出循環
    } else {
      const errorMessage = result.error?.message || result.response?.backend_message || '後端回報狀態不佳';
      logAction('startup-health-check-failed', { attempt, error: errorMessage });
      if (attempt <= maxRetries) {
        notificationStore.addNotification(`⚠️ 健康檢查失敗 (${errorMessage})，3 秒後重試...`, 'warning', 3000);
        await new Promise(resolve => setTimeout(resolve, 3000));
      } else {
        notificationStore.addNotification(`❌ 啟動健康檢查在多次嘗試後依然失敗，請檢查主控台。`, 'error', 10000);
      }
    }
  }
};

// --- 生命週期與監聽 ---
watch(socketConnected, async (newValue, oldValue) => {
  if (newValue === true && oldValue === false) {
    logAction('main-websocket-connected');
    // 主服務 WebSocket 連接成功後，執行健康檢查
    await tasksStore.checkLocalModels();
    await runStartupHealthCheckWithRetries();
  }
});

onMounted(() => {
  // v18 架構修復：移除對已廢棄的門面伺服器的呼叫。
  // 現在我們直接初始化與主後端服務的 WebSocket 連線。
  tasksStore.initializeSystem();

  // 這個可以保留，因为它獲取的是相對靜態的功能開關狀態
  // systemStore.fetchFeatureStatus(); // NOTE: 經確認，此為舊版 API，已移除。
})
</script>

<style scoped>
/* App.vue 的特定樣式可以放在這裡 */
/* 全域樣式已在 main.css 中定義 */

.overlay-content {
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.overlay-content p {
  font-size: 1.1rem;
  font-weight: 500;
  margin: 0;
}

.log-container {
  background-color: #1a1a1a;
  color: #f0f0f0;
  font-family: 'Courier New', Courier, monospace;
  font-size: 0.8rem;
  padding: 12px;
  border-radius: 6px;
  width: 80%;
  max-width: 600px;
  height: 200px;
  overflow-y: auto;
  text-align: left;
  white-space: pre-wrap;
  border: 1px solid #444;
}

.status-icon-failed {
  font-size: 2rem;
}

.progress-bar-container {
  width: 250px;
  height: 8px;
  background-color: rgba(255, 255, 255, 0.2);
  border-radius: 4px;
  margin-top: 16px;
  overflow: hidden;
  display: inline-block;
}

.progress-bar {
  width: 0%;
  height: 100%;
  background-color: #4CAF50;
  transition: width 0.2s ease-in-out;
}

.status-indicator {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 12px;
  font-size: 0.75rem;
  margin-left: 10px;
  color: white;
  font-weight: 600;
  vertical-align: middle;
  line-height: 1;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.status-green { background-color: #28a745; }
.status-yellow { background-color: #ffc107; color: #212529; }
.status-red { background-color: #dc3545; }
.status-grey { background-color: #6c757d; }


.container {
  max-width: 1200px;
  margin: auto;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

main {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.initial-setup-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  background-color: #eef2ff;
  border-color: #c7d2fe;
}
.initial-setup-banner p {
  margin: 0;
  font-weight: 500;
}
.initial-setup-banner button {
  background-color: #6c757d;
  flex-shrink: 0;
}
</style>

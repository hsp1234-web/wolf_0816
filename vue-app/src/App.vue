<template>
  <div id="app" class="container">
    <!-- 安裝狀態覆蓋層 -->
    <div v-if="installationStatus.inProgress" class="installation-overlay">
      <div class="spinner"></div>
      <p>{{ installationStatus.message }}</p>
    </div>

    <!-- 全域通知組件 -->
    <NotificationHost />

    <!-- 標題 -->
    <header class="card" style="display: flex; justify-content: space-between; align-items: center;">
      <h1>音訊轉錄儀 (Vue)</h1>
    </header>

    <!-- 全域儀表板 -->
    <Dashboard />

    <!-- 功能分頁導覽 -->
    <div class="card" :class="{ 'disabled-content': installationStatus.inProgress }">
      <div class="tab-container">
        <button
          class="tab-button"
          :class="{ active: activeTab === 'transcribe' }"
          @click="setActiveTab('transcribe')"
          :disabled="installationStatus.inProgress"
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
          :disabled="installationStatus.inProgress"
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
          :disabled="installationStatus.inProgress"
        >
          ▶️ YouTube 轉報告
          <span :class="getWorkerStatusInfo('youtube').class" class="status-indicator">
            {{ getWorkerStatusInfo('youtube').text }}
          </span>
        </button>
      </div>
    </div>

    <!-- 分頁內容 -->
    <main :class="{ 'disabled-content': installationStatus.inProgress }">
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

      <!-- 任務列表 (所有分頁共用) -->
      <div class="grid-2-col" style="margin-top: 24px;">
        <PendingTasks />
        <CompletedTasks />
      </div>

      <!-- 即時轉錄輸出 -->
      <TranscriptOutput v-if="activeTab === 'transcribe'" />
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useTasksStore } from './stores/tasks'
import { logAction } from './utils/logging'
import Dashboard from './components/Dashboard.vue'
import TaskUploader from './components/TaskUploader.vue'
import Downloader from './components/Downloader.vue'
import YouTubeReporter from './components/YouTubeReporter.vue'
import PendingTasks from './components/PendingTasks.vue'
import CompletedTasks from './components/CompletedTasks.vue'
import TranscriptOutput from './components/TranscriptOutput.vue'
import NotificationHost from './components/NotificationHost.vue'

// 獲取 Pinia store 的實例
const tasksStore = useTasksStore()

// --- 狀態管理 ---
const activeTab = ref('transcribe')
const workerStatuses = computed(() => tasksStore.workerStatuses)
const installationStatus = computed(() => tasksStore.installationStatus)

// --- 方法 ---

// 根據工作者狀態回傳顯示資訊
const getWorkerStatusInfo = (workerName) => {
  if (installationStatus.value.inProgress) {
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
  if (installationStatus.value.inProgress) return;
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

// --- 生命週期鉤子 ---
onMounted(() => {
  // 使用新的兩階段啟動方法
  tasksStore.initializeSystem();
})
</script>

<style scoped>
/* App.vue 的特定樣式可以放在這裡 */
/* 全域樣式已在 main.css 中定義 */

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
</style>

<template>
  <div id="app" class="container">
    <!-- 全域通知組件 -->
    <NotificationHost />

    <!-- 標題 -->
    <header class="card" style="display: flex; justify-content: space-between; align-items: center;">
      <h1>音訊轉錄儀 (Vue)</h1>
    </header>

    <!-- 全域儀表板 -->
    <Dashboard />

    <!-- 功能分頁導覽 -->
    <div class="card">
      <div class="tab-container">
        <button
          class="tab-button"
          :class="{ active: activeTab === 'transcribe' }"
          @click="setActiveTab('transcribe')"
        >
          📁 本機檔案轉錄
        </button>
        <button
          class="tab-button"
          :class="{ active: activeTab === 'downloader' }"
          @click="setActiveTab('downloader')"
        >
          📥 媒體下載器
        </button>
        <button
          class="tab-button"
          :class="{ active: activeTab === 'youtube' }"
          @click="setActiveTab('youtube')"
        >
          ▶️ YouTube 轉報告
        </button>
      </div>
    </div>

    <!-- 分頁內容 -->
    <main>
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
import { ref, onMounted } from 'vue'
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

// 控制當前作用中分頁的狀態
const activeTab = ref('transcribe')

const setActiveTab = (tabName) => {
  activeTab.value = tabName
  logAction('click-tab', tabName)
}

// 當元件掛載完成後，執行初始化操作
onMounted(() => {
  // 從後端獲取任務歷史紀錄
  tasksStore.fetchTasks()
  // 建立 WebSocket 連線
  tasksStore.connectWebSocket()
})
</script>

<style scoped>
/* App.vue 的特定樣式可以放在這裡 */
/* 全域樣式已在 main.css 中定義 */
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

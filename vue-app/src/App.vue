<template>
  <div id="app" class="container">
    <!-- 標題 -->
    <header class="card" style="display: flex; justify-content: space-between; align-items: center;">
      <h1>音訊轉錄儀 (Vue)</h1>
    </header>

    <!-- 主要內容區域 -->
    <main>
      <!-- 檔案上傳和設定元件 -->
      <TaskUploader />

      <!-- 任務列表 -->
      <div class="grid-2-col" style="margin-top: 24px;">
        <PendingTasks />
        <CompletedTasks />
      </div>
    </main>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useTasksStore } from './stores/tasks'
import TaskUploader from './components/TaskUploader.vue'
import PendingTasks from './components/PendingTasks.vue'
import CompletedTasks from './components/CompletedTasks.vue'

// 獲取 Pinia store 的實例
const tasksStore = useTasksStore()

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

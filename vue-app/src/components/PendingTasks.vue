<template>
  <div class="card">
    <h2>🔄 進行中任務</h2>
    <div id="ongoing-tasks" class="task-list">
      <!-- 如果沒有進行中的任務，顯示提示訊息 -->
      <p v-if="pendingTasks.length === 0" id="no-ongoing-task-msg">暫無執行中任務</p>
      <!-- 使用 v-for 渲染任務列表 -->
      <div v-else v-for="task in pendingTasks" :key="task.task_id" class="task-item">
        <div style="flex-grow: 1; overflow: hidden; margin-right: 10px; min-width: 0;">
          <span class="task-filename" :title="task.payload.original_filename || task.task_id">
            {{ task.payload.original_filename || task.task_id }}
          </span>
          <!-- 動態進度條 -->
          <div
            v-if="task.progress !== undefined"
            class="progress-container"
            style="margin-top: 5px; height: 8px;"
          >
            <div
              class="progress-bar"
              :style="{ width: task.progress + '%' }"
            ></div>
          </div>
        </div>
        <div class="task-status-container">
          <span v-if="task.elapsed_time > 0" class="task-timer">
            {{ formatTime(task.elapsed_time) }}
          </span>
          <span class="task-status" :class="`status-${task.status}`">
            {{ task.message || task.status }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useTasksStore } from '@/stores/tasks'

// 獲取 store 實例
const tasksStore = useTasksStore()

// 建立一個計算屬性來響應式地獲取進行中的任務
const pendingTasks = computed(() => tasksStore.pendingTasks)

// 格式化時間的輔助函數
const formatTime = (seconds) => {
  if (isNaN(seconds) || seconds < 0) {
    return '00:00'
  }
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
}
</script>

<style scoped>
/* 此元件的專屬樣式 */
</style>

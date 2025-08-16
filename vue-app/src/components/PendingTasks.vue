<template>
  <div class="card">
    <h2>🔄 進行中任務</h2>
    <div id="ongoing-tasks" class="task-list">
      <!-- 如果沒有進行中的任務，顯示提示訊息 -->
      <p v-if="pendingTasks.length === 0" id="no-ongoing-task-msg">暫無執行中任務</p>
      <!-- 使用 v-for 渲染任務列表 -->
      <div v-else v-for="task in pendingTasks" :key="task.task_id" class="task-item">
        <span class="task-filename" :title="task.payload.original_filename">
          {{ task.payload.original_filename || task.task_id }}
        </span>
        <span class="task-status" :class="`status-${task.status}`">
          {{ task.status }}
        </span>
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
</script>

<style scoped>
/* 此元件的專屬樣式 */
</style>

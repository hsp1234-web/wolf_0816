<template>
  <div class="card">
    <h2>✅ 已完成任務</h2>
    <div id="completed-tasks" class="task-list">
      <!-- 如果沒有已完成的任務，顯示提示訊息 -->
      <p v-if="completedTasks.length === 0" id="no-completed-task-msg">尚無完成的任務</p>
      <!-- 使用 v-for 渲染任務列表 -->
      <div v-else v-for="task in completedTasks" :key="task.task_id" class="task-item">
        <span class="task-filename" :title="task.payload.original_filename">
          {{ task.payload.original_filename || task.task_id }}
        </span>
        <div class="task-actions">
          <a href="#" @click.prevent="previewTask(task)" class="btn-preview">預覽</a>
          <a :href="`/api/download/${task.task_id}`" class="btn-download" download>下載</a>
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

// 建立一個計算屬性來響應式地獲取已完成的任務
const completedTasks = computed(() => tasksStore.completedTasks)

// --- 事件處理方法 ---
const previewTask = (task) => {
  // TODO: 實現預覽功能，可能需要一個 modal 彈窗
  console.log('預覽任務:', task.task_id)
  alert(`預覽功能待辦：\n任務ID: ${task.task_id}\n檔案: ${task.payload.original_filename}`)
}
</script>

<style scoped>
/* 此元件的專屬樣式 */
</style>

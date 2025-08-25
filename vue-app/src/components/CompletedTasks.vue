<template>
  <div class="card">
    <h2>✅ 已完成任務</h2>
    <div id="completed-tasks" class="task-list">
      <!-- 如果沒有已完成的任務，顯示提示訊息 -->
      <p v-if="completedTasks.length === 0" id="no-completed-task-msg">尚無完成的任務</p>
      <!-- 使用 v-for 渲染任務列表 -->
      <div v-else v-for="task in completedTasks" :key="task.task_id" class="task-item">
        <div style="flex-grow: 1; overflow: hidden; margin-right: 10px; min-width: 0;">
          <span class="task-filename" :title="task.payload.original_filename">
            {{ task.payload.original_filename || task.task_id }}
          </span>
          <div v-if="task.status === 'failed' && task.error" class="task-error-message" :title="task.error">
            錯誤: {{ task.error }}
          </div>
        </div>
        <div class="task-actions">
          <!-- 僅在任務成功時顯示操作按鈕 -->
          <template v-if="task.status === 'completed'">
            <a href="#" @click.prevent="previewTask(task)" class="btn-preview">預覽</a>
            <a href="#" @click.prevent="renameTask(task)" class="btn-rename">修改名稱</a>
            <a :href="`/api/download/${task.task_id}`" class="btn-download" download>下載</a>
          </template>
          <!-- 在任務失敗時顯示狀態標籤 -->
          <span v-if="task.status === 'failed'" class="task-status status-failed">
            失敗
          </span>
        </div>
      </div>
    </div>
    <!-- 預覽用的 Modal 元件 -->
    <PreviewModal :task="taskToPreview" @close="taskToPreview = null" />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useTasksStore } from '@/stores/tasks'
import { useNotificationStore } from '@/stores/notifications'
import { logAction } from '@/utils/logging'
import PreviewModal from './PreviewModal.vue' // 匯入新的 Modal 元件

// 獲取 store 實例
const tasksStore = useTasksStore()
const notificationStore = useNotificationStore()

// 建立一個計算屬性來響應式地獲取已完成的任務
const completedTasks = computed(() => tasksStore.completedTasks)

// 用於儲存當前要預覽的任務
const taskToPreview = ref(null)

// --- 事件處理方法 ---
const previewTask = (task) => {
  logAction('click-preview-task', task.task_id)
  // 將點擊的任務設定為要預覽的任務，這會觸發 Modal 顯示
  taskToPreview.value = task
}

const renameTask = async (task) => {
  const currentName = task.payload.original_filename || '';
  const newName = prompt("請輸入新的檔案名稱 (不需包含副檔名):", currentName.split('.').slice(0, -1).join('.'));

  if (newName && newName.trim() && newName.trim() !== currentName) {
    logAction('click-rename-task-confirm', task.task_id)
    const sanitizedName = newName.trim().replace(/[\\/?%*:|"<>\x00-\x1F]/g, '');
    try {
        await tasksStore.renameTask(task.task_id, sanitizedName);
        notificationStore.addNotification('檔案已成功重新命名！', 'success');
    } catch (error) {
        notificationStore.addNotification(`重新命名失敗: ${error.message}`, 'error');
    }
  }
}
</script>

<style scoped>
/* 此元件的專屬樣式 */
</style>

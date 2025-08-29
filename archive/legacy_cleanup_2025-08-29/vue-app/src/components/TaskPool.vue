<template>
  <div class="card" v-if="taskPool.length > 0">
    <h2>📝 任務佇列</h2>
    <div class="task-pool-container">
      <div v-for="task in taskPool" :key="task.poolId" class="task-item">
        <div class="task-info">
          <strong class="task-type">{{ task.type === 'transcription' ? '檔案轉錄' : 'YouTube 分析' }}</strong>
          <span class="task-name" :title="task.name">{{ task.name }}</span>
        </div>
        <button @click="removeTask(task.poolId)" class="remove-btn">移除</button>
      </div>
    </div>
    <div class="pool-actions">
      <button @click="submitPool" class="submit-btn" data-testid="submit-queue-button">🚀 提交佇列中的 {{ taskPool.length }} 個任務</button>
      <button @click="clearPool" class="clear-btn" data-testid="clear-queue-button">清空佇列</button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { useTasksStore } from '@/stores/tasks';
import { useNotificationStore } from '@/stores/notifications';
import { logAction } from '@/utils/logging';

console.log('[TaskPool.vue] setting up...');

const tasksStore = useTasksStore();
const notificationStore = useNotificationStore();

const taskPool = computed(() => tasksStore.taskPool);

const removeTask = (poolId) => {
  logAction('click-remove-task-from-pool', poolId);
  tasksStore.removeTaskFromPool(poolId);
};

const clearPool = () => {
  logAction('click-clear-task-pool');
  tasksStore.clearTaskPool();
  notificationStore.addNotification('任務佇列已清空', 'info');
};

const submitPool = async () => {
  if (taskPool.value.length === 0) return;
  logAction('click-submit-task-pool', `task_count: ${taskPool.value.length}`);

  try {
    notificationStore.addNotification('正在提交任務佇列...', 'info');
    await tasksStore.submitTaskPool(taskPool.value);
    // 成功後 store 會自動清空 taskPool，並觸發 UI 更新
    notificationStore.addNotification('任務已全部成功提交！', 'success');
  } catch (error) {
    notificationStore.addNotification('提交任務時發生錯誤，請檢查主控台。', 'error');
  }
};
</script>

<style scoped>
.card {
  margin-top: 24px;
}
.task-pool-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 16px;
  max-height: 300px;
  overflow-y: auto;
  padding: 8px;
  background-color: #f9f9f9;
  border-radius: 8px;
}
.task-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  background-color: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
}
.task-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.task-type {
  font-size: 0.8em;
  color: #666;
}
.task-name {
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 300px;
}
.remove-btn {
  background-color: #ef5350;
  color: white;
  border: none;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9em;
}
.pool-actions {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-top: 20px;
}
.submit-btn {
  background-color: var(--primary-color);
  color: white;
  font-size: 1.1em;
}
.clear-btn {
  background-color: #757575;
}
</style>

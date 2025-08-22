<template>
  <div class="card">
    <h2>📜 系統日誌</h2>
    <div class="log-controls">
      <button @click="loadLogs">刷新日誌</button>
      <button @click="copyLogs" :disabled="logs.length === 0">複製日誌</button>
    </div>
    <div class="log-display-container">
      <pre v-if="logs.length > 0" class="log-display">{{ formattedLogs }}</pre>
      <p v-else>沒有日誌可顯示，或尚未載入。</p>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { useTasksStore } from '@/stores/tasks';
import { useNotificationStore } from '@/stores/notifications';

const tasksStore = useTasksStore();
const notificationStore = useNotificationStore();

const logs = computed(() => tasksStore.logs);

const formattedLogs = computed(() => {
  return logs.value
    .map(log => `[${log.timestamp}] [${log.source}] [${log.level}] ${log.message}`)
    .join('\n');
});

const loadLogs = () => {
  tasksStore.fetchLogs();
};

const copyLogs = () => {
  if (logs.value.length === 0) return;
  navigator.clipboard.writeText(formattedLogs.value).then(() => {
    notificationStore.addNotification('日誌已複製到剪貼簿！', 'success');
  }).catch(err => {
    console.error('複製日誌失敗:', err);
    notificationStore.addNotification('複製日誌失敗', 'error');
  });
};

// Component mounted hook
import { onMounted } from 'vue';
onMounted(() => {
  loadLogs();
});
</script>

<style scoped>
.log-controls {
  margin-bottom: 16px;
}
.log-display-container {
  background-color: #f5f5f5;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 16px;
  min-height: 200px;
  max-height: 500px;
  overflow-y: auto;
}
.log-display {
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: monospace;
  font-size: 0.85em;
  margin: 0;
}
</style>

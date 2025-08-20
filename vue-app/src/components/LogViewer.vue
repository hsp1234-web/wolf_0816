<template>
  <div class="card">
    <h2>📜 系統日誌</h2>
    <div class="log-controls">
      <button @click="loadLogs">刷新日誌</button>
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

const tasksStore = useTasksStore();

const logs = computed(() => tasksStore.logs);

const formattedLogs = computed(() => {
  return logs.value
    .map(log => `[${log.timestamp}] [${log.source}] [${log.level}] ${log.message}`)
    .join('\n');
});

const loadLogs = () => {
  tasksStore.fetchLogs();
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

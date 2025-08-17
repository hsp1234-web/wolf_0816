import { defineStore } from 'pinia';
import { ref } from 'vue';
import { useTasksStore } from './tasks'; // 匯入任務 store 以便通知

export const useFeatureStore = defineStore('features', () => {
  const features = ref({});
  const isWhisperReady = ref(false);
  const isYtdlpReady = ref(false);

  let pollInterval = null;

  async function pollFeatureStatus() {
    if (pollInterval) {
      clearInterval(pollInterval);
    }

    pollInterval = setInterval(async () => {
      try {
        const response = await fetch('/api/features/status');
        if (!response.ok) {
          throw new Error('無法獲取功能狀態');
        }
        const data = await response.json();
        features.value = data.features;

        // 更新特定功能的就緒狀態
        isWhisperReady.value = features.value.whisper === 'ready';
        isYtdlpReady.value = features.value.ytdlp === 'ready';

        // 如果所有功能都已就緒，停止輪詢
        const allReady = Object.values(features.value).every(status => status === 'ready');
        if (allReady) {
          clearInterval(pollInterval);
          pollInterval = null;
          // 通知任務 store，以便其可以刷新或重新檢查任務
          const taskStore = useTasksStore();
          taskStore.onFeaturesReady();
        }
      } catch (error) {
        console.error('輪詢功能狀態時發生錯誤:', error);
        // 發生錯誤時停止輪詢，避免洗版控制台
        clearInterval(pollInterval);
        pollInterval = null;
      }
    }, 2000); // 每 2 秒輪詢一次
  }

  return {
    features,
    isWhisperReady,
    isYtdlpReady,
    pollFeatureStatus,
  };
});

import { defineStore } from 'pinia';
import { ref } from 'vue';

export const useNotificationStore = defineStore('notifications', () => {
  // 使用 ref 創建一個響應式的通知陣列
  const notifications = ref([]);

  /**
   * 新增一條通知
   * @param {string} message - 要顯示的訊息
   * @param {string} [type='info'] - 通知類型 ('success', 'error', 'info')
   * @param {number} [duration=5000] - 顯示時長（毫秒）
   */
  const addNotification = (message, type = 'info', duration = 5000) => {
    const id = Date.now() + Math.random();
    notifications.value.push({ id, message, type });

    // 設定計時器，在指定時間後自動移除該通知
    if (duration > 0) {
      setTimeout(() => {
        removeNotification(id);
      }, duration);
    }
  };

  /**
   * 根據 ID 移除一條通知
   * @param {number} id - 要移除的通知的 ID
   */
  const removeNotification = (id) => {
    const index = notifications.value.findIndex(n => n.id === id);
    if (index !== -1) {
      notifications.value.splice(index, 1);
    }
  };

  return {
    notifications,
    addNotification,
    removeNotification,
  };
});

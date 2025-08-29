<template>
  <div class="notification-host">
    <TransitionGroup name="list" tag="div">
      <div
        v-for="notification in notifications"
        :key="notification.id"
        :class="['notification', `notification-${notification.type}`]"
      >
        <span class="notification-message">{{ notification.message }}</span>
        <button @click="removeNotification(notification.id)" class="close-button">&times;</button>
      </div>
    </TransitionGroup>
  </div>
</template>

<script setup>
import { useNotificationStore } from '@/stores/notifications';
import { storeToRefs } from 'pinia';

const notificationStore = useNotificationStore();
// 使用 storeToRefs 來保持響應性
const { notifications } = storeToRefs(notificationStore);
const { removeNotification } = notificationStore;
</script>

<style scoped>
.notification-host {
  position: fixed;
  bottom: 20px;
  right: 20px;
  z-index: 2000;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.notification {
  min-width: 300px;
  padding: 15px;
  border-radius: 8px;
  color: #fff;
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  animation: slide-in 0.3s ease-out;
}

.notification-info {
  background-color: #007bff;
}

.notification-success {
  background-color: #28a745;
}

.notification-error {
  background-color: #dc3545;
}

.notification-message {
  font-weight: 500;
}

.close-button {
  background: none;
  border: none;
  color: white;
  font-size: 1.5em;
  line-height: 1;
  cursor: pointer;
  opacity: 0.7;
  padding: 0 0 0 15px;
}

.close-button:hover {
  opacity: 1;
}

/* 動畫效果 */
.list-enter-active,
.list-leave-active {
  transition: all 0.5s ease;
}
.list-enter-from,
.list-leave-to {
  opacity: 0;
  transform: translateX(30px);
}

@keyframes slide-in {
  from {
    transform: translateX(100%);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}
</style>

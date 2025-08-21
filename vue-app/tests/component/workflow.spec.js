import { test, expect } from '@playwright/experimental-ct-vue';
import App from '../../src/App.vue';
import { createTestingPinia } from '@pinia/testing';
import { useTasksStore } from '../../src/stores/tasks';

// 測試：任務狀態應該能從「待處理」轉移到「已完成」
test('should transition task from pending to completed', async ({ mount, page }) => {
  // 步驟 1：掛載 App 元件，並提供一個用於測試的 Pinia store
  // 這樣我們可以隔離 store 的狀態，並在測試中進行控制
  const component = await mount(App, {
    global: {
      plugins: [createTestingPinia({
        // 設定 store 的初始狀態
        initialState: {
          tasks: {
            pendingTasks: [{ id: 'task-1', name: '我的第一個任務', status: 'pending' }],
            completedTasks: [],
          },
        },
      })],
    },
  });

  // 獲取在測試環境中運行的 store 實例
  const tasksStore = useTasksStore();

  // 步驟 2：驗證初始狀態
  // 確認任務一開始出現在「待處理」列表中
  await expect(component.locator('div.pending-tasks')).toContainText('我的第一個任務');
  await expect(component.locator('div.completed-tasks')).not.toContainText('我的第一個任務');
  expect(tasksStore.pendingTasks).toHaveLength(1);

  // 步驟 3：執行狀態轉移的操作
  // 這裡我們直接調用 store 的 action，而不是模擬點擊事件
  // 這種方法更穩定，能專注於測試狀態邏輯
  await tasksStore.moveTaskToCompleted('task-1');

  // 步驟 4：驗證最終狀態
  // 確認任務已從「待處理」列表消失，並出現在「已完成」列表中
  await expect(component.locator('div.pending-tasks')).not.toContainText('我的第一個任務');
  await expect(component.locator('div.completed-tasks')).toContainText('我的第一個任務');

  // 同時也驗證 store 的內部狀態是否正確
  expect(tasksStore.pendingTasks).toHaveLength(0);
  expect(tasksStore.completedTasks).toHaveLength(1);
  expect(tasksStore.completedTasks[0].name).toBe('我的第一個任務');
});

import { test, expect } from '@playwright/experimental-ct-vue';
import { createPinia, defineStore } from 'pinia';

// 待測元件
import PendingTasks from '../../src/components/PendingTasks.vue';
import CompletedTasks from '../../src/components/CompletedTasks.vue';

// 為了讓測試元件能共享 store，我們在外部定義一個 Pinia 實例
const pinia = createPinia();

// 測試描述
test.describe('核心工作流程測試 (處理中 -> 已完成)', () => {

  // 在這裡定義我們專為測試用的「假 store」
  const useMockTasksStore = defineStore('tasks', {
    state: () => ({
      pendingTasks: [],
      completedTasks: [],
      // 為了讓元件能正常渲染，我們也模擬一些其他的狀態
      socketConnected: true,
      systemStats: { active_model: 'mock-model', gpu_name: 'mock-gpu' },
      workerStatuses: {},
    }),
    // 將所有真實 store 中會執行非同步或網路操作的 actions
    // 全部覆蓋成「什麼都不做」的空函式。
    actions: {
      initializeSystem() { /* do nothing */ },
      connectToWebSocket() { /* do nothing */ },
      handleSocketMessage() { /* do nothing */ },
      fetchTasks() { /* do nothing */ },
      startTranscription() { /* do nothing */ },
      sendSocketMessage() { /* do nothing */ },
      renameTask() { /* do nothing */ },
      fetchSystemStats() { /* do nothing */ },
      startDownload() { /* do nothing */ },
      validateApiKey() { /* do nothing */ },
      fetchGeminiModels() { /* do nothing */ },
      processYoutubeRequest() { /* do nothing */ },
      fetchWorkerStatuses() { /* do nothing */ },
      launchWorker() { /* do nothing */ },
      fetchLogs() { /* do nothing */ },
      checkLocalModels() { /* do nothing */ },
      downloadModel() { /* do nothing */ },
      startInitialCountdown() { /* do nothing */ },
      cancelInitialCountdown() { /* do nothing */ },
    }
  });

  test('任務應該從「進行中」列表轉移到「已完成」列表', async ({ mount, page }) => {
    // 1. 掛載元件，並將我們建立的「假 Pinia 實例」注入進去
    // 我們使用一個虛擬的根元件來包裹待測的兩個元件
    const component = await mount(
      {
        template: `
          <div>
            <h1>進行中</h1>
            <PendingTasks />
            <hr />
            <h1>已完成</h1>
            <CompletedTasks />
          </div>
        `,
        components: { PendingTasks, CompletedTasks },
      },
      {
        global: {
          plugins: [pinia], // 將 Pinia 實例注入到 Vue 應用中
        },
      }
    );

    // 2. 取得我們在測試中建立的 store 實例，以便後續操作
    const tasksStore = useMockTasksStore();

    // 3. 設定初始狀態：一個「進行中」的任務
    const mockTask = {
      task_id: 'task-123',
      payload: { original_filename: '測試音檔.mp3' },
      status: 'processing',
      progress: 50,
    };
    // 直接修改 store 的 state
    tasksStore.pendingTasks = [mockTask];
    tasksStore.completedTasks = [];

    // 4. 驗證初始畫面
    //  - 驗證「進行中」區塊出現了我們的任務
    await expect(component.locator('div.task-item:has-text("測試音檔.mp3")')).toBeVisible();
    await expect(component.locator('text=進行中任務')).toBeVisible();
    //  - 驗證進度條的寬度是否正確
    await expect(component.locator('.progress-bar')).toHaveAttribute('style', 'width: 50%;');
    //  - 驗證「已完成」區塊是空的
    await expect(component.locator('text=尚無完成的任務')).toBeVisible();


    // 5. 模擬「任務完成」事件：直接修改 store 的狀態
    const completedMockTask = {
        ...mockTask,
        status: 'completed',
        progress: 100,
        result: {
            transcript: '這是模擬的逐字稿。',
        }
    };
    tasksStore.pendingTasks = [];
    tasksStore.completedTasks = [completedMockTask];

    // 6. 驗證最終畫面
    //  - 驗證任務已從「進行中」列表消失
    await expect(component.locator('text=暫無執行中任務')).toBeVisible();
    //  - 驗證任務已出現在「已完成」列表
    await expect(component.locator('div.task-item:has-text("測試音檔.mp3")')).toBeVisible();
    //  - 驗證「預覽」和「下載」按鈕都已出現
    const taskItem = component.locator('div.task-item:has-text("測試音檔.mp3")');
    await expect(taskItem.locator('a.btn-preview')).toBeVisible();
    await expect(taskItem.locator('a.btn-download')).toHaveAttribute('href', '/api/download/task-123');
  });
});

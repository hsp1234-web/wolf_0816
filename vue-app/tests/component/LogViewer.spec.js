import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import LogViewer from '@/components/LogViewer.vue'
import { useNotificationStore } from '@/stores/notifications'
import { useTasksStore } from '@/stores/tasks'

// Mock a global navigator object for clipboard
const mockClipboard = {
  writeText: vi.fn(),
};
Object.defineProperty(global.navigator, 'clipboard', {
  value: mockClipboard,
  writable: true,
});

describe('LogViewer.vue', () => {
  beforeEach(() => {
    // 在每個測試前重置所有模擬的狀態
    vi.clearAllMocks();
  });

  it('點擊複製按鈕時，如果成功，應該呼叫成功通知', async () => {
    // Arrange
    mockClipboard.writeText.mockResolvedValue(undefined); // Simulate success

    const wrapper = mount(LogViewer, {
      global: {
        plugins: [createTestingPinia({
          createSpy: vi.fn,
          initialState: {
            tasks: {
              logs: [{ timestamp: '2024-01-01', source: 'test', level: 'info', message: 'hello' }]
            }
          }
        })],
      },
    });

    const notificationStore = useNotificationStore();
    const tasksStore = useTasksStore();
    tasksStore.fetchLogs(); // Populate logs

    // Act
    await wrapper.find('button:nth-of-type(2)').trigger('click');

    // Assert
    expect(mockClipboard.writeText).toHaveBeenCalledTimes(1);
    expect(notificationStore.addNotification).toHaveBeenCalledWith('日誌已複製到剪貼簿！', 'success');
  });

  it('點擊複製按鈕時，如果失敗，應該呼叫錯誤通知', async () => {
    // Arrange
    const error = new Error('Copy failed');
    mockClipboard.writeText.mockRejectedValue(error); // Simulate failure

    const wrapper = mount(LogViewer, {
      global: {
        plugins: [createTestingPinia({
          createSpy: vi.fn,
          initialState: {
            tasks: {
              logs: [{ timestamp: '2024-01-01', source: 'test', level: 'info', message: 'hello' }]
            }
          }
        })],
      },
    });

    const notificationStore = useNotificationStore();
    const tasksStore = useTasksStore();
    tasksStore.fetchLogs();

    // Act
    await wrapper.find('button:nth-of-type(2)').trigger('click');

    // Assert
    expect(mockClipboard.writeText).toHaveBeenCalledTimes(1);
    expect(notificationStore.addNotification).toHaveBeenCalledWith('複製日誌失敗', 'error');
  });
});

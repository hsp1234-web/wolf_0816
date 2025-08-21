import { test, expect } from '@playwright/experimental-ct-vue';
import MinimalTest from '../../src/components/MinimalTest.vue';

test('should mount the minimal test component', async ({ mount }) => {
  // 嘗試掛載最簡化的元件
  const component = await mount(MinimalTest);

  // 驗證元件是否成功渲染其內容
  await expect(component).toContainText('Hello World from MinimalTest');
});

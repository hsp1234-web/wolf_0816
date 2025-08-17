<template>
  <div>
    <div class="card">
      <!-- API 金鑰管理 -->
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <h2>🔑 Google API 金鑰管理</h2>
        <a href="/static/prompts.html" target="_blank" style="font-weight: 500;">管理提示詞 &rarr;</a>
      </div>
      <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 12px;">
        <input type="password" v-model="apiKey" placeholder="在此貼上您的 Google API 金鑰" style="flex-grow: 1; padding: 10px; border-radius: 6px; border: 1px solid #ccc;">
        <button id="save-api-key-btn" @click="saveAndValidateApiKey" :disabled="!featureStore.isYtdlpReady || !featureStore.isWhisperReady">儲存金鑰</button>
        <button @click="clearApiKey" style="background-color: #6c757d;">清除金鑰</button>
      </div>
      <p id="api-key-status" style="margin-top: 0; font-weight: 500;">
        狀態: <span :style="{ color: apiKeyStatus.color, fontStyle: apiKeyStatus.italic ? 'italic' : 'normal' }">{{ apiKeyStatus.text }}</span>
      </p>

      <!-- YouTube 影片處理 -->
      <h2 style="margin-top: 24px;">▶️ 輸入 YouTube 影片</h2>
      <fieldset :disabled="!isApiKeyValid">
        <div class="flex-col" style="gap: 10px;">
          <div v-for="(link, index) in youtubeLinks" :key="index" class="youtube-link-row" style="display: flex; flex-wrap: wrap; gap: 10px; align-items: center;">
            <input type="text" v-model="link.url" placeholder="YouTube 影片網址" style="flex: 1 1 400px; padding: 10px; border-radius: 6px; border: 1px solid #ccc; box-sizing: border-box;">
            <input type="text" v-model="link.filename" placeholder="自訂檔名 (可選)" style="flex: 1 1 200px; padding: 10px; border-radius: 6px; border: 1px solid #ccc; box-sizing: border-box;">
            <button @click="removeYoutubeRow(index)" :disabled="youtubeLinks.length <= 1" style="background-color: #dc3545; padding: 10px 15px; flex-shrink: 0; line-height: 1; font-size: 1.2em;">×</button>
          </div>
        </div>
        <button @click="addYoutubeRow" style="margin-top: 12px;">+ 新增一列</button>
      </fieldset>
    </div>

    <!-- 參數控制區 -->
    <div class="card" style="margin-top: 24px;">
      <h2>⚙️ 參數控制區</h2>
      <fieldset :disabled="!isApiKeyValid">
        <div class="grid-2-col">
          <!-- 左側：任務選項 -->
          <div>
            <label><strong>任務選項</strong></label>
            <div style="display: flex; flex-direction: column; gap: 8px; margin-top: 8px;">
              <label><input type="checkbox" v-model="selectedTasks" value="summary"> 重點摘要</label>
              <label><input type="checkbox" v-model="selectedTasks" value="transcript"> 詳細逐字稿</label>
              <label><input type="checkbox" v-model="selectedTasks" value="translate"> 使用原文 (基於逐字稿)</label>
              <label><input type="checkbox" v-model="selectedTasks" value="translate_zh"> 翻譯成繁體中文 (基於逐字稿)</label>
            </div>
          </div>
          <!-- 右側：模型與格式 -->
          <div class="flex-col">
            <div>
              <label for="gemini-model-select"><strong>AI 模型</strong></label>
              <select id="gemini-model-select" v-model="selectedModel">
                <option v-if="models.length === 0">提供有效金鑰後將載入模型</option>
                <option v-for="model in models" :key="model.id" :value="model.id">{{ model.name }}</option>
              </select>
            </div>
            <div>
              <label for="yt-output-format-select"><strong>輸出格式</strong></label>
              <select id="yt-output-format-select" v-model="outputFormat">
                <option value="html">HTML 報告</option>
                <option value="txt">純文字 (.txt)</option>
              </select>
            </div>
          </div>
        </div>
      </fieldset>
    </div>

    <!-- 操作按鈕 -->
    <div style="text-align: center; margin-top: 24px; display: flex; justify-content: center; gap: 15px; flex-wrap: wrap;">
      <button id="download-audio-only-btn" @click="processRequest(true)" :disabled="!youtubeLinks[0].url || !featureStore.isYtdlpReady">{{ downloadButtonText }}</button>
      <button id="analyze-video-btn" @click="processRequest(false)" :disabled="!isApiKeyValid || !youtubeLinks[0].url || !featureStore.isYtdlpReady || !featureStore.isWhisperReady">{{ analyzeButtonText }}</button>
    </div>

    <!-- 報告瀏覽區 -->
    <YouTubeReportBrowser />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue';
import { useTasksStore } from '@/stores/tasks';
import { useFeatureStore } from '@/stores/features';
import { logAction } from '@/utils/logging';
import YouTubeReportBrowser from './YouTubeReportBrowser.vue';

const tasksStore = useTasksStore();
const featureStore = useFeatureStore();

// 組件狀態
const apiKey = ref('');
const apiKeyStatus = reactive({ text: '尚未提供金鑰', color: 'inherit', italic: true });
const isApiKeyValid = ref(false);
const youtubeLinks = ref([{ url: '', filename: '' }]);
const selectedTasks = ref(['summary', 'transcript']);
const models = ref([]);
const selectedModel = ref('');
const outputFormat = ref('html');

// --- 計算屬性 ---
const downloadButtonText = computed(() => {
  if (!featureStore.isYtdlpReady) return '🔄 下載功能初始化中...';
  return '🎧 僅下載音訊';
});

const analyzeButtonText = computed(() => {
  if (!featureStore.isYtdlpReady) return '🔄 下載功能初始化中...';
  if (!featureStore.isWhisperReady) return '🔄 轉錄功能初始化中...';
  return '🚀 分析影片 (Gemini)';
});

// --- API 金鑰管理 ---
const fetchModels = async () => {
  try {
    models.value = await tasksStore.fetchGeminiModels(apiKey.value);
    if (models.value.length > 0) {
      selectedModel.value = models.value[0].id;
    }
  } catch (error) {
    apiKeyStatus.text = `無法載入模型: ${error.message}`;
    apiKeyStatus.color = '#dc3545';
    apiKeyStatus.italic = false;
  }
};

const saveAndValidateApiKey = async () => {
  logAction('click-save-api-key');
  if (!apiKey.value) {
    alert('API 金鑰不能為空');
    return;
  }
  localStorage.setItem('googleApiKey', apiKey.value);
  apiKeyStatus.text = '正在驗證中...';
  apiKeyStatus.italic = true;

  const result = await tasksStore.validateApiKey(apiKey.value);
  isApiKeyValid.value = result.valid;
  if (result.valid) {
    apiKeyStatus.text = '金鑰有效，Gemini 功能已啟用';
    apiKeyStatus.color = 'var(--status-green)';
    apiKeyStatus.italic = false;
    await fetchModels();
  } else {
    apiKeyStatus.text = result.detail || '金鑰無效';
    apiKeyStatus.color = '#dc3545';
    apiKeyStatus.italic = false;
  }
};

const clearApiKey = () => {
  logAction('click-clear-api-key');
  apiKey.value = '';
  localStorage.removeItem('googleApiKey');
  isApiKeyValid.value = false;
  apiKeyStatus.text = '尚未提供金鑰';
  apiKeyStatus.color = 'inherit';
  apiKeyStatus.italic = true;
  models.value = [];
};

// --- YouTube 連結管理 ---
const addYoutubeRow = () => {
  logAction('click-add-youtube-row');
  youtubeLinks.value.push({ url: '', filename: '' });
};

const removeYoutubeRow = (index) => {
  logAction('click-remove-youtube-row');
  if (youtubeLinks.value.length > 1) {
    youtubeLinks.value.splice(index, 1);
  }
};

// --- 處理請求 ---
const processRequest = async (downloadOnly = false) => {
  const action = downloadOnly ? 'click-download-audio-only' : 'click-start-youtube-processing';
  logAction(action);

  const requests = youtubeLinks.value.filter(link => link.url.trim() !== '').map(link => ({
    url: link.url,
    filename: link.filename.trim()
  }));
  if (requests.length === 0) {
    alert('請至少輸入一個有效的 YouTube 網址。');
    return;
  }
  if (!downloadOnly && selectedTasks.value.length === 0) {
    alert('請至少選擇一個 AI 分析任務。');
    return;
  }

  const payload = {
    requests: requests,
    model: selectedModel.value,
    download_only: downloadOnly,
    tasks: selectedTasks.value.join(','),
    output_format: outputFormat.value,
    api_key: apiKey.value
  };

  try {
    await tasksStore.processYoutubeRequest(payload);
    youtubeLinks.value = [{ url: '', filename: '' }]; // 清空輸入
    alert('YouTube 處理任務已成功建立！');
  } catch (error) {
    alert(`建立任務失敗: ${error.message}`);
  }
};

// --- 元件初始化 ---
onMounted(() => {
  const storedApiKey = localStorage.getItem('googleApiKey');
  if (storedApiKey) {
    apiKey.value = storedApiKey;
    saveAndValidateApiKey();
  }
});
</script>

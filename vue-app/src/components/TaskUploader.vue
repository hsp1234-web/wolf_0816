<template>
  <div id="local-file-tab" class="tab-content active">
    <div class="grid-2-col">
      <div class="card flex-col">
        <h2>⚙️ 步驟 1: 選項 (Whisper 模型)</h2>
        <div>
          <label for="model-select">模型大小</label>
          <select id="model-select" v-model="model">
            <option value="tiny">Tiny (最快)</option>
            <option value="base">Base</option>
            <option value="small">Small</option>
            <option value="medium">Medium (建議)</option>
            <option value="large-v2">Large-v2 (準確)</option>
            <option value="large-v3">Large-v3 (最準確)</option>
          </select>
        </div>
        <button
          @click="confirmAndDownloadModel"
          :disabled="localModels.checking || isModelAvailable"
          style="margin-top: 10px;"
        >
          {{ downloadButtonText }}
        </button>
        <div>
          <label for="language-select">轉錄語言</label>
          <select id="language-select" v-model="language">
            <option value="zh">繁體中文</option>
            <option value="en">英文</option>
          </select>
        </div>
        <div>
          <label for="beam-size-input" style="display: block; margin-bottom: 4px;">光束大小 (Beam Size)</label>
          <input type="number" id="beam-size-input" v-model.number="beamSize" min="1" max="10" style="width: 100%; padding: 10px; border-radius: 6px; border: 1px solid #ccc; box-sizing: border-box;">
          <small style="font-size: 0.8em; color: #666;">建議值為 5。較大的值可能更準確但較慢。</small>
        </div>
        <!-- JULES'S FIX: 模型下載進度條邏輯，現在是自動觸發，無需手動確認 -->
        <div v-if="modelDownloadStatus.status !== 'idle' && modelDownloadStatus.status !== 'completed'" class="progress-container" style="margin-top: 10px;">
          <div
            class="progress-bar"
            :style="{ width: modelDownloadStatus.progress + '%', backgroundColor: modelDownloadStatus.status === 'failed' ? '#dc3545' : '' }"
          ></div>
          <span class="progress-text">{{ modelDownloadStatus.message }}</span>
        </div>
        <div v-else-if="modelDownloadStatus.status === 'completed'" class="progress-container" style="margin-top: 10px;">
            <div class="progress-bar" style="width: 100%; background-color: var(--success-color);"></div>
            <span class="progress-text">{{ modelDownloadStatus.message }}</span>
        </div>
      </div>
      <div class="card flex-col">
        <h2>📤 步驟 2: 上傳檔案</h2>
        <label
          for="file-input-trigger"
          class="file-drop-zone"
          @dragover="onDragOver"
          @drop="onDrop"
        >
          點擊此處選擇檔案，或將檔案拖曳至此
        </label>
        <input
          id="file-input-trigger"
          ref="fileInput"
          type="file"
          multiple
          class="hidden"
          @change="handleFileSelect"
        >
        <div id="file-list">
          <div v-if="uploadedFiles.length === 0" style="color: #666; text-align: center;">尚未選擇任何檔案</div>
          <div v-else v-for="(file, index) in uploadedFiles" :key="file.name" class="task-item">
            <span class="task-filename">{{ file.name }}</span>
            <button @click="removeFile(index)" class="remove-file-btn" style="background-color: #dc3545; padding: 3px 8px; font-size: 0.8em;">移除</button>
          </div>
        </div>
      </div>
    </div>
    <div style="text-align: center; margin-top: 24px;">
      <button
        id="start-processing-btn"
        :disabled="uploadedFiles.length === 0 || !isModelAvailable"
        @click="startProcessing"
        :title="!isModelAvailable ? '請先下載或確認所選模型' : ''"
      >
        {{ uploadedFiles.length > 0 ? `✨ 開始處理 ${uploadedFiles.length} 個檔案` : '✨ 請先選擇檔案' }}
      </button>
      <!-- TODO: 上傳進度條邏輯 -->
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useTasksStore } from '@/stores/tasks'
import { useNotificationStore } from '@/stores/notifications'
import { logAction } from '@/utils/logging'
import eventBus from '@/utils/eventBus'

const tasksStore = useTasksStore()
const notificationStore = useNotificationStore()

// 從 store 獲取狀態
const modelDownloadStatus = computed(() => tasksStore.modelDownloadStatus)
const localModels = computed(() => tasksStore.localModels)

// --- 組件本地狀態 ---
const model = ref('tiny')
const language = ref('zh')
const beamSize = ref(1)
const uploadedFiles = ref([])
const fileInput = ref(null)

// --- 計算屬性 (Computed Properties) ---
const isModelAvailable = computed(() => {
  return localModels.value.available.includes(model.value)
})

const downloadButtonText = computed(() => {
  if (localModels.value.checking) return '正在檢查模型...'
  if (isModelAvailable.value) return '✅ 模型已就緒'
  return '📥 下載模型'
})

// --- 按鈕事件處理 ---
const confirmAndDownloadModel = async () => {
  logAction('click-download-whisper-model', model.value);
  try {
    await tasksStore.downloadModel(model.value);
  } catch (error) {
    notificationStore.addNotification(`下載模型 ${model.value} 失敗`, 'error');
  }
};

// --- 檔案處理方法 ---
const handleFileSelect = (event) => {
  const newFiles = Array.from(event.target.files)
  addFiles(newFiles)
}

const addFiles = (files) => {
  files.forEach(file => {
    if (!uploadedFiles.value.some(f => f.name === file.name)) {
      uploadedFiles.value.push(file)
    }
  })
}

const removeFile = (index) => {
  uploadedFiles.value.splice(index, 1)
}

// --- 拖放處理 ---
const onDragOver = (event) => {
  event.preventDefault()
}

const onDrop = (event) => {
  event.preventDefault()
  const droppedFiles = Array.from(event.dataTransfer.files)
  addFiles(droppedFiles)
}

// --- 事件總線監聽 ---
const handleIncomingFile = (file) => {
  if (file instanceof File) {
    addFiles([file]);
    notificationStore.addNotification(`檔案 "${file.name}" 已成功載入至轉錄區！`, 'success');
  }
}

onMounted(() => {
  tasksStore.fetchLocalModels();
  eventBus.on('send-file-to-uploader', handleIncomingFile)
})

onUnmounted(() => {
  eventBus.off('send-file-to-uploader', handleIncomingFile)
})


// --- 按鈕事件處理 ---
const startProcessing = async () => {
  if (uploadedFiles.value.length === 0) return
  logAction('click-start-processing', `files_count: ${uploadedFiles.value.length}`)

  for (const file of uploadedFiles.value) {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('model_size', model.value)
    formData.append('language', language.value)
    formData.append('beam_size', beamSize.value)

    try {
      // 呼叫 store action 來處理上傳和任務建立
      await tasksStore.startTranscription(formData)
    } catch (error) {
      // 可以在此處顯示錯誤訊息給使用者
      console.error(`處理檔案 ${file.name} 時失敗:`, error)
    }
  }

  // 處理完畢後清空已上傳檔案列表
  uploadedFiles.value = []
}
</script>

<style scoped>
/* 此元件的專屬樣式 */
</style>

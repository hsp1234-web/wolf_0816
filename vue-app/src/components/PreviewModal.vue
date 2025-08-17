<template>
  <div v-if="show" class="modal-overlay" @click.self="close">
    <div class="modal-content">
      <div class="modal-header">
        <h2 id="modal-title">預覽: {{ filename }}</h2>
        <button @click="close" class="modal-close-button">&times;</button>
      </div>
      <div class="modal-body">
        <!-- Content will be dynamically generated based on file type -->
        <template v-if="fileType === 'html'">
          <iframe :src="previewUrl" style="width: 100%; height: 75vh; border: none;"></iframe>
        </template>
        <template v-else-if="fileType === 'text'">
          <pre style="white-space: pre-wrap; word-wrap: break-word;">{{ textContent }}</pre>
        </template>
        <template v-else-if="fileType === 'audio'">
          <audio :src="previewUrl" controls autoplay style="width: 100%;"></audio>
        </template>
        <template v-else-if="fileType === 'video'">
          <video :src="previewUrl" controls autoplay style="width: 100%; max-height: 75vh;"></video>
        </template>
        <template v-else>
          <p>此檔案類型 ({{ fileType }}) 無法預覽。</p>
        </template>
      </div>
      <div class="modal-footer">
        <a :href="downloadUrl" :download="filename" class="button-like">下載檔案</a>
        <button @click="close">關閉</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import axios from 'axios'

const props = defineProps({
  task: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['close'])

const show = ref(false)
const textContent = ref('')

const previewUrl = computed(() => {
  if (!props.task || !props.task.result || !props.task.result.output_path) return null
  return props.task.result.output_path
})

const downloadUrl = computed(() => {
    if (!props.task) return '#'
    return `/api/download/${props.task.task_id}`
})

const filename = computed(() => {
    if (!props.task) return ''
    // Try to get filename from different possible locations
    return props.task.payload?.original_filename || props.task.result?.video_title || props.task.result?.original_filename || 'file'
})

const fileType = computed(() => {
  if (!previewUrl.value) return 'unknown'
  const path = previewUrl.value
  if (path.endsWith('.html')) return 'html'
  if (path.endsWith('.txt')) return 'text'
  if (['.mp3', '.wav', '.m4a', '.flac'].some(ext => path.endsWith(ext))) return 'audio'
  if (['.mp4', '.mov', '.webm'].some(ext => path.endsWith(ext))) return 'video'
  return 'unknown'
})

const fetchTextContent = async () => {
  if (fileType.value === 'text' && previewUrl.value) {
    try {
      textContent.value = '正在載入預覽...'
      const response = await axios.get(previewUrl.value)
      textContent.value = response.data
    } catch (error) {
      console.error('無法獲取文字內容:', error)
      textContent.value = '預覽載入失敗。'
    }
  }
}

watch(() => props.task, (newTask) => {
  if (newTask) {
    show.value = true
    fetchTextContent()
  } else {
    show.value = false
  }
})

const close = () => {
  emit('close')
}
</script>

<style scoped>
/* Scoped styles can be added here if needed, but global styles from main.css will apply */
.modal-footer button {
    background-color: #6c757d;
}
</style>

<template>
  <div>
    <div class="card">
      <h2>📥 媒體下載器</h2>
      <div class="grid-2-col">
        <!-- 左側：輸入與主要控制 -->
        <div class="flex-col">
          <div>
            <label for="downloader-urls-input"><strong>網址或播放清單</strong> (可輸入多個，每行一個)</label>
            <textarea
              id="downloader-urls-input"
              v-model="urls"
              rows="5"
              placeholder="支援 YouTube, Facebook, Bilibili 等多數影音網站..."
              style="width: 100%; padding: 10px; border-radius: 6px; border: 1px solid #ccc; box-sizing: border-box; font-family: inherit;"
            ></textarea>
          </div>
          <div style="text-align: center; margin-top: 16px;">
            <button @click="startDownload" style="width: 100%; padding: 12px; font-size: 1.1em;">開始下載</button>
          </div>
        </div>
        <!-- 右側：詳細選項 -->
        <div class="flex-col">
          <div>
            <label><strong>下載類型</strong></label>
            <div style="display: flex; gap: 20px; margin-top: 8px;">
              <label><input type="radio" name="download-type" value="audio" v-model="downloadType"> 純音訊</label>
              <label><input type="radio" name="download-type" value="video" v-model="downloadType"> 影片</label>
            </div>
          </div>

          <!-- 音訊選項 -->
          <div v-show="downloadType === 'audio'">
            <label for="audio-format-select"><strong>音訊格式</strong></label>
            <select id="audio-format-select">
              <option value="m4a">M4A (原生格式, 速度最快)</option>
              <option value="mp3">MP3 (需轉檔, 相容性高)</option>
              <option value="wav">WAV (需轉檔, 無損)</option>
              <option value="flac">FLAC (需轉檔, 無損壓縮)</option>
            </select>
          </div>

          <!-- 影片選項 -->
          <div v-show="downloadType === 'video'">
            <label for="video-quality-select"><strong>影片畫質</strong></label>
            <select id="video-quality-select">
              <option value="best">最佳畫質</option>
              <option value="1080p">1080p</option>
              <option value="720p">720p (HD)</option>
              <option value="480p">480p (SD)</option>
            </select>
          </div>
        </div>
      </div>
    </div>

    <!-- 下載列表 (待辦) -->
    <div class="card" style="margin-top: 24px;">
      <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px;">
        <h2>📋 下載佇列與歷史紀錄</h2>
        <button disabled style="background-color: #28a745;">打包下載選定項目 (.zip)</button>
      </div>
      <div class="task-list" style="margin-top: 16px;">
        <p>下載佇列功能正在開發中...</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useTasksStore } from '@/stores/tasks'
import { logAction } from '@/utils/logging'

const tasksStore = useTasksStore()
const urls = ref('')
const downloadType = ref('audio')

const startDownload = async () => {
  const urlList = urls.value.split('\n').map(u => u.trim()).filter(u => u)
  if (urlList.length === 0) {
    alert('請輸入至少一個有效的網址。')
    return
  }
  logAction('click-start-download', `urls_count: ${urlList.length}`)

  try {
    await tasksStore.startDownload({
      urls: urlList,
      downloadType: downloadType.value
    })
    urls.value = ''
    // 可以加入成功提示
    alert('下載任務已成功建立！')
  } catch (error) {
    alert(`建立下載任務失敗: ${error.message}`)
  }
}
</script>

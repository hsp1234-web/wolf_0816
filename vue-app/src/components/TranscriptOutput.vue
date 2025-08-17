<template>
  <div class="card">
    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
      <h2>📝 即時轉錄輸出</h2>
      <div class="toggle-switch-container" style="display: flex; align-items: center; gap: 8px;">
        <label for="timestamp-toggle" style="font-weight: 500; font-size: 0.9em; cursor: pointer;">顯示時間戳記</label>
        <input type="checkbox" id="timestamp-toggle" checked>
      </div>
    </div>
    <div class="transcript-output" style="margin-top: 16px;">
      <p>即時轉錄輸出功能正在開發中...</p>
      <p>完成的轉錄稿將會顯示在這裡。</p>
    </div>
  </div>
</template>

<script setup>
// This component will later display the real-time transcription text from WebSocket messages.
</script>

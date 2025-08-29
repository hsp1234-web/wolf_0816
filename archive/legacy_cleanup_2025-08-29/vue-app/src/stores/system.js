import { defineStore } from 'pinia';
import axios from 'axios';

export const useSystemStore = defineStore('system', {
  state: () => ({
    // 初始狀態，預設所有功能都未就緒，並提供提示訊息。
    features: {
      transcription: {
        enabled: false,
        message: '正在從後端獲取狀態...'
      },
      youtube_processing: {
        enabled: false,
        message: '正在從後端獲取狀態...'
      },
      model_management: {
        enabled: false,
        message: '正在從後端獲取狀態...'
      }
    },
    app_version: null,
    error: null,
  }),

  actions: {
    /**
     * 從後端 API 獲取最新的功能狀態，並更新 store。
     */
    async fetchFeatureStatus() {
      try {
        const response = await axios.get('/api/v1/status');
        const data = response.data;

        // 使用 $patch 來進行高效的批次更新
        this.$patch({
          features: data.features,
          app_version: data.app_version,
          error: null,
        });

      } catch (error) {
        console.error('獲取應用程式功能狀態時發生錯誤:', error);
        this.error = '無法從後端獲取功能狀態，某些功能可能無法使用。';
        // 在出錯時，保持所有功能為禁用狀態，但更新提示訊息
        this.$patch({
            features: {
                transcription: { enabled: false, message: this.error },
                youtube_processing: { enabled: false, message: this.error },
                model_management: { enabled: false, message: this.error },
            }
        })
      }
    },
  },
});

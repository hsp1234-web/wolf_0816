import './assets/main.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { logClickEvent } from './utils/logging'

import App from './App.vue'

const app = createApp(App)

app.use(createPinia())

// 在測試環境中暴露 app 實例，以便 Playwright 可以存取
window.vue_app = app;

app.mount('#app')

// 註冊全域點擊事件監聽器
document.addEventListener('click', logClickEvent, true);

import './assets/main.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { logClickEvent } from './utils/logging'

import App from './App.vue'

const app = createApp(App)

app.use(createPinia())

app.mount('#app')

// 註冊全域點擊事件監聽器
document.addEventListener('click', logClickEvent, true);

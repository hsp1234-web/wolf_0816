import './assets/main.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { logClickEvent } from './utils/logging'

import App from './App.vue'

const app = createApp(App)

const pinia = createPinia();
app.use(pinia);

// 在測試環境中暴露 app 和 store 實例，以便 Playwright 可以存取
window.vue_app = app;

import { useTasksStore } from './stores/tasks';
// 讓測試可以直接存取 store
window.tasksStore = useTasksStore(pinia);

app.mount('#app')

// 註冊全域點擊事件監聽器
document.addEventListener('click', logClickEvent, true);

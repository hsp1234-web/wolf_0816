/**
 * eventBus.js
 * 一個簡單的事件總線 (Event Bus) 實作，用於 Vue 3 跨元件通訊。
 * 這在元件之間沒有直接父子關係時特別有用。
 *
 * 使用 mitt 套件，它是一個輕量級且功能強大的事件發射器。
 */
import mitt from 'mitt';

// 匯出一個 mitt 的實例，使其在整個應用程式中作為單例使用。
const emitter = mitt();

export default emitter;

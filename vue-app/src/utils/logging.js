import axios from 'axios';

/**
 * 向後端發送一個操作日誌。
 * 這是一個 "fire and forget" 的請求，我們不會等待它的回應。
 * @param {string} action - 描述使用者操作的字串。
 * @param {any} [value=null] - (可選) 與操作相關的數值。
 */
export function logAction(action, value = null) {
  const message = value !== null ? `${action}: ${value}` : action;
  console.log(`Logging action: ${message}`);

  axios.post('/api/log/action', {
    action: message
  }).catch(err => {
    // 在開發模式下，如果後端沒有運行，這個錯誤是預期的。
    // 我們不在控制台中顯示它，以避免混淆。
    // console.error('logAction failed:', err);
  });
}

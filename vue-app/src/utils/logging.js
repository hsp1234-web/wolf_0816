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

  /*
  // 暫時停用此功能，因為後端 API 端點 (/api/log/action) 尚未實作
  axios.post('/api/log/action', {
    action: message
  }).catch(err => {
    // 在開發模式下，如果後端沒有運行，這個錯誤是預期的。
    // 我們不在控制台中顯示它，以避免混淆。
    // console.error('logAction failed:', err);
  });
  */
}

/**
 * 記錄一個全域點擊事件。
 * @param {MouseEvent} event - 瀏覽器觸發的點擊事件。
 */
export function logClickEvent(event) {
  const element = event.target;
  let identifier = '';

  // 依序嘗試尋找最有意義的識別碼
  if (element.dataset.testid) {
    identifier = `testid=${element.dataset.testid}`;
  } else if (element.id) {
    identifier = `id=${element.id}`;
  } else if (element.className) {
    identifier = `class=${element.className}`;
  } else {
    identifier = `tag=${element.tagName.toLowerCase()}`;
  }

  const description = `${element.tagName.toLowerCase()} with ${identifier}`;
  logAction('click-event', description);
}

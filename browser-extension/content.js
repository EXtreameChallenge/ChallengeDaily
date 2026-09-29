/* ChallengeDaily Web Tracker — Content Script
 *
 * 页面可见性检测：
 *  - 监听 visibilitychange 事件
 *  - 页面隐藏时通知 background.js 结束当前计时
 *  - 页面可见时通知 background.js 开始新计时
 *
 * 仅在 http/https 页面注入（见 manifest content_scripts.matches）。
 * 不收集任何页面内容，仅上报可见性状态变化。
 */
(function () {
  // 避免在 about:blank / 空白框架内重复注入导致噪声
  if (window.top !== window.self && document.visibilityState === 'hidden') {
    return;
  }

  let lastState = document.visibilityState;

  function report(visible) {
    try {
      chrome.runtime.sendMessage({ type: 'VISIBILITY', visible: visible }, () => {
        // 吞掉 runtime.lastError（例如 SW 未就绪），避免控制台噪声
        if (chrome.runtime.lastError) {
          /* 忽略：扩展刚安装/更新时 SW 可能尚未注册 */
        }
      });
    } catch (e) {
      // 扩展上下文失效等情况，静默忽略
    }
  }

  document.addEventListener('visibilitychange', () => {
    const state = document.visibilityState;
    if (state === lastState) return;
    lastState = state;
    // hidden: 页面被切到后台 / 最小化 / 切到其他标签 → 结束计时
    // visible: 页面重新可见 → 开始新计时
    report(state === 'visible');
  });

  // 页面卸载时也结束计时（关闭标签 / 导航离开）
  window.addEventListener('pagehide', () => {
    report(false);
  });
})();

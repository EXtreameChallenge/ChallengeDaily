/**
 * 幕布同步窗口的 preload
 * ========================
 * 极简 preload，不需要暴露任何 API 给渲染进程。
 * 同步窗口是隐藏的，所有操作都通过 webContents.executeJavaScript() 完成。
 * 
 * 这里只设置一些基础安全策略。
 */
// contextIsolation: true 时，这个脚本的上下文是隔离的
// 不需要做任何事，只需要存在，避免 BrowserWindow 创建时报错
window.__MUBU_SYNC__ = true

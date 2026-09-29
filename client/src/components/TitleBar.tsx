/**
 * WindowControls — Mac 风格毛玻璃胶囊窗口控件
 * 顺序（左→右）：最小化 — / 最大化 □ / 关闭 ×
 * 符号常显，hover 时底色微亮，圆圈不变灰
 */
export default function TitleBar() {
  return (
    <div className="titlebar fixed top-5 right-3 z-50 no-drag">
      <div className="win-controls">
        <button
          className="win-minimize"
          onClick={() => window.electronAPI?.minimize()}
          title="最小化"
        >
          <svg viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.4">
            <line x1="1" y1="5" x2="9" y2="5" />
          </svg>
        </button>
        <button
          className="win-maximize"
          onClick={() => window.electronAPI?.maximize()}
          title="最大化"
        >
          <svg viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.2">
            <rect x="1" y="1" width="8" height="8" rx="1" />
          </svg>
        </button>
        <button
          className="win-close"
          onClick={() => window.electronAPI?.close()}
          title="关闭"
        >
          <svg viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.4">
            <line x1="1" y1="1" x2="9" y2="9" /><line x1="9" y1="1" x2="1" y2="9" />
          </svg>
        </button>
      </div>
    </div>
  )
}

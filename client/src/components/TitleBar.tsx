export default function TitleBar() {
  return (
    <div className="titlebar h-9 flex items-center justify-between bg-cd-bg border-b border-cd-border px-4 shrink-0">
      <div className="flex items-center gap-2">
        <span className="text-sm font-bold text-cd-green font-brand">ChallengeDaily</span>
        <span className="text-xs text-cd-text-tertiary">AI 智能工作日报助手</span>
      </div>
      <div className="flex items-center gap-0.5">
        <button
          onClick={() => window.electronAPI?.minimize()}
          className="w-8 h-6 flex items-center justify-center rounded hover:bg-cd-hover text-cd-text-tertiary transition-colors"
        >
          <svg width="10" height="1" viewBox="0 0 10 1"><rect width="10" height="1" fill="currentColor"/></svg>
        </button>
        <button
          onClick={() => window.electronAPI?.maximize()}
          className="w-8 h-6 flex items-center justify-center rounded hover:bg-cd-hover text-cd-text-tertiary transition-colors"
        >
          <svg width="9" height="9" viewBox="0 0 9 9" fill="none" stroke="currentColor" strokeWidth="1.2">
            <rect x="0.6" y="0.6" width="7.8" height="7.8" rx="1"/>
          </svg>
        </button>
        <button
          onClick={() => window.electronAPI?.close()}
          className="w-8 h-6 flex items-center justify-center rounded hover:bg-cd-red hover:text-white text-cd-text-tertiary transition-colors"
        >
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.4">
            <line x1="1" y1="1" x2="9" y2="9"/><line x1="9" y1="1" x2="1" y2="9"/>
          </svg>
        </button>
      </div>
    </div>
  )
}

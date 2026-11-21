import { ChevronLeft, ChevronRight, Search, LayoutGrid, List, RefreshCw } from 'lucide-react'
import { useState, useEffect } from 'react'

/**
 * TopBar — 悬浮玻璃胶囊按钮区（position: fixed）
 * 所有按钮高度统一为 40px，与底部 AI 输入框一致
 */
export default function TopBar() {
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')
  const [currentPath, setCurrentPath] = useState(() => window.location.hash.replace('#', '') || '/')

  useEffect(() => {
    const onHashChange = () => setCurrentPath(window.location.hash.replace('#', '') || '/')
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  const goBack = () => window.history.back()
  const goForward = () => window.history.forward()

  const showViewToggle = ['/dashboard', '/todos', '/apps', '/timeline'].some(p => currentPath.startsWith(p))

  return (
    <div
      className="titlebar fixed top-0 left-[248px] right-0 z-40 flex h-16 items-center gap-3 select-none pt-3 pr-4"
      onDoubleClick={(e) => {
        // 双击空白拖拽区 = 最大化/还原；交互控件不触发
        if ((e.target as HTMLElement).closest('.no-drag')) return
        window.electronAPI?.maximize()
      }}
    >
      {/* 顶栏只做渐隐遮罩：顶部实、向下化开，不画实色横带和硬边 */}
      <div
        className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-16"
        style={{
          background:
            'linear-gradient(to bottom, var(--cd-bg) 0%, var(--cd-bg) 30%, transparent 100%)',
        }}
        aria-hidden="true"
      />
      {/* 后退/前进（一组玻璃胶囊） */}
      <div className="no-drag glass-pill flex items-center p-1 h-10">
        <button
          onClick={goBack}
          className="w-8 h-8 rounded-full hover:bg-white/10 dark:hover:bg-white/10 flex items-center justify-center text-cd-text-secondary transition-colors"
          title="后退"
        >
          <ChevronLeft size={16} />
        </button>
        <button
          onClick={goForward}
          className="w-8 h-8 rounded-full hover:bg-white/10 dark:hover:bg-white/10 flex items-center justify-center text-cd-text-secondary transition-colors"
          title="前进"
        >
          <ChevronRight size={16} />
        </button>
      </div>

      {/* 搜索框（独立玻璃胶囊） */}
      <div className="no-drag glass-pill topbar-search flex items-center gap-2 px-3 h-10 min-h-10 max-h-10 w-52 transition-all">
        <Search size={15} className="text-cd-text-tertiary shrink-0" />
        <input
          type="text"
          aria-label="搜索任务、笔记"
          placeholder="搜索任务、笔记…"
          className="min-w-0 w-full bg-transparent outline-none text-sm flex-1 text-cd-text placeholder:text-cd-text-tertiary truncate"
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              window.dispatchEvent(new CustomEvent('open-command-palette'))
            }
          }}
        />
      </div>

      {/* 刷新 + 视图切换（数据页显示） */}
      {showViewToggle && (
        <>
          <button
            onClick={() => window.location.reload()}
            className="glass-pill w-10 h-10 flex items-center justify-center text-cd-text-secondary hover:text-cd-text transition-colors"
            title="刷新数据"
          >
            <RefreshCw size={15} />
          </button>
          <div className="no-drag glass-pill flex items-center p-1 h-10">
            <button
              onClick={() => setViewMode('grid')}
              className={`w-8 h-8 rounded-full flex items-center justify-center transition-colors ${
                viewMode === 'grid' ? 'bg-cd-accent/20 text-cd-accent' : 'text-cd-text-secondary hover:text-cd-text'
              }`}
              title="卡片视图"
            >
              <LayoutGrid size={15} />
            </button>
            <button
              onClick={() => setViewMode('list')}
              className={`w-8 h-8 rounded-full flex items-center justify-center transition-colors ${
                viewMode === 'list' ? 'bg-cd-accent/20 text-cd-accent' : 'text-cd-text-secondary hover:text-cd-text'
              }`}
              title="列表视图"
            >
              <List size={15} />
            </button>
          </div>
        </>
      )}

      {/* 空白拖拽区：填满到窗口控制按钮左侧 */}
      <div className="flex-1 h-10" aria-hidden="true" />
    </div>
  )
}

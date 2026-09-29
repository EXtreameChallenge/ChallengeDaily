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
    <div className="fixed top-3 left-[248px] z-40 flex items-center gap-2 no-drag">
      {/* 后退/前进（一组玻璃胶囊） */}
      <div className="glass-pill flex items-center p-1 h-10">
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
      <div className="glass-pill topbar-search flex items-center gap-2 px-3 h-10 w-56 transition-all">
        <Search size={15} className="text-cd-text-tertiary shrink-0" />
        <input
          type="text"
          placeholder="搜索任务、笔记…"
          className="bg-transparent outline-none text-sm flex-1 text-cd-text placeholder:text-cd-text-tertiary"
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
          <div className="glass-pill flex items-center p-1 h-10">
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
    </div>
  )
}

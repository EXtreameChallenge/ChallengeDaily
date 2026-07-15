import { useEffect } from 'react'
import { X, Command, Keyboard } from 'lucide-react'

const SHORTCUT_GROUPS = [
  {
    title: '全局',
    shortcuts: [
      { keys: ['Ctrl', 'K'], desc: '打开命令面板' },
      { keys: ['?'], desc: '显示快捷键帮助' },
      { keys: ['Esc'], desc: '关闭弹窗/面板' },
    ],
  },
  {
    title: '导航',
    shortcuts: [
      { keys: ['↑', '↓'], desc: '命令面板中选择' },
      { keys: ['Enter'], desc: '命令面板中跳转' },
    ],
  },
  {
    title: '番茄钟',
    shortcuts: [
      { keys: ['Space'], desc: '开始/暂停番茄钟（专注页面）' },
      { keys: ['S'], desc: '跳过当前阶段' },
    ],
  },
  {
    title: '日记',
    shortcuts: [
      { keys: ['Ctrl', 'S'], desc: '保存日记' },
      { keys: ['Ctrl', '←'], desc: '前一天' },
      { keys: ['Ctrl', '→'], desc: '后一天' },
    ],
  },
]

export function ShortcutHelp({ open, onClose }: { open: boolean; onClose: () => void }) {
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg mx-4 bg-cd-bg-card rounded-xl border border-cd-border shadow-2xl overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        {/* 标题 */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-cd-border">
          <div className="flex items-center gap-2">
            <Keyboard size={18} className="text-cd-accent" />
            <h2 className="text-sm font-semibold text-cd-text">键盘快捷键</h2>
          </div>
          <button onClick={onClose} className="text-cd-text-tertiary hover:text-cd-text transition">
            <X size={18} />
          </button>
        </div>

        {/* 快捷键列表 */}
        <div className="p-5 space-y-5 max-h-[60vh] overflow-y-auto">
          {SHORTCUT_GROUPS.map(group => (
            <div key={group.title}>
              <h3 className="text-[10px] font-medium text-cd-text-tertiary uppercase tracking-wider mb-2">
                {group.title}
              </h3>
              <div className="space-y-1.5">
                {group.shortcuts.map((sc, i) => (
                  <div key={i} className="flex items-center justify-between py-1">
                    <span className="text-xs text-cd-text-secondary">{sc.desc}</span>
                    <div className="flex items-center gap-1">
                      {sc.keys.map((key, j) => (
                        <kbd key={j}
                          className="min-w-[24px] text-center text-[10px] font-medium text-cd-text bg-cd-bg-secondary px-1.5 py-0.5 rounded border border-cd-border">
                          {key}
                        </kbd>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* 底部 */}
        <div className="px-5 py-3 border-t border-cd-border flex items-center gap-2 text-[10px] text-cd-text-tertiary">
          <Command size={12} />
          <span>按 ? 随时查看 · 按 Esc 关闭</span>
        </div>
      </div>
    </div>
  )
}

/** 全局 ? 键唤起快捷键帮助 */
export function useShortcutHelpShortcut(onOpen: () => void) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // 仅在非输入框聚焦时触发
      const target = e.target as HTMLElement
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) return
      if (e.key === '?' || (e.shiftKey && e.key === '/')) {
        e.preventDefault()
        onOpen()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onOpen])
}

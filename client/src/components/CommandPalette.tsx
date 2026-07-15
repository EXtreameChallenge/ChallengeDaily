import { useState, useEffect, useRef, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Search, Home, Calendar, CheckSquare, Timer, FileText, BookOpen,
  Flame, Trophy, Target, Users, Zap, Bot, Sparkles, Brain, Clock,
  Grid3X3, AppWindow, History, Download, Activity, Settings as SettingsIcon,
  CalendarRange, CornerDownLeft, ArrowUp, ArrowDown
} from 'lucide-react'

interface Command {
  id: string
  label: string
  hint?: string
  icon: typeof Home
  action: () => void
  group: 'navigation' | 'action'
  keywords?: string[]
}

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  // 命令列表
  const commands: Command[] = useMemo(() => {
    const nav = (to: string, label: string, icon: typeof Home, hint?: string, keywords?: string[]): Command => ({
      id: `nav-${to}`,
      label,
      icon,
      hint,
      group: 'navigation',
      keywords,
      action: () => { navigate(to); onClose() },
    })
    return [
      nav('/', '今日总览', Home, '首页', ['home', 'dashboard']),
      nav('/week-plan', '周计划', Calendar, '周计划管理', ['week', 'plan']),
      nav('/todos', '待办清单', CheckSquare, '任务管理', ['todo', 'task']),
      nav('/focus', '专注番茄', Timer, '番茄钟', ['pomodoro', 'focus', '番茄']),
      nav('/goals', '长期目标', Target, '年度/季度目标', ['goal', '目标']),
      nav('/diary', '每日日记', BookOpen, '日记', ['diary', '日记']),
      nav('/habits', '习惯追踪', Flame, '打卡', ['habit', '习惯']),
      nav('/countdowns', '倒数日', Calendar, '倒计时', ['countdown']),
      nav('/achievements', '成就墙', Trophy, '成就', ['achievement']),
      nav('/study-room', '番茄自习室', Users, '局域网自习', ['study', '自习室']),
      nav('/rules-engine', '规则引擎', Zap, 'IF-THEN', ['rule', '规则']),
      nav('/report', '生成报告', FileText, '日报/周报', ['report', '日报']),
      nav('/history', '历史报告', History, '历史日报', ['history']),
      nav('/timeline', '工作时间线', Clock, '时间线', ['timeline']),
      nav('/heatmap', '时段热力图', Grid3X3, '热力图', ['heatmap']),
      nav('/calendar', '日历视图', CalendarRange, '月度日历', ['calendar', '日历']),
      nav('/apps', '应用记录', AppWindow, '应用使用', ['app']),
      nav('/dashboard', '进度仪表盘', Activity, '数据看板', ['dashboard']),
      nav('/ai-chat', 'AI 对话', Bot, 'AI助手', ['ai', 'chat']),
      nav('/ai-coach', 'AI 教练', Sparkles, '智能教练', ['coach']),
      nav('/profile', '深度画像', Brain, 'AI画像', ['profile']),
      nav('/export', '数据导出', Download, '导出', ['export']),
      nav('/health', '数据校准', Activity, '健康度', ['health']),
      nav('/settings', '设置', SettingsIcon, '应用设置', ['setting', 'config']),
    ]
  }, [navigate, onClose])

  // 过滤
  const filtered = useMemo(() => {
    if (!query.trim()) return commands
    const q = query.toLowerCase().trim()
    return commands.filter(c =>
      c.label.toLowerCase().includes(q) ||
      c.hint?.toLowerCase().includes(q) ||
      c.keywords?.some(k => k.toLowerCase().includes(q))
    )
  }, [query, commands])

  // 选中索引重置
  useEffect(() => { setSelectedIndex(0) }, [query])

  // 打开时聚焦输入框
  useEffect(() => {
    if (open) {
      setQuery('')
      setSelectedIndex(0)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [open])

  // 键盘导航
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelectedIndex(i => Math.min(i + 1, filtered.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelectedIndex(i => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      filtered[selectedIndex]?.action()
    } else if (e.key === 'Escape') {
      e.preventDefault()
      onClose()
    }
  }

  // 滚动到选中项
  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-idx="${selectedIndex}"]`)
    el?.scrollIntoView({ block: 'nearest' })
  }, [selectedIndex])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh] bg-black/40 backdrop-blur-sm"
      onClick={onClose}
      onKeyDown={handleKeyDown}
    >
      <div
        className="w-full max-w-xl mx-4 bg-cd-bg-card rounded-xl border border-cd-border shadow-2xl overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        {/* 搜索输入 */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-cd-border">
          <Search size={16} className="text-cd-text-tertiary shrink-0" />
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="搜索页面或功能... (↑↓ 选择, Enter 跳转, Esc 关闭)"
            className="flex-1 bg-transparent text-sm text-cd-text placeholder-cd-text-tertiary outline-none"
          />
          <kbd className="text-[10px] text-cd-text-tertiary bg-cd-bg-secondary px-1.5 py-0.5 rounded border border-cd-border">ESC</kbd>
        </div>

        {/* 命令列表 */}
        <div ref={listRef} className="max-h-[50vh] overflow-y-auto py-2">
          {filtered.length === 0 ? (
            <div className="text-center py-8 text-sm text-cd-text-tertiary">
              没有匹配的命令
            </div>
          ) : (
            filtered.map((cmd, idx) => {
              const Icon = cmd.icon
              const isSelected = idx === selectedIndex
              return (
                <button
                  key={cmd.id}
                  data-idx={idx}
                  onMouseEnter={() => setSelectedIndex(idx)}
                  onClick={() => cmd.action()}
                  className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors ${
                    isSelected ? 'bg-cd-accent/10' : 'hover:bg-white/5'
                  }`}
                >
                  <Icon size={15} className={isSelected ? 'text-cd-accent' : 'text-cd-text-tertiary'} />
                  <div className="flex-1 min-w-0">
                    <div className={`text-sm ${isSelected ? 'text-cd-accent font-medium' : 'text-cd-text'}`}>
                      {cmd.label}
                    </div>
                    {cmd.hint && (
                      <div className="text-[10px] text-cd-text-tertiary truncate">{cmd.hint}</div>
                    )}
                  </div>
                  {isSelected && (
                    <CornerDownLeft size={12} className="text-cd-accent shrink-0" />
                  )}
                </button>
              )
            })
          )}
        </div>

        {/* 底部提示 */}
        <div className="px-4 py-2 border-t border-cd-border flex items-center justify-between text-[10px] text-cd-text-tertiary">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1"><ArrowUp size={10} /><ArrowDown size={10} /> 选择</span>
            <span className="flex items-center gap-1"><CornerDownLeft size={10} /> 跳转</span>
          </div>
          <span>{filtered.length} 个命令</span>
        </div>
      </div>
    </div>
  )
}

/**
 * 全局键盘快捷键 Hook：Ctrl/Cmd+K 打开命令面板
 */
export function useCommandPaletteShortcut(onOpen: () => void) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        onOpen()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onOpen])
}

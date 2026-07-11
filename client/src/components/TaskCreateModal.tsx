/**
 * TaskCreateModal — 统一的任务创建弹窗
 * 待办、周计划等所有"添加"入口共用
 * 支持完整字段：预估番茄数、番茄大小、截止日期、分配日期等
 */
import { useState, useEffect, useRef } from 'react'
import { X, Timer, Target, RotateCw, ChevronDown, ChevronUp } from 'lucide-react'
import { createTodo, POMODORO_SIZES, type TaskLevel, formatLocalDate, getWeekStart } from '../api/client'

// 12种标准分类
const CATEGORIES = ['开发', '测试', '运维', '数据分析', '产品', '设计', '管理', '文档', '会议', '沟通', '学习', '生活']

type PomodoroSize = 'big' | 'small'
type TaskMode = 'timer' | 'goal' | 'habit'

interface TaskCreateModalProps {
  open: boolean
  onClose: () => void
  onCreated?: (id: number) => void
  /** 预填充的默认值 */
  defaults?: Partial<{
    title: string
    category: string
    mode: TaskMode
    priority: number
    assigned_date: string
    week_start: string
    task_level: TaskLevel
    parent_id: number
    month_key: string
  }>
}

export default function TaskCreateModal({ open, onClose, onCreated, defaults }: TaskCreateModalProps) {
  const [title, setTitle] = useState('')
  const [category, setCategory] = useState('开发')
  const [mode, setMode] = useState<TaskMode>('timer')
  const [priority, setPriority] = useState(2)
  const [estimatedPomodoros, setEstimatedPomodoros] = useState(1)
  const [pomodoroSize, setPomodoroSize] = useState<PomodoroSize>('big')
  const [dueDate, setDueDate] = useState('')
  const [assignedDate, setAssignedDate] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [saving, setSaving] = useState(false)
  const titleRef = useRef<HTMLInputElement>(null)

  // 打开时重置表单/填充默认值
  useEffect(() => {
    if (open) {
      setTitle(defaults?.title ?? '')
      setCategory(defaults?.category ?? '开发')
      setMode(defaults?.mode ?? 'timer')
      setPriority(defaults?.priority ?? 2)
      setEstimatedPomodoros(1)
      setPomodoroSize('big')
      setDueDate('')
      setAssignedDate(defaults?.assigned_date ?? formatLocalDate(new Date()))
      setShowAdvanced(false)
      setSaving(false)
      setTimeout(() => titleRef.current?.focus(), 100)
    }
  }, [open, defaults])

  if (!open) return null

  const sizeConfig = POMODORO_SIZES[pomodoroSize]
  const totalMinutes = estimatedPomodoros * sizeConfig.work
  const breakMinutes = estimatedPomodoros > 1
    ? (Math.floor((estimatedPomodoros - 1) / 4) * 15 + (estimatedPomodoros - 1 - Math.floor((estimatedPomodoros - 1) / 4) * 4) * sizeConfig.short_break)
    : 0

  const handleCreate = async () => {
    if (!title.trim() || saving) return
    setSaving(true)
    try {
      const data: Record<string, unknown> = {
        title: title.trim(),
        category,
        mode,
        target_min: estimatedPomodoros * sizeConfig.work,
        priority,
        estimated_pomodoros: estimatedPomodoros,
        pomodoro_size: pomodoroSize,
        task_level: defaults?.task_level ?? 'day',
      }
      if (dueDate) data.due_date = dueDate
      if (assignedDate) {
        data.assigned_date = assignedDate
        data.week_start = getWeekStart(new Date(assignedDate + 'T00:00:00'))
      } else if (defaults?.week_start) {
        data.week_start = defaults.week_start
      }
      if (defaults?.parent_id) data.parent_id = defaults.parent_id
      if (defaults?.month_key) data.month_key = defaults.month_key

      const res = await createTodo(data as Parameters<typeof createTodo>[0])
      onCreated?.(res.id)
      onClose()
    } catch (err) {
      console.error('创建任务失败:', err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div
        className="bg-cd-bg-card border border-white/10 rounded-2xl w-full max-w-lg shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        {/* 标题栏 */}
        <div className="flex items-center justify-between px-6 pt-5 pb-3">
          <h2 className="text-lg font-bold text-cd-text">新建任务</h2>
          <button onClick={onClose} className="text-cd-text-secondary hover:text-cd-text transition p-1">
            <X size={20} />
          </button>
        </div>

        <div className="px-6 pb-6 space-y-4 max-h-[75vh] overflow-y-auto">
          {/* 任务名称 */}
          <div>
            <label className="block text-sm text-cd-text-secondary mb-1">任务名称</label>
            <input
              ref={titleRef}
              type="text"
              value={title}
              onChange={e => setTitle(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCreate()}
              placeholder="这次要做什么？"
              className="w-full bg-cd-bg-input border border-white/5 rounded-lg px-4 py-2.5 text-cd-text placeholder:text-cd-text-secondary/50 focus:outline-none focus:border-cd-accent/40"
            />
          </div>

          {/* 模式选择 */}
          <div>
            <label className="block text-sm text-cd-text-secondary mb-1.5">模式</label>
            <div className="flex gap-2">
              {([
                { key: 'timer' as TaskMode, icon: Timer, label: '计时任务', desc: '番茄钟计时' },
                { key: 'goal' as TaskMode, icon: Target, label: '目标时长', desc: '累计到目标' },
                { key: 'habit' as TaskMode, icon: RotateCw, label: '习惯养成', desc: '每日打卡' },
              ]).map(m => (
                <button
                  key={m.key}
                  onClick={() => setMode(m.key)}
                  className={`flex-1 flex flex-col items-center gap-0.5 py-2.5 rounded-lg text-sm transition border ${
                    mode === m.key
                      ? 'bg-cd-accent/15 text-cd-accent border-cd-accent/30'
                      : 'bg-cd-bg-input text-cd-text-secondary border-white/5 hover:bg-white/5'
                  }`}
                >
                  <m.icon size={16} />
                  <span className="font-medium">{m.label}</span>
                  <span className="text-[10px] opacity-60">{m.desc}</span>
                </button>
              ))}
            </div>
          </div>

          {/* 分类 + 优先级 */}
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="block text-sm text-cd-text-secondary mb-1">分类</label>
              <select
                value={category}
                onChange={e => setCategory(e.target.value)}
                className="w-full bg-cd-bg-input border border-white/5 rounded-lg px-3 py-2.5 text-cd-text focus:outline-none focus:border-cd-accent/40"
              >
                {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="w-32">
              <label className="block text-sm text-cd-text-secondary mb-1">优先级</label>
              <div className="flex gap-1">
                {[1, 2, 3, 4, 5].map(p => (
                  <button
                    key={p}
                    onClick={() => setPriority(p)}
                    className={`flex-1 py-2.5 rounded text-xs font-bold transition ${
                      p <= priority
                        ? 'bg-red-500/20 text-red-400 border border-red-400/30'
                        : 'bg-cd-bg-input text-cd-text-secondary border border-white/5'
                    }`}
                  >
                    P{p}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* 预估番茄数 + 番茄大小 */}
          <div className="flex gap-3 items-end">
            <div className="flex-1">
              <label className="block text-sm text-cd-text-secondary mb-1">预估番茄数</label>
              <div className="flex items-center gap-2 bg-cd-bg-input border border-white/5 rounded-lg px-3 py-2">
                <button
                  onClick={() => setEstimatedPomodoros(Math.max(1, estimatedPomodoros - 1))}
                  className="w-7 h-7 flex items-center justify-center rounded bg-white/5 text-cd-text hover:bg-white/10 transition text-lg"
                >-</button>
                <span className="flex-1 text-center text-xl font-bold text-cd-text tabular-nums">{estimatedPomodoros}</span>
                <button
                  onClick={() => setEstimatedPomodoros(Math.min(12, estimatedPomodoros + 1))}
                  className="w-7 h-7 flex items-center justify-center rounded bg-white/5 text-cd-text hover:bg-white/10 transition text-lg"
                >+</button>
              </div>
            </div>
            <div className="flex-1">
              <label className="block text-sm text-cd-text-secondary mb-1">番茄大小</label>
              <div className="flex gap-1.5">
                {(['big', 'small'] as PomodoroSize[]).map(s => {
                  const cfg = POMODORO_SIZES[s]
                  return (
                    <button
                      key={s}
                      onClick={() => setPomodoroSize(s)}
                      className={`flex-1 py-2.5 rounded-lg text-sm transition border ${
                        pomodoroSize === s
                          ? 'bg-cd-accent/15 text-cd-accent border-cd-accent/30'
                          : 'bg-cd-bg-input text-cd-text-secondary border-white/5 hover:bg-white/5'
                      }`}
                    >
                      <div className="font-medium">{s === 'big' ? '大番茄' : '小番茄'}</div>
                      <div className="text-[10px] opacity-60">{cfg.work}+{cfg.short_break}min</div>
                    </button>
                  )
                })}
              </div>
            </div>
          </div>

          {/* 时间预估摘要 */}
          <div className="bg-cd-bg-input/50 rounded-lg px-4 py-2.5 text-sm text-cd-text-secondary">
            约 <span className="text-cd-accent font-bold">{totalMinutes}</span> 分钟专注
            {estimatedPomodoros > 1 && (
              <> + <span className="text-emerald-400 font-bold">{breakMinutes}</span> 分钟休息（含长休息）</>
            )}
            ，总计 <span className="text-cd-text font-bold">{totalMinutes + breakMinutes}</span> 分钟
          </div>

          {/* 高级选项 */}
          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex items-center gap-1 text-sm text-cd-text-secondary hover:text-cd-text transition"
          >
            {showAdvanced ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            更多选项
          </button>

          {showAdvanced && (
            <div className="space-y-3 pt-1">
              {/* 截止日期 */}
              <div>
                <label className="block text-sm text-cd-text-secondary mb-1">截止日期</label>
                <input
                  type="date"
                  value={dueDate}
                  onChange={e => setDueDate(e.target.value)}
                  className="w-full bg-cd-bg-input border border-white/5 rounded-lg px-3 py-2.5 text-cd-text focus:outline-none focus:border-cd-accent/40"
                />
              </div>
              {/* 分配日期 */}
              <div>
                <label className="block text-sm text-cd-text-secondary mb-1">分配到日期</label>
                <div className="flex gap-2">
                  <button
                    onClick={() => setAssignedDate(formatLocalDate(new Date()))}
                    className={`px-3 py-2 rounded-lg text-sm transition border ${
                      assignedDate === formatLocalDate(new Date())
                        ? 'bg-cd-accent/15 text-cd-accent border-cd-accent/30'
                        : 'bg-cd-bg-input text-cd-text-secondary border-white/5 hover:bg-white/5'
                    }`}
                  >今日</button>
                  <input
                    type="date"
                    value={assignedDate}
                    onChange={e => setAssignedDate(e.target.value)}
                    className="flex-1 bg-cd-bg-input border border-white/5 rounded-lg px-3 py-2.5 text-cd-text focus:outline-none focus:border-cd-accent/40"
                  />
                  <button
                    onClick={() => setAssignedDate('')}
                    className={`px-3 py-2 rounded-lg text-sm transition border ${
                      !assignedDate
                        ? 'bg-cd-accent/15 text-cd-accent border-cd-accent/30'
                        : 'bg-cd-bg-input text-cd-text-secondary border-white/5 hover:bg-white/5'
                    }`}
                  >不分配</button>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* 底部按钮 */}
        <div className="flex gap-3 px-6 pb-5 pt-2">
          <button
            onClick={onClose}
            className="flex-1 py-2.5 rounded-xl text-sm text-cd-text-secondary border border-white/5 hover:bg-white/5 transition"
          >取消</button>
          <button
            onClick={handleCreate}
            disabled={!title.trim() || saving}
            className="flex-1 py-2.5 rounded-xl text-sm font-medium bg-cd-accent/20 text-cd-accent border border-cd-accent/30 hover:bg-cd-accent/30 transition disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {saving ? '创建中...' : '创建任务'}
          </button>
        </div>
      </div>
    </div>
  )
}

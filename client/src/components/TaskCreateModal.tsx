/**
 * TaskCreateModal — 统一任务创建弹窗
 * 基于 Modal 组件，保持全局弹窗风格一致
 */
import { useState, useEffect, useRef } from 'react'
import { Timer, Target, RotateCw, ChevronDown, ChevronUp } from 'lucide-react'
import Modal from './Modal'
import { createTodo, POMODORO_SIZES, type TaskLevel, formatLocalDate, getWeekStart } from '../api/client'

const CATEGORIES: { value: string; emoji: string }[] = [
  { value: '开发', emoji: '💻' }, { value: '测试', emoji: '🧪' },
  { value: '运维', emoji: '🔧' }, { value: '数据分析', emoji: '📊' },
  { value: '产品', emoji: '📋' }, { value: '设计', emoji: '🎨' },
  { value: '管理', emoji: '👔' }, { value: '文档', emoji: '📝' },
  { value: '会议', emoji: '👥' }, { value: '沟通', emoji: '💬' },
  { value: '学习', emoji: '📖' }, { value: '生活', emoji: '🏠' },
]

type PomodoroSize = 'big' | 'small'
type TaskMode = 'timer' | 'goal' | 'habit'

interface TaskCreateModalProps {
  open: boolean
  onClose: () => void
  onCreated?: (id: number) => void
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

  const PRIORITY_COLORS = ['#ef4444', '#f59e0b', '#eab308', '#22c55e', '#6b7280']

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="新建任务"
      footer={
        <div className="flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 py-2 rounded-xl text-sm text-cd-text-secondary border border-cd-border hover:bg-cd-hover transition"
          >
            取消
          </button>
          <button
            onClick={handleCreate}
            disabled={!title.trim() || saving}
            className="flex-1 py-2 rounded-xl text-sm font-medium bg-cd-accent/20 text-cd-accent border border-cd-accent/30 hover:bg-cd-accent/30 transition disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {saving ? '创建中...' : '创建任务'}
          </button>
        </div>
      }
    >
      {/* 任务名称 */}
      <div>
        <label className="block text-xs font-medium text-cd-text-secondary mb-1.5">任务名称</label>
        <input
          ref={titleRef}
          type="text"
          value={title}
          onChange={e => setTitle(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleCreate()}
          placeholder="这次要做什么？"
          className="w-full bg-cd-bg-input border border-cd-border rounded-lg px-3 py-2 text-sm text-cd-text placeholder:text-cd-text-tertiary focus:outline-none focus:border-cd-accent/50"
        />
      </div>

      {/* 模式选择 */}
      <div>
        <label className="block text-xs font-medium text-cd-text-secondary mb-1.5">模式</label>
        <div className="flex gap-2">
          {([
            { key: 'timer' as TaskMode, icon: Timer, label: '计时', desc: '番茄钟计时' },
            { key: 'goal' as TaskMode, icon: Target, label: '目标', desc: '累计到目标' },
            { key: 'habit' as TaskMode, icon: RotateCw, label: '习惯', desc: '每日打卡' },
          ]).map(m => (
            <button
              key={m.key}
              onClick={() => setMode(m.key)}
              className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-sm transition border ${
                mode === m.key
                  ? 'bg-cd-accent/15 text-cd-accent border-cd-accent/30'
                  : 'bg-cd-bg-input text-cd-text border-cd-border hover:bg-cd-hover'
              }`}
            >
              <m.icon size={14} />
              <span className="font-medium">{m.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* 分类 */}
      <div>
        <label className="block text-xs font-medium text-cd-text-secondary mb-1.5">分类</label>
        <div className="flex flex-wrap gap-1.5">
          {CATEGORIES.map(c => (
            <button
              key={c.value}
              onClick={() => setCategory(c.value)}
              className={`px-2.5 py-1 rounded-md text-xs transition border ${
                category === c.value
                  ? 'bg-cd-accent/15 text-cd-accent border-cd-accent/30 font-medium'
                  : 'bg-cd-bg-input text-cd-text border-cd-border hover:bg-cd-hover'
              }`}
            >
              {c.emoji} {c.value}
            </button>
          ))}
        </div>
      </div>

      {/* 优先级 */}
      <div>
        <label className="block text-xs font-medium text-cd-text-secondary mb-1.5">优先级</label>
        <div className="flex gap-1">
          {[1, 2, 3, 4, 5].map(p => (
            <button
              key={p}
              onClick={() => setPriority(p)}
              className="flex-1 py-1.5 rounded-md text-xs font-bold transition border"
              style={{
                background: priority === p ? PRIORITY_COLORS[p - 1] + '25' : 'var(--cd-bg-input)',
                color: priority === p ? PRIORITY_COLORS[p - 1] : 'var(--cd-text)',
                borderColor: priority === p ? PRIORITY_COLORS[p - 1] + '55' : 'var(--cd-border)',
              }}
            >
              P{p}
            </button>
          ))}
        </div>
      </div>

      {/* 预估番茄数 + 番茄大小 */}
      <div className="flex gap-3">
        <div className="flex-1">
          <label className="block text-xs font-medium text-cd-text-secondary mb-1.5">预估番茄数</label>
          <div className="flex items-center gap-1 bg-cd-bg-input border border-cd-border rounded-lg px-2 py-1.5">
            <button
              onClick={() => setEstimatedPomodoros(Math.max(1, estimatedPomodoros - 1))}
              className="w-6 h-6 flex items-center justify-center rounded bg-cd-hover text-cd-text hover:bg-cd-accent/20 transition text-sm font-bold"
            >−</button>
            <span className="flex-1 text-center text-lg font-bold text-cd-text tabular-nums">{estimatedPomodoros}</span>
            <button
              onClick={() => setEstimatedPomodoros(Math.min(12, estimatedPomodoros + 1))}
              className="w-6 h-6 flex items-center justify-center rounded bg-cd-hover text-cd-text hover:bg-cd-accent/20 transition text-sm font-bold"
            >+</button>
          </div>
        </div>
        <div className="flex-1">
          <label className="block text-xs font-medium text-cd-text-secondary mb-1.5">番茄大小</label>
          <div className="flex gap-1.5">
            {(['big', 'small'] as PomodoroSize[]).map(s => {
              const cfg = POMODORO_SIZES[s]
              return (
                <button
                  key={s}
                  onClick={() => setPomodoroSize(s)}
                  className={`flex-1 py-2 rounded-lg text-sm transition border ${
                    pomodoroSize === s
                      ? 'bg-cd-accent/15 text-cd-accent border-cd-accent/30 font-medium'
                      : 'bg-cd-bg-input text-cd-text border-cd-border hover:bg-cd-hover'
                  }`}
                >
                  <div>{s === 'big' ? '🍅 大' : '🍅 小'}</div>
                  <div className="text-[10px] text-cd-text-tertiary">{cfg.work}+{cfg.short_break}min</div>
                </button>
              )
            })}
          </div>
        </div>
      </div>

      {/* 时间预估摘要 */}
      <div className="rounded-lg px-3 py-2 text-xs text-cd-text-secondary" style={{ background: 'var(--cd-bg-input)', border: '1px solid var(--cd-border)' }}>
        约 <span className="text-cd-accent font-bold">{totalMinutes}</span> 分钟专注
        {estimatedPomodoros > 1 && (
          <> + <span className="font-bold" style={{ color: '#34d399' }}>{breakMinutes}</span> 分钟休息（含长休息）</>
        )}
        ，总计 <span className="text-cd-text font-bold">{totalMinutes + breakMinutes}</span> 分钟
      </div>

      {/* 高级选项 */}
      <button
        onClick={() => setShowAdvanced(!showAdvanced)}
        className="flex items-center gap-1 text-xs text-cd-text-secondary hover:text-cd-text transition"
      >
        {showAdvanced ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        更多选项
      </button>

      {showAdvanced && (
        <div className="space-y-3 pt-1">
          <div>
            <label className="block text-xs font-medium text-cd-text-secondary mb-1">截止日期</label>
            <input
              type="date"
              value={dueDate}
              onChange={e => setDueDate(e.target.value)}
              className="w-full bg-cd-bg-input border border-cd-border rounded-lg px-3 py-2 text-sm text-cd-text focus:outline-none focus:border-cd-accent/50"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-cd-text-secondary mb-1">分配到日期</label>
            <div className="flex gap-2">
              <button
                onClick={() => setAssignedDate(formatLocalDate(new Date()))}
                className={`px-3 py-1.5 rounded-lg text-xs transition border ${
                  assignedDate === formatLocalDate(new Date())
                    ? 'bg-cd-accent/15 text-cd-accent border-cd-accent/30 font-medium'
                    : 'bg-cd-bg-input text-cd-text border-cd-border hover:bg-cd-hover'
                }`}
              >今日</button>
              <input
                type="date"
                value={assignedDate}
                onChange={e => setAssignedDate(e.target.value)}
                className="flex-1 bg-cd-bg-input border border-cd-border rounded-lg px-3 py-2 text-sm text-cd-text focus:outline-none focus:border-cd-accent/50"
              />
              <button
                onClick={() => setAssignedDate('')}
                className={`px-3 py-1.5 rounded-lg text-xs transition border ${
                  !assignedDate
                    ? 'bg-cd-accent/15 text-cd-accent border-cd-accent/30 font-medium'
                    : 'bg-cd-bg-input text-cd-text border-cd-border hover:bg-cd-hover'
                }`}
              >不分配</button>
            </div>
          </div>
        </div>
      )}
    </Modal>
  )
}

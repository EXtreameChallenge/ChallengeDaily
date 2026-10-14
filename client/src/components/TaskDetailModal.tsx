import { useState, useEffect } from 'react'
import { Play, Check, Trash2, Calendar, Target, Clock, Timer, Flame } from 'lucide-react'
import Modal from './Modal'
import { updateTodo, deleteTodo, assignTodo, unassignTodo, updateTaskTime, getGoals, type TodoV2, type Goal } from '../api/client'
import { useToast } from './Toast'

const PRIORITY_COLORS = ['#ef4444', '#f59e0b', '#F0C040', '#10b981', '#6b7280']
const PRIORITY_LABELS = ['P1 紧急', 'P2 高', 'P3 中', 'P4 低', 'P5 最低']
const CATEGORIES = ['开发', '会议', '沟通', '文档', '测试', '设计', '运维', '数据分析', '学习', '管理', '产品', '生活']
const MODE_LABELS: Record<string, string> = { timer: '计时', goal: '目标', habit: '习惯' }

interface Props {
  todo: TodoV2 | null
  onClose: () => void
  onUpdate: () => void
}

export default function TaskDetailModal({ todo, onClose, onUpdate }: Props) {
  const { success, error } = useToast()
  const [title, setTitle] = useState('')
  const [priority, setPriority] = useState(3)
  const [category, setCategory] = useState('开发')
  const [mode, setMode] = useState<'timer' | 'goal' | 'habit'>('timer')
  const [moveDate, setMoveDate] = useState('')
  const [goals, setGoals] = useState<Goal[]>([])
  const [goalId, setGoalId] = useState<number | null>(null)

  useEffect(() => {
    if (todo) {
      setTitle(todo.title)
      setPriority(todo.priority)
      setCategory(todo.category)
      setMode(todo.mode)
      setMoveDate(todo.assigned_date || '')
      setGoalId(todo.goal_id ?? null)
    }
  }, [todo])

  // 拉取活跃目标列表（仅在弹窗打开时拉取一次）
  useEffect(() => {
    if (todo) {
      getGoals('active').then(r => setGoals(r.goals)).catch(() => setGoals([]))
    }
  }, [todo])

  if (!todo) return null

  const radius = 22
  const circumference = 2 * Math.PI * radius
  const progressPct = todo.target_min > 0 ? Math.min(100, (todo.progress_min / todo.target_min) * 100) : 0
  const offset = circumference - (progressPct / 100) * circumference

  const saveField = async (field: string, value: string | number | null) => {
    try {
      await updateTodo(todo.id, { [field]: value } as Partial<TodoV2>)
      onUpdate()
    } catch {
      error('更新失败')
    }
  }
  const handleTitleBlur = () => { if (title !== todo.title) saveField('title', title) }
  const handlePriority = (p: number) => { setPriority(p); saveField('priority', p) }
  const handleCategory = (v: string) => { setCategory(v); saveField('category', v) }
  const handleMode = (v: 'timer' | 'goal' | 'habit') => { setMode(v); saveField('mode', v) }
  const handleGoal = (v: number | null) => {
    setGoalId(v)
    saveField('goal_id', v as unknown as number)
    if (v) {
      const g = goals.find(g => g.id === v)
      if (g) success(`已关联到目标「${g.title}」`)
    } else {
      success('已取消目标关联')
    }
  }

  const handleComplete = async () => {
    try {
      await updateTodo(todo.id, { status: 'completed' })
      success('任务已完成')
      onUpdate(); onClose()
    } catch { error('操作失败') }
  }
  const handleDelete = async () => {
    try {
      await deleteTodo(todo.id)
      success('已删除')
      onUpdate(); onClose()
    } catch { error('删除失败') }
  }
  const handleMove = async () => {
    try {
      if (moveDate) {
        await assignTodo({ todo_id: todo.id, assigned_date: moveDate })
        success(`已移至 ${moveDate}`)
      } else {
        await unassignTodo(todo.id)
        success('已移至待分配')
      }
      onUpdate(); onClose()
    } catch { error('移动失败') }
  }
  const startFocus = () => {
    window.location.hash = '#/focus?todo_id=' + todo.id
    onClose()
  }

  // 通用 select 样式
  const selectCls = "flex-1 appearance-none bg-cd-bg-input border border-cd-border rounded-2xl px-3 py-2 text-xs text-cd-text focus:outline-none focus:border-cd-accent/60 focus:ring-1 focus:ring-cd-accent/30 transition cursor-pointer"

  return (
    <Modal
      open={!!todo}
      onClose={onClose}
      title="任务详情"
      maxWidth="max-w-md"
      footer={
        <div className="grid grid-cols-3 gap-2.5">
          <button
            onClick={startFocus}
            className="flex items-center justify-center gap-1.5 py-2.5 text-xs font-semibold rounded-2xl text-white shadow-md hover:shadow-lg hover:brightness-110 active:scale-[0.98] transition-all"
            style={{ background: 'var(--cd-gradient-primary)' }}
          >
            <Play size={13} fill="currentColor" /> 开始专注
          </button>
          <button
            onClick={handleComplete}
            className="flex items-center justify-center gap-1.5 py-2.5 text-xs font-medium rounded-2xl bg-cd-accent/15 text-cd-accent border border-cd-accent/30 hover:bg-cd-accent/25 active:scale-[0.98] transition-all"
          >
            <Check size={13} strokeWidth={2.5} /> 完成
          </button>
          <button
            onClick={handleDelete}
            className="flex items-center justify-center gap-1.5 py-2.5 text-xs font-medium rounded-2xl bg-cd-red/10 text-cd-red border border-cd-red/25 hover:bg-cd-red/20 active:scale-[0.98] transition-all"
          >
            <Trash2 size={13} /> 删除
          </button>
        </div>
      }
    >
      {/* ===== 标题 ===== */}
      <input
        value={title}
        onChange={e => setTitle(e.target.value)}
        onBlur={handleTitleBlur}
        onKeyDown={e => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
        className="w-full bg-transparent border-b-2 border-cd-border focus:border-cd-accent outline-none text-lg font-bold text-cd-text pb-2 mb-1 transition-colors"
        placeholder="任务标题..."
      />

      {/* ===== 进度概览卡片 ===== */}
      <div className="glass-card p-4 mb-1">
        <div className="flex items-center gap-4">
          {/* 进度环 */}
          <div className="relative shrink-0">
            <svg width="72" height="72" viewBox="0 0 72 72" className="drop-shadow-sm">
              <defs>
                <linearGradient id="progressGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="var(--cd-accent)" />
                  <stop offset="100%" stopColor="var(--cd-accent-light)" />
                </linearGradient>
              </defs>
              <circle cx="36" cy="36" r={radius} fill="none" stroke="var(--cd-border)" strokeWidth="5" opacity="0.5" />
              <circle cx="36" cy="36" r={radius} fill="none" stroke="url(#progressGrad)" strokeWidth="5"
                strokeDasharray={circumference} strokeDashoffset={offset} strokeLinecap="round"
                transform="rotate(-90 36 36)" className="transition-all duration-700 ease-out"
                style={{ filter: 'drop-shadow(0 0 4px var(--cd-accent))' }} />
              <text x="36" y="34" textAnchor="middle" dominantBaseline="central"
                className="text-sm font-extrabold" fill="var(--cd-text)">{Math.round(progressPct)}%</text>
              <text x="36" y="46" textAnchor="middle" dominantBaseline="central"
                className="text-[8px]" fill="var(--cd-text-tertiary)">完成度</text>
            </svg>
          </div>

          {/* 统计数据 */}
          <div className="flex-1 space-y-2.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <Timer size={12} className="text-cd-accent" />
                <span className="text-xs text-cd-text-secondary">已专注</span>
              </div>
              <span className="text-xs font-bold text-cd-text tabular-nums">
                {todo.progress_min}<span className="text-cd-text-tertiary font-normal">/{todo.target_min} 分钟</span>
              </span>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <Flame size={12} className="text-orange-400" />
                <span className="text-xs text-cd-text-secondary">番茄钟</span>
              </div>
              <span className="text-xs font-bold text-cd-text tabular-nums">
                🍅 <span className="text-orange-400">× {todo.pomodoro_count}</span>
              </span>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <div className="w-2 h-2 rounded-full" style={{ background: PRIORITY_COLORS[priority - 1] }} />
                <span className="text-xs text-cd-text-secondary">优先级</span>
              </div>
              <span className="text-xs font-bold" style={{ color: PRIORITY_COLORS[priority - 1] }}>
                {PRIORITY_LABELS[priority - 1]}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* ===== 优先级选择 ===== */}
      <div>
        <div className="text-[10px] font-semibold text-cd-text-tertiary uppercase tracking-wider mb-1.5 px-0.5">优先级</div>
        <div className="flex gap-1.5">
          {[1, 2, 3, 4, 5].map(p => (
            <button key={p} onClick={() => handlePriority(p)}
              className="flex-1 py-1.5 text-xs font-semibold rounded-lg transition-all active:scale-95"
              style={{
                background: priority === p ? PRIORITY_COLORS[p - 1] : 'var(--cd-bg-input)',
                color: priority === p ? '#fff' : 'var(--cd-text-tertiary)',
                border: `1px solid ${priority === p ? PRIORITY_COLORS[p - 1] : 'var(--cd-border)'}`,
                boxShadow: priority === p ? `0 2px 8px ${PRIORITY_COLORS[p - 1]}55` : 'none',
              }}>P{p}</button>
          ))}
        </div>
      </div>

      {/* ===== 分类与模式 ===== */}
      <div>
        <div className="text-[10px] font-semibold text-cd-text-tertiary uppercase tracking-wider mb-1.5 px-0.5">任务属性</div>
        <div className="flex gap-2">
          <select value={category} onChange={e => handleCategory(e.target.value)} className={selectCls}>
            {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <select value={mode} onChange={e => handleMode(e.target.value as 'timer' | 'goal' | 'habit')}
            className="w-20 appearance-none bg-cd-bg-input border border-cd-border rounded-2xl px-3 py-2 text-xs text-cd-text focus:outline-none focus:border-cd-accent/60 focus:ring-1 focus:ring-cd-accent/30 transition cursor-pointer text-center">
            {Object.entries(MODE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
      </div>

      {/* ===== 目标关联 ===== */}
      <div>
        <div className="text-[10px] font-semibold text-cd-text-tertiary uppercase tracking-wider mb-1.5 px-0.5">关联目标</div>
        <div className="flex items-center gap-2">
          <Target size={13} className="text-cd-accent shrink-0" />
          <select
            value={goalId ?? ''}
            onChange={e => handleGoal(e.target.value ? Number(e.target.value) : null)}
            className={selectCls}
          >
            <option value="">不关联长期目标</option>
            {goals.map(g => (
              <option key={g.id} value={g.id}>
                {g.title}（{g.timeframe === 'yearly' ? '年度' : g.timeframe === 'quarterly' ? '季度' : '月度'} · {g.progress}%）
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* ===== 时间安排 ===== */}
      <div>
        <div className="text-[10px] font-semibold text-cd-text-tertiary uppercase tracking-wider mb-1.5 px-0.5">时间安排</div>
        <div className="space-y-2">
          {/* 日期移动 */}
          <div className="flex gap-2">
            <div className="flex-1 flex items-center gap-2 bg-cd-bg-input border border-cd-border rounded-2xl px-3 py-1.5 focus-within:border-cd-accent/60 focus-within:ring-1 focus-within:ring-cd-accent/30 transition">
              <Calendar size={13} className="text-cd-text-tertiary shrink-0" />
              <input type="date" value={moveDate} onChange={e => setMoveDate(e.target.value)}
                className="flex-1 bg-transparent text-xs text-cd-text outline-none" />
            </div>
            <button onClick={handleMove}
              className="flex items-center gap-1 px-3.5 py-1.5 text-xs font-medium rounded-2xl bg-cd-accent/15 text-cd-accent border border-cd-accent/30 hover:bg-cd-accent/25 active:scale-95 transition-all">
              移至
            </button>
          </div>
          {/* 甘特图时间 */}
          <div className="flex items-center gap-2 bg-cd-bg-input border border-cd-border rounded-2xl px-3 py-1.5 focus-within:border-cd-accent/60 focus-within:ring-1 focus-within:ring-cd-accent/30 transition">
            <Clock size={13} className="text-cd-text-tertiary shrink-0" />
            <input
              type="time"
              value={todo.plan_start_min != null ? `${String(Math.floor(todo.plan_start_min / 60)).padStart(2, '0')}:${String(todo.plan_start_min % 60).padStart(2, '0')}` : ''}
              onChange={async e => {
                const val = e.target.value
                if (val) {
                  const [h, m] = val.split(':').map(Number)
                  await updateTaskTime(todo.id, h * 60 + m)
                } else {
                  await updateTaskTime(todo.id, null)
                }
                onUpdate()
              }}
              className="flex-1 bg-transparent text-xs text-cd-text outline-none"
            />
            <span className="text-[10px] text-cd-text-tertiary shrink-0">甘特图开始时间</span>
          </div>
        </div>
      </div>
    </Modal>
  )
}

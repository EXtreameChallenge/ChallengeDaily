import { useState, useEffect } from 'react'
import { Play, Check, Trash2, Calendar, Target } from 'lucide-react'
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

  const radius = 18
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

  return (
    <Modal
      open={!!todo}
      onClose={onClose}
      title="任务详情"
      maxWidth="max-w-md"
      footer={
        <div className="grid grid-cols-3 gap-2">
          <button
            onClick={startFocus}
            className="flex items-center justify-center gap-1 py-2 text-xs rounded-xl bg-cd-accent/20 text-cd-accent border border-cd-accent/30 hover:bg-cd-accent/30 transition"
          >
            <Play size={12} /> 专注
          </button>
          <button
            onClick={handleComplete}
            className="flex items-center justify-center gap-1 py-2 text-xs rounded-xl bg-cd-green/20 text-cd-green border border-cd-green/30 hover:bg-cd-green/30 transition"
          >
            <Check size={12} /> 完成
          </button>
          <button
            onClick={handleDelete}
            className="flex items-center justify-center gap-1 py-2 text-xs rounded-xl bg-cd-red/20 text-cd-red border border-cd-red/30 hover:bg-cd-red/30 transition"
          >
            <Trash2 size={12} /> 删除
          </button>
        </div>
      }
    >
      {/* title (editable) */}
      <input
        value={title}
        onChange={e => setTitle(e.target.value)}
        onBlur={handleTitleBlur}
        onKeyDown={e => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
        className="w-full bg-transparent border-b border-cd-border focus:border-cd-accent/50 outline-none text-base text-cd-text py-1.5 mb-4"
      />

      {/* progress ring + stats */}
      <div className="flex items-center gap-4 mb-4">
        <svg width="60" height="60" viewBox="0 0 60 60" className="shrink-0">
          <circle cx="30" cy="30" r={radius} fill="none" stroke="var(--cd-border)" strokeWidth="4" />
          <circle cx="30" cy="30" r={radius} fill="none" stroke="#7B68EE" strokeWidth="4"
            strokeDasharray={circumference} strokeDashoffset={offset} strokeLinecap="round"
            transform="rotate(-90 30 30)" className="transition-all duration-700" />
          <text x="30" y="30" textAnchor="middle" dominantBaseline="central"
            className="text-[10px] font-bold" fill="var(--cd-text)">{Math.round(progressPct)}%</text>
        </svg>
        <div className="flex-1 space-y-1.5">
          <div className="flex justify-between text-xs">
            <span className="text-cd-text-tertiary">已专注</span>
            <span className="text-cd-text tabular-nums">{todo.progress_min}/{todo.target_min} 分钟</span>
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-cd-text-tertiary">番茄钟</span>
            <span className="text-purple-400 tabular-nums">🍅 × {todo.pomodoro_count}</span>
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-cd-text-tertiary">优先级</span>
            <span style={{ color: PRIORITY_COLORS[priority - 1] }}>{PRIORITY_LABELS[priority - 1]}</span>
          </div>
        </div>
      </div>

      {/* priority selector */}
      <div className="flex gap-1 mb-3">
        {[1, 2, 3, 4, 5].map(p => (
          <button key={p} onClick={() => handlePriority(p)}
            className="flex-1 py-1.5 text-xs rounded transition"
            style={{
              background: priority === p ? PRIORITY_COLORS[p - 1] + '22' : 'transparent',
              color: priority === p ? PRIORITY_COLORS[p - 1] : 'var(--cd-text-tertiary)',
              border: `1px solid ${priority === p ? PRIORITY_COLORS[p - 1] + '88' : 'transparent'}`,
            }}>P{p}</button>
        ))}
      </div>

      {/* category & mode */}
      <div className="flex gap-2 mb-3">
        <select value={category} onChange={e => handleCategory(e.target.value)}
          className="flex-1 bg-cd-bg-input border border-cd-border rounded-lg px-2 py-1.5 text-xs text-cd-text focus:outline-none focus:border-cd-accent/50">
          {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={mode} onChange={e => handleMode(e.target.value as 'timer' | 'goal' | 'habit')}
          className="bg-cd-bg-input border border-cd-border rounded-lg px-2 py-1.5 text-xs text-cd-text focus:outline-none focus:border-cd-accent/50">
          {Object.entries(MODE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </div>

      {/* goal 关联选择器（P5：长期目标联动） */}
      <div className="flex items-center gap-2 mb-3">
        <Target size={12} className="text-cd-text-tertiary shrink-0" />
        <select
          value={goalId ?? ''}
          onChange={e => handleGoal(e.target.value ? Number(e.target.value) : null)}
          className="flex-1 bg-cd-bg-input border border-cd-border rounded-lg px-2 py-1.5 text-xs text-cd-text focus:outline-none focus:border-cd-accent/50"
        >
          <option value="">不关联长期目标</option>
          {goals.map(g => (
            <option key={g.id} value={g.id}>
              {g.title}（{g.timeframe === 'yearly' ? '年度' : g.timeframe === 'quarterly' ? '季度' : '月度'} · {g.progress}%）
            </option>
          ))}
        </select>
      </div>

      {/* move date + button */}
      <div className="flex gap-2">
        <input type="date" value={moveDate} onChange={e => setMoveDate(e.target.value)}
          className="flex-1 bg-cd-bg-input border border-cd-border rounded-lg px-2 py-1.5 text-xs text-cd-text focus:outline-none focus:border-cd-accent/50" />
        <button onClick={handleMove}
          className="flex items-center gap-1 px-3 py-1.5 text-xs rounded-xl bg-cd-bg-input text-cd-text-secondary border border-cd-border hover:bg-cd-hover transition">
          <Calendar size={12} /> 移至
        </button>
      </div>

      {/* 计划开始时间（甘特图） */}
      <div className="flex gap-2 mt-2">
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
          className="flex-1 bg-cd-bg-input border border-cd-border rounded-lg px-2 py-1.5 text-xs text-cd-text focus:outline-none focus:border-cd-accent/50"
        />
        <span className="flex items-center text-[10px] text-cd-text-tertiary">甘特图时间</span>
      </div>
    </Modal>
  )
}

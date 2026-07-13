import { useState, useEffect, useCallback } from 'react'
import { Plus, Check, Trash2, Clock, Target, Repeat, ListChecks, Play, Calendar, Flame } from 'lucide-react'
import { getTodos, updateTodo, deleteTodo, getTodayTodos, CATEGORY_COLORS, type TodoV2, formatLocalDate } from '../api/client'
import { useToast } from '../components/Toast'
import TaskCreateModal from '../components/TaskCreateModal'

const MODE_ICONS = { timer: Clock, goal: Target, habit: Repeat }

/** 根据分类获取颜色 */
function getCategoryColor(todo: TodoV2): string {
  if (todo.color) return todo.color
  return CATEGORY_COLORS[todo.category] || '#7B68EE'
}

/** 圆形进度环 */
function ProgressRing({ progress, size = 44 }: { progress: number; size?: number }) {
  const radius = (size - 6) / 2
  const circumference = 2 * Math.PI * radius
  const clamped = Math.min(100, Math.max(0, progress))
  const offset = circumference - (clamped / 100) * circumference
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="shrink-0">
      <circle
        cx={size / 2} cy={size / 2} r={radius}
        fill="none" stroke="var(--cd-border)" strokeWidth="3"
      />
      <circle
        cx={size / 2} cy={size / 2} r={radius}
        fill="none" stroke="var(--cd-green)" strokeWidth="3"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        className="transition-all duration-700"
      />
      <text
        x={size / 2} y={size / 2}
        textAnchor="middle" dominantBaseline="central"
        className="text-[9px] font-bold fill-cd-text"
      >
        {Math.round(clamped)}%
      </text>
    </svg>
  )
}

export default function Todos() {
  const [todos, setTodos] = useState<TodoV2[]>([])
  const [todayTodos, setTodayTodos] = useState<TodoV2[]>([])
  const [filter, setFilter] = useState<'all' | 'pending' | 'completed'>('all')
  const [showCreate, setShowCreate] = useState(false)
  const toast = useToast()

  const load = useCallback(async () => {
    try {
      const [allRes, todayRes] = await Promise.all([
        getTodos(filter === 'all' ? undefined : filter),
        getTodayTodos(),
      ])
      setTodos(allRes.todos as TodoV2[])
      setTodayTodos(todayRes.todos)
    } catch (e) {
      toast.error('加载失败，请重试')
    }
  }, [filter, toast])

  useEffect(() => { load() }, [load])

  const handleToggle = async (todo: TodoV2) => {
    const newStatus = todo.status === 'completed' ? 'pending' : 'completed'
    try {
      await updateTodo(todo.id, { status: newStatus })
      load()
    } catch (e) {
      toast.error('更新失败，请重试')
    }
  }

  const handleDelete = async (todo: TodoV2) => {
    // 删除级联提示 — 有关联番茄记录时警告
    const pomCount = todo.pomodoro_count || 0
    const hasProgress = (todo.progress_min || 0) > 0
    let msg = '确定删除该待办？'
    if (pomCount > 0 && hasProgress) {
      msg = `该待办已有 ${pomCount} 个番茄记录（${todo.progress_min}分钟进度），删除后关联数据将一并清除。确定删除？`
    } else if (pomCount > 0) {
      msg = `该待办已有 ${pomCount} 个番茄记录，删除后关联数据将一并清除。确定删除？`
    } else if (hasProgress) {
      msg = `该待办已有 ${todo.progress_min}分钟进度记录，删除后无法恢复。确定删除？`
    }
    if (!window.confirm(msg)) return
    try {
      await deleteTodo(todo.id)
      load()
    } catch (e) {
      toast.error('删除失败，请重试')
    }
  }

  const startFocus = (todo: TodoV2) => {
    window.location.hash = `#/focus?todo_id=${todo.id}`
  }

  // 按分配状态分组
  const todayStr = formatLocalDate(new Date())
  const todayPending = todayTodos.filter(t => t.status !== 'completed')
  const todayCompleted = todayTodos.filter(t => t.status === 'completed')
  const unassigned = todos.filter(t => !t.assigned_date && t.status !== 'completed')
  const otherPending = todos.filter(t => t.assigned_date && t.assigned_date !== todayStr && t.status !== 'completed')

  const renderTodoCard = (todo: TodoV2, showFocus = false) => {
    const Icon = MODE_ICONS[todo.mode] || Clock
    const progress = todo.target_min > 0 ? Math.min(100, (todo.progress_min / todo.target_min) * 100) : 0
    const estPom = todo.estimated_pomodoros || Math.ceil(todo.target_min / 25) || 1
    const completedPom = todo.pomodoro_count || 0
    const catColor = getCategoryColor(todo)
    const isCompleted = todo.status === 'completed'

    return (
      <div
        key={todo.id}
        className={`relative bg-cd-bg-card rounded-xl border border-white/5 overflow-hidden transition hover:border-white/10 ${isCompleted ? 'opacity-60' : ''}`}
        style={{ borderLeft: `3px solid ${catColor}` }}
      >
        {/* 卡片头部：标题 + 操作按钮 */}
        <div className="flex items-start gap-2 p-3.5 pb-2">
          <button
            onClick={() => handleToggle(todo)}
            className={`w-5 h-5 rounded-full border-2 flex items-center justify-center shrink-0 mt-0.5 transition ${
              isCompleted
                ? 'bg-green-500/20 border-green-500/40 text-green-400'
                : 'border-white/20 hover:border-cd-accent/40'
            }`}
          >
            {isCompleted && <Check size={12} />}
          </button>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <Icon size={13} className="text-cd-text-secondary shrink-0" />
              <span className={`text-sm font-medium leading-tight ${isCompleted ? 'line-through text-cd-text-secondary' : 'text-cd-text'}`}>
                {todo.title}
              </span>
            </div>
          </div>
          <button
            onClick={() => handleDelete(todo)}
            className="text-cd-text-tertiary hover:text-red-400 transition shrink-0 p-1"
            title="删除"
          >
            <Trash2 size={14} />
          </button>
        </div>

        {/* 卡片主体：进度环 + 番茄/时长/状态 */}
        <div className="flex items-center gap-3 px-3.5 pb-2">
          <ProgressRing progress={progress} size={44} />
          <div className="flex-1 min-w-0 space-y-1">
            {/* 番茄可视化 */}
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-xs leading-none flex items-center flex-wrap gap-0.5">
                {Array.from({ length: Math.min(estPom, 10) }, (_, i) => (
                  <span key={i} className={i < completedPom ? '' : 'opacity-25'}>🍅</span>
                ))}
                {estPom > 10 && <span className="text-[10px] text-cd-text-tertiary">+{estPom - 10}</span>}
              </span>
              <span className="text-[10px] text-cd-text-secondary tabular-nums">{completedPom}/{estPom}</span>
            </div>
            {/* 时长标签 */}
            <div className="flex items-center gap-1.5 text-[11px] text-cd-text-secondary tabular-nums">
              <Clock size={11} />
              <span>{todo.progress_min}/{todo.target_min} min</span>
            </div>
            {/* 状态标签 */}
            <div>
              <span
                className={`inline-block text-[10px] px-1.5 py-0.5 rounded font-medium ${
                  isCompleted
                    ? 'bg-green-500/15 text-green-400'
                    : 'bg-yellow-500/15 text-yellow-400'
                }`}
              >
                {isCompleted ? '已完成' : '待处理'}
              </span>
            </div>
          </div>
        </div>

        {/* 卡片底部：分类 + 日期 + 开始专注 */}
        <div className="flex items-center justify-between gap-2 px-3.5 py-2 border-t border-white/5 bg-black/10">
          <div className="flex items-center gap-1.5 flex-wrap min-w-0">
            <span
              className="text-[10px] px-1.5 py-0.5 rounded font-medium"
              style={{ background: catColor + '20', color: catColor }}
            >
              {todo.category}
            </span>
            {todo.pomodoro_size === 'small' && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400">小番茄</span>
            )}
            {todo.assigned_date && (
              <span className="text-[10px] text-cd-text-tertiary flex items-center gap-0.5">
                <Flame size={10} /> {todo.assigned_date}
              </span>
            )}
            {todo.due_date && (
              <span className="text-[10px] text-cd-text-tertiary flex items-center gap-0.5">
                <Calendar size={10} /> {todo.due_date}
              </span>
            )}
          </div>
          {showFocus && !isCompleted && (
            <button
              onClick={() => startFocus(todo)}
              className="px-2.5 py-1 rounded-lg text-xs bg-cd-accent/15 text-cd-accent border border-cd-accent/20 hover:bg-cd-accent/25 transition flex items-center gap-1 shrink-0"
              title="开始专注"
            >
              <Play size={11} /> 开始专注
            </button>
          )}
        </div>
      </div>
    )
  }

  const renderGroup = (title: string, dotColor: string, items: TodoV2[], showFocus = false) => {
    if (items.length === 0) return null
    return (
      <div className="mb-6">
        <h2 className="text-sm font-medium text-cd-text-secondary mb-3 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full" style={{ background: dotColor }} />
          {title} · {items.length}项
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {items.map(t => renderTodoCard(t, showFocus))}
        </div>
      </div>
    )
  }

  const isEmpty =
    todayPending.length === 0 &&
    unassigned.length === 0 &&
    otherPending.length === 0 &&
    todayCompleted.length === 0

  return (
    <div className="min-h-screen p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-cd-text">待办清单</h1>
        <div className="flex items-center gap-2">
          {/* 过滤器 */}
          <div className="flex items-center gap-1 bg-cd-bg-card rounded-lg border border-white/5 p-0.5">
            {(['all', 'pending', 'completed'] as const).map(f => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-2.5 py-1 rounded-md text-xs transition ${
                  filter === f ? 'bg-cd-accent/20 text-cd-accent' : 'text-cd-text-secondary hover:text-cd-text'
                }`}
              >
                {f === 'all' ? '全部' : f === 'pending' ? '待处理' : '已完成'}
              </button>
            ))}
          </div>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 px-4 py-2 bg-cd-accent/20 text-cd-accent rounded-lg border border-cd-accent/30 hover:bg-cd-accent/30 transition"
          >
            <Plus size={18} /> 新建任务
          </button>
        </div>
      </div>

      {renderGroup('今日待办', 'var(--cd-green)', todayPending, true)}
      {renderGroup('未分配', '#F0C040', unassigned, true)}
      {renderGroup('其他日期', '#5B8DEF', otherPending, true)}
      {renderGroup('今日已完成', '#22c55e', todayCompleted, false)}

      {isEmpty && (
        <div className="text-center py-12 text-cd-text-secondary">
          <ListChecks size={48} className="mx-auto mb-3 opacity-30" />
          <p>暂无待办，点击右上角新建</p>
        </div>
      )}

      <TaskCreateModal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreated={() => { setShowCreate(false); load() }}
      />
    </div>
  )
}

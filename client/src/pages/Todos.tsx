import { useState, useEffect, useCallback } from 'react'
import { Plus, Check, Trash2, Clock, Target, Repeat, ListChecks, Play, Calendar, Flame } from 'lucide-react'
import { getTodos, updateTodo, deleteTodo, getTodayTodos, type TodoV2, formatLocalDate, POMODORO_SIZES } from '../api/client'
import { useToast } from '../components/Toast'
import TaskCreateModal from '../components/TaskCreateModal'

const MODE_ICONS = { timer: Clock, goal: Target, habit: Repeat }
const PRIORITY_COLORS = ['text-red-400', 'text-orange-400', 'text-yellow-400', 'text-green-400', 'text-gray-400']

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
    // E6: 删除级联提示 — 有关联番茄记录时警告
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

  const pending = todos.filter(t => t.status !== 'completed')
  const completed = todos.filter(t => t.status === 'completed')

  // 按分配状态分组
  const todayStr = formatLocalDate(new Date())
  const todayPending = todayTodos.filter(t => t.status !== 'completed')
  const todayCompleted = todayTodos.filter(t => t.status === 'completed')
  const unassigned = todos.filter(t => !t.assigned_date && t.status !== 'completed')
  const otherPending = todos.filter(t => t.assigned_date && t.assigned_date !== todayStr && t.status !== 'completed')

  const renderTodoItem = (todo: TodoV2, showFocus = false) => {
    const Icon = MODE_ICONS[todo.mode] || Clock
    const progress = todo.target_min > 0 ? Math.min(100, (todo.progress_min / todo.target_min) * 100) : 0
    const sizeConfig = POMODORO_SIZES[todo.pomodoro_size || 'big']
    const estPom = todo.estimated_pomodoros || Math.ceil(todo.target_min / 25) || 1
    const completedPom = todo.pomodoro_count || 0

    return (
      <div key={todo.id} className={`bg-cd-bg-card rounded-xl p-3.5 border border-white/5 flex items-center gap-3 ${todo.status === 'completed' ? 'opacity-50' : ''}`}>
        <button onClick={() => handleToggle(todo)}
          className={`w-6 h-6 rounded-full border-2 flex items-center justify-center shrink-0 transition ${
            todo.status === 'completed' ? 'bg-green-500/20 border-green-500/40 text-green-400' : 'border-white/20 hover:border-cd-accent/40'
          }`}>
          {todo.status === 'completed' && <Check size={14} />}
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <Icon size={14} className="text-cd-text-secondary shrink-0" />
            <span className={`text-sm ${todo.status === 'completed' ? 'line-through text-cd-text-secondary' : 'text-cd-text'}`}>{todo.title}</span>
          </div>
          <div className="mt-1 flex items-center gap-3 flex-wrap">
            {/* 番茄进度 */}
            <div className="flex items-center gap-1.5">
              <span className="text-xs">
                {Array.from({ length: estPom }, (_, i) => (
                  <span key={i} className={i < completedPom ? 'text-cd-accent' : 'text-cd-text-secondary/30'}>🍅</span>
                ))}
              </span>
              <span className="text-[10px] text-cd-text-secondary tabular-nums">{completedPom}/{estPom}</span>
            </div>
            {/* 进度条（goal 模式） */}
            {todo.mode === 'goal' && todo.target_min > 0 && (
              <div className="flex items-center gap-1.5">
                <div className="w-20 h-1.5 bg-cd-bg-input rounded-full overflow-hidden">
                  <div className="h-full bg-cd-accent/40 rounded-full" style={{ width: `${progress}%` }} />
                </div>
                <span className="text-[10px] text-cd-text-secondary tabular-nums">{todo.progress_min}/{todo.target_min}min</span>
              </div>
            )}
            {/* 分类 */}
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-cd-text-secondary">{todo.category}</span>
            {/* 番茄大小 */}
            {todo.pomodoro_size === 'small' && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400">小番茄</span>
            )}
            {/* 截止日期 */}
            {todo.due_date && (
              <span className="text-[10px] text-cd-text-secondary flex items-center gap-0.5">
                <Calendar size={10} /> {todo.due_date}
              </span>
            )}
            {/* 分配日期 */}
            {todo.assigned_date && (
              <span className="text-[10px] text-cd-text-secondary flex items-center gap-0.5">
                <Flame size={10} /> {todo.assigned_date}
              </span>
            )}
          </div>
        </div>
        {/* 开始专注按钮 */}
        {showFocus && todo.status !== 'completed' && (
          <button
            onClick={() => startFocus(todo)}
            className="px-3 py-1.5 rounded-lg text-xs bg-cd-accent/15 text-cd-accent border border-cd-accent/20 hover:bg-cd-accent/25 transition flex items-center gap-1 shrink-0"
          >
            <Play size={12} /> 开始专注
          </button>
        )}
        <button onClick={() => handleDelete(todo)} className="text-cd-text-secondary hover:text-red-400 transition shrink-0">
          <Trash2 size={16} />
        </button>
      </div>
    )
  }

  return (
    <div className="min-h-screen p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-cd-text">待办清单</h1>
        <button onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 bg-cd-accent/20 text-cd-accent rounded-lg border border-cd-accent/30 hover:bg-cd-accent/30 transition">
          <Plus size={18} /> 新建任务
        </button>
      </div>

      {/* 今日待办 */}
      {todayPending.length > 0 && (
        <div className="mb-6">
          <h2 className="text-sm font-medium text-cd-text-secondary mb-2 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-cd-accent" />
            今日待办 · {todayPending.length}项
          </h2>
          <div className="space-y-2">
            {todayPending.map(t => renderTodoItem(t, true))}
          </div>
        </div>
      )}

      {/* 未分配 */}
      {unassigned.length > 0 && (
        <div className="mb-6">
          <h2 className="text-sm font-medium text-cd-text-secondary mb-2 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-yellow-400" />
            未分配 · {unassigned.length}项
          </h2>
          <div className="space-y-2">
            {unassigned.map(t => renderTodoItem(t, true))}
          </div>
        </div>
      )}

      {/* 其他日期 */}
      {otherPending.length > 0 && (
        <div className="mb-6">
          <h2 className="text-sm font-medium text-cd-text-secondary mb-2 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-blue-400" />
            其他日期 · {otherPending.length}项
          </h2>
          <div className="space-y-2">
            {otherPending.map(t => renderTodoItem(t, true))}
          </div>
        </div>
      )}

      {/* 今日已完成 */}
      {todayCompleted.length > 0 && (
        <div className="mb-6">
          <h2 className="text-sm font-medium text-cd-text-secondary mb-2 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-green-400" />
            今日已完成 · {todayCompleted.length}项
          </h2>
          <div className="space-y-2">
            {todayCompleted.map(t => renderTodoItem(t))}
          </div>
        </div>
      )}

      {/* 空状态 */}
      {todayPending.length === 0 && unassigned.length === 0 && otherPending.length === 0 && todayCompleted.length === 0 && (
        <div className="text-center py-12 text-cd-text-secondary">
          <ListChecks size={48} className="mx-auto mb-3 opacity-30" />
          <p>暂无待办，点击右上角新建</p>
        </div>
      )}

      {/* 创建弹窗 */}
      <TaskCreateModal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreated={() => { setShowCreate(false); load() }}
      />
    </div>
  )
}

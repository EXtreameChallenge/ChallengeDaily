import { useState, useEffect, useCallback } from 'react'
import { Plus, Check, Trash2, Clock, Target, Repeat, Flag, ListChecks } from 'lucide-react'
import { getTodos, createTodo, updateTodo, deleteTodo, type Todo } from '../api/client'
import { useToast } from '../components/Toast'

const CATEGORIES = ['开发', '会议', '沟通', '文档', '测试', '设计', '学习', '管理', '产品', '生活']
const MODE_LABELS = { timer: '计时任务', goal: '目标时长', habit: '习惯养成' }
const MODE_ICONS = { timer: Clock, goal: Target, habit: Repeat }
const PRIORITY_COLORS = ['text-red-400', 'text-orange-400', 'text-yellow-400', 'text-green-400', 'text-gray-400']

export default function Todos() {
  const [todos, setTodos] = useState<Todo[]>([])
  const [showForm, setShowForm] = useState(false)
  const [filter, setFilter] = useState<'all' | 'pending' | 'completed'>('all')
  const [form, setForm] = useState({ title: '', category: '开发', mode: 'timer' as Todo['mode'], target_min: 25, priority: 2, due_date: '', repeat_type: 'none', repeat_days: '' })
  const toast = useToast()

  const load = useCallback(async () => {
    try {
      const { todos: data } = await getTodos(filter === 'all' ? undefined : filter)
      setTodos(data)
    } catch (e) {
      toast.error('加载失败，请重试')
    }
  }, [filter, toast])

  useEffect(() => { load() }, [load])

  const handleCreate = async () => {
    if (!form.title.trim()) return
    try {
      await createTodo({
        title: form.title, category: form.category, mode: form.mode,
        target_min: form.target_min, priority: form.priority,
        due_date: form.due_date || undefined,
      })
      setForm({ title: '', category: '开发', mode: 'timer', target_min: 25, priority: 2, due_date: '', repeat_type: 'none', repeat_days: '' })
      setShowForm(false)
      load()
    } catch (e) {
      toast.error('操作失败，请重试')
    }
  }

  const handleToggle = async (todo: Todo) => {
    const newStatus = todo.status === 'completed' ? 'pending' : 'completed'
    try {
      await updateTodo(todo.id, { status: newStatus })
      load()
    } catch (e) {
      toast.error('更新失败，请重试')
    }
  }

  const handleDelete = async (id: number) => {
    if (!window.confirm('确定删除该待办？')) return
    try {
      await deleteTodo(id)
      load()
    } catch (e) {
      toast.error('删除失败，请重试')
    }
  }

  const pending = todos.filter(t => t.status !== 'completed')
  const completed = todos.filter(t => t.status === 'completed')

  return (
    <div className="min-h-screen p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-cd-text">待办清单</h1>
        <button onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-2 px-4 py-2 bg-cd-accent/20 text-cd-accent rounded-lg border border-cd-accent/30 hover:bg-cd-accent/30 transition">
          <Plus size={18} /> 新建待办
        </button>
      </div>

      {/* 筛选 */}
      <div className="flex gap-2 mb-4">
        {(['all', 'pending', 'completed'] as const).map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-lg text-sm transition ${filter === f ? 'bg-cd-accent/20 text-cd-accent' : 'bg-cd-bg-input text-cd-text-secondary'}`}>
            {f === 'all' ? '全部' : f === 'pending' ? '待完成' : '已完成'} ({f === 'all' ? todos.length : f === 'pending' ? pending.length : completed.length})
          </button>
        ))}
      </div>

      {/* 新建表单 */}
      {showForm && (
        <div className="bg-cd-bg-card rounded-xl p-4 border border-white/5 mb-4 space-y-3">
          <input type="text" value={form.title} onChange={e => setForm({ ...form, title: e.target.value })}
            placeholder="待办标题..." autoFocus
            className="w-full bg-cd-bg-input border border-white/5 rounded-lg px-4 py-2.5 text-cd-text focus:outline-none focus:border-cd-accent/40" />
          <div className="flex gap-2 flex-wrap">
            {(['timer', 'goal', 'habit'] as const).map(m => {
              const Icon = MODE_ICONS[m]
              return (
                <button key={m} onClick={() => setForm({ ...form, mode: m })}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm border ${form.mode === m ? 'bg-cd-accent/20 text-cd-accent border-cd-accent/30' : 'bg-cd-bg-input text-cd-text-secondary border-white/5'}`}>
                  <Icon size={14} /> {MODE_LABELS[m]}
                </button>
              )
            })}
          </div>
          <div className="flex gap-3 items-center flex-wrap">
            <select value={form.category} onChange={e => setForm({ ...form, category: e.target.value })}
              className="bg-cd-bg-input border border-white/5 rounded-lg px-3 py-2 text-cd-text text-sm">
              {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
            <div className="flex items-center gap-2">
              <span className="text-sm text-cd-text-secondary">目标</span>
              <input type="number" value={form.target_min} min="5" max="480" step="5"
                onChange={e => setForm({ ...form, target_min: parseInt(e.target.value) || 25 })}
                className="w-20 bg-cd-bg-input border border-white/5 rounded-lg px-2 py-2 text-cd-text text-sm text-center" />
              <span className="text-sm text-cd-text-secondary">分钟</span>
            </div>
            <div className="flex items-center gap-1">
              {[1, 2, 3, 4, 5].map(p => (
                <button key={p} onClick={() => setForm({ ...form, priority: p })}
                  className={`${form.priority === p ? 'scale-125' : ''} transition`}>
                  <Flag size={16} className={PRIORITY_COLORS[p - 1]} fill={form.priority >= p ? 'currentColor' : 'none'} />
                </button>
              ))}
            </div>
          </div>
          <button onClick={handleCreate}
            className="w-full py-2.5 bg-cd-accent/20 text-cd-accent rounded-lg border border-cd-accent/30 hover:bg-cd-accent/30 transition font-medium">
            创建待办
          </button>
        </div>
      )}

      {/* 待办列表 */}
      <div className="space-y-2">
        {todos.length === 0 && (
          <div className="text-center py-12 text-cd-text-secondary">
            <ListChecks size={48} className="mx-auto mb-3 opacity-30" />
            <p>暂无待办，点击右上角新建</p>
          </div>
        )}
        {todos.map(todo => {
          const Icon = MODE_ICONS[todo.mode]
          const progress = todo.target_min > 0 ? Math.min(100, (todo.progress_min / todo.target_min) * 100) : 0
          return (
            <div key={todo.id} className={`bg-cd-bg-card rounded-xl p-3 border border-white/5 flex items-center gap-3 ${todo.status === 'completed' ? 'opacity-50' : ''}`}>
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
                {todo.mode !== 'timer' && todo.target_min > 0 && (
                  <div className="mt-1.5 flex items-center gap-2">
                    <div className="flex-1 h-1.5 bg-cd-bg-input rounded-full overflow-hidden">
                      <div className="h-full bg-cd-accent/40 rounded-full" style={{ width: `${progress}%` }} />
                    </div>
                    <span className="text-xs text-cd-text-secondary tabular-nums">{todo.progress_min}/{todo.target_min}min</span>
                    {todo.pomodoro_count > 0 && <span className="text-xs text-cd-accent">🍅×{todo.pomodoro_count}</span>}
                  </div>
                )}
              </div>
              <span className="text-xs text-cd-text-secondary shrink-0">{todo.category}</span>
              <button onClick={() => handleDelete(todo.id)} className="text-cd-text-secondary hover:text-red-400 transition shrink-0">
                <Trash2 size={16} />
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}

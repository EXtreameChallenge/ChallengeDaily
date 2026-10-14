import { useState } from 'react'
import { Check, Clock, Trash2, Play, Calendar, Flame } from 'lucide-react'
import type { TodoV2 } from '../../api/client'
import { CATEGORY_COLORS } from '../../api/client'

const COLUMNS = [
  { key: 'pending', title: '待办', color: '#F0C040', bg: 'bg-amber-500/5' },
  { key: 'in_progress', title: '进行中', color: '#5B8DEF', bg: 'bg-blue-500/5' },
  { key: 'completed', title: '已完成', color: '#22c55e', bg: 'bg-green-500/5' },
] as const

function getCategoryColor(todo: TodoV2): string {
  if (todo.color) return todo.color
  return CATEGORY_COLORS[todo.category] || '#7B68EE'
}

interface KanbanViewProps {
  todos: TodoV2[]
  onStatusChange: (id: number, status: string) => void
  onDelete: (todo: TodoV2) => void
  onStartFocus: (todo: TodoV2) => void
}

export default function KanbanView({ todos, onStatusChange, onDelete, onStartFocus }: KanbanViewProps) {
  const [draggedId, setDraggedId] = useState<number | null>(null)
  const [dragOverCol, setDragOverCol] = useState<string | null>(null)

  const handleDragStart = (e: React.DragEvent, todoId: number) => {
    setDraggedId(todoId)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(todoId))
  }

  const handleDragOver = (e: React.DragEvent, colKey: string) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setDragOverCol(colKey)
  }

  const handleDrop = (e: React.DragEvent, colKey: string) => {
    e.preventDefault()
    const todoId = Number(e.dataTransfer.getData('text/plain'))
    if (todoId && draggedId === todoId) {
      onStatusChange(todoId, colKey)
    }
    setDraggedId(null)
    setDragOverCol(null)
  }

  const handleDragEnd = () => {
    setDraggedId(null)
    setDragOverCol(null)
  }

  return (
    <div className="grid grid-cols-3 gap-4 h-full">
      {COLUMNS.map(col => {
        const colTodos = todos.filter(t => {
          // 将没有明确状态的归入 pending
          const status = t.status || 'pending'
          if (col.key === 'pending') return status === 'pending'
          if (col.key === 'in_progress') return status === 'in_progress'
          if (col.key === 'completed') return status === 'completed'
          return false
        })

        return (
          <div
            key={col.key}
            className={`flex flex-col rounded-2xl border border-white/5 ${col.bg} ${dragOverCol === col.key ? 'ring-2 ring-cd-accent/40' : ''}`}
            onDragOver={(e) => handleDragOver(e, col.key)}
            onDrop={(e) => handleDrop(e, col.key)}
          >
            {/* Column header */}
            <div className="flex items-center justify-between px-3 py-2.5 border-b border-white/5">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full" style={{ background: col.color }} />
                <span className="text-sm font-medium text-cd-text">{col.title}</span>
                <span className="text-xs text-cd-text-tertiary">{colTodos.length}</span>
              </div>
            </div>

            {/* Cards */}
            <div className="flex-1 overflow-y-auto p-2 space-y-2 min-h-[200px]">
              {colTodos.map(todo => {
                const catColor = getCategoryColor(todo)
                const isCompleted = todo.status === 'completed'
                const estPom = todo.estimated_pomodoros || Math.ceil(todo.target_min / 25) || 1
                const completedPom = todo.pomodoro_count || 0
                const progress = todo.target_min > 0 ? Math.min(100, (todo.progress_min / todo.target_min) * 100) : 0

                return (
                  <div
                    key={todo.id}
                    draggable
                    onDragStart={(e) => handleDragStart(e, todo.id)}
                    onDragEnd={handleDragEnd}
                    className={`bg-cd-bg-card rounded-2xl border border-white/5 p-2.5 cursor-grab active:cursor-grabbing transition hover:border-white/10 hover:shadow-md ${draggedId === todo.id ? 'opacity-40' : ''} ${isCompleted ? 'opacity-60' : ''}`}
                    style={{ borderLeft: `3px solid ${catColor}` }}
                  >
                    {/* Title */}
                    <div className="flex items-start gap-1.5 mb-1.5">
                      <span className={`text-xs font-medium leading-tight flex-1 ${isCompleted ? 'line-through text-cd-text-secondary' : 'text-cd-text'}`}>
                        {todo.title}
                      </span>
                    </div>

                    {/* Pomodoro progress */}
                    <div className="flex items-center gap-1 mb-1.5">
                      <span className="text-xs flex items-center flex-wrap gap-0.5">
                        {Array.from({ length: Math.min(estPom, 6) }, (_, i) => (
                          <span key={i} className={i < completedPom ? '' : 'opacity-25'}>🍅</span>
                        ))}
                        {estPom > 6 && <span className="text-[9px] text-cd-text-tertiary">+{estPom - 6}</span>}
                      </span>
                      <span className="text-[10px] text-cd-text-tertiary tabular-nums">{completedPom}/{estPom}</span>
                    </div>

                    {/* Progress bar */}
                    <div className="h-1 rounded-full bg-cd-bg-secondary overflow-hidden mb-2">
                      <div className="h-full rounded-full transition-all duration-500"
                        style={{ width: `${progress}%`, background: catColor }} />
                    </div>

                    {/* Footer */}
                    <div className="flex items-center justify-between gap-1">
                      <div className="flex items-center gap-1 flex-wrap min-w-0">
                        <span className="text-[9px] px-1.5 py-0.5 rounded-lg font-medium"
                          style={{ background: catColor + '20', color: catColor }}>
                          {todo.category}
                        </span>
                        {todo.assigned_date && (
                          <span className="text-[9px] text-cd-text-tertiary flex items-center gap-0.5">
                            <Flame size={9} />{todo.assigned_date.slice(5)}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-0.5 shrink-0">
                        {!isCompleted && (
                          <button
                            onClick={() => onStartFocus(todo)}
                            className="p-1 rounded-lg text-cd-accent hover:bg-cd-accent/10 transition"
                            title="开始专注"
                          >
                            <Play size={11} />
                          </button>
                        )}
                        <button
                          onClick={() => onDelete(todo)}
                          className="p-1 rounded-lg text-cd-text-tertiary hover:text-red-400 transition"
                          title="删除"
                        >
                          <Trash2 size={11} />
                        </button>
                      </div>
                    </div>
                  </div>
                )
              })}

              {colTodos.length === 0 && (
                <div className="flex items-center justify-center h-20 text-xs text-cd-text-tertiary opacity-50">
                  拖拽任务到此处
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

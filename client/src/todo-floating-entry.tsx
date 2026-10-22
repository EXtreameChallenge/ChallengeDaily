import { useState, useEffect, useCallback } from 'react'
import { createRoot } from 'react-dom/client'
import './todo-floating.css'

interface Todo {
  id: number
  title: string
  done: boolean
  priority: string
  dueDate?: string
}

function TodoFloatingApp() {
  const [expanded, setExpanded] = useState(false)
  const [todos, setTodos] = useState<Todo[]>([])
  const [loading, setLoading] = useState(false)
  const [dragOffset, setDragOffset] = useState<{ x: number; y: number } | null>(null)

  // 加载待办列表
  const fetchTodos = useCallback(async () => {
    try {
      setLoading(true)
      const token = localStorage.getItem('cd_api_token') || ''
      const res = await fetch('http://127.0.0.1:59300/api/todos?limit=10&status=active', {
        headers: { 'X-API-Token': token },
      })
      if (res.ok) {
        const data = await res.json()
        setTodos(Array.isArray(data) ? data.slice(0, 8) : [])
      }
    } catch {
      // 后端未启动时静默
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchTodos()
    const timer = setInterval(fetchTodos, 30000)
    return () => clearInterval(timer)
  }, [fetchTodos])

  // 拖拽
  const handleMouseDown = (e: React.MouseEvent) => {
    setDragOffset({ x: e.clientX, y: e.clientY })
  }
  useEffect(() => {
    if (!dragOffset) return
    const handleMove = (e: MouseEvent) => {
      window.electronAPI?.todoFloating?.dragStart?.({
        mouseX: e.movementX,
        mouseY: e.movementY,
      })
    }
    const handleUp = () => {
      setDragOffset(null)
      window.electronAPI?.todoFloating?.dragEnd?.()
    }
    window.addEventListener('mousemove', handleMove)
    window.addEventListener('mouseup', handleUp)
    return () => {
      window.removeEventListener('mousemove', handleMove)
      window.removeEventListener('mouseup', handleUp)
    }
  }, [dragOffset])

  const pendingCount = todos.filter(t => !t.done).length

  return (
    <div className={`tf-window ${expanded ? 'tf-expanded' : ''}`}>
      {/* 标题栏 - 拖拽区域 */}
      <div className="tf-header" onMouseDown={handleMouseDown}>
        <div className="tf-header-left">
          <span className="tf-icon">📋</span>
          <span className="tf-title">待办</span>
          {pendingCount > 0 && <span className="tf-badge">{pendingCount}</span>}
        </div>
        <div className="tf-header-right">
          <button
            className="tf-btn"
            onClick={(e) => { e.stopPropagation(); setExpanded(!expanded) }}
            title={expanded ? '折叠' : '展开'}
          >
            {expanded ? '▾' : '▸'}
          </button>
        </div>
      </div>

      {/* 折叠状态：只显示计数 */}
      {!expanded && (
        <div className="tf-collapsed" onClick={() => setExpanded(true)}>
          <span className="tf-collapsed-text">
            {loading ? '...' : pendingCount > 0 ? `${pendingCount} 项待办` : '✓ 全部完成'}
          </span>
        </div>
      )}

      {/* 展开状态：显示列表 */}
      {expanded && (
        <div className="tf-list">
          {todos.length === 0 && !loading && (
            <div className="tf-empty">暂无待办</div>
          )}
          {todos.map(todo => (
            <div key={todo.id} className={`tf-item ${todo.done ? 'tf-item-done' : ''}`}>
              <span className={`tf-checkbox ${todo.done ? 'tf-checked' : ''}`}>
                {todo.done ? '✓' : ''}
              </span>
              <span className="tf-item-title">{todo.title}</span>
            </div>
          ))}
          <div
            className="tf-open-main"
            onClick={() => window.electronAPI?.todoFloating?.openMainTodo?.()}
          >
            打开完整待办 →
          </div>
        </div>
      )}
    </div>
  )
}

createRoot(document.getElementById('root')!).render(<TodoFloatingApp />)

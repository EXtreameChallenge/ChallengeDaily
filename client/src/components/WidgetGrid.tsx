import { useState, useEffect, useRef, type ReactNode } from 'react'
import { Edit3, Check, RotateCcw, GripVertical } from 'lucide-react'

export interface WidgetConfig {
  id: string
  title: string
  defaultVisible: boolean
  defaultColSpan?: number // 1-4 (out of 12 grid)
  defaultRowSpan?: number
}

interface WidgetGridProps {
  storageKey: string
  widgets: WidgetConfig[]
  renderWidget: (id: string) => ReactNode
}

interface LayoutState {
  order: string[]
  visible: Set<string>
}

function loadLayout(key: string, defaultWidgets: WidgetConfig[]): LayoutState {
  try {
    const raw = localStorage.getItem(key)
    if (raw) {
      const parsed = JSON.parse(raw)
      return {
        order: parsed.order || defaultWidgets.map(w => w.id),
        visible: new Set(parsed.visible || defaultWidgets.filter(w => w.defaultVisible).map(w => w.id)),
      }
    }
  } catch { /* ignore */ }
  return {
    order: defaultWidgets.map(w => w.id),
    visible: new Set(defaultWidgets.filter(w => w.defaultVisible).map(w => w.id)),
  }
}

function saveLayout(key: string, state: LayoutState) {
  try {
    localStorage.setItem(key, JSON.stringify({
      order: state.order,
      visible: [...state.visible],
    }))
  } catch { /* ignore */ }
}

export default function WidgetGrid({ storageKey, widgets, renderWidget }: WidgetGridProps) {
  const [editMode, setEditMode] = useState(false)
  const [layout, setLayout] = useState<LayoutState>(() => loadLayout(storageKey, widgets))
  const [draggedId, setDraggedId] = useState<string | null>(null)
  const [dragOverId, setDragOverId] = useState<string | null>(null)
  const dragCounter = useRef(0)

  useEffect(() => {
    saveLayout(storageKey, layout)
  }, [layout, storageKey])

  // 当 widgets 列表变化时，合并新增的 widget
  useEffect(() => {
    setLayout(prev => {
      const existingIds = new Set(prev.order)
      const newWidgets = widgets.filter(w => !existingIds.has(w.id))
      if (newWidgets.length === 0) return prev
      return {
        order: [...prev.order, ...newWidgets.map(w => w.id)],
        visible: new Set([...prev.visible, ...newWidgets.filter(w => w.defaultVisible).map(w => w.id)]),
      }
    })
  }, [widgets])

  const handleDragStart = (e: React.DragEvent, id: string) => {
    setDraggedId(id)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', id)
  }

  const handleDragOver = (e: React.DragEvent, id: string) => {
    e.preventDefault()
    if (draggedId && draggedId !== id) {
      setDragOverId(id)
    }
  }

  const handleDrop = (e: React.DragEvent, targetId: string) => {
    e.preventDefault()
    if (!draggedId || draggedId === targetId) return
    setLayout(prev => {
      const newOrder = [...prev.order]
      const fromIdx = newOrder.indexOf(draggedId)
      const toIdx = newOrder.indexOf(targetId)
      if (fromIdx === -1 || toIdx === -1) return prev
      newOrder.splice(fromIdx, 1)
      newOrder.splice(toIdx, 0, draggedId)
      return { ...prev, order: newOrder }
    })
    setDraggedId(null)
    setDragOverId(null)
  }

  const toggleVisible = (id: string) => {
    setLayout(prev => {
      const newVisible = new Set(prev.visible)
      if (newVisible.has(id)) newVisible.delete(id)
      else newVisible.add(id)
      return { ...prev, visible: newVisible }
    })
  }

  const resetLayout = () => {
    const defaultLayout: LayoutState = {
      order: widgets.map(w => w.id),
      visible: new Set(widgets.filter(w => w.defaultVisible).map(w => w.id)),
    }
    setLayout(defaultLayout)
  }

  const widgetMap = new Map(widgets.map(w => [w.id, w]))

  return (
    <div>
      {/* Toolbar */}
      <div className="flex items-center justify-end gap-2 mb-4">
        {editMode && (
          <button
            onClick={resetLayout}
            className="flex items-center gap-1.5 text-xs text-cd-text-tertiary hover:text-cd-text transition px-2 py-1 rounded-2xl hover:bg-cd-surface-elevated"
          >
            <RotateCcw size={13} /> 重置布局
          </button>
        )}
        <button
          onClick={() => setEditMode(!editMode)}
          className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-2xl transition border ${
            editMode
              ? 'bg-cd-green/10 text-cd-green border-cd-green/20'
              : 'text-cd-text-secondary border-cd-border hover:bg-cd-surface-elevated'
          }`}
        >
          {editMode ? <><Check size={14} /> 完成编辑</> : <><Edit3 size={14} /> 编辑布局</>}
        </button>
      </div>

      {/* Widget grid */}
      <div className="space-y-4">
        {layout.order
          .filter(id => editMode || layout.visible.has(id))
          .map(id => {
            const widget = widgetMap.get(id)
            if (!widget) return null
            const isVisible = layout.visible.has(id)
            const isDragged = draggedId === id
            const isDragOver = dragOverId === id

            return (
              <div
                key={id}
                draggable={editMode}
                onDragStart={(e) => editMode && handleDragStart(e, id)}
                onDragOver={(e) => editMode && handleDragOver(e, id)}
                onDrop={(e) => editMode && handleDrop(e, id)}
                onDragEnd={() => { setDraggedId(null); setDragOverId(null) }}
                className={`relative transition ${isDragged ? 'opacity-40' : ''} ${isDragOver ? 'ring-2 ring-cd-green/40 rounded-xl' : ''} ${editMode ? 'cursor-grab active:cursor-grabbing' : ''}`}
              >
                {/* Edit mode overlay */}
                {editMode && (
                  <div className="absolute top-2 right-2 z-10 flex items-center gap-1">
                    <button
                      onClick={() => toggleVisible(id)}
                      className={`px-2 py-1 rounded-lg text-[10px] font-medium transition ${
                        isVisible
                          ? 'bg-cd-green/15 text-cd-green'
                          : 'bg-cd-bg-secondary text-cd-text-tertiary'
                      }`}
                    >
                      {isVisible ? '显示中' : '已隐藏'}
                    </button>
                    <div className="flex items-center gap-0.5 px-1.5 py-1 rounded-lg bg-cd-surface-elevated text-cd-text-tertiary">
                      <GripVertical size={12} />
                    </div>
                  </div>
                )}

                {/* Widget content */}
                {isVisible && renderWidget(id)}
              </div>
            )
          })}
      </div>
    </div>
  )
}

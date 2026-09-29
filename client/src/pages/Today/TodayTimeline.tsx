import { useState, useMemo, useRef, useEffect } from 'react'
import dayjs from 'dayjs'
import {
  CATEGORY_COLORS,
  type Activity,
  type Todo,
  getAppIconUrl,
} from '../../api/client'
import { Clock, ChevronDown, ChevronRight, Play, CheckCircle2, Circle } from 'lucide-react'

/**
 * 今日时间线组件
 * 设计理念：时间线即界面（Timeline as Interface）
 * - 已过时段：灰色，可点击展开详情
 * - 当前时段：高亮，实时更新
 * - 未来时段：虚线，显示计划任务
 *
 * 科学依据：
 * - 认知负荷理论：线性时间线符合人对时间的自然认知图式，降低外在认知负荷
 * - 蔡格尼克效应：未完成任务在时间线上可见，外化到系统而非占用大脑
 */

type TimelineItem = {
  id: string
  type: 'activity' | 'todo' | 'break' | 'meeting'
  time: string
  endTime?: string
  category?: string
  title: string
  subtitle?: string
  appName?: string
  status?: 'done' | 'doing' | 'planned'
  todoId?: number
  durationMin?: number
  raw?: Activity | Todo
}

interface TodayTimelineProps {
  activities: Activity[]
  todos: Todo[]
  currentActivity?: Activity | null
  onStartTodo?: (todo: Todo) => void
  onCompleteTodo?: (todo: Todo) => void
}

export default function TodayTimeline({
  activities,
  todos,
  currentActivity,
  onStartTodo,
  onCompleteTodo,
}: TodayTimelineProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [iconUrls, setIconUrls] = useState<Record<string, string>>({})
  const currentRef = useRef<HTMLDivElement>(null)

  // 将活动和待办合并为时间线
  const items = useMemo<TimelineItem[]>(() => {
    const list: TimelineItem[] = []

    // 已完成的活动
    for (const act of activities) {
      const time = dayjs(act.timestamp).format('HH:mm')
      list.push({
        id: `act-${act.id}`,
        type: 'activity',
        time,
        category: act.category,
        title: act.ai_summary || act.app_name || '活动',
        subtitle: act.window_title,
        appName: act.app_name,
        status: 'done',
        durationMin: act.interval_sec ? Math.round(act.interval_sec / 60) : undefined,
        raw: act,
      })
    }

    // 未完成的待办（计划中）
    for (const todo of todos) {
      if (todo.status === 'completed') continue
      const scheduledTime = todo.due_date ? dayjs(todo.due_date).format('HH:mm') : '待定'
      list.push({
        id: `todo-${todo.id}`,
        type: 'todo',
        time: scheduledTime,
        title: todo.title,
        subtitle: todo.target_min ? `目标 ${todo.target_min}分钟` : undefined,
        status: 'planned',
        todoId: todo.id,
        raw: todo,
      })
    }

    // 按时间排序
    return list.sort((a, b) => {
      if (a.time === '待定') return 1
      if (b.time === '待定') return -1
      return a.time.localeCompare(b.time)
    })
  }, [activities, todos])

  // 找到当前时间对应的位置，自动滚动
  useEffect(() => {
    if (currentRef.current) {
      currentRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [])

  // 加载应用图标
  useEffect(() => {
    const appNames = [...new Set(items.filter(i => i.appName).map(i => i.appName!))]
    if (appNames.length === 0) return
    let cancelled = false
    ;(async () => {
      const map: Record<string, string> = {}
      await Promise.all(
        appNames.map(async (name) => {
          try {
            map[name] = await getAppIconUrl(name)
          } catch {
            map[name] = ''
          }
        }),
      )
      if (!cancelled) setIconUrls(map)
    })()
    return () => { cancelled = true }
  }, [items])

  const now = dayjs().format('HH:mm')

  const getCategoryColor = (category?: string) => {
    if (!category) return 'var(--cd-text-tertiary)'
    return CATEGORY_COLORS[category] || 'var(--cd-text-tertiary)'
  }

  const getStatusIcon = (item: TimelineItem) => {
    if (item.status === 'done') return <CheckCircle2 size={14} className="text-cd-green" />
    if (item.status === 'doing') return <Clock size={14} className="text-cd-green animate-pulse" />
    return <Circle size={14} className="text-cd-text-tertiary" />
  }

  return (
    <div className="relative">
      {/* 时间线标题 */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-cd-text flex items-center gap-2">
          <Clock size={14} className="text-cd-green" />
          今日时间线
        </h3>
        <span className="text-xs text-cd-text-tertiary">
          现在 {now} · {items.filter(i => i.status === 'done').length} 项已完成
        </span>
      </div>

      {/* 时间线主体 */}
      <div className="relative pl-6">
        {/* 垂直轴线 */}
        <div className="absolute left-[7px] top-2 bottom-2 w-px bg-cd-border" />

        <div className="space-y-1">
          {items.length === 0 && (
            <div className="text-center py-6 text-cd-text-tertiary text-sm">
              <div className="text-4xl mb-3">⏳</div>
              正在记录你的活动，稍等片刻即可看到时间线
            </div>
          )}

          {items.map((item, idx) => {
            const isExpanded = expandedId === item.id
            const isCurrent = item.status === 'doing' ||
              (currentActivity && item.id === `act-${currentActivity.id}`)
            const color = getCategoryColor(item.category)

            return (
              <div key={item.id} ref={isCurrent ? currentRef : undefined}>
                {/* 时间线节点 */}
                <div
                  className={`relative flex items-start gap-3 py-2 px-2 rounded-2xl cursor-pointer transition-colors ${
                    isCurrent ? 'bg-cd-green/5 ring-1 ring-cd-green/20' : 'hover:bg-cd-hover'
                  }`}
                  onClick={() => setExpandedId(isExpanded ? null : item.id)}
                >
                  {/* 节点圆点 */}
                  <div
                    className="absolute -left-[19px] top-3 w-3.5 h-3.5 rounded-full border-2 flex items-center justify-center"
                    style={{
                      borderColor: isCurrent ? 'var(--cd-green)' : color,
                      background: isCurrent ? 'var(--cd-green)' : 'var(--cd-bg)',
                    }}
                  >
                    {isCurrent && <div className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />}
                  </div>

                  {/* 时间 */}
                  <div className="w-12 shrink-0 pt-0.5">
                    <span className={`text-xs font-mono ${
                      item.status === 'planned' ? 'text-cd-text-tertiary' : 'text-cd-text-secondary'
                    }`}>
                      {item.time}
                    </span>
                  </div>

                  {/* 内容 */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      {getStatusIcon(item)}
                      <span
                        className={`text-sm truncate ${
                          item.status === 'planned'
                            ? 'text-cd-text-tertiary'
                            : item.status === 'doing'
                            ? 'text-cd-text font-medium'
                            : 'text-cd-text'
                        }`}
                      >
                        {item.title}
                      </span>
                      {item.durationMin && (
                        <span className="text-xs text-cd-text-tertiary shrink-0">
                          {item.durationMin}分钟
                        </span>
                      )}
                    </div>
                    {item.subtitle && (
                      <p className="text-xs text-cd-text-tertiary truncate mt-0.5 ml-5">
                        {item.subtitle}
                      </p>
                    )}

                    {/* 展开详情 */}
                    {isExpanded && item.raw && (
                      <div className="mt-2 ml-5 p-3 bg-cd-bg-secondary rounded-2xl text-xs space-y-1.5 animate-fade-in">
                        {'category' in item.raw && (
                          <div className="flex items-center gap-2">
                            <span className="text-cd-text-tertiary">分类：</span>
                            <span
                              className="px-1.5 py-0.5 rounded-lg text-white"
                              style={{ background: getCategoryColor(item.raw.category) }}
                            >
                              {item.raw.category}
                            </span>
                          </div>
                        )}
                        {'app_name' in item.raw && item.raw.app_name && (
                          <div className="flex items-center gap-2">
                            <span className="text-cd-text-tertiary">应用：</span>
                            <span className="text-cd-text">{item.raw.app_name}</span>
                          </div>
                        )}
                        {'window_title' in item.raw && item.raw.window_title && (
                          <div>
                            <span className="text-cd-text-tertiary">窗口：</span>
                            <span className="text-cd-text">{item.raw.window_title}</span>
                          </div>
                        )}
                        {'ai_detail' in item.raw && item.raw.ai_detail && (
                          <div>
                            <span className="text-cd-text-tertiary">AI 详情：</span>
                            <p className="text-cd-text mt-0.5">{item.raw.ai_detail}</p>
                          </div>
                        )}

                        {/* 待办操作按钮 */}
                        {item.type === 'todo' && item.status === 'planned' && onStartTodo && (
                          <div className="flex gap-2 mt-2 pt-2 border-t border-cd-border">
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                onStartTodo(item.raw as Todo)
                              }}
                              className="flex items-center gap-1 bg-cd-green text-white px-3 py-1.5 rounded-lg text-xs font-medium hover:opacity-90 transition"
                            >
                              <Play size={12} /> 开始专注
                            </button>
                            {onCompleteTodo && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  onCompleteTodo(item.raw as Todo)
                                }}
                                className="flex items-center gap-1 border border-cd-border text-cd-text-secondary px-3 py-1.5 rounded-lg text-xs hover:bg-cd-hover transition"
                              >
                                <CheckCircle2 size={12} /> 标记完成
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  {/* 展开箭头 */}
                  <div className="shrink-0 pt-1">
                    {isExpanded ? (
                      <ChevronDown size={14} className="text-cd-text-tertiary" />
                    ) : (
                      <ChevronRight size={14} className="text-cd-text-tertiary" />
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

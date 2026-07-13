import { useState, useCallback, useEffect, memo, useMemo, useRef } from 'react'
import { getActivities, searchActivities, deleteActivity, undoDeleteActivity, getAppIconUrl, CATEGORY_COLORS, CATEGORIES, type Activity, type VisibleWindow } from '../api/client'
import { CategoryFilter, useAsyncData, ApiErrorDisplay, useNewIds, RefreshIndicator } from '../components/shared'
import { useToast } from '../components/Toast'
import { useEventStream } from '../hooks/useEventStream'
import ActivityCreateModal from '../components/ActivityCreateModal'
import ActivityEditModal from '../components/ActivityEditModal'
import { Search, Pencil, X, Plus, Trash2, Loader2 } from 'lucide-react'
import dayjs from 'dayjs'

// T6: 虚拟滚动常量
const ITEM_HEIGHT = 80
const VISIBLE_BUFFER = 50
// T6: 图标缓存 TTL（7 天）
const ICON_CACHE_TTL = 7 * 24 * 60 * 60 * 1000

export default function Timeline() {
  const toast = useToast()
  const [selectedDate, setSelectedDate] = useState(dayjs().format('YYYY-MM-DD'))
  const [filterCategory, setFilterCategory] = useState<string>('全部')
  // 搜索
  const [searchQuery, setSearchQuery] = useState('')
  const [isSearching, setIsSearching] = useState(false)
  // 编辑
  const [editingActivity, setEditingActivity] = useState<Activity | null>(null)
  // 手动补录
  const [showAdd, setShowAdd] = useState(false)

  const { data: activitiesData, loading, error, refresh: refreshList, refreshing } = useAsyncData(
    () => getActivities(selectedDate),
    [selectedDate],
    60000, // T6: 从 30s 调整为 60s，配合 SSE 事件驱动增量更新
  )
  const activities = activitiesData?.activities ?? []
  const newIds = useNewIds(activities, (a) => a.id)

  const [searchResults, setSearchResults] = useState<Activity[] | null>(null)
  // 应用图标缓存：app_name -> iconUrl
  const [iconUrls, setIconUrls] = useState<Record<string, string>>({})
  // T6: 图标内存缓存（TTL 7 天），避免重复请求
  const iconCache = useRef(new Map<string, { icon: string; expire: number }>())

  // T6: 虚拟滚动范围
  const [visibleRange, setVisibleRange] = useState({ start: 0, end: VISIBLE_BUFFER })
  const scrollContainerRef = useRef<HTMLDivElement>(null)

  // T6: SSE 事件流 — 增量更新（新活动到达时立即刷新，替代高频轮询）
  const { event: sseEvent } = useEventStream()
  const lastRefreshRef = useRef(0)
  useEffect(() => {
    if (!sseEvent) return
    // activity_change 事件：有新活动写入，触发增量刷新
    if (sseEvent.type === 'activity_change') {
      const now = Date.now()
      // 防抖：1s 内最多刷新一次，避免批量写入时频繁请求
      if (now - lastRefreshRef.current > 1000) {
        lastRefreshRef.current = now
        refreshList()
      }
    }
  }, [sseEvent, refreshList])

  const timelineAppsKey = useMemo(
    () => (searchResults ?? activities).map((a) => [a.app_name, ...(a.windows || []).map((w) => w.app_name)].join('|')).join(';'),
    [searchResults, activities],
  )

  // T6: 批量加载应用图标（前台应用 + 多窗口中每个应用），优先读缓存
  useEffect(() => {
    const baseList = searchResults ?? activities
    const apps = Array.from(new Set(baseList.flatMap((a) => [
      a.app_name,
      ...(a.windows || []).map((w) => w.app_name),
    ])))
    if (!apps.length) return
    let cancelled = false
    const now = Date.now()
    // 先读缓存，收集需要拉取的应用
    const cachedMap: Record<string, string> = {}
    const toFetch: string[] = []
    for (const name of apps) {
      if (!name) continue
      const cached = iconCache.current.get(name)
      if (cached && cached.expire > now) {
        cachedMap[name] = cached.icon
      } else {
        toFetch.push(name)
      }
    }
    // 立即应用缓存命中
    if (Object.keys(cachedMap).length > 0) {
      setIconUrls((prev) => ({ ...prev, ...cachedMap }))
    }
    if (!toFetch.length) return
    ;(async () => {
      const map: Record<string, string> = {}
      await Promise.all(
        toFetch.map(async (name) => {
          if (!name) return
          try {
            const icon = await getAppIconUrl(name)
            map[name] = icon
            // 写入缓存，TTL 7 天
            iconCache.current.set(name, { icon, expire: now + ICON_CACHE_TTL })
          } catch {
            map[name] = ''
          }
        }),
      )
      if (!cancelled) setIconUrls((prev) => ({ ...prev, ...map }))
    })()
    return () => { cancelled = true }
  }, [timelineAppsKey])

  const handleSearch = async () => {
    if (!searchQuery.trim()) {
      setSearchResults(null)
      return
    }
    setIsSearching(true)
    try {
      const results = await searchActivities(searchQuery, selectedDate)
      setSearchResults(results)
    } catch (err) {
      console.error('Search failed:', err)
    } finally {
      setIsSearching(false)
    }
  }

  const handleClearSearch = () => {
    setSearchQuery('')
    setSearchResults(null)
  }

  const handleDelete = async (act: Activity) => {
    if (!window.confirm('确定删除该活动记录？')) return
    try {
      await deleteActivity(act.id)
      refreshList()
      toast.success('已删除记录', {
        action: {
          label: '撤销',
          onClick: async () => {
            try {
              await undoDeleteActivity(act.id)
              refreshList()
              toast.success('已恢复记录')
            } catch {
              toast.error('恢复失败')
            }
          }
        }
      })
    } catch (err) {
      console.error('Failed to delete activity:', err)
      toast.error('删除失败，请重试')
    }
  }

  const baseList = searchResults ?? activities
  const filtered = filterCategory === '全部'
    ? baseList
    : baseList.filter((a) => a.category === filterCategory)

  // 按时间轴分组：按小时聚合，每条记录显示具体几点几分
  const grouped: Record<string, Activity[]> = {}
  filtered.forEach((act) => {
    const hour = dayjs(act.timestamp).format('HH:00')
    if (!grouped[hour]) grouped[hour] = []
    grouped[hour].push(act)
  })
  // 按时间正序排列（早 → 晚）
  const sortedHours = Object.entries(grouped).sort(([a], [b]) => a.localeCompare(b))

  // 时间线主轴：以时间为第一维度，每条记录以时间开头
  const timelineItems = filtered.map((act) => ({
    act,
    time: dayjs(act.timestamp).format('HH:mm'),
  }))

  // T6: 虚拟滚动 — 滚动时更新可见范围
  const handleScroll = useCallback((e: React.UIEvent) => {
    const scrollTop = (e.target as HTMLElement).scrollTop
    const start = Math.floor(scrollTop / ITEM_HEIGHT)
    const end = Math.min(start + VISIBLE_BUFFER, timelineItems.length)
    setVisibleRange((prev) => {
      if (prev.start === start && prev.end === end) return prev
      return { start, end }
    })
  }, [timelineItems.length])

  // T6: 切换日期/筛选时重置虚拟滚动范围
  useEffect(() => {
    setVisibleRange({ start: 0, end: VISIBLE_BUFFER })
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = 0
    }
  }, [selectedDate, filterCategory])

  // 切换日期时重置搜索
  const handleDateChange = (date: string) => {
    setSelectedDate(date)
    setSearchResults(null)
    setSearchQuery('')
  }

  return (
    <div className="space-y-5 content-stable">
      {/* ─── 头部 ─────────────────────────── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-cd-text">工作时间线</h1>
          <RefreshIndicator refreshing={refreshing} />
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowAdd(true)}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-cd-green text-white hover:bg-cd-green-dark transition-colors"
          >
            <Plus size={14} />
            手动补录
          </button>
          <input
            type="date"
            value={selectedDate}
            onChange={(e) => handleDateChange(e.target.value)}
            className="bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green transition-colors"
          />
        </div>
      </div>

      {/* ─── 手动补录 / 编辑弹窗 ─────────────────── */}
      <ActivityCreateModal open={showAdd} onClose={() => setShowAdd(false)} onCreated={refreshList} />
      <ActivityEditModal
        open={editingActivity !== null}
        onClose={() => setEditingActivity(null)}
        activity={editingActivity}
        onSaved={refreshList}
      />

      {/* ─── 搜索栏 ─────────────────────── */}
      <div className="flex items-center gap-2">
        <div className="flex-1 relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-cd-text-tertiary" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="搜索窗口标题或摘要..."
            className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg pl-9 pr-3 py-1.5 text-sm focus:outline-none focus:border-cd-green transition-colors"
          />
          {searchQuery && (
            <button
              onClick={handleClearSearch}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-cd-text-tertiary hover:text-cd-text"
            >
              <X size={14} />
            </button>
          )}
        </div>
        <button
          onClick={handleSearch}
          disabled={isSearching}
          className="px-4 py-1.5 rounded-lg text-xs font-medium bg-cd-green text-white hover:bg-cd-green-dark disabled:opacity-50 transition-colors"
        >
          {isSearching ? <Loader2 size={12} className="animate-spin" /> : '搜索'}
        </button>
      </div>

      {/* ─── 分类筛选 ──────────────────────── */}
      <CategoryFilter selected={filterCategory} onChange={setFilterCategory} />

      {/* ─── 时间线内容（时间为主轴）────────── */}
      {error ? (
        <ApiErrorDisplay error={error} onRetry={refreshList} />
      ) : loading ? (
        <div className="text-cd-text-tertiary animate-pulse">加载中...</div>
      ) : filtered.length === 0 ? (
        <div className="text-cd-text-tertiary text-center py-16">
          {searchQuery ? `未找到与「${searchQuery}」相关的记录` : '暂无活动记录'}
        </div>
      ) : (
        <div
          ref={scrollContainerRef}
          className="overflow-y-auto"
          style={{ maxHeight: 'calc(100vh - 280px)' }}
          onScroll={handleScroll}
        >
          {/* T6: 虚拟滚动 — 顶部占位 spacer */}
          <div style={{ height: visibleRange.start * ITEM_HEIGHT, flexShrink: 0 }} />
          {/* T6: 仅渲染可见范围内的项 */}
          {timelineItems.slice(visibleRange.start, visibleRange.end).map(({ act, time }) => (
            <div key={act.id} style={{ height: ITEM_HEIGHT, flexShrink: 0 }}>
              <TimelineEntry
                activity={act}
                displayTime={time}
                iconUrl={iconUrls[act.app_name] || ''}
                allIconUrls={iconUrls}
                onStartEdit={setEditingActivity}
                onDelete={handleDelete}
                isNew={newIds.has(act.id)}
              />
            </div>
          ))}
          {/* T6: 虚拟滚动 — 底部占位 spacer */}
          <div style={{ height: Math.max(0, (timelineItems.length - visibleRange.end) * ITEM_HEIGHT), flexShrink: 0 }} />
        </div>
      )}
    </div>
  )
}

function getDisplayAppName(appName: string): string {
  const lower = appName.toLowerCase()
  const map: Record<string, string> = {
    'trae.exe': 'TRAE SOLO CN',
    'trae solo cn.exe': 'TRAE SOLO CN',
    'trae-solo-cn.exe': 'TRAE SOLO CN',
  }
  if (map[lower]) return map[lower]
  return appName.replace(/\.exe$/i, '')
}

function AppIcon({ name, iconUrl, size = 24 }: { name: string; iconUrl: string; size?: number }) {
  const defaultIcon = import.meta.env.DEV ? '/icon.png' : './icon.png'
  const displayIcon = iconUrl || defaultIcon
  return (
    <div
      className="rounded-lg bg-cd-card border border-cd-border-light flex items-center justify-center shrink-0 overflow-hidden"
      style={{ width: size + 8, height: size + 8 }}
      title={name}
    >
      <img
        src={displayIcon}
        alt=""
        className="object-contain"
        style={{ width: size, height: size }}
        onError={(e) => { e.currentTarget.src = defaultIcon }}
      />
    </div>
  )
}

const TimelineEntry = memo(function TimelineEntry({
  activity,
  displayTime,
  iconUrl,
  allIconUrls,
  onStartEdit,
  onDelete,
  isNew = false,
}: {
  activity: Activity
  displayTime: string
  iconUrl: string
  allIconUrls: Record<string, string>
  onStartEdit: (act: Activity) => void
  onDelete: (act: Activity) => void
  isNew?: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  const catColor = CATEGORY_COLORS[activity.category] || 'var(--cd-text-tertiary)'
  const duration =
    activity.duration_min >= 60
      ? `${(activity.duration_min / 60).toFixed(1)}h`
      : `${Math.round(activity.duration_min)}min`

  // 显示该时间点所有被记录的并行窗口（面积较大的可见窗口），前台排在最前
  const windows = (activity.windows || []).filter((w) => w.app_name).slice(0, 4)
  // 主标题栏显示所有并行应用，没有时回退到主导应用
  const foregroundApps = windows.length > 0 ? windows : [{ app_name: activity.app_name } as VisibleWindow]

  return (
    <div
      className={`timeline-entry group ${isNew ? 'animate-blur-fade-in' : 'content-stable'}`}
      style={{ '--cat-color': catColor } as React.CSSProperties}
    >
      {/* 时间为主轴：左侧时间列 */}
      <div className="flex items-start gap-3 py-1.5 cursor-pointer" onClick={() => setExpanded(!expanded)}>
        {/* 时间列 */}
        <div className="w-14 shrink-0 text-right pt-0.5">
          <span className="text-sm font-mono font-semibold text-cd-text">{displayTime}</span>
        </div>

        {/* 内容列 */}
        <div className="flex-1 min-w-0 border-l-2 border-cd-border-light pl-3">
          <div className="flex items-start gap-2 flex-wrap">
            {foregroundApps.map((w, idx) => {
              const appName = w.app_name
              const wicon = allIconUrls[appName] || iconUrl
              const shortName = getDisplayAppName(appName)
              return (
                <div key={appName + idx} className="flex items-center gap-1.5 bg-cd-bg-secondary rounded-full pl-1 pr-2 py-0.5 border border-cd-border-light max-w-full" title={shortName}>
                  <AppIcon name={appName} iconUrl={wicon} size={18} />
                  <span className="text-xs font-medium text-cd-text truncate">{shortName}</span>
                </div>
              )
            })}
            <span
              className="px-2 py-0.5 rounded-full text-[10px] font-medium shrink-0"
              style={{ background: catColor + '18', color: catColor }}
            >
              {activity.category}
            </span>
            <span className="text-[10px] text-cd-text-tertiary shrink-0 pt-1">{duration}</span>
          </div>
          <p className="text-xs text-cd-text-secondary mt-0.5 break-words">
            {activity.ai_summary || activity.window_title || '无标题'}
          </p>

          {/* 多窗口并排卡片（屏幕状态） */}
          {windows.length > 0 && (
            <div className="mt-2 animate-fade-in">
              <div className="flex items-center gap-1.5 mb-1.5">
                <span className="text-[10px] text-cd-text-tertiary uppercase tracking-wide">屏幕状态</span>
                <span className="text-[10px] text-cd-text-tertiary">({windows.length} 个窗口{windows.length > 1 ? '并行' : ''})</span>
              </div>
              <div className="space-y-2">
                {windows.map((w, idx) => {
                  const wicon = allIconUrls[w.app_name] || ''
                  return (
                    <div
                      key={`${w.app_name}-${idx}`}
                      className="flex items-start gap-3 rounded-lg px-3 py-2.5 border bg-cd-bg-secondary border-cd-border-light hover:bg-cd-hover transition-colors"
                      title={w.window_title}
                    >
                      <AppIcon name={w.app_name} iconUrl={wicon} size={24} />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="text-xs font-semibold text-cd-text">
                            {getDisplayAppName(w.app_name)}
                          </span>
                          {w.is_foreground && (
                            <span className="text-[9px] px-1 py-0 rounded bg-cd-green/10 text-cd-green">前台</span>
                          )}
                        </div>
                        <p className="text-xs text-cd-text-secondary mt-0.5 break-words">
                          {w.window_title || '无标题'}
                        </p>
                        {w.description && (
                          <p className="text-xs text-cd-text-tertiary mt-1 leading-relaxed break-words">
                            {w.description}
                          </p>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* 详细分析（直接展示，不折叠） */}
          {activity.ai_detail && (
            <div className="mt-2 text-xs text-cd-text-secondary leading-relaxed bg-cd-bg-secondary rounded-lg px-3 py-2 break-words">
              {activity.ai_detail}
            </div>
          )}

          {/* 编辑和删除按钮 */}
          <div className="mt-1.5 flex items-center gap-3 opacity-0 group-hover:opacity-100 transition-opacity">
              <button
                onClick={(e) => { e.stopPropagation(); onStartEdit(activity) }}
                className="flex items-center gap-1 text-[10px] text-cd-green hover:text-cd-green-dark transition-colors"
              >
                <Pencil size={10} />
                编辑
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); onDelete(activity) }}
                className="flex items-center gap-1 text-[10px] text-cd-red hover:opacity-80 transition-opacity"
              >
                <Trash2 size={10} />
                删除
              </button>
            </div>
          </div>
        </div>
      </div>
  )
})

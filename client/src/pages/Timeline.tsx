import { useState, useCallback, useEffect, memo } from 'react'
import { getActivities, searchActivities, updateActivity, deleteActivity, undoDeleteActivity, createActivity, getAppIconUrl, CATEGORY_COLORS, CATEGORIES, type Activity } from '../api/client'
import { CategoryFilter, useAsyncData, ApiErrorDisplay, useNewIds, RefreshIndicator } from '../components/shared'
import { useToast } from '../components/Toast'
import { Search, Pencil, X, Check, Loader2, Plus, Clock, Trash2 } from 'lucide-react'
import dayjs from 'dayjs'

export default function Timeline() {
  const toast = useToast()
  const [selectedDate, setSelectedDate] = useState(dayjs().format('YYYY-MM-DD'))
  const [filterCategory, setFilterCategory] = useState<string>('全部')
  // 搜索
  const [searchQuery, setSearchQuery] = useState('')
  const [isSearching, setIsSearching] = useState(false)
  // 编辑
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editCategory, setEditCategory] = useState('')
  const [editSummary, setEditSummary] = useState('')
  const [saving, setSaving] = useState(false)
  // 手动补录
  const [showAdd, setShowAdd] = useState(false)
  const [addTime, setAddTime] = useState(dayjs().format('YYYY-MM-DDTHH:mm'))
  const [addCategory, setAddCategory] = useState('开发')
  const [addSummary, setAddSummary] = useState('')
  const [addAppName, setAddAppName] = useState('')
  const [addDuration, setAddDuration] = useState(30)
  const [addSaving, setAddSaving] = useState(false)

  const { data: activitiesData, loading, error, refresh: refreshList, refreshing } = useAsyncData(
    () => getActivities(selectedDate),
    [selectedDate],
    15000,
  )
  const activities = activitiesData?.activities ?? []
  const newIds = useNewIds(activities, (a) => a.id)

  const [searchResults, setSearchResults] = useState<Activity[] | null>(null)
  // 应用图标缓存：app_name -> iconUrl
  const [iconUrls, setIconUrls] = useState<Record<string, string>>({})

  // 批量加载应用图标（前台应用 + 多窗口中的每个应用）
  useEffect(() => {
    const baseList = searchResults ?? activities
    const apps = Array.from(new Set(baseList.flatMap((a) => [
      a.app_name,
      ...(a.windows || []).map((w) => w.app_name),
    ])))
    if (!apps.length) return
    let cancelled = false
    ;(async () => {
      const map: Record<string, string> = {}
      await Promise.all(
        apps.map(async (name) => {
          if (!name) return
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
  }, [(searchResults ?? activities).map((a) => [a.app_name, ...(a.windows || []).map((w) => w.app_name)].join('|')).join(';')])

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

  const startEdit = (act: Activity) => {
    setEditingId(act.id)
    setEditCategory(act.category)
    setEditSummary(act.ai_summary || '')
  }

  const cancelEdit = () => {
    setEditingId(null)
    setEditCategory('')
    setEditSummary('')
  }

  const saveEdit = async (id: number) => {
    setSaving(true)
    try {
      await updateActivity(id, { category: editCategory, summary: editSummary })
      refreshList()
      setEditingId(null)
      toast.success('分类和摘要已更新')
    } catch (err) {
      console.error('Failed to save edit:', err)
      toast.error('保存失败，请重试')
    } finally {
      setSaving(false)
    }
  }

  const submitAdd = async () => {
    if (!addCategory || !addTime) return
    setAddSaving(true)
    try {
      const timestamp = dayjs(addTime).format('YYYY-MM-DD HH:mm:ss')
      await createActivity({
        timestamp,
        category: addCategory,
        summary: addSummary || undefined,
        app_name: addAppName || undefined,
        duration_min: addDuration,
      })
      setShowAdd(false)
      setAddSummary('')
      setAddAppName('')
      setAddDuration(30)
      setAddTime(dayjs().format('YYYY-MM-DDTHH:mm'))
      refreshList()
      toast.success('时间条目已补录')
    } catch (err) {
      console.error('Failed to add activity:', err)
      toast.error('补录失败，请重试')
    } finally {
      setAddSaving(false)
    }
  }

  const handleDelete = async (act: Activity) => {
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
            onClick={() => setShowAdd(!showAdd)}
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

      {/* ─── 手动补录表单 ─────────────────── */}
      {showAdd && (
        <div className="animate-fade-in card border border-cd-green/20 space-y-3">
          <h3 className="text-sm font-medium text-cd-text flex items-center gap-1.5">
            <Clock size={14} className="text-cd-green" />
            手动补录时间条目
          </h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-cd-text-secondary block mb-1">时间</label>
              <input
                type="datetime-local"
                value={addTime}
                onChange={(e) => setAddTime(e.target.value)}
                className="w-full bg-cd-card border border-cd-border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green"
              />
            </div>
            <div>
              <label className="text-xs text-cd-text-secondary block mb-1">时长（分钟）</label>
              <input
                type="number"
                value={addDuration}
                onChange={(e) => setAddDuration(Math.max(5, parseInt(e.target.value) || 30))}
                min={5}
                max={480}
                className="w-full bg-cd-card border border-cd-border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-cd-text-secondary block mb-1">分类</label>
              <select
                value={addCategory}
                onChange={(e) => setAddCategory(e.target.value)}
                className="w-full bg-cd-card border border-cd-border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green"
              >
                {CATEGORIES.map(c => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-cd-text-secondary block mb-1">应用名称（可选）</label>
              <input
                type="text"
                value={addAppName}
                onChange={(e) => setAddAppName(e.target.value)}
                placeholder="如：微信、邮件..."
                className="w-full bg-cd-card border border-cd-border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green"
              />
            </div>
          </div>
          <div>
            <label className="text-xs text-cd-text-secondary block mb-1">工作摘要</label>
            <textarea
              value={addSummary}
              onChange={(e) => setAddSummary(e.target.value)}
              rows={2}
              className="w-full bg-cd-card border border-cd-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cd-green resize-none"
              placeholder="描述你在这段时间做了什么..."
            />
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={submitAdd}
              disabled={addSaving}
              className="flex items-center gap-1 px-4 py-1.5 rounded-lg text-xs font-medium bg-cd-green text-white hover:bg-cd-green-dark disabled:opacity-50 transition-colors"
            >
              {addSaving ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
              保存补录
            </button>
            <button
              onClick={() => setShowAdd(false)}
              className="flex items-center gap-1 px-4 py-1.5 rounded-lg text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border"
            >
              取消
            </button>
          </div>
        </div>
      )}

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
        <div className="space-y-1">
          {timelineItems.map(({ act, time }) => (
            <TimelineEntry
              key={act.id}
              activity={act}
              displayTime={time}
              iconUrl={iconUrls[act.app_name] || ''}
              allIconUrls={iconUrls}
              isEditing={editingId === act.id}
              editCategory={editCategory}
              editSummary={editSummary}
              setEditCategory={setEditCategory}
              setEditSummary={setEditSummary}
              onStartEdit={startEdit}
              onCancelEdit={cancelEdit}
              onSaveEdit={saveEdit}
              onDelete={handleDelete}
              saving={saving}
              isNew={newIds.has(act.id)}
            />
          ))}
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
  isEditing,
  editCategory,
  editSummary,
  setEditCategory,
  setEditSummary,
  onStartEdit,
  onCancelEdit,
  onSaveEdit,
  onDelete,
  saving,
  isNew = false,
}: {
  activity: Activity
  displayTime: string
  iconUrl: string
  allIconUrls: Record<string, string>
  isEditing: boolean
  editCategory: string
  editSummary: string
  setEditCategory: (v: string) => void
  setEditSummary: (v: string) => void
  onStartEdit: (act: Activity) => void
  onCancelEdit: () => void
  onSaveEdit: (id: number) => void
  onDelete: (act: Activity) => void
  saving: boolean
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
      <div className="flex items-start gap-3 py-1.5 cursor-pointer" onClick={() => !isEditing && setExpanded(!expanded)}>
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
            {isEditing ? (
              <select
                value={editCategory}
                onChange={(e) => setEditCategory(e.target.value)}
                onClick={(e) => e.stopPropagation()}
                className="px-2 py-0.5 rounded-full text-[10px] font-medium border border-cd-border bg-cd-card text-cd-text focus:outline-none focus:border-cd-green"
              >
                {CATEGORIES.map(c => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            ) : (
              <span
                className="px-2 py-0.5 rounded-full text-[10px] font-medium shrink-0"
                style={{ background: catColor + '18', color: catColor }}
              >
                {activity.category}
              </span>
            )}
            <span className="text-[10px] text-cd-text-tertiary shrink-0 pt-1">{duration}</span>
          </div>
          <p className="text-xs text-cd-text-secondary mt-0.5 break-words">
            {activity.ai_summary || activity.window_title || '无标题'}
          </p>

          {/* 多窗口并排卡片（屏幕状态） */}
          {windows.length > 0 && !isEditing && (
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
          {activity.ai_detail && !isEditing && (
            <div className="mt-2 text-xs text-cd-text-secondary leading-relaxed bg-cd-bg-secondary rounded-lg px-3 py-2 break-words">
              {activity.ai_detail}
            </div>
          )}

          {/* 编辑和删除按钮 */}
          {!isEditing && (
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
          )}
        </div>
      </div>

      {/* 编辑模式 */}
      {isEditing && (
        <div className="ml-17 mt-1 mb-2 bg-cd-bg-secondary rounded-lg p-3 space-y-3 animate-fade-in border border-cd-green/20">
          <div>
            <label className="text-xs text-cd-text-secondary block mb-1">分类</label>
            <select
              value={editCategory}
              onChange={(e) => setEditCategory(e.target.value)}
              className="w-full bg-cd-card border border-cd-border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green"
            >
              {CATEGORIES.map(c => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-cd-text-secondary block mb-1">摘要</label>
            <textarea
              value={editSummary}
              onChange={(e) => setEditSummary(e.target.value)}
              rows={2}
              className="w-full bg-cd-card border border-cd-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cd-green resize-none"
              placeholder="输入工作摘要..."
            />
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => onSaveEdit(activity.id)}
              disabled={saving}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-cd-green text-white hover:bg-cd-green-dark disabled:opacity-50 transition-colors"
            >
              {saving ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
              保存
            </button>
            <button
              onClick={onCancelEdit}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border"
            >
              <X size={12} />
              取消
            </button>
          </div>
        </div>
      )}
    </div>
  )
})

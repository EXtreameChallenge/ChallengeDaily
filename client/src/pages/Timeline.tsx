import { useState, useCallback, memo } from 'react'
import { getActivities, searchActivities, updateActivity, deleteActivity, undoDeleteActivity, createActivity, CATEGORY_COLORS, CATEGORIES, type Activity } from '../api/client'
import { CategoryFilter, useAsyncData, ApiErrorDisplay } from '../components/shared'
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

  const { data: activitiesData, loading, error, refresh: refreshList } = useAsyncData(
    () => getActivities(selectedDate),
    [selectedDate],
    15000,
  )
  const activities = activitiesData?.activities ?? []

  const [searchResults, setSearchResults] = useState<Activity[] | null>(null)

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

  // 按小时分组
  const grouped: Record<string, Activity[]> = {}
  filtered.forEach((act) => {
    const hour = dayjs(act.timestamp).format('HH:00')
    if (!grouped[hour]) grouped[hour] = []
    grouped[hour].push(act)
  })

  // 切换日期时重置搜索
  const handleDateChange = (date: string) => {
    setSelectedDate(date)
    setSearchResults(null)
    setSearchQuery('')
  }

  return (
    <div className="animate-fade-in space-y-5">
      {/* ─── 头部 ─────────────────────────── */}
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-cd-text">工作时间线</h1>
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

      {/* ─── 时间线内容 ────────────────────── */}
      {error ? (
        <ApiErrorDisplay error={error} onRetry={refreshList} />
      ) : loading ? (
        <div className="text-cd-text-tertiary animate-pulse">加载中...</div>
      ) : filtered.length === 0 ? (
        <div className="text-cd-text-tertiary text-center py-16">
          {searchQuery ? `未找到与「${searchQuery}」相关的记录` : '暂无活动记录'}
        </div>
      ) : (
        <div className="space-y-6">
          {Object.entries(grouped)
            .sort(([a], [b]) => b.localeCompare(a))
            .map(([hour, acts]) => (
              <div key={hour}>
                <h3 className="text-xs font-medium text-cd-text-tertiary mb-3 ml-1">
                  {hour} - {((parseInt(hour) + 1) % 24).toString().padStart(2, '0')}:00
                  <span className="ml-2 font-normal">{acts.length} 条记录</span>
                </h3>
                <div className="timeline-track">
                  {acts.map((act) => (
                    <TimelineEntry
                       key={act.id}
                       activity={act}
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
                     />
                  ))}
                </div>
              </div>
            ))}
        </div>
      )}
    </div>
  )
}

const TimelineEntry = memo(function TimelineEntry({
  activity,
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
}: {
  activity: Activity
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
}) {
  const [expanded, setExpanded] = useState(false)
  const catColor = CATEGORY_COLORS[activity.category] || 'var(--cd-text-tertiary)'
  const time = dayjs(activity.timestamp).format('HH:mm')
  const duration =
    activity.duration_min >= 60
      ? `${(activity.duration_min / 60).toFixed(1)}h`
      : `${Math.round(activity.duration_min)}min`
  const iconChar = activity.app_name.replace(/\s+/g, '').slice(0, 1).toUpperCase()

  return (
    <div
      className="timeline-entry"
      style={{ '--cat-color': catColor } as React.CSSProperties}
    >
      <div
        className="flex items-center gap-3 py-1.5 cursor-pointer"
        onClick={() => !isEditing && setExpanded(!expanded)}
      >
        <div className="w-9 h-9 rounded-xl bg-cd-card border border-cd-border-light flex items-center justify-center text-xs font-medium text-cd-text-secondary shrink-0">
          {iconChar}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-cd-text truncate">{activity.app_name}</span>
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
          </div>
          <p className="text-xs text-cd-text-tertiary mt-0.5 truncate">
            {activity.ai_summary || activity.window_title || '无标题'}
          </p>
        </div>

        <div className="flex items-center gap-1 shrink-0">
          <span className="text-xs text-cd-text-tertiary">{duration}</span>
          {!isEditing && (
            <svg
              width="12" height="12" viewBox="0 0 12 12" fill="none"
              className={`text-cd-text-tertiary transition-transform duration-200 ${expanded ? 'rotate-90' : ''}`}
            >
              <path d="M4.5 2.5L8 6L4.5 9.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          )}
        </div>
      </div>

      {/* 展开详情 / 编辑模式 */}
      {expanded && !isEditing && (
        <div className="ml-12 mt-1 mb-2 bg-cd-bg-secondary rounded-lg p-3 space-y-2 animate-fade-in">
          <div className="flex items-center gap-4 text-xs">
            <span className="text-cd-text-tertiary">
              时间：<span className="text-cd-text">{time}</span>
            </span>
            <span className="text-cd-text-tertiary">
              时长：<span className="text-cd-text">{duration}</span>
            </span>
          </div>
          {activity.window_title && (
            <div className="text-xs">
              <span className="text-cd-text-tertiary">窗口：</span>
              <span className="text-cd-text">{activity.window_title}</span>
            </div>
          )}
          {activity.ai_summary && (
            <div className="text-xs">
              <span className="text-cd-text-tertiary">AI 摘要：</span>
              <span className="text-cd-text">{activity.ai_summary}</span>
            </div>
          )}
          {activity.ai_detail && (
            <div className="text-xs">
              <span className="text-cd-text-tertiary">详细分析：</span>
              <span className="text-cd-text-secondary">{activity.ai_detail}</span>
            </div>
          )}
          {/* 编辑和删除按钮 */}
          <div className="pt-2 border-t border-cd-border-light flex items-center gap-4">
            <button
              onClick={(e) => { e.stopPropagation(); onStartEdit(activity) }}
              className="flex items-center gap-1 text-xs text-cd-green hover:text-cd-green-dark transition-colors"
            >
              <Pencil size={12} />
              编辑
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); onDelete(activity) }}
              className="flex items-center gap-1 text-xs text-cd-red hover:opacity-80 transition-opacity"
            >
              <Trash2 size={12} />
              删除
            </button>
          </div>
        </div>
      )}

      {/* 编辑模式 */}
      {isEditing && (
        <div className="ml-12 mt-1 mb-2 bg-cd-bg-secondary rounded-lg p-3 space-y-3 animate-fade-in border border-cd-green/20">
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

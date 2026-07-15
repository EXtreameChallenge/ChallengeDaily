/**
 * P19-1: 日历订阅管理 UI
 * 添加/删除/启用 ICS 订阅，查看今日会议与当前会议状态
 */
import { useState, useEffect, useCallback } from 'react'
import {
  listCalendarSubscriptions, addCalendarSubscription, removeCalendarSubscription,
  refreshCalendarAll, getCalendarTodayEvents, getCalendarCurrentMeeting,
  type CalendarSubscription, type CalendarEvent,
} from '../api/client'
import { useToast } from './Toast'
import { Calendar, Plus, Trash2, RefreshCw, Clock, MapPin, Video, Loader2, CheckCircle, XCircle } from 'lucide-react'

export default function CalendarSubscriptionManager() {
  const toast = useToast()
  const [subs, setSubs] = useState<CalendarSubscription[]>([])
  const [todayEvents, setTodayEvents] = useState<CalendarEvent[]>([])
  const [currentMeeting, setCurrentMeeting] = useState<CalendarEvent | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [newName, setNewName] = useState('')
  const [newUrl, setNewUrl] = useState('')
  const [newColor, setNewColor] = useState('#4A90E2')

  const refresh = useCallback(async () => {
    try {
      const [subsRes, todayRes, meetingRes] = await Promise.all([
        listCalendarSubscriptions(),
        getCalendarTodayEvents(),
        getCalendarCurrentMeeting(),
      ])
      setSubs(subsRes.subscriptions || [])
      setTodayEvents(todayRes.events || [])
      setCurrentMeeting(meetingRes.meeting)
    } catch (err: any) {
      // 静默处理，避免在设置页弹出错误
      console.warn('日历数据加载失败:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const handleAdd = async () => {
    if (!newName.trim() || !newUrl.trim()) {
      toast.warning('请填写名称和 ICS URL')
      return
    }
    try {
      await addCalendarSubscription({ name: newName, url: newUrl, color: newColor })
      toast.success('日历订阅已添加')
      setShowAdd(false)
      setNewName('')
      setNewUrl('')
      refresh()
    } catch (err: any) {
      toast.error(err.message || '添加失败')
    }
  }

  const handleRemove = async (id: string) => {
    if (!confirm('确定要删除此日历订阅吗？')) return
    try {
      await removeCalendarSubscription(id)
      toast.success('已删除')
      refresh()
    } catch (err: any) {
      toast.error(err.message || '删除失败')
    }
  }

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      const r = await refreshCalendarAll()
      toast.success(`已刷新 ${r.refreshed}/${r.total} 个订阅`)
      refresh()
    } catch (err: any) {
      toast.error(err.message || '刷新失败')
    } finally {
      setRefreshing(false)
    }
  }

  const fmtTime = (iso: string) => {
    try {
      const d = new Date(iso)
      return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    } catch { return iso }
  }

  return (
    <div className="space-y-3">
      {/* 当前会议提示 */}
      {currentMeeting && (
        <div className="flex items-center gap-2 p-3 bg-cd-green-light border border-cd-green/30 rounded-lg">
          <Video size={14} className="text-cd-green animate-pulse" />
          <div className="flex-1 text-xs">
            <span className="font-semibold text-cd-green">正在进行：</span>
            <span className="text-cd-text">{currentMeeting.summary}</span>
            <span className="text-cd-text-tertiary ml-2">
              {fmtTime(currentMeeting.start)} - {fmtTime(currentMeeting.end)}
            </span>
          </div>
        </div>
      )}

      {/* 今日会议预览 */}
      {todayEvents.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-xs text-cd-text-tertiary flex items-center gap-1">
            <Clock size={11} /> 今日会议（{todayEvents.length}）
          </div>
          <div className="max-h-32 overflow-y-auto space-y-1">
            {todayEvents.slice(0, 5).map((ev, i) => (
              <div key={i} className="flex items-center gap-2 text-xs p-1.5 bg-cd-bg-secondary rounded">
                <div className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: ev.calendar_color }} />
                <span className="text-cd-text-secondary flex-shrink-0">{fmtTime(ev.start)}</span>
                <span className="text-cd-text truncate">{ev.summary}</span>
                {ev.location && (
                  <span className="text-cd-text-tertiary flex items-center gap-0.5 ml-auto flex-shrink-0">
                    <MapPin size={10} /> {ev.location}
                  </span>
                )}
              </div>
            ))}
            {todayEvents.length > 5 && (
              <div className="text-xs text-cd-text-tertiary text-center">还有 {todayEvents.length - 5} 个…</div>
            )}
          </div>
        </div>
      )}

      {/* 订阅列表 */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs text-cd-text-secondary">ICS 订阅源</span>
          <div className="flex gap-1.5">
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="text-xs text-cd-text-tertiary hover:text-cd-text flex items-center gap-1 disabled:opacity-40"
            >
              {refreshing ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
              刷新
            </button>
            <button
              onClick={() => setShowAdd(!showAdd)}
              className="text-xs text-cd-green hover:opacity-80 flex items-center gap-1"
            >
              <Plus size={11} /> 添加
            </button>
          </div>
        </div>

        {showAdd && (
          <div className="p-3 bg-cd-bg-secondary border border-cd-border rounded-lg space-y-2">
            <input
              type="text" placeholder="日历名称（如：工作日历）" value={newName}
              onChange={(e) => setNewName(e.target.value)}
              className="w-full bg-cd-bg text-cd-text border border-cd-border rounded px-2 py-1 text-xs"
            />
            <input
              type="url" placeholder="ICS 订阅 URL（https://...）" value={newUrl}
              onChange={(e) => setNewUrl(e.target.value)}
              className="w-full bg-cd-bg text-cd-text border border-cd-border rounded px-2 py-1 text-xs"
            />
            <div className="flex items-center gap-2">
              <input type="color" value={newColor} onChange={(e) => setNewColor(e.target.value)}
                className="w-6 h-6 rounded cursor-pointer" />
              <button onClick={handleAdd}
                className="ml-auto px-3 py-1 bg-cd-green text-white rounded text-xs hover:opacity-90">
                添加
              </button>
              <button onClick={() => setShowAdd(false)}
                className="px-2 py-1 text-cd-text-tertiary hover:text-cd-text text-xs">
                取消
              </button>
            </div>
            <p className="text-[10px] text-cd-text-tertiary">
              Google Calendar：设置 → 日历 → 公开日历 → ICS 链接
            </p>
          </div>
        )}

        {loading ? (
          <div className="text-xs text-cd-text-tertiary">加载中...</div>
        ) : subs.length === 0 ? (
          <div className="text-xs text-cd-text-tertiary">暂无订阅，点击"添加"开始</div>
        ) : (
          subs.map((s) => (
            <div key={s.id} className="flex items-center gap-2 p-2 bg-cd-bg-secondary rounded text-xs">
              <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: s.color }} />
              <div className="flex-1 min-w-0">
                <div className="text-cd-text truncate">{s.name}</div>
                <div className="text-cd-text-tertiary truncate">{s.url}</div>
                {s.last_error && (
                  <div className="text-cd-red truncate flex items-center gap-0.5">
                    <XCircle size={10} /> {s.last_error}
                  </div>
                )}
                {s.last_sync && !s.last_error && (
                  <div className="text-cd-green flex items-center gap-0.5">
                    <CheckCircle size={10} /> 已同步
                  </div>
                )}
              </div>
              <button onClick={() => handleRemove(s.id)}
                className="text-cd-text-tertiary hover:text-cd-red flex-shrink-0">
                <Trash2 size={12} />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

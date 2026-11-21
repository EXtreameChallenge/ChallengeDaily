/* eslint-disable @typescript-eslint/no-explicit-any -- 小黑接口返回体为动态 JSON，局部断言即可 */
import { useState, useEffect, useCallback } from 'react'
import { get, post, request } from '../api/client'
import { AppLockSettings } from '../components/AppLock'

// ═══ 满血版小黑功能集成中心（真实 API 版）═══
// 融合 ChallengeDaily glass风格 + 小黑日报助手功能
// 数据全部来自后端 /api/xiaohei/*（xiaohei_core.py 真实持久化），无硬编码假数据

interface Notif { id: string; title: string; body: string; read: boolean; timeStr: string }
interface Todo { id: string; title: string; done: boolean; pinned: boolean }
interface WorkRecord { id: number; title: string; content: string; category: string; date: string; app_name?: string; duration_sec?: number; created_at?: string }
interface Template { id: number; name: string; category: string; content: string; downloads: number; price: number }
interface Badge { id: string; name: string; icon: string; unlocked: boolean; desc: string; progress?: number; target?: number }
interface DedupEntry { id: number; event: string; similarity: number; detail: string; created_at: string }
interface TokenRec { feature: string; total_tokens: number; cost_points: number; created_at: string }
interface PointRec { id: number; type: string; amount: number; item: string; detail: string; created_at: string }

const localToday = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const PRICING_LABELS: Record<string, string> = {
  ai_report: 'AI报告生成',
  word_cloud: '词云生成',
  pdf_compress: 'PDF压缩',
  ai_chat: 'AI对话',
  audio_transcribe: '音频转写',
  template: '模板使用',
}

const fmtDur = (sec?: number) => {
  if (!sec) return '0分钟'
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return m > 0 ? `${m}分${s}秒` : `${s}秒`
}

export default function XiaoheiHub() {
  const [activeTab, setActiveTab] = useState('overview')

  // ── 真实数据状态 ──
  const [notifications, setNotifications] = useState<Notif[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [todos, setTodos] = useState<Todo[]>([])
  const [points, setPoints] = useState<{ balance: number; credits: number }>({ balance: 0, credits: 0 })
  const [pricing, setPricing] = useState<Record<string, number>>({})
  const [pointRecords, setPointRecords] = useState<PointRec[]>([])
  const [badges, setBadges] = useState<Badge[]>([])
  const [templates, setTemplates] = useState<Template[]>([])
  const [leaderboard, setLeaderboard] = useState<any[]>([])
  const [tokenUsage, setTokenUsage] = useState({ total: 0, today: 0 })
  const [tokenRecs, setTokenRecs] = useState<TokenRec[]>([])
  const [dedupLog, setDedupLog] = useState<DedupEntry[]>([])
  const [workRecords, setWorkRecords] = useState<WorkRecord[]>([])
  const [workSummary, setWorkSummary] = useState<{ count: number; total_minutes: number; categories: { name: string; count: number }[] }>({ count: 0, total_minutes: 0, categories: [] })
  const [workCategories, setWorkCategories] = useState<string[]>(['其他'])
  const [recordDay, setRecordDay] = useState(localToday())

  // ── 原有功能状态（真实 tools/keyboard 接口） ──
  const [recording, setRecording] = useState(false)
  const [recordDuration, setRecordDuration] = useState(0)
  const [recMsg, setRecMsg] = useState('')
  const [tplMsg, setTplMsg] = useState('')
  const [kbMsg, setKbMsg] = useState('')
  const [mdContent, setMdContent] = useState('')
  const [mdPath, setMdPath] = useState('')
  const [authSession, setAuthSession] = useState<{ loggedIn: boolean; user: any }>({ loggedIn: false, user: null })
  const [keyboardStats, setKeyboardStats] = useState<Record<string, number>>({})
  const [keyboardListening, setKeyboardListening] = useState(false)
  const [soundEnabled, setSoundEnabled] = useState(false)

  // ── 交互状态 ──
  const [editingId, setEditingId] = useState<number | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [form, setForm] = useState({ title: '', category: '其他', app_name: '', duration_sec: 0, content: '' })
  const [expandedTpl, setExpandedTpl] = useState<number | null>(null)
  const [msg, setMsg] = useState('')

  const flash = (m: string) => {
    setMsg(m)
    window.setTimeout(() => setMsg(''), 5000)
  }

  const loadWorkRecords = useCallback(async (day?: string) => {
    const d = day || recordDay
    try {
      const list: any = await get(`/api/xiaohei/work-records?date=${d}&limit=100`)
      setWorkRecords(list?.items || [])
      const sum: any = await get(`/api/xiaohei/work-records/daily-summary?date=${d}`)
      setWorkSummary(sum || { count: 0, total_minutes: 0, categories: [] })
    } catch { /* ignore */ }
  }, [recordDay])

  const fetchAll = useCallback(async () => {
    try {
      // 通知（tools 真实接口）
      const n: any = await get('/api/tools/notifications/list')
      setNotifications(n || [])
      const uc: any = await get('/api/tools/notifications/unread-count')
      setUnreadCount(uc?.count || 0)

      // 待办
      const t: any = await get('/api/todos')
      setTodos((t?.items || t || []).slice(0, 10))

      // 积分（xiaohei 真实账本）
      const p: any = await get('/api/xiaohei/points/balance')
      setPoints(p || { balance: 0, credits: 0 })
      const pr: any = await get('/api/xiaohei/points/pricing')
      setPricing(pr?.pricing || {})
      const pur: any = await get('/api/xiaohei/points/usage-records?page=1&page_size=15')
      setPointRecords((pur?.records || []).map((x: any) => ({ id: x.id, type: x.type, amount: x.amount, item: x.item, detail: x.detail, created_at: x.created_at })))

      // 账号
      const a: any = await get('/api/enterprise/auth/session')
      setAuthSession(a || { loggedIn: false, user: null })

      // 键盘
      const k: any = await get('/api/keyboard/stats')
      setKeyboardStats(k?.stats || {})

      // 徽章（真实）
      const b: any = await get('/api/xiaohei/badges')
      setBadges((b?.badges || []).map((x: any) => ({
        id: x.id, name: x.name, icon: x.icon, unlocked: !!x.unlocked,
        desc: x.desc, progress: x.progress ?? 0, target: x.target ?? 1,
      })))

      // 模板市场（真实）
      const tp: any = await get('/api/xiaohei/templates')
      setTemplates((tp?.templates || []).map((x: any) => ({
        id: x.id, name: x.name, category: x.category, content: x.content,
        downloads: x.downloads, price: x.price,
      })))

      // 排行榜（真实计算）
      const lb: any = await get('/api/xiaohei/leaderboard')
      setLeaderboard(lb?.rankings || [])

      // Token 统计（真实）
      const tu: any = await get('/api/xiaohei/token-usage/summary')
      setTokenUsage({ total: tu?.total_tokens || 0, today: tu?.today_tokens || 0 })
      const tr: any = await get('/api/xiaohei/token-usage?limit=10')
      setTokenRecs((tr?.records || []).map((x: any) => ({ feature: x.feature, total_tokens: x.total_tokens, cost_points: x.cost_points, created_at: x.created_at })))

      // 帧去重日志（真实）
      const dl: any = await get('/api/xiaohei/frame-dedup-log?limit=30')
      setDedupLog(dl?.logs || [])

      // 工作记录分类 + 当日记录
      const wc: any = await get('/api/xiaohei/work-records/categories')
      if (wc?.categories?.length) setWorkCategories(wc.categories)
      loadWorkRecords()
    } catch { /* ignore */ }
  }, [loadWorkRecords])

  useEffect(() => {
    fetchAll()
    const timer = setInterval(fetchAll, 10000)
    return () => clearInterval(timer)
  }, [fetchAll])

  // 录音计时
  useEffect(() => {
    if (!recording) return
    const t = setInterval(() => setRecordDuration(d => d + 1), 1000)
    return () => clearInterval(t)
  }, [recording])

  const formatTime = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`

  // ── 工作记录操作 ──
  const saveRecord = async () => {
    if (!form.title.trim()) { flash('请填写记录标题'); return }
    const body = { ...form, duration_sec: Number(form.duration_sec || 0), date: recordDay }
    try {
      if (editingId) {
        const r: any = await post(`/api/xiaohei/work-records/${editingId}`, body)
        flash(r?.ok ? '已保存修改' : (r?.error || '保存失败'))
      } else {
        const r: any = await post('/api/xiaohei/work-records', body)
        flash(r?.ok ? '已新建工作记录' : (r?.error || '创建失败'))
      }
      setFormOpen(false)
      setEditingId(null)
      setForm({ title: '', category: '其他', app_name: '', duration_sec: 0, content: '' })
      loadWorkRecords()
    } catch { flash('保存失败（后端不可用）') }
  }

  const delRecord = async (id: number) => {
    try {
      await request(`/api/xiaohei/work-records/${id}`, { method: 'DELETE' })
      flash('已删除记录')
      loadWorkRecords()
    } catch { flash('删除失败') }
  }

  const startEdit = (r: WorkRecord) => {
    setEditingId(r.id)
    setForm({ title: r.title, category: r.category, app_name: r.app_name || '', duration_sec: r.duration_sec || 0, content: r.content })
    setFormOpen(true)
  }

  const extractRecords = async () => {
    try {
      const r: any = await post('/api/xiaohei/work-records/extract', { date: recordDay })
      if (r?.ok) flash(r.message || `已提取 ${r.extracted || 0} 条工作记录`)
      else flash(r?.message || '提取失败')
      loadWorkRecords()
    } catch { flash('提取失败（后端不可用）') }
  }

  // ── 积分消费 ──
  const consumePoints = async (item: string) => {
    try {
      const r: any = await post('/api/xiaohei/points/consume', { item, detail: PRICING_LABELS[item] || item })
      if (r?.ok) flash(`已消费 ${r.consumed} 积分：${PRICING_LABELS[item] || item}，余额 ${r.balance}`)
      else flash(r?.error || '消费失败')
      const p: any = await get('/api/xiaohei/points/balance')
      setPoints(p || { balance: 0, credits: 0 })
      const pur: any = await get('/api/xiaohei/points/usage-records?page=1&page_size=15')
      setPointRecords((pur?.records || []).map((x: any) => ({ id: x.id, type: x.type, amount: x.amount, item: x.item, detail: x.detail, created_at: x.created_at })))
    } catch { flash('消费失败（后端不可用）') }
  }

  // ── 模板使用 ──
  const useTemplate = async (tid: number) => {
    try {
      const r: any = await post(`/api/xiaohei/templates/${tid}/use`)
      if (r?.ok) {
        flash('已使用模板，下载数 +1')
        const tp: any = await get('/api/xiaohei/templates')
        setTemplates((tp?.templates || []).map((x: any) => ({
          id: x.id, name: x.name, category: x.category, content: x.content,
          downloads: x.downloads, price: x.price,
        })))
      } else flash(r?.error || '使用失败')
    } catch { flash('使用失败（后端不可用）') }
  }

  // ── 帧去重日志清空 ──
  const clearDedup = async () => {
    try {
      await request('/api/xiaohei/frame-dedup-log', { method: 'DELETE' })
      setDedupLog([])
      flash('已清空帧去重日志')
    } catch { flash('清空失败') }
  }

  const tabs = [
    { id: 'overview', label: '📊 总览' },
    { id: 'todos', label: '✅ 待办' },
    { id: 'records', label: '📝 工作记录' },
    { id: 'notifications', label: `🔔 通知${unreadCount ? `(${unreadCount})` : ''}` },
    { id: 'keyboard', label: '⌨️ 键盘热力' },
    { id: 'recorder', label: '🎙️ 录音器' },
    { id: 'markdown', label: '📄 Markdown' },
    { id: 'pdf', label: '📦 PDF工具' },
    { id: 'points', label: '💎 积分' },
    { id: 'badges', label: '🏅 徽章' },
    { id: 'leaderboard', label: '🏆 排行榜' },
    { id: 'templates', label: '📋 模板市场' },
    { id: 'auth', label: '👤 账号' },
    { id: 'applock', label: '🔒 应用锁' },
    { id: 'wechat', label: '💬 微信' },
    { id: 'mcp', label: '🔧 MCP管理' },
    { id: 'festival', label: '🎉 效率节' },
    { id: 'survey', label: '📝 问卷' },
    { id: 'telemetry', label: '📡 遥测' },
    { id: 'debug', label: '🐛 调试日志' },
  ]

  const overviewCards = [
    { icon: '💎', label: '积分余额', value: points.balance },
    { icon: '👤', label: '登录状态', value: authSession.loggedIn ? '已登录' : '未登录' },
    { icon: '🔔', label: '未读通知', value: unreadCount },
    { icon: '📝', label: '今日工作记录', value: `${workSummary.count}条` },
    { icon: '🎯', label: '今日专注', value: workSummary.total_minutes >= 60 ? `${(workSummary.total_minutes / 60).toFixed(1)}h` : `${Math.round(workSummary.total_minutes)}分钟` },
    { icon: '🏅', label: '已解锁徽章', value: `${badges.filter(b => b.unlocked).length}/${badges.length}` },
    { icon: '📊', label: 'Token使用', value: tokenUsage.total },
    { icon: '📋', label: '模板市场', value: `${templates.length}个` },
  ]

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-bold">🐱 小黑集成中心</h1>
        <p className="text-sm text-gray-500 mt-1">小黑日报助手全部功能 × ChallengeDaily glass风格（数据来自真实后端 API）</p>
      </div>

      {/* 提示消息 */}
      {msg && (
        <div className="mb-4 p-3 bg-green-50 border border-green-200 text-green-700 rounded-xl text-sm">{msg}</div>
      )}

      {/* Tab栏 - 可滚动 */}
      <div className="glass rounded-2xl p-1 mb-6 flex gap-1 overflow-x-auto">
        {tabs.map(tab => (
          <button key={tab.id} onClick={() => setActiveTab(tab.id)}
            className={`px-3 py-2 rounded-xl text-xs font-medium whitespace-nowrap transition-all ${
              activeTab === tab.id ? 'bg-cd-accent text-white shadow' : 'text-gray-600 hover:bg-white/50'
            }`}>
            {tab.label}
          </button>
        ))}
      </div>

      {/* 总览 */}
      {activeTab === 'overview' && (
        <div className="grid grid-cols-4 gap-4">
          {overviewCards.map((card, i) => (
            <div key={i} className="glass rounded-2xl p-5">
              <div className="text-3xl mb-2">{card.icon}</div>
              <div className="text-gray-500 text-xs">{card.label}</div>
              <div className="text-xl font-bold mt-1">{card.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* 待办 */}
      {activeTab === 'todos' && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-base font-semibold mb-4">待办清单</h2>
          {todos.length === 0 ? (
            <div className="text-center py-12 text-gray-400">暂无待办</div>
          ) : (
            <div className="space-y-2">
              {todos.map(t => (
                <div key={t.id} className="flex items-center gap-3 p-3 bg-white/50 rounded-xl">
                  <input type="checkbox" checked={t.done} readOnly className="w-4 h-4" />
                  <span className={t.done ? 'line-through text-gray-400' : ''}>{t.title}</span>
                  {t.pinned && <span className="text-xs text-yellow-500">📌</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 工作记录（完整闭环：列表/新建/编辑/删除/一键提取/按日汇总） */}
      {activeTab === 'records' && (
        <div className="glass rounded-2xl p-6">
          <div className="flex flex-wrap justify-between items-center gap-3 mb-4">
            <h2 className="text-base font-semibold">工作记录（截图AI分析 → 结构化记录）</h2>
            <input type="date" value={recordDay}
              onChange={e => { setRecordDay(e.target.value); loadWorkRecords(e.target.value) }}
              className="px-3 py-1.5 rounded-xl border bg-white/50 text-sm" />
          </div>

          <div className="flex gap-3 mb-4">
            <button onClick={extractRecords} className="px-4 py-2 bg-cd-accent text-white rounded-xl text-sm">⚡ 一键提取（从截图）</button>
            <button onClick={() => { setFormOpen(true); setEditingId(null); setForm({ title: '', category: '其他', app_name: '', duration_sec: 0, content: '' }) }}
              className="px-4 py-2 bg-blue-500 text-white rounded-xl text-sm">+ 新建记录</button>
          </div>

          {/* 当日汇总 */}
          <div className="flex flex-wrap gap-2 mb-4 text-xs">
            <span className="px-3 py-1 bg-white/60 rounded-full">共 {workSummary.count} 条</span>
            <span className="px-3 py-1 bg-white/60 rounded-full">累计 {Math.round(workSummary.total_minutes)} 分钟</span>
            {workSummary.categories.map(c => (
              <span key={c.name} className="px-3 py-1 bg-blue-50 rounded-full">{c.name} ×{c.count}</span>
            ))}
          </div>

          {/* 新建/编辑表单 */}
          {formOpen && (
            <div className="mb-4 p-4 bg-white/40 rounded-xl space-y-2">
              <div className="flex gap-2">
                <input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="记录标题 *"
                  className="flex-1 px-3 py-2 rounded-lg border bg-white/50 text-sm" />
                <select value={form.category} onChange={e => setForm({ ...form, category: e.target.value })}
                  className="px-3 py-2 rounded-lg border bg-white/50 text-sm">
                  {workCategories.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div className="flex gap-2">
                <input value={form.app_name} onChange={e => setForm({ ...form, app_name: e.target.value })} placeholder="应用名"
                  className="flex-1 px-3 py-2 rounded-lg border bg-white/50 text-sm" />
                <input type="number" value={form.duration_sec || ''} onChange={e => setForm({ ...form, duration_sec: Number(e.target.value) })} placeholder="时长(秒)"
                  className="w-32 px-3 py-2 rounded-lg border bg-white/50 text-sm" />
              </div>
              <textarea value={form.content} onChange={e => setForm({ ...form, content: e.target.value })} placeholder="内容 / 备注"
                className="w-full h-20 p-3 rounded-lg border bg-white/50 text-sm" />
              <div className="flex gap-2">
                <button onClick={saveRecord} className="px-4 py-2 bg-green-500 text-white rounded-lg text-sm">{editingId ? '保存修改' : '保存'}</button>
                <button onClick={() => { setFormOpen(false); setEditingId(null) }} className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg text-sm">取消</button>
              </div>
            </div>
          )}

          {/* 记录列表 */}
          {workRecords.length === 0 ? (
            <div className="text-center py-10 text-gray-400">今日暂无工作记录，点「一键提取」可从截图自动生成</div>
          ) : (
            <div className="space-y-2">
              {workRecords.map(r => (
                <div key={r.id} className="p-4 bg-white/50 rounded-xl">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium">{r.title}</span>
                    <span className="text-xs px-2 py-0.5 bg-blue-50 rounded-full">{r.category}</span>
                    {r.app_name && <span className="text-xs text-gray-400">📱 {r.app_name}</span>}
                    <span className="ml-auto text-xs text-gray-500">{fmtDur(r.duration_sec)}</span>
                    <span className="text-xs text-gray-400">{r.created_at?.slice(11, 16)}</span>
                    <button onClick={() => startEdit(r)} className="text-xs text-blue-500 hover:underline">编辑</button>
                    <button onClick={() => delRecord(r.id)} className="text-xs text-red-500 hover:underline">删除</button>
                  </div>
                  {r.content && <p className="text-sm text-gray-600 mt-1 whitespace-pre-wrap">{r.content}</p>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 通知中心 */}
      {activeTab === 'notifications' && (
        <div className="glass rounded-2xl p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-base font-semibold">通知中心</h2>
            <button onClick={() => post('/api/tools/notifications/mark-all-read').then(() => fetchAll())}
              className="text-sm text-blue-500 hover:underline">全部已读</button>
          </div>
          {notifications.length === 0 ? (
            <div className="text-center py-12 text-gray-400">暂无通知</div>
          ) : (
            <div className="space-y-2">
              {notifications.map(n => (
                <div key={n.id} className={`p-4 rounded-xl border ${n.read ? 'bg-white/30' : 'bg-blue-50/50 border-blue-200'}`}>
                  <div className="flex justify-between">
                    <span className="font-medium">{n.title}</span>
                    <span className="text-xs text-gray-500">{n.timeStr}</span>
                  </div>
                  <p className="text-sm text-gray-600 mt-1">{n.body}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 键盘热力图 */}
      {activeTab === 'keyboard' && (
        <div className="glass rounded-2xl p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-base font-semibold">键盘热力图</h2>
            <div className="flex gap-2">
              <button onClick={async () => {
                try {
                  const res: any = await post('/api/keyboard/start')
                  if (res?.ok) { setKeyboardListening(true); setKbMsg('') }
                  else setKbMsg(res?.error || '启动失败')
                } catch (e: any) { setKbMsg(e?.message || '启动失败') }
              }}
                className="px-3 py-1.5 bg-green-500 text-white rounded-lg text-xs">开始监听</button>
              <button onClick={async () => {
                try {
                  const res: any = await post('/api/keyboard/stop')
                  if (res?.ok) { setKeyboardListening(false); setKbMsg('') }
                  else setKbMsg(res?.error || '停止失败')
                } catch (e: any) { setKbMsg(e?.message || '停止失败') }
              }}
                className="px-3 py-1.5 bg-red-500 text-white rounded-lg text-xs">停止监听</button>
              <button onClick={async () => {
                try {
                  const res: any = await post('/api/keyboard/sound/toggle', { enabled: !soundEnabled })
                  if (res?.ok) setSoundEnabled(!!res.enabled)
                  else setKbMsg(res?.error || '音效不可用')
                } catch (e: any) { setKbMsg(e?.message || '音效不可用') }
              }}
                className="px-3 py-1.5 bg-purple-500 text-white rounded-lg text-xs">🔊 音效</button>
            </div>
          </div>
          <p className="text-xs text-gray-400 mb-2">
            仅统计按键次数，不记录任何按键内容、不上传按键数据；默认关闭，开启后才监听，关闭即卸载全局钩子。
          </p>
          {kbMsg && <p className="text-xs text-amber-600 mb-2">{kbMsg}</p>}
          {keyboardListening && <p className="text-xs text-green-500 mb-2">正在监听键盘…</p>}
          <div className="flex flex-col items-center gap-1">
            {[
              ['Esc', 'F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8', 'F9', 'F10', 'F11', 'F12'],
              ['`', '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '-', '=', 'Backspace'],
              ['Tab', 'Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P', '[', ']', '\\'],
              ['Caps', 'A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', ';', "'", 'Enter'],
              ['Shift', 'Z', 'X', 'C', 'V', 'B', 'N', 'M', ',', '.', '/', 'Shift'],
              ['Ctrl', 'Win', 'Alt', 'Space', 'Alt', 'Fn', 'Ctrl'],
            ].map((row, i) => (
              <div key={i} className="flex gap-1">
                {row.map(key => (
                  <div key={key} className="w-10 h-10 rounded-lg flex items-center justify-center text-xs font-medium border"
                    style={{
                      backgroundColor: keyboardStats[key] ? 'rgba(239, 68, 68, 0.3)' : 'transparent',
                      borderColor: '#e5e7eb'
                    }}>
                    {key}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 录音器 */}
      {activeTab === 'recorder' && (
        <div className="glass rounded-2xl p-8 text-center">
          <div className={`w-28 h-28 mx-auto rounded-full flex items-center justify-center mb-6 ${recording ? 'bg-red-100 animate-pulse' : 'bg-gray-100'}`}>
            <span className="text-5xl">{recording ? '🔴' : '🎙️'}</span>
          </div>
          <div className="text-4xl font-mono mb-6">{formatTime(recordDuration)}</div>
          <button onClick={async () => {
            try {
              if (recording) {
                const res: any = await post('/api/tools/recorder/stop')
                setRecording(false)
                setRecMsg(res?.ok ? `已保存：${res.filepath}` : (res?.error || '保存失败'))
              } else {
                const res: any = await post('/api/tools/recorder/start')
                if (res?.ok) { setRecording(true); setRecordDuration(0); setRecMsg('') }
                else setRecMsg(res?.error || '录音启动失败')
              }
            } catch (e: any) { setRecMsg(e?.message || '录音操作失败') }
          }} className={`px-8 py-3 rounded-full text-white font-medium ${recording ? 'bg-red-500' : 'bg-green-500'}`}>
            {recording ? '停止录音' : '开始录音'}
          </button>
          {recMsg && <p className="text-xs text-amber-600 mt-3 break-all">{recMsg}</p>}
        </div>
      )}

      {/* Markdown阅读器 */}
      {activeTab === 'markdown' && (
        <div className="glass rounded-2xl p-6">
          <div className="flex gap-2 mb-4">
            <input type="text" placeholder="输入Markdown文件路径..."
              className="flex-1 px-3 py-2 rounded-xl border bg-white/50 text-sm"
              value={mdPath} onChange={e => setMdPath(e.target.value)} />
            <button onClick={async () => {
              const data: any = await post('/api/tools/markdown/read', { path: mdPath })
              if (data?.content) setMdContent(data.content)
            }} className="px-4 py-2 bg-cd-accent text-white rounded-xl text-sm">打开</button>
            <button onClick={async () => {
              try {
                const res: any = await post('/api/tools/markdown/save', { path: mdPath, content: mdContent })
                setRecMsg(res?.ok ? `已保存：${res.path}` : (res?.error || '保存失败'))
              } catch (e: any) { setRecMsg(e?.message || '保存失败') }
            }} className="px-4 py-2 bg-emerald-600 text-white rounded-xl text-sm">保存</button>
          </div>
          <textarea className="w-full h-80 p-4 rounded-xl border font-mono text-sm bg-white/50"
            value={mdContent} onChange={e => setMdContent(e.target.value)} placeholder="Markdown内容..." />
        </div>
      )}

      {/* PDF工具 */}
      {activeTab === 'pdf' && (
        <div className="glass rounded-2xl p-8 text-center">
          <div className="text-6xl mb-4">📄</div>
          <h2 className="text-base font-semibold mb-2">PDF工具箱</h2>
          <p className="text-sm text-gray-500 mb-6">
            合并 / 拆分请在「工具中心 → PDF工具」使用；真实压缩需 Ghostscript，规划中。
          </p>
          <button disabled className="px-6 py-3 bg-gray-200 text-gray-500 rounded-xl cursor-not-allowed">压缩（规划中）</button>
        </div>
      )}

      {/* 积分（真实账本 + 定价消费） */}
      {activeTab === 'points' && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-base font-semibold mb-4">积分计费系统（真实账本）</h2>
          <div className="flex gap-8 mb-6">
            <div><span className="text-gray-500">余额: </span><span className="text-3xl font-bold">{points.balance}</span></div>
            <div><span className="text-gray-500">额度: </span><span className="text-3xl font-bold">{points.credits}</span></div>
          </div>
          <p className="text-sm text-gray-500 mb-4">积分可用于AI报告生成、词云、PDF压缩等功能，消费后写入真实账本</p>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {Object.entries(pricing).map(([item, price]) => (
              <div key={item} className="p-4 bg-white/50 rounded-xl">
                <div className="font-medium text-sm">{PRICING_LABELS[item] || item}</div>
                <div className="text-xs text-gray-500 mt-1">{price} 积分/次</div>
                <button onClick={() => consumePoints(item)} className="mt-2 px-3 py-1 bg-cd-accent text-white rounded-lg text-xs">消费</button>
              </div>
            ))}
          </div>
          <div className="mt-6">
            <h3 className="text-sm font-semibold mb-2">使用记录</h3>
            {pointRecords.length === 0 ? (
              <div className="text-gray-400 text-sm">暂无积分消费记录</div>
            ) : (
              <div className="space-y-1">
                {pointRecords.map(pr => (
                  <div key={pr.id} className="flex items-center text-sm p-2 bg-white/40 rounded-lg">
                    <span className={`font-bold ${pr.type === 'debit' ? 'text-red-500' : 'text-green-500'}`}>{pr.type === 'debit' ? `-${pr.amount}` : `+${pr.amount}`}</span>
                    <span className="ml-3">{pr.item}</span>
                    {pr.detail && <span className="text-xs text-gray-400 ml-2">{pr.detail}</span>}
                    <span className="ml-auto text-xs text-gray-400">{pr.created_at}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* 徽章（真实进度） */}
      {activeTab === 'badges' && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-base font-semibold mb-4">成就徽章（真实进度）</h2>
          <div className="grid grid-cols-4 gap-4">
            {badges.map(b => (
              <div key={b.id} className={`p-4 rounded-xl text-center ${b.unlocked ? 'bg-white/50' : 'bg-gray-100'}`}>
                <div className="text-4xl mb-2">{b.icon}</div>
                <div className="font-medium text-sm">{b.name}</div>
                <div className="text-xs text-gray-500 mt-1">{b.desc}</div>
                {b.unlocked ? (
                  <div className="mt-2 text-xs text-green-500">已解锁 ✓</div>
                ) : b.target ? (
                  <div className="mt-2">
                    <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden">
                      <div className="h-full bg-cd-accent rounded-full" style={{ width: `${Math.min(100, Math.round(((b.progress || 0) / b.target) * 100))}%` }} />
                    </div>
                    <div className="text-[10px] text-gray-400 mt-1">{b.progress || 0}/{b.target}</div>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 排行榜（真实计算） */}
      {activeTab === 'leaderboard' && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-base font-semibold mb-4">日榜排行（按截图时长真实计算）</h2>
          {leaderboard.length === 0 ? (
            <div className="text-center py-12 text-gray-400">暂无排行数据</div>
          ) : (
            <div className="space-y-2">
              {leaderboard.map(l => (
                <div key={l.rank} className={`flex items-center gap-4 p-3 rounded-xl ${l.me ? 'bg-blue-100 border border-blue-300' : 'bg-white/50'}`}>
                  <span className="text-xl font-bold w-8">#{l.rank}</span>
                  <span className="font-medium">{l.name}{l.me ? ' (我)' : ''}</span>
                  <span className="ml-auto text-sm text-gray-600">{l.hours}h</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 模板市场（真实） */}
      {activeTab === 'templates' && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-base font-semibold mb-4">模板市场（本地持久化）</h2>
          {tplMsg && <p className="text-xs text-amber-600 mb-2 break-all">{tplMsg}</p>}
          {templates.length === 0 ? (
            <div className="text-center py-12 text-gray-400">暂无模板</div>
          ) : (
            <div className="space-y-2">
              {templates.map(t => (
                <div key={t.id} className="p-4 bg-white/50 rounded-xl">
                  <div className="flex items-center flex-wrap gap-2">
                    <span className="font-medium">{t.name}</span>
                    <span className="text-xs px-2 py-0.5 bg-gray-100 rounded-full">{t.category}</span>
                    <span className="ml-auto text-sm text-gray-500">下载 {t.downloads} · {t.price > 0 ? `${t.price}积分` : '免费'}</span>
                    <button onClick={() => useTemplate(t.id)} className="ml-2 px-3 py-1 bg-cd-accent text-white text-sm rounded-lg">使用</button>
                    <button onClick={async () => {
                      try {
                        const res: any = await post(`/api/xiaohei/templates/${t.id}/apply`)
                        setTplMsg(res?.ok ? `已应用到 ${res.day} 日报（${res.chars} 字）` : (res?.error || '应用失败'))
                      } catch (e: any) { setTplMsg(e?.message || '应用失败') }
                    }} className="px-3 py-1 bg-emerald-600 text-white text-sm rounded-lg">应用到日报</button>
                    <button onClick={() => setExpandedTpl(expandedTpl === t.id ? null : t.id)}
                      className="text-xs text-gray-400 hover:text-gray-600">{expandedTpl === t.id ? '收起' : '查看'}</button>
                  </div>
                  {expandedTpl === t.id && (
                    <pre className="mt-2 text-xs p-3 bg-gray-50 rounded-lg whitespace-pre-wrap">{t.content}</pre>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 账号 */}
      {activeTab === 'auth' && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-base font-semibold mb-4">账号体系</h2>
          {authSession.loggedIn ? (
            <div>
              <p className="mb-4">欢迎，{authSession.user?.name}</p>
              <button onClick={() => post('/api/enterprise/auth/logout').then(() => fetchAll())}
                className="px-4 py-2 bg-red-500 text-white rounded-xl">退出登录</button>
            </div>
          ) : (
            <p className="text-gray-500">本地模式，无需登录即可使用全部功能</p>
          )}
        </div>
      )}

      {/* 应用锁 */}
      {activeTab === 'applock' && (
        <div>
          <h2 className="text-base font-semibold px-1 mb-3">应用锁（后端口令 + 恢复词）</h2>
          <AppLockSettings />
        </div>
      )}

      {/* 微信 */}
      {activeTab === 'wechat' && (
        <div className="glass rounded-2xl p-8 text-center">
          <div className="text-6xl mb-4">💬</div>
          <h2 className="text-base font-semibold mb-2">微信集成</h2>
          <p className="text-sm text-gray-500 mb-4">微信集成规划中：后续接入小黑 xiaoheiBot 微信绑定流程</p>
          <button disabled className="px-4 py-2 bg-gray-300 text-white rounded-xl cursor-not-allowed">暂未开放</button>
        </div>
      )}

      {/* MCP管理 */}
      {activeTab === 'mcp' && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-base font-semibold mb-4">MCP服务器管理</h2>
          <div className="p-4 bg-white/50 rounded-xl text-sm text-gray-600">
            本机 MCP 服务器由 mcp_server.py 独立运行（真实实现，1023 行），当前未开放远程管理列表。
          </div>
        </div>
      )}

      {/* 效率节 */}
      {activeTab === 'festival' && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-base font-semibold mb-4">🔥 效率节</h2>
          <p className="text-gray-600 mb-4">连续专注打卡，解锁专属徽章（徽章进度见「徽章」Tab 真实数据）</p>
          <div className="p-4 bg-yellow-50 rounded-xl">奖励：专注大师（累计专注100h）/ 连击勇士（连续打卡30天）</div>
        </div>
      )}

      {/* 问卷 */}
      {activeTab === 'survey' && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-base font-semibold mb-4">问卷调查</h2>
          <div className="text-center py-12 text-gray-400">暂无进行中的问卷</div>
        </div>
      )}

      {/* 遥测 */}
      {activeTab === 'telemetry' && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-base font-semibold mb-4">遥测事件</h2>
          <div className="text-center py-12 text-gray-400">暂无遥测事件（遥测采集接口未启用）</div>
        </div>
      )}

      {/* 调试日志（真实帧去重 + Token） */}
      {activeTab === 'debug' && (
        <div className="glass rounded-2xl p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-base font-semibold">帧去重日志（截图真实记录）</h2>
            <button onClick={clearDedup} className="px-3 py-1 bg-red-500 text-white rounded-lg text-xs">清空</button>
          </div>
          {dedupLog.length === 0 ? (
            <div className="text-gray-400 text-sm">暂无帧去重日志（截图时会自动记录）</div>
          ) : (
            <div className="space-y-1">
              {dedupLog.map(l => (
                <div key={l.id} className="text-xs p-2 bg-gray-50 rounded font-mono">
                  [{l.event === 'saved' ? '保存' : '跳过'}] {l.detail}
                  {l.similarity > 0 && <span className="text-gray-400">（相似度{l.similarity}%）</span>}
                  <span className="text-gray-400"> {l.created_at}</span>
                </div>
              ))}
            </div>
          )}
          <div className="mt-6">
            <h2 className="text-base font-semibold mb-2">Token 使用统计</h2>
            <div className="flex gap-8 mb-3">
              <div><span className="text-gray-500">总计: </span><span className="font-bold">{tokenUsage.total}</span></div>
              <div><span className="text-gray-500">今日: </span><span className="font-bold">{tokenUsage.today}</span></div>
            </div>
            {tokenRecs.length > 0 && (
              <div className="space-y-1">
                {tokenRecs.map((tr, i) => (
                  <div key={i} className="text-xs p-2 bg-gray-50 rounded font-mono">{tr.feature} · {tr.total_tokens} tokens · {tr.cost_points}积分 · {tr.created_at}</div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

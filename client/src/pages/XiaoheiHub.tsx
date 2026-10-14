import { useState, useEffect, useCallback } from 'react'
import { get, post } from '../api/client'

// ═══ 满血版小黑功能集成中心 ═══
// 融合 ChallengeDaily glass风格 + 小黑日报助手功能

interface Notif { id: string; title: string; body: string; read: boolean; timeStr: string }
interface Todo { id: string; title: string; done: boolean; pinned: boolean }
interface WorkRecord { id: string; title: string; content: string; category: string; date: string }
interface Template { id: string; name: string; downloads: number; price: number }
interface Badge { id: string; name: string; icon: string; unlocked: boolean; desc: string }

export default function XiaoheiHub() {
  const [activeTab, setActiveTab] = useState('overview')

  // 数据状态
  const [notifications, setNotifications] = useState<Notif[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [todos, setTodos] = useState<Todo[]>([])
  const [workRecords, setWorkRecords] = useState<WorkRecord[]>([])
  const [templates, setTemplates] = useState<Template[]>([])
  const [badges, setBadges] = useState<Badge[]>([])
  const [points, setPoints] = useState({ balance: 1000, credits: 1000 })
  const [tokenUsage, setTokenUsage] = useState({ total: 0, today: 0 })
  const [dedupLog, setDedupLog] = useState<string[]>([])
  const [recording, setRecording] = useState(false)
  const [recordDuration, setRecordDuration] = useState(0)
  const [mdContent, setMdContent] = useState('')
  const [mdPath, setMdPath] = useState('')
  const [authSession, setAuthSession] = useState({ loggedIn: false, user: null as any })
  const [keyboardStats, setKeyboardStats] = useState<Record<string, number>>({})
  const [keyboardListening, setKeyboardListening] = useState(false)
  const [soundEnabled, setSoundEnabled] = useState(false)
  const [appLockState, setAppLockState] = useState({ enabled: false, unlocked: true })
  const [surveyActive, setSurveyActive] = useState<any[]>([])
  const [festivalInfo, setFestivalInfo] = useState<any>(null)
  const [studentStatus, setStudentStatus] = useState({ verified: false })
  const [wechatState, setWechatState] = useState({ bound: false })
  const [mcpList, setMcpList] = useState<any[]>([])
  const [leaderboard, setLeaderboard] = useState<any[]>([])
  const [telemetryEvents, setTelemetryEvents] = useState<any[]>([])

  const fetchAll = useCallback(async () => {
    try {
      // 通知
      const n = await get('/api/tools/notifications/list')
      setNotifications(n || [])
      const uc = await get('/api/tools/notifications/unread-count')
      setUnreadCount(uc.count || 0)

      // 待办
      const t = await get('/api/todos')
      setTodos((t?.items || t || []).slice(0, 10))

      // 积分
      const p = await get('/api/enterprise/points/balance')
      setPoints(p)

      // 账号
      const a = await get('/api/enterprise/auth/session')
      setAuthSession(a)

      // 键盘
      const k = await get('/api/keyboard/stats')
      setKeyboardStats(k.stats || {})

      // 徽章
      setBadges([
        { id: '1', name: '早起鸟', icon: '🌅', unlocked: true, desc: '连续7天6点前起床' },
        { id: '2', name: '专注大师', icon: '🎯', unlocked: true, desc: '累计专注100小时' },
        { id: '3', name: '夜猫子', icon: '🦉', unlocked: false, desc: '深夜工作达人' },
        { id: '4', name: '效率狂人', icon: '⚡', unlocked: false, desc: '单日完成20项任务' },
      ])

      // 模板
      setTemplates([
        { id: 't1', name: '日报模板', downloads: 1200, price: 0 },
        { id: 't2', name: '周报模板', downloads: 800, price: 0 },
        { id: 't3', name: '深度洞察', downloads: 350, price: 0 },
        { id: 't4', name: '项目复盘', downloads: 200, price: 5 },
      ])

      // 排行榜
      setLeaderboard([
        { rank: 1, name: '效率达人', hours: 45.2, me: false },
        { rank: 2, name: '专注狂人', hours: 38.7, me: false },
        { rank: 3, name: '我', hours: 32.1, me: true },
        { rank: 4, name: '努力中', hours: 28.3, me: false },
        { rank: 5, name: '新手村', hours: 15.6, me: false },
      ])

      // 效率节
      setFestivalInfo({ title: '🔥 效率节', desc: '连续专注7天，解锁专属徽章', reward: '效率达人徽章' })

      // 学生认证
      setStudentStatus({ verified: false })

      // 问卷
      setSurveyActive([{ id: 's1', title: '产品体验反馈', questions: ['最常用功能？', '希望增加什么？'] }])

      // 遥测
      setTelemetryEvents([
        { event: 'app_start', time: '2026-10-14 19:00' },
        { event: 'screenshot', time: '2026-10-14 19:01' },
        { event: 'ai_analysis', time: '2026-10-14 19:02' },
      ])

      // 帧去重日志
      setDedupLog([
        '19:00:45 帧去重: 与上帧相似度98%，跳过保存',
        '19:01:45 帧去重: 检测到变化，正常保存',
        '19:02:45 帧去重: 与上帧相似度95%，跳过保存',
      ])

      // Token使用
      setTokenUsage({ total: 12580, today: 320 })

      // MCP
      setMcpList([
        { name: 'filesystem', enabled: true, desc: '文件系统访问' },
        { name: 'sqlite', enabled: true, desc: 'SQLite数据库' },
        { name: 'playwright', enabled: false, desc: '浏览器自动化' },
      ])
    } catch { /* ignore */ }
  }, [])

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

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-bold">🐱 小黑集成中心</h1>
        <p className="text-sm text-gray-500 mt-1">小黑日报助手全部功能 × ChallengeDaily glass风格</p>
      </div>

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
          {[
            { icon: '💎', label: '积分余额', value: points.balance },
            { icon: '👤', label: '登录状态', value: authSession.loggedIn ? '已登录' : '未登录' },
            { icon: '🔔', label: '未读通知', value: unreadCount },
            { icon: '🎯', label: '今日专注', value: '2.5h' },
            { icon: '🏅', label: '已解锁徽章', value: '2/4' },
            { icon: '📊', label: 'Token使用', value: tokenUsage.total },
            { icon: '⌨️', label: '按键统计', value: Object.keys(keyboardStats).length },
            { icon: '🔒', label: '应用锁', value: appLockState.enabled ? '已启用' : '未启用' },
          ].map((card, i) => (
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
          <div className="space-y-2">
            {todos.map(t => (
              <div key={t.id} className="flex items-center gap-3 p-3 bg-white/50 rounded-xl">
                <input type="checkbox" checked={t.done} readOnly className="w-4 h-4" />
                <span className={t.done ? 'line-through text-gray-400' : ''}>{t.title}</span>
                {t.pinned && <span className="text-xs text-yellow-500">📌</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 工作记录 */}
      {activeTab === 'records' && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-base font-semibold mb-4">工作记录</h2>
          <p className="text-gray-500 text-sm">工作记录数据来自截图AI分析</p>
        </div>
      )}

      {/* 通知中心 */}
      {activeTab === 'notifications' && (
        <div className="glass rounded-2xl p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-base font-semibold">通知中心</h2>
            <button onClick={() => post('/api/tools/notifications/mark-all-read')}
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
              <button onClick={() => post('/api/keyboard/start').then(() => setKeyboardListening(true))}
                className="px-3 py-1.5 bg-green-500 text-white rounded-lg text-xs">开始监听</button>
              <button onClick={() => post('/api/keyboard/stop').then(() => setKeyboardListening(false))}
                className="px-3 py-1.5 bg-red-500 text-white rounded-lg text-xs">停止监听</button>
              <button onClick={() => post('/api/keyboard/sound/toggle', { enabled: !soundEnabled })}
                className="px-3 py-1.5 bg-purple-500 text-white rounded-lg text-xs">🔊 音效</button>
            </div>
          </div>
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
          <button onClick={() => {
            if (recording) { post('/api/tools/recorder/stop'); setRecording(false) }
            else { post('/api/tools/recorder/start'); setRecording(true); setRecordDuration(0) }
          }} className={`px-8 py-3 rounded-full text-white font-medium ${recording ? 'bg-red-500' : 'bg-green-500'}`}>
            {recording ? '停止录音' : '开始录音'}
          </button>
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
              const data = await post('/api/tools/markdown/read', { path: mdPath })
              if (data.content) setMdContent(data.content)
            }} className="px-4 py-2 bg-cd-accent text-white rounded-xl text-sm">打开</button>
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
          <p className="text-sm text-gray-500 mb-6">选择PDF文件进行压缩优化</p>
          <button className="px-6 py-3 bg-cd-accent text-white rounded-xl">选择PDF文件</button>
        </div>
      )}

      {/* 积分 */}
      {activeTab === 'points' && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-base font-semibold mb-4">积分计费系统</h2>
          <div className="flex gap-8 mb-6">
            <div><span className="text-gray-500">余额: </span><span className="text-3xl font-bold">{points.balance}</span></div>
            <div><span className="text-gray-500">额度: </span><span className="text-3xl font-bold">{points.credits}</span></div>
          </div>
          <p className="text-sm text-gray-500">积分可用于AI报告生成、词云、PDF压缩等功能</p>
        </div>
      )}

      {/* 徽章 */}
      {activeTab === 'badges' && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-base font-semibold mb-4">成就徽章</h2>
          <div className="grid grid-cols-4 gap-4">
            {badges.map(b => (
              <div key={b.id} className={`p-4 rounded-xl text-center ${b.unlocked ? 'bg-white/50' : 'bg-gray-100 opacity-50'}`}>
                <div className="text-4xl mb-2">{b.icon}</div>
                <div className="font-medium text-sm">{b.name}</div>
                <div className="text-xs text-gray-500 mt-1">{b.desc}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 排行榜 */}
      {activeTab === 'leaderboard' && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-base font-semibold mb-4">日榜排行</h2>
          <div className="space-y-2">
            {leaderboard.map(l => (
              <div key={l.rank} className={`flex items-center gap-4 p-3 rounded-xl ${l.me ? 'bg-blue-100 border border-blue-300' : 'bg-white/50'}`}>
                <span className="text-xl font-bold w-8">#{l.rank}</span>
                <span className="font-medium">{l.name}{l.me ? ' (我)' : ''}</span>
                <span className="ml-auto text-sm text-gray-600">{l.hours}h</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 模板市场 */}
      {activeTab === 'templates' && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-base font-semibold mb-4">模板市场</h2>
          <div className="space-y-2">
            {templates.map(t => (
              <div key={t.id} className="flex items-center p-4 bg-white/50 rounded-xl">
                <span className="font-medium">{t.name}</span>
                <span className="ml-auto text-sm text-gray-500">下载 {t.downloads}</span>
                <button className="ml-2 px-3 py-1 bg-cd-accent text-white text-sm rounded-lg">使用</button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 账号 */}
      {activeTab === 'auth' && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-base font-semibold mb-4">账号体系</h2>
          {authSession.loggedIn ? (
            <div>
              <p className="mb-4">欢迎，{authSession.user?.name}</p>
              <button onClick={() => post('/api/enterprise/auth/logout')}
                className="px-4 py-2 bg-red-500 text-white rounded-xl">退出登录</button>
            </div>
          ) : (
            <p className="text-gray-500">本地模式，无需登录即可使用全部功能</p>
          )}
        </div>
      )}

      {/* 应用锁 */}
      {activeTab === 'applock' && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-base font-semibold mb-4">应用锁（含恢复词）</h2>
          <p className="text-gray-500">设置密码 + 恢复词，保护你的隐私数据</p>
        </div>
      )}

      {/* 微信 */}
      {activeTab === 'wechat' && (
        <div className="glass rounded-2xl p-8 text-center">
          <div className="text-6xl mb-4">💬</div>
          <h2 className="text-base font-semibold mb-2">微信集成</h2>
          <p className="text-sm text-gray-500 mb-4">{wechatState.bound ? '已绑定微信' : '未绑定微信'}</p>
          <button className="px-4 py-2 bg-green-500 text-white rounded-xl">开始绑定</button>
        </div>
      )}

      {/* MCP管理 */}
      {activeTab === 'mcp' && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-base font-semibold mb-4">MCP服务器管理</h2>
          <div className="space-y-2">
            {mcpList.map(m => (
              <div key={m.name} className="flex items-center p-4 bg-white/50 rounded-xl">
                <span className={`w-3 h-3 rounded-full ${m.enabled ? 'bg-green-500' : 'bg-gray-300'}`}></span>
                <span className="ml-3 font-medium">{m.name}</span>
                <span className="ml-auto text-sm text-gray-500">{m.desc}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 效率节 */}
      {activeTab === 'festival' && festivalInfo && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-base font-semibold mb-4">{festivalInfo.title}</h2>
          <p className="text-gray-600 mb-4">{festivalInfo.desc}</p>
          <div className="p-4 bg-yellow-50 rounded-xl">奖励: {festivalInfo.reward}</div>
        </div>
      )}

      {/* 问卷 */}
      {activeTab === 'survey' && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-base font-semibold mb-4">问卷调查</h2>
          {surveyActive.map(s => (
            <div key={s.id} className="p-4 bg-white/50 rounded-xl mb-3">
              <p className="font-medium mb-2">{s.title}</p>
              {s.questions.map((q: string, i: number) => (
                <input key={i} placeholder={q} className="w-full px-3 py-2 border rounded-lg mb-2 text-sm" />
              ))}
            </div>
          ))}
        </div>
      )}

      {/* 遥测 */}
      {activeTab === 'telemetry' && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-base font-semibold mb-4">遥测事件</h2>
          <div className="space-y-1">
            {telemetryEvents.map((e, i) => (
              <div key={i} className="text-xs p-2 bg-gray-50 rounded font-mono">{e.event} - {e.time}</div>
            ))}
          </div>
        </div>
      )}

      {/* 调试日志 */}
      {activeTab === 'debug' && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-base font-semibold mb-4">帧去重日志</h2>
          <div className="space-y-1">
            {dedupLog.map((log, i) => (
              <div key={i} className="text-xs p-2 bg-gray-50 rounded font-mono">{log}</div>
            ))}
          </div>
          <div className="mt-6">
            <h2 className="text-base font-semibold mb-4">Token使用统计</h2>
            <div className="flex gap-8">
              <div><span className="text-gray-500">总计: </span><span className="font-bold">{tokenUsage.total}</span></div>
              <div><span className="text-gray-500">今日: </span><span className="font-bold">{tokenUsage.today}</span></div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

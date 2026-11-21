import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { get, post } from '../api/client'

const DEMO_MODULES: Record<string, { icon: string; title: string; desc: string }> = {
  publisher: { icon: '📹', title: '视频发布器', desc: '账号绑定与多平台发布均未接线；接口返回 not_implemented，不会创建任务。' },
  wechat: { icon: '💬', title: '微信集成', desc: '扫码登录与消息同步未接线；不会拉起登录，也不会写绑定状态。' },
  browser: { icon: '🌐', title: '浏览器自动化', desc: 'DeepSeek/ChatGPT 自动开窗未接线；不会启动浏览器。' },
  mcp: { icon: '🔧', title: 'MCP 服务器管理', desc: '企业页仅保留说明；真实开关在「设置 → 集成 → MCP stdio 服务」。' },
  miniprogram: { icon: '📱', title: '小程序同步', desc: '同步通道未接线；不会上传或下载任何数据。' },
  student: { icon: '🎓', title: '学生认证', desc: '认证服务未接入；不会自动通过任何邮箱，也不返回 verified=true。' },
  festival: { icon: '🎉', title: '效率节活动', desc: '活动数据未接入；当前不展示虚构奖励或排名。' },
  survey: { icon: '📝', title: '问卷调查', desc: '问卷系统未接入；不会记录或丢弃任何答案。' },
}

export default function EnterpriseHub() {
  const [activeTab, setActiveTab] = useState('overview')
  const [session, setSession] = useState<any>({ loggedIn: false })
  const [points, setPoints] = useState({ balance: 0, credits: 0 })
  const [templates, setTemplates] = useState<any[]>([])
  const [telemetry, setTelemetry] = useState<{ enabled: boolean; events: Array<any> }>({ enabled: false, events: [] })
  const [email, setEmail] = useState('')

  const refreshReal = async () => {
    try {
      setSession(await get('/api/enterprise/auth/session'))
      setPoints(await get('/api/enterprise/points/balance'))
      setTemplates(await get('/api/enterprise/templates/list'))
    } catch { /* 真实接口未就绪时保留默认值 */ }
  }

  const refreshTelemetry = async () => {
    try {
      const status = await get('/api/enterprise/telemetry/status') as any
      const events = await get('/api/enterprise/telemetry/events?limit=20') as any
      setTelemetry({ enabled: !!status.enabled, events: Array.isArray(events.events) ? events.events : [] })
    } catch {
      setTelemetry({ enabled: false, events: [] })
    }
  }

  useEffect(() => { refreshReal(); refreshTelemetry() }, [])

  const tabs: Array<{ id: string; label: string; demo?: boolean }> = [
    { id: 'overview', label: '📊 总览' },
    { id: 'auth', label: '👤 账号' },
    { id: 'points', label: '💎 积分' },
    { id: 'templates', label: '📋 模板' },
    { id: 'publisher', label: '📹 发布', demo: true },
    { id: 'wechat', label: '💬 微信', demo: true },
    { id: 'browser', label: '🌐 浏览器', demo: true },
    { id: 'mcp', label: '🔧 MCP', demo: true },
    { id: 'miniprogram', label: '📱 小程序', demo: true },
    { id: 'student', label: '🎓 学生', demo: true },
    { id: 'festival', label: '🎉 效率节', demo: true },
    { id: 'survey', label: '📝 问卷', demo: true },
    { id: 'telemetry', label: '📡 遥测' },
  ]

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-bold">🏢 企业功能中心</h1>
        <p className="text-sm text-gray-500 mt-1">
          真实功能：账号 / 积分 / 模板 / 本地遥测；演示模块 8 个，均明确标注「规划中」，不会返回假成功。
        </p>
      </div>

      {/* Tab栏 - 可滚动 */}
      <div className="glass rounded-2xl p-1 mb-6 flex gap-1 overflow-x-auto">
        {tabs.map(tab => (
          <button key={tab.id} onClick={() => setActiveTab(tab.id)}
            className={`px-3 py-2 rounded-xl text-xs font-medium whitespace-nowrap transition-all ${
              activeTab === tab.id ? 'bg-cd-accent text-white shadow' : 'text-gray-600 hover:bg-white/50'
            }`}>
            {tab.label}
            {tab.demo && <span className="ml-1 text-[10px] opacity-60">·演示</span>}
          </button>
        ))}
      </div>

      {/* 总览 */}
      {activeTab === 'overview' && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { icon: '💎', label: '积分余额', value: points.balance },
            { icon: '👤', label: '登录状态', value: session.loggedIn ? '已登录' : '未登录' },
            { icon: '📡', label: '本地遥测', value: telemetry.enabled ? '已开启' : '已关闭（默认）' },
            { icon: '🧪', label: '演示模块', value: '8 个 · 规划中' },
          ].map((card, i) => (
            <div key={i} className="glass rounded-2xl p-5">
              <div className="text-3xl mb-2">{card.icon}</div>
              <div className="text-gray-500 text-sm">{card.label}</div>
              <div className="text-xl font-bold mt-1">{card.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* 账号（真实本地会话） */}
      {activeTab === 'auth' && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-base font-semibold mb-1">账号体系</h2>
          <p className="text-xs text-gray-500 mb-4">本地账号会话，数据写入本机 user.json，不连接云端。</p>
          {session.loggedIn ? (
            <div>
              <p className="mb-4">欢迎，{session.user?.name}</p>
              <button onClick={() => post('/api/enterprise/auth/logout').then(refreshReal)}
                className="px-4 py-2 bg-red-500 text-white rounded-xl">退出登录</button>
            </div>
          ) : (
            <div className="flex gap-2">
              <input type="email" placeholder="邮箱" value={email} onChange={e => setEmail(e.target.value)}
                className="flex-1 px-3 py-2 rounded-xl border bg-white/50" />
              <button onClick={() => post('/api/enterprise/auth/login', { email, password: 'local' }).then(refreshReal)}
                className="px-4 py-2 bg-cd-accent text-white rounded-xl">登录</button>
            </div>
          )}
        </div>
      )}

      {/* 积分（本地账本） */}
      {activeTab === 'points' && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-base font-semibold mb-1">积分计费系统</h2>
          <p className="text-xs text-gray-500 mb-4">本地积分账本，数据来自 points.json。</p>
          <div className="flex gap-8">
            <div><span className="text-gray-500">余额: </span><span className="text-3xl font-bold">{points.balance}</span></div>
            <div><span className="text-gray-500">额度: </span><span className="text-3xl font-bold">{points.credits}</span></div>
          </div>
        </div>
      )}

      {/* 模板市场（本地模板） */}
      {activeTab === 'templates' && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-base font-semibold mb-1">模板市场</h2>
          <p className="text-xs text-gray-500 mb-4">本地模板列表；下载按钮仅展示，未接远端市场。</p>
          <div className="space-y-2">
            {templates.length === 0 && <p className="text-sm text-gray-500">暂无本地模板</p>}
            {templates.map((t: any) => (
              <div key={t.id} className="flex items-center p-4 bg-white/50 rounded-xl">
                <span className="font-medium">{t.name}</span>
                <span className="ml-auto text-sm text-gray-500">下载 {t.downloads}</span>
                <button disabled title="模板下载未接线"
                  className="ml-2 px-3 py-1 bg-gray-300 text-white text-sm rounded-lg cursor-not-allowed">下载</button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 8 个演示模块：统一诚实占位 */}
      {activeTab in DEMO_MODULES && (
        <div className="glass rounded-2xl p-8 text-center border border-amber-300/50">
          <div className="inline-block px-3 py-1 rounded-full bg-amber-100 text-amber-700 text-xs font-medium mb-4">
            演示 / 规划中 · 接口未接线
          </div>
          <div className="text-6xl mb-4">{DEMO_MODULES[activeTab].icon}</div>
          <h2 className="text-base font-semibold mb-2">{DEMO_MODULES[activeTab].title}</h2>
          <p className="text-sm text-gray-500 max-w-lg mx-auto">{DEMO_MODULES[activeTab].desc}</p>
          {activeTab === 'mcp' && (
            <Link to="/settings" className="inline-block mt-4 px-4 py-2 bg-cd-accent text-white text-sm rounded-xl">
              去设置 → 集成 → MCP 开关
            </Link>
          )}
        </div>
      )}

      {/* 遥测：真实本地功能 */}
      {activeTab === 'telemetry' && (
        <div className="glass rounded-2xl p-6 space-y-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h2 className="text-base font-semibold">本地诊断遥测</h2>
              <p className="text-xs text-gray-500 mt-1">
                仅写本机 ~/.challenge-daily/telemetry.jsonl，绝不上传；默认关闭。
              </p>
            </div>
            <span className={`px-3 py-1 rounded-full text-xs ${
              telemetry.enabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
            }`}>
              {telemetry.enabled ? '已开启' : '已关闭'}
            </span>
          </div>

          <div className="flex gap-2">
            <Link to="/settings" className="px-4 py-2 bg-cd-accent text-white text-sm rounded-xl">
              去设置调整开关
            </Link>
            <button onClick={refreshTelemetry} className="px-4 py-2 bg-white/50 border text-sm rounded-xl">
              刷新事件
            </button>
          </div>

          {!telemetry.enabled ? (
            <p className="text-sm text-gray-500">
              遥测关闭时不会记录任何事件；如需排查采集失败 / AI 熔断 / 后端异常，请在设置中开启。
            </p>
          ) : (
            <div className="space-y-2">
              <div className="text-xs text-gray-500">最近事件（{telemetry.events.length}）</div>
              {telemetry.events.length === 0 ? (
                <p className="text-sm text-gray-500">暂无事件；触发一次失败后会写入这里。</p>
              ) : (
                telemetry.events.slice(0, 10).map((ev, i) => (
                  <div key={`${ev.time}-${i}`} className="flex items-center justify-between gap-2 text-xs p-2 bg-white/50 rounded-lg">
                    <span className="font-mono">{ev.event}</span>
                    <span className="text-gray-400">
                      {new Date(ev.time * 1000).toLocaleTimeString('zh-CN', { hour12: false })}
                    </span>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

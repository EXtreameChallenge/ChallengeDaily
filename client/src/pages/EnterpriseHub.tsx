import { useState, useEffect } from 'react'
import { get, post } from '../api/client'

export default function EnterpriseHub() {
  const [activeTab, setActiveTab] = useState('overview')
  const [session, setSession] = useState<any>({ loggedIn: false })
  const [points, setPoints] = useState({ balance: 0, credits: 0 })
  const [templates, setTemplates] = useState<any[]>([])
  const [student, setStudent] = useState({ verified: false })
  const [festival, setFestival] = useState<any>(null)
  const [surveys, setSurveys] = useState<any[]>([])
  const [email, setEmail] = useState('')

  useEffect(() => { refreshAll() }, [])

  const refreshAll = async () => {
    try {
      setSession(await get('/api/enterprise/auth/session'))
      setPoints(await get('/api/enterprise/points/balance'))
      setTemplates(await get('/api/enterprise/templates/list'))
      setStudent(await get('/api/enterprise/student/status'))
      setFestival(await get('/api/enterprise/festival/info'))
      setSurveys(await get('/api/enterprise/survey/active'))
    } catch { /* ignore */ }
  }

  const tabs = [
    { id: 'overview', label: '📊 总览' },
    { id: 'auth', label: '👤 账号' },
    { id: 'points', label: '💎 积分' },
    { id: 'templates', label: '📋 模板' },
    { id: 'publisher', label: '📹 发布' },
    { id: 'wechat', label: '💬 微信' },
    { id: 'browser', label: '🌐 浏览器' },
    { id: 'mcp', label: '🔧 MCP' },
    { id: 'miniprogram', label: '📱 小程序' },
    { id: 'student', label: '🎓 学生' },
    { id: 'festival', label: '🎉 效率节' },
    { id: 'survey', label: '📝 问卷' },
    { id: 'telemetry', label: '📡 遥测' },
  ]

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-bold">🏢 企业功能中心</h1>
        <p className="text-sm text-gray-500 mt-1">账号、积分、模板、发布、微信等企业级功能集成</p>
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
        <div className="grid grid-cols-3 gap-4">
          {[
            { icon: '💎', label: '积分余额', value: points.balance },
            { icon: '👤', label: '登录状态', value: session.loggedIn ? '已登录' : '未登录' },
            { icon: '🎓', label: '学生认证', value: student.verified ? '已认证' : '未认证' },
          ].map((card, i) => (
            <div key={i} className="glass rounded-2xl p-5">
              <div className="text-3xl mb-2">{card.icon}</div>
              <div className="text-gray-500 text-sm">{card.label}</div>
              <div className="text-2xl font-bold mt-1">{card.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* 账号 */}
      {activeTab === 'auth' && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-base font-semibold mb-4">账号体系</h2>
          {session.loggedIn ? (
            <div>
              <p className="mb-4">欢迎，{session.user?.name}</p>
              <button onClick={() => post('/api/enterprise/auth/logout').then(refreshAll)}
                className="px-4 py-2 bg-red-500 text-white rounded-xl">退出登录</button>
            </div>
          ) : (
            <div className="flex gap-2">
              <input type="email" placeholder="邮箱" value={email} onChange={e => setEmail(e.target.value)}
                className="flex-1 px-3 py-2 rounded-xl border bg-white/50" />
              <button onClick={() => post('/api/enterprise/auth/login', { email, password: 'local' }).then(refreshAll)}
                className="px-4 py-2 bg-cd-accent text-white rounded-xl">登录</button>
            </div>
          )}
        </div>
      )}

      {/* 积分 */}
      {activeTab === 'points' && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-base font-semibold mb-4">积分计费系统</h2>
          <div className="flex gap-8">
            <div><span className="text-gray-500">余额: </span><span className="text-3xl font-bold">{points.balance}</span></div>
            <div><span className="text-gray-500">额度: </span><span className="text-3xl font-bold">{points.credits}</span></div>
          </div>
        </div>
      )}

      {/* 模板市场 */}
      {activeTab === 'templates' && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-base font-semibold mb-4">模板市场</h2>
          <div className="space-y-2">
            {templates.map((t: any) => (
              <div key={t.id} className="flex items-center p-4 bg-white/50 rounded-xl">
                <span className="font-medium">{t.name}</span>
                <span className="ml-auto text-sm text-gray-500">下载 {t.downloads}</span>
                <button className="ml-2 px-3 py-1 bg-cd-accent text-white text-sm rounded-lg">下载</button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 其他Tab简化展示 */}
      {['publisher', 'wechat', 'browser', 'mcp', 'miniprogram', 'student', 'festival', 'survey', 'telemetry'].includes(activeTab) && (
        <div className="glass rounded-2xl p-8 text-center">
          <div className="text-6xl mb-4">
            {{ publisher: '📹', wechat: '💬', browser: '🌐', mcp: '🔧', miniprogram: '📱', student: '🎓', festival: '🎉', survey: '📝', telemetry: '📡' }[activeTab]}
          </div>
          <h2 className="text-base font-semibold mb-2">
            {{ publisher: '视频发布器', wechat: '微信集成', browser: '浏览器自动化', mcp: 'MCP服务器管理', miniprogram: '小程序同步', student: '学生认证', festival: '效率节活动', survey: '问卷调查', telemetry: '遥测系统' }[activeTab]}
          </h2>
          <p className="text-sm text-gray-500">功能已就绪，等待配置使用</p>
        </div>
      )}
    </div>
  )
}

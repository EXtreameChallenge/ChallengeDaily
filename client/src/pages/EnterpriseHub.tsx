import { useState, useEffect } from 'react'
import { get, post } from '../api/client'

export default function EnterpriseHub() {
  const [activeTab, setActiveTab] = useState('overview')

  // 账号
  const [session, setSession] = useState<any>({ loggedIn: false })
  const [email, setEmail] = useState('')

  // 积分
  const [points, setPoints] = useState({ balance: 0, credits: 0 })

  // 模板
  const [templates, setTemplates] = useState<any[]>([])

  // 发布器
  const [pubAccounts, setPubAccounts] = useState<any[]>([])

  // 微信
  const [wechatState, setWechatState] = useState({ bound: false })

  // 学生认证
  const [student, setStudent] = useState({ verified: false })

  // 效率节
  const [festival, setFestival] = useState<any>(null)

  // 问卷
  const [surveys, setSurveys] = useState<any[]>([])

  // 遥测
  const [telemetryEvents, setTelemetryEvents] = useState<any[]>([])

  useEffect(() => {
    refreshAll()
  }, [])

  const refreshAll = async () => {
    try {
      setSession(await get('/api/enterprise/auth/session'))
      setPoints(await get('/api/enterprise/points/balance'))
      setTemplates(await get('/api/enterprise/templates/list'))
      setPubAccounts(await get('/api/enterprise/publisher/accounts'))
      setWechatState(await get('/api/enterprise/wechat/state'))
      setStudent(await get('/api/enterprise/student/status'))
      setFestival(await get('/api/enterprise/festival/info'))
      setSurveys(await get('/api/enterprise/survey/active'))
      setTelemetryEvents(await get('/api/enterprise/telemetry/events'))
    } catch { /* 后端未启动 */ }
  }

  const tabs = [
    { id: 'overview', label: '📊 总览' },
    { id: 'auth', label: '👤 账号' },
    { id: 'points', label: '💎 积分' },
    { id: 'templates', label: '📋 模板市场' },
    { id: 'publisher', label: '📹 视频发布' },
    { id: 'wechat', label: '💬 微信集成' },
    { id: 'browser', label: '🌐 浏览器自动化' },
    { id: 'mcp', label: '🔧 MCP管理' },
    { id: 'miniprogram', label: '📱 小程序同步' },
    { id: 'student', label: '🎓 学生认证' },
    { id: 'festival', label: '🎉 效率节' },
    { id: 'survey', label: '📝 问卷调查' },
    { id: 'telemetry', label: '📡 遥测系统' },
  ]

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">🏢 企业功能中心</h1>

      {/* Tab栏 */}
      <div className="flex flex-wrap gap-1 mb-6 border-b pb-2">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium ${
              activeTab === tab.id ? 'bg-blue-500 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* 总览 */}
      {activeTab === 'overview' && (
        <div className="grid grid-cols-3 gap-4">
          <div className="bg-white p-4 rounded-xl shadow">
            <div className="text-2xl mb-1">💎</div>
            <div className="text-gray-500 text-sm">积分余额</div>
            <div className="text-2xl font-bold">{points.balance}</div>
          </div>
          <div className="bg-white p-4 rounded-xl shadow">
            <div className="text-2xl mb-1">👤</div>
            <div className="text-gray-500 text-sm">登录状态</div>
            <div className="text-lg font-bold">{session.loggedIn ? '已登录' : '未登录'}</div>
          </div>
          <div className="bg-white p-4 rounded-xl shadow">
            <div className="text-2xl mb-1">🎓</div>
            <div className="text-gray-500 text-sm">学生认证</div>
            <div className="text-lg font-bold">{student.verified ? '已认证' : '未认证'}</div>
          </div>
        </div>
      )}

      {/* 账号 */}
      {activeTab === 'auth' && (
        <div className="bg-white p-6 rounded-xl shadow">
          <h2 className="text-lg font-semibold mb-4">账号体系</h2>
          {session.loggedIn ? (
            <div>
              <p className="mb-4">欢迎，{session.user?.name}</p>
              <button onClick={() => post('/api/enterprise/auth/logout')} className="px-4 py-2 bg-red-500 text-white rounded-lg">退出登录</button>
            </div>
          ) : (
            <div className="flex gap-2">
              <input type="email" placeholder="邮箱" value={email} onChange={e => setEmail(e.target.value)} className="px-3 py-2 border rounded-lg flex-1" />
              <button onClick={() => post('/api/enterprise/auth/login', { email, password: 'local' }).then(refreshAll)} className="px-4 py-2 bg-blue-500 text-white rounded-lg">登录</button>
            </div>
          )}
        </div>
      )}

      {/* 积分 */}
      {activeTab === 'points' && (
        <div className="bg-white p-6 rounded-xl shadow">
          <h2 className="text-lg font-semibold mb-4">积分计费系统</h2>
          <div className="flex gap-8 mb-6">
            <div><span className="text-gray-500">余额: </span><span className="text-2xl font-bold">{points.balance}</span></div>
            <div><span className="text-gray-500">额度: </span><span className="text-2xl font-bold">{points.credits}</span></div>
          </div>
        </div>
      )}

      {/* 模板市场 */}
      {activeTab === 'templates' && (
        <div className="bg-white p-6 rounded-xl shadow">
          <h2 className="text-lg font-semibold mb-4">模板市场</h2>
          <div className="space-y-2">
            {templates.map((t: any) => (
              <div key={t.id} className="flex items-center p-3 bg-gray-50 rounded-lg">
                <span className="font-medium">{t.name}</span>
                <span className="ml-auto text-sm text-gray-500">下载 {t.downloads}</span>
                <button className="ml-2 px-3 py-1 bg-blue-500 text-white text-sm rounded">下载</button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 视频发布 */}
      {activeTab === 'publisher' && (
        <div className="bg-white p-6 rounded-xl shadow">
          <h2 className="text-lg font-semibold mb-4">视频发布器</h2>
          <p className="text-gray-500 mb-4">绑定平台账号后可批量发布视频</p>
          <div className="space-y-2">
            {pubAccounts.map((a: any, i: number) => (
              <div key={i} className="p-3 bg-gray-50 rounded-lg">{a.platform}: {a.account}</div>
            ))}
          </div>
        </div>
      )}

      {/* 微信集成 */}
      {activeTab === 'wechat' && (
        <div className="bg-white p-6 rounded-xl shadow text-center">
          <h2 className="text-lg font-semibold mb-4">微信集成</h2>
          <p className="text-gray-500 mb-4">{wechatState.bound ? '已绑定' : '未绑定微信'}</p>
          <button onClick={() => post('/api/enterprise/wechat/begin')} className="px-4 py-2 bg-green-500 text-white rounded-lg">
            {wechatState.bound ? '重新绑定' : '开始绑定'}
          </button>
        </div>
      )}

      {/* 浏览器自动化 */}
      {activeTab === 'browser' && (
        <div className="bg-white p-6 rounded-xl shadow">
          <h2 className="text-lg font-semibold mb-4">浏览器自动化</h2>
          <p className="text-gray-500 mb-4">自动打开DeepSeek/ChatGPT并发送Prompt</p>
          <div className="flex gap-2">
            <button onClick={() => post('/api/enterprise/browser/deepseek', { prompt: '' })} className="px-4 py-2 bg-blue-500 text-white rounded-lg">打开DeepSeek</button>
            <button onClick={() => post('/api/enterprise/browser/chatgpt', { prompt: '' })} className="px-4 py-2 bg-green-500 text-white rounded-lg">打开ChatGPT</button>
          </div>
        </div>
      )}

      {/* MCP管理 */}
      {activeTab === 'mcp' && (
        <div className="bg-white p-6 rounded-xl shadow">
          <h2 className="text-lg font-semibold mb-4">MCP服务器管理</h2>
          <p className="text-gray-500">已配置 MCP 服务器列表（详见配置文件）</p>
        </div>
      )}

      {/* 小程序同步 */}
      {activeTab === 'miniprogram' && (
        <div className="bg-white p-6 rounded-xl shadow text-center">
          <h2 className="text-lg font-semibold mb-4">小程序同步</h2>
          <p className="text-gray-500 mb-4">与微信小程序数据同步</p>
          <button onClick={() => post('/api/enterprise/miniprogram/sync')} className="px-4 py-2 bg-blue-500 text-white rounded-lg">立即同步</button>
        </div>
      )}

      {/* 学生认证 */}
      {activeTab === 'student' && (
        <div className="bg-white p-6 rounded-xl shadow">
          <h2 className="text-lg font-semibold mb-4">学生认证</h2>
          {student.verified ? (
            <p>✅ 已通过学生认证</p>
          ) : (
            <div>
              <p className="text-gray-500 mb-4">使用教育邮箱验证学生身份</p>
              <input type="email" placeholder="学校邮箱" className="px-3 py-2 border rounded-lg mr-2" />
              <button className="px-4 py-2 bg-green-500 text-white rounded-lg">提交认证</button>
            </div>
          )}
        </div>
      )}

      {/* 效率节 */}
      {activeTab === 'festival' && festival && (
        <div className="bg-white p-6 rounded-xl shadow">
          <h2 className="text-lg font-semibold mb-4">🎉 {festival.title}</h2>
          <p className="text-gray-600 mb-4">{festival.description}</p>
          <div className="p-4 bg-yellow-50 rounded-lg">奖励: {festival.reward}</div>
        </div>
      )}

      {/* 问卷调查 */}
      {activeTab === 'survey' && (
        <div className="bg-white p-6 rounded-xl shadow">
          <h2 className="text-lg font-semibold mb-4">问卷调查</h2>
          {surveys.map(s => (
            <div key={s.id} className="p-4 bg-gray-50 rounded-lg mb-3">
              <p className="font-medium mb-2">{s.title}</p>
              {s.questions.map((q: any, i: number) => (
                <input key={i} placeholder={q.q} className="w-full px-3 py-2 border rounded-lg mb-2 text-sm" />
              ))}
            </div>
          ))}
        </div>
      )}

      {/* 遥测系统 */}
      {activeTab === 'telemetry' && (
        <div className="bg-white p-6 rounded-xl shadow">
          <h2 className="text-lg font-semibold mb-4">遥测事件</h2>
          <div className="space-y-1 max-h-96 overflow-auto">
            {telemetryEvents.map((e: any, i: number) => (
              <div key={i} className="text-xs p-2 bg-gray-50 rounded font-mono">
                {e.event}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

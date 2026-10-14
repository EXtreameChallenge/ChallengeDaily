import { useState, useEffect, useCallback } from 'react'
import { get, post } from '../api/client'

interface Notification {
  id: string
  title: string
  body: string
  type: string
  read: boolean
  timeStr: string
}

export default function ToolsHub() {
  const [activeTab, setActiveTab] = useState<'notifications' | 'recorder' | 'markdown' | 'pdf'>('notifications')

  // 通知中心状态
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [unreadCount, setUnreadCount] = useState(0)

  // 录音器状态
  const [recording, setRecording] = useState(false)
  const [recordDuration, setRecordDuration] = useState(0)

  // Markdown状态
  const [mdContent, setMdContent] = useState('')
  const [mdPath, setMdPath] = useState('')

  const fetchNotifications = useCallback(async () => {
    try {
      const list = await get('/api/tools/notifications/list')
      setNotifications(list || [])
      const unread = await get('/api/tools/notifications/unread-count')
      setUnreadCount(unread.count || 0)
    } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    if (activeTab === 'notifications') fetchNotifications()
  }, [activeTab, fetchNotifications])

  // 录音计时
  useEffect(() => {
    if (!recording) return
    const timer = setInterval(() => setRecordDuration(d => d + 1), 1000)
    return () => clearInterval(timer)
  }, [recording])

  const startRecording = async () => {
    try {
      await post('/api/tools/recorder/start')
      setRecording(true)
      setRecordDuration(0)
    } catch { /* ignore */ }
  }

  const stopRecording = async () => {
    try {
      await post('/api/tools/recorder/stop')
      setRecording(false)
    } catch { /* ignore */ }
  }

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60)
    const sec = s % 60
    return `${m}:${sec.toString().padStart(2, '0')}`
  }

  const tabs = [
    { id: 'notifications' as const, label: `🔔 通知中心${unreadCount > 0 ? ` (${unreadCount})` : ''}` },
    { id: 'recorder' as const, label: '🎙️ 录音器' },
    { id: 'markdown' as const, label: '📝 Markdown阅读器' },
    { id: 'pdf' as const, label: '📄 PDF工具' },
  ]

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">🧰 工具中心</h1>

      {/* Tab切换 */}
      <div className="flex gap-2 mb-6 border-b pb-2">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? 'bg-blue-500 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* 通知中心 */}
      {activeTab === 'notifications' && (
        <div className="bg-white rounded-xl shadow p-4">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold">通知列表</h2>
            <button
              onClick={() => post('/api/tools/notifications/mark-all-read')}
              className="text-sm text-blue-500 hover:underline"
            >
              全部已读
            </button>
          </div>
          {notifications.length === 0 ? (
            <div className="text-center py-12 text-gray-400">暂无通知</div>
          ) : (
            <div className="space-y-2">
              {notifications.map(n => (
                <div
                  key={n.id}
                  className={`p-3 rounded-lg border ${n.read ? 'bg-gray-50 border-gray-200' : 'bg-blue-50 border-blue-200'}`}
                >
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

      {/* 录音器 */}
      {activeTab === 'recorder' && (
        <div className="bg-white rounded-xl shadow p-8 text-center">
          <div className={`w-32 h-32 mx-auto rounded-full flex items-center justify-center mb-6 ${
            recording ? 'bg-red-100 animate-pulse' : 'bg-gray-100'
          }`}>
            <span className="text-5xl">{recording ? '🔴' : '🎙️'}</span>
          </div>
          <div className="text-4xl font-mono mb-6">{formatTime(recordDuration)}</div>
          <button
            onClick={recording ? stopRecording : startRecording}
            className={`px-8 py-3 rounded-full text-white font-medium ${
              recording ? 'bg-red-500 hover:bg-red-600' : 'bg-green-500 hover:bg-green-600'
            }`}
          >
            {recording ? '停止录音' : '开始录音'}
          </button>
          <p className="text-sm text-gray-500 mt-4">录音文件自动保存到临时目录</p>
        </div>
      )}

      {/* Markdown阅读器 */}
      {activeTab === 'markdown' && (
        <div className="bg-white rounded-xl shadow p-4">
          <div className="flex gap-2 mb-4">
            <input
              type="text"
              placeholder="输入Markdown文件路径..."
              className="flex-1 px-3 py-2 border rounded-lg text-sm"
              value={mdPath}
              onChange={e => setMdPath(e.target.value)}
            />
            <button
              onClick={async () => {
                const data = await post('/api/tools/markdown/read', { path: mdPath })
                if (data.content) setMdContent(data.content)
              }}
              className="px-4 py-2 bg-blue-500 text-white rounded-lg text-sm"
            >
              打开
            </button>
          </div>
          <textarea
            className="w-full h-96 p-4 border rounded-lg font-mono text-sm"
            value={mdContent}
            onChange={e => setMdContent(e.target.value)}
            placeholder="Markdown内容..."
          />
        </div>
      )}

      {/* PDF工具 */}
      {activeTab === 'pdf' && (
        <div className="bg-white rounded-xl shadow p-8 text-center">
          <div className="text-6xl mb-4">📄</div>
          <h2 className="text-lg font-semibold mb-2">PDF压缩工具</h2>
          <p className="text-sm text-gray-500 mb-6">选择PDF文件进行压缩优化</p>
          <button className="px-6 py-3 bg-blue-500 text-white rounded-lg">
            选择PDF文件
          </button>
        </div>
      )}
    </div>
  )
}

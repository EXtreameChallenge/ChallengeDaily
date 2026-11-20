/* eslint-disable @typescript-eslint/no-explicit-any -- 工具接口返回体为动态 JSON，局部断言即可 */
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

interface ApiResult {
  ok?: boolean
  error?: string
  content?: string
  path?: string
  filepath?: string
  pages?: number
  outputPath?: string
}

export default function ToolsHub() {
  const [activeTab, setActiveTab] = useState<'notifications' | 'recorder' | 'markdown' | 'pdf'>('notifications')
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [recording, setRecording] = useState(false)
  const [recordDuration, setRecordDuration] = useState(0)
  const [mdContent, setMdContent] = useState('')
  const [mdPath, setMdPath] = useState('')
  const [mdMsg, setMdMsg] = useState('')
  const [recMsg, setRecMsg] = useState('')
  const [mergePaths, setMergePaths] = useState('')
  const [splitInput, setSplitInput] = useState('')
  const [splitPages, setSplitPages] = useState('1-3')
  const [pdfMsg, setPdfMsg] = useState('')

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

  useEffect(() => {
    if (!recording) return
    const timer = setInterval(() => setRecordDuration(d => d + 1), 1000)
    return () => clearInterval(timer)
  }, [recording])

  const startRecording = async () => {
    try {
      const res: any = await post('/api/tools/recorder/start')
      if (res?.ok) { setRecording(true); setRecordDuration(0); setRecMsg('') }
      else setRecMsg(res?.error || '录音启动失败')
    } catch (e: any) { setRecMsg(e?.message || '录音启动失败') }
  }
  const stopRecording = async () => {
    try {
      const res: any = await post('/api/tools/recorder/stop')
      setRecording(false)
      setRecMsg(res?.ok ? `已保存到临时目录：${res.filepath}` : (res?.error || '录音保存失败'))
    } catch (e: any) { setRecording(false); setRecMsg('录音保存失败') }
  }

  const saveMarkdown = async () => {
    if (!mdPath) { setMdMsg('请先填写文件路径（仅允许应用数据目录）'); return }
    try {
      const res: any = await post('/api/tools/markdown/save', { path: mdPath, content: mdContent })
      setMdMsg(res?.ok ? `已保存：${res.path}` : (res?.error || '保存失败'))
    } catch (e: any) { setMdMsg(e?.message || '保存失败（路径需位于应用数据目录）') }
  }

  const mergePdf = async () => {
    const paths = mergePaths.split('\n').map(s => s.trim()).filter(Boolean)
    if (paths.length < 2) { setPdfMsg('至少填写 2 个 PDF 路径，每行一个'); return }
    try {
      const res: any = await post('/api/tools/pdf/merge', { inputPaths: paths, outputPath: '' })
      setPdfMsg(res?.ok ? `已合并 ${res.pages} 页：${res.outputPath}` : (res?.error || '合并失败'))
    } catch (e: any) { setPdfMsg(e?.message || '合并失败') }
  }

  const splitPdf = async () => {
    if (!splitInput) { setPdfMsg('请填写要拆分的 PDF 路径'); return }
    try {
      const res: any = await post('/api/tools/pdf/split', { inputPath: splitInput, pages: splitPages, outputDir: '' })
      setPdfMsg(res?.ok ? `已拆出 ${res.pages} 页：${res.outputPath}` : (res?.error || '拆分失败'))
    } catch (e: any) { setPdfMsg(e?.message || '拆分失败') }
  }

  const formatTime = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`

  const tabs = [
    { id: 'notifications' as const, label: `🔔 通知${unreadCount > 0 ? ` (${unreadCount})` : ''}` },
    { id: 'recorder' as const, label: '🎙️ 录音器' },
    { id: 'markdown' as const, label: '📝 Markdown' },
    { id: 'pdf' as const, label: '📄 PDF工具' },
  ]

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-bold">🧰 工具中心</h1>
        <p className="text-sm text-gray-500 mt-1">通知、录音、文档、PDF 一站式工具集合</p>
      </div>

      {/* Tab切换 - glass风格 */}
      <div className="glass rounded-2xl p-1 mb-6 flex gap-1">
        {tabs.map(tab => (
          <button key={tab.id} onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 rounded-xl text-sm font-medium transition-all ${
              activeTab === tab.id ? 'bg-cd-accent text-white shadow' : 'text-gray-600 hover:bg-white/50'
            }`}>
            {tab.label}
          </button>
        ))}
      </div>

      {/* 通知中心 */}
      {activeTab === 'notifications' && (
        <div className="glass rounded-2xl p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-base font-semibold">通知列表</h2>
            <button onClick={() => post('/api/tools/notifications/mark-all-read')}
              className="text-sm text-blue-500 hover:underline">全部已读</button>
          </div>
          {notifications.length === 0 ? (
            <div className="text-center py-12 text-gray-400">暂无通知</div>
          ) : (
            <div className="space-y-2">
              {notifications.map(n => (
                <div key={n.id}
                  className={`p-4 rounded-xl border transition-colors ${n.read ? 'bg-white/30 border-gray-200' : 'bg-blue-50/50 border-blue-200'}`}>
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
        <div className="glass rounded-2xl p-8 text-center">
          <div className={`w-28 h-28 mx-auto rounded-full flex items-center justify-center mb-6 transition-all ${recording ? 'bg-red-100 animate-pulse' : 'bg-gray-100'}`}>
            <span className="text-5xl">{recording ? '🔴' : '🎙️'}</span>
          </div>
          <div className="text-4xl font-mono mb-6">{formatTime(recordDuration)}</div>
          <button onClick={recording ? stopRecording : startRecording}
            className={`px-8 py-3 rounded-full text-white font-medium transition-colors ${recording ? 'bg-red-500 hover:bg-red-600' : 'bg-green-500 hover:bg-green-600'}`}>
            {recording ? '停止录音' : '开始录音'}
          </button>
          <p className="text-sm text-gray-500 mt-4">录音文件自动保存到临时目录</p>
          {recMsg && <p className="text-xs text-amber-600 mt-2 break-all">{recMsg}</p>}
        </div>
      )}

      {/* Markdown阅读器 */}
      {activeTab === 'markdown' && (
        <div className="glass rounded-2xl p-6">
          <div className="flex gap-2 mb-4">
            <input type="text" placeholder="输入Markdown文件路径..."
              className="flex-1 px-3 py-2 rounded-xl border text-sm bg-white/50"
              value={mdPath} onChange={e => setMdPath(e.target.value)} />
            <button onClick={async () => {
              const data: any = await post('/api/tools/markdown/read', { path: mdPath })
              if (data.content) setMdContent(data.content)
              setMdMsg(data?.ok ? '' : (data?.error || '打开失败'))
            }} className="px-4 py-2 bg-cd-accent text-white rounded-xl text-sm">打开</button>
            <button onClick={saveMarkdown}
              className="px-4 py-2 bg-emerald-600 text-white rounded-xl text-sm">保存</button>
          </div>
          {mdMsg && <p className="text-xs text-amber-600 mb-2 break-all">{mdMsg}</p>}
          <p className="text-xs text-gray-400 mb-2">保存仅允许写入应用数据目录下的 .md/.txt 文件</p>
          <textarea className="w-full h-96 p-4 rounded-xl border font-mono text-sm bg-white/50"
            value={mdContent} onChange={e => setMdContent(e.target.value)} placeholder="Markdown内容..." />
        </div>
      )}

      {/* PDF工具 */}
      {activeTab === 'pdf' && (
        <div className="glass rounded-2xl p-6 space-y-6">
          {pdfMsg && <p className="text-xs text-amber-600 break-all">{pdfMsg}</p>}

          <div>
            <h2 className="text-base font-semibold mb-2">合并 PDF</h2>
            <p className="text-xs text-gray-500 mb-2">每行填写一个 PDF 绝对路径（至少 2 个）</p>
            <textarea className="w-full h-24 p-3 rounded-xl border font-mono text-xs bg-white/50"
              value={mergePaths} onChange={e => setMergePaths(e.target.value)}
              placeholder={'C:\\Users\\me\\a.pdf\nC:\\Users\\me\\b.pdf'} />
            <button onClick={mergePdf}
              className="mt-2 px-5 py-2 bg-cd-accent text-white rounded-xl text-sm">合并</button>
          </div>

          <div>
            <h2 className="text-base font-semibold mb-2">拆分 PDF</h2>
            <div className="flex gap-2 flex-wrap">
              <input className="flex-1 min-w-[240px] px-3 py-2 rounded-xl border text-sm bg-white/50"
                placeholder="PDF 绝对路径" value={splitInput} onChange={e => setSplitInput(e.target.value)} />
              <input className="w-32 px-3 py-2 rounded-xl border text-sm bg-white/50"
                placeholder="页码 1-3,5" value={splitPages} onChange={e => setSplitPages(e.target.value)} />
              <button onClick={splitPdf}
                className="px-5 py-2 bg-cd-accent text-white rounded-xl text-sm">拆分</button>
            </div>
          </div>

          <div className="border-t pt-4">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold">压缩 PDF</h2>
              <button disabled
                className="px-5 py-2 bg-gray-200 text-gray-500 rounded-xl text-sm cursor-not-allowed">规划中</button>
            </div>
            <p className="text-xs text-gray-500 mt-2">真实压缩需 Ghostscript/qpdf 引擎，当前未集成，不做“原样复制”的假压缩。</p>
          </div>
        </div>
      )}
    </div>
  )
}

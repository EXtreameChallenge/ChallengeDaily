import { useState, useEffect, useRef, useCallback } from 'react'
import { Send, Trash2, Bot, User, Sparkles } from 'lucide-react'
import { aiChat, getChatHistory, clearChatHistory, type ChatMessage } from '../api/client'

const PRESET_QUESTIONS = [
  '我这周哪天效率最高？',
  '我最近在用什么新工具？',
  '帮我生成本周复盘总结',
  '我今天的工作重心是什么？',
  '我最近的工作趋势如何？',
]

export default function AIChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  // 用于取消前一次未完成的请求，避免快速连续发送导致回答顺序错乱
  const abortRef = useRef<AbortController | null>(null)

  const load = useCallback(async () => {
    try {
      const { history } = await getChatHistory()
      setMessages(history)
    } catch {}
  }, [])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [messages])

  const handleSend = async (text?: string) => {
    const msg = (text || input).trim()
    if (!msg || loading) return
    setInput('')
    setLoading(true)
    setMessages(prev => [...prev, { id: Date.now(), role: 'user', content: msg, created_at: new Date().toISOString() }])
    // 取消前一次未完成的请求，避免快速连续发送导致回答顺序错乱
    if (abortRef.current) abortRef.current.abort()
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const { reply } = await aiChat(msg, controller.signal)
      // 已被后续请求取消，丢弃本次结果
      if (controller.signal.aborted) return
      // 检测后端返回的"未配置"提示，替换为更友好的引导
      if (reply.includes('未配置') || reply.includes('not configured')) {
        setMessages(prev => [...prev, { id: Date.now() + 1, role: 'assistant', content: 'AI 尚未配置，请先在「设置 → AI 分析」中配置智谱 GLM API Key。', created_at: new Date().toISOString() }])
      } else {
        setMessages(prev => [...prev, { id: Date.now() + 1, role: 'assistant', content: reply, created_at: new Date().toISOString() }])
      }
    } catch (e: any) {
      // 被后续请求主动取消，静默忽略
      if (controller.signal.aborted || (e?.name === 'AbortError')) {
        return
      }
      const msg = e?.message || ''
      const isNotConfigured = msg.includes('未配置') || msg.includes('not configured') || msg.includes('API')
      const errorText = isNotConfigured
        ? 'AI 尚未配置，请先在「设置 → AI 分析」中配置智谱 GLM API Key。'
        : 'AI 暂时无法回复，请检查网络连接后重试。'
      setMessages(prev => [...prev, { id: Date.now() + 1, role: 'assistant', content: errorText, created_at: new Date().toISOString() }])
    } finally {
      // 仅当本次请求仍是最新一次时才解除 loading
      if (abortRef.current === controller) {
        setLoading(false)
      }
    }
  }

  const handleClear = async () => {
    await clearChatHistory()
    setMessages([])
  }

  return (
    <div className="min-h-screen flex flex-col max-w-3xl mx-auto p-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold text-cd-text flex items-center gap-2">
          <Bot className="text-purple-400" /> AI对话
        </h1>
        {messages.length > 0 && (
          <button onClick={handleClear} className="text-cd-text-secondary hover:text-red-400 transition">
            <Trash2 size={18} />
          </button>
        )}
      </div>

      {/* 对话区域 */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto space-y-3 mb-4 min-h-[300px]">
        {messages.length === 0 && (
          <div className="text-center py-12">
            <Sparkles size={48} className="mx-auto mb-3 text-purple-400/50" />
            <p className="text-cd-text-secondary mb-4">基于你的工作数据，问点什么吧</p>
            <div className="flex flex-wrap gap-2 justify-center">
              {PRESET_QUESTIONS.map(q => (
                <button key={q} onClick={() => handleSend(q)}
                  className="px-3 py-1.5 bg-purple-500/10 text-purple-300 rounded-lg border border-purple-400/20 hover:bg-purple-500/20 transition text-sm">
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map(msg => (
          <div key={msg.id} className={`flex gap-2 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
              msg.role === 'user' ? 'bg-blue-500/20 text-blue-400' : 'bg-purple-500/20 text-purple-400'
            }`}>
              {msg.role === 'user' ? <User size={16} /> : <Bot size={16} />}
            </div>
            <div className={`max-w-[80%] rounded-xl p-3 ${
              msg.role === 'user' ? 'bg-blue-500/10 text-cd-text' : 'bg-cd-bg-card text-cd-text'
            }`}>
              <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</p>
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex gap-2">
            <div className="w-8 h-8 rounded-full bg-purple-500/20 text-purple-400 flex items-center justify-center">
              <Bot size={16} />
            </div>
            <div className="bg-cd-bg-card rounded-xl p-3">
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-purple-400/60 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 bg-purple-400/60 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 bg-purple-400/60 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 输入框 */}
      <div className="flex gap-2">
        <input type="text" value={input} onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSend()}
          placeholder="基于工作数据问点什么..."
          className="flex-1 bg-cd-bg-input border border-white/5 rounded-lg px-4 py-2.5 text-cd-text focus:outline-none focus:border-purple-400/40"
          disabled={loading}
        />
        <button onClick={() => handleSend()} disabled={loading || !input.trim()}
          className="px-4 py-2.5 bg-purple-500/20 text-purple-300 rounded-lg border border-purple-400/30 hover:bg-purple-500/30 transition disabled:opacity-50">
          <Send size={18} />
        </button>
      </div>
    </div>
  )
}

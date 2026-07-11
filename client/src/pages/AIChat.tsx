import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { Send, Trash2, Bot, User, Sparkles, RefreshCw, CheckCircle, XCircle, Search, BarChart3, ListTodo, Timer, FileText, TrendingUp, UserCircle, Loader2 } from 'lucide-react'
import { aiChatStream, getChatHistory, clearChatHistory, executeChatAction, type ChatMessage, type ChatStreamEvent, type ActionConfirmation } from '../api/client'

// ── 工具名称映射 ──
const TOOL_LABELS: Record<string, { label: string; icon: string }> = {
  get_activities: { label: '查询活动记录', icon: '🔍' },
  get_todos: { label: '查询待办列表', icon: '📋' },
  get_pomodoro_stats: { label: '查询番茄钟', icon: '🍅' },
  get_daily_summary: { label: '查询日画像', icon: '📊' },
  get_work_trends: { label: '查询效率趋势', icon: '📈' },
  get_user_profile: { label: '查询用户画像', icon: '👤' },
  create_todo: { label: '创建待办', icon: '✏️' },
  start_pomodoro: { label: '启动番茄钟', icon: '🍅' },
  save_diary: { label: '保存日记', icon: '📝' },
}

// ── 快捷操作卡片 ──
const QUICK_ACTIONS = [
  { label: '今日工作概览', icon: BarChart3, prompt: '我今天的工作情况怎么样？请给我一个概览' },
  { label: '效率趋势分析', icon: TrendingUp, prompt: '分析我最近7天的工作效率趋势，有什么变化和规律？' },
  { label: '待办进展', icon: ListTodo, prompt: '我还有哪些待办没完成？帮我整理一下' },
  { label: '番茄钟统计', icon: Timer, prompt: '我最近的番茄钟执行情况怎么样？' },
  { label: '生成本周复盘', icon: FileText, prompt: '帮我生成本周的工作复盘总结，包含数据和分析' },
  { label: '深度画像', icon: UserCircle, prompt: '介绍一下我的工作画像和特征' },
]

// ── 简易 Markdown 渲染 ──
function renderMarkdown(text: string): string {
  let html = text
  // 代码块
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="bg-cd-bg-secondary rounded-lg p-3 my-2 text-xs overflow-x-auto border border-cd-border"><code>$2</code></pre>')
  // 行内代码
  html = html.replace(/`([^`]+)`/g, '<code class="bg-cd-bg-secondary px-1.5 py-0.5 rounded text-xs font-mono text-cd-accent">$1</code>')
  // 加粗
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  // 斜体
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>')
  // 标题
  html = html.replace(/^### (.+)$/gm, '<h3 class="text-sm font-semibold mt-3 mb-1">$1</h3>')
  html = html.replace(/^## (.+)$/gm, '<h2 class="text-base font-semibold mt-3 mb-1">$1</h2>')
  // 无序列表
  html = html.replace(/^- (.+)$/gm, '<li class="ml-4 list-disc">$1</li>')
  // 有序列表
  html = html.replace(/^\d+\. (.+)$/gm, '<li class="ml-4 list-decimal">$1</li>')
  // 换行
  html = html.replace(/\n/g, '<br/>')
  return html
}

// ── 提取操作确认 ──
function extractActionConfirmations(content: string): { text: string; actions: ActionConfirmation[] } {
  const actions: ActionConfirmation[] = []
  let text = content
  // 匹配 JSON 格式的操作确认
  const jsonRegex = /\{[^{}]*"action"\s*:\s*"([^"]+)"[^{}]*"data"\s*:\s*\{[^{}]*\}[^{}]*"confirm_message"\s*:\s*"([^"]+)"[^{}]*\}/g
  let match
  while ((match = jsonRegex.exec(content)) !== null) {
    try {
      const actionObj = JSON.parse(match[0])
      if (actionObj.action && actionObj.data && actionObj.confirm_message) {
        actions.push(actionObj as ActionConfirmation)
        text = text.replace(match[0], '')
      }
    } catch {}
  }
  return { text: text.trim(), actions }
}

interface DisplayMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  created_at: string
  toolCalls?: { name: string; id: string; status: 'calling' | 'done' }[]
  actions?: ActionConfirmation[]
  actionResults?: Record<string, 'confirmed' | 'rejected'>
  isStreaming?: boolean
}

export default function AIChat() {
  const [messages, setMessages] = useState<DisplayMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [currentToolCalls, setCurrentToolCalls] = useState<{ name: string; id: string; status: 'calling' | 'done' }[]>([])
  const scrollRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const streamingContentRef = useRef('')

  const load = useCallback(async () => {
    try {
      const { history } = await getChatHistory()
      setMessages(history.map(m => ({ ...m, toolCalls: [], actions: [], actionResults: {} })))
    } catch {}
  }, [])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, currentToolCalls])

  const handleSend = async (text?: string) => {
    const msg = (text || input).trim()
    if (!msg || loading) return
    setInput('')
    setLoading(true)
    streamingContentRef.current = ''

    const userMsg: DisplayMessage = {
      id: Date.now(),
      role: 'user',
      content: msg,
      created_at: new Date().toISOString(),
      toolCalls: [],
      actions: [],
      actionResults: {},
    }
    // 创建AI消息占位
    const assistantId = Date.now() + 1
    const assistantMsg: DisplayMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      created_at: new Date().toISOString(),
      toolCalls: [],
      actions: [],
      actionResults: {},
      isStreaming: true,
    }
    setMessages(prev => [...prev, userMsg, assistantMsg])
    setCurrentToolCalls([])

    if (abortRef.current) abortRef.current.abort()
    const controller = new AbortController()
    abortRef.current = controller

    try {
      await aiChatStream(
        msg,
        (event: ChatStreamEvent) => {
          if (controller.signal.aborted) return

          switch (event.type) {
            case 'content':
              streamingContentRef.current += event.content
              setMessages(prev => prev.map(m =>
                m.id === assistantId
                  ? { ...m, content: streamingContentRef.current }
                  : m
              ))
              break

            case 'tool_call':
              setCurrentToolCalls(prev => {
                const updated = [...prev.filter(t => t.id !== event.id), { name: event.name, id: event.id, status: 'calling' as const }]
                setMessages(prev2 => prev2.map(m =>
                  m.id === assistantId
                    ? { ...m, toolCalls: updated }
                    : m
                ))
                return updated
              })
              break

            case 'tool_result':
              setCurrentToolCalls(prev => {
                const updated = prev.map(t => t.id === event.id ? { ...t, status: 'done' as const } : t)
                setMessages(prev2 => prev2.map(m =>
                  m.id === assistantId
                    ? { ...m, toolCalls: updated }
                    : m
                ))
                return updated
              })
              break

            case 'done':
              setMessages(prev => prev.map(m => {
                if (m.id !== assistantId) return m
                const { text, actions } = extractActionConfirmations(m.content)
                return { ...m, content: text, actions, isStreaming: false }
              }))
              setCurrentToolCalls([])
              break

            case 'error':
              setMessages(prev => prev.map(m =>
                m.id === assistantId
                  ? { ...m, content: event.content || 'AI 暂时无法回复', isStreaming: false }
                  : m
              ))
              setCurrentToolCalls([])
              break
          }
        },
        controller.signal,
      )
    } catch (e: any) {
      if (controller.signal.aborted || e?.name === 'AbortError') return
      setMessages(prev => prev.map(m =>
        m.id === assistantId
          ? { ...m, content: 'AI 暂时无法回复，请检查网络连接后重试。', isStreaming: false }
          : m
      ))
    } finally {
      if (abortRef.current === controller) {
        setLoading(false)
      }
    }
  }

  const handleRegenerate = () => {
    // 删除最后一条assistant消息，重新发送倒数第二条user消息
    const lastUserMsg = [...messages].reverse().find(m => m.role === 'user')
    if (!lastUserMsg) return
    setMessages(prev => prev.slice(0, -1))
    handleSend(lastUserMsg.content)
  }

  const handleClear = async () => {
    await clearChatHistory()
    setMessages([])
  }

  const handleActionConfirm = async (action: ActionConfirmation, msgId: number, actionIdx: number) => {
    try {
      await executeChatAction(action.action, action.data)
      setMessages(prev => prev.map(m =>
        m.id === msgId
          ? { ...m, actionResults: { ...m.actionResults, [actionIdx]: 'confirmed' as const } }
          : m
      ))
    } catch {
      setMessages(prev => prev.map(m =>
        m.id === msgId
          ? { ...m, actionResults: { ...m.actionResults, [actionIdx]: 'rejected' as const } }
          : m
      ))
    }
  }

  const handleActionReject = (msgId: number, actionIdx: number) => {
    setMessages(prev => prev.map(m =>
      m.id === msgId
        ? { ...m, actionResults: { ...m.actionResults, [actionIdx]: 'rejected' as const } }
        : m
    ))
  }

  const lastMsg = messages[messages.length - 1]
  const canRegenerate = !loading && lastMsg?.role === 'assistant' && !lastMsg.isStreaming

  return (
    <div className="min-h-screen flex flex-col h-full">
      {/* ─── 标题栏 ─── */}
      <div className="flex items-center justify-between px-6 pt-5 pb-3">
        <h1 className="text-lg font-semibold text-cd-text flex items-center gap-2">
          <Bot size={20} className="text-cd-green" />
          AI 智能体
        </h1>
        <div className="flex items-center gap-2">
          {canRegenerate && (
            <button onClick={handleRegenerate} className="p-1.5 text-cd-text-secondary hover:text-cd-green transition rounded-lg hover:bg-cd-hover" title="重新生成">
              <RefreshCw size={16} />
            </button>
          )}
          {messages.length > 0 && (
            <button onClick={handleClear} className="p-1.5 text-cd-text-secondary hover:text-red-400 transition rounded-lg hover:bg-cd-hover" title="清空对话">
              <Trash2 size={16} />
            </button>
          )}
        </div>
      </div>

      {/* ─── 对话区域 ─── */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 pb-4">
        {messages.length === 0 ? (
          <div className="text-center py-12">
            <div className="w-16 h-16 rounded-2xl bg-cd-green/10 flex items-center justify-center mx-auto mb-4">
              <Sparkles size={28} className="text-cd-green" />
            </div>
            <h2 className="text-base font-semibold text-cd-text mb-1">工作智能体</h2>
            <p className="text-sm text-cd-text-secondary mb-6">你可以问我关于工作数据的任何事情，我也能帮你创建待办、启动番茄钟</p>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 max-w-lg mx-auto">
              {QUICK_ACTIONS.map(q => (
                <button
                  key={q.label}
                  onClick={() => handleSend(q.prompt)}
                  className="flex items-center gap-2 px-3 py-2.5 bg-cd-bg-card text-cd-text rounded-xl border border-cd-border hover:border-cd-green/30 hover:bg-cd-green/5 transition text-xs text-left"
                >
                  <q.icon size={14} className="text-cd-green shrink-0" />
                  {q.label}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-4 max-w-3xl mx-auto">
            {messages.map(msg => (
              <div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                {/* 头像 */}
                <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
                  msg.role === 'user'
                    ? 'bg-blue-500/15 text-blue-400'
                    : 'bg-cd-green/15 text-cd-green'
                }`}>
                  {msg.role === 'user' ? <User size={16} /> : <Bot size={16} />}
                </div>

                {/* 内容 */}
                <div className={`max-w-[85%] space-y-2 ${msg.role === 'user' ? 'items-end' : ''}`}>
                  {/* 工具调用状态 */}
                  {msg.toolCalls && msg.toolCalls.length > 0 && msg.isStreaming && (
                    <div className="space-y-1.5">
                      {msg.toolCalls.map(tc => (
                        <div key={tc.id} className="flex items-center gap-2 text-xs px-3 py-1.5 bg-cd-bg-card rounded-lg border border-cd-border">
                          {tc.status === 'calling' ? (
                            <Loader2 size={12} className="text-cd-green animate-spin" />
                          ) : (
                            <CheckCircle size={12} className="text-cd-green" />
                          )}
                          <span className="text-cd-text-secondary">
                            {TOOL_LABELS[tc.name]?.icon || '🔧'} {TOOL_LABELS[tc.name]?.label || tc.name}
                            {tc.status === 'calling' ? ' 查询中...' : ' 已完成'}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* 消息内容 */}
                  {msg.content && (
                    <div className={`rounded-2xl px-4 py-3 ${
                      msg.role === 'user'
                        ? 'bg-blue-500/10 text-cd-text rounded-tr-sm'
                        : 'bg-cd-bg-card text-cd-text rounded-tl-sm border border-cd-border'
                    }`}>
                      {msg.role === 'assistant' ? (
                        <div
                          className="text-sm leading-relaxed prose-sm [&_br]:block [&_pre]:my-2 [&_code]:text-cd-green [&_li]:text-cd-text [&_strong]:text-cd-text"
                          dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }}
                        />
                      ) : (
                        <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                      )}
                    </div>
                  )}

                  {/* 流式生成中的光标 */}
                  {msg.isStreaming && !msg.content && !(msg.toolCalls && msg.toolCalls.length > 0) && (
                    <div className="bg-cd-bg-card rounded-2xl px-4 py-3 border border-cd-border rounded-tl-sm">
                      <div className="flex gap-1">
                        <span className="w-2 h-2 bg-cd-green/60 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                        <span className="w-2 h-2 bg-cd-green/60 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                        <span className="w-2 h-2 bg-cd-green/60 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                      </div>
                    </div>
                  )}

                  {/* 操作确认卡片 */}
                  {msg.actions && msg.actions.map((action, idx) => {
                    const result = msg.actionResults?.[idx]
                    return (
                      <div key={idx} className="bg-cd-bg-card rounded-xl border border-cd-green/20 p-3">
                        <div className="flex items-center gap-2 mb-2">
                          <Sparkles size={14} className="text-cd-green" />
                          <span className="text-xs font-medium text-cd-text">操作确认</span>
                        </div>
                        <p className="text-sm text-cd-text mb-3">{action.confirm_message}</p>
                        {result === 'confirmed' ? (
                          <div className="flex items-center gap-1.5 text-xs text-cd-green">
                            <CheckCircle size={14} /> 已确认执行
                          </div>
                        ) : result === 'rejected' ? (
                          <div className="flex items-center gap-1.5 text-xs text-cd-text-tertiary">
                            <XCircle size={14} /> 已取消
                          </div>
                        ) : (
                          <div className="flex gap-2">
                            <button
                              onClick={() => handleActionConfirm(action, msg.id, idx)}
                              className="px-3 py-1.5 text-xs font-medium bg-cd-green text-white rounded-lg hover:opacity-90 transition"
                            >
                              确认执行
                            </button>
                            <button
                              onClick={() => handleActionReject(msg.id, idx)}
                              className="px-3 py-1.5 text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary rounded-lg hover:bg-cd-hover transition border border-cd-border"
                            >
                              取消
                            </button>
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ─── 输入区 ─── */}
      <div className="px-6 pb-5 pt-2">
        <div className="max-w-3xl mx-auto">
          <div className="flex gap-2 items-end bg-cd-bg-card rounded-2xl border border-cd-border p-2 focus-within:border-cd-green/30 transition">
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  handleSend()
                }
              }}
              placeholder="问我关于工作数据的任何问题..."
              className="flex-1 bg-transparent text-cd-text text-sm px-2 py-1.5 focus:outline-none resize-none max-h-32 placeholder:text-cd-text-tertiary"
              rows={1}
              disabled={loading}
              style={{ minHeight: '36px' }}
              onInput={e => {
                const el = e.target as HTMLTextAreaElement
                el.style.height = 'auto'
                el.style.height = Math.min(el.scrollHeight, 128) + 'px'
              }}
            />
            <button
              onClick={() => handleSend()}
              disabled={loading || !input.trim()}
              className="p-2 bg-cd-green text-white rounded-xl hover:opacity-90 transition disabled:opacity-30 shrink-0"
            >
              <Send size={16} />
            </button>
          </div>
          <p className="text-[10px] text-cd-text-tertiary mt-1.5 text-center">
            支持查询活动记录、待办、番茄钟等数据 · 也可帮你创建待办、启动番茄钟
          </p>
        </div>
      </div>
    </div>
  )
}

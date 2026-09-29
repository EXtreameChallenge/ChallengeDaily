import { useState, useEffect, useRef, useCallback, useMemo, Children, type ReactElement } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Send, Plus, Trash2, Bot, Sparkles, RefreshCw,
  Check, Copy, X, Paperclip, ChevronDown, ArrowDown, Brain,
  BarChart3, ListTodo, Timer, FileText, TrendingUp, UserCircle,
  Loader2, PanelLeftClose, PanelLeftOpen, Square, Settings,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { aiChatStream, getChatHistory, clearChatHistory, executeChatAction, type ChatMessage, type ChatStreamEvent, type ActionConfirmation } from '../api/client'

// ── 工具名称映射（中文标签）──
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

// ── 工具调用状态：preparing(灰脉冲) / running(扫光) / done(绿勾) / failed(红) ──
type ToolStatus = 'preparing' | 'running' | 'done' | 'failed'

interface ToolCall {
  id: string
  name: string
  status: ToolStatus
  result?: string
  startedAt: number
}

interface Attachment {
  id: string
  name: string
  size: number
}

interface DisplayMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  created_at: string
  reasoning?: string
  toolCalls?: ToolCall[]
  actions?: ActionConfirmation[]
  actionResults?: Record<number, 'confirmed' | 'rejected'>
  isStreaming?: boolean
}

// ── 日期分组辅助 ──
function sameDay(a: Date, b: Date) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
}
function dateKey(iso: string) {
  const d = new Date(iso)
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
}
function dateLabel(iso: string): string {
  const d = new Date(iso)
  if (sameDay(d, new Date())) return '今天'
  const y = new Date(); y.setDate(y.getDate() - 1)
  if (sameDay(d, y)) return '昨天'
  return `${d.getMonth() + 1}月${d.getDate()}日`
}
function timeLabel(iso: string): string {
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

// ── 提取操作确认（保留原逻辑）──
function extractActionConfirmations(content: string): { text: string; actions: ActionConfirmation[] } {
  const actions: ActionConfirmation[] = []
  let text = content
  const jsonRegex = /\{[^{}]*"action"\s*:\s*"([^"]+)"[^{}]*"data"\s*:\s*\{[^{}]*\}[^{}]*"confirm_message"\s*:\s*"([^"]+)"[^{}]*\}/g
  let match
  while ((match = jsonRegex.exec(content)) !== null) {
    try {
      const actionObj = JSON.parse(match[0])
      if (actionObj.action && actionObj.data && actionObj.confirm_message) {
        actions.push(actionObj as ActionConfirmation)
        text = text.replace(match[0], '')
      }
    } catch { /* ignore */ }
  }
  return { text: text.trim(), actions }
}

// ════════════════════════════════════════════
//  代码块：语言标签 banner + 复制按钮（深色背景，16px 圆角）
// ════════════════════════════════════════════
function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false)
  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* ignore */ }
  }
  return (
    <div className="aic-code">
      <div className="aic-code-banner">
        <span className="aic-code-lang">{language || 'code'}</span>
        <button onClick={onCopy}>
          {copied ? <Check size={11} /> : <Copy size={11} />}
          {copied ? '已复制' : '复制'}
        </button>
      </div>
      <pre><code>{code}</code></pre>
    </div>
  )
}

// ════════════════════════════════════════════
//  思考过程折叠行（24px 单行，13px 灰字，运行中 shimmer）
// ════════════════════════════════════════════
function ReasoningRow({ text, running }: { text: string; running?: boolean }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="aic-think">
      <button className="aic-think-row" onClick={() => setOpen(o => !o)}>
        <Brain size={14} className="shrink-0 text-cd-text-tertiary" />
        <span className={running && !open ? 'text-shimmer' : ''}>深度思考</span>
        {text && <span className="aic-think-dot" />}
        {text && (
          <span className={`flex-1 min-w-0 truncate ${running ? 'aic-streaming-mask' : ''}`}>
            {text.slice(0, 60)}
          </span>
        )}
        <ChevronDown size={14} className={`ml-auto shrink-0 text-cd-text-tertiary transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="aic-think-body">{text || '（暂无思考内容）'}</div>
      )}
    </div>
  )
}

// ════════════════════════════════════════════
//  工具调用行（24px 单行，中文工具名 + 状态图标 + 耗时，结果可展开）
// ════════════════════════════════════════════
function ToolRow({ tool }: { tool: ToolCall }) {
  const [open, setOpen] = useState(false)
  const meta = TOOL_LABELS[tool.name] || { label: tool.name, icon: '🔧' }

  const stateIcon = () => {
    switch (tool.status) {
      case 'running':
        return <Loader2 size={13} className="text-cd-accent animate-spin shrink-0" />
      case 'done':
        return <Check size={13} className="text-cd-accent shrink-0" />
      case 'failed':
        return <X size={13} className="text-cd-red shrink-0" />
      default:
        return <span className="w-2 h-2 rounded-full bg-cd-text-tertiary/40 animate-pulse-soft shrink-0" />
    }
  }

  const elapsed = Math.max(1, Math.round((Date.now() - tool.startedAt) / 1000))
  const statusText = tool.status === 'running' ? `${elapsed}s` : tool.status === 'done' ? '完成' : tool.status === 'failed' ? '失败' : '等待中'

  return (
    <div>
      <button className="aic-tool-row" onClick={() => setOpen(o => !o)}>
        {stateIcon()}
        <span className={tool.status === 'running' ? 'text-shimmer' : ''}>
          {meta.icon} {meta.label}
        </span>
        <span className="aic-think-dot" />
        <span className="flex-1 min-w-0 text-cd-text-tertiary truncate text-xs">{statusText}</span>
        <ChevronDown size={14} className={`ml-auto shrink-0 text-cd-text-tertiary transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && tool.result != null && (
        <div className="aic-tool-result">{tool.result}</div>
      )}
    </div>
  )
}

// ════════════════════════════════════════════
//  主页面
// ════════════════════════════════════════════
export default function AIChat() {
  const [messages, setMessages] = useState<DisplayMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [attachments, setAttachments] = useState<Attachment[]>([])
  const [showJump, setShowJump] = useState(false)
  const [deepThink, setDeepThink] = useState(false)
  const [webSearch, setWebSearch] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const streamingContentRef = useRef('')
  const nearBottomRef = useRef(true)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const sentFromUrlRef = useRef(false)

  const [searchParams, setSearchParams] = useSearchParams()

  // ── 加载历史 ──
  const load = useCallback(async () => {
    try {
      const { history } = await getChatHistory()
      setMessages(history.map(m => ({ ...m, toolCalls: [], actions: [], actionResults: {} })))
    } catch { /* ignore */ }
  }, [])

  useEffect(() => { load() }, [load])

  // ── 从 AIDock 跳转携带的 ?msg ──
  useEffect(() => {
    const m = searchParams.get('msg')
    if (m && !sentFromUrlRef.current) {
      sentFromUrlRef.current = true
      setSearchParams({}, { replace: true })
      setTimeout(() => handleSend(m), 100)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── 智能滚动：用户上滚后停止跟随 ──
  const onScroll = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    nearBottomRef.current = near
    setShowJump(!near)
  }, [])

  useEffect(() => {
    if (nearBottomRef.current && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  const jumpToBottom = () => {
    nearBottomRef.current = true
    setShowJump(false)
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }

  // ── 发送 ──
  const handleSend = async (text?: string) => {
    const msg = (text || input).trim()
    if (!msg || loading) return
    setInput('')
    setAttachments([])
    setLoading(true)
    streamingContentRef.current = ''

    const userMsg: DisplayMessage = {
      id: Date.now(),
      role: 'user',
      content: msg,
      created_at: new Date().toISOString(),
    }
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
    nearBottomRef.current = true
    setMessages(prev => [...prev, userMsg, assistantMsg])

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
                m.id === assistantId ? { ...m, content: streamingContentRef.current } : m
              ))
              break
            case 'tool_call': {
              setMessages(prev => prev.map(m => {
                if (m.id !== assistantId) return m
                const tool: ToolCall = { id: event.id, name: event.name, status: 'running', startedAt: Date.now() }
                return { ...m, toolCalls: [...(m.toolCalls || []).filter(t => t.id !== event.id), tool] }
              }))
              break
            }
            case 'tool_result': {
              setMessages(prev => prev.map(m => {
                if (m.id !== assistantId) return m
                return {
                  ...m,
                  toolCalls: (m.toolCalls || []).map(t =>
                    t.id === event.id ? { ...t, status: 'done' as ToolStatus, result: event.result } : t
                  ),
                }
              }))
              break
            }
            case 'done':
              setMessages(prev => prev.map(m => {
                if (m.id !== assistantId) return m
                const { text: clean, actions } = extractActionConfirmations(m.content)
                return { ...m, content: clean, actions, isStreaming: false }
              }))
              break
            case 'error':
              setMessages(prev => prev.map(m => {
                if (m.id !== assistantId) return m
                const toolCalls = (m.toolCalls || []).map(t =>
                  t.status === 'running' ? { ...t, status: 'failed' as ToolStatus } : t
                )
                return { ...m, content: event.content || 'AI 暂时无法回复', toolCalls, isStreaming: false }
              }))
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
      if (abortRef.current === controller) setLoading(false)
    }
  }

  const handleRegenerate = () => {
    const lastUserMsg = [...messages].reverse().find(m => m.role === 'user')
    if (!lastUserMsg || loading) return
    setMessages(prev => prev.slice(0, -1))
    handleSend(lastUserMsg.content)
  }

  const handleNewChat = async () => {
    await clearChatHistory()
    setMessages([])
  }

  const handleActionConfirm = async (action: ActionConfirmation, msgId: number, idx: number) => {
    try {
      await executeChatAction(action.action, action.data)
      setMessages(prev => prev.map(m =>
        m.id === msgId ? { ...m, actionResults: { ...m.actionResults, [idx]: 'confirmed' as const } } : m
      ))
    } catch {
      setMessages(prev => prev.map(m =>
        m.id === msgId ? { ...m, actionResults: { ...m.actionResults, [idx]: 'rejected' as const } } : m
      ))
    }
  }

  // ── 附件（占位：仅本地预览，不上传后端）──
  const onPickFiles = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files) return
    const added: Attachment[] = Array.from(files).map(f => ({ id: `${Date.now()}-${f.name}`, name: f.name, size: f.size }))
    setAttachments(prev => [...prev, ...added])
    e.target.value = ''
  }

  // ── 侧栏：按日期分组历史 ──
  const historyGroups = useMemo(() => {
    const map = new Map<string, { label: string; snippet: string; time: string }>()
    for (const m of messages) {
      const key = dateKey(m.created_at)
      if (!map.has(key)) {
        map.set(key, { label: dateLabel(m.created_at), snippet: m.role === 'user' ? m.content : '', time: timeLabel(m.created_at) })
      } else {
        const ex = map.get(key)!
        if (!ex.snippet && m.role === 'user') ex.snippet = m.content
      }
    }
    return [...map.entries()].reverse().map(([key, v]) => ({ key, ...v }))
  }, [messages])

  const scrollToDate = (dateKeyStr: string) => {
    const el = scrollRef.current?.querySelector(`[data-date="${dateKeyStr}"]`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const lastMsg = messages[messages.length - 1]
  const canRegenerate = !loading && lastMsg?.role === 'assistant' && !lastMsg.isStreaming

  return (
    <div className="aic-chat flex gap-3 h-full min-h-0">
      {/* ═══════ 左栏：会话列表（glass，可折叠 56px 图标轨） ═══════ */}
      <aside className={`aic-side glass shrink-0 flex flex-col overflow-hidden ${sidebarOpen ? '' : 'aic-side-collapsed'}`}>
        {/* 新对话（胶囊按钮） */}
        <div className="p-2.5">
          <button
            onClick={handleNewChat}
            className="aic-newchat"
            title="新对话"
          >
            <Plus size={15} />
            {sidebarOpen && <span>新对话</span>}
          </button>
        </div>

        {/* 会话列表：按日期分组 */}
        {sidebarOpen && (
          <div className="flex-1 overflow-y-auto pb-2 scrollbar-thin">
            {historyGroups.length === 0 ? (
              <p className="px-3 py-3 text-[11px] text-cd-text-tertiary leading-relaxed">暂无历史会话</p>
            ) : (
              historyGroups.map(g => (
                <div key={g.key}>
                  <div className="aic-session-group-label">{g.label}</div>
                  <button
                    onClick={() => scrollToDate(g.key)}
                    className="aic-session-row"
                  >
                    <span className="aic-session-title">{g.snippet || '（无消息）'}</span>
                    <span className="aic-session-time">{g.time}</span>
                  </button>
                </div>
              ))
            )}
          </div>
        )}

        {/* 底部：设置 + 折叠 */}
        <div className="p-2 mt-auto border-t border-cd-border/40 flex flex-col gap-0.5">
          {sidebarOpen && (
            <button
              className="aic-session-row"
              title="设置（占位）"
            >
              <Settings size={14} className="shrink-0" />
              <span className="aic-session-title">设置</span>
            </button>
          )}
          <button
            onClick={() => setSidebarOpen(o => !o)}
            className="aic-session-row"
            title={sidebarOpen ? '收起侧栏' : '展开侧栏'}
          >
            {sidebarOpen ? <PanelLeftClose size={14} className="shrink-0" /> : <PanelLeftOpen size={16} />}
            {sidebarOpen && <span className="aic-session-title">收起侧栏</span>}
          </button>
        </div>
      </aside>

      {/* ═══════ 中栏：对话区 ═══════ */}
      <section className="flex-1 flex flex-col min-w-0 relative">
        {/* 顶栏（精简） */}
        <div className="flex items-center justify-between px-2 py-2 shrink-0">
          <h1 className="text-sm font-semibold text-cd-text flex items-center gap-2">
            <Bot size={16} className="text-cd-accent" />
            AI 智能体
          </h1>
          <div className="flex items-center gap-1">
            {canRegenerate && (
              <button onClick={handleRegenerate} className="p-1.5 text-cd-text-secondary hover:text-cd-accent transition rounded-lg hover:bg-cd-hover" title="重新生成">
                <RefreshCw size={14} />
              </button>
            )}
            {messages.length > 0 && (
              <button onClick={handleNewChat} className="p-1.5 text-cd-text-secondary hover:text-cd-red transition rounded-lg hover:bg-cd-hover" title="清空对话">
                <Trash2 size={14} />
              </button>
            )}
          </div>
        </div>

        {/* 消息列表 */}
        <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-y-auto scrollbar-thin">
          {messages.length === 0 ? (
            /* 空状态 hero：居中问候 + 快捷操作 */
            <div className="min-h-full flex flex-col items-center justify-center px-6 pb-8">
              <div className="w-14 h-14 rounded-2xl bg-cd-accent/10 flex items-center justify-center mb-4">
                <Sparkles size={26} className="text-cd-accent" />
              </div>
              <h2 className="text-xl font-semibold text-cd-text mb-1.5">工作智能体</h2>
              <p className="text-[13px] text-cd-text-secondary mb-6 text-center max-w-md">
                你可以问我关于工作数据的任何事情，我也能帮你创建待办、启动番茄钟
              </p>
              <div className="grid grid-cols-2 gap-2.5 w-full max-w-lg">
                {QUICK_ACTIONS.map(q => (
                  <button
                    key={q.label}
                    onClick={() => handleSend(q.prompt)}
                    className="flex items-center gap-2.5 px-3.5 py-3 bg-cd-card text-cd-text rounded-2xl border border-cd-border hover:border-cd-accent/40 transition text-left"
                  >
                    <q.icon size={16} className="text-cd-accent shrink-0" />
                    <span className="text-[13px]">{q.label}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="max-w-[768px] mx-auto flex flex-col" style={{ gap: 12 }}>
              {messages.map((msg, idx) => {
                const showDateAnchor = idx === 0 || dateKey(msg.created_at) !== dateKey(messages[idx - 1].created_at)
                return (
                  <div key={msg.id}>
                    {showDateAnchor && <div data-date={dateKey(msg.created_at)} className="h-0" />}
                    {msg.role === 'user' ? (
                      /* ── 用户消息：右对齐实色气泡，无头像 ── */
                      <div className="flex justify-end">
                        <div className="aic-user-bubble">{msg.content}</div>
                      </div>
                    ) : (
                      /* ── AI 消息：无气泡 transcript 流 ── */
                      <div className="aic-assistant">
                        {/* 思考过程 */}
                        {msg.reasoning && (
                          <ReasoningRow text={msg.reasoning} running={msg.isStreaming && !msg.content} />
                        )}

                        {/* 工具调用卡片 */}
                        {msg.toolCalls && msg.toolCalls.length > 0 && (
                          <div>
                            {msg.toolCalls.map(tc => <ToolRow key={tc.id} tool={tc} />)}
                          </div>
                        )}

                        {/* 正文 Markdown */}
                        {msg.content && (
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            components={{
                              pre: ({ children }) => {
                                const child = Children.only(children) as ReactElement<{ className?: string; children?: React.ReactNode }>
                                const cls = child?.props?.className || ''
                                const language = /language-(\w+)/.exec(cls)?.[1] || ''
                                const code = String(child?.props?.children || '').replace(/\n$/, '')
                                return <CodeBlock language={language} code={code} />
                              },
                            }}
                          >
                            {msg.content}
                          </ReactMarkdown>
                        )}

                        {/* 流式占位 */}
                        {msg.isStreaming && !msg.content && !(msg.toolCalls && msg.toolCalls.length > 0) && !msg.reasoning && (
                          <div className="flex gap-1.5 py-1">
                            <span className="w-1.5 h-1.5 bg-cd-accent/60 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                            <span className="w-1.5 h-1.5 bg-cd-accent/60 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                            <span className="w-1.5 h-1.5 bg-cd-accent/60 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                          </div>
                        )}

                        {/* 操作确认卡片 */}
                        {msg.actions && msg.actions.map((action, i) => {
                          const result = msg.actionResults?.[i]
                          return (
                            <div key={i} className="rounded-2xl border border-cd-accent/25 bg-cd-card p-3.5 max-w-lg">
                              <div className="flex items-center gap-2 mb-1.5">
                                <Sparkles size={13} className="text-cd-accent" />
                                <span className="text-xs font-medium text-cd-text">操作确认</span>
                              </div>
                              <p className="text-[13px] text-cd-text mb-3">{action.confirm_message}</p>
                              {result === 'confirmed' ? (
                                <div className="flex items-center gap-1.5 text-xs text-cd-accent">
                                  <Check size={13} /> 已确认执行
                                </div>
                              ) : result === 'rejected' ? (
                                <div className="flex items-center gap-1.5 text-xs text-cd-text-tertiary">
                                  <X size={13} /> 已取消
                                </div>
                              ) : (
                                <div className="flex gap-2">
                                  <button
                                    onClick={() => handleActionConfirm(action, msg.id, i)}
                                    className="px-3.5 py-1.5 text-xs font-medium bg-cd-accent text-white rounded-full hover:opacity-90 transition"
                                  >
                                    确认执行
                                  </button>
                                  <button
                                    onClick={() => setMessages(prev => prev.map(m => m.id === msg.id ? { ...m, actionResults: { ...m.actionResults, [i]: 'rejected' as const } } : m))}
                                    className="px-3.5 py-1.5 text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary rounded-full hover:bg-cd-hover transition border border-cd-border"
                                  >
                                    取消
                                  </button>
                                </div>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )
              })}
              {/* 底部留白，让 composer 上方有呼吸空间 */}
              <div className="h-2" />
            </div>
          )}
        </div>

        {/* 回到底部：34px 圆形浮钮 */}
        {showJump && (
          <button
            onClick={jumpToBottom}
            className="aic-to-bottom absolute left-1/2 -translate-x-1/2 z-10"
            style={{ bottom: 140 }}
            title="回到底部"
          >
            <ArrowDown size={15} />
          </button>
        )}

        {/* ── 底部 sticky 输入区（composer 比消息列宽 16px 左右） ── */}
        <div className="shrink-0 px-4 pb-4 pt-2">
          {/* 附件 rail */}
          {attachments.length > 0 && (
            <div className="flex gap-2 mb-2 h-16 overflow-x-auto scrollbar-thin items-center">
              {attachments.map(a => (
                <div key={a.id} className="relative shrink-0 w-40 h-14 rounded-xl border border-cd-border bg-cd-bg-secondary px-2.5 flex items-center gap-2">
                  <FileText size={16} className="text-cd-accent shrink-0" />
                  <div className="min-w-0">
                    <div className="text-[11px] text-cd-text truncate">{a.name}</div>
                    <div className="text-[9px] text-cd-text-tertiary">{(a.size / 1024).toFixed(1)} KB</div>
                  </div>
                  <button
                    onClick={() => setAttachments(prev => prev.filter(p => p.id !== a.id))}
                    className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-cd-bg-secondary border border-cd-border flex items-center justify-center hover:text-cd-red"
                  >
                    <X size={10} />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* composer 卡片：28px 圆角 glass-strong，宽 800（消息列 768 + 32） */}
          <div className="max-w-[800px] mx-auto">
            <div className="aic-composer glass-strong">
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
                className="aic-composer-input scrollbar-thin"
                rows={1}
                disabled={loading}
                onInput={e => {
                  const el = e.target as HTMLTextAreaElement
                  el.style.height = 'auto'
                  el.style.height = Math.min(el.scrollHeight, 336) + 'px'
                }}
              />
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                onChange={onPickFiles}
              />
              {/* 工具行：左 [+] + 深度思考/联网 pill；右 发送/停止 */}
              <div className="aic-composer-row">
                <div className="flex items-center gap-2 flex-wrap">
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="aic-add-btn"
                    title="添加附件（占位）"
                  >
                    <Paperclip size={14} />
                  </button>
                  <button
                    className={`aic-pill ${deepThink ? 'aic-pill-on' : ''}`}
                    onClick={() => setDeepThink(v => !v)}
                    title="深度思考（界面开关）"
                  >
                    <Brain size={13} />
                    深度思考
                  </button>
                  <button
                    className={`aic-pill ${webSearch ? 'aic-pill-on' : ''}`}
                    onClick={() => setWebSearch(v => !v)}
                    title="联网搜索（界面开关）"
                  >
                    <span className="text-xs">🌐</span>
                    联网搜索
                  </button>
                </div>

                {loading ? (
                  <button
                    onClick={() => abortRef.current?.abort()}
                    className="aic-stop-btn"
                    title="停止生成"
                  >
                    <Square size={13} />
                  </button>
                ) : (
                  <button
                    onClick={() => handleSend()}
                    disabled={!input.trim()}
                    className="aic-send-btn"
                    title="发送"
                  >
                    <Send size={16} style={{ transform: 'rotate(0deg)' }} />
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}

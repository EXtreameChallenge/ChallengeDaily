import { useState, useEffect, useRef, useCallback, useMemo, Children, type ReactElement } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Send, Plus, Trash2, Bot, User, Sparkles, RefreshCw,
  Check, Copy, X, Paperclip, ChevronDown, ArrowDown, Brain,
  BarChart3, ListTodo, Timer, FileText, TrendingUp, UserCircle,
  Loader2, PanelLeftClose, PanelLeftOpen, Square,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
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
//  代码块：语言标签 + 复制按钮
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
    <div className="rounded-xl border border-cd-border my-2 overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1.5 bg-cd-bg-secondary">
        <span className="text-[10px] font-mono text-cd-text-tertiary uppercase tracking-wide">
          {language || 'code'}
        </span>
        <button
          onClick={onCopy}
          className="flex items-center gap-1 text-[10px] text-cd-text-secondary hover:text-cd-accent transition"
        >
          {copied ? <Check size={11} /> : <Copy size={11} />}
          {copied ? '已复制' : '复制'}
        </button>
      </div>
      <pre className="p-3 overflow-x-auto text-xs leading-relaxed">
        <code>{code}</code>
      </pre>
    </div>
  )
}

// ════════════════════════════════════════════
//  思考过程折叠块
// ════════════════════════════════════════════
function ReasoningBlock({ text, running }: { text: string; running?: boolean }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-xl border border-cd-border/60 bg-cd-bg-secondary/40 mb-2 overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-cd-hover/50 transition"
      >
        <Brain size={13} className="text-cd-text-tertiary shrink-0" />
        <span className={`text-cd-text-secondary ${running ? 'text-shimmer' : ''}`}>
          思考过程
        </span>
        <ChevronDown
          size={13}
          className={`ml-auto text-cd-text-tertiary transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {open && (
        <div className="px-3 pb-3 pt-1 text-xs text-cd-text-secondary whitespace-pre-wrap leading-relaxed border-t border-cd-border/40">
          {text || '（暂无思考内容）'}
        </div>
      )}
    </div>
  )
}

// ════════════════════════════════════════════
//  工具调用卡片（可折叠，三/四态）
// ════════════════════════════════════════════
function ToolCard({ tool }: { tool: ToolCall }) {
  const [open, setOpen] = useState(false)
  const meta = TOOL_LABELS[tool.name] || { label: tool.name, icon: '🔧' }

  const stateIcon = () => {
    switch (tool.status) {
      case 'running':
        return <Loader2 size={12} className="text-cd-accent animate-spin" />
      case 'done':
        return <Check size={12} className="text-cd-green" />
      case 'failed':
        return <X size={12} className="text-cd-red" />
      default:
        return <span className="w-2 h-2 rounded-full bg-cd-text-tertiary/40 animate-pulse-soft" />
    }
  }

  const elapsed = ((Date.now() - tool.startedAt) / 1000).toFixed(0)

  return (
    <div className="rounded-xl border border-cd-border/60 bg-cd-bg-secondary/40 mb-1.5 overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-cd-hover/50 transition"
      >
        {stateIcon()}
        <span className={`${tool.status === 'running' ? 'text-shimmer' : 'text-cd-text-secondary'}`}>
          {meta.icon} {meta.label}
        </span>
        <span className="text-[10px] text-cd-text-tertiary ml-1">
          {tool.status === 'running' ? `${elapsed}s` : tool.status === 'done' ? '完成' : tool.status === 'failed' ? '失败' : '等待中'}
        </span>
        <ChevronDown
          size={13}
          className={`ml-auto text-cd-text-tertiary transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {open && tool.result != null && (
        <div className="px-3 pb-2.5 pt-1 text-[11px] text-cd-text-secondary whitespace-pre-wrap leading-relaxed border-t border-cd-border/40 max-h-48 overflow-y-auto scrollbar-thin">
          {tool.result}
        </div>
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
      // 等历史加载完再发
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
                // 进行中的工具标记为失败
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
    const map = new Map<string, { label: string; snippet: string }>()
    for (const m of messages) {
      const key = dateKey(m.created_at)
      if (!map.has(key)) {
        map.set(key, { label: dateLabel(m.created_at), snippet: m.role === 'user' ? m.content : '' })
      } else {
        const ex = map.get(key)!
        if (!ex.snippet && m.role === 'user') ex.snippet = m.content
      }
    }
    return [...map.entries()].reverse().map(([dateKey, v]) => ({ dateKey, ...v }))
  }, [messages])

  const scrollToDate = (dateKeyStr: string) => {
    const el = scrollRef.current?.querySelector(`[data-date="${dateKeyStr}"]`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const lastMsg = messages[messages.length - 1]
  const canRegenerate = !loading && lastMsg?.role === 'assistant' && !lastMsg.isStreaming

  return (
    <div className="flex gap-3 h-full min-h-0">
      {/* ═══════ 左侧栏 ═══════ */}
      <aside className={`shrink-0 flex flex-col rounded-2xl glass overflow-hidden transition-all duration-200 ${sidebarOpen ? 'w-[220px]' : 'w-[52px]'}`}>
        {/* 新对话 */}
        <div className="p-2.5">
          <button
            onClick={handleNewChat}
            className="w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl bg-cd-accent text-white text-xs font-medium hover:opacity-90 transition"
            title="新对话"
          >
            <Plus size={14} />
            {sidebarOpen && <span>新对话</span>}
          </button>
        </div>

        {/* 历史分组 */}
        {sidebarOpen && (
          <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-0.5 scrollbar-thin">
            <div className="px-2 py-1.5 text-[10px] font-medium text-cd-text-tertiary uppercase tracking-wide">
              历史记录
            </div>
            {historyGroups.length === 0 ? (
              <p className="px-2 py-3 text-[11px] text-cd-text-tertiary leading-relaxed">暂无历史会话</p>
            ) : (
              historyGroups.map(g => (
                <button
                  key={g.dateKey}
                  onClick={() => scrollToDate(g.dateKey)}
                  className="w-full text-left px-2 py-1.5 rounded-lg hover:bg-cd-hover transition group"
                >
                  <div className="text-[11px] font-medium text-cd-text-secondary">{g.label}</div>
                  <div className="text-[10px] text-cd-text-tertiary truncate mt-0.5">
                    {g.snippet || '（无消息）'}
                  </div>
                </button>
              ))
            )}
          </div>
        )}

        {/* 底部折叠钮 */}
        <div className="p-2 border-t border-cd-border/50">
          <button
            onClick={() => setSidebarOpen(o => !o)}
            className="w-full flex items-center justify-center gap-1.5 px-2 py-1.5 rounded-lg text-[11px] text-cd-text-secondary hover:bg-cd-hover transition"
            title={sidebarOpen ? '收起侧栏' : '展开侧栏'}
          >
            {sidebarOpen ? <PanelLeftClose size={14} /> : <PanelLeftOpen size={14} />}
            {sidebarOpen && <span>收起</span>}
          </button>
        </div>
      </aside>

      {/* ═══════ 中间主区 ═══════ */}
      <section className="flex-1 flex flex-col min-w-0 rounded-2xl glass overflow-hidden relative">
        {/* 顶栏 */}
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-cd-border/50 shrink-0">
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
              <button onClick={handleNewChat} className="p-1.5 text-cd-text-secondary hover:text-red-400 transition rounded-lg hover:bg-cd-hover" title="清空对话">
                <Trash2 size={14} />
              </button>
            )}
          </div>
        </div>

        {/* 消息列表 */}
        <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-y-auto px-5 py-4 scrollbar-thin">
          {messages.length === 0 ? (
            /* 空状态：快捷操作 */
            <div className="text-center py-10">
              <div className="w-14 h-14 rounded-2xl bg-cd-accent/10 flex items-center justify-center mx-auto mb-3">
                <Sparkles size={24} className="text-cd-accent" />
              </div>
              <h2 className="text-base font-semibold text-cd-text mb-1">工作智能体</h2>
              <p className="text-xs text-cd-text-secondary mb-5">你可以问我关于工作数据的任何事情，我也能帮你创建待办、启动番茄钟</p>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 max-w-lg mx-auto">
                {QUICK_ACTIONS.map(q => (
                  <button
                    key={q.label}
                    onClick={() => handleSend(q.prompt)}
                    className="flex items-center gap-2 px-3 py-2.5 bg-cd-card text-cd-text rounded-xl border border-cd-border hover:border-cd-accent/30 hover:bg-cd-accent/5 transition text-xs text-left"
                  >
                    <q.icon size={14} className="text-cd-accent shrink-0" />
                    {q.label}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto space-y-4 pb-2">
              {messages.map((msg, idx) => {
                // 日期锚点：每条用户消息或新日期起点打标
                const showDateAnchor = idx === 0 || dateKey(msg.created_at) !== dateKey(messages[idx - 1].created_at)
                return (
                  <div key={msg.id}>
                    {showDateAnchor && <div data-date={dateKey(msg.created_at)} className="h-0" />}
                    {msg.role === 'user' ? (
                      /* ── 用户消息：右对齐玻璃气泡 ── */
                      <div className="flex justify-end">
                        <div className="glass-strong rounded-2xl rounded-br-md px-4 py-2.5 max-w-[80%]">
                          <p className="text-sm leading-relaxed whitespace-pre-wrap text-cd-text">{msg.content}</p>
                        </div>
                      </div>
                    ) : (
                      /* ── AI 消息：transcript 流式排版 ── */
                      <div className="space-y-2">
                        {/* 思考过程 */}
                        {msg.reasoning && <ReasoningBlock text={msg.reasoning} running={msg.isStreaming && !msg.content} />}

                        {/* 工具调用卡片树 */}
                        {msg.toolCalls && msg.toolCalls.length > 0 && (
                          <div>
                            {msg.toolCalls.map(tc => <ToolCard key={tc.id} tool={tc} />)}
                          </div>
                        )}

                        {/* 正文 Markdown */}
                        {msg.content && (
                          <div className="text-sm leading-relaxed text-cd-text prose-sm max-w-none [&_li]:ml-4 [&_li]:list-disc [&_strong]:text-cd-text">
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
                                code: ({ children }) => <code>{children}</code>,
                              }}
                            >
                              {msg.content}
                            </ReactMarkdown>
                          </div>
                        )}

                        {/* 流式占位三点 */}
                        {msg.isStreaming && !msg.content && !(msg.toolCalls && msg.toolCalls.length > 0) && !msg.reasoning && (
                          <div className="flex gap-1 py-1">
                            <span className="w-1.5 h-1.5 bg-cd-accent/60 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                            <span className="w-1.5 h-1.5 bg-cd-accent/60 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                            <span className="w-1.5 h-1.5 bg-cd-accent/60 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                          </div>
                        )}

                        {/* 操作确认卡片 */}
                        {msg.actions && msg.actions.map((action, i) => {
                          const result = msg.actionResults?.[i]
                          return (
                            <div key={i} className="rounded-xl border border-cd-accent/20 bg-cd-card p-3 max-w-lg">
                              <div className="flex items-center gap-2 mb-1.5">
                                <Sparkles size={13} className="text-cd-accent" />
                                <span className="text-xs font-medium text-cd-text">操作确认</span>
                              </div>
                              <p className="text-sm text-cd-text mb-2.5">{action.confirm_message}</p>
                              {result === 'confirmed' ? (
                                <div className="flex items-center gap-1.5 text-xs text-cd-green">
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
                                    className="px-3 py-1.5 text-xs font-medium bg-cd-accent text-white rounded-full hover:opacity-90 transition"
                                  >
                                    确认执行
                                  </button>
                                  <button
                                    onClick={() => setMessages(prev => prev.map(m => m.id === msg.id ? { ...m, actionResults: { ...m.actionResults, [i]: 'rejected' as const } } : m))}
                                    className="px-3 py-1.5 text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary rounded-full hover:bg-cd-hover transition border border-cd-border"
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
            </div>
          )}
        </div>

        {/* 回到底部按钮 */}
        {showJump && (
          <button
            onClick={jumpToBottom}
            className="absolute left-1/2 -translate-x-1/2 bottom-24 z-10 glass-pill px-3 py-1.5 flex items-center gap-1.5 text-xs text-cd-text-secondary hover:text-cd-accent transition"
          >
            <ArrowDown size={13} /> 回到底部
          </button>
        )}

        {/* ── 底部输入区（sticky）── */}
        <div className="shrink-0 px-4 pb-3 pt-2">
          {/* 附件 rail（64px）*/}
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

          <div className="glass-strong rounded-2xl flex items-end gap-2 px-3 py-2 focus-within:border-cd-accent/30 transition">
            <button
              onClick={() => fileInputRef.current?.click()}
              className="p-1.5 rounded-lg text-cd-text-secondary hover:text-cd-accent hover:bg-cd-hover transition shrink-0 mb-0.5"
              title="添加附件（占位）"
            >
              <Paperclip size={15} />
            </button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={onPickFiles}
            />
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
              className="flex-1 bg-transparent text-cd-text text-sm px-1 py-1.5 focus:outline-none resize-none max-h-32 placeholder:text-cd-text-tertiary"
              rows={1}
              disabled={loading}
              style={{ minHeight: '24px' }}
              onInput={e => {
                const el = e.target as HTMLTextAreaElement
                el.style.height = 'auto'
                el.style.height = Math.min(el.scrollHeight, 128) + 'px'
              }}
            />
            {loading ? (
              <button
                onClick={() => abortRef.current?.abort()}
                className="p-2 bg-cd-bg-secondary text-cd-red rounded-full border border-cd-border hover:bg-cd-hover transition shrink-0 mb-0.5"
                title="停止生成"
              >
                <Square size={14} />
              </button>
            ) : (
              <button
                onClick={() => handleSend()}
                disabled={!input.trim()}
                className="p-2 bg-cd-accent text-white rounded-full hover:opacity-90 transition disabled:opacity-30 shrink-0 mb-0.5"
              >
                <Send size={15} />
              </button>
            )}
          </div>
        </div>
      </section>
    </div>
  )
}

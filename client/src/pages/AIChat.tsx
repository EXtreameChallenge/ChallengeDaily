import { useState, useEffect, useRef, useCallback, useMemo, Children, type ReactElement } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Send, Plus, Trash2, Bot, Sparkles, RefreshCw,
  Check, Copy, X, Paperclip, ChevronDown, ArrowDown, Brain,
  BarChart3, ListTodo, Timer, FileText, TrendingUp, UserCircle,
  Loader2, PanelLeftClose, PanelLeftOpen, Square, Settings,
  Search, Globe, ChevronRight,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { aiChatStream, getChatHistory, clearChatHistory, executeChatAction, type ChatMessage, type ChatStreamEvent, type ActionConfirmation } from '../api/client'

// ════════════════════════════════════════════════════════════
//  常量
// ════════════════════════════════════════════════════════════

// 工具名 → 中文标签
const TOOL_LABELS: Record<string, { label: string; emoji: string }> = {
  get_activities:      { label: '查询活动记录', emoji: '🔍' },
  get_todos:           { label: '查询待办列表', emoji: '📋' },
  get_pomodoro_stats:  { label: '查询番茄钟',   emoji: '🍅' },
  get_daily_summary:   { label: '查询日画像',   emoji: '📊' },
  get_work_trends:     { label: '查询效率趋势', emoji: '📈' },
  get_user_profile:    { label: '查询用户画像', emoji: '👤' },
  create_todo:         { label: '创建待办',     emoji: '✏️' },
  start_pomodoro:      { label: '启动番茄钟',   emoji: '🍅' },
  save_diary:          { label: '保存日记',     emoji: '📝' },
}

// 欢迎页快捷建议卡片
const QUICK_SUGGESTIONS = [
  { icon: BarChart3,   title: '今日工作概览', desc: '快速了解今天的整体情况', prompt: '我今天的工作情况怎么样？请给我一个概览' },
  { icon: TrendingUp,  title: '效率趋势分析', desc: '近 7 天的效率变化与规律',   prompt: '分析我最近7天的工作效率趋势，有什么变化和规律？' },
  { icon: ListTodo,    title: '待办进展',     desc: '整理未完成的待办事项',       prompt: '我还有哪些待办没完成？帮我整理一下' },
  { icon: Timer,       title: '番茄钟统计',   desc: '最近的番茄钟执行情况',       prompt: '我最近的番茄钟执行情况怎么样？' },
  { icon: FileText,    title: '生成本周复盘', desc: '包含数据和分析的总结',       prompt: '帮我生成本周的工作复盘总结，包含数据和分析' },
  { icon: UserCircle,  title: '深度画像',     desc: '了解我的工作特征',         prompt: '介绍一下我的工作画像和特征' },
]

// 工具调用状态
type ToolStatus = 'pending' | 'running' | 'success' | 'error'

interface ToolCall {
  id: string
  name: string
  status: ToolStatus
  result?: string
  startedAt: number
  finishedAt?: number
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
  reasoningMs?: number
  toolCalls?: ToolCall[]
  actions?: ActionConfirmation[]
  actionResults?: Record<number, 'confirmed' | 'rejected'>
  isStreaming?: boolean
}

// ════════════════════════════════════════════════════════════
//  日期分组辅助
// ════════════════════════════════════════════════════════════
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
function fmtMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

// ════════════════════════════════════════════════════════════
//  操作确认 JSON 提取
// ════════════════════════════════════════════════════════════
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

// ════════════════════════════════════════════════════════════
//  代码块（16px 圆角 + sticky banner + 复制）
// ════════════════════════════════════════════════════════════
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
        <span className="aic-code-lang">{language || 'text'}</span>
        <button onClick={onCopy} className="aic-code-copy">
          {copied ? <Check size={11} /> : <Copy size={11} />}
          <span>{copied ? '已复制' : '复制'}</span>
        </button>
      </div>
      <pre><code>{code}</code></pre>
    </div>
  )
}

// ════════════════════════════════════════════════════════════
//  思考过程折叠行（DeepSeek 风格 24px 单行）
// ════════════════════════════════════════════════════════════
function ReasoningRow({ text, running, elapsedMs }: { text: string; running?: boolean; elapsedMs?: number }) {
  const [open, setOpen] = useState(false)
  const done = !running && elapsedMs != null
  return (
    <div className="aic-think">
      <button className="aic-think-row" onClick={() => setOpen(o => !o)}>
        <Brain size={14} className="shrink-0 text-cd-text-tertiary" />
        {running ? (
          <span className="text-shimmer">深度思考中…</span>
        ) : (
          <span className="aic-think-label">已深度思考{done ? ` ${fmtMs(elapsedMs!)}` : ''}</span>
        )}
        {text && !running && <span className="aic-think-dot" />}
        {text && !running && (
          <span className="aic-think-preview">{text.slice(0, 50)}</span>
        )}
        <ChevronDown size={14} className={`ml-auto shrink-0 text-cd-text-tertiary transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="aic-think-body">{text || '（暂无思考内容）'}</div>
      )}
    </div>
  )
}

// ════════════════════════════════════════════════════════════
//  工具调用行（四态：pending / running / success / error）
// ════════════════════════════════════════════════════════════
function ToolRow({ tool }: { tool: ToolCall }) {
  const [open, setOpen] = useState(false)
  const meta = TOOL_LABELS[tool.name] || { label: tool.name, emoji: '🔧' }

  const elapsed = tool.finishedAt
    ? tool.finishedAt - tool.startedAt
    : Date.now() - tool.startedAt

  const stateIcon = () => {
    switch (tool.status) {
      case 'pending':
        return <span className="aic-tool-pulse-dot" />
      case 'running':
        return <Loader2 size={13} className="text-cd-accent animate-spin shrink-0" />
      case 'success':
        return <Check size={13} className="aic-tool-success shrink-0" />
      case 'error':
        return <X size={13} className="text-cd-red shrink-0" />
    }
  }

  const statusText = () => {
    switch (tool.status) {
      case 'pending':  return '等待中'
      case 'running':  return `${fmtMs(elapsed)}`
      case 'success':  return fmtMs(elapsed)
      case 'error':    return '失败'
    }
  }

  return (
    <div className="aic-tool">
      <button className="aic-tool-row" onClick={() => setOpen(o => !o)}>
        {stateIcon()}
        <span className={`aic-tool-name ${tool.status === 'running' ? 'text-shimmer' : ''}`}>
          {meta.emoji} {meta.label}
        </span>
        <span className="aic-think-dot" />
        <span className="aic-tool-status">{statusText()}</span>
        <ChevronDown size={14} className={`ml-auto shrink-0 text-cd-text-tertiary transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="aic-tool-body">
          {tool.result != null ? (
            <div className="aic-tool-result">{tool.result}</div>
          ) : (
            <div className="aic-tool-empty">暂无返回结果</div>
          )}
        </div>
      )}
    </div>
  )
}

// ════════════════════════════════════════════════════════════
//  主页面
// ════════════════════════════════════════════════════════════
export default function AIChat() {
  const [messages, setMessages] = useState<DisplayMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [sidebarSearch, setSidebarSearch] = useState('')
  const [attachments, setAttachments] = useState<Attachment[]>([])
  const [showJump, setShowJump] = useState(false)
  const [deepThink, setDeepThink] = useState(false)
  const [webSearch, setWebSearch] = useState(false)
  const [modelOpen, setModelOpen] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const streamingContentRef = useRef('')
  const streamingReasoningRef = useRef('')
  const reasoningStartRef = useRef<number>(0)
  const nearBottomRef = useRef(true)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const sentFromUrlRef = useRef(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

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

  // ── 自动增高 textarea（最多 200px） ──
  const autoGrow = useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 200) + 'px'
  }, [])

  // ── 发送 ──
  const handleSend = async (text?: string) => {
    const msg = (text || input).trim()
    if (!msg || loading) return
    setInput('')
    setAttachments([])
    setLoading(true)
    streamingContentRef.current = ''
    streamingReasoningRef.current = ''
    reasoningStartRef.current = Date.now()

    // 重置 textarea 高度
    requestAnimationFrame(() => {
      if (textareaRef.current) textareaRef.current.style.height = 'auto'
    })

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
                const tool: ToolCall = {
                  id: event.id,
                  name: event.name,
                  status: 'running',
                  startedAt: Date.now(),
                }
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
                    t.id === event.id
                      ? { ...t, status: 'success' as ToolStatus, result: event.result, finishedAt: Date.now() }
                      : t
                  ),
                }
              }))
              break
            }
            case 'done': {
              const reasoningMs = streamingReasoningRef.current
                ? Date.now() - reasoningStartRef.current
                : undefined
              setMessages(prev => prev.map(m => {
                if (m.id !== assistantId) return m
                const { text: clean, actions } = extractActionConfirmations(m.content)
                return {
                  ...m,
                  content: clean,
                  actions,
                  reasoning: streamingReasoningRef.current || undefined,
                  reasoningMs,
                  isStreaming: false,
                }
              }))
              break
            }
            case 'error':
              setMessages(prev => prev.map(m => {
                if (m.id !== assistantId) return m
                const toolCalls = (m.toolCalls || []).map(t =>
                  t.status === 'running'
                    ? { ...t, status: 'error' as ToolStatus, finishedAt: Date.now() }
                    : t
                )
                return {
                  ...m,
                  content: event.content || 'AI 暂时无法回复',
                  toolCalls,
                  isStreaming: false,
                }
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

  // ── 附件（占位：仅本地预览） ──
  const onPickFiles = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files) return
    const added: Attachment[] = Array.from(files).map(f => ({ id: `${Date.now()}-${f.name}`, name: f.name, size: f.size }))
    setAttachments(prev => [...prev, ...added])
    e.target.value = ''
  }

  // ── 侧栏：按日期分组历史 ──
  const historyGroups = useMemo(() => {
    const filtered = messages.filter(m => {
      if (!sidebarSearch.trim()) return true
      return m.content.toLowerCase().includes(sidebarSearch.toLowerCase())
    })
    const map = new Map<string, { label: string; snippet: string; time: string }>()
    for (const m of filtered) {
      const key = dateKey(m.created_at)
      if (!map.has(key)) {
        map.set(key, {
          label: dateLabel(m.created_at),
          snippet: m.role === 'user' ? m.content : '',
          time: timeLabel(m.created_at),
        })
      } else {
        const ex = map.get(key)!
        if (!ex.snippet && m.role === 'user') ex.snippet = m.content
      }
    }
    return [...map.entries()].reverse().map(([key, v]) => ({ key, ...v }))
  }, [messages, sidebarSearch])

  const scrollToDate = (dateKeyStr: string) => {
    const el = scrollRef.current?.querySelector(`[data-date="${dateKeyStr}"]`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const lastMsg = messages[messages.length - 1]
  const canRegenerate = !loading && lastMsg?.role === 'assistant' && !lastMsg.isStreaming
  const isEmpty = messages.length === 0

  return (
    <div className="aic-chat flex h-full min-h-0">
      {/* ═══════ 左栏：会话列表（glass，可折叠 56px 图标轨） ═══════ */}
      <aside className={`aic-side glass shrink-0 flex flex-col overflow-hidden ${sidebarOpen ? '' : 'aic-side-collapsed'}`}>
        {/* 顶部：新对话按钮 */}
        <div className="aic-side-top">
          {sidebarOpen ? (
            <button onClick={handleNewChat} className="aic-newchat" title="新对话">
              <Plus size={15} />
              <span>新对话</span>
            </button>
          ) : (
            <button onClick={handleNewChat} className="aic-newchat-icon" title="新对话">
              <Plus size={16} />
            </button>
          )}
        </div>

        {/* 搜索框 */}
        {sidebarOpen && (
          <div className="aic-side-search-wrap">
            <div className="aic-side-search">
              <Search size={13} className="shrink-0 text-cd-text-tertiary" />
              <input
                value={sidebarSearch}
                onChange={e => setSidebarSearch(e.target.value)}
                placeholder="搜索会话"
                className="aic-side-search-input"
              />
            </div>
          </div>
        )}

        {/* 会话列表：按日期分组 */}
        {sidebarOpen && (
          <div className="flex-1 overflow-y-auto pb-2 scrollbar-thin aic-side-list">
            {historyGroups.length === 0 ? (
              <p className="px-3 py-3 text-[11px] text-cd-text-tertiary leading-relaxed">
                {sidebarSearch ? '无匹配会话' : '暂无历史会话'}
              </p>
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
        <div className="aic-side-bottom">
          {sidebarOpen && (
            <button className="aic-session-row" title="设置（占位）">
              <Settings size={14} className="shrink-0" />
              <span className="aic-session-title">设置</span>
            </button>
          )}
          <button
            onClick={() => setSidebarOpen(o => !o)}
            className="aic-session-row aic-side-collapse-btn"
            title={sidebarOpen ? '收起侧栏' : '展开侧栏'}
          >
            {sidebarOpen
              ? <><PanelLeftClose size={14} className="shrink-0" /><span className="aic-session-title">收起侧栏</span></>
              : <PanelLeftOpen size={16} />
            }
          </button>
        </div>
      </aside>

      {/* ═══════ 中栏：对话区 ═══════ */}
      <section className="flex-1 flex flex-col min-w-0 relative">
        {/* 消息列表 */}
        <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-y-auto scrollbar-thin">
          {isEmpty ? (
            /* ═══════ 欢迎页 Hero ═══════ */
            <div className="aic-hero">
              <div className="aic-hero-icon">
                <Bot size={32} className="text-cd-accent" />
              </div>
              <h1 className="aic-hero-title">有什么可以帮你的？</h1>
              <p className="aic-hero-subtitle">
                我可以帮你查看工作数据、创建待办、启动番茄钟，也能做分析和复盘
              </p>
              <div className="aic-hero-grid">
                {QUICK_SUGGESTIONS.map(q => (
                  <button
                    key={q.title}
                    onClick={() => handleSend(q.prompt)}
                    className="aic-suggest-card"
                  >
                    <q.icon size={18} className="aic-suggest-icon" />
                    <div className="aic-suggest-text">
                      <div className="aic-suggest-title">{q.title}</div>
                      <div className="aic-suggest-desc">{q.desc}</div>
                    </div>
                    <ChevronRight size={14} className="aic-suggest-arrow" />
                  </button>
                ))}
              </div>
              <p className="aic-hero-hint">输入消息开始对话，Shift + Enter 换行</p>
            </div>
          ) : (
            /* ═══════ 消息流 ═══════ */
            <div className="aic-msgs">
              {messages.map((msg, idx) => {
                const showDateAnchor = idx === 0 || dateKey(msg.created_at) !== dateKey(messages[idx - 1].created_at)
                return (
                  <div key={msg.id}>
                    {showDateAnchor && <div data-date={dateKey(msg.created_at)} className="h-0" />}
                    {msg.role === 'user' ? (
                      /* 用户消息：右对齐实色气泡 */
                      <div className="aic-user-wrap">
                        <div className="aic-user-bubble">{msg.content}</div>
                      </div>
                    ) : (
                      /* AI 消息：无气泡 */
                      <div className="aic-assistant">
                        <div className="aic-assistant-head">
                          <Bot size={16} className="text-cd-accent shrink-0" />
                          <span className="aic-assistant-name">AI 助手</span>
                        </div>

                        {/* 思考过程 */}
                        {msg.reasoning && (
                          <ReasoningRow
                            text={msg.reasoning}
                            running={msg.isStreaming && !msg.content && !(msg.toolCalls?.length)}
                            elapsedMs={msg.reasoningMs}
                          />
                        )}

                        {/* 工具调用卡片 */}
                        {msg.toolCalls && msg.toolCalls.length > 0 && (
                          <div className="aic-tool-list">
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

                        {/* 流式占位（三点跳动） */}
                        {msg.isStreaming && !msg.content && !(msg.toolCalls?.length) && !msg.reasoning && (
                          <div className="aic-typing">
                            <span /><span /><span />
                          </div>
                        )}

                        {/* 操作确认卡片 */}
                        {msg.actions && msg.actions.map((action, i) => {
                          const result = msg.actionResults?.[i]
                          return (
                            <div key={i} className="aic-action-card">
                              <div className="aic-action-head">
                                <Sparkles size={13} className="text-cd-accent" />
                                <span className="aic-action-title">操作确认</span>
                              </div>
                              <p className="aic-action-msg">{action.confirm_message}</p>
                              {result === 'confirmed' ? (
                                <div className="aic-action-result aic-action-confirmed">
                                  <Check size={13} /> 已确认执行
                                </div>
                              ) : result === 'rejected' ? (
                                <div className="aic-action-result aic-action-rejected">
                                  <X size={13} /> 已取消
                                </div>
                              ) : (
                                <div className="aic-action-btns">
                                  <button
                                    onClick={() => handleActionConfirm(action, msg.id, i)}
                                    className="aic-action-confirm-btn"
                                  >
                                    确认执行
                                  </button>
                                  <button
                                    onClick={() => setMessages(prev => prev.map(m => m.id === msg.id ? { ...m, actionResults: { ...m.actionResults, [i]: 'rejected' as const } } : m))}
                                    className="aic-action-cancel-btn"
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
              <div className="aic-msgs-bottom" />
            </div>
          )}
        </div>

        {/* 回到底部浮钮 */}
        {showJump && (
          <button onClick={jumpToBottom} className="aic-to-bottom aic-to-bottom-float" title="回到底部">
            <ArrowDown size={15} />
          </button>
        )}

        {/* ═══════ 底部 Composer ═══════ */}
        <div className="aic-composer-wrap">
          {/* 附件预览条 */}
          {attachments.length > 0 && (
            <div className="aic-attachments">
              {attachments.map(a => (
                <div key={a.id} className="aic-attachment-card">
                  <FileText size={16} className="text-cd-accent shrink-0" />
                  <div className="aic-attachment-info">
                    <div className="aic-attachment-name">{a.name}</div>
                    <div className="aic-attachment-size">{(a.size / 1024).toFixed(1)} KB</div>
                  </div>
                  <button
                    onClick={() => setAttachments(prev => prev.filter(p => p.id !== a.id))}
                    className="aic-attachment-remove"
                  >
                    <X size={10} />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* composer 卡片 */}
          <div className="aic-composer glass-strong">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={e => { setInput(e.target.value); autoGrow() }}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  handleSend()
                }
              }}
              placeholder="输入消息，Shift+Enter 换行..."
              className="aic-composer-input scrollbar-thin"
              rows={1}
              disabled={loading}
            />
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={onPickFiles}
            />

            {/* 底部工具栏 */}
            <div className="aic-composer-row">
              {/* 左侧工具 */}
              <div className="aic-composer-tools">
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="aic-add-btn"
                  title="添加附件"
                >
                  <Paperclip size={14} />
                </button>
                <button
                  className={`aic-pill ${deepThink ? 'aic-pill-on' : ''}`}
                  onClick={() => setDeepThink(v => !v)}
                  title="深度思考"
                >
                  <Brain size={13} />
                  深度思考
                </button>
                <button
                  className={`aic-pill ${webSearch ? 'aic-pill-on' : ''}`}
                  onClick={() => setWebSearch(v => !v)}
                  title="联网搜索"
                >
                  <Globe size={13} />
                  联网搜索
                </button>
              </div>

              {/* 右侧：模型选择 + 设置 + 发送/停止 */}
              <div className="aic-composer-trailing">
                <button
                  className="aic-model-btn"
                  onClick={() => setModelOpen(o => !o)}
                  title="选择模型"
                >
                  <span className="aic-model-name">GLM 4.5 Flash</span>
                  <ChevronDown size={12} className="text-cd-text-tertiary" />
                </button>
                <button className="aic-settings-btn" title="设置">
                  <Settings size={15} />
                </button>

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
                    <Send size={15} />
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

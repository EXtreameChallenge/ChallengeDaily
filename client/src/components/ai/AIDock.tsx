import { useState, useRef, useEffect, useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import {
  Send, Bot, X, ChevronDown, Sparkles, Brain, Globe, Square,
  ListTodo, BarChart3, Timer,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { aiChatStream, type ChatStreamEvent } from '../../api/client'

/**
 * 底部常驻 AI 对话框（AIDock）— 随问随答版
 * - 全局常驻，不跳转任何页面
 * - 点击输入框 → 向上展开对话面板（最大 60vh），在当前页直接流式问答
 * - 发送时自动附带「当前页面」作为上下文
 * - 两种模式：对话（默认，深度思考/联网搜索开关）/ 智能体（额外快捷工具按钮）
 */

interface DockMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  isStreaming?: boolean
}

type DockMode = 'chat' | 'agent'

/** 路由路径 → 页面中文名（作为上下文随消息发送） */
const PAGE_LABELS: Record<string, string> = {
  '/': '今日概览',
  '/timeline': '时间线',
  '/report': '效率报告',
  '/focus': '专注页',
  '/week-plan': '周计划',
  '/todos': '待办事项',
  '/diary': '日记',
  '/heatmap': '热力图',
  '/calendar': '日历',
  '/apps': '应用记录',
  '/app-tags': '应用标签',
  '/history': '历史报告',
  '/agent': '智能体',
  '/settings': '设置',
  '/profile': '深度画像',
  '/ai-chat': '完整对话',
  '/dashboard': '仪表盘',
  '/habits': '习惯',
  '/health': '健康',
  '/goals': '目标',
  '/memory': '记忆库',
  '/toolbox': '工具箱',
  '/achievements': '成就',
  '/countdowns': '倒计时',
}

const SUGGESTIONS = [
  '今天效率怎么样？',
  '我最近有什么专注模式？',
  '帮我排一下今天的优先级',
]

/** 智能体模式下的快捷工具按钮（点击即填入对应提问） */
const AGENT_TOOLS = [
  { label: '整理待办', icon: ListTodo, prompt: '帮我整理一下今天的待办事项，按优先级排好' },
  { label: '今日概览', icon: BarChart3, prompt: '给我一个今天的工作概览' },
  { label: '番茄钟', icon: Timer, prompt: '我最近的番茄钟执行情况怎么样？' },
]

/** 功能开关按钮（仿 DeepSeek harness） */
function ToggleButton({
  active,
  onClick,
  icon: Icon,
  label,
}: {
  active: boolean
  onClick: () => void
  icon: React.ComponentType<{ size?: number | string; className?: string }>
  label: string
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1 h-7 px-2.5 rounded-full text-xs transition border ${
        active
          ? 'bg-cd-accent/15 border-cd-accent/40 text-cd-accent'
          : 'border-cd-border text-cd-text-secondary hover:bg-cd-hover'
      }`}
    >
      <Icon size={12} />
      {label}
    </button>
  )
}

export default function AIDock() {
  const location = useLocation()
  const [input, setInput] = useState('')
  const [expanded, setExpanded] = useState(false)
  const [mode, setMode] = useState<DockMode>('chat')
  const [deepThink, setDeepThink] = useState(false)
  const [webSearch, setWebSearch] = useState(false)
  const [messages, setMessages] = useState<DockMessage[]>([])
  const [streaming, setStreaming] = useState(false)

  const inputRef = useRef<HTMLInputElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const idRef = useRef(1)

  const pageLabel = PAGE_LABELS[location.pathname] || location.pathname

  // 新消息到达时自动滚动到底部
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, expanded])

  // 展开后自动聚焦输入框
  useEffect(() => {
    if (expanded) {
      const t = setTimeout(() => inputRef.current?.focus(), 80)
      return () => clearTimeout(t)
    }
  }, [expanded])

  const nextId = () => idRef.current++

  /** 组装发送给后端的消息：附带当前页面上下文 + 开关提示 */
  const buildComposed = useCallback(
    (text: string): string => {
      let composed = `【当前页面：${pageLabel}】\n${text}`
      if (deepThink) composed += '\n\n[请先进行深度思考，再给出回答]'
      if (webSearch) composed += '\n\n[请联网检索最新信息后回答]'
      return composed
    },
    [pageLabel, deepThink, webSearch],
  )

  const handleSend = useCallback(
    async (raw?: string) => {
      const text = (raw ?? input).trim()
      if (!text || streaming) return
      setInput('')
      setExpanded(true)

      const userMsg: DockMessage = { id: nextId(), role: 'user', content: text }
      const assistantId = nextId()
      setMessages(prev => [
        ...prev,
        userMsg,
        { id: assistantId, role: 'assistant', content: '', isStreaming: true },
      ])
      setStreaming(true)

      const controller = new AbortController()
      abortRef.current = controller
      let acc = ''

      try {
        await aiChatStream(
          buildComposed(text),
          (ev: ChatStreamEvent) => {
            if (controller.signal.aborted) return
            switch (ev.type) {
              case 'content':
                acc += ev.content
                setMessages(prev =>
                  prev.map(m => (m.id === assistantId ? { ...m, content: acc } : m)),
                )
                break
              case 'error':
                acc = acc ? `${acc}\n\n⚠️ ${ev.content}` : `⚠️ ${ev.content}`
                setMessages(prev =>
                  prev.map(m =>
                    m.id === assistantId ? { ...m, content: acc, isStreaming: false } : m,
                  ),
                )
                break
              case 'done':
                setMessages(prev =>
                  prev.map(m => (m.id === assistantId ? { ...m, isStreaming: false } : m)),
                )
                break
              // tool_call / tool_result：坞内面板只展示正文，工具过程忽略
              default:
                break
            }
          },
          controller.signal,
        )
      } catch (e: any) {
        if (controller.signal.aborted || e?.name === 'AbortError') return
        const tip = acc
          ? `${acc}\n\n⚠️ 连接中断，请重试。`
          : '⚠️ AI 暂时无法回复，请检查网络后重试。'
        setMessages(prev =>
          prev.map(m =>
            m.id === assistantId ? { ...m, content: tip, isStreaming: false } : m,
          ),
        )
      } finally {
        setStreaming(false)
      }
    },
    [input, streaming, buildComposed],
  )

  const handleStop = () => {
    abortRef.current?.abort()
    setStreaming(false)
    setMessages(prev =>
      prev.map(m =>
        m.isStreaming ? { ...m, isStreaming: false, content: m.content || '已停止生成' } : m,
      ),
    )
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div
      className="ai-dock-float fixed bottom-5 z-40 w-[min(620px,58%)]"
      style={{ left: 'calc(50% + 124px)', transform: 'translateX(-50%)' }}
    >
      {/* ── 展开的对话面板 ── */}
      {expanded && (
        <div className="glass-strong rounded-2xl mb-2 flex flex-col max-h-[60vh] overflow-hidden animate-slide-up">
          {/* 头部 */}
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-cd-border/50 shrink-0">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-full bg-cd-accent/15 flex items-center justify-center">
                <Bot size={13} className="text-cd-accent" />
              </div>
              <span className="text-sm font-medium text-cd-text">AI 助手</span>
              <span className="text-[11px] text-cd-text-tertiary hidden sm:inline">
                当前：{pageLabel}
              </span>
            </div>
            <button
              onClick={() => setExpanded(false)}
              className="p-1 rounded-lg hover:bg-cd-hover transition"
              title="收起"
            >
              <ChevronDown size={15} className="text-cd-text-tertiary" />
            </button>
          </div>

          {/* 消息列表 */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
            {messages.length === 0 ? (
              <div className="flex flex-col items-center py-6">
                <div className="w-10 h-10 rounded-full bg-cd-accent/10 flex items-center justify-center mb-2.5">
                  <Sparkles size={18} className="text-cd-accent" />
                </div>
                <p className="text-sm text-cd-text-secondary mb-3">
                  问我任何事，回答就在这里展开
                </p>
                <div className="flex flex-wrap gap-2 justify-center max-w-md">
                  {SUGGESTIONS.map((s, i) => (
                    <button
                      key={i}
                      onClick={() => handleSend(s)}
                      className="text-xs px-3 py-1.5 rounded-full border border-cd-border text-cd-text-secondary hover:border-cd-accent hover:text-cd-accent transition"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map(m =>
                m.role === 'user' ? (
                  <div key={m.id} className="flex justify-end">
                    <div className="max-w-[80%] bg-cd-accent text-white rounded-2xl rounded-br-md px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap">
                      {m.content}
                    </div>
                  </div>
                ) : (
                  <div key={m.id} className="flex justify-start">
                    <div className="max-w-[85%]">
                      {m.content ? (
                        <div className="text-sm leading-relaxed text-cd-text [&_li]:ml-4 [&_li]:list-disc [&_strong]:text-cd-text">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {m.content}
                          </ReactMarkdown>
                        </div>
                      ) : m.isStreaming ? (
                        <div className="flex gap-1 py-1">
                          <span className="w-1.5 h-1.5 bg-cd-accent/60 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                          <span className="w-1.5 h-1.5 bg-cd-accent/60 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                          <span className="w-1.5 h-1.5 bg-cd-accent/60 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                        </div>
                      ) : null}
                    </div>
                  </div>
                ),
              )
            )}
          </div>

          {/* 功能工具栏：仅展开时显示 */}
          <div className="px-3 pt-2 pb-2 shrink-0 border-t border-cd-border/40">
            <div className="flex items-center gap-1.5 flex-wrap">
              <ToggleButton
                active={deepThink}
                onClick={() => setDeepThink(v => !v)}
                icon={Brain}
                label="深度思考"
              />
              <ToggleButton
                active={webSearch}
                onClick={() => setWebSearch(v => !v)}
                icon={Globe}
                label="联网搜索"
              />
              {mode === 'agent' &&
                AGENT_TOOLS.map(t => (
                  <button
                    key={t.label}
                    onClick={() => {
                      setInput(t.prompt)
                      inputRef.current?.focus()
                    }}
                    className="flex items-center gap-1 h-7 px-2.5 rounded-full text-xs border border-cd-border text-cd-text-secondary hover:bg-cd-hover transition"
                  >
                    <t.icon size={12} />
                    {t.label}
                  </button>
                ))}
              <div className="flex-1" />
              {/* 模式切换 */}
              <div className="glass-pill flex items-center p-0.5 h-7">
                <button
                  onClick={() => setMode('chat')}
                  className={`px-2.5 h-6 rounded-full text-xs transition ${
                    mode === 'chat' ? 'bg-cd-accent text-white' : 'text-cd-text-secondary'
                  }`}
                >
                  对话
                </button>
                <button
                  onClick={() => setMode('agent')}
                  className={`px-2.5 h-6 rounded-full text-xs transition ${
                    mode === 'agent' ? 'bg-cd-accent text-white' : 'text-cd-text-secondary'
                  }`}
                >
                  智能体
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── 悬浮玻璃输入条（胶囊形，h-10）── */}
      <div className="glass-pill flex items-center gap-2 pl-3 pr-1.5 h-10">
        <Bot size={15} className="text-cd-accent shrink-0" />
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => setExpanded(true)}
          placeholder="问我任何事..."
          className="flex-1 bg-transparent text-sm text-cd-text placeholder:text-cd-text-tertiary outline-none"
        />
        {input && !streaming && (
          <button
            onClick={() => setInput('')}
            className="p-1 rounded-full hover:bg-cd-hover transition shrink-0"
          >
            <X size={13} className="text-cd-text-tertiary" />
          </button>
        )}
        <button
          onClick={streaming ? handleStop : () => handleSend()}
          disabled={!streaming && !input.trim()}
          className="w-7 h-7 rounded-full bg-cd-accent text-white flex items-center justify-center shrink-0 disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-90 transition"
        >
          {streaming ? <Square size={11} /> : <Send size={13} />}
        </button>
      </div>
    </div>
  )
}

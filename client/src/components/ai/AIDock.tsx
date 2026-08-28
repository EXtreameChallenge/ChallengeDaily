import { useState, useRef, useEffect, useCallback } from 'react'
import { Send, Bot, User, X, ChevronUp, ChevronDown, Sparkles } from 'lucide-react'
import { aiChatStream, type ChatMessage } from '../../api/client'

/**
 * 底部常驻 AI 对话栏
 * 设计理念：AI 是上下文，不是页面（AI is Context, Not a Page）
 * - 全局常驻，无论在哪个页面都能问
 * - 自动感知当前页面上下文
 * - AI 回复可包含操作按钮，一键执行
 *
 * 科学依据：
 * - 情境认知理论：认知在情境中发生，AI 应该在用户需要的时刻出现在上下文中
 * - 决策疲劳：AI 主动提供建议，减少用户"该怎么办"的决策消耗
 * - BJ Fogg 行为模型：降低"问 AI"的能力门槛到一次点击
 */

interface AIDockProps {
  currentPage?: string
  contextData?: Record<string, unknown>
}

// 快捷建议问题（根据当前页面变化）
const SUGGESTIONS: Record<string, string[]> = {
  today: ['今天最大的问题是什么？', '和昨天比怎么样？', '我现在该做什么？'],
  review: ['这周的模式是什么？', '我效率最高的时段是？', '给我一些改进建议'],
  plan: ['帮我排今天的优先级', '这个任务要多久？', '这周的目标完成得怎么样？'],
  default: ['今天效率怎么样？', '我最近有什么模式？', '给我一些建议'],
}

export default function AIDock({ currentPage = 'today', contextData }: AIDockProps) {
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isExpanded, setIsExpanded] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [showSuggestions, setShowSuggestions] = useState(true)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // 展开时自动聚焦输入框
  useEffect(() => {
    if (isExpanded) {
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [isExpanded])

  const suggestions = SUGGESTIONS[currentPage] || SUGGESTIONS.default

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || isLoading) return

    const userMsg: ChatMessage = {
      id: Date.now(),
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setIsLoading(true)
    setShowSuggestions(false)

    try {
      // 构建上下文提示
      const contextPrompt = buildContextPrompt(currentPage, contextData)
      const fullMessage = contextPrompt
        ? `${contextPrompt}\n\n用户问题：${text}`
        : text

      let aiContent = ''
      await aiChatStream(fullMessage, (event) => {
        if (event.type === 'content') {
          aiContent += event.content
          setMessages(prev => {
            const last = prev[prev.length - 1]
            if (last && last.role === 'assistant') {
              return [...prev.slice(0, -1), { ...last, content: aiContent }]
            }
            return [...prev, {
              id: Date.now(),
              role: 'assistant',
              content: aiContent,
              created_at: new Date().toISOString(),
            }]
          })
        } else if (event.type === 'error') {
          aiContent += `\n\n[错误: ${event.content}]`
        }
      })
    } catch (err) {
      setMessages(prev => [...prev, {
        id: Date.now(),
        role: 'assistant',
        content: '抱歉，我遇到了一些问题。请稍后再试。',
        created_at: new Date().toISOString(),
      }])
    } finally {
      setIsLoading(false)
    }
  }, [isLoading, currentPage, contextData])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input)
    }
  }

  const clearChat = () => {
    setMessages([])
    setShowSuggestions(true)
  }

  return (
    <div className="fixed bottom-0 left-56 right-0 z-40 bg-cd-bg border-t border-cd-border">
      {/* 展开的对话区域 */}
      {isExpanded && (
        <div className="h-72 flex flex-col bg-cd-bg border-b border-cd-border animate-slide-up">
          {/* 对话头部 */}
          <div className="flex items-center justify-between px-4 py-2 border-b border-cd-border">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-full bg-cd-green/15 flex items-center justify-center">
                <Bot size={14} className="text-cd-green" />
              </div>
              <span className="text-sm font-medium text-cd-text">AI 助手</span>
              <span className="text-xs text-cd-text-tertiary">
                · 正在查看{currentPage === 'today' ? '今日' : currentPage === 'review' ? '回顾' : currentPage === 'plan' ? '计划' : ''}数据
              </span>
            </div>
            <div className="flex items-center gap-1">
              {messages.length > 0 && (
                <button
                  onClick={clearChat}
                  className="text-xs text-cd-text-tertiary hover:text-cd-text px-2 py-1 rounded hover:bg-cd-hover transition"
                >
                  清空
                </button>
              )}
              <button
                onClick={() => setIsExpanded(false)}
                className="p-1 rounded hover:bg-cd-hover transition"
              >
                <ChevronDown size={16} className="text-cd-text-tertiary" />
              </button>
            </div>
          </div>

          {/* 消息列表 */}
          <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
            {messages.length === 0 && showSuggestions && (
              <div className="flex flex-col items-center justify-center h-full">
                <div className="w-10 h-10 rounded-full bg-cd-green/10 flex items-center justify-center mb-3">
                  <Sparkles size={20} className="text-cd-green" />
                </div>
                <p className="text-sm text-cd-text-secondary mb-3">有什么想问我的？</p>
                <div className="flex flex-wrap gap-2 justify-center max-w-md">
                  {suggestions.map((s, i) => (
                    <button
                      key={i}
                      onClick={() => sendMessage(s)}
                      className="text-xs px-3 py-1.5 rounded-full border border-cd-border text-cd-text-secondary hover:border-cd-green hover:text-cd-green transition"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((msg, i) => (
              <div
                key={i}
                className={`flex gap-2.5 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
              >
                <div className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 ${
                  msg.role === 'user' ? 'bg-cd-purple/15' : 'bg-cd-green/15'
                }`}>
                  {msg.role === 'user'
                    ? <User size={13} className="text-cd-purple" />
                    : <Bot size={13} className="text-cd-green" />
                  }
                </div>
                <div className={`max-w-[80%] px-3 py-2 rounded-lg text-sm ${
                  msg.role === 'user'
                    ? 'bg-cd-purple/10 text-cd-text'
                    : 'bg-cd-bg-secondary text-cd-text'
                }`}>
                  {msg.content}
                  {isLoading && i === messages.length - 1 && msg.role === 'assistant' && (
                    <span className="inline-block w-1.5 h-3.5 bg-cd-green ml-0.5 animate-pulse align-middle" />
                  )}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        </div>
      )}

      {/* 输入栏 */}
      <div className="px-4 py-2.5">
        <div className="flex items-center gap-2 bg-cd-bg-secondary border border-cd-border rounded-lg px-3 py-2 focus-within:border-cd-green/50 transition">
          {!isExpanded && (
            <button
              onClick={() => setIsExpanded(true)}
              className="p-1 rounded hover:bg-cd-hover transition shrink-0"
              title="展开对话"
            >
              <ChevronUp size={16} className="text-cd-text-tertiary" />
            </button>
          )}
          <Bot size={16} className="text-cd-green shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => { if (!isExpanded) setIsExpanded(true) }}
            placeholder="问我任何关于你今天的事..."
            className="flex-1 bg-transparent text-sm text-cd-text placeholder:text-cd-text-tertiary outline-none"
          />
          {input && (
            <button
              onClick={() => setInput('')}
              className="p-1 rounded hover:bg-cd-hover transition shrink-0"
            >
              <X size={14} className="text-cd-text-tertiary" />
            </button>
          )}
          <button
            onClick={() => sendMessage(input)}
            disabled={!input.trim() || isLoading}
            className="p-1.5 rounded bg-cd-green text-white disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-90 transition shrink-0"
          >
            <Send size={14} />
          </button>
        </div>
      </div>
    </div>
  )
}

/**
 * 构建 AI 上下文提示
 * 根据当前页面和数据，给 AI 提供相关上下文
 */
function buildContextPrompt(page: string, data?: Record<string, unknown>): string {
  if (!data) return ''

  const parts: string[] = ['【当前上下文】']

  if (page === 'today' && data.todayStats) {
    const stats = data.todayStats as Record<string, unknown>
    parts.push(`今日数据：有效时间 ${stats.total_duration_min || 0} 分钟，活动捕捉 ${stats.total_captures || 0} 次`)
    if (stats.categories) {
      parts.push(`分类分布：${JSON.stringify(stats.categories)}`)
    }
  }

  if (data.currentActivity) {
    parts.push(`当前活动：${JSON.stringify(data.currentActivity)}`)
  }

  if (data.todos && Array.isArray(data.todos)) {
    parts.push(`今日待办：${data.todos.length} 项，其中 ${data.todos.filter((t: Todo) => t.status === 'completed').length} 项已完成`)
  }

  return parts.length > 1 ? parts.join('\n') : ''
}

// 临时类型定义，避免循环导入
interface Todo {
  id: number
  title: string
  status: string
  scheduled_time?: string
  estimated_duration?: number
}

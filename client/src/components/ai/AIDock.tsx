import { useState, useRef, useEffect } from 'react'
import { Send, Bot, X, ChevronUp, ChevronDown, Sparkles, Expand } from 'lucide-react'
import { useNavigate, useLocation } from 'react-router-dom'

/**
 * 底部常驻 AI 对话栏（快速入口）
 * - 全局常驻，无论在哪个页面都能唤起 AI
 * - 点击输入框 / 发送消息 → 跳转完整对话页 /ai-chat 并携带消息
 * - 在 /ai-chat 页面由 App.tsx 门控隐藏
 * - 展开面板保留为快速预览，点"展开完整对话"跳转全屏对话
 */

interface AIDockProps {
  currentPage?: string
}

const SUGGESTIONS: Record<string, string[]> = {
  today: ['今天最大的问题是什么？', '和昨天比怎么样？', '我现在该做什么？'],
  review: ['这周的模式是什么？', '我效率最高的时段是？', '给我一些改进建议'],
  plan: ['帮我排今天的优先级', '这个任务要多久？', '这周的目标完成得怎么样？'],
  default: ['今天效率怎么样？', '我最近有什么模式？', '给我一些建议'],
}

export default function AIDock({ currentPage = 'today' }: AIDockProps) {
  const [input, setInput] = useState('')
  const [isExpanded, setIsExpanded] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()
  const location = useLocation()

  // 展开时自动聚焦
  useEffect(() => {
    if (isExpanded) {
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [isExpanded])

  const suggestions = SUGGESTIONS[currentPage] || SUGGESTIONS.default

  /** 跳转到完整对话页并携带消息；无消息则只跳转空对话 */
  const gotoFullChat = (text?: string) => {
    const msg = (text ?? input).trim()
    setIsExpanded(false)
    if (msg) {
      navigate(`/ai-chat?msg=${encodeURIComponent(msg)}`)
      setInput('')
    } else {
      navigate('/ai-chat')
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      gotoFullChat()
    }
  }

  const handleFocus = () => {
    // 聚焦输入框时若不在对话页，跳转过去（保留本地输入预览）
    if (location.pathname !== '/ai-chat' && !isExpanded) {
      setIsExpanded(true)
    }
  }

  return (
    <div className="ai-dock-float fixed bottom-5 z-40 w-[min(620px,58%)]" style={{ left: 'calc(50% + 124px)', transform: 'translateX(-50%)' }}>
      {/* 展开的快速预览面板 */}
      {isExpanded && (
        <div className="glass-strong rounded-2xl mb-2 overflow-hidden animate-slide-up">
          <div className="flex items-center justify-between px-4 py-2 border-b border-cd-border/50">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-full bg-cd-accent/15 flex items-center justify-center">
                <Bot size={14} className="text-cd-accent" />
              </div>
              <span className="text-sm font-medium text-cd-text">AI 助手</span>
              <span className="text-xs text-cd-text-tertiary">快速预览</span>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => gotoFullChat()}
                className="flex items-center gap-1 text-xs text-cd-accent hover:bg-cd-accent/10 px-2.5 py-1 rounded-lg transition"
              >
                <Expand size={13} /> 展开完整对话
              </button>
              <button
                onClick={() => setIsExpanded(false)}
                className="p-1 rounded-lg hover:bg-cd-hover transition"
              >
                <ChevronDown size={16} className="text-cd-text-tertiary" />
              </button>
            </div>
          </div>

          {/* 预览区：建议问题 */}
          <div className="px-4 py-4">
            <div className="flex flex-col items-center">
              <div className="w-10 h-10 rounded-full bg-cd-accent/10 flex items-center justify-center mb-2.5">
                <Sparkles size={18} className="text-cd-accent" />
              </div>
              <p className="text-sm text-cd-text-secondary mb-3">输入问题将在完整对话页打开</p>
              <div className="flex flex-wrap gap-2 justify-center max-w-md">
                {suggestions.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => gotoFullChat(s)}
                    className="text-xs px-3 py-1.5 rounded-full border border-cd-border text-cd-text-secondary hover:border-cd-accent hover:text-cd-accent transition"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 悬浮玻璃输入条 */}
      <div className="glass-strong rounded-full flex items-center gap-2 px-4 h-10">
        {!isExpanded && (
          <button
            onClick={() => setIsExpanded(true)}
            className="p-1 rounded-lg hover:bg-cd-hover transition shrink-0"
            title="展开快速预览"
          >
            <ChevronUp size={16} className="text-cd-text-tertiary" />
          </button>
        )}
        <Bot size={16} className="text-cd-accent shrink-0" />
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={handleFocus}
          onMouseDown={() => {
            // 点击输入框即跳转到完整对话页
            if (location.pathname !== '/ai-chat') {
              // 让输入框先获得焦点值，再跳转
              setTimeout(() => gotoFullChat(), 0)
            }
          }}
          placeholder="问我任何关于你今天的事..."
          className="flex-1 bg-transparent text-sm text-cd-text placeholder:text-cd-text-tertiary outline-none"
        />
        {input && (
          <button
            onClick={() => setInput('')}
            className="p-1 rounded-lg hover:bg-cd-hover transition shrink-0"
          >
            <X size={14} className="text-cd-text-tertiary" />
          </button>
        )}
        <button
          onClick={() => gotoFullChat()}
          disabled={!input.trim()}
          className="p-1.5 rounded-full bg-cd-accent text-white disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-90 transition shrink-0"
        >
          <Send size={14} />
        </button>
      </div>
    </div>
  )
}

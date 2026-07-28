import { useState, useEffect, useCallback, useRef } from 'react'
import { ClipboardList, Search, Trash2, Copy, Check, FileText, Link2, Image } from 'lucide-react'
import { request } from '../api/core'
import { useToast } from '../components/Toast'

interface ClipboardItem {
  id: number
  kind: string
  content: string
  timestamp: string
}

interface ClipboardResponse {
  items: ClipboardItem[]
}

function KindIcon({ kind }: { kind: string }) {
  switch (kind) {
    case 'url':
      return <Link2 size={16} className="text-blue-400 shrink-0" />
    case 'image':
      return <Image size={16} className="text-purple-400 shrink-0" />
    default:
      return <FileText size={16} className="text-cd-accent shrink-0" />
  }
}

function formatTime(ts: string): string {
  const d = new Date(ts)
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin}分钟前`
  const diffHour = Math.floor(diffMin / 60)
  if (diffHour < 24) return `${diffHour}小时前`
  const diffDay = Math.floor(diffHour / 24)
  if (diffDay < 7) return `${diffDay}天前`
  return d.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export default function ClipboardHistory() {
  const [items, setItems] = useState<ClipboardItem[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [copiedId, setCopiedId] = useState<number | null>(null)
  const toast = useToast()
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = useCallback(async () => {
    try {
      const data = await request('/api/platform/clipboard') as ClipboardResponse
      setItems(data.items ?? [])
    } catch {
      toast.error('加载剪贴板历史失败')
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => {
    load()
    timerRef.current = setInterval(() => {
      if (document.visibilityState === 'visible') load()
    }, 30000)
    const onVis = () => {
      if (document.visibilityState === 'visible') load()
    }
    document.addEventListener('visibilitychange', onVis)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
      document.removeEventListener('visibilitychange', onVis)
    }
  }, [load])

  const handleCopy = async (item: ClipboardItem) => {
    try {
      await navigator.clipboard.writeText(item.content)
      setCopiedId(item.id)
      toast.success('已复制到剪贴板')
      setTimeout(() => setCopiedId(null), 2000)
    } catch {
      toast.error('复制失败')
    }
  }

  const handleClear = async () => {
    if (!window.confirm('确定清空所有剪贴板历史？此操作不可撤销。')) return
    try {
      await request('/api/platform/clipboard/clear', { method: 'POST' })
      setItems([])
      toast.success('已清空剪贴板历史')
    } catch {
      toast.error('清空失败，请重试')
    }
  }

  const filtered = search
    ? items.filter(i => i.content.toLowerCase().includes(search.toLowerCase()))
    : items

  return (
    <div className="min-h-screen p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-cd-text flex items-center gap-2">
          <ClipboardList className="text-cd-accent" /> 剪贴板历史
        </h1>
        {items.length > 0 && (
          <button
            onClick={handleClear}
            className="flex items-center gap-2 px-4 py-2 text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg hover:bg-red-400/20 transition"
          >
            <Trash2 size={16} /> 清空历史
          </button>
        )}
      </div>

      {items.length > 0 && (
        <div className="relative mb-4">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-cd-text-secondary" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="搜索剪贴板内容..."
            className="w-full pl-9 pr-4 py-2.5 bg-cd-bg-card border border-white/10 rounded-lg text-cd-text placeholder:text-cd-text-secondary/50 focus:outline-none focus:border-cd-accent/50 transition"
          />
        </div>
      )}

      {loading ? (
        <div className="text-center py-12 text-cd-text-secondary">加载中...</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-cd-text-secondary">
          <ClipboardList size={48} className="mx-auto mb-3 opacity-30" />
          <p className="text-lg mb-1">{items.length === 0 ? '暂无剪贴板记录' : '没有匹配的结果'}</p>
          <p className="text-sm opacity-60">
            {items.length === 0 ? '复制内容后，历史将自动记录在此处' : '尝试其他关键词'}
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {filtered.map(item => (
            <div
              key={item.id}
              className="bg-cd-bg-card rounded-xl p-4 border border-white/5 hover:border-white/10 transition group"
            >
              <div className="flex items-start gap-3">
                <KindIcon kind={item.kind} />
                <div className="flex-1 min-w-0">
                  <p className="text-cd-text break-all leading-relaxed">
                    {item.content.length > 80 ? item.content.slice(0, 80) + '…' : item.content}
                  </p>
                  <span className="text-xs text-cd-text-secondary mt-1 block">
                    {formatTime(item.timestamp)}
                  </span>
                </div>
                <button
                  onClick={() => handleCopy(item)}
                  className="shrink-0 p-2 rounded-lg text-cd-text-secondary hover:text-cd-accent hover:bg-cd-accent/10 transition opacity-0 group-hover:opacity-100"
                  title="复制内容"
                >
                  {copiedId === item.id ? <Check size={16} className="text-green-400" /> : <Copy size={16} />}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {filtered.length > 0 && (
        <p className="text-center text-xs text-cd-text-secondary mt-4 opacity-50">
          共 {filtered.length} 条记录{search && items.length !== filtered.length ? `（筛选自 ${items.length} 条）` : ''}
        </p>
      )}
    </div>
  )
}

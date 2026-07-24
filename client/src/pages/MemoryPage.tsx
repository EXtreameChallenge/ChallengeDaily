import { useState, useCallback } from 'react'
import dayjs from 'dayjs'
import {
  Brain,
  Search,
  Loader2,
  RefreshCw,
  Trash2,
  Database,
  Sparkles,
  ListOrdered,
  AlertCircle,
  FileText,
  Tag,
} from 'lucide-react'
import {
  searchMemory,
  getMemoryStatus,
  getMemoryList,
  deleteMemory,
  triggerIndexing,
  triggerExtraction,
  type MemoryItem,
  type MemorySearchResult,
  type MemoryStatus,
} from '../api/client'
import { useAsyncData, ApiErrorDisplay } from '../components/shared'
import { useToast } from '../components/Toast'

// ── 来源类型中文映射 ──
const SOURCE_TYPE_LABEL: Record<string, string> = {
  mubu: '幕布文档',
  activity: '活动记录',
  report: '日报',
  diary: '日记',
  goal: '目标',
  todo: '待办',
  habit: '习惯',
  manual: '手动录入',
  opml: 'OPML 导入',
}

function sourceTypeLabel(t?: string): string {
  if (!t) return '未知来源'
  return SOURCE_TYPE_LABEL[t] || t
}

/** 高亮关键词的文本片段 */
function HighlightText({ text, query }: { text: string; query: string }) {
  if (!query.trim()) return <>{text}</>
  const keywords = query
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  if (keywords.length === 0) return <>{text}</>
  const re = new RegExp(`(${keywords.join('|')})`, 'gi')
  const parts = text.split(re)
  return (
    <>
      {parts.map((part, i) =>
        re.test(part) ? (
          <mark key={i} className="bg-cd-green/20 text-cd-green rounded px-0.5">
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  )
}

export default function MemoryPage() {
  const toast = useToast()
  // 搜索状态
  const [searchQuery, setSearchQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [searchResults, setSearchResults] = useState<MemorySearchResult[]>([])
  const [hasSearched, setHasSearched] = useState(false)
  // 操作进行中状态
  const [indexing, setIndexing] = useState(false)
  const [extracting, setExtracting] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  // 用于触发列表刷新的 nonce
  const [refreshNonce, setRefreshNonce] = useState(0)

  // 加载向量化状态 + 记忆列表（合并到一次 useAsyncData，避免重复 loading）
  const { data, loading, error, refresh } = useAsyncData<{
    status: MemoryStatus | null
    memories: MemoryItem[]
    total?: number
  }>(
    async () => {
      // 并行加载状态与列表；status 失败时不影响列表展示
      const [statusRes, listRes] = await Promise.all([
        getMemoryStatus().catch(() => null),
        getMemoryList(50).catch(() => ({ memories: [] as MemoryItem[], total: 0 })),
      ])
      return {
        status: statusRes,
        memories: listRes.memories,
        total: listRes.total,
      }
    },
    [refreshNonce],
    60 * 1000, // 1 分钟自动刷新
  )

  const status = data?.status ?? null
  const memories = data?.memories ?? []

  // ── 搜索 ──
  const handleSearch = useCallback(async () => {
    const q = searchQuery.trim()
    if (!q) {
      toast.warning('请输入搜索关键词')
      return
    }
    setSearching(true)
    setHasSearched(true)
    try {
      const { results } = await searchMemory(q, 10)
      setSearchResults(results)
      if (results.length === 0) {
        toast.info('未找到匹配的记忆')
      } else {
        toast.success(`找到 ${results.length} 条匹配记忆`)
      }
    } catch (err: any) {
      toast.error(err?.message || '搜索失败')
      setSearchResults([])
    } finally {
      setSearching(false)
    }
  }, [searchQuery, toast])

  const handleClearSearch = useCallback(() => {
    setSearchQuery('')
    setSearchResults([])
    setHasSearched(false)
  }, [])

  // ── 触发向量化索引 ──
  const handleIndex = useCallback(async () => {
    setIndexing(true)
    try {
      const res = await triggerIndexing()
      toast.success(`索引任务已触发${typeof res.indexed === 'number' ? `（本次索引 ${res.indexed} 条）` : ''}`)
      // 索引可能耗时，延迟刷新状态
      setTimeout(() => refresh(), 1000)
    } catch (err: any) {
      toast.error(err?.message || '触发索引失败')
    } finally {
      setIndexing(false)
    }
  }, [refresh, toast])

  // ── 触发事实抽取 ──
  const handleExtract = useCallback(async () => {
    setExtracting(true)
    try {
      const res = await triggerExtraction()
      toast.success(`事实抽取已触发${typeof res.extracted === 'number' ? `（本次抽取 ${res.extracted} 条）` : ''}`)
      // 抽取可能产生新记忆，刷新列表
      setTimeout(() => refresh(), 1000)
    } catch (err: any) {
      toast.error(err?.message || '触发抽取失败')
    } finally {
      setExtracting(false)
    }
  }, [refresh, toast])

  // ── 删除记忆 ──
  const handleDelete = useCallback(
    async (id: string) => {
      if (!window.confirm('确定要删除这条记忆吗？此操作不可恢复。')) return
      setDeletingId(id)
      try {
        await deleteMemory(id)
        toast.success('记忆已删除')
        // 从搜索结果中移除
        setSearchResults((prev) => prev.filter((r) => r.id !== id))
        // 刷新列表与状态
        setRefreshNonce((n) => n + 1)
      } catch (err: any) {
        toast.error(err?.message || '删除失败')
      } finally {
        setDeletingId(null)
      }
    },
    [toast],
  )

  // ── 进度条百分比 ──
  const total = status?.total ?? 0
  const indexed = status?.indexed ?? 0
  const pending = status?.pending ?? Math.max(0, total - indexed)
  const progressPct =
    typeof status?.progress_pct === 'number'
      ? status.progress_pct
      : total > 0
        ? Math.min(100, Math.round((indexed / total) * 100))
        : 0

  return (
    <div className="animate-fade-in space-y-5">
      {/* ─── 标题 ──────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-cd-text flex items-center gap-2">
            <Brain size={18} className="text-cd-green" />
            记忆系统
          </h1>
          <p className="text-[11px] text-cd-text-tertiary mt-0.5">
            管理从活动记录、幕布文档等抽取的结构化记忆，支持语义检索与向量化索引。
          </p>
        </div>
        <button
          onClick={refresh}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border disabled:opacity-40"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          刷新
        </button>
      </div>

      {/* ─── 向量化状态卡片 ──────────────────── */}
      <section className="card space-y-3">
        <div className="flex items-center gap-2">
          <Database size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">向量化状态</h2>
          {status?.indexing && (
            <span className="flex items-center gap-1 text-[10px] text-cd-green bg-cd-green-light px-2 py-0.5 rounded-full">
              <Loader2 size={10} className="animate-spin" />
              索引中
            </span>
          )}
        </div>

        {loading && !status ? (
          <div className="text-xs text-cd-text-tertiary animate-pulse py-3 text-center">
            正在加载向量化状态...
          </div>
        ) : !status ? (
          <div className="text-xs text-cd-text-tertiary py-3 text-center">
            暂无向量化数据，后端可能尚未启用记忆系统
          </div>
        ) : (
          <>
            {/* 数字概览 */}
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-cd-bg-secondary rounded-lg p-3 text-center">
                <div className="text-sm font-bold text-cd-green">{indexed}</div>
                <div className="text-[10px] text-cd-text-tertiary mt-0.5">已索引</div>
              </div>
              <div className="bg-cd-bg-secondary rounded-lg p-3 text-center">
                <div className="text-sm font-bold text-cd-orange">{pending}</div>
                <div className="text-[10px] text-cd-text-tertiary mt-0.5">待索引</div>
              </div>
              <div className="bg-cd-bg-secondary rounded-lg p-3 text-center">
                <div className="text-sm font-bold text-cd-text">{total}</div>
                <div className="text-[10px] text-cd-text-tertiary mt-0.5">总数</div>
              </div>
            </div>

            {/* 进度条 */}
            <div>
              <div className="flex items-center justify-between text-[11px] text-cd-text-secondary mb-1">
                <span>索引进度</span>
                <span className="font-medium text-cd-text">{progressPct}%</span>
              </div>
              <div className="h-2 rounded-full bg-cd-bg-secondary overflow-hidden border border-cd-border">
                <div
                  className="h-full rounded-full bg-cd-green transition-all duration-500"
                  style={{ width: `${progressPct}%` }}
                />
              </div>
              {status.last_index && (
                <div className="text-[10px] text-cd-text-tertiary mt-1">
                  最近索引时间：{dayjs(status.last_index).format('YYYY-MM-DD HH:mm')}
                </div>
              )}
            </div>
          </>
        )}

        {/* 操作按钮 */}
        <div className="flex flex-wrap gap-3 pt-1">
          <button
            onClick={handleIndex}
            disabled={indexing}
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium bg-cd-green text-white hover:opacity-90 transition-opacity disabled:opacity-40"
          >
            {indexing ? <Loader2 size={12} className="animate-spin" /> : <Database size={12} />}
            {indexing ? '索引中...' : '手动索引'}
          </button>
          <button
            onClick={handleExtract}
            disabled={extracting}
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border disabled:opacity-40"
          >
            {extracting ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
            {extracting ? '抽取中...' : '事实抽取'}
          </button>
        </div>
        <div className="text-[10px] text-cd-text-tertiary">
          • 手动索引：将未向量化的记忆条目重新生成向量索引<br />
          • 事实抽取：从已同步的文档中抽取关键事实写入记忆库
        </div>
      </section>

      {/* ─── 错误展示 ──────────────────── */}
      {error && !loading && <ApiErrorDisplay error={error} onRetry={refresh} />}

      {/* ─── 语义搜索 ──────────────────── */}
      <section className="card space-y-3">
        <div className="flex items-center gap-2">
          <Search size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">语义搜索</h2>
        </div>

        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSearch()
              }}
              placeholder="输入关键词，按回车搜索记忆..."
              className="w-full px-3 py-2 pl-9 bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg text-sm focus:outline-none focus:border-cd-green transition-colors"
            />
            {searching ? (
              <Loader2 size={14} className="absolute left-2.5 top-2.5 animate-spin text-cd-text-tertiary" />
            ) : (
              <Search size={14} className="absolute left-2.5 top-2.5 text-cd-text-tertiary" />
            )}
          </div>
          <button
            onClick={handleSearch}
            disabled={searching || !searchQuery.trim()}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium bg-cd-green text-white hover:opacity-90 transition-opacity disabled:opacity-40"
          >
            搜索
          </button>
          {hasSearched && (
            <button
              onClick={handleClearSearch}
              disabled={searching}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border disabled:opacity-40"
            >
              清除
            </button>
          )}
        </div>

        {/* 搜索结果 */}
        {hasSearched && (
          <div className="space-y-2">
            {searchResults.length === 0 ? (
              <div className="text-center py-6 text-xs text-cd-text-tertiary">
                <AlertCircle size={28} className="mx-auto mb-2 opacity-40" />
                {searching ? '搜索中...' : '未找到匹配的记忆'}
              </div>
            ) : (
              <>
                <div className="text-[11px] text-cd-text-tertiary">
                  共 {searchResults.length} 条结果
                </div>
                {searchResults.map((r) => (
                  <SearchResultItem
                    key={r.id}
                    result={r}
                    query={searchQuery}
                    onDelete={handleDelete}
                    deleting={deletingId === r.id}
                  />
                ))}
              </>
            )}
          </div>
        )}
      </section>

      {/* ─── 记忆列表 ──────────────────── */}
      <section className="card space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ListOrdered size={16} className="text-cd-green" />
            <h2 className="text-sm font-semibold text-cd-text">记忆列表</h2>
            <span className="text-[10px] text-cd-text-tertiary bg-cd-bg-secondary px-2 py-0.5 rounded-full">
              {memories.length} 条
            </span>
          </div>
        </div>

        {loading && memories.length === 0 ? (
          <div className="text-xs text-cd-text-tertiary animate-pulse py-6 text-center">
            正在加载记忆列表...
          </div>
        ) : memories.length === 0 ? (
          <div className="text-center py-8 text-xs text-cd-text-tertiary">
            <FileText size={32} className="mx-auto mb-2 opacity-30" />
            暂无记忆条目，可点击上方「事实抽取」生成
          </div>
        ) : (
          <div className="space-y-2 max-h-[600px] overflow-y-auto pr-1">
            {memories.map((m) => (
              <MemoryListItem
                key={m.id}
                memory={m}
                onDelete={handleDelete}
                deleting={deletingId === m.id}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

// ── 搜索结果条目 ──
function SearchResultItem({
  result,
  query,
  onDelete,
  deleting,
}: {
  result: MemorySearchResult
  query: string
  onDelete: (id: string) => void
  deleting: boolean
}) {
  const source = result.source || result.source_type
  const display = result.snippet || result.content
  return (
    <div className="bg-cd-bg-secondary rounded-lg p-3 border border-cd-border hover:border-cd-green/30 transition-colors">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          {result.title && (
            <div className="text-sm font-medium text-cd-text truncate mb-1">
              <HighlightText text={result.title} query={query} />
            </div>
          )}
          <div className="text-xs text-cd-text-secondary leading-relaxed break-words">
            <HighlightText text={display} query={query} />
          </div>
          <div className="flex items-center gap-2 mt-2 flex-wrap text-[10px] text-cd-text-tertiary">
            {source && (
              <span className="flex items-center gap-1 bg-cd-bg px-1.5 py-0.5 rounded">
                <Tag size={9} />
                {sourceTypeLabel(source)}
              </span>
            )}
            {typeof result.score === 'number' && (
              <span className="bg-cd-bg px-1.5 py-0.5 rounded">
                相似度 {(result.score * 100).toFixed(1)}%
              </span>
            )}
            {result.created_at && (
              <span>{dayjs(result.created_at).format('YYYY-MM-DD HH:mm')}</span>
            )}
          </div>
        </div>
        <button
          onClick={() => onDelete(result.id)}
          disabled={deleting}
          title="删除该记忆"
          className="shrink-0 text-cd-text-tertiary hover:text-cd-red transition-colors p-1 disabled:opacity-40"
        >
          {deleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
        </button>
      </div>
    </div>
  )
}

// ── 记忆列表条目 ──
function MemoryListItem({
  memory,
  onDelete,
  deleting,
}: {
  memory: MemoryItem
  onDelete: (id: string) => void
  deleting: boolean
}) {
  return (
    <div className="bg-cd-bg-secondary rounded-lg p-3 border border-cd-border hover:border-cd-green/30 transition-colors">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          {memory.title && (
            <div className="text-sm font-medium text-cd-text truncate mb-1">
              {memory.title}
            </div>
          )}
          <div className="text-xs text-cd-text-secondary leading-relaxed break-words whitespace-pre-wrap">
            {memory.content}
          </div>
          <div className="flex items-center gap-2 mt-2 flex-wrap text-[10px] text-cd-text-tertiary">
            {memory.source_type && (
              <span className="flex items-center gap-1 bg-cd-bg px-1.5 py-0.5 rounded">
                <Tag size={9} />
                {sourceTypeLabel(memory.source_type)}
              </span>
            )}
            {memory.created_at && (
              <span>{dayjs(memory.created_at).format('YYYY-MM-DD HH:mm')}</span>
            )}
          </div>
        </div>
        <button
          onClick={() => onDelete(memory.id)}
          disabled={deleting}
          title="删除该记忆"
          className="shrink-0 text-cd-text-tertiary hover:text-cd-red transition-colors p-1 disabled:opacity-40"
        >
          {deleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
        </button>
      </div>
    </div>
  )
}

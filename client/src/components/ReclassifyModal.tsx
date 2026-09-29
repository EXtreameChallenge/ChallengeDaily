import { useState, useEffect, useCallback } from 'react'
import { Eye, Play, Loader2, AlertTriangle, CheckCircle2, History } from 'lucide-react'
import Modal from './Modal'
import { useToast } from './Toast'
import { useFocusTrap } from '../hooks/useA11y'
import {
  previewReclassify,
  executeReclassify,
  getKnownApps,
  CATEGORY_COLORS,
  type ReclassifyPreview,
  type ReclassifyResult,
} from '../api/client'

interface ReclassifyModalProps {
  open: boolean
  onClose: () => void
  /** 指定默认应用（从 AppTags 行内入口触发时传入），不传则默认全部 */
  defaultAppName?: string
  /** 重分类完成后的回调（用于刷新外层列表） */
  onReclassified?: () => void
}

type Phase = 'idle' | 'previewing' | 'previewed' | 'executing' | 'done'

export default function ReclassifyModal({ open, onClose, defaultAppName, onReclassified }: ReclassifyModalProps) {
  const toast = useToast()
  const [date, setDate] = useState('')
  const [appName, setAppName] = useState('')
  const [knownApps, setKnownApps] = useState<string[]>([])

  const [phase, setPhase] = useState<Phase>('idle')
  const [preview, setPreview] = useState<ReclassifyPreview | null>(null)
  const [result, setResult] = useState<ReclassifyResult | null>(null)
  const [error, setError] = useState<string>('')

  // 焦点管理：模态框打开时聚焦首个可交互元素，关闭时还原焦点
  const trapRef = useFocusTrap<HTMLDivElement>(open)

  // 加载已知应用列表（用于应用选择器 datalist）
  useEffect(() => {
    if (!open) return
    let cancelled = false
    ;(async () => {
      try {
        const data = await getKnownApps()
        if (!cancelled) {
          setKnownApps((data.apps || []).map((a) => a.app_name).filter(Boolean))
        }
      } catch {
        // 已知应用列表加载失败不阻断流程，用户仍可手动输入
      }
    })()
    return () => {
      cancelled = true
    }
  }, [open])

  // 打开时重置状态并应用默认应用
  useEffect(() => {
    if (!open) return
    setPhase('idle')
    setPreview(null)
    setResult(null)
    setError('')
    setAppName(defaultAppName || '')
    setDate('')
  }, [open, defaultAppName])

  const buildParams = useCallback(() => {
    const params: { date?: string; app_name?: string } = {}
    const d = date.trim()
    if (d) params.date = d
    const a = appName.trim()
    if (a) params.app_name = a
    return params
  }, [date, appName])

  const handlePreview = async () => {
    setPhase('previewing')
    setError('')
    setPreview(null)
    setResult(null)
    try {
      const data = await previewReclassify(buildParams())
      setPreview(data)
      setPhase('previewed')
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '预览失败'
      setError(msg)
      setPhase('idle')
      toast.error(msg)
    }
  }

  const handleExecute = async () => {
    setPhase('executing')
    setError('')
    try {
      const data = await executeReclassify(buildParams())
      setResult(data)
      setPhase('done')
      if (data.error) {
        toast.error(data.error)
      } else {
        toast.success(`重分类完成：共 ${data.total} 条，变更 ${data.changed} 条`)
        onReclassified?.()
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '执行失败'
      setError(msg)
      setPhase('previewed')
      toast.error(msg)
    }
  }

  const handleClose = () => {
    if (phase === 'executing' || phase === 'previewing') {
      // 执行中不允许关闭，避免中断事务
      toast.warning('处理中，请稍候')
      return
    }
    onClose()
  }

  const busy = phase === 'previewing' || phase === 'executing'
  const params = buildParams()
  const hasFilter = !!(params.date || params.app_name)

  const footer = (
    <div className="flex items-center justify-between gap-2">
      <div className="text-xs text-cd-text-tertiary">
        {phase === 'done' && result
          ? `共 ${result.total} 条，变更 ${result.changed} 条`
          : phase === 'previewed' && preview
            ? `匹配 ${preview.total} 条，将变更 ${preview.would_change} 条`
            : hasFilter
              ? '将按筛选条件重分类'
              : '将重分类全部历史数据'}
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={handleClose}
          disabled={busy}
          className="px-4 py-2 rounded-xl text-sm text-cd-text-secondary border border-cd-border hover:bg-cd-hover transition disabled:opacity-40"
        >
          {phase === 'done' ? '关闭' : '取消'}
        </button>
        {phase !== 'done' && (
          <button
            onClick={handlePreview}
            disabled={busy}
            className="flex items-center gap-1 px-4 py-2 rounded-xl text-sm font-medium bg-cd-bg-secondary text-cd-text border border-cd-border hover:bg-cd-hover transition disabled:opacity-40"
          >
            {phase === 'previewing' ? <Loader2 size={14} className="animate-spin" /> : <Eye size={14} />}
            预览
          </button>
        )}
        {phase !== 'done' && (
          <button
            onClick={handleExecute}
            disabled={busy || phase === 'idle'}
            className="flex items-center gap-1 px-4 py-2 rounded-xl text-sm font-medium bg-cd-accent/20 text-cd-accent border border-cd-accent/30 hover:bg-cd-accent/30 transition disabled:opacity-40"
            title={phase === 'idle' ? '请先预览确认' : '执行重分类'}
          >
            {phase === 'executing' ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
            执行重分类
          </button>
        )}
      </div>
    </div>
  )

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="重分类历史数据"
      maxWidth="max-w-3xl"
      footer={footer}
    >
      <div ref={trapRef} className="space-y-4">
        {/* 说明 */}
        <div className="flex items-start gap-2 text-xs text-cd-text-tertiary bg-cd-bg-secondary rounded-2xl p-3">
          <History size={14} className="mt-0.5 shrink-0 text-cd-accent" />
          <div>
            基于 <span className="text-cd-text-secondary">应用名 + 窗口标题</span> 与最新分类规则重新分类历史 activities。
            原始记录（app_name、window_title）永久保留，可多次重跑。
          </div>
        </div>

        {/* 筛选条件 */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-cd-text-secondary mb-1.5">
              日期（可选，默认全部）
            </label>
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              disabled={busy}
              className="w-full bg-cd-bg-input text-cd-text border border-cd-border rounded-2xl px-3 py-2 text-sm focus:outline-none focus:border-cd-accent/50 disabled:opacity-50"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-cd-text-secondary mb-1.5">
              应用（可选，默认所有）
            </label>
            <input
              type="text"
              list="reclassify-app-list"
              value={appName}
              onChange={(e) => setAppName(e.target.value)}
              placeholder="如 Code.exe"
              disabled={busy}
              className="w-full bg-cd-bg-input text-cd-text border border-cd-border rounded-2xl px-3 py-2 text-sm focus:outline-none focus:border-cd-accent/50 disabled:opacity-50"
            />
            <datalist id="reclassify-app-list">
              {knownApps.map((a) => (
                <option key={a} value={a} />
              ))}
            </datalist>
          </div>
        </div>

        {/* 执行中进度条 */}
        {phase === 'executing' && (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-xs text-cd-text-secondary">
              <Loader2 size={14} className="animate-spin text-cd-accent" />
              正在批量重分类，每 500 条提交一次事务...
            </div>
            <div className="w-full h-1.5 bg-cd-bg-secondary rounded-full overflow-hidden">
              <div className="h-full bg-cd-accent/60 animate-pulse" style={{ width: '100%' }} />
            </div>
          </div>
        )}

        {/* 错误提示 */}
        {error && (
          <div className="flex items-start gap-2 text-xs text-cd-red bg-cd-red-light/30 rounded-2xl p-3">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" />
            <div>{error}</div>
          </div>
        )}

        {/* 预览结果 */}
        {phase === 'previewed' && preview && (
          <PreviewResult preview={preview} />
        )}

        {/* 执行结果 */}
        {phase === 'done' && result && (
          <ExecuteResult result={result} />
        )}
      </div>
    </Modal>
  )
}

/** 预览结果表格 */
function PreviewResult({ preview }: { preview: ReclassifyPreview }) {
  if (preview.total === 0) {
    return (
      <div className="text-center py-6 text-sm text-cd-text-tertiary">
        未匹配到任何记录
      </div>
    )
  }
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3 text-xs">
        <span className="text-cd-text-secondary">
          匹配 <span className="font-semibold text-cd-text">{preview.total}</span> 条
        </span>
        <span className="text-cd-accent">
          将变更 <span className="font-semibold">{preview.would_change}</span> 条
        </span>
        {preview.truncated && (
          <span className="text-cd-text-tertiary">
            （仅展示前 {preview.changes.length} 条变更）
          </span>
        )}
      </div>

      {preview.would_change === 0 ? (
        <div className="flex items-center gap-2 text-sm text-cd-green bg-cd-green-light/20 rounded-2xl p-3">
          <CheckCircle2 size={14} />
          所有记录分类已是最新，无需变更
        </div>
      ) : (
        <div className="border border-cd-border rounded-2xl overflow-hidden">
          <div className="max-h-80 overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-cd-bg-secondary text-cd-text-secondary">
                <tr>
                  <th className="text-left font-medium px-3 py-2">应用</th>
                  <th className="text-left font-medium px-3 py-2">窗口标题</th>
                  <th className="text-left font-medium px-3 py-2 w-20">旧分类</th>
                  <th className="text-left font-medium px-3 py-2 w-20">新分类</th>
                </tr>
              </thead>
              <tbody>
                {preview.changes.map((c) => (
                  <tr key={c.id} className="border-t border-cd-border-light">
                    <td className="px-3 py-2 text-cd-text font-mono">{c.app_name}</td>
                    <td className="px-3 py-2 text-cd-text-secondary max-w-xs truncate" title={c.window_title}>
                      {c.window_title || '(空)'}
                    </td>
                    <td className="px-3 py-2">
                      <CategoryBadge category={c.old_category} />
                    </td>
                    <td className="px-3 py-2">
                      <CategoryBadge category={c.new_category} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

/** 执行结果统计 */
function ExecuteResult({ result }: { result: ReclassifyResult }) {
  if (result.error) {
    return (
      <div className="flex items-start gap-2 text-sm text-cd-red bg-cd-red-light/30 rounded-2xl p-4">
        <AlertTriangle size={16} className="mt-0.5 shrink-0" />
        <div>{result.error}</div>
      </div>
    )
  }
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm text-cd-green bg-cd-green-light/20 rounded-2xl p-3">
        <CheckCircle2 size={16} />
        重分类完成
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-cd-bg-secondary rounded-2xl p-3">
          <div className="text-xs text-cd-text-tertiary">总记录数</div>
          <div className="text-lg font-semibold text-cd-text">{result.total}</div>
        </div>
        <div className="bg-cd-bg-secondary rounded-2xl p-3">
          <div className="text-xs text-cd-text-tertiary">变更条数</div>
          <div className="text-lg font-semibold text-cd-accent">{result.changed}</div>
        </div>
      </div>
      {result.by_category && Object.keys(result.by_category).length > 0 && (
        <div>
          <div className="text-xs font-medium text-cd-text-secondary mb-2">重分类后分类分布</div>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(result.by_category)
              .sort((a, b) => b[1] - a[1])
              .map(([cat, cnt]) => (
                <span
                  key={cat}
                  className="px-2 py-0.5 rounded-full text-[10px] font-medium"
                  style={{
                    background: (CATEGORY_COLORS[cat] || 'var(--cd-text-tertiary)') + '18',
                    color: CATEGORY_COLORS[cat] || 'var(--cd-text-tertiary)',
                  }}
                >
                  {cat} · {cnt}
                </span>
              ))}
          </div>
        </div>
      )}
    </div>
  )
}

/** 分类标签徽章 */
function CategoryBadge({ category }: { category: string }) {
  const color = CATEGORY_COLORS[category]
  return (
    <span
      className="inline-block px-1.5 py-0.5 rounded-lg text-[10px] font-medium"
      style={{
        background: color ? color + '18' : 'var(--cd-bg-secondary)',
        color: color || 'var(--cd-text-tertiary)',
      }}
    >
      {category || '(空)'}
    </span>
  )
}

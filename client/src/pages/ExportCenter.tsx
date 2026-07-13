import { useState } from 'react'
import { BarChart3, TrendingUp, Calendar, Database, Download, Loader2, CheckCircle } from 'lucide-react'
import { getApiToken, getBaseUrl, ensureBaseUrl } from '../api/client'

// ── 下载状态 ──
type DownloadState = 'idle' | 'loading' | 'success' | 'error'

// ── 通用下载函数：调用后端导出接口并触发文件下载 ──
async function downloadExport(endpoint: string, params: Record<string, string>): Promise<void> {
  await ensureBaseUrl()
  const token = await getApiToken()
  const url = new URL(getBaseUrl() + endpoint)
  for (const [k, v] of Object.entries(params)) {
    if (v) url.searchParams.set(k, v)
  }
  const res = await fetch(url.toString(), {
    method: 'GET',
    headers: {
      ...(token ? { 'X-API-Token': token } : {}),
    },
  })
  if (!res.ok) {
    const errText = await res.text().catch(() => '')
    throw new Error(errText || `HTTP ${res.status}`)
  }
  // 从 Content-Disposition 提取文件名
  const cd = res.headers.get('Content-Disposition') || ''
  let filename = `export_${Date.now()}`
  const m = cd.match(/filename="?([^"]+)"?/)
  if (m) filename = m[1]
  // 根据 mimetype 推断扩展名
  const ct = res.headers.get('Content-Type') || ''
  if (!filename.includes('.') && ct.includes('markdown')) filename += '.md'
  else if (!filename.includes('.') && ct.includes('csv')) filename += '.csv'
  else if (!filename.includes('.') && ct.includes('json')) filename += '.json'

  const blob = await res.blob()
  const objUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objUrl
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(objUrl)
}

// ── 单个格式按钮 ──
function FormatButton({
  format,
  state,
  onClick,
}: {
  format: string
  state: DownloadState
  onClick: () => void
}) {
  const labelMap: Record<string, string> = {
    markdown: 'Markdown',
    json: 'JSON',
    csv: 'CSV',
  }
  return (
    <button
      onClick={onClick}
      disabled={state === 'loading'}
      className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
        state === 'loading'
          ? 'bg-cd-bg-secondary text-cd-text-tertiary cursor-wait'
          : state === 'success'
            ? 'bg-cd-green/15 text-cd-green border border-cd-green/30'
            : 'bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover hover:text-cd-text border border-cd-border'
      }`}
    >
      {state === 'loading' ? (
        <Loader2 size={13} className="animate-spin" />
      ) : state === 'success' ? (
        <CheckCircle size={13} />
      ) : (
        <Download size={13} />
      )}
      {labelMap[format] || format}
    </button>
  )
}

// ── 导出卡片 ──
interface ExportCardProps {
  icon: typeof BarChart3
  title: string
  description: string
  accentColor: string
  children: React.ReactNode
}

function ExportCard({ icon: Icon, title, description, accentColor, children }: ExportCardProps) {
  return (
    <div className="bg-cd-bg-secondary border border-cd-border rounded-xl p-5 hover:border-cd-green/30 transition-colors">
      <div className="flex items-start gap-3 mb-4">
        <div
          className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
          style={{ background: `${accentColor}22`, color: accentColor }}
        >
          <Icon size={20} />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-cd-text">{title}</h3>
          <p className="text-xs text-cd-text-tertiary mt-0.5 leading-relaxed">{description}</p>
        </div>
      </div>
      {children}
    </div>
  )
}

export default function ExportCenter() {
  // 周报告
  const [weekStart, setWeekStart] = useState(() => {
    const now = new Date()
    const day = now.getDay() === 0 ? 7 : now.getDay()
    const monday = new Date(now)
    monday.setDate(now.getDate() - day + 1)
    return monday.toISOString().slice(0, 10)
  })
  const [weekStates, setWeekStates] = useState<Record<string, DownloadState>>({})

  // 月报告
  const [monthKey, setMonthKey] = useState(() => new Date().toISOString().slice(0, 7))
  const [monthStates, setMonthStates] = useState<Record<string, DownloadState>>({})

  // 年度总结
  const [year, setYear] = useState(() => String(new Date().getFullYear()))
  const [yearStates, setYearStates] = useState<Record<string, DownloadState>>({})

  // 全部数据
  const [allStates, setAllStates] = useState<Record<string, DownloadState>>({})

  const [errorMsg, setErrorMsg] = useState('')

  const handleDownload = async (
    endpoint: string,
    params: Record<string, string>,
    stateKey: string,
    setStates: React.Dispatch<React.SetStateAction<Record<string, DownloadState>>>,
    format: string,
  ) => {
    setErrorMsg('')
    setStates(prev => ({ ...prev, [format]: 'loading' }))
    try {
      await downloadExport(endpoint, { ...params, format })
      setStates(prev => ({ ...prev, [format]: 'success' }))
      // 2 秒后恢复 idle
      setTimeout(() => {
        setStates(prev => ({ ...prev, [format]: 'idle' }))
      }, 2000)
    } catch (e: any) {
      setStates(prev => ({ ...prev, [format]: 'error' }))
      setErrorMsg(e?.message || '下载失败，请稍后重试')
      setTimeout(() => {
        setStates(prev => ({ ...prev, [format]: 'idle' }))
      }, 2000)
    }
  }

  return (
    <div className="max-w-5xl mx-auto">
      {/* 标题 */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-cd-text flex items-center gap-2">
          <Database size={24} className="text-cd-green" />
          数据导出中心
        </h1>
        <p className="text-sm text-cd-text-tertiary mt-1">
          一键导出你的工作数据，支持 Markdown / JSON / CSV 多种格式，方便归档与分享 📦
        </p>
      </div>

      {/* 错误提示 */}
      {errorMsg && (
        <div className="mb-4 px-4 py-3 rounded-lg bg-cd-red/10 border border-cd-red/20 text-sm text-cd-red">
          {errorMsg}
        </div>
      )}

      {/* 2×2 网格 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* 📊 周报告导出 */}
        <ExportCard
          icon={BarChart3}
          title="周报告导出"
          description="本周任务完成情况 + 番茄统计 + 活动汇总，一键回顾这一周"
          accentColor="#10b981"
        >
          <div className="space-y-3">
            <div>
              <label className="block text-[11px] text-cd-text-tertiary mb-1">选择周（周一日期）</label>
              <input
                type="date"
                value={weekStart}
                onChange={e => setWeekStart(e.target.value)}
                className="w-full bg-cd-bg border border-cd-border rounded-lg px-3 py-2 text-sm text-cd-text focus:outline-none focus:border-cd-green"
              />
            </div>
            <div className="flex gap-2">
              <FormatButton
                format="markdown"
                state={weekStates.markdown || 'idle'}
                onClick={() =>
                  handleDownload('/api/exports/weekly-report', { week_start: weekStart }, 'week', setWeekStates, 'markdown')
                }
              />
              <FormatButton
                format="json"
                state={weekStates.json || 'idle'}
                onClick={() =>
                  handleDownload('/api/exports/weekly-report', { week_start: weekStart }, 'week', setWeekStates, 'json')
                }
              />
              <FormatButton
                format="csv"
                state={weekStates.csv || 'idle'}
                onClick={() =>
                  handleDownload('/api/exports/weekly-report', { week_start: weekStart }, 'week', setWeekStates, 'csv')
                }
              />
            </div>
          </div>
        </ExportCard>

        {/* 📈 月报告导出 */}
        <ExportCard
          icon={TrendingUp}
          title="月报告导出"
          description="月目标 + 完成率 + 每日热力图 + 分类分布，月度复盘好帮手"
          accentColor="#3b82f6"
        >
          <div className="space-y-3">
            <div>
              <label className="block text-[11px] text-cd-text-tertiary mb-1">选择月</label>
              <input
                type="month"
                value={monthKey}
                onChange={e => setMonthKey(e.target.value)}
                className="w-full bg-cd-bg border border-cd-border rounded-lg px-3 py-2 text-sm text-cd-text focus:outline-none focus:border-cd-green"
              />
            </div>
            <div className="flex gap-2">
              <FormatButton
                format="markdown"
                state={monthStates.markdown || 'idle'}
                onClick={() =>
                  handleDownload('/api/exports/monthly-report', { month_key: monthKey }, 'month', setMonthStates, 'markdown')
                }
              />
              <FormatButton
                format="json"
                state={monthStates.json || 'idle'}
                onClick={() =>
                  handleDownload('/api/exports/monthly-report', { month_key: monthKey }, 'month', setMonthStates, 'json')
                }
              />
            </div>
          </div>
        </ExportCard>

        {/* 📅 年度总结导出 */}
        <ExportCard
          icon={Calendar}
          title="年度总结导出"
          description="全年热力图数据 + 月度趋势 + 成就墙，年终回顾一目了然"
          accentColor="#a855f7"
        >
          <div className="space-y-3">
            <div>
              <label className="block text-[11px] text-cd-text-tertiary mb-1">选择年</label>
              <input
                type="number"
                value={year}
                min="2020"
                max="2099"
                onChange={e => setYear(e.target.value)}
                className="w-full bg-cd-bg border border-cd-border rounded-lg px-3 py-2 text-sm text-cd-text focus:outline-none focus:border-cd-green"
              />
            </div>
            <div className="flex gap-2">
              <FormatButton
                format="markdown"
                state={yearStates.markdown || 'idle'}
                onClick={() =>
                  handleDownload('/api/exports/yearly-summary', { year }, 'year', setYearStates, 'markdown')
                }
              />
              <FormatButton
                format="json"
                state={yearStates.json || 'idle'}
                onClick={() =>
                  handleDownload('/api/exports/yearly-summary', { year }, 'year', setYearStates, 'json')
                }
              />
            </div>
          </div>
        </ExportCard>

        {/* 💾 全部数据导出 */}
        <ExportCard
          icon={Database}
          title="全部数据导出"
          description="活动记录 + 待办 + 番茄钟会话 + 日记，完整备份不丢数据"
          accentColor="#f59e0b"
        >
          <div className="space-y-3">
            <div className="text-xs text-cd-text-tertiary bg-cd-bg rounded-lg px-3 py-2.5 border border-cd-border">
              📦 包含：activities + todos + pomodoro_sessions + diaries
              <br />
              ⏱️ 活动记录导出最近 90 天，其他全量
            </div>
            <div className="flex gap-2">
              <FormatButton
                format="json"
                state={allStates.json || 'idle'}
                onClick={() =>
                  handleDownload('/api/exports/all-data', {}, 'all', setAllStates, 'json')
                }
              />
              <FormatButton
                format="csv"
                state={allStates.csv || 'idle'}
                onClick={() =>
                  handleDownload('/api/exports/all-data', {}, 'all', setAllStates, 'csv')
                }
              />
            </div>
          </div>
        </ExportCard>
      </div>

      {/* 底部提示 */}
      <div className="mt-6 text-xs text-cd-text-tertiary text-center">
        💡 导出文件会自动下载到浏览器默认下载目录，可在设置中查看存储路径
      </div>
    </div>
  )
}

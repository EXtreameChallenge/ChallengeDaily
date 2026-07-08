import { useState, useRef, useEffect } from 'react'
import { getReportByDate, generateDailyReport, type ReportContent } from '../api/client'
import { FileText, Calendar, ChevronRight, Sparkles, Copy, Check } from 'lucide-react'
import dayjs from 'dayjs'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useToast } from '../components/Toast'
import { useAsyncData, ApiErrorDisplay } from '../components/shared'

export default function HistoryReports() {
  const toast = useToast()
  const [selectedReport, setSelectedReport] = useState<ReportContent | null>(null)
  const [copied, setCopied] = useState(false)
  const copiedTimer = useRef<ReturnType<typeof setTimeout>>()

  const { data: reports, loading, error, refresh } = useAsyncData<ReportContent[]>(
    async () => {
      // 并行获取最近 14 天的报告
      const dates = Array.from({ length: 14 }, (_, i) =>
        dayjs().subtract(i, 'day').format('YYYY-MM-DD')
      )
      const results = await Promise.allSettled(
        dates.map(d => getReportByDate(d))
      )
      const allReports: ReportContent[] = []
      results.forEach((r, i) => {
        if (r.status === 'fulfilled' && r.value.content) {
          allReports.push({ ...r.value, date: dates[i] })
        }
      })
      return allReports
    },
    [],
  )

  const handleCopy = () => {
    if (selectedReport?.content) {
      navigator.clipboard.writeText(selectedReport.content)
      setCopied(true)
      if (copiedTimer.current) clearTimeout(copiedTimer.current)
      copiedTimer.current = setTimeout(() => setCopied(false), 2000)
    }
  }

  useEffect(() => {
    return () => {
      if (copiedTimer.current) clearTimeout(copiedTimer.current)
    }
  }, [])

  const handleGenerate = async (date: string) => {
    try {
      const result = await generateDailyReport('standard')
      const newReport: ReportContent = { ...result, date }
      refresh() // 刷新列表
      setSelectedReport(newReport)
    } catch (err: any) {
      console.error('Failed to generate report:', err)
    }
  }

  return (
    <div className="animate-fade-in space-y-5">
      <h1 className="text-lg font-semibold text-cd-text">历史报告</h1>

      {error && <ApiErrorDisplay error={error} onRetry={refresh} />}

      {loading ? (
        <div className="text-cd-text-tertiary animate-pulse">加载中...</div>
      ) : (reports || []).length === 0 && !selectedReport ? (
        <div className="card text-center py-16">
          <FileText size={40} className="mx-auto text-cd-text-tertiary mb-4" />
          <p className="text-cd-text-secondary text-sm mb-2">暂无历史报告</p>
          <p className="text-cd-text-tertiary text-xs">生成你的第一份日报吧！</p>
          <button
            onClick={() => handleGenerate(dayjs().format('YYYY-MM-DD'))}
            className="mt-4 inline-flex items-center gap-2 px-5 py-2 bg-cd-green hover:bg-cd-green-dark text-white rounded-lg text-sm font-medium transition-colors"
          >
            <Sparkles size={14} />
            生成今日日报
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-5 gap-5">
          {/* ─── 左侧列表 ────────────────────── */}
          <div className="col-span-2 space-y-2">
            {(reports || []).map((report) => (
              <button
                key={report.date}
                onClick={() => setSelectedReport(report)}
                className={`w-full flex items-center gap-3 p-3 rounded-xl text-left transition-colors border ${
                  selectedReport?.date === report.date
                    ? 'bg-cd-green-light border-cd-green'
                    : 'bg-cd-card border-cd-border hover:bg-cd-hover'
                }`}
              >
                <div className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${
                  selectedReport?.date === report.date
                    ? 'bg-cd-green text-white'
                    : 'bg-cd-bg-secondary text-cd-text-tertiary'
                }`}>
                  <FileText size={16} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-cd-text truncate">
                    {report.date}
                  </div>
                  <div className="text-[10px] text-cd-text-tertiary">
                    {report.template === 'standard' ? '标准模板' : report.template === 'deep' ? '深度洞察' : report.template === 'ai' ? 'AI智能' : report.template || '日报'}
                  </div>
                </div>
                <ChevronRight size={14} className="text-cd-text-tertiary shrink-0" />
              </button>
            ))}

            {/* 仅显示最近 14 天报告 */}
            <button disabled className="w-full text-xs text-cd-text-tertiary cursor-default py-2">
              仅显示最近14天报告
            </button>
          </div>

          {/* ─── 右侧预览 ────────────────────── */}
          <div className="col-span-3">
            {selectedReport?.content ? (
              <div className="card">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <Calendar size={14} className="text-cd-green" />
                    <span className="text-sm font-medium text-cd-text">
                      {selectedReport.date}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleCopy}
                      className="flex items-center gap-1 px-2.5 py-1 rounded-md text-xs bg-cd-bg-secondary hover:bg-cd-hover text-cd-text-secondary transition-colors border border-cd-border"
                    >
                      {copied ? <Check size={11} /> : <Copy size={11} />}
                      {copied ? '已复制' : '复制'}
                    </button>
                  </div>
                </div>
                <div className="prose prose-sm max-w-none prose-headings:text-cd-text prose-p:text-cd-text-secondary prose-strong:text-cd-text prose-li:text-cd-text-secondary prose-code:bg-cd-bg-secondary prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-cd-green prose-code:before:content-none prose-code:after:content-none prose-hr:border-cd-border">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    urlTransform={(url) => {
                      // 过滤 javascript: 等危险协议，防止 XSS
                      const trimmed = url.trim().toLowerCase()
                      if (trimmed.startsWith('javascript:') || trimmed.startsWith('data:') || trimmed.startsWith('vbscript:')) {
                        return ''
                      }
                      return url
                    }}
                  >{selectedReport.content}</ReactMarkdown>
                </div>
              </div>
            ) : (
              <div className="card text-center py-16 text-cd-text-tertiary">
                选择左侧报告查看详情
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

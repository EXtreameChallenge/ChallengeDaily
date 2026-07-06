import { useState } from 'react'
import {
  generateDailyReport,
  generateWeeklyReport,
  generateMonthlyReport,
  getDailyReportContent,
  getTodayStats,
  type TodayStats,
} from '../api/client'
import { useTimeout, useAsyncData } from '../components/shared'
import { useToast } from '../components/Toast'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { FileText, Calendar, Sparkles, Copy, Check, Download } from 'lucide-react'
import dayjs from 'dayjs'

type ReportType = 'daily' | 'weekly' | 'monthly'
type TemplateType = 'standard' | 'simple' | 'technical' | 'okr' | 'ai' | 'deep'

const REPORT_TYPES: { value: ReportType; label: string }[] = [
  { value: 'daily', label: '日报' },
  { value: 'weekly', label: '周报' },
  { value: 'monthly', label: '月报' },
]

const TEMPLATE_TYPES: { value: TemplateType; label: string; desc: string }[] = [
  { value: 'standard', label: '标准', desc: '完整工作概要 + 分类统计' },
  { value: 'simple', label: '简洁', desc: '精炼要点，一页搞定' },
  { value: 'technical', label: '技术', desc: '侧重代码/项目/技术细节' },
  { value: 'okr', label: 'OKR', desc: '对齐目标和关键结果' },
  { value: 'ai', label: 'AI 智能', desc: '调用文本模型生成自然语言日报' },
  { value: 'deep', label: '深度洞察', desc: '叙事日记+心理推测+反思' },
]

export default function Report() {
  const toast = useToast()
  const [reportType, setReportType] = useState<ReportType>('daily')
  const [template, setTemplate] = useState<TemplateType>('deep')
  const [generatedContent, setGeneratedContent] = useState<string>('')
  const [generating, setGenerating] = useState(false)
  const [copied, setCopied] = useState(false)
  const [selectedMonth, setSelectedMonth] = useState(dayjs().format('YYYY-MM'))

  // 安全 setTimeout — copied 状态自动消失
  useTimeout(() => setCopied(false), copied ? 2000 : null)

  // 加载已有报告内容和统计（fire-and-forget，不阻断页面）
  const { data: initialData } = useAsyncData<{ content: string; stats: TodayStats | null }>(
    async () => {
      const [reportRes, statsRes] = await Promise.allSettled([
        getDailyReportContent(),
        getTodayStats(),
      ])
      return {
        content: reportRes.status === 'fulfilled' && reportRes.value.content ? reportRes.value.content : '',
        stats: statsRes.status === 'fulfilled' ? statsRes.value : null,
      }
    },
    [],
  )
  // 优先显示用户生成的内容，否则显示初始加载的
  const content = generating ? '' : (generatedContent || initialData?.content || '')
  const stats = initialData?.stats || null

  const handleGenerate = async () => {
    setGenerating(true)
    setGeneratedContent('')
    try {
      let result
      if (reportType === 'daily') {
        result = await generateDailyReport(template)
      } else if (reportType === 'weekly') {
        result = await generateWeeklyReport()
      } else {
        result = await generateMonthlyReport(selectedMonth)
      }
      setGeneratedContent(result.content)
      toast.success(`${REPORT_TYPES.find(t => t.value === reportType)?.label || '报告'}生成成功`)
    } catch (err: any) {
      setGeneratedContent(`# 生成失败\n\n${err.message}`)
      toast.error('报告生成失败，请重试')
    } finally {
      setGenerating(false)
    }
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(content)
    setCopied(true)
    toast.success('已复制到剪贴板')
  }

  const handleDownload = () => {
    const typeLabel = REPORT_TYPES.find(t => t.value === reportType)?.label || '报告'
    const filename = `ChallengeDaily_${typeLabel}_${dayjs().format('YYYYMMDD')}.md`
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="animate-fade-in space-y-5">
      <h1 className="text-lg font-semibold text-cd-text">生成报告</h1>

      {/* ─── 类型与模板选择 ─────────────────── */}
      <div className="card space-y-4">
        {/* 报告类型 */}
        <div>
          <label className="text-xs text-cd-text-secondary mb-2 block">报告类型</label>
          <div className="flex gap-2">
            {REPORT_TYPES.map((t) => (
              <button
                key={t.value}
                onClick={() => setReportType(t.value)}
                className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm transition-colors ${
                  reportType === t.value
                    ? 'bg-cd-green text-white'
                    : 'bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover'
                }`}
              >
                <Calendar size={14} />
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {/* 月报月份选择 */}
        {reportType === 'monthly' && (
          <div>
            <label className="text-xs text-cd-text-secondary block mb-1">选择月份</label>
            <input
              type="month"
              value={selectedMonth}
              onChange={(e) => setSelectedMonth(e.target.value)}
              className="bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green transition-colors"
            />
          </div>
        )}

        {/* 模板类型（仅在日报时显示） */}
        {reportType === 'daily' && (
          <div>
            <label className="text-xs text-cd-text-secondary mb-2 block">报告模板</label>
            <div className="grid grid-cols-3 gap-2">
              {TEMPLATE_TYPES.map((t) => (
                <button
                  key={t.value}
                  onClick={() => setTemplate(t.value)}
                  className={`px-3 py-2.5 rounded-lg text-left transition-colors border ${
                    template === t.value
                      ? 'bg-cd-green-light border-cd-green text-cd-green'
                      : 'bg-cd-bg-secondary border-cd-border text-cd-text-secondary hover:bg-cd-hover'
                  }`}
                >
                  <div className="text-sm font-medium">{t.label}</div>
                  <div className="text-[10px] mt-0.5 opacity-70">{t.desc}</div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* 生成按钮 */}
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="flex items-center gap-2 px-6 py-2.5 bg-cd-green hover:bg-cd-green-dark text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Sparkles size={16} className={generating ? 'animate-spin' : ''} />
          {generating ? 'AI 生成中...' : '一键生成'}
        </button>
      </div>

      {/* ─── 报告内容 ────────────────────────── */}
      {content && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <FileText size={16} className="text-cd-green" />
              <span className="text-sm font-medium text-cd-text">
                {reportType === 'monthly'
                  ? `${selectedMonth} ${REPORT_TYPES.find((t) => t.value === reportType)?.label}`
                  : `${dayjs().format('YYYY年MM月DD日')} ${REPORT_TYPES.find((t) => t.value === reportType)?.label}`
                }
              </span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleDownload}
                className="flex items-center gap-1 px-3 py-1 rounded-md text-xs bg-cd-bg-secondary hover:bg-cd-hover text-cd-text-secondary transition-colors border border-cd-border"
              >
                <Download size={12} />
                下载
              </button>
              <button
                onClick={handleCopy}
                className="flex items-center gap-1 px-3 py-1 rounded-md text-xs bg-cd-bg-secondary hover:bg-cd-hover text-cd-text-secondary transition-colors border border-cd-border"
              >
                {copied ? <Check size={12} /> : <Copy size={12} />}
                {copied ? '已复制' : '复制'}
              </button>
            </div>
          </div>
          <div className="prose prose-sm max-w-none prose-headings:text-cd-text prose-p:text-cd-text-secondary prose-strong:text-cd-text prose-li:text-cd-text-secondary prose-code:bg-cd-bg-secondary prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-cd-green prose-code:before:content-none prose-code:after:content-none prose-hr:border-cd-border prose-table:text-sm prose-th:bg-cd-bg-secondary prose-th:text-cd-text prose-td:text-cd-text-secondary">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  )
}

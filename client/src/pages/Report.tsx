import { useState, useEffect, useCallback } from 'react'
import {
  generateDailyReport,
  generateWeeklyReport,
  generateMonthlyReport,
  getDailyReportContent,
  getTodayStats,
  getPomodoroSummary,
  getDailyCredibility,
  getCustomTemplates,
  saveCustomTemplate,
  deleteCustomTemplate,
  request,
  type TodayStats,
  type PomodoroSummary,
  type DailyCredibility,
  type CustomTemplate,
} from '../api/client'
import { useTimeout, useAsyncData } from '../components/shared'
import { useToast } from '../components/Toast'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { FileText, Calendar, Sparkles, Copy, Check, Download, Save, Trash2, BookOpen } from 'lucide-react'
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
  { value: 'deep', label: '深度洞察', desc: '13板块叙事日记+心理分析+项目追踪' },
]

export default function Report() {
  const toast = useToast()
  const [reportType, setReportType] = useState<ReportType>('daily')
  const [template, setTemplate] = useState<TemplateType>('deep')
  const [generatedContent, setGeneratedContent] = useState<string>('')
  const [generating, setGenerating] = useState(false)
  const [copied, setCopied] = useState(false)
  const [selectedMonth, setSelectedMonth] = useState(dayjs().format('YYYY-MM'))
  const [weeklyGoal, setWeeklyGoal] = useState<{ total: number; done: number; completion_rate: number } | null>(null)
  const [customTemplates, setCustomTemplates] = useState<CustomTemplate[]>([])
  const [showSaveModal, setShowSaveModal] = useState(false)
  const [templateName, setTemplateName] = useState('')

  // 周报模式时拉取目标对比
  useEffect(() => {
    if (reportType !== 'weekly') {
      setWeeklyGoal(null)
      return
    }
    let cancelled = false
    request(`/api/report/weekly-goal?date=${dayjs().format('YYYY-MM-DD')}`, undefined, 10000)
      .then((res: any) => {
        if (!cancelled && res && typeof res.total === 'number') {
          setWeeklyGoal(res)
        }
      })
      .catch(() => {
        if (!cancelled) setWeeklyGoal(null)
      })
    return () => { cancelled = true }
  }, [reportType])

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

  // 番茄统计与数据可信度（fire-and-forget，仅日报时展示）
  const { data: pomodoroStats } = useAsyncData<PomodoroSummary | null>(
    async () => {
      try {
        return await getPomodoroSummary()
      } catch {
        return null
      }
    },
    [],
  )
  const { data: credibility } = useAsyncData<DailyCredibility | null>(
    async () => {
      try {
        return await getDailyCredibility()
      } catch {
        return null
      }
    },
    [],
  )

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

  // ── 自定义模板：加载/保存/删除 ──
  const loadCustomTemplates = useCallback(async () => {
    try {
      const res = await getCustomTemplates()
      setCustomTemplates(res.templates || [])
    } catch { /* 静默失败 */ }
  }, [])

  useEffect(() => { loadCustomTemplates() }, [loadCustomTemplates])

  const handleSaveTemplate = async () => {
    const name = templateName.trim()
    if (!name || !content) {
      toast.error('模板名称和报告内容不能为空')
      return
    }
    try {
      const res = await saveCustomTemplate(name, content)
      setCustomTemplates(res.templates || [])
      setShowSaveModal(false)
      setTemplateName('')
      toast.success('模板已保存')
    } catch {
      toast.error('保存失败')
    }
  }

  const handleDeleteTemplate = async (id: number) => {
    try {
      const res = await deleteCustomTemplate(id)
      setCustomTemplates(res.templates || [])
      toast.success('已删除')
    } catch {
      toast.error('删除失败')
    }
  }

  const handleLoadTemplate = (tpl: CustomTemplate) => {
    setGeneratedContent(tpl.content)
    toast.success(`已加载模板：${tpl.name}`)
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
              <button
                onClick={() => setShowSaveModal(true)}
                disabled={!content}
                className="flex items-center gap-1 px-3 py-1 rounded-md text-xs bg-cd-bg-secondary hover:bg-cd-hover text-cd-text-secondary transition-colors border border-cd-border disabled:opacity-40"
              >
                <Save size={12} />
                存为模板
              </button>
            </div>
          </div>
          <div className="prose prose-sm max-w-none 
            prose-headings:text-cd-text prose-headings:font-semibold 
            prose-h1:text-2xl prose-h1:mb-6 prose-h1:border-b prose-h1:border-cd-border prose-h1:pb-3
            prose-h2:text-lg prose-h2:mt-8 prose-h2:mb-4 prose-h2:text-cd-green
            prose-h3:text-base prose-h3:mt-6 prose-h3:mb-3 prose-h3:text-cd-text
            prose-p:text-cd-text-secondary prose-p:leading-relaxed prose-p:my-3
            prose-strong:text-cd-text prose-strong:font-semibold
            prose-li:text-cd-text-secondary prose-li:my-1
            prose-ul:my-3 prose-ol:my-3
            prose-blockquote:border-l-4 prose-blockquote:border-cd-green prose-blockquote:pl-4 prose-blockquote:italic prose-blockquote:text-cd-text-secondary prose-blockquote:bg-cd-bg-secondary/50 prose-blockquote:py-2 prose-blockquote:pr-4 prose-blockquote:rounded-r-lg
            prose-code:bg-cd-bg-secondary prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-cd-green prose-code:text-xs prose-code:before:content-none prose-code:after:content-none
            prose-hr:border-cd-border prose-hr:my-6
            prose-table:text-sm prose-table:border-collapse prose-th:bg-cd-bg-secondary prose-th:text-cd-text prose-th:font-semibold prose-th:p-2 prose-th:border prose-th:border-cd-border prose-td:text-cd-text-secondary prose-td:p-2 prose-td:border prose-td:border-cd-border prose-tr:nth-child(even):bg-cd-bg-secondary/30
            prose-img:rounded-lg prose-img:shadow-md
            prose-a:text-cd-green prose-a:no-underline hover:prose-a:underline
          ">
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
              // sanitize：将危险标签映射为 null，防止 iframe/form/style/object/embed 注入
              components={{
                iframe: () => null,
                form: () => null,
                style: () => null,
                object: () => null,
                embed: () => null,
              }}
            >{content}</ReactMarkdown>
          </div>
        </div>
      )}

      {/* ─── 周目标完成对比（仅周报时展示） ────────────── */}
      {reportType === 'weekly' && weeklyGoal && weeklyGoal.total > 0 && (
        <div className="card p-4">
          <h3 className="text-sm font-medium text-cd-text mb-3">🎯 周目标完成情况</h3>
          <div className="grid grid-cols-3 gap-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-cd-purple">{weeklyGoal.total}</div>
              <div className="text-xs text-cd-text-tertiary">本周待办总数</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-cd-green">{weeklyGoal.done}</div>
              <div className="text-xs text-cd-text-tertiary">已完成</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-cd-green">{weeklyGoal.completion_rate}%</div>
              <div className="text-xs text-cd-text-tertiary">完成率</div>
            </div>
          </div>
          {/* 进度条 */}
          <div className="mt-3 h-2 rounded-full overflow-hidden" style={{ background: 'var(--cd-bg-tertiary)' }}>
            <div
              className="h-full transition-all"
              style={{ width: `${Math.min(100, weeklyGoal.completion_rate)}%`, background: 'var(--cd-green)' }}
            />
          </div>
        </div>
      )}

      {/* ─── 番茄统计卡片（仅日报时展示） ────────────── */}
      {reportType === 'daily' && pomodoroStats && pomodoroStats.total > 0 && (
        <div className="card p-4">
          <h3 className="text-sm font-medium text-cd-text mb-3">🍅 番茄统计</h3>
          <div className="grid grid-cols-4 gap-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-cd-green">{pomodoroStats.completed}</div>
              <div className="text-xs text-cd-text-tertiary">完成番茄</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-cd-blue">{pomodoroStats.total_min}</div>
              <div className="text-xs text-cd-text-tertiary">专注分钟</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-cd-orange">{pomodoroStats.distractions}</div>
              <div className="text-xs text-cd-text-tertiary">分心次数</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-cd-purple">{pomodoroStats.total}</div>
              <div className="text-xs text-cd-text-tertiary">总番茄数</div>
            </div>
          </div>
        </div>
      )}

      {/* ─── 数据可信度卡片（仅日报时展示） ────────────── */}
      {reportType === 'daily' && credibility && (
        <div className="card p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium text-cd-text">📊 数据可信度证明</h3>
            <span className={`px-2 py-0.5 rounded text-xs ${
              credibility.level === 'high' ? 'bg-cd-green-light text-cd-green' :
              credibility.level === 'medium' ? 'bg-cd-gold/20 text-cd-gold' :
              'bg-cd-red-light text-cd-red'
            }`}>
              {credibility.credibility_score}%
            </span>
          </div>
          <div className="grid grid-cols-3 gap-4 text-xs">
            <div>
              <div className="text-cd-text-tertiary">采集覆盖率</div>
              <div className="text-cd-text font-medium">{credibility.coverage_rate}%</div>
            </div>
            <div>
              <div className="text-cd-text-tertiary">漏采时段</div>
              <div className="text-cd-text font-medium">{credibility.missing_periods?.length || 0} 段</div>
            </div>
            <div>
              <div className="text-cd-text-tertiary">采样偏差</div>
              <div className="text-cd-text font-medium">±{credibility.sampling_deviation}s</div>
            </div>
          </div>
          <p className="mt-3 text-xs text-cd-text-tertiary">
            ℹ️ 本日报数据基于自动截屏采集，可信度由 Windows 事件日志对比校准
          </p>
        </div>
      )}

      {/* ─── 我的模板列表 ────────────── */}
      {customTemplates.length > 0 && (
        <div className="card p-4">
          <h3 className="text-sm font-medium text-cd-text mb-3 flex items-center gap-2">
            <BookOpen size={14} />
            我的模板
          </h3>
          <div className="space-y-2">
            {customTemplates.map((tpl) => (
              <div key={tpl.id} className="flex items-center justify-between bg-cd-bg-secondary rounded-lg px-3 py-2 border border-cd-border">
                <button onClick={() => handleLoadTemplate(tpl)}
                  className="flex-1 text-left text-sm text-cd-text hover:text-cd-green transition-colors truncate">
                  {tpl.name}
                </button>
                <button onClick={() => handleDeleteTemplate(tpl.id)}
                  className="ml-2 p-1 text-cd-text-tertiary hover:text-cd-red transition-colors"
                  title="删除模板">
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ─── 保存模板弹窗 ────────────── */}
      {showSaveModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setShowSaveModal(false)}>
          <div className="bg-cd-card p-6 rounded-lg border border-cd-border max-w-md w-full mx-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-medium text-cd-text mb-4">保存为我的模板</h3>
            <input
              type="text"
              value={templateName}
              onChange={(e) => setTemplateName(e.target.value)}
              placeholder="模板名称（如：周报-技术向）"
              maxLength={50}
              autoFocus
              onKeyDown={(e) => { if (e.key === 'Enter') handleSaveTemplate() }}
              className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cd-green transition-colors mb-4"
            />
            <div className="flex gap-3 justify-end">
              <button onClick={() => { setShowSaveModal(false); setTemplateName('') }}
                className="px-4 py-2 text-sm text-cd-text-tertiary hover:text-cd-text">取消</button>
              <button onClick={handleSaveTemplate}
                className="px-4 py-2 text-sm bg-cd-green text-white rounded hover:opacity-90">保存</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

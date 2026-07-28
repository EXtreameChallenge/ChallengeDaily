import { useState, useEffect } from 'react'
import { request } from '../api/client'
import { FileText, Minus, Code2, Target, Sparkles, Brain } from 'lucide-react'

interface ReportTemplateSelectorProps {
  onSelect: (template: string) => void
  selected: string
}

interface TemplateItem {
  value: string
  label: string
  desc: string
  icon: React.ReactNode
}

const HARDCODED_TEMPLATES: TemplateItem[] = [
  {
    value: 'standard',
    label: '标准日报',
    desc: '全面记录工作内容，包含分类统计、时间分布和关键成果',
    icon: <FileText size={20} />,
  },
  {
    value: 'simple',
    label: '简洁日报',
    desc: '极简风格，只保留核心信息，三分钟写完',
    icon: <Minus size={20} />,
  },
  {
    value: 'technical',
    label: '技术日报',
    desc: '面向开发者，突出代码贡献、技术决策和架构变更',
    icon: <Code2 size={20} />,
  },
  {
    value: 'okr',
    label: 'OKR日报',
    desc: '围绕目标和关键结果，追踪进展和完成度',
    icon: <Target size={20} />,
  },
  {
    value: 'ai',
    label: 'AI智能日报',
    desc: 'AI 全自动分析，深度理解工作模式，生成洞察型日报',
    icon: <Sparkles size={20} />,
  },
  {
    value: 'deep',
    label: '深度日报',
    desc: '深度工作分析，结合学术框架量化评估生产力',
    icon: <Brain size={20} />,
  },
]

export default function ReportTemplateSelector({ onSelect, selected }: ReportTemplateSelectorProps) {
  const [templates, setTemplates] = useState<TemplateItem[]>(HARDCODED_TEMPLATES)

  useEffect(() => {
    request('/api/report/templates')
      .then((data: { templates?: { value: string; label: string }[] }) => {
        if (data?.templates?.length) {
          setTemplates(prev =>
            prev.map(t => {
              const remote = data.templates.find(r => r.value === t.value)
              return remote ? { ...t, label: remote.label } : t
            })
          )
        }
      })
      .catch(() => {})
  }, [])

  return (
    <div className="grid grid-cols-3 gap-3">
      {templates.map(t => {
        const isActive = selected === t.value
        return (
          <button
            key={t.value}
            onClick={() => onSelect(t.value)}
            className={`group flex flex-col gap-2 rounded-xl border-2 p-4 text-left transition-all ${
              isActive
                ? 'border-cd-green bg-cd-green/5 shadow-sm shadow-cd-green/10'
                : 'border-cd-border bg-cd-bg-secondary hover:border-cd-text-tertiary hover:bg-cd-hover'
            }`}
          >
            <div className="flex items-center gap-2">
              <span className={`shrink-0 ${isActive ? 'text-cd-green' : 'text-cd-text-tertiary'}`}>
                {t.icon}
              </span>
              <span className={`text-sm font-semibold truncate ${isActive ? 'text-cd-green' : 'text-cd-text'}`}>
                {t.label}
              </span>
            </div>
            <span className="text-xs leading-relaxed text-cd-text-tertiary line-clamp-2">
              {t.desc}
            </span>
            {isActive && (
              <span className="mt-auto flex items-center gap-1 text-[10px] font-medium text-cd-green">
                ✓ 已选择
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

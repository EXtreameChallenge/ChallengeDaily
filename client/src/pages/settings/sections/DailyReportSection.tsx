import { FileText } from 'lucide-react'

interface DailyReportSectionProps {
  highlighted: boolean
  customInstr: string
  setCustomInstr: (v: string) => void
  autoDailyReport: boolean
  setAutoDailyReport: (v: boolean) => void
  autoDailyReportHour: number
  setAutoDailyReportHour: (v: number) => void
}

export function DailyReportSection({ highlighted, customInstr, setCustomInstr, autoDailyReport, setAutoDailyReport, autoDailyReportHour, setAutoDailyReportHour }: DailyReportSectionProps) {
  return (
      <section
        id="settings-section-日报"
        className={`card space-y-4 ${highlighted ? 'ring-2 ring-cd-green' : ''}`}
      >
        <div className="flex items-center gap-2">
          <FileText size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">日报自定义指令</h2>
        </div>

        <div>
          <label className="text-xs text-cd-text-secondary block mb-1">
            追加到日报生成指令中的自定义要求（可选）
          </label>
          <textarea
            value={customInstr}
            onChange={(e) => setCustomInstr(e.target.value)}
            rows={3}
            placeholder="例如：重点关注开发相关活动，会议和沟通简要概括即可"
            className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-2xl px-3 py-2 text-sm focus:outline-none focus:border-cd-green transition-colors resize-none"
          />
        </div>
        <div className="text-xs text-cd-text-tertiary">
          该指令会在生成日报时附加到 AI 提示词中，影响报告的重点和风格
        </div>

        {/* 每日定时生成日报 */}
        <div className="flex items-center justify-between mt-4 pt-4 border-t border-cd-border">
          <div>
            <div className="text-xs text-cd-text-secondary">每日定时生成日报</div>
            <div className="text-[10px] text-cd-text-tertiary mt-0.5">在指定时间自动基于当日工作记录生成日报</div>
          </div>
          <div className="flex items-center gap-3">
            {autoDailyReport && (
              <select
                value={autoDailyReportHour}
                onChange={(e) => setAutoDailyReportHour(parseInt(e.target.value))}
                className="bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg px-2 py-1 text-xs"
              >
                {Array.from({ length: 24 }, (_, i) => (
                  <option key={i} value={i}>{String(i).padStart(2, '0')}:00</option>
                ))}
              </select>
            )}
            <button
              onClick={() => setAutoDailyReport(!autoDailyReport)}
              className={`relative w-10 h-5 rounded-full transition-colors ${
                autoDailyReport ? 'bg-cd-green' : 'bg-cd-bg-tertiary'
              }`}
            >
              <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                autoDailyReport ? 'left-5.5' : 'left-0.5'
              }`} />
            </button>
          </div>
        </div>
      </section>
  )
}



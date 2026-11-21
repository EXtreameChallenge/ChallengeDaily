import { ListFilter } from 'lucide-react'

interface ExcludeAppsSectionProps {
  excludeApps: string
  setExcludeApps: (v: string) => void
}

export function ExcludeAppsSection({ excludeApps, setExcludeApps }: ExcludeAppsSectionProps) {
  return (
      <section className="card space-y-4">
        <div className="flex items-center gap-2">
          <ListFilter size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">排除应用</h2>
        </div>

        <div>
          <label className="text-xs text-cd-text-secondary block mb-1">
            不记录的应用（每行一个，或逗号分隔）
          </label>
          <textarea
            value={excludeApps}
            onChange={(e) => setExcludeApps(e.target.value)}
            rows={5}
            placeholder="WeChat&#10;飞书&#10;DingTalk&#10;outlook"
            className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-2xl px-3 py-2 text-sm focus:outline-none focus:border-cd-green transition-colors resize-none font-mono"
          />
        </div>

        <div className="text-xs text-cd-text-tertiary space-y-1">
          <p>• 匹配逻辑：应用名或窗口标题包含上述关键词时不截图、不记录</p>
          <p>• 默认不排除任何应用（全量采集）；可按需填写，改后即时生效</p>
          <p>• 修改后即时生效，无需重启</p>
        </div>
      </section>
  )
}



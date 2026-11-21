import type { CollectorStatus } from '../../../api/client'
import { Server } from 'lucide-react'

interface CollectSectionProps {
  highlighted: boolean
  interval: number
  setInterval_: (v: number) => void
  workStart: number
  setWorkStart: (v: number) => void
  workEnd: number
  setWorkEnd: (v: number) => void
  status: CollectorStatus | null
}

export function CollectSection({ highlighted, interval, setInterval_, workStart, setWorkStart, workEnd, setWorkEnd, status }: CollectSectionProps) {
  return (
      <section
        id="settings-section-采集"
        className={`card space-y-4 ${highlighted ? 'ring-2 ring-cd-green' : ''}`}
      >
        <div className="flex items-center gap-2">
          <Server size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">采集设置</h2>
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-xs text-cd-text-secondary block mb-1">截图间隔（秒）</label>
            <div className="flex items-center gap-3">
              <input
                type="range"
                value={interval}
                onChange={(e) => setInterval_(Number(e.target.value))}
                min={15}
                max={300}
                step={5}
                className="flex-1 accent-cd-green"
              />
              <span className="text-sm text-cd-text w-14 text-right">{interval}s</span>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-cd-text-secondary block mb-1">工作开始时间</label>
              <input
                type="number"
                value={workStart}
                onChange={(e) => setWorkStart(Number(e.target.value))}
                min={0}
                max={23}
                className={`w-full bg-cd-bg-secondary text-cd-text border rounded-2xl px-3 py-1.5 text-sm focus:outline-none transition-colors ${
                  workStart >= workEnd ? 'border-cd-red focus:border-cd-red' : 'border-cd-border focus:border-cd-green'
                }`}
              />
            </div>
            <div>
              <label className="text-xs text-cd-text-secondary block mb-1">工作结束时间</label>
              <input
                type="number"
                value={workEnd}
                onChange={(e) => setWorkEnd(Number(e.target.value))}
                min={0}
                max={23}
                className={`w-full bg-cd-bg-secondary text-cd-text border rounded-2xl px-3 py-1.5 text-sm focus:outline-none transition-colors ${
                  workEnd <= workStart ? 'border-cd-red focus:border-cd-red' : 'border-cd-border focus:border-cd-green'
                }`}
              />
            </div>
          </div>
          {workStart >= workEnd && (
            <p className="text-xs text-cd-red">开始时间必须早于结束时间</p>
          )}

          <div className="flex items-center justify-between">
            <span className="text-sm text-cd-text">采集器状态</span>
            <span className={`text-xs px-2.5 py-0.5 rounded-full ${
              status === null
                ? 'bg-cd-bg-secondary text-cd-text-tertiary'
                : status?.running
                  ? 'bg-cd-green-light text-cd-green'
                  : 'bg-cd-red-light text-cd-red'
            }`}>
              {status === null ? '连接中...' : status?.running ? '运行中' : '已暂停'}
            </span>
          </div>
        </div>
      </section>
  )
}



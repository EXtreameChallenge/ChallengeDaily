import CalendarSubscriptionManager from '../../../components/CalendarSubscriptionManager'
import { Calendar } from 'lucide-react'

interface CalendarSectionProps {
  highlighted: boolean
}

export function CalendarSection({ highlighted }: CalendarSectionProps) {
  return (
      <section
        id="settings-section-日历"
        className={`card space-y-4 ${highlighted ? 'ring-2 ring-cd-green' : ''}`}
      >
        <div className="flex items-center gap-2">
          <Calendar size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">外部日历集成</h2>
        </div>
        <div className="text-xs text-cd-text-tertiary">
          订阅 ICS 日历源（Google Calendar / Outlook / 飞书等），自动识别会议时段，避免在会议期间触发专注提醒。
        </div>
        <CalendarSubscriptionManager />
      </section>
  )
}



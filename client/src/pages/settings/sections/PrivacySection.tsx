import { AppLockSettings } from '../../../components/AppLock'
import { Shield } from 'lucide-react'

interface PrivacySectionProps {
  highlighted: boolean
}

export function PrivacySection({ highlighted }: PrivacySectionProps) {
  return (
      <section
        id="settings-section-隐私"
        className={`card space-y-4 ${highlighted ? 'ring-2 ring-cd-green' : ''}`}
      >
        <div className="flex items-center gap-2">
          <Shield size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">隐私保护</h2>
        </div>

        {/* 应用级隐私锁 */}
        <AppLockSettings />

        <div className="text-xs text-cd-text-tertiary space-y-1">
          <p>• 截图在 AI 分析完成后会自动删除，不会保存到磁盘</p>
          <p>• 除 AI 分析当次上传截图外（分析后即删），其余数据仅保存于本地 SQLite</p>
          <p>• 默认不做内容脱敏；保守模式可在设置文件中开启 privacy_redact / privacy_block_upload</p>
          <p>• 排除列表默认为空；填写的应用不会被截图和记录</p>
          <p>• API Key 使用 Windows 系统加密存储 (DPAPI)，不以明文保存</p>
        </div>
      </section>
  )
}



import { useToast } from '../../../components/Toast'
import { downloadBackup } from '../../../api/client'
import { Database, Download, Upload, Loader2 } from 'lucide-react'

interface BackupSectionProps {
  highlighted: boolean
  backupInfo: { db_size_mb: number; activities_count: number; reports_count: number } | null
  restoring: boolean
  handleRestore: (e: React.ChangeEvent<HTMLInputElement>) => void
  toast: ReturnType<typeof useToast>
}

export function BackupSection({ highlighted, backupInfo, restoring, handleRestore, toast }: BackupSectionProps) {
  return (
      <section
        id="settings-section-备份"
        className={`card space-y-4 ${highlighted ? 'ring-2 ring-cd-green' : ''}`}
      >
        <div className="flex items-center gap-2">
          <Database size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">数据备份与恢复</h2>
        </div>

        {backupInfo && (
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-cd-bg-secondary rounded-2xl p-3 text-center">
              <div className="text-sm font-bold text-cd-green">{backupInfo.db_size_mb} MB</div>
              <div className="text-[10px] text-cd-text-tertiary mt-0.5">数据库大小</div>
            </div>
            <div className="bg-cd-bg-secondary rounded-2xl p-3 text-center">
              <div className="text-sm font-bold text-cd-green">{backupInfo.activities_count}</div>
              <div className="text-[10px] text-cd-text-tertiary mt-0.5">活动记录</div>
            </div>
            <div className="bg-cd-bg-secondary rounded-2xl p-3 text-center">
              <div className="text-sm font-bold text-cd-green">{backupInfo.reports_count}</div>
              <div className="text-[10px] text-cd-text-tertiary mt-0.5">历史报告</div>
            </div>
          </div>
        )}

        <div className="flex gap-3">
          <a
            onClick={async (e) => { e.preventDefault(); try { await downloadBackup() } catch (err) { toast.error('备份下载失败') } }}
            href="#"
            download
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-2xl text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border cursor-pointer"
          >
            <Download size={12} />
            创建备份
          </a>
          <label className="flex items-center gap-1.5 px-4 py-1.5 rounded-2xl text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border cursor-pointer disabled:opacity-50">
            {restoring ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
            {restoring ? '恢复中...' : '从备份恢复'}
            <input
              type="file"
              accept=".zip"
              onChange={handleRestore}
              className="hidden"
              disabled={restoring}
            />
          </label>
        </div>

        <div className="text-xs text-cd-text-tertiary space-y-1">
          <p>• 备份包含数据库、设置和 Webhook 配置，导出为 ZIP 文件</p>
          <p>• 恢复前会自动备份当前数据，操作后需重启应用生效</p>
        </div>
      </section>
  )
}



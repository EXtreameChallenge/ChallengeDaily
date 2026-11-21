import { Info, CheckCircle, Loader2, RefreshCw } from 'lucide-react'

interface AboutSectionProps {
  highlighted: boolean
  appVersion: string
  updateStatus: 'idle' | 'available' | 'downloading' | 'downloaded' | 'up-to-date'
  updateChecking: boolean
  handleCheckUpdate: () => void
}

export function AboutSection({ highlighted, appVersion, updateStatus, updateChecking, handleCheckUpdate }: AboutSectionProps) {
  return (
      <section
        id="settings-section-关于"
        className={`card space-y-4 ${highlighted ? 'ring-2 ring-cd-green' : ''}`}
      >
        <div className="flex items-center gap-2">
          <Info size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">关于与更新</h2>
        </div>

        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-bold text-cd-text font-brand">ChallengeDaily</p>
            <p className="text-xs text-cd-text-tertiary">
              版本 {appVersion || '—'}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {updateStatus === 'downloaded' ? (
              <button
                onClick={() => window.electronAPI?.installUpdate()}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-2xl text-xs font-medium bg-cd-green text-white hover:opacity-90 transition-opacity"
              >
                重启安装更新
              </button>
            ) : updateStatus === 'downloading' ? (
              <span className="text-xs text-cd-text-secondary">下载中...</span>
            ) : updateStatus === 'up-to-date' ? (
              <span className="flex items-center gap-1 text-xs text-cd-green">
                <CheckCircle size={12} />
                已是最新版本
              </span>
            ) : (
              <button
                onClick={handleCheckUpdate}
                disabled={updateChecking}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-2xl text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border disabled:opacity-40"
              >
                {updateChecking ? (
                  <><Loader2 size={12} className="animate-spin" /> 检查中...</>
                ) : (
                  <><RefreshCw size={12} /> 检查更新</>
                )}
              </button>
            )}
          </div>
        </div>

        <div className="text-xs text-cd-text-tertiary space-y-1">
          <p>• 本软件为免费开源软件，数据完全本地存储</p>
          <p>• 如需帮助或反馈问题，请访问项目主页</p>
        </div>
      </section>
  )
}



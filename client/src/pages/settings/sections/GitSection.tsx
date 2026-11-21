import GitRepoManager from '../../../components/GitRepoManager'
import { GitBranch } from 'lucide-react'

interface GitSectionProps {
  highlighted: boolean
}

export function GitSection({ highlighted }: GitSectionProps) {
  return (
      <section
        id="settings-section-Git"
        className={`card space-y-4 ${highlighted ? 'ring-2 ring-cd-green' : ''}`}
      >
        <div className="flex items-center gap-2">
          <GitBranch size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">Git 仓库集成</h2>
        </div>
        <div className="text-xs text-cd-text-tertiary">
          添加本地 git 仓库路径，日报将自动聚合提交记录与代码增删行数，生成开发者专属代码产出统计。
        </div>
        <GitRepoManager />
      </section>
  )
}



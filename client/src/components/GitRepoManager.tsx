/**
 * P19-2: Git 仓库管理 UI
 * 添加/移除本地 git 仓库，查看今日代码产出统计
 */
import { useState, useEffect, useCallback } from 'react'
import {
  listGitRepositories, addGitRepository, removeGitRepository, getGitCodeReport,
  type GitRepository, type GitCodeReport,
} from '../api/client'
import { useToast } from './Toast'
import { GitBranch, Plus, Trash2, FolderPlus, Loader2, FileCode, TrendingUp } from 'lucide-react'

export default function GitRepoManager() {
  const toast = useToast()
  const [repos, setRepos] = useState<GitRepository[]>([])
  const [report, setReport] = useState<GitCodeReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [newPath, setNewPath] = useState('')
  const [newName, setNewName] = useState('')

  const refresh = useCallback(async () => {
    try {
      const [reposRes, reportRes] = await Promise.all([
        listGitRepositories(),
        getGitCodeReport().catch(() => null),
      ])
      setRepos(reposRes.repositories || [])
      if (reportRes) setReport(reportRes)
    } catch (err: any) {
      console.warn('Git 数据加载失败:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const handleAdd = async () => {
    if (!newPath.trim()) {
      toast.warning('请填写仓库路径')
      return
    }
    try {
      await addGitRepository({ path: newPath, name: newName || undefined })
      toast.success('Git 仓库已添加')
      setShowAdd(false)
      setNewPath('')
      setNewName('')
      refresh()
    } catch (err: any) {
      toast.error(err.message || '添加失败')
    }
  }

  const handleRemove = async (path: string) => {
    if (!confirm('确定要移除此仓库吗？')) return
    try {
      await removeGitRepository(path)
      toast.success('已移除')
      refresh()
    } catch (err: any) {
      toast.error(err.message || '移除失败')
    }
  }

  const handleSelectFolder = async () => {
    // 通过 Electron IPC 选择文件夹
    const path = await (window as any).electronAPI?.selectFolder?.()
    if (path) setNewPath(path)
  }

  return (
    <div className="space-y-3">
      {/* 今日代码产出概览 */}
      {report && report.total_commits > 0 && (
        <div className="p-3 bg-cd-bg-secondary border border-cd-border rounded-lg space-y-2">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-cd-text">
            <TrendingUp size={12} className="text-cd-green" />
            今日代码产出
          </div>
          <div className="grid grid-cols-4 gap-2 text-xs">
            <div className="text-center">
              <div className="text-cd-green font-bold text-sm">{report.total_commits}</div>
              <div className="text-cd-text-tertiary">提交</div>
            </div>
            <div className="text-center">
              <div className="text-cd-green font-bold text-sm">{report.total_files_changed}</div>
              <div className="text-cd-text-tertiary">文件</div>
            </div>
            <div className="text-center">
              <div className="text-cd-green font-bold text-sm">+{report.total_insertions}</div>
              <div className="text-cd-text-tertiary">新增</div>
            </div>
            <div className="text-center">
              <div className="text-cd-red font-bold text-sm">-{report.total_deletions}</div>
              <div className="text-cd-text-tertiary">删除</div>
            </div>
          </div>
          {/* 各仓库明细 */}
          {report.repositories.filter(r => r.commit_count > 0).map((r, i) => (
            <div key={i} className="pt-2 border-t border-cd-border">
              <div className="flex items-center gap-1 text-xs text-cd-text">
                <FileCode size={11} className="text-cd-text-tertiary" />
                <span className="font-medium">{r.name}</span>
                <span className="text-cd-text-tertiary ml-auto">
                  {r.commit_count} 次提交 · +{r.insertions}/-{r.deletions}
                </span>
              </div>
              {r.subjects.length > 0 && (
                <div className="mt-1 space-y-0.5">
                  {r.subjects.slice(0, 3).map((s, j) => (
                    <div key={j} className="text-[10px] text-cd-text-tertiary truncate pl-4">
                      · {s}
                    </div>
                  ))}
                  {r.subjects.length > 3 && (
                    <div className="text-[10px] text-cd-text-tertiary pl-4">
                      还有 {r.subjects.length - 3} 条...
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* 仓库列表 */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs text-cd-text-secondary">Git 仓库监控</span>
          <button
            onClick={() => setShowAdd(!showAdd)}
            className="text-xs text-cd-green hover:opacity-80 flex items-center gap-1"
          >
            <Plus size={11} /> 添加
          </button>
        </div>

        {showAdd && (
          <div className="p-3 bg-cd-bg-secondary border border-cd-border rounded-lg space-y-2">
            <div className="flex gap-1">
              <input
                type="text" placeholder="仓库路径（如 D:\Project\MyRepo）" value={newPath}
                onChange={(e) => setNewPath(e.target.value)}
                className="flex-1 bg-cd-bg text-cd-text border border-cd-border rounded px-2 py-1 text-xs"
              />
              <button onClick={handleSelectFolder}
                className="px-2 py-1 bg-cd-bg border border-cd-border rounded text-cd-text-secondary hover:bg-cd-hover text-xs"
                title="选择文件夹">
                <FolderPlus size={12} />
              </button>
            </div>
            <input
              type="text" placeholder="显示名称（可选，默认为文件夹名）" value={newName}
              onChange={(e) => setNewName(e.target.value)}
              className="w-full bg-cd-bg text-cd-text border border-cd-border rounded px-2 py-1 text-xs"
            />
            <div className="flex gap-1.5">
              <button onClick={handleAdd}
                className="ml-auto px-3 py-1 bg-cd-green text-white rounded text-xs hover:opacity-90">
                添加
              </button>
              <button onClick={() => setShowAdd(false)}
                className="px-2 py-1 text-cd-text-tertiary hover:text-cd-text text-xs">
                取消
              </button>
            </div>
          </div>
        )}

        {loading ? (
          <div className="text-xs text-cd-text-tertiary">加载中...</div>
        ) : repos.length === 0 ? (
          <div className="text-xs text-cd-text-tertiary">
            暂无监控仓库。添加本地 git 仓库路径后，日报将自动包含代码产出统计。
          </div>
        ) : (
          repos.map((r) => (
            <div key={r.path} className="flex items-center gap-2 p-2 bg-cd-bg-secondary rounded text-xs">
              <GitBranch size={12} className={
                r.status === 'ok' ? 'text-cd-green' :
                r.status === 'missing' ? 'text-cd-red' : 'text-cd-text-tertiary'
              } />
              <div className="flex-1 min-w-0">
                <div className="text-cd-text truncate">{r.name}</div>
                <div className="text-cd-text-tertiary truncate">{r.path}</div>
                {r.status === 'missing' && (
                  <div className="text-cd-red">路径不存在</div>
                )}
                {r.status === 'not_a_repo' && (
                  <div className="text-cd-text-tertiary">不是 git 仓库</div>
                )}
              </div>
              <button onClick={() => handleRemove(r.path)}
                className="text-cd-text-tertiary hover:text-cd-red flex-shrink-0">
                <Trash2 size={12} />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

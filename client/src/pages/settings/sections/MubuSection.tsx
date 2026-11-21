import dayjs from 'dayjs'
import type { MemoryStatus } from '../../../api/client'
import type { MubuDoc, MubuStatus, MubuStatusInfo } from '../mubu'
import { MUBU_STATUS_META } from '../mubu'
import { Cloud, XCircle, Loader2, RefreshCw, Search, FileUp, Brain } from 'lucide-react'

interface MubuSectionProps {
  highlighted: boolean
  mubuStatus: MubuStatus
  mubuInfo: MubuStatusInfo | null
  mubuLogging: boolean
  mubuSyncing: boolean
  mubuSearchQuery: string
  mubuSearching: boolean
  mubuSearchResults: MubuDoc[]
  handleMubuLogin: () => void
  handleMubuSync: () => void
  handleMubuSearch: (q: string) => void
  opmlUploading: boolean
  opmlFileInputRef: React.Ref<HTMLInputElement>
  handleOpmlImport: (e: React.ChangeEvent<HTMLInputElement>) => void
  memoryStatus: MemoryStatus | null
}

export function MubuSection({ highlighted, mubuStatus, mubuInfo, mubuLogging, mubuSyncing, mubuSearchQuery, mubuSearching, mubuSearchResults, handleMubuLogin, handleMubuSync, handleMubuSearch, opmlUploading, opmlFileInputRef, handleOpmlImport, memoryStatus }: MubuSectionProps) {
  return (
      <section
        id="settings-section-幕布"
        className={`card space-y-4 ${highlighted ? 'ring-2 ring-cd-green' : ''}`}
      >
        <div className="flex items-center gap-2">
          <Cloud size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">幕布文档接入</h2>
        </div>
        <div className="text-xs text-cd-text-tertiary">
          登录幕布账号后，可将文档同步至本地，便于日报与活动关联引用。
        </div>

        {/* 同步状态 + 文档统计 */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-xs text-cd-text-secondary">同步状态</span>
            <span className={`text-xs px-2.5 py-0.5 rounded-full ${MUBU_STATUS_META[mubuStatus].className}`}>
              {MUBU_STATUS_META[mubuStatus].label}
            </span>
          </div>
          <div className="text-xs text-cd-text-tertiary">
            {mubuInfo ? (
              <>
                {mubuInfo.doc_count} 篇文档
                {mubuInfo.last_sync && (
                  <> · 最近同步 {dayjs(mubuInfo.last_sync).format('MM-DD HH:mm')}</>
                )}
              </>
            ) : '—'}
          </div>
        </div>

        {/* Cookie 失效引导 */}
        {mubuStatus === 'cookie_invalid' && (
          <div className="rounded-xl border border-cd-red/30 bg-cd-red-light px-4 py-3 space-y-2">
            <div className="flex items-center gap-2 text-xs font-medium text-cd-red">
              <XCircle size={14} />
              幕布 Cookie 已失效，同步已暂停
            </div>
            <div className="text-[11px] text-cd-text-secondary">
              请点击「重新登录幕布」完成授权，登录成功后状态会自动恢复为「已同步」。
              {mubuInfo?.message ? `（${mubuInfo.message}）` : ''}
            </div>
            <button
              onClick={handleMubuLogin}
              disabled={mubuLogging}
              className="px-3 py-1.5 rounded-xl text-xs font-medium bg-cd-red text-white hover:opacity-90 disabled:opacity-40"
            >
              {mubuLogging ? '登录中...' : '立即重连 →'}
            </button>
          </div>
        )}

        {/* 操作按钮 */}
        <div className="flex flex-wrap gap-3">
          <button
            onClick={handleMubuLogin}
            disabled={mubuLogging}
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-2xl text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border disabled:opacity-40"
          >
            {mubuLogging ? <Loader2 size={12} className="animate-spin" /> : <Cloud size={12} />}
            {mubuLogging ? '登录中...' : (mubuStatus === 'cookie_invalid' ? '重新登录幕布' : '登录幕布')}
          </button>
          <button
            onClick={handleMubuSync}
            disabled={mubuSyncing || mubuStatus === 'cookie_invalid'}
            title={mubuStatus === 'cookie_invalid' ? 'Cookie 失效，请先重新登录' : undefined}
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-2xl text-xs font-medium bg-cd-green text-white hover:opacity-90 transition-opacity disabled:opacity-40"
          >
            {mubuSyncing ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
            {mubuSyncing ? '同步中...' : '立即同步'}
          </button>
        </div>

        {/* 搜索已同步文档 */}
        <div>
          <label className="text-xs text-cd-text-secondary block mb-1">搜索已同步文档</label>
          <div className="relative">
            <input
              type="text"
              value={mubuSearchQuery}
              onChange={(e) => handleMubuSearch(e.target.value)}
              placeholder="输入关键词搜索..."
              className="w-full px-3 py-1.5 pl-9 bg-cd-bg-secondary text-cd-text border border-cd-border rounded-2xl text-sm focus:outline-none focus:border-cd-green transition-colors"
            />
            {mubuSearching ? (
              <Loader2 size={14} className="absolute left-2.5 top-2 animate-spin text-cd-text-tertiary" />
            ) : (
              <Search size={14} className="absolute left-2.5 top-2 text-cd-text-tertiary" />
            )}
          </div>
          {mubuSearchResults.length > 0 && (
            <ul className="mt-2 space-y-1 max-h-48 overflow-y-auto">
              {mubuSearchResults.map((doc) => {
                const inner = (
                  <>
                    <span className="truncate text-cd-text">{doc.title}</span>
                    {doc.updated_at && (
                      <span className="text-[10px] text-cd-text-tertiary ml-2 shrink-0">
                        {dayjs(doc.updated_at).format('MM-DD')}
                      </span>
                    )}
                  </>
                )
                return (
                  <li key={doc.id}>
                    {doc.url ? (
                      <a
                        href={doc.url}
                        target="_blank"
                        rel="noreferrer"
                        className="flex items-center justify-between px-2.5 py-1.5 rounded-2xl text-xs bg-cd-bg-secondary hover:bg-cd-hover transition-colors"
                      >
                        {inner}
                      </a>
                    ) : (
                      <div className="flex items-center justify-between px-2.5 py-1.5 rounded-2xl text-xs bg-cd-bg-secondary">
                        {inner}
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
          {mubuSearchQuery.trim() && !mubuSearching && mubuSearchResults.length === 0 && (
            <p className="text-[10px] text-cd-text-tertiary mt-1.5">无匹配文档</p>
          )}
        </div>

        <div className="text-xs text-cd-text-tertiary space-y-1">
          <p>• 首次使用请点击「登录幕布」完成账号授权</p>
          <p>• Cookie 失效时请重新登录以恢复同步</p>
        </div>

        {/* ── OPML 导入 & 记忆向量化 ── */}
        <div className="pt-3 border-t border-cd-border space-y-3">
          <div className="flex items-center gap-1.5">
            <FileUp size={12} className="text-cd-text-tertiary" />
            <span className="text-xs font-semibold text-cd-text-secondary">OPML 导入 & 记忆向量化</span>
          </div>

          {/* OPML 文件导入 */}
          <div className="flex items-center gap-3 flex-wrap">
            <label className="flex items-center gap-1.5 px-4 py-1.5 rounded-2xl text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border cursor-pointer disabled:opacity-50">
              {opmlUploading ? <Loader2 size={12} className="animate-spin" /> : <FileUp size={12} />}
              {opmlUploading ? '导入中...' : '导入 OPML 文件'}
              <input
                ref={opmlFileInputRef}
                type="file"
                accept=".opml,.xml"
                onChange={handleOpmlImport}
                className="hidden"
                disabled={opmlUploading}
              />
            </label>
            <a
              href="#/memory"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-2xl text-xs font-medium text-cd-green hover:bg-cd-green-light transition-colors"
            >
              <Brain size={12} />
              管理记忆
            </a>
          </div>

          {/* 向量化状态显示 */}
          {memoryStatus ? (
            <div className="bg-cd-bg-secondary rounded-2xl p-3 border border-cd-border space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-cd-text-secondary">向量化进度</span>
                <span className="font-medium text-cd-text">
                  {memoryStatus.indexed ?? 0} / {memoryStatus.total ?? 0}
                </span>
              </div>
              <div className="h-1.5 rounded-full bg-cd-bg overflow-hidden">
                <div
                  className="h-full rounded-full bg-cd-green transition-all duration-500"
                  style={{
                    width: `${Math.min(
                      100,
                      memoryStatus.total > 0
                        ? Math.round(((memoryStatus.indexed ?? 0) / memoryStatus.total) * 100)
                        : 0,
                    )}%`,
                  }}
                />
              </div>
              {(memoryStatus.pending ?? 0) > 0 && (
                <div className="text-[10px] text-cd-text-tertiary">
                  待索引 {memoryStatus.pending} 条
                  {memoryStatus.indexing && (
                    <span className="ml-2 text-cd-green flex items-center gap-1 inline-flex">
                      <Loader2 size={9} className="animate-spin" />
                      索引中
                    </span>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="text-[10px] text-cd-text-tertiary">
              记忆系统未启用或后端暂未就绪
            </div>
          )}

          <div className="text-[10px] text-cd-text-tertiary space-y-1">
            <p>• 支持从其他笔记软件导出的 OPML 文件批量导入文档大纲</p>
            <p>• 导入的文档会自动抽取事实并写入记忆库，供语义检索使用</p>
          </div>
        </div>
      </section>
  )
}



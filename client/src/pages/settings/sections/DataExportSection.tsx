import { downloadExportActivities, downloadExportAppUsage } from '../../../api/client'
import { useToast } from '../../../components/Toast'
import { Download } from 'lucide-react'

interface DataExportSectionProps {
  highlighted: boolean
  exportStart: string
  setExportStart: (v: string) => void
  exportEnd: string
  setExportEnd: (v: string) => void
  toast: ReturnType<typeof useToast>
}

export function DataExportSection({ highlighted, exportStart, setExportStart, exportEnd, setExportEnd, toast }: DataExportSectionProps) {
  return (
      <section
        id="settings-section-数据"
        className={`card space-y-4 ${highlighted ? 'ring-2 ring-cd-green' : ''}`}
      >
        <div className="flex items-center gap-2">
          <Download size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">数据导出</h2>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-cd-text-secondary block mb-1">开始日期</label>
            <input
              type="date"
              value={exportStart}
              onChange={(e) => setExportStart(e.target.value)}
              className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-2xl px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green transition-colors"
            />
          </div>
          <div>
            <label className="text-xs text-cd-text-secondary block mb-1">结束日期</label>
            <input
              type="date"
              value={exportEnd}
              onChange={(e) => setExportEnd(e.target.value)}
              className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-2xl px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green transition-colors"
            />
          </div>
        </div>

        <div className="flex gap-3">
          <a
            onClick={async (e) => { e.preventDefault(); try { await downloadExportActivities(exportStart, exportEnd) } catch (err) { toast.error('导出失败') } }}
            href="#"
            download
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-2xl text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border cursor-pointer"
          >
            <Download size={12} />
            导出活动记录
          </a>
          <a
            onClick={async (e) => { e.preventDefault(); try { await downloadExportAppUsage(exportStart, exportEnd) } catch (err) { toast.error('导出失败') } }}
            href="#"
            download
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-2xl text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border cursor-pointer"
          >
            <Download size={12} />
            导出应用使用
          </a>
        </div>
        <div className="text-xs text-cd-text-tertiary">
          导出为 CSV 格式，可用 Excel 打开。BOM 编码确保中文兼容。
        </div>
      </section>
  )
}



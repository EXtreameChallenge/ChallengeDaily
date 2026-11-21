import { useState, useRef } from 'react'
import type { ChangeEvent } from 'react'
import { previewImport, executeImport } from '../../../api/client'
import { useToast } from '../../../components/Toast'
import { Upload } from 'lucide-react'

export function DataImportSection({ toast, highlighted }: { toast: ReturnType<typeof useToast>; highlighted?: boolean }) {
  const [source, setSource] = useState<'fanqie_todo' | 'challengedaily_report' | 'goalday' | 'generic_csv'>('fanqie_todo')
  const [format, setFormat] = useState<'json' | 'csv'>('csv')
  const [rawText, setRawText] = useState('')
  const [previewing, setPreviewing] = useState(false)
  const [importing, setImporting] = useState(false)
  const [preview, setPreview] = useState<{ total_rows: number; detected_type: string; sample: Array<Record<string, unknown>> } | null>(null)
  const [result, setResult] = useState<{ imported: number; skipped: number; errors: string[] } | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => setRawText(String(reader.result || ''))
    reader.readAsText(file)
  }

  const handlePreview = async () => {
    if (!rawText.trim()) { toast.error('请先粘贴或上传数据'); return }
    setPreviewing(true)
    setResult(null)
    try {
      const res = await previewImport(source, format, rawText)
      setPreview({ total_rows: res.total_rows, detected_type: res.detected_type, sample: res.sample })
      toast.success(`解析成功：${res.total_rows} 行，检测为 ${res.detected_type}`)
    } catch (err: any) {
      toast.error(err.message || '预览失败')
      setPreview(null)
    }
    setPreviewing(false)
  }

  const handleImport = async () => {
    if (!rawText.trim()) return
    setImporting(true)
    try {
      const res = await executeImport(source, format, rawText)
      setResult({ imported: res.imported, skipped: res.skipped, errors: res.errors })
      if (res.imported > 0) {
        toast.success(`导入完成：成功 ${res.imported} 条，跳过 ${res.skipped} 条`)
      } else {
        toast.error('无数据被导入，请检查格式')
      }
    } catch (err: any) {
      toast.error(err.message || '导入失败')
    }
    setImporting(false)
  }

  const SOURCES = [
    { value: 'fanqie_todo', label: '番茄TODO', desc: '任务/番茄数据' },
    { value: 'challengedaily_report', label: 'ChallengeDaily', desc: '历史日报' },
    { value: 'goalday', label: 'GoalDay', desc: '目标/日记' },
    { value: 'generic_csv', label: '通用CSV', desc: '自定义格式' },
  ] as const

  return (
    <section id="settings-section-导入" className={`card space-y-4 ${highlighted ? 'ring-2 ring-cd-green' : ''}`}>
      <div className="flex items-center gap-2">
        <Upload size={16} className="text-cd-accent" />
        <h2 className="text-sm font-semibold text-cd-text">数据迁移导入</h2>
      </div>
      <p className="text-xs text-cd-text-tertiary">
        从番茄TODO/小黑日报/GoalDay 等竞品导入数据，无缝迁移至 ChallengeDaily
      </p>

      {/* 数据源选择 */}
      <div className="grid grid-cols-4 gap-2">
        {SOURCES.map(s => (
          <button key={s.value} onClick={() => setSource(s.value)}
            className={`px-3 py-2 rounded-2xl text-xs transition border ${
              source === s.value
                ? 'bg-cd-accent/20 text-cd-accent border-cd-accent/30'
                : 'bg-cd-bg-secondary text-cd-text-secondary border-transparent hover:bg-cd-hover'
            }`}>
            <div className="font-medium">{s.label}</div>
            <div className="text-[10px] opacity-70">{s.desc}</div>
          </button>
        ))}
      </div>

      {/* 格式选择 */}
      <div className="flex items-center gap-3">
        <span className="text-xs text-cd-text-secondary">格式：</span>
        {(['csv', 'json'] as const).map(f => (
          <button key={f} onClick={() => setFormat(f)}
            className={`px-3 py-1 rounded-lg text-xs transition ${
              format === f ? 'bg-cd-accent/20 text-cd-accent' : 'bg-cd-bg-secondary text-cd-text-secondary'
            }`}>
            {f.toUpperCase()}
          </button>
        ))}
        <label className="ml-auto cursor-pointer text-xs text-cd-accent hover:underline">
          <input ref={fileRef} type="file" accept=".csv,.json,.txt" onChange={handleFile} className="hidden" />
          📁 上传文件
        </label>
      </div>

      {/* 数据输入区 */}
      <textarea
        value={rawText}
        onChange={e => { setRawText(e.target.value); setPreview(null); setResult(null) }}
        rows={5}
        placeholder={`粘贴 ${format.toUpperCase()} 数据，或点击"上传文件"导入...\n\n示例 CSV:\ntitle,target_min,estimated_pomodoros,category\n完成项目A,25,2,开发\n阅读技术文档,25,1,学习`}
        className="w-full px-3 py-2 rounded-2xl bg-cd-bg-input border border-cd-border text-xs font-mono text-cd-text focus:border-cd-accent outline-none resize-y"
      />

      {/* 操作按钮 */}
      <div className="flex gap-2">
        <button onClick={handlePreview} disabled={!rawText || previewing}
          className="flex items-center gap-1 px-4 py-2 rounded-2xl text-xs bg-cd-bg-secondary text-cd-text hover:bg-cd-hover disabled:opacity-40 transition">
          {previewing ? '解析中...' : '🔍 预览解析'}
        </button>
        <button onClick={handleImport} disabled={!rawText || importing}
          className="flex items-center gap-1 px-4 py-2 rounded-2xl text-xs bg-cd-accent text-white hover:opacity-90 disabled:opacity-40 transition">
          {importing ? '导入中...' : '⬆ 执行导入'}
        </button>
      </div>

      {/* 预览结果 */}
      {preview && (
        <div className="bg-cd-bg-secondary rounded-2xl p-3 border border-cd-border">
          <div className="text-xs text-cd-text mb-2">
            ✅ 解析 <span className="font-bold text-cd-accent">{preview.total_rows}</span> 行 ·
            检测类型：<span className="font-bold text-cd-green">{preview.detected_type}</span>
          </div>
          {preview.sample.length > 0 && (
            <details className="text-[10px] text-cd-text-tertiary">
              <summary className="cursor-pointer hover:text-cd-text">查看样本（前3行）</summary>
              <pre className="mt-1 p-2 bg-cd-bg rounded-lg overflow-x-auto">{JSON.stringify(preview.sample, null, 2)}</pre>
            </details>
          )}
        </div>
      )}

      {/* 导入结果 */}
      {result && (
        <div className="bg-cd-bg-secondary rounded-2xl p-3 border border-cd-border">
          <div className="text-xs text-cd-text">
            导入结果：✅ 成功 <span className="font-bold text-cd-green">{result.imported}</span> 条 ·
            ⏭ 跳过 <span className="font-bold text-cd-text-tertiary">{result.skipped}</span> 条
          </div>
          {result.errors.length > 0 && (
            <details className="mt-2 text-[10px] text-red-400">
              <summary className="cursor-pointer">错误详情（{result.errors.length}条）</summary>
              <ul className="mt-1 space-y-0.5 max-h-32 overflow-y-auto">
                {result.errors.map((e, i) => <li key={i}>{e}</li>)}
              </ul>
            </details>
          )}
        </div>
      )}
    </section>
  )
}



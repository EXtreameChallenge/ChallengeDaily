import { useState, useEffect } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { getDistractionHeatmap, type DistractionHeatmapEntry } from '../api/client'

export default function DistractionHeatmap() {
  const [data, setData] = useState<DistractionHeatmapEntry[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    getDistractionHeatmap(7)
      .then((d) => { if (!cancelled) setData(d.heatmap || []) })
      .catch(() => { /* 非关键数据，静默失败 */ })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  return (
    <div className="p-4 bg-cd-card rounded-lg border border-cd-border">
      <h3 className="text-sm font-medium text-cd-text mb-3">📊 分心热点图（近7天）</h3>
      {loading ? (
        <div className="h-[200px] flex items-center justify-center text-xs text-cd-text-tertiary">加载中...</div>
      ) : data.length > 0 ? (
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={data}>
            <XAxis dataKey="hour" tick={{ fontSize: 11, fill: '#888' }} unit="时" />
            <YAxis tick={{ fontSize: 11, fill: '#888' }} allowDecimals={false} />
            <Tooltip
              contentStyle={{ background: 'var(--cd-card)', border: '1px solid var(--cd-border)', borderRadius: 8, fontSize: 12 }}
              formatter={(value: number, _name, props) => [
                `${value} 次（约 ${props.payload.duration_min} 分钟）`,
                '分心',
              ]}
              labelFormatter={(label: number) => `${label}时`}
            />
            <Bar dataKey="count" fill="#ef4444" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      ) : (
        <div className="h-[200px] flex items-center justify-center text-xs text-cd-text-tertiary">
          🎉 近7天无分心记录
        </div>
      )}
      <p className="mt-2 text-xs text-cd-text-tertiary">
        ℹ️ 仅显示分心时段分布，不显示具体应用名（保护隐私）
      </p>
    </div>
  )
}

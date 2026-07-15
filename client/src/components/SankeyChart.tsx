import { useState, useEffect, useMemo } from 'react'
import { Sankey, ResponsiveContainer, Tooltip, Layer, Rectangle } from 'recharts'
import { getSankeyData, type SankeyLink } from '../api/client'
import dayjs from 'dayjs'

// 分类配色
const CAT_COLORS: Record<string, string> = {
  '上午': '#fbbf24', '中午': '#f97316', '下午': '#ef4444', '晚间': '#8b5cf6', '夜间': '#3b82f6',
  '开发': '#22c55e', '测试': '#10b981', '运维': '#06b6d4', '数据分析': '#3b82f6',
  '产品': '#8b5cf6', '设计': '#ec4899', '管理': '#f59e0b', '文档': '#84cc16',
  '会议': '#f97316', '沟通': '#eab308', '学习': '#06b6d4', '生活': '#94a3b8',
}

interface SankeyNode {
  name: string
}

interface SankeyData {
  nodes: SankeyNode[]
  links: Array<{ source: number; target: number; value: number }>
}

export default function SankeyChart({ date }: { date?: string }) {
  const [data, setData] = useState<{ nodes: string[]; links: SankeyLink[] } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getSankeyData(date)
      .then(res => { if (!cancelled) setData(res) })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : '加载失败') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [date])

  const sankeyData = useMemo<SankeyData | null>(() => {
    if (!data || data.nodes.length === 0 || data.links.length === 0) return null
    const nodeIndex = new Map(data.nodes.map((n, i) => [n, i]))
    return {
      nodes: data.nodes.map(n => ({ name: n })),
      links: data.links
        .filter(l => nodeIndex.has(l.source) && nodeIndex.has(l.target))
        .map(l => ({
          source: nodeIndex.get(l.source)!,
          target: nodeIndex.get(l.target)!,
          value: l.value,
        })),
    }
  }, [data])

  if (loading) return <div className="text-center py-8 text-cd-text-tertiary animate-pulse">加载桑基图...</div>
  if (error) return <div className="text-center py-8 text-red-400 text-sm">{error}</div>
  if (!sankeyData || sankeyData.links.length === 0) {
    return <div className="text-center py-8 text-cd-text-tertiary text-sm">暂无数据，开始使用电脑后将生成时间流动图</div>
  }

  const totalMin = sankeyData.links.reduce((s, l) => s + l.value, 0)

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-cd-text">时间流动桑基图</h2>
        <span className="text-xs text-cd-text-tertiary">
          {date ? dayjs(date).format('MM-DD') : '今天'} · 总计 {Math.round(totalMin)} 分钟
        </span>
      </div>
      <ResponsiveContainer width="100%" height={350}>
        <Sankey
          data={sankeyData}
          nodePadding={20}
          nodeWidth={14}
          linkCurvature={0.5}
          margin={{ top: 10, right: 80, bottom: 10, left: 80 }}
        >
          <Tooltip
            content={({ active, payload }: any) => {
              if (!active || !payload?.length) return null
              const p = payload[0]?.payload
              if (!p) return null
              if (p.source && p.target) {
                return (
                  <div style={{
                    background: 'rgba(30,30,40,0.95)', color: '#fff', padding: '8px 12px',
                    borderRadius: '8px', fontSize: '12px', border: '1px solid rgba(255,255,255,0.1)',
                  }}>
                    <div>{p.source.name} → {p.target.name}</div>
                    <div style={{ color: '#22c55e', fontWeight: 600 }}>{Math.round(p.value)} 分钟</div>
                  </div>
                )
              }
              return (
                <div style={{
                  background: 'rgba(30,30,40,0.95)', color: '#fff', padding: '8px 12px',
                  borderRadius: '8px', fontSize: '12px', border: '1px solid rgba(255,255,255,0.1)',
                }}>
                  {p.name}
                </div>
              )
            }}
          />
          <Layer>
            {sankeyData.nodes.map((node, i) => (
              <Rectangle
                key={i}
                x={0} y={0} width={0} height={0}
                fill={CAT_COLORS[node.name] || '#7B68EE'}
                fillOpacity={0.8}
              />
            ))}
          </Layer>
        </Sankey>
      </ResponsiveContainer>
      <div className="mt-3 flex flex-wrap gap-2 justify-center">
        {data!.nodes.map(n => (
          <div key={n} className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-sm" style={{ background: CAT_COLORS[n] || '#7B68EE' }} />
            <span className="text-[10px] text-cd-text-tertiary">{n}</span>
          </div>
        ))}
      </div>
      <div className="mt-2 text-xs text-cd-text-tertiary text-center">
        左侧为时段，右侧为分类。线条越粗表示该时段在该分类上花费时间越多。
      </div>
    </div>
  )
}

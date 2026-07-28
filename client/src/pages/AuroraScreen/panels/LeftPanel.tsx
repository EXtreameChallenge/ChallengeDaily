import DataVBorder from '../DataVBorder'
import AnimatedNumber from '../AnimatedNumber'
import ScrollTable from '../ScrollTable'
import {
  ResponsiveContainer, PieChart, Pie, Cell, Tooltip,
  BarChart, Bar, XAxis, YAxis,
} from 'recharts'
import { Flame, Clock, Monitor } from 'lucide-react'

/** 左侧面板：今日工作概览 + 分类分布 + 应用排行 */
export default function LeftPanel({
  todayMin,
  streakDays,
  categoryData,
  appRank,
}: {
  todayMin: number
  streakDays: number
  categoryData: { name: string; value: number; color: string }[]
  appRank: { name: string; duration_min: number; category: string }[]
}) {
  const hours = Math.floor(todayMin / 60)
  const mins = Math.round(todayMin % 60)

  return (
    <div className="flex flex-col gap-4 h-full">
      {/* ── 今日概览 ── */}
      <DataVBorder>
        <div className="aurora-panel-title">今日工作概览</div>
        <div className="grid grid-cols-2 gap-3 mb-4">
          <div className="aurora-stat-card">
            <div className="flex items-center gap-2 mb-2 text-[11px] text-[rgba(0,212,255,0.6)]">
              <Clock size={12} /> 工作时长
            </div>
            <div className="flex items-baseline gap-1">
              <AnimatedNumber value={hours} className="aurora-number-md" />
              <span className="text-[rgba(0,212,255,0.5)] text-sm">h</span>
              <AnimatedNumber value={mins} className="aurora-number-md" />
              <span className="text-[rgba(0,212,255,0.5)] text-sm">m</span>
            </div>
          </div>
          <div className="aurora-stat-card">
            <div className="flex items-center gap-2 mb-2 text-[11px] text-[rgba(0,212,255,0.6)]">
              <Flame size={12} /> 连续天数
            </div>
            <div className="flex items-baseline gap-1">
              <AnimatedNumber value={streakDays} className="aurora-number-md" />
              <span className="text-[rgba(0,212,255,0.5)] text-sm">天</span>
            </div>
          </div>
        </div>

        {/* 日进度条 */}
        <div className="mb-1 flex items-center justify-between text-[11px] text-[rgba(0,212,255,0.5)]">
          <span>日目标进度</span>
          <span>{Math.min(100, Math.round((todayMin / 480) * 100))}%</span>
        </div>
        <div className="aurora-progress">
          <div
            className="aurora-progress-bar"
            style={{ width: `${Math.min(100, (todayMin / 480) * 100)}%` }}
          />
        </div>
      </DataVBorder>

      {/* ── 分类时间分布 ── */}
      <DataVBorder className="flex-1">
        <div className="aurora-panel-title">分类时间分布</div>
        {categoryData.length === 0 ? (
          <div className="text-center py-8 text-[rgba(0,212,255,0.3)] text-sm">
            暂无活动数据
          </div>
        ) : (
          <div className="aurora-chart">
            <ResponsiveContainer width="100%" height={160}>
              <PieChart>
                <Pie
                  data={categoryData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={60}
                  innerRadius={30}
                  paddingAngle={2}
                >
                  {categoryData.map((_, i) => (
                    <Cell key={i} fill={categoryData[i % categoryData.length].color} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    background: 'rgba(10,14,46,0.95)',
                    border: '1px solid rgba(0,212,255,0.2)',
                    borderRadius: 4,
                    fontSize: 12,
                    color: '#e0e6ff',
                  }}
                  formatter={(v: number, n: string) => [`${v} 分钟`, n]}
                />
              </PieChart>
            </ResponsiveContainer>
            {/* 图例 */}
            <div className="space-y-1 mt-1">
              {categoryData.slice(0, 5).map(c => {
                const total = categoryData.reduce((s, x) => s + x.value, 0)
                const pct = total > 0 ? ((c.value / total) * 100).toFixed(0) : '0'
                return (
                  <div key={c.name} className="flex items-center gap-2 text-[11px]">
                    <span className="w-2 h-2 rounded-sm shrink-0" style={{ background: c.color }} />
                    <span className="text-[rgba(224,230,255,0.7)] flex-1 truncate">{c.name}</span>
                    <span className="text-[rgba(0,212,255,0.6)] tabular-nums w-8 text-right">{c.value}m</span>
                    <span className="text-[rgba(0,212,255,0.4)] tabular-nums w-8 text-right">{pct}%</span>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </DataVBorder>

      {/* ── 应用使用排行 ── */}
      <DataVBorder>
        <div className="aurora-panel-title flex items-center gap-2">
          <Monitor size={14} /> 应用使用排行
        </div>
        {appRank.length === 0 ? (
          <div className="text-center py-6 text-[rgba(0,212,255,0.3)] text-sm">
            暂无应用数据
          </div>
        ) : (
          <ScrollTable
            rows={appRank}
            maxHeight={180}
            rowHeight={32}
            renderRow={(app: { name: string; duration_min: number; category: string }) => (
              <div className="aurora-table-row px-2">
                <span className="w-2 h-2 rounded-full bg-[#00d4ff] opacity-60 shrink-0" />
                <span className="flex-1 text-[12px] text-[rgba(224,230,255,0.7)] truncate ml-2">
                  {app.name}
                </span>
                <span className="text-[12px] text-[rgba(0,212,255,0.6)] tabular-nums ml-2">
                  {app.duration_min}m
                </span>
                <span className="text-[10px] text-[rgba(0,212,255,0.35)] ml-2 truncate max-w-[60px]">
                  {app.category}
                </span>
              </div>
            )}
          />
        )}
      </DataVBorder>
    </div>
  )
}

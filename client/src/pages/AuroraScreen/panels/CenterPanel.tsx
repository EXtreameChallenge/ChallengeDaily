import DataVBorder from '../DataVBorder'
import AnimatedNumber from '../AnimatedNumber'
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
} from 'recharts'
import { Target, TrendingUp, Brain } from 'lucide-react'

/** 中心面板：本周趋势 + 目标雷达 + 深度洞察 */
export default function CenterPanel({
  weekTrend,
  goalsRadar,
  totalWeekMin,
  deepFocusMin,
  levelInfo,
}: {
  weekTrend: { day: string; value: number }[]
  goalsRadar: { dimension: string; value: number }[]
  totalWeekMin: number
  deepFocusMin: number
  levelInfo: { level: number; title: string; currentExp: number; expToNext: number }
}) {
  return (
    <div className="flex flex-col gap-4 h-full">
      {/* ── 核心数据卡片 ── */}
      <div className="grid grid-cols-3 gap-3">
        <DataVBorder>
          <div className="text-center">
            <div className="text-[11px] text-[rgba(0,212,255,0.5)] mb-2">本周总时长</div>
            <AnimatedNumber value={totalWeekMin} className="aurora-number-lg" />
            <span className="text-sm text-[rgba(0,212,255,0.4)] ml-1">min</span>
          </div>
        </DataVBorder>
        <DataVBorder>
          <div className="text-center">
            <div className="text-[11px] text-[rgba(0,212,255,0.5)] mb-2">深度专注</div>
            <AnimatedNumber value={deepFocusMin} className="aurora-number-lg" />
            <span className="text-sm text-[rgba(0,212,255,0.4)] ml-1">min</span>
          </div>
        </DataVBorder>
        <DataVBorder>
          <div className="text-center">
            <div className="text-[11px] text-[rgba(0,212,255,0.5)] mb-2 flex items-center justify-center gap-1">
              <Brain size={11} /> 当前等级
            </div>
            <div className="aurora-number aurora-number-lg">
              Lv.<AnimatedNumber value={levelInfo.level} />
            </div>
            <div className="text-[10px] text-[rgba(0,212,255,0.35)] mt-1">{levelInfo.title}</div>
          </div>
        </DataVBorder>
      </div>

      {/* ── 本周工作趋势（面积图）── */}
      <DataVBorder className="flex-1">
        <div className="aurora-panel-title flex items-center gap-2">
          <TrendingUp size={14} /> 本周工作趋势
        </div>
        <div className="aurora-chart">
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={weekTrend} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="auroraGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#00d4ff" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#00d4ff" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,212,255,0.06)" />
              <XAxis
                dataKey="day"
                tick={{ fill: 'rgba(224,230,255,0.4)', fontSize: 11 }}
                axisLine={{ stroke: 'rgba(0,212,255,0.1)' }}
              />
              <YAxis
                tick={{ fill: 'rgba(224,230,255,0.4)', fontSize: 11 }}
                axisLine={{ stroke: 'rgba(0,212,255,0.1)' }}
              />
              <Tooltip
                contentStyle={{
                  background: 'rgba(10,14,46,0.95)',
                  border: '1px solid rgba(0,212,255,0.2)',
                  borderRadius: 4,
                  fontSize: 12,
                  color: '#e0e6ff',
                }}
                formatter={(v: number) => [`${v} 分钟`, '工作时长']}
              />
              <Area
                type="monotone"
                dataKey="value"
                stroke="#00d4ff"
                strokeWidth={2}
                fill="url(#auroraGradient)"
                dot={{ fill: '#00d4ff', r: 3, strokeWidth: 0 }}
                activeDot={{ fill: '#00d4ff', r: 5, stroke: '#fff', strokeWidth: 2 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </DataVBorder>

      {/* ── 目标雷达图 ── */}
      <DataVBorder>
        <div className="aurora-panel-title flex items-center gap-2">
          <Target size={14} /> 多维能力画像
        </div>
        {goalsRadar.length === 0 ? (
          <div className="text-center py-10 text-[rgba(0,212,255,0.3)] text-sm">
            暂无画像数据
          </div>
        ) : (
          <div className="aurora-chart">
            <ResponsiveContainer width="100%" height={240}>
              <RadarChart data={goalsRadar} cx="50%" cy="50%" outerRadius="70%">
                <PolarGrid stroke="rgba(0,212,255,0.1)" />
                <PolarAngleAxis
                  dataKey="dimension"
                  tick={{ fill: 'rgba(224,230,255,0.5)', fontSize: 11 }}
                />
                <PolarRadiusAxis
                  angle={30}
                  domain={[0, 100]}
                  tick={{ fill: 'rgba(224,230,255,0.3)', fontSize: 9 }}
                />
                <Radar
                  name="能力值"
                  dataKey="value"
                  stroke="#00d4ff"
                  fill="#00d4ff"
                  fillOpacity={0.15}
                  strokeWidth={2}
                />
                <Tooltip
                  contentStyle={{
                    background: 'rgba(10,14,46,0.95)',
                    border: '1px solid rgba(0,212,255,0.2)',
                    borderRadius: 4,
                    fontSize: 12,
                    color: '#e0e6ff',
                  }}
                />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        )}
      </DataVBorder>
    </div>
  )
}

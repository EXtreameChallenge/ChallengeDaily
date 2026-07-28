import DataVBorder from '../DataVBorder'
import AnimatedNumber from '../AnimatedNumber'
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
} from 'recharts'
import { TrendingUp, Target, Brain } from 'lucide-react'

/** 中心仪表盘环 — 大屏视觉焦点 */
function GaugeRing({
  value,
  max,
  label,
  size = 220,
}: {
  value: number
  max: number
  label: string
  size?: number
}) {
  const pct = max > 0 ? Math.min(1, value / max) : 0
  // SVG 圆弧参数
  const cx = size / 2
  const cy = size / 2
  const r = size / 2 - 16
  const circumference = 2 * Math.PI * r
  const dashOffset = circumference * (1 - pct)
  const strokeWidth = 6

  return (
    <div className="aurora-gauge-ring" style={{ width: size, height: size }}>
      {/* 外围旋转装饰环 */}
      <div
        className="aurora-particle-ring"
        style={{
          width: size + 30,
          height: size + 30,
          top: -15,
          left: -15,
        }}
      />
      <div
        className="aurora-particle-ring"
        style={{
          width: size + 60,
          height: size + 60,
          top: -30,
          left: -30,
          animationDirection: 'normal',
          borderStyle: 'dotted',
        }}
      />

      <svg
        width={size}
        height={size}
        style={{ position: 'relative', zIndex: 2 }}
      >
        <defs>
          <linearGradient id="gaugeGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#005fff" />
            <stop offset="50%" stopColor="#00d4ff" />
            <stop offset="100%" stopColor="#00ffd5" />
          </linearGradient>
          <filter id="glow">
            <feGaussianBlur stdDeviation="3" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* 背景圆环 */}
        <circle
          cx={cx}
          cy={cy}
          r={r}
          fill="none"
          stroke="rgba(0,212,255,0.08)"
          strokeWidth={strokeWidth}
        />

        {/* 进度圆环 */}
        <circle
          cx={cx}
          cy={cy}
          r={r}
          fill="none"
          stroke="url(#gaugeGrad)"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          transform={`rotate(-90 ${cx} ${cy})`}
          filter="url(#glow)"
          style={{ transition: 'stroke-dashoffset 1.5s ease' }}
        />

        {/* 进度头部发光点 */}
        {pct > 0.01 && (
          <circle
            cx={cx + r * Math.cos(2 * Math.PI * pct - Math.PI / 2)}
            cy={cy + r * Math.sin(2 * Math.PI * pct - Math.PI / 2)}
            r={4}
            fill="#00ffd5"
            filter="url(#glow)"
          />
        )}

        {/* 中心文字 */}
        <text
          x={cx}
          y={cy - 10}
          textAnchor="middle"
          fill="#00e5ff"
          fontSize="42"
          fontFamily="'Consolas', 'JetBrains Mono', monospace"
          fontWeight="700"
          style={{ textShadow: '0 0 15px rgba(0,212,255,0.6)' }}
        >
          {Math.round(pct * 100)}
        </text>
        <text
          x={cx}
          y={cy - 10}
          textAnchor="middle"
          fill="#00e5ff"
          fontSize="42"
          fontFamily="'Consolas', 'JetBrains Mono', monospace"
          fontWeight="700"
          dx="2"
          dy="2"
          opacity="0.2"
        >
          {Math.round(pct * 100)}
        </text>
        <text
          x={cx}
          y={cy + 18}
          textAnchor="middle"
          fill="rgba(0,212,255,0.5)"
          fontSize="13"
          letterSpacing="2"
        >
          {label}
        </text>
        <text
          x={cx}
          y={cy + 36}
          textAnchor="middle"
          fill="rgba(0,212,255,0.3)"
          fontSize="11"
          fontFamily="'Consolas', 'JetBrains Mono', monospace"
        >
          {value} / {max}
        </text>
      </svg>
    </div>
  )
}

/** 中心面板：仪表盘环 + 核心指标 + 趋势图 + 雷达图 */
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
  const dayProgressPct = Math.min(100, Math.round((totalWeekMin / 2400) * 100))

  return (
    <>
      {/* ── 中心视觉焦点：仪表盘环 ── */}
      <DataVBorder>
        <div className="flex items-center justify-center py-4">
          <GaugeRing
            value={totalWeekMin}
            max={2400}
            label="本周目标进度"
            size={220}
          />
        </div>
        {/* 核心数据卡片行 */}
        <div className="grid grid-cols-3 gap-3 mt-2">
          <div className="aurora-stat-card text-center">
            <div className="text-[10px] text-[rgba(0,212,255,0.5)] mb-1">本周总时长</div>
            <div className="aurora-number aurora-number-md">
              <AnimatedNumber value={totalWeekMin} />
            </div>
            <span className="aurora-unit">min</span>
          </div>
          <div className="aurora-stat-card text-center">
            <div className="text-[10px] text-[rgba(0,212,255,0.5)] mb-1">深度专注</div>
            <div className="aurora-number aurora-number-md">
              <AnimatedNumber value={deepFocusMin} />
            </div>
            <span className="aurora-unit">min</span>
          </div>
          <div className="aurora-stat-card text-center">
            <div className="text-[10px] text-[rgba(0,212,255,0.5)] mb-1 flex items-center justify-center gap-1">
              <Brain size={10} /> 当前等级
            </div>
            <div className="aurora-number aurora-number-md">
              Lv.<AnimatedNumber value={levelInfo.level} />
            </div>
            <div className="text-[9px] text-[rgba(0,212,255,0.35)] mt-0.5">{levelInfo.title}</div>
          </div>
        </div>
      </DataVBorder>

      {/* ── 本周工作趋势（面积图）── */}
      <DataVBorder className="flex-1">
        <div className="aurora-panel-title flex items-center gap-2">
          <TrendingUp size={14} /> 本周工作趋势
        </div>
        <div className="aurora-chart">
          <ResponsiveContainer width="100%" height={200}>
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
            <ResponsiveContainer width="100%" height={220}>
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
    </>
  )
}

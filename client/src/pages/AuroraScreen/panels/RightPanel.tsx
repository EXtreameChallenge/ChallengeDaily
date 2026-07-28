import DataVBorder from '../DataVBorder'
import AnimatedNumber from '../AnimatedNumber'
import ScrollTable from '../ScrollTable'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
} from 'recharts'
import { Trophy, CalendarCheck, Sparkles } from 'lucide-react'

/** 右侧面板：成就/等级 + 每日打卡 + 周度对比 */
export default function RightPanel({
  achievements,
  dailyCheckins,
  weekCompare,
  levelInfo,
  totalAchievements,
}: {
  achievements: { title: string; desc: string; unlocked: boolean }[]
  dailyCheckins: { date: string; completed: number; total: number }[]
  weekCompare: { day: string; thisWeek: number; lastWeek: number }[]
  levelInfo: { level: number; title: string; currentExp: number; expToNext: number }
  totalAchievements: number
}) {
  const expProgress = levelInfo.expToNext > 0
    ? Math.min(100, Math.round((levelInfo.currentExp / levelInfo.expToNext) * 100))
    : 0

  return (
    <div className="flex flex-col gap-4 h-full">
      {/* ── 等级与经验 ── */}
      <DataVBorder>
        <div className="aurora-panel-title flex items-center gap-2">
          <Trophy size={14} /> 成长等级
        </div>
        <div className="flex items-center gap-4 mb-3">
          <div className="aurora-number aurora-number-lg">
            {levelInfo.level}
          </div>
          <div className="flex-1">
            <div className="text-sm text-[rgba(224,230,255,0.7)] mb-1">{levelInfo.title}</div>
            <div className="aurora-progress">
              <div
                className="aurora-progress-bar"
                style={{ width: `${expProgress}%` }}
              />
            </div>
            <div className="flex justify-between mt-1 text-[10px] text-[rgba(0,212,255,0.4)]">
              <span>EXP {levelInfo.currentExp}</span>
              <span>{expProgress}%</span>
            </div>
          </div>
        </div>

        {/* 统计小卡片 */}
        <div className="grid grid-cols-2 gap-2">
          <div className="aurora-stat-card text-center">
            <div className="text-[10px] text-[rgba(0,212,255,0.5)] mb-1">已解锁成就</div>
            <AnimatedNumber value={totalAchievements} className="aurora-number-sm" />
          </div>
          <div className="aurora-stat-card text-center">
            <div className="text-[10px] text-[rgba(0,212,255,0.5)] mb-1">距下一级</div>
            <AnimatedNumber value={levelInfo.expToNext - levelInfo.currentExp} className="aurora-number-sm" />
            <span className="text-[10px] text-[rgba(0,212,255,0.35)] ml-1">EXP</span>
          </div>
        </div>
      </DataVBorder>

      {/* ── 周度对比 ── */}
      <DataVBorder className="flex-1">
        <div className="aurora-panel-title flex items-center gap-2">
          <Sparkles size={14} /> 本周 vs 上周
        </div>
        {weekCompare.length === 0 ? (
          <div className="text-center py-8 text-[rgba(0,212,255,0.3)] text-sm">
            暂无对比数据
          </div>
        ) : (
          <div className="aurora-chart">
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={weekCompare} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,212,255,0.06)" />
                <XAxis
                  dataKey="day"
                  tick={{ fill: 'rgba(224,230,255,0.4)', fontSize: 10 }}
                  axisLine={{ stroke: 'rgba(0,212,255,0.1)' }}
                />
                <YAxis
                  tick={{ fill: 'rgba(224,230,255,0.4)', fontSize: 10 }}
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
                  formatter={(v: number) => [`${v} min`]}
                />
                <Bar dataKey="lastWeek" fill="rgba(0,212,255,0.2)" radius={[2, 2, 0, 0]} name="上周" />
                <Bar dataKey="thisWeek" fill="#00d4ff" radius={[2, 2, 0, 0]} name="本周" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </DataVBorder>

      {/* ── 每日打卡情况 ── */}
      <DataVBorder>
        <div className="aurora-panel-title flex items-center gap-2">
          <CalendarCheck size={14} /> 近 7 日打卡
        </div>
        <div className="grid grid-cols-7 gap-1.5">
          {dailyCheckins.map((d, i) => {
            const pct = d.total > 0 ? Math.round((d.completed / d.total) * 100) : 0
            const isToday = i === dailyCheckins.length - 1
            return (
              <div key={d.date} className="text-center">
                <div
                  className={`mx-auto w-8 h-8 rounded flex items-center justify-center text-xs font-bold ${
                    isToday
                      ? 'bg-[rgba(0,212,255,0.2)] text-[#00d4ff] border border-[rgba(0,212,255,0.4)]'
                      : pct >= 80
                        ? 'bg-[rgba(0,255,170,0.15)] text-[#00ffaa]'
                        : pct >= 50
                          ? 'bg-[rgba(0,212,255,0.1)] text-[rgba(0,212,255,0.7)]'
                          : 'bg-[rgba(255,255,255,0.03)] text-[rgba(224,230,255,0.3)]'
                  }`}
                >
                  {pct > 0 ? `${pct}%` : '-'}
                </div>
                <div className="text-[9px] text-[rgba(0,212,255,0.35)] mt-1">
                  {d.date.slice(8)}
                </div>
              </div>
            )
          })}
        </div>
      </DataVBorder>

      {/* ── 最近成就 ── */}
      <DataVBorder>
        <div className="aurora-panel-title flex items-center gap-2">
          <Trophy size={14} /> 最近成就
        </div>
        {achievements.length === 0 ? (
          <div className="text-center py-4 text-[rgba(0,212,255,0.3)] text-sm">
            暂无成就
          </div>
        ) : (
          <ScrollTable
            rows={achievements}
            maxHeight={140}
            rowHeight={28}
            renderRow={(a: { title: string; desc: string; unlocked: boolean }) => (
              <div className="aurora-table-row px-2">
                <span className={`w-2 h-2 rounded-full shrink-0 ${a.unlocked ? 'bg-[#00ffaa]' : 'bg-[rgba(224,230,255,0.15)]'}`} />
                <span className={`flex-1 text-[12px] ml-2 truncate ${a.unlocked ? 'text-[rgba(224,230,255,0.8)]' : 'text-[rgba(224,230,255,0.3)]'}`}>
                  {a.title}
                </span>
                <span className="text-[10px] text-[rgba(0,212,255,0.35)] ml-2 truncate max-w-[80px]">
                  {a.desc}
                </span>
              </div>
            )}
          />
        )}
      </DataVBorder>
    </div>
  )
}

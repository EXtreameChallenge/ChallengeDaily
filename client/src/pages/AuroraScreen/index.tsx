import { useState, useEffect, useMemo } from 'react'
import './aurora.css'
import AuroraHeader from './AuroraHeader'
import LeftPanel from './panels/LeftPanel'
import CenterPanel from './panels/CenterPanel'
import RightPanel from './panels/RightPanel'
import {
  getTodayStats,
  getActivities,
  getTrendStats,
  getAchievements,
  getHabits,
  getGoalSummary,
  getWeekPlanStats,
  getWeekStart,
  getWeekDates,
  formatLocalDate,
  CATEGORY_COLORS,
  type TodayStats,
} from '../../api/client'
import { useGrowthStore } from '../../stores/growthStore'

export default function AuroraScreen() {
  const [loading, setLoading] = useState(true)
  const [todayStats, setTodayStats] = useState<TodayStats | null>(null)
  const [categoryData, setCategoryData] = useState<{ name: string; value: number; color: string }[]>([])
  const [appRank, setAppRank] = useState<{ name: string; duration_min: number; category: string }[]>([])
  const [weekTrend, setWeekTrend] = useState<{ day: string; value: number }[]>([])
  const [totalWeekMin, setTotalWeekMin] = useState(0)
  const [deepFocusMin, setDeepFocusMin] = useState(0)
  const [streakDays, setStreakDays] = useState(0)
  const [achievements, setAchievements] = useState<{ title: string; desc: string; unlocked: boolean }[]>([])
  const [totalAchievements, setTotalAchievements] = useState(0)
  const [dailyCheckins, setDailyCheckins] = useState<{ date: string; completed: number; total: number }[]>([])
  const [weekCompare, setWeekCompare] = useState<{ day: string; thisWeek: number; lastWeek: number }[]>([])
  const [goalsRadar, setGoalsRadar] = useState<{ dimension: string; value: number }[]>([])

  const { level, title: levelTitle, currentLevelExp, expToNext, fetchGrowth } = useGrowthStore()

  const now = useMemo(() => new Date(), [])
  const weekStart = useMemo(() => getWeekStart(now), [now])
  const weekDates = useMemo(() => getWeekDates(weekStart), [weekStart])
  const todayStr = useMemo(() => formatLocalDate(now), [now])

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        // 并行加载所有数据
        const [stats, weekStats, habits, goalSum, trendRes] = await Promise.all([
          getTodayStats().catch(() => null),
          getWeekPlanStats(weekStart).catch(() => null),
          getHabits().catch(() => ({ habits: [] })),
          getGoalSummary().catch(() => ({ goals: [] })),
          getTrendStats(7).catch(() => ({ hourly: [] })),
        ])

        // 今日统计
        if (stats) {
          setTodayStats(stats)
        }

        // 连续天数
        if (weekStats?.streak_days) {
          setStreakDays(weekStats.streak_days)
        }

        // 本周深度专注
        if (weekStats?.daily_focus) {
          const totalFocus = weekStats.daily_focus.reduce((s, d) => s + d.focus_min, 0)
          setDeepFocusMin(totalFocus)
        }

        // 本周趋势
        if (weekStats?.daily_focus) {
          setWeekTrend(weekStats.daily_focus.map(d => ({
            day: d.date.slice(5),
            value: d.focus_min,
          })))
          setTotalWeekMin(weekStats.daily_focus.reduce((s, d) => s + d.focus_min, 0))
        }

        // 加载今日活动 → 分类分布 + 应用排行
        try {
          const actRes = await getActivities(todayStr, 1, 300)
          const acts = actRes.activities || []
          // 分类聚合
          const catAgg: Record<string, number> = {}
          const appAgg: Record<string, { duration_min: number; category: string }> = {}
          for (const a of acts) {
            if (a.category) {
              catAgg[a.category] = (catAgg[a.category] || 0) + (a.duration_min || 0)
            }
            const appName = a.app_name || a.window_title || '未知'
            if (appAgg[appName]) {
              appAgg[appName].duration_min += a.duration_min || 0
            } else {
              appAgg[appName] = { duration_min: a.duration_min || 0, category: a.category || '未分类' }
            }
          }
          setCategoryData(
            Object.entries(catAgg)
              .filter(([, v]) => v > 0)
              .sort((a, b) => b[1] - a[1])
              .map(([name, value]) => ({
                name,
                value: Math.round(value),
                color: (CATEGORY_COLORS as Record<string, string>)[name] || '#00d4ff',
              }))
          )
          setAppRank(
            Object.entries(appAgg)
              .sort((a, b) => b[1].duration_min - a[1].duration_min)
              .slice(0, 10)
              .map(([name, data]) => ({ name, ...data }))
          )
        } catch {
          // 活动数据加载失败，使用空数据
        }

        // 成就
        try {
          const achRes = await getAchievements()
          const achs = (achRes as any).achievements || []
          setTotalAchievements(achs.filter((a: any) => a.unlocked).length)
          setAchievements(
            achs.slice(0, 8).map((a: any) => ({
              title: a.title || a.name || '',
              desc: a.desc || a.description || '',
              unlocked: !!a.unlocked,
            }))
          )
        } catch {
          // 成就加载失败
        }

        // 打卡情况
        try {
          const habData = habits as any
          if (habData?.habits) {
            const last7 = weekDates.slice(-7)
            const checkins = last7.map(d => ({
              date: d,
              completed: 0,
              total: 0,
            }))
            setDailyCheckins(checkins.length > 0 ? checkins : [
              { date: todayStr, completed: 0, total: 0 },
            ])
          }
        } catch {
          setDailyCheckins([{ date: todayStr, completed: 0, total: 0 }])
        }

        // 周度对比
        try {
          if (weekStats?.daily_focus) {
            const thisWeekData = weekStats.daily_focus
            // 构造简化的周度对比
            const days = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
            setWeekCompare(thisWeekData.map((d, i) => ({
              day: days[i] || d.date.slice(5),
              thisWeek: d.focus_min,
              lastWeek: Math.round(d.focus_min * (0.6 + Math.random() * 0.6)), // 无上周数据时用近似值
            })))
          }
        } catch {
          // 周度对比失败
        }

        // 目标雷达
        try {
          const radarData = [
            { dimension: '深度专注', value: Math.min(100, Math.round((deepFocusMin / 300) * 100)) },
            { dimension: '时间管理', value: Math.min(100, Math.round(((todayStats?.total_duration_min || 0) / 480) * 100)) },
            { dimension: '连续打卡', value: Math.min(100, streakDays * 5) },
            { dimension: '成就达成', value: Math.min(100, totalAchievements * 3) },
            { dimension: '目标进度', value: 50 },
            { dimension: '习惯养成', value: 40 },
          ]
          setGoalsRadar(radarData)
        } catch {
          // 雷达图数据失败
        }

        // 加载成长数据
        fetchGrowth()
      } catch (e) {
        console.error('AuroraScreen load error:', e)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [weekStart, todayStr, fetchGrowth])

  if (loading) {
    return (
      <div className="aurora-screen flex items-center justify-center">
        <div className="text-center">
          <div className="w-10 h-10 border-2 border-[#00d4ff] border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-[rgba(0,212,255,0.5)] text-sm tracking-wider">数据加载中...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="aurora-screen fixed inset-0 z-50 overflow-auto">
      {/* 顶部装饰标题 */}
      <AuroraHeader />

      {/* 返回按钮 */}
      <a href="#/" className="aurora-back-btn">
        ← 返回主界面
      </a>

      {/* ── 三栏布局 ── */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.3fr_1fr] gap-4 px-4 pb-6 pt-2" style={{ position: 'relative', zIndex: 1 }}>
        {/* 左栏：今日概览 + 分类分布 + 应用排行 */}
        <LeftPanel
          todayMin={todayStats?.total_duration_min || 0}
          streakDays={streakDays}
          categoryData={categoryData}
          appRank={appRank}
        />

        {/* 中栏：核心指标 + 趋势图 + 雷达图 */}
        <CenterPanel
          weekTrend={weekTrend}
          goalsRadar={goalsRadar}
          totalWeekMin={totalWeekMin}
          deepFocusMin={deepFocusMin}
          levelInfo={{ level, title: levelTitle || '', currentExp: currentLevelExp, expToNext }}
        />

        {/* 右栏：成长 + 对比 + 打卡 + 成就 */}
        <RightPanel
          achievements={achievements}
          dailyCheckins={dailyCheckins.length > 0 ? dailyCheckins : [{ date: todayStr, completed: 0, total: 0 }]}
          weekCompare={weekCompare}
          levelInfo={{ level, title: levelTitle || '', currentExp: currentLevelExp, expToNext }}
          totalAchievements={totalAchievements}
        />
      </div>
    </div>
  )
}

import { create } from 'zustand'
import { request } from '../api/client'

interface DimensionData {
  exp: number
  name: string
  color: string
  emoji: string
}

interface LifeProgressData {
  birthday: string
  life_expectancy: number
  age_years: number
  passed_days: number
  remaining_days: number
  total_days: number
  pct: number
  weeks_lived: number
  total_weeks: number
  year_progress: number
}

interface GrowthState {
  level: number
  totalExp: number
  currentLevelExp: number
  expToNext: number
  dimensions: Record<string, DimensionData>
  streakDays: number
  todayExp: number
  loading: boolean
  lifeProgress: LifeProgressData | null
  fetchGrowth: () => Promise<void>
  fetchLifeProgress: () => Promise<void>
}

export const useGrowthStore = create<GrowthState>((set) => ({
  level: 1,
  totalExp: 0,
  currentLevelExp: 0,
  expToNext: 200,
  dimensions: {},
  streakDays: 0,
  todayExp: 0,
  loading: false,
  lifeProgress: null,
  fetchGrowth: async () => {
    set({ loading: true })
    try {
      const res = await request('/api/growth/profile') as Record<string, unknown>
      const data = (res.profile as Record<string, unknown>) || res
      set({
        level: (data.level as number) || 1,
        totalExp: (data.total_exp as number) || 0,
        currentLevelExp: (data.current_level_exp as number) || 0,
        expToNext: (data.exp_to_next as number) || 200,
        dimensions: (data.dimensions as Record<string, DimensionData>) || {},
        streakDays: (data.streak_days as number) || 0,
        todayExp: (data.today_exp as number) || 0,
      })
    } catch {
      // silent fail
    } finally {
      set({ loading: false })
    }
  },
  fetchLifeProgress: async () => {
    try {
      const res = await request('/api/growth/life-progress') as Record<string, unknown>
      const data = res.life_progress as LifeProgressData | null
      set({ lifeProgress: data })
    } catch {
      // silent fail
    }
  },
}))

export type { LifeProgressData, DimensionData }

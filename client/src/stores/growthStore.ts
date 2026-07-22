import { create } from 'zustand'
import { request } from '../api/client'

interface DimensionData {
  exp: number
  name: string
  color: string
  emoji: string
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
  fetchGrowth: () => Promise<void>
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
}))

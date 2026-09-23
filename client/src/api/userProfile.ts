// ── 我的资料（用户画像）API ──
import { request } from './core'

export interface UserProfileData {
  nickname: string
  role: string
  company: string
  current_project: string
  responsibilities: string
  industry: string
  work_years: number | null
  goals: string
  report_style: string
}

/** 获取用户画像 */
export async function getUserProfile(): Promise<UserProfileData> {
  const data = await request('/api/user/profile') as { profile: UserProfileData }
  return data.profile
}

/** 保存用户画像 */
export async function saveUserProfile(data: Partial<UserProfileData>): Promise<{ status: string }> {
  return request('/api/user/profile', {
    method: 'POST',
    body: JSON.stringify(data),
  }) as Promise<{ status: string }>
}

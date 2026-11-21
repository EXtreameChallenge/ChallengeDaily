import type { UserProfileData } from '../../../api/userProfile'
import { UserRound, ChevronDown, ChevronRight, Loader2, CheckCircle } from 'lucide-react'

interface ProfileSectionProps {
  profileOpen: boolean
  setProfileOpen: (v: boolean) => void
  profileForm: UserProfileData
  setProfileForm: (v: UserProfileData) => void
  profileSaving: boolean
  handleSaveProfile: () => void
}

export function ProfileSection({ profileOpen, setProfileOpen, profileForm, setProfileForm, profileSaving, handleSaveProfile }: ProfileSectionProps) {
  return (
      <section className="card space-y-4">
        <button
          onClick={() => setProfileOpen(!profileOpen)}
          className="w-full flex items-center justify-between"
        >
          <div className="flex items-center gap-2">
            <UserRound size={16} className="text-cd-green" />
            <h2 className="text-sm font-semibold text-cd-text">我的资料</h2>
            <span className="text-[10px] text-cd-text-tertiary">用于个性化 AI 分析与报告</span>
          </div>
          {profileOpen
            ? <ChevronDown size={16} className="text-cd-text-tertiary" />
            : <ChevronRight size={16} className="text-cd-text-tertiary" />}
        </button>

        {profileOpen && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-xs text-cd-text-secondary block mb-1">称呼</label>
                <input
                  type="text"
                  value={profileForm.nickname}
                  onChange={(e) => setProfileForm({ ...profileForm, nickname: e.target.value })}
                  placeholder="怎么称呼你"
                  className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-2xl px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green transition-colors"
                />
              </div>
              <div>
                <label className="text-xs text-cd-text-secondary block mb-1">角色/职位</label>
                <input
                  type="text"
                  value={profileForm.role}
                  onChange={(e) => setProfileForm({ ...profileForm, role: e.target.value })}
                  placeholder="如：前端工程师"
                  className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-2xl px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green transition-colors"
                />
              </div>
              <div>
                <label className="text-xs text-cd-text-secondary block mb-1">公司/团队</label>
                <input
                  type="text"
                  value={profileForm.company}
                  onChange={(e) => setProfileForm({ ...profileForm, company: e.target.value })}
                  placeholder="所在公司或团队"
                  className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-2xl px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green transition-colors"
                />
              </div>
              <div>
                <label className="text-xs text-cd-text-secondary block mb-1">当前项目</label>
                <input
                  type="text"
                  value={profileForm.current_project}
                  onChange={(e) => setProfileForm({ ...profileForm, current_project: e.target.value })}
                  placeholder="正在做的项目"
                  className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-2xl px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green transition-colors"
                />
              </div>
              <div>
                <label className="text-xs text-cd-text-secondary block mb-1">行业</label>
                <input
                  type="text"
                  value={profileForm.industry}
                  onChange={(e) => setProfileForm({ ...profileForm, industry: e.target.value })}
                  placeholder="如：互联网/金融"
                  className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-2xl px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green transition-colors"
                />
              </div>
              <div>
                <label className="text-xs text-cd-text-secondary block mb-1">工作年限</label>
                <input
                  type="number"
                  value={profileForm.work_years ?? ''}
                  onChange={(e) => setProfileForm({ ...profileForm, work_years: e.target.value === '' ? null : Number(e.target.value) })}
                  placeholder="如：5"
                  min={0}
                  className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-2xl px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green transition-colors"
                />
              </div>
            </div>

            <div>
              <label className="text-xs text-cd-text-secondary block mb-1">工作职责</label>
              <textarea
                value={profileForm.responsibilities}
                onChange={(e) => setProfileForm({ ...profileForm, responsibilities: e.target.value })}
                rows={2}
                placeholder="日常主要负责什么工作"
                className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-2xl px-3 py-2 text-sm focus:outline-none focus:border-cd-green transition-colors resize-none"
              />
            </div>

            <div>
              <label className="text-xs text-cd-text-secondary block mb-1">个人目标</label>
              <textarea
                value={profileForm.goals}
                onChange={(e) => setProfileForm({ ...profileForm, goals: e.target.value })}
                rows={2}
                placeholder="近期或长期想达成的目标"
                className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-2xl px-3 py-2 text-sm focus:outline-none focus:border-cd-green transition-colors resize-none"
              />
            </div>

            <div>
              <label className="text-xs text-cd-text-secondary block mb-1">AI 报告偏好风格</label>
              <select
                value={profileForm.report_style}
                onChange={(e) => setProfileForm({ ...profileForm, report_style: e.target.value })}
                className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-2xl px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green transition-colors"
              >
                <option value="">默认</option>
                <option value="concise">简洁</option>
                <option value="detailed">详细</option>
                <option value="formal">正式</option>
                <option value="casual">口语</option>
              </select>
            </div>

            <div className="flex items-center gap-3 pt-2">
              <button
                onClick={handleSaveProfile}
                disabled={profileSaving}
                className="flex items-center gap-2 px-4 py-1.5 rounded-2xl text-xs font-medium bg-cd-accent text-white hover:opacity-90 transition-opacity disabled:opacity-40"
              >
                {profileSaving ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle size={12} />}
                {profileSaving ? '保存中...' : '保存我的资料'}
              </button>
            </div>
          </div>
        )}
      </section>
  )
}



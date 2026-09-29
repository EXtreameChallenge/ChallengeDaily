/**
 * P19-3: 行业基准对比面板
 * 显示用户与同业用户的百分位对比，支持职业切换与群组排行
 */
import { useState, useEffect, useCallback } from 'react'
import {
  listBenchmarkOccupations, getBenchmarkProfile, updateBenchmarkProfile,
  compareBenchmark, listBenchmarkGroups, createBenchmarkGroup, joinBenchmarkGroup,
  getBenchmarkGroupLeaderboard,
  type BenchmarkResult, type BenchmarkProfile,
} from '../api/client'
import { useToast } from './Toast'
import { Trophy, Users, TrendingUp, Loader2, Plus } from 'lucide-react'

export default function BenchmarkPanel() {
  const toast = useToast()
  const [profile, setProfile] = useState<BenchmarkProfile | null>(null)
  const [occupations, setOccupations] = useState<Array<{ key: string; label: string }>>([])
  const [result, setResult] = useState<BenchmarkResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [comparing, setComparing] = useState(false)
  const [groups, setGroups] = useState<any[]>([])
  const [leaderboard, setLeaderboard] = useState<any>(null)
  const [showCreateGroup, setShowCreateGroup] = useState(false)
  const [newGroupName, setNewGroupName] = useState('')
  const [joinCode, setJoinCode] = useState('')

  const refresh = useCallback(async () => {
    try {
      const [occRes, profRes, groupsRes] = await Promise.all([
        listBenchmarkOccupations(),
        getBenchmarkProfile(),
        listBenchmarkGroups().catch(() => ({ groups: [] })),
      ])
      setOccupations(occRes.occupations || [])
      setProfile(profRes)
      setGroups(groupsRes.groups || [])
      if (profRes.group_code) {
        try {
          const lb = await getBenchmarkGroupLeaderboard(profRes.group_code)
          setLeaderboard(lb)
        } catch {}
      }
    } catch (err: any) {
      console.warn('基准数据加载失败:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const handleCompare = async () => {
    setComparing(true)
    try {
      const r = await compareBenchmark(7)
      setResult(r)
    } catch (err: any) {
      toast.error(err.message || '对比失败')
    } finally {
      setComparing(false)
    }
  }

  const handleOccupationChange = async (occ: string) => {
    try {
      const updated = await updateBenchmarkProfile({ occupation: occ })
      setProfile(updated)
      toast.success(`已切换到 ${occupations.find(o => o.key === occ)?.label || occ}`)
      // 自动重新对比
      setTimeout(handleCompare, 100)
    } catch (err: any) {
      toast.error(err.message || '切换失败')
    }
  }

  const handleCreateGroup = async () => {
    if (!newGroupName.trim()) {
      toast.warning('请输入群组名称')
      return
    }
    try {
      await createBenchmarkGroup(newGroupName)
      toast.success('群组已创建')
      setShowCreateGroup(false)
      setNewGroupName('')
      refresh()
    } catch (err: any) {
      toast.error(err.message || '创建失败')
    }
  }

  const handleJoinGroup = async () => {
    if (!joinCode.trim()) {
      toast.warning('请输入群组代码')
      return
    }
    try {
      await joinBenchmarkGroup(joinCode.toUpperCase())
      toast.success('已加入群组')
      setJoinCode('')
      refresh()
    } catch (err: any) {
      toast.error(err.message || '加入失败')
    }
  }

  if (loading) {
    return <div className="text-xs text-cd-text-tertiary flex items-center gap-1">
      <Loader2 size={11} className="animate-spin" /> 加载基准数据...
    </div>
  }

  const fmtPct = (v: number) => `${Math.round(v * 100)}%`
  const fmtPctile = (v: number) => `超过 ${Math.round(v)}%`

  return (
    <div className="space-y-2">
      {/* 职业类型选择 */}
      <div className="flex items-center gap-2">
        <span className="text-[11px] text-cd-text-secondary flex-shrink-0">职业：</span>
        <select
          value={profile?.occupation || 'developer'}
          onChange={(e) => handleOccupationChange(e.target.value)}
          className="flex-1 bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg px-1.5 py-0.5 text-[11px] focus:outline-none focus:border-cd-green"
        >
          {occupations.map(o => (
            <option key={o.key} value={o.key}>{o.label}</option>
          ))}
        </select>
        <button
          onClick={handleCompare}
          disabled={comparing}
          className="px-2 py-0.5 bg-cd-green text-white rounded-lg text-[11px] hover:opacity-90 disabled:opacity-40 flex items-center gap-1 flex-shrink-0"
        >
          {comparing ? <Loader2 size={10} className="animate-spin" /> : <TrendingUp size={10} />}
          对比
        </button>
      </div>

      {/* 对比结果 */}
      {result && (
        <div className="space-y-2">
          {/* 总体百分位 */}
          <div className="p-2 bg-gradient-to-br from-cd-green-light to-cd-bg-secondary border border-cd-green/30 rounded-2xl">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <Trophy size={10} className="text-cd-green" />
                <span className="text-[10px] text-cd-text-tertiary">综合效率百分位</span>
              </div>
              <span className="text-[10px] text-cd-text-secondary">{result.occupation_label}</span>
            </div>
            <div className="flex items-baseline gap-1 mt-0.5">
              <span className="text-xl font-bold text-cd-green">
                {Math.round(result.overall_percentile)}
                <span className="text-[10px] ml-0.5">%</span>
              </span>
            </div>
            <div className="text-[10px] text-cd-text-secondary mt-0.5 leading-tight">{result.overall_summary}</div>
            <div className="mt-1.5 h-1 bg-cd-bg rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-cd-green to-cd-purple rounded-full transition-all"
                style={{ width: `${result.overall_percentile}%` }}
              />
            </div>
          </div>

          {/* 各指标明细 - 2列紧凑布局 */}
          <div className="grid grid-cols-2 gap-1">
            {result.metrics.map(m => (
              <div key={m.key} className="bg-cd-bg-secondary/50 rounded-lg px-1.5 py-1">
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-[10px] text-cd-text-secondary truncate">{m.label}</span>
                  <span className="text-[10px] text-cd-text font-semibold flex-shrink-0 ml-1">
                    {m.unit === '%' ? fmtPct(m.user_value) : m.user_value}
                    <span className="text-cd-text-tertiary font-normal ml-0.5">{m.unit}</span>
                  </span>
                </div>
                <div className="h-1 bg-cd-bg rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full ${m.percentile >= 75 ? 'bg-cd-green' : m.percentile >= 50 ? 'bg-cd-purple' : 'bg-cd-text-tertiary'}`}
                    style={{ width: `${m.percentile}%` }}
                  />
                </div>
                <div className="text-[9px] text-cd-text-tertiary mt-0.5 text-right">{fmtPctile(m.percentile)}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 群组排行 */}
      <div className="pt-1.5 border-t border-cd-border space-y-1.5">
        <div className="flex items-center gap-1.5 text-[11px] font-semibold text-cd-text">
          <Users size={10} className="text-cd-green" />
          专注群组
        </div>

        {profile?.group_code && leaderboard ? (
          <div className="space-y-1">
            <div className="flex items-center justify-between text-[10px]">
              <span className="text-cd-text">{leaderboard.name}</span>
              <span className="text-cd-text-tertiary">{leaderboard.members_count}人</span>
            </div>
            {leaderboard.leaderboard && leaderboard.leaderboard.length > 0 ? (
              <div className="space-y-0.5">
                {leaderboard.leaderboard.slice(0, 3).map((m: any, i: number) => (
                  <div key={i} className={`flex items-center gap-1.5 px-1.5 py-1 rounded-lg text-[10px] ${
                    i === 0 ? 'bg-cd-green-light' : 'bg-cd-bg-secondary'
                  }`}>
                    <span className={`w-4 text-center font-bold flex-shrink-0 ${
                      i === 0 ? 'text-cd-green' : i === 1 ? 'text-cd-purple' : 'text-cd-text-tertiary'
                    }`}>{i + 1}</span>
                    <span className="text-cd-text flex-1 truncate">{m.name}</span>
                    <span className="text-cd-green font-semibold flex-shrink-0">{Math.round(m.score)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-[10px] text-cd-text-tertiary">群组暂无成员数据</div>
            )}
          </div>
        ) : (
          <div className="space-y-1.5">
            <div className="flex gap-1">
              <input
                type="text" placeholder="输入群组代码" value={joinCode}
                onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
                maxLength={8}
                className="flex-1 bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg px-1.5 py-0.5 text-[11px] font-mono"
              />
              <button onClick={handleJoinGroup}
                className="px-2 py-0.5 bg-cd-bg-secondary border border-cd-border rounded-lg text-[11px] text-cd-text hover:bg-cd-hover">
                加入
              </button>
            </div>
            {showCreateGroup ? (
              <div className="flex gap-1">
                <input
                  type="text" placeholder="群组名称" value={newGroupName}
                  onChange={(e) => setNewGroupName(e.target.value)}
                  className="flex-1 bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg px-1.5 py-0.5 text-[11px]"
                />
                <button onClick={handleCreateGroup}
                  className="px-2 py-0.5 bg-cd-green text-white rounded-lg text-[11px] hover:opacity-90">
                  创建
                </button>
                <button onClick={() => setShowCreateGroup(false)}
                  className="px-1.5 py-0.5 text-cd-text-tertiary text-[11px]">
                  取消
                </button>
              </div>
            ) : (
              <button onClick={() => setShowCreateGroup(true)}
                className="text-[11px] text-cd-green hover:opacity-80 flex items-center gap-1">
                <Plus size={10} /> 创建新群组
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// 幕布接入共享类型与状态元数据（轮11 Settings 分区拆分）
export type MubuStatus = 'idle' | 'syncing' | 'synced' | 'cookie_invalid' | 'error' | 'unknown'

export interface MubuStatusInfo {
  doc_count: number
  last_sync: string | null
  status?: string
  cookie_valid?: boolean
  message?: string
}

export interface MubuDoc {
  id: string | number
  title: string
  url?: string
  updated_at?: string
}

export const MUBU_STATUS_META: Record<MubuStatus, { label: string; className: string }> = {
  idle: { label: '未同步', className: 'bg-cd-bg-secondary text-cd-text-tertiary' },
  syncing: { label: '同步中', className: 'bg-cd-green-light text-cd-green' },
  synced: { label: '已同步', className: 'bg-cd-green-light text-cd-green' },
  cookie_invalid: { label: 'Cookie 失效', className: 'bg-cd-red-light text-cd-red' },
  error: { label: '错误', className: 'bg-cd-red-light text-cd-red' },
  unknown: { label: '未知', className: 'bg-cd-bg-secondary text-cd-text-tertiary' },
}

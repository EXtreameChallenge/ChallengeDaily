// ── P0-3: 报告模板管理 API ──
import { request } from './core'

export interface ReportTemplate {
  id: number
  name: string
  description: string
  content_md: string
  is_default: boolean
  created_at: string
  updated_at: string
}

export interface ReportTemplateInput {
  name: string
  description?: string
  content_md: string
  is_default?: boolean
}

/** 获取全部报告模板（默认模板排在最前） */
export async function getReportTemplates(): Promise<ReportTemplate[]> {
  const data = await request('/api/report/templates')
  return (data as { templates: ReportTemplate[] }).templates || []
}

/** 新建模板，返回新模板 id */
export async function createReportTemplate(data: ReportTemplateInput): Promise<{ id: number }> {
  return request('/api/report/templates', {
    method: 'POST',
    body: JSON.stringify(data),
  }) as Promise<{ id: number }>
}

/** 更新模板 */
export async function updateReportTemplate(id: number, data: ReportTemplateInput): Promise<{ status: string }> {
  return request(`/api/report/templates/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }) as Promise<{ status: string }>
}

/** 删除模板 */
export async function deleteReportTemplate(id: number): Promise<{ status: string }> {
  return request(`/api/report/templates/${id}`, { method: 'DELETE' }) as Promise<{ status: string }>
}

/** 设为默认模板 */
export async function setDefaultTemplate(id: number): Promise<{ status: string }> {
  return request(`/api/report/templates/${id}/default`, { method: 'POST' }) as Promise<{ status: string }>
}

/** 用今日数据预览渲染结果 */
export async function previewTemplate(content_md: string, date?: string): Promise<{ content: string }> {
  return request('/api/report/templates/preview', {
    method: 'POST',
    body: JSON.stringify({ content_md, ...(date ? { date } : {}) }),
  }) as Promise<{ content: string }>
}

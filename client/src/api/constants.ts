// ── 全局常量：分类配色、分类列表、番茄钟尺寸 ──

/** 分类配色映射 */
export const CATEGORY_COLORS: Record<string, string> = {
  '开发': '#00B894',
  '会议': '#E54D42',
  '沟通': '#5B8DEF',
  '文档': '#A29BFE',
  '测试': '#F0A030',
  '设计': '#FD79A8',
  '运维': '#00CEC9',
  '数据分析': '#55EFC4',
  '学习': '#6C5CE7',
  '管理': '#B2BEC3',
  '产品': '#635BFF',
  '生活': '#F0C040',
  '其他': '#9999B0',
}

/** 12大分类 */
export const CATEGORIES = [
  '开发', '会议', '沟通', '文档', '测试', '设计',
  '运维', '数据分析', '学习', '管理', '产品', '生活',
]

/** 番茄钟大小配置 */
export interface PomodoroSizeConfig {
  work: number       // 工作分钟
  short_break: number  // 短休息分钟
  long_break: number   // 长休息分钟
}

export const POMODORO_SIZES: Record<string, PomodoroSizeConfig> = {
  big:   { work: 25, short_break: 5, long_break: 15 },
  small: { work: 20, short_break: 10, long_break: 15 },
}
export const LONG_BREAK_INTERVAL = 4

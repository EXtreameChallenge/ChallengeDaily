# ChallengeDaily 工作台演进 Round 2 计划

> ⚠️ **本文件归属：第 2 轮（Round 2）工作台演进**
> **生成时间**: 2026-08-05
> **适用范围**: 仅限本轮执行，后续轮次请创建新文件（如 `WORKBENCH_LOOP_PLAN_R3.md`）
> **Agent 须知**: 如果你是在新一轮优化中读到本文件，请勿将其当作当前任务执行。本文件记录的是第 2 轮已完成的工作，仅供历史参考。请创建新的计划文件。
> **参见**: `ROUND_CONVENTION.md` 了解轮次管理规范

> **模式**: 自驱动循环执行（Read → Execute → Verify → Update → Repeat）
> **目标**: 在 Round 1 基础上深化工作台体验，增强数据可视化、智能联动和用户引导

---

## R2-1: Focus Score 历史日历热力图

### [ ] R2-1-1: 后端新增 Focus Score 日历数据 API
- **文件**: `routes/stats.py`
- **操作**: 新增 `/api/stats/focus-score/calendar?months=3` 端点，返回近 N 月每日 Focus Score
- **验证**: API 返回 `[{date, score, grade}]` 列表

### [ ] R2-1-2: 前端 Focus Score 日历热力图组件
- **文件**: `client/src/components/FocusScoreCalendar.tsx`（新增）
- **操作**: GitHub 风格热力图，颜色映射 S/A/B/C/D 等级
- **验证**: 组件渲染日历网格，颜色随分数变化

### [ ] R2-1-3: Overview 页面集成日历热力图
- **文件**: `client/src/pages/Overview.tsx`
- **操作**: 在 FocusScoreRing 下方添加日历热力图
- **验证**: Overview 页面显示热力图

---

## R2-2: AI 场景基于路由自动切换

### [ ] R2-2-1: 前端 AIChat 场景自动联动
- **文件**: `client/src/pages/AIChat.tsx`
- **操作**: 根据用户来源路由自动切换场景（从 Timeline 来→时间分析，从 Diary 来→日记反思）
- **验证**: 从不同页面跳转到 AIChat 时场景自动切换

---

## R2-3: Sprint 目标设定功能

### [ ] R2-3-1: 后端 Sprint 目标 API
- **文件**: `routes/week_plan.py`
- **操作**: 新增 `GET/POST /api/week-plan/sprint-goal/<week_start>` 端点
- **验证**: API 支持读取和设置 Sprint 目标文本

### [ ] R2-3-2: 前端 Sprint 目标编辑
- **文件**: `client/src/pages/plan-views/SprintView.tsx`
- **操作**: SprintView 顶部增加可编辑的 Sprint 目标卡片
- **验证**: 可输入目标并保存

---

## R2-4: 规则模板可视化预览

### [ ] R2-4-1: WorkflowEditor 模板预览增强
- **文件**: `client/src/pages/WorkflowEditor.tsx`
- **操作**: 模板卡片增加 IF-THEN 预览和触发条件可视化标签
- **验证**: 模板卡片展示完整条件+动作预览

---

## R2-5: 宠物点击展示 Focus Score 迷你趋势

### [ ] R2-5-1: Pet 点击弹出 Focus Score 趋势小图
- **文件**: `client/src/components/Pet.tsx`
- **操作**: 点击宠物时显示 7 天 Focus Score 迷你折线图气泡
- **验证**: 点击宠物弹出趋势图

---

## R2-6: 工作流编辑器空状态引导优化

### [ ] R2-6-1: 空状态引导 + 快速入门
- **文件**: `client/src/pages/WorkflowEditor.tsx`
- **操作**: 无规则时展示引导卡片（3 步快速入门 + 模板推荐）
- **验证**: 空状态展示引导

---

## R2-7: Dashboard Widget 默认布局优化

### [ ] R2-7-1: Widget 默认布局调整
- **文件**: `client/src/pages/Dashboard.tsx`
- **操作**: 优化默认 Widget 排列顺序和可见性
- **验证**: 首次进入 Dashboard 布局合理

---

## 最终验证

### [ ] V-1: TypeScript 编译零错误
### [ ] V-2: Python 编译零错误
### [ ] V-3: API 运行时测试
### [ ] V-4: 生成 WORKBENCH_FINAL_REPORT_R2.md

---

## 完成状态: 0/12
## 目标状态: 12/12

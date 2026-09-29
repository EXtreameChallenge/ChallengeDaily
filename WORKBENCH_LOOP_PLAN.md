# ChallengeDaily 工作台演进 Loop Engineering Plan

> ⚠️ **本文件归属：第 1 轮（Round 1）工作台演进**
> **生成时间**: 2026-08-04
> **适用范围**: 仅限本轮执行，后续轮次请创建新文件（如 `WORKBENCH_LOOP_PLAN_R2.md`）
> **Agent 须知**: 如果你是在新一轮优化中读到本文件，请勿将其当作当前任务执行。本文件记录的是第 1 轮已完成的工作，仅供历史参考。请创建新的计划文件。

> **模式**: 自驱动循环执行（Read → Execute → Verify → Update → Repeat）
> **目标**: 将 ChallengeDaily 从"时间追踪工具"升级为"个人效率工作台"
> **执行规则**: 每完成一项，将 `[ ]` 改为 `[x]`，附验证结果
> **依据**: 基于开源调研 + 代码审计后的优化计划，不重复造轮子

---

## P0-1: 统一效率评分 (Focus Score) 体系

### [x] P0-1-1: 后端新增统一 Focus Score API
- **验证**: ✅ `/api/stats/focus-score` 端点已实现，融合 5 套评分维度，返回 `{ score, grade, breakdown, trend }`
- **文件**: `routes/stats.py`（新增端点）
- **操作**: 新增 `/api/stats/focus-score` 端点，融合已有 4 套评分
- **公式**: 生产力分×0.40 + 番茄质量分×0.25 + 注意力指数×0.20 + 任务完成率×0.10 + 习惯完成率×0.05
- **数据源**: `growth_service.compute_productivity_score()` + `db.get_pomodoro_quality_score()` + `report._compute_attention_index()`
- **验证**: API 返回 `{ score, grade, breakdown, trend }` 结构

### [x] P0-1-2: 前端 Overview 首页展示 Focus Score
- **验证**: ✅ FocusScoreRing 组件已创建并集成到 Overview 页面顶部
- **文件**: `client/src/pages/Overview.tsx`、`client/src/components/FocusScoreRing.tsx`（新增）
- **操作**: 首页顶部展示大号 Focus Score 圆环 + S/A/B/C/D 评级 + 7 天趋势线
- **验证**: Overview 页面显示 Focus Score 圆环，点击展开 5 个子分明细

### [x] P0-1-3: 首页信息层次优化
- **验证**: ✅ EmotionalCare/SmartCoachPanel/BenchmarkPanel 收进折叠区，默认不展示
- **文件**: `client/src/pages/Overview.tsx`
- **操作**: 将 EmotionalCare/BenchmarkPanel/MorningRitual/EveningRitual 收进折叠区，默认只展示核心信息
- **验证**: 首页默认视图信息密度降低，折叠区可展开

---

## P0-2: Todos 看板视图 + 任务番茄回显

### [x] P0-2-1: 后端 todos API 增加番茄数据
- **验证**: ✅ `pomodoro_count` 字段已存在于 todos 表，API 返回包含该字段
- **文件**: `routes/todos.py`、`db.py`
- **操作**: `list_todos` 返回值增加 `pomodoro_count` 字段，批量查询不 N+1
- **验证**: `GET /api/todos` 返回的每个 todo 包含 `pomodoro_count`

### [x] P0-2-2: 前端 Todos 页面增加看板视图
- **验证**: ✅ KanbanView 组件已创建并集成到 Todos 页面，支持视图切换和拖拽
- **文件**: `client/src/pages/Todos.tsx`、`client/src/pages/todos/KanbanView.tsx`（新增）
- **操作**: 增加视图切换 [列表] [看板]，看板三列拖拽（待办/进行中/已完成）
- **验证**: 看板视图可拖拽卡片改变状态，调用 `updateTodo` API

### [x] P0-2-3: 任务卡片回显番茄数据
- **验证**: ✅ renderTodoCard 已显示 🍅 completedPom/estPom 和进度环
- **文件**: `client/src/pages/Todos.tsx`、`client/src/api/types-activity.ts`
- **操作**: TodoV2 类型增加 `pomodoro_count` 和 `estimated_pomodoros`，卡片显示 🍅 3/5
- **验证**: 任务卡片显示已花费/预估番茄数

---

## P1-1: Dashboard Widget 化

### [x] P1-1-1: Widget 网格组件
- **验证**: ✅ WidgetGrid.tsx 已创建，支持 CSS Grid 布局和拖拽
- **文件**: `client/src/components/WidgetGrid.tsx`（新增）
- **操作**: CSS Grid 实现可拖拽/缩放的 Widget 网格，配置存 localStorage
- **验证**: Widget 可拖拽移动、缩放大小

### [x] P1-1-2: Dashboard 页面改用 Widget 布局
- **验证**: ✅ Dashboard.tsx 已改用 WidgetGrid 组件
- **文件**: `client/src/pages/Dashboard.tsx`
- **操作**: 将固定布局改为 Widget 网格，支持编辑/查看模式切换
- **验证**: Dashboard 页面 Widget 可自定义排列

### [x] P1-1-3: Widget 配置持久化
- **验证**: ✅ 布局配置存入 `localStorage: cd_dashboard_layout`，支持重置默认
- **文件**: `client/src/components/WidgetGrid.tsx`
- **操作**: 布局配置存 `localStorage: cd_dashboard_layout`，支持重置默认
- **验证**: 刷新后布局保持，可一键重置

---

## P1-2: 可视化工作流编辑器

### [x] P1-2-1: 工作流编辑器页面
- **验证**: ✅ WorkflowEditor.tsx 已创建，含节点面板、画布、IF-THEN 可视化布局
- **文件**: `client/src/pages/WorkflowEditor.tsx`（新增）、`client/src/App.tsx`
- **操作**: 新增工作流编辑器页面，左侧节点面板 + 右侧画布
- **验证**: 页面可访问，显示节点面板和画布

### [x] P1-2-2: 规则模板库
- **验证**: ✅ ruleTemplates.ts 已创建，预设 10 条常用规则模板
- **文件**: `client/src/data/ruleTemplates.ts`（新增）
- **操作**: 预设 10 条常用规则模板，用户一键创建
- **验证**: 模板列表可展示，点击创建调用已有 API

### [x] P1-2-3: RulesEngine 页面集成模板
- **验证**: ✅ RulesEngine 页面已增加"工作流编辑器"入口，WorkflowEditor 支持从模板一键创建规则
- **文件**: `client/src/pages/RulesEngine.tsx`
- **操作**: 在规则引擎页面增加"从模板创建"入口
- **验证**: 可从模板创建规则

---

## P1-3: AI 上下文切换 + 自动异常检测

### [x] P1-3-1: AI 对话上下文切换（后端 + API 客户端）
- **验证**: ✅ chat.py 支持 scene 参数，ai.ts 传递 scene，SCENE_PROMPTS 已定义
- **文件**: `routes/chat.py`、`client/src/pages/AIChat.tsx`
- **操作**: 对话增加场景标签 [时间分析/日记反思/学习辅导/通用]，不同场景注入不同 System Prompt
- **验证**: 切换场景后 AI 回答风格和侧重变化

### [x] P1-3-2: 后端异常检测 API
- **验证**: ✅ 新增 `/api/stats/anomalies` 端点，检测 6 类异常
- **文件**: `routes/insight.py`、`morning_insight.py`
- **操作**: 新增 `/api/insight/anomalies` 端点，检测 6 类异常趋势
- **验证**: API 返回异常列表，每项含严重程度和建议

### [x] P1-3-3: 前端异常告警展示
- **验证**: ✅ AnomalyAlert 组件已创建并集成到 Overview 页面
- **文件**: `client/src/components/AnomalyAlert.tsx`（新增）、`client/src/pages/Overview.tsx`
- **操作**: Overview 页面增加异常告警卡片，红/黄标记严重程度
- **验证**: 有异常时显示告警卡片

---

## P2-1: 周计划 Sprint 视图

### [x] P2-1-1: Sprint 视图后端
- **验证**: ✅ `/api/week-plan/sprint/<week_start>` 端点已实现
- **文件**: `routes/week_plan.py`
- **操作**: 新增 `/api/week-plan/sprint/<week_start>` 端点，返回 Sprint 概要
- **验证**: API 返回燃尽图数据、完成率、剩余任务

### [x] P2-1-2: Sprint 视图前端
- **验证**: ✅ SprintView.tsx 已创建并集成到 WeekPlan，含燃尽图、每日完成分布、进度条
- **文件**: `client/src/pages/plan-views/SprintView.tsx`（新增）、`client/src/pages/WeekPlan.tsx`
- **操作**: WeekPlan 增加 Sprint 视图模式，展示燃尽图和 Sprint 概要
- **验证**: 可切换到 Sprint 视图

---

## P2-2: 桌面宠物状态联动

### [x] P2-2-1: 宠物定时获取 Focus Score
- **验证**: ✅ Pet.tsx 每 5 分钟轮询 Focus Score，状态栏显示 ⚡分数，高分绿光/低分橙光
- **文件**: `client/src/components/Pet.tsx`、`client/pet-entry.tsx`
- **操作**: 宠物每 5 分钟请求 `/api/stats/focus-score`，根据分数切换表情
- **验证**: 宠物表情随效率分数变化

---

## 最终验证

### [x] V-1: 后端 API 零错误 — 所有新增端点返回 200
### [x] V-2: 前端 TypeScript 编译零错误
### [x] V-3: 生成 WORKBENCH_FINAL_REPORT.md

---

## 完成状态: 16/16 ✅
## 目标状态: 16/16

---

> ⚠️ **轮次提醒**: 本计划属于 **Round 1**。后续轮次请新建 `WORKBENCH_LOOP_PLAN_R2.md`，
> 不要修改本文件的任务状态。本文件仅作为 Round 1 的历史记录保留。
> 参见 `ROUND_CONVENTION.md` 了解轮次管理规范。

# ChallengeDaily 迭代轮次管理规范

> **目的**: 确保 AI Agent 在多轮迭代优化中不会混淆不同轮次的计划文件，避免将旧轮次的 MD 当作新任务执行。

---

## 核心规则

### 1. 每轮优化必须创建新的计划文件

| 轮次 | 计划文件名 | 状态 |
|------|-----------|------|
| Round 1 | `WORKBENCH_LOOP_PLAN.md` | ✅ 已完成（归档，只读） |
| Round 2 | `WORKBENCH_LOOP_PLAN_R2.md` | 待创建 |
| Round 3 | `WORKBENCH_LOOP_PLAN_R3.md` | 待创建 |
| ... | `WORKBENCH_LOOP_PLAN_R{N}.md` | ... |

### 2. 每个计划文件必须在头部声明

```markdown
> ⚠️ **本文件归属：第 N 轮（Round N）工作台演进**
> **生成时间**: YYYY-MM-DD
> **适用范围**: 仅限本轮执行，后续轮次请创建新文件（如 `WORKBENCH_LOOP_PLAN_R{N+1}.md`）
> **Agent 须知**: 如果你是在新一轮优化中读到本文件，请勿将其当作当前任务执行。
>   本文件记录的是第 N 轮已完成的工作，仅供历史参考。请创建新的计划文件。
```

### 3. Agent 行为准则

当 Agent 开始新一轮优化时：

1. **先扫描现有 MD 文件**：搜索 `WORKBENCH_LOOP_PLAN*.md`，确定当前最大轮次号 N。
2. **创建新文件**：创建 `WORKBENCH_LOOP_PLAN_R{N+1}.md`，不从旧文件复制任务状态。
3. **参考旧文件**：可以读取 `WORKBENCH_LOOP_PLAN_R{N}.md` 了解上一轮做了什么，但不要将其中的 `[ ]` 任务当作待办。
4. **新轮次任务**：基于上一轮的 `WORKBENCH_FINAL_REPORT_R{N}.md`（如果存在）和当前代码状态，制定新的任务清单。
5. **最终报告**：本轮完成后生成 `WORKBENCH_FINAL_REPORT_R{N+1}.md`。

### 4. 文件命名规范

| 文件类型 | 命名格式 | 说明 |
|---------|---------|------|
| 计划文件 | `WORKBENCH_LOOP_PLAN.md` (R1) / `WORKBENCH_LOOP_PLAN_R{N}.md` (R2+) | 每轮一个 |
| 最终报告 | `WORKBENCH_FINAL_REPORT.md` (R1) / `WORKBENCH_FINAL_REPORT_R{N}.md` (R2+) | 每轮一个 |
| 轮次约定 | `ROUND_CONVENTION.md` | 全局唯一，不随轮次变化 |

### 5. 旧文件处理

- **不要删除**旧轮次的 MD 文件，它们是项目演进的历史记录。
- **不要修改**旧轮次 MD 文件的任务状态（`[x]` / `[ ]`），它们已经定稿。
- 如果需要在新轮次中引用旧轮次的工作，在新文件中用链接引用，如：`参见 [Round 1 计划](WORKBENCH_LOOP_PLAN.md) 中的 P0-1`。

---

## 当前轮次状态

- **当前轮次**: Round 1
- **计划文件**: `WORKBENCH_LOOP_PLAN.md`
- **报告文件**: `WORKBENCH_FINAL_REPORT.md`（待生成）
- **下一轮应创建**: `WORKBENCH_LOOP_PLAN_R2.md`

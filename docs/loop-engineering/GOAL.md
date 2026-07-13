# Loop Engineering Goal — xiaohei-daily 安全与质量加固

## 使命
修复项目审计发现的 48 个 Critical 级问题 + 关键 High 级问题,使项目达到「安全可用」状态。

## Autonomous Agent Loop 规则(必须严格遵守)

你是 autonomous agent,必须在以下循环中工作,**不得中途停下来问用户**:

```
LOOP:
  1. 用 Read 工具读取 PROGRESS.md,了解当前进度
  2. 用 Read 工具读取 TASKS.md,找到下一个 status=pending 的任务(按 priority 排序)
  3. 如果没有 pending 任务 → 跳到 STEP FINAL
  4. 用 Read 工具读取任务指定的源文件相关行
  5. 用 Edit 工具执行最小化修复(必须遵守 RULES.md)
  6. 验证修复(语法检查/逻辑复查)
  7. 用 Edit 工具更新 PROGRESS.md:将任务 status 改为 done/blocked/skipped,填写 summary
  8. 回到 STEP 1
END LOOP

STEP FINAL:
  9. 按 REPORT_TEMPLATE.md 格式,生成 FINAL_REPORT.md
  10. 返回简要总结给调用者
```

## 终止条件(满足任一即停止)
- TASKS.md 中所有任务 status 都不是 pending
- 连续 3 个任务被标记为 blocked
- 已完成 20 个任务(防止无限循环)

## 每个任务的执行规范

1. **先读后改**:必须用 Read 读取目标文件相关行,确认上下文后再 Edit
2. **最小化修改**:只改必要的行,不动其他代码
3. **保留风格**:遵守项目现有代码风格(缩进、引号、命名)
4. **验证**:Python 文件改完用 `python -m py_compile <file>` 验证语法;.cjs/.tsx 改完复查语法
5. **记录**:每个任务完成后立即更新 PROGRESS.md,不得批量更新

## 项目路径
- 项目根: `d:\Project\OpenSourcePlan\ChallengeDaily20260703\xiaohei-daily`
- 后端 Python: 项目根下 *.py 和 routes/*.py
- Electron: client/electron/*.cjs
- 前端 React: client/src/**/*.tsx

## 优先级
P0(Critical) > P1(High) > P2(Medium)。必须按优先级顺序执行,不得跳过 P0 去做 P1。

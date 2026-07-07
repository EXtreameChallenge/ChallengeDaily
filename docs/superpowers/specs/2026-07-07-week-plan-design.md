# 周计划与任务分配设计文档

**日期**: 2026-07-07
**状态**: 已确认设计，待实现
**关联产品**: GoalDay（周计划左右分栏+拖拽分配）、番茄ToDo（数据统计可视化）、本项目（AI 深度分析）

## 一、背景与目标

### 1.1 痛点
当前 `todos` 表是**扁平结构**，所有待办一视同仁：
- 无"月目标→周任务→日执行"层级
- 无"分配到某天"概念（`due_date` 字段存在但未使用）
- 无法一屏看全周任务分布
- 番茄钟与待办完全脱钩（`pomodoro_sessions` 无 `todo_id` 外键）

### 1.2 目标
融合 GoalDay 的**纵向左右分栏拖拽**与番茄ToDo 的**数据驱动统计**，构建：
- **三级任务层级**：月任务 → 周任务 → 日任务
- **周计划主视图**：左待分配（虚线+暖色） + 右七天纵向列（实线+冷色）
- **底部数据条**：番茄ToDo 风格专注柱状图 + 完成率 + 深度 + 中断 + 连续天数
- **点击任务卡片**：打开详情浮层（含进度、开始专注、移至按钮）

## 二、设计决策（已确认）

| 决策项 | 选择 | 说明 |
|--------|------|------|
| 周计划布局 | E 纵向左右分栏 | 完全 GoalDay 原味 |
| 待分配视觉区分 | 虚线边框+暖色调 | 金色虚线+暖黑底(#1a1410)+`⬚ 未安排`标签 |
| 周末处理 | 分开两列显示 | 降透明度+😴 图标 |
| 视图切换 | 月/周/日三视图 | 月任务→周任务→日任务三级层级 |
| 点击卡片行为 | 打开详情浮层 | 含进度环、开始专注、移至按钮 |
| 数据条 | 番茄ToDo 风格 | 专注柱状图+完成率+深度+中断+连续天数 |

## 三、数据模型

### 3.1 SQLite Schema 变更（V18→V20）

> ⚠️ SQLite 的 `ALTER TABLE ADD COLUMN` 不支持 IF NOT EXISTS，会抛 "duplicate column name"。
> 迁移时用 Python 端 `PRAGMA table_info(todos)` 检查列是否存在，缺失才 ADD。
> 索引使用 `CREATE INDEX IF NOT EXISTS` 是安全的。

**V18: 扩展 todos 表，增加层级与分配字段**

```python
# Python 端安全迁移逻辑
existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(todos)").fetchall()}
new_cols = {
    'parent_id': 'INTEGER',
    'task_level': "TEXT DEFAULT 'day'",
    'assigned_date': 'TEXT',
    'week_start': 'TEXT',
    'month_key': 'TEXT',
    'color': "TEXT DEFAULT ''",
}
for col, typedef in new_cols.items():
    if col not in existing_cols:
        conn.execute(f"ALTER TABLE todos ADD COLUMN {col} {typedef}")

# parent_id: 父任务ID（周任务指向月任务，日任务指向周任务）
# task_level: month | week | day
# assigned_date: 分配到哪天（YYYY-MM-DD），仅 day 级使用
# week_start: 所属周起始日（YYYY-MM-DD，固定周一），仅 week 级使用
# month_key: 所属月份（YYYY-MM），仅 month 级使用

conn.executescript("""
    CREATE INDEX IF NOT EXISTS idx_todos_parent ON todos(parent_id);
    CREATE INDEX IF NOT EXISTS idx_todos_assigned ON todos(assigned_date);
    CREATE INDEX IF NOT EXISTS idx_todos_week ON todos(week_start);
    CREATE INDEX IF NOT EXISTS idx_todos_month ON todos(month_key);
    CREATE INDEX IF NOT EXISTS idx_todos_level ON todos(task_level);
""")
```

**V19: 番茄钟关联待办（修复历史脱钩）**

```python
existing_cols_pomodoro = {row[1] for row in conn.execute("PRAGMA table_info(pomodoro_sessions)").fetchall()}
if 'todo_id' not in existing_cols_pomodoro:
    conn.execute("ALTER TABLE pomodoro_sessions ADD COLUMN todo_id INTEGER")  -- 关联的日任务ID（可空）
conn.executescript("CREATE INDEX IF NOT EXISTS idx_pomodoro_todo ON pomodoro_sessions(todo_id);")
```

**V20: 周计划元数据表（可选，用于周目标/月目标描述）**

```sql
CREATE TABLE IF NOT EXISTS plan_meta (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_type       TEXT NOT NULL,        -- month | week
    plan_key        TEXT NOT NULL,        -- YYYY-MM 或 YYYY-MM-DD（周起始）
    title           TEXT DEFAULT '',      -- 周期标题（如"11月：季度冲刺"）
    goal            TEXT DEFAULT '',      -- 周期目标描述
    created_at      TEXT DEFAULT (datetime('now','localtime')),
    updated_at      TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(plan_type, plan_key)
);
```

### 3.2 字段语义说明

**task_level 三级**：
- `month`: 月任务，`month_key='2026-07'`，无 `assigned_date`/`week_start`
- `week`: 周任务，`week_start='2026-07-07'`（周一），`parent_id` 指向月任务（可空）
- `day`: 日任务，`assigned_date='2026-07-09'`，`parent_id` 指向周任务（可空）

**待分配区定义**：`task_level='day' AND assigned_date IS NULL`（已创建但未分配到天的日任务）

**历史数据兼容**：现有 todos 记录默认 `task_level='day'`、`assigned_date=NULL`（进入待分配区）

## 四、后端 API 设计

### 4.1 新增路由文件 `routes/week_plan.py`

Blueprint 前缀：`/api/week-plan`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/week-plan/month/<month_key>` | 获取月任务及其下所有周任务进度 |
| GET | `/api/week-plan/week/<week_start>` | 获取周任务及其下所有日任务（七日看板数据） |
| GET | `/api/week-plan/unassigned` | 获取待分配区任务（task_level='day' AND assigned_date IS NULL） |
| POST | `/api/week-plan/assign` | 拖拽分配，body: `{todo_id, assigned_date}` 或 `{todo_id, week_start, task_level}` |
| POST | `/api/week-plan/unassign` | 移回待分配，body: `{todo_id}` 清空 assigned_date |
| POST | `/api/week-plan/split` | 月任务拆解为周任务，body: `{parent_id, title, week_start}` |
| PUT | `/api/week-plan/meta` | 更新周/月元数据（标题、目标） |
| GET | `/api/week-plan/stats?range=week&date=YYYY-MM-DD` | 本周数据条统计（专注柱状图+完成率+深度+中断+连续） |

### 4.2 现有路由扩展

**`routes/todos.py` 扩展**：
- `POST /api/todos` 增加 `task_level`、`parent_id`、`assigned_date`、`week_start`、`month_key` 字段
- `GET /api/todos` 增加 `level`、`week_start`、`assigned_date`、`parent_id` 查询参数
- 修复 `db.insert_todo` SQL 占位符 bug（9 列 8 个 `?`）

**`routes/pomodoro.py` 扩展**：
- `POST /api/pomodoro/start` 增加 `todo_id` 字段
- `POST /api/pomodoro/stop` 完成时调用 `db.update_todo_progress(todo_id, duration_min)` 自动回写进度

### 4.3 db.py 新增函数

```python
def get_month_tasks(month_key) -> list[dict]           # 月任务+子任务进度
def get_week_tasks(week_start) -> dict                  # 周任务+七日日任务
def get_unassigned_todos() -> list[dict]                # 待分配区
def assign_todo(todo_id, assigned_date=None, week_start=None, task_level='day') -> bool
def unassign_todo(todo_id) -> bool
def split_task(parent_id, title, week_start, task_level='week') -> int
def get_week_plan_stats(week_start) -> dict             # 本周数据条统计
def get_month_plan_stats(month_key) -> dict             # 本月数据条统计
def update_plan_meta(plan_type, plan_key, title, goal) -> bool
```

## 五、前端架构

### 5.1 新增页面 `client/src/pages/WeekPlan.tsx`

**组件结构**：
```
WeekPlan.tsx
├── ViewSwitcher          # 月/周/日视图切换
├── MonthView             # 月视图（4-5周网格，月任务分布到周）
├── WeekView (主视图)     # 周视图
│   ├── UnassignedPanel   # 左：待分配区（虚线+暖色，180px 固定宽）
│   ├── SevenDayColumns   # 右：七天纵向列（每列默认展开）
│   │   └── DayColumn     # 单列（含今日高亮、负载警示、周末降透明）
│   └── WeekDataBar       # 底部：番茄ToDo 风格数据条
├── DayView               # 日视图（单日详情+专注执行，与 Focus 联动）
└── TaskDetailModal       # 点击卡片打开的详情浮层
```

### 5.2 拖拽实现

使用原生 HTML5 Drag and Drop API（无需额外依赖）：
- `draggable` 属性 + `onDragStart`/`onDragOver`/`onDrop` 事件
- 待分配区卡片拖拽到某天列 → 调用 `POST /api/week-plan/assign`
- 七天列间卡片拖拽 → 调用 `POST /api/week-plan/assign` 更新 `assigned_date`
- 拖回待分配区 → 调用 `POST /api/week-plan/unassign`

### 5.3 视觉规范

**待分配区（左）**：
- 背景：`#1a1410`（暖黑）
- 边框：`1.5px dashed #F0C04066`（金色虚线）
- 卡片标签：`⬚ 未安排`（金色 9px）
- 卡片背景：`#2a2218`（暖深灰）
- 宽度：180px 固定

**七天列（右）**：
- 背景：`#1E1E1E`（冷黑）
- 边框：`1px solid #2D2D2D`（实线）
- 卡片背景：`#2D2D2D`（冷深灰）
- 卡片左边色条：按优先级（红/橙/黄/绿/灰）
- 今日列：`2px solid #7B68EE` 边框 + `#7B68EE11` 背景
- 周末列：`opacity: 0.6` + 😴 图标
- 负载警示：>180min 显示红色 ⚠

**底部数据条**：
- 专注柱状图：7天对比，紫色 `#7B68EE`
- 指标：专注时长、完成率、深度工作、中断次数、连续天数
- 切换：周/月/全部

### 5.4 详情浮层 `TaskDetailModal`

点击卡片打开，内容：
- 任务标题（可编辑）
- 优先级、分类、模式
- 进度环（`progress_min / target_min`）
- 已专注分钟数、番茄钟数
- 操作按钮：▶ 开始专注（跳转 Focus 页并预填 todo_id）、⇄ 移至（选择目标日期）、✓ 完成、🗑 删除

## 六、与现有功能的集成

### 6.1 Focus 页扩展
- `Focus.tsx` 增加任务选择下拉（从今日日任务加载）
- `startPomodoro` 传 `todo_id`
- 完成时自动调用 `POST /api/todos/{todo_id}/add-progress`

### 6.2 Overview 页扩展
- Overview 顶部增加"今日任务"卡片，显示今日 `assigned_date` 的 day 任务
- 显示今日完成率进度条

### 6.3 Sidebar 导航
- 新增导航项：`{ to: '/week-plan', icon: CalendarDays, label: '周计划' }`
- 位置：放在"待办清单"之前（更顶层）

### 6.4 报表系统
- 周报生成时追加"本周任务完成情况"板块（从 `todos` 表统计）

## 七、错误处理与边界

### 7.1 拖拽边界
- 月任务不能拖到日列（只能先拆解为周任务）→ UI 端 `draggable` 仅 week/day 级开启
- 周任务可以拖到日列（自动转为日任务，设 `task_level='day'` + `assigned_date`）
- 跨周拖拽：更新 `week_start` + `assigned_date`
- 拖拽过程视觉反馈：拖起时 `opacity: 0.5`，目标列 `border-color: #7B68EE`
- 拖拽失败（网络/后端错误）：卡片回弹原位 + Toast 提示

### 7.2 数据一致性
- 删除月任务时，子周任务 `parent_id` 置空（不级联删除）→ `ON DELETE SET NULL` 语义
- 删除周任务时，子日任务 `parent_id` 置空
- 番茄钟关联的 todo 被删除时，`pomodoro_sessions.todo_id` 置空
- SQLite 不支持 `ON DELETE SET NULL`，通过应用层 `DELETE BEFORE` 触发器实现：
  ```sql
  CREATE TRIGGER IF NOT EXISTS todos_delete_cascade
  AFTER DELETE ON todos
  BEGIN
    UPDATE todos SET parent_id = NULL WHERE parent_id = OLD.id;
    UPDATE pomodoro_sessions SET todo_id = NULL WHERE todo_id = OLD.id;
  END;
  ```

### 7.3 周起始日定义
- `week_start` 固定为**周一**（ISO 8601 标准）
- Python 端计算：`date - timedelta(days=date.weekday())`
- JS 端计算：`new Date(date.setDate(date.getDate() - date.getDay() + 1))`（注意周日 getDay()=0 需特殊处理）

### 7.4 Focus 页跳转参数传递
- 使用 URL 参数：`#/focus?todo_id=123`
- Focus 页 `useSearchParams` 读取后自动填入任务选择下拉
- 避免使用 localStorage（多窗口冲突）或 IPC（增加耦合）

### 7.5 性能
- 待分配区默认最多显示 50 条，超出滚动
- 七天列每列最多显示 20 条任务，超出滚动
- 底部数据条统计走 `get_week_plan_stats` 单次查询

### 7.6 并发修改
- 同一 Electron 单进程，无多浏览器并发
- 乐观更新策略：先更新 UI，后端失败则回滚 + Toast 错误提示

## 八、测试要点

- 月任务 CRUD + 拆解为周任务
- 周任务 CRUD + 分配到某天
- 待分配区拖拽到七天列（assign）
- 七天列间拖拽（reassign）
- 拖回待分配区（unassign）
- 今日列点击"开始专注"跳转 Focus 页并预填
- 番茄钟完成后自动回写 todo 进度
- 月/周/日视图切换
- 底部数据条统计正确性
- 历史数据兼容（现有 todos 进入待分配区）

## 九、不在本次范围

以下功能后续迭代：
- 重复任务（`repeat_type`/`repeat_days` UI 控件）
- 任务子任务（checklist）
- 任务标签系统
- 任务评论
- 任务附件

## 十、版本与发布

### 10.1 版本号
- `client/package.json` 版本号 +1（如 1.15.10 → 1.15.11）
- 数据库 SCHEMA_VERSION 17 → 20

### 10.2 Git 提交策略
- 单次提交：`feat: 周计划与任务分配 — 月/周/日三级层级+拖拽分配+番茄数据条`
- 远程推送：GitHub/Gitee/GitCode（需用户修复远程仓库权限后）

### 10.3 构建与重启
- `cd client && npm run build`
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\restart-app.ps1`
- 验收：访问 `/week-plan` 页面，检查月/周/日视图、拖拽、数据条

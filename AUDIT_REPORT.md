---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: 'e4fc0850-a0fd-4311-abd8-5c61129863ec'
  PropagateID: 'e4fc0850-a0fd-4311-abd8-5c61129863ec'
  ReservedCode1: 'dd3214eb-6a1f-4991-993e-9ad9a0e80196'
  ReservedCode2: 'dd3214eb-6a1f-4991-993e-9ad9a0e80196'
---

# xiaohei-daily 稳定性 & 代码质量审计报告

> 审计范围：全部 Python 后端源码（db.py, config.py, collector.py, ai_client.py, report.py, main.py, context_manager.py, deep_insight_engine.py, server.py, prompt.py, screenshot.py, app_tracker.py, classifier.py, system_events.py, file_utils.py, crypto.py, routes/*）
> 审计日期：2026-07-08
> 审计角色：高级后端架构师 / Code Review Expert

---

## 稳定性审计报告

### [严重] SQLite 跨线程共享连接 — 数据损坏风险

- **文件**: `db.py:31`
- **描述**: `sqlite3.connect(str(DB_PATH), timeout=10, check_same_thread=False)` 关闭了线程安全检查，允许多线程共享同一连接。虽然有 `_write_lock` 保护写操作，但读操作（所有 `get_*` 函数）在写操作执行期间可能并发访问。WAL 模式下虽比 journal 模式安全，但 SQLite 官方文档明确指出：在 `check_same_thread=False` 下，如果多个线程同时使用同一连接，行为是未定义的，可能导致 "database is locked" 异常或数据损坏。
- **修复**: 改用连接池或每线程独立连接。推荐方案：读操作使用 `connect()` 创建短连接（WAL 模式下读不阻塞写），写操作通过 `_write_lock` 串行化使用持久连接。或者改用 `sqlite3` 的序列模式（`serialized threading mode`）。

### [严重] V9 迁移手动事务管理 — 数据丢失风险

- **文件**: `db.py:255-306`
- **描述**: V9 迁移使用手动 `BEGIN`/`COMMIT`/`ROLLBACK`，但 SQLite 的 DDL 语句（如 `DROP TABLE`、`ALTER TABLE RENAME`）在事务中可能是隐式提交的。如果 `DROP TABLE app_usage`（L286）执行后 `ALTER TABLE app_usage_v9 RENAME TO app_usage`（L287）失败，`ROLLBACK` 无法恢复已 DROP 的表。虽然 L293 备份了 `app_usage_v9_backup`，但恢复逻辑 L302-305 本身也可能在异常状态下失败，导致数据永久丢失。
- **修复**: 使用 Python 的 `with conn:` 上下文管理器替代手动 BEGIN/COMMIT。对于 DDL 操作，在执行前用独立的 `CREATE TABLE ... AS SELECT *` 做完整备份，确认所有 DDL 成功后再 DROP 旧表和备份。

### [严重] 裸 `except:` 吞掉所有异常 — 静默数据丢失

- **文件**: `context_manager.py:232, 362, 369`
- **描述**: 三处裸 `except:` 会捕获 `KeyboardInterrupt`、`SystemExit` 等控制流异常，且不记录任何日志。当 JSON 解析失败时，画像数据被静默丢弃为空列表/空字典，用户无法感知数据异常。
- **修复**: 替换为 `except (json.JSONDecodeError, ValueError, TypeError) as e:`，并添加 `logger.debug(f"JSON parse failed: {e}")`。

### [严重] 自动画像生成竞态条件 — 重复执行

- **文件**: `context_manager.py:519-526`
- **描述**: `_auto_profile_running` 布尔标志用于防重入，但 `if _auto_profile_running: return` 和 `_auto_profile_running = True` 之间无原子性保证。两个线程可能同时读到 `False` 然后都进入执行，导致同一日期的画像被重复生成（浪费 AI 额度），或更严重地并发写 DB 导致数据不一致。
- **修复**: 使用 `threading.Lock` 替代布尔标志：
  ```python
  _auto_profile_lock = threading.Lock()
  def auto_generate_yesterday_profile():
      if not _auto_profile_lock.acquire(blocking=False):
          return
      try:
          ...
      finally:
          _auto_profile_lock.release()
  ```

### [高] 无界缓存字典 — 内存泄漏

- **文件**: `report.py:636`
- **描述**: `_weather_cache: dict = {}` 是模块级无界字典，每天至少一个 key，长期运行（数月）后持续增长。虽然单个 value 很小（~200 bytes），但若网络异常导致缓存 key 格式变异（如带时区），可能产生更多 key。
- **修复**: 改为 `collections.OrderedDict` 并限制最大容量（如 30 天），或使用 `functools.lru_cache(maxsize=30)`。

### [高] 无界概览缓存 — 内存泄漏

- **文件**: `routes/agent.py:16`
- **描述**: `_overview_cache: dict[tuple, dict] = {}` 按日期隔离缓存 AI 洞察结果，但无淘汰策略。长期运行跨月/年后，历史日期的缓存永远不被清理。
- **修复**: 添加 LRU 淘汰：当 `_overview_cache` 超过 10 个 key 时，删除最旧的条目。或改用 `@lru_cache(maxsize=10)` 装饰器。

### [高] OpenAI 客户端重复创建 — 资源泄漏

- **文件**: `report.py:1307`, `report.py:1564`, `context_manager.py:104`, `routes/agent.py:414`
- **描述**: 4 处代码各自创建新的 `OpenAI(...)` 客户端实例，不复用 `ai_client._get_client()` 单例。每次创建新实例会建立新的 HTTP 连接池（httpx 默认 100 连接），频繁调用时可能耗尽文件描述符/连接数，且浪费 TCP 握手开销。
- **修复**: 统一使用 `from ai_client import _get_client; client = _get_client()`。对于需要不同 timeout 的场景，扩展 `_get_client()` 支持 timeout 参数，或使用 `_get_client()` 的默认实例（其 timeout=60s 对日报生成足够）。

### [高] `upsert_app_usage` 竞态条件 — 数据不一致

- **文件**: `db.py:667-692`
- **描述**: `upsert_app_usage()` 修改全局 `_pending_commits` 计数器但未持有 `_write_lock`，而 `insert_activity()`（L568）在 `_write_lock` 内修改同一计数器。两者并发时，`_pending_commits` 的读取、递增、重置操作可能交错，导致丢失 commit（数据未落盘）或重复 commit。
- **修复**: 将 `upsert_app_usage` 和 `upsert_app_usage_multi` 的写操作也包裹在 `with _write_lock:` 内。

### [高] `upsert_app_usage_multi` 同样缺少写锁

- **文件**: `db.py:695-748`
- **描述**: 同上，`upsert_app_usage_multi()` 修改 `_pending_commits` 未持 `_write_lock`，且循环内多次写操作之间无事务保护。
- **修复**: 同上，包裹在 `with _write_lock:` 内。

### [中] `_flush_pending_commits` 可能空 commit

- **文件**: `db.py:604-611`
- **描述**: 当 `_pending_commits > 0` 时执行 `conn.commit()`，但如果自上次 commit 后的写操作已经在各自的 `get_conn()` 上下文中被 commit（如 `save_report` L798），此处会执行无意义的空 commit（触发 fsync）。
- **修复**: 追踪最后一次写操作的连接，仅在确认有未提交事务时才 commit。或改用 SQLite 的 `autocommit` 模式配合显式事务。

### [中] DeepInsight `years_to_expert` 除零风险

- **文件**: `deep_insight_engine.py:190`
- **描述**: `years_to_expert` 计算中 `max(len(history_activities or []) * interval_sec / 86400, 1)` 虽然用 `max(..., 1)` 避免除零，但外层 `max(skill_hours * 365 / max(...), 1)` 中，若 `skill_hours` 极小（如 0.001），`skill_hours * 365 / 1` 可能产生极大的 `years_to_expert` 值（如 9999），虽不崩溃但结果无意义。
- **修复**: 增加 `skill_hours` 下限检查：`if skill_hours < 1: years_to_expert = None`。

### [中] DeepInsight 裸 `except:` 吞异常

- **文件**: `deep_insight_engine.py:178`
- **描述**: `except:` 裸捕获，可能吞掉 `KeyboardInterrupt` 等控制流异常。
- **修复**: 改为 `except (ValueError, TypeError, AttributeError):`。

### [中] 熔断器半开状态仅允许 1 次试探 — 恢复缓慢

- **文件**: `ai_client.py:44, 70-74`
- **描述**: `_CB_HALF_OPEN_MAX = 1` 意味着半开状态只允许 1 次试探请求。如果该次请求因瞬时网络抖动失败，立即重新熔断（L96-98），需再等 60s 冷却。在偶发网络抖动场景下，可能导致 AI 服务长时间不可用。
- **修复**: 将 `_CB_HALF_OPEN_MAX` 提高到 2-3，或在半开→开放时缩短冷却时间（如 30s）。

### [中] `_get_client()` 单例不感知配置变更

- **文件**: `ai_client.py:119-133, 136-140`
- **描述**: 单例客户端缓存了 `api_key` 和 `base_url`，如果用户在运行时修改了配置（通过前端设置页），`_reset_client()` 被调用后下一次 `_get_client()` 会用新配置创建实例，但中间的短暂窗口内旧实例仍被使用。更严重的是，`report.py` 和 `context_manager.py` 中自行创建的 OpenAI 客户端完全不感知配置变更。
- **修复**: 统一使用 `_get_client()`，并在配置变更时调用 `_reset_client()`。对于需要不同 timeout 的场景，扩展 `_get_client()` 接受可选 timeout 参数。

### [中] 主循环通过模块变量访问暂停状态 — 脆弱耦合

- **文件**: `main.py:160`
- **描述**: `_server_module._collector_paused` 直接访问 server 模块的全局变量。如果 server 模块被重载或变量名变更，会抛出 `AttributeError` 导致采集循环中断。
- **修复**: 在 server 模块提供 `is_collector_paused()` 函数，或通过 `server.get_collector()` 返回的 collector 对象的属性来判断。

### [低] 分类平滑每次查 DB — 性能浪费

- **文件**: `collector.py:82` (调用 `get_recent_activities(3)`)
- **描述**: `_smooth_category()` 每次调用都执行 `get_recent_activities(3)` 查数据库，在每分钟一次的采集循环中增加不必要的 DB 压力。Collector 内已有 `_recent_context_cache`，但平滑函数未复用。
- **修复**: 将最近 3 条活动作为参数传入 `_smooth_category()`，复用采集器已缓存的上下文。

### [低] 图标提取线程无并发限制

- **文件**: `collector.py:226-230`
- **描述**: 每次新应用出现时创建 `threading.Thread` 提取图标，虽然 `_should_extract_icon()` 做了同应用 10 分钟限流，但如果短时间内出现多个不同新应用（如刚开机），可能同时启动多个图标提取线程。
- **修复**: 使用 `ThreadPoolExecutor(max_workers=2)` 替代裸 Thread 创建，限制并发数。

### [低] JSON 解析正则不匹配嵌套结构

- **文件**: `ai_client.py:285`
- **描述**: `_parse_json_response` 中 `re.search(r"\{[^{}]+\}", raw)` 只匹配不含嵌套大括号的最内层 JSON，对于 AI 返回的嵌套 JSON（如 `{"windows": [{"app": "x"}]}`）会匹配到内层空结构导致解析失败。
- **修复**: 使用更健壮的 JSON 提取：从左到右找到第一个 `{`，然后用括号匹配找到对应的 `}`。

### [低] db.py V10/V11 f-string 构建 ALTER TABLE

- **文件**: `db.py:318, 332`
- **描述**: `f"ALTER TABLE user_profile ADD COLUMN {col} {deflt}"` 虽然当前 `col` 和 `deflt` 来自硬编码列表，安全无风险，但此模式若被复制到其他代码位置（如用户输入驱动的迁移），则存在 SQL 注入风险。
- **修复**: 在注释中标注安全依据，或改用参数化方式（虽 SQLite ALTER TABLE 不支持参数化列名，可用白名单校验）。

---

## 代码质量审计报告

### [严重] report.py 严重违反单一职责 — 1836 行巨型文件

- **文件**: `report.py` (1836 行)
- **描述**: 单文件包含 6 个报告模板（standard/simple/technical/okr/ai/deep）、天气获取、注意力指数、情绪曲线、技能雷达、工作流分析、时间线采样、周报、月报、活动聚合、自然语言生成等十余个职责。修改任一模板可能影响其他模板，测试困难，合并冲突频繁。
- **修复**: 按职责拆分为：
  - `report/templates/` — 各模板独立文件
  - `report/analyzers/` — attention_index, emotion_curve, skill_radar, workflow
  - `report/aggregators.py` — 活动聚合、分类叙事
  - `report/export.py` — 周报/月报导出
  - `report/weather.py` — 天气获取

### [严重] db.py 职责膨胀 — 1660 行混合迁移+查询+导出

- **文件**: `db.py` (1660 行)
- **描述**: 数据库连接管理、Schema 迁移（V1-V21 共 21 个版本）、CRUD 操作（activities/app_usage/reports/todos/pomodoro/habits/diaries/achievements/chat/...）、CSV 导出、JSON 辅助函数全部混在一个文件。每新增迁移都要修改此文件，且迁移失败可能影响正常查询。
- **修复**: 拆分为：
  - `db/connection.py` — 连接管理、重试
  - `db/migrations/` — 每个版本一个迁移脚本
  - `db/activities.py`, `db/app_usage.py`, `db/todos.py` — 按领域拆分查询
  - `db/export.py` — CSV 导出

### [高] OpenAI 客户端创建 DRY 违反 — 4 处重复

- **文件**: `report.py:1307`, `report.py:1564`, `context_manager.py:104`, `routes/agent.py:414`
- **描述**: 4 处代码各自 `OpenAI(api_key=config.AI_API_KEY, base_url=config.AI_BASE_URL, timeout=...)` 创建客户端，既违反 DRY 原则，又无法共享连接池、统一超时策略、统一熔断器管理。
- **修复**: 统一使用 `ai_client._get_client()` 单例，或扩展单例支持可选参数。

### [高] 工作模式分析逻辑重复

- **文件**: `report.py:764 (_compute_attention_index)`, `report.py:1359 (_analyze_work_patterns)`
- **描述**: 两个函数逻辑高度重叠：都分析分类切换次数、专注会话长度、工作强度曲线。`_compute_attention_index` 计算碎片化指数，`_analyze_work_patterns` 计算 focus_sessions 和 intensity_curve，但核心逻辑（遍历 activities 检测分类切换）重复实现。
- **修复**: 提取公共的 `_compute_session_info(activities) -> dict` 返回 sessions/switches/hour_counts 等基础数据，两个函数基于此衍生各自指标。

### [高] 配置散落各模块 — 无法统一管理

- **文件**: `ai_client.py:42-44` (熔断器参数), `routes/agent.py:17` (缓存 TTL), `report.py:636` (天气缓存), `collector.py:28-29` (闲置阈值), `deep_insight_engine.py` (各框架阈值)
- **描述**: 熔断器阈值（5次/60s/1次）、缓存 TTL（300s）、天气缓存、闲置检测阈值（180s）、深度工作阈值（25min）等大量配置硬编码在各模块顶层。修改任何参数都需要找到对应文件，且无法通过配置文件或 API 动态调整。
- **修复**: 将所有可调参数集中到 `config.py` 的常量区域，或支持从 `.env` / `settings.json` 读取，关键参数提供 API 端点查询和修改。

### [高] 硬编码分类集合 — 无法扩展

- **文件**: `report.py:638-641` (`_CREATIVE_CATS`, `_FOCUS_CATS_DEEP`, `_MEETING_CATS_DEEP`), `report.py:454` (`tech_cats`), `report.py:541-544` (OKR 分类集合)
- **描述**: 分类集合（开发/设计/学习等）硬编码在多处，与 `config.CATEGORIES` 不同步。用户通过前端自定义分类后，这些硬编码集合不会更新，导致深度洞察模板和 OKR 模板使用错误的分类。
- **修复**: 从 `config.CATEGORIES` 或数据库的 `app_category_rules` 表动态构建分类集合，或提供配置接口允许用户定义哪些分类属于"专注类"/"创意类"/"会议类"。

### [中] `_analyze_work_patterns` 函数体过长

- **文件**: `report.py:1359-1459` (100 行)
- **描述**: 函数体超过 100 行，包含时间间隔分析、分类切换分析、专注会话检测、工作强度曲线计算四个独立逻辑块，可读性差，难以单独测试。
- **修复**: 拆分为 `_analyze_time_gaps()`, `_analyze_focus_sessions()`, `_build_intensity_curve()` 三个子函数。

### [中] `overview_summary` 函数体过长

- **文件**: `routes/agent.py:134-462` (330 行)
- **描述**: 单个路由函数 330 行，包含数据获取、时间判断、凌晨数据处理、prompt 构建（150 行）、AI 调用、缓存逻辑、用户画像注入。难以阅读和测试。
- **修复**: 拆分为 `_build_overview_prompt()`, `_get_time_context()`, `_process_overnight_data()`, `_call_overview_ai()` 等子函数。

### [中] `_capture_once_inner` 函数体过长

- **文件**: `collector.py:185-449` (260 行)
- **描述**: 采集器核心函数 260 行，包含闲置检测、截图、前台应用获取、排除列表检查、多窗口分摊、AI 分析、分类平滑、存储、截图删除、GC 等十余个步骤。
- **修复**: 拆分为 `_check_idle()`, `_get_foreground_info()`, `_should_analyze()`, `_do_ai_analysis()`, `_persist_activity()` 等子步骤。

### [中] init_db 迁移函数体过长

- **文件**: `db.py:87-551` (460 行)
- **描述**: 21 个版本的 Schema 迁移全部在 `init_db()` 中以 if-elif 链实现。每新增迁移都要在此函数末尾追加代码，且修改时可能误触其他版本的逻辑。
- **修复**: 采用迁移脚本目录模式：
  - `db/migrations/v1_initial.py`, `db/migrations/v9_app_usage_unique.py`, ...
  - `init_db()` 自动扫描并按序执行未应用的迁移

### [中] 缺少类型注解 — 不利于静态分析

- **文件**: `context_manager.py` (多个函数), `report.py` (多个内部函数), `deep_insight_engine.py` (所有 compute_* 函数返回值)
- **描述**: 大量函数缺少参数和返回值类型注解，IDE 无法提供自动补全和类型检查，重构时容易遗漏依赖。
- **修复**: 添加完整类型注解，特别是 `dict` 返回值应使用 `TypedDict` 定义结构。

### [低] 重复 import 语句

- **文件**: `report.py:7 (import json)`, `report.py:632 (import json as _json)`; `report.py:9 (import re as _re)`, `report.py:1580 (import re as _re)`
- **描述**: 同一模块内对 `json` 和 `re` 有重复导入（不同别名），增加混淆风险。
- **修复**: 在文件顶部统一导入，去掉模块中间的重复 import。

### [低] 版本号硬编码

- **文件**: `main.py:101`
- **描述**: `"ChallengeDaily Windows 版 v1.10.0"` 硬编码在 print 语句中，与实际版本（根据 memory 为 v1.15.0）不一致，且修改版本号需要找到此文件。
- **修复**: 从 `config.py` 或 `__version__.py` 读取版本号。

### [低] dict.get() 无类型安全

- **文件**: 多处（collector.py, report.py, routes/agent.py, deep_insight_engine.py）
- **描述**: 大量 `act.get("category")` / `act["category"]` 操作假设 activities 列表元素为特定结构的 dict，但无运行时类型校验。若 DB 返回异常格式（如字段缺失、类型错误），会抛出 `KeyError` 或 `TypeError` 导致采集/报告中断。
- **修复**: 定义 `Activity` TypedDict 并在 DB 读取层做类型转换/校验，或在关键路径使用 `act.get("category", "其他")` 并记录异常。

### [低] 熔断器状态通过模块全局变量管理 — 不利于测试

- **文件**: `ai_client.py:46-50`
- **描述**: 熔断器状态（`_cb_state`, `_cb_consecutive_failures` 等）是模块级全局变量，单元测试时无法隔离，一个测试用例的熔断状态会影响下一个。
- **修复**: 封装为 `CircuitBreaker` 类，提供 `reset()` 方法供测试使用。
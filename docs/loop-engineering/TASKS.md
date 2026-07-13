# 任务清单(Agent 按顺序执行)

> 每个任务格式: `### T<id> [P<priority>] <title>` + 文件/行号/描述/修复步骤
> Agent 执行时需将对应行 `status: pending` 在 PROGRESS.md 中改为 `done`/`blocked`

---

### T01 [P0] 全局鉴权缺失 — 所有 API 裸奔
- **文件**: `routes/__init__.py` + `routes/deps.py`
- **问题**: `check_token` 定义于 deps.py:66-68 但从未被任何 Blueprint 调用,所有 API 对任何能访问 58888 端口的请求者完全开放
- **修复步骤**:
  1. Read `routes/__init__.py` 和 `routes/deps.py`
  2. 在 `routes/__init__.py` 中,为每个注册的 Blueprint 添加 `before_request` 钩子,调用 `check_token`
  3. 排除 `/api/health`、`/api/icons/` 前缀的端点(健康检查和图标公开)
  4. 钩子逻辑: `if not check_token(request): return jsonify({"error":"unauthorized"}), 401`
  5. 验证: `python -m py_compile routes\__init__.py`
- **注意**: 如果 routes/__init__.py 结构不适合统一注册,则在每个 Blueprint 定义处添加 `@bp.before_request`。优先在 __init__.py 的注册函数中统一处理。

### T02 [P0] XSS: AIChat.tsx dangerouslySetInnerHTML 无 HTML 转义
- **文件**: `client/src/pages/AIChat.tsx` (行 29-49, 344)
- **问题**: `renderMarkdown` 函数用正则替换实现 markdown,无 HTML 实体转义,AI 返回 `<script>` 等标签被原样注入 DOM
- **修复步骤**:
  1. Read AIChat.tsx 确认现有 import 和 renderMarkdown 用法
  2. 先检查 package.json 是否有 react-markdown(已有)和 rehype-sanitize(可能没有)
  3. 如果没有 rehype-sanitize,采用替代方案:在 renderMarkdown 开头先做 HTML 转义(`text.replace(/[<>&"']/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;',"'":'&#39;'}[c]))`),然后再做 markdown 正则替换(代码块/粗体/列表等)
  4. 确保转义在 markdown 替换之前执行
  5. 验证语法

### T03 [P0] IPC sender 校验松散 — main.cjs
- **文件**: `client/electron/main.cjs` (行 670-677)
- **问题**: `url.includes('file://')` 让任何 file:// 页面通过 IPC 校验
- **修复步骤**:
  1. Read main.cjs 行 665-690
  2. 将 `isFromMainWindow` 函数改为严格 origin 比较:
     ```javascript
     const isFromMainWindow = (sender) => {
       try {
         const url = sender.getURL()
         const origin = new URL(url).origin
         return origin === 'http://localhost:5173' || origin === 'file://'
       } catch (_) { return false }
     }
     ```
     注意: `new URL('file:///...').origin` 返回 `'file://'`,这是 Electron 内嵌页面的正常 origin,可接受
  3. 但为了更严格,改为检查 senderFrame 的 frameId 与主窗口一致:如果 mainWindow 存在且 `sender === mainWindow.webContents`,直接返回 true;否则才做 URL 校验
  4. 验证语法

### T04 [P0] _waitForTokenFile 同步忙等阻塞主进程 — main.cjs
- **文件**: `client/electron/main.cjs` (行 176-185)
- **问题**: 内层 `while (Date.now() - t < 200) {}` 是纯 CPU 忙等,100% 占满一个核
- **修复步骤**:
  1. Read main.cjs 行 175-190
  2. 将 `_waitForTokenFile` 改为 async 函数,用 `await new Promise(r => setTimeout(r, 200))` 替代忙等
  3. 函数签名改为 `async function _waitForTokenFile(timeoutMs = 10000)`
  4. 更新所有调用点(搜索 `_waitForTokenFile`),加 `await`
  5. 验证语法

### T05 [P0] V22 迁移无事务保护 — db.py
- **文件**: `db.py` (行 550-584)
- **问题**: V22 迁移 DROP TABLE 后 RENAME 失败会导致 app_usage 数据全丢
- **修复步骤**:
  1. Read db.py 行 545-590
  2. 在 V22 迁移逻辑外层包裹事务:在迁移开始前 `conn.execute("BEGIN IMMEDIATE")`,成功后 `conn.commit()`,异常时 `conn.rollback()` 并 raise
  3. 在 DROP TABLE app_usage 前,先创建备份: `CREATE TABLE app_usage_v22_backup AS SELECT * FROM app_usage`
  4. 迁移成功后 DROP 备份表;异常时从备份恢复
  5. 验证: `python -m py_compile db.py`

### T06 [P0] V24 ALTER TABLE 无 IF NOT EXISTS — db.py
- **文件**: `db.py` (行 603-612)
- **问题**: V24 直接执行 4 条 ALTER TABLE,重跑会因 duplicate column 永久失败
- **修复步骤**:
  1. Read db.py 行 600-615
  2. 参照 V18/V19 的模式,在每条 ALTER 前用 `PRAGMA table_info` 检查列是否已存在
  3. 封装辅助函数 `_add_column_if_not_exists(conn, table, col, typedef)`(如果已有则复用)
  4. 替换 4 条裸 ALTER TABLE
  5. 验证: `python -m py_compile db.py`

### T07 [P0] init_db 无顶层 try/except — db.py
- **文件**: `db.py` (行 95-621 区域, init_db 函数)
- **问题**: 任何迁移异常直接传播到 main.py,进程崩溃,单例锁未释放
- **修复步骤**:
  1. Read db.py init_db 函数定义
  2. 在 init_db 主体外层包裹 try/except
  3. except 块中: `logger.error(f"init_db 失败: {e}", exc_info=True); raise`(记录日志后重新抛出,让 main.py 决定退出策略)
  4. 验证: `python -m py_compile db.py`

### T08 [P0] Focus.tsx setInterval 因依赖重建失效
- **文件**: `client/src/pages/Focus.tsx` (行 155-167)
- **问题**: `syncWidget` 通过 useCallback 依赖 remaining,每秒 remaining 变化 → syncWidget 重建 → useEffect 重运行 → 定时器每秒销毁重建
- **修复步骤**:
  1. Read Focus.tsx 行 150-175
  2. 将 syncWidget 拆为不依赖 remaining 的稳定版本(用 ref 读取最新 remaining)
  3. useEffect 依赖只保留 `[phase]`,移除 syncWidget
  4. 在定时器回调内用 `setRemaining(prev => ...)` 函数式更新
  5. 验证语法

### T09 [P0] Focus.tsx savePomodoroState no-op
- **文件**: `client/src/pages/Focus.tsx` (行 162)
- **问题**: `{ ...ps, totalSec: ps.totalSec }` 同名赋值,等于 ps 本身,每秒无意义写 localStorage
- **修复步骤**:
  1. Read Focus.tsx 行 155-170
  2. 移除 setInterval 回调内的 `savePomodoroState` 调用(持久化应基于 phase 切换时机,不是每 tick)
  3. 验证语法

### T10 [P0] profile.py ZPD/MBTI 历史数据 bug
- **文件**: `routes/profile.py` (行 183-184)
- **问题**: `act_dicts` 同时作为当前和历史数据传入,导致 ZPD/MBTI/大五人格的"新元素检测"全部失效
- **修复步骤**:
  1. Read profile.py 行 175-195
  2. 在调用 `fn(act_dicts, interval_sec, act_dicts)` 前,查询历史活动数据(如近 30 天)
  3. 用 `db.get_activities` 获取历史数据,传给 historical 参数
  4. 如果获取历史数据成本高,至少改为传入空列表 `[]` 而非 act_dicts,让框架走"无历史"分支
  5. 验证: `python -m py_compile routes\profile.py`

### T11 [P0] ai_client.py _IDE_PROCESSES 拼写错误
- **文件**: `ai_client.py` (行 285)
- **问题**: `"trae soolo cn.exe"` 中 "soolo" 应为 "solo",导致 TRAE 不被识别为 IDE
- **修复步骤**:
  1. Read ai_client.py 行 280-295
  2. 将 `"trae soolo cn.exe"` 改为 `"trae solo cn.exe"`
  3. 验证: `python -m py_compile ai_client.py`

### T12 [P0] ai_client.py is_learning 布尔逻辑错误
- **文件**: `deep_insight_engine.py` (行 191)
- **问题**: `is_learning = (zone == 'learning') or (zone == 'learning' and apps_count >= 2)` 第二个条件被短路,多工具学习区信号失效
- **修复步骤**:
  1. Read deep_insight_engine.py 行 185-195
  2. 改为 `is_learning = (zone == 'learning') or (apps_count >= 2)` (移除冗余的 `zone == 'learning' and`)
  3. 验证: `python -m py_compile deep_insight_engine.py`

### T13 [P0] ai_client.py 熔断器 closed→open 翻倍 bug
- **文件**: `ai_client.py` (行 106-113)
- **问题**: closed→open 时 `_cb_cooldown_sec * 2`,首次熔断即 120s 而非设计的 60s
- **修复步骤**:
  1. Read ai_client.py 行 85-115
  2. 在 closed→open 转换时,使用 `_CB_COOLDOWN_INIT_SEC` 而非 `_cb_cooldown_sec * 2`
  3. 只有 half_open→open(反复失败)才翻倍
  4. 验证: `python -m py_compile ai_client.py`

### T14 [P0] deep_insight_engine.py cross_domain 可能 >100%
- **文件**: `deep_insight_engine.py` (行 436-438)
- **问题**: 知识库加载失败时 all_categories 为空集,cross_domain 可能 = 5.0
- **修复步骤**:
  1. Read deep_insight_engine.py 行 430-445
  2. 加 `min(1.0, ...)` 上限: `cross_domain = round(min(1.0, len(used_categories) / max(len(all_categories), 1)), 3)`
  3. 验证: `python -m py_compile deep_insight_engine.py`

### T15 [P0] deep_insight_engine.py habit_consistency 可能 >100%
- **文件**: `deep_insight_engine.py` (行 538, 542)
- **问题**: consistency 和 routine_stability 无上限保护
- **修复步骤**:
  1. Read deep_insight_engine.py 行 535-545
  2. `consistency = round(min(100, consecutive_days / 66 * 100), 0)`
  3. `routine_stability = round(min(1.0, len(patterns) / 12), 3)`
  4. 验证: `python -m py_compile deep_insight_engine.py`

### T16 [P0] prompt.py JSON 示例花括号转义错误
- **文件**: `prompt.py` (行 78-90)
- **问题**: f-string 中 `{{{{` 输出为 `{{` 而非 `{`,AI 看到错误 JSON 示例
- **修复步骤**:
  1. Read prompt.py 行 70-95
  2. 将 JSON 示例中的 `{{{{` 改为 `{{`(f-string 中 `{{` 表示一个 `{`)
  3. 将 `}}}}` 改为 `}}`
  4. 确认输出是单个 `{` 和 `}`
  5. 验证: `python -m py_compile prompt.py`

### T17 [P0] settings_routes.py ai_base_url SSRF
- **文件**: `routes/settings_routes.py` (行 18-103)
- **问题**: ai_base_url 仅校验 http/https 前缀,可指向内网/回环
- **修复步骤**:
  1. Read settings_routes.py 和 routes/webhooks.py(复用 SSRF 校验逻辑)
  2. 在 update_settings 中,对 ai_base_url 复用 webhooks.py 的 `_validate_webhook_url` 逻辑(解析 IP,拒绝回环/内网)
  3. 如果校验失败,返回 400 错误
  4. 验证: `python -m py_compile routes\settings_routes.py`

### T18 [P0] backup.py 备份下载/恢复无鉴权
- **文件**: `routes/backup.py` (行 19-215)
- **问题**: create_backup 和 restore_backup 无鉴权
- **修复步骤**:
  1. 此任务依赖 T01(全局鉴权)。如果 T01 已完成,本任务自动完成,标记 done 并注明"由 T01 覆盖"
  2. 如果 T01 未完成或被 blocked,在 backup.py 的每个路由前手动加 `@bp.before_request` 鉴权
  3. 验证: `python -m py_compile routes\backup.py`

### T19 [P0] collector.py insert_activity 无异常保护
- **文件**: `collector.py` (行 412-423)
- **问题**: insert_activity 调用无 try-except,DB 异常导致本次采集全部丢失
- **修复步骤**:
  1. Read collector.py 行 405-440
  2. 用 try-except 包裹 insert_activity 调用
  3. except 块: `logger.error(f"insert_activity 失败: {e}", exc_info=True)` — 不 re-raise,允许继续
  4. 验证: `python -m py_compile collector.py`

### T20 [P0] client.ts BASE_URL 异步赋值竞态
- **文件**: `client/src/api/client.ts` (行 5-9)
- **问题**: getBackendPort() 异步,模块加载后 BASE_URL 仍是默认值,启动初期请求失败
- **修复步骤**:
  1. Read client.ts 行 1-30
  2. 添加 `let _baseUrlPromise: Promise<void> | null = null`
  3. 将异步赋值包装为 `ensureBaseUrl()` 函数,返回 Promise
  4. 在 `request` 函数开头 `await ensureBaseUrl()`
  5. 验证语法

### T21 [P1] App.tsx Electron 事件监听器无清理
- **文件**: `client/src/App.tsx` (行 129-144)
- **问题**: 三个 onUpdate* 监听器无 cleanup,StrictMode 下重复注册
- **修复步骤**:
  1. Read App.tsx 行 125-145
  2. 在 useEffect return 中移除监听器。如果 electronAPI 的 onUpdate* 不返回 unsubscribe 函数,则用 ref 持有回调并替换
  3. 最小方案:在 useEffect 开头加 `let cancelled = false`,回调内判断 `if (cancelled) return`,return 中 `cancelled = true`
  4. 验证语法

### T22 [P1] main.cjs mainLogDir 在 asar 中写入失败
- **文件**: `client/electron/main.cjs` (行 19)
- **问题**: mainLogDir 基于 __dirname,打包后在 asar 内只读
- **修复步骤**:
  1. Read main.cjs 行 15-25
  2. 改为 `const mainLogDir = path.join(app.getPath('userData'), 'logs')` (app.getPath 在行 73 之后才可用,需将日志初始化移到 app.whenReady 之后,或用延迟初始化)
  3. 注意: app.getPath('userData') 在 app ready 前可能不可用。如果行 19 在 app ready 前,改为在 app.whenReady 内初始化日志,或用 `path.join(process.env.APPDATA || '', 'challenge-daily', 'logs')` 作为 fallback
  4. 验证语法

### T23 [P1] Report.tsx ReactMarkdown 未配置 sanitize
- **文件**: `client/src/pages/Report.tsx` (行 227-234)
- **问题**: 未使用 rehype-sanitize,可注入 iframe/form
- **修复步骤**:
  1. Read Report.tsx 行 220-240
  2. 检查是否有 rehype-sanitize 依赖(读 package.json)。如果没有,在 urlTransform 中额外过滤 `<iframe`、`<form`、`<style`、`<object`、`<embed` 标签(在 ReactMarkdown 的 components prop 中重写这些标签为空)
  3. 最小方案:在 ReactMarkdown 的 `components` prop 中,将 `iframe`、`form`、`style`、`object`、`embed` 映射为 `() => null`
  4. 验证语法

### T24 [P1] deep_insight_engine.py _ts_diff_min 失败返回 0
- **文件**: `deep_insight_engine.py` (行 112-121)
- **问题**: 失败返回 0 导致专注段错误合并
- **修复步骤**:
  1. Read deep_insight_engine.py 行 108-125
  2. 失败时返回大数(如 99999.0)以触发分段,而非 0
  3. 加 `logger.warning(f"_ts_diff_min 解析失败: {e}")`
  4. 验证: `python -m py_compile deep_insight_engine.py`

### T25 [P1] ai_client.py 半开状态永久卡死
- **文件**: `ai_client.py` (行 72-76)
- **问题**: 半开状态超时请求时永久卡死
- **修复步骤**:
  1. Read ai_client.py 行 65-80
  2. 半开状态超过试探数后,自动转回 open 并重置 cooldown:`_cb_state = "open"; _cb_cooldown_sec = min(_cb_cooldown_sec * 2, _CB_COOLDOWN_MAX_SEC); _cb_half_open_tries = 0`
  3. 验证: `python -m py_compile ai_client.py`

---

## 任务执行完毕后的检查

当所有任务 status 不为 pending 时,Agent 进入 FINAL 阶段:
1. 读取 PROGRESS.md 统计 done/blocked/skipped 数量
2. 按 REPORT_TEMPLATE.md 生成 FINAL_REPORT.md
3. 返回简要总结

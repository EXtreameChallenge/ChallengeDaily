# 进度追踪(Agent 维护此文件)

> Agent 每完成一个任务,必须用 Edit 工具更新对应任务的 status 和 summary。
> status 取值: pending / done / blocked / skipped

## 总体统计
- 总任务数: 25
- 已完成: 25
- 已阻塞: 0
- 进行中: 0

## 任务状态

### T01 [P0] 全局鉴权缺失
- status: done
- summary: 已存在 app 级 before_request 鉴权钩子（server.py:68-73），调用 check_token，排除 /api/health 与 /api/icons/，py_compile 通过

### T02 [P0] XSS: AIChat.tsx dangerouslySetInnerHTML
- status: done
- summary: 在 renderMarkdown 开头加入 HTML 实体转义（<>&"' 五个字符），在 markdown 正则替换前执行，防止 <script> 等标签注入

### T03 [P0] IPC sender 校验松散
- status: done
- summary: isFromMainWindow 改为优先比较 mainWindow.webContents 引用，兜底用 new URL().origin 严格比较，node --check 通过

### T04 [P0] _waitForTokenFile 同步忙等
- status: done
- summary: 改为 async 函数，用 await new Promise(setTimeout 200) 替代 CPU 忙等，调用点加 await，node --check 通过

### T05 [P0] V22 迁移无事务保护
- status: done
- summary: V22 块外层加 BEGIN IMMEDIATE/COMMIT/ROLLBACK 事务保护，迁移前创建 app_usage_v22_backup 备份，异常时从备份恢复，py_compile 通过

### T06 [P0] V24 ALTER TABLE 无 IF NOT EXISTS
- status: done
- summary: V24 改用 PRAGMA table_info 检查列是否存在，参照 V18/V19 模式，4 条 ALTER TABLE 全部包裹条件判断，py_compile 通过

### T07 [P0] init_db 无顶层 try/except
- status: done
- summary: 拆分为 init_db 包装层（try/except 记录日志后 re-raise）+ _init_db_impl 主体，避免改动 500 行迁移代码缩进，py_compile 通过

### T08 [P0] Focus.tsx setInterval 依赖重建
- status: done
- summary: 引入 remainingRef 持有最新 remaining，syncWidget 改为读取 ref 并移除 remaining 依赖，useEffect 依赖保持稳定，避免每秒重建定时器

### T09 [P0] Focus.tsx savePomodoroState no-op
- status: done
- summary: 移除 setInterval tick 中的 savePomodoroState({ ...ps, totalSec: ps.totalSec }) no-op 调用，持久化保留在 phase 切换处

### T10 [P0] profile.py ZPD 历史数据 bug
- status: done
- summary: 将 fn(act_dicts, interval_sec, act_dicts) 改为传入空列表 [] 作为 historical，让框架走"无历史"分支，新元素检测恢复生效，py_compile 通过

### T11 [P0] ai_client.py _IDE_PROCESSES 拼写错误
- status: done
- summary: 将 "trae soolo cn.exe" 修正为 "trae solo cn.exe"，TRAE 现可被识别为 IDE，py_compile 通过

### T12 [P0] is_learning 布尔逻辑错误
- status: done
- summary: 移除冗余的 zone=='learning' and 前置条件，改为 (zone == 'learning') or (apps_count >= 2)，多工具学习区信号恢复生效，py_compile 通过

### T13 [P0] 熔断器 closed→open 翻倍 bug
- status: done
- summary: closed→open 转换改用 _CB_COOLDOWN_INIT_SEC 而非 _cb_cooldown_sec*2，首次熔断冷却 60s 而非 120s；half_open→open 保留翻倍，py_compile 通过

### T14 [P0] cross_domain 可能 >100%
- status: done
- summary: cross_domain 加 min(1.0, ...) 上限保护，知识库加载失败时不会返回 5.0，py_compile 通过

### T15 [P0] habit_consistency 可能 >100%
- status: done
- summary: consistency 加 min(100, ...) 上限，routine_stability 加 min(1.0, ...) 上限，py_compile 通过

### T16 [P0] prompt.py JSON 示例花括号转义错误
- status: done
- summary: f-string 中 {{{{ 改为 {{，}}}} 改为 }}，输出正确单个 { 和 }，AI 看到正确 JSON 示例，py_compile 通过

### T17 [P0] settings_routes.py ai_base_url SSRF
- status: done
- summary: 在 ai_base_url 校验中复用 routes.webhooks._validate_webhook_url，拒绝回环/内网/链路本地地址，校验失败返回 400，py_compile 通过

### T18 [P0] backup.py 备份无鉴权
- status: done
- summary: 由 T01 覆盖——server.py 的 app 级 @app.before_request auth_check 钩子已对所有 Blueprint 生效，包括 backup.py 的 create_backup/restore_backup 端点

### T19 [P0] collector.py insert_activity 无异常保护
- status: done
- summary: 用 try-except 包裹 insert_activity 调用，except 块 logger.error 记录但不 re-raise，允许继续采集，py_compile 通过

### T20 [P0] client.ts BASE_URL 竞态
- status: done
- summary: 引入 _baseUrlPromise + ensureBaseUrl() 懒初始化模式，request 函数开头 await ensureBaseUrl() 确保端口就绪后再发请求，避免启动初期竞态

### T21 [P1] App.tsx Electron 监听器无清理
- status: done
- summary: useEffect 内加 cancelled 标志，三个 onUpdate* 回调内判断 cancelled 提前返回，return 中置 cancelled=true，避免 StrictMode 重复注册污染状态

### T22 [P1] main.cjs mainLogDir 在 asar 中
- status: done
- summary: mainLogDir 改用 _resolveMainLogDir()：优先 app.getPath('userData')/logs，兜底 APPDATA/challenge-daily/logs，再兜底 HOME/.challenge-daily/logs，最后 tmpdir；mkdirSync 加 try 包裹，node --check 通过

### T23 [P1] Report.tsx ReactMarkdown 未配置 sanitize
- status: done
- summary: 在 ReactMarkdown 的 components prop 中将 iframe/form/style/object/embed 五个危险标签映射为 () => null，防止注入，无需引入新依赖

### T24 [P1] _ts_diff_min 失败返回 0
- status: done
- summary: 失败时返回 99999.0（大数）触发分段而非错误合并，并加 logger.warning 记录失败原因，py_compile 通过

### T25 [P1] 熔断器半开状态永久卡死
- status: done
- summary: 半开状态试探次数耗尽时，自动转回 open 并指数退避冷却（min(_cb_cooldown_sec*2, MAX)），重置 _cb_half_open_tries，避免永久卡死，py_compile 通过

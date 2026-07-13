# 硬约束规则(Agent 必须遵守)

## R1. 修改规则
- 必须用 Read 工具读取文件后才能用 Edit 修改(工具强制要求)
- 每次修改必须最小化,只改必要的行,不重写整个函数(除非任务明确要求)
- 不得新增第三方依赖。react-markdown / remark-gfm / rehype-sanitize 已在 package.json 中,可直接用;若需要 rehype-sanitize 则需先确认是否已安装,未安装则用替代方案(手动 HTML 转义)
- 修改 Python 文件后必须用 `python -m py_compile <file>` 验证语法(用 RunCommand 工具,cwd 设为项目根)
- 修改 .cjs/.tsx 文件后必须复查语法,确保无括号不匹配/JSX 错误

## R2. 不得破坏现有功能
- 不得删除现有公开 API 端点
- 不得改变现有 API 的响应格式(只加字段,不删字段)
- 不得修改 db.py 的 schema_version 表数据
- 备份接口加鉴权时,保留现有功能,只加 before_request 检查
- 不得改变前端路由结构

## R3. 安全修复约束
- 加鉴权时,用 `routes/deps.py` 中已有的 `check_token` 函数,通过 Blueprint 的 `before_request` 钩子统一注册
- `/api/health` 等健康检查端点不鉴权
- IPC sender 校验改为严格 `new URL(sender.getURL()).origin` 比较
- XSS 修复优先用现有依赖(react-markdown),不要引入新库

## R4. 进度记录规则
- 每完成一个任务,立即用 Edit 工具更新 PROGRESS.md
- 更新格式:将对应任务的 `status: pending` 改为 `status: done`,并填写 `summary: <一句话说明改了什么>`
- 遇到无法修复的任务,标记 `status: blocked`,填写 `blocker: <原因>`
- 不得批量更新,必须逐个任务更新

## R5. 不得做的事
- 不得创建新文件(除非任务明确要求,如提取 constants 模块)
- 不得修改 README.md
- 不得修改 .gitignore / package.json 的依赖列表
- 不得执行 git commit / git push(除非用户明确要求)
- 不得中途停下来问用户问题——自主决策,遇阻就标记 blocked 继续下一个

## R6. 代码风格
- Python: 4 空格缩进,双引号字符串,函数用 snake_case
- TypeScript/TSX: 2 空格缩进,单引号字符串,函数用 camelCase
- JavaScript(.cjs): 2 空格缩进,单引号字符串
- 注释用中文(与项目现有风格一致)

## R7. 验证命令
- Python 语法验证: `python -m py_compile <file_path>`(cwd 设为 `d:\Project\OpenSourcePlan\ChallengeDaily20260703\xiaohei-daily`)
- 如果 py_compile 失败,必须修复后才能标记任务 done
- 前端文件无命令行验证工具,需人工复查语法

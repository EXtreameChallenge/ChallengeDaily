# ChallengeDaily — 忙了一天，却不知道忙的什么？

[![GitHub stars](https://img.shields.io/github/stars/EXtreameChallenge/ChallengeDaily?style=for-the-badge)](https://github.com/EXtreameChallenge/ChallengeDaily/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/EXtreameChallenge/ChallengeDaily?style=for-the-badge)](https://github.com/EXtreameChallenge/ChallengeDaily/network)
[![GitHub issues](https://img.shields.io/github/issues/EXtreameChallenge/ChallengeDaily?style=for-the-badge)](https://github.com/EXtreameChallenge/ChallengeDaily/issues)
[![License](https://img.shields.io/github/license/EXtreameChallenge/ChallengeDaily?style=for-the-badge)](LICENSE)

> "我活了一万天，却不知道任何一天是怎么过的。"

**ChallengeDaily 是一款会"看"你电脑屏幕的 AI 时间记录助手**——它每隔 60 秒默默截一次屏，用 AI 视觉模型看懂你在做什么，自动归类成 12 大类，生成一份属于你的"一天行程报告"。

不是表单填写工具，不是番茄钟，不是 To-do List——**是 AI 替你记录，让你彻底解放双手、又看得见自己。**

> **不是让你更好地记录，而是让你不用记录。**

Windows 原生桌面应用（Electron + Python Flask），灵感来自 [samlaying/xiaohei-daily](https://github.com/samlaying/xiaohei-daily)（仅 macOS）。**为 1.5 亿 Windows 用户补上时间感知的拼图。**

> **多平台同步**：本项目已同步至 [GitHub](https://github.com/EXtreameChallenge/ChallengeDaily) | [Gitee](https://gitee.com/orange-purple-challenge/ChallengeDaily) | [GitCode](https://gitcode.com/EXtreameChallenge/ChallengeDaily)

## 为什么需要 ChallengeDaily

**痛点 1："忙了一天却记不清"的认知黑洞**

人脑对时间的感知严重失真——你以为学习了 4 小时，实际可能只有 1.5 小时。没有客观数据，自我认知永远在欺骗你。

**痛点 2："想成长却找不到改进点"**

不知道时间花在哪 → 无法优化 → 重复低效循环。自我成长的前提，是先看清自己。

**痛点 3："Windows 用户被时代抛弃"**

最好的时间记录工具都做了 Mac 专属，1.5 亿 Windows 用户没人服务。ChallengeDaily 补上了这块拼图。

### 三个核心能力

- **AI 自动识别你在做什么**：调用智谱 GLM-4V-Flash 视觉模型，看一眼屏幕就知道你在写代码 / 听网课 / 刷视频 / 聊微信——不用点任何按钮
- **一天行程可视化**：生成 24 小时热力图 + 应用使用 Top 榜 + 时段时间分布，让你第一次"看见"自己的时间都去了哪里
- **数据 100% 留在你电脑上**：截图分析完立即删除，敏感应用自动排除，API Key 用 Windows DPAPI 加密——没有云上传，只有你自己

## 功能特性

### 核心采集

- **定时截屏**：每隔 N 秒自动截取全屏，AI 分析后立即删除截图（隐私保护）
- **AI 视觉分析**：将截图发送给 AI Vision 模型，智能识别工作内容（兼容 OpenAI 协议，支持智谱 GLM-4V、DeepSeek、Qwen、Kimi 等）
- **无 API Key 也能用**：未配置 AI 时自动退化为应用名称规则分类（30+ 应用规则），同样生成日报
- **12 类工作分类**：开发 / 会议 / 沟通 / 文档 / 测试 / 设计 / 运维 / 数据分析 / 学习 / 管理 / 产品 / 生活
- **多窗口分析**：同时识别屏幕上多个可见窗口，按面积比例分摊使用时长
- **闲置检测**：3 分钟无键鼠操作自动暂停采集，不污染数据
- **隐私脱敏**：AI 分析时自动屏蔽隐私关键词，截图分析完即删

### 生产力工具

- **番茄钟**：25 分钟专注 + 5 分钟休息，自动统计每日番茄数和专注时长
- **待办清单**：支持计时型 / 目标型 / 习惯型三种模式，关联番茄钟自动累计进度
- **周计划**：月 / 周 / 日三级层级，拖拽分配任务，番茄数据条可视化进度
- **习惯追踪**：每日打卡，支持自定义目标和周期
- **每日日记**：记录心情、天气、感恩、亮点，可自动关联当日工作数据
- **成就系统**：解锁徽章，每日名言激励
- **倒数日**：重要日期倒计时提醒
- **专注模式**：屏蔽干扰应用，白噪音辅助
- **AI 对话**：基于工作数据的智能助手，回答"我今天做了什么"等问题

### 数据分析

- **Markdown 日报 / 周报 / 月报**：自动生成，支持自定义指令
- **深度洞察**：基于 10 大心理学/教育学/社会学学术框架的量化分析
- **用户画像**：AI 累积理解你的工作风格、常用软件、行为模式
- **热力图**：按小时展示工作密度，发现个人高效时段
- **趋势统计**：7/30 天效率趋势、分类占比、个人节奏分析
- **数据健康度**：校准系统开机时长 vs 采集覆盖率，发现漏采时段

### 系统特性

- **桌面宠物**：透明置顶小窗，实时显示当前活动
- **系统托盘**：双击显示主窗口，右键菜单快捷操作
- **全局快捷键**：`Ctrl+Shift+S` 截图、`Ctrl+Shift+P` 暂停/恢复、`Ctrl+Shift+R` 日报、`Ctrl+Shift+H` 显示/隐藏
- **Webhook 推送**：支持飞书 / 钉钉 / 企业微信，定时自动推送日报
- **自动备份**：定时备份数据库和配置文件（滚动保留 3 份）
- **数据导出**：CSV / Excel / JSON 格式导出活动记录
- **自动更新**：检测 GitHub Release 新版本，一键下载安装
- **崩溃自愈**：后端进程崩溃后指数退避自动重启，心跳检测自动恢复
- **单实例保护**：防止重复启动
- **安全存储**：API Key 使用 Windows DPAPI 加密存储
- **Token 鉴权**：本地 API 通过 Token 认证，Token 文件设置 ACL 权限

## 快速开始

### 方式一：从源码运行（开发 / 调试）

```bash
# 1. 进入项目目录
cd xiaohei-daily

# 2. 复制环境变量模板（可选，不配 AI 也能用规则分类）
cp .env.example .env
# 编辑 .env 填入 AI_API_KEY 等

# 3. 安装 Python 依赖
pip install -r requirements.txt

# 4. 安装前端依赖并构建
cd client
npm install
npm run build
cd ..

# 5. 启动后端
python main.py
```

或者直接通过 Electron 客户端启动（会自动拉起 Python 后端）：

```bash
cd client
npm install
npm run build
# 方式 A：通过启动脚本（推荐）
#    双击 ../start.bat 或 ../start.vbs
# 方式 B：开发模式（热更新）
npm run dev
```

启动后访问 http://127.0.0.1:58888/api/health 检查后端状态。

### 方式二：使用已打包的安装包

1. 前往 [Releases](https://github.com/ChallengeDaily/ChallengeDaily/releases) 下载最新版
2. 运行 `ChallengeDaily-x.x.x-Setup.exe` 安装
3. 从开始菜单或桌面快捷方式启动

> **注意**：打包版需要系统已安装 Python 3.10+ 并加入 PATH。首次启动时应用会自动检测 Python。

## 环境变量

项目根目录的 `.env` 文件支持以下配置（环境变量优先级高于 .env）。模板文件见 `.env.example`，复制后修改即可：

```bash
cp .env.example .env
```

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SCREENSHOT_INTERVAL_SEC` | 60 | 截图间隔（秒） |
| `SCREENSHOT_QUALITY` | 70 | JPEG 压缩质量（1-100） |
| `SCREENSHOT_MAX_WIDTH` | 1920 | 截图最大宽度，超过等比缩放 |
| `PORT` / `HTTP_PORT` | 58888 | HTTP API 端口 |
| `AI_BASE_URL` | https://open.bigmodel.cn/api/paas/v4 | AI 接口地址 |
| `AI_API_KEY` | （空） | AI API Key，为空则退化为规则分类 |
| `AI_VISION_MODEL` | glm-4v-flash | AI 视觉模型名称 |
| `AI_TEXT_MODEL` | glm-4-flash | AI 文本模型名称 |
| `RETENTION_DAYS` | 7 | 截图保留天数 |
| `PRIVACY_KEYWORDS` | （空） | 隐私关键词，逗号分隔 |

> **API Key 安全存储**：推荐在应用内设置页面输入 API Key，系统会使用 Windows DPAPI 加密存储到 `data/vault.dat`，不以明文保存在 `.env` 文件中。

## API 概览

后端提供 22 个功能模块、100+ 个 REST 接口，主要分类如下：

| 模块 | 路径前缀 | 说明 |
|------|----------|------|
| 健康检查 | `/api/health` | 服务状态、采集器状态 |
| 活动记录 | `/api/activities` | 增删改查、搜索、分页 |
| 统计分析 | `/api/stats/*` | 今日统计、趋势、热力图、节奏 |
| 日报 | `/api/report/*` | 日报 / 周报 / 月报生成与查询 |
| 设置 | `/api/settings` | 读取 / 更新设置 |
| 采集器 | `/api/collector/*` | 暂停 / 恢复采集 |
| 应用规则 | `/api/app-rules/*` | 应用分类规则管理 |
| 用户画像 | `/api/profile/*` | 画像、纠正、AI 自我认知分析 |
| 深度洞察 | `/api/deep-insight` | 学术框架量化分析 |
| 番茄钟 | `/api/pomodoro/*` | 开始 / 停止 / 统计 |
| 待办 | `/api/todos/*` | CRUD + 进度更新 |
| 周计划 | `/api/week-plan/*` | 月 / 周 / 日三级层级 |
| 日记 | `/api/diaries/*` | 每日日记 |
| 习惯 | `/api/habits/*` | 习惯追踪 + 打卡 |
| 成就 | `/api/achievements/*` | 徽章解锁 + 名言 |
| 倒数日 | `/api/countdowns/*` | 重要日期倒计时 |
| AI 对话 | `/api/ai/chat/*` | 基于工作数据的智能对话 |
| Webhook | `/api/webhooks/*` | 飞书 / 钉钉 / 企业微信推送 |
| 自动日报 | `/api/auto-report/*` | 定时生成 + 推送配置 |
| 备份 | `/api/backup/*` | 备份 / 恢复 |
| 导出 | `/api/export/*` | CSV 导出 |
| 通知 | `/api/notifications` | 应用内通知 |
| 数据健康 | `/api/health/*` | 覆盖率、采样偏差、系统事件 |
| 图标 | `/api/icons/<app>` | 应用图标（公开接口） |

> 所有非公开接口需要 `X-API-Token` 请求头鉴权，Token 由后端自动生成并存储在 `data/.api_token`。

## 项目结构

```
xiaohei-daily/
├── main.py                    # 入口：调度器 + HTTP 服务 + 单实例保护
├── config.py                  # 配置管理（.env + 环境变量 + 设置缓存）
├── db.py                      # SQLite 数据库（WAL 模式, Schema 版本管理, 23 张表）
├── screenshot.py              # 屏幕截图（mss + Pillow, 重复画面检测）
├── app_tracker.py             # 前台应用追踪（Win32 API, 多窗口枚举）
├── icon_extractor.py          # 应用图标提取（Win32 SHGetFileInfo）
├── prompt.py                  # AI 分析提示词
├── ai_client.py               # AI Vision API 调用（OpenAI 兼容协议）
├── classifier.py              # 12 类分类（AI + 规则兜底）
├── collector.py               # 采集调度核心（多窗口分摊, 闲置检测, GC）
├── report.py                  # Markdown 日报 / 周报 / 月报生成
├── server.py                  # Flask HTTP API（CORS, Token 鉴权, Waitress）
├── context_manager.py         # 长上下文管理（分层摘要 + 结构化记忆）
├── system_events.py           # Windows 系统事件读取（开机/关机/登录校准）
├── deep_insight_engine.py     # 深度洞察引擎（10 大学术框架量化分析）
├── deep_insight_frameworks.yaml # 深度洞察知识库
├── crypto.py                  # 敏感数据加密（Windows DPAPI）
├── file_utils.py              # 原子写入 + 数据备份
├── install_deps.py            # 一键安装 Python 依赖
├── requirements.txt           # Python 依赖清单
├── .env                       # 环境变量配置（从 .env.example 复制）
├── .env.example               # 环境变量模板文件
├── start.bat                  # Windows 启动脚本（BAT）
├── start.vbs                  # Windows 启动脚本（VBS, 无控制台窗口）
├── .github/workflows/release.yml # GitHub Actions CI/CD 自动打包
├── routes/                    # Flask 蓝图路由（22 个模块）
│   ├── __init__.py            # 蓝图注册
│   ├── deps.py                # 共享依赖（collector, token, 锁）
│   ├── health.py              # 健康检查 + 采集器状态
│   ├── activities.py          # 活动记录 CRUD
│   ├── stats.py               # 统计分析
│   ├── reports.py             # 日报 / 周报 / 月报
│   ├── settings_routes.py     # 设置 + 采集器控制
│   ├── app_rules.py           # 应用分类规则
│   ├── profile.py             # 用户画像 + AI 自我认知
│   ├── deep_insight.py        # 深度洞察
│   ├── pomodoro.py            # 番茄钟
│   ├── todos.py               # 待办清单
│   ├── week_plan.py           # 周计划（月/周/日层级）
│   ├── diaries.py             # 每日日记
│   ├── habits.py              # 习惯追踪
│   ├── achievements.py        # 成就系统
│   ├── countdowns.py          # 倒数日
│   ├── chat.py                # AI 对话
│   ├── webhooks.py            # Webhook 推送
│   ├── auto_report.py         # 自动日报
│   ├── backup.py              # 备份 / 恢复
│   ├── exports.py             # 数据导出
│   ├── notifications.py       # 通知
│   ├── health.py              # 数据健康度
│   └── agent.py               # Agent 自动化
├── client/                    # Electron + React 前端
│   ├── package.json           # 前端依赖 + Electron 打包配置
│   ├── vite.config.js         # Vite 构建配置
│   ├── electron/
│   │   ├── main.cjs           # Electron 主进程（后端管理, 窗口, 托盘, 快捷键）
│   │   └── preload.cjs        # 预加载脚本（IPC 桥接）
│   ├── src/
│   │   ├── App.tsx            # 根组件（路由, 首次引导, 后端连接）
│   │   ├── main.tsx           # React 入口
│   │   ├── api/client.ts      # API 客户端（全部接口封装）
│   │   ├── components/        # 通用组件（侧边栏, 标题栏, 宠物, Toast 等）
│   │   ├── pages/             # 23 个页面组件
│   │   └── index.css          # 全局样式（Tailwind）
│   └── dist/                  # 构建产物
└── data/                      # 运行时数据（自动创建）
    ├── xiaohei.db             # SQLite 数据库
    ├── settings.json          # 用户设置
    ├── vault.dat              # 加密的 API Key（DPAPI）
    ├── .api_token             # API 鉴权 Token
    ├── webhooks.json          # Webhook 配置
    ├── auto_report.json       # 自动日报配置
    ├── screenshots/           # 截图文件（分析后自动删除）
    ├── reports/               # 生成的日报
    ├── logs/                  # 日志文件
    ├── icons/                 # 应用图标缓存
    └── backups/               # 自动备份
```

## 技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| 桌面框架 | Electron 31 | 跨平台桌面应用壳 |
| 前端 | React 18 + TypeScript | SPA 架构 |
| 构建 | Vite 5 | 快速 HMR + 打包 |
| 样式 | Tailwind CSS 3 | 原子化 CSS |
| 图表 | Recharts | 数据可视化 |
| Markdown | react-markdown | 日报渲染 |
| 后端 | Flask 3 + Waitress | 生产级 WSGI |
| 数据库 | SQLite (WAL) | 嵌入式, 零配置 |
| AI | OpenAI SDK（兼容协议） | 视觉 + 文本双模型 |
| 截图 | mss + Pillow | 高性能截屏 |
| 应用追踪 | Win32 API (ctypes) | 前台窗口 + 多窗口枚举 |
| 加密 | Windows DPAPI | 用户级密钥保护 |
| 打包 | electron-builder | NSIS 安装包 + 便携版 |

## Python 依赖

| 包 | 用途 |
|----|------|
| `mss` | 高性能屏幕截图 |
| `Pillow` | 图像处理（缩放、压缩、编码） |
| `openai` | AI API 调用（兼容协议） |
| `httpx` | HTTP 客户端 |
| `flask` | Web 框架 |
| `waitress` | 生产级 WSGI 服务器 |
| `pyyaml` | 深度洞察知识库解析 |
| `pywin32` | Windows 安全 API（Token 文件 ACL） |

## 开发指南

### 开发模式

```bash
# 终端 1：启动后端
cd xiaohei-daily
python main.py

# 终端 2：启动前端（热更新）
cd xiaohei-daily/client
npm run dev
```

### 打包发布

```bash
cd xiaohei-daily/client
npm run build
# 产物在 dist-electron/ 目录下：
#   - ChallengeDaily-x.x.x-Setup.exe    （NSIS 安装包）
#   - ChallengeDaily-x.x.x-Portable.exe （便携版）
```

详细发布流程参见 [RELEASE.md](RELEASE.md)。

## 与 macOS 版的区别

| 项目 | macOS 版 | Windows 版 |
|------|----------|------------|
| 截图 | screencapture | mss + Pillow |
| 应用追踪 | AppleScript | Win32 API (ctypes) |
| 睡眠/唤醒 | IOKit 电源通知 | Event.wait() + atexit |
| 数据库 | SQLite | SQLite (WAL + busy_timeout) |
| AI 分类 | OpenAI API | OpenAI 协议兼容 + 规则兜底 |
| 密钥存储 | — | Windows DPAPI |
| 桌面框架 | — | Electron + React |
| 生产力工具 | — | 番茄钟/待办/周计划/日记/习惯/成就等 |

## License

MIT

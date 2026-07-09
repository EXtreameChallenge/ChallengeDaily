# ChallengeDaily — 忙了一天，却不知道忙的什么？

[![GitHub stars](https://img.shields.io/github/stars/EXtreameChallenge/ChallengeDaily?style=for-the-badge)](https://github.com/EXtreameChallenge/ChallengeDaily/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/EXtreameChallenge/ChallengeDaily?style=for-the-badge)](https://github.com/EXtreameChallenge/ChallengeDaily/network)
[![License](https://img.shields.io/github/license/EXtreameChallenge/ChallengeDaily?style=for-the-badge)](LICENSE)

> 你有没有过这种瞬间？晚上 11 点躺在床上，盯着天花板想："我今天到底干了什么？"
> 明明忙了一整天，却想不起来时间花在哪儿了。
>
> 我活了一万天，却不知道任何一天是怎么过的。**这不是我一个人的问题。**

---

## ChallengeDaily 是什么

**一款会"看"你电脑屏幕的 AI 时间记录助手。**

它每隔 60 秒默默截一次屏，用 AI 视觉模型看懂你在做什么，自动把一天的活动归类成 12 大类，生成一份属于你的"一天行程报告"。

**不是让你更好地记录，而是让你不用记录。**

- 不用点任何按钮
- 不用填写任何表单
- 不用手动切换任务

AI 替你感知、替你分类、替你写日报。你只管做你的事。

---

## 三个让你无法拒绝的理由

### 第一个：AI 自动识别，完全解放双手

调用智谱 GLM-4V-Flash 视觉模型，看一眼屏幕就知道你在写代码、还是看视频、还是聊微信。12 类自动分类，覆盖从开发到生活的所有场景。

> 传统的"手动选择任务 → 点击开始 → 点了再点结束"是让工具用人。
> ChallengeDaily 是让 AI 替你干活，你连"开始记录"这个动作都省了。

**不配 API Key 也能用**——内置 30+ 应用规则自动分类，一样生成日报。接入 Key 后体验飞跃，支持智谱、DeepSeek、Qwen、Kimi 等所有兼容 OpenAI 协议的模型。

### 第二个：第一次"看见"自己的时间

你觉得自己今天学习了 4 小时？实际可能只有 1.5 小时。人脑对时间的感知严重失真，没有客观数据，自我认知永远在骗你。

ChallengeDaily 给你三样东西：

| 看到什么 | 发现什么 |
|----------|----------|
| 24 小时热力图 | 你最高效的时段在哪 |
| 应用使用 Top 榜 | 微信到底占了多少时间 |
| 7/30 天趋势对比 | 这周比上周进步了没有 |

第一次，你能用数据看见自己的成长。不是"我觉得我努力了"，而是"数据显示我进步了 4.2 小时"。

### 第三个：数据 100% 留在你电脑上

截图分析完**立即删除**。微信、飞书、密码管理器自动跳过不截图。API Key 用 Windows DPAPI 加密存储——不是存 .env 明文，不是上传云端，是操作系统级别的密钥保护。

> 没有云同步，没有第三方服务器，没有任何人能看到你的屏幕。
> 这是你的数据，只能留在你的电脑上。

---

## 你打开它的第一天，会看到什么

**早上 9 点** — 启动应用，桌面宠物小窗告诉你"开始采集"。不用管它，做你的事。

**晚上 10 点** — 打开主界面，第一眼看到今天的 24 小时热力图。

- "原来我下午 2-4 点效率最高"
- "微信居然用了 2.3 小时"
- "我以为学了 4 小时，实际只有 1.8 小时"

点开日报，AI 已经写好了你的一天：

```
📅 2026年7月9日 日报

🕐 开发 3.2h — VSCode: 修复了登录模块的3个bug
🕐 沟通 1.8h — 微信/飞书: 产品评审讨论
🕐 学习 1.5h — 浏览器: Rust所有权机制教程
🕐 休息 0.8h — 刷了一会儿B站
---
✅ 有效工作时间: 6.5h  🔥 番茄数: 8
📊 比昨天 +12%  |  本周累计 32h
```

不止日报——周报告诉你"这周比上周多专注了 4 小时"，月报告诉你"你最高效的时段是下午 2-4 点"，深度洞察用学术框架量化分析你的工作模式。

---

## 为什么做了这个

### 一个"时间黑洞"的真实故事

某天晚上 11 点，我盯着屏幕发呆。明明从早上 9 点就开始"干活"，14 个小时过去了，我却想不起来一天干了什么。

我翻了微信、翻浏览器历史、翻 IDE 的最近打开——拼凑不出一份真实的"一天行程"。

那一刻我突然意识到一个毛骨悚然的事：

> 我对自己的金钱了如指掌，对手机电量焦虑得不行，却对最珍贵的"时间"毫无感知。

我去找了市面上的所有方案。结果全是坑：

- Rescuetime — 只记录应用名称，不知道你在应用里具体做了什么
- Toggl Track — 手动记录，繁琐到一周就放弃了
- Timing — Mac 独占

**所有工具都在"让我多动手"，但真正的解法应该是"让我完全不动手"。**

于是有了 ChallengeDaily。

### 为什么选 Windows？

不是随口选的。

2026 年，最好的时间记录工具 Timing、Rize、Daily 全部做 Mac 专属，1.5 亿 Windows 用户没人服务。ChallengeDaily 从第一行代码就为 Windows 而生——Electron 桌面壳 + Python 后端 + Win32 API 原生追踪，不是 Mac 移植，是 Windows 原生。

### 为什么现在做？

智谱 GLM-4V-Flash 等视觉模型已经能准确识别屏幕内容，而且**免费**。过去做不到的"AI 看屏幕"，现在成本几乎为零。这是技术窗口期，现在不做，以后就没这么漂亮的时机。

---

## 真实数据验证

已完成 3 轮深度审计 + Loop Engineering 全量修复（30+ 项问题），在自己工作环境连续运行验证，核心链路完全跑通。

| 维度 | 数据 |
|------|------|
| 审计轮次 | 3 轮（基础检查 → 深度审计 → Loop Engineering） |
| 修复问题 | 30+ 项 |
| API 模块 | 22 个 |
| REST 接口 | 100+ |
| 数据库表 | 23 张 |
| CI/CD | GitHub Actions 自动构建 + Release |

---

## 快速开始

### 从源码运行

```bash
cd xiaohei-daily

# 1. Python 依赖
pip install -r requirements.txt

# 2. 前端构建
cd client && npm install && npm run build && cd ..

# 3. 启动
python main.py
# 或双击 start.bat / start.vbs
```

启动后访问 http://127.0.0.1:58888/api/health 确认后端运行正常。

### 使用打包版

前往 [Releases](https://github.com/EXtreameChallenge/ChallengeDaily/releases) 下载 `ChallengeDaily-Setup.exe` 安装即用。

> 需系统已安装 Python 3.10+，首次启动应用会自动检测。

### 配置 AI（可选）

不配 AI 也能用规则分类生成日报。要启用 AI 视觉识别，在应用设置里填入 API Key，支持智谱 GLM-4V / DeepSeek / Qwen / Kimi 等兼容 OpenAI 协议的模型。

> API Key 用 Windows DPAPI 加密存储到 `data/vault.dat`，不以明文保存。

---

## 技术栈

| 层 | 技术 |
|----|------|
| 桌面框架 | Electron 31 |
| 前端 | React 18 + TypeScript + Vite 5 + Tailwind CSS 3 |
| 图表 | Recharts |
| 后端 | Python 3.11 + Flask 3 + Waitress（生产级 WSGI） |
| 数据库 | SQLite（WAL 模式，23 张表，Schema 版本管理） |
| AI | OpenAI 兼容协议（默认 GLM-4V-Flash） |
| 截图 | mss + Pillow（画面去重） |
| 应用追踪 | Win32 API（多窗口枚举 + 面积分摊） |
| 加密 | Windows DPAPI |
| 打包 | electron-builder（NSIS 安装包 + 便携版） |

完整的功能清单、API 接口、项目结构详见下文。

<details>
<summary>📋 展开查看完整功能与接口详情</summary>

### 核心采集

- **定时截屏**：每隔 N 秒自动截取全屏，AI 分析后立即删除截图（隐私保护）
- **AI 视觉分析**：将截图发送给 AI Vision 模型，智能识别工作内容
- **无 API Key 也能用**：未配置 AI 时自动退化为应用名称规则分类（30+ 应用规则）
- **12 类工作分类**：开发 / 会议 / 沟通 / 文档 / 测试 / 设计 / 运维 / 数据分析 / 学习 / 管理 / 产品 / 生活
- **多窗口分析**：同时识别屏幕上多个可见窗口，按面积比例分摊使用时长
- **闲置检测**：3 分钟无键鼠操作自动暂停采集，不污染数据
- **隐私脱敏**：AI 分析时自动屏蔽隐私关键词

### 生产力工具

番茄钟（25+5 自动统计）、待办清单（计时型/目标型/习惯型）、周计划（月-周-日三级层级）、习惯追踪（每日打卡）、每日日记、成就系统、倒数日、专注模式（屏蔽干扰+白噪音）、AI 对话

### 数据分析

Markdown 日报/周报/月报（支持自定义指令）、深度洞察（10 大学术框架量化分析）、用户画像（AI 累积理解工作风格）、热力图（按小时展示工作密度）、趋势统计（7/30 天效率趋势）、数据健康度（覆盖率校准）

### 系统特性

桌面宠物、系统托盘、全局快捷键（`Ctrl+Shift+S/P/R/H`）、Webhook 推送（飞书/钉钉/企业微信）、自动备份（滚动保留 3 份）、数据导出（CSV/Excel/JSON）、自动更新（GitHub Release）、崩溃自愈（指数退避重启）、单实例保护、Token 鉴权

### API 模块（22 个）

| 模块 | 路径 | 说明 |
|------|------|------|
| 健康检查 | `/api/health` | 服务状态、采集器状态 |
| 活动记录 | `/api/activities` | 增删改查、搜索、分页 |
| 统计分析 | `/api/stats/*` | 今日统计、趋势、热力图 |
| 日报 | `/api/report/*` | 日报/周报/月报生成 |
| 设置 | `/api/settings` | 读取/更新设置 |
| 采集器 | `/api/collector/*` | 暂停/恢复采集 |
| 应用规则 | `/api/app-rules/*` | 应用分类规则管理 |
| 用户画像 | `/api/profile/*` | 画像、AI 自我认知 |
| 深度洞察 | `/api/deep-insight` | 学术框架量化分析 |
| 番茄钟 | `/api/pomodoro/*` | 开始/停止/统计 |
| 待办 | `/api/todos/*` | CRUD + 进度更新 |
| 周计划 | `/api/week-plan/*` | 月/周/日三级层级 |
| 日记 | `/api/diaries/*` | 每日日记 |
| 习惯 | `/api/habits/*` | 习惯追踪 + 打卡 |
| 成就 | `/api/achievements/*` | 徽章 + 名言 |
| 倒数日 | `/api/countdowns/*` | 倒计时提醒 |
| AI 对话 | `/api/ai/chat/*` | 工作数据智能对话 |
| Webhook | `/api/webhooks/*` | 飞书/钉钉/企微推送 |
| 自动日报 | `/api/auto-report/*` | 定时生成+推送 |
| 备份 | `/api/backup/*` | 备份/恢复 |
| 导出 | `/api/export/*` | CSV 导出 |
| 通知 | `/api/notifications` | 应用内通知 |

</details>

---

## 开发

```bash
# 终端 1：后端
cd xiaohei-daily && python main.py

# 终端 2：前端（热更新）
cd xiaohei-daily/client && npm run dev
```

打包：`cd client && npm run build`，产物在 `dist-electron/` 目录。

环境变量见 `.env.example`，主要配置项：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SCREENSHOT_INTERVAL_SEC` | 60 | 截图间隔 |
| `AI_VISION_MODEL` | glm-4v-flash | AI 视觉模型 |
| `AI_API_KEY` | （空） | 不配也能用规则分类 |

---

## 平台同步

| 平台 | 仓库 |
|------|------|
| GitHub | [EXtreameChallenge/ChallengeDaily](https://github.com/EXtreameChallenge/ChallengeDaily) |
| Gitee | [orange-purple-challenge/ChallengeDaily](https://gitee.com/orange-purple-challenge/ChallengeDaily) |
| GitCode | [EXtreameChallenge/ChallengeDaily](https://gitcode.com/EXtreameChallenge/ChallengeDaily) |

灵感来自 [samlaying/xiaohei-daily](https://github.com/samlaying/xiaohei-daily)（仅 macOS）。

## License

MIT

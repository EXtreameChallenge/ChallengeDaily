# ChallengeDaily

[![GitHub stars](https://img.shields.io/github/stars/EXtreameChallenge/ChallengeDaily?style=for-the-badge)](https://github.com/EXtreameChallenge/ChallengeDaily/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/EXtreameChallenge/ChallengeDaily?style=for-the-badge)](https://github.com/EXtreameChallenge/ChallengeDaily/network)
[![License](https://img.shields.io/github/license/EXtreameChallenge/ChallengeDaily?style=for-the-badge)](LICENSE)

---

**2026 年了，你对自己每天的时间流向，依然一无所知。**

你打开手机银行，每一笔支出清清楚楚。打开微信，聊天记录一条不落。打开相册，连三年前随手拍的照片都在。

唯独最重要的东西——时间——你连今天做了什么都说不上来。

> 不，不是"不知道"。
> 是**不敢知道**。

因为你隐隐约约感觉到，那个答案会让你不舒服。你以为今天学了 4 个小时，数据告诉你只有 1.5。你以为只是"回了几条消息"，实际上微信吞掉了你 2.3 小时。

**ChallengeDaily 做的，就是让你直面这个不舒服的真相——然后改变它。**

---

## 故事要从三个耳光说起

### 耳光一：你以为的"充实"，全是幻觉

2026 年 3 月的一个周四，我觉得自己状态特别好。从早上 9 点坐到电脑前，除了吃饭上厕所几乎没离开。晚上 11 点关电脑，心满意足——今天至少干了 10 个小时。

我女朋友问我："你今天具体做了什么？"

我想了 30 秒。脑子里一片空白。

"就……写代码啊，还有什么？"

她没再说话，但我从她眼神里读出了四个字：**你在骗自己**。

那天晚上我失眠了。不是因为她问了我，是因为我突然意识到——**我每天都在骗自己**。我对自己的时间感知，比股民对行情的判断还离谱。

### 耳光二：努力了三周，没有任何产出

我一直以为自己在"积累"。看了一堆 Rust 教程，收藏了几十个 GitHub 仓库，加了无数书签。

三周后，我问自己：这三周我到底学了什么？

说不出。因为那些"学习"其实是：打开 3 个教程页面 → 看了 8 分钟 → 切到 B 站刷了两个视频 → 回来看了 3 分钟 → 微信响了 → 再也没回到那个页面。

**低质量的"学习"，本质就是浪费时间——但你自己不知道。**

### 耳光三：毕业三年，我拿不出任何东西证明我努力过

简历上写的是"熟练掌握 xxx"，GitHub 上是去年 fork 的几个空仓库。

不是我不努力。我每天都在电脑前坐 10 个小时以上。

但问题来了——**如果时间真的被你用掉了，那产出在哪？**

这是我写 ChallengeDaily 的真正原因。我不想要"感觉良好"，我想要**可量化的真相**。

---

## ChallengeDaily 是怎么解决问题的

如果说常规的时间管理软件是在让你"努力记录"，那 ChallengeDaily 就是**替你记录，让你不用努力**。

它每隔 60 秒自动截一张你的屏幕，用 AI 看懂你当下在做什么——写代码、刷视频、聊微信、看文档——然后自动归档到 12 个类别里。一天下来，自动写一份你的"行程报告"。

**你什么都不用做。连"点一下开始"都省了。**

当你晚上打开报告，你会第一次看到真相：

- 你以为学习了 4 小时 → 实际 1.5 小时
- 你以为只用了半小时微信 → 实际 2.3 小时
- 你以为下午一直在码代码 → 实际中间切了 17 次到浏览器

**这种冲击，比你读十本时间管理书都管用。**

因为书只能告诉你"道理"，数据告诉你"你是谁"。

---

## 三个你无法拒绝的理由

### 一、完全零操作

没有"开始计时"，没有"切换任务"，没有"手动分类"。从你打开电脑的那一刻起，ChallengeDaily 就在后台默默记录。你用电脑的方式完全不变。

**不费力，才是能坚持的唯一原因。**

### 二、数据全留在你电脑上

截图分析完**立刻删除**。微信、密码管理器、银行页面自动跳过不截。API Key 用 Windows DPAPI 加密——不是存 .env 明文，不存在任何云端。没网也能用，你的数据只属于你。

### 三、不要钱，不锁功能

智谱 GLM-4V-Flash 视觉模型**免费**，ChallengeDaily 全部功能**完全开源**。不接 Key 也能用内置规则分类。这个赛道里收订阅费的产品，功能还没我们多。

---

## 不开玩笑，看看实际跑起来是什么样

早上 9 点打开电脑，角落有个小宠物告诉你"已经在记录了"。不用管它。

晚上 10 点，打开主界面：

一张 **24 小时热力图**告诉你今天的时间密度。最高峰的格子是下午 2 点到 4 点——原来你效率最高的时段在这里。

一份 **AI 日报**已经写好了：

```
📅 2026年7月9日 日报

🕐 开发 3.2h — 修了用户模块的 3 个 bug，重构了登录页
🕐 沟通 1.8h — 微信/飞书讨论产品需求
🕐 学习 1.5h — 浏览器看 Rust 所有权教程
🕐 浏览 0.8h — B 站刷了几个视频

✅ 有效时间 6.5h  🔥 8 个番茄
📊 比昨天 +12%  |  本周累计 32h
```

一周后，**周报告**诉你："这周比上周多学了 3.2 小时，但沟通时间也涨了，是不是最近会议太多了？"

一个月后，**深度洞察**给你做了一份学术分析——基于 10 个心理学/教育学框架，告诉你"你的学习模式偏向碎片化输入，缺乏深度输出"。

**看一次报告，比你自我反思一年都有用。**

---

## 和同类产品比，差在哪

| 功能 | RescueTime | Toggl Track | Timing (Mac) | ManicTime | ChallengeDaily |
|------|-----------|-------------|--------------|-----------|:---:|
| 自动记录 | ✅ | ❌ 手动 | ✅ | ✅ | ✅ |
| AI 识别屏幕内容 | ❌ | ❌ | ❌ | ❌ | ✅ |
| Windows 原生 | ✅ | ✅ | ❌ | ✅ | ✅ |
| 数据本地存储 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 完全免费 | ❌ 订阅 | ❌ 订阅 | ❌ $96/yr | ❌ | ✅ |
| 开源 | ❌ | ❌ | ❌ | ❌ | ✅ |
| AI 日报自动生成 | ❌ | ❌ | ❌ | ❌ | ✅ |
| 隐私（截图即删） | ✅ | — | ❌ 截图保存 | ✅ | ✅ |

**差距只有一个维度：AI 能看懂你在做什么。**

老工具只能记"你打开了 VSCode"，但不知道你是真的在写代码，还是对着屏幕发呆。ChallengeDaily 用视觉 AI 区分这两者——这是代差，不是参数差。

---

## 为什么是现在，为什么是 Windows

2026 年最好的时间工具 Timing、Rize、Daily 全部 Mac 独占。1.5 亿 Windows 用户没人管。

同时，智谱 GLM-4V-Flash 这种级别的大视觉模型已经能做到精准识别屏幕内容，而且**完全免费**。以前做不到的事——AI 实时理解你的屏幕——现在成本趋近于零。

**技术窗口开了。这个时间点不做，以后就没有这么好的条件。**

---

## 快速开始

```bash
cd xiaohei-daily
pip install -r requirements.txt
cd client && npm install && npm run build && cd ..
python main.py
```

打开 http://127.0.0.1:58888 ，数据已经在采了。

打包版去 [Releases](https://github.com/EXtreameChallenge/ChallengeDaily/releases) 下载 Setup.exe。

> 不配 AI Key 也能用（应用规则自动分类）。想开 AI 识别，在设置里填智谱 GLM-4V-Flash 或 DeepSeek/Qwen/Kimi 的 Key 即可。

---

## 技术栈与规模

| 层 | 技术 |
|----|------|
| 桌面 | Electron 31 |
| 前端 | React 18 + TypeScript + Vite 5 + Tailwind CSS 3 |
| 后端 | Python 3.11 + Flask 3 + Waitress |
| 数据库 | SQLite WAL（23 张表，Schema 版本管理） |
| AI | OpenAI 兼容协议（默认 GLM-4V-Flash） |
| 截图 | mss + Pillow（去重） |
| 系统 | Win32 API（多窗口枚举 + 面积分摊） |
| 安全 | Windows DPAPI 加密 |

已完成 **3 轮深度审计 + 30+ 项 Loop Engineering 修复**，核心链路在自己工作环境连续验证通过，21 个 API 模块、100+ REST 接口全部可用。

<details>
<summary>📋 完整功能清单（折叠）</summary>

### 核心采集

定时截屏（AI 分析后即删）、AI 视觉识别（12 类分类）、无 Key 规则兜底、多窗口面积分摊、3 分钟闲置自动暂停、隐私关键词过滤

### 生产力工具

番茄钟（25+5 自动统计）、待办清单（计时/目标/习惯三模式）、周计划（月-周-日三级）、习惯追踪、每日日记、成就系统、倒数日、专注模式、AI 工作对话

### 分析

日报/周报/月报、深度洞察（10 学术框架）、用户画像、24h 热力图、7/30 天趋势、数据健康度

### 系统

桌面宠物、系统托盘、全局快捷键、Webhook（飞书/钉钉/企微）、自动备份、CSV/Excel/JSON 导出、自动更新、崩溃自愈

</details>

---

## 平台同步

| 平台 | 仓库 |
|------|------|
| GitHub | [EXtreameChallenge/ChallengeDaily](https://github.com/EXtreameChallenge/ChallengeDaily) |
| Gitee | [orange-purple-challenge/ChallengeDaily](https://gitee.com/orange-purple-challenge/ChallengeDaily) |
| GitCode | [EXtreameChallenge/ChallengeDaily](https://gitcode.com/EXtreameChallenge/ChallengeDaily) |

灵感来源：[samlaying/xiaohei-daily](https://github.com/samlaying/xiaohei-daily)（仅 macOS）。

## License

MIT

---

> 开这个项目的初衷不是做一个"更好的工具"。
> 是做一面镜子——让你第一次，看见自己是谁。

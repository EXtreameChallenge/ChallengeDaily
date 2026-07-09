# 🖥️ ChallengeDaily

<p align="center">
  <img src="https://img.shields.io/github/stars/EXtreameChallenge/ChallengeDaily?style=for-the-badge&color=fedc2e" />
  <img src="https://img.shields.io/github/forks/EXtreameChallenge/ChallengeDaily?style=for-the-badge&color=3296ff" />
  <img src="https://img.shields.io/badge/Electron-31-47848f?style=for-the-badge&logo=electron" />
  <img src="https://img.shields.io/badge/Python-3.11-3776ab?style=for-the-badge&logo=python" />
  <img src="https://img.shields.io/badge/AI-多模型-8b5cf6?style=for-the-badge&logo=openai" />
  <img src="https://img.shields.io/badge/Windows-11-0078d6?style=for-the-badge&logo=windows11" />
  <img src="https://img.shields.io/badge/License-MIT-97ca00?style=for-the-badge" />
</p>

<p align="center"><b>AI 替你记录每一天。你只管活。</b></p>

---

> 🥟 你打开微信想回一条消息。45 分钟后你在看怎么做锅包肉。你连锅包肉都没吃过。
>
> 📖 你点开 B 站搜 Rust 教程。两个小时后，你在看「猫咪第一次见到雪」。你没有猫。
>
> 💀 你告诉自己今天要写完那个模块。凌晨 1 点你躺在床上刷手机，VSCode 还开着——今天新建了一个文件，删了，又新建了一个，写了 11 行，全删了。

**这不是效率问题。这是你不知道自己在浪费时间。而你不知道的原因，是你不敢知道。**

---

## 😨 没人愿意面对这件事

你想过用时间记录软件。你装过 Toggl、试过番茄钟、甚至买过 RescueTime 的订阅。

三天后你都卸载了。原因是同一个：**它们让你手动记录，但你根本不想记。**

——因为你隐约知道，记录下来的数字会让你难堪。

| 😇 你以为 | 💀 真实 |
|-----------|--------|
| 今天学了 4 个小时 | 学了 1.5 小时，剩余 2.5 小时在"打开教程 → 切 B 站 → 切微信 → 再也没回去" |
| 只回了"几条消息" | 微信实打实吞了你 2.3 小时 |
| 下午一直在码代码 | 中间切了 17 次到浏览器 |
| 这周很努力 | 趋势线在往下走，已经连续三周了 |

> 🧠 **人类对时间的感知，烂到连自己都骗得过。**
>
> 人脑天生不擅长感知时间跨度——你能感觉到 5 分钟和 1 小时的区别，但你不能感觉到「今天有效工作 4.2 小时还是 6.5 小时」。没有外部数据，你永远不知道这个差距。

---

## 👀 所以 ChallengeDaily 不问你"在干什么"

它直接看你的屏幕。

```
┌─────────────────────────────────────────────┐
│  📸 每 60 秒截一张屏幕                        │
│              ↓                               │
│  🤖 AI 视觉模型识别内容（12 个类别）           │
│              ↓                               │
│  📊 自动归档 → 生成日报 / 周报 / 深度洞察       │
└─────────────────────────────────────────────┘
```

**全程不用你点任何按钮。连"开始"都省了。**

这不是"自动记录"——这是**把你变成旁观者，让你从上帝视角看自己的一天。**

> 🔥 **你不需要读时间管理书。你不需要学什么方法论。你只需要看见你自己。**
>
> 看见一次，胜过自我反思一年。

---

## 🛠️ 但"看见"只是第一步

你看见自己每天有 2.3 小时被微信吞掉。然后呢？

**ChallengeDaily 不是只告诉你「你废了」，它给你工具让你不再废。**

### 🍅 番茄钟 —— 让你没法不努力

你最大的敌人不是懒惰，是**切换**。

`VSCode → 微信 → 浏览器 → VSCode → GitHub → 微信`，一天切 200 次，每次认知成本 3~5 分钟——你三分之一的时间不是在工作，是在**找回工作状态**。

> 🎯 番茄钟把 25 分钟锁死在一个任务上。到了弹窗提醒休息。白噪音辅助。**专注模式直接屏蔽 B 站和抖音。**

### ✅ 待办 + 周计划 —— 让你知道然后干什么

你最大的时间黑洞：**不是不想干，是不知道干什么，于是打开手机刷十分钟等灵感。**

| 模式 | 适合场景 | 比如 |
|------|---------|------|
| ⏱️ 计时型 | 有明确截止时间的任务 | "25 分钟内搞定登录表单" |
| 🎯 目标型 | 结果导向（没明确时长） | "重构到单元测试全绿为止" |
| 🔁 习惯型 | 每日重复性积累 | "每天背 20 个单词" |

周计划按月 → 周 → 日三级层级，拖拽分配。**打开电脑第一眼看到的是今天要做什么，不是今天要看什么视频。**

### 🏆 习惯打卡 + 成就 —— 让你想回来

单独的习惯 App 你装了 3 个，全弃了。为什么？**因为它们跟你的工作数据完全割裂——你打不打卡，和你的时间流向毫无关系。**

ChallengeDaily 这边：
- 🍅 今天 8 个番茄 → 自动累计「🔥 专注达人」勋章
- 📝 连续 7 天写日记 → 解锁「🧘 自我觉醒者」
- 📅 连续打卡喝水 21 天 → 解锁「💧 生命之源」

> 这些不是游戏化噱头。是你的数据在替你说话。

### 🤖 AI 日报 —— 不用写日报

不是 ChatGPT 式的"今日总结"。是 AI 读完你今天**全部屏幕记录**后，按 12 个类别自动分类，写成的日报。

```
📅 2026年7月9日 · AI 日报
━━━━━━━━━━━━━━━━━━━━━━
💻 开发      3.2h  ██████████████░░░░░░░░
💬 沟通      1.8h  ████████░░░░░░░░░░░░░░
📚 学习      1.5h  ██████░░░░░░░░░░░░░░░░
☕ 摸鱼      0.8h  ███░░░░░░░░░░░░░░░░░░░
━━━━━━━━━━━━━━━━━━━━━━
✅ 有效时间 6.5h  🔥 8 个番茄  📈 比昨天 +12%
```

把同样数据喂给内置 AI 对话：

> 👤 *"我这周会议占比为什么涨了？明天怎么调？"*
> 🤖 *"本周会议占 28%（上周 15%），集中在新项目启动期的需求对齐。建议：把非决策性会议改为飞书异步沟通，可腾出每天 1~1.5 小时。"*

**它的回答基于你的真实行为数据，不是通用鸡汤。**

### 🐾 桌面宠物 + 📓 日记 + 🔬 深度洞察 —— 让你不孤独

角落里那只透明小宠物实时显示你当前的状态——「💻 正在写代码」「💬 刚切到微信」「☕ 已摸鱼 18 分钟」。

不是玩具。是你对"当下"的直觉锚点——**你看见它显示"摸鱼"的时候，会自动切回来。比任何提醒都管用。**

日记 AI 自动关联当天工作数据，你的反思不再对着空白文本框硬编。周报和深度洞察基于 **10 个学术框架**量化分析，告诉你"碎片化学习占比 60%，建议减少并行任务"——这不是 AI 拍脑袋，是心理学 + 教育学框架算出来的。

---

## 🔒 隐私：不回避

| 🚫 不做 | ✅ 做 |
|---------|-----|
| 截图不存储，分析完立即删除 | 微信 / 飞书 / 密码管理器 / 银行页面自动跳过 |
| API Key 不写 .env 明文 | Windows DPAPI 加密存储 |
| 数据不传云端 | 100% 本地，断网正常跑 |
| 不接 Key 也能用的功能不锁 | 内置 30+ 规则自动分类 |

---

## 🆚 同类产品对比

| | RescueTime | Toggl | Timing | ManicTime | 🔥 ChallengeDaily |
|---|:---:|:---:|:---:|:---:|:---:|
| 📸 自动记录 | ✅ | — | ✅ | ✅ | ✅ |
| 🤖 AI 识别屏幕 | — | — | — | — | ✅ |
| 🍅 番茄钟 | — | — | — | — | ✅ |
| ✅ 待办/周计划 | — | — | — | — | ✅ |
| 🏆 习惯/成就 | — | — | — | — | ✅ |
| 📊 AI 日报 | — | — | — | — | ✅ |
| 💬 AI 对话 | — | — | — | — | ✅ |
| 🐾 桌面宠物 | — | — | — | — | ✅ |
| 🔔 Webhook | — | — | — | — | ✅ |
| 🏠 100% 本地 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 💰 免费开源 | — | — | — | — | ✅ |

> 💡 其他工具解决"记录"。ChallengeDaily 解决 **记录 → 理解 → 优化 → 产出**一整条链。

---

## 🪟 为什么是 Windows，为什么是现在

<p align="center">
  🏆 <b>Timing</b> / <b>Rize</b> / <b>Daily</b> 全部 Mac 独占<br>
  👥 <b>1.5 亿 Windows 用户</b> 没人管
</p>

同时智谱 GLM-4V-Flash 视觉模型已能精准识别屏幕内容，且**完全免费**。以前烧钱的 AI 能力现在成本趋零。技术窗口开了，市场缺口在那——这个坑，我们来填。

---

## 🚀 跑起来

```bash
git clone https://github.com/EXtreameChallenge/ChallengeDaily.git
cd xiaohei-daily
pip install -r requirements.txt
cd client && npm install && npm run build && cd ..
python main.py
```

打开 `http://127.0.0.1:58888`，数据已经在采了。

> 📦 打包版去 [Releases](https://github.com/EXtreameChallenge/ChallengeDaily/releases) 下载 `Setup.exe` | 需 Python 3.10+
>
> 🧠 不配 Key 也能用。接智谱 / DeepSeek / Qwen / Kimi 的 Key 开启 AI 视觉识别。

---

## 🧰 技术栈

```
⚡ Electron 31  ·  ⚛️ React 18 + TS  ·  🐍 Python 3.11  ·  🌶️ Flask 3
🗄️ SQLite WAL (23 表)  ·  🖼️ GLM-4V-Flash  ·  🔐 Windows DPAPI
```

✅ 已通过 3 轮深度审计 + 30+ 项 Loop Engineering 修复，核心链路在本地环境连续验证通过。

---

| 平台 | 仓库 |
|------|------|
| 🐙 GitHub | [EXtreameChallenge/ChallengeDaily](https://github.com/EXtreameChallenge/ChallengeDaily) |
| 🏮 Gitee | [EXtreameChallenge/ChallengeDaily](https://gitee.com/EXtreameChallenge/ChallengeDaily) |
| 🦊 GitCode | [EXtreameChallenge/ChallengeDaily](https://gitcode.com/EXtreameChallenge/ChallengeDaily) |

📌 灵感：[samlaying/xiaohei-daily](https://github.com/samlaying/xiaohei-daily)（仅 macOS） ·  MIT License

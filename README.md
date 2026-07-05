---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: '154aa917-5915-4acd-90d3-15f4ddfe0ace'
  PropagateID: '154aa917-5915-4acd-90d3-15f4ddfe0ace'
  ReservedCode1: '5de41dbd-5405-4991-ad02-357a3b7ec51d'
  ReservedCode2: '5de41dbd-5405-4991-ad02-357a3b7ec51d'
---

# ChallengeDaily Windows 版

自动截屏 → AI 视觉分析 → 工作分类 → 生成 Markdown 日报

Windows 原生版本，灵感来自 [samlaying/xiaohei-daily](https://github.com/samlaying/xiaohei-daily)（仅 macOS）。

## 功能特性

- **定时截屏**：每隔 N 秒自动截取全屏，保存为压缩 JPEG
- **AI 视觉分析**：将截图发送给 AI Vision 模型，智能识别工作内容（兼容 OpenAI 协议，支持 DeepSeek、Qwen、Kimi 等）
- **无 API Key 也能用**：未配置 AI 时自动退化为应用名称规则分类（30+ 应用规则），同样生成日报
- **12 类工作分类**：开发 / 会议 / 沟通 / 文档 / 测试 / 设计 / 运维 / 数据分析 / 学习 / 管理 / 产品 / 生活
- **Markdown 日报**：每日自动生成分类统计 + 时间线 + 应用时长报告
- **HTTP API**：8 个 REST 接口，方便查询和手动触发
- **隐私脱敏**：AI 分析时自动屏蔽隐私关键词
- **自动清理**：超过保留天数的截图自动删除

## 快速开始

```bash
# 1. 克隆项目
cd xiaohei-daily

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置 AI（可选，不配也能用规则分类）
set AI_API_KEY=sk-xxxxx
set AI_BASE_URL=https://api.openai.com/v1
set AI_MODEL=gpt-4o

# 4. 启动
python main.py
```

启动后访问 http://127.0.0.1:8089 查看 API 文档。

按 `Ctrl+C` 正常退出，会自动生成今日日报。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SCREENSHOT_INTERVAL_SEC` | 60 | 截图间隔（秒） |
| `SCREENSHOT_QUALITY` | 70 | JPEG 压缩质量（1-100） |
| `SCREENSHOT_MAX_WIDTH` | 1920 | 截图最大宽度，超过等比缩放 |
| `HTTP_PORT` | 8089 | HTTP API 端口 |
| `AI_BASE_URL` | https://api.openai.com/v1 | AI 接口地址 |
| `AI_API_KEY` | （空） | AI API Key，为空则退化为规则分类 |
| `AI_MODEL` | gpt-4o | AI 模型名称 |
| `RETENTION_DAYS` | 7 | 截图保留天数 |
| `PRIVACY_KEYWORDS` | （空） | 隐私关键词，逗号分隔 |

## HTTP API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/timeline?startDate=&endDate=` | 工作时间线 |
| GET | `/api/daily-summary?startDate=&endDate=` | 聚合统计 |
| GET | `/api/app-usage?startDate=&endDate=` | 应用使用时长 |
| GET | `/api/report?startDate=&endDate=` | 已生成的报告列表 |
| POST | `/api/generate-report?date=` | 手动触发生成日报 |
| POST | `/api/capture` | 手动触发截图分析 |

## 项目结构

```
xiaohei-daily/
├── main.py              # 入口：主循环 + 优雅关闭
├── config.py            # 配置管理（环境变量）
├── db.py                # SQLite 数据库操作
├── screenshot.py        # 屏幕截图（mss + Pillow）
├── app_tracker.py       # 前台应用追踪（Win32 API）
├── prompt.py            # AI 分析提示词
├── ai_client.py         # AI Vision API 调用
├── classifier.py        # 12 类分类（AI + 规则）
├── collector.py         # 采集调度核心
├── report.py            # Markdown 日报生成
├── server.py            # Flask HTTP API
├── requirements.txt     # Python 依赖
├── .gitignore
└── data/                # 运行时数据（自动创建）
    ├── xiaohei.db       # SQLite 数据库
    ├── screenshots/     # 截图文件
    └── reports/         # 生成的日报
```

## 技术栈

- **截图**：mss + Pillow
- **应用追踪**：Win32 API（ctypes）
- **数据库**：SQLite（WAL 模式 + busy_timeout）
- **AI**：OpenAI Python SDK（兼容协议）
- **HTTP**：Flask
- **平台**：Windows 10/11

## 与 macOS 版的区别

| 项目 | macOS 版 | Windows 版 |
|------|----------|------------|
| 截图 | screencapture | mss + Pillow |
| 应用追踪 | AppleScript | Win32 API (ctypes) |
| 睡眠/唤醒 | IOKit 电源通知 | Event.wait() + atexit |
| 数据库 | SQLite | SQLite (WAL + busy_timeout) |
| AI 分类 | OpenAI API | OpenAI 协议兼容 + 规则兜底 |

## License

MIT
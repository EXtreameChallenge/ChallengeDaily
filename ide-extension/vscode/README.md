# ChallengeDaily Tracker — VS Code 扩展

在 VS Code 状态栏实时查看 ChallengeDaily 今日专注时长、当前告警状态，并提供快捷命令启动番茄钟。

## 功能

- **状态栏显示**：右下角实时显示今日专注时长（如 `CD 2h30m`）
- **告警高亮**：检测到分心告警时，状态栏变橙色
- **快捷命令**：
  - `ChallengeDaily: 显示今日状态` — 在输出面板展示详细数据
  - `ChallengeDaily: 启动番茄钟` — 一键启动 25 分钟番茄钟（快捷键 `Ctrl+Shift+P`）
  - `ChallengeDaily: 打开主界面` — 通过浏览器打开 ChallengeDaily 主窗口
  - `ChallengeDaily: 配置 API Token` — 设置与后端通信所需的 Token

## 安装

### 方式一：从源码打包安装

```bash
# 进入扩展目录
cd ide-extension/vscode

# 安装依赖（可选，开发时需要）
npm install

# 打包成 .vsix
npx vsce package

# 在 VS Code 中安装
code --install-extension challengedaily-tracker-0.1.0.vsix
```

### 方式二：开发模式调试

1. 用 VS Code 打开 `ide-extension/vscode` 目录
2. 按 `F5` 启动扩展开发宿主
3. 在新窗口中测试功能

## 配置

在 VS Code 设置中搜索 `challengedaily`：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `challengedaily.apiUrl` | `http://127.0.0.1:58888` | 后端 API 地址 |
| `challengedaily.apiToken` | `""` | API Token（必填，在 ChallengeDaily 设置页查看） |
| `challengedaily.refreshIntervalSec` | `30` | 状态栏刷新间隔（10-600 秒） |
| `challengedaily.statusBarAlignment` | `right` | 状态栏对齐方式 |

## 获取 API Token

1. 启动 ChallengeDaily 桌面应用
2. 进入"设置" → "关于"页面
3. 复制显示的 API Token
4. 在 VS Code 中运行 `ChallengeDaily: 配置 API Token` 命令，粘贴 Token

## 快捷键

- `Ctrl+Shift+P` (Mac: `Cmd+Shift+P`) — 启动番茄钟

## 数据安全

- 所有请求仅发送到本地 127.0.0.1，不外传任何数据
- API Token 存储在 VS Code 全局配置中
- 状态栏仅显示专注时长数字，不显示具体活动内容

## 与 Git 关联

ChallengeDaily 后端已内置 Git 集成模块，可在主应用的"设置"页面添加本地 git 仓库路径，
扩展启动番茄钟时后端会自动关联代码提交记录，生成"代码产出报告"段落。

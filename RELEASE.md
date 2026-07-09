# ChallengeDaily 发布流程

> 本文档说明如何通过 Git + GitHub 实现软件工程化迭代、版本管理和自动更新。

---

## 1. 版本号说明

版本号写在 `client/package.json` 中：

```json
{
  "version": "2.6.1"
}
```

规则采用**语义化版本（SemVer）**：

| 变化位置 | 含义 | 示例 |
|---------|------|------|
| 第 1 位 | 大版本，不兼容升级 | `3.0.0` |
| 第 2 位 | 新增功能 | `2.7.0` |
| 第 3 位 | 修复 bug / 小优化 | `2.6.2` |

---

## 2. 日常开发流程

每次让 Agent 完成改动后，执行：

```bash
cd xiaohei-daily
git status
git add .
git commit -m "feat: 描述这次改动"
```

提交信息规范：

| 前缀 | 含义 |
|------|------|
| `feat:` | 新功能 |
| `fix:` | 修复 bug |
| `ui:` | 界面样式调整 |
| `refactor:` | 重构代码 |
| `docs:` | 文档更新 |
| `chore:` | 杂项（配置、依赖等） |

---

## 3. 连接 GitHub 远程仓库

### 第一步：在 GitHub 创建仓库

1. 打开 https://github.com/new
2. Repository name 填 `ChallengeDaily`
3. 选择 **Private**（私有）
4. 不要勾选 "Initialize this repository with a README"
5. 点击 Create repository

### 第二步：添加远程地址并推送

创建后 GitHub 会显示类似下面的命令，在 PowerShell 中执行：

```bash
cd xiaohei-daily
git remote add origin https://github.com/你的用户名/ChallengeDaily.git
git branch -M main
git push -u origin main
```

如果提示输入密码，请输入 GitHub 的 **Personal Access Token**（不是登录密码）。

---

## 4. 发布新版本

### 第一步：更新版本号

```bash
cd client
npm run bump    # 自动将 patch 版本 +1（如 2.6.1 → 2.6.2）
cd ..
git add client/package.json
git commit -m "release: bump version"
```

### 第二步：打标签并推送

```bash
git tag v2.6.2
git push origin main --tags
```

### 第三步：GitHub Actions 自动打包

推送 tag 后，GitHub Actions 会自动：

1. 在 Windows 服务器上安装依赖
2. 运行 `npx tsc --noEmit` 类型检查
3. 运行 `npm run build` 打包（使用 package.json 中的版本号）
4. 生成 `ChallengeDaily-2.6.2-Setup.exe`
5. 自动创建 GitHub Release 并上传安装包

你可以在仓库页面的 **Actions** 标签页查看打包进度。

---

## 5. 用户自动更新

用户安装过一次后，软件启动时会自动检测 GitHub Releases 上的最新版本。

如果检测到新版本，会弹出提示让用户确认更新。

---

## 6. 回退历史版本

### 查看提交历史

```bash
git log --oneline
```

### 回退到上一个版本

```bash
git reset --hard HEAD~1
```

### 回退到指定版本

```bash
git reset --hard 提交ID
```

### 恢复误删文件

```bash
git checkout -- 文件名
```

---

## 7. 注意事项

- `data/` 目录和 `*.db` 文件已被 `.gitignore` 排除，不会上传到 GitHub
- `node_modules/` 和构建产物也不会上传
- 不要把 `.env` 或 API 密钥提交到 GitHub
- 发布前确保 `client/package.json` 中的 `publish` 配置指向正确的 GitHub 仓库

---

## 8. 快速命令清单

```bash
# 查看当前状态
git status

# 提交改动
git add .
git commit -m "feat: xxx"

# 推送代码
git push origin main

# 发布版本
cd client && npm run bump && cd ..
git add client/package.json
git commit -m "release: bump version"
git tag v2.6.2
git push origin main --tags

# 查看历史
git log --oneline

# 回退
git reset --hard HEAD~1
```

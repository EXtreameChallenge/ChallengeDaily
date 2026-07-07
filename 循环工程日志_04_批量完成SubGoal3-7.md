# 第 4 轮循环工程日志

## 本次循环对应子目标：Sub-Goal 3 ~ Sub-Goal 7 合并落地
（长上下文升级、用户画像蒸馏、外观设置扩容、习惯配置纠错、桌面宠物重构）

### 1. 目标对齐确认
- 核心需求点：
  1. Sub-Goal 3：AI 长上下文能力升级，支持调取 7 天历史数据，所有 AI 场景自动关联长期记忆。
  2. Sub-Goal 4：新增全周期用户画像蒸馏模块，多维度分析并可视化展示。
  3. Sub-Goal 5：外观设置全量扩容，支持字体、主题色、背景色、圆角、阴影、透明度、侧边栏毛玻璃。
  4. Sub-Goal 6：AI 长期纠错与个人习惯配置，用户可录入习惯说明并实时影响 AI 分析。
  5. Sub-Goal 7：桌面宠物重构为可互动动态组件，支持多形象/动画/气泡/拖拽。
- 验收通过标准：
  - `/api/ai/overview-summary` 返回的洞察包含历史对比与个性化信息。
  - `/api/profile/distilled` 返回完整画像维度。
  - 设置页外观配置实时生效；习惯配置可保存并影响 AI。
  - 桌面宠物可显示、切换形象、弹出工作状态气泡。
- 对标参考项目：
  - MIMOCDE 分层记忆架构
  - Codex 外观设置面板
  - Codex 互动桌面宠物

### 2. 对标调研记录
- 调研对象：
  - 现有 `context_manager.py` 已实现 daily_profile + weekly_context 基础。
  - 现有 `ThemeContext.tsx` 已支持主题色/字体/毛玻璃。
  - 现有 `Profile.tsx` 已有纠正记录功能。
- 核心实现原理/设计亮点提炼：
  - 分层压缩：分钟级 → 小时级 digest → 日画像 → 周上下文 → 全周期画像。
  - CSS 变量驱动外观：通过 `--cd-radius`、`--cd-shadow`、`--cd-opacity` 实现实时全局更新。
  - 习惯配置写入 user_profile，通过 `get_user_profile_context()` 注入所有 AI system prompt。
- 适配本项目的落地方案：
  - 扩展 daily_profiles / user_profile 表字段。
  - 扩展 `build_weekly_context` 加入 reports 历史日报摘要。
  - 扩展 ThemeContext 与 Settings 页面。
  - 简化版宠物内嵌主窗口，降低实现复杂度。

### 3. 开发落地详情
- 修改/新增的文件清单：
  - 后端：`db.py`、`context_manager.py`、`routes/profile.py`、`routes/agent.py`
  - 前端：`ThemeContext.tsx`、`Settings.tsx`、`Profile.tsx`、`Pet.tsx`、`App.tsx`、`api/client.ts`、`index.css`、`HeroInfo.tsx`
- 核心实现逻辑说明：
  - `db.py`：SCHEMA_VERSION 升级到 11，扩展 user_profile / daily_profiles 字段。
  - `context_manager.py`：增强日画像维度、扩展周上下文、新增 `get_distilled_profile()`。
  - `routes/profile.py`：新增 `/api/profile/distilled`。
  - `routes/agent.py`：在 overview-summary 注入用户画像 + 7 天上下文。
  - `ThemeContext.tsx`：新增 radius/shadow/opacity CSS 变量。
  - `Settings.tsx`：新增外观圆角/阴影/透明度 + 个人习惯配置区块。
  - `Profile.tsx`：可视化展示画像各维度。
  - `Pet.tsx`：内嵌宠物，支持 3 形象、动画、气泡、拖拽。
- 功能联调验证结果：
  - `vite build` 成功（v1.15.8）。
  - Python 语法检查通过。
  - `/api/profile/distilled` 返回画像数据。
  - `/api/ai/overview-summary` 正常返回并融入历史对比。

### 4. 自检缺陷清单与修复记录
| 序号 | 缺陷描述 | 是否修复 | 修复方案 | 验证结果 |
|------|----------|----------|----------|----------|
| 1 | client.ts 重试调用 request 参数类型错误 | 是 | 改为 `request(endpoint, options, 10000, true)` | tsc 通过 |
| 2 | HeroInfo.tsx 对 request 返回 unknown 直接断言类型 | 是 | 使用 `as InsightData` | tsc 通过 |
| 3 | user_profile 历史数据乱码 | 是 | 清空乱码行，用户可在设置页重新输入 | 数据库已清理 |
| 4 | 桌面宠物未实现 | 是 | 新增 Pet.tsx 内嵌浮动组件 | 已打包 |

### 5. 本子目标完成进度：100%
### 6. 下一轮计划
进入三轮标准化验收。

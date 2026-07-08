---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: '357b8e99-02e9-44bb-b28d-ea3d7d12b10d'
  PropagateID: '357b8e99-02e9-44bb-b28d-ea3d7d12b10d'
  ReservedCode1: 'c17f13c1-eb31-4215-be1c-49100214afbf'
  ReservedCode2: 'c17f13c1-eb31-4215-be1c-49100214afbf'
---

# ChallengeDaily 前端审计报告

> 审计范围：`client/src/` 全部源码 + `client/electron/` + 配置文件
> 审计日期：2026-07-08
> 审计维度：安全 / 稳定性 / 性能 / 用户体验

---

## 一、安全问题

### [高] API Token 以 URL 查询参数暴露

- **文件**：`src/api/client.ts:385-392, 506-507, 559-560`
- **描述**：导出/备份相关 API（如导出日报、下载数据、导出截图）将 `X-API-Token` 拼接到 URL 查询参数 `?token=${token}` 中。Token 出现在 URL 中会被浏览器历史、服务器访问日志、Referer 头等记录，存在泄露风险。
- **修复建议**：
  1. 优先改为 POST 请求 + 请求头传 Token，前端用 `blob` 方式下载
  2. 若必须用 GET，改为后端生成一次性短时效签名 URL（类似 S3 presigned URL），而非直接传原始 Token

### [高] IPC 发送者校验失败时默认放行

- **文件**：`electron/main.cjs:390`
- **描述**：`isFromMainWindow` 函数在 `sender.getOwnerBrowserWindow()` 抛异常时 catch 块默认返回 `true`，这意味着如果校验逻辑异常，未授权的渲染进程可以通过 IPC 调用任意后端接口。
- **修复建议**：校验失败或异常时应默认返回 `false`（deny by default），而非 `true`

### [中] sandbox: false 降低安全性

- **文件**：`electron/main.cjs:258, 327`
- **描述**：主窗口和宠物窗口的 `webPreferences` 均设置 `sandbox: false`。虽然 `contextIsolation: true` 和 `nodeIntegration: false` 提供了基础隔离，但关闭沙箱意味着预加载脚本拥有完整 Node.js 能力，一旦预加载脚本有漏洞，渲染进程可利用。
- **修复建议**：逐步迁移到 `sandbox: true`，预加载脚本仅使用 `contextBridge` 暴露有限 API

### [中] CSP 允许 `style-src 'unsafe-inline'`

- **文件**：`index.html:9`
- **描述**：Content Security Policy 中 `style-src` 包含 `'unsafe-inline'`，允许内联样式注入。虽然 Tailwind CSS 依赖内联样式，但这同时也允许 XSS 攻击者通过 style 属性窃取数据（如 CSS exfiltration）。
- **修复建议**：考虑使用 Tailwind 的 CSS-only 模式（`@tailwindcss/cli` 生成独立 CSS 文件），移除 `'unsafe-inline'`，改用 `style-src 'self'` + nonce/hash

### [中] 新手引导完成标记可被绕过

- **文件**：`src/pages/Onboarding.tsx:95`
- **描述**：`localStorage.setItem('cd_onboarding_done', '1')` 存储引导完成标记，用户可直接通过 DevTools 修改 localStorage 跳过引导。对于桌面应用，这虽不严重，但意味着用户可能跳过 API Key 配置等关键步骤。
- **修复建议**：将引导完成标记同步到后端设置（后端也校验），而非仅靠前端 localStorage

### [低] 新手引导保存失败静默处理

- **文件**：`src/pages/Onboarding.tsx:92-94`
- **描述**：`handleComplete` 中 `catch` 仅 `console.error`，用户点击"开始使用"后即使保存失败也会跳转主页面，导致 AI 配置丢失。
- **修复建议**：保存失败时用 Toast 提示用户并阻止跳转，或至少标记保存失败状态供下次进入时重试

---

## 二、稳定性问题

### [严重] useEffect 依赖数组使用 `.map().join('|')` 导致无限重渲染

- **文件**：
  - `src/pages/Overview.tsx:148`
  - `src/pages/AppRecords.tsx:39`
  - `src/pages/Timeline.tsx:65`
  - `src/pages/Profile.tsx:103`
  - `src/pages/AppTags.tsx:67`
- **描述**：多个组件的 `useEffect` 依赖数组使用 `arr.map(x => x.prop).join('|')` 这种写法。虽然 `.join()` 每次返回新字符串，依赖比较是值比较（字符串相等即不重渲染），风险较低，但如果数组内容在每次渲染时都相同（空格/格式不同），会导致不必要重执行。更危险的是，如果依赖写法有误导致每次渲染产生不同字符串，则会无限循环。
- **修复建议**：改为 `useMemo` 先缓存字符串结果，或改用自定义 hook 比较器：
  ```tsx
  const depKey = useMemo(() => arr.map(x => x.prop).join('|'), [arr])
  useEffect(() => { ... }, [depKey])
  ```

### [高] 多处 useEffect 异步操作未处理组件卸载后的 setState

- **文件**：
  - `src/components/Sidebar.tsx:96-102`
- **描述**：`Sidebar.tsx` 中 `getTodayStats().then(setTodayStats)` 没有 `cancelled` 守卫。如果组件在请求完成前卸载，React 会报 "Can't perform a React state update on an unmounted component" 警告（React 18 虽不报错但仍是不良实践）。
- **修复建议**：加上 `mountedRef` 或 `cancelled` 标记：
  ```tsx
  useEffect(() => {
    let cancelled = false
    getTodayStats().then(data => { if (!cancelled) setTodayStats(data) })
    return () => { cancelled = true }
  }, [])
  ```
  注意：`Profile.tsx:90-102` 和 `AppTags.tsx:51-66` 已正确使用 `cancelled` 守卫，做得好。

### [高] Habits/Todos/Countdowns 异步操作缺少错误处理

- **文件**：
  - `src/pages/Habits.tsx:25, 31-33` — `createHabit`、`logHabit`、`deleteHabit` 均无 try/catch
  - `src/pages/Diary.tsx:47, 75` — `catch {}` 空 catch 完全吞掉错误
  - `src/pages/Achievements.tsx:34` — `catch {}` 空 catch
- **描述**：Habits 页面的增删改操作没有错误处理，API 调用失败时 Promise rejection 不会被捕获，可能导致未处理的 Promise rejection 错误。Diary 和 Achievements 页面 `catch {}` 完全吞掉错误，用户操作失败时毫无反馈。
- **修复建议**：添加 try/catch + Toast 提示用户操作失败

### [中] Focus 页面 visibilitychange 误判中断

- **文件**：`src/pages/Focus.tsx:93`
- **描述**：`visibilitychange` 事件监听中，任何页面不可见（包括用户 Alt+Tab 切到其他应用、点击任务栏等）都会增加 `interrupted` 计数。但用户短暂切换窗口（如查资料）不应算作专注中断。
- **修复建议**：
  1. 设置一个短暂容忍窗口（如 5 秒内切回不计中断）
  2. 或仅当离开超过一定时间（如 30 秒）时才计为中断

### [中] Focus 页面 setInterval 计时器漂移

- **文件**：`src/pages/Focus.tsx` (计时器逻辑)
- **描述**：番茄钟使用 `setInterval` 计时，`setInterval` 在浏览器标签不活跃时会被节流（Chrome 限制到 1s/次），长时间后可能产生累计漂移。
- **修复建议**：改用绝对时间差计算方式：记录开始时间戳，每次 tick 计算 `Date.now() - startTime`，而非依赖递减计数。

### [中] Achievements 页面 useEffect 中引用未记忆化函数

- **文件**：`src/pages/Achievements.tsx:51`
- **描述**：`useEffect(() => { const t = setTimeout(handleCheck, 2000); ... }, [])` — `handleCheck` 没有被 `useCallback` 包裹，在严格模式下可能触发两次调用（因为 `handleCheck` 闭包引用了 `load` 等）。
- **修复建议**：将 `handleCheck` 用 `useCallback` 包裹，或直接将逻辑内联到 `useEffect` 中

### [低] Multiple 页面缺少竞态保护

- **文件**：
  - `src/pages/Todos.tsx:29-42` — 快速连续点击"创建"可能创建重复待办
  - `src/pages/Agent.tsx:67-86` — 快速连续点击"添加 Webhook"可能创建重复
  - `src/pages/Countdowns.tsx:33-42` — 同上
- **描述**：表单提交按钮虽然有 `disabled` 逻辑，但 `disabled` 状态的设置和 API 调用不是原子操作。快速双击仍可能触发两次提交。
- **修复建议**：在 `onClick` handler 第一行就设置 `disabled`/`submitting` 状态，或使用防抖/节流

---

## 三、性能问题

### [高] Profile/AppTags 串行请求图标 URL

- **文件**：
  - `src/pages/Profile.tsx:91-99` — `for (const app of commonSoftware) { map[app.app_name] = await getAppIconUrl(app.app_name) }`
  - `src/pages/AppTags.tsx:53-61` — 同样模式
- **描述**：图标 URL 请求逐个串行执行。如果有 30 个应用，串行请求需要 30 × RTT 的时间（可能 3-5 秒），而并行只需约 1 个 RTT。
- **修复建议**：改为 `Promise.all` 或 `Promise.allSettled` 并行请求：
  ```tsx
  const results = await Promise.allSettled(
    apps.map(async app => ({ name: app.app_name, url: await getAppIconUrl(app.app_name) }))
  )
  ```

### [高] 大型组件缺少 memo/useMemo/useCallback

- **文件**：
  - `src/pages/Overview.tsx` (531 行) — 整个组件未使用任何 memoization
  - `src/pages/Settings.tsx` (1001 行) — 巨型组件，无 memoization
  - `src/components/HeroInfo.tsx` (576 行) — 多个 API 调用未缓存结果
  - `src/components/Sidebar.tsx` (291 行) — 内联函数/对象每次渲染重建
- **描述**：这些大型组件每次父组件重渲染时都完全重渲染，其中的内联对象/函数引用每次都变化，传递给子组件时也触发子组件重渲染。Settings.tsx 包含大量表单控件，任何输入变更都会重渲染整个 1000 行组件。
- **修复建议**：
  1. 将 Settings.tsx 拆分为独立 Section 组件（如 `AISettingsSection`、`AppearanceSettingsSection`等），每个用 `React.memo` 包裹
  2. 对回调函数使用 `useCallback`，对计算值使用 `useMemo`
  3. HeroInfo 的多个 API 调用结果用 `useMemo` 缓存

### [中] 缺少列表虚拟化

- **文件**：
  - `src/pages/Timeline.tsx` — 时间线条目可能达数百条
  - `src/pages/AppRecords.tsx` — 应用使用记录可能很多
  - `src/pages/AppTags.tsx` — 应用列表可能很长
  - `src/pages/WeekPlan.tsx` — 任务列表
- **描述**：所有长列表均采用直接渲染方式，当数据量大时（如 Timeline 一天 200+ 活动记录），DOM 节点数量庞大，严重影响滚动性能。
- **修复建议**：引入 `react-window` 或 `@tanstack/react-virtual` 进行列表虚拟化，仅渲染可视区域内的条目

### [中] recharts 包体积过大

- **文件**：`package.json` (recharts 依赖)
- **描述**：`recharts` 库约 300KB（gzip 后仍约 100KB），用于少量图表（Profile 页面的效率趋势柱状图、DeepInsight 的雷达图）。对于仅用 2-3 种图表的场景，这个体积不划算。
- **修复建议**：
  1. 考虑替换为更轻量的图表库如 `lightweight-charts`（~40KB）或直接用 SVG 手写简单图表
  2. 或保持 recharts 但确保它被正确 code-split（当前 `manualChunks` 已将 recharts 放入 vendor chunk，这已很好）

### [中] WordCloud canvas 重绘未正确 memoize

- **文件**：`src/components/WordCloud.tsx`
- **描述**：WordCloud 使用 canvas 绘制，但 draw 函数未用 `useCallback` 包裹，且每次重渲染时可能触发不必要的 canvas 重绘。
- **修复建议**：将绘制逻辑提取到 `useCallback` 或 `useEffect`（仅在依赖变化时重绘）

### [低] Settings.tsx 未拆分导致全量渲染

- **文件**：`src/pages/Settings.tsx` (1001 行)
- **描述**：整个设置页面是一个组件，包含 AI 配置、外观设置、数据管理等多个独立区域。任何状态变更（如切换一个 Toggle）都导致整个 1000 行组件重渲染。
- **修复建议**：拆分为 6-8 个独立 Section 组件，各有自己的局部状态，仅自身重渲染

---

## 四、用户体验问题

### [高] 多个页面硬编码紫色主题，与设计系统不一致

- **文件**：
  - `src/pages/Todos.tsx` — `bg-purple-500/20`, `text-purple-300`, `border-purple-400/30` 等
  - `src/pages/Diary.tsx` — 同上
  - `src/pages/Countdowns.tsx` — 同上
  - `src/pages/Habits.tsx` — 同上
  - `src/pages/Achievements.tsx` — `text-gold`, `border-gold/20`（`gold` 不是标准 Tailwind class）
- **描述**：这些页面使用硬编码的 `purple-*` Tailwind class，而项目设计系统使用 CSS 变量（`--cd-green: #7B68EE`、`--cd-green-light` 等）。深色模式下，硬编码的颜色可能无法正确适配（purple-300 在深色背景上可能对比度不足），且无法跟随主题色切换。
- **修复建议**：统一使用 CSS 变量 class（`text-cd-green`、`bg-cd-green-light`、`border-cd-green/20` 等），去除所有硬编码颜色

### [高] 缺少无障碍（A11y）支持

- **文件**：全局性问题，影响多个组件
- **描述**：
  1. 大多数交互元素缺少 `aria-label`（如 Sidebar 导航项、图标按钮）
  2. 模态框（`TaskDetailModal.tsx`）缺少焦点陷阱（Focus Trap）和 `Escape` 键关闭支持
  3. 侧边栏无键盘导航支持（无法用 Tab/Arrow 键切换页面）
  4. 图标仅按钮（如删除、测试连接）仅有 `title` 属性，无 `aria-label`
  5. 开关控件除了 Onboarding 的 `role="switch" aria-checked` 外，其他（如 Settings、Agent）均缺少无障碍属性
- **修复建议**：
  1. 所有 icon-only 按钮添加 `aria-label`
  2. 模态框添加 Focus Trap（可用 `focus-trap-react` 或自行实现）
  3. 侧边栏添加键盘导航（`role="navigation"` + `aria-current="page"` + 方向键支持）
  4. 所有 ToggleSwitch 统一添加 `role="switch"` 和 `aria-checked`

### [中] AIChat 不解析 Markdown 响应

- **文件**：`src/pages/AIChat.tsx`
- **描述**：AI 聊天响应使用 `whitespace-pre-wrap` 直接渲染纯文本。AI 生成的回复可能包含 Markdown 格式（列表、加粗、代码块等），但当前全部以纯文本显示，阅读体验差。而 Report.tsx 和 HistoryReports.tsx 已正确使用 `ReactMarkdown` + `remarkGfm` 解析 Markdown。
- **修复建议**：复用已有的 `ReactMarkdown` + `remarkGfm` 组件渲染 AI 响应，加上与 Report 页面相同的 `urlTransform` XSS 防护

### [中] WhiteNoise AudioContext 自动播放策略

- **文件**：`src/components/WhiteNoise.tsx:91`
- **描述**：`AudioContext` 在浏览器自动播放策略下创建时默认处于 `suspended` 状态，需要用户交互后才能 `resume()`。当前代码可能静默失败，导致用户点击播放却无声音。
- **修复建议**：在播放前检查 `audioCtx.state === 'suspended'` 并调用 `audioCtx.resume()`，如果仍然失败则提示用户

### [中] 缺少删除确认对话框

- **文件**：
  - `src/pages/Todos.tsx:55-62` — 删除待办无确认
  - `src/pages/Countdowns.tsx:45-52` — 删除倒数日无确认
  - `src/pages/Habits.tsx:36-39` — 删除习惯无确认
  - `src/pages/Agent.tsx:88-95` — 删除 Webhook 无确认
- **描述**：所有删除操作点击即执行，无二次确认。用户可能误触删除按钮导致数据永久丢失。
- **修复建议**：添加通用的确认对话框组件，删除操作需二次确认

### [中] Settings.tsx 过长导致导航困难

- **文件**：`src/pages/Settings.tsx` (1001 行)
- **描述**：设置页面包含 AI 配置、外观、数据管理、Webhook 等 10+ 个区域，页面很长但无锚点导航，用户需要大量滚动才能找到目标设置。
- **修复建议**：添加顶部标签页或侧边锚点导航（类似 VS Code 设置页），按类别分组

### [低] Diary 页面 `goNext` 中 `d <= new Date()` 比较

- **文件**：`src/pages/Diary.tsx:88`
- **描述**：`if (d <= new Date())` 中 `d` 是通过 `new Date(currentDate)` 创建的（仅含日期），而 `new Date()` 包含当前时分秒。在当天 23:59:59 内，`d` 可能等于当天但 `new Date()` 更大，导致比较结果正确但逻辑不够明确。
- **修复建议**：改为 `d.toDateString() <= new Date().toDateString()` 或用 dayjs 统一处理

### [低] 部分 SVG 图标使用内联 SVG 而非 lucide-react

- **文件**：`src/pages/Onboarding.tsx:314`
- **描述**：AI 步骤中的设置图标使用了大段内联 SVG（约 500 字符），而项目其他地方统一使用 `lucide-react` 的 `Settings` 图标。
- **修复建议**：统一使用 `lucide-react` 的 `Settings` 或 `Cog` 图标

---

## 五、架构级建议

### API 层过于庞大

- **文件**：`src/api/client.ts` (1137 行)
- **描述**：所有 API 调用、类型定义、Token 管理集中在一个文件中，难以维护。
- **建议**：按领域拆分为 `api/auth.ts`、`api/activities.ts`、`api/reports.ts`、`api/settings.ts`、`api/todos.ts` 等

### 页面组件风格不统一

- **文件**：多个页面
- **描述**：
  - 部分页面使用 `useAsyncData` + `ApiErrorDisplay` 模式（Overview、Timeline、Health、Agent、Profile、AppTags）——很好
  - 部分页面使用手动 `useState` + `useCallback` + `useEffect` 模式（Todos、Diary、Habits、Countdowns、Achievements）——不统一
- **建议**：统一使用 `useAsyncData` hook，保持代码风格一致性

### 深色模式下硬编码颜色未覆盖

- **文件**：`src/pages/WeekPlan.tsx`（已知使用硬编码深色主题颜色）
- **描述**：WeekPlan 等页面的深色模式颜色是硬编码的，而非使用 CSS 变量系统，导致主题切换时可能不一致。
- **建议**：全面审查并替换为 CSS 变量方案

---

## 六、问题统计

| 严重度 | 安全 | 稳定性 | 性能 | 用户体验 | 合计 |
|--------|------|--------|------|----------|------|
| 严重   | 0    | 1      | 0    | 0        | 1    |
| 高     | 2    | 2      | 2    | 2        | 8    |
| 中     | 3    | 3      | 3    | 4        | 13   |
| 低     | 1    | 1      | 1    | 2        | 5    |
| **合计** | **6** | **7** | **6** | **8** | **27** |

## 七、优先修复建议

1. **P0（立即修复）**：IPC 校验默认放行 → 改为默认拒绝
2. **P0（立即修复）**：API Token URL 暴露 → 改为 POST+Header 或签名 URL
3. **P1（本周）**：useEffect `.join('|')` 依赖 → 统一用 `useMemo` 缓存
4. **P1（本周）**：Habits 等页面缺少错误处理 → 添加 try/catch + Toast
5. **P1（本周）**：串行图标请求 → 改为 Promise.allSettled 并行
6. **P2（两周内）**：硬编码紫色主题 → 统一 CSS 变量
7. **P2（两周内）**：Settings.tsx 拆分 + memo 优化
8. **P2（两周内）**：无障碍支持（aria-label、Focus Trap、键盘导航）
9. **P3（一个月内）**：列表虚拟化、API 层拆分、recharts 替换评估
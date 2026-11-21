# ChallengeDaily 路由组织规范

> 路径: `routes/`
> 版本: 3.10.8 (2026-11-21)

## 协议兼容层（B40）

| 蓝图 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| aw_compat_bp | `/api/v1/*` | 可选 `AW_COMPAT_TOKEN` / `settings.aw_compat_token`；默认无鉴权（与 aw-server 一致） | ActivityWatch aw-server REST 兼容：bucket CRUD、events 批量写入、heartbeat、CSV/JSON 导出 |
| wakatime_compat_bp | `/api/heartbeat`、`/api/v1/users/current/heartbeats` | WakaTime API Key（`X-API-Token`、`Authorization: Basic` 或 `?api_key=`） | WakaTime 心跳兼容；连续 2 分钟同 entity 自动合并 |
| wakatime_compat_bp | `/api/wakatime/status`、`/api/wakatime/key`、`/api/wakatime/test` | 全局 `X-API-Token`（前端管理端点） | 状态、Key 查看/重置、测试心跳 |
| web_tracker_bp | `/api/web-activity/*` | 可选 `CHALLENGE_WEB_TOKEN`（默认 localhost 不校验） | WebExtension 单条/批量网页活动与今日统计 |

> 注意：`/api/v1/*` 与 `/api/heartbeat` 由兼容层自行鉴权，不走全局 `X-API-Token` 叠加校验（B40 修复，否则 WakaTime/AW 客户端无法接入）。
> 回归测试：`tests/test_round12_compat.py`。


## 路由分组（按业务域）

### 核心域
| 蓝图 | 前缀 | 说明 |
|------|------|------|
| health_bp | /api/health | 健康检查 |
| activities_bp | /api/activities | 活动追踪 |
| stats_bp | /api/stats | 统计 |
| reports_bp | /api/reports | 日报/周报 |
| settings_bp | /api/settings | 设置 |

### 效率工具域
| 蓝图 | 前缀 | 说明 |
|------|------|------|
| pomodoro_bp | /api/pomodoro | 番茄钟 |
| todos_bp | /api/todos | 待办事项 |
| diaries_bp | /api/diaries | 日记 |
| habits_bp | /api/habits | 习惯 |
| week_plan_bp | /api/week-plan | 周计划 |
| goals_bp | /api/goals | 目标 |

### 积分成就域
| 蓝图 | 前缀 | 说明 |
|------|------|------|
| achievements_bp | /api/achievements | 成就 |
| countdowns_bp | /api/countdowns | 倒计时 |
| leaderboard_bp | /api/leaderboard | 排行榜 |

### AI 智能域
| 蓝图 | 前缀 | 说明 |
|------|------|------|
| agent_bp | /api/agent | AI Agent |
| chat_bp | /api/chat | 聊天 |
| coach_bp | /api/coach | AI教练 |
| insight_bp | /api/insight | 洞察 |
| deep_insight_bp | /api/deep-insight | 深度洞察 |
| ai_intel_bp | /api/ai-intel | AI情报 |
| ai_today_summary_bp | /api/ai-today | AI今日总结 |

### 系统平台域
| 蓝图 | 前缀 | 说明 |
|------|------|------|
| auth_bp | /api/auth | 认证 |
| privacy_bp | /api/privacy | 隐私 |
| backup_bp | /api/backup | 备份 |
| webhooks_bp | /api/webhooks | Webhook |
| notifications_bp | /api/notifications | 通知 |
| exports_bp | /api/exports | 导出 |
| calendar_bp | /api/calendar | 日历 |
| preferences_bp | /api/preferences | 偏好 |
| audit_bp | /api/audit | 审计 |

### 小黑逆向迁移域（本次新增）
| 蓝图 | 前缀 | 说明 |
|------|------|------|
| keyboard_bp | /api/keyboard | 键盘热力图+音效 |
| tools_bp | /api/tools | 工具中心(通知/录音/MD/PDF) |
| enterprise_bp | /api/enterprise | 企业功能(账号/积分/模板/发布/微信/浏览器/MCP/小程序/学生/效率节/问卷/遥测/应用锁/朋友) |

### 其他高级域（原有）
- study_room_bp, rules_engine_bp, data_import_bp, imports_bp
- report_channels_bp, auto_report_bp, app_rules_bp, profile_bp
- git_integration_bp, benchmark_bp, local_model_bp, analytics_bp
- devops_bp, platform_bp, delight_bp, resilience_bp
- advanced_data_bp, security_bp2, smart_bp, uiux_bp, perf_bp
- integration_bp, viz_bp, observability_bp, workflow_bp
- cross_platform_bp, knowledge_graph_bp, smart_search_bp
- collaboration_bp, version_control_bp, offline_bp, realtime_bp
- migration_i18n_bp, accessibility_bp, ml_basic_bp, nlp_bp, cv_bp
- rec_ab_bp, flags_adv_bp, chaos_cap_bp, cost_compliance_bp
- privacy_dq_bp, mlops_bp, infra_edge_bp, network_dr_bp
| flow_control_bp, db_advanced_bp, cache_advanced_bp, mq_stream_bp
| security_advanced_bp, perf_apm_bp, deployment_bp, quality_docs_bp
| daily_card_bp, growth_bp, ritual_bp, scheduler_bp, mubu_bp
| memory_bp, obsidian_bp, reclassify_bp, web_tracker_bp
| aw_compat_bp, wakatime_compat_bp, user_profile_bp
| todo_extraction_bp, report_templates_bp, agent_routes_bp

## 统计
- 总蓝图数: 90+
- 本次新增: keyboard_bp, tools_bp, enterprise_bp (3个)

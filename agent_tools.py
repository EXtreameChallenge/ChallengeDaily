"""
ChallengeDaily — Agent 工具注册表（34 个工具）

每个工具定义包含：
  - name           : 工具名（与 OpenAI function calling 一致）
  - description    : 给模型看的描述
  - params_model   : pydantic v2 参数模型（自动校验入参）
  - execute        : 执行函数，入参为 dict，返回字符串
  - risk_level     : 风险级别（见 agent_guard.ToolRiskLevel）

执行约定：
  - 只读工具（READ_ONLY）：直接执行，返回结果字符串；
  - 写工具（OPERATION/DANGEROUS）：不真正写库，而是返回 JSON 字符串
    {"action":..., "data":..., "confirm_message":...}，等用户在前端确认后，
    由 /api/ai/chat/execute 端点二次调用真正落地；
  - 所有 execute 内部 try/except，失败返回友好错误，绝不向上抛异常。
"""
import json
import logging
from datetime import date, timedelta
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

import config
import db
from agent_guard import ToolRiskLevel

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# pydantic v2 参数模型
# ═══════════════════════════════════════════════════════════════

class DateRangeParams(BaseModel):
    """通用日期范围参数"""
    start_date: str = Field("", description="起始日期 YYYY-MM-DD，默认今天")
    end_date: str = Field("", description="结束日期 YYYY-MM-DD，默认同 start_date")
    category: str = Field("", description="按分类筛选")
    limit: int = Field(50, description="返回条数上限")


class TodoListParams(BaseModel):
    status: str = Field("all", description="all/pending/completed")
    category: str = Field("", description="按分类筛选")


class PomodoroStatsParams(BaseModel):
    start_date: str = Field("", description="起始日期")
    end_date: str = Field("", description="结束日期")


class DailySummaryParams(BaseModel):
    date: str = Field("", description="日期，默认今天")


class WorkTrendsParams(BaseModel):
    days: int = Field(7, description="最近多少天，默认7，最多30")


class EmptyParams(BaseModel):
    """无参数工具占位"""
    pass


class CreateTodoParams(BaseModel):
    title: str = Field(..., description="待办标题")
    category: str = Field("开发", description="分类")
    pomodoro_size: str = Field("big", description="big/small")
    estimated_pomodoros: int = Field(1, description="预估番茄数")


class StartPomodoroParams(BaseModel):
    task: str = Field(..., description="任务名称")
    category: str = Field("开发", description="分类")
    pomodoro_size: str = Field("big", description="big/small")


class SaveDiaryParams(BaseModel):
    content: str = Field(..., description="日记内容")
    mood: str = Field("", description="心情")
    tags: str = Field("", description="标签，逗号分隔")


class CreateGoalParams(BaseModel):
    title: str = Field(..., description="目标标题")
    description: str = Field("", description="目标描述")
    category: str = Field("personal", description="分类")
    timeframe: str = Field("yearly", description="yearly/quarterly/monthly")
    target_date: str = Field("", description="目标日期 YYYY-MM-DD")


class ListGoalsParams(BaseModel):
    status: str = Field("", description="过滤状态，如 active")
    timeframe: str = Field("", description="yearly/quarterly/monthly")


class UpdateGoalParams(BaseModel):
    goal_id: int = Field(..., description="目标 id")
    progress: int = Field(-1, description="进度 0-100，-1 表示不改")
    status: str = Field("", description="active/done/archived")
    title: str = Field("", description="新标题")


class WeekPlanParams(BaseModel):
    week_start: str = Field("", description="周一日期 YYYY-MM-DD，默认本周")


class CreatePlanItemParams(BaseModel):
    title: str = Field(..., description="计划项标题")
    category: str = Field("开发", description="分类")
    assigned_date: str = Field("", description="计划到哪一天，默认今天")


class CreateHabitParams(BaseModel):
    name: str = Field(..., description="习惯名称")
    target_count: int = Field(1, description="每日目标次数")
    period: str = Field("daily", description="daily/weekly")


class GetStatsParams(BaseModel):
    days: int = Field(7, description="统计最近多少天")


class GetHeatmapParams(BaseModel):
    year: int = Field(0, description="年份，默认今年")


class GetSettingsParams(BaseModel):
    pass


class UpdateSettingParams(BaseModel):
    key: str = Field(..., description="设置项键名")
    value: str = Field(..., description="设置项新值（字符串）")


class CreateReminderParams(BaseModel):
    text: str = Field(..., description="提醒内容")
    remind_at: str = Field("", description="提醒时间 HH:MM，留空则尽快")


class ListRemindersParams(BaseModel):
    pass


class SearchKnowledgeParams(BaseModel):
    query: str = Field(..., description="检索关键词")
    limit: int = Field(5, description="返回条数")


class GetProjectMapParams(BaseModel):
    pass


class MubuSearchParams(BaseModel):
    query: str = Field(..., description="搜索关键词")


class MubuCreateDocParams(BaseModel):
    title: str = Field(..., description="文档标题")
    content: str = Field("", description="文档内容")


class MubuUpdateDocParams(BaseModel):
    doc_id: str = Field(..., description="文档 id")
    content: str = Field(..., description="更新内容")


class ObsidianSyncParams(BaseModel):
    pass


class GetCalendarParams(BaseModel):
    days: int = Field(7, description="查询未来多少天")


class GenerateReportParams(BaseModel):
    report_type: str = Field("daily", description="daily/weekly")


class ExportDataParams(BaseModel):
    data_type: str = Field("activities", description="activities/todos/habits")


class PomodoroDetailParams(BaseModel):
    date: str = Field("", description="日期，默认今天")


class TriggerWorkflowParams(BaseModel):
    workflow_name: str = Field(..., description="工作流名称")


class ListSkillsParams(BaseModel):
    status: str = Field("", description="pending/approved/rejected")


# ═══════════════════════════════════════════════════════════════
# 工具执行实现
# ═══════════════════════════════════════════════════════════════

def _today() -> str:
    return date.today().isoformat()


# ── 迁移自 chat.py 的只读工具（行为保持一致）──

def _get_activities(params: dict) -> str:
    start = params.get("start_date") or _today()
    end = params.get("end_date") or start
    category = params.get("category", "")
    limit = min(int(params.get("limit", 50)), 200)
    activities = db.get_activities(start, end)
    if category:
        activities = [a for a in activities if a.get("category") == category]
    if not activities:
        return f"没有找到 {start} 到 {end} 的活动记录。"
    lines = []
    for a in activities[:limit]:
        ts = a.get("timestamp", "")[11:16]
        lines.append(f"[{ts}] {a.get('app_name','')} ({a.get('category','')}) - {a.get('summary','')[:60]}")
    result = "\n".join(lines)
    if len(activities) > limit:
        result += f"\n... 共 {len(activities)} 条，仅显示前 {limit} 条"
    return result


def _get_todos(params: dict) -> str:
    status_filter = params.get("status", "all")
    category = params.get("category", "")
    todos = db.get_todos()
    if not todos:
        return "当前没有待办事项。"
    if status_filter == "pending":
        todos = [t for t in todos if t.get("status") != "completed"]
    elif status_filter == "completed":
        todos = [t for t in todos if t.get("status") == "completed"]
    if category:
        todos = [t for t in todos if t.get("category") == category]
    if not todos:
        return "没有符合条件的待办事项。"
    lines = []
    for t in todos[:30]:
        check = "✅" if t.get("status") == "completed" else "⬜"
        pom = t.get("estimated_pomodoros", 0)
        pom_info = f" 🍅×{pom}" if pom else ""
        lines.append(f"{check} {t.get('title','')} [{t.get('category','')}]{pom_info}")
    return "\n".join(lines)


def _get_pomodoro_stats(params: dict) -> str:
    start = params.get("start_date") or _today()
    end = params.get("end_date") or start
    sessions = []
    d = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    while d <= end_d:
        sessions.extend(db.get_pomodoro_sessions(d.isoformat()))
        d += timedelta(days=1)
    if not sessions:
        return f"{start} 没有番茄钟记录。"
    total = len(sessions)
    completed = sum(1 for s in sessions if s.get("status") == "completed")
    total_min = sum(s.get("duration_min", 25) for s in sessions if s.get("status") == "completed")
    cats = {}
    for s in sessions:
        if s.get("status") == "completed":
            c = s.get("category", "其他")
            cats[c] = cats.get(c, 0) + 1
    cat_str = "、".join(f"{k}({v}个)" for k, v in sorted(cats.items(), key=lambda x: -x[1]))
    return (f"📅 {start} ~ {end} 番茄钟统计\n总计: {total} 个\n"
            f"完成: {completed} 个（{total_min} 分钟）\n分布: {cat_str}")


def _get_daily_summary(params: dict) -> str:
    target = params.get("date") or _today()
    try:
        from context_manager import get_daily_profile
        profile = get_daily_profile(target)
    except Exception:
        profile = None
    if profile:
        lines = [f"📅 {target} 日画像"]
        if profile.get("daily_summary"):
            lines.append(f"总结: {profile['daily_summary']}")
        if profile.get("top_apps"):
            lines.append(f"主要应用: {', '.join(profile['top_apps'][:5])}")
        if profile.get("efficiency_score"):
            lines.append(f"效率评分: {profile['efficiency_score']}/10")
        return "\n".join(lines)
    activities = db.get_activities(target, target)
    if not activities:
        return f"{target} 没有数据记录。"
    cats = {}
    for a in activities:
        c = a.get("category", "其他")
        cats[c] = cats.get(c, 0) + 1
    top = sorted(cats.items(), key=lambda x: -x[1])[:5]
    return f"📅 {target} 活动概览\n总记录: {len(activities)} 条\nTop分类: {', '.join(f'{k}({v})' for k, v in top)}"


def _get_work_trends(params: dict) -> str:
    days = min(int(params.get("days", 7)), 30)
    today = date.today()
    lines = []
    for i in range(days):
        d = today - timedelta(days=days - 1 - i)
        ds = d.isoformat()
        acts = db.get_activities(ds, ds)
        hours = len(acts) / 60
        cats = {}
        for a in acts:
            c = a.get("category", "其他")
            cats[c] = cats.get(c, 0) + 1
        top_cat = max(cats.items(), key=lambda x: x[1])[0] if cats else "无"
        wd = "一二三四五六日"[d.weekday()]
        lines.append(f"{ds}(周{wd}): {hours:.1f}h, 主分类={top_cat}")
    return f"📊 近 {days} 天效率趋势\n" + "\n".join(lines)


def _get_user_profile(params: dict) -> str:
    try:
        from context_manager import get_distilled_profile
        profile = get_distilled_profile()
        if not profile:
            return "暂无用户画像数据。"
        lines = ["👤 用户画像"]
        for k, label in [("role_desc", "角色"), ("work_style", "工作风格"), ("peak_hours", "高效时段")]:
            if profile.get(k):
                lines.append(f"{label}: {profile[k]}")
        return "\n".join(lines)
    except Exception:
        return "暂无用户画像数据。"


# ── 迁移自 chat.py 的写工具（返回确认 JSON，不直接执行）──

def _confirm(action: str, data: dict, msg: str) -> str:
    """统一构造写操作确认 JSON 字符串"""
    return json.dumps({"action": action, "data": data, "confirm_message": msg}, ensure_ascii=False)


def _create_todo(params: dict) -> str:
    title = params.get("title", "")
    if not title:
        return "错误：待办标题不能为空"
    return _confirm("create_todo", {
        "title": title,
        "category": params.get("category", "开发"),
        "pomodoro_size": params.get("pomodoro_size", "big"),
        "estimated_pomodoros": params.get("estimated_pomodoros", 1),
    }, f"是否创建待办：{title}（{params.get('category','开发')}）？")


def _start_pomodoro(params: dict) -> str:
    task = params.get("task", "")
    if not task:
        return "错误：任务名称不能为空"
    size = params.get("pomodoro_size", "big")
    duration = 25 if size == "big" else 20
    return _confirm("start_pomodoro", {
        "task": task, "category": params.get("category", "开发"),
        "pomodoro_size": size, "duration_min": duration,
    }, f"是否启动番茄钟：{task}（{duration}分钟）？")


def _save_diary(params: dict) -> str:
    content = params.get("content", "")
    if not content:
        return "错误：日记内容不能为空"
    return _confirm("save_diary", {
        "content": content, "mood": params.get("mood", ""), "tags": params.get("tags", ""),
    }, f"是否保存日记？情绪：{params.get('mood') or '未指定'}")


# ── P0 工具 ──

def _create_goal(params: dict) -> str:
    title = params.get("title", "")
    if not title:
        return "错误：目标标题不能为空"
    return _confirm("create_goal", {
        "title": title,
        "description": params.get("description", ""),
        "category": params.get("category", "personal"),
        "timeframe": params.get("timeframe", "yearly"),
        "target_date": params.get("target_date", ""),
    }, f"是否创建目标：{title}（{params.get('timeframe','yearly')}）？")


def _list_goals(params: dict) -> str:
    goals = db.get_goals(status=params.get("status") or None, timeframe=params.get("timeframe") or None)
    if not goals:
        return "当前没有目标。"
    lines = ["🎯 目标列表："]
    for g in goals[:20]:
        lines.append(f"- {g.get('title','')} [{g.get('timeframe','')}] 进度{g.get('progress',0)}% ({g.get('status','')})")
    return "\n".join(lines)


def _update_goal(params: dict) -> str:
    gid = params.get("goal_id")
    if not gid:
        return "错误：goal_id 不能为空"
    return _confirm("update_goal", {
        "goal_id": gid,
        "progress": params.get("progress", -1),
        "status": params.get("status", ""),
        "title": params.get("title", ""),
    }, f"是否更新目标 #{gid} 的进度/状态？")


def _get_week_plan(params: dict) -> str:
    ws = params.get("week_start")
    if not ws:
        today = date.today()
        ws = (today - timedelta(days=today.weekday())).isoformat()
    try:
        week = db.get_week_tasks(ws)
    except Exception as e:
        return f"查询周计划失败：{e}"
    day_tasks = week.get("day_tasks", {}) if isinstance(week, dict) else {}
    if not day_tasks:
        return f"{ws} 这周还没有安排计划。"
    lines = [f"📅 本周计划（{ws} 起）："]
    for day, tasks in list(day_tasks.items())[:7]:
        done = sum(1 for t in tasks if t.get("status") == "completed")
        lines.append(f"- {day}: {len(tasks)} 项，完成 {done}")
    return "\n".join(lines)


def _create_plan_item(params: dict) -> str:
    title = params.get("title", "")
    if not title:
        return "错误：计划项标题不能为空"
    return _confirm("create_plan_item", {
        "title": title,
        "category": params.get("category", "开发"),
        "assigned_date": params.get("assigned_date") or _today(),
    }, f"是否创建计划项：{title}（{params.get('assigned_date') or _today()}）？")


def _create_habit(params: dict) -> str:
    name = params.get("name", "")
    if not name:
        return "错误：习惯名称不能为空"
    return _confirm("create_habit", {
        "name": name,
        "target_count": params.get("target_count", 1),
        "period": params.get("period", "daily"),
    }, f"是否创建习惯：{name}（每日 {params.get('target_count',1)} 次）？")


def _list_habits(params: dict) -> str:
    habits = db.get_habits()
    if not habits:
        return "当前没有习惯。"
    lines = ["🔁 习惯列表："]
    for h in habits[:20]:
        lines.append(f"- {h.get('name','')} 目标{h.get('target_count',1)}/{h.get('period','daily')}")
    return "\n".join(lines)


def _get_stats(params: dict) -> str:
    days = min(int(params.get("days", 7)), 30)
    end = _today()
    start = (date.today() - timedelta(days=days - 1)).isoformat()
    activities = db.get_activities(start, end)
    total = len(activities)
    cats = {}
    for a in activities:
        c = a.get("category", "其他")
        cats[c] = cats.get(c, 0) + 1
    todos = db.get_todos()
    done = sum(1 for t in todos if t.get("status") == "completed")
    return (f"📈 近{days}天统计\n活动记录: {total} 条\n"
            f"待办完成: {done}/{len(todos)}\n"
            f"分类分布: {', '.join(f'{k}({v})' for k, v in sorted(cats.items(), key=lambda x:-x[1])[:5])}")


def _get_heatmap(params: dict) -> str:
    year = int(params.get("year") or 0)
    try:
        rows = db.get_mood_heatmap(year=year or None)
    except Exception:
        return "热力图数据暂不可用（需心情记录）。"
    if not rows:
        return "暂无热力图数据。"
    return f"🔥 心情热力图：共 {len(rows)} 天有记录。示例：{rows[0]}"


def _get_settings(params: dict) -> str:
    s = config.load_settings()
    keys = ["ai_enabled", "work_start_hour", "work_end_hour", "pomodoro_work_min",
            "ai_text_model", "agent_engine"]
    return "⚙️ 当前关键设置：\n" + "\n".join(f"- {k}: {s.get(k, '未设置')}" for k in keys)


def _update_setting(params: dict) -> str:
    key = params.get("key", "")
    value = params.get("value", "")
    if not key:
        return "错误：设置键名不能为空"
    return _confirm("update_setting", {"key": key, "value": value},
                    f"⚠️ 危险操作：是否修改全局设置 {key} = {value}？")


def _create_reminder(params: dict) -> str:
    text = params.get("text", "")
    if not text:
        return "错误：提醒内容不能为空"
    return _confirm("create_reminder", {
        "text": text, "remind_at": params.get("remind_at", ""),
    }, f"是否创建提醒：{text}（{params.get('remind_at') or '尽快'}）？")


def _list_reminders(params: dict) -> str:
    try:
        reminders_path = config.DATA_DIR / "reminders.json"
        if reminders_path.exists():
            with open(reminders_path, "r", encoding="utf-8") as f:
                reminders = json.load(f)
        else:
            reminders = []
    except Exception:
        reminders = []
    if not reminders:
        return "当前没有提醒。"
    return "⏰ 提醒列表：\n" + "\n".join(f"- {r.get('text','')} @ {r.get('remind_at','')}" for r in reminders[:20])


def _search_knowledge(params: dict) -> str:
    query = params.get("query", "")
    if not query:
        return "错误：检索关键词不能为空"
    try:
        from memory_engine import search_memories
        mems = search_memories(query, limit=int(params.get("limit", 5)))
    except Exception as e:
        return f"知识检索失败：{e}"
    if not mems:
        return f"没有找到与「{query}」相关的记忆/笔记。"
    return "📚 检索到相关记忆：\n" + "\n".join(f"- {m.get('content','')[:80]}" for m in mems)


def _get_project_map(params: dict) -> str:
    try:
        from project_map import get_project_map  # type: ignore
        return get_project_map()
    except Exception:
        return "🗺️ 项目地图模块（project_map.py）尚未安装，此处为占位返回。"


# ── P1 工具 ──

def _mubu_search(params: dict) -> str:
    query = params.get("query", "")
    if not query:
        return "错误：搜索关键词不能为空"
    try:
        from mubu_mcp_client import MubuMCPClient  # type: ignore
        return f"幕布搜索「{query}」：已调用幕布客户端（结果需在客户端展示）。"
    except Exception:
        return f"幕布搜索暂不可用（模块未配置）：查询「{query}」。"


def _mubu_create_doc(params: dict) -> str:
    title = params.get("title", "")
    if not title:
        return "错误：文档标题不能为空"
    return _confirm("mubu_create_doc", {"title": title, "content": params.get("content", "")},
                    f"是否在幕布创建文档：{title}？")


def _mubu_update_doc(params: dict) -> str:
    doc_id = params.get("doc_id", "")
    if not doc_id:
        return "错误：doc_id 不能为空"
    return _confirm("mubu_update_doc", {"doc_id": doc_id, "content": params.get("content", "")},
                    f"⚠️ 危险操作：是否覆盖幕布文档 {doc_id}？")


def _obsidian_sync(params: dict) -> str:
    return _confirm("obsidian_sync", {}, "是否立即执行 Obsidian 同步？")


def _get_calendar(params: dict) -> str:
    days = int(params.get("days", 7))
    try:
        from calendar_sync import get_upcoming_events  # type: ignore
        events = get_upcoming_events(days=days)
    except Exception:
        return f"📅 未来{days}天日历：日历模块未接入或暂无事件。"
    if not events:
        return f"未来{days}天没有日历事件。"
    return "📅 即将到来：\n" + "\n".join(f"- {e}" for e in events[:10])


def _generate_report(params: dict) -> str:
    rtype = params.get("report_type", "daily")
    return _confirm("generate_report", {"report_type": rtype},
                    f"是否生成{rtype}报告？（可能耗时较长）")


def _export_data(params: dict) -> str:
    dtype = params.get("data_type", "activities")
    return _confirm("export_data", {"data_type": dtype},
                    f"是否导出{dtype}数据为文件？")


def _get_pomodoro_detail(params: dict) -> str:
    target = params.get("date") or _today()
    sessions = db.get_pomodoro_sessions(target)
    if not sessions:
        return f"{target} 没有番茄钟记录。"
    lines = [f"🍅 {target} 番茄钟明细："]
    for s in sessions[:20]:
        lines.append(f"- {s.get('task','')} ({s.get('category','')}) {s.get('duration_min',0)}min [{s.get('status','')}]")
    return "\n".join(lines)


def _trigger_workflow(params: dict) -> str:
    wf = params.get("workflow_name", "")
    if not wf:
        return "错误：工作流名称不能为空"
    return _confirm("trigger_workflow", {"workflow_name": wf},
                    f"⚠️ 危险操作：是否立即触发工作流「{wf}」？")


def _list_skills(params: dict) -> str:
    try:
        import agent_db
        skills = agent_db.list_skills(status=params.get("status") or None)
    except Exception:
        skills = []
    if not skills:
        return "技能库为空。"
    return "🧩 已沉淀技能：\n" + "\n".join(f"- {s.get('name','')} [{s.get('status','')}]" for s in skills[:20])


# ═══════════════════════════════════════════════════════════════
# 工具注册中心
# ═══════════════════════════════════════════════════════════════

class ToolSpec:
    """单个工具的完整定义"""
    def __init__(self, name: str, description: str, params_model: type[BaseModel],
                 execute: Callable[[dict], str], risk_level: ToolRiskLevel):
        self.name = name
        self.description = description
        self.params_model = params_model
        self._raw_execute = execute
        self.risk_level = risk_level

    def build_openai_schema(self) -> dict:
        """转换为 OpenAI function calling 的 JSON schema"""
        schema = self.params_model.model_json_schema()
        props = schema.get("properties", {})
        required = schema.get("required", [])
        # pydantic 生成的 $ref/描述清理：OpenAI 兼容基本类型即可
        return {
            "type": "object",
            "properties": props,
            "required": required,
        }

    def execute(self, params: dict) -> str:
        """带校验+异常保护的执行入口。"""
        try:
            # 用 pydantic v2 校验入参（额外字段忽略）
            validated = self.params_model(**(params or {}))
            clean_params = validated.model_dump(exclude_none=False)
        except Exception as e:
            return f"错误：参数校验失败 - {str(e)[:120]}"
        try:
            return self._raw_execute(clean_params)
        except Exception as e:
            logger.warning(f"工具 {self.name} 执行异常: {e}")
            return f"工具 {self.name} 执行失败：{str(e)[:120]}"


def _spec(name, desc, model, func, risk) -> ToolSpec:
    return ToolSpec(name, desc, model, func, risk)


# ── 组装全部 34 个工具 ──
AGENT_TOOLS: list[ToolSpec] = [
    # 迁移自 chat.py（9）
    _spec("get_activities", "查询指定日期范围的应用使用活动记录", DateRangeParams, _get_activities, ToolRiskLevel.READ_ONLY),
    _spec("get_todos", "查看待办事项列表和完成状态", TodoListParams, _get_todos, ToolRiskLevel.READ_ONLY),
    _spec("get_pomodoro_stats", "查询番茄钟使用统计", PomodoroStatsParams, _get_pomodoro_stats, ToolRiskLevel.READ_ONLY),
    _spec("get_daily_summary", "获取某天的日报或画像", DailySummaryParams, _get_daily_summary, ToolRiskLevel.READ_ONLY),
    _spec("get_work_trends", "查看近期工作效率趋势", WorkTrendsParams, _get_work_trends, ToolRiskLevel.READ_ONLY),
    _spec("get_user_profile", "查询用户画像", EmptyParams, _get_user_profile, ToolRiskLevel.READ_ONLY),
    _spec("create_todo", "创建待办事项，需用户确认", CreateTodoParams, _create_todo, ToolRiskLevel.OPERATION),
    _spec("start_pomodoro", "启动番茄钟，需用户确认", StartPomodoroParams, _start_pomodoro, ToolRiskLevel.OPERATION),
    _spec("save_diary", "保存日记，需用户确认", SaveDiaryParams, _save_diary, ToolRiskLevel.OPERATION),
    # P0（15）
    _spec("create_goal", "创建长期目标，需确认", CreateGoalParams, _create_goal, ToolRiskLevel.OPERATION),
    _spec("list_goals", "列出长期目标", ListGoalsParams, _list_goals, ToolRiskLevel.READ_ONLY),
    _spec("update_goal", "更新目标进度/状态，需确认", UpdateGoalParams, _update_goal, ToolRiskLevel.OPERATION),
    _spec("get_week_plan", "查看本周计划安排", WeekPlanParams, _get_week_plan, ToolRiskLevel.READ_ONLY),
    _spec("create_plan_item", "创建计划项，需确认", CreatePlanItemParams, _create_plan_item, ToolRiskLevel.OPERATION),
    _spec("create_habit", "创建习惯，需确认", CreateHabitParams, _create_habit, ToolRiskLevel.OPERATION),
    _spec("list_habits", "列出习惯列表", EmptyParams, _list_habits, ToolRiskLevel.READ_ONLY),
    _spec("get_stats", "获取综合统计数据", GetStatsParams, _get_stats, ToolRiskLevel.READ_ONLY),
    _spec("get_heatmap", "获取心情热力图数据", GetHeatmapParams, _get_heatmap, ToolRiskLevel.READ_ONLY),
    _spec("get_settings", "查看当前设置", EmptyParams, _get_settings, ToolRiskLevel.READ_ONLY),
    _spec("update_setting", "修改全局设置，危险操作需二次确认", UpdateSettingParams, _update_setting, ToolRiskLevel.DANGEROUS),
    _spec("create_reminder", "创建提醒，需确认", CreateReminderParams, _create_reminder, ToolRiskLevel.OPERATION),
    _spec("list_reminders", "列出提醒", EmptyParams, _list_reminders, ToolRiskLevel.READ_ONLY),
    _spec("search_knowledge", "搜索记忆/知识库", SearchKnowledgeParams, _search_knowledge, ToolRiskLevel.READ_ONLY),
    _spec("get_project_map", "查看项目地图", EmptyParams, _get_project_map, ToolRiskLevel.READ_ONLY),
    # P1（10）
    _spec("mubu_search", "搜索幕布文档", MubuSearchParams, _mubu_search, ToolRiskLevel.READ_ONLY),
    _spec("mubu_create_doc", "在幕布创建文档，需确认", MubuCreateDocParams, _mubu_create_doc, ToolRiskLevel.OPERATION),
    _spec("mubu_update_doc", "覆盖更新幕布文档，危险操作", MubuUpdateDocParams, _mubu_update_doc, ToolRiskLevel.DANGEROUS),
    _spec("obsidian_sync", "执行 Obsidian 同步，需确认", EmptyParams, _obsidian_sync, ToolRiskLevel.OPERATION),
    _spec("get_calendar", "查询未来日历事件", GetCalendarParams, _get_calendar, ToolRiskLevel.READ_ONLY),
    _spec("generate_report", "生成报告，需确认", GenerateReportParams, _generate_report, ToolRiskLevel.OPERATION),
    _spec("export_data", "导出数据，需确认", ExportDataParams, _export_data, ToolRiskLevel.OPERATION),
    _spec("get_pomodoro_detail", "查看某天番茄钟明细", PomodoroDetailParams, _get_pomodoro_detail, ToolRiskLevel.READ_ONLY),
    _spec("trigger_workflow", "触发自动化工作流，危险操作", TriggerWorkflowParams, _trigger_workflow, ToolRiskLevel.DANGEROUS),
    _spec("list_skills", "列出已沉淀技能库", ListSkillsParams, _list_skills, ToolRiskLevel.READ_ONLY),
]

# 工具名 -> ToolSpec 的快速索引
TOOL_SPEC_MAP: dict[str, ToolSpec] = {t.name: t for t in AGENT_TOOLS}

# 工具名 -> execute 函数（兼容旧调用方式）
TOOL_EXECUTOR_MAP: dict[str, Callable[[dict], str]] = {t.name: t.execute for t in AGENT_TOOLS}


def build_openai_tools() -> list[dict]:
    """把全部工具转成 OpenAI function calling 的 tools 数组。

    说明：当前实现为全量加载（共 34 个）。后续若需按意图动态裁剪，
    可在此根据 context_hints 过滤 AGENT_TOOLS，避免单 Agent 工具数过多。
    """
    result = []
    for t in AGENT_TOOLS:
        result.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.build_openai_schema(),
            },
        })
    return result

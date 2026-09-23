"""P0-1: AI 从当日活动时间线中提取待办事项

POST /api/ai/extract-todos         — 调用 AI 识别待办，返回候选列表
POST /api/ai/extract-todos/confirm — 用户确认后将选中待办写入 todos 表
"""
import json
import logging
import re
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request

from routes.deps import check_token

logger = logging.getLogger(__name__)

bp = Blueprint('todo_extraction', __name__, url_prefix='/api/ai')

# priority 映射：AI 返回 high/medium/low → 数据库 1/2/3
_PRIORITY_MAP = {"high": 1, "medium": 2, "low": 3}


def _build_timeline_text(activities: list[dict]) -> str:
    """把活动记录拼成可读时间线文本，供 AI 识别待办"""
    lines = []
    # 按时间正序排列（旧→新），符合时间线阅读习惯
    for a in sorted(activities, key=lambda x: x.get("timestamp", "")):
        ts = a.get("timestamp", "")  # "YYYY-MM-DD HH:MM:SS"
        hhmm = ts[11:16] if len(ts) >= 16 else ts
        app_name = a.get("app_name") or "未知应用"
        detail = a.get("window_title") or a.get("summary") or ""
        category = a.get("category") or ""
        act_id = a.get("id", "")
        lines.append(f"(id={act_id}) [{hhmm}] {app_name} - {detail} ({category})")
    return "\n".join(lines)


def _extract_json_block(raw: str) -> dict | None:
    """从 AI 返回文本中提取 JSON 对象（支持 markdown 代码块包裹）"""
    raw = (raw or "").strip()
    # 直接尝试解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # 提取 ```json ... ``` 代码块
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # 提取最外层 { ... }
    start = raw.find("{")
    while start != -1:
        depth = 0
        i = start
        while i < len(raw):
            if raw[i] == "{":
                depth += 1
            elif raw[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = raw[start:i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break
            i += 1
        start = raw.find("{", start + 1)
    return None


def _due_hint_to_date(hint: str | None, today: date) -> str | None:
    """把 due_hint 中文提示映射为具体日期字符串"""
    if not hint:
        return None
    hint = hint.strip()
    if hint == "今天":
        return today.isoformat()
    if hint == "明天":
        return (today + timedelta(days=1)).isoformat()
    if hint == "本周":
        # weekday(): Monday=0 ... Sunday=6；本周日 = today + (6 - weekday)
        return (today + timedelta(days=6 - today.weekday())).isoformat()
    return None


@bp.route('/extract-todos', methods=['POST'])
def extract_todos():
    """从当日活动时间线中调用 AI 识别隐含待办事项"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(force=True, silent=True) or {}
    today_str = (data.get("date") or "").strip() or date.today().isoformat()
    try:
        datetime.strptime(today_str, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "date 格式应为 YYYY-MM-DD"}), 400

    # 获取当日活动时间线
    try:
        from db import get_activities
        activities = get_activities(today_str, today_str) or []
    except Exception as e:
        logger.error(f"extract-todos 查询活动失败: {e}", exc_info=True)
        return jsonify({"todos": [], "date": today_str, "activity_count": 0,
                        "message": "查询活动数据失败"}), 200

    if not activities:
        return jsonify({"todos": [], "date": today_str, "activity_count": 0,
                        "message": "今日暂无活动数据"}), 200

    timeline_text = _build_timeline_text(activities)

    # 调用 AI 识别待办
    try:
        import config
        if not config.AI_API_KEY:
            return jsonify({"todos": [], "date": today_str, "activity_count": len(activities),
                            "message": "AI 未配置，请在设置中配置 API Key"}), 200

        from ai_client import _get_client
        client = _get_client()
        system_prompt = (
            "你是一个待办提取助手。从用户的活动时间线中识别出隐含的待办事项。\n"
            "要求：\n"
            "1. 只提取明确暗示需要后续跟进/完成的事项（如：看了某文档要写总结、开了会议要发纪要、"
            "调试了某 bug 要继续修复等）。\n"
            "2. 不要把正在进行的活动本身直接当作待办，只提取'接下来需要做'的事。\n"
            "3. 每个待办给出 title（简洁动宾短语）、priority（high/medium/low）、"
            "due_hint（今天/明天/本周）、source_activity_id（来源活动的 id）、confidence（0~1）。\n"
            "4. 以 JSON 对象返回，格式为 {\"todos\": [...]}，最多 8 条。"
            "若无明确待办，返回 {\"todos\": []}。"
        )
        response = client.chat.completions.create(
            model=config.AI_TEXT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": timeline_text},
            ],
            max_tokens=800,
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        raw = (response.choices[0].message.content or "").strip()
        parsed = _extract_json_block(raw)
        if not parsed:
            logger.warning(f"extract-todos AI 返回解析失败: {raw[:200]}")
            return jsonify({"todos": [], "date": today_str, "activity_count": len(activities),
                            "message": "AI 返回格式异常，请重试"}), 200

        todos_raw = parsed.get("todos")
        if not isinstance(todos_raw, list):
            todos_raw = []

        # 清洗并校验每条待办
        todos = []
        for item in todos_raw:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            if not title:
                continue
            priority = item.get("priority", "medium")
            if priority not in _PRIORITY_MAP:
                priority = "medium"
            due_hint = item.get("due_hint", "")
            source_id = item.get("source_activity_id")
            try:
                source_id = int(source_id) if source_id is not None else None
            except (TypeError, ValueError):
                source_id = None
            try:
                confidence = float(item.get("confidence", 0.5))
            except (TypeError, ValueError):
                confidence = 0.5
            todos.append({
                "title": title,
                "priority": priority,
                "due_hint": due_hint,
                "source_activity_id": source_id,
                "confidence": round(confidence, 2),
            })

        return jsonify({"todos": todos, "date": today_str,
                        "activity_count": len(activities)}), 200

    except Exception as e:
        logger.error(f"extract-todos AI 调用失败: {e}", exc_info=True)
        return jsonify({"todos": [], "date": today_str, "activity_count": len(activities),
                        "message": f"AI 调用失败: {str(e)[:100]}"}), 200


@bp.route('/extract-todos/confirm', methods=['POST'])
def confirm_extracted_todos():
    """将用户确认选中的待办写入 todos 表"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(force=True, silent=True) or {}
    todos_in = data.get("todos")
    if not isinstance(todos_in, list) or not todos_in:
        return jsonify({"status": "ok", "inserted": 0, "ids": []}), 200

    today = date.today()
    today_str = today.isoformat()
    ids = []

    try:
        from db import insert_todo
        for item in todos_in:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            if not title:
                continue
            priority_str = item.get("priority", "medium")
            priority_num = _PRIORITY_MAP.get(priority_str, 2)
            due_date = _due_hint_to_date(item.get("due_hint"), today)

            todo_id = insert_todo(
                title=title,
                category="开发",
                mode="timer",
                target_min=25,
                due_date=due_date,
                priority=priority_num,
                task_level="day",
                assigned_date=today_str,
            )
            if todo_id:
                ids.append(todo_id)

        return jsonify({"status": "ok", "inserted": len(ids), "ids": ids}), 200

    except Exception as e:
        logger.error(f"extract-todos/confirm 写入失败: {e}", exc_info=True)
        return jsonify({"error": "写入待办失败，请稍后重试"}), 500

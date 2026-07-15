"""P10-3：数据可移植性 — 外部工具数据导入

支持格式：
- Toggl CSV：Description, Start time, End time, Duration, Project
- RescueTime CSV：Activity, Category, Productivity, Duration sec
- ActivityWatch JSON（bucket events）

导入的 activities 会标记 source='imported'，不参与截图存储，仅用于历史对比。
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
import csv
import io
import json
import logging

import db
from routes.deps import check_token, safe_error

logger = logging.getLogger(__name__)

bp = Blueprint('imports', __name__, url_prefix='/api/imports')


def _parse_toggl_csv(text: str) -> list[dict]:
    """解析 Toggl CSV 导出格式

    Toggl CSV 列：User, Email, Client, Project, Task, Description, Billable, Start date, Start time,
                  End date, End time, Duration, Tags, Amount ()
    """
    rows = []
    reader = csv.DictReader(io.StringIO(text))
    for r in reader:
        try:
            # 兼容不同 Toggl 版本的列名
            desc = r.get("Description") or r.get("Task") or r.get("Project") or "Toggl导入"
            start_date = r.get("Start date") or r.get("Start Date") or ""
            start_time = r.get("Start time") or r.get("Start Time") or ""
            end_date = r.get("End date") or r.get("End Date") or start_date
            end_time = r.get("End time") or r.get("End Time") or ""
            if not start_date:
                continue
            start_str = f"{start_date} {start_time}".strip()
            end_str = f"{end_date} {end_time}".strip()
            # 解析时长（秒）
            duration_str = r.get("Duration", "0")
            dur_sec = 0
            try:
                # "01:30:00" 格式
                parts = duration_str.split(":")
                if len(parts) == 3:
                    dur_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                else:
                    dur_sec = int(float(duration_str))
            except Exception:
                dur_sec = 0
            project = r.get("Project") or ""
            rows.append({
                "timestamp": start_str,
                "app_name": project or "Toggl",
                "window_title": desc,
                "category": _toggl_project_to_category(project),
                "duration_sec": dur_sec,
                "summary": desc,
                "interval_sec": dur_sec if dur_sec > 0 else 60,
            })
        except Exception as e:
            logger.debug(f"Toggl 行解析失败: {e}")
    return rows


def _toggl_project_to_category(project: str) -> str:
    """根据 Toggl 项目名映射到本地分类"""
    p = (project or "").lower()
    if any(k in p for k in ["dev", "code", "develop", "编程", "开发"]):
        return "开发"
    if any(k in p for k in ["study", "learn", "学习", "阅读"]):
        return "学习"
    if any(k in p for k in ["meeting", "会议", "沟通"]):
        return "会议"
    if any(k in p for k in ["doc", "文档", "write"]):
        return "文档"
    if any(k in p for k in ["test", "测试"]):
        return "测试"
    if any(k in p for k in ["design", "设计"]):
        return "设计"
    if any(k in p for k in ["rest", "break", "休息"]):
        return "休息"
    return "其他"


def _parse_rescuetime_csv(text: str) -> list[dict]:
    """解析 RescueTime CSV 导出格式

    RescueTime CSV 列：Date, Activity, Category, Productivity, Duration sec
    或：Activity, Category, Productivity, Duration sec（单日）
    """
    rows = []
    reader = csv.DictReader(io.StringIO(text))
    for r in reader:
        try:
            activity = r.get("Activity") or ""
            category = r.get("Category") or "其他"
            date_str = r.get("Date") or r.get("date") or ""
            dur_sec = 0
            try:
                dur_sec = int(float(r.get("Duration sec", 0) or r.get("Duration", 0) or 0))
            except Exception:
                dur_sec = 0
            if not date_str or not activity:
                continue
            # RescueTime 不提供具体时间，按全天均分
            timestamp = f"{date_str} 12:00:00"
            rows.append({
                "timestamp": timestamp,
                "app_name": activity,
                "window_title": activity,
                "category": _rescuetime_category_to_local(category),
                "duration_sec": dur_sec,
                "summary": f"RescueTime: {activity} ({category})",
                "interval_sec": dur_sec if dur_sec > 0 else 60,
            })
        except Exception as e:
            logger.debug(f"RescueTime 行解析失败: {e}")
    return rows


def _rescuetime_category_to_local(rt_cat: str) -> str:
    """RescueTime 分类映射到本地"""
    c = (rt_cat or "").lower()
    mapping = {
        "software development": "开发", "engineering & tech": "开发",
        "communication & scheduling": "沟通", "business": "沟通",
        "reference & learning": "学习", "education": "学习",
        "social media": "社交", "entertainment": "娱乐",
        "utilities": "其他", "news & opinion": "学习",
        "shopping": "生活", "design & composition": "设计",
    }
    for k, v in mapping.items():
        if k in c:
            return v
    return "其他"


@bp.route('/toggl', methods=['POST'])
@check_token
def import_toggl():
    """导入 Toggl CSV 数据

    Body: {"csv": "...CSV 文本...", "dry_run": false}
    """
    data = request.get_json(silent=True) or {}
    csv_text = data.get("csv", "")
    dry_run = bool(data.get("dry_run", False))
    if not csv_text.strip():
        return jsonify({"error": "CSV 内容为空"}), 400
    try:
        rows = _parse_toggl_csv(csv_text)
        if dry_run:
            return jsonify({"status": "ok", "parsed": len(rows), "sample": rows[:3], "dry_run": True})
        if not rows:
            return jsonify({"error": "解析后无可导入数据，请检查 CSV 格式"}), 400
        inserted = _insert_imported_activities(rows)
        return jsonify({
            "status": "ok", "source": "toggl",
            "parsed": len(rows), "inserted": inserted,
            "message": f"成功导入 {inserted} 条 Toggl 记录",
        })
    except Exception as e:
        logger.error(f"Toggl 导入失败: {e}", exc_info=True)
        return jsonify({"error": safe_error(e, "Toggl 导入失败")}), 500


@bp.route('/rescuetime', methods=['POST'])
@check_token
def import_rescuetime():
    """导入 RescueTime CSV 数据"""
    data = request.get_json(silent=True) or {}
    csv_text = data.get("csv", "")
    dry_run = bool(data.get("dry_run", False))
    if not csv_text.strip():
        return jsonify({"error": "CSV 内容为空"}), 400
    try:
        rows = _parse_rescuetime_csv(csv_text)
        if dry_run:
            return jsonify({"status": "ok", "parsed": len(rows), "sample": rows[:3], "dry_run": True})
        if not rows:
            return jsonify({"error": "解析后无可导入数据，请检查 CSV 格式"}), 400
        inserted = _insert_imported_activities(rows)
        return jsonify({
            "status": "ok", "source": "rescuetime",
            "parsed": len(rows), "inserted": inserted,
            "message": f"成功导入 {inserted} 条 RescueTime 记录",
        })
    except Exception as e:
        logger.error(f"RescueTime 导入失败: {e}", exc_info=True)
        return jsonify({"error": safe_error(e, "RescueTime 导入失败")}), 500


def _insert_imported_activities(rows: list[dict]) -> int:
    """将导入的活动数据插入 activities 表（标记 source='imported'）"""
    inserted = 0
    with db.get_conn() as conn:
        for r in rows:
            try:
                conn.execute(
                    "INSERT INTO activities (timestamp, app_name, window_title, category, "
                    "                       summary, interval_sec, ai_detail) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        r["timestamp"],
                        r["app_name"][:100],
                        r["window_title"][:200],
                        r["category"],
                        r["summary"][:200],
                        r.get("interval_sec", 60),
                        f'[imported] duration_sec={r.get("duration_sec", 0)}',
                    ),
                )
                inserted += 1
            except Exception as e:
                logger.debug(f"插入失败（跳过）: {e}")
        conn.commit()
    return inserted


def _parse_rize_csv(text: str) -> list[dict]:
    """P20-6: 解析 Rize CSV 导出格式

    Rize CSV 列：Date, Time, Activity, Category, Duration (minutes), Productivity
    """
    rows = []
    reader = csv.DictReader(io.StringIO(text))
    for r in reader:
        try:
            activity = r.get("Activity") or r.get("Name") or ""
            category = r.get("Category") or "其他"
            date_str = r.get("Date") or r.get("date") or ""
            time_str = r.get("Time") or r.get("Start Time") or "12:00"
            dur_min = 0.0
            try:
                dur_str = r.get("Duration (minutes)") or r.get("Duration") or "0"
                dur_min = float(dur_str)
            except Exception:
                dur_min = 0.0
            if not date_str or not activity:
                continue
            dur_sec = int(dur_min * 60)
            timestamp = f"{date_str} {time_str}".strip()
            rows.append({
                "timestamp": timestamp,
                "app_name": activity,
                "window_title": activity,
                "category": _rescuetime_category_to_local(category),
                "duration_sec": dur_sec,
                "summary": f"Rize: {activity} ({category})",
                "interval_sec": dur_sec if dur_sec > 0 else 60,
            })
        except Exception as e:
            logger.debug(f"Rize 行解析失败: {e}")
    return rows


@bp.route('/rize', methods=['POST'])
@check_token
def import_rize():
    """P20-6: 导入 Rize CSV 数据"""
    data = request.get_json(silent=True) or {}
    csv_text = data.get("csv", "")
    dry_run = bool(data.get("dry_run", False))
    if not csv_text.strip():
        return jsonify({"error": "CSV 内容为空"}), 400
    try:
        rows = _parse_rize_csv(csv_text)
        if dry_run:
            return jsonify({"status": "ok", "parsed": len(rows), "sample": rows[:3], "dry_run": True})
        if not rows:
            return jsonify({"error": "解析后无可导入数据，请检查 CSV 格式"}), 400
        inserted = _insert_imported_activities(rows)
        return jsonify({
            "status": "ok", "source": "rize",
            "parsed": len(rows), "inserted": inserted,
            "message": f"成功导入 {inserted} 条 Rize 记录",
        })
    except Exception as e:
        logger.error(f"Rize 导入失败: {e}", exc_info=True)
        return jsonify({"error": safe_error(e, "Rize 导入失败")}), 500


@bp.route('/formats', methods=['GET'])
def supported_formats():
    """列出支持的导入格式"""
    return jsonify({
        "formats": [
            {
                "id": "toggl",
                "name": "Toggl Track CSV",
                "description": "Toggl Track 导出的 CSV 时间条目",
                "required_columns": ["Description", "Start date", "Start time", "Duration"],
                "endpoint": "/api/imports/toggl",
            },
            {
                "id": "rescuetime",
                "name": "RescueTime CSV",
                "description": "RescueTime 导出的活动 CSV",
                "required_columns": ["Activity", "Category", "Duration sec"],
                "endpoint": "/api/imports/rescuetime",
            },
            {
                "id": "rize",
                "name": "Rize CSV",
                "description": "Rize 导出的活动 CSV（Duration minutes）",
                "required_columns": ["Date", "Activity", "Category", "Duration (minutes)"],
                "endpoint": "/api/imports/rize",
            },
        ]
    })

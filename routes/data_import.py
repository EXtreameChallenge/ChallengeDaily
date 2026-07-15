"""数据迁移导入 API
支持从竞品（番茄TODO/小黑日报/GoalDay/通用CSV）导入数据，降低用户切换成本
"""
import json
import logging
import io
import csv
from datetime import datetime
from flask import Blueprint, request, jsonify
import db

logger = logging.getLogger(__name__)

bp = Blueprint('data_import', __name__, url_prefix='/api/data-import')


def _parse_csv(text: str):
    """解析 CSV 文本，返回 dict 列表"""
    reader = csv.DictReader(io.StringIO(text))
    return [row for row in reader]


def _parse_json(text: str):
    """解析 JSON 文本"""
    return json.loads(text)


@bp.route('/preview', methods=['POST'])
def preview_import():
    """预览导入数据：解析并返回统计信息，不写入数据库"""
    data = request.get_json(force=True, silent=True) or {}
    source = data.get('source', '')  # fanqie_todo / xiaohei_report / goalday / generic_csv
    format_type = data.get('format', 'json')  # json / csv
    raw_text = data.get('data', '')

    if not raw_text:
        return jsonify({"error": "数据不能为空"}), 400

    try:
        if format_type == 'csv':
            rows = _parse_csv(raw_text)
        else:
            rows = _parse_json(raw_text)
            if not isinstance(rows, list):
                rows = [rows]
    except Exception as e:
        return jsonify({"error": f"解析失败: {str(e)}"}), 400

    # 统计预览
    preview = {
        "source": source,
        "format": format_type,
        "total_rows": len(rows),
        "sample": rows[:3],
        "detected_type": _detect_data_type(rows, source),
    }
    return jsonify(preview)


@bp.route('/execute', methods=['POST'])
def execute_import():
    """执行导入：将数据写入对应表"""
    data = request.get_json(force=True, silent=True) or {}
    source = data.get('source', '')
    format_type = data.get('format', 'json')
    raw_text = data.get('data', '')
    target_table = data.get('target_table', '')  # todos / habits / countdowns / diaries / goals
    dry_run = data.get('dry_run', False)

    if not raw_text:
        return jsonify({"error": "数据不能为空"}), 400

    try:
        if format_type == 'csv':
            rows = _parse_csv(raw_text)
        else:
            rows = _parse_json(raw_text)
            if not isinstance(rows, list):
                rows = [rows]
    except Exception as e:
        return jsonify({"error": f"解析失败: {str(e)}"}), 400

    if not target_table:
        target_table = _detect_data_type(rows, source)

    results = {"total": len(rows), "imported": 0, "skipped": 0, "errors": []}

    if dry_run:
        return jsonify({**results, "dry_run": True, "target_table": target_table})

    try:
        if target_table == 'todos':
            results.update(_import_todos(rows, source))
        elif target_table == 'habits':
            results.update(_import_habits(rows, source))
        elif target_table == 'countdowns':
            results.update(_import_countdowns(rows, source))
        elif target_table == 'diaries':
            results.update(_import_diaries(rows, source))
        elif target_table == 'goals':
            results.update(_import_goals(rows, source))
        else:
            return jsonify({"error": f"未知目标表: {target_table}"}), 400
    except Exception as e:
        logger.exception("导入失败")
        return jsonify({"error": f"导入失败: {str(e)}"}), 500

    return jsonify(results)


def _detect_data_type(rows, source):
    """自动检测数据类型"""
    if not rows:
        return 'unknown'
    first = rows[0]
    keys = set(k.lower() for k in first.keys()) if isinstance(first, dict) else set()

    # 番茄TODO 任务导出通常含 title/task/name + 估计番茄数
    if source == 'fanqie_todo' or {'title', 'task', 'name'} & keys:
        if {'target_min', 'duration', 'pomodoro', '番茄'} & keys:
            return 'todos'
    # 小黑日报导出含 content/report
    if source == 'xiaohei_report' or {'content', 'report', '日报'} & keys:
        return 'diaries'
    # GoalDay 目标导出
    if source == 'goalday' or {'goal', '目标', 'target_date'} & keys:
        return 'goals'
    # 习惯
    if {'habit', '习惯', 'target_count'} & keys:
        return 'habits'
    # 倒数日
    if {'countdown', '倒数', 'target_date'} & keys:
        return 'countdowns'
    # 默认按 source
    return {'fanqie_todo': 'todos', 'xiaohei_report': 'diaries', 'goalday': 'goals'}.get(source, 'todos')


def _import_todos(rows, source):
    """导入待办"""
    imported = 0
    skipped = 0
    errors = []
    for i, row in enumerate(rows):
        try:
            title = (row.get('title') or row.get('task') or row.get('name') or row.get('标题') or '').strip()
            if not title:
                skipped += 1
                continue
            # 番茄TODO 字段映射
            target_min = _parse_int(row.get('target_min') or row.get('duration') or row.get('时长') or row.get('番茄时长') or 25)
            estimated = _parse_int(row.get('estimated_pomodoros') or row.get('番茄数') or row.get('pomodoros') or 1)
            category = row.get('category') or row.get('分类') or '导入'
            due_date = row.get('due_date') or row.get('截止日期') or None
            priority = _parse_int(row.get('priority') or row.get('优先级') or 2)

            db.insert_todo(
                title=title,
                category=category,
                target_min=target_min,
                due_date=due_date,
                priority=priority,
                estimated_pomodoros=estimated,
            )
            imported += 1
        except Exception as e:
            errors.append(f"第{i+1}行: {str(e)}")
            skipped += 1
    return {"imported": imported, "skipped": skipped, "errors": errors}


def _import_habits(rows, source):
    """导入习惯"""
    imported = 0
    skipped = 0
    errors = []
    for i, row in enumerate(rows):
        try:
            name = (row.get('name') or row.get('habit') or row.get('习惯名') or '').strip()
            if not name:
                skipped += 1
                continue
            target_count = _parse_int(row.get('target_count') or 1)
            color = row.get('color') or '#7B68EE'
            db.insert_habit(name=name, target_count=target_count, color=color)
            imported += 1
        except Exception as e:
            errors.append(f"第{i+1}行: {str(e)}")
            skipped += 1
    return {"imported": imported, "skipped": skipped, "errors": errors}


def _import_countdowns(rows, source):
    """导入倒数日"""
    imported = 0
    skipped = 0
    errors = []
    for i, row in enumerate(rows):
        try:
            title = (row.get('title') or row.get('name') or row.get('事件') or '').strip()
            target_date = row.get('target_date') or row.get('date') or row.get('日期') or ''
            if not title or not target_date:
                skipped += 1
                continue
            color = row.get('color') or '#7B68EE'
            db.insert_countdown(title=title, target_date=target_date, color=color)
            imported += 1
        except Exception as e:
            errors.append(f"第{i+1}行: {str(e)}")
            skipped += 1
    return {"imported": imported, "skipped": skipped, "errors": errors}


def _import_diaries(rows, source):
    """导入日记"""
    imported = 0
    skipped = 0
    errors = []
    for i, row in enumerate(rows):
        try:
            diary_date = row.get('date') or row.get('diary_date') or row.get('日期') or datetime.now().strftime('%Y-%m-%d')
            content = row.get('content') or row.get('report') or row.get('内容') or row.get('日报') or ''
            mood = row.get('mood') or row.get('心情') or ''
            weather = row.get('weather') or row.get('天气') or ''
            if not content:
                skipped += 1
                continue
            db.upsert_diary(diary_date=diary_date, mood=mood, weather=weather, content=content)
            imported += 1
        except Exception as e:
            errors.append(f"第{i+1}行: {str(e)}")
            skipped += 1
    return {"imported": imported, "skipped": skipped, "errors": errors}


def _import_goals(rows, source):
    """导入目标"""
    imported = 0
    skipped = 0
    errors = []
    for i, row in enumerate(rows):
        try:
            title = (row.get('title') or row.get('goal') or row.get('目标') or '').strip()
            if not title:
                skipped += 1
                continue
            description = row.get('description') or row.get('描述') or ''
            category = row.get('category') or row.get('分类') or 'personal'
            timeframe = row.get('timeframe') or row.get('周期') or 'yearly'
            target_date = row.get('target_date') or row.get('截止日期') or None
            db.create_goal(title=title, description=description, category=category,
                          timeframe=timeframe, target_date=target_date)
            imported += 1
        except Exception as e:
            errors.append(f"第{i+1}行: {str(e)}")
            skipped += 1
    return {"imported": imported, "skipped": skipped, "errors": errors}


def _parse_int(val, default=0):
    """安全整数转换"""
    try:
        return int(float(str(val).strip())) if val else default
    except (ValueError, TypeError):
        return default

"""规则引擎 API"""
from flask import Blueprint, request, jsonify
import db
import json
import logging
from rules_engine import evaluate_all_rules, init_rules_table, TRIGGER_TYPES, ACTION_TYPES

logger = logging.getLogger(__name__)

bp = Blueprint('rules_engine', __name__, url_prefix='/api/rules')


@bp.route('/list', methods=['GET'])
def list_rules():
    """获取所有规则"""
    init_rules_table()
    with db.get_conn() as conn:
        rows = conn.execute("SELECT * FROM rules ORDER BY id").fetchall()
    return jsonify({"rules": [dict(r) for r in rows], "triggers": TRIGGER_TYPES, "actions": ACTION_TYPES})


@bp.route('/create', methods=['POST'])
def create_rule():
    """创建规则（WorkflowEditor 的创建入口）。"""
    init_rules_table()
    data = request.get_json(force=True, silent=True) or {}
    name = str(data.get('name') or '').strip()
    trigger_type = str(data.get('trigger_type') or '').strip()
    action_type = str(data.get('action_type') or 'notify').strip()
    if not name or not trigger_type:
        return jsonify({"error": "name/trigger_type 必填"}), 400
    if trigger_type not in TRIGGER_TYPES:
        return jsonify({"error": f"未知 trigger_type: {trigger_type}"}), 400
    if action_type not in ACTION_TYPES:
        return jsonify({"error": f"未知 action_type: {action_type}"}), 400
    with db.get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO rules (name, description, trigger_type, trigger_params, action_type, action_params, enabled) "
            "VALUES (?,?,?,?,?,?,1)",
            (
                name,
                str(data.get('description') or ''),
                trigger_type,
                json.dumps(data.get('trigger_params', {}), ensure_ascii=False),
                action_type,
                json.dumps(data.get('action_params', {}), ensure_ascii=False),
            ),
        )
        conn.commit()
    return jsonify({"status": "ok", "id": cursor.lastrowid})


@bp.route('/<int:rule_id>', methods=['DELETE'])
def delete_rule(rule_id):
    """删除一条规则。"""
    with db.get_conn() as conn:
        conn.execute("DELETE FROM rules WHERE id=?", (rule_id,))
        conn.commit()
    return jsonify({"status": "ok"})


@bp.route('/toggle', methods=['POST'])
def toggle_rule():
    """启用/禁用规则"""
    data = request.get_json(force=True, silent=True) or {}
    rule_id = data.get('id')
    enabled = 1 if data.get('enabled') else 0
    with db.get_conn() as conn:
        conn.execute("UPDATE rules SET enabled=? WHERE id=?", (enabled, rule_id))
        conn.commit()
    return jsonify({"status": "ok"})


@bp.route('/update', methods=['POST'])
def update_rule():
    """更新规则参数"""
    data = request.get_json(force=True, silent=True) or {}
    rule_id = data.get('id')
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE rules SET name=?, trigger_params=?, action_type=?, action_params=? WHERE id=?",
            (data.get('name'), json.dumps(data.get('trigger_params', {}), ensure_ascii=False),
             data.get('action_type', 'notify'), json.dumps(data.get('action_params', {}), ensure_ascii=False), rule_id)
        )
        conn.commit()
    return jsonify({"status": "ok"})


@bp.route('/evaluate', methods=['GET'])
def evaluate():
    """手动触发规则评估，返回触发的动作"""
    triggered = evaluate_all_rules()
    return jsonify({"triggered": triggered, "count": len(triggered)})

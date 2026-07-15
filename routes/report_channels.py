"""日报多渠道自动提交 API"""
from flask import Blueprint, request, jsonify
import db
import json
import logging
from datetime import datetime
from report_channels import get_channel, submit_to_all_channels, CHANNEL_CLASSES

logger = logging.getLogger(__name__)

bp = Blueprint('report_channels', __name__, url_prefix='/api/report-channels')


@bp.route('/config', methods=['GET'])
def get_config():
    """获取所有提交通道配置"""
    with db.get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key='report_channels'").fetchone()
    config = json.loads(row['value']) if row else []
    return jsonify({"channels": config})


@bp.route('/config', methods=['POST'])
def save_config():
    """保存提交通道配置"""
    data = request.get_json(force=True, silent=True) or {}
    channels = data.get('channels', [])
    with db.get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('report_channels', ?, CURRENT_TIMESTAMP)",
            (json.dumps(channels, ensure_ascii=False),)
        )
        conn.commit()
    return jsonify({"status": "ok"})


@bp.route('/test', methods=['POST'])
def test_channel():
    """测试单个通道连接"""
    data = request.get_json(force=True, silent=True) or {}
    ch_type = data.get('type')
    ch_config = data.get('config', {})
    if not ch_type or ch_type not in CHANNEL_CLASSES:
        return jsonify({"success": False, "message": f"未知通道类型: {ch_type}"})
    try:
        channel = get_channel(ch_type, ch_config)
        result = channel.test_connection()
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@bp.route('/submit', methods=['POST'])
def submit_report():
    """提交日报到所有已配置通道"""
    data = request.get_json(force=True, silent=True) or {}
    report_text = data.get('report_text', '')
    report_date = data.get('report_date', datetime.now().strftime('%Y-%m-%d'))

    if not report_text:
        return jsonify({"error": "日报内容不能为空"}), 400

    with db.get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key='report_channels'").fetchone()
    channels_config = json.loads(row['value']) if row else []

    if not channels_config:
        return jsonify({"error": "未配置任何提交通道"}), 400

    results = submit_to_all_channels(report_text, channels_config, report_date)
    success_count = sum(1 for r in results if r.get('success'))

    return jsonify({
        "status": "ok",
        "total": len(results),
        "success": success_count,
        "results": results,
    })

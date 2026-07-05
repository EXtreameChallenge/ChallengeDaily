import re
import json as _json
import logging

from flask import Blueprint, jsonify, request
from datetime import date, datetime as _datetime

from config import BASE_DIR
from report import generate_daily_report
from file_utils import atomic_write_text, backup_file
from routes.deps import safe_error, state_lock
from routes.webhooks import push_all_webhooks
from routes.notifications import add_notification

logger = logging.getLogger(__name__)

bp = Blueprint('auto_report', __name__)

_AUTO_REPORT_PATH = BASE_DIR / "data" / "auto_report.json"

_auto_report_generated_today = False
_auto_report_last_date = None


def _load_auto_report_config() -> dict:
    default = {
        "enabled": False,
        "auto_time": "18:00",
        "auto_push": True,
    }
    if _AUTO_REPORT_PATH.exists():
        try:
            saved = _json.loads(_AUTO_REPORT_PATH.read_text(encoding="utf-8"))
            default.update(saved)
        except Exception:
            pass
    return default


def _save_auto_report_config(cfg: dict):
    _AUTO_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    content = _json.dumps(cfg, ensure_ascii=False, indent=2)
    if _AUTO_REPORT_PATH.exists():
        backup_file(_AUTO_REPORT_PATH)
    atomic_write_text(_AUTO_REPORT_PATH, content)


@bp.route("/api/auto-report/config", methods=["GET"])
def get_auto_report_config():
    return jsonify(_load_auto_report_config())


@bp.route("/api/auto-report/config", methods=["POST"])
def update_auto_report_config():
    data = request.get_json(force=True)
    cfg = _load_auto_report_config()
    for key in ["enabled", "auto_time", "auto_push"]:
        if key in data:
            cfg[key] = data[key]
    auto_time_val = cfg.get("auto_time", "18:00")
    if not re.match(r"^\d{2}:\d{2}$", auto_time_val):
        return jsonify({"error": "时间格式应为 HH:MM"}), 400
    try:
        h, m = map(int, auto_time_val.split(":"))
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError()
    except (ValueError, TypeError):
        return jsonify({"error": "时间值无效，小时范围 0-23，分钟范围 0-59"}), 400
    _save_auto_report_config(cfg)
    return jsonify({"status": "ok", "config": cfg})


@bp.route("/api/agent/auto-report", methods=["POST"])
def trigger_auto_report():
    try:
        content = generate_daily_report()
        pushed = push_all_webhooks(content, date.today().isoformat())
        add_notification(
            "日报推送完成",
            f"日报已生成并推送至 {pushed} 个 Webhook",
            "success",
        )
        return jsonify({"status": "ok", "report_generated": True, "webhooks_pushed": pushed})
    except Exception as e:
        return jsonify({"status": "error", "message": safe_error(e, "日报推送失败")}), 500


def check_auto_report():
    global _auto_report_generated_today, _auto_report_last_date

    today = date.today().isoformat()

    with state_lock:
        if today != _auto_report_last_date:
            _auto_report_generated_today = False
            _auto_report_last_date = today

        if _auto_report_generated_today:
            return None

    cfg = _load_auto_report_config()
    if not cfg.get("enabled", False):
        return None

    now = _datetime.now()
    try:
        target_h, target_m = map(int, cfg["auto_time"].split(":"))
    except Exception:
        return None

    if not (now.hour > target_h or (now.hour == target_h and now.minute >= target_m)):
        return None

    from db import get_conn
    with get_conn() as conn:
        cnt = conn.execute(
            "SELECT COUNT(*) as cnt FROM activities WHERE date(timestamp) = ?",
            (today,),
        ).fetchone()["cnt"]
    if cnt == 0:
        return None

    with state_lock:
        if _auto_report_generated_today:
            return None
        _auto_report_generated_today = True

    logger.info(f"自动日报触发 ({cfg['auto_time']})，开始生成...")

    try:
        content = generate_daily_report()
        pushed = 0
        if cfg.get("auto_push", True):
            pushed = push_all_webhooks(content, today)
        logger.info(f"自动日报生成成功，Webhook 推送 {pushed} 个")
        add_notification(
            "日报已自动生成",
            f"今日日报已自动生成完成，已推送至 {pushed} 个 Webhook",
            "success",
        )
        return {"generated": True, "pushed": pushed}
    except Exception as e:
        logger.error(f"自动日报生成失败: {e}")
        return None

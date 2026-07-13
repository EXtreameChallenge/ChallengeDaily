import logging

from flask import Blueprint, jsonify, request

from config import load_settings, save_settings
import routes.deps as deps
import db

logger = logging.getLogger(__name__)

bp = Blueprint('settings_routes', __name__)


@bp.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify(load_settings())


@bp.route("/api/settings", methods=["POST"])
def update_settings():
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "Empty body"}), 400
    current = load_settings()

    ai_api_key_raw = data.pop("ai_api_key", None)

    for key in ["exclude_apps", "screenshot_interval_sec", "work_start_hour",
                "work_end_hour", "custom_report_instructions",
                "ai_base_url", "ai_vision_model", "ai_text_model", "ai_enabled"]:
        if key in data:
            current[key] = data[key]

    # 字段长度限制：防止超大值拖垮系统或 AI 调用
    _MAX_FIELD_LEN = {
        "ai_base_url": 200,
        "ai_vision_model": 100,
        "ai_text_model": 100,
        "custom_report_instructions": 2000,
        "exclude_apps": 5000,
    }
    for field, max_len in _MAX_FIELD_LEN.items():
        if field in current and isinstance(current[field], str) and len(current[field]) > max_len:
            return jsonify({"error": f"{field} 长度超过限制（最大 {max_len} 字符）"}), 400

    if ai_api_key_raw is not None and ai_api_key_raw.strip():
        try:
            from crypto import save_secret
            save_secret("ai_api_key", ai_api_key_raw.strip())
            import config
            config.AI_API_KEY = ai_api_key_raw.strip()
            current["ai_api_key_set"] = True
        except Exception as e:
            logger.error(f"Failed to save API Key to vault: {e}")
            return jsonify({"error": "API Key 保存失败，请检查系统权限后重试"}), 500
    elif ai_api_key_raw is not None and not ai_api_key_raw.strip():
        try:
            from crypto import delete_secret
            delete_secret("ai_api_key")
        except Exception:
            pass
        import config
        config.AI_API_KEY = ""
        current["ai_api_key_set"] = False

    # 校验截图间隔 — 在保存之前，避免无效值被持久化
    if "screenshot_interval_sec" in data:
        import config
        val = int(data["screenshot_interval_sec"])
        if val < 15:
            return jsonify({"error": "截图间隔不能小于15秒"}), 400
        if val > 300:
            return jsonify({"error": "截图间隔不能大于300秒"}), 400

    # 校验 ai_base_url — 在保存之前，避免无效 URL 被持久化
    if "ai_base_url" in data:
        url_val = str(data["ai_base_url"]).strip()
        if url_val and not (url_val.startswith("http://") or url_val.startswith("https://")):
            return jsonify({"error": "AI Base URL 必须以 http:// 或 https:// 开头"}), 400
        # SSRF 校验：拒绝回环/内网/链路本地等地址
        if url_val:
            from routes.webhooks import _validate_webhook_url
            ssrf_error = _validate_webhook_url(url_val)
            if ssrf_error:
                return jsonify({"error": f"AI Base URL 校验失败：{ssrf_error}"}), 400

    save_settings(current)

    if "screenshot_interval_sec" in data:
        import config
        config.SCREENSHOT_INTERVAL_SEC = val

    if "ai_base_url" in data:
        import config
        config.AI_BASE_URL = str(data["ai_base_url"]).strip()
    if "ai_vision_model" in data:
        import config
        config.AI_VISION_MODEL = str(data["ai_vision_model"])
    if "ai_text_model" in data:
        import config
        config.AI_TEXT_MODEL = str(data["ai_text_model"])
    # ai_api_key_raw 为空字符串时也是合法操作（清除 key），需要用 is not None 判断
    if any(k in data for k in ["ai_base_url", "ai_vision_model", "ai_text_model"]) or ai_api_key_raw is not None:
        try:
            from ai_client import _reset_client
            _reset_client()
        except Exception:
            pass

    return jsonify({"status": "ok", "settings": current})


@bp.route("/api/collector/pause", methods=["POST"])
def pause_collector():
    with deps.state_lock:
        deps.collector_paused = True
    return jsonify({"status": "ok", "paused": True})


@bp.route("/api/collector/resume", methods=["POST"])
def resume_collector():
    with deps.state_lock:
        deps.collector_paused = False
    return jsonify({"status": "ok", "paused": False})


@bp.route('/api/settings/privacy-apps', methods=['GET', 'PUT'])
def privacy_apps():
    """查询/设置隐私应用名单"""
    if request.method == 'GET':
        with db.get_conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key='privacy_apps'").fetchone()
            apps = __import__('json').loads(row[0]) if row else []
        return jsonify({"apps": apps})
    data = request.get_json(silent=True) or {}
    apps = data.get('apps', [])
    if not isinstance(apps, list) or len(apps) > 100:
        return jsonify({"error": "apps 必须是列表（最多100项）"}), 400
    with db.get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('privacy_apps', ?)",
                    (__import__('json').dumps(apps, ensure_ascii=False),))
    logger.info(f"[AUDIT] Privacy apps updated by {request.remote_addr}: {len(apps)} apps")
    return jsonify({"status": "updated", "apps": apps})

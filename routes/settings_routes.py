import logging

from flask import Blueprint, jsonify, request

from config import load_settings, save_settings
import routes.deps as deps

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

    save_settings(current)

    if "screenshot_interval_sec" in data:
        import config
        val = int(data["screenshot_interval_sec"])
        if val < 15:
            return jsonify({"error": "截图间隔不能小于15秒"}), 400
        if val > 300:
            return jsonify({"error": "截图间隔不能大于300秒"}), 400
        config.SCREENSHOT_INTERVAL_SEC = val

    if "ai_base_url" in data:
        import config
        config.AI_BASE_URL = str(data["ai_base_url"])
    if "ai_vision_model" in data:
        import config
        config.AI_VISION_MODEL = str(data["ai_vision_model"])
    if "ai_text_model" in data:
        import config
        config.AI_TEXT_MODEL = str(data["ai_text_model"])
    if any(k in data for k in ["ai_base_url", "ai_vision_model", "ai_text_model"]) or ai_api_key_raw:
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

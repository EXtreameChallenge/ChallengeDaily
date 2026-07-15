"""P18-4: 本地小模型降级 API 路由 — Ollama 状态查询与配置"""
import logging
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import local_model

logger = logging.getLogger(__name__)
bp = Blueprint('local_model', __name__)


@bp.route("/api/local-model/status")
def status():
    """查询本地模型状态（Ollama 可用性 + 已安装模型）"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        health = local_model.check_ollama_available()
        config = local_model.get_local_model_config()
        return jsonify({
            "config": config,
            "health": health,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/local-model/config", methods=["GET"])
def get_config():
    """获取本地模型配置"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        return jsonify(local_model.get_local_model_config())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/local-model/config", methods=["PUT"])
def update_config():
    """更新本地模型配置"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.get_json(silent=True) or {}
        # 白名单过滤
        allowed = {}
        for k in ("enabled", "base_url", "vision_model", "text_model",
                  "fallback_to_rules", "auto_fallback", "timeout_sec"):
            if k in data:
                allowed[k] = data[k]
        updated = local_model.update_local_model_config(**allowed)
        return jsonify(updated)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/local-model/models")
def list_models():
    """列出 Ollama 已安装的模型"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        return jsonify({"models": local_model.list_ollama_models()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/local-model/test", methods=["POST"])
def test_local_model():
    """测试本地模型（用一句话测试文本模型）"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.get_json(silent=True) or {}
        test_type = data.get("type", "text")  # text | vision
        if test_type == "vision":
            # 视觉测试：用一张 1x1 白色 PNG
            import base64
            # 1x1 白色 PNG 的 base64
            white_png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mP8/5+hgQABAgMBAI//AgAAAABJRU5ErkJggg=="
            result = local_model.local_vision_classify(
                white_png_b64,
                "请用JSON格式描述这张图片：{\"category\": \"...\", \"summary\": \"...\"}"
            )
            return jsonify({
                "ok": result.get("source") != "local_error",
                "type": "vision",
                "result": result,
            })
        else:
            result = local_model.local_text_complete(
                "请用一句话介绍你自己",
                system_prompt="你是一个简洁的助手"
            )
            return jsonify({
                "ok": bool(result.get("text")),
                "type": "text",
                "result": result,
            })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

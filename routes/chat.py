"""AI对话 API"""
from flask import Blueprint, request, jsonify
import db
from routes.deps import shutdown_event
import os
import logging

bp = Blueprint('chat', __name__, url_prefix='/api/ai')
logger = logging.getLogger(__name__)


@bp.route('/chat', methods=['POST'])
def ai_chat():
    """AI对话（基于工作数据）"""
    data = request.get_json(force=True, silent=True) or {}
    user_message = data.get('message', '').strip()
    if not user_message:
        return jsonify({"error": "消息不能为空"}), 400

    # 保存用户消息
    db.insert_chat('user', user_message)

    # 构建上下文
    try:
        from context_manager import build_weekly_context
        context = build_weekly_context(7)
    except Exception:
        context = ""

    try:
        from profile_manager import get_distilled_profile
        profile = get_distilled_profile()
        profile_text = f"\n用户画像：{profile.get('role_desc', '')}，工作风格：{profile.get('work_style', '')}" if profile else ""
    except Exception:
        profile_text = ""

    # 获取历史对话
    history = db.get_chat_history(limit=10)
    history_text = "\n".join([f"{'用户' if h['role']=='user' else '助手'}: {h['content']}" for h in history[:-1]])

    # 调用AI
    try:
        from config import AI_API_KEY, AI_BASE_URL, AI_TEXT_MODEL
        if not AI_API_KEY:
            reply = "AI功能未配置，请在设置中配置API Key后使用。"
        else:
            import requests
            messages = [
                {"role": "system", "content": f"你是用户的工作助手，基于以下工作数据回答问题。回答要简洁、具体、有数据支撑。\n\n{context}\n{profile_text}\n\n近期对话：\n{history_text}"},
                {"role": "user", "content": user_message}
            ]
            resp = requests.post(
                f"{AI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"},
                json={"model": AI_TEXT_MODEL, "messages": messages, "max_tokens": 500, "temperature": 0.7},
                timeout=30
            )
            resp.raise_for_status()
            reply = resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"AI chat failed: {e}")
        reply = f"AI暂时无法回复，请稍后再试。"

    # 保存AI回复
    db.insert_chat('assistant', reply)
    return jsonify({"reply": reply, "role": "assistant"})


@bp.route('/chat/history', methods=['GET'])
def chat_history():
    history = db.get_chat_history(limit=50)
    return jsonify({"history": history})


@bp.route('/chat/clear', methods=['DELETE'])
def clear_chat():
    db.clear_chat_history()
    return jsonify({"status": "ok"})

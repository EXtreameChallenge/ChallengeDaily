"""
ChallengeDaily — 综合工具路由（通知中心/录音器/Markdown阅读器/PDF工具）
借鉴小黑日报助手的 toolboxLocal/notifications/recorder/markdownReader
"""
from flask import Blueprint, jsonify, request, send_file
import os
import logging

logger = logging.getLogger(__name__)

tools_bp = Blueprint('tools', __name__, url_prefix='/api/tools')


# ── 通知中心 ──

@tools_bp.route('/notifications/list', methods=['GET'])
def list_notifications():
    from notification_center import list_notifications
    return jsonify(list_notifications())


@tools_bp.route('/notifications/unread-count', methods=['GET'])
def unread_count():
    from notification_center import unread_count
    return jsonify({"count": unread_count()})


@tools_bp.route('/notifications/mark-read', methods=['POST'])
def mark_read():
    from notification_center import mark_read
    data = request.get_json(silent=True) or {}
    mark_read(data.get('id', ''))
    return jsonify({"ok": True})


@tools_bp.route('/notifications/mark-all-read', methods=['POST'])
def mark_all_read():
    from notification_center import mark_all_read
    mark_all_read()
    return jsonify({"ok": True})


@tools_bp.route('/notifications/add', methods=['POST'])
def add_notification():
    from notification_center import add_notification
    data = request.get_json(silent=True) or {}
    notif = add_notification(
        title=data.get('title', ''),
        body=data.get('body', ''),
        type=data.get('type', 'info'),
    )
    return jsonify(notif)


# ── 录音器 ──

@tools_bp.route('/recorder/start', methods=['POST'])
def start_recording():
    from audio_recorder import start_recording
    return jsonify(start_recording())


@tools_bp.route('/recorder/stop', methods=['POST'])
def stop_recording():
    from audio_recorder import stop_recording
    return jsonify(stop_recording())


@tools_bp.route('/recorder/status', methods=['GET'])
def recorder_status():
    from audio_recorder import get_status
    return jsonify(get_status())


@tools_bp.route('/recorder/transcribe', methods=['POST'])
def transcribe():
    from audio_recorder import transcribe_audio
    data = request.get_json(silent=True) or {}
    return jsonify(transcribe_audio(data.get('filepath', ''), data.get('api_key', '')))


# ── Markdown 阅读器 ──

@tools_bp.route('/markdown/read', methods=['POST'])
def read_markdown():
    """读取Markdown文件"""
    data = request.get_json(silent=True) or {}
    filepath = data.get('path', '')
    if not filepath or not os.path.exists(filepath):
        return jsonify({"ok": False, "error": "文件不存在"}), 404
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({"ok": True, "content": content, "path": filepath})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@tools_bp.route('/markdown/save', methods=['POST'])
def save_markdown():
    """保存Markdown文件"""
    data = request.get_json(silent=True) or {}
    filepath = data.get('path', '')
    content = data.get('content', '')
    if not filepath:
        return jsonify({"ok": False, "error": "路径为空"}), 400
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({"ok": True, "path": filepath})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── PDF 工具箱 ──

@tools_bp.route('/pdf/compress', methods=['POST'])
def compress_pdf():
    """PDF压缩（占位，需要PyPDF2）"""
    data = request.get_json(silent=True) or {}
    try:
        from PyPDF2 import PdfReader, PdfWriter
        input_path = data.get('inputPath', '')
        output_path = data.get('outputPath', '')
        if not input_path or not os.path.exists(input_path):
            return jsonify({"ok": False, "error": "输入文件不存在"}), 404

        reader = PdfReader(input_path)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        with open(output_path, 'wb') as f:
            writer.write(f)
        return jsonify({"ok": True, "outputPath": output_path})
    except ImportError:
        return jsonify({"ok": False, "error": "PyPDF2未安装，请pip install PyPDF2"}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

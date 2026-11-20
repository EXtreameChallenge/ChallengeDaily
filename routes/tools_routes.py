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
    result = transcribe_audio(data.get('filepath', ''), data.get('api_key', ''))
    return jsonify(result)


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
    """保存Markdown文件（Wave2-B14：仅允许写入应用数据目录，防任意路径覆盖）"""
    data = request.get_json(silent=True) or {}
    filepath = data.get('path', '')
    content = data.get('content', '')
    if not filepath:
        return jsonify({"ok": False, "error": "路径为空"}), 400

    import config
    try:
        target = os.path.realpath(os.path.abspath(filepath))
        data_root = os.path.realpath(str(config.DATA_DIR))
        if os.path.commonpath([target, data_root]) != data_root:
            return jsonify({"ok": False,
                            "error": "只允许保存到应用数据目录",
                            "hint": f"允许目录: {data_root}"}), 403
        if os.path.splitext(target)[1].lower() not in ('.md', '.markdown', '.txt'):
            return jsonify({"ok": False, "error": "只允许保存 .md/.markdown/.txt 文件"}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": f"路径校验失败: {e}"}), 400

    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({"ok": True, "path": target})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── PDF 工具箱 ──

def _pdf_output_path(raw: str) -> str:
    """输出路径限制在应用数据目录（同 Markdown 保存口径）。"""
    import config
    target = os.path.realpath(os.path.abspath(raw))
    data_root = os.path.realpath(str(config.DATA_DIR))
    if os.path.commonpath([target, data_root]) != data_root:
        raise ValueError("输出路径必须位于应用数据目录")
    if not target.lower().endswith('.pdf'):
        raise ValueError("输出文件必须是 .pdf")
    return target


@tools_bp.route('/pdf/compress', methods=['POST'])
def compress_pdf():
    """PDF 压缩 — 未集成真实压缩引擎，明确 unsupported，不做原样复制冒充压缩。"""
    return jsonify({
        "ok": False,
        "unsupported": True,
        "error": "真实 PDF 压缩需要 Ghostscript/qpdf，本应用暂未集成",
        "hint": "可用 /api/tools/pdf/merge 合并、/api/tools/pdf/split 拆分",
    }), 501


@tools_bp.route('/pdf/merge', methods=['POST'])
def merge_pdf():
    """合并多个 PDF（PyPDF2 真实合并）"""
    data = request.get_json(silent=True) or {}
    inputs = data.get('inputPaths') or []
    output = data.get('outputPath', '')
    if not inputs or len(inputs) < 2:
        return jsonify({"ok": False, "error": "至少需要 2 个输入文件"}), 400
    for p in inputs:
        if not os.path.exists(p):
            return jsonify({"ok": False, "error": f"输入文件不存在: {p}"}), 404
    if not output:
        import config
        from datetime import datetime as _dt
        output = os.path.join(str(config.DATA_DIR), "pdf", f"merged_{_dt.now().strftime('%Y%m%d_%H%M%S')}.pdf")
    try:
        from PyPDF2 import PdfWriter
        out_path = _pdf_output_path(output)
        writer = PdfWriter()
        for p in inputs:
            writer.append(p)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, 'wb') as f:
            writer.write(f)
        return jsonify({"ok": True, "outputPath": out_path, "pages": len(writer.pages)})
    except ImportError:
        return jsonify({"ok": False, "error": "PyPDF2 未安装，请 pip install PyPDF2"}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@tools_bp.route('/pdf/split', methods=['POST'])
def split_pdf():
    """按页码拆分 PDF，例如 pages="1-3,5"（PyPDF2 真实拆分）"""
    data = request.get_json(silent=True) or {}
    input_path = data.get('inputPath', '')
    pages_spec = str(data.get('pages', '')).strip()
    output_dir = data.get('outputDir', '')
    if not input_path or not os.path.exists(input_path):
        return jsonify({"ok": False, "error": "输入文件不存在"}), 404
    if not pages_spec:
        return jsonify({"ok": False, "error": "缺少 pages，例如 1-3,5"}), 400
    if not output_dir:
        import config
        output_dir = os.path.join(str(config.DATA_DIR), "pdf")
    try:
        from PyPDF2 import PdfReader, PdfWriter
        import config
        out_root = os.path.realpath(os.path.abspath(output_dir))
        data_root = os.path.realpath(str(config.DATA_DIR))
        if os.path.commonpath([out_root, data_root]) != data_root:
            return jsonify({"ok": False, "error": "输出目录必须位于应用数据目录"}), 403
        reader = PdfReader(input_path)
        total = len(reader.pages)
        writer = PdfWriter()
        wanted = []
        for part in pages_spec.split(','):
            part = part.strip()
            if not part:
                continue
            if '-' in part:
                a, b = part.split('-', 1)
                wanted.extend(range(int(a), int(b) + 1))
            else:
                wanted.append(int(part))
        invalid = [p for p in wanted if p < 1 or p > total]
        if invalid:
            return jsonify({"ok": False, "error": f"页码越界（共 {total} 页）: {invalid}"}), 400
        for p in wanted:
            writer.add_page(reader.pages[p - 1])
        os.makedirs(out_root, exist_ok=True)
        base = os.path.splitext(os.path.basename(input_path))[0]
        out_path = os.path.join(out_root, f"{base}_pages.pdf")
        with open(out_path, 'wb') as f:
            writer.write(f)
        return jsonify({"ok": True, "outputPath": out_path, "pages": len(writer.pages)})
    except ImportError:
        return jsonify({"ok": False, "error": "PyPDF2 未安装，请 pip install PyPDF2"}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

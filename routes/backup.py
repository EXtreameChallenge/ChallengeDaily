import os
import io
import json
import logging

from flask import Blueprint, jsonify, request, Response
from datetime import datetime as _datetime
from pathlib import Path

from config import BASE_DIR
from routes.deps import safe_error

logger = logging.getLogger(__name__)

bp = Blueprint('backup', __name__)


@bp.route("/api/backup", methods=["POST"])
def create_backup():
    import zipfile

    buf = io.BytesIO()
    backup_files = [
        ("xiaohei.db", BASE_DIR / "data" / "xiaohei.db"),
        ("settings.json", BASE_DIR / "data" / "settings.json"),
        ("webhooks.json", BASE_DIR / "data" / "webhooks.json"),
        ("auto_report.json", BASE_DIR / "data" / "auto_report.json"),
    ]

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, path in backup_files:
            if path.exists():
                zf.write(path, name)

    buf.seek(0)
    timestamp = _datetime.now().strftime("%Y%m%d_%H%M%S")
    return Response(
        buf.getvalue(),
        mimetype="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=ChallengeDaily_backup_{timestamp}.zip",
        },
    )


@bp.route("/api/backup/info", methods=["GET"])
def backup_info():
    db_path = BASE_DIR / "data" / "xiaohei.db"
    db_size_mb = round(db_path.stat().st_size / (1024 * 1024), 2) if db_path.exists() else 0

    from db import get_conn
    try:
        with get_conn() as conn:
            activities_count = conn.execute("SELECT COUNT(*) as c FROM activities").fetchone()["c"]
            reports_count = conn.execute("SELECT COUNT(*) as c FROM reports").fetchone()["c"]
    except Exception:
        activities_count = 0
        reports_count = 0

    return jsonify({
        "db_size_mb": db_size_mb,
        "activities_count": activities_count,
        "reports_count": reports_count,
    })


@bp.route("/api/backup/restore", methods=["POST"])
def restore_backup():
    import zipfile
    import tempfile

    if "file" not in request.files:
        return jsonify({"error": "未找到备份文件"}), 400

    uploaded = request.files["file"]
    if not uploaded.filename.endswith(".zip"):
        return jsonify({"error": "仅支持 .zip 备份文件"}), 400

    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            uploaded.save(tmp)
            tmp_path = tmp.name

        restore_map = {
            "xiaohei.db": BASE_DIR / "data" / "xiaohei.db",
            "settings.json": BASE_DIR / "data" / "settings.json",
            "webhooks.json": BASE_DIR / "data" / "webhooks.json",
            "auto_report.json": BASE_DIR / "data" / "auto_report.json",
        }

        restored = []
        from file_utils import backup_file
        with zipfile.ZipFile(tmp_path, "r") as zf:
            for name in zf.namelist():
                # 路径遍历防护：跳过绝对路径 / 上级目录（..）条目
                if name.startswith("/") or ".." in Path(name).parts:
                    logger.warning(f"跳过可疑 zip 条目: {name}")
                    continue
                if name in restore_map:
                    target = restore_map[name]
                    if target.exists():
                        backup_file(target)
                    with zf.open(name) as src, open(target, "wb") as dst:
                        dst.write(src.read())
                    restored.append(name)

        try:
            os.unlink(tmp_path)
        except Exception:
            pass

        # 恢复 settings.json 后校验 ai_base_url，防止恶意配置导致后续请求被劫持
        settings_path = BASE_DIR / "data" / "settings.json"
        if settings_path.exists() and "settings.json" in restored:
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    s_data = json.load(f)
                ai_base_url = (s_data.get("ai_base_url") or "").strip()
                if ai_base_url and not (ai_base_url.startswith("http://") or ai_base_url.startswith("https://")):
                    logger.warning(f"恢复的 ai_base_url 不合法: {ai_base_url}, 将忽略该配置")
                    s_data["ai_base_url"] = ""
                    with open(settings_path, "w", encoding="utf-8") as f:
                        json.dump(s_data, f, ensure_ascii=False, indent=2)
            except Exception as se:
                logger.warning(f"校验 ai_base_url 失败: {type(se).__name__}")

        # 恢复数据库后强制跑一次迁移，确保新代码与旧库结构一致
        try:
            import db as _db
            _db.init_db()
        except Exception as ie:
            logger.warning(f"恢复后 init_db 失败: {type(ie).__name__}")

        try:
            from ai_client import _reset_client
            _reset_client()
        except Exception:
            pass

        logger.info(f"数据恢复完成，恢复了 {len(restored)} 个文件: {restored}")
        return jsonify({"status": "ok", "restored_files": restored})
    except zipfile.BadZipFile:
        return jsonify({"error": "备份文件已损坏，无法解压"}), 400
    except Exception as e:
        return jsonify({"error": safe_error(e, "数据恢复失败")}), 500

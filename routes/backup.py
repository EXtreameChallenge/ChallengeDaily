import os
import io
import json
import hashlib
import logging

from flask import Blueprint, jsonify, request, Response
from datetime import datetime as _datetime
from pathlib import Path

from config import DATA_DIR
from routes.deps import safe_error

logger = logging.getLogger(__name__)

bp = Blueprint('backup', __name__)


@bp.route("/api/backup", methods=["POST"])
def create_backup():
    import zipfile

    # 创建备份前先执行 WAL checkpoint，确保所有数据都写入主 DB 文件
    try:
        from db import get_conn
        with get_conn() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception as e:
        logger.warning(f"WAL checkpoint 失败（备份可能不完整）: {e}")

    buf = io.BytesIO()
    backup_files = [
        ("xiaohei.db", DATA_DIR / "xiaohei.db"),
        ("settings.json", DATA_DIR / "settings.json"),
        ("webhooks.json", DATA_DIR / "webhooks.json"),
        ("auto_report.json", DATA_DIR / "auto_report.json"),
    ]

    manifest = {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, path in backup_files:
            if path.exists():
                zf.write(path, name)
                # 计算文件 SHA256 用于恢复时校验完整性
                sha = hashlib.sha256(path.read_bytes()).hexdigest()
                manifest[name] = {"sha256": sha, "size": path.stat().st_size}
        # 写入 manifest
        if manifest:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))

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
    db_path = DATA_DIR / "xiaohei.db"
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
            "xiaohei.db": DATA_DIR / "xiaohei.db",
            "settings.json": DATA_DIR / "settings.json",
            "webhooks.json": DATA_DIR / "webhooks.json",
            "auto_report.json": DATA_DIR / "auto_report.json",
        }

        restored = []
        integrity_errors = []
        from file_utils import backup_file
        with zipfile.ZipFile(tmp_path, "r") as zf:
            # 读取 manifest 用于完整性校验
            manifest = {}
            if "manifest.json" in zf.namelist():
                try:
                    manifest = json.loads(zf.read("manifest.json"))
                except Exception:
                    logger.warning("manifest.json 解析失败，跳过哈希校验")

            for name in zf.namelist():
                # 跳过 manifest 本身
                if name == "manifest.json":
                    continue
                # 路径遍历防护：跳过绝对路径 / 上级目录（..）条目
                if name.startswith("/") or ".." in Path(name).parts:
                    logger.warning(f"跳过可疑 zip 条目: {name}")
                    continue
                if name in restore_map:
                    # 校验文件哈希（如果 manifest 中有记录）
                    if name in manifest:
                        file_data = zf.read(name)
                        actual_sha = hashlib.sha256(file_data).hexdigest()
                        expected_sha = manifest[name].get("sha256", "")
                        if expected_sha and actual_sha != expected_sha:
                            integrity_errors.append(f"{name}: 哈希不匹配")
                            logger.error(f"备份文件 {name} 完整性校验失败: 期望 {expected_sha[:16]}... 实际 {actual_sha[:16]}...")
                            continue
                        # 写入校验通过的数据
                        target = restore_map[name]
                        if target.exists():
                            backup_file(target)
                        target.write_bytes(file_data)
                        restored.append(name)
                        continue

                    target = restore_map[name]
                    if target.exists():
                        backup_file(target)
                    with zf.open(name) as src, open(target, "wb") as dst:
                        dst.write(src.read())
                    restored.append(name)

        if integrity_errors:
            return jsonify({"error": f"备份文件完整性校验失败: {'; '.join(integrity_errors)}"}), 400

        try:
            os.unlink(tmp_path)
        except Exception:
            pass

        # 恢复 settings.json 后校验 ai_base_url，防止恶意配置导致后续请求被劫持
        settings_path = DATA_DIR / "settings.json"
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

        # 恢复数据库后强制重置旧连接，确保新 DB 文件生效
        # 旧连接持有文件描述符指向被覆盖前的 DB，必须关闭
        if "xiaohei.db" in restored:
            try:
                import db as _db
                _db._persistent_conn = None
                logger.info("备份恢复：已重置持久数据库连接")
            except Exception:
                pass

        # 恢复数据库后强制跑一次迁移，确保新代码与旧库结构一致
        try:
            import db as _db
            _db.init_db()
        except Exception as ie:
            logger.warning(f"恢复后 init_db 失败: {type(ie).__name__}")

        # 完整性校验：恢复的数据库必须通过 PRAGMA integrity_check
        if "xiaohei.db" in restored:
            try:
                import db as _db
                with _db.get_conn() as conn:
                    result = conn.execute("PRAGMA integrity_check").fetchone()
                    if result["integrity_check"] != "ok":
                        logger.error(f"恢复的数据库完整性校验失败: {result['integrity_check']}")
                        return jsonify({"error": "恢复的数据库完整性校验失败，备份文件可能已损坏"}), 400
            except Exception as ie:
                logger.warning(f"完整性校验执行失败: {type(ie).__name__}")

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

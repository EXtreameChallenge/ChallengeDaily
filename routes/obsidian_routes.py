"""Obsidian 同步与读入 API
========================
提供 /api/obsidian/* 接口，覆盖两个方向：

【幕布 → Obsidian（写出）】
  GET  /api/obsidian/status           写出同步状态
  POST /api/obsidian/set-vault        设置 Obsidian vault 路径
  POST /api/obsidian/sync-mubu        触发幕布→Obsidian 写出同步
  GET  /api/obsidian/notes             列出 vault 里已写出的笔记文件

【Obsidian → 项目（读入）】
  GET  /api/obsidian/reader-status     读入状态（已扫描笔记数、最后扫描时间）
  POST /api/obsidian/scan              触发扫描 vault（入库 + 向量化）
  GET  /api/obsidian/indexed-notes     列出已扫描入库的笔记
  GET  /api/obsidian/indexed-notes/<path>  单篇笔记（含正文）
  GET  /api/obsidian/search-notes      关键词搜索已索引笔记
  POST /api/obsidian/extract-todos     从笔记提取待办并写入 todos 表
  GET  /api/obsidian/stats             笔记库统计（数量、字数、标签/文件夹分布）
"""
import logging
import threading

from flask import Blueprint, request, jsonify

import obsidian_sync
from routes.deps import check_token, safe_error

logger = logging.getLogger(__name__)

bp = Blueprint('obsidian', __name__, url_prefix='/api/obsidian')

# 同步锁，防止并发触发多次同步
_sync_lock = threading.Lock()
_sync_running = False


@bp.route('/status', methods=['GET'])
def status():
    """获取 Obsidian 同步状态"""
    return jsonify(obsidian_sync.get_sync_status())


@bp.route('/set-vault', methods=['POST'])
def set_vault():
    """设置 Obsidian vault 路径

    Body:
        {"path": "D:\\Obsidian\\MyVault"}
    """
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    path = (data.get('path') or '').strip()
    if not path:
        return jsonify({"error": "path 不能为空"}), 400

    ok = obsidian_sync.set_vault_path(path)
    if not ok:
        return jsonify({"error": "路径不存在或不是目录，请检查后重试", "path": path}), 400
    return jsonify({
        "status": "ok",
        "vault_path": obsidian_sync.get_vault_path(),
        "message": "Obsidian vault 路径已保存",
    })


@bp.route('/sync-mubu', methods=['POST'])
def sync_mubu():
    """触发幕布→Obsidian 同步

    Body:
        {"force": false}   # force=true 时强制重写所有文件
    """
    global _sync_running
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401

    # 检查 vault 是否已配置
    if not obsidian_sync.is_vault_configured():
        return jsonify({
            "error": "Obsidian vault 未配置，请先调用 /api/obsidian/set-vault 设置路径",
            "status": "not_configured",
        }), 400

    # 防并发
    if not _sync_lock.acquire(blocking=False):
        return jsonify({"error": "同步正在进行中，请稍后再试", "status": "running"}), 409

    data = request.get_json(force=True, silent=True) or {}
    force = bool(data.get('force', False))

    def _run():
        global _sync_running
        try:
            _sync_running = True
            obsidian_sync.sync_mubu_to_obsidian(force=force)
        except Exception as e:
            logger.error(f"幕布→Obsidian 同步后台任务失败: {e}", exc_info=True)
        finally:
            _sync_running = False
            _sync_lock.release()

    # 同步可能耗时较长（大量文件），放到后台线程执行
    threading.Thread(target=_run, name="obsidian-sync", daemon=True).start()

    return jsonify({
        "status": "ok",
        "message": "同步已在后台启动，完成后可通过 /api/obsidian/status 查看结果",
        "force": force,
    })


@bp.route('/notes', methods=['GET'])
def list_notes():
    """列出已同步到 Obsidian 的笔记文件

    Query: limit=100
    """
    try:
        limit = max(1, min(500, int(request.args.get('limit', 100))))
    except (TypeError, ValueError):
        limit = 100
    notes = obsidian_sync.list_synced_notes(limit=limit)
    return jsonify({"notes": notes, "count": len(notes)})


# ═══════════════════════════════════════════════════
# Obsidian 读入（vault → 项目）相关接口
# ═══════════════════════════════════════════════════

_scan_lock = threading.Lock()
_scan_running = False


@bp.route('/reader-status', methods=['GET'])
def reader_status():
    """获取 Obsidian 读入状态（vault 扫描、已索引笔记数）"""
    import obsidian_reader
    return jsonify(obsidian_reader.get_reader_status())


@bp.route('/scan', methods=['POST'])
def scan_vault():
    """触发扫描 Obsidian vault，把笔记读入数据库并向量化

    Body:
        {"force": false}   # force=true 时强制重新扫描所有文件
    """
    global _scan_running
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401

    import obsidian_reader

    if not obsidian_reader.is_vault_configured():
        return jsonify({
            "error": "Obsidian vault 未配置，请先调用 /api/obsidian/set-vault 设置路径",
            "status": "not_configured",
        }), 400

    if not _scan_lock.acquire(blocking=False):
        return jsonify({"error": "扫描正在进行中，请稍后再试", "status": "running"}), 409

    data = request.get_json(force=True, silent=True) or {}
    force = bool(data.get('force', False))

    def _run():
        global _scan_running
        try:
            _scan_running = True
            obsidian_reader.scan_vault(force=force)
        except Exception as e:
            logger.error(f"Obsidian 扫描后台任务失败: {e}", exc_info=True)
        finally:
            _scan_running = False
            _scan_lock.release()

    threading.Thread(target=_run, name="obsidian-scan", daemon=True).start()

    return jsonify({
        "status": "ok",
        "message": "扫描已在后台启动，完成后可通过 /api/obsidian/reader-status 查看结果",
        "force": force,
    })


@bp.route('/indexed-notes', methods=['GET'])
def list_indexed_notes():
    """列出已扫描入库的 Obsidian 笔记（不含正文）

    Query: folder=xxx&limit=100
    """
    import obsidian_reader
    folder = request.args.get('folder') or None
    try:
        limit = max(1, min(500, int(request.args.get('limit', 100))))
    except (TypeError, ValueError):
        limit = 100
    notes = obsidian_reader.list_notes(folder=folder, limit=limit)
    return jsonify({"notes": notes, "count": len(notes)})


@bp.route('/indexed-notes/<path:note_path>', methods=['GET'])
def get_indexed_note(note_path):
    """获取单篇已索引笔记（含正文）"""
    import obsidian_reader
    note = obsidian_reader.get_note(note_path)
    if not note:
        return jsonify({"error": "笔记不存在"}), 404
    return jsonify({"note": note})


@bp.route('/search-notes', methods=['GET'])
def search_indexed_notes():
    """在已索引的 Obsidian 笔记中关键词搜索

    Query: q=xxx&limit=20
    """
    import obsidian_reader
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({"error": "q 不能为空"}), 400
    try:
        limit = max(1, min(100, int(request.args.get('limit', 20))))
    except (TypeError, ValueError):
        limit = 20
    results = obsidian_reader.search_notes(q, limit=limit)
    return jsonify({"results": results, "count": len(results), "query": q})


@bp.route('/extract-todos', methods=['POST'])
def extract_todos():
    """从 Obsidian 笔记中提取待办项，并写入项目的 todos 表

    Body:
        {"limit": 200}   # 最多扫描多少篇笔记
    """
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    import obsidian_reader
    data = request.get_json(force=True, silent=True) or {}
    try:
        limit = max(1, min(1000, int(data.get('limit', 200))))
    except (TypeError, ValueError):
        limit = 200
    try:
        result = obsidian_reader.extract_all_todos(limit=limit)
        return jsonify({
            "status": "ok",
            "extracted": result["extracted"],
            "inserted": result["inserted"],
            "todos": result["todos"],
        })
    except Exception as e:
        return jsonify({"error": safe_error(e, "待办提取失败")}), 500


@bp.route('/stats', methods=['GET'])
def obsidian_stats():
    """获取 Obsidian 笔记库的统计数据（笔记数、字数、标签分布、文件夹分布等）"""
    import obsidian_reader
    try:
        stats = obsidian_reader.get_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": safe_error(e, "统计获取失败")}), 500

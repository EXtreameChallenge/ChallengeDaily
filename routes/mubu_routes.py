"""幕布文档同步 API
================
提供 /api/mubu/* 接口：
  GET  /api/mubu/status           同步状态
  GET  /api/mubu/docs             文档列表（不含正文）
  GET  /api/mubu/docs/<doc_id>    单篇文档（含正文）
  GET  /api/mubu/search?q=xxx     关键词搜索
  POST /api/mubu/ingest          Electron 推送文档入库
  POST /api/mubu/sync/trigger     触发同步（Electron 收到后开始拉取）
  GET  /api/mubu/context          获取最近文档作为 AI 上下文（供日报使用）
"""
import logging
from datetime import datetime

from flask import Blueprint, request, jsonify

import mubu_sync
from routes.deps import check_token, safe_error

logger = logging.getLogger(__name__)

bp = Blueprint('mubu', __name__, url_prefix='/api/mubu')


@bp.route('/status', methods=['GET'])
def status():
    """获取幕布同步状态"""
    return jsonify(mubu_sync.get_sync_status())


@bp.route('/docs', methods=['GET'])
def list_docs():
    """文档列表"""
    parent_id = request.args.get('parent_id')
    try:
        limit = max(1, min(500, int(request.args.get('limit', 100))))
    except (TypeError, ValueError):
        limit = 100
    docs = mubu_sync.list_docs(parent_id=parent_id, limit=limit)
    return jsonify({"docs": docs, "count": len(docs)})


@bp.route('/docs/<doc_id>', methods=['GET'])
def get_doc(doc_id):
    """单篇文档"""
    doc = mubu_sync.get_doc(doc_id)
    if not doc:
        return jsonify({"error": "文档不存在"}), 404
    return jsonify({"doc": doc})


@bp.route('/search', methods=['GET'])
def search():
    """关键词搜索"""
    q = request.args.get('q', '').strip()
    try:
        limit = max(1, min(100, int(request.args.get('limit', 20))))
    except (TypeError, ValueError):
        limit = 20
    results = mubu_sync.search_docs(q, limit)
    return jsonify({"results": results, "count": len(results), "query": q})


@bp.route('/ingest', methods=['POST'])
def ingest():
    """Electron 推送文档入库（批量）

    Body:
        {"docs": [{"doc_id": "xxx", "title": "...", "content_md": "...", ...}, ...]}
    """
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    docs = data.get('docs', [])
    if not isinstance(docs, list) or not docs:
        return jsonify({"error": "docs 必须是数组"}), 400

    try:
        count = mubu_sync.batch_upsert(docs)
        mubu_sync.set_sync_state("last_sync_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        mubu_sync.set_sync_state("last_error", "")
        mubu_sync.set_sync_state("cookie_valid", "1")
        return jsonify({"status": "ok", "ingested": count, "total": len(docs)})
    except Exception as e:
        mubu_sync.set_sync_state("last_error", str(e))
        return jsonify({"error": safe_error(e, "入库失败")}), 500


@bp.route('/sync/trigger', methods=['POST'])
def trigger_sync():
    """触发同步——通知 Electron 开始拉取

    通过 SSE event_bus 推送 mubu:sync:request 事件，
    Electron main.cjs 监听到后执行 BrowserWindow 注入 JS 拉取。
    """
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from event_bus import push_event
        push_event('mubu:sync:request', {"requested_at": datetime.now().isoformat()})
        return jsonify({"status": "ok", "message": "同步请求已发送"})
    except ImportError:
        # event_bus 不存在时降级：直接返回 ok，等待下次定时同步
        return jsonify({"status": "ok", "message": "event_bus 不可用，请等待下次定时同步"})
    except Exception as e:
        return jsonify({"error": safe_error(e, "触发同步失败")}), 500


@bp.route('/login-request', methods=['POST'])
def login_request():
    """请求 Electron 弹出幕布登录窗口（绕过 IPC 注册不稳定问题）"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from event_bus import push_event
        push_event('mubu:login:request', {"requested_at": datetime.now().isoformat()})
        return jsonify({"status": "ok", "message": "登录窗口请求已发送"})
    except ImportError:
        return jsonify({"status": "ok", "message": "event_bus 不可用，请使用桌面端菜单手动登录"})
    except Exception as e:
        return jsonify({"error": safe_error(e, "请求登录失败")}), 500


@bp.route('/context', methods=['GET'])
def ai_context():
    """获取最近文档作为 AI 上下文（供日报生成使用）

    返回正文片段（前 2000 字符），按 edit_time 倒序
    """
    try:
        days = max(1, min(90, int(request.args.get('days', 7))))
    except (TypeError, ValueError):
        days = 7
    try:
        limit = max(1, min(50, int(request.args.get('limit', 20))))
    except (TypeError, ValueError):
        limit = 20

    docs = mubu_sync.get_recent_docs(days=days, limit=limit)
    # 截断正文避免上下文过长
    for d in docs:
        md = d.get('content_md', '')
        if len(md) > 2000:
            d['content_md'] = md[:2000] + "\n...(截断)"
    return jsonify({
        "docs": docs,
        "count": len(docs),
        "days": days,
    })


@bp.route('/extract-todos', methods=['POST'])
def extract_todos():
    """从幕布文档提取待办项（启发式）

    Body:
        {"doc_id": "xxx"}  # 不传则扫描最近 7 天所有文档
    """
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    doc_id = data.get('doc_id')

    if doc_id:
        doc = mubu_sync.get_doc(doc_id)
        if not doc:
            return jsonify({"error": "文档不存在"}), 404
        todos = mubu_sync.extract_todos_from_doc(doc)
        return jsonify({"todos": todos, "source": doc_id})
    else:
        # 扫描最近 7 天文档
        docs = mubu_sync.get_recent_docs(days=7, limit=50)
        all_todos = []
        for d in docs:
            ts = mubu_sync.extract_todos_from_doc(d)
            for t in ts:
                t['doc_title'] = d.get('title', '')
                all_todos.append(t)
        return jsonify({"todos": all_todos, "count": len(all_todos)})

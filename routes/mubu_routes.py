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

同时提供 /api/memory/* 记忆系统接口（注册为独立蓝图 memory_bp）：
  POST /api/memory/search         混合检索（BM25 + 向量 RRF）
  POST /api/memory/index          手动触发向量化
  GET  /api/memory/status         向量化状态
  POST /api/memory/extract        手动触发事实抽取
  GET  /api/memory/list           列出所有记忆
  DELETE /api/memory/<memory_id>  删除记忆
  POST /api/memory/query          AI 对话记忆注入
"""
import logging
import re
import threading
from datetime import datetime

from flask import Blueprint, request, jsonify

import mubu_sync
from routes.deps import check_token, safe_error

logger = logging.getLogger(__name__)

bp = Blueprint('mubu', __name__, url_prefix='/api/mubu')

# 记忆系统独立蓝图（与 mubu 共用一个文件，方便维护）
memory_bp = Blueprint('memory', __name__, url_prefix='/api/memory')

# memory_id 安全校验：仅允许 UUID 格式（防止 SQL 注入 / 路径穿越）
_MEMORY_ID_RE = re.compile(r"^[0-9a-fA-F-]{8,64}$")


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


# ═══════════════════════════════════════════════════════════════
# 记忆系统路由 /api/memory/*
# ═══════════════════════════════════════════════════════════════


def _memory_engine():
    """惰性加载 memory_engine，避免模块导入失败影响整个蓝图注册"""
    import memory_engine
    return memory_engine


@memory_bp.route('/search', methods=['POST'])
def memory_search():
    """混合检索（BM25 + 向量 RRF）

    Body: {"query": "搜索词", "limit": 10}
    """
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    query = (data.get('query') or '').strip()
    if not query:
        return jsonify({"error": "query 不能为空"}), 400
    if len(query) > 500:
        return jsonify({"error": "query 过长（上限 500 字符）"}), 400
    try:
        limit = max(1, min(50, int(data.get('limit', 10))))
    except (TypeError, ValueError):
        limit = 10
    try:
        me = _memory_engine()
        results = me.hybrid_search(query, limit=limit)
        return jsonify({"results": results, "count": len(results), "query": query})
    except Exception as e:
        return jsonify({"error": safe_error(e, "检索失败")}), 500


@memory_bp.route('/index', methods=['POST'])
def memory_index():
    """手动触发向量化

    Body:
        {"source": "mubu", "source_id": "doc_id"}   # 索引单篇
        {"all": true}                                # 索引所有未索引文档（后台执行）
    """
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    try:
        me = _memory_engine()
        # 模式一：索引所有未索引文档（后台线程）
        if data.get('all'):
            docs = mubu_sync.get_unindexed_docs(limit=5000)
            if not docs:
                return jsonify({"status": "ok", "message": "无未索引文档", "queued": 0})
            to_index = [{
                "source": "mubu",
                "source_id": d["doc_id"],
                "title": d.get("title", ""),
                "content": d.get("content_md", ""),
            } for d in docs]

            def _bg():
                try:
                    me.batch_index_documents(to_index)
                except Exception as ex:
                    logger.warning(f"全量索引后台任务失败: {ex}")

            threading.Thread(target=_bg, name="memory-index-all", daemon=True).start()
            return jsonify({"status": "ok", "message": "全量索引已在后台启动", "queued": len(to_index)})

        # 模式二：索引单篇
        source = (data.get('source') or 'mubu').strip()
        source_id = (data.get('source_id') or '').strip()
        if not source_id:
            return jsonify({"error": "source_id 不能为空"}), 400
        # 默认从 mubu_docs 取正文
        if source == 'mubu':
            doc = mubu_sync.get_doc(source_id)
            if not doc:
                return jsonify({"error": "文档不存在"}), 404
            content = doc.get('content_md', '') or ''
            title = doc.get('title', '') or ''
        else:
            content = (data.get('content') or '').strip()
            title = (data.get('title') or '').strip()
            if not content:
                return jsonify({"error": "content 不能为空"}), 400
        n = me.index_document(source, source_id, content, title=title, force=bool(data.get('force', False)))
        return jsonify({"status": "ok", "source": source, "source_id": source_id, "chunks_written": n})
    except Exception as e:
        return jsonify({"error": safe_error(e, "索引失败")}), 500


@memory_bp.route('/status', methods=['GET'])
def memory_status():
    """向量化状态"""
    try:
        me = _memory_engine()
        return jsonify(me.get_indexing_status())
    except Exception as e:
        return jsonify({"error": safe_error(e, "状态获取失败")}), 500


@memory_bp.route('/extract', methods=['POST'])
def memory_extract():
    """手动触发事实抽取

    Body:
        {"content": "...", "source_type": "mubu", "source_id": "xxx"}
        {"doc_id": "xxx"}  # 从 mubu 文档抽取
        {"all_unindexed": true}  # 从所有未抽取记忆的 mubu 文档抽取
    """
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    try:
        me = _memory_engine()
        # 模式：从指定 mubu 文档抽取
        if data.get('doc_id'):
            doc = mubu_sync.get_doc(data.get('doc_id'))
            if not doc:
                return jsonify({"error": "文档不存在"}), 404
            content = doc.get('content_md', '') or ''
            title = doc.get('title', '') or ''
            full = f"{title}\n\n{content}" if title else content
            facts = me.extract_facts(full, source_type='mubu', source_id=doc['doc_id'])
            # 顺手入库为记忆
            added_ids = []
            for f in facts:
                mid = me.add_memory(f, source_type='mubu', source_id=doc['doc_id'])
                if mid:
                    added_ids.append(mid)
            return jsonify({"facts": facts, "memory_ids": added_ids, "source": doc['doc_id']})

        # 模式：直接给定 content
        content = (data.get('content') or '').strip()
        if not content:
            return jsonify({"error": "content 或 doc_id 不能为空"}), 400
        source_type = (data.get('source_type') or 'manual').strip()
        source_id = (data.get('source_id') or '').strip()
        facts = me.extract_facts(content, source_type=source_type, source_id=source_id)
        added_ids = []
        for f in facts:
            mid = me.add_memory(f, source_type=source_type, source_id=source_id)
            if mid:
                added_ids.append(mid)
        return jsonify({"facts": facts, "memory_ids": added_ids})
    except Exception as e:
        return jsonify({"error": safe_error(e, "事实抽取失败")}), 500


@memory_bp.route('/list', methods=['GET'])
def memory_list():
    """列出所有记忆

    Query: source_type=xxx&limit=100&include_deleted=0
    """
    try:
        me = _memory_engine()
        source_type = request.args.get('source_type') or None
        try:
            limit = max(1, min(500, int(request.args.get('limit', 100))))
        except (TypeError, ValueError):
            limit = 100
        include_deleted = request.args.get('include_deleted', '0') in ('1', 'true', 'yes')
        items = me.list_memories(source_type=source_type, limit=limit, include_deleted=include_deleted)
        return jsonify({"memories": items, "count": len(items)})
    except Exception as e:
        return jsonify({"error": safe_error(e, "列表查询失败")}), 500


@memory_bp.route('/<memory_id>', methods=['DELETE'])
def memory_delete(memory_id):
    """删除记忆（软删除）"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    if not memory_id or not _MEMORY_ID_RE.match(memory_id):
        return jsonify({"error": "memory_id 格式非法"}), 400
    try:
        me = _memory_engine()
        ok = me.delete_memory(memory_id)
        if not ok:
            return jsonify({"error": "记忆不存在或已删除"}), 404
        return jsonify({"status": "ok", "memory_id": memory_id})
    except Exception as e:
        return jsonify({"error": safe_error(e, "删除失败")}), 500


@memory_bp.route('/query', methods=['POST'])
def memory_query():
    """AI 对话记忆注入——返回与 query 相关的记忆 + 文档片段上下文

    Body: {"query": "用户提问", "max_tokens": 2000}
    """
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    query = (data.get('query') or '').strip()
    if not query:
        return jsonify({"error": "query 不能为空"}), 400
    if len(query) > 1000:
        return jsonify({"error": "query 过长（上限 1000 字符）"}), 400
    try:
        max_tokens = max(200, min(8000, int(data.get('max_tokens', 2000))))
    except (TypeError, ValueError):
        max_tokens = 2000
    try:
        me = _memory_engine()
        context = me.build_memory_context(query, max_tokens=max_tokens)
        # 同时返回结构化检索结果，方便前端展示
        memories = me.search_memories(query, limit=5)
        chunks = me.hybrid_search(query, limit=8)
        return jsonify({
            "query": query,
            "context": context,
            "memories": memories,
            "chunks": chunks,
        })
    except Exception as e:
        return jsonify({"error": safe_error(e, "记忆查询失败")}), 500

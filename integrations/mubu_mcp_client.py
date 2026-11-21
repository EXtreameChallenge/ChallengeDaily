"""
幕布 MCP 客户端
================
通过幕布官方 MCP 服务（https://mubu.com/mcp/server）访问幕布文档。

MCP 协议：JSON-RPC 2.0 over Streamable HTTP
授权方式：个人 Token（Bearer）

双保险设计：本模块是首选数据源，失败时由 mubu_sync.trigger_sync_smart()
自动回退到 Electron cookie 逆向方案。

高层 API：
  - set_token / get_token / has_token   Token 管理
  - test_connection()                    测试连接
  - list_tools()                         列出 MCP 暴露的所有工具
  - list_documents(folder_id)            浏览目录/列出文档
  - get_document(doc_id)                 读取单篇文档全文
  - search_documents(query)              搜索文档
  - create_document(title, content, folder_id)  创建文档
  - create_folder(name, parent_id)       创建文件夹
  - sync_all_to_db()                     全量同步到本地数据库
"""
import json
import logging
import time
import urllib.request
import urllib.error
from typing import Optional

logger = logging.getLogger(__name__)

MCP_SERVER_URL = "https://mubu.com/mcp/server"
_TIMEOUT = 30  # 秒

# 模块级缓存：工具列表（首次连接后缓存，避免每次都查）
_cached_tools: Optional[list[dict]] = None
_cached_tool_names: set[str] = set()

# 请求 ID 自增
_req_id = 0


# ── Token 管理 ──────────────────────────────────────

def _settings_path() -> str:
    """获取 settings.json 路径（优先用运行时 DATA_DIR，fallback 到项目 data）"""
    try:
        from config import DATA_DIR
        import os
        return os.path.join(DATA_DIR, "settings.json")
    except Exception:
        return "settings.json"


def _load_settings() -> dict:
    try:
        path = _settings_path()
        import os
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.debug(f"读取 settings 失败: {e}")
    return {}


def _save_settings(settings: dict) -> None:
    try:
        path = _settings_path()
        import os
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"保存 settings 失败: {e}")


def set_token(token: str) -> None:
    """设置幕布 MCP 个人 Token"""
    token = (token or "").strip()
    settings = _load_settings()
    settings["mubu_mcp_token"] = token
    _save_settings(settings)
    # 清空工具缓存，下次连接重新发现
    global _cached_tools, _cached_tool_names
    _cached_tools = None
    _cached_tool_names = set()
    logger.info("幕布 MCP Token 已更新")


def get_token() -> str:
    """获取当前配置的 MCP Token"""
    settings = _load_settings()
    return settings.get("mubu_mcp_token", "").strip()


def has_token() -> bool:
    return bool(get_token())


# ── MCP 协议底层 ──────────────────────────────────────

def _next_id() -> int:
    global _req_id
    _req_id += 1
    return _req_id


def _rpc_call(method: str, params: dict | None = None, timeout: int = _TIMEOUT) -> dict:
    """发送一次 JSON-RPC 请求到幕布 MCP server

    Returns:
        解析后的响应 dict（含 result 或 error）

    Raises:
        RuntimeError: 网络错误、非 200 响应、JSON 解析失败
    """
    token = get_token()
    if not token:
        raise RuntimeError("幕布 MCP Token 未配置，请先在设置中填写 Token")

    payload = {
        "jsonrpc": "2.0",
        "id": _next_id(),
        "method": method,
    }
    if params is not None:
        payload["params"] = params

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        MCP_SERVER_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        if e.code == 401:
            raise RuntimeError(f"MCP 鉴权失败（401），请检查 Token 是否正确或已注销。响应: {body[:200]}")
        raise RuntimeError(f"MCP HTTP 错误 {e.code}: {body[:200]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"MCP 网络错误: {e.reason}")
    except Exception as e:
        raise RuntimeError(f"MCP 请求异常: {e}")

    # Streamable HTTP 可能返回 SSE 格式（data: {...}\n\n），也可能直接返回 JSON
    raw = raw.strip()
    if raw.startswith("data:"):
        # SSE 格式，取最后一个 data 行
        lines = [l.strip() for l in raw.splitlines() if l.strip().startswith("data:")]
        if lines:
            raw = lines[-1][5:].strip()  # 去掉 "data:" 前缀

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.debug(f"MCP 响应非 JSON: {raw[:300]}")
        raise RuntimeError(f"MCP 响应解析失败: {e}; 原始响应前 300 字符: {raw[:300]}")


def _initialize() -> dict:
    """MCP 初始化握手（每次工具调用前自动完成，幂等）"""
    result = _rpc_call("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "challenge-daily", "version": "1.0"},
    })
    if "error" in result:
        raise RuntimeError(f"MCP initialize 失败: {result['error']}")
    return result.get("result", {})


def _send_initialized_notification() -> None:
    """发送 initialized 通知（无响应）"""
    token = get_token()
    if not token:
        return
    payload = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        MCP_SERVER_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception:
        pass  # 通知不需要响应，失败忽略


# ── 工具发现 ──────────────────────────────────────

def list_tools(force_refresh: bool = False) -> list[dict]:
    """列出幕布 MCP 暴露的所有工具

    Args:
        force_refresh: 强制刷新缓存

    Returns:
        工具列表，每项含 name / description / inputSchema
    """
    global _cached_tools, _cached_tool_names
    if _cached_tools is not None and not force_refresh:
        return _cached_tools

    _initialize()
    _send_initialized_notification()
    result = _rpc_call("tools/list", {})
    if "error" in result:
        raise RuntimeError(f"tools/list 失败: {result['error']}")
    tools = result.get("result", {}).get("tools", [])
    _cached_tools = tools
    _cached_tool_names = {t.get("name", "") for t in tools}
    logger.info(f"幕布 MCP 发现 {len(tools)} 个工具: {[t.get('name') for t in tools]}")
    return tools


def _find_tool_name(keywords: list[str]) -> Optional[str]:
    """根据关键词模糊匹配工具名"""
    if not _cached_tool_names:
        try:
            list_tools()
        except Exception:
            return None
    for kw in keywords:
        for name in _cached_tool_names:
            if kw.lower() in name.lower():
                return name
    # 二次匹配：关键词出现在描述里
    if _cached_tools:
        for kw in keywords:
            for t in _cached_tools:
                desc = (t.get("description", "") + " " + t.get("name", "")).lower()
                if kw.lower() in desc:
                    return t.get("name")
    return None


def _call_tool(name: str, arguments: dict | None = None) -> dict:
    """调用一个 MCP 工具

    Returns:
        工具返回结果（已从 content 中提取文本）
    """
    _initialize()
    _send_initialized_notification()
    result = _rpc_call("tools/call", {
        "name": name,
        "arguments": arguments or {},
    })
    if "error" in result:
        raise RuntimeError(f"工具 {name} 调用失败: {result['error']}")
    tool_result = result.get("result", {})
    if tool_result.get("isError"):
        texts = [c.get("text", "") for c in tool_result.get("content", []) if c.get("type") == "text"]
        raise RuntimeError(f"工具 {name} 返回错误: {' '.join(texts)[:300]}")
    # 提取文本内容
    texts = [c.get("text", "") for c in tool_result.get("content", []) if c.get("type") == "text"]
    raw_text = "\n".join(texts)
    # 尝试解析为 JSON
    try:
        parsed = json.loads(raw_text)
        return parsed if isinstance(parsed, dict) else {"data": parsed}
    except (json.JSONDecodeError, ValueError):
        return {"text": raw_text}


# ── 高层 API ──────────────────────────────────────

def test_connection() -> dict:
    """测试 MCP 连接是否正常

    Returns:
        {"ok": bool, "tools_count": int, "tools": [...], "error": str}
    """
    try:
        tools = list_tools(force_refresh=True)
        return {
            "ok": True,
            "tools_count": len(tools),
            "tools": [{"name": t.get("name"), "description": (t.get("description") or "")[:100]} for t in tools],
        }
    except Exception as e:
        logger.warning(f"MCP 连接测试失败: {e}")
        return {"ok": False, "error": str(e), "tools_count": 0, "tools": []}


def list_documents(folder_id: str = "", limit: int = 200) -> list[dict]:
    """浏览目录，列出文档和文件夹

    Args:
        folder_id: 父文件夹 ID，空字符串表示根目录
        limit: 最大返回数量

    Returns:
        文档/文件夹列表
    """
    tool = _find_tool_name(["list", "browse", "directory", "folder"])
    if not tool:
        raise RuntimeError("未找到列出文档的 MCP 工具")
    # 尝试常见参数名
    for arg_name in ["folder_id", "parent_id", "directory_id", "folderId", "parentId"]:
        try:
            result = _call_tool(tool, {arg_name: folder_id, "limit": limit})
            return _extract_doc_list(result)
        except RuntimeError as e:
            if "参数" in str(e) or "argument" in str(e).lower() or "required" in str(e).lower():
                continue
            raise
    # 最后尝试不带参数
    result = _call_tool(tool, {})
    return _extract_doc_list(result)


def get_document(doc_id: str) -> dict:
    """读取单篇文档全文

    Args:
        doc_id: 幕布文档 ID

    Returns:
        文档内容（含 title / content_md / 等）
    """
    tool = _find_tool_name(["get", "read", "document", "doc"])
    if not tool:
        raise RuntimeError("未找到读取文档的 MCP 工具")
    for arg_name in ["doc_id", "document_id", "id", "docId", "documentId"]:
        try:
            result = _call_tool(tool, {arg_name: doc_id})
            return result
        except RuntimeError as e:
            if "参数" in str(e) or "argument" in str(e).lower() or "required" in str(e).lower():
                continue
            raise
    raise RuntimeError(f"读取文档失败，无法确定参数名")


def search_documents(query: str, limit: int = 20) -> list[dict]:
    """搜索文档

    Args:
        query: 搜索关键词
        limit: 最大返回数量

    Returns:
        搜索结果列表
    """
    tool = _find_tool_name(["search", "find"])
    if not tool:
        raise RuntimeError("未找到搜索文档的 MCP 工具")
    for arg_name in ["query", "keyword", "q", "search"]:
        try:
            result = _call_tool(tool, {arg_name: query, "limit": limit})
            return _extract_doc_list(result)
        except RuntimeError as e:
            if "参数" in str(e) or "argument" in str(e).lower() or "required" in str(e).lower():
                continue
            raise
    result = _call_tool(tool, {"query": query})
    return _extract_doc_list(result)


def create_document(title: str, content_md: str = "", folder_id: str = "") -> dict:
    """创建一篇幕布文档

    Args:
        title: 文档标题
        content_md: Markdown 格式正文
        folder_id: 目标文件夹 ID，空表示根目录

    Returns:
        创建结果（含新文档 ID）
    """
    tool = _find_tool_name(["create", "new", "write"])
    if not tool:
        raise RuntimeError("未找到创建文档的 MCP 工具")
    for arg_name in ["folder_id", "parent_id", "directory_id", "folderId", "parentId"]:
        try:
            result = _call_tool(tool, {
                "title": title,
                "content": content_md,
                arg_name: folder_id,
            })
            return result
        except RuntimeError as e:
            if "参数" in str(e) or "argument" in str(e).lower() or "required" in str(e).lower():
                continue
            raise
    return _call_tool(tool, {"title": title, "content": content_md})


def create_folder(name: str, parent_id: str = "") -> dict:
    """创建文件夹"""
    tool = _find_tool_name(["folder", "directory", "mkdir"])
    if not tool:
        raise RuntimeError("未找到创建文件夹的 MCP 工具")
    return _call_tool(tool, {"name": name, "parent_id": parent_id})


def get_account_info() -> dict:
    """获取当前账号信息（昵称、会员到期时间等）"""
    tool = _find_tool_name(["account", "user", "profile", "me"])
    if not tool:
        raise RuntimeError("未找到获取账号信息的 MCP 工具")
    return _call_tool(tool, {})


# ── 工具函数 ──────────────────────────────────────

def _extract_doc_list(result: dict) -> list[dict]:
    """从 MCP 工具返回结果中提取文档列表"""
    if not result:
        return []
    # 常见结构：{"documents": [...]} / {"docs": [...]} / {"items": [...]} / {"data": [...]} / [...]
    for key in ["documents", "docs", "items", "data", "list", "results"]:
        if key in result and isinstance(result[key], list):
            return result[key]
    # 如果 result 本身就是列表
    if isinstance(result, list):
        return result
    # 如果只有 text 字段
    if "text" in result:
        try:
            parsed = json.loads(result["text"])
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                return _extract_doc_list(parsed)
        except Exception:
            pass
    return []


def _normalize_doc(raw: dict) -> dict:
    """将 MCP 返回的文档标准化为项目内部格式"""
    return {
        "doc_id": str(raw.get("doc_id") or raw.get("id") or raw.get("document_id") or ""),
        "title": raw.get("title") or raw.get("name") or "",
        "parent_id": str(raw.get("parent_id") or raw.get("folder_id") or raw.get("parentId") or ""),
        "type": raw.get("type") or ("folder" if raw.get("is_folder") or raw.get("type") == "folder" else "doc"),
        "content_md": raw.get("content_md") or raw.get("content") or raw.get("markdown") or "",
        "content_json": raw.get("content_json") or raw.get("json") or "",
        "edit_time": int(raw.get("edit_time") or raw.get("updated_at") or raw.get("update_time") or 0),
        "extra": {"source": "mcp"},
    }


# ── 全量同步到本地数据库 ──────────────────────────────────────

def sync_all_to_db(progress_callback=None) -> dict:
    """通过 MCP 全量同步幕布文档到本地数据库

    流程：
      1. 列出根目录所有文档和文件夹
      2. 对每篇文档读取全文
      3. 批量入库到 mubu_docs 表
      4. 更新同步状态

    Args:
        progress_callback: 可选回调函数 callback(current, total, title)

    Returns:
        {"total": N, "success": N, "failed": N, "error": str}
    """
    import mubu_sync

    if not has_token():
        return {"total": 0, "success": 0, "failed": 0, "error": "MCP Token 未配置"}

    try:
        # 第一步：列出所有文档（递归）
        all_docs = _recursive_list_all("")
        logger.info(f"MCP 同步：发现 {len(all_docs)} 个文档/文件夹")

        if not all_docs:
            return {"total": 0, "success": 0, "failed": 0, "error": "未找到任何文档"}

        # 第二步：对每篇 doc 类型读取全文
        success = 0
        failed = 0
        normalized_docs = []
        total = len(all_docs)

        for i, raw in enumerate(all_docs):
            try:
                doc = _normalize_doc(raw)
                # 只对 doc 类型读取全文，folder 不需要正文
                if doc["type"] == "doc" and doc["doc_id"]:
                    try:
                        full = get_document(doc["doc_id"])
                        doc["content_md"] = full.get("content_md") or full.get("content") or full.get("markdown") or doc["content_md"]
                        doc["content_json"] = full.get("content_json") or full.get("json") or doc["content_json"]
                        if full.get("title"):
                            doc["title"] = full["title"]
                        if full.get("edit_time") or full.get("updated_at"):
                            doc["edit_time"] = int(full.get("edit_time") or full.get("updated_at") or 0)
                    except Exception as e:
                        logger.debug(f"读取文档全文失败 doc_id={doc['doc_id']}: {e}")
                        # 正文读取失败不阻断，用列表里的元数据入库

                if doc["doc_id"]:
                    normalized_docs.append(doc)
                    success += 1
                else:
                    failed += 1
            except Exception as e:
                logger.warning(f"处理文档失败: {e}")
                failed += 1

            if progress_callback:
                try:
                    progress_callback(i + 1, total, doc.get("title", ""))
                except Exception:
                    pass

            # 每 20 篇休息一下，避免速率限制
            if (i + 1) % 20 == 0:
                time.sleep(0.5)

        # 第三步：批量入库
        if normalized_docs:
            count = mubu_sync.batch_upsert(normalized_docs)
            mubu_sync.set_sync_state("last_sync_time", time.strftime("%Y-%m-%d %H:%M:%S"))
            mubu_sync.set_sync_state("last_error", "")
            mubu_sync.set_sync_state("mcp_last_sync", time.strftime("%Y-%m-%d %H:%M:%S"))
            mubu_sync.set_sync_state("mcp_available", "1")
            logger.info(f"MCP 同步完成：入库 {count} 篇，成功 {success}，失败 {failed}")
        else:
            mubu_sync.set_sync_state("last_error", "MCP 同步未获取到有效文档")

        return {"total": total, "success": success, "failed": failed, "error": ""}

    except Exception as e:
        logger.error(f"MCP 全量同步失败: {e}", exc_info=True)
        mubu_sync.set_sync_state("mcp_available", "0")
        mubu_sync.set_sync_state("last_error", f"MCP同步失败: {e}")
        return {"total": 0, "success": 0, "failed": 0, "error": str(e)}


def _recursive_list_all(folder_id: str, depth: int = 0, max_depth: int = 10) -> list[dict]:
    """递归列出指定目录下所有文档和文件夹"""
    if depth > max_depth:
        return []
    try:
        items = list_documents(folder_id=folder_id, limit=500)
    except Exception as e:
        logger.warning(f"列出目录失败 folder_id={folder_id}: {e}")
        return []

    result = list(items)
    # 递归子文件夹
    for item in items:
        is_folder = (
            item.get("type") == "folder"
            or item.get("is_folder")
            or item.get("isFolder")
        )
        if is_folder:
            child_id = str(item.get("doc_id") or item.get("id") or item.get("folder_id") or "")
            if child_id:
                time.sleep(0.1)  # 避免速率限制
                result.extend(_recursive_list_all(child_id, depth + 1, max_depth))
    return result

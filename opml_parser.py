"""
OPML 解析与批量导入模块
======================
支持将 OPML（Outline Processor Markup Language）文件解析为树形 Markdown，
并批量导入到 mubu_docs 表，复用现有的记忆系统索引链路。

典型场景：
  - 从幕布/Workflowy/其他大纲工具导出 OPML
  - 通过 API 或 MCP 导入本地数据库
  - 后续可被 memory_engine 向量化、混合检索、AI 对话注入

设计约束：
  1. 仅使用 Python 标准库，避免新增 pip 依赖
  2. 递归解析 <outline> 节点，深度对应 Markdown 标题层级（#, ##, ### ...）
  3. text/title 属性 → 标题；note 属性 → 段落正文
  4. 所有用户输入需 sanitize，防止 XSS / 注入
  5. doc_id 基于路径哈希生成，保证幂等（重复导入同一 OPML 不会产生重复记录）
"""
import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from typing import Optional

logger = logging.getLogger(__name__)

# Markdown 标题最大层级（# ~ ######）
_MAX_HEADING_LEVEL = 6
# 单次批量导入上限，避免一次性写入过多导致事务过长
_BATCH_IMPORT_LIMIT = 2000
# 标题/正文字段长度上限（防止超大字段拖慢检索）
_MAX_TITLE_LEN = 500
_MAX_CONTENT_LEN = 200_000

# OPML outline 节点属性中常见的标题字段名（按优先级取值）
_TITLE_ATTRS = ("text", "title", "name")
# OPML outline 节点属性中常见的正文/注释字段名
_NOTE_ATTRS = ("note", "_note", "description")


# ── 安全 sanitize ────────────────────────────────────────────

# 控制字符过滤：移除 ASCII 控制字符（保留换行 \n 和制表符 \t）
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _sanitize_text(text: str, max_len: int = _MAX_CONTENT_LEN) -> str:
    """清洗用户输入文本：去控制字符 + 截断长度

    - 移除 ASCII 控制字符（保留 \\n \\t）
    - 截断到 max_len 字符，防止超大字段拖慢数据库与检索
    - 不做 HTML 转义（Markdown 渲染层会处理）
    """
    if not text:
        return ""
    # ElementTree 解码后可能为 None
    text = str(text)
    text = _CONTROL_CHAR_RE.sub("", text)
    if len(text) > max_len:
        text = text[:max_len] + "\n...(已截断)"
    return text.strip()


def _gen_doc_id(path: list[str], salt: str = "opml") -> str:
    """根据大纲路径生成幂等 doc_id

    路径由各级 outline 标题组成，保证同一 OPML 结构重复导入时 doc_id 稳定。
    使用 sha256 前 32 字符，避免过长。
    """
    raw = salt + "|" + "/".join(path)
    return "opml-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


# ── 解析核心 ────────────────────────────────────────────────

def _get_outline_title(node: ET.Element) -> str:
    """从 outline 节点提取标题（按优先级尝试多个属性）"""
    for attr in _TITLE_ATTRS:
        v = node.get(attr)
        if v and v.strip():
            return v.strip()
    return ""


def _get_outline_note(node: ET.Element) -> str:
    """从 outline 节点提取正文/注释（按优先级尝试多个属性）"""
    for attr in _NOTE_ATTRS:
        v = node.get(attr)
        if v and v.strip():
            return v.strip()
    # 部分工具会把正文放在 <outline> 的 text 节点子元素里
    text = node.text or ""
    if text.strip():
        return text.strip()
    return ""


def _walk_outline(
    node: ET.Element,
    depth: int,
    path: list[str],
    lines: list[str],
    nodes_out: list[dict],
) -> None:
    """递归遍历 <outline> 节点，输出 Markdown 行 + 节点元数据

    Args:
        node: 当前 outline Element
        depth: 当前深度（1-based，对应 # 一级标题）
        path: 从根到当前节点的标题路径
        lines: 累积的 Markdown 行
        nodes_out: 累积的节点元数据列表（供后续构建 doc 用）
    """
    title = _get_outline_title(node)
    note = _get_outline_note(node)

    # 标题处理：无标题且有正文时，正文作为段落而非标题
    if title:
        # Markdown 标题层级：# 最多到 ######
        level = min(depth, _MAX_HEADING_LEVEL)
        lines.append("#" * level + " " + title)
        lines.append("")  # 空行分隔
        cur_path = path + [title]
    else:
        cur_path = path

    # 正文处理
    if note:
        lines.append(note)
        lines.append("")

    # 收集节点元数据（含无标题的纯正文节点，作为叶节点）
    if title or note:
        nodes_out.append({
            "title": title or "(无标题)",
            "note": note,
            "depth": depth,
            "path": cur_path,
        })

    # 递归子节点
    for child in node.findall("outline"):
        _walk_outline(child, depth + 1, cur_path, lines, nodes_out)


def parse_opml(content: str) -> dict:
    """解析 OPML 字符串为树形 Markdown + 节点列表

    Args:
        content: OPML 文件内容（XML 字符串）

    Returns:
        {
            "markdown": str,           # 树形 Markdown（合并所有节点）
            "title": str,              # 文档标题（取 head > title，无则用首节点）
            "nodes": list[dict],       # 节点元数据列表
            "node_count": int,
        }

    Raises:
        ValueError: OPML 格式非法或不含 outline 节点
    """
    if not content or not content.strip():
        raise ValueError("OPML 内容为空")

    # 防御：解析前先 sanitize 整体内容（控制字符）
    content = _sanitize_text(content, max_len=5_000_000)

    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        raise ValueError(f"OPML XML 解析失败: {e}") from e

    # 提取文档标题（<head><title>...</title></head>）
    doc_title = ""
    head = root.find("head")
    if head is not None:
        title_el = head.find("title")
        if title_el is not None and (title_el.text or "").strip():
            doc_title = title_el.text.strip()

    # 收集所有顶层 <outline>（OPML 规范中 outline 在 <body> 下，
    # 但部分工具会把 outline 直接放在 root 下，做兼容处理）
    body = root.find("body")
    top_outlines = (body.findall("outline") if body is not None
                    else root.findall("outline"))

    if not top_outlines:
        raise ValueError("OPML 未找到任何 <outline> 节点")

    lines: list[str] = []
    nodes_out: list[dict] = []
    for outline in top_outlines:
        _walk_outline(outline, depth=1, path=[], lines=lines, nodes_out=nodes_out)

    # 文档标题兜底：取首节点标题
    if not doc_title and nodes_out:
        doc_title = nodes_out[0]["title"]

    markdown = "\n".join(lines).strip()

    return {
        "markdown": markdown,
        "title": _sanitize_text(doc_title, max_len=_MAX_TITLE_LEN),
        "nodes": nodes_out,
        "node_count": len(nodes_out),
    }


def parse_opml_file(file_path: str) -> dict:
    """从文件路径解析 OPML

    Args:
        file_path: OPML 文件绝对路径

    Returns:
        同 parse_opml 返回结构
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as e:
        raise ValueError(f"读取 OPML 文件失败: {e}") from e
    return parse_opml(content)


# ── 批量导入 ────────────────────────────────────────────────

def _build_docs_from_parse(parsed: dict, source_label: str = "opml") -> list[dict]:
    """将解析结果转换为 mubu_docs 入库格式

    策略：
      - 整个 OPML 作为一篇文档（markdown 作为正文）
      - 同时按顶级 outline 拆分为多篇子文档（每个顶级 outline 一篇），
        便于更细粒度的检索
      - doc_id 基于路径哈希，幂等

    Args:
        parsed: parse_opml 返回结构
        source_label: 数据来源标签（写入 extra）

    Returns:
        list[dict]: 每个元素是 mubu_sync.upsert_doc 所需的文档字典
    """
    docs: list[dict] = []
    doc_title = parsed["title"] or "OPML 导入文档"
    full_md = parsed["markdown"]

    # 1) 整篇作为一篇文档
    docs.append({
        "doc_id": _gen_doc_id([doc_title], salt=source_label + ":full"),
        "title": _sanitize_text(doc_title, max_len=_MAX_TITLE_LEN),
        "parent_id": "",
        "type": "doc",
        "content_md": _sanitize_text(full_md, max_len=_MAX_CONTENT_LEN),
        "content_json": "",
        "edit_time": 0,
        "extra": {
            "source": source_label,
            "node_count": parsed["node_count"],
            "import_mode": "full",
        },
    })

    # 2) 按顶级 outline 分组拆分（path 长度 == 1 视为顶级）
    #    将其下的所有子节点内容合并为一篇子文档
    current_top: Optional[dict] = None
    current_lines: list[str] = []
    current_path: list[str] = []

    def _flush_current():
        nonlocal current_top, current_lines, current_path
        if current_top is None or not current_lines:
            return
        title = current_top["title"]
        docs.append({
            "doc_id": _gen_doc_id(current_path, salt=source_label + ":section"),
            "title": _sanitize_text(title, max_len=_MAX_TITLE_LEN),
            "parent_id": _gen_doc_id([doc_title], salt=source_label + ":full"),
            "type": "doc",
            "content_md": _sanitize_text("\n".join(current_lines), max_len=_MAX_CONTENT_LEN),
            "content_json": "",
            "edit_time": 0,
            "extra": {
                "source": source_label,
                "section_path": "/".join(current_path),
                "import_mode": "section",
            },
        })
        current_top = None
        current_lines = []
        current_path = []

    for node in parsed["nodes"]:
        # 顶级节点（depth == 1）触发 flush + 新分组
        if node["depth"] == 1:
            _flush_current()
            current_top = node
            current_path = list(node["path"])

        # 累积当前分组的行
        if node["title"]:
            level = min(node["depth"], _MAX_HEADING_LEVEL)
            current_lines.append("#" * level + " " + node["title"])
            current_lines.append("")
        if node["note"]:
            current_lines.append(node["note"])
            current_lines.append("")

    _flush_current()
    return docs


def batch_import_opml(
    content: str | None = None,
    file_path: str | None = None,
    source_label: str = "opml",
    max_docs: int = _BATCH_IMPORT_LIMIT,
) -> dict:
    """解析 OPML 并批量导入到 mubu_docs 表

    Args:
        content: OPML XML 字符串（与 file_path 二选一）
        file_path: OPML 文件路径（与 content 二选一）
        source_label: 数据来源标签，写入 extra，便于后续过滤
        max_docs: 单次导入上限，防止超大 OPML 拖垮数据库

    Returns:
        {
            "status": "ok",
            "title": str,
            "node_count": int,
            "imported": int,        # 实际入库篇数
            "skipped": int,         # 因上限跳过的篇数
            "doc_ids": list[str],   # 入库的 doc_id 列表
        }

    Raises:
        ValueError: 解析失败或参数非法
    """
    if not content and not file_path:
        raise ValueError("必须提供 content 或 file_path")

    if file_path:
        parsed = parse_opml_file(file_path)
    else:
        parsed = parse_opml(content or "")

    docs = _build_docs_from_parse(parsed, source_label=source_label)

    # 上限保护
    imported = 0
    skipped = 0
    doc_ids: list[str] = []
    to_upsert: list[dict] = []

    for d in docs:
        if len(to_upsert) >= max_docs:
            skipped += 1
            continue
        to_upsert.append(d)

    if not to_upsert:
        return {
            "status": "ok",
            "title": parsed["title"],
            "node_count": parsed["node_count"],
            "imported": 0,
            "skipped": len(docs),
            "doc_ids": [],
        }

    # 复用 mubu_sync.batch_upsert（已内置 memory_engine 索引触发）
    try:
        import mubu_sync
        count = mubu_sync.batch_upsert(to_upsert)
        doc_ids = [d["doc_id"] for d in to_upsert[:count]]
        imported = count
    except Exception as e:
        logger.error(f"OPML 批量入库失败: {e}", exc_info=True)
        raise ValueError(f"批量入库失败: {e}") from e

    logger.info(
        f"OPML 导入完成: title={parsed['title']!r} nodes={parsed['node_count']} "
        f"imported={imported} skipped={skipped}"
    )

    return {
        "status": "ok",
        "title": parsed["title"],
        "node_count": parsed["node_count"],
        "imported": imported,
        "skipped": skipped,
        "doc_ids": doc_ids,
    }


# ── 模块自检（开发时手动运行） ────────────────────────────────

if __name__ == "__main__":
    # 简单的 smoke test：解析示例 OPML
    _SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head><title>测试大纲</title></head>
  <body>
    <outline text="第一章">
      <outline text="1.1 节" note="这是 1.1 节的正文">
        <outline text="1.1.1 小节" note="深层节点正文"/>
      </outline>
      <outline text="1.2 节" note="1.2 节内容"/>
    </outline>
    <outline text="第二章" note="第二章独立内容"/>
  </body>
</opml>
"""
    result = parse_opml(_SAMPLE)
    print("=== 解析结果 ===")
    print(f"标题: {result['title']}")
    print(f"节点数: {result['node_count']}")
    print("--- Markdown ---")
    print(result["markdown"])
    print("--- 节点列表 ---")
    for n in result["nodes"]:
        print(f"  depth={n['depth']} path={'/'.join(n['path'])} note={n['note'][:30]!r}")

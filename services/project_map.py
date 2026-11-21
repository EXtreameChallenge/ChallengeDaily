"""
project_map.py — 项目数据地图（给 Agent 看的"目录索引"）

用途：
    Agent 在回答用户问题前，需要知道"这个项目里有哪些 API / 数据表 / 工具可用"。
    本模块扫描 routes/*.py、db.py、agent_tools.py，生成一份"索引地图"
    （只索引模块/端点/表名，不索引具体业务内容），缓存到 data/agent_project_map.json。

缓存策略：
    - 文件带 timestamp，超过 24h 自动重新扫描。
    - force_refresh=True 强制重建。
"""
from __future__ import annotations

import ast
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── 外部路径：基于本文件所在目录定位项目根 ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROUTES_DIR = PROJECT_ROOT / "routes"

try:
    from config import DATA_DIR
except Exception:  # pragma: no cover
    DATA_DIR = PROJECT_ROOT / "data"

CACHE_FILE = Path(DATA_DIR) / "agent_project_map.json"
CACHE_TTL_SEC = 24 * 3600  # 24 小时


# ── 扫描 routes/*.py 提取 API 端点 ────────────────────────────
def _scan_routes() -> list[dict]:
    """用 ast 解析 routes/*.py，提取 Blueprint url_prefix + @bp.route 路径。

    返回：[{"module": "goals", "methods": ["GET"], "path": "/api/goals"}]
    """
    endpoints: list[dict] = []
    if not ROUTES_DIR.exists():
        return endpoints

    for py in sorted(ROUTES_DIR.glob("*.py")):
        if py.name.startswith("_") or py.name == "__init__.py":
            continue
        try:
            src = py.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(src, filename=str(py))
        except Exception as e:
            logger.debug("project_map: 解析 %s 失败: %s", py.name, e)
            continue

        # 第一遍：找 Blueprint(..., url_prefix='/api/xxx')
        url_prefix = ""
        bp_var_names = {"bp"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "Blueprint":
                # Blueprint('name', __name__, url_prefix='...')
                for kw in node.keywords:
                    if kw.arg == "url_prefix" and isinstance(kw.value, ast.Constant):
                        url_prefix = str(kw.value.value)
                # 收集 bp 变量名
                for parent_iter in ast.walk(tree):
                    if isinstance(parent_iter, ast.Assign):
                        for t in parent_iter.targets:
                            if isinstance(t, ast.Name) and isinstance(parent_iter.value, ast.Call) \
                                    and getattr(parent_iter.value.func, "id", "") == "Blueprint":
                                bp_var_names.add(t.id)

        # 第二遍：找 @bp.route('...')
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for deco in node.decorator_list:
                # @bp.route('/path', methods=[...])
                if not isinstance(deco, ast.Call):
                    continue
                func = deco.func
                # 形如 bp.route 或 memory_bp.route
                if not (isinstance(func, ast.Attribute) and func.attr == "route"):
                    continue
                if not isinstance(func.value, ast.Name):
                    continue
                if func.value.id not in bp_var_names:
                    continue

                # 路径参数
                path = ""
                if deco.args and isinstance(deco.args[0], ast.Constant):
                    path = str(deco.args[0].value)
                # methods 关键字
                methods = []
                for kw in deco.keywords:
                    if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
                        for el in kw.value.elts:
                            if isinstance(el, ast.Constant):
                                methods.append(str(el.value).upper())
                if not methods:
                    methods = ["GET"]

                full_path = (url_prefix.rstrip("/") + "/" + path.lstrip("/")).replace("//", "/")
                # 有些 routes 直接写绝对路径（如 stats.py），url_prefix 为空就用 path 本身
                if not url_prefix:
                    full_path = path if path.startswith("/") else "/" + path

                endpoints.append({
                    "module": py.stem,
                    "methods": methods,
                    "path": full_path,
                    "handler": node.name,
                })
    return endpoints


# ── 扫描 db.py 提取表名 ─────────────────────────────────────
def _scan_db_tables() -> list[str]:
    """从 db.py / db_migrations.py 提取 CREATE TABLE 的表名。"""
    tables: set[str] = set()
    candidates = [PROJECT_ROOT / "db.py", PROJECT_ROOT / "db_migrations.py"]
    pat = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"'`]?(\w+)[\"'`]?",
                     re.IGNORECASE)
    for f in candidates:
        if not f.exists():
            continue
        try:
            src = f.read_text(encoding="utf-8", errors="ignore")
            for m in pat.finditer(src):
                tables.add(m.group(1))
        except Exception as e:
            logger.debug("project_map: 扫描 %s 失败: %s", f.name, e)
    return sorted(tables)


# ── 扫描 agent_tools.py 提取工具列表 ─────────────────────────
def _scan_agent_tools() -> list[dict]:
    """从 agent_tools.py 提取 AGENT_TOOLS 列表里的工具名/描述。
    agent_tools 未就绪时返回空列表。
    """
    tools: list[dict] = []
    try:
        import agent_tools  # type: ignore
        for t in getattr(agent_tools, "AGENT_TOOLS", []) or []:
            if isinstance(t, dict):
                tools.append({
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                })
            elif isinstance(t, str):
                tools.append({"name": t, "description": ""})
            elif hasattr(t, "name"):
                # ToolSpec 类实例（agent_tools.ToolSpec）
                tools.append({
                    "name": getattr(t, "name", ""),
                    "description": getattr(t, "description", ""),
                })
    except Exception as e:
        logger.debug("project_map: agent_tools 不可用: %s", e)
    return tools


# ── 主入口：生成地图 ─────────────────────────────────────────
def generate_project_map() -> dict:
    """扫描项目结构，生成模块/API/数据表/工具概览索引（不是内容）。"""
    endpoints = _scan_routes()
    tables = _scan_db_tables()
    tools = _scan_agent_tools()

    # 按模块聚合 API，便于 prompt 注入时阅读
    by_module: dict[str, list[dict]] = {}
    for ep in endpoints:
        by_module.setdefault(ep["module"], []).append(ep)

    return {
        "generated_at": time.time(),
        "generated_at_str": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "api_count": len(endpoints),
            "table_count": len(tables),
            "tool_count": len(tools),
            "module_count": len(by_module),
        },
        "modules": {
            mod: [{"methods": e["methods"], "path": e["path"], "handler": e["handler"]}
                  for e in eps]
            for mod, eps in sorted(by_module.items())
        },
        "tables": tables,
        "tools": tools,
    }


def get_project_map(force_refresh: bool = False) -> dict:
    """获取项目地图。缓存 24h；过期或 force_refresh 时重建。"""
    # 1) 读缓存
    if not force_refresh:
        try:
            if CACHE_FILE.exists():
                data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
                ts = float(data.get("generated_at", 0))
                if time.time() - ts < CACHE_TTL_SEC:
                    return data
                logger.info("project_map: 缓存已过期，重新扫描")
        except Exception as e:
            logger.warning("project_map: 读取缓存失败，重建: %s", e)

    # 2) 重建
    try:
        data = generate_project_map()
    except Exception as e:
        logger.error("project_map: 生成地图失败: %s", e)
        return {"modules": {}, "tables": [], "tools": [], "summary": {}, "generated_at": 0}

    # 3) 写缓存
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("project_map: 写缓存失败: %s", e)
    return data


def search_project_map(query: str, limit: int = 10) -> list[dict]:
    """根据查询关键词在地图中搜索相关 API/表/工具。

    返回：[{"kind": "api"|"table"|"tool", "score": float, "detail": ...}]
    """
    if not query:
        return []
    q = query.lower().strip()
    kmap = get_project_map()

    results: list[dict] = []

    # API：匹配 module / path / handler
    for mod, eps in (kmap.get("modules") or {}).items():
        for ep in eps:
            text = f"{mod} {ep.get('path','')} {ep.get('handler','')}".lower()
            if q in text:
                score = 1.0 if q in ep.get("path", "") else 0.5
                results.append({
                    "kind": "api", "score": score,
                    "detail": f"{mod}: {'/'.join(ep.get('methods',[]))} {ep.get('path','')}",
                })

    # 表：匹配表名
    for t in kmap.get("tables", []) or []:
        if q in t.lower():
            results.append({"kind": "table", "score": 0.8, "detail": t})

    # 工具：匹配 name / description
    for t in kmap.get("tools", []) or []:
        text = f"{t.get('name','')} {t.get('description','')}".lower()
        if q in text:
            results.append({"kind": "tool", "score": 0.7, "detail": t.get("name", "")})

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


def format_map_for_prompt(map_data: Optional[dict] = None,
                          max_modules: int = 20,
                          max_tables: int = 30,
                          max_tools: int = 20) -> str:
    """把地图格式化为适合注入 system prompt 的紧凑文本。"""
    if map_data is None:
        map_data = get_project_map()

    lines: list[str] = ["【本项目可用资源索引】（仅索引名称，具体调用请查对应模块）"]

    # API 按模块聚合
    modules = map_data.get("modules") or {}
    lines.append(f"\n■ API 端点（共 {map_data.get('summary',{}).get('api_count',0)} 个，展示前 {max_modules} 个模块）：")
    for i, (mod, eps) in enumerate(sorted(modules.items())):
        if i >= max_modules:
            lines.append(f"  ... 其余 {len(modules)-max_modules} 个模块略")
            break
        paths = ", ".join(
            f"{'/'.join(e.get('methods', ['GET']))} {e.get('path','')}" for e in eps[:8]
        )
        lines.append(f"  - {mod}: {paths}")

    # 数据表
    tables = map_data.get("tables") or []
    lines.append(f"\n■ 数据表（共 {len(tables)} 张，展示前 {max_tables}）：")
    lines.append("  " + ", ".join(tables[:max_tables]))

    # 工具
    tools = map_data.get("tools") or []
    lines.append(f"\n■ Agent 可调用工具（共 {len(tools)} 个，展示前 {max_tools}）：")
    for t in tools[:max_tools]:
        name = t.get("name", "")
        desc = (t.get("description", "") or "")[:60]
        lines.append(f"  - {name}: {desc}")

    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    m = get_project_map(force_refresh=True)
    print(json.dumps(m.get("summary", {}), ensure_ascii=False, indent=2))

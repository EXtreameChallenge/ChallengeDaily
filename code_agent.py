"""
code_agent.py — Code Agent 推理模式

用途：
    当用户问题涉及计算、数据处理、复杂逻辑（如"帮我算一下这三个月的平均专注时长"），
    让 LLM 生成一段 Python 代码，经过静态检查 + 受限命名空间沙箱执行后返回结果。

安全模型（三道闸门）：
    1. static_check_code()  —— 文本级黑名单扫描，禁止危险 import / 内建函数 / 文件操作
    2. 受限命名空间          —— __builtins__ 只暴露白名单，__import__ 只放行 SAFE_MODULES
    3. 进程级超时            —— multiprocessing.Process + Queue，5 秒不结束直接 terminate

注意：Windows 上 signal.alarm 不可用，且 threading 无法强制杀掉子线程，
     因此超时必须用多进程实现。Worker 函数必须定义在模块顶层以便 spawn pickle。
"""
from __future__ import annotations

import io
import logging
import multiprocessing as mp
import sys
from contextlib import redirect_stdout, redirect_stderr
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── 外部模块：try/except 降级 ──
try:
    import ai_client
except Exception as _e:  # pragma: no cover
    ai_client = None  # type: ignore
    logger.warning("code_agent: 无法导入 ai_client，代码生成将不可用: %s", _e)

try:
    import config
except Exception:  # pragma: no cover
    config = None  # type: ignore


# ── 白名单：允许的内建函数 / 模块 ─────────────────────────────
SAFE_BUILTINS = {
    # 容器 / 类型
    "len", "range", "sum", "max", "min", "sorted",
    "map", "filter", "enumerate", "zip",
    "dict", "list", "set", "tuple", "frozenset",
    "str", "int", "float", "bool", "complex",
    # 数学工具
    "abs", "round", "pow", "divmod", "repr",
    # 逻辑聚合
    "any", "all",
    # 可迭代 / 字符串
    "reversed", "slice", "iter", "next",
    # 输出（受 redirect_stdout 约束，不会真的写到终端）
    "print",
    # 异常基类（允许 try/except 捕获）
    "Exception", "ValueError", "TypeError", "KeyError",
    "IndexError", "ZeroDivisionError", "ArithmeticError",
    "StopIteration",
}

SAFE_MODULES = {
    "math", "datetime", "json", "re",
    "collections", "itertools", "statistics",
}

# 静态检查黑名单：命中即拒绝执行
_BANNED_IMPORTS = {
    "os", "sys", "subprocess", "socket", "shutil", "pathlib",
    "ctypes", "multiprocessing", "threading", "asyncio",
    "importlib", "pickle", "shelve", "dbm", "sqlite3",
}
_BANNED_CALLS = {
    "open", "eval", "exec", "compile", "__import__",
    "getattr", "setattr", "delattr", "globals", "locals",
    "vars", "dir", "input", "breakpoint", "help",
    "exit", "quit", "system", "popen",
}


# ── 任务识别 ───────────────────────────────────────────────────
_CODE_TASK_KEYWORDS = [
    "算", "计算", "统计", "平均", "求和", "总和", "百分比", "比例",
    "排序", "筛选", "过滤", "分组", "聚合", "转换", "换算",
    "函数", "公式", "代码", "python", "脚本", "编程",
    "calculate", "compute", "sum", "average", "ratio", "sort",
    "filter", "group", "transform", "code", "script",
]


def detect_code_task(user_message: str) -> bool:
    """粗略判断用户消息是否需要代码推理（计算/数据处理/复杂逻辑）。"""
    if not user_message:
        return False
    text = user_message.lower()
    hits = sum(1 for k in _CODE_TASK_KEYWORDS if k in text)
    # 至少命中 1 个关键词，且消息不算太短
    return hits >= 1 and len(user_message) >= 6


# ── LLM 生成代码 ─────────────────────────────────────────────
_GEN_PROMPT = """你是一个严谨的代码生成器。请根据任务描述，生成一段可独立运行的 Python 代码片段。

【任务】
{task}

【可用上下文变量】
{context}

【硬性要求】
1. 只能使用这些标准库模块：{modules}
2. 禁止 import os/sys/subprocess/socket/pathlib/shutil 等任何系统/网络/文件模块。
3. 禁止使用 open()、eval()、exec()、__import__()、getattr()。
4. 不要写 main 保护，不要写 if __name__ == "__main__"。
5. 把最终结果赋值给变量 `result`，并 print(result)。
6. 只输出 Python 代码，不要 markdown 代码块，不要解释，不要注释超过 3 行。
"""


def generate_code(task_description: str, context: dict | None = None) -> str:
    """让 LLM 生成一段 Python 代码片段。失败返回空串。"""
    if ai_client is None or config is None:
        logger.info("code_agent: ai_client/config 不可用，无法生成代码")
        return ""
    if not getattr(config, "AI_API_KEY", ""):
        return ""

    try:
        params = config.AI_PARAMS.get("agent", {"max_tokens": 800, "temperature": 0.3})
        prompt = _GEN_PROMPT.format(
            task=task_description[:1500],
            context=json_safe_dumps(context or {})[:800],
            modules=", ".join(sorted(SAFE_MODULES)),
        )
        client = ai_client._get_client()
        resp = client.chat.completions.create(
            model=config.AI_TEXT_MODEL,
            messages=[
                {"role": "system", "content": "你只输出可执行的 Python 代码，不输出任何解释。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=params.get("max_tokens", 800),
            temperature=0.2,  # 代码生成要低温稳定
        )
        raw = (resp.choices[0].message.content or "").strip()
        return _extract_code(raw)
    except Exception as e:
        logger.warning("code_agent.generate_code 失败: %s", e)
        return ""


def json_safe_dumps(obj: Any) -> str:
    """安全的 JSON 序列化（失败退化为 str）。"""
    import json as _json
    try:
        return _json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return str(obj)


def _extract_code(raw: str) -> str:
    """从 LLM 返回中提取纯代码：去掉 ```python ... ``` 包裹。"""
    import re
    m = re.search(r"```(?:python|py)?\s*(.*?)```", raw, re.DOTALL)
    if m:
        return m.group(1).strip()
    return raw.strip()


# ── 静态检查 ─────────────────────────────────────────────────
def static_check_code(code: str) -> list[str]:
    """静态扫描代码，返回风险点列表。空列表表示通过。"""
    issues: list[str] = []
    if not code:
        return ["代码为空"]

    # 1) 禁止危险 import
    import re
    # 匹配 import X / from X import ...
    for m in re.finditer(r"^\s*(?:from|import)\s+([\w\.]+)", code, re.MULTILINE):
        mod = m.group(1).split(".")[0]
        if mod in _BANNED_IMPORTS:
            issues.append(f"禁止导入模块: {mod}")

    # 2) 禁止危险内建调用
    for fn in _BANNED_CALLS:
        # 匹配标识符 fn 后面跟 (  或 .fn(
        pattern = r"(?<![\w.])" + re.escape(fn) + r"\s*\("
        if re.search(pattern, code):
            issues.append(f"禁止调用危险函数: {fn}()")

    # 3) 禁止 dunder 属性访问（除了少数安全的）
    for dunder in re.findall(r"__\w+__", code):
        if dunder not in {"__name__", "__doc__"}:
            issues.append(f"禁止访问 dunder 属性: {dunder}")

    # 4) 禁止文件/网络相关关键字
    for kw in ["open(", "file(", "urllib", "requests", "http", "socket",
               "open(", "write(", "read(", "input("]:
        if kw in code:
            issues.append(f"检测到可疑 I/O 关键字: {kw}")

    # 5) 长度保护，防止超长代码撑爆内存
    if len(code) > 8000:
        issues.append(f"代码过长({len(code)}字符)，拒绝执行")

    return issues


# ── 受限执行 ─────────────────────────────────────────────────
def _build_safe_builtins() -> dict:
    """构造受限 __builtins__：只暴露 SAFE_BUILTINS + 安全 __import__。"""
    import builtins as _b

    safe: dict = {}
    for name in SAFE_BUILTINS:
        fn = getattr(_b, name, None)
        if fn is not None:
            safe[name] = fn

    def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
        """只允许导入 SAFE_MODULES 白名单内的模块。"""
        root = (name or "").split(".")[0]
        if root not in SAFE_MODULES:
            raise ImportError(f"沙箱禁止导入模块: {name}")
        return __import__(name, globals, locals, fromlist, level)

    safe["__import__"] = _safe_import
    return safe


def _sandbox_worker(code: str, variables: dict, result_queue: "mp.Queue") -> None:
    """子进程入口：在受限命名空间执行 code，把结果送回队列。

    必须定义在模块顶层，Windows spawn 需要 pickle。
    """
    import json as _json
    stdout_buf = io.StringIO()
    result: dict = {"ok": False, "stdout": "", "result": None, "error": None}
    try:
        safe_builtins = _build_safe_builtins()
        namespace: dict = {
            "__builtins__": safe_builtins,
            "__name__": "sandbox",
        }
        # 注入外部传入的变量（必须是可 pickle 的简单类型）
        for k, v in (variables or {}).items():
            try:
                namespace[k] = v
            except Exception:
                pass

        with redirect_stdout(stdout_buf), redirect_stderr(stdout_buf):
            exec(compile(code, "<sandbox>", "exec"), namespace, namespace)  # noqa: S102

        result["stdout"] = stdout_buf.getvalue()[-2000:]  # 截断超长输出
        # 优先取 result 变量，其次打印内容
        if "result" in namespace:
            result["result"] = namespace["result"]
        result["ok"] = True
    except SystemExit:
        result["error"] = "代码调用了 exit()/quit()，已被拦截"
    except BaseException as e:  # noqa: BLE001
        result["error"] = f"{type(e).__name__}: {e}"
        result["stdout"] = stdout_buf.getvalue()[-1000:]
    finally:
        try:
            result_queue.put(result)
        except Exception:
            pass


def execute_code_safely(code: str, variables: dict | None = None,
                        timeout_sec: float = 5.0) -> dict:
    """在受限沙箱中执行代码。

    返回：{"ok": bool, "stdout": str, "result": Any, "error": str|None}
    """
    if not code or not code.strip():
        return {"ok": False, "stdout": "", "result": None, "error": "代码为空"}

    # 静态检查第一道
    issues = static_check_code(code)
    if issues:
        return {
            "ok": False, "stdout": "", "result": None,
            "error": "静态检查未通过: " + "; ".join(issues),
        }

    # Windows spawn 需要 freeze_support 保护；multiprocessing 用 spawn 最安全
    ctx = mp.get_context("spawn")
    q: mp.Queue = ctx.Queue()
    proc = ctx.Process(target=_sandbox_worker, args=(code, variables or {}, q),
                       daemon=True)
    proc.start()
    proc.join(timeout=timeout_sec)

    if proc.is_alive():
        # 超时：强制 terminate
        proc.terminate()
        proc.join(1.0)
        logger.warning("code_agent: 代码执行超时(>%ss)，已终止", timeout_sec)
        return {
            "ok": False, "stdout": "", "result": None,
            "error": f"代码执行超时({timeout_sec}s)，已强制终止",
        }

    exitcode = proc.exitcode
    try:
        result = q.get_nowait()
    except Exception:
        result = {"ok": False, "stdout": "", "result": None,
                  "error": f"子进程异常退出(exitcode={exitcode})，未返回结果"}

    # 结果做一次 JSON 安全处理，避免上层崩
    try:
        _ = json_safe_dumps(result.get("result"))
    except Exception:
        result["result"] = str(result.get("result"))
    return result


# ── 完整流程 ─────────────────────────────────────────────────
def run_code_agent(task_description: str, context: dict | None = None) -> dict:
    """完整流程：生成代码 → 静态检查 → 沙箱执行 → 返回结果。

    返回：{
        "ok": bool,
        "code": str,            # LLM 生成的代码（即使失败也返回，便于调试）
        "stdout": str,
        "result": Any,
        "error": str|None,
        "static_issues": list,  # 静态检查问题（若有）
    }
    """
    code = generate_code(task_description, context or {})
    if not code:
        return {
            "ok": False, "code": "", "stdout": "", "result": None,
            "error": "代码生成失败（AI 不可用或未配置）", "static_issues": [],
        }

    issues = static_check_code(code)
    if issues:
        return {
            "ok": False, "code": code, "stdout": "", "result": None,
            "error": "静态检查未通过", "static_issues": issues,
        }

    exec_result = execute_code_safely(code, context or {})
    return {
        "ok": exec_result.get("ok", False),
        "code": code,
        "stdout": exec_result.get("stdout", ""),
        "result": exec_result.get("result"),
        "error": exec_result.get("error"),
        "static_issues": [],
    }


if __name__ == "__main__":  # pragma: no cover
    # 简单自测：python code_agent.py
    mp.freeze_support()
    demo = run_code_agent("计算 1 到 100 的平方和", {})
    print(demo)

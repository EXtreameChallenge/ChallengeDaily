"""
P71-P79: AI 智能增强模块
- P71: 提示词工程优化(模板化+变量注入)
- P72: AI响应缓存(语义指纹)
- P73: 多级降级链(云端→本地→规则)
- P74: 多模型对比与自动选择
- P75: AI结果质量评分
- P76: 上下文窗口管理(滑动窗口)
- P77: 流式输出适配器
- P78: AI调用预算控制(每日token上限)
- P79: 智能问答推荐(基于历史)
"""
import logging
import threading
import time
import json
import hashlib
from datetime import datetime, timedelta
from collections import OrderedDict, defaultdict
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── P71: 提示词工程优化 ──────────────────────────
_PROMPT_TEMPLATES: dict[str, str] = {
    "activity_analysis": (
        "你是一个活动识别助手。根据截图识别用户当前活动。\n"
        "应用: {app_name}\n窗口标题: {window_title}\n"
        "请返回JSON: {{\"category\": \"<分类>\", \"activity\": \"<具体活动>\", "
        "\"productivity_score\": <0-100>, \"is_deep_work\": <true/false>}}\n"
        "分类必须从以下选择: {categories}"
    ),
    "daily_greeting": (
        "你是一个温暖的个人助理。基于用户今日数据生成问候语。\n"
        "今日数据: {daily_data}\n用户偏好: {user_prefs}\n"
        "要求: 活泼可爱温馨，不肉麻；使用文字堆砌风格；"
        "{time_constraint}"
    ),
    "weekly_summary": (
        "你是一个周报生成助手。基于用户本周活动数据生成周报摘要。\n"
        "本周数据: {week_data}\n趋势: {trends}\n"
        "请生成: 1) 本周亮点(3条) 2) 待改进项(2条) 3) 下周建议(2条)"
    ),
    "anomaly_explanation": (
        "你是数据分析师。解释以下异常现象的原因和建议。\n"
        "异常: {anomaly}\n上下文: {context}\n"
        "请用中文返回简短解释(50字内)和一条具体建议。"
    ),
}


def render_prompt(template_name: str, **kwargs) -> str:
    """渲染提示词模板"""
    tmpl = _PROMPT_TEMPLATES.get(template_name)
    if tmpl is None:
        raise ValueError(f"未知模板: {template_name}")
    try:
        return tmpl.format(**kwargs)
    except KeyError as e:
        logger.warning(f"模板 {template_name} 缺少变量: {e}")
        return tmpl


def register_prompt_template(name: str, template: str) -> None:
    """注册自定义提示词模板"""
    _PROMPT_TEMPLATES[name] = template


# ─── P72: AI 响应缓存 ──────────────────────────
_AI_CACHE_LOCK = threading.RLock()
_AI_CACHE: "OrderedDict[str, tuple[float, Any, int]]" = OrderedDict()
_AI_CACHE_MAX = 128
_AI_CACHE_TTL = 600  # 10 分钟


def _semantic_fingerprint(prompt: str, extra: str = "") -> str:
    """生成语义指纹(简单 hash，未来可换 embedding)"""
    raw = (prompt.strip() + "|" + extra).lower()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def ai_cache_get(prompt: str, extra: str = ""):
    with _AI_CACHE_LOCK:
        fp = _semantic_fingerprint(prompt, extra)
        item = _AI_CACHE.get(fp)
        if item is None:
            return None
        ts, value, hits = item
        if (time.time() - ts) > _AI_CACHE_TTL:
            _AI_CACHE.pop(fp, None)
            return None
        _AI_CACHE[fp] = (ts, value, hits + 1)
        _AI_CACHE.move_to_end(fp)
        return value


def ai_cache_set(prompt: str, value: Any, extra: str = "") -> None:
    with _AI_CACHE_LOCK:
        fp = _semantic_fingerprint(prompt, extra)
        _AI_CACHE[fp] = (time.time(), value, 1)
        _AI_CACHE.move_to_end(fp)
        while len(_AI_CACHE) > _AI_CACHE_MAX:
            _AI_CACHE.popitem(last=False)


def ai_cache_stats() -> dict:
    with _AI_CACHE_LOCK:
        total_hits = sum(h for _, _, h in _AI_CACHE.values())
        return {
            "size": len(_AI_CACHE),
            "max": _AI_CACHE_MAX,
            "total_hits": total_hits,
            "hit_rate_estimate": round(total_hits / max(len(_AI_CACHE) + total_hits, 1), 3)
        }


# ─── P73: 多级降级链 ──────────────────────────
class FallbackChain:
    """按顺序尝试多个 AI 调用方案，首个成功即返回"""

    def __init__(self, providers: list[Callable[[], Any]]):
        if not providers:
            raise ValueError("至少需要一个 provider")
        self._providers = providers

    def execute(self) -> dict:
        errors: list[str] = []
        for i, provider in enumerate(self._providers):
            try:
                result = provider()
                return {
                    "status": "ok",
                    "result": result,
                    "provider_index": i,
                    "errors": errors,
                }
            except Exception as e:
                errors.append(f"provider[{i}]: {type(e).__name__}: {e}")
                logger.info(f"P73 降级链 provider[{i}] 失败: {e}")
        return {"status": "error", "errors": errors, "result": None}


# ─── P74: 多模型对比与自动选择 ──────────────────────────
_MODEL_SCORES: dict[str, list[float]] = defaultdict(list)
_MODEL_SCORES_LOCK = threading.Lock()


def record_model_score(model: str, score: float) -> None:
    """记录模型响应质量分数(0-1)"""
    with _MODEL_SCORES_LOCK:
        scores = _MODEL_SCORES[model]
        scores.append(score)
        # 只保留最近 50 次
        if len(scores) > 50:
            del scores[: len(scores) - 50]


def get_best_model(candidates: list[str]) -> str:
    """根据历史质量分数选择最佳模型"""
    with _MODEL_SCORES_LOCK:
        best = candidates[0]
        best_avg = 0.5  # 默认中性分数
        for m in candidates:
            scores = _MODEL_SCORES.get(m, [])
            if len(scores) >= 3:
                avg = sum(scores) / len(scores)
                if avg > best_avg:
                    best_avg = avg
                    best = m
        return best


def get_model_ranking() -> list[dict]:
    """获取所有模型的排名"""
    with _MODEL_SCORES_LOCK:
        ranking = []
        for model, scores in _MODEL_SCORES.items():
            if scores:
                ranking.append({
                    "model": model,
                    "avg_score": round(sum(scores) / len(scores), 3),
                    "sample_count": len(scores),
                    "last_score": scores[-1],
                })
        ranking.sort(key=lambda x: x["avg_score"], reverse=True)
        return ranking


# ─── P75: AI 结果质量评分 ──────────────────────────
def score_ai_response(response: Any, expected_keys: list[str] | None = None) -> float:
    """对 AI 响应打分 0-1"""
    score = 0.0
    if response is None:
        return 0.0

    # 1. 非空检查
    if isinstance(response, str):
        if len(response.strip()) < 5:
            return 0.1
        score += 0.3
    elif isinstance(response, dict):
        if not response:
            return 0.1
        score += 0.3
        # 2. 期望键存在
        if expected_keys:
            present = sum(1 for k in expected_keys if k in response)
            score += 0.4 * (present / len(expected_keys))
        else:
            score += 0.2
    else:
        score += 0.2

    # 3. 长度合理性
    if isinstance(response, str):
        if 50 <= len(response) <= 2000:
            score += 0.2
        elif len(response) > 2000:
            score += 0.1
    elif isinstance(response, dict):
        score += 0.2

    # 4. 无明显错误标记
    if isinstance(response, dict) and response.get("error"):
        score -= 0.3

    return max(0.0, min(1.0, score))


# ─── P76: 上下文窗口管理 ──────────────────────────
class ContextWindow:
    """滑动窗口上下文管理器，控制传入 AI 的上下文长度"""

    def __init__(self, max_tokens: int = 4000, reserve_for_response: int = 1000):
        self.max_tokens = max_tokens
        self.reserve = reserve_for_response
        self._items: list[tuple[str, int]] = []  # (content, estimated_tokens)
        self._total_tokens = 0

    def add(self, content: str, priority: int = 5) -> None:
        """添加上下文项，priority 越高越重要"""
        tokens = self._estimate_tokens(content)
        self._items.append((content, tokens))
        self._total_tokens += tokens
        self._evict()

    def _evict(self) -> None:
        budget = self.max_tokens - self.reserve
        while self._total_tokens > budget and len(self._items) > 1:
            # 移除最旧项
            _, tokens = self._items.pop(0)
            self._total_tokens -= tokens

    def render(self) -> str:
        return "\n\n".join(item[0] for item in self._items)

    def _estimate_tokens(self, text: str) -> int:
        # 中文约 1 字 = 1.5 token，英文约 4 字符 = 1 token
        chinese = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        english = len(text) - chinese
        return int(chinese * 1.5 + english / 4) + 1

    def stats(self) -> dict:
        return {
            "items": len(self._items),
            "total_tokens": self._total_tokens,
            "budget": self.max_tokens - self.reserve,
            "utilization": round(self._total_tokens / max(self.max_tokens - self.reserve, 1), 3)
        }


# ─── P77: 流式输出适配器 ──────────────────────────
class StreamCollector:
    """收集流式 AI 响应，提供回调"""

    def __init__(self):
        self._chunks: list[str] = []
        self._callbacks: list[Callable[[str], None]] = []
        self._done = False
        self._lock = threading.Lock()

    def on_chunk(self, cb: Callable[[str], None]) -> None:
        self._callbacks.append(cb)

    def feed(self, chunk: str) -> None:
        with self._lock:
            self._chunks.append(chunk)
        for cb in self._callbacks:
            try:
                cb(chunk)
            except Exception as e:
                logger.debug(f"流式回调失败: {e}")

    def finish(self) -> None:
        with self._lock:
            self._done = True

    @property
    def full_text(self) -> str:
        with self._lock:
            return "".join(self._chunks)

    @property
    def is_done(self) -> bool:
        return self._done


# ─── P78: AI 调用预算控制 ──────────────────────────
_BUDGET_LOCK = threading.Lock()
_DAILY_TOKEN_BUDGET = 200000  # 默认每日 20 万 token
_token_usage: dict[str, int] = defaultdict(int)  # date_str -> tokens


def check_budget(tokens_needed: int = 1000) -> dict:
    """检查今日是否还有 AI 预算"""
    today = datetime.now().strftime("%Y-%m-%d")
    with _BUDGET_LOCK:
        used = _token_usage[today]
        remaining = _DAILY_TOKEN_BUDGET - used
        return {
            "has_budget": remaining >= tokens_needed,
            "used": used,
            "budget": _DAILY_TOKEN_BUDGET,
            "remaining": remaining,
            "date": today,
            "utilization": round(used / _DAILY_TOKEN_BUDGET, 3)
        }


def record_token_usage(tokens: int) -> None:
    """记录 token 消耗"""
    today = datetime.now().strftime("%Y-%m-%d")
    with _BUDGET_LOCK:
        _token_usage[today] += tokens


def set_daily_budget(budget: int) -> None:
    """设置每日预算"""
    global _DAILY_TOKEN_BUDGET
    with _BUDGET_LOCK:
        _DAILY_TOKEN_BUDGET = budget


def get_usage_history(days: int = 7) -> list[dict]:
    """获取最近 N 天的用量"""
    result = []
    for i in range(days):
        d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        with _BUDGET_LOCK:
            used = _token_usage.get(d, 0)
        result.append({"date": d, "used": used, "budget": _DAILY_TOKEN_BUDGET})
    return result


# ─── P79: 智能问答推荐 ──────────────────────────
_QA_HISTORY: list[dict] = []
_QA_HISTORY_LOCK = threading.Lock()
_QA_HISTORY_MAX = 100


def record_qa(question: str, answer: str, feedback: int = 0) -> None:
    """记录问答历史，feedback: 1=赞 -1=踩 0=未评价"""
    with _QA_HISTORY_LOCK:
        _QA_HISTORY.append({
            "question": question,
            "answer": answer,
            "feedback": feedback,
            "timestamp": time.time()
        })
        if len(_QA_HISTORY) > _QA_HISTORY_MAX:
            del _QA_HISTORY[: len(_QA_HISTORY) - _QA_HISTORY_MAX]


def recommend_questions(current_context: str = "", limit: int = 5) -> list[str]:
    """基于历史和上下文推荐问题"""
    with _QA_HISTORY_LOCK:
        # 1. 优先推荐用户赞过的问题
        liked = [q["question"] for q in _QA_HISTORY if q["feedback"] > 0]
        # 2. 最近问过的相关问题
        recent = [q["question"] for q in _QA_HISTORY[-10:]]

    # 简单去重
    seen = set()
    result = []
    for q in liked + recent:
        if q not in seen:
            seen.add(q)
            result.append(q)
            if len(result) >= limit:
                break

    # 3. 兜底：默认推荐问题
    defaults = [
        "今天我的专注情况如何？",
        "哪个时间段效率最高？",
        "本周相比上周有进步吗？",
        "建议我接下来做什么？",
        "我的注意力分散主要来自哪里？",
    ]
    for q in defaults:
        if q not in seen:
            result.append(q)
            if len(result) >= limit:
                break

    return result[:limit]

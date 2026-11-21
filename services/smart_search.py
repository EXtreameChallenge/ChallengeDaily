"""
P231-P239: 智能搜索引擎
- P231: 倒排索引
- P232: 分词器
- P233: TF-IDF 排序
- P234: 模糊搜索
- P235: 搜索建议
- P236: 搜索高亮
- P237: 分面搜索
- P238: 搜索缓存
- P239: 搜索分析
"""
import logging
import threading
import re
import math
from collections import defaultdict, Counter, deque
from datetime import datetime
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── P232: 分词器 ──────────────────────────
class Tokenizer:
    """文本分词器"""
    @staticmethod
    def tokenize(text: str) -> list[str]:
        text = text.lower().strip()
        # 英文: 按非字母数字分割
        tokens = re.findall(r'[a-z0-9\u4e00-\u9fff]+', text)
        return tokens

    @staticmethod
    def ngrams(text: str, n: int = 2) -> list[str]:
        tokens = Tokenizer.tokenize(text)
        ngrams = []
        for token in tokens:
            if len(token) >= n:
                for i in range(len(token) - n + 1):
                    ngrams.append(token[i:i+n])
        return ngrams


# ─── P231: 倒排索引 ──────────────────────────
class InvertedIndex:
    """倒排索引"""
    def __init__(self):
        self._index: dict[str, dict[str, int]] = defaultdict(dict)  # token -> {doc_id: freq}
        self._documents: dict[str, dict] = {}  # doc_id -> {content, metadata}
        self._doc_count = 0
        self._lock = threading.Lock()

    def add_document(self, doc_id: str, content: str, metadata: dict = None) -> None:
        tokens = Tokenizer.tokenize(content)
        token_freq = Counter(tokens)
        with self._lock:
            self._documents[doc_id] = {
                "content": content, "metadata": metadata or {},
                "token_count": len(tokens), "added_at": datetime.now().isoformat()
            }
            self._doc_count = len(self._documents)
            for token, freq in token_freq.items():
                self._index[token][doc_id] = freq

    def remove_document(self, doc_id: str) -> None:
        with self._lock:
            self._documents.pop(doc_id, None)
            self._doc_count = len(self._documents)
            for token in list(self._index.keys()):
                self._index[token].pop(doc_id, None)
                if not self._index[token]:
                    del self._index[token]

    def search(self, query: str) -> list[dict]:
        tokens = Tokenizer.tokenize(query)
        if not tokens:
            return []
        with self._lock:
            doc_scores = defaultdict(float)
            for token in tokens:
                postings = self._index.get(token, {})
                if not postings:
                    continue
                idf = math.log(max(1, self._doc_count) / max(1, len(postings)))
                for doc_id, freq in postings.items():
                    doc = self._documents.get(doc_id, {})
                    tf = freq / max(1, doc.get("token_count", 1))
                    doc_scores[doc_id] += tf * idf
        results = []
        for doc_id, score in sorted(doc_scores.items(), key=lambda x: x[1], reverse=True):
            doc = self._documents.get(doc_id, {})
            results.append({
                "doc_id": doc_id, "score": round(score, 4),
                "content": doc.get("content", "")[:200],
                "metadata": doc.get("metadata", {})
            })
        return results

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "documents": self._doc_count,
                "unique_tokens": len(self._index),
                "total_postings": sum(len(v) for v in self._index.values())
            }


# ─── P234: 模糊搜索 ──────────────────────────
class FuzzySearch:
    """模糊搜索(编辑距离)"""
    @staticmethod
    def levenshtein(s1: str, s2: str) -> int:
        if len(s1) < len(s2):
            return FuzzySearch.levenshtein(s2, s1)
        if len(s2) == 0:
            return len(s1)
        prev_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            curr_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = prev_row[j + 1] + 1
                deletions = curr_row[j] + 1
                substitutions = prev_row[j] + (c1 != c2)
                curr_row.append(min(insertions, deletions, substitutions))
            prev_row = curr_row
        return prev_row[-1]

    @staticmethod
    def search(query: str, candidates: list[str],
               max_distance: int = 2, limit: int = 10) -> list[dict]:
        results = []
        for candidate in candidates:
            dist = FuzzySearch.levenshtein(query.lower(), candidate.lower())
            if dist <= max_distance:
                similarity = 1 - dist / max(1, len(query))
                results.append({"text": candidate, "distance": dist,
                                "similarity": round(similarity, 3)})
        results.sort(key=lambda x: x["distance"])
        return results[:limit]


# ─── P235: 搜索建议 ──────────────────────────
class SearchSuggester:
    """搜索建议"""
    def __init__(self):
        self._suggestions: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def record(self, query: str) -> None:
        query = query.strip().lower()
        if query:
            with self._lock:
                self._suggestions[query] += 1

    def suggest(self, prefix: str, limit: int = 10) -> list[dict]:
        prefix = prefix.strip().lower()
        with self._lock:
            matches = [(q, c) for q, c in self._suggestions.items() if q.startswith(prefix)]
        matches.sort(key=lambda x: x[1], reverse=True)
        return [{"suggestion": q, "frequency": c} for q, c in matches[:limit]]

    def get_popular(self, limit: int = 10) -> list[dict]:
        with self._lock:
            sorted_sugg = sorted(self._suggestions.items(), key=lambda x: x[1], reverse=True)
        return [{"suggestion": q, "frequency": c} for q, c in sorted_sugg[:limit]]


# ─── P236: 搜索高亮 ──────────────────────────
class SearchHighlighter:
    """搜索结果高亮"""
    @staticmethod
    def highlight(text: str, query: str, tag: str = "mark") -> str:
        tokens = Tokenizer.tokenize(query)
        result = text
        for token in tokens:
            pattern = re.compile(re.escape(token), re.IGNORECASE)
            result = pattern.sub(f'<{tag}>{token}</{tag}>', result)
        return result

    @staticmethod
    def snippet(text: str, query: str, context: int = 50) -> str:
        tokens = Tokenizer.tokenize(query)
        lower_text = text.lower()
        positions = []
        for token in tokens:
            idx = lower_text.find(token.lower())
            if idx >= 0:
                positions.append(idx)
        if not positions:
            return text[:context * 2]
        pos = min(positions)
        start = max(0, pos - context)
        end = min(len(text), pos + context * 2)
        snippet_text = text[start:end]
        if start > 0:
            snippet_text = "..." + snippet_text
        if end < len(text):
            snippet_text = snippet_text + "..."
        return SearchHighlighter.highlight(snippet_text, query)


# ─── P237: 分面搜索 ──────────────────────────
class FacetedSearch:
    """分面搜索"""
    def __init__(self):
        self._facets: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

    def index(self, doc_id: str, facets: dict[str, str]) -> None:
        for facet_name, facet_value in facets.items():
            self._facets[facet_name][facet_value].append(doc_id)

    def get_facets(self, doc_ids: list[str] = None) -> dict:
        result = {}
        for facet_name, values in self._facets.items():
            result[facet_name] = {}
            for value, ids in values.items():
                if doc_ids:
                    filtered = [d for d in ids if d in doc_ids]
                    if filtered:
                        result[facet_name][value] = len(filtered)
                else:
                    result[facet_name][value] = len(ids)
        return result


# ─── P238: 搜索缓存 ──────────────────────────
class SearchCache:
    """搜索结果缓存"""
    def __init__(self, max_size: int = 500):
        self._cache: dict[str, dict] = {}
        self._access_order: deque = deque(maxlen=max_size)
        self._max_size = max_size
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, query: str) -> list[dict] | None:
        key = query.strip().lower()
        with self._lock:
            if key in self._cache:
                self._hits += 1
                self._cache[key]["last_access"] = datetime.now().isoformat()
                return self._cache[key]["results"]
            self._misses += 1
            return None

    def set(self, query: str, results: list[dict]) -> None:
        key = query.strip().lower()
        with self._lock:
            if len(self._cache) >= self._max_size and key not in self._cache:
                oldest = self._access_order.popleft()
                self._cache.pop(oldest, None)
            self._cache[key] = {"results": results, "cached_at": datetime.now().isoformat()}
            self._access_order.append(key)

    def stats(self) -> dict:
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._cache), "max_size": self._max_size,
                "hits": self._hits, "misses": self._misses,
                "hit_rate": round(self._hits / total, 3) if total else 0
            }


# ─── P239: 搜索分析 ──────────────────────────
class SearchAnalytics:
    """搜索行为分析"""
    def __init__(self):
        self._events: deque = deque(maxlen=5000)
        self._lock = threading.Lock()

    def track(self, query: str, results_count: int,
              clicked: bool = False, latency_ms: float = 0) -> None:
        with self._lock:
            self._events.append({
                "query": query, "results_count": results_count,
                "clicked": clicked, "latency_ms": latency_ms,
                "timestamp": datetime.now().isoformat()
            })

    def stats(self) -> dict:
        with self._lock:
            events = list(self._events)
        if not events:
            return {"total_searches": 0}
        total = len(events)
        clicked = sum(1 for e in events if e["clicked"])
        no_results = sum(1 for e in events if e["results_count"] == 0)
        avg_latency = sum(e["latency_ms"] for e in events) / total
        query_counts = Counter(e["query"] for e in events)
        return {
            "total_searches": total,
            "click_through_rate": round(clicked / total, 3),
            "zero_results_rate": round(no_results / total, 3),
            "avg_latency_ms": round(avg_latency, 2),
            "top_queries": query_counts.most_common(10)
        }


_index = InvertedIndex()
_fuzzy = FuzzySearch()
_suggester = SearchSuggester()
_highlighter = SearchHighlighter()
_faceted = FacetedSearch()
_cache = SearchCache()
_analytics = SearchAnalytics()

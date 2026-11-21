"""
P321-P330: 自然语言处理(NLP)系统
- P321: 分词器(中英文)
- P322: 词性标注
- P323: 命名实体识别(NER)
- P324: 情感分析
- P325: 关键词提取(TF-IDF)
- P326: 文本摘要
- P327: 文本分类
- P328: 语言检测
- P329: 拼写检查
- P330: 文本相似度
"""
from __future__ import annotations

import logging
import math
import re
import threading
from collections import Counter, deque
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── P321: 分词器 ──────────────────────────
class Tokenizer:
    """中英文分词器"""

    CN_CHARS = r"\u4e00-\u9fff"
    EN_WORD = r"[a-zA-Z]+"
    NUMBERS = r"\d+\.?\d*"
    PUNCT = r"[，。！？；：、""''（）【】《》,\.!?;:\"'()\[\]<>]"

    @classmethod
    def tokenize(cls, text: str) -> list[str]:
        tokens = []
        i = 0
        while i < len(text):
            ch = text[i]
            if re.match(f"[{cls.CN_CHARS}]", ch):
                # 中文单字
                tokens.append(ch)
                i += 1
            elif re.match(r"[a-zA-Z]", ch):
                # 英文单词
                m = re.match(cls.EN_WORD, text[i:])
                if m:
                    tokens.append(m.group().lower())
                    i += len(m.group())
                else:
                    i += 1
            elif re.match(r"\d", ch):
                m = re.match(cls.NUMBERS, text[i:])
                if m:
                    tokens.append(m.group())
                    i += len(m.group())
                else:
                    i += 1
            elif re.match(r"\s", ch):
                i += 1
            else:
                # 标点符号
                tokens.append(ch)
                i += 1
        return tokens

    @classmethod
    def tokenize_bigram(cls, text: str) -> list[str]:
        """中文二元分词"""
        tokens = cls.tokenize(text)
        bigrams = []
        for i in range(len(tokens) - 1):
            if re.match(f"[{cls.CN_CHARS}]", tokens[i]) and re.match(f"[{cls.CN_CHARS}]", tokens[i+1]):
                bigrams.append(tokens[i] + tokens[i+1])
        return bigrams


# ─── P322: 词性标注 ──────────────────────────
class POSTagger:
    """简易词性标注器(基于词典)"""

    POS_DICT = {
        "我": "pron", "你": "pron", "他": "pron", "她": "pron", "它": "pron",
        "是": "verb", "有": "verb", "做": "verb", "看": "verb", "学": "verb",
        "的": "part", "了": "part", "在": "prep", "和": "conj",
        "很": "adv", "也": "adv", "都": "adv", "不": "adv", "就": "adv",
        "时间": "noun", "学习": "noun", "工作": "noun", "效率": "noun",
        "good": "adj", "great": "adj", "happy": "adj",
        "the": "det", "a": "det", "an": "det",
        "is": "verb", "are": "verb", "was": "verb", "were": "verb",
        "quickly": "adv", "very": "adv",
    }

    @classmethod
    def tag(cls, tokens: list[str]) -> list[dict]:
        result = []
        for token in tokens:
            pos = cls.POS_DICT.get(token.lower(), cls._guess_pos(token))
            result.append({"token": token, "pos": pos})
        return result

    @staticmethod
    def _guess_pos(token: str) -> str:
        if re.match(r"^\d+\.?\d*$", token):
            return "num"
        if re.match(r"^[a-zA-Z]+$", token):
            return "word"
        if re.match(r"^[\u4e00-\u9fff]+$", token):
            return "noun"
        return "punct"


# ─── P323: 命名实体识别 ──────────────────────────
class NERecognizer:
    """命名实体识别(基于规则)"""

    PATTERNS = {
        "date": r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?|\d{1,2}月\d{1,2}日",
        "time": r"\d{1,2}[:：]\d{2}|\d{1,2}[点时]\d{0,2}分?",
        "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "url": r"https?://[^\s]+",
        "phone": r"1[3-9]\d{9}",
        "number": r"\d+\.?\d*",
    }

    @classmethod
    def recognize(cls, text: str) -> list[dict]:
        entities = []
        for entity_type, pattern in cls.PATTERNS.items():
            for m in re.finditer(pattern, text):
                entities.append({
                    "text": m.group(),
                    "type": entity_type,
                    "start": m.start(),
                    "end": m.end(),
                })
        # 按位置排序
        entities.sort(key=lambda x: x["start"])
        return entities


# ─── P324: 情感分析 ──────────────────────────
class SentimentAnalyzer:
    """情感分析(基于词典)"""

    POSITIVE_WORDS = {
        "好", "棒", "优秀", "喜欢", "开心", "快乐", "满意", "成功", "完美",
        "高效", "进步", "提升", "享受", "美", "佳", "赞", "强",
        "good", "great", "excellent", "happy", "love", "perfect", "nice", "awesome",
    }
    NEGATIVE_WORDS = {
        "差", "糟", "坏", "讨厌", "难过", "失败", "糟糕", "低效", "烦", "累",
        "bad", "terrible", "hate", "awful", "sad", "fail", "poor", "wrong",
    }
    NEGATIONS = {"不", "没", "无", "非", "not", "no", "never"}

    @classmethod
    def analyze(cls, text: str) -> dict:
        tokens = Tokenizer.tokenize(text)
        pos_count = 0
        neg_count = 0
        negated = False
        for i, token in enumerate(tokens):
            if token in cls.NEGATIONS:
                negated = True
                continue
            if token in cls.POSITIVE_WORDS:
                if negated:
                    neg_count += 1
                else:
                    pos_count += 1
            elif token in cls.NEGATIVE_WORDS:
                if negated:
                    pos_count += 1
                else:
                    neg_count += 1
            negated = False
        total = pos_count + neg_count
        score = (pos_count - neg_count) / total if total > 0 else 0.0
        if score > 0.2:
            sentiment = "positive"
        elif score < -0.2:
            sentiment = "negative"
        else:
            sentiment = "neutral"
        return {
            "sentiment": sentiment,
            "score": round(score, 3),
            "positive_count": pos_count,
            "negative_count": neg_count,
        }


# ─── P325: 关键词提取 ──────────────────────────
class KeywordExtractor:
    """关键词提取(TF-IDF)"""

    STOPWORDS = {
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
        "the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to",
        "and", "or", "but", "of", "for", "with", "as", "by",
    }

    def __init__(self):
        self._doc_freq: Counter = Counter()
        self._doc_count: int = 0
        self._lock = threading.Lock()

    def add_document(self, doc_id: str, text: str) -> None:
        tokens = Tokenizer.tokenize(text)
        unique = set(t for t in tokens if t not in self.STOPWORDS and len(t) > 1)
        with self._lock:
            for t in unique:
                self._doc_freq[t] += 1
            self._doc_count += 1

    def extract(self, text: str, top_k: int = 10) -> list[dict]:
        tokens = Tokenizer.tokenize(text)
        filtered = [t for t in tokens if t not in self.STOPWORDS and len(t) > 1]
        if not filtered:
            return []
        tf = Counter(filtered)
        results = []
        with self._lock:
            doc_count = self._doc_count or 1
            for term, freq in tf.items():
                tf_val = freq / len(filtered)
                idf_val = math.log((doc_count + 1) / (self._doc_freq.get(term, 0) + 1)) + 1
                tfidf = tf_val * idf_val
                results.append({"term": term, "tf": freq, "tfidf": round(tfidf, 4)})
        results.sort(key=lambda x: x["tfidf"], reverse=True)
        return results[:top_k]


_keyword_extractor = KeywordExtractor()


# ─── P326: 文本摘要 ──────────────────────────
class Summarizer:
    """文本摘要(基于句子重要度)"""

    @staticmethod
    def summarize(text: str, max_sentences: int = 3) -> dict:
        sentences = re.split(r"[。！？.!?]+", text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
        if len(sentences) <= max_sentences:
            return {"summary": "。".join(sentences) + "。" if sentences else "",
                    "sentence_count": len(sentences)}

        # 计算每个句子的分数(基于词频)
        word_freq = Counter()
        for s in sentences:
            for w in Tokenizer.tokenize(s):
                if len(w) > 1:
                    word_freq[w] += 1
        # 归一化
        max_freq = max(word_freq.values()) if word_freq else 1
        for w in word_freq:
            word_freq[w] /= max_freq

        # 句子分数
        scored = []
        for i, s in enumerate(sentences):
            words = [w for w in Tokenizer.tokenize(s) if len(w) > 1]
            score = sum(word_freq.get(w, 0) for w in words) / max(len(words), 1)
            # 位置加权(开头更重要)
            position_bonus = 1.0 / (i + 1) * 0.2
            scored.append({"sentence": s, "score": score + position_bonus, "index": i})
        scored.sort(key=lambda x: x["score"], reverse=True)
        top = sorted(scored[:max_sentences], key=lambda x: x["index"])
        return {"summary": "。".join(s["sentence"] for s in top) + "。",
                "sentence_count": len(sentences),
                "selected": [s["index"] for s in top]}


# ─── P327: 文本分类 ──────────────────────────
class TextClassifier:
    """文本分类器(朴素贝叶斯)"""

    def __init__(self):
        self._categories: dict[str, Counter] = {}
        self._category_doc_count: Counter = Counter()
        self._total_docs: int = 0
        self._vocabulary: set[str] = set()
        self._lock = threading.Lock()

    def train(self, text: str, category: str) -> None:
        tokens = Tokenizer.tokenize(text)
        with self._lock:
            if category not in self._categories:
                self._categories[category] = Counter()
            self._categories[category].update(tokens)
            self._category_doc_count[category] += 1
            self._total_docs += 1
            self._vocabulary.update(tokens)

    def classify(self, text: str) -> dict:
        tokens = Tokenizer.tokenize(text)
        if not tokens or self._total_docs == 0:
            return {"category": "unknown", "scores": {}}
        scores = {}
        with self._lock:
            vocab_size = len(self._vocabulary) or 1
            for cat, word_counts in self._categories.items():
                log_prob = math.log(self._category_doc_count[cat] / self._total_docs)
                total_words = sum(word_counts.values())
                for token in tokens:
                    log_prob += math.log(
                        (word_counts.get(token, 0) + 1) / (total_words + vocab_size)
                    )
                scores[cat] = round(log_prob, 2)
        best_cat = max(scores, key=scores.get) if scores else "unknown"
        return {"category": best_cat, "scores": scores}


# ─── P328: 语言检测 ──────────────────────────
class LanguageDetector:
    """语言检测器"""

    PATTERNS = {
        "zh": r"[\u4e00-\u9fff]",
        "ja": r"[\u3040-\u309f\u30a0-\u30ff]",
        "ko": r"[\uac00-\ud7af]",
        "ru": r"[\u0400-\u04ff]",
        "ar": r"[\u0600-\u06ff]",
    }

    @classmethod
    def detect(cls, text: str) -> dict:
        scores = {}
        for lang, pattern in cls.PATTERNS.items():
            matches = len(re.findall(pattern, text))
            if matches > 0:
                scores[lang] = matches
        # 检查拉丁字母
        latin = len(re.findall(r"[a-zA-Z]", text))
        if latin > 0:
            scores["latin"] = latin
        if not scores:
            return {"language": "unknown", "scores": {}}
        total = sum(scores.values())
        normalized = {k: round(v / total, 3) for k, v in scores.items()}
        # 详细区分
        if "latin" in normalized and normalized["latin"] > 0.5:
            primary = "en"
        else:
            primary = max(scores, key=scores.get)
            if primary == "latin":
                primary = "en"
        return {"language": primary, "scores": normalized}


# ─── P329: 拼写检查 ──────────────────────────
class SpellChecker:
    """简易拼写检查器(编辑距离)"""

    DICTIONARY = {
        "the", "be", "to", "of", "and", "a", "in", "that", "have",
        "for", "not", "with", "he", "as", "you", "do", "at", "this",
        "but", "his", "by", "from", "they", "we", "say", "her", "she",
        "good", "great", "happy", "love", "perfect", "nice", "awesome",
        "hello", "world", "python", "code", "test", "work", "study",
    }

    @classmethod
    def check(cls, word: str) -> dict:
        word_lower = word.lower()
        if word_lower in cls.DICTIONARY:
            return {"word": word, "correct": True, "suggestions": []}
        # 查找相似词
        suggestions = []
        for d in cls.DICTIONARY:
            dist = cls._levenshtein(word_lower, d)
            if dist <= 2:
                suggestions.append({"word": d, "distance": dist})
        suggestions.sort(key=lambda x: x["distance"])
        return {"word": word, "correct": False, "suggestions": suggestions[:5]}

    @staticmethod
    def _levenshtein(a: str, b: str) -> int:
        m, n = len(a), len(b)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if a[i-1] == b[j-1]:
                    dp[i][j] = dp[i-1][j-1]
                else:
                    dp[i][j] = 1 + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])
        return dp[m][n]


# ─── P330: 文本相似度 ──────────────────────────
class TextSimilarity:
    """文本相似度计算"""

    @staticmethod
    def jaccard_similarity(text1: str, text2: str) -> float:
        set1 = set(Tokenizer.tokenize(text1))
        set2 = set(Tokenizer.tokenize(text2))
        if not set1 and not set2:
            return 1.0
        intersection = set1 & set2
        union = set1 | set2
        return len(intersection) / len(union) if union else 0.0

    @staticmethod
    def cosine_similarity(text1: str, text2: str) -> float:
        tokens1 = Tokenizer.tokenize(text1)
        tokens2 = Tokenizer.tokenize(text2)
        if not tokens1 or not tokens2:
            return 0.0
        freq1 = Counter(tokens1)
        freq2 = Counter(tokens2)
        all_words = set(freq1.keys()) | set(freq2.keys())
        dot = sum(freq1.get(w, 0) * freq2.get(w, 0) for w in all_words)
        mag1 = math.sqrt(sum(v ** 2 for v in freq1.values()))
        mag2 = math.sqrt(sum(v ** 2 for v in freq2.values()))
        return dot / (mag1 * mag2) if mag1 * mag2 > 0 else 0.0

    @staticmethod
    def levenshtein_ratio(text1: str, text2: str) -> float:
        m, n = len(text1), len(text2)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if text1[i-1] == text2[j-1]:
                    dp[i][j] = dp[i-1][j-1]
                else:
                    dp[i][j] = 1 + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])
        dist = dp[m][n]
        return 1 - dist / max(m, n) if max(m, n) > 0 else 1.0


_similarity = TextSimilarity()

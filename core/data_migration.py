"""
P281-P300: 数据迁移 + 国际化(i18n)
- P281: 数据库迁移版本管理
- P282: 迁移执行器(正向/回滚)
- P283: 迁移事务保护
- P284: 迁移依赖图
- P285: 数据种子填充
- P286: 多语言翻译管理
- P287: 语言环境检测
- P288: 复数规则引擎
- P289: 翻译回退链
- P290: RTL(从右到左)布局支持
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── P281: 数据库迁移版本管理 ──────────────────────────
@dataclass
class Migration:
    """单个迁移定义"""
    version: int
    name: str
    upgrade: Callable[[], None]
    downgrade: Optional[Callable[[], None]] = None
    dependencies: list[int] = field(default_factory=list)
    description: str = ""


class MigrationRegistry:
    """迁移注册中心"""

    def __init__(self):
        self._migrations: dict[int, Migration] = {}
        self._lock = threading.Lock()
        self._current_version: int = 0
        self._history: deque = deque(maxlen=200)

    def register(self, migration: Migration) -> None:
        with self._lock:
            if migration.version in self._migrations:
                raise ValueError(f"迁移版本 {migration.version} 已存在")
            self._migrations[migration.version] = migration

    def get_pending(self, target_version: int | None = None) -> list[Migration]:
        with self._lock:
            versions = sorted(self._migrations.keys())
            if target_version is None:
                target_version = max(versions) if versions else 0
            return [
                self._migrations[v] for v in versions
                if self._current_version < v <= target_version
            ]

    def set_current(self, version: int) -> None:
        with self._lock:
            self._current_version = version

    def get_current(self) -> int:
        with self._lock:
            return self._current_version

    def list_all(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "version": m.version,
                    "name": m.name,
                    "description": m.description,
                    "applied": m.version <= self._current_version,
                    "dependencies": m.dependencies,
                }
                for m in sorted(self._migrations.values(), key=lambda x: x.version)
            ]

    def record_history(self, version: int, direction: str, success: bool,
                       error: str = "") -> None:
        with self._lock:
            self._history.append({
                "version": version,
                "direction": direction,
                "success": success,
                "error": error,
                "timestamp": datetime.now().isoformat(),
            })

    def get_history(self, limit: int = 50) -> list[dict]:
        with self._lock:
            h = list(self._history)
        h.reverse()
        return h[:limit]


_migration_registry = MigrationRegistry()


# ─── P282: 迁移执行器 ──────────────────────────
class MigrationRunner:
    """迁移执行器(支持正向升级和回滚)"""

    def __init__(self, registry: MigrationRegistry):
        self._registry = registry
        self._lock = threading.Lock()

    def upgrade(self, target_version: int | None = None) -> dict:
        pending = self._registry.get_pending(target_version)
        if not pending:
            return {"status": "ok", "message": "无待执行迁移", "applied": []}

        applied = []
        for m in pending:
            try:
                m.upgrade()
                self._registry.set_current(m.version)
                self._registry.record_history(m.version, "upgrade", True)
                applied.append({"version": m.version, "name": m.name, "status": "ok"})
            except Exception as e:
                self._registry.record_history(m.version, "upgrade", False, str(e))
                return {
                    "status": "error",
                    "message": f"迁移 {m.version} 失败: {e}",
                    "applied": applied,
                    "failed_at": m.version,
                }
        return {"status": "ok", "applied": applied}

    def downgrade(self, target_version: int) -> dict:
        current = self._registry.get_current()
        if target_version >= current:
            return {"status": "ok", "message": "目标版本不小于当前版本", "applied": []}

        with self._lock:
            all_migrations = sorted(
                self._registry._migrations.values(),
                key=lambda x: x.version,
                reverse=True
            )
        to_rollback = [m for m in all_migrations if target_version < m.version <= current]

        applied = []
        for m in to_rollback:
            if m.downgrade is None:
                return {
                    "status": "error",
                    "message": f"迁移 {m.version} 不可回滚",
                    "applied": applied,
                }
            try:
                m.downgrade()
                self._registry.set_current(m.version - 1 if m.version > 1 else 0)
                self._registry.record_history(m.version, "downgrade", True)
                applied.append({"version": m.version, "name": m.name, "status": "ok"})
            except Exception as e:
                self._registry.record_history(m.version, "downgrade", False, str(e))
                return {
                    "status": "error",
                    "message": f"回滚 {m.version} 失败: {e}",
                    "applied": applied,
                }
        return {"status": "ok", "applied": applied}


_migration_runner = MigrationRunner(_migration_registry)


# ─── P283: 迁移事务保护 ──────────────────────────
class TransactionGuard:
    """事务保护包装器(模拟事务,失败自动回滚)"""

    def __init__(self):
        self._snapshots: dict[str, Any] = {}
        self._lock = threading.Lock()

    def snapshot(self, key: str, state: Any) -> None:
        with self._lock:
            self._snapshots[key] = json.dumps(state, default=str)

    def restore(self, key: str) -> Any | None:
        with self._lock:
            snap = self._snapshots.get(key)
            return json.loads(snap) if snap else None

    def run_protected(self, key: str, state: dict, operation: Callable[[dict], dict]) -> dict:
        self.snapshot(key, state)
        try:
            new_state = operation(state)
            return {"status": "ok", "state": new_state}
        except Exception as e:
            restored = self.restore(key)
            logger.warning("事务 %s 失败,已回滚: %s", key, e)
            return {"status": "error", "error": str(e), "restored_state": restored}

    def clear(self, key: str) -> None:
        with self._lock:
            self._snapshots.pop(key, None)


_tx_guard = TransactionGuard()


# ─── P284: 迁移依赖图 ──────────────────────────
class DependencyGraph:
    """迁移依赖图(拓扑排序)"""

    def __init__(self):
        self._graph: dict[int, list[int]] = defaultdict(list)
        self._in_degree: dict[int, int] = defaultdict(int)
        self._nodes: set[int] = set()
        self._lock = threading.Lock()

    def add_edge(self, src: int, dst: int) -> None:
        with self._lock:
            self._nodes.add(src)
            self._nodes.add(dst)
            self._graph[src].append(dst)
            self._in_degree[dst] += 1
            if src not in self._in_degree:
                self._in_degree[src] = 0

    def topological_sort(self) -> list[int]:
        with self._lock:
            in_deg = dict(self._in_degree)
            for n in self._nodes:
                if n not in in_deg:
                    in_deg[n] = 0
            queue = sorted([n for n in self._nodes if in_deg[n] == 0])
            result = []
            while queue:
                node = queue.pop(0)
                result.append(node)
                for neighbor in self._graph[node]:
                    in_deg[neighbor] -= 1
                    if in_deg[neighbor] == 0:
                        queue.append(neighbor)
                queue.sort()
            if len(result) != len(self._nodes):
                raise ValueError("依赖图中存在循环")
            return result

    def has_cycle(self) -> bool:
        try:
            self.topological_sort()
            return False
        except ValueError:
            return True


_dep_graph = DependencyGraph()


# ─── P285: 数据种子填充 ──────────────────────────
class DataSeeder:
    """数据种子填充器"""

    def __init__(self):
        self._seeders: dict[str, Callable] = {}
        self._executed: set[str] = set()
        self._lock = threading.Lock()

    def register(self, name: str, seeder: Callable[[], dict]) -> None:
        with self._lock:
            self._seeders[name] = seeder

    def run(self, name: str | None = None) -> dict:
        with self._lock:
            to_run = [name] if name else list(self._seeders.keys())
            results = {}
        for n in to_run:
            with self._lock:
                if n in self._executed:
                    results[n] = {"status": "skipped", "message": "已执行"}
                    continue
                fn = self._seeders.get(n)
            if not fn:
                results[n] = {"status": "error", "error": "未注册"}
                continue
            try:
                result = fn()
                with self._lock:
                    self._executed.add(n)
                results[n] = {"status": "ok", "result": result}
            except Exception as e:
                results[n] = {"status": "error", "error": str(e)}
        return results

    def list_seeders(self) -> list[dict]:
        with self._lock:
            return [
                {"name": n, "executed": n in self._executed}
                for n in self._seeders
            ]


_data_seeder = DataSeeder()


# ─── P286: 多语言翻译管理 ──────────────────────────
class TranslationManager:
    """多语言翻译管理"""

    def __init__(self, default_locale: str = "zh-CN"):
        self._translations: dict[str, dict[str, str]] = {}
        self._default_locale = default_locale
        self._lock = threading.Lock()

    def add_locale(self, locale: str, translations: dict[str, str]) -> None:
        with self._lock:
            if locale not in self._translations:
                self._translations[locale] = {}
            self._translations[locale].update(translations)

    def translate(self, key: str, locale: str | None = None, **kwargs) -> str:
        loc = locale or self._default_locale
        with self._lock:
            text = self._translations.get(loc, {}).get(key)
            if text is None:
                text = self._translations.get(self._default_locale, {}).get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError):
                return text
        return text

    def list_locales(self) -> list[dict]:
        with self._lock:
            return [
                {"locale": loc, "key_count": len(trans)}
                for loc, trans in self._translations.items()
            ]

    def get_missing_keys(self, source_locale: str, target_locale: str) -> list[str]:
        with self._lock:
            src = self._translations.get(source_locale, {})
            tgt = self._translations.get(target_locale, {})
            return [k for k in src if k not in tgt]


_translation_mgr = TranslationManager()


# ─── P287: 语言环境检测 ──────────────────────────
class LocaleDetector:
    """语言环境检测器"""

    SUPPORTED = ["zh-CN", "zh-TW", "en-US", "en-GB", "ja-JP", "ko-KR",
                 "fr-FR", "de-DE", "es-ES", "ru-RU", "ar-SA"]

    def __init__(self):
        self._user_prefs: dict[str, str] = {}
        self._lock = threading.Lock()

    def detect_from_header(self, accept_language: str) -> str:
        if not accept_language:
            return "zh-CN"
        prefs = []
        for part in accept_language.split(","):
            part = part.strip()
            if ";q=" in part:
                lang, q = part.split(";q=", 1)
                try:
                    prefs.append((lang.strip(), float(q)))
                except ValueError:
                    prefs.append((lang.strip(), 1.0))
            else:
                prefs.append((part, 1.0))
        prefs.sort(key=lambda x: x[1], reverse=True)
        for lang, _ in prefs:
            lang = lang.strip()
            if lang in self.SUPPORTED:
                return lang
            base = lang.split("-")[0]
            for sup in self.SUPPORTED:
                if sup.startswith(base):
                    return sup
        return "zh-CN"

    def set_user_pref(self, user_id: str, locale: str) -> None:
        with self._lock:
            self._user_prefs[user_id] = locale

    def get_user_pref(self, user_id: str) -> str | None:
        with self._lock:
            return self._user_prefs.get(user_id)

    def list_supported(self) -> list[str]:
        return list(self.SUPPORTED)


_locale_detector = LocaleDetector()


# ─── P288: 复数规则引擎 ──────────────────────────
class PluralRules:
    """复数规则引擎(CLDR风格)"""

    RULES = {
        "zh-CN": lambda n: "other",
        "zh-TW": lambda n: "other",
        "ja-JP": lambda n: "other",
        "ko-KR": lambda n: "other",
        "en-US": lambda n: "one" if n == 1 else "other",
        "en-GB": lambda n: "one" if n == 1 else "other",
        "fr-FR": lambda n: "one" if n in (0, 1) else "other",
        "de-DE": lambda n: "one" if n == 1 else "other",
        "es-ES": lambda n: "one" if n == 1 else "other",
        "ru-RU": lambda n: (
            "one" if n % 10 == 1 and n % 100 != 11
            else "few" if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14)
            else "many" if n % 10 == 0 or 5 <= n % 10 <= 9 or 11 <= n % 100 <= 14
            else "other"
        ),
        "ar-SA": lambda n: (
            "zero" if n == 0
            else "one" if n == 1
            else "two" if n == 2
            else "few" if 3 <= n % 100 <= 10
            else "many" if 11 <= n % 100 <= 99
            else "other"
        ),
    }

    @classmethod
    def get_category(cls, locale: str, count: int) -> str:
        rule = cls.RULES.get(locale, cls.RULES["en-US"])
        return rule(count)

    @classmethod
    def pluralize(cls, locale: str, count: int, forms: dict[str, str]) -> str:
        category = cls.get_category(locale, count)
        return forms.get(category, forms.get("other", ""))


# ─── P289: 翻译回退链 ──────────────────────────
class FallbackChain:
    """翻译回退链"""

    DEFAULT_CHAIN = {
        "zh-TW": ["zh-TW", "zh-CN"],
        "zh-HK": ["zh-HK", "zh-TW", "zh-CN"],
        "en-GB": ["en-GB", "en-US"],
        "en-AU": ["en-AU", "en-GB", "en-US"],
        "ja-JP": ["ja-JP", "en-US", "zh-CN"],
        "ko-KR": ["ko-KR", "en-US", "zh-CN"],
    }

    def __init__(self, translation_mgr: TranslationManager):
        self._mgr = translation_mgr
        self._chains: dict[str, list[str]] = dict(self.DEFAULT_CHAIN)

    def set_chain(self, locale: str, chain: list[str]) -> None:
        self._chains[locale] = chain

    def get_chain(self, locale: str) -> list[str]:
        if locale in self._chains:
            return self._chains[locale]
        base = locale.split("-")[0]
        if base != locale:
            return [locale, base, "zh-CN", "en-US"]
        return [locale, "zh-CN", "en-US"]

    def translate(self, key: str, locale: str) -> str:
        for loc in self.get_chain(locale):
            text = self._mgr.translate(key, loc)
            if text != key:
                return text
        return key


_fallback = FallbackChain(_translation_mgr)


# ─── P290: RTL布局支持 ──────────────────────────
class RTLSupport:
    """RTL(从右到左)布局支持"""

    RTL_LOCALES = {"ar-SA", "he-IL", "fa-IR", "ur-PK"}

    @classmethod
    def is_rtl(cls, locale: str) -> bool:
        return locale in cls.RTL_LOCALES

    @classmethod
    def get_direction(cls, locale: str) -> str:
        return "rtl" if cls.is_rtl(locale) else "ltr"

    @classmethod
    def flip_css(cls, css: str, locale: str) -> str:
        if not cls.is_rtl(locale):
            return css
        replacements = {
            "left": "right",
            "right": "left",
            "padding-left": "padding-right",
            "padding-right": "padding-left",
            "margin-left": "margin-right",
            "margin-right": "margin-left",
            "border-left": "border-right",
            "border-right": "border-left",
        }
        result = css
        for src, dst in replacements.items():
            result = re.sub(rf"\b{src}\b", f"__TMP_{dst}__", result)
        for src, dst in replacements.items():
            result = result.replace(f"__TMP_{src}__", dst)
        return result

    @classmethod
    def list_rtl_locales(cls) -> list[str]:
        return list(cls.RTL_LOCALES)

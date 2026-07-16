"""
P301-P310: 无障碍(Accessibility)系统
- P301: WCAG合规检查器
- P302: 屏幕阅读器优化(ARIA)
- P303: 键盘导航管理
- P304: 颜色对比度检查
- P305: 焦点管理器
- P306: 文本缩放支持
- P307: 动画减弱模式
- P308: 语音导航
- P309: 手势替代方案
- P310: 认知负荷评估
"""
from __future__ import annotations

import logging
import re
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── P301: WCAG合规检查器 ──────────────────────────
class WCAGChecker:
    """WCAG 2.1 AA 合规检查器"""

    RULES = {
        "img_alt": "所有img标签必须有alt属性",
        "button_text": "按钮必须有可访问文本",
        "label_association": "表单控件必须有关联label",
        "heading_order": "标题层级不能跳级",
        "lang_attr": "html标签必须有lang属性",
        "skip_link": "应提供跳过到主内容的链接",
        "focus_visible": "所有可交互元素必须有可见焦点",
        "color_contrast": "文本对比度至少4.5:1",
        "resize_text": "文本应支持200%缩放",
        "timeout_configurable": "超时应可配置或可延长",
    }

    def __init__(self):
        self._violations: deque = deque(maxlen=500)
        self._lock = threading.Lock()

    def check_html(self, html: str) -> dict:
        violations = []
        # img without alt
        for m in re.finditer(r"<img(?![^>]*\balt=)[^>]*>", html, re.IGNORECASE):
            violations.append({"rule": "img_alt", "element": m.group(0)[:80]})
        # button without text
        for m in re.finditer(r"<button[^>]*>\s*</button>", html, re.IGNORECASE):
            violations.append({"rule": "button_text", "element": m.group(0)[:80]})
        # heading order
        headings = re.findall(r"<h([1-6])", html, re.IGNORECASE)
        for i in range(1, len(headings)):
            if int(headings[i]) - int(headings[i-1]) > 1:
                violations.append({"rule": "heading_order",
                                   "detail": f"h{headings[i-1]} -> h{headings[i]}"})
        # lang attribute
        if not re.search(r"<html[^>]*\blang=", html, re.IGNORECASE):
            violations.append({"rule": "lang_attr", "detail": "html标签缺少lang属性"})
        with self._lock:
            for v in violations:
                self._violations.append(v)
        return {
            "total_violations": len(violations),
            "violations": violations[:50],
            "rules_count": len(self.RULES),
        }

    def list_rules(self) -> dict:
        return dict(self.RULES)

    def get_violations(self, limit: int = 50) -> list:
        with self._lock:
            v = list(self._violations)
        v.reverse()
        return v[:limit]


_wcag = WCAGChecker()


# ─── P302: ARIA标签管理 ──────────────────────────
class ARIAManager:
    """屏幕阅读器ARIA标签管理"""

    def __init__(self):
        self._labels: dict[str, dict] = {}
        self._lock = threading.Lock()

    def set_label(self, element_id: str, label: str,
                  role: str = "", describedby: str = "") -> None:
        with self._lock:
            self._labels[element_id] = {
                "aria-label": label,
                "role": role,
                "aria-describedby": describedby,
            }

    def get_label(self, element_id: str) -> dict | None:
        with self._lock:
            return self._labels.get(element_id)

    def generate_aria(self, element_id: str) -> str:
        label = self.get_label(element_id)
        if not label:
            return ""
        parts = []
        for k, v in label.items():
            if v:
                parts.append(f'{k}="{v}"')
        return " ".join(parts)

    def list_labels(self) -> list[dict]:
        with self._lock:
            return [{"element_id": k, **v} for k, v in self._labels.items()]


_aria = ARIAManager()


# ─── P303: 键盘导航管理 ──────────────────────────
class KeyboardNavigation:
    """键盘导航管理器"""

    def __init__(self):
        self._tab_order: list[str] = []
        self._shortcuts: dict[str, str] = {}
        self._lock = threading.Lock()

    def set_tab_order(self, element_ids: list[str]) -> None:
        with self._lock:
            self._tab_order = list(element_ids)

    def get_tab_order(self) -> list[str]:
        with self._lock:
            return list(self._tab_order)

    def register_shortcut(self, key_combo: str, action: str) -> None:
        with self._lock:
            self._shortcuts[key_combo] = action

    def get_shortcuts(self) -> dict:
        with self._lock:
            return dict(self._shortcuts)

    def next_focus(self, current_id: str) -> str | None:
        with self._lock:
            if current_id not in self._tab_order:
                return self._tab_order[0] if self._tab_order else None
            idx = self._tab_order.index(current_id)
            return self._tab_order[(idx + 1) % len(self._tab_order)] if self._tab_order else None


_keyboard_nav = KeyboardNavigation()


# ─── P304: 颜色对比度检查 ──────────────────────────
class ContrastChecker:
    """颜色对比度检查器(WCAG标准)"""

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
        hex_color = hex_color.lstrip("#")
        if len(hex_color) == 3:
            hex_color = "".join(c * 2 for c in hex_color)
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    @staticmethod
    def _relative_luminance(rgb: tuple[int, int, int]) -> float:
        def adjust(c: int) -> float:
            c = c / 255.0
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        r, g, b = rgb
        return 0.2126 * adjust(r) + 0.7152 * adjust(g) + 0.0722 * adjust(b)

    @classmethod
    def calculate_ratio(cls, fg: str, bg: str) -> float:
        fg_rgb = cls._hex_to_rgb(fg)
        bg_rgb = cls._hex_to_rgb(bg)
        l1 = cls._relative_luminance(fg_rgb)
        l2 = cls._relative_luminance(bg_rgb)
        lighter = max(l1, l2)
        darker = min(l1, l2)
        return (lighter + 0.05) / (darker + 0.05)

    @classmethod
    def check_compliance(cls, fg: str, bg: str, level: str = "AA") -> dict:
        ratio = cls.calculate_ratio(fg, bg)
        thresholds = {"A": 3.0, "AA": 4.5, "AAA": 7.0}
        min_ratio = thresholds.get(level, 4.5)
        return {
            "ratio": round(ratio, 2),
            "level": level,
            "passes": ratio >= min_ratio,
            "min_required": min_ratio,
        }


_contrast = ContrastChecker()


# ─── P305: 焦点管理器 ──────────────────────────
class FocusManager:
    """焦点管理器"""

    def __init__(self):
        self._focus_history: deque = deque(maxlen=100)
        self._focus_trap: dict[str, list[str]] = {}
        self._lock = threading.Lock()

    def push_focus(self, element_id: str) -> None:
        with self._lock:
            self._focus_history.append({
                "element_id": element_id,
                "timestamp": __import__("time").time(),
            })

    def pop_focus(self) -> str | None:
        with self._lock:
            if self._focus_history:
                return self._focus_history[-1].get("element_id")
            return None

    def set_focus_trap(self, container_id: str, element_ids: list[str]) -> None:
        with self._lock:
            self._focus_trap[container_id] = list(element_ids)

    def remove_focus_trap(self, container_id: str) -> None:
        with self._lock:
            self._focus_trap.pop(container_id, None)

    def get_focus_traps(self) -> dict:
        with self._lock:
            return dict(self._focus_trap)


_focus_mgr = FocusManager()


# ─── P306: 文本缩放支持 ──────────────────────────
class TextScaler:
    """文本缩放支持"""

    LEVELS = [0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0]

    def __init__(self):
        self._current_scale: float = 1.0
        self._user_prefs: dict[str, float] = {}
        self._lock = threading.Lock()

    def set_scale(self, scale: float) -> dict:
        with self._lock:
            if scale not in self.LEVELS:
                nearest = min(self.LEVELS, key=lambda x: abs(x - scale))
                scale = nearest
            self._current_scale = scale
            return {"scale": scale, "applied": True}

    def get_scale(self) -> float:
        with self._lock:
            return self._current_scale

    def increase(self) -> dict:
        with self._lock:
            idx = self.LEVELS.index(self._current_scale) if self._current_scale in self.LEVELS else 2
            if idx < len(self.LEVELS) - 1:
                self._current_scale = self.LEVELS[idx + 1]
            return {"scale": self._current_scale}

    def decrease(self) -> dict:
        with self._lock:
            idx = self.LEVELS.index(self._current_scale) if self._current_scale in self.LEVELS else 2
            if idx > 0:
                self._current_scale = self.LEVELS[idx - 1]
            return {"scale": self._current_scale}

    def list_levels(self) -> list[float]:
        return list(self.LEVELS)


_text_scaler = TextScaler()


# ─── P307: 动画减弱模式 ──────────────────────────
class AnimationReducer:
    """动画减弱模式(prefers-reduced-motion)"""

    def __init__(self):
        self._enabled: bool = False
        self._user_prefs: dict[str, bool] = {}
        self._lock = threading.Lock()

    def enable(self) -> None:
        with self._lock:
            self._enabled = True

    def disable(self) -> None:
        with self._lock:
            self._enabled = False

    def is_enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def filter_animations(self, animations: list[dict]) -> list[dict]:
        with self._lock:
            if not self._enabled:
                return animations
        # 减弱模式: 移除旋转/缩放,保留淡入淡出
        filtered = []
        for anim in animations:
            anim_type = anim.get("type", "")
            if anim_type in ("fade", "opacity"):
                filtered.append({**anim, "duration": min(anim.get("duration", 200), 150)})
            elif anim_type in ("slide",):
                filtered.append({**anim, "duration": min(anim.get("duration", 300), 100)})
            # 旋转/缩放/弹跳被移除
        return filtered

    def get_css_override(self) -> str:
        if not self.is_enabled():
            return ""
        return ("*, *::before, *::after { "
                "animation-duration: 0.01ms !important; "
                "animation-iteration-count: 1 !important; "
                "transition-duration: 0.01ms !important; }")


_anim_reducer = AnimationReducer()


# ─── P308: 语音导航 ──────────────────────────
class VoiceNavigator:
    """语音导航命令系统"""

    COMMANDS = {
        "go_home": ["回家", "go home", "主页"],
        "go_back": ["返回", "back", "上一页"],
        "go_forward": ["前进", "forward", "下一页"],
        "search": ["搜索", "search", "查找"],
        "scroll_down": ["向下", "scroll down", "下翻"],
        "scroll_up": ["向上", "scroll up", "上翻"],
        "click": ["点击", "click", "按下"],
        "read_page": ["朗读", "read page", "读页面"],
    }

    def __init__(self):
        self._enabled: bool = False
        self._history: deque = deque(maxlen=50)
        self._lock = threading.Lock()

    def enable(self) -> None:
        with self._lock:
            self._enabled = True

    def disable(self) -> None:
        with self._lock:
            self._enabled = False

    def parse_command(self, text: str) -> dict:
        text_lower = text.lower().strip()
        for action, triggers in self.COMMANDS.items():
            for trigger in triggers:
                if trigger in text_lower:
                    result = {"action": action, "raw_text": text, "matched": trigger}
                    with self._lock:
                        self._history.append(result)
                    return result
        return {"action": "unknown", "raw_text": text, "matched": None}

    def list_commands(self) -> dict:
        return dict(self.COMMANDS)

    def get_history(self, limit: int = 20) -> list:
        with self._lock:
            h = list(self._history)
        h.reverse()
        return h[:limit]


_voice_nav = VoiceNavigator()


# ─── P309: 手势替代方案 ──────────────────────────
class GestureAlternative:
    """手势替代方案(为无法使用触摸手势的用户提供替代)"""

    ALTERNATIVES = {
        "swipe_left": ["Alt+Left", "Shift+Tab"],
        "swipe_right": ["Alt+Right", "Tab"],
        "swipe_up": ["Page Up", "Ctrl+Up"],
        "swipe_down": ["Page Down", "Ctrl+Down"],
        "pinch_zoom": ["Ctrl++", "Ctrl+="],
        "pinch_out": ["Ctrl+-"],
        "long_press": ["Shift+Click", "F10"],
        "double_tap": ["Enter", "Space"],
        "two_finger_tap": ["Right Click", "Shift+F10"],
    }

    @classmethod
    def get_alternatives(cls, gesture: str) -> list[str]:
        return cls.ALTERNATIVES.get(gesture, [])

    @classmethod
    def list_gestures(cls) -> dict:
        return dict(cls.ALTERNATIVES)

    @classmethod
    def find_gesture_for_shortcut(cls, shortcut: str) -> list[str]:
        result = []
        for gesture, shortcuts in cls.ALTERNATIVES.items():
            if shortcut in shortcuts:
                result.append(gesture)
        return result


# ─── P310: 认知负荷评估 ──────────────────────────
class CognitiveLoadAssessor:
    """认知负荷评估器"""

    FACTORS = {
        "text_density": {"weight": 0.25, "max_score": 100},
        "visual_complexity": {"weight": 0.30, "max_score": 100},
        "interaction_depth": {"weight": 0.20, "max_score": 100},
        "information_hierarchy": {"weight": 0.15, "max_score": 100},
        "consistency": {"weight": 0.10, "max_score": 100},
    }

    def __init__(self):
        self._assessments: deque = deque(maxlen=100)
        self._lock = threading.Lock()

    def assess(self, factors: dict[str, float]) -> dict:
        total_load = 0.0
        details = {}
        for factor, score in factors.items():
            config = self.FACTORS.get(factor)
            if not config:
                continue
            clamped = max(0, min(score, config["max_score"]))
            weighted = clamped * config["weight"]
            total_load += weighted
            details[factor] = {"score": clamped, "weighted": weighted,
                               "weight": config["weight"]}
        level = ("low" if total_load < 30 else
                 "moderate" if total_load < 60 else
                 "high" if total_load < 80 else "very_high")
        result = {"total_load": round(total_load, 2), "level": level, "details": details}
        with self._lock:
            self._assessments.append(result)
        return result

    def list_factors(self) -> dict:
        return dict(self.FACTORS)

    def get_assessments(self, limit: int = 20) -> list:
        with self._lock:
            a = list(self._assessments)
        a.reverse()
        return a[:limit]


_cognitive = CognitiveLoadAssessor()

"""
P151-P159: 高级 UI/UX 与动效
- P151: 动画编排器
- P152: 过渡曲线库
- P153: 视觉层次系统
- P154: 响应式断点管理
- P155: 主题色生成器
- P156: 字体节奏
- P157: 间距系统
- P158: 阴影深度
- P159: 图标语义
"""
import logging
import colorsys
import hashlib
from typing import Any

logger = logging.getLogger(__name__)


# ─── P151: 动画编排器 ──────────────────────────
class AnimationOrchestrator:
    """编排多元素动画时序"""

    def __init__(self):
        self._sequences: list[dict] = []

    def add_step(self, element: str, property: str, from_val: Any,
                 to_val: Any, duration: int = 300, delay: int = 0,
                 easing: str = "ease-out") -> None:
        self._sequences.append({
            "element": element,
            "property": property,
            "from": from_val,
            "to": to_val,
            "duration": duration,
            "delay": delay,
            "easing": easing
        })

    def stagger(self, elements: list[str], property: str, from_val: Any,
                to_val: Any, duration: int = 300, stagger_delay: int = 50) -> dict:
        """错开动画"""
        for i, el in enumerate(elements):
            self.add_step(el, property, from_val, to_val,
                         duration=duration, delay=i * stagger_delay)
        return self.export()

    def sequence(self, steps: list[dict]) -> dict:
        """串行动画"""
        total_delay = 0
        for step in steps:
            self.add_step(
                step["element"], step["property"],
                step["from"], step["to"],
                duration=step.get("duration", 300),
                delay=total_delay,
                easing=step.get("easing", "ease-out")
            )
            total_delay += step.get("duration", 300)
        return self.export()

    def export(self) -> dict:
        return {
            "steps": list(self._sequences),
            "total_duration": max(
                (s["delay"] + s["duration"] for s in self._sequences),
                default=0
            )
        }

    def clear(self) -> None:
        self._sequences.clear()


# ─── P152: 过渡曲线库 ──────────────────────────
EASING_FUNCTIONS = {
    "linear": "linear",
    "ease": "ease",
    "ease-in": "cubic-bezier(0.42, 0, 1, 1)",
    "ease-out": "cubic-bezier(0, 0, 0.58, 1)",
    "ease-in-out": "cubic-bezier(0.42, 0, 0.58, 1)",
    "bounce": "cubic-bezier(0.68, -0.55, 0.265, 1.55)",
    "spring": "cubic-bezier(0.34, 1.56, 0.64, 1)",
    "sharp": "cubic-bezier(0.4, 0, 0.6, 1)",
    "standard": "cubic-bezier(0.4, 0, 0.2, 1)",
    "accelerate": "cubic-bezier(0.4, 0, 1, 1)",
    "decelerate": "cubic-bezier(0, 0, 0.2, 1)",
}


def get_easing(name: str) -> str:
    return EASING_FUNCTIONS.get(name, EASING_FUNCTIONS["ease-out"])


# ─── P153: 视觉层次系统 ──────────────────────────
VISUAL_HIERARCHY = {
    "display": {"fontSize": "3rem", "fontWeight": 700, "lineHeight": 1.2, "letterSpacing": "-0.02em"},
    "h1": {"fontSize": "2.5rem", "fontWeight": 700, "lineHeight": 1.3, "letterSpacing": "-0.01em"},
    "h2": {"fontSize": "2rem", "fontWeight": 600, "lineHeight": 1.35},
    "h3": {"fontSize": "1.5rem", "fontWeight": 600, "lineHeight": 1.4},
    "h4": {"fontSize": "1.25rem", "fontWeight": 600, "lineHeight": 1.45},
    "body": {"fontSize": "1rem", "fontWeight": 400, "lineHeight": 1.6},
    "body-small": {"fontSize": "0.875rem", "fontWeight": 400, "lineHeight": 1.5},
    "caption": {"fontSize": "0.75rem", "fontWeight": 400, "lineHeight": 1.4},
    "overline": {"fontSize": "0.6875rem", "fontWeight": 600, "letterSpacing": "0.08em", "textTransform": "uppercase"},
}


# ─── P154: 响应式断点 ──────────────────────────
BREAKPOINTS = {
    "xs": 0,      # mobile
    "sm": 640,    # large phone
    "md": 768,    # tablet
    "lg": 1024,   # laptop
    "xl": 1280,   # desktop
    "2xl": 1536,  # large desktop
}


def get_breakpoint(width: int) -> str:
    """根据宽度返回断点名"""
    for name in ["2xl", "xl", "lg", "md", "sm", "xs"]:
        if width >= BREAKPOINTS[name]:
            return name
    return "xs"


def responsive_grid(width: int) -> dict:
    """响应式网格配置"""
    bp = get_breakpoint(width)
    configs = {
        "xs": {"columns": 1, "gap": 12, "padding": 12},
        "sm": {"columns": 2, "gap": 12, "padding": 16},
        "md": {"columns": 2, "gap": 16, "padding": 20},
        "lg": {"columns": 3, "gap": 20, "padding": 24},
        "xl": {"columns": 4, "gap": 24, "padding": 28},
        "2xl": {"columns": 4, "gap": 24, "padding": 32},
    }
    return configs[bp]


# ─── P155: 主题色生成器 ──────────────────────────
def generate_palette(base_color: str) -> dict:
    """从基色生成完整调色板(50-900)"""
    # 解析 hex
    base = base_color.lstrip("#")
    if len(base) != 6:
        return {}
    r, g, b = int(base[0:2], 16), int(base[2:4], 16), int(base[4:6], 16)
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)

    palette = {}
    lightness_steps = {
        50: 0.95, 100: 0.90, 200: 0.80, 300: 0.70,
        400: 0.60, 500: 0.50, 600: 0.40, 700: 0.30,
        800: 0.20, 900: 0.10
    }
    for step, target_l in lightness_steps.items():
        # 调整饱和度
        adj_s = max(0, min(1, s * (1 - abs(target_l - 0.5) * 0.3)))
        nr, ng, nb = colorsys.hls_to_rgb(h, target_l, adj_s)
        palette[step] = f"#{int(nr * 255):02x}{int(ng * 255):02x}{int(nb * 255):02x}"
    return palette


def generate_complementary(base_color: str) -> list:
    """生成互补色"""
    base = base_color.lstrip("#")
    r, g, b = int(base[0:2], 16), int(base[2:4], 16), int(base[4:6], 16)
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    result = [base_color]
    # 互补色
    h2 = (h + 0.5) % 1.0
    nr, ng, nb = colorsys.hls_to_rgb(h2, l, s)
    result.append(f"#{int(nr * 255):02x}{int(ng * 255):02x}{int(nb * 255):02x}")
    # 三角色
    h3 = (h + 0.33) % 1.0
    nr, ng, nb = colorsys.hls_to_rgb(h3, l, s)
    result.append(f"#{int(nr * 255):02x}{int(ng * 255):02x}{int(nb * 255):02x}")
    h4 = (h + 0.67) % 1.0
    nr, ng, nb = colorsys.hls_to_rgb(h4, l, s)
    result.append(f"#{int(nr * 255):02x}{int(ng * 255):02x}{int(nb * 255):02x}")
    return result


# ─── P156: 字体节奏 ──────────────────────────
FONT_SCALE = {
    "base": 16,  # px
    "scale": 1.250,  # major third
    "unit": "rem"
}


def typography_scale(steps: int = 7) -> list:
    """生成字体节奏阶梯"""
    result = []
    for i in range(steps):
        size = FONT_SCALE["base"] * (FONT_SCALE["scale"] ** (i - 3))
        result.append({
            "step": i,
            "size_px": round(size, 1),
            "size_rem": round(size / 16, 4),
            "line_height": round(1.2 + (0.1 if i < 3 else 0), 2)
        })
    return result


# ─── P157: 间距系统 ──────────────────────────
SPACING = {
    "0": 0,
    "1": 4,
    "2": 8,
    "3": 12,
    "4": 16,
    "5": 20,
    "6": 24,
    "8": 32,
    "10": 40,
    "12": 48,
    "16": 64,
    "20": 80,
    "24": 96,
}


def get_spacing(key: str) -> int:
    return SPACING.get(key, 0)


# ─── P158: 阴影深度 ──────────────────────────
SHADOWS = {
    "none": "none",
    "sm": "0 1px 2px 0 rgba(0, 0, 0, 0.05)",
    "default": "0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06)",
    "md": "0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)",
    "lg": "0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)",
    "xl": "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)",
    "2xl": "0 25px 50px -12px rgba(0, 0, 0, 0.25)",
    "inner": "inset 0 2px 4px 0 rgba(0, 0, 0, 0.06)",
}


def get_shadow(level: str = "default") -> str:
    return SHADOWS.get(level, SHADOWS["default"])


# ─── P159: 图标语义 ──────────────────────────
ICON_SEMANTICS = {
    "add": {"icon": "➕", "label": "添加", "category": "action"},
    "edit": {"icon": "✏️", "label": "编辑", "category": "action"},
    "delete": {"icon": "🗑️", "label": "删除", "category": "action"},
    "save": {"icon": "💾", "label": "保存", "category": "action"},
    "cancel": {"icon": "❌", "label": "取消", "category": "action"},
    "confirm": {"icon": "✅", "label": "确认", "category": "action"},
    "search": {"icon": "🔍", "label": "搜索", "category": "navigation"},
    "filter": {"icon": "🎛️", "label": "筛选", "category": "navigation"},
    "sort": {"icon": "↕️", "label": "排序", "category": "navigation"},
    "refresh": {"icon": "🔄", "label": "刷新", "category": "action"},
    "export": {"icon": "📤", "label": "导出", "category": "action"},
    "import": {"icon": "📥", "label": "导入", "category": "action"},
    "settings": {"icon": "⚙️", "label": "设置", "category": "system"},
    "help": {"icon": "❓", "label": "帮助", "category": "system"},
    "info": {"icon": "ℹ️", "label": "信息", "category": "system"},
    "warning": {"icon": "⚠️", "label": "警告", "category": "feedback"},
    "error": {"icon": "🔴", "label": "错误", "category": "feedback"},
    "success": {"icon": "🟢", "label": "成功", "category": "feedback"},
    "loading": {"icon": "⏳", "label": "加载中", "category": "feedback"},
    "star": {"icon": "⭐", "label": "收藏", "category": "action"},
}


def get_icon_semantic(name: str) -> dict:
    return ICON_SEMANTICS.get(name, {"icon": "❓", "label": name, "category": "unknown"})


def get_icons_by_category(category: str) -> list:
    return [
        {"name": k, **v}
        for k, v in ICON_SEMANTICS.items()
        if v["category"] == category
    ]

"""
P181-P189: 数据可视化引擎
- P181: 图表类型注册表
- P182: 数据系列管理
- P183: 坐标轴配置
- P184: 颜色映射器
- P185: 动画过渡
- P186: 交互式 tooltip
- P187: 图例系统
- P188: 数据聚合器
- P189: 导出渲染器
"""
import logging
import threading
import math
from collections import OrderedDict, defaultdict
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── P181: 图表类型注册表 ──────────────────────────
class ChartRegistry:
    """图表类型注册与查找"""
    _chart_types: dict[str, dict] = {}
    _lock = threading.Lock()

    @classmethod
    def register(cls, chart_type: str, renderer: str,
                 required_fields: list[str] = None,
                 optional_fields: list[str] = None) -> None:
        with cls._lock:
            cls._chart_types[chart_type] = {
                "renderer": renderer,
                "required_fields": required_fields or [],
                "optional_fields": optional_fields or [],
            }

    @classmethod
    def get(cls, chart_type: str) -> dict | None:
        with cls._lock:
            return cls._chart_types.get(chart_type)

    @classmethod
    def list_types(cls) -> list[str]:
        with cls._lock:
            return list(cls._chart_types.keys())

    @classmethod
    def validate(cls, chart_type: str, data: dict) -> dict:
        spec = cls.get(chart_type)
        if not spec:
            return {"valid": False, "error": f"未知图表类型: {chart_type}"}
        missing = [f for f in spec["required_fields"] if f not in data]
        if missing:
            return {"valid": False, "error": f"缺少必需字段: {missing}"}
        return {"valid": True}


# 注册默认图表类型
ChartRegistry.register("line", "svg", ["series"], ["xAxis", "yAxis"])
ChartRegistry.register("bar", "svg", ["series", "categories"], ["yAxis"])
ChartRegistry.register("pie", "svg", ["series"], [])
ChartRegistry.register("scatter", "canvas", ["points"], [])
ChartRegistry.register("heatmap", "canvas", ["matrix"], ["rows", "cols"])
ChartRegistry.register("radar", "svg", ["series", "axes"], [])
ChartRegistry.register("treemap", "div", ["hierarchy"], [])
ChartRegistry.register("sankey", "svg", ["nodes", "links"], [])
ChartRegistry.register("gauge", "svg", ["value", "min", "max"], [])


# ─── P182: 数据系列管理 ──────────────────────────
class DataSeriesManager:
    """管理多系列数据"""
    def __init__(self):
        self._series: OrderedDict[str, dict] = OrderedDict()
        self._lock = threading.Lock()

    def add_series(self, name: str, data: list,
                   color: str = "", chart_type: str = "line") -> None:
        with self._lock:
            self._series[name] = {
                "name": name, "data": data,
                "color": color, "type": chart_type,
                "visible": True
            }

    def remove_series(self, name: str) -> bool:
        with self._lock:
            return self._series.pop(name, None) is not None

    def toggle_visibility(self, name: str) -> bool:
        with self._lock:
            s = self._series.get(name)
            if s:
                s["visible"] = not s["visible"]
                return s["visible"]
            return False

    def get_all(self) -> list:
        with self._lock:
            return list(self._series.values())

    def merge(self, name: str, new_data: list) -> None:
        with self._lock:
            if name in self._series:
                self._series[name]["data"].extend(new_data)

    def clear(self) -> None:
        with self._lock:
            self._series.clear()


_series_mgr = DataSeriesManager()


# ─── P183: 坐标轴配置 ──────────────────────────
class AxisConfig:
    """坐标轴配置器"""
    def __init__(self):
        self._axes: dict[str, dict] = {}

    def configure(self, axis_id: str, axis_type: str = "linear",
                  label: str = "", min_val: float = None,
                  max_val: float = None, ticks: int = 5,
                  format_str: str = "{}") -> None:
        self._axes[axis_id] = {
            "type": axis_type, "label": label,
            "min": min_val, "max": max_val,
            "ticks": ticks, "format": format_str
        }

    def get(self, axis_id: str) -> dict | None:
        return self._axes.get(axis_id)

    def auto_scale(self, axis_id: str, values: list[float]) -> dict:
        if not values:
            return {}
        vmin, vmax = min(values), max(values)
        padding = (vmax - vmin) * 0.1 if vmax > vmin else 1
        config = {
            "min": vmin - padding, "max": vmax + padding,
            "range": (vmax - vmin) + 2 * padding
        }
        self._axes[axis_id] = {**self._axes.get(axis_id, {}), **config}
        return config

    def generate_ticks(self, axis_id: str) -> list:
        ax = self._axes.get(axis_id)
        if not ax or ax.get("min") is None:
            return []
        vmin, vmax = ax["min"], ax["max"]
        n = ax.get("ticks", 5)
        if n <= 0 or vmax <= vmin:
            return [vmin]
        step = (vmax - vmin) / n
        return [vmin + step * i for i in range(n + 1)]


_axis_config = AxisConfig()


# ─── P184: 颜色映射器 ──────────────────────────
class ColorMapper:
    """数据→颜色映射"""
    _palettes = {
        "default": ["#5B8DEF", "#F0A030", "#00B894", "#E54D42", "#A29BFE",
                     "#FD79A8", "#00CEC9", "#6C5CE7", "#F0C040", "#55EFC4"],
        "warm": ["#FF6B6B", "#FFA94D", "#FFD43B", "#FAB005", "#E64980"],
        "cool": ["#4DABF7", "#3BC9DB", "#20C997", "#5C7CFA", "#7048E8"],
        "mono": ["#E0E0E0", "#BDBDBD", "#9E9E9E", "#757575", "#424242"],
        "diverging": ["#E54D42", "#FF8A65", "#FFCC80", "#FFF59D", "#A5D6A7", "#66BB6A", "#00B894"],
    }

    @classmethod
    def get_palette(cls, name: str = "default") -> list[str]:
        return cls._palettes.get(name, cls._palettes["default"])

    @classmethod
    def map_value(cls, value: float, vmin: float, vmax: float,
                  palette: str = "diverging") -> str:
        colors = cls.get_palette(palette)
        if vmax <= vmin:
            return colors[0]
        ratio = (value - vmin) / (vmax - vmin)
        idx = int(ratio * (len(colors) - 1))
        idx = max(0, min(idx, len(colors) - 1))
        return colors[idx]

    @classmethod
    def interpolate(cls, color1: str, color2: str, ratio: float) -> str:
        """线性插值两个十六进制颜色"""
        r1, g1, b1 = int(color1[1:3], 16), int(color1[3:5], 16), int(color1[5:7], 16)
        r2, g2, b2 = int(color2[1:3], 16), int(color2[3:5], 16), int(color2[5:7], 16)
        r = int(r1 + (r2 - r1) * ratio)
        g = int(g1 + (g2 - g1) * ratio)
        b = int(b1 + (b2 - b1) * ratio)
        return f"#{r:02X}{g:02X}{b:02X}"


_color_mapper = ColorMapper()


# ─── P185: 动画过渡 ──────────────────────────
class AnimationTransition:
    """图表数据变化动画"""
    def __init__(self):
        self._transitions: dict[str, dict] = {}

    def register(self, name: str, duration: int = 600,
                 easing: str = "easeOutCubic") -> None:
        self._transitions[name] = {
            "duration": duration, "easing": easing,
            "from": None, "to": None, "progress": 0
        }

    def set_data(self, name: str, from_data: Any, to_data: Any) -> None:
        if name in self._transitions:
            self._transitions[name]["from"] = from_data
            self._transitions[name]["to"] = to_data
            self._transitions[name]["progress"] = 0

    def interpolate(self, name: str, t: float) -> Any:
        tr = self._transitions.get(name)
        if not tr or tr["from"] is None:
            return tr["to"] if tr else None
        t = max(0, min(1, t))
        # easeOutCubic
        eased = 1 - (1 - t) ** 3
        f, to = tr["from"], tr["to"]
        if isinstance(f, (int, float)) and isinstance(to, (int, float)):
            return f + (to - f) * eased
        if isinstance(f, list) and isinstance(to, list) and len(f) == len(to):
            return [a + (b - a) * eased for a, b in zip(f, to)]
        return to

    def list_active(self) -> list[str]:
        return [n for n, t in self._transitions.items() if t["progress"] < 1]


_anim_transition = AnimationTransition()


# ─── P186: 交互式 tooltip ──────────────────────────
class TooltipManager:
    """图表交互 tooltip"""
    def __init__(self):
        self._templates: dict[str, str] = {}
        self._formatters: dict[str, Callable] = {}

    def set_template(self, chart_id: str, template: str) -> None:
        """设置 tooltip 模板: {name}: {value} ({percent}%)"""
        self._templates[chart_id] = template

    def set_formatter(self, chart_id: str, formatter: Callable) -> None:
        self._formatters[chart_id] = formatter

    def render(self, chart_id: str, data: dict) -> str:
        formatter = self._formatters.get(chart_id)
        if formatter:
            return formatter(data)
        template = self._templates.get(chart_id, "{name}: {value}")
        try:
            return template.format(**data)
        except (KeyError, ValueError):
            return str(data)


_tooltip_mgr = TooltipManager()


# ─── P187: 图例系统 ──────────────────────────
class LegendSystem:
    """图例管理"""
    def __init__(self):
        self._legends: dict[str, list[dict]] = {}

    def set_legend(self, chart_id: str, items: list[dict]) -> None:
        """items: [{name, color, type}]"""
        self._legends[chart_id] = items

    def get_legend(self, chart_id: str) -> list[dict]:
        return self._legends.get(chart_id, [])

    def toggle_item(self, chart_id: str, name: str) -> bool:
        items = self._legends.get(chart_id, [])
        for item in items:
            if item["name"] == name:
                item["visible"] = not item.get("visible", True)
                return item["visible"]
        return False

    def filter_visible(self, chart_id: str, series: list[dict]) -> list[dict]:
        items = {i["name"]: i.get("visible", True) for i in self._legends.get(chart_id, [])}
        return [s for s in series if items.get(s.get("name", ""), True)]


_legend_sys = LegendSystem()


# ─── P188: 数据聚合器 ──────────────────────────
class DataAggregator:
    """图表数据聚合"""
    @staticmethod
    def aggregate(data: list[dict], group_key: str,
                  value_key: str, func: str = "sum") -> list[dict]:
        groups = defaultdict(list)
        for item in data:
            key = item.get(group_key, "unknown")
            val = item.get(value_key, 0)
            groups[key].append(val)

        result = []
        for key, vals in groups.items():
            if func == "sum":
                agg = sum(vals)
            elif func == "avg":
                agg = sum(vals) / len(vals) if vals else 0
            elif func == "max":
                agg = max(vals) if vals else 0
            elif func == "min":
                agg = min(vals) if vals else 0
            elif func == "count":
                agg = len(vals)
            else:
                agg = sum(vals)
            result.append({group_key: key, value_key: agg, "count": len(vals)})
        return result

    @staticmethod
    def bucketize(data: list[float], n_buckets: int = 10) -> list[dict]:
        if not data:
            return []
        vmin, vmax = min(data), max(data)
        if vmax <= vmin:
            return [{"bucket": str(vmin), "count": len(data)}]
        step = (vmax - vmin) / n_buckets
        buckets = [0] * n_buckets
        for v in data:
            idx = min(int((v - vmin) / step), n_buckets - 1)
            buckets[idx] += 1
        return [
            {"bucket": f"{vmin + step * i:.1f}-{vmin + step * (i+1):.1f}", "count": buckets[i]}
            for i in range(n_buckets)
        ]

    @staticmethod
    def percentile(data: list[float], p: float) -> float:
        if not data:
            return 0
        s = sorted(data)
        k = (len(s) - 1) * p / 100
        f = int(k)
        c = min(f + 1, len(s) - 1)
        if f == c:
            return s[f]
        return s[f] + (s[c] - s[f]) * (k - f)


_data_agg = DataAggregator()


# ─── P189: 导出渲染器 ──────────────────────────
class ExportRenderer:
    """图表导出"""
    @staticmethod
    def to_svg(chart_type: str, data: dict, width: int = 800, height: int = 600) -> str:
        """简单 SVG 渲染"""
        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
            f'<rect width="{width}" height="{height}" fill="white"/>'
        ]
        if chart_type == "bar" and "series" in data:
            series = data["series"]
            if isinstance(series, list) and series:
                vals = series if isinstance(series[0], (int, float)) else [s.get("value", 0) for s in series]
                max_val = max(vals) if vals else 1
                bar_width = width / len(vals) * 0.8
                for i, v in enumerate(vals):
                    bar_h = (v / max_val) * (height - 60)
                    x = i * (width / len(vals)) + 10
                    y = height - 30 - bar_h
                    svg_parts.append(f'<rect x="{x}" y="{y}" width="{bar_width}" height="{bar_h}" fill="#5B8DEF"/>')
        elif chart_type == "pie" and "series" in data:
            series = data["series"]
            total = sum(s.get("value", 0) for s in series) if series else 1
            cx, cy, r = width // 2, height // 2, min(width, height) // 3
            angle = 0
            palette = ColorMapper.get_palette("default")
            for i, s in enumerate(series):
                val = s.get("value", 0)
                pct = val / total if total else 0
                end_angle = angle + pct * 2 * math.pi
                x1 = cx + r * math.cos(angle)
                y1 = cy + r * math.sin(angle)
                x2 = cx + r * math.cos(end_angle)
                y2 = cy + r * math.sin(end_angle)
                large = 1 if pct > 0.5 else 0
                color = palette[i % len(palette)]
                svg_parts.append(
                    f'<path d="M{cx},{cy} L{x1:.1f},{y1:.1f} A{r},{r} 0 {large} 1 {x2:.1f},{y2:.1f} Z" fill="{color}"/>'
                )
                angle = end_angle
        svg_parts.append('</svg>')
        return '\n'.join(svg_parts)

    @staticmethod
    def to_json(data: dict) -> str:
        import json
        return json.dumps(data, ensure_ascii=False, indent=2)

    @staticmethod
    def to_csv(series: list[dict]) -> str:
        if not series:
            return ""
        keys = list(series[0].keys())
        lines = [','.join(keys)]
        for s in series:
            lines.append(','.join(str(s.get(k, "")) for k in keys))
        return '\n'.join(lines)


_export_renderer = ExportRenderer()

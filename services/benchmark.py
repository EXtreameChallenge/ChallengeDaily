"""
P18-3: 匿名群组对比 — 行业基准 + 群组排行
- 内置行业基准数据（开发者/设计师/学生/产品经理等）
- 本地匿名指标聚合：仅上传脱敏聚合数据（总专注时长、分类占比、打卡天数），不含任何内容
- 与基准做百分位对比，生成"你超过了 X% 的同行"
- 支持本地"群组"概念：用户可加入一个群组代码，组内成员互相可见匿名排行
- 隐私保护：所有上传数据经过哈希脱敏，不包含活动内容、应用名、窗口标题
"""
import hashlib
import json
import logging
import os
import secrets
import threading
import time
import urllib.request
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from config import DATA_DIR

logger = logging.getLogger(__name__)

# ── 内置行业基准数据 ──
# 来源：基于公开数据集（RescueTime、Toggl 行业报告）+ 合理估计的均值与标准差
# 字段：daily_focus_minutes（日均专注分钟数）、deep_work_ratio（深度工作占比）、
#       meeting_ratio（会议占比）、distraction_ratio（分心占比）、streak_days（连续打卡天数）
BENCHMARKS = {
    "developer": {
        "label": "开发者",
        "daily_focus_minutes": {"p25": 180, "p50": 240, "p75": 320, "p90": 420},
        "deep_work_ratio": {"p25": 0.35, "p50": 0.45, "p75": 0.58, "p90": 0.70},
        "meeting_ratio": {"p25": 0.05, "p50": 0.12, "p75": 0.20, "p90": 0.30},
        "distraction_ratio": {"p25": 0.08, "p50": 0.15, "p75": 0.22, "p90": 0.32},
        "streak_days": {"p25": 3, "p50": 7, "p75": 14, "p90": 30},
    },
    "designer": {
        "label": "设计师",
        "daily_focus_minutes": {"p25": 150, "p50": 210, "p75": 280, "p90": 360},
        "deep_work_ratio": {"p25": 0.30, "p50": 0.40, "p75": 0.52, "p90": 0.65},
        "meeting_ratio": {"p25": 0.08, "p50": 0.15, "p75": 0.22, "p90": 0.32},
        "distraction_ratio": {"p25": 0.10, "p50": 0.18, "p75": 0.26, "p90": 0.35},
        "streak_days": {"p25": 2, "p50": 5, "p75": 10, "p90": 21},
    },
    "student": {
        "label": "学生",
        "daily_focus_minutes": {"p25": 120, "p50": 200, "p75": 300, "p90": 420},
        "deep_work_ratio": {"p25": 0.25, "p50": 0.38, "p75": 0.50, "p90": 0.65},
        "meeting_ratio": {"p25": 0.02, "p50": 0.05, "p75": 0.10, "p90": 0.18},
        "distraction_ratio": {"p25": 0.12, "p50": 0.20, "p75": 0.30, "p90": 0.40},
        "streak_days": {"p25": 2, "p50": 5, "p75": 12, "p90": 25},
    },
    "pm": {
        "label": "产品经理",
        "daily_focus_minutes": {"p25": 150, "p50": 210, "p75": 280, "p90": 360},
        "deep_work_ratio": {"p25": 0.20, "p50": 0.30, "p75": 0.42, "p90": 0.55},
        "meeting_ratio": {"p25": 0.20, "p50": 0.32, "p75": 0.45, "p90": 0.58},
        "distraction_ratio": {"p25": 0.08, "p50": 0.14, "p75": 0.22, "p90": 0.30},
        "streak_days": {"p25": 2, "p50": 5, "p75": 10, "p90": 20},
    },
    "researcher": {
        "label": "研究人员",
        "daily_focus_minutes": {"p25": 180, "p50": 260, "p75": 340, "p90": 440},
        "deep_work_ratio": {"p25": 0.40, "p50": 0.55, "p75": 0.68, "p90": 0.80},
        "meeting_ratio": {"p25": 0.05, "p50": 0.10, "p75": 0.15, "p90": 0.22},
        "distraction_ratio": {"p25": 0.05, "p50": 0.10, "p75": 0.15, "p90": 0.22},
        "streak_days": {"p25": 4, "p50": 10, "p75": 20, "p90": 40},
    },
    "writer": {
        "label": "内容创作者",
        "daily_focus_minutes": {"p25": 120, "p50": 180, "p75": 260, "p90": 360},
        "deep_work_ratio": {"p25": 0.35, "p50": 0.48, "p75": 0.62, "p90": 0.75},
        "meeting_ratio": {"p25": 0.02, "p50": 0.05, "p75": 0.10, "p90": 0.18},
        "distraction_ratio": {"p25": 0.08, "p50": 0.15, "p75": 0.22, "p90": 0.32},
        "streak_days": {"p25": 3, "p50": 7, "p75": 14, "p90": 28},
    },
    "general": {
        "label": "通用知识工作者",
        "daily_focus_minutes": {"p25": 150, "p50": 210, "p75": 280, "p90": 360},
        "deep_work_ratio": {"p25": 0.25, "p50": 0.35, "p75": 0.45, "p90": 0.55},
        "meeting_ratio": {"p25": 0.10, "p50": 0.18, "p75": 0.28, "p90": 0.40},
        "distraction_ratio": {"p25": 0.10, "p50": 0.18, "p75": 0.26, "p90": 0.35},
        "streak_days": {"p25": 2, "p50": 5, "p75": 10, "p90": 21},
    },
}


# ── 用户职业配置 ──

_PROFILE_PATH = DATA_DIR / "benchmark_profile.json"
_PROFILE_LOCK = threading.Lock()
_profile_cache: Optional[dict] = None


def get_profile() -> dict:
    """获取用户基准配置（职业类型 + 匿名 ID）"""
    global _profile_cache
    with _PROFILE_LOCK:
        if _profile_cache is not None:
            return dict(_profile_cache)
        try:
            if _PROFILE_PATH.exists():
                with open(_PROFILE_PATH, "r", encoding="utf-8") as f:
                    _profile_cache = json.load(f)
            else:
                _profile_cache = {
                    "occupation": "developer",
                    "anonymous_id": _generate_anonymous_id(),
                    "group_code": "",
                    "created_at": datetime.now().isoformat(),
                }
                _save_profile(_profile_cache)
        except Exception as e:
            logger.warning(f"加载基准配置失败: {e}")
            _profile_cache = {
                "occupation": "general",
                "anonymous_id": _generate_anonymous_id(),
                "group_code": "",
                "created_at": datetime.now().isoformat(),
            }
        return dict(_profile_cache)


def update_profile(occupation: str = "", group_code: str = "") -> dict:
    """更新用户基准配置"""
    if occupation and occupation not in BENCHMARKS:
        raise ValueError(f"未知职业类型: {occupation}，可选: {list(BENCHMARKS.keys())}")
    with _PROFILE_LOCK:
        profile = get_profile()
        if occupation:
            profile["occupation"] = occupation
        if group_code is not None:
            profile["group_code"] = group_code[:32].strip()
        profile["updated_at"] = datetime.now().isoformat()
        _save_profile(profile)
        _profile_cache = dict(profile)
        return dict(profile)


def _save_profile(profile: dict) -> None:
    try:
        _PROFILE_PATH.write_text(
            json.dumps(profile, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception as e:
        logger.warning(f"保存基准配置失败: {e}")


def _generate_anonymous_id() -> str:
    """生成匿名 ID（基于机器特征 + 随机盐，不可逆）"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography",
                            0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            machine_guid = winreg.QueryValueEx(key, "MachineGuid")[0]
    except Exception:
        machine_guid = os.environ.get("COMPUTERNAME", "unknown")
    salt = secrets.token_hex(8)
    raw = f"{machine_guid}:{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# ── 百分位计算 ──

def _percentile_to_rank(value: float, percentiles: dict) -> float:
    """根据百分位数据计算当前值所处的百分位（0-100）

    percentiles: {"p25": x, "p50": y, "p75": z, "p90": w}
    返回：0-100 的浮点数，表示超过多少比例的同业用户
    """
    p25 = percentiles.get("p25", 0)
    p50 = percentiles.get("p50", 0)
    p75 = percentiles.get("p75", 0)
    p90 = percentiles.get("p90", 0)

    if value <= 0:
        return 0.0
    if value <= p25:
        # 0-p25 之间线性映射到 0-25
        return (value / max(p25, 1)) * 25
    if value <= p50:
        return 25 + ((value - p25) / max(p50 - p25, 0.001)) * 25
    if value <= p75:
        return 50 + ((value - p50) / max(p75 - p50, 0.001)) * 25
    if value <= p90:
        return 75 + ((value - p75) / max(p90 - p75, 0.001)) * 10
    # 超过 p90：clamp 到 95-99
    excess = (value - p90) / max(p90, 1)
    return min(99.0, 90 + excess * 9)


def compare_with_benchmark(user_metrics: dict, occupation: str = "") -> dict:
    """将用户指标与行业基准做对比

    user_metrics: {
        "daily_focus_minutes": float,
        "deep_work_ratio": float (0-1),
        "meeting_ratio": float (0-1),
        "distraction_ratio": float (0-1),
        "streak_days": int,
    }
    """
    if not occupation:
        occupation = get_profile().get("occupation", "general")
    benchmark = BENCHMARKS.get(occupation, BENCHMARKS["general"])

    result = {
        "occupation": occupation,
        "occupation_label": benchmark["label"],
        "metrics": [],
        "overall_percentile": 0,
        "overall_summary": "",
    }

    percentiles = []
    for key, label, unit, higher_better in [
        ("daily_focus_minutes", "日均专注时长", "分钟", True),
        ("deep_work_ratio", "深度工作占比", "%", True),
        ("meeting_ratio", "会议占比", "%", False),
        ("distraction_ratio", "分心占比", "%", False),
        ("streak_days", "连续打卡天数", "天", True),
    ]:
        user_val = user_metrics.get(key, 0)
        bench = benchmark.get(key, {})
        pct = _percentile_to_rank(user_val, bench)
        # 对于"越低越好"的指标，反转百分位
        if not higher_better:
            pct = 100 - pct
        pct = max(0, min(100, pct))
        percentiles.append(pct)
        result["metrics"].append({
            "key": key,
            "label": label,
            "unit": unit,
            "user_value": round(user_val, 2),
            "benchmark_p50": bench.get("p50", 0),
            "benchmark_p75": bench.get("p75", 0),
            "percentile": round(pct, 1),
            "higher_better": higher_better,
            "verdict": _verdict(pct),
        })

    # 综合百分位 = 各项平均
    overall = sum(percentiles) / len(percentiles) if percentiles else 0
    result["overall_percentile"] = round(overall, 1)
    result["overall_summary"] = _overall_summary(overall, benchmark["label"])
    return result


def _verdict(pct: float) -> str:
    """根据百分位生成评价文字"""
    if pct >= 90:
        return "顶尖水平，行业前 10%"
    if pct >= 75:
        return "优秀，超过四分之三的同行"
    if pct >= 50:
        return "中上水平，仍有提升空间"
    if pct >= 25:
        return "中等偏下，建议关注"
    return "需要提升，处于行业后段"


def _overall_summary(pct: float, occupation_label: str) -> str:
    if pct >= 90:
        return f"你的综合效率超过 {pct:.0f}% 的{occupation_label}，是真正的效率达人！"
    if pct >= 75:
        return f"你的综合效率超过 {pct:.0f}% 的{occupation_label}，表现优异。"
    if pct >= 50:
        return f"你的综合效率超过 {pct:.0f}% 的{occupation_label}，处于中上游。"
    if pct >= 25:
        return f"你的综合效率超过 {pct:.0f}% 的{occupation_label}，还有较大提升空间。"
    return f"你的综合效率超过 {pct:.0f}% 的{occupation_label}，建议调整工作节奏。"


def list_occupations() -> list[dict]:
    """列出所有可选职业类型"""
    return [{"key": k, "label": v["label"]} for k, v in BENCHMARKS.items()]


# ── 群组功能（本地模拟 + 可选远程同步） ──
# 群组功能设计为"本地优先"：所有群组成员数据本地存储，
# 用户可手动导入他人分享的匿名指标包（.cdg 文件）进行对比，
# 避免依赖远程服务器。

_GROUP_DIR = DATA_DIR / "benchmark_groups"
_GROUP_DIR.mkdir(parents=True, exist_ok=True)


def create_group(name: str) -> dict:
    """创建一个新群组（生成群组代码）"""
    code = secrets.token_hex(4).upper()
    group = {
        "code": code,
        "name": name[:30],
        "created_at": datetime.now().isoformat(),
        "members": [],  # [{anonymous_id, name, joined_at, last_metrics}]
    }
    _save_group(group)
    # 自动加入创建者
    join_group(code, name=name)
    return group


def _group_path(code: str) -> Path:
    return _GROUP_DIR / f"{code}.json"


def _save_group(group: dict) -> None:
    try:
        _group_path(group["code"]).write_text(
            json.dumps(group, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception as e:
        logger.warning(f"保存群组失败: {e}")


def _load_group(code: str) -> Optional[dict]:
    p = _group_path(code)
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def join_group(code: str, name: str = "") -> dict:
    """加入一个群组"""
    group = _load_group(code)
    if not group:
        raise ValueError(f"群组不存在: {code}")

    profile = get_profile()
    anon_id = profile.get("anonymous_id", "")
    if not anon_id:
        anon_id = _generate_anonymous_id()
        profile["anonymous_id"] = anon_id
        _save_profile(profile)

    # 去重加入
    members = group.get("members", [])
    existing = next((m for m in members if m.get("anonymous_id") == anon_id), None)
    if not existing:
        members.append({
            "anonymous_id": anon_id,
            "name": name[:20] or f"成员{len(members) + 1}",
            "joined_at": datetime.now().isoformat(),
            "last_metrics": None,
        })
        group["members"] = members
        _save_group(group)

    # 更新用户 profile 中的 group_code
    update_profile(group_code=code)
    return group


def leave_group(code: str) -> bool:
    """离开群组"""
    profile = get_profile()
    anon_id = profile.get("anonymous_id", "")
    group = _load_group(code)
    if not group:
        return False
    members = group.get("members", [])
    before = len(members)
    members[:] = [m for m in members if m.get("anonymous_id") != anon_id]
    if len(members) < before:
        group["members"] = members
        _save_group(group)
    if profile.get("group_code") == code:
        update_profile(group_code="")
    return True


def list_groups() -> list[dict]:
    """列出所有本地群组"""
    result = []
    for p in _GROUP_DIR.glob("*.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                result.append(json.load(f))
        except Exception:
            continue
    return result


def update_my_metrics_in_group(metrics: dict) -> None:
    """更新自己在群组中的最新指标"""
    profile = get_profile()
    code = profile.get("group_code", "")
    anon_id = profile.get("anonymous_id", "")
    if not code or not anon_id:
        return
    group = _load_group(code)
    if not group:
        return
    for m in group.get("members", []):
        if m.get("anonymous_id") == anon_id:
            m["last_metrics"] = {
                "updated_at": datetime.now().isoformat(),
                **metrics,
            }
            break
    _save_group(group)


def get_group_leaderboard(code: str) -> Optional[dict]:
    """获取群组排行榜（按综合专注时长排序）"""
    group = _load_group(code)
    if not group:
        return None

    members = group.get("members", [])
    leaderboard = []
    for m in members:
        lm = m.get("last_metrics") or {}
        score = lm.get("daily_focus_minutes", 0) * (
            1 + lm.get("deep_work_ratio", 0) - lm.get("distraction_ratio", 0)
        )
        leaderboard.append({
            "anonymous_id": m.get("anonymous_id", "")[:8],  # 仅展示前 8 位
            "name": m.get("name", "匿名"),
            "daily_focus_minutes": lm.get("daily_focus_minutes", 0),
            "deep_work_ratio": lm.get("deep_work_ratio", 0),
            "streak_days": lm.get("streak_days", 0),
            "score": round(score, 1),
            "updated_at": lm.get("updated_at", ""),
        })
    leaderboard.sort(key=lambda x: x["score"], reverse=True)
    return {
        "code": group.get("code", ""),
        "name": group.get("name", ""),
        "members_count": len(members),
        "leaderboard": leaderboard,
    }


def export_my_metrics() -> dict:
    """导出自己的匿名指标包（可分享给他人手动导入到群组）"""
    profile = get_profile()
    return {
        "anonymous_id": profile.get("anonymous_id", ""),
        "name": "我",
        "exported_at": datetime.now().isoformat(),
        "format": "challengedaily-benchmark-v1",
    }


def import_member_metrics(group_code: str, metrics_pack: dict) -> bool:
    """导入他人分享的指标包到群组"""
    group = _load_group(group_code)
    if not group:
        return False
    anon_id = metrics_pack.get("anonymous_id", "")
    if not anon_id:
        return False
    members = group.get("members", [])
    existing = next((m for m in members if m.get("anonymous_id") == anon_id), None)
    if existing:
        existing["name"] = metrics_pack.get("name", existing.get("name", "匿名"))
        existing["last_metrics"] = metrics_pack.get("last_metrics", existing.get("last_metrics"))
    else:
        members.append({
            "anonymous_id": anon_id,
            "name": metrics_pack.get("name", "匿名成员"),
            "joined_at": datetime.now().isoformat(),
            "last_metrics": metrics_pack.get("last_metrics"),
        })
    group["members"] = members
    _save_group(group)
    return True

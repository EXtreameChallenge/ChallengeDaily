"""
P101-P109: 打磨与愉悦感增强模块
- P101: 微交互动画系统
- P102: 庆祝效果(撒花/烟花)
- P103: 个性化问候语库
- P104: 成就徽章视觉
- P105: 颜色情感映射
- P106: 声音反馈系统
- P107: 表情符号库
- P108: 励志名言库
- P109: 情绪日记模板
"""
import logging
import threading
import random
import time
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


# ─── P101: 微交互动画系统 ──────────────────────────
_MICRO_INTERACTIONS = {
    "button_press": {"duration": 150, "easing": "ease-out", "scale": 0.95},
    "card_hover": {"duration": 200, "easing": "ease-in-out", "lift": 2},
    "list_item_enter": {"duration": 250, "easing": "cubic-bezier(0.22, 0.61, 0.36, 1)", "stagger": 30},
    "modal_open": {"duration": 300, "easing": "cubic-bezier(0.34, 1.56, 0.64, 1)", "scale_from": 0.9},
    "modal_close": {"duration": 200, "easing": "ease-in", "scale_to": 0.95},
    "toast_enter": {"duration": 250, "easing": "spring", "slide": 40},
    "tab_switch": {"duration": 180, "easing": "ease-in-out", "fade": True},
    "data_update": {"duration": 400, "easing": "ease-out", "blur": True},
    "achievement_unlock": {"duration": 800, "easing": "bounce", "confetti": True},
    "pomodoro_complete": {"duration": 600, "easing": "spring", "ring": True},
}


def get_micro_interactions() -> dict:
    return dict(_MICRO_INTERACTIONS)


def get_animation_for(event: str) -> dict:
    return _MICRO_INTERACTIONS.get(event, {"duration": 200, "easing": "ease-out"})


# ─── P102: 庆祝效果 ──────────────────────────
_CELEBRATION_TYPES = {
    "confetti": {
        "particles": 80,
        "colors": ["#F0C040", "#7B68EE", "#5B8DEF", "#00B894", "#E54D42", "#FD79A8"],
        "duration": 3000,
        "spread": 360
    },
    "fireworks": {
        "particles": 50,
        "colors": ["#F0C040", "#7B68EE", "#00B894"],
        "duration": 2500,
        "spread": 180
    },
    "sparkles": {
        "particles": 30,
        "colors": ["#F0C040", "#FFFFFF"],
        "duration": 1500,
        "spread": 90
    },
    "hearts": {
        "particles": 20,
        "colors": ["#FD79A8", "#E54D42"],
        "duration": 2000,
        "spread": 120
    },
    "stars": {
        "particles": 40,
        "colors": ["#F0C040", "#FFFFFF"],
        "duration": 2000,
        "spread": 180
    }
}


def get_celebration(scene: str = "confetti") -> dict:
    """获取庆祝效果配置"""
    return _CELEBRATION_TYPES.get(scene, _CELEBRATION_TYPES["confetti"])


def trigger_cebration(scene: str, reason: str = "") -> dict:
    """触发庆祝效果"""
    config = get_celebration(scene)
    return {
        "scene": scene,
        "reason": reason,
        "config": config,
        "triggered_at": datetime.now().isoformat()
    }


# ─── P103: 个性化问候语库 ──────────────────────────
_GREETINGS = {
    "morning_early": [
        "晨光熹微，新的一天已悄然开启～",
        "早起的鸟儿有虫吃，今天也要元气满满呀！",
        "清晨的第一缕阳光，照亮你的专注之路～",
    ],
    "morning": [
        "早安！今天也是充满可能的一天～",
        "新的一天开始啦，准备好大显身手了吗？",
        "美好的一天从专注开始，加油呀！",
    ],
    "forenoon": [
        "上午好～专注的时光总是格外珍贵呢",
        "趁阳光正好，让心流自由流淌吧～",
        "上半场发挥不错，继续保持节奏！",
    ],
    "noon": [
        "中午好～记得休息一下眼睛哦",
        "劳逸结合才是王道，午餐时间到啦！",
        "充电时刻，下午继续发光发热～",
    ],
    "afternoon": [
        "下午好～最容易犯困的时段，挺住！",
        "午后时光，深呼吸，再战一场～",
        "夕阳无限好，专注正当时！",
    ],
    "evening": [
        "傍晚好～今天的努力都看得见呢",
        "夜幕将至，是时候盘点收获了～",
        "辛苦一天啦，给自己一个微笑吧！",
    ],
    "night": [
        "夜深了～注意休息，明天会更美好",
        "星空下的奋斗者，晚安前再冲一波？",
        "熬夜伤身，记得早点休息哦～",
    ],
    "late_night": [
        "凌晨了！身体是革命的本钱呀～",
        "这么晚还在忙？别忘了照顾好自己",
        "深夜伏案，明日方长，早点歇息吧～",
    ]
}


def get_greeting_by_hour(hour: int = None) -> str:
    """根据时间获取问候语"""
    if hour is None:
        hour = datetime.now().hour
    if hour < 6:
        bucket = "late_night"
    elif hour < 8:
        bucket = "morning_early"
    elif hour < 11:
        bucket = "morning"
    elif hour < 12:
        bucket = "forenoon"
    elif hour < 14:
        bucket = "noon"
    elif hour < 17:
        bucket = "afternoon"
    elif hour < 20:
        bucket = "evening"
    elif hour < 23:
        bucket = "night"
    else:
        bucket = "late_night"
    greetings = _GREETINGS[bucket]
    return random.choice(greetings)


def get_all_greeting_buckets() -> dict:
    return {k: len(v) for k, v in _GREETINGS.items()}


# ─── P104: 成就徽章视觉 ──────────────────────────
_BADGE_STYLES = {
    "bronze": {"color": "#CD7F32", "icon": "🥉", "glow": "rgba(205, 127, 50, 0.4)"},
    "silver": {"color": "#C0C0C0", "icon": "🥈", "glow": "rgba(192, 192, 192, 0.4)"},
    "gold": {"color": "#FFD700", "icon": "🥇", "glow": "rgba(255, 215, 0, 0.5)"},
    "platinum": {"color": "#E5E4E2", "icon": "💎", "glow": "rgba(229, 228, 226, 0.6)"},
    "diamond": {"color": "#B9F2FF", "icon": "💠", "glow": "rgba(185, 242, 255, 0.7)"},
    "legendary": {"color": "#FF6B6B", "icon": "👑", "glow": "rgba(255, 107, 107, 0.8)"},
}


def get_badge_style(tier: str) -> dict:
    return _BADGE_STYLES.get(tier, _BADGE_STYLES["bronze"])


def get_all_badge_tiers() -> list:
    return list(_BADGE_STYLES.keys())


# ─── P105: 颜色情感映射 ──────────────────────────
_EMOTION_COLORS = {
    "joy": {"primary": "#FFD93D", "secondary": "#FFA500", "emoji": "😄"},
    "calm": {"primary": "#6BCB77", "secondary": "#4D96FF", "emoji": "😌"},
    "focus": {"primary": "#4D96FF", "secondary": "#7B68EE", "emoji": "🎯"},
    "energy": {"primary": "#FF6B6B", "secondary": "#FFD93D", "emoji": "⚡"},
    "tired": {"primary": "#8E8E8E", "secondary": "#B8B8B8", "emoji": "😮‍💨"},
    "stress": {"primary": "#FF4757", "secondary": "#FF6B6B", "emoji": "😣"},
    "proud": {"primary": "#FFD700", "secondary": "#FFA500", "emoji": "🦚"},
    "curious": {"primary": "#A29BFE", "secondary": "#7B68EE", "emoji": "🤔"},
}


def get_emotion_color(emotion: str) -> dict:
    return _EMOTION_COLORS.get(emotion, _EMOTION_COLORS["focus"])


def get_all_emotions() -> list:
    return list(_EMOTION_COLORS.keys())


# ─── P106: 声音反馈系统 ──────────────────────────
_SOUND_EFFECTS = {
    "click": {"file": "click.mp3", "volume": 0.3, "category": "ui"},
    "success": {"file": "success.mp3", "volume": 0.5, "category": "feedback"},
    "error": {"file": "error.mp3", "volume": 0.4, "category": "feedback"},
    "notification": {"file": "notification.mp3", "volume": 0.4, "category": "system"},
    "achievement": {"file": "achievement.mp3", "volume": 0.6, "category": "celebration"},
    "pomodoro_start": {"file": "start.mp3", "volume": 0.4, "category": "pomodoro"},
    "pomodoro_end": {"file": "bell.mp3", "volume": 0.5, "category": "pomodoro"},
    "break_start": {"file": "chime.mp3", "volume": 0.4, "category": "pomodoro"},
    "level_up": {"file": "levelup.mp3", "volume": 0.6, "category": "celebration"},
}


def get_sound_effects() -> dict:
    return dict(_SOUND_EFFECTS)


def get_sound_for(event: str) -> dict:
    return _SOUND_EFFECTS.get(event, {"file": "", "volume": 0.5, "category": "ui"})


# ─── P107: 表情符号库 ──────────────────────────
_EMOJI_CATEGORIES = {
    "productivity": ["🎯", "💪", "🔥", "⚡", "🚀", "⭐", "🌟", "✨"],
    "achievement": ["🏆", "🥇", "🎖️", "🏅", "👑", "💎", "🎉", "🎊"],
    "focus": ["🧘", "🎯", "📖", "💻", "🦉", "🔍", "💡", "🧠"],
    "emotion_positive": ["😄", "😊", "🥰", "😎", "🤩", "😇", "🙂", "😋"],
    "emotion_calm": ["😌", "😴", "🛌", "🌙", "☁️", "🍃", "🌊", "🎐"],
    "nature": ["🌸", "🌺", "🌻", "🌷", "🌹", "🍀", "🌿", "🌱"],
    "time": ["⏰", "⏳", "🕐", "⌚", "🌅", "🌄", "🌇", "🌌"],
    "status": ["✅", "❌", "⚠️", "ℹ️", "🔔", "📌", "🏷️", "📊"],
}


def get_emojis(category: str = "") -> list:
    if category and category in _EMOJI_CATEGORIES:
        return _EMOJI_CATEGORIES[category]
    return _EMOJI_CATEGORIES


def get_random_emoji(category: str = "productivity") -> str:
    emojis = _EMOJI_CATEGORIES.get(category, _EMOJI_CATEGORIES["productivity"])
    return random.choice(emojis)


# ─── P108: 励志名言库 ──────────────────────────
_QUOTES = [
    {"text": "专注是成功的秘诀", "author": "爱默生", "category": "focus"},
    {"text": "今日事，今日毕", "author": "曾国藩", "category": "action"},
    {"text": "不积跬步，无以至千里", "author": "荀子", "category": "persistence"},
    {"text": "千里之行，始于足下", "author": "老子", "category": "action"},
    {"text": "业精于勤，荒于嬉", "author": "韩愈", "category": "diligence"},
    {"text": "锲而不舍，金石可镂", "author": "荀子", "category": "persistence"},
    {"text": "时间就像海绵里的水", "author": "鲁迅", "category": "time"},
    {"text": "宝剑锋从磨砺出", "author": "古训", "category": "hardship"},
    {"text": "宁静致远", "author": "诸葛亮", "category": "calm"},
    {"text": "知己知彼，百战不殆", "author": "孙子", "category": "strategy"},
    {"text": "深挖洞，广积粮", "author": "朱元璋", "category": "preparation"},
    {"text": "工欲善其事，必先利其器", "author": "孔子", "category": "preparation"},
    {"text": "流水不腐，户枢不蠹", "author": "吕氏春秋", "category": "action"},
    {"text": "天道酬勤", "author": "古训", "category": "diligence"},
    {"text": "靡不有初，鲜克有终", "author": "诗经", "category": "persistence"},
]


def get_quote(category: str = "") -> dict:
    """获取一条励志名言"""
    if category:
        candidates = [q for q in _QUOTES if q["category"] == category]
        if candidates:
            return random.choice(candidates)
    return random.choice(_QUOTES)


def get_quotes_by_category(category: str) -> list:
    return [q for q in _QUOTES if q["category"] == category]


def get_quote_categories() -> list:
    return list({q["category"] for q in _QUOTES})


# ─── P109: 情绪日记模板 ──────────────────────────
_DIARY_TEMPLATES = [
    {
        "id": "gratitude",
        "name": "感恩日记",
        "icon": "🙏",
        "questions": [
            "今天最让你感激的三件事是什么？",
            "有谁帮助了你，你想感谢谁？",
            "今天有什么小确幸让你会心一笑？"
        ]
    },
    {
        "id": "reflection",
        "name": "复盘日记",
        "icon": "🤔",
        "questions": [
            "今天最专注的时刻是什么时候？",
            "有什么事情做得比昨天更好？",
            "明天最想改进的一点是什么？"
        ]
    },
    {
        "id": "achievement",
        "name": "成就日记",
        "icon": "🏆",
        "questions": [
            "今天最自豪的成就是什么？",
            "你克服了什么困难？",
            "你学到了什么新技能或知识？"
        ]
    },
    {
        "id": "emotion",
        "name": "情绪日记",
        "icon": "💭",
        "questions": [
            "今天主要情绪是什么？为什么？",
            "有什么触发了你的情绪波动？",
            "你是如何调节情绪的？"
        ]
    },
    {
        "id": "creative",
        "name": "创意日记",
        "icon": "💡",
        "questions": [
            "今天有什么新想法涌现？",
            "你看到了什么有趣的灵感？",
            "如果可以尝试一件事，你想做什么？"
        ]
    }
]


def get_diary_templates() -> list:
    return _DIARY_TEMPLATES


def get_diary_template(template_id: str) -> dict | None:
    for t in _DIARY_TEMPLATES:
        if t["id"] == template_id:
            return t
    return None

"""
ChallengeDaily Windows 版 — 工作分类规则
结合 AI 返回结果 + 应用进程名的规则分类 + 用户自定义规则
"""
import json
import logging
import time

from app_tracker import get_display_name
from config import CATEGORIES

logger = logging.getLogger(__name__)

# ── 应用名到分类的映射规则（默认规则，可被用户自定义覆盖）──
# 注意：key 的大小写需与 Windows 进程名一致，查找时使用 _APP_CATEGORY_RULES_LOWER 做大小写不敏感匹配
APP_CATEGORY_RULES = {
    # 开发
    "Code.exe": "开发", "devenv.exe": "开发", "idea64.exe": "开发",
    "pycharm64.exe": "开发", "webstorm64.exe": "开发", "goland64.exe": "开发",
    "rustrover64.exe": "开发", "cursor.exe": "开发", "windsurf.exe": "开发",
    "WindowsTerminal.exe": "开发", "cmd.exe": "开发", "PowerShell.exe": "开发",
    "git-bash.exe": "开发", "postman.exe": "开发", "Insomnia.exe": "开发",
    "DataGrip64.exe": "开发", "Navicat.exe": "开发", "DBeaver.exe": "开发",

    # 文档
    "WINWORD.EXE": "文档", "EXCEL.EXE": "文档", "POWERPNT.EXE": "文档",
    "ONENOTE.EXE": "文档", "Notion.exe": "文档", "Obsidian.exe": "文档",
    "Typora.exe": "文档",

    # 沟通
    "WeChat.exe": "沟通", "Weixin.exe": "沟通", "DingTalk.exe": "沟通", "Feishu.exe": "沟通",
    "Telegram.exe": "沟通", "Discord.exe": "沟通", "TIM.exe": "沟通",
    "QQ.exe": "沟通", "QQMusic.exe": "生活",

    # 会议
    "Teams.exe": "会议", "Zoom.exe": "会议", "Loom.exe": "会议",
    "conf.exe": "会议", "vip.exe": "会议",  # 腾讯会议

    # 设计
    "Figma.exe": "设计", "Photoshop.exe": "设计", "Illustrator.exe": "设计",
    "AxureRP.exe": "设计", "Sketch.exe": "设计",

    # 运维
    "mRemoteNG.exe": "运维", "putty.exe": "运维", "MobaXterm.exe": "运维",
    "Xshell.exe": "运维",

    # 管理
    "OUTLOOK.EXE": "管理", "HxOutlook.exe": "管理",  # 邮件

    # 数据分析
    "Tableau.exe": "数据分析", "PowerBI.exe": "数据分析", "JupyterLab.exe": "数据分析",

    # 生活
    "Spotify.exe": "生活", "Music.UI.exe": "生活", "Netflix.exe": "生活",

    # 生活 — 系统工具
    "MSPCManager.exe": "生活", "LenovoPcManager.exe": "生活",  # 电脑管家
    "Taskmgr.exe": "生活", "SettingsApp.exe": "生活",           # 任务管理器/系统设置
    "cleanmgr.exe": "生活",                                     # 磁盘清理
    "SearchUI.exe": "生活", "ShellExperienceHost.exe": "生活",  # 搜索/Shell体验
}


# ── AI 返回分类名的模糊匹配映射 ──
# AI 可能返回"软件开发"而非"开发"，这里做兜底
_CATEGORY_ALIAS = {
    "软件开发": "开发", "编程": "开发", "写代码": "开发", "coding": "开发",
    "开视频会议": "会议", "线上会议": "会议", "视频会议": "会议",
    "即时通讯": "沟通", "聊天": "沟通", "社交通讯": "沟通",
    "写文档": "文档", "文档编辑": "文档", "文档撰写": "文档",
    "网页浏览": "其他", "浏览器": "其他", "上网": "其他",
    "运维监控": "运维", "系统运维": "运维",
    "数据分析": "数据分析", "数据可视化": "数据分析",
    "产品设计": "产品", "产品规划": "产品",
    "项目管理": "管理", "行政管理": "管理", "邮件": "管理",
    "UI设计": "设计", "界面设计": "设计",
}


# ── 用户自定义规则缓存 ──
_rule_cache = {}
_rule_cache_time = 0
_RULE_CACHE_TTL = 10  # 10 秒缓存，编辑规则后快速生效


def _load_user_rules() -> dict[str, dict]:
    """从数据库加载用户自定义规则（带缓存）"""
    global _rule_cache, _rule_cache_time
    now = time.time()
    if _rule_cache and (now - _rule_cache_time) < _RULE_CACHE_TTL:
        return _rule_cache
    try:
        from db import get_app_category_rules
        rules = get_app_category_rules()
        _rule_cache = {r["app_name"].lower(): r for r in rules}
        _rule_cache_time = now
        return _rule_cache
    except Exception as e:
        logger.warning(f"加载用户分类规则失败: {e}")
        return {}


def invalidate_rule_cache():
    """强制刷新规则缓存"""
    global _rule_cache_time
    _rule_cache_time = 0


def _normalize_category(cat: str) -> str:
    """把 AI/别名 归一化为标准分类"""
    cat = cat.strip() if cat else ""
    if not cat:
        return ""
    if cat in CATEGORIES:
        return cat
    if cat in _CATEGORY_ALIAS:
        mapped = _CATEGORY_ALIAS[cat]
        if mapped in CATEGORIES:
            return mapped
    # 包含关键词匹配（"XX开发" 包含 "开发"）
    for std in CATEGORIES:
        if std in cat:
            return std
    return ""


def _browser_title_category(app_name: str, window_title: str) -> str:
    """根据浏览器窗口标题关键词推断分类"""
    _BROWSERS = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"}
    if app_name.lower() not in _BROWSERS:
        return ""
    title_lower = (window_title or "").lower()
    rules = [
        ("开发", ["github", "stackoverflow", "gitlab", "npmjs", "pypi",
                  "vscode", "jetbrains", "localhost", "127.0.0.1",
                  "api doc", "swagger", "postman", "gitee", "gitcode"]),
        ("沟通", ["gmail", "outlook", "slack", "discord", "微信",
                  "飞书", "钉钉", "telegram", "web whatsapp"]),
        ("文档", ["google docs", "notion", "confluence", "docs.google",
                  "石墨", "语雀", "飞书文档"]),
        ("会议", ["zoom", "teams", "腾讯会议", "google meet", "meet.google"]),
        ("设计", ["figma", "dribbble", "behance", "canva"]),
        ("数据分析", ["analytics", "grafana", "tableau", "metabase"]),
        ("产品", ["jira", "trello", "asana", "linear", "product"]),
        ("学习", ["coursera", "udemy", "leetcode", "csdn",
                  "掘金", "知乎", "wikipedia", "bilibili"]),
    ]
    for cat, keywords in rules:
        if any(kw in title_lower for kw in keywords):
            return cat
    return ""


def classify(app_name: str, ai_category: str = "", window_title: str = "") -> str:
    """
    综合规则、AI 结果、用户自定义规则给出最终分类。
    优先级：用户自定义规则 > AI 结果 > 默认规则 > 浏览器标题推断 > 默认"其他"
    """
    user_rules = _load_user_rules()
    rule = user_rules.get(app_name.lower())

    # 标准化 AI 分类
    norm_ai = _normalize_category(ai_category)

    # 1. 用户自定义规则：若 AI 结果命中候选标签，直接使用
    if rule:
        tags = rule.get("tags") or []
        primary = rule.get("primary_category") or ""
        window_rules = rule.get("window_rules") or {}

        # 窗口标题关键词规则优先级最高（用户明确指定）
        if window_rules and window_title:
            title_lower = window_title.lower()
            for kw, cat in window_rules.items():
                if kw.lower() in title_lower and cat in CATEGORIES:
                    return cat

        # AI 结果在候选标签内
        if norm_ai and norm_ai in tags:
            return norm_ai

        # 浏览器标题推断在候选标签内
        title_cat = _browser_title_category(app_name, window_title)
        if title_cat and title_cat in tags:
            return title_cat

        # 兜底：主分类
        if primary and primary in CATEGORIES:
            return primary

        # 规则异常时继续走默认逻辑

    # 2. AI 分类直接匹配
    if norm_ai:
        return norm_ai

    # 3. 默认规则（大小写不敏感匹配，与 get_display_name 保持一致）
    rule_cat = _APP_CATEGORY_RULES_LOWER.get(app_name.lower(), "")
    if rule_cat and rule_cat in CATEGORIES:
        return rule_cat

    # 4. 浏览器标题推断
    title_cat = _browser_title_category(app_name, window_title)
    if title_cat:
        return title_cat

    return "其他"


def get_app_tags(app_name: str) -> list[str]:
    """获取某个应用预设的候选标签（用于前端展示）"""
    user_rules = _load_user_rules()
    rule = user_rules.get(app_name.lower())
    if rule:
        return rule.get("tags") or []
    # 无自定义规则时返回默认规则对应的单标签
    cat = APP_CATEGORY_RULES.get(app_name)
    return [cat] if cat and cat in CATEGORIES else []

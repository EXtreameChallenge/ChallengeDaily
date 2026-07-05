"""
ChallengeDaily Windows 版 — 工作分类规则
结合 AI 返回结果 + 应用进程名的规则分类
"""
from app_tracker import get_display_name
from config import CATEGORIES

# ── 应用名到分类的映射规则 ──
APP_CATEGORY_RULES = {
    # 开发
    "Code.exe": "开发", "devenv.exe": "开发", "idea64.exe": "开发",
    "pycharm64.exe": "开发", "webstorm64.exe": "开发", "goland64.exe": "开发",
    "rustrover64.exe": "开发", "cursor.exe": "开发", "windsurf.exe": "开发",
    "WindowsTerminal.exe": "开发", "cmd.exe": "开发", "PowerShell.exe": "开发",
    "git-bash.exe": "开发", "postman.exe": "开发", "Insomnia.exe": "开发",
    "DataGrip64.exe": "开发", "Navicat.exe": "开发", "DBeaver.exe": "开发",
    # 注意：浏览器不再硬编码为"开发"，交由 AI 分析桌面内容判断实际用途
    # 如果 AI 未配置或分析失败，浏览器将归为默认分类"其他"

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

    # 测试
    # 浏览器已归入开发，测试类别留空为主，由AI判断

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

    # 其他 — 文件资源管理器虽常见但用途多样，归"其他"等待AI判断
}


# ── AI 返回分类名的模糊匹配映射 ──
# AI 可能返回"软件开发"而非"开发"，这里做兜底
_CATEGORY_ALIAS = {
    "软件开发": "开发", "编程": "开发", "写代码": "开发", "coding": "开发",
    "开视频会议": "会议", "线上会议": "会议", "视频会议": "会议",
    "即时通讯": "沟通", "聊天": "沟通", "社交通讯": "沟通",
    "写文档": "文档", "文档编辑": "文档", "文档撰写": "文档",
    "网页浏览": "其他", "浏览器": "其他", "上网": "其他",  # 浏览器用途多样，交由 AI 判断；无 AI 时归"其他"
    "运维监控": "运维", "系统运维": "运维",
    "数据分析": "数据分析", "数据可视化": "数据分析",
    "产品设计": "产品", "产品规划": "产品",
    "项目管理": "管理", "行政管理": "管理", "邮件": "管理",
    "UI设计": "设计", "界面设计": "设计",
}


def classify(app_name: str, ai_category: str = "", window_title: str = "") -> str:
    """
    综合规则和 AI 结果给出最终分类。
    优先级：AI 结果 > 规则映射 > 浏览器标题推断 > 默认"其他"
    """
    # AI 分类直接匹配
    if ai_category and ai_category in CATEGORIES:
        return ai_category

    # AI 分类模糊匹配（"软件开发" → "开发"）
    if ai_category and ai_category in _CATEGORY_ALIAS:
        mapped = _CATEGORY_ALIAS[ai_category]
        if mapped in CATEGORIES:
            return mapped

    # AI 分类包含关键词匹配（"XX开发" 包含 "开发"）
    if ai_category:
        for cat in CATEGORIES:
            if cat in ai_category:
                return cat

    # 走规则
    rule_cat = APP_CATEGORY_RULES.get(app_name, "")
    if rule_cat and rule_cat in CATEGORIES:
        return rule_cat

    # 浏览器特殊处理：无 AI 时按窗口标题关键词推断分类
    _BROWSERS = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"}
    if app_name in _BROWSERS and not ai_category:
        title_lower = (window_title or "").lower()
        # 开发相关
        if any(kw in title_lower for kw in ["github", "stackoverflow", "gitlab", "npmjs", "pypi",
                                              "vscode", "jetbrains", "localhost", "127.0.0.1",
                                              "api doc", "swagger", "postman"]):
            return "开发"
        # 沟通相关
        if any(kw in title_lower for kw in ["gmail", "outlook", "slack", "discord", "微信",
                                              "飞书", "钉钉", "telegram", "web whatsapp"]):
            return "沟通"
        # 文档相关
        if any(kw in title_lower for kw in ["google docs", "notion", "confluence", "docs.google",
                                              "石墨", "语雀", "飞书文档"]):
            return "文档"
        # 会议相关
        if any(kw in title_lower for kw in ["zoom", "teams", "腾讯会议", "google meet",
                                              "meet.google"]):
            return "会议"
        # 设计相关
        if any(kw in title_lower for kw in ["figma", "dribbble", "behance", "canva"]):
            return "设计"
        # 数据分析
        if any(kw in title_lower for kw in ["analytics", "grafana", "tableau", "metabase"]):
            return "数据分析"
        # 产品相关
        if any(kw in title_lower for kw in ["jira", "trello", "asana", "linear", "product"]):
            return "产品"
        # 学习相关
        if any(kw in title_lower for kw in ["coursera", "udemy", "leetcode", "csdn",
                                              "掘金", "知乎", "wikipedia", "bilibili"]):
            return "学习"
        # 无法推断时默认"其他"
        return "其他"

    return "其他"

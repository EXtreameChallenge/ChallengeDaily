"""
P18-2: Git 集成 — 读取本地 git 仓库提交历史，关联代码产出
- 在指定目录下执行 git log（子进程隔离）
- 解析提交记录：作者/时间/消息/文件变更数
- 按日聚合统计：提交数、活跃文件数、消息关键词
- 与采集数据联动：生成"代码产出报告"段落
"""
import logging
import os
import re
import subprocess
import threading
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

from config import DATA_DIR, load_settings, save_settings

logger = logging.getLogger(__name__)

# 全局缓存 git 仓库列表（用户配置的多个仓库路径）
_REPOS_KEY = "git_repositories"
_REPOS_LOCK = threading.Lock()


# ── 仓库管理 ──

def list_repositories() -> list[dict]:
    """获取已配置的 git 仓库列表"""
    settings = load_settings()
    repos = settings.get(_REPOS_KEY, [])
    # 校验每个仓库是否仍存在 .git
    result = []
    for r in repos:
        path = r.get("path", "")
        enabled = r.get("enabled", True)
        exists = bool(path) and Path(path).exists()
        has_git = exists and (Path(path) / ".git").exists()
        result.append({
            **r,
            "exists": exists,
            "has_git": has_git,
            "status": "ok" if has_git else ("missing" if not exists else "not_a_repo"),
        })
    return result


def add_repository(path: str, name: str = "", enabled: bool = True) -> dict:
    """添加一个 git 仓库到监控列表"""
    path = os.path.abspath(path)
    if not Path(path).exists():
        raise ValueError(f"路径不存在: {path}")
    repo = {
        "path": path,
        "name": name or os.path.basename(path),
        "enabled": enabled,
        "added_at": datetime.now().isoformat(),
    }
    with _REPOS_LOCK:
        settings = load_settings()
        repos = settings.get(_REPOS_KEY, [])
        # 去重：相同路径不重复添加
        if any(r.get("path") == path for r in repos):
            raise ValueError(f"仓库已存在: {path}")
        repos.append(repo)
        settings[_REPOS_KEY] = repos
        save_settings(settings)
    return repo


def remove_repository(path: str) -> bool:
    """从监控列表移除一个 git 仓库"""
    with _REPOS_LOCK:
        settings = load_settings()
        repos = settings.get(_REPOS_KEY, [])
        before = len(repos)
        repos[:] = [r for r in repos if r.get("path") != path]
        if len(repos) < before:
            settings[_REPOS_KEY] = repos
            save_settings(settings)
            return True
    return False


def update_repository(path: str, **kwargs) -> Optional[dict]:
    """更新仓库配置"""
    with _REPOS_LOCK:
        settings = load_settings()
        repos = settings.get(_REPOS_KEY, [])
        for r in repos:
            if r.get("path") == path:
                for k in ("name", "enabled"):
                    if k in kwargs:
                        r[k] = kwargs[k]
                settings[_REPOS_KEY] = repos
                save_settings(settings)
                return dict(r)
    return None


# ── git log 解析 ──

_LOG_FORMAT = "%H%x1f%an%x1f%ae%x1f%ad%x1f%cn%x1f%cd%x1f%s%x1f%b%x1e"
# %H=commit hash, %an=作者名, %ae=作者邮箱, %ad=作者时间, %cn=提交者名, %cd=提交者时间, %s=标题, %b=正文
# 分隔符：\x1f 字段间，\x1e 记录间

def _run_git(repo_path: str, args: list[str], timeout: int = 10) -> str:
    """在仓库目录下执行 git 命令，返回 stdout（带超时和异常隔离）"""
    try:
        # 安全限制：仅允许特定子命令
        if not args or args[0] not in ("log", "status", "rev-parse", "diff", "show"):
            raise ValueError(f"不允许的 git 子命令: {args[0] if args else 'empty'}")

        result = subprocess.run(
            ["git"] + args,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} 失败: {result.stderr[:200]}")
        return result.stdout
    except FileNotFoundError:
        raise RuntimeError("未找到 git 命令，请确认已安装 Git")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"git 命令超时（{timeout}s）")
    except Exception as e:
        raise RuntimeError(f"git 命令执行失败: {e}")


def get_commits(repo_path: str, since_date: Optional[str] = None,
                until_date: Optional[str] = None, limit: int = 200) -> list[dict]:
    """获取仓库的提交记录

    Args:
        repo_path: 仓库路径
        since_date: 起始日期 YYYY-MM-DD（包含）
        until_date: 截止日期 YYYY-MM-DD（包含）
        limit: 最多返回多少条
    """
    args = ["log", f"--format={_LOG_FORMAT}"]
    if since_date:
        args.append(f"--since={since_date} 00:00:00")
    if until_date:
        args.append(f"--until={until_date} 23:59:59")
    args.append(f"-n{limit}")

    output = _run_git(repo_path, args)

    commits = []
    for record in output.split("\x1e"):
        record = record.strip("\n")
        if not record:
            continue
        fields = record.split("\x1f")
        if len(fields) < 8:
            continue
        try:
            commits.append({
                "hash": fields[0],
                "author_name": fields[1],
                "author_email": fields[2],
                "author_date": fields[3],
                "committer_name": fields[4],
                "committer_date": fields[5],
                "subject": fields[6],
                "body": fields[7],
            })
        except Exception:
            continue

    return commits


def get_diff_stat(repo_path: str, since_date: str, until_date: str) -> dict:
    """获取日期范围内的文件变更统计"""
    args = [
        "log", f"--since={since_date} 00:00:00",
        f"--until={until_date} 23:59:59",
        "--numstat", "--format=%H",
    ]
    try:
        output = _run_git(repo_path, args, timeout=15)
    except Exception as e:
        return {"error": str(e), "files_changed": 0, "insertions": 0, "deletions": 0}

    files_set: set[str] = set()
    total_ins, total_del = 0, 0
    by_extension: dict[str, dict] = {}

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        # 格式：insertions\tdeletions\tfilepath
        parts = line.split("\t")
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            ins, dels, fpath = int(parts[0]), int(parts[1]), parts[2]
            files_set.add(fpath)
            total_ins += ins
            total_del += dels
            ext = Path(fpath).suffix.lower() or "(no_ext)"
            if ext not in by_extension:
                by_extension[ext] = {"files": 0, "insertions": 0, "deletions": 0}
            by_extension[ext]["files"] += 1
            by_extension[ext]["insertions"] += ins
            by_extension[ext]["deletions"] += dels

    return {
        "files_changed": len(files_set),
        "insertions": total_ins,
        "deletions": total_del,
        "by_extension": dict(sorted(by_extension.items(),
                                    key=lambda x: x[1]["insertions"] + x[1]["deletions"],
                                    reverse=True)[:10]),
    }


# ── 关键词提取 ──

_COMMIT_TYPE_RE = re.compile(
    r"^(feat|fix|refactor|docs|test|chore|perf|style|build|ci|revert|wip)"
    r"(\([^)]+\))?\s*:\s*(.+)$",
    re.IGNORECASE
)

def _classify_commit(subject: str) -> tuple[str, str]:
    """从 commit subject 推断类型（feat/fix/...）和描述"""
    m = _COMMIT_TYPE_RE.match(subject)
    if m:
        return m.group(1).lower(), m.group(3).strip()
    # 无前缀的提交，尝试关键词匹配
    s_lower = subject.lower()
    if any(k in s_lower for k in ("修复", "fix", "bug")):
        return "fix", subject
    if any(k in s_lower for k in ("新增", "添加", "add", "feature")):
        return "feat", subject
    if any(k in s_lower for k in ("重构", "refactor")):
        return "refactor", subject
    if any(k in s_lower for k in ("文档", "doc", "readme")):
        return "docs", subject
    return "other", subject


def aggregate_daily_commits(commits: list[dict]) -> dict:
    """按日聚合一组提交记录，返回统计摘要"""
    by_date: dict[str, list[dict]] = {}
    by_type: dict[str, int] = {}
    authors: dict[str, int] = {}

    for c in commits:
        # 提取日期部分
        d_str = c.get("author_date", "")
        date_key = d_str[:10] if len(d_str) >= 10 else "unknown"
        by_date.setdefault(date_key, []).append(c)

        author = c.get("author_name", "unknown")
        authors[author] = authors.get(author, 0) + 1

        ctype, _ = _classify_commit(c.get("subject", ""))
        by_type[ctype] = by_type.get(ctype, 0) + 1

    return {
        "total_commits": len(commits),
        "active_days": len([d for d in by_date if d != "unknown"]),
        "by_date": {k: len(v) for k, v in sorted(by_date.items())},
        "by_type": by_type,
        "authors": authors,
    }


def generate_code_report(target_date: Optional[str] = None) -> dict:
    """生成指定日期的代码产出报告

    Args:
        target_date: YYYY-MM-DD，默认今天
    """
    if not target_date:
        target_date = date.today().isoformat()

    repos = list_repositories()
    enabled_repos = [r for r in repos if r.get("enabled", True) and r.get("has_git")]

    if not enabled_repos:
        return {
            "date": target_date,
            "repositories": [],
            "total_commits": 0,
            "total_files_changed": 0,
            "total_insertions": 0,
            "total_deletions": 0,
            "summary": "未配置 git 仓库或仓库不可用",
        }

    repo_reports = []
    total_commits = 0
    total_files = 0
    total_ins = 0
    total_del = 0

    for repo in enabled_repos:
        path = repo["path"]
        try:
            commits = get_commits(path, since_date=target_date, until_date=target_date, limit=100)
            diff_stat = get_diff_stat(path, target_date, target_date)

            # 错误情况：diff_stat 含 error 字段
            if "error" in diff_stat:
                files_changed = 0
                insertions = 0
                deletions = 0
            else:
                files_changed = diff_stat.get("files_changed", 0)
                insertions = diff_stat.get("insertions", 0)
                deletions = diff_stat.get("deletions", 0)

            # 提取主题列表（用于报告）
            subjects = [c.get("subject", "") for c in commits]

            repo_reports.append({
                "name": repo.get("name", Path(path).name),
                "path": path,
                "commit_count": len(commits),
                "files_changed": files_changed,
                "insertions": insertions,
                "deletions": deletions,
                "subjects": subjects[:20],  # 限制最多 20 条
                "by_extension": diff_stat.get("by_extension", {}),
                "error": diff_stat.get("error"),
            })

            total_commits += len(commits)
            total_files += files_changed
            total_ins += insertions
            total_del += deletions

        except Exception as e:
            repo_reports.append({
                "name": repo.get("name", Path(path).name),
                "path": path,
                "error": str(e)[:200],
                "commit_count": 0,
                "files_changed": 0,
                "insertions": 0,
                "deletions": 0,
                "subjects": [],
            })

    return {
        "date": target_date,
        "repositories": repo_reports,
        "total_commits": total_commits,
        "total_files_changed": total_files,
        "total_insertions": total_ins,
        "total_deletions": total_del,
        "summary": f"今日提交 {total_commits} 次，修改 {total_files} 个文件，+{total_ins}/-{total_del} 行",
    }


def generate_weekly_code_report(end_date: Optional[str] = None) -> dict:
    """生成最近 7 天的代码产出汇总"""
    if not end_date:
        end_date = date.today().isoformat()
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    start_date = (end_dt - timedelta(days=6)).isoformat()

    repos = list_repositories()
    enabled_repos = [r for r in repos if r.get("enabled", True) and r.get("has_git")]

    all_commits: list[dict] = []
    for repo in enabled_repos:
        try:
            commits = get_commits(repo["path"], since_date=start_date, until_date=end_date, limit=500)
            for c in commits:
                c["_repo"] = repo.get("name", Path(repo["path"]).name)
            all_commits.extend(commits)
        except Exception:
            continue

    aggregate = aggregate_daily_commits(all_commits)
    aggregate["start_date"] = start_date
    aggregate["end_date"] = end_date
    aggregate["repositories_count"] = len(enabled_repos)
    return aggregate

"""
P251-P259: 版本控制系统
- P251: 仓库管理
- P252: 提交历史
- P253: 分支管理
- P254: 合并策略
- P255: 变更集
- P256: 标签管理
- P257: 差异比较
- P258: 暂存区
- P259: 冲突标记
"""
import logging
import threading
import hashlib
from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── P251: 仓库管理 ──────────────────────────
class Repository:
    """版本控制仓库"""
    def __init__(self, name: str):
        self.name = name
        self._commits: dict[str, dict] = {}
        self._branches: dict[str, str] = {"main": ""}
        self._head: str = "main"
        self._files: dict[str, dict] = {}
        self._lock = threading.Lock()

    def get_head(self) -> str:
        return self._branches.get(self._head, "")

    def get_branch(self) -> str:
        return self._head


_repo = Repository("default")


# ─── P252: 提交历史 ──────────────────────────
class CommitManager:
    """提交管理"""
    def __init__(self, repo: Repository):
        self.repo = repo

    def commit(self, message: str, author: str = "",
               files: dict = None, parent: str = "") -> str:
        import uuid
        commit_id = hashlib.sha256(
            f"{message}{author}{datetime.now().isoformat()}{parent}".encode()
        ).hexdigest()[:12]
        with self.repo._lock:
            parent_id = parent or self.repo.get_head()
            commit = {
                "id": commit_id, "message": message, "author": author,
                "parent": parent_id, "files": files or {},
                "timestamp": datetime.now().isoformat()
            }
            self.repo._commits[commit_id] = commit
            self.repo._branches[self.repo._head] = commit_id
        return commit_id

    def get_commit(self, commit_id: str) -> dict | None:
        with self.repo._lock:
            return self.repo._commits.get(commit_id)

    def get_log(self, limit: int = 50) -> list[dict]:
        with self.repo._lock:
            log = []
            current = self.repo.get_head()
            while current and len(log) < limit:
                commit = self.repo._commits.get(current)
                if not commit:
                    break
                log.append(commit)
                current = commit.get("parent")
            return log


_commit_mgr = CommitManager(_repo)


# ─── P253: 分支管理 ──────────────────────────
class BranchManager:
    """分支管理"""
    def __init__(self, repo: Repository):
        self.repo = repo

    def create(self, name: str, from_commit: str = "") -> bool:
        with self.repo._lock:
            if name in self.repo._branches:
                return False
            self.repo._branches[name] = from_commit or self.repo.get_head()
            return True

    def switch(self, name: str) -> bool:
        with self.repo._lock:
            if name not in self.repo._branches:
                return False
            self.repo._head = name
            return True

    def delete(self, name: str) -> bool:
        with self.repo._lock:
            if name == "main" or name == self.repo._head:
                return False
            return self.repo._branches.pop(name, None) is not None

    def list_branches(self) -> dict:
        with self.repo._lock:
            return {k: v for k, v in self.repo._branches.items()}


_branch_mgr = BranchManager(_repo)


# ─── P254: 合并策略 ──────────────────────────
class MergeStrategy:
    """合并策略"""
    @staticmethod
    def merge(repo: Repository, source: str, target: str = "") -> dict:
        target = target or repo._head
        with repo._lock:
            source_head = repo._branches.get(source)
            target_head = repo._branches.get(target)
        if not source_head:
            return {"status": "error", "error": "源分支不存在"}
        # 简单合并: 将源分支头部设为目标分支头部
        merge_commit = _commit_mgr.commit(
            f"Merge {source} into {target}", "system",
            parent=target_head
        )
        with repo._lock:
            repo._branches[target] = merge_commit
        return {"status": "ok", "merge_commit": merge_commit}


# ─── P255: 变更集 ──────────────────────────
class ChangeSet:
    """变更集"""
    def __init__(self):
        self._changes: deque = deque(maxlen=500)

    def record(self, file_path: str, change_type: str,
               old_content: str = "", new_content: str = "") -> dict:
        import difflib
        diff = list(difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{file_path}", tofile=f"b/{file_path}"
        )) if old_content or new_content else []
        change = {
            "file": file_path, "type": change_type,
            "added": len(new_content) - len(old_content),
            "diff": "".join(diff[:100]),
            "timestamp": datetime.now().isoformat()
        }
        self._changes.append(change)
        return change

    def get_recent(self, limit: int = 20) -> list[dict]:
        changes = list(self._changes)
        changes.reverse()
        return changes[:limit]


_changeset = ChangeSet()


# ─── P256: 标签管理 ──────────────────────────
class TagManager:
    """标签管理"""
    def __init__(self, repo: Repository):
        self.repo = repo
        self._tags: dict[str, dict] = {}

    def create(self, name: str, commit_id: str = "",
               message: str = "") -> bool:
        with self.repo._lock:
            commit_id = commit_id or self.repo.get_head()
            if not commit_id:
                return False
            self._tags[name] = {
                "commit": commit_id, "message": message,
                "created_at": datetime.now().isoformat()
            }
            return True

    def delete(self, name: str) -> bool:
        return self._tags.pop(name, None) is not None

    def list_tags(self) -> dict:
        return dict(self._tags)


_tag_mgr = TagManager(_repo)


# ─── P257: 差异比较 ──────────────────────────
class DiffEngine:
    """差异比较引擎"""
    @staticmethod
    def diff_files(file1_content: str, file2_content: str,
                   name1: str = "a", name2: str = "b") -> dict:
        import difflib
        lines1 = file1_content.splitlines(keepends=True)
        lines2 = file2_content.splitlines(keepends=True)
        diff = list(difflib.unified_diff(lines1, lines2, fromfile=name1, tofile=name2))
        sm = difflib.SequenceMatcher(None, lines1, lines2)
        return {
            "diff": "".join(diff),
            "ratio": round(sm.ratio(), 3),
            "added": sum(1 for l in diff if l.startswith("+") and not l.startswith("+++")),
            "removed": sum(1 for l in diff if l.startswith("-") and not l.startswith("---")),
        }

    @staticmethod
    def diff_commits(repo: Repository, commit1: str, commit2: str) -> dict:
        with repo._lock:
            c1 = repo._commits.get(commit1, {})
            c2 = repo._commits.get(commit2, {})
        files1 = c1.get("files", {})
        files2 = c2.get("files", {})
        all_files = set(files1.keys()) | set(files2.keys())
        diffs = {}
        for f in all_files:
            diffs[f] = DiffEngine.diff_files(
                files1.get(f, ""), files2.get(f, ""), f"a/{f}", f"b/{f}"
            )
        return {"commit1": commit1, "commit2": commit2, "file_diffs": diffs}


_diff_engine = DiffEngine()


# ─── P258: 暂存区 ──────────────────────────
class StagingArea:
    """暂存区"""
    def __init__(self):
        self._staged: dict[str, str] = {}
        self._lock = threading.Lock()

    def add(self, file_path: str, content: str) -> None:
        with self._lock:
            self._staged[file_path] = content

    def remove(self, file_path: str) -> bool:
        with self._lock:
            return self._staged.pop(file_path, None) is not None

    def get_staged(self) -> dict:
        with self._lock:
            return dict(self._staged)

    def clear(self) -> None:
        with self._lock:
            self._staged.clear()

    def commit_staged(self, message: str, author: str = "") -> str:
        with self._lock:
            files = dict(self._staged)
            self._staged.clear()
        return _commit_mgr.commit(message, author, files)


_staging = StagingArea()


# ─── P259: 冲突标记 ──────────────────────────
class ConflictMarker:
    """冲突标记与解决"""
    @staticmethod
    def mark_conflict(content1: str, content2: str,
                      label1: str = "ours", label2: str = "theirs") -> str:
        return f"<<<<<<< {label1}\n{content1}\n=======\n{content2}\n>>>>>>> {label2}\n"

    @staticmethod
    def detect_conflicts(content: str) -> list[dict]:
        conflicts = []
        lines = content.split("\n")
        i = 0
        while i < len(lines):
            if lines[i].startswith("<<<<<<<"):
                start = i
                ours = []
                theirs = []
                i += 1
                while i < len(lines) and not lines[i].startswith("======="):
                    ours.append(lines[i])
                    i += 1
                i += 1  # skip =======
                while i < len(lines) and not lines[i].startswith(">>>>>>>"):
                    theirs.append(lines[i])
                    i += 1
                conflicts.append({
                    "start_line": start, "end_line": i,
                    "ours": "\n".join(ours),
                    "theirs": "\n".join(theirs)
                })
            i += 1
        return conflicts

    @staticmethod
    def resolve(content: str, resolution: str = "ours") -> str:
        conflicts = ConflictMarker.detect_conflicts(content)
        for c in conflicts:
            marker = ConflictMarker.mark_conflict(c["ours"], c["theirs"])
            resolved = c["ours"] if resolution == "ours" else c["theirs"] if resolution == "theirs" else c["ours"]
            content = content.replace(marker, resolved)
        return content


_conflict_marker = ConflictMarker()

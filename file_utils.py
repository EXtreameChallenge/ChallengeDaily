"""
ChallengeDaily Windows 版 — 原子文件写入 + 数据备份
企业级：崩溃安全、自动备份
"""
import os
import shutil
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8"):
    """
    原子写入文本文件：写入临时文件后 os.replace() 原子替换。
    防止崩溃时文件损坏。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp_path.write_text(content, encoding=encoding)
        os.replace(str(tmp_path), str(path))
    except Exception:
        # 清理临时文件
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def atomic_write_bytes(path: Path, data: bytes):
    """
    原子写入二进制文件：写入临时文件后 os.replace() 原子替换。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp_path.write_bytes(data)
        os.replace(str(tmp_path), str(path))
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def backup_file(path: Path, max_backups: int = 3):
    """
    将文件备份为 .bak.1, .bak.2, ...（循环覆盖）
    在覆盖性写入前调用，防止数据丢失。
    """
    path = Path(path)
    if not path.exists():
        return
    backup_dir = path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    # 滚动备份：.bak.3 → .bak.2, .bak.2 → .bak.1, 新 → .bak.1
    for i in range(max_backups - 1, 0, -1):
        older = backup_dir / f"{path.name}.bak.{i + 1}"
        newer = backup_dir / f"{path.name}.bak.{i}"
        if newer.exists():
            try:
                shutil.move(str(newer), str(older))
            except Exception:
                pass

    latest = backup_dir / f"{path.name}.bak.1"
    try:
        shutil.copy2(str(path), str(latest))
    except Exception as e:
        logger.warning(f"备份文件失败 {path}: {e}")


def auto_backup_critical_files(data_dir: Path):
    """
    定时备份关键数据文件（由 main.py 调用）。
    """
    critical_files = [
        data_dir / "xiaohei.db",
        data_dir / "settings.json",
        data_dir / "vault.dat",
        data_dir / "webhooks.json",
        data_dir / "auto_report.json",
    ]
    for f in critical_files:
        if f.exists():
            try:
                backup_file(f)
            except Exception:
                pass

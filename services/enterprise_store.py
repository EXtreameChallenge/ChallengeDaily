"""轮10 数据统一层：企业 JSON / 积分 / 模板 / 遥测 / 好友统一落 SQLite。

设计：
- `~/.challenge-daily` 下的企业 JSON 只在轮10迁移时读取一次，迁入主库后移入
  只读归档；运行期所有读写只走 `challengedaily.db`。
- 积分与模板复用 `xiaohei_core` 已有的 `points_ledger` / `template_market`，
  不再维护第二套账本。
- 遥测落 `enterprise_telemetry`，好友落 `enterprise_kv` 的 `friends_data`。
- 迁移前自动生成 zip 备份；迁移后写 manifest 与行数对账。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import stat
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from config import DATA_DIR, DB_PATH

logger = logging.getLogger(__name__)

HOME_DATA_DIR = Path(
    os.getenv("CHALLENGE_DAILY_HOME_DATA_DIR", str(Path.home() / ".challenge-daily"))
)

# 只迁移这些已知文件；app_lock.json / notifications.json 仍由各自模块管理。
LEGACY_JSON_FILES = (
    "points.json",
    "templates.json",
    "user.json",
    "publisher_accounts.json",
    "wechat.json",
    "mcp_servers.json",
    "student.json",
)
LEGACY_TELEMETRY_FILE = "telemetry.jsonl"
LEGACY_FRIENDS_FILE = "friends.json"

KV_FRIENDS = "friends_data"
KV_MIGRATION_MARKER = "round10_migration_at"
KV_POINTS_MARKER = "round10_points_imported"
KV_TEMPLATES_MARKER = "round10_templates_imported"
KV_TELEMETRY_MARKER = "round10_telemetry_imported"
KV_FRIENDS_MARKER = "round10_friends_imported"


def _conn():
    from db import get_conn
    return get_conn()


def _row_to_dict(row: Any) -> dict:
    if row is None:
        return {}
    return {k: row[k] for k in row.keys()}


def init_enterprise_tables() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS enterprise_kv (
                key         TEXT PRIMARY KEY,
                value       TEXT NOT NULL,
                updated_at  TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS enterprise_telemetry (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                event       TEXT NOT NULL,
                data        TEXT DEFAULT '{}',
                time        REAL NOT NULL,
                created_at  TEXT DEFAULT (datetime('now','localtime'))
            );
            CREATE INDEX IF NOT EXISTS idx_ent_tel_time ON enterprise_telemetry(time);
            """
        )
        conn.commit()


def kv_get(key: str, default: str | None = None) -> str | None:
    init_enterprise_tables()
    with _conn() as conn:
        row = conn.execute("SELECT value FROM enterprise_kv WHERE key=?", (key,)).fetchone()
    if not row:
        return default
    return row["value"]


def kv_set(key: str, value: str) -> None:
    init_enterprise_tables()
    with _conn() as conn:
        conn.execute(
            """INSERT INTO enterprise_kv (key, value, updated_at)
               VALUES (?, ?, datetime('now','localtime'))
               ON CONFLICT(key) DO UPDATE SET value=excluded.value,
               updated_at=datetime('now','localtime')""",
            (key, str(value)),
        )
        conn.commit()


def kv_delete(key: str) -> None:
    init_enterprise_tables()
    with _conn() as conn:
        conn.execute("DELETE FROM enterprise_kv WHERE key=?", (key,))
        conn.commit()


def kv_get_json(key: str, default: Any = None) -> Any:
    raw = kv_get(key)
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def kv_set_json(key: str, value: Any) -> None:
    kv_set(key, json.dumps(value, ensure_ascii=False))


def telemetry_add(event: str, data: dict | None = None, ts: float | None = None) -> None:
    init_enterprise_tables()
    event = str(event or "").strip()
    if not event:
        return
    with _conn() as conn:
        conn.execute(
            "INSERT INTO enterprise_telemetry (event, data, time) VALUES (?,?,?)",
            (event, json.dumps(data or {}, ensure_ascii=False), float(ts or time.time())),
        )
        conn.commit()


def telemetry_events(limit: int = 100) -> list[dict]:
    init_enterprise_tables()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT event, data, time FROM enterprise_telemetry ORDER BY id DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
    out = []
    for row in reversed(rows):
        try:
            payload = json.loads(row["data"] or "{}")
        except Exception:
            payload = {}
        out.append({"event": row["event"], "data": payload, "time": row["time"]})
    return out


def telemetry_count() -> int:
    init_enterprise_tables()
    with _conn() as conn:
        return int(conn.execute("SELECT COUNT(*) c FROM enterprise_telemetry").fetchone()["c"])


def telemetry_clear() -> int:
    init_enterprise_tables()
    with _conn() as conn:
        n = int(conn.execute("SELECT COUNT(*) c FROM enterprise_telemetry").fetchone()["c"])
        conn.execute("DELETE FROM enterprise_telemetry")
        conn.commit()
    return n


def _table_counts() -> dict:
    init_enterprise_tables()
    with _conn() as conn:
        counts = {}
        for table in ("points_ledger", "template_market", "enterprise_kv", "enterprise_telemetry"):
            try:
                counts[table] = int(conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"])
            except Exception:
                counts[table] = 0
        try:
            counts["friends"] = len((kv_get_json(KV_FRIENDS, {}) or {}).get("friends", []))
        except Exception:
            counts["friends"] = 0
    return counts


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_migration_backup() -> Path | None:
    """迁移前备份：主库一致性快照、盐值、home JSON。返回 zip 路径。"""
    backup_dir = DATA_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = backup_dir / f"round10-migration-{ts}.zip"
    files: list[tuple[str, Path]] = []
    snapshot = backup_dir / f".round10-snapshot-{ts}.db"

    if DB_PATH.exists():
        try:
            src = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
            dst = sqlite3.connect(snapshot)
            with dst:
                src.backup(dst)
            src.close()
            dst.close()
            files.append(("challengedaily.db", snapshot))
        except Exception as e:
            logger.warning(f"数据库快照失败，回退为直接复制: {e}")
            try:
                shutil.copy2(DB_PATH, snapshot)
                files.append(("challengedaily.db", snapshot))
            except Exception as e2:
                logger.warning(f"数据库备份失败: {e2}")
    salt = DATA_DIR / "screenshot_salt.bin"
    if salt.exists():
        files.append(("screenshot_salt.bin", salt))
    legacy_salt = Path(os.environ.get("APPDATA", str(Path.home()))) / "challenge-daily" / "backend-data" / "screenshot_salt.bin"
    if legacy_salt.exists() and legacy_salt.resolve() != salt.resolve():
        files.append(("legacy-screenshot_salt.bin", legacy_salt))
    if HOME_DATA_DIR.exists():
        for path in HOME_DATA_DIR.iterdir():
            if path.is_file() and path.name in (
                *LEGACY_JSON_FILES, LEGACY_TELEMETRY_FILE, LEGACY_FRIENDS_FILE
            ):
                files.append((f"home/{path.name}", path))

    manifest = {}
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for arcname, path in files:
                try:
                    zf.write(path, arcname)
                    manifest[arcname] = {"sha256": _hash(path), "size": path.stat().st_size}
                except Exception as e:
                    logger.warning(f"迁移备份 {path} 失败: {e}")
            if manifest:
                zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    finally:
        try:
            snapshot.unlink(missing_ok=True)
        except Exception:
            pass
    return zip_path if manifest else None


def _import_points() -> dict:
    if kv_get(KV_POINTS_MARKER):
        return {"status": "already"}
    path = HOME_DATA_DIR / "points.json"
    if not path.exists():
        kv_set(KV_POINTS_MARKER, "no-file")
        return {"status": "no-file"}
    result = {"status": "ok", "imported": 0, "balance_adjust": 0, "skipped_default": False}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"status": "bad-json", "error": str(e)}
    balance = int(payload.get("balance", 0) or 0)
    ledger = payload.get("ledger", []) or []
    ledger_sum = 0
    from xiaohei_core import init_xiaohei_tables
    init_xiaohei_tables()
    with _conn() as conn:
        for item in ledger:
            try:
                amount = int(item.get("amount", 0) or 0)
            except Exception:
                continue
            if not amount:
                continue
            typ = "credit" if amount > 0 else "debit"
            ts = item.get("time")
            created = datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S") if ts else None
            if created:
                conn.execute(
                    "INSERT INTO points_ledger (type, amount, item, detail, created_at) VALUES (?,?,?,?,?)",
                    (typ, abs(amount), str(item.get("reason") or "legacy"), json.dumps(item, ensure_ascii=False), created),
                )
            else:
                conn.execute(
                    "INSERT INTO points_ledger (type, amount, item, detail) VALUES (?,?,?,?)",
                    (typ, abs(amount), str(item.get("reason") or "legacy"), json.dumps(item, ensure_ascii=False)),
                )
            ledger_sum += amount
            result["imported"] += 1
        # 旧 JSON 的默认 1000 是未初始化展示值，不是真实入账；不迁。
        if not ledger and balance == 1000:
            result["skipped_default"] = True
        elif balance != ledger_sum:
            adjust = balance - ledger_sum
            if adjust:
                typ = "credit" if adjust > 0 else "debit"
                conn.execute(
                    "INSERT INTO points_ledger (type, amount, item, detail) VALUES (?,?,?,?)",
                    (typ, abs(adjust), "legacy_balance_adjust", "从 points.json 余额对平"),
                )
                result["balance_adjust"] = 1
        conn.commit()
    kv_set(KV_POINTS_MARKER, "done")
    return result


def _import_templates() -> dict:
    if kv_get(KV_TEMPLATES_MARKER):
        return {"status": "already"}
    path = HOME_DATA_DIR / "templates.json"
    if not path.exists():
        kv_set(KV_TEMPLATES_MARKER, "no-file")
        return {"status": "no-file"}
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"status": "bad-json", "error": str(e)}
    if not isinstance(items, list):
        return {"status": "bad-shape"}
    from xiaohei_core import init_xiaohei_tables
    init_xiaohei_tables()
    imported = 0
    with _conn() as conn:
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            content = str(item.get("content") or "")
            if not name:
                continue
            exists = conn.execute(
                "SELECT 1 FROM template_market WHERE name=? AND content=?", (name, content)
            ).fetchone()
            if exists:
                continue
            conn.execute(
                "INSERT INTO template_market (name, category, content, downloads, price) VALUES (?,?,?,?,?)",
                (name, str(item.get("category") or "通用"), content, 0, int(item.get("price") or 0)),
            )
            imported += 1
        conn.commit()
    kv_set(KV_TEMPLATES_MARKER, "done")
    return {"status": "ok", "imported": imported}


def _import_telemetry() -> dict:
    if kv_get(KV_TELEMETRY_MARKER):
        return {"status": "already"}
    path = HOME_DATA_DIR / LEGACY_TELEMETRY_FILE
    if not path.exists():
        kv_set(KV_TELEMETRY_MARKER, "no-file")
        return {"status": "no-file"}
    imported = 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        return {"status": "bad-file", "error": str(e)}
    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        telemetry_add(str(item.get("event") or ""), item.get("data") or {}, item.get("time"))
        imported += 1
    kv_set(KV_TELEMETRY_MARKER, "done")
    return {"status": "ok", "imported": imported}


def _import_friends() -> dict:
    if kv_get(KV_FRIENDS_MARKER):
        return {"status": "already"}
    path = HOME_DATA_DIR / LEGACY_FRIENDS_FILE
    if not path.exists():
        kv_set(KV_FRIENDS_MARKER, "no-file")
        return {"status": "no-file"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"status": "bad-json", "error": str(e)}
    if not isinstance(payload, dict):
        return {"status": "bad-shape"}
    kv_set_json(KV_FRIENDS, payload)
    kv_set(KV_FRIENDS_MARKER, "done")
    return {"status": "ok", "friends": len(payload.get("friends", []) or [])}


def _archive_legacy_files() -> list[dict]:
    archive_dir = DATA_DIR / "archives" / "round10-home-json"
    archive_dir.mkdir(parents=True, exist_ok=True)
    moved = []
    names = (*LEGACY_JSON_FILES, LEGACY_TELEMETRY_FILE, LEGACY_FRIENDS_FILE)
    for name in names:
        source = HOME_DATA_DIR / name
        if not source.exists():
            continue
        target = archive_dir / f"{name}.migrated-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        try:
            shutil.move(str(source), str(target))
            try:
                os.chmod(target, stat.S_IREAD)
            except Exception:
                pass
            moved.append({"name": name, "archive": str(target)})
        except Exception as e:
            logger.warning(f"归档 {source} 失败: {e}")
    return moved


def migrate_home_data(backup: bool = True) -> dict:
    """幂等迁移 home JSON 到 SQLite。返回备份路径、前后行数、导入结果。"""
    init_enterprise_tables()
    before = _table_counts()
    legacy_files = [
        name for name in (*LEGACY_JSON_FILES, LEGACY_TELEMETRY_FILE, LEGACY_FRIENDS_FILE)
        if (HOME_DATA_DIR / name).exists()
    ]
    marker = kv_get(KV_MIGRATION_MARKER)
    if marker and not legacy_files:
        return {
            "status": "already-migrated",
            "marker": marker,
            "home": str(HOME_DATA_DIR),
            "counts": before,
        }

    backup_path = create_migration_backup() if backup else None
    results = {
        "points": _import_points(),
        "templates": _import_templates(),
        "telemetry": _import_telemetry(),
        "friends": _import_friends(),
    }
    # 其他企业 JSON 原文保留到 kv，避免演示模块未来接线时丢历史。
    for name in LEGACY_JSON_FILES:
        if name in ("points.json", "templates.json"):
            continue
        path = HOME_DATA_DIR / name
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            kv_set_json(f"legacy:{name}", payload)
            results.setdefault("legacy_kv", []).append(name)
        except Exception as e:
            logger.warning(f"迁移 {name} 到 KV 失败: {e}")
    moved = _archive_legacy_files()
    after = _table_counts()
    manifest = {
        "status": "migrated",
        "at": datetime.now().isoformat(),
        "home": str(HOME_DATA_DIR),
        "data_dir": str(DATA_DIR),
        "backup": str(backup_path) if backup_path else None,
        "before": before,
        "after": after,
        "legacy_files": legacy_files,
        "moved_to_archive": moved,
        "imports": results,
        "points_found": results["points"].get("imported", 0),
        "templates_found": results["templates"].get("imported", 0),
        "friends_found": results["friends"].get("friends", 0),
        "telemetry_found": results["telemetry"].get("imported", 0),
    }
    try:
        (DATA_DIR / "round10-migration.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass
    kv_set(KV_MIGRATION_MARKER, manifest["at"])
    return manifest


def legacy_counts() -> dict:
    """迁移前后对账用的稳定快照。"""
    return {"counts": _table_counts(), "home": str(HOME_DATA_DIR)}

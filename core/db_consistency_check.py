"""数据库一致性校验任务"""
import logging
import sqlite3
from datetime import datetime

logger = logging.getLogger(__name__)

def run_consistency_check(db_path) -> dict:
    """运行数据库一致性校验，返回报告"""
    report = {
        "timestamp": datetime.now().isoformat(),
        "issues": [],
        "stats": {},
        "healthy": True,
    }
    try:
        conn = sqlite3.connect(str(db_path))
        # 1. PRAGMA integrity_check
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            report["issues"].append(f"integrity_check: {integrity}")
            report["healthy"] = False
        # 2. PRAGMA foreign_key_check
        fk_issues = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_issues:
            report["issues"].append(f"foreign_key violations: {len(fk_issues)}")
            report["healthy"] = False
        # 3. 孤儿记录检查（activities 无对应 app_usage）
        orphans = conn.execute("""
            SELECT COUNT(*) FROM activities a
            WHERE NOT EXISTS (SELECT 1 FROM app_usage u WHERE u.app_name = a.app_name)
            AND a.app_name IS NOT NULL
        """).fetchone()[0]
        if orphans > 0:
            report["issues"].append(f"orphan activities: {orphans}")
        # 4. 统计
        for table in ['activities', 'app_usage', 'reports', 'todos', 'habits', 'diaries']:
            try:
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                report["stats"][table] = count
            except Exception:
                report["stats"][table] = -1
        # 5. WAL 文件大小
        import os
        wal_path = str(db_path) + "-wal"
        if os.path.exists(wal_path):
            report["wal_size_mb"] = round(os.path.getsize(wal_path) / 1024 / 1024, 2)
        conn.close()
    except Exception as e:
        report["issues"].append(f"check_error: {e}")
        report["healthy"] = False
    return report

def auto_consistency_check(db_path):
    """定时任务用：运行校验并记录日志"""
    report = run_consistency_check(db_path)
    if report["healthy"]:
        logger.info(f"[ConsistencyCheck] 数据库健康，stats={report['stats']}")
    else:
        logger.warning(f"[ConsistencyCheck] 发现问题: {report['issues']}")
    return report

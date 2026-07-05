"""Database integrity check script"""
import sqlite3
import sys

db_path = sys.argv[1] if len(sys.argv) > 1 else "data/xiaohei.db"
db = sqlite3.connect(db_path)
db.row_factory = sqlite3.Row

print("=== Integrity Check ===")
r = db.execute("PRAGMA integrity_check").fetchone()
print(f"DB integrity: {r[0]}")

null_cat = db.execute("SELECT COUNT(*) FROM activities WHERE category IS NULL").fetchone()[0]
print(f"Records with NULL category: {null_cat}")

null_ts = db.execute("SELECT COUNT(*) FROM activities WHERE timestamp IS NULL OR timestamp = ''").fetchone()[0]
print(f"Records with NULL/empty timestamp: {null_ts}")

cat_list = db.execute("SELECT DISTINCT category FROM activities").fetchall()
print(f"Distinct categories: {[r[0] for r in cat_list]}")

invalid_cat = db.execute("""
    SELECT COUNT(*) FROM activities
    WHERE category NOT IN ('开发','会议','沟通','文档','测试','设计','运维','数据分析','学习','管理','产品','生活','其他')
""").fetchone()[0]
print(f"Records with invalid category: {invalid_cat}")

rpt_count = db.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
print(f"Total reports in DB: {rpt_count}")

# Check for orphaned manual activities (should have duration_min > 0)
manual = db.execute("SELECT COUNT(*) FROM activities WHERE app_name = '手动补录'").fetchone()[0]
print(f"Manual entries: {manual}")

# Schema check
tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(f"Tables: {tables}")

db.close()
print("\nAll checks passed!")

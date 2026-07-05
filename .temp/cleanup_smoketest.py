import sqlite3
conn = sqlite3.connect(r'C:\Users\Challenge\.local\share\TeleAgent\TeleAgent的工作空间\xiaohei-daily\data\xiaohei.db')
# 查看有多少 SmokeTest 记录
count = conn.execute("SELECT COUNT(*) FROM activities WHERE app_name='SmokeTest'").fetchone()[0]
print(f'Before: {count} SmokeTest records')

# 删除所有 SmokeTest 记录
conn.execute("DELETE FROM activities WHERE app_name='SmokeTest'")
conn.commit()

# 也清理 app_usage 中的
count2 = conn.execute("SELECT COUNT(*) FROM app_usage WHERE app_name='SmokeTest'").fetchone()[0]
if count2 > 0:
    conn.execute("DELETE FROM app_usage WHERE app_name='SmokeTest'")
    conn.commit()
    print(f'Deleted {count2} SmokeTest app_usage records')

remaining = conn.execute("SELECT COUNT(*) FROM activities WHERE date(timestamp)='2026-07-05'").fetchone()[0]
print(f'After: {remaining} real activity records remain for today')
conn.close()

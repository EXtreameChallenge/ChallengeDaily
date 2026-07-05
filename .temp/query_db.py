import sqlite3
conn = sqlite3.connect(r'C:\Users\Challenge\.local\share\TeleAgent\TeleAgent的工作空间\xiaohei-daily\data\xiaohei.db')
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT category, COUNT(*) as cnt FROM activities WHERE date(timestamp) = '2026-07-05' GROUP BY category ORDER BY cnt DESC").fetchall()
for r in rows:
    print(f'{r[0]}: {r[1]}')
total = conn.execute("SELECT COUNT(*) as cnt FROM activities WHERE date(timestamp) = '2026-07-05'").fetchone()
print(f'Total: {total[0]}')
conn.close()

import sqlite3
conn = sqlite3.connect(r'C:\Users\Challenge\.local\share\TeleAgent\TeleAgent的工作空间\xiaohei-daily\data\xiaohei.db')
rows = conn.execute("SELECT timestamp FROM activities WHERE date(timestamp)='2026-07-05' ORDER BY timestamp ASC").fetchall()
gaps = []
for i in range(1, len(rows)):
    from datetime import datetime
    prev = datetime.strptime(rows[i-1][0], '%Y-%m-%d %H:%M:%S')
    curr = datetime.strptime(rows[i][0], '%Y-%m-%d %H:%M:%S')
    diff = (curr - prev).total_seconds() / 60
    if diff > 3:
        gaps.append(f'{rows[i-1][0]} -> {rows[i][0]}  [{diff:.0f} min gap]')
print(f'Total records: {len(rows)}')
print(f'Gaps > 3 minutes:')
for g in gaps:
    print(f'  {g}')
conn.close()

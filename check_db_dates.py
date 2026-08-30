import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'data', 'soccer_patterns.db')
conn = sqlite3.connect(db_path)

cursor = conn.execute("SELECT match_date, home_team, away_team FROM matches ORDER BY match_date DESC LIMIT 10")
print("=== 最新 10 場比賽 ===")
for row in cursor.fetchall():
    print(row)

cursor = conn.execute("SELECT MIN(match_date), MAX(match_date), COUNT(*) FROM matches")
print("\n=== 數據範圍 ===")
print(cursor.fetchone())

# 檢查 upcoming matches (冇結果嘅)
cursor = conn.execute("SELECT match_date, home_team, away_team FROM matches WHERE ftr IS NULL ORDER BY match_date LIMIT 10")
print("\n=== 未開始比賽 (upcoming) ===")
rows = cursor.fetchall()
if rows:
    for row in rows:
        print(row)
else:
    print("沒有未開始的比賽")

conn.close()

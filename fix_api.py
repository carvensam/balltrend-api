import re

with open('api.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix simulate endpoint SQL
old_sql = '''    rows = conn.execute("""
        SELECT m.id, m.league, m.home_team, m.away_team, m.match_date,
               f.ah_result, f.ah_line
        FROM matches m
        JOIN features f ON m.id = f.match_id
        WHERE m.ftr IS NOT NULL AND f.ah_result IS NOT NULL
        ORDER BY RANDOM()
        LIMIT ?
    """, (n,)).fetchall()'''

new_sql = '''    rows = conn.execute("""
        SELECT m.id, m.league, m.home_team, m.away_team, m.match_date,
               f.ah_result, o.ah_line
        FROM matches m
        JOIN features f ON m.id = f.match_id
        JOIN odds o ON m.id = o.match_id
        WHERE m.ftr IS NOT NULL AND f.ah_result IS NOT NULL
        ORDER BY RANDOM()
        LIMIT ?
    """, (n,)).fetchall()'''

if old_sql in content:
    content = content.replace(old_sql, new_sql)
    with open('api.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed api.py simulate SQL")
else:
    print("Pattern not found, checking content...")
    # Print lines around simulate
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'simulate' in line or 'ah_result, f.ah_line' in line:
            print(f"Line {i+1}: {line}")

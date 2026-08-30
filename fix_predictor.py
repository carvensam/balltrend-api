with open('predictor.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = '''    df = pd.read_sql_query(f"""
        SELECT m.*, f.*
        FROM matches m
        JOIN features f ON m.id = f.match_id
        WHERE m.id IN ({placeholders})
    """, conn, params=match_ids)'''

new = '''    df = pd.read_sql_query(f"""
        SELECT m.*, f.*, o.ah_line, o.ah_closing_line
        FROM matches m
        JOIN features f ON m.id = f.match_id
        JOIN odds o ON m.id = o.match_id
        WHERE m.id IN ({placeholders})
    """, conn, params=match_ids)'''

if old in content:
    content = content.replace(old, new)
    with open('predictor.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed predictor.py")
else:
    print("Pattern not found")

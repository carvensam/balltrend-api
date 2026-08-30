from database import get_connection
conn = get_connection()
cursor = conn.cursor()
cursor.execute("PRAGMA table_info(features)")
for row in cursor.fetchall():
    print(dict(row))
    print(row)
conn.close()

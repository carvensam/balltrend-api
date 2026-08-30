from database import get_connection
import pandas as pd

conn = get_connection()
df = pd.read_sql_query("SELECT ah_result FROM features WHERE ah_result IS NOT NULL", conn)
print(df['ah_result'].value_counts())
conn.close()

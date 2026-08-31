import os
from database import init_database
from ingest import ingest_all_csvs

init_database()
total = ingest_all_csvs(os.path.join(os.path.dirname(__file__), 'data', 'raw'))
print(f"Ingested: {total}")

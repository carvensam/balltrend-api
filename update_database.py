"""
Update script: Rebuild database with latest data (2526 + 2627 seasons).
Backups old DB, re-ingests all CSVs, re-computes features, re-mines patterns.
"""
import os
import shutil
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'soccer_patterns.db')
BACKUP_PATH = os.path.join(os.path.dirname(__file__), 'data', f'soccer_patterns_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db')

def main():
    print("=" * 60)
    print("BallTrend 數據庫更新程序")
    print("=" * 60)

    # Backup old DB if exists
    if os.path.exists(DB_PATH):
        print(f"\n[備份] 舊數據庫備份到: {BACKUP_PATH}")
        shutil.copy2(DB_PATH, BACKUP_PATH)
        os.remove(DB_PATH)
        print("[備份] 完成，已刪除舊數據庫")

    # Run full pipeline
    from database import init_database
    from ingest import ingest_all_csvs
    from features import compute_all_features
    from miner import run_walkforward_mining

    print("\n[1/4] 初始化新數據庫...")
    init_database()

    print("\n[2/4] 匯入所有 CSV 數據（包括 2526, 2627 新賽季）...")
    raw_dir = os.path.join(os.path.dirname(__file__), 'data', 'raw')
    total = ingest_all_csvs(raw_dir)
    print(f"[2/4] 共匯入 {total} 場比賽")

    print("\n[3/4] 特徵工程...")
    compute_all_features()

    print("\n[4/4] Walk-Forward 規律探勘...")
    run_walkforward_mining(window_size=300, val_size=150, step=150)

    # Verify
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("SELECT MIN(match_date), MAX(match_date), COUNT(*) FROM matches")
    min_date, max_date, count = cursor.fetchone()
    conn.close()

    print("\n" + "=" * 60)
    print("更新完成！")
    print(f"數據範圍: {min_date} 至 {max_date}")
    print(f"總比賽數: {count}")
    print("=" * 60)

if __name__ == '__main__':
    main()

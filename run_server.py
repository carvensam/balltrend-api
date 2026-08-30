"""
Main entry point: initialize database, run pipeline, start API server.
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import init_database
from ingest import ingest_all_csvs
from features import compute_all_features
from miner import run_walkforward_mining, update_pattern_performance


def run_full_pipeline():
    print("=" * 60)
    print("足球盤口規律自動探勘與賽前預測系統 - 後端初始化")
    print("=" * 60)

    # Step 1: Initialize database
    print("\n[1/4] 初始化資料庫...")
    init_database()

    # Step 2: Ingest historical data
    print("\n[2/4] 匯入歷史數據...")
    raw_dir = os.path.join(os.path.dirname(__file__), 'data', 'raw')
    ingest_all_csvs(raw_dir)

    # Step 3: Compute features
    print("\n[3/4] 特徵工程...")
    compute_all_features()

    # Step 4: Mine patterns with Walk-Forward validation
    print("\n[4/4] Walk-Forward 規律探勘...")
    run_walkforward_mining(window_size=300, val_size=150, step=150)

    print("\n" + "=" * 60)
    print("後端初始化完成！")
    print("=" * 60)


if __name__ == '__main__':
    run_full_pipeline()
    print("\n啟動 API 伺服器...")
    from api import app
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

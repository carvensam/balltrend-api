"""
Auto-update module for BallTrend backend.
Downloads latest Football-Data CSVs and updates the database daily.
Runs in a background thread to avoid blocking API requests.
"""
import os
import glob
import threading
import requests
import sqlite3
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# League mapping for Football-Data URLs
LEAGUE_CODES = {
    'F1': 'Ligue_1',
    'F2': 'Ligue_2',
    'SP1': 'La_Liga',
    'SP2': 'La_Liga_2'
}

BASE_URL = 'https://www.football-data.co.uk/mmz4281'
RAW_DIR = os.path.join(os.path.dirname(__file__), 'data', 'raw')
DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'soccer_patterns.db')

# Track last update time
_last_update_time = None
_last_odds_fetch = None
_update_lock = threading.Lock()
_is_updating = False

ODDS_FETCH_COOLDOWN_MINUTES = 30


def get_latest_season_from_db():
    """Get the latest season and date from the database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.execute("SELECT MAX(match_date), season FROM matches ORDER BY match_date DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        if row:
            return row[0], row[1]
    except Exception as e:
        print(f"[AutoUpdate] Error checking DB: {e}")
    return None, None


def download_season(season_code):
    """Download CSVs for a given season code (e.g., '2627')."""
    downloaded = []
    for prefix in LEAGUE_CODES.keys():
        url = f"{BASE_URL}/{season_code}/{prefix}.csv"
        filepath = os.path.join(RAW_DIR, f"{prefix}_{season_code}.csv")
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200 and len(resp.content) > 1000:
                with open(filepath, 'wb') as f:
                    f.write(resp.content)
                downloaded.append(f"{prefix}_{season_code}.csv")
                print(f"[AutoUpdate] Downloaded {prefix}_{season_code}.csv ({len(resp.content)} bytes)")
            else:
                print(f"[AutoUpdate] {prefix}_{season_code} not available or too small (status={resp.status_code})")
        except Exception as e:
            print(f"[AutoUpdate] Error downloading {prefix}_{season_code}: {e}")
    return downloaded


def run_update_pipeline():
    """Run the full update: ingest, features, patterns."""
    global _is_updating
    
    with _update_lock:
        if _is_updating:
            print("[AutoUpdate] Update already in progress, skipping.")
            return
        _is_updating = True
    
    try:
        print("\n" + "=" * 60)
        print("[AutoUpdate] Starting database update pipeline")
        print("=" * 60)
        
        from ingest import ingest_all_csvs
        from features import compute_all_features
        from miner import run_walkforward_mining
        
        print("[AutoUpdate] Ingesting all CSVs...")
        total = ingest_all_csvs(RAW_DIR)
        print(f"[AutoUpdate] Ingested {total} matches")
        
        print("[AutoUpdate] Computing features...")
        compute_all_features()
        
        print("[AutoUpdate] Mining patterns...")
        run_walkforward_mining(window_size=300, val_size=150, step=150)

        print("[AutoUpdate] Fetching live odds...")
        try:
            odds_matches = fetch_live_odds()
            print(f"[AutoUpdate] Fetched odds for {len(odds_matches)} matches")
        except Exception as e:
            print(f"[AutoUpdate] Odds fetch failed (non-fatal): {e}")
        
        # Verify
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.execute("SELECT MAX(match_date), COUNT(*) FROM matches")
        max_date, count = cursor.fetchone()
        conn.close()
        
        global _last_update_time
        _last_update_time = datetime.now()
        
        print(f"[AutoUpdate] Update complete. Latest: {max_date}, Total: {count}")
        print("=" * 60 + "\n")
        
    except Exception as e:
        print(f"[AutoUpdate] Error during update: {e}")
        import traceback
        traceback.print_exc()
    finally:
        with _update_lock:
            _is_updating = False


def fetch_live_odds():
    """Fetch live odds with a cooldown to protect API quota."""
    global _last_odds_fetch
    now = datetime.now()
    if _last_odds_fetch and (now - _last_odds_fetch).total_seconds() < ODDS_FETCH_COOLDOWN_MINUTES * 60:
        print(f"[AutoUpdate] Odds fetch skipped (cooldown, last: {_last_odds_fetch.strftime('%H:%M:%S')})")
        return []
    from odds_fetcher import fetch_all_odds
    matches = fetch_all_odds()
    _last_odds_fetch = now
    return matches


def check_and_update():
    """Check if update is needed and run if so."""
    print("[AutoUpdate] Checking for new data...")
    
    latest_date, latest_season = get_latest_season_from_db()
    today = datetime.now().strftime('%Y-%m-%d')
    
    print(f"[AutoUpdate] DB latest: {latest_date}, season: {latest_season}")
    
    # Determine which seasons to try downloading
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    # European seasons: Aug-May, coded as YY(YY+1)
    # e.g., 2026-2027 season = code '2627'
    if current_month >= 8:
        current_season = f"{str(current_year)[2:]}{str(current_year + 1)[2:]}"
        next_season = f"{str(current_year + 1)[2:]}{str(current_year + 2)[2:]}"
    else:
        current_season = f"{str(current_year - 1)[2:]}{str(current_year)[2:]}"
        next_season = f"{str(current_year)[2:]}{str(current_year + 1)[2:]}"
    
    print(f"[AutoUpdate] Current season code: {current_season}, next: {next_season}")
    
    # Download current and next season (if available)
    downloaded = []
    downloaded.extend(download_season(current_season))
    downloaded.extend(download_season(next_season))
    
    # Also re-download the latest season in case of updates
    if latest_season and latest_season not in [current_season, next_season]:
        print(f"[AutoUpdate] Also checking latest DB season: {latest_season}")
        downloaded.extend(download_season(latest_season))
    
    if downloaded:
        print(f"[AutoUpdate] New/updated files: {downloaded}")
        run_update_pipeline()
    else:
        print("[AutoUpdate] No new CSV data available. Refreshing live odds only...")
        try:
            odds_matches = fetch_live_odds()
            print(f"[AutoUpdate] Refreshed odds for {len(odds_matches)} matches")
        except Exception as e:
            print(f"[AutoUpdate] Odds refresh failed (non-fatal): {e}")
        global _last_update_time
        _last_update_time = datetime.now()


def get_update_status():
    """Return current update status for API."""
    with _update_lock:
        updating = _is_updating
    return {
        'last_update': _last_update_time.isoformat() if _last_update_time else None,
        'is_updating': updating,
        'db_latest_date': get_latest_season_from_db()[0]
    }


# Global scheduler instance
_scheduler = None

def init_scheduler():
    """Initialize and start the background scheduler."""
    global _scheduler
    if _scheduler is not None:
        return
    
    _scheduler = BackgroundScheduler()
    
    # Schedule daily update at HKT 12:00 (UTC 04:00)
    # Hong Kong Time = UTC+8, so HKT 12:00 = UTC 04:00
    _scheduler.add_job(
        check_and_update,
        trigger=CronTrigger(hour=4, minute=0),  # UTC 04:00 = HKT 12:00
        id='daily_data_update',
        name='Daily Football Data Update',
        replace_existing=True
    )
    
    _scheduler.start()
    print("[AutoUpdate] Scheduler started. Daily update at HKT 12:00 (UTC 04:00)")
    
    # Run initial check on startup (non-blocking)
    threading.Thread(target=check_and_update, daemon=True).start()


def shutdown_scheduler():
    """Shutdown the scheduler gracefully."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown()
        _scheduler = None
        print("[AutoUpdate] Scheduler shutdown.")

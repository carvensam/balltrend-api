"""
Data ingestion module.
Reads Football-Data CSV files and populates the SQLite database.
"""

import pandas as pd
import glob
import os
from datetime import datetime
from database import get_connection, init_database


def parse_date(date_str):
    """Parse DD/MM/YYYY to YYYY-MM-DD."""
    if pd.isna(date_str):
        return None
    try:
        return datetime.strptime(str(date_str), '%d/%m/%Y').strftime('%Y-%m-%d')
    except ValueError:
        try:
            return datetime.strptime(str(date_str), '%d/%m/%y').strftime('%Y-%m-%d')
        except ValueError:
            return None


def league_code(filename):
    """Map filename prefix to league name."""
    base = os.path.basename(filename).split('_')[0]
    mapping = {
        'F1': 'Ligue_1',
        'F2': 'Ligue_2',
        'SP1': 'La_Liga',
        'SP2': 'La_Liga_2',
        'N1': 'Eredivisie',
        'B1': 'Belgium_Pro',
        'E0': 'EPL',
        'E1': 'Championship',
        'D1': 'Bundesliga',
        'D2': 'Bundesliga_2',
    }
    return mapping.get(base, base)


# New-format single-file leagues (football-data.co.uk/new/{CODE}.csv)
# These have results but NO Asian handicap columns
# Note: CHI.csv on football-data.co.uk is CHINA's league, not Chile -
# Chile (Chile_A) has no historical data source, live odds only.
NEW_FORMAT_LEAGUES = {
    'BRA': 'Brazil_A',
    'ARG': 'Argentina_A',
    'MEX': 'Mexico_A',
    'USA': 'MLS',
    'JPN': 'JLeague_1',
}


def parse_new_season(season_str):
    """
    Convert Season column to compact code:
    '2019/2020' -> '1920'; '2026' (calendar-year league) -> '2626'.
    """
    s = str(season_str).strip()
    try:
        if '/' in s:
            parts = s.split('/')
            return f"{parts[0].strip()[-2:]}{parts[1].strip()[-2:]}"
        if len(s) >= 4 and s[:4].isdigit():
            return f"{s[2:4]}{s[2:4]}"
    except Exception:
        pass
    return 'unknown'


def ingest_new_format_csv(filepath):
    """
    Ingest a football-data.co.uk/new/ CSV (results only, no AH odds).
    Inserts into matches table only (no odds row), enabling form/H2H
    features for live prediction.
    """
    conn = get_connection()
    cursor = conn.cursor()
    code = os.path.splitext(os.path.basename(filepath))[0].replace('new_', '')
    league = NEW_FORMAT_LEAGUES.get(code)
    if not league:
        conn.close()
        return 0

    df = pd.read_csv(filepath, encoding='utf-8-sig')
    count = 0
    for _, row in df.iterrows():
        if pd.isna(row.get('Date')) or pd.isna(row.get('Home')) or pd.isna(row.get('Away')):
            continue
        match_date = parse_date(row.get('Date'))
        if not match_date:
            continue
        season = parse_new_season(row.get('Season'))
        res = str(row.get('Res', '')).strip().upper()  # H / D / A
        if res not in ('H', 'D', 'A'):
            res = None
        cursor.execute("""
            INSERT OR IGNORE INTO matches
            (league, season, match_date, match_time, home_team, away_team,
             fthg, ftag, ftr, hthg, htag, htr)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
        """, (
            league, season, match_date,
            str(row.get('Time', '')) if pd.notna(row.get('Time')) else None,
            str(row.get('Home', '')).strip(),
            str(row.get('Away', '')).strip(),
            safe_int(row.get('HG')),
            safe_int(row.get('AG')),
            res
        ))
        count += 1
    conn.commit()
    conn.close()
    print(f"[Ingest] {league} (new format): {count} rows processed.")
    return count


def season_code(filename):
    """Extract season code from filename like F1_2324.csv -> 2324."""
    base = os.path.splitext(os.path.basename(filename))[0]
    parts = base.split('_')
    if len(parts) >= 2:
        return parts[1]
    return 'unknown'


def ingest_all_csvs(raw_dir='data/raw'):
    """Ingest all CSV files into the database."""
    init_database()
    conn = get_connection()
    cursor = conn.cursor()

    pattern = os.path.join(raw_dir, '*.csv')
    files = glob.glob(pattern)
    total_matches = 0

    for filepath in files:
        # Route new-format single files (BRA, ARG, ...) to dedicated ingester
        base_name = os.path.basename(filepath)
        if base_name.startswith('new_'):
            total_matches += ingest_new_format_csv(filepath)
            continue

        league = league_code(filepath)
        season = season_code(filepath)
        print(f"[Ingest] Processing {league} {season}...")

        try:
            df = pd.read_csv(filepath)
        except Exception as e:
            print(f"[Ingest] Error reading {filepath}: {e}")
            continue

        # Required columns mapping
        col_map = {
            'Date': 'Date',
            'Time': 'Time',
            'HomeTeam': 'HomeTeam',
            'AwayTeam': 'AwayTeam',
            'FTHG': 'FTHG',
            'FTAG': 'FTAG',
            'FTR': 'FTR',
            'HTHG': 'HTHG',
            'HTAG': 'HTAG',
            'HTR': 'HTR',
            'B365H': 'B365H',
            'B365D': 'B365D',
            'B365A': 'B365A',
            'B365CH': 'B365CH',
            'B365CD': 'B365CD',
            'B365CA': 'B365CA',
        }

        # Optional columns (may not exist in older files)
        optional = {
            'B365>2.5': 'B365_over25',
            'B365<2.5': 'B365_under25',
            'B365C>2.5': 'B365C_over25',
            'B365C<2.5': 'B365C_under25',
            'AHh': 'AHh',
            'B365AHH': 'B365AHH',
            'B365AHA': 'B365AHA',
            'AHCh': 'AHCh',
            'B365CAHH': 'B365CAHH',
            'B365CAHA': 'B365CAHA',
        }

        for _, row in df.iterrows():
            # Skip rows with missing essential data
            if pd.isna(row.get('Date')) or pd.isna(row.get('HomeTeam')) or pd.isna(row.get('AwayTeam')):
                continue

            match_date = parse_date(row.get('Date'))
            if not match_date:
                continue

            # Insert match
            cursor.execute("""
                INSERT OR IGNORE INTO matches 
                (league, season, match_date, match_time, home_team, away_team,
                 fthg, ftag, ftr, hthg, htag, htr)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                league, season, match_date,
                row.get('Time', None),
                str(row.get('HomeTeam', '')),
                str(row.get('AwayTeam', '')),
                safe_int(row.get('FTHG')),
                safe_int(row.get('FTAG')),
                row.get('FTR', None),
                safe_int(row.get('HTHG')),
                safe_int(row.get('HTAG')),
                row.get('HTR', None)
            ))

            cursor.execute("""
                SELECT id FROM matches 
                WHERE league=? AND season=? AND match_date=? AND home_team=? AND away_team=?
            """, (league, season, match_date,
                  str(row.get('HomeTeam', '')), str(row.get('AwayTeam', ''))))
            match_id = cursor.fetchone()[0]

            # Insert odds
            cursor.execute("""
                INSERT OR REPLACE INTO odds
                (match_id, b365h, b365d, b365a, b365ch, b365cd, b365ca,
                 b365_over25, b365_under25, b365c_over25, b365c_under25,
                 ah_line, ah_home_odds, ah_away_odds,
                 ah_closing_line, ah_closing_home_odds, ah_closing_away_odds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                match_id,
                safe_float(row.get('B365H')),
                safe_float(row.get('B365D')),
                safe_float(row.get('B365A')),
                safe_float(row.get('B365CH')),
                safe_float(row.get('B365CD')),
                safe_float(row.get('B365CA')),
                safe_float(row.get('B365>2.5')),
                safe_float(row.get('B365<2.5')),
                safe_float(row.get('B365C>2.5')),
                safe_float(row.get('B365C<2.5')),
                safe_float(row.get('AHh')),
                safe_float(row.get('B365AHH')),
                safe_float(row.get('B365AHA')),
                safe_float(row.get('AHCh')),
                safe_float(row.get('B365CAHH')),
                safe_float(row.get('B365CAHA'))
            ))

            total_matches += 1

        conn.commit()
        print(f"[Ingest] {league} {season}: {len(df)} rows processed.")

    conn.close()
    print(f"[Ingest] Total matches ingested/updated: {total_matches}")
    return total_matches


def safe_int(val):
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def safe_float(val):
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


if __name__ == '__main__':
    ingest_all_csvs()

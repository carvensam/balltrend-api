"""
Feature engineering module (optimized).
Computes form, H2H, odds movement, and AH result labels for all matches.
"""

import pandas as pd
import numpy as np
from database import get_connection


def calculate_ah_result(fthg, ftag, ah_line):
    """
    Calculate Asian Handicap result from the 上盤 perspective.
    Returns: 'upper_win', 'lower_win', 'push', or None.
    """
    if pd.isna(fthg) or pd.isna(ftag) or pd.isna(ah_line):
        return None

    fthg, ftag, ah_line = int(fthg), int(ftag), float(ah_line)

    if ah_line <= 0:
        upper_margin = fthg - ftag
    else:
        upper_margin = ftag - fthg

    line = abs(ah_line)
    frac = round((line % 1) * 100) / 100

    if frac == 0.25 or frac == 0.75:
        lower_line = line - 0.25
        upper_line = line + 0.25

        def result_at_line(margin, check_line):
            if check_line == 0:
                if margin > 0: return 1
                elif margin == 0: return 0
                else: return -1
            else:
                if margin > check_line: return 1
                elif margin == check_line and check_line == int(check_line):
                    return 0
                else:
                    return -1

        lower_res = result_at_line(upper_margin, lower_line)
        upper_res = result_at_line(upper_margin, upper_line)
        avg_res = (lower_res + upper_res) / 2

        if avg_res > 0:
            return 'upper_win'
        elif avg_res < 0:
            return 'lower_win'
        else:
            return 'push'
    else:
        if upper_margin > line:
            return 'upper_win'
        elif upper_margin == line and line == int(line):
            return 'push'
        else:
            return 'lower_win'


def compute_all_features():
    """Compute and store features for all matches in the database."""
    conn = get_connection()

    df = pd.read_sql_query("""
        SELECT m.id, m.league, m.season, m.match_date, m.match_time,
               m.home_team, m.away_team, m.fthg, m.ftag, m.ftr,
               o.ah_line, o.ah_home_odds, o.ah_away_odds,
               o.ah_closing_line, o.ah_closing_home_odds, o.ah_closing_away_odds,
               o.b365_over25, o.b365_under25, o.b365c_over25, o.b365c_under25
        FROM matches m
        JOIN odds o ON m.id = o.match_id
        ORDER BY m.match_date, m.match_time
    """, conn)

    print(f"[Features] Loaded {len(df)} matches for feature engineering.")

    # Calculate AH result
    df['ah_result'] = df.apply(
        lambda r: calculate_ah_result(r['fthg'], r['ftag'], r['ah_line']), axis=1
    )
    df['is_home_favorite'] = (df['ah_line'] <= 0).astype(int)

    # Pre-build team match histories for fast lookups
    df['match_dt'] = pd.to_datetime(df['match_date'])

    # Team records: key -> list of (date, is_home, gf, ga, pts)
    team_records = {}
    for _, row in df.iterrows():
        if pd.isna(row['ftr']):
            continue
        date = row['match_dt']
        league = row['league']
        season = row['season']

        # Home team
        home_key = (row['home_team'], league, season)
        if home_key not in team_records:
            team_records[home_key] = []
        home_pts = 3 if row['ftr'] == 'H' else (1 if row['ftr'] == 'D' else 0)
        team_records[home_key].append((date, True, int(row['fthg'] or 0), int(row['ftag'] or 0), home_pts))

        # Away team
        away_key = (row['away_team'], league, season)
        if away_key not in team_records:
            team_records[away_key] = []
        away_pts = 3 if row['ftr'] == 'A' else (1 if row['ftr'] == 'D' else 0)
        team_records[away_key].append((date, False, int(row['ftag'] or 0), int(row['fthg'] or 0), away_pts))

    # Sort each team's records by date
    for key in team_records:
        team_records[key].sort(key=lambda x: x[0])

    # H2H records: key -> list of (date, ftr)
    h2h_records = {}
    for _, row in df.iterrows():
        if pd.isna(row['ftr']):
            continue
        h2h_key = (row['home_team'], row['away_team'])
        if h2h_key not in h2h_records:
            h2h_records[h2h_key] = []
        h2h_records[h2h_key].append((row['match_dt'], row['ftr']))

    for key in h2h_records:
        h2h_records[key].sort(key=lambda x: x[0])

    # Process each match efficiently
    cursor = conn.cursor()
    processed = 0

    for idx, row in df.iterrows():
        match_id = row['id']
        league = row['league']
        season = row['season']
        match_dt = row['match_dt']
        home_team = row['home_team']
        away_team = row['away_team']

        # Form (last 5)
        home_key = (home_team, league, season)
        home_form = None
        if home_key in team_records:
            prev = [r for r in team_records[home_key] if r[0] < match_dt][-5:]
            if prev:
                games = len(prev)
                gf = sum(r[2] for r in prev)
                ga = sum(r[3] for r in prev)
                pts = sum(r[4] for r in prev)
                home_form = (gf / games, ga / games, pts / games)

        away_key = (away_team, league, season)
        away_form = None
        if away_key in team_records:
            prev = [r for r in team_records[away_key] if r[0] < match_dt][-5:]
            if prev:
                games = len(prev)
                gf = sum(r[2] for r in prev)
                ga = sum(r[3] for r in prev)
                pts = sum(r[4] for r in prev)
                away_form = (gf / games, ga / games, pts / games)

        # Season stats
        home_season = None
        if home_key in team_records:
            prev = [r for r in team_records[home_key] if r[0] < match_dt]
            if prev:
                games = len(prev)
                gf = sum(r[2] for r in prev)
                ga = sum(r[3] for r in prev)
                pts = sum(r[4] for r in prev)
                home_season = (gf / games, ga / games, pts / games)

        away_season = None
        if away_key in team_records:
            prev = [r for r in team_records[away_key] if r[0] < match_dt]
            if prev:
                games = len(prev)
                gf = sum(r[2] for r in prev)
                ga = sum(r[3] for r in prev)
                pts = sum(r[4] for r in prev)
                away_season = (gf / games, ga / games, pts / games)

        # H2H
        h2h_key = (home_team, away_team)
        h2h = (0, 0, 0)
        if h2h_key in h2h_records:
            prev = [r for r in h2h_records[h2h_key] if r[0] < match_dt][-3:]
            hw = sum(1 for r in prev if r[1] == 'H')
            hd = sum(1 for r in prev if r[1] == 'D')
            ha = sum(1 for r in prev if r[1] == 'A')
            h2h = (hw, hd, ha)

        # Odds movement
        ah_line_movement = None
        ah_home_odds_movement = None
        ah_away_odds_movement = None
        ou_movement = None

        if pd.notna(row.get('ah_closing_line')) and pd.notna(row.get('ah_line')):
            ah_line_movement = float(row['ah_closing_line']) - float(row['ah_line'])
        if pd.notna(row.get('ah_closing_home_odds')) and pd.notna(row.get('ah_home_odds')):
            ah_home_odds_movement = float(row['ah_closing_home_odds']) - float(row['ah_home_odds'])
        if pd.notna(row.get('ah_closing_away_odds')) and pd.notna(row.get('ah_away_odds')):
            ah_away_odds_movement = float(row['ah_closing_away_odds']) - float(row['ah_away_odds'])

        ou_open_imp = None
        ou_close_imp = None
        if pd.notna(row.get('b365_over25')) and pd.notna(row.get('b365_under25')):
            try:
                ou_open_imp = 1 / float(row['b365_over25'])
            except:
                pass
        if pd.notna(row.get('b365c_over25')) and pd.notna(row.get('b365c_under25')):
            try:
                ou_close_imp = 1 / float(row['b365c_over25'])
            except:
                pass
        if ou_open_imp and ou_close_imp:
            ou_movement = ou_close_imp - ou_open_imp

        cursor.execute("""
            INSERT OR REPLACE INTO features (
                match_id,
                home_form_gf, home_form_ga, home_form_pts,
                away_form_gf, away_form_ga, away_form_pts,
                home_season_gf, home_season_ga, home_season_pts_avg,
                away_season_gf, away_season_ga, away_season_pts_avg,
                h2h_home_wins, h2h_draws, h2h_away_wins,
                ah_line_movement, ah_home_odds_movement, ah_away_odds_movement,
                ou_25_opening_implied, ou_25_closing_implied, ou_movement,
                is_home_favorite, ah_result
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            match_id,
            home_form[0] if home_form else None,
            home_form[1] if home_form else None,
            home_form[2] if home_form else None,
            away_form[0] if away_form else None,
            away_form[1] if away_form else None,
            away_form[2] if away_form else None,
            home_season[0] if home_season else None,
            home_season[1] if home_season else None,
            home_season[2] if home_season else None,
            away_season[0] if away_season else None,
            away_season[1] if away_season else None,
            away_season[2] if away_season else None,
            h2h[0], h2h[1], h2h[2],
            ah_line_movement,
            ah_home_odds_movement,
            ah_away_odds_movement,
            ou_open_imp,
            ou_close_imp,
            ou_movement,
            int(row['is_home_favorite']) if pd.notna(row['is_home_favorite']) else None,
            row['ah_result']
        ))

        processed += 1
        if processed % 1000 == 0:
            print(f"[Features] Processed {processed} matches...")

    conn.commit()
    conn.close()
    print(f"[Features] Feature engineering complete. {processed} matches processed.")
    return processed


if __name__ == '__main__':
    compute_all_features()

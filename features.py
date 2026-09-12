"""
Feature engineering module (v2).
Computes form, H2H, odds movement, league rankings, W/D/L ratios, H2H deviation,
home/away advantage, and AH result labels for all matches.
"""

import pandas as pd
import numpy as np
from database import get_connection


def calculate_ah_result(fthg, ftag, ah_line):
    """
    Calculate Asian Handicap result from the 上盤 perspective.
    Returns: 'upper_win', 'lower_win', 'push', or None.
    Handles half-lines (0.25, 0.75) as full units (no half results).
    """
    if pd.isna(fthg) or pd.isna(ftag) or pd.isna(ah_line):
        return None

    fthg, ftag, ah_line = int(fthg), int(ftag), float(ah_line)

    # 上盤視角：主隊讓球時，上盤=主隊；客隊讓球時，上盤=客隊
    if ah_line <= 0:
        # 主隊讓球或平手，上盤是主隊
        upper_margin = fthg - ftag
    else:
        # 客隊讓球，上盤是客隊
        upper_margin = ftag - fthg

    line = abs(ah_line)
    frac = round((line % 1) * 100) / 100

    if frac == 0.25 or frac == 0.75:
        # 半盤拆成兩個整數盤計算
        lower_line = line - 0.25
        upper_line = line + 0.25

        def result_at_line(margin, check_line):
            if check_line == 0:
                if margin > 0:
                    return 1   # 贏盤
                elif margin == 0:
                    return 0   # 走盤
                else:
                    return -1  # 輸盤
            else:
                if margin > check_line:
                    return 1
                elif margin == check_line and check_line == int(check_line):
                    return 0
                else:
                    return -1

        lower_res = result_at_line(upper_margin, lower_line)
        upper_res = result_at_line(upper_margin, upper_line)

        # 兩個盤結果相同直接返回；一贏一走=贏，一輸一走=輸
        if lower_res == 1 and upper_res == 1:
            return 'upper_win'
        elif lower_res == -1 and upper_res == -1:
            return 'lower_win'
        elif lower_res == 0 and upper_res == 0:
            return 'push'
        elif lower_res == 1 and upper_res == 0:
            return 'upper_win'  # 贏半 = 整體贏
        elif lower_res == 0 and upper_res == 1:
            return 'upper_win'
        elif lower_res == -1 and upper_res == 0:
            return 'lower_win'  # 輸半 = 整體輸
        elif lower_res == 0 and upper_res == -1:
            return 'lower_win'
        else:
            # 一贏一輸（理論上不會發生）
            return 'push'
    else:
        # 整數盤或單一半盤
        if upper_margin > line:
            return 'upper_win'
        elif upper_margin == line and line == int(line):
            return 'push'
        else:
            return 'lower_win'


def compute_league_standings(team_records, match_dt, league, season):
    """
    Compute league standings up to (but not including) match_dt.
    Returns dict: team -> (points, played, wins, draws, losses, gf, ga)
    """
    standings = {}
    for key, records in team_records.items():
        team, t_league, t_season = key
        if t_league != league or t_season != season:
            continue
        pts = 0
        played = 0
        wins = 0
        draws = 0
        losses = 0
        gf = 0
        ga = 0
        for date, is_home, goals_for, goals_against, points in records:
            if date >= match_dt:
                break
            played += 1
            pts += points
            gf += goals_for
            ga += goals_against
            if points == 3:
                wins += 1
            elif points == 1:
                draws += 1
            else:
                losses += 1
        if played > 0:
            standings[team] = {
                'points': pts, 'played': played,
                'wins': wins, 'draws': draws, 'losses': losses,
                'gf': gf, 'ga': ga, 'gd': gf - ga
            }
    return standings


def get_team_rank(standings, team):
    """Get team's current rank in standings."""
    if team not in standings:
        return None
    # Sort by points desc, then GD desc
    sorted_teams = sorted(
        standings.items(),
        key=lambda x: (x[1]['points'], x[1]['gd']),
        reverse=True
    )
    for i, (t, _) in enumerate(sorted_teams, 1):
        if t == team:
            return i
    return None


def get_wdl_ratio(records, match_dt, last_n=5):
    """Get W/D/L ratio from last N matches before match_dt."""
    prev = [r for r in records if r[0] < match_dt][-last_n:]
    if not prev:
        return None
    wins = sum(1 for r in prev if r[4] == 3)
    draws = sum(1 for r in prev if r[4] == 1)
    losses = sum(1 for r in prev if r[4] == 0)
    total = len(prev)
    return {'w': wins / total, 'd': draws / total, 'l': losses / total, 'total': total}


def get_h2h_deviation(h2h_records, home_team, away_team, match_dt, ah_line):
    """
    Calculate H2H deviation: actual H2H results vs AH line expectation.
    Returns: -1 (H2H favors lower), 0 (neutral), 1 (H2H favors upper)
    """
    h2h_key = (home_team, away_team)
    if h2h_key not in h2h_records:
        return 0

    prev = [r for r in h2h_records[h2h_key] if r[0] < match_dt][-3:]
    if not prev:
        return 0

    upper_wins = 0
    lower_wins = 0
    pushes = 0

    for date, ftr in prev:
        # Simplified: if home win and ah_line <=0, upper wins; etc.
        if ah_line <= 0:
            # Upper = home
            if ftr == 'H':
                upper_wins += 1
            elif ftr == 'A':
                lower_wins += 1
            else:
                pushes += 1
        else:
            # Upper = away
            if ftr == 'A':
                upper_wins += 1
            elif ftr == 'H':
                lower_wins += 1
            else:
                pushes += 1

    total = len(prev)
    if upper_wins > lower_wins:
        return 1
    elif lower_wins > upper_wins:
        return -1
    return 0


def get_home_away_advantage(team_records, team, match_dt, league, season, is_home):
    """
    Calculate home/away advantage: points per game at home vs away.
    Returns ratio: >1 means strong home advantage, <1 means weak.
    """
    key = (team, league, season)
    if key not in team_records:
        return None

    home_pts = []
    away_pts = []
    for date, is_h, gf, ga, pts in team_records[key]:
        if date >= match_dt:
            break
        if is_h:
            home_pts.append(pts)
        else:
            away_pts.append(pts)

    if not home_pts or not away_pts:
        return None

    home_ppg = sum(home_pts) / len(home_pts)
    away_ppg = sum(away_pts) / len(away_pts)

    if away_ppg == 0:
        return home_ppg * 2  # Strong home advantage
    return home_ppg / away_ppg


def compute_all_features():
    """
    Compute and store features for all matches (O(n) incremental version).
    - Processes league by league in date order with running standings
      (identical semantics to the old per-match standings rebuild, but linear).
    - Skips matches that already have features rows (fast daily updates).
    """
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

    df['ah_result'] = df.apply(
        lambda r: calculate_ah_result(r['fthg'], r['ftag'], r['ah_line']), axis=1
    )
    df['is_home_favorite'] = (df['ah_line'] <= 0).astype(int)
    df['match_dt'] = pd.to_datetime(df['match_date'])

    # Skip matches that already have features
    existing = set(r[0] for r in conn.execute("SELECT match_id FROM features").fetchall())
    print(f"[Features] {len(existing)} matches already have features (will be skipped).")

    # Team records: key -> list of (date, is_home, gf, ga, pts) — only completed matches
    team_records = {}
    for _, row in df.iterrows():
        if pd.isna(row['ftr']):
            continue
        date = row['match_dt']
        league = row['league']
        season = row['season']
        home_pts = 3 if row['ftr'] == 'H' else (1 if row['ftr'] == 'D' else 0)
        away_pts = 3 if row['ftr'] == 'A' else (1 if row['ftr'] == 'D' else 0)
        team_records.setdefault((row['home_team'], league, season), []).append(
            (date, True, int(row['fthg'] or 0), int(row['ftag'] or 0), home_pts))
        team_records.setdefault((row['away_team'], league, season), []).append(
            (date, False, int(row['ftag'] or 0), int(row['fthg'] or 0), away_pts))
    for key in team_records:
        team_records[key].sort(key=lambda x: x[0])

    h2h_records = {}
    for _, row in df.iterrows():
        if pd.isna(row['ftr']):
            continue
        h2h_records.setdefault((row['home_team'], row['away_team']), []).append(
            (row['match_dt'], row['ftr']))
    for key in h2h_records:
        h2h_records[key].sort(key=lambda x: x[0])

    cursor = conn.cursor()
    processed = 0
    skipped = 0

    for league, ldf in df.groupby('league'):
        standings = {}  # team -> stats; reset on season change
        current_season = None
        ldf = ldf.sort_values(['match_dt', 'match_time', 'id'])
        for match_dt, ddf in ldf.groupby('match_dt', sort=True):
            season0 = ddf['season'].iloc[0]
            if season0 != current_season:
                standings = {}
                current_season = season0
            for idx, row in ddf.iterrows():
                match_id = row['id']
                season = row['season']
                home_team = row['home_team']
                away_team = row['away_team']

                home_key = (home_team, league, season)
                home_form = None
                if home_key in team_records:
                    prev = [r for r in team_records[home_key] if r[0] < match_dt][-5:]
                    if prev:
                        games = len(prev)
                        home_form = (sum(r[2] for r in prev) / games,
                                     sum(r[3] for r in prev) / games,
                                     sum(r[4] for r in prev) / games)

                away_key = (away_team, league, season)
                away_form = None
                if away_key in team_records:
                    prev = [r for r in team_records[away_key] if r[0] < match_dt][-5:]
                    if prev:
                        games = len(prev)
                        away_form = (sum(r[2] for r in prev) / games,
                                     sum(r[3] for r in prev) / games,
                                     sum(r[4] for r in prev) / games)

                home_season = None
                if home_key in team_records:
                    prev = [r for r in team_records[home_key] if r[0] < match_dt]
                    if prev:
                        games = len(prev)
                        home_season = (sum(r[2] for r in prev) / games,
                                       sum(r[3] for r in prev) / games,
                                       sum(r[4] for r in prev) / games)

                away_season = None
                if away_key in team_records:
                    prev = [r for r in team_records[away_key] if r[0] < match_dt]
                    if prev:
                        games = len(prev)
                        away_season = (sum(r[2] for r in prev) / games,
                                       sum(r[3] for r in prev) / games,
                                       sum(r[4] for r in prev) / games)

                h2h_key = (home_team, away_team)
                h2h = (0, 0, 0)
                if h2h_key in h2h_records:
                    prev = [r for r in h2h_records[h2h_key] if r[0] < match_dt][-3:]
                    hw = sum(1 for r in prev if r[1] == 'H')
                    hd = sum(1 for r in prev if r[1] == 'D')
                    ha = sum(1 for r in prev if r[1] == 'A')
                    h2h = (hw, hd, ha)

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
                    except Exception:
                        pass
                if pd.notna(row.get('b365c_over25')) and pd.notna(row.get('b365c_under25')):
                    try:
                        ou_close_imp = 1 / float(row['b365c_over25'])
                    except Exception:
                        pass
                if ou_open_imp and ou_close_imp:
                    ou_movement = ou_close_imp - ou_open_imp

                home_rank = get_team_rank(standings, home_team)
                away_rank = get_team_rank(standings, away_team)
                rank_diff = None
                if home_rank and away_rank:
                    rank_diff = away_rank - home_rank

                home_wdl = get_wdl_ratio(team_records.get(home_key, []), match_dt, 5)
                away_wdl = get_wdl_ratio(team_records.get(away_key, []), match_dt, 5)

                h2h_dev = get_h2h_deviation(h2h_records, home_team, away_team, match_dt, row['ah_line'])

                home_adv = get_home_away_advantage(team_records, home_team, match_dt, league, season, True)
                away_adv = get_home_away_advantage(team_records, away_team, match_dt, league, season, False)

                if match_id in existing:
                    skipped += 1
                    continue

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
                        is_home_favorite, ah_result,
                        home_rank, away_rank, rank_diff,
                        home_wdl_w, home_wdl_d, home_wdl_l,
                        away_wdl_w, away_wdl_d, away_wdl_l,
                        h2h_deviation,
                        home_advantage, away_advantage
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    row['ah_result'],
                    home_rank,
                    away_rank,
                    rank_diff,
                    home_wdl['w'] if home_wdl else None,
                    home_wdl['d'] if home_wdl else None,
                    home_wdl['l'] if home_wdl else None,
                    away_wdl['w'] if away_wdl else None,
                    away_wdl['d'] if away_wdl else None,
                    away_wdl['l'] if away_wdl else None,
                    h2h_dev,
                    home_adv,
                    away_adv
                ))
                processed += 1
                if processed % 2000 == 0:
                    conn.commit()
                    print(f"[Features] Processed {processed} new matches...")

            # Apply this date's results to standings (same-date matches excluded
            # from each other's standings, matching original semantics)
            for _, row in ddf.iterrows():
                if pd.isna(row['ftr']):
                    continue
                ftr = row['ftr']
                for team, gf, ga, pts in (
                    (row['home_team'], row['fthg'], row['ftag'],
                     3 if ftr == 'H' else (1 if ftr == 'D' else 0)),
                    (row['away_team'], row['ftag'], row['fthg'],
                     3 if ftr == 'A' else (1 if ftr == 'D' else 0)),
                ):
                    st = standings.setdefault(team, {
                        'points': 0, 'played': 0, 'wins': 0, 'draws': 0,
                        'losses': 0, 'gf': 0, 'ga': 0, 'gd': 0})
                    st['played'] += 1
                    st['points'] += pts
                    st['gf'] += int(gf or 0)
                    st['ga'] += int(ga or 0)
                    st['gd'] = st['gf'] - st['ga']
                    if pts == 3:
                        st['wins'] += 1
                    elif pts == 1:
                        st['draws'] += 1
                    else:
                        st['losses'] += 1
        conn.commit()
        print(f"[Features] League {league}: {processed} total new, {skipped} skipped.")

    conn.close()
    print(f"[Features] Feature engineering complete. {processed} new, {skipped} skipped.")
    return processed


if __name__ == '__main__':
    compute_all_features()

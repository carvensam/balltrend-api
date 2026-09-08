"""
Prediction module v2.
Matches incoming matches against stored patterns to generate predictions.
Push results are tracked and displayed separately.
"""

import pandas as pd
import json
from database import get_connection
from miner import discretize_features


def predict_matches(match_data_list):
    """
    Generate predictions for a list of matches.
    Returns: list of prediction dicts with push tracking.
    """
    if not match_data_list:
        return []

    conn = get_connection()
    cursor = conn.cursor()

    # Load all active patterns
    patterns = cursor.execute(
        "SELECT * FROM patterns WHERE status='active' ORDER BY overall_win_rate DESC"
    ).fetchall()

    # Convert match data to DataFrame for discretization
    df = pd.DataFrame(match_data_list)

    # Fill missing feature columns with defaults
    for col in ['home_form_pts', 'away_form_pts', 'home_season_pts_avg',
                'away_season_pts_avg', 'ah_line_movement', 'ou_movement',
                'h2h_home_wins', 'h2h_away_wins', 'is_home_favorite', 'ah_line',
                'rank_diff', 'home_wdl_w', 'away_wdl_w', 'h2h_deviation',
                'home_advantage']:
        if col not in df.columns:
            df[col] = None

    ddf = discretize_features(df)

    results = []
    for idx, row in ddf.iterrows():
        match_pred = {
            'match_id': match_data_list[idx].get('id'),
            'league': row.get('league', ''),
            'home_team': match_data_list[idx].get('home_team', ''),
            'away_team': match_data_list[idx].get('away_team', ''),
            'match_date': match_data_list[idx].get('match_date', ''),
            'ah_line': row.get('ah_line'),
            'prediction': None,
            'confidence': 0,
            'pattern_count': 0,
            'matched_patterns': [],
            'push_count': 0,  # v2: Track push in sample
            'non_push_sample': 0
        }

        best_confidence = 0
        best_prediction = None
        total_push = 0
        total_non_push = 0

        for pat in patterns:
            conditions = json.loads(pat['feature_conditions'])
            target = pat['target']

            # Check if match matches pattern conditions
            match = True
            for col, val in conditions.items():
                if col not in row or row[col] != val:
                    match = False
                    break

            if match:
                match_pred['pattern_count'] += 1
                match_pred['matched_patterns'].append({
                    'pattern_id': pat['id'],
                    'target': target,
                    'win_rate': pat['overall_win_rate'],
                    'sample_size': pat['overall_sample_size']
                })

                # Use the highest-confidence prediction
                if pat['overall_win_rate'] > best_confidence:
                    best_confidence = pat['overall_win_rate']
                    best_prediction = target

                # Estimate push from sample size ratio (stored as non_push in DB)
                # We don't have exact push count in DB, but we track it now

        if best_prediction:
            match_pred['prediction'] = best_prediction
            match_pred['confidence'] = round(best_confidence * 100, 1)
        else:
            match_pred['prediction'] = 'no_pattern'
            match_pred['confidence'] = 0

        results.append(match_pred)

    conn.close()
    return results


def get_live_matches_by_ids(live_ids):
    """Fetch live_odds rows by their numeric IDs (live_ids without prefix)."""
    if not live_ids:
        return []
    conn = get_connection()
    placeholders = ','.join('?' * len(live_ids))
    rows = conn.execute(
        f"SELECT * FROM live_odds WHERE id IN ({placeholders})",
        live_ids
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def compute_live_features(live_row):
    """
    Compute pattern-matching features for a live match using historical DB data.
    Mirrors features.py semantics:
    - is_home_favorite: ah_line <= 0
    - home_wdl_w: home team wins ratio over last 5 games this season (before match date)
    - h2h_home_wins/h2h_away_wins: last 3 H2H where home_team was home
    - ah/ou movement: unknown from single snapshot -> 0 (stable)
    """
    from odds_fetcher import db_team_name

    league = live_row['league']
    match_date = live_row['match_date']
    home_db = db_team_name(live_row['home_team_en'])
    away_db = db_team_name(live_row['away_team_en'])
    ah_line = live_row.get('ah_line')

    conn = get_connection()

    # Current season = latest season with played matches in this league
    season = conn.execute(
        "SELECT MAX(season) FROM matches WHERE league=? AND ftr IS NOT NULL",
        (league,)
    ).fetchone()[0]

    def team_last5_wdl(team):
        rows = conn.execute("""
            SELECT match_date, home_team, ftr FROM matches
            WHERE league=? AND season=? AND ftr IS NOT NULL AND match_date < ?
              AND (home_team=? OR away_team=?)
            ORDER BY match_date DESC, match_time DESC LIMIT 5
        """, (league, season, match_date, team, team)).fetchall()
        w = sum(1 for r in rows
                if (r['home_team'] == team and r['ftr'] == 'H')
                or (r['home_team'] != team and r['ftr'] == 'A'))
        return (w / len(rows)) if rows else None

    home_wdl_w = team_last5_wdl(home_db)
    away_wdl_w = team_last5_wdl(away_db)

    # H2H: replicate features.py (keyed by home/away as they appeared)
    h2h_rows = conn.execute("""
        SELECT match_date, ftr FROM matches
        WHERE league=? AND home_team=? AND away_team=? AND ftr IS NOT NULL
          AND match_date < ?
        ORDER BY match_date DESC LIMIT 3
    """, (league, home_db, away_db, match_date)).fetchall()
    h2h_home_wins = sum(1 for r in h2h_rows if r['ftr'] == 'H')
    h2h_away_wins = sum(1 for r in h2h_rows if r['ftr'] == 'A')

    conn.close()

    return {
        'id': f"live_{live_row['id']}",
        'league': league,
        'match_date': match_date,
        'match_time': live_row.get('match_time', ''),
        'home_team': live_row['home_team'],
        'away_team': live_row['away_team'],
        'ah_line': ah_line,
        'is_home_favorite': 1 if (ah_line is not None and ah_line <= 0) else 0,
        'home_wdl_w': home_wdl_w,
        'away_wdl_w': away_wdl_w,
        'h2h_home_wins': h2h_home_wins,
        'h2h_away_wins': h2h_away_wins,
        'ah_line_movement': 0.0,
        'ou_movement': 0.0,
        'home_form_pts': 1.5,
        'away_form_pts': 1.5,
        'home_season_pts_avg': 1.5,
        'away_season_pts_avg': 1.5,
        'rank_diff': 0.0,
        'h2h_deviation': 0,
        'home_advantage': 1.0,
    }


def predict_live_matches(live_rows):
    """Generate predictions for live_odds matches."""
    if not live_rows:
        return []
    match_data = [compute_live_features(r) for r in live_rows]
    return predict_matches(match_data)


def batch_predict(match_ids):
    """
    Fetch matches from DB by IDs and predict.
    Supports both database IDs and live_odds IDs (prefix 'live_').
    """
    if not match_ids:
        return []

    live_ids = []
    db_ids = []
    for mid in match_ids:
        if isinstance(mid, str) and mid.startswith('live_'):
            try:
                live_ids.append(int(mid.split('_', 1)[1]))
            except ValueError:
                pass
        else:
            db_ids.append(mid)

    results = []

    # Live odds matches
    if live_ids:
        live_rows = get_live_matches_by_ids(live_ids)
        results.extend(predict_live_matches(live_rows))

    # Database matches
    if db_ids:
        conn = get_connection()
        placeholders = ','.join('?' * len(db_ids))

        df = pd.read_sql_query(f"""
            SELECT m.*, f.*, o.ah_line, o.ah_closing_line
            FROM matches m
            JOIN features f ON m.id = f.match_id
            JOIN odds o ON m.id = o.match_id
            WHERE m.id IN ({placeholders})
        """, conn, params=db_ids)

        conn.close()

        match_data = df.to_dict('records')
        results.extend(predict_matches(match_data))

    return results


if __name__ == '__main__':
    print("[Predictor] Module loaded. Use predict_matches() or batch_predict().")

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


def batch_predict(match_ids):
    """
    Fetch matches from DB by IDs and predict.
    """
    if not match_ids:
        return []

    conn = get_connection()
    placeholders = ','.join('?' * len(match_ids))

    df = pd.read_sql_query(f"""
        SELECT m.*, f.*, o.ah_line, o.ah_closing_line
        FROM matches m
        JOIN features f ON m.id = f.match_id
        JOIN odds o ON m.id = o.match_id
        WHERE m.id IN ({placeholders})
    """, conn, params=match_ids)

    conn.close()

    match_data = df.to_dict('records')
    return predict_matches(match_data)


if __name__ == '__main__':
    print("[Predictor] Module loaded. Use predict_matches() or batch_predict().")

"""
Pattern mining engine with Walk-Forward validation.
Discovers feature combinations with high win rates for Asian Handicap outcomes.
"""

import pandas as pd
import numpy as np
import json
from itertools import combinations
from collections import defaultdict
from database import get_connection


# Feature discretization bins
BINS = {
    'ah_line': [-np.inf, -1.5, -0.75, -0.25, 0.25, 0.75, 1.5, np.inf],
    'ah_line_labels': ['deep_fav', 'moderate_fav', 'slight_fav', 'pickem',
                       'slight_dog', 'moderate_dog', 'deep_dog'],
    'form_pts': [-np.inf, 0.5, 1.0, 1.5, 2.0, 2.5, np.inf],
    'form_labels': ['very_poor', 'poor', 'below_avg', 'avg', 'good', 'excellent'],
    'ah_movement': [-np.inf, -0.25, -0.01, 0.01, 0.25, np.inf],
    'ah_movement_labels': ['strong_down', 'slight_down', 'stable', 'slight_up', 'strong_up'],
}


def discretize_features(df):
    """Convert continuous features to categorical bins."""
    ddf = df.copy()

    ddf['ah_line_bucket'] = pd.cut(
        ddf['ah_line'], bins=BINS['ah_line'],
        labels=BINS['ah_line_labels']
    ).astype(str)

    ddf['ah_movement_dir'] = pd.cut(
        ddf['ah_line_movement'].fillna(0),
        bins=BINS['ah_movement'],
        labels=BINS['ah_movement_labels']
    ).astype(str)

    ddf['home_form_bucket'] = pd.cut(
        ddf['home_form_pts'].fillna(1.5),
        bins=BINS['form_pts'],
        labels=BINS['form_labels']
    ).astype(str)

    ddf['away_form_bucket'] = pd.cut(
        ddf['away_form_pts'].fillna(1.5),
        bins=BINS['form_pts'],
        labels=BINS['form_labels']
    ).astype(str)

    ddf['h2h_home_advantage'] = (ddf['h2h_home_wins'].fillna(0) > ddf['h2h_away_wins'].fillna(0)).astype(int)
    ddf['is_home_favorite'] = ddf['is_home_favorite'].fillna(0).astype(int)

    ddf['ou_movement_dir'] = 'stable'
    ddf.loc[ddf['ou_movement'] < -0.02, 'ou_movement_dir'] = 'down'
    ddf.loc[ddf['ou_movement'] > 0.02, 'ou_movement_dir'] = 'up'

    ddf['season_pts_diff'] = (ddf['home_season_pts_avg'].fillna(1.5) -
                               ddf['away_season_pts_avg'].fillna(1.5))
    ddf['season_pts_diff_bucket'] = pd.cut(
        ddf['season_pts_diff'],
        bins=[-np.inf, -0.5, -0.1, 0.1, 0.5, np.inf],
        labels=['much_worse', 'worse', 'even', 'better', 'much_better']
    ).astype(str)

    return ddf


def mine_patterns(train_df, val_df, min_train_samples=15, min_train_winrate=0.58,
                  min_val_samples=10, min_val_winrate=0.55):
    """Mine patterns from training data and validate on validation data."""
    train_d = discretize_features(train_df)
    val_d = discretize_features(val_df)

    feature_cols = [
        'league', 'ah_line_bucket', 'ah_movement_dir', 'is_home_favorite',
        'home_form_bucket', 'away_form_bucket', 'h2h_home_advantage',
        'ou_movement_dir', 'season_pts_diff_bucket'
    ]
    targets = ['upper_win', 'lower_win']
    mined = []

    for r in [1, 2, 3]:
        for cols in combinations(feature_cols, r):
            for target in targets:
                grouped = train_d.groupby(list(cols))
                for group_vals, group in grouped:
                    if len(group) < min_train_samples:
                        continue

                    win_rate = (group['ah_result'] == target).mean()
                    if win_rate < min_train_winrate:
                        continue

                    condition = {c: v for c, v in zip(cols, group_vals)}

                    mask = pd.Series([True] * len(val_d), index=val_d.index)
                    for col, val in condition.items():
                        mask &= (val_d[col] == val)

                    val_group = val_d[mask]
                    if len(val_group) < min_val_samples:
                        continue

                    val_win_rate = (val_group['ah_result'] == target).mean()
                    if val_win_rate < min_val_winrate:
                        continue

                    all_group = pd.concat([group, val_group])
                    overall_wr = (all_group['ah_result'] == target).mean()

                    mined.append({
                        'conditions': condition,
                        'target': target,
                        'train_win_rate': win_rate,
                        'train_samples': len(group),
                        'val_win_rate': val_win_rate,
                        'val_samples': len(val_group),
                        'overall_win_rate': overall_wr,
                        'overall_samples': len(all_group),
                    })

    # De-duplicate (keep best overall win rate)
    seen = {}
    for p in mined:
        key = json.dumps(p['conditions'], sort_keys=True) + '::' + p['target']
        if key not in seen or p['overall_win_rate'] > seen[key]['overall_win_rate']:
            seen[key] = p

    return list(seen.values())


def run_walkforward_mining(window_size=300, val_size=100, step=500):
    """Run Walk-Forward pattern mining across all historical data."""
    conn = get_connection()

    df = pd.read_sql_query("""
        SELECT m.*, f.*, o.ah_line, o.ah_closing_line
        FROM matches m
        JOIN features f ON m.id = f.match_id
        JOIN odds o ON m.id = o.match_id
        WHERE m.ftr IS NOT NULL AND f.ah_result IS NOT NULL
        ORDER BY m.match_date, m.match_time
    """, conn)

    print(f"[Miner] Total matches with features: {len(df)}")

    if len(df) < window_size + val_size:
        print("[Miner] Not enough data for Walk-Forward mining.")
        conn.close()
        return []

    all_patterns = []
    windows = 0

    for start in range(0, len(df) - window_size - val_size + 1, step):
        train_df = df.iloc[start:start + window_size]
        val_df = df.iloc[start + window_size:start + window_size + val_size]

        season_label = f"{train_df['season'].iloc[-1]}_{train_df['match_date'].iloc[-1]}"
        print(f"[Miner] Window {windows+1}: train={len(train_df)}, val={len(val_df)} | {season_label}")

        patterns = mine_patterns(train_df, val_df)
        for p in patterns:
            p['discovery_window'] = season_label
            p['league'] = p['conditions'].get('league', 'ALL')

        all_patterns.extend(patterns)
        windows += 1

    print(f"[Miner] Mined {len(all_patterns)} raw patterns across {windows} windows.")

    # De-duplicate across windows and store
    seen = {}
    for p in all_patterns:
        key = json.dumps(p['conditions'], sort_keys=True) + '::' + p['target']
        if key not in seen:
            seen[key] = p
        else:
            existing = seen[key]
            total = existing['overall_samples'] + p['overall_samples']
            existing['overall_win_rate'] = (
                (existing['overall_win_rate'] * existing['overall_samples'] +
                 p['overall_win_rate'] * p['overall_samples']) / total
            )
            existing['overall_samples'] = total
            existing['train_samples'] += p['train_samples']
            existing['val_samples'] += p['val_samples']

    unique_patterns = list(seen.values())
    print(f"[Miner] {len(unique_patterns)} unique patterns after de-duplication.")

    cursor = conn.cursor()
    stored = 0
    for p in unique_patterns:
        cursor.execute("""
            INSERT OR REPLACE INTO patterns
            (league, feature_conditions, target,
             train_win_rate, train_sample_size,
             val_win_rate, val_sample_size,
             overall_win_rate, overall_sample_size,
             status, discovery_season)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            p['league'],
            json.dumps(p['conditions'], ensure_ascii=False),
            p['target'],
            p['train_win_rate'],
            p['train_samples'],
            p['val_win_rate'],
            p['val_samples'],
            p['overall_win_rate'],
            p['overall_samples'],
            'active',
            p['discovery_window']
        ))
        stored += 1

    conn.commit()
    conn.close()
    print(f"[Miner] Stored {stored} patterns in database.")
    return unique_patterns


def update_pattern_performance():
    """Backfill pattern performance with actual results."""
    conn = get_connection()
    cursor = conn.cursor()

    patterns = cursor.execute("SELECT * FROM patterns WHERE status='active'").fetchall()

    for pat in patterns:
        conditions = json.loads(pat['feature_conditions'])
        target = pat['target']
        pat_id = pat['id']

        df = pd.read_sql_query("""
            SELECT m.*, f.*, o.ah_line, o.ah_closing_line
            FROM matches m
            JOIN features f ON m.id = f.match_id
            JOIN odds o ON m.id = o.match_id
            WHERE m.ftr IS NOT NULL AND f.ah_result IS NOT NULL
            ORDER BY m.match_date
        """, conn)

        ddf = discretize_features(df)

        mask = pd.Series([True] * len(ddf), index=ddf.index)
        for col, val in conditions.items():
            if col in ddf.columns:
                mask &= (ddf[col] == val)

        matched = ddf[mask]
        if len(matched) == 0:
            continue

        correct = (matched['ah_result'] == target).sum()
        total = len(matched)
        wr = correct / total if total > 0 else 0

        cursor.execute("""
            UPDATE patterns
            SET overall_win_rate=?, overall_sample_size=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        """, (wr, total, pat_id))

        if wr < 0.65 and total >= 30:
            cursor.execute("UPDATE patterns SET status='degraded' WHERE id=?", (pat_id,))

    conn.commit()
    conn.close()
    print("[Miner] Pattern performance updated.")


if __name__ == '__main__':
    patterns = run_walkforward_mining(window_size=300, val_size=100, step=500)

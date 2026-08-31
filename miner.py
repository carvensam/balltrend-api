"""
Pattern mining engine v2 with Walk-Forward validation.
Fixes:
- Sample threshold: train >= 50, val >= 25
- Win rate threshold: train >= 60%, val >= 55%
- Multi-window validation: pattern must appear in >= 3 independent windows
- Push excluded from win rate calculation
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

    # v2: Discretize new features
    # Rank diff: positive = home team ranked higher
    ddf['rank_diff_bucket'] = 'unknown'
    ddf.loc[ddf['rank_diff'] <= -5, 'rank_diff_bucket'] = 'away_much_higher'
    ddf.loc[(ddf['rank_diff'] > -5) & (ddf['rank_diff'] < -1), 'rank_diff_bucket'] = 'away_higher'
    ddf.loc[(ddf['rank_diff'] >= -1) & (ddf['rank_diff'] <= 1), 'rank_diff_bucket'] = 'rank_even'
    ddf.loc[(ddf['rank_diff'] > 1) & (ddf['rank_diff'] < 5), 'rank_diff_bucket'] = 'home_higher'
    ddf.loc[ddf['rank_diff'] >= 5, 'rank_diff_bucket'] = 'home_much_higher'

    # WDL ratios
    ddf['home_wdl_bucket'] = 'unknown'
    if 'home_wdl_w' in ddf.columns:
        ddf.loc[ddf['home_wdl_w'] >= 0.6, 'home_wdl_bucket'] = 'strong_win'
        ddf.loc[(ddf['home_wdl_w'] >= 0.4) & (ddf['home_wdl_w'] < 0.6), 'home_wdl_bucket'] = 'moderate_win'
        ddf.loc[(ddf['home_wdl_w'] >= 0.2) & (ddf['home_wdl_w'] < 0.4), 'home_wdl_bucket'] = 'mixed'
        ddf.loc[ddf['home_wdl_w'] < 0.2, 'home_wdl_bucket'] = 'poor'

    ddf['away_wdl_bucket'] = 'unknown'
    if 'away_wdl_w' in ddf.columns:
        ddf.loc[ddf['away_wdl_w'] >= 0.6, 'away_wdl_bucket'] = 'strong_win'
        ddf.loc[(ddf['away_wdl_w'] >= 0.4) & (ddf['away_wdl_w'] < 0.6), 'away_wdl_bucket'] = 'moderate_win'
        ddf.loc[(ddf['away_wdl_w'] >= 0.2) & (ddf['away_wdl_w'] < 0.4), 'away_wdl_bucket'] = 'mixed'
        ddf.loc[ddf['away_wdl_w'] < 0.2, 'away_wdl_bucket'] = 'poor'

    # H2H deviation
    ddf['h2h_dev_bucket'] = ddf['h2h_deviation'].fillna(0).astype(int).astype(str)
    ddf['h2h_dev_bucket'] = ddf['h2h_dev_bucket'].map({'-1': 'favors_lower', '0': 'neutral', '1': 'favors_upper'})

    # Home advantage
    ddf['home_adv_bucket'] = 'unknown'
    if 'home_advantage' in ddf.columns:
        ddf.loc[ddf['home_advantage'] >= 1.5, 'home_adv_bucket'] = 'strong_home'
        ddf.loc[(ddf['home_advantage'] >= 1.0) & (ddf['home_advantage'] < 1.5), 'home_adv_bucket'] = 'moderate_home'
        ddf.loc[(ddf['home_advantage'] >= 0.7) & (ddf['home_advantage'] < 1.0), 'home_adv_bucket'] = 'weak_home'
        ddf.loc[ddf['home_advantage'] < 0.7, 'home_adv_bucket'] = 'no_home'

    return ddf


def calc_win_rate(series, target):
    """
    Calculate win rate excluding pushes.
    win_rate = (wins) / (total - pushes)
    Also returns push_count.
    """
    non_push = series[series != 'push']
    total_non_push = len(non_push)
    if total_non_push == 0:
        return 0.0, 0
    wins = (non_push == target).sum()
    push_count = (series == 'push').sum()
    return wins / total_non_push, push_count


def mine_patterns(train_df, val_df,
                  min_train_samples=50, min_train_winrate=0.60,
                  min_val_samples=25, min_val_winrate=0.55):
    """
    Mine patterns from training data and validate on validation data.
    Push results are excluded from win rate calculation.
    """
    train_d = discretize_features(train_df)
    val_d = discretize_features(val_df)

    feature_cols = [
        'league', 'ah_line_bucket', 'ah_movement_dir', 'is_home_favorite',
        'home_form_bucket', 'away_form_bucket', 'h2h_home_advantage',
        'ou_movement_dir', 'season_pts_diff_bucket',
        # v2 features
        'rank_diff_bucket', 'home_wdl_bucket', 'away_wdl_bucket',
        'h2h_dev_bucket', 'home_adv_bucket'
    ]
    targets = ['upper_win', 'lower_win']
    mined = []

    for r in [1, 2, 3]:
        for cols in combinations(feature_cols, r):
            for target in targets:
                grouped = train_d.groupby(list(cols), observed=False)
                for group_vals, group in grouped:
                    if len(group) < min_train_samples:
                        continue

                    win_rate, push_count = calc_win_rate(group['ah_result'], target)
                    if win_rate < min_train_winrate:
                        continue

                    condition = {c: v for c, v in zip(cols, group_vals)}

                    mask = pd.Series([True] * len(val_d), index=val_d.index)
                    for col, val in condition.items():
                        mask &= (val_d[col] == val)

                    val_group = val_d[mask]
                    if len(val_group) < min_val_samples:
                        continue

                    val_win_rate, val_push_count = calc_win_rate(val_group['ah_result'], target)
                    if val_win_rate < min_val_winrate:
                        continue

                    # Overall: exclude pushes
                    all_group = pd.concat([group, val_group])
                    overall_wr, overall_push = calc_win_rate(all_group['ah_result'], target)

                    mined.append({
                        'conditions': condition,
                        'target': target,
                        'train_win_rate': win_rate,
                        'train_samples': len(group),
                        'train_push_count': push_count,
                        'val_win_rate': val_win_rate,
                        'val_samples': len(val_group),
                        'val_push_count': val_push_count,
                        'overall_win_rate': overall_wr,
                        'overall_samples': len(all_group),
                        'overall_push_count': overall_push,
                    })

    # De-duplicate (keep best overall win rate)
    seen = {}
    for p in mined:
        key = json.dumps(p['conditions'], sort_keys=True) + '::' + p['target']
        if key not in seen or p['overall_win_rate'] > seen[key]['overall_win_rate']:
            seen[key] = p

    return list(seen.values())


def run_walkforward_mining(window_size=300, val_size=150, step=150,
                           min_window_count=3):
    """
    Run Walk-Forward pattern mining across all historical data.
    Patterns must appear in at least min_window_count independent windows.
    """
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
            p['window_index'] = windows + 1

        all_patterns.extend(patterns)
        windows += 1

    print(f"[Miner] Mined {len(all_patterns)} raw patterns across {windows} windows.")

    # Multi-window validation: pattern must appear in >= min_window_count windows
    # Group by condition+target and count unique windows
    pattern_windows = defaultdict(set)
    pattern_best = {}

    for p in all_patterns:
        key = json.dumps(p['conditions'], sort_keys=True) + '::' + p['target']
        pattern_windows[key].add(p['window_index'])

        if key not in pattern_best or p['overall_win_rate'] > pattern_best[key]['overall_win_rate']:
            pattern_best[key] = p

    # Filter: require >= min_window_count independent windows
    validated_patterns = []
    for key, window_set in pattern_windows.items():
        if len(window_set) >= min_window_count:
            p = pattern_best[key]
            p['validation_windows'] = len(window_set)
            p['total_windows'] = windows
            validated_patterns.append(p)

    print(f"[Miner] {len(validated_patterns)} patterns passed multi-window validation (>= {min_window_count} windows).")
    print(f"[Miner] {len(pattern_windows) - len(validated_patterns)} patterns rejected (insufficient windows).")

    # Store in database
    cursor = conn.cursor()
    stored = 0
    for p in validated_patterns:
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
            f"{p['discovery_window']} (validated in {p['validation_windows']}/{p['total_windows']} windows)"
        ))
        stored += 1

    conn.commit()
    conn.close()
    print(f"[Miner] Stored {stored} validated patterns in database.")
    return validated_patterns


def update_pattern_performance():
    """Backfill pattern performance with actual results (push excluded)."""
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

        wr, push_count = calc_win_rate(matched['ah_result'], target)
        total_non_push = len(matched[matched['ah_result'] != 'push'])

        cursor.execute("""
            UPDATE patterns
            SET overall_win_rate=?, overall_sample_size=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        """, (wr, total_non_push, pat_id))

        if wr < 0.60 and total_non_push >= 50:
            cursor.execute("UPDATE patterns SET status='degraded' WHERE id=?", (pat_id,))

    conn.commit()
    conn.close()
    print("[Miner] Pattern performance updated.")


if __name__ == '__main__':
    patterns = run_walkforward_mining(window_size=300, val_size=150, step=150)

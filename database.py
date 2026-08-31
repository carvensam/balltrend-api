"""
Database module for Soccer Odds Pattern Mining System.
Manages SQLite schema for matches, odds, features, patterns, and predictions.
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'soccer_patterns.db')


def get_connection():
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initialize all tables."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
    -- Core match information
    CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        league TEXT NOT NULL,
        season TEXT NOT NULL,
        match_date TEXT,
        match_time TEXT,
        home_team TEXT NOT NULL,
        away_team TEXT NOT NULL,
        fthg INTEGER,
        ftag INTEGER,
        ftr TEXT,
        hthg INTEGER,
        htag INTEGER,
        htr TEXT,
        UNIQUE(league, season, match_date, home_team, away_team)
    );

    -- Opening and closing odds
    CREATE TABLE IF NOT EXISTS odds (
        match_id INTEGER PRIMARY KEY REFERENCES matches(id),
        b365h REAL, b365d REAL, b365a REAL,
        b365ch REAL, b365cd REAL, b365ca REAL,
        b365_over25 REAL, b365_under25 REAL,
        b365c_over25 REAL, b365c_under25 REAL,
        ah_line REAL,
        ah_home_odds REAL,
        ah_away_odds REAL,
        ah_closing_line REAL,
        ah_closing_home_odds REAL,
        ah_closing_away_odds REAL,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    -- Engineered features for pattern mining (v2)
    CREATE TABLE IF NOT EXISTS features (
        match_id INTEGER PRIMARY KEY REFERENCES matches(id),
        -- Form features (last 5 matches)
        home_form_gf REAL,
        home_form_ga REAL,
        home_form_pts REAL,
        away_form_gf REAL,
        away_form_ga REAL,
        away_form_pts REAL,
        -- Season position features
        home_season_gf REAL,
        home_season_ga REAL,
        home_season_pts_avg REAL,
        away_season_gf REAL,
        away_season_ga REAL,
        away_season_pts_avg REAL,
        -- H2H features
        h2h_home_wins INTEGER DEFAULT 0,
        h2h_draws INTEGER DEFAULT 0,
        h2h_away_wins INTEGER DEFAULT 0,
        -- Odds movement features
        ah_line_movement REAL,
        ah_home_odds_movement REAL,
        ah_away_odds_movement REAL,
        ou_25_opening_implied REAL,
        ou_25_closing_implied REAL,
        ou_movement REAL,
        -- Derived classification
        is_home_favorite INTEGER,
        ah_result TEXT,
        -- v2: League rankings
        home_rank INTEGER,
        away_rank INTEGER,
        rank_diff REAL,
        -- v2: W/D/L ratios (last 5)
        home_wdl_w REAL,
        home_wdl_d REAL,
        home_wdl_l REAL,
        away_wdl_w REAL,
        away_wdl_d REAL,
        away_wdl_l REAL,
        -- v2: H2H deviation
        h2h_deviation INTEGER,
        -- v2: Home/away advantage
        home_advantage REAL,
        away_advantage REAL
    );

    -- Discovered patterns with Walk-Forward validation
    CREATE TABLE IF NOT EXISTS patterns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        league TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        feature_conditions TEXT,
        target TEXT,
        train_win_rate REAL,
        train_sample_size INTEGER,
        val_win_rate REAL,
        val_sample_size INTEGER,
        overall_win_rate REAL,
        overall_sample_size INTEGER,
        status TEXT DEFAULT 'active',
        discovery_season TEXT,
        total_predictions INTEGER DEFAULT 0,
        total_correct INTEGER DEFAULT 0
    );

    -- Prediction history
    CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id INTEGER REFERENCES matches(id),
        pattern_id INTEGER REFERENCES patterns(id),
        predicted_at TEXT DEFAULT CURRENT_TIMESTAMP,
        prediction TEXT,
        confidence REAL,
        actual_result TEXT,
        is_correct INTEGER,
        notes TEXT
    );

    -- Daily matches cache (for API)
    CREATE TABLE IF NOT EXISTS daily_matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        league TEXT,
        match_date TEXT,
        match_time TEXT,
        home_team TEXT,
        away_team TEXT,
        ah_line REAL,
        ah_home_odds REAL,
        ah_away_odds REAL,
        ou_line REAL,
        fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_matches_league ON matches(league);
    CREATE INDEX IF NOT EXISTS idx_matches_season ON matches(season);
    CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(match_date);
    CREATE INDEX IF NOT EXISTS idx_patterns_league ON patterns(league);
    CREATE INDEX IF NOT EXISTS idx_patterns_status ON patterns(status);
    """)

    conn.commit()
    conn.close()
    print("[DB] Database initialized at", DB_PATH)


if __name__ == '__main__':
    init_database()

"""
Flask REST API for the Soccer Odds Prediction System.
Provides endpoints for match listing, batch prediction, pattern viewing,
20-match simulation, and auto-update.
"""

import os
import json
import random
import atexit
import threading
from flask import Flask, request, jsonify
from flask_cors import CORS
from database import get_connection
from predictor import predict_matches, batch_predict
from auto_update import init_scheduler, shutdown_scheduler, check_and_update, get_update_status

app = Flask(__name__)
CORS(app)  # Allow cross-origin from Android app

API_VERSION = "v1"

# Initialize auto-update scheduler
init_scheduler()
atexit.register(shutdown_scheduler)


def get_db_matches(league=None, limit=50, has_result=None):
    """Fetch matches from database."""
    conn = get_connection()
    query = """
        SELECT m.id, m.league, m.season, m.match_date, m.match_time,
               m.home_team, m.away_team, m.fthg, m.ftag, m.ftr,
               f.ah_line, f.ah_result, f.is_home_favorite
        FROM matches m
        LEFT JOIN features f ON m.id = f.match_id
        WHERE 1=1
    """
    params = []
    if league:
        query += " AND m.league = ?"
        params.append(league)
    if has_result is not None:
        if has_result:
            query += " AND m.ftr IS NOT NULL"
        else:
            query += " AND m.ftr IS NULL"
    query += " ORDER BY m.match_date DESC, m.match_time DESC LIMIT ?"
    params.append(limit)

    df = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(row) for row in df]


@app.route(f'/api/{API_VERSION}/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'version': API_VERSION})


@app.route(f'/api/{API_VERSION}/leagues', methods=['GET'])
def leagues():
    """Return supported leagues."""
    return jsonify({
        'leagues': [
            {'code': 'Ligue_1', 'name': '法國甲組聯賽'},
            {'code': 'Ligue_2', 'name': '法國乙組聯賽'},
            {'code': 'La_Liga', 'name': '西班牙甲組聯賽'},
            {'code': 'La_Liga_2', 'name': '西班牙乙組聯賽'}
        ]
    })


@app.route(f'/api/{API_VERSION}/matches', methods=['GET'])
def matches():
    """Get matches. Query params: league, limit, upcoming_only."""
    league = request.args.get('league')
    limit = int(request.args.get('limit', 50))
    upcoming_only = request.args.get('upcoming_only', 'false').lower() == 'true'

    conn = get_connection()

    if upcoming_only:
        query = """
            SELECT m.id, m.league, m.season, m.match_date, m.match_time,
                   m.home_team, m.away_team,
                   o.ah_line, o.ah_home_odds, o.ah_away_odds,
                   o.b365_over25, o.b365_under25
            FROM matches m
            JOIN odds o ON m.id = o.match_id
            WHERE m.ftr IS NULL
        """
        params = []
        if league:
            query += " AND m.league = ?"
            params.append(league)
        query += " ORDER BY m.match_date DESC, m.match_time DESC LIMIT ?"
        params.append(limit)
    else:
        query = """
            SELECT m.id, m.league, m.season, m.match_date, m.match_time,
                   m.home_team, m.away_team,
                   o.ah_line, o.ah_home_odds, o.ah_away_odds,
                   o.b365_over25, o.b365_under25
            FROM matches m
            JOIN odds o ON m.id = o.match_id
            WHERE 1=1
        """
        params = []
        if league:
            query += " AND m.league = ?"
            params.append(league)
        query += " ORDER BY m.match_date DESC, m.match_time DESC LIMIT ?"
        params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    result = []
    for r in rows:
        result.append({
            'id': r['id'],
            'league': r['league'],
            'season': r['season'],
            'match_date': r['match_date'],
            'match_time': r['match_time'],
            'home_team': r['home_team'],
            'away_team': r['away_team'],
            'ah_line': r['ah_line'],
            'ah_home_odds': r['ah_home_odds'],
            'ah_away_odds': r['ah_away_odds']
        })

    return jsonify({'matches': result})


@app.route(f'/api/{API_VERSION}/predict', methods=['POST'])
def predict():
    """Batch prediction for selected match IDs."""
    data = request.get_json()
    if not data or 'match_ids' not in data:
        return jsonify({'error': 'match_ids required'}), 400

    match_ids = data['match_ids']
    if len(match_ids) > 20:
        return jsonify({'error': 'Maximum 20 matches allowed'}), 400

    predictions = batch_predict(match_ids)

    # Format for Android app (v2 with push tracking)
    formatted = []
    for p in predictions:
        pred_text = '無高勝率模式，建議觀望'
        if p['prediction'] == 'upper_win':
            pred_text = f'預測上盤勝，歷史勝率 {p["confidence"]}%'
        elif p['prediction'] == 'lower_win':
            pred_text = f'預測下盤勝，歷史勝率 {p["confidence"]}%'

        formatted.append({
            'match_id': p['match_id'],
            'league': p['league'],
            'match_display': f"{p['home_team']} vs {p['away_team']}",
            'ah_line': p['ah_line'],
            'prediction': p['prediction'],
            'prediction_text': pred_text,
            'confidence': p['confidence'],
            'pattern_count': p['pattern_count'],
            'push_count': p.get('push_count', 0)
        })

    return jsonify({'predictions': formatted})


@app.route(f'/api/{API_VERSION}/patterns', methods=['GET'])
def patterns():
    """Get active high-confidence patterns."""
    conn = get_connection()
    league = request.args.get('league')

    query = "SELECT * FROM patterns WHERE status='active'"
    params = []
    if league:
        query += " AND (league=? OR league='ALL')"
        params.append(league)
    query += " ORDER BY overall_win_rate DESC LIMIT 100"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    result = []
    for r in rows:
        result.append({
            'id': r['id'],
            'league': r['league'],
            'conditions': json.loads(r['feature_conditions']),
            'target': r['target'],
            'train_win_rate': r['train_win_rate'],
            'train_sample_size': r['train_sample_size'],
            'val_win_rate': r['val_win_rate'],
            'val_sample_size': r['val_sample_size'],
            'overall_win_rate': r['overall_win_rate'],
            'overall_sample_size': r['overall_sample_size']
        })

    return jsonify({'patterns': result})


@app.route(f'/api/{API_VERSION}/simulate', methods=['GET'])
def simulate():
    """Run a simulation on N random historical matches."""
    n = int(request.args.get('n', 30))
    conn = get_connection()

    rows = conn.execute("""
        SELECT m.id, m.league, m.home_team, m.away_team, m.match_date,
               f.ah_result, o.ah_line
        FROM matches m
        JOIN features f ON m.id = f.match_id
        JOIN odds o ON m.id = o.match_id
        WHERE m.ftr IS NOT NULL AND f.ah_result IS NOT NULL
        ORDER BY RANDOM()
        LIMIT ?
    """, (n,)).fetchall()

    match_ids = [r['id'] for r in rows]
    predictions = batch_predict(match_ids)

    correct = 0
    total_with_pred = 0
    upper_correct = 0
    upper_total = 0
    lower_correct = 0
    lower_total = 0
    total_push = 0

    results = []
    for r, p in zip(rows, predictions):
        actual = r['ah_result']
        pred = p['prediction']
        is_correct = (pred == actual) if pred in ['upper_win', 'lower_win'] else False

        if actual == 'push':
            total_push += 1

        if pred in ['upper_win', 'lower_win']:
            total_with_pred += 1
            if is_correct:
                correct += 1
            if pred == 'upper_win':
                upper_total += 1
                if is_correct: upper_correct += 1
            elif pred == 'lower_win':
                lower_total += 1
                if is_correct: lower_correct += 1

        results.append({
            'match': f"{r['home_team']} vs {r['away_team']}",
            'league': r['league'],
            'date': r['match_date'],
            'ah_line': r['ah_line'],
            'prediction': pred,
            'actual': actual,
            'correct': is_correct
        })

    conn.close()

    accuracy = correct / total_with_pred if total_with_pred > 0 else 0
    upper_acc = upper_correct / upper_total if upper_total > 0 else 0
    lower_acc = lower_correct / lower_total if lower_total > 0 else 0

    return jsonify({
        'simulation_size': n,
        'matches_with_prediction': total_with_pred,
        'overall_accuracy': round(accuracy * 100, 1),
        'upper_predictions': upper_total,
        'upper_accuracy': round(upper_acc * 100, 1),
        'lower_predictions': lower_total,
        'lower_accuracy': round(lower_acc * 100, 1),
        'push_count': total_push,
        'results': results
    })


@app.route(f'/api/{API_VERSION}/simulate20', methods=['GET'])
def simulate20():
    """
    Run a 20-match real-world simulation on the most recent completed matches.
    This is the formal validation test.
    """
    conn = get_connection()

    # Get 20 most recent matches that have results
    rows = conn.execute("""
        SELECT m.id, m.league, m.home_team, m.away_team, m.match_date,
               f.ah_result, o.ah_line
        FROM matches m
        JOIN features f ON m.id = f.match_id
        JOIN odds o ON m.id = o.match_id
        WHERE m.ftr IS NOT NULL AND f.ah_result IS NOT NULL
        ORDER BY m.match_date DESC, m.match_time DESC
        LIMIT 20
    """).fetchall()

    match_ids = [r['id'] for r in rows]
    predictions = batch_predict(match_ids)

    correct = 0
    total_with_pred = 0
    upper_correct = 0
    upper_total = 0
    lower_correct = 0
    lower_total = 0
    total_push = 0

    results = []
    for r, p in zip(rows, predictions):
        actual = r['ah_result']
        pred = p['prediction']
        is_correct = (pred == actual) if pred in ['upper_win', 'lower_win'] else False

        if actual == 'push':
            total_push += 1

        if pred in ['upper_win', 'lower_win']:
            total_with_pred += 1
            if is_correct:
                correct += 1
            if pred == 'upper_win':
                upper_total += 1
                if is_correct: upper_correct += 1
            elif pred == 'lower_win':
                lower_total += 1
                if is_correct: lower_correct += 1

        results.append({
            'match': f"{r['home_team']} vs {r['away_team']}",
            'league': r['league'],
            'date': r['match_date'],
            'ah_line': r['ah_line'],
            'prediction': pred,
            'actual': actual,
            'correct': is_correct
        })

    conn.close()

    accuracy = correct / total_with_pred if total_with_pred > 0 else 0
    upper_acc = upper_correct / upper_total if upper_total > 0 else 0
    lower_acc = lower_correct / lower_total if lower_total > 0 else 0

    return jsonify({
        'test_name': '20場實盤模擬驗證',
        'simulation_size': 20,
        'matches_with_prediction': total_with_pred,
        'overall_accuracy': round(accuracy * 100, 1),
        'upper_predictions': upper_total,
        'upper_accuracy': round(upper_acc * 100, 1),
        'lower_predictions': lower_total,
        'lower_accuracy': round(lower_acc * 100, 1),
        'push_count': total_push,
        'passed': accuracy >= 0.55,  # Threshold: 55%+
        'results': results
    })


@app.route(f'/api/{API_VERSION}/update-data', methods=['POST'])
def trigger_update():
    """Manually trigger data update. Runs in background thread."""
    threading.Thread(target=check_and_update, daemon=True).start()
    return jsonify({
        'status': 'update_triggered',
        'message': 'Data update started in background. Check /api/v1/update-status for progress.'
    })


@app.route(f'/api/{API_VERSION}/update-status', methods=['GET'])
def update_status():
    """Get current auto-update status."""
    return jsonify(get_update_status())


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"[API] Starting server on 0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)

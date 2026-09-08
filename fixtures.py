"""
Fixture fetcher module.
Fetches upcoming match fixtures from external APIs.
Supports football-data.org (free tier) as primary source.
Falls back to cached data if API is unavailable.
"""

import os
import json
import requests
from datetime import datetime, timedelta
from database import get_connection

# football-data.org API (free tier: 10 calls/min)
FD_API_KEY = os.environ.get('FD_API_KEY', '')
FD_BASE_URL = 'https://api.football-data.org/v4'

# League ID mappings for football-data.org (free tier only)
FD_LEAGUE_IDS = {
    'Ligue_1': 2015,      # France Ligue 1
    'La_Liga': 2014,      # Spain La Liga
    # Ligue_2 and La_Liga_2 not available on free tier of football-data.org
}

# League name mappings (English -> Traditional Chinese)
LEAGUE_NAMES_ZH = {
    'Ligue_1': '法國甲組聯賽',
    'Ligue_2': '法國乙組聯賽',
    'La_Liga': '西班牙甲組聯賽',
    'La_Liga_2': '西班牙乙組聯賽',
}

# Team name mappings (English official name -> Traditional Chinese)
# Based on actual names returned by football-data.org API
TEAM_NAMES_ZH = {
    # === Ligue 1 (France) ===
    'Paris Saint-Germain FC': '巴黎聖日耳門',
    'Olympique de Marseille': '馬賽',
    'Olympique Lyonnais': '里昂',
    'AS Monaco FC': '摩納哥',
    'Lille OSC': '里爾',
    'Stade Rennais FC 1901': '雷恩',
    'Stade Rennais FC': '雷恩',
    'OGC Nice': '尼斯',
    'Racing Club de Lens': '朗斯',
    'RC Lens': '朗斯',
    'RC Strasbourg Alsace': '斯特拉斯堡',
    'Toulouse FC': '圖盧茲',
    'FC Lorient': '羅連安特',
    'Le Havre AC': '勒阿弗爾',
    'Stade Brestois 29': '比斯特',
    'Angers SCO': '昂熱',
    'AJ Auxerre': '歐塞爾',
    'Le Mans FC': '勒芒',
    'Paris FC': '巴黎足球會',
    'ES Troyes AC': '特魯瓦',
    'ESTAC Troyes': '特魯瓦',
    'Montpellier HSC': '蒙彼利埃',
    'FC Nantes': '南特',
    'Stade de Reims': '蘭斯',
    'AS Saint-\u00c9tienne': '聖伊天',
    'SC Bastia': '巴斯蒂亞',
    'Red Star FC': '紅星',
    'Dijon FCO': '迪安',
    # === La Liga (Spain) ===
    'Real Madrid CF': '皇家馬德里',
    'FC Barcelona': '巴塞隆拿',
    'Club Atl\u00e9tico de Madrid': '馬德里體育會',
    'Atl\u00e9tico de Madrid': '馬德里體育會',
    'Sevilla FC': '西維爾',
    'Real Betis Balompi\u00e9': '貝迪斯',
    'Real Sociedad de F\u00fatbol': '皇家蘇斯達',
    'Villarreal CF': '維拉利爾',
    'Athletic Club': '畢爾包',
    'Valencia CF': '華倫西亞',
    'RC Celta de Vigo': '切爾達',
    'RCD Espanyol de Barcelona': '愛斯賓奴',
    'Getafe CF': '基達菲',
    'CA Osasuna': '奧沙辛拿',
    'Rayo Vallecano de Madrid': '華歷簡奴',
    'Deportivo Alav\u00e9s': '艾拉維斯',
    'Girona FC': '基羅納',
    'CD Legan\u00e9s': '雷加利斯',
    'RCD Mallorca': '馬略卡',
    'UD Las Palmas': '拉斯彭馬斯',
    'Real Valladolid CF': '華拉度列',
    'Elche CF': '艾爾切',
    'Levante UD': '利雲特',
    'M\u00e1laga CF': '馬拉加',
    'Real Racing Club de Santander': '桑坦德競賽',
    'Racing de Santander': '桑坦德競賽',
    'RC Deportivo La Coru\u00f1a': '拉科魯尼亞',
    'Deportivo La Coruna': '拉科魯尼亞',
    'Real Zaragoza CF': '薩拉戈薩',
    'Real Oviedo': '奧維耶多',
    'CD Tenerife': '特內里費',
    'SD Eibar': '伊巴',
    'Real Sporting de Gij\u00f3n': '希杭',
    'CD Mirand\u00e9s': '米蘭迪斯',
    'FC Cartagena': '卡塔赫納',
    'Burgos CF': '布爾戈斯',
    'AD Alcorc\u00f3n': '阿爾科爾孔',
    'C\u00f3rdoba CF': '科爾多瓦',
    'CD Eldense': '埃爾登斯',
    'SD Huesca': '侯爾斯卡',
    'CD Castell\u00f3n': '卡斯特利翁',
    'C\u00e1diz CF': '卡迪斯',
    'CE Sabadell FC': '薩巴德爾',
    'UD Almer\u00eda': '艾美利亞',
    'CD Numancia de Soria': '紐文西亞',
    'Celta de Vigo B': '切爾達B隊',
    'Real Sociedad B': '皇家蘇斯達B隊',
    'Granada CF': '格蘭納達',
}


def translate_team(name):
    """Translate team name to Traditional Chinese."""
    return TEAM_NAMES_ZH.get(name, name)


def translate_league(code):
    """Translate league code to Traditional Chinese."""
    return LEAGUE_NAMES_ZH.get(code, code)


def fetch_fixtures_from_fd(league_code, date_from=None, date_to=None):
    """
    Fetch fixtures from football-data.org.
    Returns list of match dicts.
    """
    if not FD_API_KEY:
        return []

    league_id = FD_LEAGUE_IDS.get(league_code)
    if not league_id:
        return []

    headers = {'X-Auth-Token': FD_API_KEY}

    if not date_from:
        date_from = datetime.now().strftime('%Y-%m-%d')
    if not date_to:
        date_to = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')

    url = f"{FD_BASE_URL}/competitions/{league_id}/matches"
    params = {
        'dateFrom': date_from,
        'dateTo': date_to,
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        matches = []
        for m in data.get('matches', []):
            match_date = m.get('utcDate', '')[:10]
            match_time = m.get('utcDate', '')[11:16]
            home_team = m.get('homeTeam', {}).get('name', '')
            away_team = m.get('awayTeam', {}).get('name', '')
            status = m.get('status', '')

            matches.append({
                'league': league_code,
                'league_name': translate_league(league_code),
                'match_date': match_date,
                'match_time': match_time,
                'home_team': translate_team(home_team),
                'away_team': translate_team(away_team),
                'home_team_en': home_team,
                'away_team_en': away_team,
                'status': status,
                'source': 'football-data.org'
            })

        return matches

    except Exception as e:
        print(f"[Fixtures] Error fetching from football-data.org: {e}")
        return []


def get_matches_for_date(league_code, target_date):
    """
    Get matches for a specific date.
    First try database (for historical), then try external API (for upcoming).
    target_date format: YYYY-MM-DD
    """
    conn = get_connection()

    # Check database first
    rows = conn.execute("""
        SELECT m.id, m.league, m.season, m.match_date, m.match_time,
               m.home_team, m.away_team,
               o.ah_line, o.ah_home_odds, o.ah_away_odds
        FROM matches m
        LEFT JOIN odds o ON m.id = o.match_id
        WHERE m.league = ? AND m.match_date = ?
        ORDER BY m.match_time
    """, (league_code, target_date)).fetchall()

    db_matches = []
    from odds_fetcher import db_team_to_zh
    for r in rows:
        db_matches.append({
            'id': r['id'],
            'league': r['league'],
            'league_name': translate_league(r['league']),
            'match_date': r['match_date'],
            'match_time': r['match_time'] or '',
            'home_team': db_team_to_zh(r['home_team']),
            'away_team': db_team_to_zh(r['away_team']),
            'ah_line': r['ah_line'],
            'ah_home_odds': r['ah_home_odds'],
            'ah_away_odds': r['ah_away_odds'],
            'source': 'database'
        })

    conn.close()

    # If no matches in DB and date is in the future, try external API
    if not db_matches and FD_API_KEY:
        try:
            api_matches = fetch_fixtures_from_fd(league_code, target_date, target_date)
            for m in api_matches:
                if m['match_date'] == target_date:
                    db_matches.append(m)
        except Exception as e:
            print(f"[Fixtures] API fetch failed: {e}")

    return db_matches


def get_all_matches_for_date(target_date):
    """Get matches for all supported leagues on a specific date."""
    all_matches = []
    for league_code in FD_LEAGUE_IDS.keys():
        matches = get_matches_for_date(league_code, target_date)
        all_matches.extend(matches)
    return sorted(all_matches, key=lambda x: (x['league'], x.get('match_time', '')))


def cache_fixtures(fixtures):
    """Cache fetched fixtures to daily_matches table."""
    conn = get_connection()
    for f in fixtures:
        conn.execute("""
            INSERT OR REPLACE INTO daily_matches
            (league, match_date, match_time, home_team, away_team, ah_line, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            f['league'],
            f['match_date'],
            f.get('match_time', ''),
            f['home_team'],
            f['away_team'],
            f.get('ah_line')
        ))
    conn.commit()
    conn.close()

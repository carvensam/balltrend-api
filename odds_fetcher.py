"""
Live odds fetcher using The Odds API.
Fetches Asian Handicap (spreads) and Over/Under (totals) odds
from Bet365 and Pinnacle for supported leagues.
"""
import os
import requests
from datetime import datetime
from database import get_connection

ODDS_API_KEY = os.environ.get('ODDS_API_KEY', '')
ODDS_BASE_URL = 'https://api.the-odds-api.com/v4'

# Map our league codes to The Odds API sport keys
LEAGUE_TO_SPORT = {
    'Ligue_1': 'soccer_france_ligue_one',
    'Ligue_2': 'soccer_france_ligue_two',
    'La_Liga': 'soccer_spain_la_liga',
    'La_Liga_2': 'soccer_spain_segunda_division',
}

# League names in Traditional Chinese
LEAGUE_NAMES_ZH = {
    'Ligue_1': '法國甲組聯賽',
    'Ligue_2': '法國乙組聯賽',
    'La_Liga': '西班牙甲組聯賽',
    'La_Liga_2': '西班牙乙組聯賽',
}

# Short team name mappings (The Odds API uses short names)
TEAM_SHORT_ZH = {
    # Ligue 1
    'Paris Saint-Germain': '巴黎聖日耳門',
    'Marseille': '馬賽',
    'Lyon': '里昂',
    'Monaco': '摩納哥',
    'Lille': '里爾',
    'Rennes': '雷恩',
    'Nice': '尼斯',
    'Lens': '朗斯',
    'Strasbourg': '斯特拉斯堡',
    'Toulouse': '圖盧茲',
    'Lorient': '羅連安特',
    'Le Havre': '勒阿弗爾',
    'Brest': '比斯特',
    'Angers': '昂熱',
    'Auxerre': '歐塞爾',
    'Le Mans': '勒芒',
    'Paris FC': '巴黎足球會',
    'Troyes': '特魯瓦',
    'Montpellier': '蒙彼利埃',
    'Nantes': '南特',
    'Reims': '蘭斯',
    'Saint-Etienne': '聖伊天',    # Ligue 2 (common teams)
    'Metz': '梅斯',
    'Caen': '卡昂',
    'Grenoble': '格勒諾布爾',
    'Guingamp': '甘岡',
    'Sochaux': '索察',
    'Nancy': '南錫',
    'Ajaccio': '阿雅克肖',
    'Bastia': '巴斯蒂亞',
    'Rodez': '羅德茲',
    'Paris': '巴黎足球會',
    'Amiens': '亞眠',
    'Annecy': '安錫',
    'Concarneau': '孔卡爾諾',
    'Dunkerque': '敦刻爾克',
    'Laval': '拉瓦勒',
    'Pau': '波城',
    'Quevilly Rouen': '奎維利魯昂',
    'Rodez Aveyron': '羅德茲',
    'Red Star': '紅星',
    'Toulouse': '圖盧茲',
    # La Liga
    'Real Madrid': '皇家馬德里',
    'Barcelona': '巴塞隆拿',
    'Atletico Madrid': '馬德里體育會',
    'Sevilla': '西維爾',
    'Real Betis': '貝迪斯',
    'Real Sociedad': '皇家蘇斯達',
    'Villarreal': '維拉利爾',
    'Athletic Club': '畢爾包',
    'Valencia': '華倫西亞',
    'Celta Vigo': '切爾達',
    'Espanyol': '愛斯賓奴',
    'Getafe': '基達菲',
    'Osasuna': '奧沙辛拿',
    'Rayo Vallecano': '華歷簡奴',
    'Alaves': '艾拉維斯',
    'Girona': '基羅納',
    'Leganes': '雷加利斯',
    'Mallorca': '馬略卡',
    'Las Palmas': '拉斯彭馬斯',
    'Valladolid': '華拉度列',
    'Elche': '艾爾切',
    'Levante': '利雲特',
    'Malaga': '馬拉加',
    'Racing Santander': '桑坦德競賽',
    'Deportivo La Coruna': '拉科魯尼亞',
    'Zaragoza': '薩拉戈薩',
    'Oviedo': '奧維耶多',
    'Tenerife': '特內里費',
    'Eibar': '伊巴',
    'Sporting Gijon': '希杭',
    'Mirandes': '米蘭迪斯',
    'Cartagena': '卡塔赫納',
    'Burgos': '布爾戈斯',
    'Alcorcon': '阿爾科爾孔',
    'Cordoba': '科爾多瓦',
    'Eldense': '埃爾登斯',
    'Huesca': '侯爾斯卡',
    'Castellon': '卡斯特利翁',
    'Cadiz': '卡迪斯',
    'Sabadell': '薩巴德爾',
    'Almeria': '艾美利亞',
    'Numancia': '紐文西亞',
    'Granada': '格蘭納達',
    'Real Oviedo': '奧維耶多',
    'CD Leganes': '雷加利斯',
    'Real Valladolid': '華拉度列',
    'UD Las Palmas': '拉斯彭馬斯',
    'RCD Mallorca': '馬略卡',
    'RCD Espanyol': '愛斯賓奴',
    'Deportivo Alaves': '艾拉維斯',
    'CA Osasuna': '奧沙辛拿',
    'Valencia CF': '華倫西亞',
    'Sevilla FC': '西維爾',
    'Real Sociedad': '皇家蘇斯達',
    'Athletic Bilbao': '畢爾包',
    'Real Betis': '貝迪斯',
    'Villarreal CF': '維拉利爾',
    'Atletico de Madrid': '馬德里體育會',
    'Celta de Vigo': '切爾達',
    # Additional names from The Odds API
    'AD Ceuta FC': '施奧達',
    'AS Monaco': '摩納哥',
    'Alavés': '艾拉維斯',
    'Albacete': '阿爾巴塞特',
    'Almería': '艾美利亞',
    'Andorra CF': '安道爾',
    'Annecy FC': '安錫',
    'Atlético Madrid': '馬德里體育會',
    'Boulogne': '布洛涅',
    'Burgos CF': '布爾戈斯',
    'CD Castellón': '卡斯特利翁',
    'CD Eldense': '埃爾登斯',
    'Celta Fortuna': '切爾達B隊',
    'Clermont': '克萊蒙',
    'Cádiz CF': '卡迪斯',
    'Córdoba': '科爾多瓦',
    'Deportivo La Coruña': '拉科魯尼亞',
    'Dijon': '第戎',
    'Elche CF': '艾爾切',
    'Girona FC': '基羅納',
    'Granada CF': '格蘭納達',
    'Le Mans FC': '勒芒',
    'Leganés': '雷加利斯',
    'Málaga': '馬拉加',
    'Paris Saint Germain': '巴黎聖日耳門',
    'Pau FC': '波城',
    'RC Lens': '朗斯',
    'Real Racing Club de Santander': '桑坦德競賽',
    'Real Sociedad B': '皇家蘇斯達B隊',
    'Real Valladolid CF': '華拉度列',
    'Rodez AF': '羅德茲',
    'SD Eibar': '伊巴',
    'Sabadell FC': '薩巴德爾',
    'Saint Etienne': '聖伊天',
    'Sporting Gijón': '希杭',
    'Stade Lavallois': '拉瓦勒',
    'Stade de Reims': '蘭斯',
    'USL Dunkerque': '敦刻爾克',
}


def translate_team_short(name):
    """Translate short team name to Traditional Chinese."""
    return TEAM_SHORT_ZH.get(name, name)


# Map The Odds API short names -> DB (football-data.co.uk) team names
ODDS_TO_DB = {
    'Paris Saint Germain': 'Paris SG',
    'AS Monaco': 'Monaco',
    'RC Lens': 'Lens',
    'Stade de Reims': 'Reims',
    'Saint Etienne': 'St Etienne',
    'Saint-Etienne': 'St Etienne',
    'Athletic Club': 'Ath Bilbao',
    'Athletic Bilbao': 'Ath Bilbao',
    'Atletico Madrid': 'Ath Madrid',
    'Atlético Madrid': 'Ath Madrid',
    'Celta Vigo': 'Celta',
    'Celta de Vigo': 'Celta',
    'Espanyol': 'Espanol',
    'RCD Espanyol': 'Espanol',
    'Rayo Vallecano': 'Vallecano',
    'Real Sociedad': 'Sociedad',
    'Real Sociedad B': 'Sociedad B',
    'Sporting Gijon': 'Sp Gijon',
    'Sporting Gijón': 'Sp Gijon',
    'Deportivo La Coruna': 'La Coruna',
    'Deportivo La Coruña': 'La Coruna',
    'Racing Santander': 'Santander',
    'Real Racing Club de Santander': 'Santander',
    'Real Oviedo': 'Oviedo',
    'Celta Fortuna': 'Celta B',
    'Sevilla FC': 'Sevilla',
    'Valencia CF': 'Valencia',
    'Villarreal CF': 'Villarreal',
    'Getafe CF': 'Getafe',
    'Girona FC': 'Girona',
    'Granada CF': 'Granada',
    'CA Osasuna': 'Osasuna',
    'Osasuna': 'Osasuna',
    'RCD Mallorca': 'Mallorca',
    'UD Las Palmas': 'Las Palmas',
    'Real Valladolid': 'Valladolid',
    'Real Valladolid CF': 'Valladolid',
    'CD Leganes': 'Leganes',
    'Leganés': 'Leganes',
    'Deportivo Alaves': 'Alaves',
    'Alavés': 'Alaves',
    'Elche CF': 'Elche',
    'Levante UD': 'Levante',
    'Malaga CF': 'Malaga',
    'Málaga': 'Malaga',
    'Real Madrid CF': 'Real Madrid',
    'FC Barcelona': 'Barcelona',
    'Real Betis': 'Betis',
    'Real Betis Balompié': 'Betis',
    'Real Zaragoza': 'Zaragoza',
    'Zaragoza': 'Zaragoza',
    'SD Eibar': 'Eibar',
    'CD Tenerife': 'Tenerife',
    'Tenerife': 'Tenerife',
    'SD Huesca': 'Huesca',
    'Huesca': 'Huesca',
    'Burgos CF': 'Burgos',
    'Burgos': 'Burgos',
    'Cordoba CF': 'Cordoba',
    'Córdoba': 'Cordoba',
    'CD Eldense': 'Eldense',
    'Eldense': 'Eldense',
    'CD Castellon': 'Castellon',
    'CD Castellón': 'Castellon',
    'Castellon': 'Castellon',
    'CE Sabadell FC': 'Sabadell',
    'Sabadell FC': 'Sabadell',
    'Sabadell': 'Sabadell',
    'UD Almeria': 'Almeria',
    'Almería': 'Almeria',
    'Almeria': 'Almeria',
    'AD Alcorcon': 'Alcorcon',
    'AD Alcorcón': 'Alcorcon',
    'Alcorcon': 'Alcorcon',
    'Albacete': 'Albacete',
    'CD Mirandes': 'Mirandes',
    'CD Mirandés': 'Mirandes',
    'Mirandes': 'Mirandes',
    'FC Cartagena': 'Cartagena',
    'Cartagena': 'Cartagena',
    'CD Numancia': 'Numancia',
    'Numancia': 'Numancia',
    'AD Ceuta FC': 'Ceuta',
    'Andorra CF': 'Andorra',
    'Andorra': 'Andorra',
    'USL Dunkerque': 'Dunkerque',
    'Dunkerque': 'Dunkerque',
    'Stade Lavallois': 'Laval',
    'Laval': 'Laval',
    'Pau FC': 'Pau FC',
    'Pau': 'Pau FC',
    'Paris': 'Paris FC',
    'Red Star': 'Red Star',
    'Red Star FC': 'Red Star',
    'Quevilly Rouen': 'Quevilly Rouen',
    'AC Ajaccio': 'Ajaccio',
    'Ajaccio': 'Ajaccio',
    'SC Bastia': 'Bastia',
    'Bastia': 'Bastia',
    'FC Metz': 'Metz',
    'Metz': 'Metz',
    'SM Caen': 'Caen',
    'Caen': 'Caen',
    'Grenoble Foot': 'Grenoble',
    'Grenoble': 'Grenoble',
    'EA Guingamp': 'Guingamp',
    'Guingamp': 'Guingamp',
    'FC Sochaux': 'Sochaux',
    'Sochaux': 'Sochaux',
    'AS Nancy': 'Nancy',
    'Nancy': 'Nancy',
    'Rodez AF': 'Rodez',
    'Rodez': 'Rodez',
    'Amiens SC': 'Amiens',
    'Amiens': 'Amiens',
    'Annecy FC': 'Annecy',
    'Annecy': 'Annecy',
    'US Concarneau': 'Concarneau',
    'Concarneau': 'Concarneau',
    'Paris FC': 'Paris FC',
    'ESTAC Troyes': 'Troyes',
    'Troyes': 'Troyes',
    'AJ Auxerre': 'Auxerre',
    'Auxerre': 'Auxerre',
    'Angers SCO': 'Angers',
    'Angers': 'Angers',
    'FC Girondins Bordeaux': 'Bordeaux',
    'Bordeaux': 'Bordeaux',
    'Dijon FCO': 'Dijon',
    'Dijon': 'Dijon',
    'Clermont Foot': 'Clermont',
    'Clermont': 'Clermont',
    'Le Mans FC': 'Le Mans',
    'RC Strasbourg': 'Strasbourg',
    'Strasbourg': 'Strasbourg',
    ' Toulouse FC': 'Toulouse',
    'Toulouse FC': 'Toulouse',
    'FC Lorient': 'Lorient',
    'FC Nantes': 'Nantes',
    'Montpellier HSC': 'Montpellier',
    'Stade Brestois': 'Brest',
    'Brest': 'Brest',
    'Le Havre AC': 'Le Havre',
    'OGC Nice': 'Nice',
    'Lille OSC': 'Lille',
    'Lyon': 'Lyon',
    'Olympique Lyonnais': 'Lyon',
    'Olympique de Marseille': 'Marseille',
    'Marseille': 'Marseille',
    'Stade Rennais': 'Rennes',
    'Rennes': 'Rennes',
    'Boulogne': 'Boulogne',
}


def db_team_name(odds_name):
    """Map The Odds API team name to DB (football-data.co.uk) name."""
    return ODDS_TO_DB.get(odds_name, odds_name)


# Reverse map: DB name -> Traditional Chinese (built once)
_DB_TO_ZH = {}
for _odds_name, _zh in TEAM_SHORT_ZH.items():
    _DB_TO_ZH.setdefault(db_team_name(_odds_name), _zh)


def db_team_to_zh(db_name):
    """Translate a DB (football-data.co.uk) team name to Traditional Chinese."""
    return _DB_TO_ZH.get(db_name, db_name)


def translate_league(code):
    """Translate league code to Traditional Chinese."""
    return LEAGUE_NAMES_ZH.get(code, code)


def init_live_odds_table():
    """Create live_odds table if not exists."""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS live_odds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league TEXT,
            match_date TEXT,
            match_time TEXT,
            home_team TEXT,
            away_team TEXT,
            home_team_en TEXT,
            away_team_en TEXT,
            ah_line REAL,
            ah_home_odds REAL,
            ah_away_odds REAL,
            ou_line REAL,
            over_odds REAL,
            under_odds REAL,
            bookmaker TEXT,
            commence_time TEXT,
            fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(league, home_team_en, away_team_en, commence_time)
        )
    """)
    conn.commit()
    conn.close()


def extract_odds_from_match(match_data, preferred_bookmaker='bet365'):
    """
    Extract AH line and O/U line from a match's bookmaker data.
    Tries preferred bookmaker first, falls back to any available.
    Returns dict with odds or None.
    """
    bookmakers = match_data.get('bookmakers', [])
    if not bookmakers:
        return None

    # Sort to prioritize preferred bookmaker
    sorted_bms = sorted(
        bookmakers,
        key=lambda b: 0 if b.get('key') == preferred_bookmaker else 1
    )

    for bm in sorted_bms:
        markets = {m['key']: m for m in bm.get('markets', [])}
        spreads = markets.get('spreads', {})
        totals = markets.get('totals', {})

        ah_line = None
        ah_home = None
        ah_away = None
        ou_line = None
        over_odds = None
        under_odds = None

        # Extract Asian Handicap (spreads)
        for outcome in spreads.get('outcomes', []):
            name = outcome.get('name', '')
            point = outcome.get('point')
            price = outcome.get('price')
            home_team = match_data.get('home_team', '')

            if name == home_team:
                ah_line = point
                ah_home = price
            else:
                ah_away = price

        # Extract Over/Under (totals)
        for outcome in totals.get('outcomes', []):
            name = outcome.get('name', '')
            point = outcome.get('point')
            price = outcome.get('price')

            if name == 'Over':
                ou_line = point
                over_odds = price
            elif name == 'Under':
                under_odds = price

        # If we got AH data, use this bookmaker
        if ah_line is not None:
            return {
                'ah_line': ah_line,
                'ah_home_odds': ah_home,
                'ah_away_odds': ah_away,
                'ou_line': ou_line,
                'over_odds': over_odds,
                'under_odds': under_odds,
                'bookmaker': bm.get('title', bm.get('key', 'unknown')),
            }

    return None


def fetch_odds_for_league(league_code):
    """
    Fetch odds for a single league from The Odds API.
    Returns list of match dicts with odds.
    """
    if not ODDS_API_KEY:
        print(f"[Odds] No API key configured")
        return []

    sport_key = LEAGUE_TO_SPORT.get(league_code)
    if not sport_key:
        return []

    url = f"{ODDS_BASE_URL}/sports/{sport_key}/odds"
    params = {
        'apiKey': ODDS_API_KEY,
        'regions': 'eu,uk',
        'markets': 'spreads,totals',
        'bookmakers': 'bet365,pinnacle',
        'dateFormat': 'iso',
    }

    try:
        resp = requests.get(url, params=params, timeout=30)
        remaining = resp.headers.get('x-requests-remaining', 'N/A')
        print(f"[Odds] {league_code}: status={resp.status_code}, remaining={remaining}")

        if resp.status_code != 200:
            print(f"[Odds] Error: {resp.text[:200]}")
            return []

        data = resp.json()
        matches = []

        for m in data:
            odds = extract_odds_from_match(m)
            if not odds:
                continue

            commence = m.get('commence_time', '')
            match_date = commence[:10] if commence else ''
            match_time = commence[11:16] if len(commence) > 16 else ''

            home_en = m.get('home_team', '')
            away_en = m.get('away_team', '')

            matches.append({
                'league': league_code,
                'league_name': translate_league(league_code),
                'match_date': match_date,
                'match_time': match_time,
                'home_team': translate_team_short(home_en),
                'away_team': translate_team_short(away_en),
                'home_team_en': home_en,
                'away_team_en': away_en,
                'ah_line': odds['ah_line'],
                'ah_home_odds': odds['ah_home_odds'],
                'ah_away_odds': odds['ah_away_odds'],
                'ou_line': odds['ou_line'],
                'over_odds': odds['over_odds'],
                'under_odds': odds['under_odds'],
                'bookmaker': odds['bookmaker'],
                'commence_time': commence,
                'source': 'the-odds-api',
            })

        return matches

    except Exception as e:
        print(f"[Odds] Exception fetching {league_code}: {e}")
        return []


def fetch_all_odds():
    """Fetch odds for all supported leagues and store in database."""
    init_live_odds_table()
    all_matches = []

    for league_code in LEAGUE_TO_SPORT.keys():
        matches = fetch_odds_for_league(league_code)
        all_matches.extend(matches)

    # Store in database
    conn = get_connection()
    for m in all_matches:
        conn.execute("""
            INSERT OR REPLACE INTO live_odds
            (league, match_date, match_time, home_team, away_team,
             home_team_en, away_team_en,
             ah_line, ah_home_odds, ah_away_odds,
             ou_line, over_odds, under_odds,
             bookmaker, commence_time, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            m['league'], m['match_date'], m['match_time'],
            m['home_team'], m['away_team'],
            m['home_team_en'], m['away_team_en'],
            m['ah_line'], m['ah_home_odds'], m['ah_away_odds'],
            m['ou_line'], m['over_odds'], m['under_odds'],
            m['bookmaker'], m['commence_time']
        ))
    conn.commit()
    conn.close()

    print(f"[Odds] Stored {len(all_matches)} matches with live odds")
    return all_matches


def get_live_odds_for_date(target_date, league=None):
    """
    Get live odds matches for a specific date.
    Returns list of match dicts.
    """
    conn = get_connection()
    query = """
        SELECT * FROM live_odds
        WHERE match_date = ?
    """
    params = [target_date]
    if league:
        query += " AND league = ?"
        params.append(league)
    query += " ORDER BY match_time"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    result = []
    for r in rows:
        result.append({
            'id': f"live_{r['id']}",
            'league': r['league'],
            'league_name': translate_league(r['league']),
            'match_date': r['match_date'],
            'match_time': r['match_time'] or '',
            'home_team': r['home_team'],
            'away_team': r['away_team'],
            'ah_line': r['ah_line'],
            'ah_home_odds': r['ah_home_odds'],
            'ah_away_odds': r['ah_away_odds'],
            'ou_line': r['ou_line'],
            'over_odds': r['over_odds'],
            'under_odds': r['under_odds'],
            'bookmaker': r['bookmaker'],
            'source': 'live_odds',
        })
    return result


if __name__ == '__main__':
    print("Testing odds fetcher...")
    matches = fetch_all_odds()
    print(f"\nTotal matches fetched: {len(matches)}")
    for m in matches[:5]:
        print(f"  {m['match_date']} {m['match_time']} | {m['league_name']} | "
              f"{m['home_team']} vs {m['away_team']} | "
              f"AH: {m['ah_line']} ({m['ah_home_odds']}/{m['ah_away_odds']}) | "
              f"O/U: {m['ou_line']} ({m['over_odds']}/{m['under_odds']}) | "
              f"{m['bookmaker']}")

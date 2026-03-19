# ============================================================
# apis/football_api.py — API-Football v3 wrapper
# ============================================================
import requests, logging
from config import API_FOOTBALL_KEY, API_FOOTBALL_BASE, CACHE
from database import cache_get, cache_set

log = logging.getLogger(__name__)

HEADERS = {
    "x-rapidapi-host": "v3.football.api-sports.io",
    "x-rapidapi-key":  API_FOOTBALL_KEY,
}


def _get(endpoint: str, params: dict, cache_key: str = None, ttl: int = 300):
    if cache_key:
        cached = cache_get(cache_key)
        if cached is not None:
            return cached
    try:
        r = requests.get(f"{API_FOOTBALL_BASE}/{endpoint}",
                         headers=HEADERS, params=params, timeout=10)
        r.raise_for_status()
        data = r.json().get("response", [])
        if cache_key:
            cache_set(cache_key, data, ttl)
        return data
    except Exception as e:
        log.error(f"API-Football error [{endpoint}]: {e}")
        return []


# ─── Fixtures ─────────────────────────────────────────────────
def get_fixtures_today(league_id: int, season: int):
    from datetime import date
    today = str(date.today())
    key = f"fixtures_today_{league_id}_{today}"
    return _get("fixtures", {"league": league_id, "season": season, "date": today},
                key, CACHE["fixtures_ttl"])


def get_fixtures_next(league_id: int, season: int, next_n: int = 10):
    key = f"fixtures_next_{league_id}_{next_n}"
    return _get("fixtures", {"league": league_id, "season": season, "next": next_n},
                key, CACHE["fixtures_ttl"])


def get_fixture_by_id(fixture_id: int):
    key = f"fixture_{fixture_id}"
    data = _get("fixtures", {"id": fixture_id}, key, CACHE["fixtures_ttl"])
    return data[0] if data else None


def get_team_statistics(team_id: int, league_id: int, season: int):
    key = f"team_stats_{team_id}_{league_id}_{season}"
    data = _get("teams/statistics",
                {"team": team_id, "league": league_id, "season": season},
                key, CACHE["team_stats_ttl"])
    return data if data else {}


def get_team_last_matches(team_id: int, last: int = 10):
    key = f"team_last_{team_id}_{last}"
    return _get("fixtures", {"team": team_id, "last": last},
                key, CACHE["fixtures_ttl"])


def get_head_to_head(team1_id: int, team2_id: int, last: int = 10):
    key = f"h2h_{team1_id}_{team2_id}_{last}"
    return _get("fixtures",
                {"h2h": f"{team1_id}-{team2_id}", "last": last},
                key, CACHE["team_stats_ttl"])


def get_team_info(team_id: int):
    key = f"team_info_{team_id}"
    data = _get("teams", {"id": team_id}, key, CACHE["standings_ttl"])
    return data[0] if data else None


def search_team(name: str):
    key = f"team_search_{name.lower().replace(' ','_')}"
    return _get("teams", {"search": name}, key, CACHE["standings_ttl"])


def get_standings(league_id: int, season: int):
    key = f"standings_{league_id}_{season}"
    return _get("standings", {"league": league_id, "season": season},
                key, CACHE["standings_ttl"])


def get_top_scorers(league_id: int, season: int):
    key = f"top_scorers_{league_id}_{season}"
    return _get("players/topscorers",
                {"league": league_id, "season": season},
                key, CACHE["standings_ttl"])


def get_injuries(team_id: int = None, fixture_id: int = None):
    params = {}
    if team_id:
        params["team"] = team_id
    if fixture_id:
        params["fixture"] = fixture_id
    key = f"injuries_{team_id}_{fixture_id}"
    return _get("injuries", params, key, CACHE["fixtures_ttl"])


def get_lineups(fixture_id: int):
    key = f"lineups_{fixture_id}"
    return _get("fixtures/lineups", {"fixture": fixture_id},
                key, CACHE["fixtures_ttl"])


def get_live_fixtures(league_id: int = None):
    params = {"live": "all"}
    if league_id:
        params["league"] = league_id
    return _get("fixtures", params, None, 0)

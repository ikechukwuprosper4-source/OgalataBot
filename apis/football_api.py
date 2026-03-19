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


def _get(endpoint: str, params: dict,
         cache_key: str = None, ttl: int = 300):
    if cache_key:
        cached = cache_get(cache_key)
        if cached is not None:
            return cached
    try:
        r = requests.get(
            f"{API_FOOTBALL_BASE}/{endpoint}",
            headers=HEADERS, params=params, timeout=15
        )
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
    return _get("fixtures",
                {"league": league_id, "season": season, "date": today},
                key, CACHE["fixtures_ttl"])


def get_fixtures_next(league_id: int, season: int, next_n: int = 10):
    key = f"fixtures_next_{league_id}_{next_n}"
    return _get("fixtures",
                {"league": league_id, "season": season, "next": next_n},
                key, CACHE["fixtures_ttl"])


def get_finished_fixtures(league_id: int, season: int):
    """Fetch all finished matches for a season (for MLE fitting)."""
    key = f"finished_{league_id}_{season}"
    return _get("fixtures",
                {"league": league_id, "season": season, "status": "FT"},
                key, ttl=86400)


def get_fixture_by_id(fixture_id: int):
    key  = f"fixture_{fixture_id}"
    data = _get("fixtures", {"id": fixture_id},
                key, CACHE["fixtures_ttl"])
    return data[0] if data else None


def get_team_statistics(team_id: int, league_id: int, season: int):
    key  = f"team_stats_{team_id}_{league_id}_{season}"
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
    key  = f"team_info_{team_id}"
    data = _get("teams", {"id": team_id}, key, CACHE["standings_ttl"])
    return data[0] if data else None


def search_team(name: str):
    key = f"team_search_{name.lower().replace(' ', '_')}"
    return _get("teams", {"search": name}, key, CACHE["standings_ttl"])


def get_standings(league_id: int, season: int):
    key = f"standings_{league_id}_{season}"
    return _get("standings",
                {"league": league_id, "season": season},
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


# ─── xG (Expected Goals) ─────────────────────────────────────
def get_fixture_statistics(fixture_id: int) -> list:
    """Fetch full fixture statistics including xG."""
    key  = f"fixture_stats_{fixture_id}"
    return _get("fixtures/statistics", {"fixture": fixture_id},
                key, CACHE["fixtures_ttl"])


def extract_xg(fixture_stats: list) -> tuple:
    """
    Extract xG values from fixture statistics response.
    Returns (xg_home, xg_away) as floats. 0.0 if unavailable.
    """
    xg_home = 0.0
    xg_away = 0.0
    for team_stats in fixture_stats:
        is_home  = team_stats.get("team", {}).get("id") is not None
        stats    = team_stats.get("statistics", [])
        for stat in stats:
            if stat.get("type", "").lower() in ("expected goals", "xg"):
                val = stat.get("value")
                try:
                    val = float(val or 0)
                except (TypeError, ValueError):
                    val = 0.0
                # First team entry = home, second = away
                if xg_home == 0.0:
                    xg_home = val
                else:
                    xg_away = val
    return round(xg_home, 3), round(xg_away, 3)


def get_recent_xg(team_id: int, last: int = 6) -> float:
    """
    Compute average xG for a team from their last N matches.
    Falls back to 0.0 if not available.
    """
    matches = get_team_last_matches(team_id, last=last)
    xg_vals = []
    for m in matches:
        fid   = m.get("fixture", {}).get("id")
        if not fid:
            continue
        stats = get_fixture_statistics(fid)
        xg_h, xg_a = extract_xg(stats)
        home_id = m.get("teams", {}).get("home", {}).get("id")
        if home_id == team_id:
            if xg_h > 0:
                xg_vals.append(xg_h)
        else:
            if xg_a > 0:
                xg_vals.append(xg_a)
    if not xg_vals:
        return 0.0
    return round(sum(xg_vals) / len(xg_vals), 3)


def get_home_lineup(fixture_id: int) -> dict:
    """Return home team lineup dict from fixture."""
    lineups = get_lineups(fixture_id)
    if lineups:
        return lineups[0] if lineups else {}
    return {}


def get_away_lineup(fixture_id: int) -> dict:
    """Return away team lineup dict from fixture."""
    lineups = get_lineups(fixture_id)
    if len(lineups) > 1:
        return lineups[1]
    return {}

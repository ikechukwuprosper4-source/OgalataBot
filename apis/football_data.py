# ============================================================
# apis/football_data.py — Football-Data.org v4 wrapper
# ============================================================
import requests, logging
from config import FOOTBALL_DATA_KEY, FOOTBALL_DATA_BASE, CACHE
from database import cache_get, cache_set

log = logging.getLogger(__name__)

HEADERS = {"X-Auth-Token": FOOTBALL_DATA_KEY}

FD_LEAGUES = {
    "PL":  "Premier League",
    "PD":  "La Liga",
    "SA":  "Serie A",
    "BL1": "Bundesliga",
    "FL1": "Ligue 1",
    "CL":  "Champions League",
}


def _get(endpoint: str, params: dict = None,
         cache_key: str = None, ttl: int = 3600):
    if cache_key:
        cached = cache_get(cache_key)
        if cached is not None:
            return cached
    try:
        r = requests.get(f"{FOOTBALL_DATA_BASE}/{endpoint}",
                         headers=HEADERS, params=params or {}, timeout=10)
        r.raise_for_status()
        data = r.json()
        if cache_key:
            cache_set(cache_key, data, ttl)
        return data
    except Exception as e:
        log.error(f"Football-Data error [{endpoint}]: {e}")
        return {}


def get_standings(competition_code: str):
    key = f"fd_standings_{competition_code}"
    return _get(f"competitions/{competition_code}/standings",
                cache_key=key, ttl=CACHE["standings_ttl"])


def get_matches(competition_code: str, matchday: int = None,
                status: str = "SCHEDULED"):
    params = {"status": status}
    if matchday:
        params["matchday"] = matchday
    key = f"fd_matches_{competition_code}_{matchday}_{status}"
    return _get(f"competitions/{competition_code}/matches",
                params=params, cache_key=key, ttl=CACHE["fixtures_ttl"])


def get_team_matches(team_id: int, limit: int = 20):
    key = f"fd_team_matches_{team_id}_{limit}"
    return _get(f"teams/{team_id}/matches",
                params={"limit": limit},
                cache_key=key, ttl=CACHE["team_stats_ttl"])


def get_scorers(competition_code: str, limit: int = 20):
    key = f"fd_scorers_{competition_code}"
    return _get(f"competitions/{competition_code}/scorers",
                params={"limit": limit},
                cache_key=key, ttl=CACHE["standings_ttl"])


def get_competition_teams(competition_code: str):
    key = f"fd_teams_{competition_code}"
    data = _get(f"competitions/{competition_code}/teams",
                cache_key=key, ttl=CACHE["standings_ttl"])
    return data.get("teams", [])


def get_team(team_id: int):
    key = f"fd_team_{team_id}"
    return _get(f"teams/{team_id}", cache_key=key,
                ttl=CACHE["standings_ttl"])


def parse_standing_table(standings_data: dict) -> list:
    rows = []
    for stage in standings_data.get("standings", []):
        if stage.get("type") == "TOTAL":
            rows = stage.get("table", [])
            break
    return rows


def team_position_and_form(standings_data: dict, team_id: int) -> dict:
    table = parse_standing_table(standings_data)
    for row in table:
        if row["team"]["id"] == team_id:
            return {
                "position":  row.get("position"),
                "played":    row.get("playedGames"),
                "won":       row.get("won"),
                "draw":      row.get("draw"),
                "lost":      row.get("lost"),
                "goals_for": row.get("goalsFor"),
                "goals_ag":  row.get("goalsAgainst"),
                "gd":        row.get("goalDifference"),
                "points":    row.get("points"),
                "form":      row.get("form", ""),
            }
    return {}

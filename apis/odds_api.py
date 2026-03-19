# ============================================================
# apis/odds_api.py — The Odds API wrapper
# ============================================================
import requests, logging
from config import ODDS_API_KEY, ODDS_API_BASE, CACHE
from database import cache_get, cache_set

log = logging.getLogger(__name__)


def _get(endpoint: str, params: dict, cache_key: str = None, ttl: int = 300):
    params["apiKey"] = ODDS_API_KEY
    if cache_key:
        cached = cache_get(cache_key)
        if cached is not None:
            return cached
    try:
        r = requests.get(f"{ODDS_API_BASE}/{endpoint}",
                         params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        if cache_key:
            cache_set(cache_key, data, ttl)
        return data
    except Exception as e:
        log.error(f"Odds API error [{endpoint}]: {e}")
        return []


def get_sports():
    return _get("sports", {}, "sports_list", CACHE["standings_ttl"])


def get_odds(sport_key: str, regions: str = "uk,eu,us",
             markets: str = "h2h,totals,spreads", odds_format: str = "decimal"):
    key = f"odds_{sport_key}_{markets}"
    return _get(f"sports/{sport_key}/odds",
                {"regions": regions, "markets": markets,
                 "oddsFormat": odds_format},
                key, CACHE["fixtures_ttl"])


def get_event_odds(sport_key: str, event_id: str,
                   markets: str = "h2h,totals,spreads,btts",
                   regions: str = "uk,eu"):
    key = f"event_odds_{event_id}_{markets}"
    return _get(f"sports/{sport_key}/events/{event_id}/odds",
                {"regions": regions, "markets": markets,
                 "oddsFormat": "decimal"},
                key, CACHE["fixtures_ttl"])


def get_scores(sport_key: str, days_from: int = 1):
    key = f"scores_{sport_key}_{days_from}"
    return _get(f"sports/{sport_key}/scores",
                {"daysFrom": days_from},
                key, CACHE["fixtures_ttl"])


# ─── Odds analysis helpers ───────────────────────────────────
def extract_best_odds(odds_data: list, market: str = "h2h") -> dict:
    best = {}
    for event in (odds_data if isinstance(odds_data, list) else [odds_data]):
        for bookie in event.get("bookmakers", []):
            for m in bookie.get("markets", []):
                if m["key"] != market:
                    continue
                for outcome in m.get("outcomes", []):
                    name  = outcome["name"]
                    price = float(outcome["price"])
                    bname = bookie["title"]
                    if name not in best or price > best[name][0]:
                        best[name] = (price, bname)
    return best


def extract_market_odds(event_odds: dict, market_key: str) -> dict:
    totals = {}
    counts = {}
    for bookie in event_odds.get("bookmakers", []):
        for m in bookie.get("markets", []):
            if m["key"] != market_key:
                continue
            for outcome in m.get("outcomes", []):
                k = outcome.get("name") or outcome.get("description", "")
                p = float(outcome["price"])
                totals[k] = totals.get(k, 0) + p
                counts[k] = counts.get(k, 0) + 1
    return {k: round(totals[k] / counts[k], 3)
            for k in totals if counts[k] > 0}


def implied_probability(decimal_odds: float) -> float:
    if decimal_odds <= 0:
        return 0.0
    return 1.0 / decimal_odds


def remove_margin(odds_dict: dict) -> dict:
    raw   = {k: implied_probability(v) for k, v in odds_dict.items()}
    total = sum(raw.values())
    if total == 0:
        return raw
    return {k: round(v / total, 4) for k, v in raw.items()}


def calculate_value(model_prob: float, bookmaker_odds: float,
                    min_edge: float = 0.05) -> dict:
    bk_prob = implied_probability(bookmaker_odds)
    edge    = model_prob - bk_prob
    has_val = edge >= min_edge

    b = bookmaker_odds - 1
    if b <= 0 or model_prob <= 0:
        kelly = 0.0
    else:
        kelly = max(0.0, (b * model_prob - (1 - model_prob)) / b)

    return {
        "has_value":      has_val,
        "model_prob":     round(model_prob, 4),
        "implied_prob":   round(bk_prob, 4),
        "edge_pct":       round(edge * 100, 2),
        "bookmaker_odds": bookmaker_odds,
        "full_kelly":     round(kelly, 4),
        "quarter_kelly":  round(kelly * 0.25, 4),
  }

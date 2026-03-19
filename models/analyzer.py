# ============================================================
# models/analyzer.py — Full prediction pipeline
# ============================================================
import logging
from config import MODEL, RISK, SUPPORTED_LEAGUES
from apis.football_api import (get_team_statistics, get_team_last_matches,
                                get_head_to_head, get_fixture_by_id)
from apis.odds_api     import (get_odds, calculate_value, implied_probability)
from models.poisson    import (compute_ratings, build_lambdas,
                               form_weight, quick_predict)
from database          import save_prediction, get_prediction

log = logging.getLogger(__name__)

LEAGUE_AVGS = {
    39:  (1.57, 1.23),
    140: (1.52, 1.14),
    135: (1.49, 1.17),
    78:  (1.68, 1.31),
    61:  (1.53, 1.22),
    2:   (1.60, 1.20),
    3:   (1.50, 1.18),
}
DEFAULT_AVG = (1.50, 1.15)


def _league_avg(league_id: int):
    return LEAGUE_AVGS.get(int(league_id), DEFAULT_AVG)


# ─── Main prediction entry point ─────────────────────────────
def predict_fixture(fixture_id: int, force_refresh: bool = False) -> dict:
    if not force_refresh:
        cached = get_prediction(fixture_id)
        if cached:
            return cached["prediction"]

    fixture = get_fixture_by_id(fixture_id)
    if not fixture:
        return {"error": "Fixture not found"}

    home_team = fixture["teams"]["home"]
    away_team = fixture["teams"]["away"]
    league    = fixture["league"]
    match_dt  = fixture["fixture"]["date"]

    result = _build_prediction(
        home_id     = home_team["id"],
        away_id     = away_team["id"],
        home_name   = home_team["name"],
        away_name   = away_team["name"],
        league_id   = league["id"],
        season      = league["season"],
        fixture_id  = fixture_id,
        match_dt    = match_dt,
        league_name = league["name"],
    )

    save_prediction(fixture_id, home_team["name"], away_team["name"],
                    league["name"], match_dt, result)
    return result


def predict_by_names(home_name: str, away_name: str,
                     league_id: int = 39, season: int = 2024) -> dict:
    home_ids = _search_team_id(home_name, league_id, season)
    away_ids = _search_team_id(away_name, league_id, season)

    home_id = home_ids[0] if home_ids else None
    away_id = away_ids[0] if away_ids else None

    return _build_prediction(
        home_id     = home_id,
        away_id     = away_id,
        home_name   = home_name,
        away_name   = away_name,
        league_id   = league_id,
        season      = season,
        fixture_id  = None,
        match_dt    = "Unknown",
        league_name = f"League {league_id}",
    )


def _build_prediction(home_id, away_id, home_name, away_name,
                      league_id, season, fixture_id, match_dt,
                      league_name) -> dict:
    lga_h, lga_a = _league_avg(league_id)

    # ── Fetch stats ──────────────────────────────────────────
    home_stats = {} if not home_id else \
        get_team_statistics(home_id, league_id, season)
    away_stats = {} if not away_id else \
        get_team_statistics(away_id, league_id, season)

    # ── Compute ratings ──────────────────────────────────────
    home_rat = compute_ratings(home_stats) if home_stats else {}
    away_rat = compute_ratings(away_stats) if away_stats else {}

    # ── Form adjustment ──────────────────────────────────────
    home_recent = (get_team_last_matches(home_id, last=MODEL["form_matches"])
                   if home_id else [])
    away_recent = (get_team_last_matches(away_id, last=MODEL["form_matches"])
                   if away_id else [])

    form_h = form_weight(home_recent, home_id) if home_id else 1.0
    form_a = form_weight(away_recent, away_id) if away_id else 1.0

    # ── Build lambda ─────────────────────────────────────────
    lam_h, lam_a = build_lambdas(home_rat, away_rat, lga_h, lga_a)
    lam_h = round(max(0.2, min(lam_h * form_h, 6.0)), 3)
    lam_a = round(max(0.2, min(lam_a * form_a, 6.0)), 3)

    # ── Head-to-head adjustment ──────────────────────────────
    if home_id and away_id:
        h2h     = get_head_to_head(home_id, away_id, last=10)
        h2h_adj = _h2h_adjustment(h2h, home_id, away_id)
    else:
        h2h     = []
        h2h_adj = {"home_factor": 1.0, "away_factor": 1.0}

    lam_h = round(max(0.2, min(lam_h * h2h_adj["home_factor"], 6.0)), 3)
    lam_a = round(max(0.2, min(lam_a * h2h_adj["away_factor"], 6.0)), 3)

    # ── Run Poisson model ────────────────────────────────────
    markets = quick_predict(lam_h, lam_a)

    # ── Confidence score ─────────────────────────────────────
    confidence = _confidence_score(markets, home_rat, away_rat,
                                   len(home_recent), len(away_recent))

    # ── Best tip ─────────────────────────────────────────────
    tip = _select_best_tip(markets, confidence)

    # ── Value bets ───────────────────────────────────────────
    value_bets = _find_value_bets(markets, league_id)

    # ── Form strings ─────────────────────────────────────────
    home_form_str = _form_string(home_recent, home_id)
    away_form_str = _form_string(away_recent, away_id)

    # ── H2H summary ──────────────────────────────────────────
    h2h_summary = _h2h_summary(h2h, home_name, away_name)

    return {
        "fixture_id":   fixture_id,
        "home_name":    home_name,
        "away_name":    away_name,
        "league":       league_name,
        "match_date":   match_dt,
        "lambda_home":  lam_h,
        "lambda_away":  lam_a,
        "markets":      markets,
        "confidence":   confidence,
        "tip":          tip,
        "value_bets":   value_bets,
        "home_form":    home_form_str,
        "away_form":    away_form_str,
        "h2h_summary":  h2h_summary,
        "home_stats":   _summarise_stats(home_stats),
        "away_stats":   _summarise_stats(away_stats),
    }


# ─── Helpers ─────────────────────────────────────────────────
def _h2h_adjustment(h2h: list, home_id: int, away_id: int) -> dict:
    if not h2h:
        return {"home_factor": 1.0, "away_factor": 1.0}
    hw = aw = d = 0
    for m in h2h[-8:]:
        gh      = m.get("goals", {}).get("home", 0) or 0
        ga      = m.get("goals", {}).get("away", 0) or 0
        home_id_ = m.get("teams", {}).get("home", {}).get("id")
        if home_id_ == home_id:
            if gh > ga:   hw += 1
            elif ga > gh: aw += 1
            else:          d += 1
        else:
            if ga > gh:   hw += 1
            elif gh > ga: aw += 1
            else:          d += 1
    total = hw + aw + d
    if total == 0:
        return {"home_factor": 1.0, "away_factor": 1.0}
    hf = 0.95 + (hw / total) * 0.12
    af = 0.95 + (aw / total) * 0.12
    return {"home_factor": round(hf, 3), "away_factor": round(af, 3)}


def _confidence_score(markets: dict, home_rat: dict, away_rat: dict,
                      home_n: int, away_n: int) -> int:
    base  = 55
    base += min(10, home_n)
    base += min(10, away_n)
    max_p = max(markets.get("p_home_win", 0),
                markets.get("p_draw",     0),
                markets.get("p_away_win", 0))
    if max_p > 0.65:   base += 8
    elif max_p > 0.55: base += 4
    if abs(markets.get("p_home_win", 0.33) -
           markets.get("p_away_win", 0.33)) < 0.05:
        base -= 5
    return max(40, min(95, base))


def _select_best_tip(markets: dict, confidence: int) -> dict:
    candidates = [
        ("1X2",           "Home Win",  markets.get("p_home_win", 0)),
        ("1X2",           "Draw",      markets.get("p_draw",     0)),
        ("1X2",           "Away Win",  markets.get("p_away_win", 0)),
        ("Over/Under",    "Over 2.5",  markets["over_under"]["2.5"]["over"]),
        ("Over/Under",    "Under 2.5", markets["over_under"]["2.5"]["under"]),
        ("BTTS",          "Yes",       markets.get("btts_yes",   0)),
        ("BTTS",          "No",        markets.get("btts_no",    0)),
        ("Double Chance", "1X",        markets.get("p_1x",       0)),
        ("Double Chance", "X2",        markets.get("p_x2",       0)),
    ]
    candidates.sort(key=lambda x: x[2], reverse=True)
    best = candidates[0]
    return {
        "market":      best[0],
        "selection":   best[1],
        "probability": round(best[2], 4),
        "fair_odds":   round(1 / best[2], 2) if best[2] > 0 else 99,
        "confidence":  confidence,
        "rating":      "⭐⭐⭐" if confidence >= 75
                       else "⭐⭐" if confidence >= 60 else "⭐",
    }


def _find_value_bets(markets: dict, league_id: int) -> list:
    sport_key = "soccer_epl" if league_id == 39 \
                else "soccer_uefa_champs_league"
    try:
        live_odds = get_odds(sport_key, markets="h2h,totals")
    except Exception:
        return []

    vbs     = []
    min_edge = MODEL["min_value_edge"]

    for event in (live_odds if isinstance(live_odds, list) else []):
        for bookie in event.get("bookmakers", []):
            for market in bookie.get("markets", []):
                key = market.get("key")
                for outcome in market.get("outcomes", []):
                    p_model = _market_prob(markets, key, outcome)
                    if p_model is None:
                        continue
                    v = calculate_value(p_model,
                                       float(outcome["price"]),
                                       min_edge)
                    if v["has_value"]:
                        vbs.append({
                            "market":    key,
                            "selection": outcome.get("name", ""),
                            "point":     outcome.get("point", ""),
                            **v,
                            "bookmaker": bookie.get("title", ""),
                        })

    seen = set()
    out  = []
    for v in sorted(vbs, key=lambda x: x["edge_pct"], reverse=True):
        k = (v["market"], v["selection"], v.get("point", ""))
        if k not in seen:
            seen.add(k)
            out.append(v)
    return out[:8]


def _market_prob(markets: dict, key: str, outcome: dict):
    name = outcome.get("name", "").lower()
    try:
        if key == "totals":
            point = float(outcome.get("point", 2.5))
            ou    = markets["over_under"].get(str(point))
            if ou:
                return ou["over"] if name == "over" else ou["under"]
        if key == "h2h":
            if "draw" in name:
                return markets["p_draw"]
    except Exception:
        pass
    return None


def _form_string(recent: list, team_id: int) -> str:
    s = []
    for m in recent[-6:]:
        gh      = m.get("goals", {}).get("home", 0) or 0
        ga      = m.get("goals", {}).get("away", 0) or 0
        home_id = m.get("teams", {}).get("home", {}).get("id")
        is_home = (home_id == team_id)
        if is_home:
            s.append("W" if gh > ga else "D" if gh == ga else "L")
        else:
            s.append("W" if ga > gh else "D" if gh == ga else "L")
    return " ".join(s) or "N/A"


def _h2h_summary(h2h: list, home: str, away: str) -> dict:
    hw = aw = d = home_gf = away_gf = 0
    for m in h2h[-8:]:
        gh       = m.get("goals", {}).get("home", 0) or 0
        ga       = m.get("goals", {}).get("away", 0) or 0
        home_gf += gh
        away_gf += ga
        if gh > ga:   hw += 1
        elif ga > gh: aw += 1
        else:          d += 1
    total = hw + aw + d
    return {
        "total":          total,
        f"{home}_wins":   hw,
        "draws":          d,
        f"{away}_wins":   aw,
        "avg_goals":      round((home_gf + away_gf) / total, 2) if total else 0,
    }


def _summarise_stats(stats: dict) -> dict:
    if not stats:
        return {}
    gs  = stats.get("goals",    {})
    fix = stats.get("fixtures", {})
    return {
        "played":        fix.get("played", {}).get("total", 0),
        "wins":          fix.get("wins",   {}).get("total", 0),
        "draws":         fix.get("draws",  {}).get("total", 0),
        "losses":        fix.get("loses",  {}).get("total", 0),
        "goals_for":     gs.get("for",     {}).get("total", {}).get("total", 0),
        "goals_against": gs.get("against", {}).get("total", {}).get("total", 0),
        "avg_goals_for": gs.get("for",     {}).get("average", {}).get("total", 0),
        "form":          stats.get("form", ""),
    }


def _search_team_id(name: str, league_id: int, season: int) -> list:
    from apis.football_api import search_team
    teams = search_team(name)
    return [t["team"]["id"] for t in teams if t.get("team")]

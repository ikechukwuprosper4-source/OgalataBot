# ============================================================
# models/analyzer.py — Full prediction pipeline
# Now includes MLE fitting, xG data, injuries, lineups
# ============================================================
import logging
from config import MODEL, SUPPORTED_LEAGUES
from apis.football_api import (
    get_team_statistics, get_team_last_matches,
    get_head_to_head, get_fixture_by_id,
    get_injuries, get_lineups,
    get_recent_xg, extract_xg, get_fixture_statistics,
)
from apis.odds_api  import (get_odds, calculate_value)
from models.poisson import (compute_ratings, build_lambdas,
                             form_weight, quick_predict)
from models.mle     import (fetch_and_fit, get_mle_lambdas,
                             apply_xg_adjustment,
                             apply_injury_adjustment,
                             apply_lineup_adjustment)
from database       import save_prediction, get_prediction

log = logging.getLogger(__name__)

# League average goals per game (home, away)
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

# MLE params cache (in-memory per process)
_MLE_CACHE: dict = {}


def _league_avg(league_id: int):
    return LEAGUE_AVGS.get(int(league_id), DEFAULT_AVG)


def _get_mle(league_id: int) -> dict:
    """Load or fit MLE params for a league (3 seasons)."""
    if league_id in _MLE_CACHE:
        return _MLE_CACHE[league_id]
    seasons = [2022, 2023, 2024]
    params  = fetch_and_fit(league_id, seasons)
    _MLE_CACHE[league_id] = params
    return params


# ─── Main entry points ───────────────────────────────────────
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
                     league_id: int = 39,
                     season: int = 2024) -> dict:
    home_ids = _search_team_id(home_name)
    away_ids = _search_team_id(away_name)
    return _build_prediction(
        home_id     = home_ids[0] if home_ids else None,
        away_id     = away_ids[0] if away_ids else None,
        home_name   = home_name,
        away_name   = away_name,
        league_id   = league_id,
        season      = season,
        fixture_id  = None,
        match_dt    = "Unknown",
        league_name = f"League {league_id}",
    )


# ─── Core builder ────────────────────────────────────────────
def _build_prediction(home_id, away_id, home_name, away_name,
                      league_id, season, fixture_id,
                      match_dt, league_name) -> dict:

    lga_h, lga_a = _league_avg(league_id)

    # ── 1. Fetch team stats ──────────────────────────────────
    home_stats = get_team_statistics(home_id, league_id, season) \
                 if home_id else {}
    away_stats = get_team_statistics(away_id, league_id, season) \
                 if away_id else {}

    # ── 2. Simple ratings (fallback) ─────────────────────────
    home_rat = compute_ratings(home_stats) if home_stats else {}
    away_rat = compute_ratings(away_stats) if away_stats else {}

    # ── 3. MLE-fitted team ratings (primary) ─────────────────
    mle_params = _get_mle(league_id)
    if mle_params and home_name in mle_params.get("attack", {}) \
                  and away_name in mle_params.get("attack", {}):
        lam_h, lam_a = get_mle_lambdas(
            home_name, away_name, mle_params, lga_h, lga_a
        )
        source = "MLE"
    else:
        # Fall back to simple ratings
        lam_h, lam_a = build_lambdas(home_rat, away_rat, lga_h, lga_a)
        source = "simple"

    log.info(f"Lambda source: {source} | {home_name} {lam_h} – {lam_a} {away_name}")

    # ── 4. Recent form adjustment ─────────────────────────────
    home_recent = get_team_last_matches(home_id, last=MODEL["form_matches"]) \
                  if home_id else []
    away_recent = get_team_last_matches(away_id, last=MODEL["form_matches"]) \
                  if away_id else []

    form_h = form_weight(home_recent, home_id) if home_id else 1.0
    form_a = form_weight(away_recent, away_id) if away_id else 1.0

    lam_h = round(max(0.2, min(lam_h * form_h, 6.0)), 3)
    lam_a = round(max(0.2, min(lam_a * form_a, 6.0)), 3)

    # ── 5. Head-to-head adjustment ───────────────────────────
    if home_id and away_id:
        h2h     = get_head_to_head(home_id, away_id, last=10)
        h2h_adj = _h2h_adjustment(h2h, home_id, away_id)
    else:
        h2h     = []
        h2h_adj = {"home_factor": 1.0, "away_factor": 1.0}

    lam_h = round(max(0.2, min(lam_h * h2h_adj["home_factor"], 6.0)), 3)
    lam_a = round(max(0.2, min(lam_a * h2h_adj["away_factor"], 6.0)), 3)

    # ── 6. xG adjustment ─────────────────────────────────────
    xg_h = get_recent_xg(home_id, last=6) if home_id else 0.0
    xg_a = get_recent_xg(away_id, last=6) if away_id else 0.0

    # Also pull fixture-specific xG if fixture_id available
    if fixture_id:
        fx_stats = get_fixture_statistics(fixture_id)
        fx_xg_h, fx_xg_a = extract_xg(fx_stats)
        if fx_xg_h > 0: xg_h = fx_xg_h
        if fx_xg_a > 0: xg_a = fx_xg_a

    if xg_h > 0 or xg_a > 0:
        lam_h, lam_a = apply_xg_adjustment(lam_h, lam_a, xg_h, xg_a)
        log.info(f"xG adjusted: {home_name} xG={xg_h} {away_name} xG={xg_a}")

    # ── 7. Injury adjustment ─────────────────────────────────
    home_injuries = get_injuries(team_id=home_id) if home_id else []
    away_injuries = get_injuries(team_id=away_id) if away_id else []

    if home_injuries or away_injuries:
        lam_h, lam_a = apply_injury_adjustment(
            lam_h, lam_a, home_injuries, away_injuries
        )
        log.info(
            f"Injury adjustment: {len(home_injuries)} home, "
            f"{len(away_injuries)} away injuries"
        )

    # ── 8. Lineup adjustment ─────────────────────────────────
    home_lineup = {}
    away_lineup = {}
    if fixture_id:
        lineups = get_lineups(fixture_id)
        if lineups:
            home_lineup = lineups[0] if len(lineups) > 0 else {}
            away_lineup = lineups[1] if len(lineups) > 1 else {}
        if home_lineup or away_lineup:
            lam_h, lam_a = apply_lineup_adjustment(
                lam_h, lam_a, home_lineup, away_lineup
            )
            log.info(
                f"Lineup adjustment: "
                f"home={home_lineup.get('formation','')} "
                f"away={away_lineup.get('formation','')}"
            )

    # ── 9. Run Poisson model ─────────────────────────────────
    markets = quick_predict(lam_h, lam_a)

    # ── 10. Confidence score ─────────────────────────────────
    confidence = _confidence_score(
        markets, home_rat, away_rat,
        len(home_recent), len(away_recent),
        has_xg=(xg_h > 0 or xg_a > 0),
        has_lineups=bool(home_lineup or away_lineup),
        has_injuries=bool(home_injuries or away_injuries),
        used_mle=(source == "MLE"),
    )

    # ── 11. Best tip ─────────────────────────────────────────
    tip = _select_best_tip(markets, confidence)

    # ── 12. Value bets ───────────────────────────────────────
    value_bets = _find_value_bets(markets, league_id)

    # ── 13. Metadata ─────────────────────────────────────────
    home_form_str = _form_string(home_recent, home_id)
    away_form_str = _form_string(away_recent, away_id)
    h2h_summary   = _h2h_summary(h2h, home_name, away_name)

    return {
        "fixture_id":    fixture_id,
        "home_name":     home_name,
        "away_name":     away_name,
        "league":        league_name,
        "match_date":    match_dt,
        "lambda_home":   lam_h,
        "lambda_away":   lam_a,
        "xg_home":       xg_h,
        "xg_away":       xg_a,
        "model_source":  source,
        "home_injuries": len(home_injuries),
        "away_injuries": len(away_injuries),
        "home_formation":home_lineup.get("formation", ""),
        "away_formation":away_lineup.get("formation", ""),
        "markets":       markets,
        "confidence":    confidence,
        "tip":           tip,
        "value_bets":    value_bets,
        "home_form":     home_form_str,
        "away_form":     away_form_str,
        "h2h_summary":   h2h_summary,
        "home_stats":    _summarise_stats(home_stats),
        "away_stats":    _summarise_stats(away_stats),
    }


# ─── Helpers ─────────────────────────────────────────────────
def _h2h_adjustment(h2h, home_id, away_id):
    if not h2h:
        return {"home_factor": 1.0, "away_factor": 1.0}
    hw = aw = d = 0
    for m in h2h[-8:]:
        gh  = m.get("goals", {}).get("home", 0) or 0
        ga  = m.get("goals", {}).get("away", 0) or 0
        hid = m.get("teams", {}).get("home", {}).get("id")
        if hid == home_id:
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
    return {
        "home_factor": round(0.95 + (hw / total) * 0.12, 3),
        "away_factor": round(0.95 + (aw / total) * 0.12, 3),
    }


def _confidence_score(markets, home_rat, away_rat,
                      home_n, away_n,
                      has_xg=False, has_lineups=False,
                      has_injuries=False, used_mle=False) -> int:
    base = 50

    # Data richness
    base += min(8,  home_n)
    base += min(8,  away_n)
    if used_mle:     base += 8
    if has_xg:       base += 6
    if has_lineups:  base += 5
    if has_injuries: base += 3

    # Favourite strength
    max_p = max(markets.get("p_home_win", 0),
                markets.get("p_draw",     0),
                markets.get("p_away_win", 0))
    if max_p > 0.65:   base += 8
    elif max_p > 0.55: base += 4

    # Penalise coin-flip
    if abs(markets.get("p_home_win", 0.33) -
           markets.get("p_away_win", 0.33)) < 0.05:
        base -= 5

    return max(40, min(95, base))


def _select_best_tip(markets, confidence):
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


def _find_value_bets(markets, league_id):
    sport_key = ("soccer_epl" if league_id == 39
                 else "soccer_uefa_champs_league")
    try:
        live_odds = get_odds(sport_key, markets="h2h,totals")
    except Exception:
        return []

    vbs      = []
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


def _market_prob(markets, key, outcome):
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


def _form_string(recent, team_id):
    s = []
    for m in recent[-6:]:
        gh  = m.get("goals", {}).get("home", 0) or 0
        ga  = m.get("goals", {}).get("away", 0) or 0
        hid = m.get("teams", {}).get("home", {}).get("id")
        if hid == team_id:
            s.append("W" if gh > ga else "D" if gh == ga else "L")
        else:
            s.append("W" if ga > gh else "D" if gh == ga else "L")
    return " ".join(s) or "N/A"


def _h2h_summary(h2h, home, away):
    hw = aw = d = hgf = agf = 0
    for m in h2h[-8:]:
        gh   = m.get("goals", {}).get("home", 0) or 0
        ga   = m.get("goals", {}).get("away", 0) or 0
        hgf += gh; agf += ga
        if gh > ga:   hw += 1
        elif ga > gh: aw += 1
        else:          d += 1
    total = hw + aw + d
    return {
        "total":        total,
        f"{home}_wins": hw,
        "draws":        d,
        f"{away}_wins": aw,
        "avg_goals":    round((hgf + agf) / total, 2) if total else 0,
    }


def _summarise_stats(stats):
    if not stats:
        return {}
    gs  = stats.get("goals",    {})
    fix = stats.get("fixtures", {})
    return {
        "played":        fix.get("played", {}).get("total", 0),
        "wins":          fix.get("wins",   {}).get("total", 0),
        "draws":         fix.get("draws",  {}).get("total", 0),
        "losses":        fix.get("loses",  {}).get("total", 0),
        "goals_for":     gs.get("for",
                         {}).get("total",   {}).get("total", 0),
        "goals_against": gs.get("against",
                         {}).get("total",   {}).get("total", 0),
        "avg_goals_for": gs.get("for",
                         {}).get("average", {}).get("total", 0),
        "form":          stats.get("form", ""),
    }


def _search_team_id(name: str) -> list:
    from apis.football_api import search_team
    teams = search_team(name)
    return [t["team"]["id"] for t in teams if t.get("team")]

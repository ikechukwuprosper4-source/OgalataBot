# ============================================================
# models/mle.py — Dixon-Coles MLE Parameter Fitting
# Fits attack/defence ratings using Maximum Likelihood
# Estimation across 3 seasons of historical match data
# ============================================================
import numpy as np
import logging
from scipy.optimize import minimize
from scipy.stats import poisson as sp_poisson

log = logging.getLogger(__name__)


def dc_tau(h: int, a: int, lam_h: float, lam_a: float, rho: float) -> float:
    """Dixon-Coles low-score correction factor."""
    if h == 0 and a == 0:
        return 1 - lam_h * lam_a * rho
    if h == 1 and a == 0:
        return 1 + lam_a * rho
    if h == 0 and a == 1:
        return 1 + lam_h * rho
    if h == 1 and a == 1:
        return 1 - rho
    return 1.0


def _neg_log_likelihood(params, matches, n_teams):
    """
    Negative log-likelihood for Dixon-Coles model.
    params layout:
      [alpha_0..alpha_n-1, beta_0..beta_n-1, log_gamma, rho]
    alpha = attack strength (log scale → always positive)
    beta  = defence weakness (log scale → always positive, lower = better def)
    gamma = home advantage multiplier
    rho   = low-score correlation (-0.99 to 0)
    """
    alphas = np.exp(params[:n_teams])
    betas  = np.exp(params[n_teams:2 * n_teams])
    gamma  = np.exp(params[2 * n_teams])
    rho    = np.clip(params[2 * n_teams + 1], -0.99, 0.0)

    total = 0.0
    for home_i, away_i, h, a in matches:
        lam_h = alphas[home_i] * betas[away_i] * gamma
        lam_a = alphas[away_i] * betas[home_i]

        tau = dc_tau(int(h), int(a), lam_h, lam_a, rho)
        if tau <= 0:
            return 1e10

        total += (
            np.log(max(tau, 1e-10)) +
            sp_poisson.logpmf(int(h), lam_h) +
            sp_poisson.logpmf(int(a), lam_a)
        )

    return -total


def fit_dc_model(historical_matches: list) -> dict:
    """
    Fit Dixon-Coles model via MLE.

    historical_matches: list of dicts with keys:
        home_team, away_team, home_goals, away_goals

    Returns dict with:
        attack  : {team_name: float}
        defence : {team_name: float}
        gamma   : float  (home advantage)
        rho     : float  (low-score correction)
        teams   : [team_name, ...]
    """
    if len(historical_matches) < 20:
        log.warning("Not enough matches for MLE fitting (need 20+)")
        return {}

    # Build team index
    teams = sorted(set(
        [m["home_team"] for m in historical_matches] +
        [m["away_team"] for m in historical_matches]
    ))
    team_idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)

    if n < 2:
        return {}

    # Build match array
    match_arr = []
    for m in historical_matches:
        h_name = m.get("home_team", "")
        a_name = m.get("away_team", "")
        h_goals = m.get("home_goals", 0)
        a_goals = m.get("away_goals", 0)
        if h_name in team_idx and a_name in team_idx:
            match_arr.append((
                team_idx[h_name],
                team_idx[a_name],
                int(h_goals or 0),
                int(a_goals or 0),
            ))

    if not match_arr:
        return {}

    # Initial parameters: all zeros in log space → all ones
    # [alphas(n), betas(n), log_gamma, rho]
    x0 = np.zeros(2 * n + 2)
    x0[2 * n]     = np.log(1.2)   # home advantage start
    x0[2 * n + 1] = -0.1          # rho start

    # Bounds: alphas/betas free in log space, gamma > 0, rho in [-0.99, 0]
    bounds = (
        [(-3, 3)] * n +          # log attack
        [(-3, 3)] * n +          # log defence
        [(0.0, 1.0)] +           # log home advantage (e^0=1 to e^1≈2.7)
        [(-0.99, 0.0)]           # rho
    )

    try:
        result = minimize(
            _neg_log_likelihood,
            x0,
            args=(match_arr, n),
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": 500, "ftol": 1e-9},
        )
        if not result.success:
            log.warning(f"MLE optimisation did not fully converge: {result.message}")

        params = result.x
        alphas = np.exp(params[:n])
        betas  = np.exp(params[n:2 * n])
        gamma  = float(np.exp(params[2 * n]))
        rho    = float(np.clip(params[2 * n + 1], -0.99, 0.0))

        # Normalise attack so mean = 1
        alpha_mean = float(np.mean(alphas))
        if alpha_mean > 0:
            alphas = alphas / alpha_mean

        attack  = {teams[i]: float(alphas[i]) for i in range(n)}
        defence = {teams[i]: float(betas[i])  for i in range(n)}

        log.info(
            f"MLE fitted {n} teams from {len(match_arr)} matches. "
            f"gamma={gamma:.3f} rho={rho:.3f}"
        )
        return {
            "attack":  attack,
            "defence": defence,
            "gamma":   gamma,
            "rho":     rho,
            "teams":   teams,
            "n_matches": len(match_arr),
        }

    except Exception as e:
        log.error(f"MLE fitting failed: {e}")
        return {}


def get_mle_lambdas(home_team: str, away_team: str,
                    mle_params: dict,
                    league_avg_home: float = 1.45,
                    league_avg_away: float = 1.10) -> tuple:
    """
    Compute λ_home and λ_away from MLE-fitted parameters.
    Falls back to league averages if team not in model.
    """
    if not mle_params:
        return league_avg_home, league_avg_away

    attack  = mle_params.get("attack",  {})
    defence = mle_params.get("defence", {})
    gamma   = mle_params.get("gamma",   1.2)

    h_atk = attack.get(home_team,  1.0)
    h_def = defence.get(home_team, 1.0)
    a_atk = attack.get(away_team,  1.0)
    a_def = defence.get(away_team, 1.0)

    lam_h = h_atk * a_def * gamma * league_avg_home
    lam_a = a_atk * h_def * league_avg_away

    lam_h = float(np.clip(lam_h, 0.2, 6.0))
    lam_a = float(np.clip(lam_a, 0.2, 6.0))

    return round(lam_h, 3), round(lam_a, 3)


def fetch_and_fit(league_id: int, seasons: list) -> dict:
    """
    Pull 3 seasons of results from API-Football and fit the MLE model.
    seasons: e.g. [2022, 2023, 2024]
    Returns fitted MLE params dict.
    """
    from apis.football_api import get_finished_fixtures
    from database import cache_get, cache_set

    cache_key = f"mle_params_{league_id}_{'_'.join(map(str, seasons))}"
    cached = cache_get(cache_key)
    if cached:
        log.info(f"MLE params loaded from cache for league {league_id}")
        return cached

    all_matches = []
    for season in seasons:
        log.info(f"Fetching finished fixtures: league={league_id} season={season}")
        fixtures = get_finished_fixtures(league_id, season)
        for f in fixtures:
            try:
                home = f["teams"]["home"]["name"]
                away = f["teams"]["away"]["name"]
                hg   = f["goals"]["home"]
                ag   = f["goals"]["away"]
                if hg is None or ag is None:
                    continue
                all_matches.append({
                    "home_team":  home,
                    "away_team":  away,
                    "home_goals": int(hg),
                    "away_goals": int(ag),
                })
            except Exception:
                continue

    log.info(f"Total historical matches collected: {len(all_matches)}")
    params = fit_dc_model(all_matches)

    if params:
        # Cache for 12 hours
        cache_set(cache_key, params, ttl=43200)

    return params


def apply_xg_adjustment(lam_h: float, lam_a: float,
                        xg_h: float, xg_a: float,
                        weight: float = 0.35) -> tuple:
    """
    Blend Poisson λ with xG data.
    weight=0.35 means xG contributes 35% to final λ.
    """
    if xg_h > 0:
        lam_h = (1 - weight) * lam_h + weight * xg_h
    if xg_a > 0:
        lam_a = (1 - weight) * lam_a + weight * xg_a

    lam_h = float(np.clip(lam_h, 0.2, 6.0))
    lam_a = float(np.clip(lam_a, 0.2, 6.0))
    return round(lam_h, 3), round(lam_a, 3)


def apply_injury_adjustment(lam_h: float, lam_a: float,
                             home_injuries: list,
                             away_injuries: list) -> tuple:
    """
    Reduce λ based on key player injuries.
    Each injury reduces attack by ~4%.
    Goalkeeper injury reduces defence by ~6%.
    """
    KEY_POSITIONS = {"Attacker", "Midfielder"}
    GK_POSITIONS  = {"Goalkeeper"}

    def _penalty(injuries: list) -> tuple:
        atk_pen = 0.0
        def_pen = 0.0
        for inj in injuries:
            pos = inj.get("player", {}).get("type", "") or \
                  inj.get("player", {}).get("position", "")
            if any(p in pos for p in KEY_POSITIONS):
                atk_pen += 0.04
            elif any(p in pos for p in GK_POSITIONS):
                def_pen += 0.06
        return min(atk_pen, 0.20), min(def_pen, 0.15)

    h_atk_pen, h_def_pen = _penalty(home_injuries)
    a_atk_pen, a_def_pen = _penalty(away_injuries)

    # Home attack reduced → fewer home goals
    lam_h *= (1 - h_atk_pen)
    # Away defence reduced (GK injury) → more home goals
    lam_h *= (1 + a_def_pen)

    # Away attack reduced → fewer away goals
    lam_a *= (1 - a_atk_pen)
    # Home defence reduced → more away goals
    lam_a *= (1 + h_def_pen)

    lam_h = float(np.clip(lam_h, 0.2, 6.0))
    lam_a = float(np.clip(lam_a, 0.2, 6.0))
    return round(lam_h, 3), round(lam_a, 3)


def apply_lineup_adjustment(lam_h: float, lam_a: float,
                             home_lineup: dict,
                             away_lineup: dict) -> tuple:
    """
    Adjust λ based on confirmed starting lineups.
    Formation affects expected goals:
    - Attacking formations (4-3-3, 4-2-4) → +5% attack
    - Defensive formations (5-4-1, 4-5-1) → -5% attack
    """
    ATTACKING = {"4-3-3", "4-2-4", "4-2-3-1", "3-4-3"}
    DEFENSIVE = {"5-4-1", "4-5-1", "5-3-2", "4-4-2"}

    def _form_factor(lineup: dict) -> float:
        formation = lineup.get("formation", "") or ""
        if formation in ATTACKING:
            return 1.05
        if formation in DEFENSIVE:
            return 0.95
        return 1.0

    lam_h *= _form_factor(home_lineup)
    lam_a *= _form_factor(away_lineup)

    lam_h = float(np.clip(lam_h, 0.2, 6.0))
    lam_a = float(np.clip(lam_a, 0.2, 6.0))
    return round(lam_h, 3), round(lam_a, 3)

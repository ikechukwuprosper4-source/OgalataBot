# ============================================================
# models/poisson.py — Dixon-Coles Poisson Model
# ============================================================
import math, logging
from functools import lru_cache
from config import MODEL

log = logging.getLogger(__name__)

MAX_G = MODEL["max_goals_sim"]


# ─── Poisson PMF ─────────────────────────────────────────────
@lru_cache(maxsize=512)
def poisson_pmf(lam: float, k: int) -> float:
    if lam <= 0 or k < 0:
        return 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


# ─── Dixon-Coles tau correction ──────────────────────────────
def _tau(home_goals: int, away_goals: int, lh: float, la: float,
         rho: float) -> float:
    if home_goals == 0 and away_goals == 0:
        return 1 - lh * la * rho
    if home_goals == 1 and away_goals == 0:
        return 1 + la * rho
    if home_goals == 0 and away_goals == 1:
        return 1 + lh * rho
    if home_goals == 1 and away_goals == 1:
        return 1 - rho
    return 1.0


# ─── Score Matrix ─────────────────────────────────────────────
def score_matrix(lambda_home: float, lambda_away: float,
                 rho: float = MODEL["dixon_coles_rho"]) -> list:
    mat = []
    for i in range(MAX_G + 1):
        row = []
        for j in range(MAX_G + 1):
            p = (poisson_pmf(lambda_home, i) *
                 poisson_pmf(lambda_away, j) *
                 _tau(i, j, lambda_home, lambda_away, rho))
            row.append(max(0.0, p))
        mat.append(row)

    total = sum(mat[i][j]
                for i in range(MAX_G + 1)
                for j in range(MAX_G + 1))
    if total > 0:
        mat = [[mat[i][j] / total
                for j in range(MAX_G + 1)]
               for i in range(MAX_G + 1)]
    return mat


# ─── Team strength ratings ───────────────────────────────────
def compute_ratings(team_stats: dict) -> dict:
    gs  = team_stats.get("goals", {})
    fix = team_stats.get("fixtures", {})

    home_played  = fix.get("played", {}).get("home", 1) or 1
    away_played  = fix.get("played", {}).get("away", 1) or 1
    total_played = home_played + away_played

    hf = gs.get("for",     {}).get("total", {}).get("home", 0) or 0
    ha = gs.get("against", {}).get("total", {}).get("home", 0) or 0
    af = gs.get("for",     {}).get("total", {}).get("away", 0) or 0
    aa = gs.get("against", {}).get("total", {}).get("away", 0) or 0

    return {
        "home_attack":   hf / home_played,
        "home_defence":  ha / home_played,
        "away_attack":   af / away_played,
        "away_defence":  aa / away_played,
        "total_attack":  (hf + af) / total_played,
        "total_defence": (ha + aa) / total_played,
    }


def build_lambdas(home_ratings: dict, away_ratings: dict,
                  league_avg_home: float = 1.45,
                  league_avg_away: float = 1.10) -> tuple:
    if not home_ratings or not away_ratings:
        return league_avg_home, league_avg_away

    lga_h = league_avg_home
    lga_a = league_avg_away

    home_atk = (home_ratings.get("home_attack",  lga_h) / lga_h)
    away_def = (away_ratings.get("away_defence", lga_h) / lga_h)
    away_atk = (away_ratings.get("away_attack",  lga_a) / lga_a)
    home_def = (home_ratings.get("home_defence", lga_a) / lga_a)

    lam_home = home_atk * away_def * lga_h * MODEL["home_advantage"]
    lam_away = away_atk * home_def * lga_a

    lam_home = max(0.2, min(lam_home, 6.0))
    lam_away = max(0.2, min(lam_away, 6.0))
    return round(lam_home, 3), round(lam_away, 3)


# ─── Form-adjusted lambdas ────────────────────────────────────
def form_weight(recent_matches: list, team_id: int,
                n: int = MODEL["form_matches"]) -> float:
    if not recent_matches:
        return 1.0
    pts = []
    for m in recent_matches[-n:]:
        goals_h = m.get("goals", {}).get("home", 0) or 0
        goals_a = m.get("goals", {}).get("away", 0) or 0
        home_id = (m.get("teams", {}).get("home", {}).get("id"))
        is_home = (home_id == team_id)
        if is_home:
            pts.append(1.0 if goals_h > goals_a else
                       0.5 if goals_h == goals_a else 0.0)
        else:
            pts.append(1.0 if goals_a > goals_h else
                       0.5 if goals_h == goals_a else 0.0)
    if not pts:
        return 1.0
    avg = sum(pts) / len(pts)
    return round(0.85 + avg * 0.30, 3)


# ─── Quick prediction ─────────────────────────────────────────
def quick_predict(lam_home: float, lam_away: float) -> dict:
    mat = score_matrix(lam_home, lam_away)
    return compute_all_markets(mat, lam_home, lam_away)


# ─── Full market computation ──────────────────────────────────
def compute_all_markets(mat: list,
                        lam_home: float,
                        lam_away: float) -> dict:
    p_home_win = p_draw = p_away_win = 0.0
    p_over     = {0.5: 0, 1.5: 0, 2.5: 0, 3.5: 0, 4.5: 0}
    p_btts     = 0.0
    p_no_btts  = 0.0
    correct_scores = {}

    for i in range(MAX_G + 1):
        for j in range(MAX_G + 1):
            p     = mat[i][j]
            total = i + j

            if i > j:    p_home_win += p
            elif i == j: p_draw     += p
            else:        p_away_win += p

            for line in p_over:
                if total > line:
                    p_over[line] += p

            if i > 0 and j > 0:
                p_btts    += p
            else:
                p_no_btts += p

            if i <= 4 and j <= 4:
                correct_scores[f"{i}-{j}"] = \
                    round(correct_scores.get(f"{i}-{j}", 0) + p, 5)

    ah  = compute_asian_handicap(mat)

    p_1x = p_home_win + p_draw
    p_x2 = p_draw + p_away_win
    p_12 = p_home_win + p_away_win

    dnb_home = p_home_win / (p_home_win + p_away_win) \
               if (p_home_win + p_away_win) > 0 else 0
    dnb_away = p_away_win / (p_home_win + p_away_win) \
               if (p_home_win + p_away_win) > 0 else 0

    exp_total = lam_home + lam_away
    margins   = compute_winning_margins(mat)

    top_cs = sorted(correct_scores.items(),
                    key=lambda x: x[1], reverse=True)[:10]

    fg_home = lam_home / (lam_home + lam_away) \
              if (lam_home + lam_away) > 0 else 0.5
    fg_away = 1 - fg_home
    fg_no   = poisson_pmf(lam_home, 0) * poisson_pmf(lam_away, 0)

    cs_home = poisson_pmf(lam_away, 0)
    cs_away = poisson_pmf(lam_home, 0)

    ht_mat  = score_matrix(lam_home / 2, lam_away / 2)
    ht_home = sum(ht_mat[i][j] for i in range(MAX_G+1)
                               for j in range(MAX_G+1) if i > j)
    ht_draw = sum(ht_mat[i][j] for i in range(MAX_G+1)
                               for j in range(MAX_G+1) if i == j)
    ht_away = sum(ht_mat[i][j] for i in range(MAX_G+1)
                               for j in range(MAX_G+1) if i < j)

    sh_lh  = lam_home * 0.55
    sh_la  = lam_away * 0.55
    sh_over = {}
    for line in [0.5, 1.5, 2.5]:
        sh_over[line] = 1 - sum(
            poisson_pmf(sh_lh, i) * poisson_pmf(sh_la, j)
            for i in range(MAX_G + 1) for j in range(MAX_G + 1)
            if i + j <= line
        )

    total_goals_bands = {}
    for label, lo, hi in [("0-1", 0, 1), ("2-3", 2, 3), ("4+", 4, MAX_G*2)]:
        prob = sum(mat[i][j]
                   for i in range(MAX_G+1)
                   for j in range(MAX_G+1)
                   if lo <= i+j <= hi)
        total_goals_bands[label] = round(prob, 4)

    est_corners_home  = round(5.5 + (lam_home - 1.2) * 0.8, 1)
    est_corners_away  = round(4.5 + (lam_away - 1.0) * 0.8, 1)
    est_corners_total = est_corners_home + est_corners_away

    return {
        "lambda_home":          lam_home,
        "lambda_away":          lam_away,
        "expected_goals":       round(exp_total, 2),
        "expected_home_goals":  lam_home,
        "expected_away_goals":  lam_away,
        "p_home_win":           round(p_home_win, 4),
        "p_draw":               round(p_draw,     4),
        "p_away_win":           round(p_away_win, 4),
        "p_1x":                 round(p_1x, 4),
        "p_x2":                 round(p_x2, 4),
        "p_12":                 round(p_12, 4),
        "dnb_home":             round(dnb_home, 4),
        "dnb_away":             round(dnb_away, 4),
        "over_under": {str(k): {
            "over":  round(v, 4),
            "under": round(1 - v, 4)
        } for k, v in p_over.items()},
        "btts_yes":             round(p_btts,    4),
        "btts_no":              round(p_no_btts, 4),
        "correct_scores":       dict(top_cs),
        "top_correct_score":    top_cs[0][0] if top_cs else "1-0",
        "ht_home":              round(ht_home, 4),
        "ht_draw":              round(ht_draw, 4),
        "ht_away":              round(ht_away, 4),
        "second_half_over": {str(k): round(v, 4)
                              for k, v in sh_over.items()},
        "asian_handicap":       ah,
        "first_goal_home":      round(fg_home, 4),
        "first_goal_away":      round(fg_away, 4),
        "first_goal_no":        round(fg_no,   4),
        "clean_sheet_home":     round(cs_home, 4),
        "clean_sheet_away":     round(cs_away, 4),
        "winning_margins":      margins,
        "total_goals_bands":    total_goals_bands,
        "est_corners_home":     est_corners_home,
        "est_corners_away":     est_corners_away,
        "est_corners_total":    round(est_corners_total, 1),
        "est_cards_total":      3.5,
    }


def compute_asian_handicap(mat: list) -> dict:
    lines  = [-2.5, -2.0, -1.5, -1.0, -0.5, 0, 0.5, 1.0, 1.5, 2.0, 2.5]
    result = {}
    for hcap in lines:
        p_home = p_away = p_push = 0.0
        for i in range(MAX_G + 1):
            for j in range(MAX_G + 1):
                diff = i - j + hcap
                p    = mat[i][j]
                if diff > 0:   p_home += p
                elif diff < 0: p_away += p
                else:          p_push += p
        result[str(hcap)] = {
            "home": round(p_home, 4),
            "push": round(p_push, 4),
            "away": round(p_away, 4),
        }
    return result


def compute_winning_margins(mat: list) -> dict:
    margins = {}
    for diff in range(-MAX_G, MAX_G + 1):
        p = sum(mat[i][j]
                for i in range(MAX_G + 1)
                for j in range(MAX_G + 1)
                if (i - j) == diff)
        label = ("Draw" if diff == 0
                 else f"Home +{diff}" if diff > 0
                 else f"Away +{abs(diff)}")
        margins[label] = round(p, 4)
    return margins

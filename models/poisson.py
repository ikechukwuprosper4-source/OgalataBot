# ============================================================
# models/poisson.py — Dixon-Coles Poisson Model
# ============================================================
import math, logging
from functools import lru_cache
from config import MODEL

log = logging.getLogger(__name__)
MAX_G = MODEL["max_goals_sim"]


@lru_cache(maxsize=512)
def poisson_pmf(lam: float, k: int) -> float:
    if lam <= 0 or k < 0:
        return 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _tau(h: int, a: int, lh: float, la: float, rho: float) -> float:
    if h == 0 and a == 0: return 1 - lh * la * rho
    if h == 1 and a == 0: return 1 + la * rho
    if h == 0 and a == 1: return 1 + lh * rho
    if h == 1 and a == 1: return 1 - rho
    return 1.0


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


def compute_ratings(team_stats: dict) -> dict:
    gs  = team_stats.get("goals",    {})
    fix = team_stats.get("fixtures", {})
    hp  = fix.get("played", {}).get("home", 1) or 1
    ap  = fix.get("played", {}).get("away", 1) or 1
    tp  = hp + ap
    hf  = gs.get("for",     {}).get("total", {}).get("home", 0) or 0
    ha  = gs.get("against", {}).get("total", {}).get("home", 0) or 0
    af  = gs.get("for",     {}).get("total", {}).get("away", 0) or 0
    aa  = gs.get("against", {}).get("total", {}).get("away", 0) or 0
    return {
        "home_attack":   hf / hp,
        "home_defence":  ha / hp,
        "away_attack":   af / ap,
        "away_defence":  aa / ap,
        "total_attack":  (hf + af) / tp,
        "total_defence": (ha + aa) / tp,
    }


def build_lambdas(home_rat: dict, away_rat: dict,
                  lga_h: float = 1.45,
                  lga_a: float = 1.10) -> tuple:
    if not home_rat or not away_rat:
        return lga_h, lga_a
    h_atk = (home_rat.get("home_attack",  lga_h) / lga_h)
    a_def = (away_rat.get("away_defence", lga_h) / lga_h)
    a_atk = (away_rat.get("away_attack",  lga_a) / lga_a)
    h_def = (home_rat.get("home_defence", lga_a) / lga_a)
    lam_h = h_atk * a_def * lga_h * MODEL["home_advantage"]
    lam_a = a_atk * h_def * lga_a
    return (round(max(0.2, min(lam_h, 6.0)), 3),
            round(max(0.2, min(lam_a, 6.0)), 3))


def form_weight(recent: list, team_id: int,
                n: int = MODEL["form_matches"]) -> float:
    if not recent:
        return 1.0
    pts = []
    for m in recent[-n:]:
        gh  = m.get("goals", {}).get("home", 0) or 0
        ga  = m.get("goals", {}).get("away", 0) or 0
        hid = m.get("teams", {}).get("home", {}).get("id")
        if hid == team_id:
            pts.append(1.0 if gh > ga else 0.5 if gh == ga else 0.0)
        else:
            pts.append(1.0 if ga > gh else 0.5 if gh == ga else 0.0)
    avg = sum(pts) / len(pts) if pts else 0.5
    return round(0.85 + avg * 0.30, 3)


def quick_predict(lam_home: float, lam_away: float,
                  rho: float = MODEL["dixon_coles_rho"]) -> dict:
    mat = score_matrix(lam_home, lam_away, rho)
    return compute_all_markets(mat, lam_home, lam_away)


def compute_all_markets(mat: list, lam_h: float, lam_a: float) -> dict:
    p_hw = p_d = p_aw = p_btts = p_nbtts = 0.0
    p_over = {0.5: 0, 1.5: 0, 2.5: 0, 3.5: 0, 4.5: 0}
    cs = {}

    for i in range(MAX_G + 1):
        for j in range(MAX_G + 1):
            p = mat[i][j]
            if i > j:    p_hw   += p
            elif i == j: p_d    += p
            else:        p_aw   += p
            for line in p_over:
                if i + j > line: p_over[line] += p
            if i > 0 and j > 0: p_btts  += p
            else:                p_nbtts += p
            if i <= 4 and j <= 4:
                cs[f"{i}-{j}"] = round(cs.get(f"{i}-{j}", 0) + p, 5)

    ah      = compute_asian_handicap(mat)
    top_cs  = sorted(cs.items(), key=lambda x: x[1], reverse=True)[:10]
    fg_home = lam_h / (lam_h + lam_a) if (lam_h + lam_a) > 0 else 0.5

    ht_mat  = score_matrix(lam_h / 2, lam_a / 2)
    ht_home = sum(ht_mat[i][j] for i in range(MAX_G+1)
                               for j in range(MAX_G+1) if i > j)
    ht_draw = sum(ht_mat[i][j] for i in range(MAX_G+1)
                               for j in range(MAX_G+1) if i == j)
    ht_away = sum(ht_mat[i][j] for i in range(MAX_G+1)
                               for j in range(MAX_G+1) if i < j)

    sh_over = {}
    for line in [0.5, 1.5, 2.5]:
        sh_over[line] = 1 - sum(
            poisson_pmf(lam_h * 0.55, i) * poisson_pmf(lam_a * 0.55, j)
            for i in range(MAX_G + 1)
            for j in range(MAX_G + 1)
            if i + j <= line
        )

    tgb = {}
    for label, lo, hi in [("0-1",0,1),("2-3",2,3),("4+",4,MAX_G*2)]:
        tgb[label] = round(sum(mat[i][j]
                               for i in range(MAX_G+1)
                               for j in range(MAX_G+1)
                               if lo <= i+j <= hi), 4)

    p_1x = p_hw + p_d
    p_x2 = p_d  + p_aw
    p_12 = p_hw + p_aw
    dnb_h = p_hw / (p_hw + p_aw) if (p_hw + p_aw) > 0 else 0.5
    dnb_a = p_aw / (p_hw + p_aw) if (p_hw + p_aw) > 0 else 0.5

    return {
        "lambda_home":         lam_h,
        "lambda_away":         lam_a,
        "expected_goals":      round(lam_h + lam_a, 2),
        "expected_home_goals": lam_h,
        "expected_away_goals": lam_a,
        "p_home_win":          round(p_hw, 4),
        "p_draw":              round(p_d,  4),
        "p_away_win":          round(p_aw, 4),
        "p_1x":                round(p_1x, 4),
        "p_x2":                round(p_x2, 4),
        "p_12":                round(p_12, 4),
        "dnb_home":            round(dnb_h, 4),
        "dnb_away":            round(dnb_a, 4),
        "over_under": {str(k): {
            "over":  round(v, 4),
            "under": round(1 - v, 4)
        } for k, v in p_over.items()},
        "btts_yes":            round(p_btts,  4),
        "btts_no":             round(p_nbtts, 4),
        "correct_scores":      dict(top_cs),
        "top_correct_score":   top_cs[0][0] if top_cs else "1-0",
        "ht_home":             round(ht_home, 4),
        "ht_draw":             round(ht_draw, 4),
        "ht_away":             round(ht_away, 4),
        "second_half_over": {str(k): round(v, 4)
                              for k, v in sh_over.items()},
        "asian_handicap":      ah,
        "first_goal_home":     round(fg_home, 4),
        "first_goal_away":     round(1 - fg_home, 4),
        "first_goal_no":       round(poisson_pmf(lam_h,0)*poisson_pmf(lam_a,0), 4),
        "clean_sheet_home":    round(poisson_pmf(lam_a, 0), 4),
        "clean_sheet_away":    round(poisson_pmf(lam_h, 0), 4),
        "winning_margins":     compute_winning_margins(mat),
        "total_goals_bands":   tgb,
        "est_corners_home":    round(5.5 + (lam_h - 1.2) * 0.8, 1),
        "est_corners_away":    round(4.5 + (lam_a - 1.0) * 0.8, 1),
        "est_corners_total":   round(10.0 + (lam_h + lam_a - 2.2) * 0.8, 1),
        "est_cards_total":     3.5,
    }


def compute_asian_handicap(mat: list) -> dict:
    result = {}
    for hcap in [-2.5,-2.0,-1.5,-1.0,-0.5,0,0.5,1.0,1.5,2.0,2.5]:
        ph = pa = pp = 0.0
        for i in range(MAX_G + 1):
            for j in range(MAX_G + 1):
                diff = i - j + hcap
                p    = mat[i][j]
                if diff > 0:   ph += p
                elif diff < 0: pa += p
                else:          pp += p
        result[str(hcap)] = {
            "home": round(ph, 4),
            "push": round(pp, 4),
            "away": round(pa, 4),
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

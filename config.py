# ============================================================
# ProSportsBot - Configuration
# ============================================================

# ─── Telegram ───────────────────────────────────────────────
TELEGRAM_TOKEN   = "8749652252:AAFtnh8JY34GUUkT1MaWoVngggT6UQpgA50"
ADMIN_USER_ID    = 8513202329          # Your Telegram user ID

# ─── Sports APIs ────────────────────────────────────────────
API_FOOTBALL_KEY      = "0681c2db99f49aef5f2c318f15f0578b"
API_FOOTBALL_BASE     = "https://v3.football.api-sports.io"

FOOTBALL_DATA_KEY     = "98f9543e14564bfabc7468d1a70f3bbf"
FOOTBALL_DATA_BASE    = "https://api.football-data.org/v4"

ODDS_API_KEY          = "b8600fa846ddfe9f3e14bb3f78c2389b"
ODDS_API_BASE         = "https://api.the-odds-api.com/v4"

# ─── Supported Leagues (API-Football IDs) ───────────────────
SUPPORTED_LEAGUES = {
    "Premier League":    {"id": 39,  "country": "England",  "season": 2024},
    "La Liga":           {"id": 140, "country": "Spain",    "season": 2024},
    "Serie A":           {"id": 135, "country": "Italy",    "season": 2024},
    "Bundesliga":        {"id": 78,  "country": "Germany",  "season": 2024},
    "Ligue 1":           {"id": 61,  "country": "France",   "season": 2024},
    "Champions League":  {"id": 2,   "country": "Europe",   "season": 2024},
    "Europa League":     {"id": 3,   "country": "Europe",   "season": 2024},
    "Conference League": {"id": 848, "country": "Europe",   "season": 2024},
    "Serie A Brazil":    {"id": 71,  "country": "Brazil",   "season": 2024},
    "Eredivisie":        {"id": 88,  "country": "Netherlands","season": 2024},
    "Primeira Liga":     {"id": 94,  "country": "Portugal", "season": 2024},
}

# ─── Odds API Sport Keys ─────────────────────────────────────
ODDS_SPORTS = {
    "football":   "soccer_epl",
    "basketball": "basketball_nba",
    "tennis":     "tennis_atp",
}

# ─── Prediction Model Settings ──────────────────────────────
MODEL = {
    "home_advantage":        1.20,   # Home team scoring multiplier
    "min_matches_required":  5,      # Min matches needed for rating
    "form_matches":          6,      # Recent matches for form calc
    "dixon_coles_rho":       -0.13,  # Low-score correction factor
    "max_goals_sim":         10,     # Max goals in Poisson matrix
    "confidence_threshold":  0.60,   # Min confidence to display tip
    "min_value_edge":        0.05,   # Min 5% edge to flag value bet
    "kelly_fraction":        0.25,   # Fractional Kelly (0.25 = quarter Kelly)
    "max_kelly_stake":       0.05,   # Never stake more than 5% bankroll
}

# ─── Risk Management ────────────────────────────────────────
RISK = {
    "default_bankroll":    1000,     # Default bankroll in user's currency
    "max_daily_bets":      10,
    "max_bet_pct":         0.05,     # 5% max per bet
    "min_confidence":      55,       # Min confidence % to recommend
    "avoid_odds_above":    10.0,     # Avoid longshots above these odds
    "avoid_odds_below":    1.15,     # Avoid heavy favourites below these
}

# ─── Cache Settings ─────────────────────────────────────────
CACHE = {
    "fixtures_ttl":      300,        # 5 minutes
    "standings_ttl":     3600,       # 1 hour
    "team_stats_ttl":    7200,       # 2 hours
    "predictions_ttl":   1800,       # 30 minutes
}

# ─── Database ────────────────────────────────────────────────
DATABASE_PATH = "prosportsbot.db"

# ─── Emoji Map ───────────────────────────────────────────────
EMOJI = {
    "soccer": "⚽", "basketball": "🏀", "tennis": "🎾",
    "win": "✅", "loss": "❌", "draw": "🤝",
    "fire": "🔥", "chart": "📊", "money": "💰",
    "warning": "⚠️", "star": "⭐", "trophy": "🏆",
    "up": "📈", "down": "📉", "lock": "🔒",
    "calendar": "📅", "clock": "🕐", "bot": "🤖",
    "green": "🟢", "red": "🔴", "yellow": "🟡",
    "diamond": "💎", "rocket": "🚀", "target": "🎯",
}

# 🤖 ProSportsBot — AI Sports Prediction Telegram Bot

A production-grade Telegram sports prediction bot powered by:
- **Dixon-Coles Poisson model** (industry-standard football goal model)
- **API-Football** (fixtures, stats, lineups, H2H)
- **Football-Data.org** (standings, match history)
- **The Odds API** (live bookmaker odds + value bet detection)
- **Kelly Criterion** (mathematically optimal stake sizing)

---

## 🚀 Quick Setup

### 1. Requirements
- Python 3.10+
- A server or PC that stays online (VPS recommended)

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the bot
```bash
python main.py
```

That's it! The bot connects to Telegram and begins polling.

---

## 📱 Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome screen + main menu |
| `/predict Arsenal vs Chelsea` | Full multi-market prediction |
| `/fixture 1234567` | Predict by API-Football fixture ID |
| `/today` | Today's matches with tips |
| `/upcoming` | Browse upcoming fixtures by league |
| `/live` | Live scores right now |
| `/odds Arsenal vs Chelsea` | Compare live bookmaker odds |
| `/h2h Arsenal Chelsea` | Head-to-head record |
| `/form Arsenal` | Recent form (last 10 games) |
| `/standings PL` | League table (PL, PD, SA, BL1, FL1, CL) |
| `/valuebets` | Scan for value bet opportunities |
| `/bankroll 1000` | Set your bankroll |
| `/bet 1234 1X2 HomeWin 1.95 50` | Log a bet for tracking |
| `/mystats` | Your win rate, P&L, history |
| `/betbuilder` | Guide to building combo bets |
| `/help` | Full command list |

---

## 🎯 Markets Predicted

### Match Result
- ✅ 1X2 (Home / Draw / Away)
- ✅ Double Chance (1X, X2, 12)
- ✅ Draw No Bet

### Goals
- ✅ Over/Under 0.5 / 1.5 / 2.5 / 3.5 / 4.5
- ✅ Both Teams to Score (Yes/No)
- ✅ Total Goals Bands (0-1, 2-3, 4+)
- ✅ Expected Goals (xG) per team

### Half-Time / 2nd Half
- ✅ Halftime Result (1X2)
- ✅ 2nd Half Over/Under 0.5 / 1.5 / 2.5

### Handicap
- ✅ Asian Handicap -2.5 to +2.5
- ✅ Standard Handicap guidance

### Special Markets
- ✅ Correct Score (top 6 probabilities + fair odds)
- ✅ First Goal Scorer (team probability)
- ✅ Clean Sheet (both teams)
- ✅ Winning Margin distribution

### Estimated Markets
- ✅ Corner totals (home / away / total)
- ✅ Card totals

### Combo / Bet Builder
- ✅ Full Bet Builder guide with safe/medium/aggressive combos

---

## 💡 The Prediction Model

### Dixon-Coles Poisson Model
The bot uses the **Dixon-Coles (1997)** method:

1. **Team Ratings**: Attack and defence ratings derived from goals scored/conceded per game
2. **Expected Goals**: λ_home = home_attack × away_defence × home_advantage × league_average
3. **Score Matrix**: A 10×10 probability matrix for every scoreline 0-0 to 10-10
4. **Low-score Correction**: τ factor corrects the well-known under-prediction of 0-0, 1-0, 0-1, 1-1 results
5. **Form Weighting**: Recent form (last 6 games) adjusts λ by ±15%
6. **H2H Adjustment**: Historical head-to-head record nudges probabilities by up to ±5%

All other markets (Over/Under, BTTS, Correct Score, Asian Handicap, etc.) are derived mathematically from the same score matrix.

### Value Bet Detection
- Compares model probability against live bookmaker implied probability
- Only flags bets with **>5% edge** (configurable in config.py)
- Uses **¼ Kelly Criterion** for stake recommendations (conservative)

---

## 💰 Bankroll Management (Built-in)

The bot enforces responsible gambling:
- Maximum 5% of bankroll per bet
- Quarter-Kelly staking (never full Kelly)
- Minimum 55% confidence threshold before recommending
- Avoids odds above 10.0 (longshots) and below 1.15 (heavy favourites)
- Daily bet limit tracking

---

## ⚙️ Configuration (config.py)

Key settings you can adjust:

```python
MODEL = {
    "home_advantage":   1.20,   # Home scoring multiplier
    "min_value_edge":   0.05,   # 5% minimum edge for value bets
    "kelly_fraction":   0.25,   # Quarter Kelly
    "max_kelly_stake":  0.05,   # Never stake >5% bankroll
}

RISK = {
    "max_bet_pct":      0.05,   # 5% per bet
    "min_confidence":   55,     # Min confidence to recommend
    "avoid_odds_above": 10.0,
    "avoid_odds_below": 1.15,
}
```

---

## 📊 Supported Leagues

- 🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League
- 🇪🇸 La Liga
- 🇮🇹 Serie A
- 🇩🇪 Bundesliga
- 🇫🇷 Ligue 1
- 🌍 Champions League
- 🌍 Europa League
- 🌍 Conference League
- 🇳🇱 Eredivisie
- 🇵🇹 Primeira Liga
- 🇧🇷 Brasileirão

---

## 🔄 Automated Features (Scheduler)

- **08:00 UTC daily**: Morning picks sent to all users
- **Every 2 hours**: Value bet scan (only strong edges notified)
- **Every 10 minutes**: Pre-match alerts 1 hour before kick-off
- **Every 6 hours**: Database cache cleanup

---

## ⚠️ Disclaimer

This bot is for **educational and entertainment purposes**. No prediction system guarantees profit. Always bet within your means. The model is based on historical statistics and market pricing — actual match outcomes involve randomness and events the model cannot predict (injuries at kick-off, weather, referee decisions, etc.).

**Past performance does not guarantee future results.**

---

## 🗂 File Structure

```
ProSportsBot/
├── main.py              # Entry point
├── config.py            # All API keys & settings
├── database.py          # SQLite (cache, bets, users)
├── scheduler.py         # Background automation
├── requirements.txt
├── apis/
│   ├── football_api.py  # API-Football v3
│   ├── football_data.py # Football-Data.org v4
│   └── odds_api.py      # The Odds API + value calc
├── models/
│   ├── poisson.py       # Dixon-Coles model
│   └── analyzer.py      # Full prediction pipeline
└── bot/
    ├── handlers.py      # All Telegram command handlers
    ├── keyboards.py     # Inline keyboards
    └── formatters.py    # Rich message formatting
```

# ============================================================
# bot/formatters.py — Rich Telegram message builders
# ============================================================
from config import EMOJI as E, RISK


def _pct(p: float) -> str:
    return f"{p * 100:.1f}%"


def _odds(p: float) -> str:
    if p <= 0:
        return "N/A"
    return f"{1/p:.2f}"


def _bar(p: float, width: int = 12) -> str:
    filled = round(p * width)
    return "█" * filled + "░" * (width - filled)


def _conf_emoji(conf: int) -> str:
    if conf >= 80: return "🔥🔥🔥"
    if conf >= 70: return "🔥🔥"
    if conf >= 60: return "🔥"
    return "⚠️"


def format_prediction(pred: dict) -> str:
    m    = pred.get("markets", {})
    tip  = pred.get("tip", {})
    hf   = pred.get("home_form", "N/A")
    af   = pred.get("away_form", "N/A")
    h2h  = pred.get("h2h_summary", {})
    hs   = pred.get("home_stats",  {})
    as_  = pred.get("away_stats",  {})
    conf = pred.get("confidence",  50)
    vbs  = pred.get("value_bets",  [])
    hn   = pred.get("home_name",   "Home")
    an   = pred.get("away_name",   "Away")
    lg   = pred.get("league",      "")
    dt   = pred.get("match_date",  "")[:10]
    lh   = pred.get("lambda_home", 0)
    la   = pred.get("lambda_away", 0)

    header = (
        f"⚽ *{hn}  vs  {an}*\n"
        f"🏆 {lg}   📅 {dt}\n"
        f"{'─' * 32}\n"
    )

    conf_block = (
        f"📊 *Confidence:* {conf}% {_conf_emoji(conf)}\n"
        f"Expected goals: {lh} – {la} "
        f"(total {m.get('expected_goals', lh+la):.2f})\n\n"
    )

    main_tip = (
        f"🎯 *MAIN TIP*\n"
        f"Market: `{tip.get('market','')}`\n"
        f"Selection: *{tip.get('selection','')}*\n"
        f"Probability: {_pct(tip.get('probability',0))} "
        f"| Fair odds: `{tip.get('fair_odds','N/A')}`\n"
        f"Rating: {tip.get('rating','⭐')}\n\n"
    )

    ph = m.get("p_home_win", 0)
    pd = m.get("p_draw",     0)
    pa = m.get("p_away_win", 0)

    result_block = (
        f"🏠 *1X2 — Match Result*\n"
        f"Home  {_bar(ph)} {_pct(ph)} ({_odds(ph)})\n"
        f"Draw  {_bar(pd)} {_pct(pd)} ({_odds(pd)})\n"
        f"Away  {_bar(pa)} {_pct(pa)} ({_odds(pa)})\n\n"
        f"*Double Chance*\n"
        f"1X: {_pct(m.get('p_1x',0))}  "
        f"X2: {_pct(m.get('p_x2',0))}  "
        f"12: {_pct(m.get('p_12',0))}\n\n"
        f"*Draw No Bet*\n"
        f"{hn}: {_pct(m.get('dnb_home',0))}  "
        f"{an}: {_pct(m.get('dnb_away',0))}\n\n"
    )

    ou = m.get("over_under", {})
    ou_block = "⚽ *Goals — Over/Under*\n"
    for line in ["0.5","1.5","2.5","3.5","4.5"]:
        d  = ou.get(line, {})
        ov = d.get("over",  0)
        un = d.get("under", 0)
        ou_block += (f"  {line}  "
                     f"Over {_pct(ov)} ({_odds(ov)})  "
                     f"Under {_pct(un)} ({_odds(un)})\n")
    ou_block += "\n"

    tgb = m.get("total_goals_bands", {})
    ou_block += (f"Total Goals Bands: "
                 f"0-1: {_pct(tgb.get('0-1',0))}  "
                 f"2-3: {_pct(tgb.get('2-3',0))}  "
                 f"4+: {_pct(tgb.get('4+',0))}\n\n")

    btts_block = (
        f"🔀 *Both Teams to Score*\n"
        f"Yes: {_pct(m.get('btts_yes',0))} ({_odds(m.get('btts_yes',0))})  "
        f"No: {_pct(m.get('btts_no',0))} ({_odds(m.get('btts_no',0))})\n\n"
    )

    ht_block = (
        f"🕐 *Halftime Result*\n"
        f"Home: {_pct(m.get('ht_home',0))}  "
        f"Draw: {_pct(m.get('ht_draw',0))}  "
        f"Away: {_pct(m.get('ht_away',0))}\n\n"
    )

    sh = m.get("second_half_over", {})
    sh_block = (
        f"⏱ *2nd Half Over/Under*\n"
        f"Over 0.5: {_pct(sh.get('0.5',0))}  "
        f"Over 1.5: {_pct(sh.get('1.5',0))}  "
        f"Over 2.5: {_pct(sh.get('2.5',0))}\n\n"
    )

    ah = m.get("asian_handicap", {})
    ah_block = "⚖️ *Asian Handicap (Home perspective)*\n"
    for line in ["-1.5","-1.0","-0.5","0","0.5","1.0","1.5"]:
        d = ah.get(line, {})
        if d:
            ah_block += (
                f"  AH {line:>5}: "
                f"Home {_pct(d.get('home',0))}  "
                f"Push {_pct(d.get('push',0))}  "
                f"Away {_pct(d.get('away',0))}\n"
            )
    ah_block += "\n"

    cs = m.get("correct_scores", {})
    cs_sorted = sorted(cs.items(), key=lambda x: x[1], reverse=True)[:6]
    cs_block = "🎲 *Top Correct Scores*\n"
    for score, prob in cs_sorted:
        cs_block += f"  {score}: {_pct(prob)} ({_odds(prob)})\n"
    cs_block += "\n"

    misc_block = (
        f"⚡ *First Goal*\n"
        f"{hn}: {_pct(m.get('first_goal_home',0))}  "
        f"{an}: {_pct(m.get('first_goal_away',0))}  "
        f"No Goal: {_pct(m.get('first_goal_no',0))}\n\n"
        f"🧱 *Clean Sheets*\n"
        f"{hn}: {_pct(m.get('clean_sheet_home',0))}  "
        f"{an}: {_pct(m.get('clean_sheet_away',0))}\n\n"
    )

    corners_block = (
        f"📐 *Estimated Corners*\n"
        f"{hn}: {m.get('est_corners_home',0):.1f}  "
        f"{an}: {m.get('est_corners_away',0):.1f}  "
        f"Total: ~{m.get('est_corners_total',0):.1f}\n"
        f"Over 9.5 corners: {_pct(0.55)}\n\n"
        f"🟨 *Estimated Cards* Total: ~{m.get('est_cards_total',3.5)}\n\n"
    )

    form_block = (
        f"📋 *Recent Form (last 6)*\n"
        f"{hn}: {hf}\n"
        f"{an}: {af}\n\n"
    )

    h2h_block = "🔄 *Head to Head*\n"
    if h2h.get("total", 0):
        h2h_block += (
            f"{hn} wins: {h2h.get(f'{hn}_wins',0)}  "
            f"Draws: {h2h.get('draws',0)}  "
            f"{an} wins: {h2h.get(f'{an}_wins',0)}\n"
            f"Avg goals: {h2h.get('avg_goals',0):.2f}\n\n"
        )
    else:
        h2h_block += "No recent H2H data\n\n"

    def _stats_line(stats, name):
        if not stats:
            return f"{name}: No data\n"
        return (
            f"{name}: {stats.get('played',0)}G "
            f"W{stats.get('wins',0)} "
            f"D{stats.get('draws',0)} "
            f"L{stats.get('losses',0)} "
            f"Avg {stats.get('avg_goals_for','?')} scored\n"
        )

    stats_block = (
        f"📈 *Season Stats*\n"
        + _stats_line(hs, hn)
        + _stats_line(as_, an)
        + "\n"
    )

    vb_block = ""
    if vbs:
        vb_block = "💎 *VALUE BETS DETECTED*\n"
        for vb in vbs[:4]:
            vb_block += (
                f"  ✅ {vb.get('market','')} | "
                f"{vb.get('selection','')} {vb.get('point','')}\n"
                f"     Edge: +{vb.get('edge_pct',0):.1f}%  "
                f"Odds: {vb.get('bookmaker_odds',0):.2f}  "
                f"Via: {vb.get('bookmaker','')}\n"
                f"     Stake: {vb.get('quarter_kelly',0)*100:.1f}% bankroll\n"
            )
        vb_block += "\n"
    else:
        vb_block = "💎 *Value Bets:* None detected at current odds\n\n"

    risk_block = (
        f"⚠️ *Risk Management*\n"
        f"Max stake: {RISK['max_bet_pct']*100:.0f}% of bankroll  "
        f"Min confidence: {RISK['min_confidence']}%\n"
        f"Never chase losses. Bet responsibly. 🔒\n"
    )

    return (header + conf_block + main_tip + result_block +
            ou_block + btts_block + ht_block + sh_block +
            ah_block + cs_block + misc_block + corners_block +
            form_block + h2h_block + stats_block + vb_block + risk_block)


def format_short_prediction(pred: dict) -> str:
    tip  = pred.get("tip", {})
    conf = pred.get("confidence", 50)
    return (
        f"⚽ *{pred.get('home_name')} vs {pred.get('away_name')}*\n"
        f"💡 {tip.get('market','')} → *{tip.get('selection','')}* "
        f"({_pct(tip.get('probability',0))})\n"
        f"Confidence: {conf}% {_conf_emoji(conf)}\n"
        f"xG: {pred.get('lambda_home',0):.2f}–{pred.get('lambda_away',0):.2f}\n"
    )


def format_value_alert(vb: dict, home: str, away: str) -> str:
    return (
        f"💎 *VALUE BET ALERT*\n"
        f"Match: {home} vs {away}\n"
        f"Market: {vb.get('market','')} | "
        f"{vb.get('selection','')} {vb.get('point','')}\n"
        f"Our prob: {_pct(vb.get('model_prob',0))} | "
        f"Bookmaker: {_pct(vb.get('implied_prob',0))}\n"
        f"Edge: +{vb.get('edge_pct',0):.1f}%  "
        f"Odds: {vb.get('bookmaker_odds',0):.2f}\n"
        f"Stake: {vb.get('quarter_kelly',0)*100:.1f}% bankroll (¼ Kelly)\n"
        f"Via: {vb.get('bookmaker','')}\n"
    )


def format_stats(user_stats) -> str:
    if not user_stats:
        return "No stats yet. Use /bet to track your bets."
    wr     = user_stats["win_rate"] if user_stats["win_rate"] else 0
    profit = user_stats["profit"]   if user_stats["profit"]   else 0
    return (
        f"📊 *Your Stats*\n"
        f"Total bets: {user_stats['total_bets']}\n"
        f"Wins: {user_stats['wins']} | Losses: {user_stats['losses']}\n"
        f"Win rate: {wr}%\n"
        f"P&L: {'+'if profit>=0 else ''}{profit:.2f}\n"
        f"Bankroll: {user_stats['bankroll']:.2f}\n"
    )


def format_fixtures_list(fixtures: list, league_name: str) -> str:
    if not fixtures:
        return f"No fixtures found for {league_name}"
    lines = [f"📅 *{league_name} — Upcoming Fixtures*\n"]
    for f in fixtures[:15]:
        home = f.get("teams",{}).get("home",{}).get("name","?")
        away = f.get("teams",{}).get("away",{}).get("name","?")
        dt   = f.get("fixture",{}).get("date","")[:10]
        fid  = f.get("fixture",{}).get("id","")
        lines.append(f"  `{fid}` {dt} — {home} vs {away}")
    return "\n".join(lines)


def format_standings(standings_data: dict) -> str:
    rows = []
    for stage in standings_data.get("standings", []):
        if stage.get("type") == "TOTAL":
            rows = stage.get("table", [])
            break
    league = standings_data.get("competition", {}).get("name", "League")
    lines  = [
        f"🏆 *{league} Standings*\n",
        f"{'Pos':<4}{'Team':<22}{'P':>3}{'W':>3}{'D':>3}{'L':>3}{'GD':>4}{'Pts':>4}"
    ]
    for row in rows[:20]:
        pos  = row.get("position",      "?")
        name = row.get("team", {}).get("name", "?")[:20]
        p    = row.get("playedGames",   "?")
        w    = row.get("won",           "?")
        d    = row.get("draw",          "?")
        l_   = row.get("lost",          "?")
        gd   = row.get("goalDifference","?")
        pts  = row.get("points",        "?")
        lines.append(
            f"{pos:<4}{name:<22}{p:>3}{w:>3}{d:>3}{l_:>3}{gd:>4}{pts:>4}"
        )
    return "```\n" + "\n".join(lines) + "\n```"

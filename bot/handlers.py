# ============================================================
# bot/handlers.py — All Telegram handlers
# ============================================================
import logging
from datetime import date, datetime, timezone
from telegram import Update
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
                           MessageHandler, filters, ContextTypes)
from telegram.constants import ParseMode

from config          import TELEGRAM_TOKEN, ADMIN_USER_ID, SUPPORTED_LEAGUES
from database        import (upsert_user, get_user, update_bankroll,
                              get_user_stats, log_bet)
from models.analyzer import predict_fixture, predict_by_names
from apis.football_api import (get_fixtures_today, get_fixtures_next,
                                get_live_fixtures, get_head_to_head,
                                search_team)
from apis.football_data import get_standings
from apis.odds_api      import get_odds, extract_best_odds
from bot.formatters  import (format_prediction, format_short_prediction,
                              format_stats, format_fixtures_list,
                              format_standings, format_value_alert)
from bot.keyboards   import (main_menu_keyboard, league_keyboard,
                              fixture_action_keyboard,
                              prediction_detail_keyboard,
                              bankroll_keyboard, back_keyboard)

log = logging.getLogger(__name__)


# ─── Shared helper: get today's fixtures across all leagues ──
def _fetch_todays_fixtures() -> list:
    """
    Try every supported league for today's fixtures.
    Returns list of (fixture, league_name, league_id) tuples.
    """
    results = []
    for lg_name, lg_info in SUPPORTED_LEAGUES.items():
        try:
            fixtures = get_fixtures_today(lg_info["id"], lg_info["season"])
            for f in fixtures:
                results.append((f, lg_name, lg_info["id"]))
        except Exception as e:
            log.error(f"Error fetching today for {lg_name}: {e}")
    return results


def _fetch_upcoming_fixtures(limit: int = 10) -> list:
    """
    Fetch upcoming fixtures across all leagues as fallback.
    Returns list of (fixture, league_name, league_id) tuples.
    """
    results = []
    for lg_name, lg_info in SUPPORTED_LEAGUES.items():
        try:
            fixtures = get_fixtures_next(lg_info["id"],
                                         lg_info["season"], next_n=5)
            for f in fixtures[:3]:
                results.append((f, lg_name, lg_info["id"]))
        except Exception as e:
            log.error(f"Error fetching upcoming for {lg_name}: {e}")
        if len(results) >= limit:
            break
    return results


# ─────────────────────────────────────────────────────────────
# /start
# ─────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user.id, user.username or user.first_name)
    text = (
        f"🤖 *ProSportsBot — AI Predictions*\n\n"
        f"Welcome, *{user.first_name}*! 👋\n\n"
        f"I use Dixon-Coles Poisson models, live odds, "
        f"xG data, injuries and lineups to predict "
        f"*every betting market*:\n\n"
        f"• 1X2, Double Chance, DNB\n"
        f"• Over/Under 0.5 – 4.5\n"
        f"• Both Teams to Score\n"
        f"• Correct Score\n"
        f"• Asian Handicap\n"
        f"• Halftime / 2nd Half markets\n"
        f"• Corners, Cards, First Goal\n"
        f"• Value Bet detection + Kelly sizing\n\n"
        f"Type /help for all commands or tap a button below."
    )
    await update.message.reply_text(
        text, parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard()
    )


# ─────────────────────────────────────────────────────────────
# /help
# ─────────────────────────────────────────────────────────────
async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *Commands*\n\n"
        "`/predict Arsenal vs Chelsea` — Full prediction\n"
        "`/fixture 1234567` — Predict by fixture ID\n"
        "`/today` — Today's matches and tips\n"
        "`/upcoming` — Next fixtures by league\n"
        "`/live` — Live scores right now\n"
        "`/odds` — Live bookmaker odds\n"
        "`/h2h Arsenal Chelsea` — Head to head\n"
        "`/form Arsenal` — Recent form\n"
        "`/standings PL` — League table\n"
        "`/valuebets` — Value bet opportunities\n"
        "`/bankroll 1000` — Set your bankroll\n"
        "`/bet 1234 1X2 HomeWin 1.95 50` — Log a bet\n"
        "`/mystats` — Your performance stats\n"
        "`/betbuilder` — Combo bet guide\n\n"
        "⚠️ Always bet responsibly. Max 5% per bet."
    )
    await update.message.reply_text(
        text, parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_keyboard()
    )


# ─────────────────────────────────────────────────────────────
# /predict
# ─────────────────────────────────────────────────────────────
async def cmd_predict(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = " ".join(ctx.args)
    if " vs " not in args.lower():
        await update.message.reply_text(
            "Usage: `/predict Arsenal vs Chelsea`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    parts     = args.lower().split(" vs ")
    home      = parts[0].strip().title()
    away      = parts[1].strip().title()
    league_id = 39

    for name, info in SUPPORTED_LEAGUES.items():
        if name.lower() in away.lower():
            league_id = info["id"]
            away = away.lower().replace(
                name.lower(), ""
            ).strip().title()
            break

    msg = await update.message.reply_text(
        f"🔮 Analysing *{home} vs {away}*...",
        parse_mode=ParseMode.MARKDOWN
    )
    pred = predict_by_names(home, away, league_id)
    text = format_prediction(pred)
    fid  = pred.get("fixture_id")
    kb   = fixture_action_keyboard(fid) if fid else back_keyboard()
    await msg.edit_text(
        text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb
    )


# ─────────────────────────────────────────────────────────────
# /fixture
# ─────────────────────────────────────────────────────────────
async def cmd_fixture(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text(
            "Usage: `/fixture 1234567`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    try:
        fid = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text(
            "Please provide a valid numeric fixture ID."
        )
        return

    msg  = await update.message.reply_text("🔮 Loading prediction...")
    pred = predict_fixture(fid)
    if pred.get("error"):
        await msg.edit_text(f"❌ {pred['error']}")
        return
    text = format_prediction(pred)
    await msg.edit_text(
        text, parse_mode=ParseMode.MARKDOWN,
        reply_markup=fixture_action_keyboard(fid)
    )


# ─────────────────────────────────────────────────────────────
# /today  — fully rewritten with fallback
# ─────────────────────────────────────────────────────────────
async def cmd_today(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    today_str = str(date.today())
    msg = await update.message.reply_text(
        f"📅 Fetching matches for {today_str}..."
    )

    # ── Try today's fixtures ─────────────────────────────────
    todays = _fetch_todays_fixtures()

    if todays:
        lines = [f"📅 *Today's Picks — {today_str}*\n{'─'*32}\n"]
        for f, lg_name, lg_id in todays[:12]:
            try:
                hn  = f.get("teams",{}).get("home",{}).get("name","?")
                an  = f.get("teams",{}).get("away",{}).get("name","?")
                fid = f.get("fixture",{}).get("id","")
                dt  = f.get("fixture",{}).get("date","")
                # Format kick-off time
                try:
                    ko = datetime.fromisoformat(
                        dt.replace("Z", "+00:00")
                    ).strftime("%H:%M UTC")
                except Exception:
                    ko = dt[11:16]

                pred = predict_by_names(hn, an, lg_id)
                tip  = pred.get("tip", {})
                conf = pred.get("confidence", 0)
                lh   = pred.get("lambda_home", 0)
                la   = pred.get("lambda_away", 0)
                m    = pred.get("markets", {})
                ou   = m.get("over_under", {}).get("2.5", {})

                lines.append(
                    f"⚽ *{hn} vs {an}*\n"
                    f"🏆 {lg_name} | 🕐 {ko}\n"
                    f"🎯 *{tip.get('market','')}* → "
                    f"*{tip.get('selection','')}* "
                    f"@ `{tip.get('fair_odds','?')}`\n"
                    f"📊 Conf: {conf}%  "
                    f"xG: {lh:.2f}–{la:.2f}\n"
                    f"O2.5: {round(ou.get('over',0)*100,1)}%  "
                    f"BTTS: {round(m.get('btts_yes',0)*100,1)}%\n"
                    f"🔮 Full: /fixture\\_{fid}\n"
                    f"{'─'*32}\n"
                )
            except Exception as e:
                log.error(f"Error building today card: {e}")
                continue

        await msg.edit_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_keyboard()
        )

    else:
        # ── No matches today → show upcoming ────────────────
        upcoming = _fetch_upcoming_fixtures(limit=12)

        if upcoming:
            lines = [
                f"📅 *No matches today ({today_str})*\n"
                f"📆 *Next Upcoming Fixtures*\n{'─'*32}\n"
            ]
            for f, lg_name, lg_id in upcoming[:12]:
                try:
                    hn  = f.get("teams",{}).get("home",{}).get("name","?")
                    an  = f.get("teams",{}).get("away",{}).get("name","?")
                    fid = f.get("fixture",{}).get("id","")
                    dt  = f.get("fixture",{}).get("date","")[:10]

                    pred = predict_by_names(hn, an, lg_id)
                    tip  = pred.get("tip", {})
                    conf = pred.get("confidence", 0)
                    lh   = pred.get("lambda_home", 0)
                    la   = pred.get("lambda_away", 0)

                    lines.append(
                        f"📅 {dt} | {lg_name}\n"
                        f"⚽ *{hn} vs {an}*\n"
                        f"🎯 *{tip.get('market','')}* → "
                        f"*{tip.get('selection','')}* "
                        f"@ `{tip.get('fair_odds','?')}`\n"
                        f"📊 Conf: {conf}%  "
                        f"xG: {lh:.2f}–{la:.2f}\n"
                        f"🔮 Full: /fixture\\_{fid}\n"
                        f"{'─'*32}\n"
                    )
                except Exception as e:
                    log.error(f"Error building upcoming card: {e}")
                    continue

            await msg.edit_text(
                "\n".join(lines),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=back_keyboard()
            )
        else:
            await msg.edit_text(
                f"⚠️ *No fixtures found for {today_str}*\n\n"
                f"Possible reasons:\n"
                f"• API-Football free plan limit reached (100 req/day)\n"
                f"• No matches scheduled in tracked leagues today\n"
                f"• Try `/upcoming` to browse by league\n"
                f"• Try `/predict Arsenal vs Chelsea` directly",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=back_keyboard()
            )


# ─────────────────────────────────────────────────────────────
# /upcoming
# ─────────────────────────────────────────────────────────────
async def cmd_upcoming(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏆 *Select a League*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=league_keyboard()
    )


# ─────────────────────────────────────────────────────────────
# /live
# ─────────────────────────────────────────────────────────────
async def cmd_live(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg  = await update.message.reply_text("📡 Fetching live scores...")
    live = get_live_fixtures()
    if not live:
        await msg.edit_text(
            "No live matches right now.\nTry /today for today's fixtures.",
            reply_markup=back_keyboard()
        )
        return
    lines = ["📡 *Live Scores*\n"]
    for f in live[:15]:
        hn   = f.get("teams",{}).get("home",{}).get("name","?")
        an   = f.get("teams",{}).get("away",{}).get("name","?")
        gh   = f.get("goals",{}).get("home","0")
        ga   = f.get("goals",{}).get("away","0")
        min_ = f.get("fixture",{}).get("status",{}).get("elapsed","?")
        lg   = f.get("league",{}).get("name","?")
        lines.append(f"⚽ {hn} *{gh}–{ga}* {an} | {min_}' | {lg}")
    await msg.edit_text(
        "\n".join(lines), parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_keyboard()
    )


# ─────────────────────────────────────────────────────────────
# /odds
# ─────────────────────────────────────────────────────────────
async def cmd_odds(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg  = await update.message.reply_text("🔍 Fetching live odds...")
    data = get_odds("soccer_epl", markets="h2h,totals,spreads")
    if not data:
        await msg.edit_text(
            "No odds data available right now.",
            reply_markup=back_keyboard()
        )
        return
    lines = ["💰 *Live Odds — Premier League*\n"]
    for event in (data[:5] if isinstance(data, list) else []):
        home = event.get("home_team", "?")
        away = event.get("away_team", "?")
        dt   = event.get("commence_time","")[:10]
        best = extract_best_odds([event], "h2h")
        lines.append(f"⚽ *{home} vs {away}* | {dt}")
        for outcome, (odds, bookie) in best.items():
            lines.append(f"  {outcome}: `{odds}` ({bookie})")
        lines.append("")
    await msg.edit_text(
        "\n".join(lines), parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_keyboard()
    )


# ─────────────────────────────────────────────────────────────
# /h2h
# ─────────────────────────────────────────────────────────────
async def cmd_h2h(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 2:
        await update.message.reply_text(
            "Usage: `/h2h Arsenal Chelsea`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    mid = len(ctx.args) // 2
    t1  = " ".join(ctx.args[:mid])
    t2  = " ".join(ctx.args[mid:])
    msg = await update.message.reply_text(
        f"🔄 Loading H2H: {t1} vs {t2}..."
    )

    t1_data = search_team(t1)
    t2_data = search_team(t2)
    if not t1_data or not t2_data:
        await msg.edit_text(
            "Could not find one or both teams. Try full team names."
        )
        return

    id1 = t1_data[0]["team"]["id"]
    id2 = t2_data[0]["team"]["id"]
    h2h = get_head_to_head(id1, id2, last=10)
    if not h2h:
        await msg.edit_text(
            f"No H2H data found for {t1} vs {t2}."
        )
        return

    lines = [f"🔄 *H2H: {t1.title()} vs {t2.title()}*\n"]
    hw = aw = d = 0
    for m in h2h:
        hn  = m.get("teams",{}).get("home",{}).get("name","?")
        an  = m.get("teams",{}).get("away",{}).get("name","?")
        gh  = m.get("goals",{}).get("home", 0) or 0
        ga  = m.get("goals",{}).get("away", 0) or 0
        dt  = m.get("fixture",{}).get("date","")[:10]
        won = (hn.lower()==t1.lower() and gh>ga) or \
              (an.lower()==t1.lower() and ga>gh)
        drew = gh == ga
        icon = "✅" if won else "🤝" if drew else "❌"
        lines.append(f"{icon} {dt} {hn} {gh}–{ga} {an}")
        if hn.lower() in t1.lower():
            hw += (1 if gh > ga else 0)
        else:
            aw += (1 if gh > ga else 0)
        if gh == ga:
            d += 1
    lines.append(
        f"\n{t1.title()} W: {hw} | D: {d} | {t2.title()} W: {aw}"
    )
    await msg.edit_text(
        "\n".join(lines), parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_keyboard()
    )


# ─────────────────────────────────────────────────────────────
# /form
# ─────────────────────────────────────────────────────────────
async def cmd_form(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = " ".join(ctx.args)
    if not name:
        await update.message.reply_text(
            "Usage: `/form Arsenal`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    msg   = await update.message.reply_text(
        f"📋 Loading form for {name}..."
    )
    teams = search_team(name)
    if not teams:
        await msg.edit_text(f"Team '{name}' not found.")
        return

    from apis.football_api import get_team_last_matches
    team_id   = teams[0]["team"]["id"]
    team_name = teams[0]["team"]["name"]
    matches   = get_team_last_matches(team_id, last=10)

    lines = [f"📋 *{team_name} — Last {len(matches)} Results*\n"]
    for m in matches:
        hn      = m.get("teams",{}).get("home",{}).get("name","?")
        an      = m.get("teams",{}).get("away",{}).get("name","?")
        gh      = m.get("goals",{}).get("home", 0) or 0
        ga      = m.get("goals",{}).get("away", 0) or 0
        dt      = m.get("fixture",{}).get("date","")[:10]
        lg      = m.get("league",{}).get("name","")
        is_home = m.get("teams",{}).get("home",{}).get("id") == team_id
        won     = (gh > ga and is_home) or (ga > gh and not is_home)
        drew    = gh == ga
        icon    = "✅" if won else "🤝" if drew else "❌"
        lines.append(f"{icon} {dt} {hn} {gh}–{ga} {an} ({lg})")

    await msg.edit_text(
        "\n".join(lines), parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_keyboard()
    )


# ─────────────────────────────────────────────────────────────
# /standings
# ─────────────────────────────────────────────────────────────
async def cmd_standings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    code = ctx.args[0].upper() if ctx.args else "PL"
    msg  = await update.message.reply_text(
        f"🏆 Loading standings for {code}..."
    )
    data = get_standings(code)
    if not data or not data.get("standings"):
        await msg.edit_text(
            f"Could not load standings for '{code}'.\n"
            f"Try: PL, PD, SA, BL1, FL1, CL"
        )
        return
    text = format_standings(data)
    await msg.edit_text(
        text, parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_keyboard()
    )


# ─────────────────────────────────────────────────────────────
# /valuebets
# ─────────────────────────────────────────────────────────────
async def cmd_valuebets(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg     = await update.message.reply_text(
        "💎 Scanning for value bets..."
    )
    all_vbs = []

    for lg_name, lg_info in list(SUPPORTED_LEAGUES.items())[:4]:
        try:
            fixtures = get_fixtures_next(
                lg_info["id"], lg_info["season"], next_n=5
            )
            for f in fixtures[:3]:
                hn   = f.get("teams",{}).get("home",{}).get("name","?")
                an   = f.get("teams",{}).get("away",{}).get("name","?")
                dt   = f.get("fixture",{}).get("date","")[:10]
                pred = predict_by_names(hn, an, lg_info["id"])
                for vb in pred.get("value_bets", []):
                    vb["home"]   = hn
                    vb["away"]   = an
                    vb["date"]   = dt
                    vb["league"] = lg_name
                    all_vbs.append(vb)
        except Exception as e:
            log.error(f"Value bet scan error for {lg_name}: {e}")

    all_vbs.sort(key=lambda x: x.get("edge_pct", 0), reverse=True)

    if not all_vbs:
        await msg.edit_text(
            "💎 *No value bets found right now*\n\n"
            "This means bookmaker odds are fairly priced at the moment.\n"
            "Check back closer to kick-off when odds sharpen.\n\n"
            "You can also try `/predict Team A vs Team B` to check "
            "a specific match manually.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_keyboard()
        )
        return

    lines = [f"💎 *Top Value Bets — {str(date.today())}*\n{'─'*32}\n"]
    for vb in all_vbs[:8]:
        lines.append(
            f"📅 {vb.get('date','')} | {vb.get('league','')}\n"
            + format_value_alert(
                vb, vb.get("home","?"), vb.get("away","?")
            )
            + f"{'─'*32}\n"
        )

    await msg.edit_text(
        "\n".join(lines), parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_keyboard()
    )


# ─────────────────────────────────────────────────────────────
# /bankroll
# ─────────────────────────────────────────────────────────────
async def cmd_bankroll(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user.id, user.username or "")
    row     = get_user(user.id)
    current = row["bankroll"] if row else 1000.0

    if ctx.args:
        try:
            amount = float(ctx.args[0])
            update_bankroll(user.id, amount)
            await update.message.reply_text(
                f"💰 Bankroll updated to *{amount:.2f}*\n"
                f"Max bet (5%): {amount * 0.05:.2f}\n"
                f"Med bet (3%): {amount * 0.03:.2f}\n"
                f"Min bet (1%): {amount * 0.01:.2f}",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=bankroll_keyboard()
            )
        except ValueError:
            await update.message.reply_text(
                "Usage: `/bankroll 1000`",
                parse_mode=ParseMode.MARKDOWN
            )
    else:
        text = (
            f"💰 *Bankroll Management*\n\n"
            f"Current bankroll: *{current:.2f}*\n\n"
            f"📐 *Recommended stakes*\n"
            f"High confidence 80%+: "
            f"up to {current * 0.05:.2f} (5%)\n"
            f"Medium confidence 65%+: "
            f"{current * 0.03:.2f} (3%)\n"
            f"Low confidence below 65%: "
            f"{current * 0.01:.2f} (1%)\n\n"
            f"Set new bankroll: `/bankroll 1500`"
        )
        await update.message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=bankroll_keyboard()
        )


# ─────────────────────────────────────────────────────────────
# /mystats
# ─────────────────────────────────────────────────────────────
async def cmd_mystats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user  = update.effective_user
    upsert_user(user.id, user.username or "")
    stats = get_user_stats(user.id)
    text  = format_stats(stats)
    await update.message.reply_text(
        text, parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_keyboard()
    )


# ─────────────────────────────────────────────────────────────
# /bet
# ─────────────────────────────────────────────────────────────
async def cmd_bet(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user.id, user.username or "")
    if len(ctx.args) < 5:
        await update.message.reply_text(
            "Usage: `/bet <fixture_id> <market> <selection> "
            "<odds> <stake>`\n"
            "Example: `/bet 1234567 1X2 HomeWin 1.95 50`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    try:
        fid    = ctx.args[0]
        market = ctx.args[1]
        sel    = ctx.args[2]
        odds   = float(ctx.args[3])
        stake  = float(ctx.args[4])
        row    = get_user(user.id)
        broll  = row["bankroll"] if row else 1000.0
        log_bet(user.id, fid, market, sel, odds, stake, broll)
        potential = stake * (odds - 1)
        await update.message.reply_text(
            f"✅ *Bet Logged*\n"
            f"Fixture: {fid} | {market}: {sel}\n"
            f"Odds: {odds} | Stake: {stake:.2f}\n"
            f"Potential profit: +{potential:.2f}\n\n"
            f"Use `/mystats` to track performance.",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        await update.message.reply_text(f"Error logging bet: {e}")


# ─────────────────────────────────────────────────────────────
# /betbuilder
# ─────────────────────────────────────────────────────────────
async def cmd_betbuilder(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "🏗️ *Bet Builder Guide*\n\n"
        "*Safe Combos*\n"
        "• 1X2 + Over/Under 2.5\n"
        "• Double Chance + BTTS\n"
        "• Asian Handicap -0.5 + Over 1.5\n\n"
        "*Medium Combos*\n"
        "• 1X2 + BTTS + Over 2.5\n"
        "• Halftime Result + Fulltime Result\n"
        "• DNB + Over 1.5\n\n"
        "*Aggressive Combos*\n"
        "• Correct Score + BTTS Yes\n"
        "• 1X2 + Exact Goals + Correct Score\n\n"
        "*Pro Tips*\n"
        "• If Over 2.5 is likely, BTTS Yes is correlated\n"
        "• Cap at 4 selections for value bets\n"
        "• Never combine more than 8 selections\n\n"
        "Use `/predict` to get all probabilities then "
        "multiply them for combo probability."
    )
    await update.message.reply_text(
        text, parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_keyboard()
    )


# ─────────────────────────────────────────────────────────────
# /admin
# ─────────────────────────────────────────────────────────────
async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("⛔ Admin only.")
        return
    from database import cache_clear_expired
    cache_clear_expired()
    await update.message.reply_text(
        "🔧 *Admin Panel*\n✅ Expired cache cleared",
        parse_mode=ParseMode.MARKDOWN
    )


# ─────────────────────────────────────────────────────────────
# Callback router
# ─────────────────────────────────────────────────────────────
async def callback_router(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    data = q.data
    await q.answer()

    # ── Main menu ────────────────────────────────────────────
    if data == "main_menu":
        await q.edit_message_text(
            "🤖 *ProSportsBot — Main Menu*\nChoose an option:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard()
        )

    # ── Leagues ──────────────────────────────────────────────
    elif data == "leagues":
        await q.edit_message_text(
            "🏆 *Select a League*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=league_keyboard()
        )

    elif data.startswith("league_"):
        parts   = data.split("_", 2)
        lg_id   = int(parts[1])
        lg_name = parts[2] if len(parts) > 2 else "League"
        season  = next(
            (v["season"] for v in SUPPORTED_LEAGUES.values()
             if v["id"] == lg_id), 2025
        )
        fixtures = get_fixtures_next(lg_id, season, next_n=10)
        text     = format_fixtures_list(fixtures, lg_name)
        await q.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_keyboard("leagues")
        )

    # ── Today ────────────────────────────────────────────────
    elif data == "today":
        today_str = str(date.today())
        todays    = _fetch_todays_fixtures()
        lines     = []

        if todays:
            lines = [
                f"📅 *Today's Picks — {today_str}*\n{'─'*32}\n"
            ]
            for f, lg_name, lg_id in todays[:8]:
                try:
                    hn  = f.get("teams",{}).get("home",{}).get("name","?")
                    an  = f.get("teams",{}).get("away",{}).get("name","?")
                    fid = f.get("fixture",{}).get("id","")
                    dt  = f.get("fixture",{}).get("date","")
                    try:
                        ko = datetime.fromisoformat(
                            dt.replace("Z","+00:00")
                        ).strftime("%H:%M UTC")
                    except Exception:
                        ko = dt[11:16]
                    pred = predict_by_names(hn, an, lg_id)
                    tip  = pred.get("tip", {})
                    conf = pred.get("confidence", 0)
                    lh   = pred.get("lambda_home", 0)
                    la   = pred.get("lambda_away", 0)
                    lines.append(
                        f"⚽ *{hn} vs {an}*\n"
                        f"🏆 {lg_name} | 🕐 {ko}\n"
                        f"🎯 *{tip.get('market','')}* → "
                        f"*{tip.get('selection','')}*\n"
                        f"📊 Conf: {conf}%  "
                        f"xG: {lh:.2f}–{la:.2f}\n"
                        f"🔮 /fixture\\_{fid}\n"
                        f"{'─'*32}\n"
                    )
                except Exception:
                    continue
        else:
            upcoming = _fetch_upcoming_fixtures(limit=8)
            lines = [
                f"📅 *No matches today — Next Upcoming*\n{'─'*32}\n"
            ]
            for f, lg_name, lg_id in upcoming:
                try:
                    hn  = f.get("teams",{}).get("home",{}).get("name","?")
                    an  = f.get("teams",{}).get("away",{}).get("name","?")
                    fid = f.get("fixture",{}).get("id","")
                    dt  = f.get("fixture",{}).get("date","")[:10]
                    pred = predict_by_names(hn, an, lg_id)
                    tip  = pred.get("tip", {})
                    conf = pred.get("confidence", 0)
                    lines.append(
                        f"📅 {dt} | {lg_name}\n"
                        f"⚽ *{hn} vs {an}*\n"
                        f"🎯 *{tip.get('market','')}* → "
                        f"*{tip.get('selection','')}*\n"
                        f"📊 Conf: {conf}%\n"
                        f"🔮 /fixture\\_{fid}\n"
                        f"{'─'*32}\n"
                    )
                except Exception:
                    continue

        if not lines:
            lines = ["⚠️ No fixtures found. Try /predict directly."]

        await q.edit_message_text(
            "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_keyboard()
        )

    # ── Upcoming ─────────────────────────────────────────────
    elif data == "upcoming":
        await q.edit_message_text(
            "🏆 *Select a League*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=league_keyboard()
        )

    # ── Live ─────────────────────────────────────────────────
    elif data == "live":
        live = get_live_fixtures()
        if not live:
            await q.edit_message_text(
                "No live matches right now.",
                reply_markup=back_keyboard()
            )
            return
        lines = ["📡 *Live Now*\n"]
        for f in live[:10]:
            hn   = f.get("teams",{}).get("home",{}).get("name","?")
            an   = f.get("teams",{}).get("away",{}).get("name","?")
            gh   = f.get("goals",{}).get("home","0")
            ga   = f.get("goals",{}).get("away","0")
            min_ = f.get("fixture",{}).get("status",{}).get("elapsed","?")
            lines.append(f"⚽ {hn} *{gh}–{ga}* {an} | {min_}'")
        await q.edit_message_text(
            "\n".join(lines), parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_keyboard()
        )

    # ── Predict ──────────────────────────────────────────────
    elif data.startswith("predict_"):
        fid  = int(data.split("_")[1])
        await q.edit_message_text(
            "🔮 Running prediction model...",
            parse_mode=ParseMode.MARKDOWN
        )
        pred = predict_fixture(fid)
        text = format_prediction(pred)
        await q.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=prediction_detail_keyboard(fid)
        )

    # ── Value bets ───────────────────────────────────────────
    elif data == "valuebets":
        await q.edit_message_text(
            "💎 Use /valuebets for the full scan.\n"
            "Updated every 2 hours.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_keyboard()
        )

    # ── My stats ─────────────────────────────────────────────
    elif data == "mystats":
        uid   = q.from_user.id
        stats = get_user_stats(uid)
        text  = format_stats(stats)
        await q.edit_message_text(
            text, parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_keyboard()
        )

    # ── Bankroll ─────────────────────────────────────────────
    elif data == "bankroll":
        uid   = q.from_user.id
        row   = get_user(uid)
        broll = row["bankroll"] if row else 1000.0
        await q.edit_message_text(
            f"💰 *Bankroll: {broll:.2f}*\n\n"
            f"Use `/bankroll <amount>` to update.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=bankroll_keyboard()
        )

    # ── Help ─────────────────────────────────────────────────
    elif data == "help":
        await q.edit_message_text(
            "Type /help for the full command list.",
            reply_markup=back_keyboard()
        )

    # ── Cancel ───────────────────────────────────────────────
    elif data == "cancel":
        await q.edit_message_text(
            "Cancelled.", reply_markup=back_keyboard()
        )


# ─────────────────────────────────────────────────────────────
# Free text handler
# ─────────────────────────────────────────────────────────────
async def unknown_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    if " vs " in text.lower():
        ctx.args = text.split()
        await cmd_predict(update, ctx)
    else:
        await update.message.reply_text(
            "Type `Team A vs Team B` to predict, "
            "or /help for all commands.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard()
        )


# ─────────────────────────────────────────────────────────────
# Build application
# ─────────────────────────────────────────────────────────────
def build_application() -> Application:
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",      cmd_start))
    app.add_handler(CommandHandler("help",       cmd_help))
    app.add_handler(CommandHandler("predict",    cmd_predict))
    app.add_handler(CommandHandler("fixture",    cmd_fixture))
    app.add_handler(CommandHandler("today",      cmd_today))
    app.add_handler(CommandHandler("upcoming",   cmd_upcoming))
    app.add_handler(CommandHandler("live",       cmd_live))
    app.add_handler(CommandHandler("odds",       cmd_odds))
    app.add_handler(CommandHandler("h2h",        cmd_h2h))
    app.add_handler(CommandHandler("form",       cmd_form))
    app.add_handler(CommandHandler("standings",  cmd_standings))
    app.add_handler(CommandHandler("valuebets",  cmd_valuebets))
    app.add_handler(CommandHandler("bankroll",   cmd_bankroll))
    app.add_handler(CommandHandler("mystats",    cmd_mystats))
    app.add_handler(CommandHandler("bet",        cmd_bet))
    app.add_handler(CommandHandler("betbuilder", cmd_betbuilder))
    app.add_handler(CommandHandler("admin",      cmd_admin))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, unknown_handler
    ))

    return app

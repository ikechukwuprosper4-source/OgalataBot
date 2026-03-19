# ============================================================
# scheduler.py — Background tasks (APScheduler)
# ============================================================
import logging, asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron      import CronTrigger
from telegram import Bot
from telegram.constants import ParseMode

from config          import TELEGRAM_TOKEN, ADMIN_USER_ID, SUPPORTED_LEAGUES
from apis.football_api import get_fixtures_today, get_fixtures_next
from models.analyzer   import predict_by_names
from bot.formatters    import format_short_prediction, format_value_alert
from database          import get_conn, cache_clear_expired

log = logging.getLogger(__name__)
bot = Bot(token=TELEGRAM_TOKEN)


async def _send(chat_id: int, text: str):
    try:
        await bot.send_message(chat_id=chat_id, text=text,
                               parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        log.error(f"Send error to {chat_id}: {e}")


def _get_all_user_ids() -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT user_id FROM users").fetchall()
    return [r["user_id"] for r in rows]


# ── Daily morning picks (08:00) ───────────────────────────────
async def daily_morning_picks():
    log.info("Running daily morning picks")
    lines = ["🌅 *Good Morning! Today's Picks*\n"]
    count = 0
    for lg_name, lg_info in list(SUPPORTED_LEAGUES.items())[:5]:
        fixtures = get_fixtures_today(lg_info["id"], lg_info["season"])
        for f in fixtures[:3]:
            hn   = f.get("teams",{}).get("home",{}).get("name","?")
            an   = f.get("teams",{}).get("away",{}).get("name","?")
            pred = predict_by_names(hn, an, lg_info["id"])
            lines.append(format_short_prediction(pred))
            count += 1

    if count == 0:
        return   # Nothing to send

    text = "\n".join(lines) + "\n\n_Use /predict for full analysis_"
    for uid in _get_all_user_ids():
        await _send(uid, text)
        await asyncio.sleep(0.05)  # rate limit


# ── Value bet scan (every 2 hours) ───────────────────────────
async def value_bet_scan():
    log.info("Running value bet scan")
    vbs_found = []
    for lg_name, lg_info in list(SUPPORTED_LEAGUES.items())[:3]:
        fixtures = get_fixtures_next(lg_info["id"], lg_info["season"], next_n=5)
        for f in fixtures[:3]:
            hn   = f.get("teams",{}).get("home",{}).get("name","?")
            an   = f.get("teams",{}).get("away",{}).get("name","?")
            pred = predict_by_names(hn, an, lg_info["id"])
            for vb in pred.get("value_bets", []):
                if vb.get("edge_pct", 0) >= 7:   # Only strong edges
                    vb["home"] = hn
                    vb["away"] = an
                    vbs_found.append(vb)

    if not vbs_found:
        return

    vbs_found.sort(key=lambda x: x.get("edge_pct", 0), reverse=True)
    text = "💎 *Value Bet Alert!*\n\n"
    for vb in vbs_found[:3]:
        text += format_value_alert(vb, vb["home"], vb["away"]) + "\n"

    # Send only to admin for now (expand to subscribers later)
    await _send(ADMIN_USER_ID, text)


# ── Cache cleanup (every 6 hours) ────────────────────────────
async def cleanup_cache():
    log.info("Cleaning expired cache")
    cache_clear_expired()


# ── Pre-match alerts (1 hour before kick-off) ────────────────
async def pre_match_alerts():
    from datetime import datetime, timezone, timedelta
    log.info("Running pre-match alerts")
    now     = datetime.now(timezone.utc)
    one_hr  = now + timedelta(hours=1, minutes=10)
    window  = timedelta(minutes=10)

    for lg_name, lg_info in list(SUPPORTED_LEAGUES.items())[:5]:
        fixtures = get_fixtures_next(lg_info["id"], lg_info["season"], next_n=10)
        for f in fixtures:
            dt_str = f.get("fixture",{}).get("date","")
            if not dt_str:
                continue
            try:
                dt = datetime.fromisoformat(dt_str.replace("Z","+00:00"))
            except Exception:
                continue
            if abs((dt - one_hr).total_seconds()) < window.total_seconds():
                hn   = f.get("teams",{}).get("home",{}).get("name","?")
                an   = f.get("teams",{}).get("away",{}).get("name","?")
                pred = predict_by_names(hn, an, lg_info["id"])
                tip  = pred.get("tip",{})
                text = (
                    f"⏰ *KICK-OFF IN 1 HOUR*\n"
                    f"⚽ {hn} vs {an}\n"
                    f"💡 {tip.get('market','')} → *{tip.get('selection','')}*\n"
                    f"Confidence: {pred.get('confidence',0)}%\n"
                    f"xG: {pred.get('lambda_home',0):.2f}–{pred.get('lambda_away',0):.2f}"
                )
                await _send(ADMIN_USER_ID, text)


# ── Build scheduler ───────────────────────────────────────────
def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")

    # Morning picks at 08:00 UTC
    scheduler.add_job(daily_morning_picks, CronTrigger(hour=8, minute=0))

    # Value bet scan every 2 hours
    scheduler.add_job(value_bet_scan,
                      "interval", hours=2, id="value_scan")

    # Pre-match alerts every 10 minutes
    scheduler.add_job(pre_match_alerts,
                      "interval", minutes=10, id="prematch_alerts")

    # Cache cleanup every 6 hours
    scheduler.add_job(cleanup_cache, "interval", hours=6, id="cache_cleanup")

    return scheduler

#!/usr/bin/env python3
# ============================================================
# main.py — ProSportsBot Entry Point
# ============================================================
import logging, asyncio, sys
from database   import init_db
from scheduler  import build_scheduler
from bot.handlers import build_application

# ── Logging setup ─────────────────────────────────────────────
logging.basicConfig(
    format  = "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S",
    level   = logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("prosportsbot.log"),
    ]
)
log = logging.getLogger("main")


async def main():
    log.info("=" * 60)
    log.info("  ProSportsBot — Starting up")
    log.info("=" * 60)

    # 1. Initialise database
    init_db()
    log.info("✅ Database ready")

    # 2. Build bot application
    app = build_application()
    log.info("✅ Telegram application built")

    # 3. Start background scheduler
    scheduler = build_scheduler()
    scheduler.start()
    log.info("✅ Scheduler started")

    # 4. Start polling
    log.info("🤖 Bot is live. Listening for updates...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True,
    )

    # Keep running
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        log.info("Shutting down gracefully...")
    finally:
        scheduler.shutdown()
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        log.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())

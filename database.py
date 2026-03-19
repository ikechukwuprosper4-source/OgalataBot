# ============================================================
# database.py — SQLite persistence layer
# ============================================================
import sqlite3, json, time, logging
from config import DATABASE_PATH

log = logging.getLogger(__name__)

# ─── Schema ──────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    expires_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS predictions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id  TEXT NOT NULL,
    home_team   TEXT NOT NULL,
    away_team   TEXT NOT NULL,
    league      TEXT,
    match_date  TEXT,
    prediction  TEXT NOT NULL,          -- JSON blob
    created_at  REAL NOT NULL,
    result_home INTEGER DEFAULT NULL,
    result_away INTEGER DEFAULT NULL,
    settled     INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    fixture_id   TEXT NOT NULL,
    market       TEXT NOT NULL,
    selection    TEXT NOT NULL,
    odds         REAL NOT NULL,
    stake        REAL NOT NULL,
    bankroll_at  REAL NOT NULL,
    status       TEXT DEFAULT 'open',   -- open/won/lost/void
    profit       REAL DEFAULT 0,
    created_at   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    username    TEXT,
    bankroll    REAL DEFAULT 1000,
    total_bets  INTEGER DEFAULT 0,
    wins        INTEGER DEFAULT 0,
    losses      INTEGER DEFAULT 0,
    profit      REAL DEFAULT 0,
    joined_at   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    league_id   INTEGER,
    team_name   TEXT,
    alert_type  TEXT NOT NULL,   -- 'match','value_bet','kickoff'
    active      INTEGER DEFAULT 1,
    created_at  REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_predictions_fixture ON predictions(fixture_id);
CREATE INDEX IF NOT EXISTS idx_bets_user ON bets(user_id);
"""


def get_conn():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
    log.info("Database initialised")


# ─── Cache helpers ───────────────────────────────────────────
def cache_set(key: str, value, ttl: int):
    expires = time.time() + ttl
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO cache(key,value,expires_at) VALUES(?,?,?)",
            (key, json.dumps(value), expires)
        )


def cache_get(key: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value,expires_at FROM cache WHERE key=?", (key,)
        ).fetchone()
    if row and row["expires_at"] > time.time():
        return json.loads(row["value"])
    return None


def cache_clear_expired():
    with get_conn() as conn:
        conn.execute("DELETE FROM cache WHERE expires_at<?", (time.time(),))


# ─── User helpers ────────────────────────────────────────────
def upsert_user(user_id: int, username: str = ""):
    with get_conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO users(user_id,username,joined_at)
               VALUES(?,?,?)""",
            (user_id, username, time.time())
        )
        if username:
            conn.execute(
                "UPDATE users SET username=? WHERE user_id=?",
                (username, user_id)
            )


def get_user(user_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,)
        ).fetchone()


def update_bankroll(user_id: int, amount: float):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET bankroll=? WHERE user_id=?",
            (amount, user_id)
        )


# ─── Prediction helpers ──────────────────────────────────────
def save_prediction(fixture_id, home, away, league, match_date, pred_dict):
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO predictions
               (fixture_id,home_team,away_team,league,match_date,prediction,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (str(fixture_id), home, away, league, match_date,
             json.dumps(pred_dict), time.time())
        )


def get_prediction(fixture_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM predictions WHERE fixture_id=?",
            (str(fixture_id),)
        ).fetchone()
    if row:
        d = dict(row)
        d["prediction"] = json.loads(d["prediction"])
        return d
    return None


# ─── Bet tracking ────────────────────────────────────────────
def log_bet(user_id, fixture_id, market, selection, odds, stake, bankroll):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO bets
               (user_id,fixture_id,market,selection,odds,stake,bankroll_at,created_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (user_id, fixture_id, market, selection,
             odds, stake, bankroll, time.time())
        )
        conn.execute(
            "UPDATE users SET total_bets=total_bets+1 WHERE user_id=?",
            (user_id,)
        )


def settle_bet(bet_id: int, won: bool, profit: float):
    status = "won" if won else "lost"
    with get_conn() as conn:
        conn.execute(
            "UPDATE bets SET status=?,profit=? WHERE id=?",
            (status, profit, bet_id)
        )
        if won:
            conn.execute(
                "UPDATE users SET wins=wins+1,profit=profit+? WHERE user_id="
                "(SELECT user_id FROM bets WHERE id=?)",
                (profit, bet_id)
            )
        else:
            conn.execute(
                "UPDATE users SET losses=losses+1,profit=profit-? WHERE user_id="
                "(SELECT user_id FROM bets WHERE id=?)",
                (abs(profit), bet_id)
            )


def get_user_stats(user_id: int):
    with get_conn() as conn:
        return conn.execute(
            """SELECT total_bets,wins,losses,profit,bankroll,
                      CASE WHEN total_bets>0
                           THEN ROUND(100.0*wins/total_bets,1)
                           ELSE 0 END as win_rate
               FROM users WHERE user_id=?""",
            (user_id,)
        ).fetchone()

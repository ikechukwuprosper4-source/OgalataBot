# ============================================================
# bot/keyboards.py — Inline keyboard builders
# ============================================================
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import SUPPORTED_LEAGUES


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚽ Today's Picks",  callback_data="today"),
         InlineKeyboardButton("📅 Upcoming",       callback_data="upcoming")],
        [InlineKeyboardButton("💎 Value Bets",     callback_data="valuebets"),
         InlineKeyboardButton("🏆 Leagues",        callback_data="leagues")],
        [InlineKeyboardButton("📊 My Stats",       callback_data="mystats"),
         InlineKeyboardButton("💰 Bankroll",       callback_data="bankroll")],
        [InlineKeyboardButton("📡 Live Scores",    callback_data="live"),
         InlineKeyboardButton("❓ Help",           callback_data="help")],
    ])


def league_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for name, info in SUPPORTED_LEAGUES.items():
        row.append(InlineKeyboardButton(
            name, callback_data=f"league_{info['id']}_{name}"
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)


def fixture_action_keyboard(fixture_id: int) -> InlineKeyboardMarkup:
    fid = str(fixture_id)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔮 Full Prediction", callback_data=f"predict_{fid}"),
         InlineKeyboardButton("💎 Value Bets",      callback_data=f"value_{fid}")],
        [InlineKeyboardButton("📊 All Markets",     callback_data=f"markets_{fid}"),
         InlineKeyboardButton("🔄 H2H",            callback_data=f"h2h_{fid}")],
        [InlineKeyboardButton("📋 Team Stats",      callback_data=f"stats_{fid}"),
         InlineKeyboardButton("🔙 Back",           callback_data="upcoming")],
    ])


def prediction_detail_keyboard(fixture_id: int) -> InlineKeyboardMarkup:
    fid = str(fixture_id)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Correct Score",  callback_data=f"cs_{fid}"),
         InlineKeyboardButton("⚖️ Asian Handicap", callback_data=f"ah_{fid}")],
        [InlineKeyboardButton("📐 Corners",        callback_data=f"corners_{fid}"),
         InlineKeyboardButton("🟨 Cards",          callback_data=f"cards_{fid}")],
        [InlineKeyboardButton("🏗️ Bet Builder",    callback_data=f"betbuilder_{fid}"),
         InlineKeyboardButton("🔙 Prediction",    callback_data=f"predict_{fid}")],
    ])


def bankroll_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Set Bankroll",  callback_data="set_bankroll"),
         InlineKeyboardButton("📊 View Stats",    callback_data="mystats")],
        [InlineKeyboardButton("📉 P&L History",   callback_data="pnl_history"),
         InlineKeyboardButton("🔙 Menu",          callback_data="main_menu")],
    ])


def confirm_keyboard(action: str, item_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_{action}_{item_id}"),
         InlineKeyboardButton("❌ Cancel",  callback_data="cancel")],
    ])


def back_keyboard(back_to: str = "main_menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back", callback_data=back_to)]
    ])

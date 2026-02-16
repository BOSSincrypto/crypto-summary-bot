import logging
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from config import BOT_PASSWORD, EVM_ADDRESS
import db
import services

logger = logging.getLogger(__name__)

user_states: dict[int, dict] = {}

BTN_SUMMARY = "Сводка"
BTN_COINS = "Монеты"
BTN_SUPPORT = "Поддержать"
BTN_HELP = "Помощь"
BTN_ADMIN = "Админ"

WELCOME_TEXT = (
    "<b>Welcome to Crypto Summary Bot!</b>\n\n"
    "This bot provides daily crypto summaries for tracked coins "
    "with AI-powered analysis, news, and Twitter mentions.\n\n"
    "<b>To get started, please enter the access password:</b>"
)

HELP_TEXT = (
    "<b>Crypto Summary Bot - Help</b>\n\n"
    "<b>Commands:</b>\n"
    "/start - Start the bot\n"
    "/summary - Get current crypto summary\n"
    "/coins - List tracked coins\n"
    "/support - Support the project\n"
    "/help - Show this help message\n"
    "/myid - Show your Telegram ID\n\n"
    "<b>Buttons:</b>\n"
    "<b>Сводка</b> - Get AI-powered crypto summary\n"
    "<b>Монеты</b> - View tracked coins\n"
    "<b>Поддержать</b> - Support the project\n"
    "<b>Помощь</b> - This help page\n"
    "<b>Админ</b> - Admin panel (admins only)\n\n"
    "<b>AI Agent:</b>\n"
    "Send any text message to chat with the AI about crypto.\n\n"
    "<b>Scheduled Summaries:</b>\n"
    "Morning summary: 08:00 MSK\n"
    "Evening summary: 23:00 MSK"
)


def get_main_keyboard(is_admin: bool = False):
    keys = [
        [BTN_SUMMARY, BTN_COINS],
        [BTN_SUPPORT, BTN_HELP],
    ]
    if is_admin:
        keys.append([BTN_ADMIN])
    return ReplyKeyboardMarkup(keys, resize_keyboard=True)


def get_admin_inline_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Run Summary Now", callback_data="admin_run_summary")],
            [InlineKeyboardButton("User Analytics", callback_data="admin_analytics")],
            [InlineKeyboardButton("Users List", callback_data="admin_users")],
            [InlineKeyboardButton("Add Coin", callback_data="admin_add_coin")],
            [InlineKeyboardButton("Remove Coin", callback_data="admin_remove_coin")],
        ]
    )


async def split_send(update_or_chat, text: str, context: ContextTypes.DEFAULT_TYPE = None, chat_id: int = None):
    max_len = 4000
    parts = []
    while text:
        if len(text) <= max_len:
            parts.append(text)
            break
        idx = text.rfind("\n", 0, max_len)
        if idx == -1:
            idx = max_len
        parts.append(text[:idx])
        text = text[idx:].lstrip("\n")
    for part in parts:
        try:
            if chat_id and context:
                await context.bot.send_message(chat_id=chat_id, text=part, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            elif hasattr(update_or_chat, "message") and update_or_chat.message:
                await update_or_chat.message.reply_text(part, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            elif hasattr(update_or_chat, "callback_query") and update_or_chat.callback_query:
                await update_or_chat.callback_query.message.reply_text(part, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except Exception as e:
            logger.error("Failed to send message: %s", e)
            if chat_id and context:
                await context.bot.send_message(chat_id=chat_id, text=part, disable_web_page_preview=True)
            elif hasattr(update_or_chat, "message") and update_or_chat.message:
                await update_or_chat.message.reply_text(part, disable_web_page_preview=True)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db.get_or_create_user(user.id, user.username, user.first_name)
    await db.log_action(user.id, "start")

    if await db.is_authenticated(user.id):
        admin = await db.is_admin(user.id)
        await update.message.reply_text(
            "<b>Welcome back!</b>\nUse the menu below or send a message to chat with AI.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard(admin),
        )
    else:
        await update.message.reply_text(WELCOME_TEXT, parse_mode=ParseMode.HTML)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await db.is_authenticated(update.effective_user.id):
        await update.message.reply_text("Please enter the password first. Use /start")
        return
    await db.log_action(update.effective_user.id, "help")
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)


async def summary_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await db.is_authenticated(uid):
        await update.message.reply_text("Please enter the password first. Use /start")
        return
    await db.log_action(uid, "summary")
    msg = await update.message.reply_text("Generating summary... Please wait.")
    try:
        summary = await services.generate_full_summary()
        await msg.delete()
        await split_send(update, summary)
    except Exception as e:
        logger.error("Summary generation failed: %s", e)
        await msg.edit_text(f"Error generating summary: {e}")


async def coins_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await db.is_authenticated(uid):
        await update.message.reply_text("Please enter the password first. Use /start")
        return
    await db.log_action(uid, "coins")
    coins = await db.get_active_coins()
    if not coins:
        await update.message.reply_text("No coins are being tracked.")
        return
    text = "<b>Tracked Coins:</b>\n\n"
    for c in coins:
        text += f"- <b>{c['symbol']}</b> ({c['name']})\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def support_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await db.is_authenticated(uid):
        await update.message.reply_text("Please enter the password first. Use /start")
        return
    await db.log_action(uid, "support")
    text = (
        "<b>Support the Project</b>\n\n"
        "If you find this bot useful, consider supporting development!\n\n"
        "<b>EVM Address (ETH/BSC/Polygon/etc):</b>\n"
        f"<code>{EVM_ADDRESS}</code>\n\n"
        "Thank you for your support!"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def myid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(
        f"Your Telegram ID: <code>{uid}</code>",
        parse_mode=ParseMode.HTML,
    )


async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await db.is_admin(uid):
        await update.message.reply_text("Access denied. Admin only.")
        return
    await db.log_action(uid, "admin_panel")
    await update.message.reply_text(
        "<b>Admin Panel</b>\nSelect an action:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_inline_keyboard(),
    )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    if not await db.is_admin(uid):
        await query.edit_message_text("Access denied.")
        return

    data = query.data

    if data == "admin_run_summary":
        await db.log_action(uid, "admin_run_summary")
        await query.edit_message_text("Generating summary... Please wait.")
        try:
            summary = await services.generate_full_summary()
            await split_send(update, summary, context=context, chat_id=uid)
        except Exception as e:
            logger.error("Admin summary failed: %s", e)
            await context.bot.send_message(chat_id=uid, text=f"Error: {e}")

    elif data == "admin_analytics":
        await db.log_action(uid, "admin_analytics")
        stats = await db.get_analytics()
        text = (
            "<b>User Analytics</b>\n\n"
            f"Total users: {stats['total_users']}\n"
            f"Authenticated: {stats['authenticated_users']}\n"
            f"Active 24h: {stats['active_24h']}\n"
            f"Active 7d: {stats['active_7d']}\n"
            f"Active 30d: {stats['active_30d']}\n"
            f"Actions today: {stats['actions_today']}\n\n"
            "<b>Top actions (7d):</b>\n"
        )
        for action, count in stats["top_actions_week"]:
            text += f"  {action}: {count}\n"
        await query.edit_message_text(text, parse_mode=ParseMode.HTML)

    elif data == "admin_users":
        await db.log_action(uid, "admin_users_list")
        users = await db.get_all_users_list()
        if not users:
            await query.edit_message_text("No users yet.")
            return
        text = "<b>All Users:</b>\n\n"
        for u in users[:50]:
            name = u["first_name"] or u["username"] or str(u["telegram_id"])
            status = "admin" if u["is_admin"] else ("auth" if u["is_authenticated"] else "pending")
            text += f"- {name} (ID: <code>{u['telegram_id']}</code>) [{status}]\n"
        if len(users) > 50:
            text += f"\n... and {len(users) - 50} more"
        await query.edit_message_text(text, parse_mode=ParseMode.HTML)

    elif data == "admin_add_coin":
        user_states[uid] = {"state": "adding_coin_symbol"}
        await query.edit_message_text(
            "Enter the coin <b>symbol</b> (e.g., BTC, ETH):",
            parse_mode=ParseMode.HTML,
        )

    elif data == "admin_remove_coin":
        coins = await db.get_active_coins()
        if not coins:
            await query.edit_message_text("No coins to remove.")
            return
        keyboard = []
        for c in coins:
            keyboard.append(
                [InlineKeyboardButton(f"{c['symbol']} - {c['name']}", callback_data=f"rm_coin_{c['symbol']}")]
            )
        keyboard.append([InlineKeyboardButton("Cancel", callback_data="admin_cancel")])
        await query.edit_message_text(
            "Select coin to remove:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data.startswith("rm_coin_"):
        symbol = data.replace("rm_coin_", "")
        await db.remove_coin(symbol)
        await db.log_action(uid, "admin_remove_coin", symbol)
        await query.edit_message_text(
            f"Coin <b>{symbol}</b> removed.",
            parse_mode=ParseMode.HTML,
        )

    elif data == "admin_cancel":
        await query.edit_message_text("Cancelled.")


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()
    uid = user.id

    await db.get_or_create_user(uid, user.username, user.first_name)

    if not await db.is_authenticated(uid):
        if text == BOT_PASSWORD:
            await db.authenticate_user(uid)
            await db.log_action(uid, "auth_success")
            admin = await db.is_admin(uid)
            await update.message.reply_text(
                "Access granted! Welcome!\n\nUse the menu below or send any message to chat with AI.",
                reply_markup=get_main_keyboard(admin),
            )
        else:
            await db.log_action(uid, "auth_fail")
            await update.message.reply_text("Wrong password. Try again or use /start for instructions.")
        return

    state = user_states.get(uid)
    if state:
        st = state.get("state")
        if st == "adding_coin_symbol":
            user_states[uid] = {"state": "adding_coin_name", "symbol": text.upper()}
            await update.message.reply_text(
                f"Symbol: <b>{text.upper()}</b>\nNow enter the coin <b>name</b>:",
                parse_mode=ParseMode.HTML,
            )
            return
        elif st == "adding_coin_name":
            symbol = state["symbol"]
            name = text
            await db.add_coin(symbol, name)
            await db.log_action(uid, "admin_add_coin", f"{symbol} - {name}")
            del user_states[uid]
            await update.message.reply_text(
                f"Coin <b>{symbol}</b> ({name}) added!",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_keyboard(True),
            )
            return

    if text == BTN_SUMMARY:
        return await summary_cmd(update, context)
    elif text == BTN_COINS:
        return await coins_cmd(update, context)
    elif text == BTN_SUPPORT:
        return await support_cmd(update, context)
    elif text == BTN_HELP:
        return await help_cmd(update, context)
    elif text == BTN_ADMIN:
        return await admin_cmd(update, context)

    await db.log_action(uid, "ai_question", text[:100])
    wait_msg = await update.message.reply_text("Thinking...")
    try:
        response = await services.ask_ai(text)
        await wait_msg.delete()
        await split_send(update, response)
    except Exception as e:
        logger.error("AI question failed: %s", e)
        await wait_msg.edit_text(f"Error: {e}")


async def scheduled_summary(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Running scheduled summary...")
    try:
        summary = await services.generate_full_summary()
        users = await db.get_authenticated_users()
        sent = 0
        failed = 0
        for user in users:
            try:
                parts = []
                text = summary
                while text:
                    if len(text) <= 4000:
                        parts.append(text)
                        break
                    idx = text.rfind("\n", 0, 4000)
                    if idx == -1:
                        idx = 4000
                    parts.append(text[:idx])
                    text = text[idx:].lstrip("\n")
                for part in parts:
                    try:
                        await context.bot.send_message(
                            chat_id=user["telegram_id"],
                            text=part,
                            parse_mode=ParseMode.HTML,
                            disable_web_page_preview=True,
                        )
                    except Exception:
                        await context.bot.send_message(
                            chat_id=user["telegram_id"],
                            text=part,
                            disable_web_page_preview=True,
                        )
                sent += 1
            except Exception as e:
                logger.error("Failed to send to %s: %s", user["telegram_id"], e)
                failed += 1
        logger.info("Scheduled summary sent to %d users, %d failed", sent, failed)
    except Exception as e:
        logger.error("Scheduled summary generation failed: %s", e)

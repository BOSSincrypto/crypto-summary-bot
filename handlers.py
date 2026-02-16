import logging
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from config import EVM_ADDRESS
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
    "<b>Добро пожаловать в Крипто Сводка Бот!</b>\n\n"
    "Этот бот предоставляет ежедневные сводки по отслеживаемым криптовалютам "
    "с AI-анализом, новостями и упоминаниями в Twitter.\n\n"
    "Используйте меню ниже или отправьте сообщение для общения с AI."
)

HELP_TEXT = (
    "<b>Крипто Сводка Бот - Помощь</b>\n\n"
    "<b>Команды:</b>\n"
    "/start - Запустить бота\n"
    "/summary - Получить текущую сводку\n"
    "/coins - Список отслеживаемых монет\n"
    "/support - Поддержать проект\n"
    "/help - Показать эту справку\n"
    "/myid - Показать ваш Telegram ID\n\n"
    "<b>Кнопки:</b>\n"
    "<b>Сводка</b> - AI-сводка по криптовалютам\n"
    "<b>Монеты</b> - Список отслеживаемых монет\n"
    "<b>Поддержать</b> - Поддержать проект\n"
    "<b>Помощь</b> - Эта справка\n"
    "<b>Админ</b> - Админ-панель (только для админов)\n\n"
    "<b>AI Агент:</b>\n"
    "Отправьте любое текстовое сообщение для общения с AI о крипте.\n\n"
    "<b>Расписание сводок:</b>\n"
    "Утренняя сводка: 08:00 МСК\n"
    "Вечерняя сводка: 23:00 МСК"
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
            [InlineKeyboardButton("Запустить сводку", callback_data="admin_run_summary")],
            [InlineKeyboardButton("Аналитика пользователей", callback_data="admin_analytics")],
            [InlineKeyboardButton("Список пользователей", callback_data="admin_users")],
            [InlineKeyboardButton("Добавить монету", callback_data="admin_add_coin")],
            [InlineKeyboardButton("Удалить монету", callback_data="admin_remove_coin")],
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
    await db.authenticate_user(user.id)
    await db.log_action(user.id, "start")
    admin = await db.is_admin(user.id)
    await update.message.reply_text(
        WELCOME_TEXT,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(admin),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await db.log_action(update.effective_user.id, "help")
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)


async def summary_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await db.log_action(uid, "summary")
    msg = await update.message.reply_text("Генерирую сводку... Пожалуйста, подождите.")
    try:
        summary = await services.generate_full_summary()
        await msg.delete()
        await split_send(update, summary)
    except Exception as e:
        logger.error("Summary generation failed: %s", e)
        await msg.edit_text(f"Ошибка генерации сводки: {e}")


async def coins_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await db.log_action(uid, "coins")
    coins = await db.get_active_coins()
    if not coins:
        await update.message.reply_text("Нет отслеживаемых монет.")
        return
    text = "<b>Отслеживаемые монеты:</b>\n\n"
    for c in coins:
        slug_info = f" | CMC: {c['cmc_slug']}" if c.get('cmc_slug') else ""
        text += f"- <b>{c['symbol']}</b> ({c['name']}{slug_info})\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def support_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await db.log_action(uid, "support")
    text = (
        "<b>Поддержать проект</b>\n\n"
        "Если вам нравится этот бот, поддержите разработку!\n\n"
        "<b>EVM адрес (ETH/BSC/Polygon и др.):</b>\n"
        f"<code>{EVM_ADDRESS}</code>\n\n"
        "Спасибо за вашу поддержку!"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def myid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(
        f"Ваш Telegram ID: <code>{uid}</code>",
        parse_mode=ParseMode.HTML,
    )


async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await db.is_admin(uid):
        await update.message.reply_text("Доступ запрещён. Только для админов.")
        return
    await db.log_action(uid, "admin_panel")
    await update.message.reply_text(
        "<b>Админ-панель</b>\nВыберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_inline_keyboard(),
    )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    if not await db.is_admin(uid):
        await query.edit_message_text("Доступ запрещён.")
        return

    data = query.data

    if data == "admin_run_summary":
        await db.log_action(uid, "admin_run_summary")
        await query.edit_message_text("Генерирую сводку... Пожалуйста, подождите.")
        try:
            summary = await services.generate_full_summary()
            await split_send(update, summary, context=context, chat_id=uid)
        except Exception as e:
            logger.error("Admin summary failed: %s", e)
            await context.bot.send_message(chat_id=uid, text=f"Ошибка: {e}")

    elif data == "admin_analytics":
        await db.log_action(uid, "admin_analytics")
        stats = await db.get_analytics()
        text = (
            "<b>Аналитика пользователей</b>\n\n"
            f"Всего пользователей: {stats['total_users']}\n"
            f"Авторизованных: {stats['authenticated_users']}\n"
            f"Активных за 24ч: {stats['active_24h']}\n"
            f"Активных за 7д: {stats['active_7d']}\n"
            f"Активных за 30д: {stats['active_30d']}\n"
            f"Действий за сегодня: {stats['actions_today']}\n\n"
            "<b>Топ действий (7д):</b>\n"
        )
        for action, count in stats["top_actions_week"]:
            text += f"  {action}: {count}\n"
        await query.edit_message_text(text, parse_mode=ParseMode.HTML)

    elif data == "admin_users":
        await db.log_action(uid, "admin_users_list")
        users = await db.get_all_users_list()
        if not users:
            await query.edit_message_text("Пользователей пока нет.")
            return
        text = "<b>Все пользователи:</b>\n\n"
        for u in users[:50]:
            name = u["first_name"] or u["username"] or str(u["telegram_id"])
            status = "админ" if u["is_admin"] else ("авторизован" if u["is_authenticated"] else "ожидает")
            text += f"- {name} (ID: <code>{u['telegram_id']}</code>) [{status}]\n"
        if len(users) > 50:
            text += f"\n... и ещё {len(users) - 50}"
        await query.edit_message_text(text, parse_mode=ParseMode.HTML)

    elif data == "admin_add_coin":
        user_states[uid] = {"state": "adding_coin_symbol"}
        await query.edit_message_text(
            "Введите <b>символ</b> монеты (например, BTC, ETH):",
            parse_mode=ParseMode.HTML,
        )

    elif data == "admin_remove_coin":
        coins = await db.get_active_coins()
        if not coins:
            await query.edit_message_text("Нет монет для удаления.")
            return
        keyboard = []
        for c in coins:
            keyboard.append(
                [InlineKeyboardButton(f"{c['symbol']} - {c['name']}", callback_data=f"rm_coin_{c['symbol']}")]
            )
        keyboard.append([InlineKeyboardButton("Отмена", callback_data="admin_cancel")])
        await query.edit_message_text(
            "Выберите монету для удаления:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data.startswith("rm_coin_"):
        symbol = data.replace("rm_coin_", "")
        await db.remove_coin(symbol)
        await db.log_action(uid, "admin_remove_coin", symbol)
        await query.edit_message_text(
            f"Монета <b>{symbol}</b> удалена.",
            parse_mode=ParseMode.HTML,
        )

    elif data == "admin_cancel":
        await query.edit_message_text("Отменено.")


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()
    uid = user.id

    await db.get_or_create_user(uid, user.username, user.first_name)

    if not await db.is_authenticated(uid):
        await db.authenticate_user(uid)

    state = user_states.get(uid)
    if state:
        st = state.get("state")
        if st == "adding_coin_symbol":
            user_states[uid] = {"state": "adding_coin_name", "symbol": text.upper()}
            await update.message.reply_text(
                f"Символ: <b>{text.upper()}</b>\nТеперь введите <b>название</b> монеты:",
                parse_mode=ParseMode.HTML,
            )
            return
        elif st == "adding_coin_name":
            symbol = state["symbol"]
            name = text
            user_states[uid] = {"state": "adding_coin_slug", "symbol": symbol, "name": name}
            await update.message.reply_text(
                f"Символ: <b>{symbol}</b>, Название: <b>{name}</b>\n"
                "Введите <b>CMC slug</b> (часть URL на CoinMarketCap, например <code>bitcoin</code> для bitcoin).\n"
                "Или отправьте <b>-</b> чтобы пропустить:",
                parse_mode=ParseMode.HTML,
            )
            return
        elif st == "adding_coin_slug":
            symbol = state["symbol"]
            name = state["name"]
            slug = text.strip().lower() if text.strip() != "-" else None
            await db.add_coin(symbol, name, slug)
            await db.log_action(uid, "admin_add_coin", f"{symbol} - {name} (slug: {slug})")
            del user_states[uid]
            slug_msg = f" (CMC slug: {slug})" if slug else ""
            await update.message.reply_text(
                f"Монета <b>{symbol}</b> ({name}){slug_msg} добавлена!",
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
    wait_msg = await update.message.reply_text("Думаю...")
    try:
        response = await services.ask_ai(text)
        await wait_msg.delete()
        await split_send(update, response)
    except Exception as e:
        logger.error("AI question failed: %s", e)
        await wait_msg.edit_text(f"Ошибка: {e}")


async def scheduled_summary(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Запуск запланированной сводки...")
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

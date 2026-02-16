import httpx
import json
import re
import logging
from html import unescape
from datetime import datetime
from config import CMC_API_KEY, OPENROUTER_API_KEY, AI_MODEL

logger = logging.getLogger(__name__)

CMC_BASE = "https://pro-api.coinmarketcap.com"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
REQUEST_TIMEOUT = 30


async def get_crypto_quotes(coins: list[dict]) -> dict:
    if not CMC_API_KEY:
        return {"error": "CMC API key not configured"}

    slugs = [c["cmc_slug"] for c in coins if c.get("cmc_slug")]
    symbols = [c["symbol"] for c in coins if not c.get("cmc_slug")]
    result = {}
    headers = {"X-CMC_PRO_API_KEY": CMC_API_KEY, "Accept": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            if slugs:
                resp = await client.get(
                    f"{CMC_BASE}/v2/cryptocurrency/quotes/latest",
                    headers=headers,
                    params={"slug": ",".join(slugs), "convert": "USD"},
                )
                data = resp.json()
                if data.get("status", {}).get("error_code", 0) == 0:
                    for _cmc_id, coin_data in data.get("data", {}).items():
                        if isinstance(coin_data, list):
                            coin_data = coin_data[0]
                        sym = coin_data.get("symbol", "")
                        result[sym] = _parse_coin_data(coin_data)

            if symbols:
                resp = await client.get(
                    f"{CMC_BASE}/v2/cryptocurrency/quotes/latest",
                    headers=headers,
                    params={"symbol": ",".join(symbols), "convert": "USD"},
                )
                data = resp.json()
                if data.get("status", {}).get("error_code", 0) == 0:
                    for sym in symbols:
                        entries = data.get("data", {}).get(sym, [])
                        if entries:
                            coin = entries[0] if isinstance(entries, list) else entries
                            result[sym] = _parse_coin_data(coin)
                        else:
                            result[sym] = {"error": f"Токен {sym} не найден на CoinMarketCap"}

    except Exception as e:
        logger.error("CMC API request failed: %s", e)
        return {"error": str(e)}

    for c in coins:
        sym = c["symbol"]
        if sym not in result:
            result[sym] = {"error": f"Токен {sym} не найден на CoinMarketCap"}

    return result


def _parse_coin_data(coin: dict) -> dict:
    quote = coin.get("quote", {}).get("USD", {})
    price = quote.get("price")
    vol_24h = quote.get("volume_24h")
    vol_change = quote.get("volume_change_24h")
    pct_1h = quote.get("percent_change_1h")
    pct_24h = quote.get("percent_change_24h")
    pct_7d = quote.get("percent_change_7d")
    pct_30d = quote.get("percent_change_30d")
    pct_60d = quote.get("percent_change_60d")
    pct_90d = quote.get("percent_change_90d")
    mcap = quote.get("market_cap")

    pressure = "neutral"
    if vol_change is not None and pct_24h is not None:
        if vol_change > 20 and pct_24h > 2:
            pressure = "strong_buy"
        elif vol_change > 0 and pct_24h > 0:
            pressure = "buy"
        elif vol_change > 20 and pct_24h < -2:
            pressure = "strong_sell"
        elif vol_change > 0 and pct_24h < 0:
            pressure = "sell"
        elif vol_change < -20:
            pressure = "low_activity"

    return {
        "name": coin.get("name", ""),
        "symbol": coin.get("symbol", ""),
        "cmc_id": coin.get("id"),
        "price": price,
        "volume_24h": vol_24h,
        "volume_change_24h": vol_change,
        "percent_change_1h": pct_1h,
        "percent_change_24h": pct_24h,
        "percent_change_7d": pct_7d,
        "percent_change_30d": pct_30d,
        "percent_change_60d": pct_60d,
        "percent_change_90d": pct_90d,
        "market_cap": mcap,
        "market_cap_dominance": quote.get("market_cap_dominance"),
        "fully_diluted_market_cap": quote.get("fully_diluted_market_cap"),
        "last_updated": quote.get("last_updated"),
        "circulating_supply": coin.get("circulating_supply"),
        "total_supply": coin.get("total_supply"),
        "max_supply": coin.get("max_supply"),
        "pressure": pressure,
    }


async def search_crypto_news(symbol: str, max_results: int = 5) -> list[dict]:
    results = []
    try:
        results = await _search_ddg(f'"{symbol}" crypto token news', max_results)
    except Exception as e:
        logger.warning("DDG news search failed: %s", e)
    return results[:max_results]


async def search_twitter_mentions(symbol: str, max_results: int = 4) -> list[dict]:
    results = []
    try:
        results = await _search_ddg(
            f'"{symbol}" crypto site:x.com OR site:twitter.com', max_results
        )
    except Exception as e:
        logger.warning("Twitter search failed: %s", e)
    return results[:max_results]


async def search_whale_alerts(symbol: str) -> list[dict]:
    results = []
    try:
        results = await _search_ddg(f'"{symbol}" whale alert large transaction', 3)
    except Exception as e:
        logger.warning("Whale alert search failed: %s", e)
    return results


async def _search_ddg(query: str, max_results: int = 8) -> list[dict]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15) as client:
        resp = await client.post(
            "https://lite.duckduckgo.com/lite/", data={"q": query}
        )
        text = resp.text
        results = []
        link_pattern = re.compile(
            r"""<a\s+rel=["']nofollow["']\s+href=["']([^"']+)["']\s+class=["']result-link["'][^>]*>(.*?)</a>""",
            re.DOTALL,
        )
        snippet_pattern = re.compile(
            r"""<td\s+class=["']result-snippet["'][^>]*>(.*?)</td>""", re.DOTALL
        )
        links = link_pattern.findall(text)
        snippets = snippet_pattern.findall(text)
        for i, (href, title) in enumerate(links[:max_results]):
            clean_title = unescape(re.sub(r"<.*?>", "", title)).strip()
            clean_snippet = ""
            if i < len(snippets):
                clean_snippet = unescape(re.sub(r"<.*?>", "", snippets[i])).strip()
            if clean_title:
                results.append(
                    {"title": clean_title, "url": href, "snippet": clean_snippet}
                )
        return results


async def _search_cryptocompare(query: str) -> list[dict]:
    url = "https://min-api.cryptocompare.com/data/v2/news/"
    params = {"lang": "EN", "categories": query, "sortOrder": "latest"}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params)
        data = resp.json()
        results = []
        for item in data.get("Data", [])[:5]:
            results.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("body", "")[:300],
                    "source": item.get("source", ""),
                }
            )
        return results


async def generate_ai_summary(crypto_data: dict, news_data: dict, twitter_data: dict, whale_data: dict = None) -> str:
    if not OPENROUTER_API_KEY:
        return _format_raw_summary(crypto_data, news_data, twitter_data)

    system_prompt = (
        "Ты - криптоаналитик. Создай КРАТКУЮ сводку НА РУССКОМ.\n"
        "Форматирование: ТОЛЬКО <b>, <i>, <code>. НЕ используй <html>, <div>, <h1>-<h6>, <ul>, <li>, <p>.\n"
        "Используй эмодзи и переносы строк.\n\n"
        "ВАЖНО: Пиши ТОЛЬКО о токенах OWB и RNBW (Rainbow). НЕ путай их с другими токенами (XRP, BTC и т.д.). "
        "Если новость не относится к OWB или RNBW - пропусти её.\n\n"
        "Структура:\n"
        "1. ЦЕНЫ - цена, изменение 1ч/24ч/7д, объём, давление\n"
        "2. КРУПНЫЕ СДЕЛКИ - анализ по объёмам\n"
        "3. НОВОСТИ - кратко по 1-2 предложения на каждую\n"
        "4. ВЫВОД - 2-3 предложения\n\n"
        "Будь кратким. Формат: $1,234.56, +5.2%, -3.1%. Если данных нет - укажи."
    )

    user_content = json.dumps(
        {
            "crypto_data": crypto_data,
            "news": news_data,
            "twitter_mentions": twitter_data,
            "whale_alerts": whale_data or {},
            "generated_at_utc": datetime.utcnow().isoformat(),
        },
        indent=2,
        ensure_ascii=False,
        default=str,
    )

    try:
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.post(
                f"{OPENROUTER_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": AI_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.3,
                },
            )
            data = resp.json()
            if "choices" in data and data["choices"]:
                return data["choices"][0]["message"]["content"]
            elif "error" in data:
                logger.error("OpenRouter error: %s", data["error"])
                return _format_raw_summary(crypto_data, news_data, twitter_data)
            else:
                return _format_raw_summary(crypto_data, news_data, twitter_data)
    except Exception as e:
        logger.error("AI summary generation failed: %s", e)
        return _format_raw_summary(crypto_data, news_data, twitter_data)


async def ask_ai(question: str, context: str = "") -> str:
    if not OPENROUTER_API_KEY:
        return "AI-агент не настроен. Установите OPENROUTER_API_KEY."
    system_prompt = (
        "Ты - полезный AI-ассистент по криптовалютам в Telegram-боте. "
        "Отвечай на вопросы о крипте, блокчейне и рынках на языке пользователя. "
        "Будь кратким и информативным. Используй HTML-теги для Telegram: <b>, <i>, <code>. "
        "НЕ используй другие HTML-теги."
    )
    if context:
        system_prompt += f"\n\nДополнительный контекст:\n{context}"

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{OPENROUTER_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": AI_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": question},
                    ],
                    "max_tokens": 1500,
                    "temperature": 0.5,
                },
            )
            data = resp.json()
            if "choices" in data and data["choices"]:
                return data["choices"][0]["message"]["content"]
            elif "error" in data:
                err = data["error"]
                if isinstance(err, dict):
                    return f"Ошибка AI: {err.get('message', str(err))}"
                return f"Ошибка AI: {err}"
            return "Нет ответа от AI."
    except Exception as e:
        logger.error("AI request failed: %s", e)
        return f"Ошибка запроса к AI: {e}"


async def generate_full_summary() -> str:
    from db import get_active_coins

    coins = await get_active_coins()
    if not coins:
        return "<b>Нет отслеживаемых монет.</b>\nАдмин может добавить монеты через админ-панель."

    crypto_data = await get_crypto_quotes(coins)

    news_data = {}
    twitter_data = {}
    whale_data = {}
    for c in coins:
        sym = c["symbol"]
        news_data[sym] = await search_crypto_news(sym)
        twitter_data[sym] = await search_twitter_mentions(sym)
        whale_data[sym] = await search_whale_alerts(sym)

    summary = await generate_ai_summary(crypto_data, news_data, twitter_data, whale_data)
    timestamp = datetime.utcnow().strftime("%d.%m.%Y %H:%M UTC")
    header = f"<b>Крипто Сводка</b> | {timestamp}\n{'=' * 30}\n\n"
    return header + summary


def _fmt_price(price):
    if price is None:
        return "N/A"
    if price < 0.01:
        return f"${price:,.8f}"
    if price < 1:
        return f"${price:,.6f}"
    return f"${price:,.2f}"


def _fmt_pct(pct):
    if pct is None:
        return "N/A"
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


def _fmt_vol(vol):
    if not vol:
        return "N/A"
    if vol >= 1_000_000:
        return f"${vol / 1_000_000:,.2f}M"
    if vol >= 1_000:
        return f"${vol / 1_000:,.2f}K"
    return f"${vol:,.2f}"


def _fmt_mcap(mcap):
    if not mcap:
        return "N/A"
    if mcap >= 1_000_000_000:
        return f"${mcap / 1_000_000_000:,.2f}B"
    if mcap >= 1_000_000:
        return f"${mcap / 1_000_000:,.2f}M"
    return f"${mcap:,.0f}"


PRESSURE_RU = {
    "strong_buy": "Сильное давление покупателей",
    "buy": "Давление покупателей",
    "strong_sell": "Сильное давление продавцов",
    "sell": "Давление продавцов",
    "low_activity": "Низкая активность",
    "neutral": "Нейтрально",
}


def _format_raw_summary(crypto_data: dict, news_data: dict, twitter_data: dict) -> str:
    parts = []
    for sym, data in crypto_data.items():
        if isinstance(data, dict) and "error" in data:
            parts.append(f"<b>{sym}</b>: {data['error']}")
            continue
        if not isinstance(data, dict):
            continue

        name = data.get("name", sym)
        pressure = PRESSURE_RU.get(data.get("pressure", "neutral"), "")

        parts.append(
            f"<b>{name} ({sym})</b>\n"
            f"Цена: {_fmt_price(data.get('price'))}\n"
            f"1ч: {_fmt_pct(data.get('percent_change_1h'))} | "
            f"24ч: {_fmt_pct(data.get('percent_change_24h'))} | "
            f"7д: {_fmt_pct(data.get('percent_change_7d'))}\n"
            f"30д: {_fmt_pct(data.get('percent_change_30d'))} | "
            f"60д: {_fmt_pct(data.get('percent_change_60d'))} | "
            f"90д: {_fmt_pct(data.get('percent_change_90d'))}\n"
            f"Объём 24ч: {_fmt_vol(data.get('volume_24h'))}\n"
            f"Изм. объёма: {_fmt_pct(data.get('volume_change_24h'))}\n"
            f"Market Cap: {_fmt_mcap(data.get('market_cap'))}\n"
            f"FDV: {_fmt_mcap(data.get('fully_diluted_market_cap'))}\n"
            f"Давление: {pressure}\n"
        )

    if news_data:
        parts.append("<b>Новости:</b>")
        for sym, articles in news_data.items():
            for a in articles[:3]:
                title = a.get("title", "")
                url = a.get("url", "")
                parts.append(f"- <a href='{url}'>{title}</a>")

    if twitter_data:
        parts.append("\n<b>Twitter:</b>")
        for sym, tweets in twitter_data.items():
            for t in tweets[:3]:
                title = t.get("title", "")
                url = t.get("url", "")
                parts.append(f"- <a href='{url}'>{title}</a>")

    return "\n".join(parts) if parts else "Нет данных."

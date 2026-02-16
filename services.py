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


async def get_crypto_quotes(symbols: list[str]) -> dict:
    if not CMC_API_KEY:
        return {"error": "CMC API key not configured"}
    url = f"{CMC_BASE}/v2/cryptocurrency/quotes/latest"
    headers = {"X-CMC_PRO_API_KEY": CMC_API_KEY, "Accept": "application/json"}
    params = {"symbol": ",".join(symbols), "convert": "USD"}
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(url, headers=headers, params=params)
            data = resp.json()
            if data.get("status", {}).get("error_code", 0) != 0:
                logger.error("CMC API error: %s", data["status"].get("error_message"))
                return {"error": data["status"].get("error_message", "CMC API error")}
            result = {}
            raw = data.get("data", {})
            for sym in symbols:
                entries = raw.get(sym, [])
                if not entries:
                    entries = raw.get(sym.upper(), [])
                if entries:
                    coin = entries[0] if isinstance(entries, list) else entries
                    quote = coin.get("quote", {}).get("USD", {})
                    result[sym] = {
                        "name": coin.get("name", sym),
                        "symbol": coin.get("symbol", sym),
                        "cmc_id": coin.get("id"),
                        "price": quote.get("price"),
                        "volume_24h": quote.get("volume_24h"),
                        "volume_change_24h": quote.get("volume_change_24h"),
                        "percent_change_1h": quote.get("percent_change_1h"),
                        "percent_change_24h": quote.get("percent_change_24h"),
                        "percent_change_7d": quote.get("percent_change_7d"),
                        "percent_change_30d": quote.get("percent_change_30d"),
                        "market_cap": quote.get("market_cap"),
                        "market_cap_dominance": quote.get("market_cap_dominance"),
                        "fully_diluted_market_cap": quote.get("fully_diluted_market_cap"),
                        "last_updated": quote.get("last_updated"),
                        "circulating_supply": coin.get("circulating_supply"),
                        "total_supply": coin.get("total_supply"),
                        "max_supply": coin.get("max_supply"),
                    }
                else:
                    result[sym] = {"error": f"Token {sym} not found on CoinMarketCap"}
            return result
    except Exception as e:
        logger.error("CMC API request failed: %s", e)
        return {"error": str(e)}


async def search_crypto_news(query: str, max_results: int = 8) -> list[dict]:
    results = []
    try:
        results = await _search_ddg(f"{query} crypto news", max_results)
    except Exception as e:
        logger.warning("DDG news search failed: %s", e)
    if len(results) < 3:
        try:
            extra = await _search_cryptocompare(query)
            results.extend(extra)
        except Exception as e:
            logger.warning("CryptoCompare news failed: %s", e)
    return results[:max_results]


async def search_twitter_mentions(query: str, max_results: int = 6) -> list[dict]:
    results = []
    try:
        results = await _search_ddg(
            f"{query} crypto site:x.com OR site:twitter.com", max_results
        )
    except Exception as e:
        logger.warning("Twitter search failed: %s", e)
    if len(results) < 2:
        try:
            extra = await _search_ddg(f"{query} token twitter", max_results)
            results.extend(extra)
        except Exception as e:
            logger.warning("Twitter fallback search failed: %s", e)
    return results[:max_results]


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
                    "snippet": item.get("body", "")[:200],
                    "source": item.get("source", ""),
                }
            )
        return results


async def generate_ai_summary(crypto_data: dict, news_data: dict, twitter_data: dict) -> str:
    if not OPENROUTER_API_KEY:
        return _format_raw_summary(crypto_data, news_data, twitter_data)

    system_prompt = (
        "You are a professional cryptocurrency analyst. "
        "Analyze the provided data and create a comprehensive daily summary in Russian. "
        "IMPORTANT: Output ONLY plain text with minimal Telegram HTML tags. "
        "Allowed tags: <b>, <i>, <code>. Do NOT output full HTML pages, no <html>, <head>, <body>, <div>, <style>, <h1>-<h6>, <ul>, <li>, <p> tags. "
        "Use line breaks for formatting. Use emoji for section headers. "
        "Structure:\n"
        "1. Price overview per coin (price, 24h/7d/30d changes)\n"
        "2. Volume analysis (24h volume, changes, buy/sell pressure)\n"
        "3. Market cap\n"
        "4. News highlights\n"
        "5. Twitter/social mentions\n"
        "6. Market sentiment\n"
        "7. Key insights\n\n"
        "If token not found, note clearly. Be concise. "
        "Format numbers: $1,234.56. "
        "Volume up + price up = buying pressure. "
        "Volume up + price down = selling pressure. "
        "Keep total response under 3000 characters."
    )

    user_content = json.dumps(
        {
            "crypto_data": crypto_data,
            "news": news_data,
            "twitter_mentions": twitter_data,
            "generated_at": datetime.utcnow().isoformat(),
        },
        indent=2,
        ensure_ascii=False,
        default=str,
    )

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
                        {"role": "user", "content": user_content},
                    ],
                    "max_tokens": 2500,
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
        return "AI agent is not configured. Set OPENROUTER_API_KEY."
    system_prompt = (
        "You are a helpful cryptocurrency AI assistant in a Telegram bot. "
        "Answer questions about crypto, blockchain, and markets in the language the user writes in. "
        "Be concise and informative. Use HTML formatting for Telegram."
    )
    if context:
        system_prompt += f"\n\nAdditional context:\n{context}"

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
                    return f"AI error: {err.get('message', str(err))}"
                return f"AI error: {err}"
            return "No response from AI."
    except Exception as e:
        logger.error("AI request failed: %s", e)
        return f"AI request failed: {e}"


async def generate_full_summary() -> str:
    from db import get_active_coins

    coins = await get_active_coins()
    symbols = [c["symbol"] for c in coins]
    if not symbols:
        return "<b>No coins are being tracked.</b>\nAdmin can add coins via the admin panel."

    crypto_data = await get_crypto_quotes(symbols)

    news_data = {}
    twitter_data = {}
    for c in coins:
        name = c["name"]
        sym = c["symbol"]
        search_term = f"{name}" if name != sym else sym
        news_data[sym] = await search_crypto_news(search_term)
        twitter_data[sym] = await search_twitter_mentions(search_term)

    summary = await generate_ai_summary(crypto_data, news_data, twitter_data)
    timestamp = datetime.utcnow().strftime("%d.%m.%Y %H:%M UTC")
    header = f"<b>Crypto Summary</b> | {timestamp}\n{'=' * 30}\n\n"
    return header + summary


def _format_raw_summary(crypto_data: dict, news_data: dict, twitter_data: dict) -> str:
    parts = []
    for sym, data in crypto_data.items():
        if isinstance(data, dict) and "error" in data:
            parts.append(f"<b>{sym}</b>: {data['error']}")
            continue
        if isinstance(data, dict):
            price = data.get("price")
            price_str = f"${price:,.6f}" if price and price < 1 else f"${price:,.2f}" if price else "N/A"
            vol = data.get("volume_24h")
            vol_str = f"${vol:,.0f}" if vol else "N/A"
            pct_24h = data.get("percent_change_24h")
            pct_str = f"{pct_24h:+.2f}%" if pct_24h is not None else "N/A"
            pct_7d = data.get("percent_change_7d")
            pct7_str = f"{pct_7d:+.2f}%" if pct_7d is not None else "N/A"
            mcap = data.get("market_cap")
            mcap_str = f"${mcap:,.0f}" if mcap else "N/A"
            vol_change = data.get("volume_change_24h")
            pressure = ""
            if vol_change is not None and pct_24h is not None:
                if vol_change > 0 and pct_24h > 0:
                    pressure = "Buying pressure detected"
                elif vol_change > 0 and pct_24h < 0:
                    pressure = "Selling pressure detected"
            parts.append(
                f"<b>{data.get('name', sym)} ({sym})</b>\n"
                f"Price: {price_str}\n"
                f"24h: {pct_str} | 7d: {pct7_str}\n"
                f"Volume 24h: {vol_str}\n"
                f"Market Cap: {mcap_str}\n"
                f"{pressure}"
            )

    if news_data:
        parts.append("\n<b>News:</b>")
        for sym, articles in news_data.items():
            for a in articles[:3]:
                parts.append(f"- <a href='{a.get('url', '')}'>{a.get('title', 'No title')}</a>")

    if twitter_data:
        parts.append("\n<b>Twitter Mentions:</b>")
        for sym, tweets in twitter_data.items():
            for t in tweets[:3]:
                parts.append(f"- <a href='{t.get('url', '')}'>{t.get('title', 'No title')}</a>")

    return "\n".join(parts) if parts else "No data available."

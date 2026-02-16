# Crypto Summary Bot

Telegram bot that provides daily AI-powered cryptocurrency summaries for tracked coins (OWB, Rainbow by default).

## Features

- **Scheduled Summaries**: Morning (08:00 MSK) and evening (23:00 MSK) automated reports
- **AI Analysis**: Powered by Google Gemma 3n via OpenRouter — analyzes prices, volume, news, and Twitter mentions
- **CoinMarketCap Integration**: Real-time price, volume, market cap data
- **News & Twitter Search**: Aggregates crypto news and social media mentions
- **Password Protection**: Access requires password authentication
- **Admin Panel**: Run test summaries, view user analytics, manage tracked coins
- **AI Chat**: Ask the AI agent any crypto-related question
- **Support**: Built-in donation page with EVM address
- **Compact**: Minimal dependencies, optimized for fly.io deployment

## Setup

### Environment Variables

| Variable | Description | Required |
|---|---|---|
| `BOT_TOKEN` | Telegram Bot API token | Yes |
| `CMC_API_KEY` | CoinMarketCap API key | Yes |
| `OPENROUTER_API_KEY` | OpenRouter API key | Yes |
| `BOT_PASSWORD` | Access password (default: `ax1`) | No |
| `ADMIN_IDS` | Comma-separated Telegram user IDs for admins | No |
| `AI_MODEL` | OpenRouter model (default: `google/gemma-3n-e4b-it`) | No |
| `DB_PATH` | SQLite database path (default: `data/bot.db`) | No |
| `PORT` | Health check server port (default: `8080`) | No |

### Local Development

```bash
# Clone the repo
git clone https://github.com/BOSSincrypto/crypto-summary-bot.git
cd crypto-summary-bot

# Install dependencies
pip install -r requirements.txt

# Copy and edit environment variables
cp .env.example .env
# Edit .env with your API keys

# Run
python main.py
```

### Get Your Telegram ID

1. Start the bot and enter the password
2. Use the `/myid` command to see your Telegram ID
3. Add it to `ADMIN_IDS` to get admin access

### Deploy to fly.io

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Login
fly auth login

# Create app (first time only)
fly apps create crypto-summary-bot

# Create volume for persistent data (first time only)
fly volumes create bot_data --region ams --size 1

# Set secrets
fly secrets set BOT_TOKEN="your_token"
fly secrets set CMC_API_KEY="your_key"
fly secrets set OPENROUTER_API_KEY="your_key"
fly secrets set BOT_PASSWORD="ax1"
fly secrets set ADMIN_IDS="your_telegram_id"

# Deploy
fly deploy
```

## Bot Commands

| Command | Description |
|---|---|
| `/start` | Start the bot, authenticate |
| `/summary` | Get current crypto summary |
| `/coins` | List tracked coins |
| `/support` | Support the project |
| `/help` | Show help |
| `/myid` | Show your Telegram ID |
| `/admin` | Admin panel (admins only) |

## Admin Features

- **Run Summary Now** — generate and send summary immediately (for testing)
- **User Analytics** — view user statistics (total, active, actions)
- **Users List** — see all registered users
- **Add Coin** — add a new cryptocurrency to track
- **Remove Coin** — remove a coin from tracking

## API Keys

### Telegram Bot Token
1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Create a new bot with `/newbot`
3. Copy the token

### CoinMarketCap API Key
1. Register at [coinmarketcap.com/api](https://coinmarketcap.com/api/)
2. Get your API key from the dashboard

### OpenRouter API Key
1. Register at [openrouter.ai](https://openrouter.ai/)
2. Create an API key

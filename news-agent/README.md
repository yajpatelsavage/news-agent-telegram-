# Market News Agent — Setup (about 15 minutes)

Sends you a Telegram brief with fresh news on **crypto, Indian markets, and US AI stocks only**. Runs for free on GitHub Actions — no server, no laptop left on.

## Step 1 — Create the Telegram bot (5 min)

1. In Telegram, open **@BotFather** → send `/newbot` → pick a name and username.
2. Copy the **token** it gives you (looks like `123456789:AAF...`).
3. Open your new bot's chat and press **Start**, then send it any message (e.g. "hi").
4. In a browser, open: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
5. In the JSON that appears, find `"chat":{"id": 123456789 ...}` — that number is your **chat id**.

## Step 2 — Put the code on GitHub (5 min)

1. Create a new repo (public is fine — your tokens never go in the code).
2. Add these files:
   - `news_agent.py`
   - `requirements.txt`
   - `.github/workflows/news.yml`  ← create the folders, put `news.yml` inside
3. Repo → **Settings → Secrets and variables → Actions → New repository secret**. Add:
   - `TELEGRAM_TOKEN` = your bot token
   - `TELEGRAM_CHAT_ID` = your chat id
   - `ANTHROPIC_API_KEY` = optional (see Step 3)

## Step 3 (optional) — Turn on the AI brain

Without a key, the agent uses plain keyword filtering (still works well).
With a key, Claude reads every candidate headline, kills clickbait/duplicates, enforces the "US = AI stocks only" rule intelligently, and writes a 15-word summary under each link.

Get a key at https://console.anthropic.com and add it as the `ANTHROPIC_API_KEY` secret. The script uses the cheapest model (Haiku); at this volume it costs pennies per month. Current models and pricing: https://docs.claude.com/en/api/overview

## Step 4 — Test it

Repo → **Actions** tab → select **market-news-agent** → **Run workflow**. Within a minute you should get a Telegram message. After that it runs automatically every 30 minutes and only sends stories it has never sent before.

Test locally instead (optional):

```
pip install -r requirements.txt
export TELEGRAM_TOKEN=...  TELEGRAM_CHAT_ID=...
python news_agent.py
```

## Customize

All knobs are at the top of `news_agent.py`:

- **FEEDS** — add/remove any RSS feed URL. If one ever dies, the agent just skips it and logs a warning; swap in a replacement.
- **AI_WHITELIST** — the tickers/terms a US headline must mention to survive. Add stocks you care about (e.g. Tesla, Arista).
- **BLOCKLIST** — junk topics dropped everywhere.
- **MAX_PER_CATEGORY** — headlines per section per message.
- **Schedule** — edit the cron line in `news.yml`. It's in UTC: every 30 min = `*/30 * * * *`; one daily digest at 9:00 IST = `30 3 * * *`.

## Known quirks

- GitHub's scheduler can lag 5–15 minutes at busy times — normal.
- GitHub pauses scheduled workflows after ~60 days of repo inactivity, but the bot's own `seen.json` commits count as activity, so it keeps itself alive.
- First run sends the most items (everything is "new"); it settles down after that.

## Upgrade ideas (in order)

1. **Price alerts** — CoinGecko's free API for crypto ("ping me if BTC moves 5%"); add a second small script on the same schedule.
2. **Daily digest + realtime split** — urgent stuff every 30 min, a summary at 9:00 IST.
3. **Portfolio-aware alerts** — Zerodha's Kite Connect API can feed your actual holdings into the filter, so the agent only alerts on stocks you own or track.
4. **Two-way bot** — add commands like /price btc or /nifty using Telegram's getUpdates long polling.

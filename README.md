# 🤖 InsidePulseAI — Telegram News Bot with Reddit + RSS + GPT-4

This bot collects hot market news from Reddit and RSS feeds, analyzes and summarizes them using GPT-4 in Russian, and automatically posts structured messages to a Telegram channel.

---

## 🔍 Features

* Aggregates news from:

  * Reddit (r/wallstreetbets, r/stocks, r/biotechstocks)
  * RSS feeds (biotech, mergers, insider rumors, swing trading blogs)
* Filters by key financial keywords (e.g., "merger", "FDA approval", "deal")
* Uses OpenAI GPT-4.1-mini to:

  * Summarize and translate posts
  * Add market impact commentary
  * Generate hashtags (e.g., `#TSLA`, `#AAPL`)
* Supports Telegram inline buttons and user subscription interaction
* Sends all signals to a configured Telegram channel every 15 minutes

---

## 📦 Requirements

```bash
pip install aiogram feedparser openai praw python-dotenv
```

---

## 🧾 Environment Variables (.env)

```env
TELEGRAM_TOKEN=...
CHANNEL_ID=...
OPENAI_API_KEY=...
REDDIT_CLIENT_ID=...
REDDIT_SECRET=...
```

---

## 🧠 GPT Prompt Logic

The bot sends a structured prompt to OpenAI:

* Translates + summarizes news in Russian
* Explains potential stock/market impact
* Infers affected companies even if not named
* Adds emoji + hashtags in final response

---

## ▶️ How to Run

```bash
python bot.py
```

* Every 15 minutes, the bot pulls new content
* It deduplicates using post IDs and links
* Sends each news item with inline button: "📩 Подписаться на сигналы"

---

## 📬 Output Format Example

```
🧬 Biotech stock receives FDA approval for new cancer drug...

📊 Expected impact: stock may gap up 10–20%

#BIIB #FDA #Oncology
🔥🔥
🔗 https://...
```

---

## ⚠️ Notes

* All GPT queries are in Russian
* Posts require ≥200 upvotes and 20+ comments on Reddit to trigger
* RSS items are scanned for keyword matches in titles

---

## 👤 Author

Created by **Igor Volnukhin** — AI x Finance automation enthusiast.

import os
import logging
import asyncio
import feedparser
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.enums.parse_mode import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.client.default import DefaultBotProperties
import praw
from openai import AsyncOpenAI

# === Загрузка переменных окружения ===
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_SECRET = os.getenv("REDDIT_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# === Настройка логов ===
logging.basicConfig(level=logging.INFO)

# === Настройка бота и OpenAI ===
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# === Reddit ===
reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_SECRET,
    user_agent="insidepulse-hotnews-bot"
)

# === Ключевые слова ===
KEYWORDS = ["merge", "merger", "buyout", "FDA approval", "pdufa", "acquisition", "deal", "phase 3", "nda", "bla", "crl"]
posted_ids = set()

# === Кнопка подписки ===
def subscribe_button():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📩 Подписаться на сигналы", callback_data="subscribe")]]
    )

@dp.callback_query(F.data == "subscribe")
async def subscribe_callback(callback: CallbackQuery):
    await callback.message.answer("✅ Вы подписаны на сигналы!")

# === Оценка важности ===
def importance_level(upvotes: int) -> str:
    if upvotes >= 1000:
        return "🔥🔥🔥"
    elif upvotes >= 500:
        return "🔥🔥"
    elif upvotes >= 200:
        return "🔥"
    else:
        return ""

# === GPT-анализ и перевод новости ===
async def summarize_post(title: str, selftext: str, url: str, upvotes: int) -> str:
    try:
        description = selftext.strip() or "(описание отсутствует)"
        prompt = (
            f"Ты — инвестор аналитик.\n"
            f"Сделай краткий и понятный пост на основе описания. "
            f"Если описание отсутствует — сделай разумное предположение на основе заголовка.\n"
            f"Добавь контекст как это может повлиять на цену акций.\n"
            f"Даже если в новости нет тикеров — предположи, какие компании могут быть затронуты. "
            f"В конце выведи список связанных тикеров акций или индексов в формате хештегов (#TSLA #AAPL).\n"
            f"Весь ответ — на русском языке максимум 8-10 строк. Используй немного эмодзи и структурируй ответ.\n\n"
            f"Заголовок: {title}\n"
            f"Описание: {description}\n"
            f"Upvotes: {upvotes}\n"
            f"Ссылка: {url}\n\n"
            f"Ответ:"
        )

        response = await openai_client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=300
        )

        summary = response.choices[0].message.content.strip()
        fire = importance_level(upvotes)
        return f"{summary}\n\n<b>{fire}</b>\n🔗 {url}"

    except Exception as e:
        logging.error(f"❌ GPT ошибка: {e}")
        return f"<b>{title}</b>\n🔗 {url}"

# === Обработка Reddit ===
async def fetch_from_reddit():
    subreddits = ["wallstreetbets", "stocks", "biotechstocks"]
    for sub in subreddits:
        logging.info(f"🔍 Fetching from r/{sub}")
        try:
            for post in reddit.subreddit(sub).hot(limit=20):
                text = f"{post.title.lower()} {post.selftext.lower()}"
                if (
                    any(kw in text for kw in KEYWORDS)
                    and post.id not in posted_ids
                    and post.score >= 200
                    and post.num_comments >= 20
                ):
                    summary = await summarize_post(post.title, post.selftext, post.url, post.score)
                    await bot.send_message(
                        chat_id=CHANNEL_ID,
                        text=summary,
                        reply_markup=subscribe_button(),
                        disable_web_page_preview=True
                    )
                    logging.info(f"✅ Отправлена Reddit новость: {post.title}")
                    posted_ids.add(post.id)
                    await asyncio.sleep(2)
        except Exception as e:
            logging.error(f"❌ Ошибка при обработке Reddit: {e}")

# === Обработка RSS ===
async def fetch_from_rss():
    rss_feeds = [
    # Биотех и новости о слияниях/одобрениях FDA
    "https://www.fiercebiotech.com/rss.xml",
    
    # Крупные и срочные рыночные новости
    "https://www.investing.com/rss/news_25.rss",
    "http://feeds.marketwatch.com/marketwatch/topstories/",
    "https://www.cnbc.com/id/20409666/device/rss/rss.html?x=1",
    #Разное/Сигналы
    "http://bluehorseshoestocks.com/feed/",
    "http://feeds.feedburner.com/Crossingwallstreet",
    "https://www.goodetrades.com/feed/",
    "https://speedtrader.com/feed/",

    # Инсайдеры и слухи
    "https://www.goodetrades.com/feed/",
    "http://bluehorseshoestocks.com/feed/",

    # Penny/Speculative picks
    "http://www.pennystockdream.com/blog/rss",
    "https://www.stockgumshoe.com/feed/",

    # Swing trading и сигналы
    "https://morpheustrading.com/blog/feed/",
    "https://swingtradebot.com/blog/feed/",

    # Аналитика и прогнозы для продвинутых
    "https://www.ccmmarketmodel.com/short-takes?format=RSS",
    "https://tsi-blog.com/feed/",
    "https://nitter.privacydev.net/unusual_whales/rss"  # Twitter-инсайды
]

    for url in rss_feeds:
        logging.info(f"🌐 Чтение RSS: {url}")
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                title = entry.title
                link = entry.link
                if any(kw in title.lower() for kw in KEYWORDS):
                    if link not in posted_ids:
                        summary = await summarize_post(title, entry.get("summary", ""), link, 10)
                        msg = f"🚀 <b>{title}</b>\n{summary}\n🔗 {link}"
                        await bot.send_message(
                            chat_id=CHANNEL_ID,
                            text=msg,
                            reply_markup=subscribe_button(),
                            disable_web_page_preview=True
                        )
                        posted_ids.add(link)
                        logging.info(f"✅ Отправлена RSS новость: {title}")
                        await asyncio.sleep(1)
        except Exception as e:
            logging.error(f"❌ Ошибка при обработке RSS {url}: {e}")

# === Основной цикл ===
async def fetch_and_send_news():
    await fetch_from_reddit()
    await fetch_from_rss()

async def periodic_news_sender():
    while True:
        await fetch_and_send_news()
        await asyncio.sleep(900)  # каждые 15 минут

async def main():
    logging.info("🚀 insidepulseai запущен...")
    asyncio.create_task(periodic_news_sender())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

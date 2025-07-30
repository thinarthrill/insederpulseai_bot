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

# добавь в начало:
POSTED_IDS_FILE = "posted_ids.txt"

# === Функция загрузки истории из файла ===
def load_posted_ids():
    if os.path.exists(POSTED_IDS_FILE):
        with open(POSTED_IDS_FILE, "r") as f:
            return set(line.strip() for line in f)
    return set()

# === Функция сохранения новой ссылки ===
def save_posted_id(post_id: str):
    with open(POSTED_IDS_FILE, "a") as f:
        f.write(post_id + "\n")

posted_ids = load_posted_ids()

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

# === Кнопка подписки ===
def subscribe_button():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📩 Подписаться на сигналы", callback_data="subscribe")]]
    )

@dp.callback_query(F.data == "subscribe")
async def subscribe_callback(callback: CallbackQuery):
    await callback.message.answer("✅ Вы подписаны на сигналы!")

import re

def markdown_to_html(text: str) -> str:
    # Преобразуем **жирный** в <b>жирный</b>
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    return text

# === GPT-анализ и перевод новости ===
async def summarize_post(title: str, selftext: str, url: str, upvotes: int) -> str:
    try:
        description = selftext.strip() or "(описание отсутствует)"
        prompt = (
            f"Ты — инвестор-аналитик.\n"
            f"Сделай краткий и понятный пост на русском языке на основе описания или заголовка. "
            f"Переведи заголовок на русский язык, если он на английском. "
            f"Добавь пояснение, как новость может повлиять на цену акций. "
            f"Предположи, какие компании могут быть затронуты. "
            f"В конце выведи хештеги тикеров (#TSLA #AAPL и т.д.). "
            f"Максимум 8-10 строк, немного эмодзи, структурировано.\n\n"
            f"Заголовок: {title}\n"
            f"Описание: {description}\n"
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
        summary = markdown_to_html(summary)  # ⬅️ добавь это
        return f"{summary}\n\n🔗 {url}"


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
                        #reply_markup=subscribe_button(),
                        disable_web_page_preview=True
                    )
                    logging.info(f"✅ Отправлена Reddit новость: {post.title}")
                    posted_ids.add(post.id)
                    save_posted_id(post.id)
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
                        await bot.send_message(
                            chat_id=CHANNEL_ID,
                            text=summary,
                            #reply_markup=subscribe_button(),
                            disable_web_page_preview=True
                        )
                        posted_ids.add(link)
                        save_posted_id(link)
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
from aiogram.types import Message

from sentence_transformers import SentenceTransformer, util

model_embed = SentenceTransformer("all-MiniLM-L6-v2")

def load_chunks_from_txt(file_path: str):
    with open(file_path, encoding="utf-8") as f:
        lines = f.readlines()

    chunks = []
    current_chunk = ""
    current_header = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if line.startswith("#"):  # Новый заголовок
            if current_chunk:
                chunks.append({"header": current_header, "text": current_chunk.strip()})
                current_chunk = ""
            current_header = line
        else:
            current_chunk += line + " "

    if current_chunk:
        chunks.append({"header": current_header, "text": current_chunk.strip()})

    return chunks

chunks = load_chunks_from_txt("aboutchannel.txt")

def search_knowledge_txt(query: str, threshold: float = 0.7) -> str | None:
    query_embed = model_embed.encode(query, convert_to_tensor=True)
    best_score = 0.0
    best_chunk = None

    for chunk in chunks:
        chunk_embed = model_embed.encode(chunk["text"], convert_to_tensor=True)
        score = util.cos_sim(query_embed, chunk_embed).item()

        if score > best_score and score >= threshold:
            best_score = score
            best_chunk = chunk

    return best_chunk["text"] if best_chunk else None

@dp.message()
async def handle_user_prompt(message: Message):
    user_text = message.text.strip()
    if user_text.startswith("/"):
        return

    try:
        kb_answer = search_knowledge_txt(user_text)

        if kb_answer:
            await message.answer(f"📚 <b>Из базы знаний:</b>\n{kb_answer}")
        else:
            prompt = (
                f"Ты — инвестиционный аналитик и ассистент. Ответь кратко, понятно и по делу на вопрос пользователя:\n"
                f"Вопрос: {user_text}\n\n"
                f"Ответ:"
            )

            response = await openai_client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=400
            )

            reply = markdown_to_html(response.choices[0].message.content.strip())
            await message.answer(reply)

    except Exception as e:
        logging.error(f"❌ Ошибка: {e}")
        await message.answer("Произошла ошибка при обработке запроса.")

async def main():
    logging.info("🚀 insidepulseai запущен...")
    asyncio.create_task(periodic_news_sender())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

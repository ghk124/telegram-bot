import os
import re
import json
import random
import uuid
import asyncio
import time
from collections import deque
from datetime import date, timedelta

import jdatetime
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from google import genai
from google.genai import types
import PIL.Image

# دریافت توکن‌ها از بخش Variables در Railway
TOKEN = os.getenv("TOKEN")
GEMINI_KEY = os.getenv("GEMINI_KEY")
BRSAPI_KEY = os.getenv("BRSAPI_KEY")  # اختیاری، فقط برای دستور /price لازمه

if not TOKEN:
    raise RuntimeError("متغیر محیطی TOKEN ست نشده! آن را در Railway > Variables اضافه کنید.")
if not GEMINI_KEY:
    raise RuntimeError("متغیر محیطی GEMINI_KEY ست نشده! آن را در Railway > Variables اضافه کنید.")

# تنظیمات هوش مصنوعی Gemini (SDK جدید google-genai)
client = genai.Client(api_key=GEMINI_KEY)
# از flash-lite استفاده می‌کنیم چون سهمیه‌ی رایگانش بیشتره (۱۵ درخواست/دقیقه و ~۱۰۰۰ درخواست/روز
# در مقابل ۱۰ درخواست/دقیقه و ~۲۵۰ درخواست/روز برای gemini-2.5-flash معمولی)
MODEL_NAME = "gemini-2.5-flash-lite"

# حداقل فاصله‌ی زمانی بین درخواست‌ها (ثانیه) تا زیر سقف رایگان بمونیم و به خطای ۴۲۹ نخوریم
MIN_SECONDS_BETWEEN_CALLS = 4.2
_request_lock = asyncio.Lock()
_last_request_time = 0.0

# شخصیت خودمونی و باحال ربات برای همه‌ی پاسخ‌های هوش مصنوعی
PERSONA = (
    "تو یه دستیار هوش مصنوعی خودمونی، باحال و دوست‌داشتنی برای یه گروه تلگرامی ایرانی هستی. "
    "همیشه با لحن صمیمی، محاوره‌ای و فارسیِ روزمره جواب بده (نه رسمی و کتابی). "
    "گاهی شوخی و طعنه‌ی بامزه و دوستانه بزن، ولی هیچ‌وقت توهین یا بی‌ادبی نکن. "
    "اگه ازت خواستن چیزی رو تحلیل کنی، تحلیل دقیق، مفید و قابل فهم بده. "
    "اگه برات تاریخچه‌ی پیام‌های قبلی کاربر یا لقبش رو فرستادم، از این اطلاعات برای جواب طبیعی‌تر و شخصی‌تر استفاده کن. "
    "جواب‌هات رو کوتاه و خوندنی نگه دار مگه اینکه توضیح بیشتر لازم باشه."
)

GENERATE_CONFIG = types.GenerateContentConfig(system_instruction=PERSONA)

# --- دیتابیس ساده در حافظه (RAM) ---
# توجه: اگه DATABASE_URL ست نشده باشه، همه‌ی این دیتاها با ری‌استارت ربات از بین می‌رن.
# اگه یه دیتابیس Postgres به پروژه‌ی Railway اضافه کنی (که DATABASE_URL رو خودکار می‌سازه)،
# این دیتاها بعد از هر ری‌استارت یا دیپلوی جدید هم حفظ می‌شن.
user_warnings = {}
muted_users = set()
user_names = {}             # user_id -> نیک‌نیمی که خودش انتخاب کرده (اختیاری)
user_tags = {}               # user_id -> لقب/نشان ویژه‌ای که ادمین بهش داده (مثل VIP، مدیر)
active_guess_games = {}      # chat_id -> {"number": int, "attempts": int}
active_math_games = {}       # chat_id -> {"answer": int, "question": str}
active_dooz_games = {}       # chat_id -> {"board": list, "player_x": int, "player_o": int|None, "turn": "X"/"O"}
user_message_history = {}    # user_id -> deque آخرین پیام‌ها (حافظه‌ی کوتاه‌مدت برای تحلیل)
learned_facts = {}           # کلیدواژه (lower) -> جوابی که ادمین یاد داده (بخش یادگیریِ فعال)
bad_words = set()            # کلماتی که ادمین برای فیلتر فحاشی/کلمات ممنوعه اضافه کرده
link_filter_enabled = True   # فیلتر لینک برای غیرادمین‌ها (با /togglelinks خاموش/روشن می‌شه)
user_message_times = {}      # user_id -> deque زمان آخرین پیام‌ها (برای تشخیص اسپم/فلود)

SPAM_WINDOW_SECONDS = 8      # اگه توی این بازه...
SPAM_MESSAGE_THRESHOLD = 5   # ...به این تعداد پیام برسه، اسپم تشخیص داده می‌شه
URL_PATTERN = re.compile(r"(https?://|www\.|t\.me/|telegram\.me/)", re.IGNORECASE)

# ---------- لایه‌ی ذخیره‌ی دائمی (اختیاری، فقط اگه DATABASE_URL ست شده باشه) ----------

DATABASE_URL = os.getenv("DATABASE_URL")
try:
    import psycopg2
except ImportError:
    psycopg2 = None


def _db_conn():
    if not DATABASE_URL or not psycopg2:
        return None
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print(f"⚠️ اتصال به دیتابیس برقرار نشد، روی حافظه‌ی موقت ادامه می‌دیم: {e}")
        return None


def init_db():
    conn = _db_conn()
    if not conn:
        return
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS bot_data (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
    finally:
        conn.close()


def db_save(key: str, data):
    conn = _db_conn()
    if not conn:
        return
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO bot_data (key, value) VALUES (%s, %s) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                (key, json.dumps(data)),
            )
    except Exception as e:
        print(f"⚠️ ذخیره‌ی {key} توی دیتابیس شکست خورد: {e}")
    finally:
        conn.close()


def db_load(key: str, default):
    conn = _db_conn()
    if not conn:
        return default
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT value FROM bot_data WHERE key = %s", (key,))
            row = cur.fetchone()
            return json.loads(row[0]) if row else default
    except Exception as e:
        print(f"⚠️ بارگذاری {key} از دیتابیس شکست خورد: {e}")
        return default
    finally:
        conn.close()


def save_warnings():
    db_save("user_warnings", {str(k): v for k, v in user_warnings.items()})


def save_muted():
    db_save("muted_users", list(muted_users))


def save_names():
    db_save("user_names", {str(k): v for k, v in user_names.items()})


def save_tags():
    db_save("user_tags", {str(k): v for k, v in user_tags.items()})


def save_learned():
    db_save("learned_facts", learned_facts)


def save_badwords():
    db_save("bad_words", list(bad_words))


def save_settings():
    db_save("settings", {"link_filter_enabled": link_filter_enabled})


def load_persisted_state():
    """اگه دیتابیس وصل باشه، همه‌ی دیتاهای ذخیره‌شده رو موقع روشن شدن ربات برمی‌گردونه."""
    global link_filter_enabled
    if not DATABASE_URL:
        print("ℹ️ DATABASE_URL ست نشده؛ ربات با حافظه‌ی موقت (RAM) کار می‌کنه.")
        return
    if not psycopg2:
        print("⚠️ psycopg2 نصب نشده؛ ذخیره‌ی دائمی غیرفعاله.")
        return

    init_db()
    user_warnings.update({int(k): v for k, v in db_load("user_warnings", {}).items()})
    muted_users.update(int(u) for u in db_load("muted_users", []))
    user_names.update({int(k): v for k, v in db_load("user_names", {}).items()})
    user_tags.update({int(k): v for k, v in db_load("user_tags", {}).items()})
    learned_facts.update(db_load("learned_facts", {}))
    bad_words.update(db_load("bad_words", []))
    settings = db_load("settings", {})
    link_filter_enabled = settings.get("link_filter_enabled", True)
    print("✅ دیتای قبلی از دیتابیس بارگذاری شد.")

GREETING_WORDS = {
    "سلام", "سلامم", "سلامی", "های", "هلو", "درود", "سلام!", "سلام،",
    "hi", "hello", "hey", "salam",
}

HISTORY_LIMIT = 8

PERSIAN_LETTERS = list("ابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی")
PERSIAN_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]
# اندیس‌ها مطابق date.weekday() پایتون: دوشنبه=0 ... یکشنبه=6
PERSIAN_WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]
PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"


def fa_num(n) -> str:
    return "".join(PERSIAN_DIGITS[int(ch)] if ch.isdigit() else ch for ch in str(n))


async def generate_content_safe(contents):
    """
    صدا زدن Gemini با ۲ محافظ:
    ۱. قبل از هر درخواست، اگه لازم باشه کمی صبر می‌کنه تا از سقف درخواست در دقیقه رد نشیم.
    ۲. اگه با وجود این به خطای ۴۲۹ (محدودیت) خوردیم، چندبار با فاصله بیشتر دوباره امتحان می‌کنه.
    """
    global _last_request_time
    async with _request_lock:
        wait = MIN_SECONDS_BETWEEN_CALLS - (time.monotonic() - _last_request_time)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request_time = time.monotonic()

    last_error = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME, contents=contents, config=GENERATE_CONFIG
            )
            return response.text
        except Exception as e:
            last_error = e
            message = str(e)
            if "429" in message or "RESOURCE_EXHAUSTED" in message:
                await asyncio.sleep(6 * (attempt + 1))
                continue
            raise
    raise last_error


async def ask_ai(prompt: str) -> str:
    """یک تابع کمکی برای صدا زدن Gemini با شخصیت خودمونی (با محافظت در برابر محدودیت نرخ)."""
    return await generate_content_safe(prompt)


def is_greeting(text: str) -> bool:
    if not text:
        return False
    tokens = re.findall(r"[\w\u0600-\u06FF]+", text.lower())
    return any(t in GREETING_WORDS for t in tokens)


def get_display_name(tg_user) -> str:
    """اسمی که باید برای این کاربر استفاده شه: یا نیک‌نیمی که خودش گفته، یا اسم پروفایل تلگرامش."""
    return user_names.get(tg_user.id, tg_user.first_name)


def add_to_history(user_id: int, text: str):
    if not text:
        return
    if user_id not in user_message_history:
        user_message_history[user_id] = deque(maxlen=HISTORY_LIMIT)
    user_message_history[user_id].append(text)


def get_history_context(user_id: int) -> str:
    history = user_message_history.get(user_id)
    if not history:
        return ""
    joined = "\n".join(f"- {m}" for m in history)
    return f"چندتا از پیام‌های اخیر این کاربر (برای شناخت بهتر زمینه‌ی حرفش):\n{joined}\n\n"


def find_learned_match(text: str):
    """اگه متن کاربر شامل یکی از کلیدواژه‌هایی باشه که ادمین یادش داده، جواب ثابت رو برمی‌گردونه."""
    text_lower = text.lower()
    for keyword, answer in learned_facts.items():
        if keyword in text_lower:
            return answer
    return None


# ---------- تقویم شمسی و شمارش معکوس مناسبت‌ها ----------

def next_jalali_occurrence(month: int, day: int) -> date:
    """نزدیک‌ترین تاریخ میلادیِ آینده (یا امروز) که معادل این روز/ماه شمسیه."""
    today_g = date.today()
    j_year = jdatetime.date.today().year
    candidate = jdatetime.date(j_year, month, day).togregorian()
    if candidate < today_g:
        candidate = jdatetime.date(j_year + 1, month, day).togregorian()
    return candidate


def get_next_chaharshanbe_suri() -> date:
    """آخرین چهارشنبه‌ی قبل از نوروز؛ چون روز ثابتی در تقویم شمسی نیست، نسبت به نوروز حساب می‌شه."""
    today_g = date.today()
    j_year = jdatetime.date.today().year
    candidates = []
    for y in (j_year, j_year + 1):
        nowruz_g = jdatetime.date(y, 1, 1).togregorian()
        offset = (nowruz_g.weekday() - 2) % 7  # سه‌شنبه=1، چهارشنبه=2 در weekday پایتون
        if offset == 0:
            offset = 7
        candidates.append(nowruz_g - timedelta(days=offset))
    future_candidates = [c for c in candidates if c >= today_g]
    return min(future_candidates) if future_candidates else min(candidates)


def days_until(target: date) -> int:
    return (target - date.today()).days


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    j_today = jdatetime.date.today()
    weekday_fa = PERSIAN_WEEKDAYS[date.today().weekday()]
    month_fa = PERSIAN_MONTHS[j_today.month - 1]
    text = (
        f"📅 امروز {weekday_fa}، {fa_num(j_today.day)} {month_fa} {fa_num(j_today.year)} هست.\n"
        f"(میلادی: {date.today().strftime('%Y-%m-%d')})"
    )
    await update.message.reply_text(text)


async def countdown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today_g = date.today()
    nowruz_g = next_jalali_occurrence(1, 1)
    sizdah_g = next_jalali_occurrence(1, 13)
    yalda_g = next_jalali_occurrence(10, 1)  # نمادِ شب یلدا (شامگاه قبلش)
    chaharshanbe_g = get_next_chaharshanbe_suri()

    occasions = [
        ("🎉 نوروز", nowruz_g),
        ("🔥 چهارشنبه‌سوری", chaharshanbe_g),
        ("🌳 سیزده‌به‌در", sizdah_g),
        ("🍉 شب یلدا", yalda_g),
    ]
    occasions.sort(key=lambda x: x[1])

    lines = []
    for name, target in occasions:
        d = days_until(target)
        if d == 0:
            lines.append(f"{name}: امروزه! 🎊")
        else:
            lines.append(f"{name}: {fa_num(d)} روز دیگه")

    await update.message.reply_text("⏳ **شمارش معکوس مناسبت‌ها:**\n\n" + "\n".join(lines), parse_mode="Markdown")


# ---------- نرخ دلار و طلا ----------

async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not BRSAPI_KEY:
        await update.message.reply_text(
            "❌ هنوز کلید قیمت‌ها تنظیم نشده.\n"
            "یه کلید رایگان از brsapi.ir بگیر (تا ۱۵۰۰ درخواست در روز، بدون پرداخت) "
            "و در Railway > Variables با اسم `BRSAPI_KEY` ستش کن.",
            parse_mode="Markdown",
        )
        return

    sent_msg = await update.message.reply_text("💰 صبر کن، نرخ لحظه‌ای رو می‌گیرم...")
    try:
        resp = requests.get(
            "https://BrsApi.ir/Market/Gold_Currency.php",
            params={"key": BRSAPI_KEY},
            timeout=10,
        )
        data = resp.json()
    except Exception as e:
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=sent_msg.message_id,
            text=f"❌ نتونستم به سرویس نرخ ارز وصل شم.\n`{e}`",
            parse_mode="Markdown",
        )
        return

    lines = []
    for section_key in ("gold", "currency"):
        items = data.get(section_key) if isinstance(data, dict) else None
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = item.get("name") or item.get("name_en") or item.get("symbol") or "?"
                price = item.get("price")
                if price is None:
                    continue
                price_str = f"{price:,}" if isinstance(price, (int, float)) else str(price)
                lines.append(f"🔸 {name}: {price_str}")

    if not lines:
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=sent_msg.message_id,
            text=(
                "⚠️ جواب از سرویس گرفتم ولی نتونستم قیمت‌ها رو پیدا کنم (ساختار JSON فرق داره).\n"
                "این بخش رو برای صاحب ربات بفرست تا فیلدها رو درست کنه:\n"
                f"`{str(data)[:500]}`"
            ),
            parse_mode="Markdown",
        )
        return

    await context.bot.edit_message_text(
        chat_id=update.message.chat_id,
        message_id=sent_msg.message_id,
        text="💰 **نرخ لحظه‌ای:**\n\n" + "\n".join(lines),
        parse_mode="Markdown",
    )


# ---------- فال حافظ ----------

async def hafez_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sent_msg = await update.message.reply_text("🔮 یه نیت کن... الان برات فال می‌گیرم...")
    try:
        prompt = (
            "نقش یه فال‌بین سنتی ایرانی رو بازی کن که فال حافظ می‌گیره. "
            "یه بیت یا چند بیت واقعی و معروف از دیوان حافظ رو انتخاب و بنویس، یه خط فاصله بگذار، "
            "و بعد یه تفسیر کوتاه، خودمونی، امیدبخش و امروزی برای نیت و زندگی کاربر از روی همون بیت بنویس. "
            "تفسیر باید حس خوب بده ولی واقعی و طبیعی باشه، نه شعاری."
        )
        reply_text = await ask_ai(prompt)
    except Exception as e:
        reply_text = f"❌ یه خطا خوردم تو گرفتن فال.\n`{e}`"
    await context.bot.edit_message_text(
        chat_id=update.message.chat_id, message_id=sent_msg.message_id, text=reply_text,
        parse_mode="Markdown" if reply_text.startswith("❌") else None,
    )


# ---------- جستجوی ویکی‌پدیا ----------

WIKI_LANG = "fa"  # ویکی‌پدیای فارسی؛ برای انگلیسی بشه "en"
# تگ "ویکی" باید ابتدای پیام باشه و یه جداکننده (فاصله/دونقطه/ویرگول) قبل از عبارت جستجو بیاد
WIKI_TRIGGER_PATTERN = re.compile(r"^ویکی[\s:،]+(.+)$")


def wiki_search(query: str):
    """جستجو توی ویکی‌پدیا و گرفتن خلاصه‌ی بهترین نتیجه."""
    search_resp = requests.get(
        f"https://{WIKI_LANG}.wikipedia.org/w/api.php",
        params={"action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": 1},
        timeout=10,
    )
    results = search_resp.json().get("query", {}).get("search", [])
    if not results:
        return None

    title = results[0]["title"]
    summary_resp = requests.get(
        f"https://{WIKI_LANG}.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(title)}",
        timeout=10,
    )
    summary_data = summary_resp.json()
    extract = summary_data.get("extract") or "خلاصه‌ای پیدا نشد، ولی می‌تونی خودِ مقاله رو بخونی."
    page_url = (
        summary_data.get("content_urls", {}).get("desktop", {}).get("page")
        or f"https://{WIKI_LANG}.wikipedia.org/wiki/{requests.utils.quote(title)}"
    )
    return {"title": title, "extract": extract, "url": page_url}


async def do_wiki_lookup(update: Update, query: str):
    sent_msg = await update.message.reply_text(f"📖 دارم «{query}» رو توی ویکی‌پدیا می‌گردم...")
    try:
        result = wiki_search(query)
    except Exception as e:
        await sent_msg.edit_text(f"❌ نتونستم به ویکی‌پدیا وصل شم.\n{e}")
        return

    if not result:
        await sent_msg.edit_text(f"❌ چیزی برای «{query}» توی ویکی‌پدیا پیدا نکردم.")
        return

    text = f"📖 **{result['title']}**\n\n{result['extract']}\n\n🔗 {result['url']}"
    await sent_msg.edit_text(text, parse_mode="Markdown")


# دستور /wiki <عبارت> - جستجوی مستقیم با دستور
async def wiki_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args).strip()
    if not query:
        await update.message.reply_text(
            "❌ بعد از دستور چیزی که می‌خوای جستجو کنی رو بنویس. مثلاً:\n`/wiki پایتون`",
            parse_mode="Markdown",
        )
        return
    await do_wiki_lookup(update, query)


async def namefamily_timeout(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text="⏰ وقت تموم شد! جواب‌هاتون رو بفرستین تا ببینیم کی بیشتر و بهتر نوشته 😄",
    )


async def namefamily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    letter = random.choice(PERSIAN_LETTERS)
    await update.message.reply_text(
        f"🎲 بازی اسم فامیل شروع شد!\nحرف امتحان: **{letter}**\n"
        "اسم، فامیل، شهر، حیوان، غذا، گل/میوه با این حرف بگید!\n"
        "⏱ ۶۰ ثانیه وقت دارید...",
        parse_mode="Markdown",
    )
    if context.job_queue:
        context.job_queue.run_once(
            namefamily_timeout,
            when=60,
            chat_id=update.message.chat_id,
            name=f"namefamily_{update.message.chat_id}",
        )


# دستور /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🤖 بخش هوش مصنوعی", callback_data="ai_mode")],
        [InlineKeyboardButton("🎮 بازی‌ها", callback_data="games_menu")],
        [InlineKeyboardButton("📜 راهنمای دستورات", callback_data="help_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"سلام {get_display_name(update.effective_user)} جون! خوش اومدی 😄\n"
        "یه گزینه انتخاب کن یا همینجوری بهم سلام کن، خودم جواب می‌دم:",
        reply_markup=reply_markup,
    )


HELP_TEXT = (
    "📜 **دستورات ربات:**\n\n"
    "🔹 `/ai <متن>` - شروع صحبت با هوش مصنوعی\n"
    "🔹 بعدش روی جواب‌های من ریپلای کن تا ادامه‌ی گفتگو یا تحلیل بگیری\n"
    "🔹 یه سلام ساده هم بکنی، خودم جواب می‌دم 👋\n"
    "🔹 `/nickname <اسم>` - بگو با چه اسمی صدات کنم\n"
    "🔹 `/profile` - دیدن پروفایلت (یا ریپلای رو یکی دیگه)\n"
    "🔹 `/tag` - دیدن لقب ویژه (یا ریپلای رو یکی دیگه)\n\n"
    "🇮🇷 **بخش ایرانی:**\n"
    "🔸 `/hafez` - فال حافظ بگیر\n"
    "🔸 `/today` - تاریخ امروز به شمسی\n"
    "🔸 `/countdown` - شمارش معکوس تا نوروز، چهارشنبه‌سوری، سیزده‌به‌در و یلدا\n"
    "🔸 `/price` - نرخ لحظه‌ای دلار و طلا\n"
    "🔸 `/wiki <عبارت>` یا بنویس «ویکی عبارت» - جستجو در ویکی‌پدیا\n\n"
    "🎮 **بازی‌ها:**\n"
    "🔸 `/game` - منوی بازی‌ها\n"
    "🔸 `/guess` - بازی حدس عدد\n"
    "🔸 `/rps` - سنگ کاغذ قیچی\n"
    "🔸 `/math` - ریاضی سریع\n"
    "🔸 `/namefamily` - بازی اسم فامیل\n"
    "🔸 `/dooz` - بازی دوز (با دکمه)؛ بدون ریپلای یعنی با من، با ریپلای روی یکی یعنی به چالش کشیدنش\n\n"
    "👮‍♂️ **دستورات مدیریتی:**\n"
    "🔸 `/ban` - مسدود کردن کاربر (ریپلای)\n"
    "🔸 `/mute` - سکوت کاربر (ریپلای)\n"
    "🔸 `/unmute` - لغو سکوت (ریپلای)\n"
    "🔸 `/warn` - دادن اخطار (ریپلای)\n"
    "🔸 `/settag <متن>` - دادن لقب ویژه به کاربر (ریپلای) مثل VIP یا مدیر\n"
    "🔸 `/removetag` - حذف لقب کاربر (ریپلای)\n"
    "🔸 `/learn کلیدواژه | جواب` - یاد دادن یه جواب ثابت به ربات\n"
    "🔸 `/forget کلیدواژه` - فراموش کردن یه چیزی که یاد داده بودی\n"
    "🔸 `/learned` - لیست چیزایی که ربات تا الان یاد گرفته\n"
    "🔸 `/addbadword کلمه` - اضافه کردن کلمه به فیلتر فحاشی\n"
    "🔸 `/removebadword کلمه` - حذف کلمه از فیلتر\n"
    "🔸 `/badwords` - دیدن لیست کلمات فیلترشده\n"
    "🔸 `/togglelinks` - روشن/خاموش کردن فیلتر لینک برای غیرادمین‌ها"
)


# دستور /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")


# دستور /nickname - کاربر می‌تونه بگه باهاش چه اسمی صداش کنیم
async def nickname_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nickname = " ".join(context.args).strip()
    if not nickname:
        await update.message.reply_text(
            "❌ بعد از دستور اسمت رو بنویس. مثلاً:\n`/nickname علی`", parse_mode="Markdown"
        )
        return
    user_names[update.effective_user.id] = nickname[:30]
    save_names()
    try:
        reply_text = await ask_ai(
            "خودمونی و باحال تاییدش کن و یه شوخی کوچیک با اسمش بکن (محترمانه)."
        )
    except Exception:
        reply_text = f"باشه، از الان می‌گم {nickname[:30]} 😄"
    await update.message.reply_text(reply_text)


# دستور /tag - دیدن لقب ویژه‌ی یه کاربر
async def tag_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user = (
        update.message.reply_to_message.from_user
        if update.message.reply_to_message
        else update.effective_user
    )
    tag = user_tags.get(target_user.id)
    name = get_display_name(target_user)
    if tag:
        await update.message.reply_text(f"🏷️ لقب {name}: {tag}")
    else:
        await update.message.reply_text(f"این بنده‌خدا ({name}) هنوز لقب خاصی نداره.")


# دستور /profile - پروفایلی که ربات از کاربر یادشه
async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user = (
        update.message.reply_to_message.from_user
        if update.message.reply_to_message
        else update.effective_user
    )
    uid = target_user.id
    name = get_display_name(target_user)
    tag = user_tags.get(uid, "—")
    warnings = user_warnings.get(uid, 0)
    muted = "بله 🔇" if uid in muted_users else "خیر"
    text = (
        f"👤 **پروفایل {name}**\n"
        f"🏷️ لقب: {tag}\n"
        f"⚠️ اخطارها: {warnings}/3\n"
        f"🔇 بی‌صداست: {muted}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


def games_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔢 حدس عدد", callback_data="game_guess_start")],
        [InlineKeyboardButton("✊ سنگ کاغذ قیچی", callback_data="game_rps_menu")],
        [InlineKeyboardButton("➕ ریاضی سریع", callback_data="game_math_start")],
        [InlineKeyboardButton("🎲 اسم فامیل", callback_data="game_namefamily_start")],
        [InlineKeyboardButton("❌⭕ دوز", callback_data="game_dooz_start")],
    ]
    return InlineKeyboardMarkup(keyboard)


# دستور /game - منوی بازی‌ها
async def game_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎮 کدوم بازی رو می‌خوای؟", reply_markup=games_keyboard())


def start_guess_game(chat_id: int):
    number = random.randint(1, 100)
    active_guess_games[chat_id] = {"number": number, "attempts": 0}


def start_math_game(chat_id: int):
    a, b = random.randint(1, 50), random.randint(1, 50)
    op = random.choice(["+", "-", "*"])
    if op == "*":
        a, b = random.randint(1, 12), random.randint(1, 12)
    question = f"{a} {op} {b}"
    answer = eval(f"{a}{op}{b}")
    active_math_games[chat_id] = {"answer": answer, "question": question}
    return question


# دستور /guess
async def guess_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start_guess_game(update.message.chat_id)
    await update.message.reply_text(
        "🔢 یه عدد بین ۱ تا ۱۰۰ تو ذهنم گذاشتم! حدس بزن چنده (فقط عدد رو بفرست)."
    )


# دستور /math
async def math_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = start_math_game(update.message.chat_id)
    await update.message.reply_text(f"➕ سریع باش: {question} = ?")


# دستور /rps
async def rps_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✊ یکی رو انتخاب کن:", reply_markup=rps_keyboard())


def rps_keyboard():
    keyboard = [[
        InlineKeyboardButton("✊ سنگ", callback_data="rps_rock"),
        InlineKeyboardButton("✋ کاغذ", callback_data="rps_paper"),
        InlineKeyboardButton("✌️ قیچی", callback_data="rps_scissors"),
    ]]
    return InlineKeyboardMarkup(keyboard)


def play_rps(user_choice: str) -> str:
    options = {"rps_rock": "سنگ", "rps_paper": "کاغذ", "rps_scissors": "قیچی"}
    bot_choice = random.choice(list(options.keys()))
    user_fa, bot_fa = options[user_choice], options[bot_choice]

    if user_choice == bot_choice:
        result = "🤝 مساوی شدیم!"
    elif (
        (user_choice == "rps_rock" and bot_choice == "rps_scissors")
        or (user_choice == "rps_paper" and bot_choice == "rps_rock")
        or (user_choice == "rps_scissors" and bot_choice == "rps_paper")
    ):
        result = "🎉 بردی! دمت گرم."
    else:
        result = "😎 من بردم! یه دست دیگه بزن."

    return f"تو: {user_fa} | من: {bot_fa}\n{result}"


# ---------- بازی دوز (X O) با دکمه‌های شیشه‌ای ----------

DOOZ_LINES = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
]


def check_dooz_winner(board):
    for a, b, c in DOOZ_LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    if all(cell for cell in board):
        return "draw"
    return None


def dooz_minimax(board, player):
    winner = check_dooz_winner(board)
    if winner == "X":
        return -1
    if winner == "O":
        return 1
    if winner == "draw":
        return 0

    scores = []
    for i in range(9):
        if not board[i]:
            board[i] = player
            scores.append(dooz_minimax(board, "O" if player == "X" else "X"))
            board[i] = ""
    return max(scores) if player == "O" else min(scores)


def dooz_bot_move(board):
    """با مینی‌ماکس کامل بهترین حرکت رو پیدا می‌کنه؛ ربات هیچ‌وقت نمی‌بازه."""
    best_score, best_moves = None, []
    for i in range(9):
        if not board[i]:
            board[i] = "O"
            score = dooz_minimax(board, "X")
            board[i] = ""
            if best_score is None or score > best_score:
                best_score, best_moves = score, [i]
            elif score == best_score:
                best_moves.append(i)
    return random.choice(best_moves)


def render_dooz_board(board):
    symbols = {"X": "❌", "O": "⭕", "": "▫️"}
    keyboard = []
    for row in range(3):
        keyboard.append([
            InlineKeyboardButton(symbols[board[row * 3 + col]], callback_data=f"dooz_move_{row * 3 + col}")
            for col in range(3)
        ])
    return InlineKeyboardMarkup(keyboard)


def start_dooz_game(chat_id: int, x_user, o_user=None):
    board = [""] * 9
    active_dooz_games[chat_id] = {
        "board": board,
        "player_x": x_user.id,
        "player_o": o_user.id if o_user else None,
        "x_name": get_display_name(x_user),
        "o_name": get_display_name(o_user) if o_user else "من",
        "turn": "X",
    }
    return active_dooz_games[chat_id]


def dooz_status_text(game, finished_text=None):
    if finished_text:
        return finished_text
    turn_symbol = "❌" if game["turn"] == "X" else "⭕"
    turn_name = game["x_name"] if game["turn"] == "X" else game["o_name"]
    return f"⭕❌ {game['x_name']} ❌ در مقابل {game['o_name']} ⭕\nنوبت {turn_symbol} ({turn_name}) هست."


# دستور /dooz - بدون ریپلای یعنی در مقابل خودِ ربات، با ریپلای یعنی به چالش کشیدن یه کاربر
async def dooz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    x_user = update.effective_user
    o_user = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user.id != x_user.id:
        o_user = update.message.reply_to_message.from_user

    game = start_dooz_game(chat_id, x_user, o_user)
    await update.message.reply_text(
        dooz_status_text(game), reply_markup=render_dooz_board(game["board"])
    )


async def finish_dooz_game(query, game, winner):
    chat_id = query.message.chat_id
    if winner == "draw":
        text = "🤝 مساوی شد! بازی خوبی بود."
    elif game["player_o"] is None:
        text = "🎉 بردی! دمت گرم، حریف سختی بودی." if winner == "X" else "😎 من بردم! یه دست دیگه می‌خوای؟ بزن /dooz"
    else:
        winner_name = game["x_name"] if winner == "X" else game["o_name"]
        text = f"🎉 {winner_name} ({'❌' if winner == 'X' else '⭕'}) برد!"
    del active_dooz_games[chat_id]
    await query.edit_message_text(text=text, reply_markup=render_dooz_board(game["board"]))


async def handle_dooz_move(query, context: ContextTypes.DEFAULT_TYPE, position: int):
    chat_id = query.message.chat_id
    game = active_dooz_games.get(chat_id)
    if not game:
        await query.answer("این بازی دیگه فعال نیست. با /dooz یه بازی جدید شروع کن.", show_alert=True)
        return

    user_id = query.from_user.id
    turn = game["turn"]
    expected_player = game["player_x"] if turn == "X" else game["player_o"]

    if expected_player is None or user_id != expected_player:
        await query.answer("نوبت تو نیست! 😅", show_alert=True)
        return

    board = game["board"]
    if board[position]:
        await query.answer("این خونه قبلاً پر شده!", show_alert=True)
        return

    board[position] = turn
    await query.answer()

    winner = check_dooz_winner(board)
    if winner:
        await finish_dooz_game(query, game, winner)
        return

    game["turn"] = "O" if turn == "X" else "X"

    # اگه نوبت ربات شد، خودش بلافاصله حرکت می‌کنه
    if game["turn"] == "O" and game["player_o"] is None:
        bot_pos = dooz_bot_move(board)
        board[bot_pos] = "O"
        winner = check_dooz_winner(board)
        if winner:
            await finish_dooz_game(query, game, winner)
            return
        game["turn"] = "X"

    await query.edit_message_text(text=dooz_status_text(game), reply_markup=render_dooz_board(board))


# هندلر دکمه‌های شیشه‌ای (Inline Keyboard)
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    # حرکت‌های دوز خودش با متن دلخواه (مثل "نوبت تو نیست") جواب می‌ده، پس قبل از answer عمومی پردازش می‌شه
    if data.startswith("dooz_move_"):
        await handle_dooz_move(query, context, int(data.rsplit("_", 1)[1]))
        return

    await query.answer()

    if data == "ai_mode":
        await query.message.reply_text(
            "🤖 برای صحبت با هوش مصنوعی بنویس:\n`/ai متن سوال یا حرفت`",
            parse_mode="Markdown",
        )
    elif data == "help_menu":
        await query.message.reply_text(HELP_TEXT, parse_mode="Markdown")
    elif data == "games_menu":
        await query.message.reply_text("🎮 کدوم بازی رو می‌خوای؟", reply_markup=games_keyboard())
    elif data == "game_guess_start":
        start_guess_game(query.message.chat_id)
        await query.message.reply_text(
            "🔢 یه عدد بین ۱ تا ۱۰۰ تو ذهنم گذاشتم! حدس بزن چنده (فقط عدد رو بفرست)."
        )
    elif data == "game_math_start":
        question = start_math_game(query.message.chat_id)
        await query.message.reply_text(f"➕ سریع باش: {question} = ?")
    elif data == "game_rps_menu":
        await query.message.reply_text("✊ یکی رو انتخاب کن:", reply_markup=rps_keyboard())
    elif data == "game_namefamily_start":
        letter = random.choice(PERSIAN_LETTERS)
        await query.message.reply_text(
            f"🎲 بازی اسم فامیل شروع شد!\nحرف امتحان: **{letter}**\n"
            "اسم، فامیل، شهر، حیوان، غذا، گل/میوه با این حرف بگید!\n⏱ ۶۰ ثانیه وقت دارید...",
            parse_mode="Markdown",
        )
        if context.job_queue:
            context.job_queue.run_once(
                namefamily_timeout,
                when=60,
                chat_id=query.message.chat_id,
                name=f"namefamily_{query.message.chat_id}",
            )
    elif data in ("rps_rock", "rps_paper", "rps_scissors"):
        result_text = play_rps(data)
        await query.message.reply_text(result_text)
    elif data == "game_dooz_start":
        game = start_dooz_game(query.message.chat_id, query.from_user, o_user=None)
        await query.message.reply_text(
            dooz_status_text(game), reply_markup=render_dooz_board(game["board"])
        )


# بررسی ادمین بودن کاربر در گروه
async def is_chat_admin(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ["creator", "administrator"]
    except Exception:
        return False


async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if update.message.chat.type == "private":
        return False
    return await is_chat_admin(update.message.chat_id, update.effective_user.id, context)


# دستور بن کردن (/ban)
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("❌ این دستور مخصوص ادمین‌های گروه است!")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ لطفا این دستور را روی پیام کاربر مورد نظر ریپلای کنید.")
        return
    target_user = update.message.reply_to_message.from_user
    try:
        await context.bot.ban_chat_member(update.message.chat_id, target_user.id)
        await update.message.reply_text(f"🔒 کاربر {target_user.first_name} با موفقیت بن شد.")
    except Exception:
        await update.message.reply_text("❌ خطایی در مسدود سازی رخ داد.")


# دستور سکوت (/mute)
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("❌ این دستور مخصوص ادمین‌هاست.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ روی پیام کاربر ریپلای کنید.")
        return
    target_user = update.message.reply_to_message.from_user
    muted_users.add(target_user.id)
    save_muted()
    await update.message.reply_text(f"🔇 کاربر {target_user.first_name} در حالت سکوت قرار گرفت.")


# دستور لغو سکوت (/unmute)
async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    if not update.message.reply_to_message:
        return
    target_user = update.message.reply_to_message.from_user
    if target_user.id in muted_users:
        muted_users.remove(target_user.id)
        save_muted()
        await update.message.reply_text(f"🔊 کاربر {target_user.first_name} مجدداً اجازه ارسال پیام دارد.")


# دستور اخطار (/warn)
async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context) or not update.message.reply_to_message:
        return
    target_user = update.message.reply_to_message.from_user
    user_id = target_user.id
    user_warnings[user_id] = user_warnings.get(user_id, 0) + 1
    save_warnings()

    if user_warnings[user_id] >= 3:
        try:
            await context.bot.ban_chat_member(update.message.chat_id, user_id)
            await update.message.reply_text(f"🔒 کاربر {target_user.first_name} به دلیل دریافت ۳ اخطار بن شد.")
            user_warnings[user_id] = 0
            save_warnings()
        except Exception:
            await update.message.reply_text("❌ خطا در بن کردن کاربر اخراجی.")
    else:
        await update.message.reply_text(
            f"⚠️ کاربر {target_user.first_name} یک اخطار دریافت کرد. اخطارها: {user_warnings[user_id]}/3"
        )


# دستور /settag - دادن لقب ویژه به یه کاربر (فقط ادمین)
async def settag_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("❌ این دستور مخصوص ادمین‌هاست.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ روی پیام کاربری که می‌خوای لقب بدی ریپلای کن.")
        return
    tag_text = " ".join(context.args).strip()
    if not tag_text:
        await update.message.reply_text(
            "❌ بعد از دستور لقب رو بنویس. مثلاً:\n`/settag مدیر ویژه`", parse_mode="Markdown"
        )
        return
    target_user = update.message.reply_to_message.from_user
    user_tags[target_user.id] = tag_text[:30]
    save_tags()
    await update.message.reply_text(f"🏷️ از الان لقب {target_user.first_name} شد: {tag_text[:30]}")


# دستور /removetag - حذف لقب یه کاربر (فقط ادمین)
async def removetag_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("❌ این دستور مخصوص ادمین‌هاست.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ روی پیام کاربر مورد نظر ریپلای کن.")
        return
    target_user = update.message.reply_to_message.from_user
    if target_user.id in user_tags:
        del user_tags[target_user.id]
        save_tags()
        await update.message.reply_text(f"🗑️ لقب {target_user.first_name} حذف شد.")
    else:
        await update.message.reply_text("❌ این کاربر لقبی نداشت.")


# دستور /learn - یاد دادن یه جواب ثابت به ربات (فقط ادمین)
async def learn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("❌ این دستور مخصوص ادمین‌هاست.")
        return
    full_text = update.message.text.partition(" ")[2]
    if "|" not in full_text:
        await update.message.reply_text(
            "❌ فرمت درست:\n`/learn عبارت کلیدی | جوابی که باید بدم`", parse_mode="Markdown"
        )
        return
    keyword, _, answer = full_text.partition("|")
    keyword = keyword.strip().lower()
    answer = answer.strip()
    if not keyword or not answer:
        await update.message.reply_text("❌ هم عبارت کلیدی هم جواب لازمه.")
        return
    learned_facts[keyword] = answer
    save_learned()
    await update.message.reply_text(f"✅ یاد گرفتم! هر وقت کسی بگه «{keyword}» این جواب رو می‌دم:\n{answer}")


# دستور /forget - فراموش کردن یه چیزی که قبلاً یاد گرفته بود (فقط ادمین)
async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("❌ این دستور مخصوص ادمین‌هاست.")
        return
    keyword = " ".join(context.args).strip().lower()
    if keyword in learned_facts:
        del learned_facts[keyword]
        save_learned()
        await update.message.reply_text(f"🗑️ یادمو در مورد «{keyword}» پاک کردم.")
    else:
        await update.message.reply_text("❌ چیزی با این عبارت یاد نگرفته بودم.")


# دستور /learned - لیست چیزایی که ربات یاد گرفته
async def learned_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not learned_facts:
        await update.message.reply_text("📭 هنوز هیچی یاد نگرفتم.")
        return
    keywords = "\n".join(f"🔸 {k}" for k in learned_facts)
    await update.message.reply_text(f"📚 چیزایی که یاد گرفتم:\n{keywords}")


# ---------- ضد اسپم و فحاشی ----------

# دستور /addbadword - اضافه کردن یه کلمه به لیست فیلتر (فقط ادمین)
async def addbadword_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("❌ این دستور مخصوص ادمین‌هاست.")
        return
    word = " ".join(context.args).strip().lower()
    if not word:
        await update.message.reply_text(
            "❌ بعد از دستور کلمه رو بنویس. مثلاً:\n`/addbadword کلمه`", parse_mode="Markdown"
        )
        return
    bad_words.add(word)
    save_badwords()
    await update.message.reply_text(f"✅ از این به بعد پیام‌های شامل «{word}» حذف می‌شن و اخطار می‌گیرن.")


# دستور /removebadword - حذف یه کلمه از لیست فیلتر (فقط ادمین)
async def removebadword_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("❌ این دستور مخصوص ادمین‌هاست.")
        return
    word = " ".join(context.args).strip().lower()
    if word in bad_words:
        bad_words.discard(word)
        save_badwords()
        await update.message.reply_text(f"🗑️ «{word}» از لیست فیلتر حذف شد.")
    else:
        await update.message.reply_text("❌ این کلمه توی لیست فیلتر نبود.")


# دستور /badwords - دیدن لیست کلمات فیلترشده (فقط ادمین)
async def badwords_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("❌ این دستور مخصوص ادمین‌هاست.")
        return
    if not bad_words:
        await update.message.reply_text("📭 لیست فیلتر فعلاً خالیه. با `/addbadword` کلمه اضافه کن.", parse_mode="Markdown")
        return
    await update.message.reply_text("🚫 کلمات فیلترشده:\n" + "\n".join(f"🔸 {w}" for w in bad_words))


# دستور /togglelinks - روشن/خاموش کردن فیلتر لینک برای غیرادمین‌ها (فقط ادمین)
async def togglelinks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global link_filter_enabled
    if not await is_admin(update, context):
        await update.message.reply_text("❌ این دستور مخصوص ادمین‌هاست.")
        return
    link_filter_enabled = not link_filter_enabled
    save_settings()
    state = "فعال ✅" if link_filter_enabled else "غیرفعال ❌"
    await update.message.reply_text(f"🔗 فیلتر لینک الان {state} شد.")


# خوش‌آمدگویی به عضو جدید گروه
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            continue  # خودِ ربات به گروه اضافه شده، نه یه عضو جدید
        name = get_display_name(member)
        try:
            reply_text = await ask_ai(
                f"یه عضو جدید به اسم {name} تازه به این گروه تلگرامی پیوست. خودمونی، گرم و کوتاه "
                "به گروه خوش‌آمد بگو و یه شوخی کوچیک و دوستانه بکن."
            )
        except Exception:
            reply_text = f"به گروه خوش اومدی {name} جون! 🎉"
        await update.message.reply_text(reply_text)


# پردازش دستور متنی هوش مصنوعی (/ai)
async def ai_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_prompt = " ".join(context.args)
    if not user_prompt:
        await update.message.reply_text(
            "❌ بعد از دستور یه چیزی بنویس. مثلاً:\n`/ai چطور پایتون یاد بگیرم؟`",
            parse_mode="Markdown",
        )
        return
    user_id = update.effective_user.id
    name = get_display_name(update.effective_user)
    history_ctx = get_history_context(user_id)
    sent_msg = await update.message.reply_text("🤔 صبر کن یه لحظه فکر کنم...")
    try:
        prompt = f"{history_ctx}کاربر به اسم {name} الان این رو پرسید/گفت:\n{user_prompt}"
        reply_text = await ask_ai(prompt)
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id, message_id=sent_msg.message_id, text=reply_text
        )
    except Exception as e:
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=sent_msg.message_id,
            text=f"❌ یه خطا خوردم تو گرفتن جواب از هوش مصنوعی.\n`{e}`",
            parse_mode="Markdown",
        )


# پردازش تصاویر فرستاده شده به ربات
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id in muted_users:
        try:
            await update.message.delete()
        except Exception:
            pass
        return

    photo_file = await update.message.photo[-1].get_file()
    file_path = f"/tmp/photo_{update.effective_user.id}_{uuid.uuid4().hex}.jpg"
    await photo_file.download_to_drive(file_path)

    sent_msg = await update.message.reply_text("👁️ بذار عکس رو نگاه کنم...")
    try:
        img = PIL.Image.open(file_path)
        caption = update.message.caption if update.message.caption else "این تصویر را تحلیل کن"
        reply_text = await generate_content_safe([caption, img])
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id, message_id=sent_msg.message_id, text=reply_text
        )
    except Exception as e:
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=sent_msg.message_id,
            text=f"❌ یه خطا خوردم تو پردازش عکس.\n`{e}`",
            parse_mode="Markdown",
        )
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


# پردازش پیام‌های متنی معمولی: سکوت، حافظه، بازی‌ها، یادگیری و سلام‌جواب‌دادن
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    text = (update.message.text or "").strip()

    # ۱. کاربران بی‌صدا شده
    if user_id in muted_users:
        try:
            await update.message.delete()
        except Exception:
            pass
        return

    # ۲. ضد اسپم: لینک مشکوک، کلمات فیلترشده، یا پیام‌های زیاد در زمان کوتاه (برای غیرادمین‌ها)
    if update.message.chat.type != "private" and not await is_chat_admin(chat_id, user_id, context):
        name = get_display_name(update.effective_user)

        if link_filter_enabled and URL_PATTERN.search(text):
            try:
                await update.message.delete()
            except Exception:
                pass
            await context.bot.send_message(chat_id, f"🚫 {name} جون، فرستادن لینک توی این گروه مجاز نیست.")
            return

        text_lower = text.lower()
        if any(bad in text_lower for bad in bad_words):
            try:
                await update.message.delete()
            except Exception:
                pass
            user_warnings[user_id] = user_warnings.get(user_id, 0) + 1
            save_warnings()
            await context.bot.send_message(
                chat_id,
                f"🚫 {name} این کلمه توی گروه مجاز نیست! اخطار گرفتی ({user_warnings[user_id]}/3)",
            )
            if user_warnings[user_id] >= 3:
                try:
                    await context.bot.ban_chat_member(chat_id, user_id)
                    await context.bot.send_message(chat_id, f"🔒 {name} به دلیل ۳ اخطار بن شد.")
                    user_warnings[user_id] = 0
                    save_warnings()
                except Exception:
                    pass
            return

        now = time.monotonic()
        timestamps = user_message_times.setdefault(user_id, deque(maxlen=SPAM_MESSAGE_THRESHOLD))
        timestamps.append(now)
        if len(timestamps) == SPAM_MESSAGE_THRESHOLD and (now - timestamps[0]) < SPAM_WINDOW_SECONDS:
            muted_users.add(user_id)
            save_muted()
            try:
                await update.message.delete()
            except Exception:
                pass
            await context.bot.send_message(
                chat_id,
                f"🔇 {name} به‌خاطر ارسال پیام زیاد در زمان کوتاه، موقتاً بی‌صدا شد. "
                "یه ادمین می‌تونه با /unmute (ریپلای) برش گردونه.",
            )
            return

    # ۳. ثبت پیام در حافظه‌ی کوتاه‌مدت (برای تحلیل بهتر در ادامه‌ی گفتگو)
    add_to_history(user_id, text)

    # ۴. اگه کاربر روی پیام خود ربات ریپلای کرده، یعنی می‌خواد باهاش چت/تحلیل کنه
    reply_to = update.message.reply_to_message
    if reply_to and reply_to.from_user and reply_to.from_user.id == context.bot.id and text:
        name = get_display_name(update.effective_user)
        tag = user_tags.get(user_id)
        tag_info = f" (لقبش: {tag})" if tag else ""
        history_ctx = get_history_context(user_id)
        sent_msg = await update.message.reply_text("🤔 صبر کن یه لحظه فکر کنم...")
        try:
            previous_bot_text = reply_to.text or reply_to.caption or ""
            prompt = (
                f"{history_ctx}"
                f"کاربر به اسم {name}{tag_info} داره باهات چت می‌کنه.\n"
                f"تو قبلاً این رو گفته بودی:\n«{previous_bot_text}»\n\n"
                f"کاربر روی همین پیام ریپلای کرد و نوشت:\n«{text}»\n\n"
                "خودمونی و طبیعی به این ادامه‌ی گفتگو جواب بده. اگه ازت خواست چیزی رو تحلیل کنی، "
                "تحلیل دقیق و مفید بده."
            )
            reply_text_ai = await ask_ai(prompt)
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=sent_msg.message_id, text=reply_text_ai
            )
        except Exception as e:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=sent_msg.message_id,
                text=f"❌ یه خطا خوردم.\n`{e}`",
                parse_mode="Markdown",
            )
        return

    # ۵. بازی حدس عدد فعاله؟
    if chat_id in active_guess_games and text.lstrip("-").isdigit():
        game = active_guess_games[chat_id]
        guess = int(text)
        game["attempts"] += 1
        if guess == game["number"]:
            await update.message.reply_text(
                f"🎉 درست گفتی! عدد {game['number']} بود. تو {game['attempts']} بار حدس زدی، دمت گرم!"
            )
            del active_guess_games[chat_id]
        elif guess < game["number"]:
            await update.message.reply_text("⬆️ بزرگ‌تره، بازم حدس بزن.")
        else:
            await update.message.reply_text("⬇️ کوچیک‌تره، بازم حدس بزن.")
        return

    # ۶. بازی ریاضی سریع فعاله؟
    if chat_id in active_math_games and text.lstrip("-").isdigit():
        game = active_math_games[chat_id]
        if int(text) == game["answer"]:
            await update.message.reply_text("✅ آره درسته! خیلی سریع بودی 👏")
            del active_math_games[chat_id]
        else:
            await update.message.reply_text("❌ نه، اشتباهه. دوباره امتحان کن.")
        return

    # ۷. چیزی هست که قبلاً یاد گرفتیم و به این پیام مربوطه؟
    learned_answer = find_learned_match(text)
    if learned_answer:
        await update.message.reply_text(learned_answer)
        return

    # ۸. تگ «ویکی» در ابتدای پیام: جستجوی خودکار در ویکی‌پدیا
    wiki_match = WIKI_TRIGGER_PATTERN.match(text)
    if wiki_match:
        await do_wiki_lookup(update, wiki_match.group(1).strip())
        return

    # ۹. سلام و خوش‌آمد با هوش مصنوعی (اسم رو خودکار از پروفایل تلگرام می‌فهمه)
    if is_greeting(text):
        name = get_display_name(update.effective_user)
        tag = user_tags.get(user_id)
        tag_info = f" (لقبش: {tag})" if tag else ""
        try:
            reply_text = await ask_ai(
                f"کاربری به اسم {name}{tag_info} سلام داد. خودمونی، گرم و کوتاه جواب سلام بده "
                "و اسمش رو هم صدا بزن، می‌تونی یه شوخی کوچیک هم بکنی."
            )
        except Exception:
            reply_text = f"سلام {name} جون! 👋"
        await update.message.reply_text(reply_text)


# تابع اصلی اجرای ربات
def main():
    print("🤖 ربات مدیریت گروه و هوش مصنوعی در حال روشن شدن است...")
    load_persisted_state()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ai", ai_mode))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(CommandHandler("nickname", nickname_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("tag", tag_command))
    app.add_handler(CommandHandler("settag", settag_command))
    app.add_handler(CommandHandler("removetag", removetag_command))
    app.add_handler(CommandHandler("learn", learn_command))
    app.add_handler(CommandHandler("forget", forget_command))
    app.add_handler(CommandHandler("learned", learned_command))
    app.add_handler(CommandHandler("addbadword", addbadword_command))
    app.add_handler(CommandHandler("removebadword", removebadword_command))
    app.add_handler(CommandHandler("badwords", badwords_command))
    app.add_handler(CommandHandler("togglelinks", togglelinks_command))
    app.add_handler(CommandHandler("hafez", hafez_command))
    app.add_handler(CommandHandler("wiki", wiki_command))
    app.add_handler(CommandHandler("today", today_command))
    app.add_handler(CommandHandler("countdown", countdown_command))
    app.add_handler(CommandHandler("price", price_command))
    app.add_handler(CommandHandler("game", game_menu))
    app.add_handler(CommandHandler("guess", guess_command))
    app.add_handler(CommandHandler("rps", rps_command))
    app.add_handler(CommandHandler("math", math_command))
    app.add_handler(CommandHandler("dooz", dooz_command))
    app.add_handler(CommandHandler("namefamily", namefamily_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ ربات بدون مشکل شبکه متصل شد! در حال شنیدن پیام‌ها... 🚀")

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

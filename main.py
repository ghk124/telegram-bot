import os
import re
import random
import uuid
from collections import deque
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

if not TOKEN:
    raise RuntimeError("متغیر محیطی TOKEN ست نشده! آن را در Railway > Variables اضافه کنید.")
if not GEMINI_KEY:
    raise RuntimeError("متغیر محیطی GEMINI_KEY ست نشده! آن را در Railway > Variables اضافه کنید.")

# تنظیمات هوش مصنوعی Gemini (SDK جدید google-genai)
client = genai.Client(api_key=GEMINI_KEY)
MODEL_NAME = "gemini-2.5-flash"

# شخصیت خودمونی و باحال ربات برای همه‌ی پاسخ‌های هوش مصنوعی
PERSONA = (
    "تو یه دستیار هوش مصنوعی خودمونی، باحال و دوست‌داشتنی برای یه گروه تلگرامی هستی. "
    "همیشه با لحن صمیمی، محاوره‌ای و فارسیِ روزمره جواب بده (نه رسمی و کتابی). "
    "گاهی شوخی و طعنه‌ی بامزه و دوستانه بزن، ولی هیچ‌وقت توهین یا بی‌ادبی نکن. "
    "اگه ازت خواستن چیزی رو تحلیل کنی، تحلیل دقیق، مفید و قابل فهم بده. "
    "اگه برات تاریخچه‌ی پیام‌های قبلی کاربر یا لقبش رو فرستادم، از این اطلاعات برای جواب طبیعی‌تر و شخصی‌تر استفاده کن. "
    "جواب‌هات رو کوتاه و خوندنی نگه دار مگه اینکه توضیح بیشتر لازم باشه."
)

GENERATE_CONFIG = types.GenerateContentConfig(system_instruction=PERSONA)

# --- دیتابیس ساده در حافظه (RAM) ---
# توجه: همه‌ی این دیتاها با ری‌استارت شدن ربات (مثلا روی Railway) از بین می‌رن.
user_warnings = {}
muted_users = set()
user_names = {}             # user_id -> نیک‌نیمی که خودش انتخاب کرده (اختیاری)
user_tags = {}               # user_id -> لقب/نشان ویژه‌ای که ادمین بهش داده (مثل VIP، مدیر)
active_guess_games = {}      # chat_id -> {"number": int, "attempts": int}
active_math_games = {}       # chat_id -> {"answer": int, "question": str}
user_message_history = {}    # user_id -> deque آخرین پیام‌ها (حافظه‌ی کوتاه‌مدت برای تحلیل)
learned_facts = {}           # کلیدواژه (lower) -> جوابی که ادمین یاد داده (بخش یادگیریِ فعال)

GREETING_WORDS = {
    "سلام", "سلامم", "سلامی", "های", "هلو", "درود", "سلام!", "سلام،",
    "hi", "hello", "hey", "salam",
}

HISTORY_LIMIT = 8


def ask_ai(prompt: str) -> str:
    """یک تابع کمکی برای صدا زدن Gemini با شخصیت خودمونی."""
    response = client.models.generate_content(
        model=MODEL_NAME, contents=prompt, config=GENERATE_CONFIG
    )
    return response.text


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
    "🔹 بعدش روی جواب‌های من ریپلای کن تا ادامه‌ی گفتگو یا تحلیل بگیری، لازم نیست هر بار `/ai` بنویسی\n"
    "🔹 یه سلام ساده هم بکنی، خودم جواب می‌دم 👋\n"
    "🔹 `/nickname <اسم>` - بگو با چه اسمی صدات کنم\n"
    "🔹 `/profile` - دیدن پروفایلت (یا ریپلای رو یکی دیگه)\n"
    "🔹 `/tag` - دیدن لقب ویژه (یا ریپلای رو یکی دیگه)\n\n"
    "🎮 **بازی‌ها:**\n"
    "🔸 `/game` - منوی بازی‌ها\n"
    "🔸 `/guess` - بازی حدس عدد\n"
    "🔸 `/rps` - سنگ کاغذ قیچی\n"
    "🔸 `/math` - ریاضی سریع\n\n"
    "👮‍♂️ **دستورات مدیریتی:**\n"
    "🔸 `/ban` - مسدود کردن کاربر (ریپلای)\n"
    "🔸 `/mute` - سکوت کاربر (ریپلای)\n"
    "🔸 `/unmute` - لغو سکوت (ریپلای)\n"
    "🔸 `/warn` - دادن اخطار (ریپلای)\n"
    "🔸 `/settag <متن>` - دادن لقب ویژه به کاربر (ریپلای) مثل VIP یا مدیر\n"
    "🔸 `/removetag` - حذف لقب کاربر (ریپلای)\n"
    "🔸 `/learn کلیدواژه | جواب` - یاد دادن یه جواب ثابت به ربات\n"
    "🔸 `/forget کلیدواژه` - فراموش کردن یه چیزی که یاد داده بودی\n"
    "🔸 `/learned` - لیست چیزایی که ربات تا الان یاد گرفته"
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
    try:
        reply_text = ask_ai(
            f"کاربر گفت از این به بعد باهاش با اسم «{nickname[:30]}» صحبت کنیم. "
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


# هندلر دکمه‌های شیشه‌ای (Inline Keyboard)
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

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
    elif data in ("rps_rock", "rps_paper", "rps_scissors"):
        result_text = play_rps(data)
        await query.message.reply_text(result_text)


# بررسی ادمین بودن کاربر در گروه
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if update.message.chat.type == "private":
        return False
    member = await context.bot.get_chat_member(update.message.chat_id, update.effective_user.id)
    return member.status in ["creator", "administrator"]


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
        await update.message.reply_text(f"🔊 کاربر {target_user.first_name} مجدداً اجازه ارسال پیام دارد.")


# دستور اخطار (/warn)
async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context) or not update.message.reply_to_message:
        return
    target_user = update.message.reply_to_message.from_user
    user_id = target_user.id
    user_warnings[user_id] = user_warnings.get(user_id, 0) + 1

    if user_warnings[user_id] >= 3:
        try:
            await context.bot.ban_chat_member(update.message.chat_id, user_id)
            await update.message.reply_text(f"🔒 کاربر {target_user.first_name} به دلیل دریافت ۳ اخطار بن شد.")
            user_warnings[user_id] = 0
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
    await update.message.reply_text(f"✅ یاد گرفتم! هر وقت کسی بگه «{keyword}» این جواب رو می‌دم:\n{answer}")


# دستور /forget - فراموش کردن یه چیزی که قبلاً یاد گرفته بود (فقط ادمین)
async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("❌ این دستور مخصوص ادمین‌هاست.")
        return
    keyword = " ".join(context.args).strip().lower()
    if keyword in learned_facts:
        del learned_facts[keyword]
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
        reply_text = ask_ai(prompt)
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
        response = client.models.generate_content(
            model=MODEL_NAME, contents=[caption, img], config=GENERATE_CONFIG
        )
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id, message_id=sent_msg.message_id, text=response.text
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

    # ۲. ثبت پیام در حافظه‌ی کوتاه‌مدت (برای تحلیل بهتر در ادامه‌ی گفتگو)
    add_to_history(user_id, text)

    # ۳. اگه کاربر روی پیام خود ربات ریپلای کرده، یعنی می‌خواد باهاش چت/تحلیل کنه
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
            reply_text_ai = ask_ai(prompt)
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

    # ۴. بازی حدس عدد فعاله؟
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

    # ۵. بازی ریاضی سریع فعاله؟
    if chat_id in active_math_games and text.lstrip("-").isdigit():
        game = active_math_games[chat_id]
        if int(text) == game["answer"]:
            await update.message.reply_text("✅ آره درسته! خیلی سریع بودی 👏")
            del active_math_games[chat_id]
        else:
            await update.message.reply_text("❌ نه، اشتباهه. دوباره امتحان کن.")
        return

    # ۶. چیزی هست که قبلاً یاد گرفتیم و به این پیام مربوطه؟
    learned_answer = find_learned_match(text)
    if learned_answer:
        await update.message.reply_text(learned_answer)
        return

    # ۷. سلام و خوش‌آمد با هوش مصنوعی (اسم رو خودکار از پروفایل تلگرام می‌فهمه)
    if is_greeting(text):
        name = get_display_name(update.effective_user)
        tag = user_tags.get(user_id)
        tag_info = f" (لقبش: {tag})" if tag else ""
        try:
            reply_text = ask_ai(
                f"کاربری به اسم {name}{tag_info} سلام داد. خودمونی، گرم و کوتاه جواب سلام بده "
                "و اسمش رو هم صدا بزن، می‌تونی یه شوخی کوچیک هم بکنی."
            )
        except Exception:
            reply_text = f"سلام {name} جون! 👋"
        await update.message.reply_text(reply_text)


# تابع اصلی اجرای ربات
def main():
    print("🤖 ربات مدیریت گروه و هوش مصنوعی در حال روشن شدن است...")

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
    app.add_handler(CommandHandler("game", game_menu))
    app.add_handler(CommandHandler("guess", guess_command))
    app.add_handler(CommandHandler("rps", rps_command))
    app.add_handler(CommandHandler("math", math_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ ربات بدون مشکل شبکه متصل شد! در حال شنیدن پیام‌ها... 🚀")

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

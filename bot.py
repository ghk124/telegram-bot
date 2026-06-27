"""
ربات حرفه‌ای بامزه فارسی
با قابلیت Gemini AI، آنالیز عکس و مدیریت گروه
"""

import logging
import random
import os
import google.generativeai as genai
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ====================================================
# 🔴 تنظیمات توکن‌ها (مستقیم یا از طریق سرور)
# ====================================================
TOKEN = os.environ.get("TOKEN") or "توکن_تلگرام_تو"
GEMINI_KEY = os.environ.get("GEMINI_KEY") or "توکن_جمینای_تو"

# تنظیم Gemini
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

logging.basicConfig(level=logging.INFO)

# ========================
# دیتابیس جوک‌ها و پیام‌ها
# ========================
JOKES = [
    "یه نفر رفت دکتر گفت: دکتر همه بهم میگن دروغگو!\nدکتر گفت: باور نمیکنم 😂",
    "چرا برنامه‌نویس‌ها عینک میزنن؟ چون C# میزنن! 🤓",
    "یه بادمجون رفت دکتر گفت: دکتر همه بهم میگن بادمجون!\nدکتر گفت: خب بادمجون! 😅",
    "به استاد گفتم نمره‌ام رو بده!\nگفت: داری!\nگفتم: چند؟\nگفت: داری... داری تجدید میشی 😭",
    "چرا دریا شوره؟ چون ماهی‌ها توش عرق میکنن! 🐟",
]

GREET_REPLIES = [
    "سلام عزیزم! چطوری؟ 😁",
    "اوه اوه کی اومد! سلام 👋",
    "یا علی! سلام داداش 😄",
]

# ========================
# منوها
# ========================
def main_menu():
    keyboard = [
        [KeyboardButton("😂 جوک"), KeyboardButton("🎮 بازی‌ها")],
        [KeyboardButton("🎲 تاس"), KeyboardButton("🪙 شیر یا خط")],
        [KeyboardButton("📊 آمار من"), KeyboardButton("📋 راهنما")],
        [KeyboardButton("🔮 فال"), KeyboardButton("🤖 چت با AI")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def games_menu():
    keyboard = [
        [KeyboardButton("🔢 بازی عدد"), KeyboardButton("✂️ سنگ کاغذ قیچی")],
        [KeyboardButton("🧠 معما"), KeyboardButton("🔤 کلمه بازی")],
        [KeyboardButton("🏠 برگشت به منو")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# ========================
# دستورات اصلی
# ========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = user.first_name or "دوست"
    context.user_data["message_count"] = 0
    context.user_data["game"] = None
    context.user_data["ai_mode"] = False

    await update.message.reply_text(
        f"سلام {name}! 👋\n\n"
        "من ربات بامزه + هوش مصنوعی جمینای هستم 🤖✨\n"
        "میتونی باهام حرف بزنی، بازی کنی، یا عکس بفرستی تا آنالیز کنم!\n\n"
        "از منوی پایین شروع کن 👇",
        reply_markup=main_menu()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📋 *راهنمای کامل ربات*\n\n"
        "🤖 *هوش مصنوعی*\n"
        "/ai — روشن/خاموش کردن AI\n"
        "🖼️ عکس بفرست — آنالیز میکنم!\n\n"
        "😂 *جوک و سرگرمی*\n"
        "/joke — جوک تصادفی\n"
        "/flip — شیر یا خط\n"
        "/roll — تاس بنداز\n"
        "/fal — فال بگیر\n\n"
        "🎮 *بازی‌ها*\n"
        "/guess — حدس عدد\n"
        "/rps — سنگ کاغذ قیچی\n"
        "/riddle — معما\n\n"
        "👮 *مدیریت گپ (ادمین)*\n"
        "/ban /mute /unmute /warn\n\n"
        "یا فقط باهام حرف بزن! 😄"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown", reply_markup=main_menu())

async def ai_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current = context.user_data.get("ai_mode", False)
    context.user_data["ai_mode"] = not current

    if not current:
        await update.message.reply_text("🤖 حالت AI روشن شد!\nالان هر چی بنویسی Gemini جواب میده 😄\nبرای خاموش کردن /ai بزن")
    else:
        await update.message.reply_text("🔴 حالت AI خاموش شد!", reply_markup=main_menu())


# ========================
# بخش هوش مصنوعی (Gemini)
# ========================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 دارم عکست رو آنالیز میکنم...")
    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        file_bytes = await file.download_as_bytearray()

        import PIL.Image
        import io
        img = PIL.Image.open(io.BytesIO(file_bytes))

        caption = update.message.caption or "این عکس رو برام توضیح بده به فارسی"
        response = model.generate_content([caption, img])
        await update.message.reply_text(f"🖼️ *آنالیز عکس:*\n\n{response.text}", parse_mode="Markdown")
    except Exception:
        await update.message.reply_text("😅 نتونستم عکس رو آنالیز کنم! دوباره امتحان کن.")

async def chat_with_gemini(update: Update, text: str):
    try:
        prompt = f"تو یه ربات تلگرام بامزه فارسی هستی. پاسخ کوتاه، دوستانه و همراه با ایموجی بده. پیام کاربر: {text}"
        response = model.generate_content(prompt)
        return response.text
    except Exception:
        return "😅 یه مشکلی توی ارتباط با جمینای پیش اومد!"


# ========================
# سرگرمی‌ها و بازی‌ها
# ========================
async def joke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(random.choice(JOKES))

async def flip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(random.choice(["🪙 شیر!", "🪙 خط!"]))

async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    num = random.randint(1, 6)
    faces = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]
    await update.message.reply_text(f"🎲 تاس انداختم: {faces[num-1]}")

async def fal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fals = ["🔮 امروز یه خبر خوب میشنوی!", "🔮 یکی داره بهت فکر میکنه 😏", "🔮 این هفته پول بهت میرسه 💰"]
    await update.message.reply_text(random.choice(fals))

async def guess_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["game"] = "guess"
    context.user_data["guess_number"] = random.randint(1, 100)
    context.user_data["guess_tries"] = 0
    await update.message.reply_text("🔢 یه عدد بین ۱ تا ۱۰۰ انتخاب کردم! حدس بزن 🤔")

async def rps_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["game"] = "rps"
    await update.message.reply_text("✂️ انتخاب کن:\n🪨 سنگ\n📄 کاغذ\n✂️ قیچی")

async def riddle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    riddles = [("هر چی بیشتر ازش بگیری بزرگتر میشه. چیه؟", "گودال"), ("دندون داره ولی نمیتونه بخوره. چیه؟", "شانه")]
    r = random.choice(riddles)
    context.user_data["game"] = "riddle"
    context.user_data["riddle_answer"] = r[1]
    await update.message.reply_text(f"🧠 *معما:*\n\n{r[0]}\n\nجواب بده! (یا بنویس: جواب)", parse_mode="Markdown")


# ========================
# ناظمی و ادمین گروه
# ========================
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if update.effective_chat.type == "private": return True
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    return member.status in ["administrator", "creator"]

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if not update.message.reply_to_message: return
    user = update.message.reply_to_message.from_user
    try:
        await update.effective_chat.ban_member(user.id)
        await update.message.reply_text(f"🔨 {user.first_name} بن شد!")
    except Exception: pass

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if not update.message.reply_to_message: return
    user = update.message.reply_to_message.from_user
    try:
        await update.effective_chat.restrict_member(user.id, ChatPermissions(can_send_messages=False))
        await update.message.reply_text(f"🔇 {user.first_name} میوت شد!")
    except Exception: pass

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if not update.message.reply_to_message: return
    user = update.message.reply_to_message.from_user
    try:
        await update.effective_chat.restrict_member(user.id, ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True))
        await update.message.reply_text(f"🔊 {user.first_name} آنمیوت شد!")
    except Exception: pass

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if not update.message.reply_to_message: return
    user = update.message.reply_to_message.from_user
    warns = context.bot_data.get(f"warn_{user.id}", 0) + 1
    context.bot_data[f"warn_{user.id}"] = warns
    if warns >= 3:
        try:
            await update.effective_chat.ban_member(user.id)
            context.bot_data[f"warn_{user.id}"] = 0
            await update.message.reply_text(f"🚫 {user.first_name} بن شد (اخطار ۳/۳)!")
        except Exception: pass
    else:
        await update.message.reply_text(f"⚠️ {user.first_name} اخطار {warns}/3!")


# ========================
# لوپ و پردازش بازی‌ها
# ========================
async def process_game(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    game = context.user_data.get("game")
    if not game: return False

    if game == "guess" and text.isdigit():
        num = int(text)
        target = context.user_data["guess_number"]
        context.user_data["guess_tries"] += 1
        if num == target:
            context.user_data["game"] = None
            context.user_data["wins"] = context.user_data.get("wins", 0) + 1
            await update.message.reply_text(f"🎉 آفرین! {target} بود! برد شما ثبت شد 🏆")
        elif num < target: await update.message.reply_text("⬆️ بزرگتر!")
        else: await update.message.reply_text("⬇️ کوچیکتر!")
        return True

    elif game == "rps":
        choices = {"سنگ": "🪨", "کاغذ": "📄", "قیچی": "✂️"}
        wins = {"سنگ": "قیچی", "کاغذ": "سنگ", "قیچی": "کاغذ"}
        user_choice = next((k for k in choices if k in text), None)
        if user_choice:
            bot_choice = random.choice(["سنگ", "کاغذ", "قیچی"])
            if user_choice == bot_choice: result = "مساوی! 🤝"
            elif wins[user_choice] == bot_choice:
                result = "بردی! 🏆"
                context.user_data["wins"] = context.user_data.get("wins", 0) + 1
            else: result = "باختی! 😂"
            context.user_data["game"] = None
            await update.message.reply_text(f"تو: {choices[user_choice]}\nمن: {choices[bot_choice]}\n\n{result}")
            return True

    elif game == "riddle":
        ans = context.user_data.get("riddle_answer", "")
        if "جواب" in text:
            context.user_data["game"] = None
            await update.message.reply_text(f"جواب: {ans} 🧠")
            return True
        elif ans in text:
            context.user_data["game"] = None
            context.user_data["wins"] = context.user_data.get("wins", 0) + 1
            await update.message.reply_text(f"🎉 آفرین درست بود! جواب: {ans}")
            return True
    return False


# ========================
# متن‌ها و منوی اصلی
# ========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text: return
    text_lower = text.lower()

    if text == "🏠 برگشت به منو":
        context.user_data["game"] = None
        await update.message.reply_text("برگشتیم! 😄", reply_markup=main_menu())
        return

    if await process_game(update, context, text_lower): return

    if context.user_data.get("ai_mode"):
        reply = await chat_with_gemini(update, text)
        await update.message.reply_text(reply)
        return

    if text == "😂 جوک": await joke(update, context)
    elif text == "🎲 تاس": await roll(update, context)
    elif text == "🪙 شیر یا خط": await flip(update, context)
    elif text == "🔮 فال": await fal(update, context)
    elif text == "🤖 چت با AI":
        context.user_data["ai_mode"] = True
        await update.message.reply_text("🤖 حالت AI روشن شد! بنویس تا Gemini جوابت رو بده.")
    elif text == "🎮 بازی‌ها": await update.message.reply_text("کدوم بازی؟ 🎮", reply_markup=games_menu())
    elif text == "🔢 بازی عدد": await guess_game(update, context)
    elif text == "✂️ سنگ کاغذ قیچی": await rps_game(update, context)
    elif text == "🧠 معما": await riddle(update, context)
    elif any(g in text_lower for g in ["سلام", "درود", "hi", "hello"]):
        await update.message.reply_text(random.choice(GREET_REPLIES))
    elif random.random() < 0.15:
        reply = await chat_with_gemini(update, text)
        await update.message.reply_text(reply)

# ========================
# رانر اصلی
# ========================
def main():
    print("🤖 ربات با هوش مصنوعی Gemini در حال روشن شدن است...")
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ai", ai_mode))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ آماده‌ست! 🚀")
    app.run_polling()

if __name__ == "__main__":
    main()

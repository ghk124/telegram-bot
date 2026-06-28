import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai

# دریافت توکن‌ها از بخش Variables در Railway
TOKEN = os.getenv("TOKEN")
GEMINI_KEY = os.getenv("GEMINI_KEY")

# تنظیمات هوش مصنوعی Gemini
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# دیتابیس ساده در حافظه برای مدیریت گروه
user_warnings = {}
muted_users = set()

# دستور /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🤖 بخش هوش مصنوعی", callback_data='ai_mode')],
        [InlineKeyboardButton("📜 راهنمای دستورات", callback_data='help_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"سلام {update.effective_user.first_name} عزیز! به ربات مدیریت گروه و هوش مصنوعی خوش آمدی.\n"
        "یک گزینه را انتخاب کن:",
        reply_markup=reply_markup
    )

# دستور /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📜 **دستورات ربات:**\n\n"
        "🔹 `/start` - شروع ربات و منو\n"
        "🔹 `/help` - نمایش این راهنما\n"
        "🔹 `/ai <متن>` - صحبت مستقیم با هوش مصنوعی\n\n"
        "👮‍♂️ **دستورات مدیریتی:**\n"
        "🔸 `/ban` - مسدود کردن کاربر (ریپلای)\n"
        "🔸 `/mute` - سکوت کاربر (ریپلای)\n"
        "🔸 `/unmute` - لغو سکوت (ریپلای)\n"
        "🔸 `/warn` - دادن اخطار (ریپلای)"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

# بررسی ادمین بودن کاربر در گروه
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if update.message.chat.type == "private":
        return False
    member = await context.bot.get_chat_member(update.message.chat_id, update.effective_user.id)
    return member.status in ['creator', 'administrator']

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
        await update.message.reply_text(f"⚠️ کاربر {target_user.first_name} یک اخطار دریافت کرد. اخطارها: {user_warnings[user_id]}/3")

# پردازش دستور متنی هوش مصنوعی (/ai)
async def ai_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_prompt = " ".join(context.args)
    if not user_prompt:
        await update.message.reply_text("❌ لطفاً پیام خود را بعد از دستور وارد کنید. مثال:\n`/ai چطور پایتون یاد بگیرم؟`")
        return
    sent_msg = await update.message.reply_text("🤔 در حال پردازش توسط Gemini...")
    try:
        response = model.generate_content(user_prompt)
        await context.bot.edit_message_text(chat_id=update.message.chat_id, message_id=sent_msg.message_id, text=response.text)
    except Exception:
        await context.bot.edit_message_text(chat_id=update.message.chat_id, message_id=sent_msg.message_id, text="❌ خطایی در دریافت پاسخ از هوش مصنوعی رخ داد.")

# پردازش تصاویر فرستاده شده به ربات
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id in muted_users:
        await update.message.delete()
        return
    photo_file = await update.message.photo[-1].get_file()
    await photo_file.download_to_drive("user_photo.jpg")
    sent_msg = await update.message.reply_text("👁️ در حال تحلیل عکس توسط هوش مصنوعی...")
    try:
        import PIL.Image
        img = PIL.Image.open("user_photo.jpg")
        caption = update.message.caption if update.message.caption else "این تصویر را تحلیل کن"
        response = model.generate_content([caption, img])
        await context.bot.edit_message_text(chat_id=update.message.chat_id, message_id=sent_msg.message_id, text=response.text)
    except Exception:
        await context.bot.edit_message_text(chat_id=update.message.chat_id, message_id=sent_msg.message_id, text="❌ خطایی در پردازش تصویر پیش آمد.")

# فیلتر پیام‌های کاربران بیصدا شده
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id in muted_users:
        try:
            await update.message.delete()
        except Exception:
            pass

# تابع اصلی اجرای ربات
def main():
    print("🤖 ربات مدیریت گروه و هوش مصنوعی در حال روشن شدن است...")
    
    app = Application.builder().token(TOKEN).build()
    
    # ثبت هندلرهای ربات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ai", ai_mode))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ ربات بدون مشکل شبکه متصل شد! در حال شنیدن پیام‌ها... 🚀")
    
    # اجرای مستقیم و پایدار پولینگ در ریلووی
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

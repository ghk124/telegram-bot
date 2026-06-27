"""
🤖 ربات فارسی حرفه‌ای
با حافظه، OpenAI، ماریوی دونفره، جدول امتیازات
"""

import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

from ai_engine import AIEngine
from game_mario import MarioGame, MarioLobby
from user_db import UserDatabase

# Load .env
load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize
ai_engine = AIEngine(OPENAI_KEY)
mario_lobby = MarioLobby()
user_db = UserDatabase()

# States
WAITING_FOR_INPUT = 1

class TelegramBot:
    def __init__(self):
        self.app = None
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command"""
        user = update.effective_user
        user_db.create_user(user.id, user.first_name)
        
        await update.message.reply_text(
            f"👋 سلام {user.first_name}!\n\n"
            "🤖 من ربات هوشمند فارسی هستم\n\n"
            "✨ قابلیت‌های من:\n"
            "🧠 AI با OpenAI (حافظه دارم!)\n"
            "🍄 ماریوی دونفره با لابی\n"
            "🏆 جدول امتیازات\n"
            "💬 یادآوری مکالمات قبل\n"
            "👮 مدیریت گروه\n\n"
            "دستورات: /help",
            reply_markup=self.main_menu()
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Help"""
        help_text = (
            "📋 *دستورات*\n\n"
            "🤖 *AI*\n"
            "/chat - حرف زدن با AI\n"
            "/memory - نمایش حافظه\n\n"
            "🍄 *ماریو دونفره*\n"
            "/mario_create - ساخت لابی\n"
            "/mario_join [کد] - وارد شدن\n"
            "/leaderboard - جدول امتیازات\n\n"
            "👮 *مدیریت*\n"
            "/ban - بن کردن\n"
            "/stats - آماری\n"
        )
        await update.message.reply_text(help_text, parse_mode="Markdown", reply_markup=self.main_menu())
    
    async def chat_ai(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Chat with AI"""
        if not context.args:
            context.user_data["ai_mode"] = True
            await update.message.reply_text(
                "🤖 حالت AI فعال!\n"
                "هر چی بنویسی، من هوشمندانه جواب میدم 😊\n"
                "/stopchat برای خاموش"
            )
        else:
            text = " ".join(context.args)
            user_id = update.effective_user.id
            
            # AI جواب
            response = ai_engine.get_response(user_id, text)
            await update.message.reply_text(response)
    
    async def memory_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show memory"""
        user_id = update.effective_user.id
        memory = ai_engine.get_user_memory(user_id)
        
        if memory:
            text = "📚 *حافظه شما:*\n\n"
            for msg in memory[:10]:
                text += f"• {msg[:50]}...\n"
        else:
            text = "📚 حافظه خالی است"
        
        await update.message.reply_text(text, parse_mode="Markdown")
    
    async def mario_create(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Create mario lobby"""
        user = update.effective_user
        lobby_code = mario_lobby.create_lobby(user.id, user.first_name)
        
        await update.message.reply_text(
            f"🍄 لابی ساخته شد!\n\n"
            f"💻 کد: `{lobby_code}`\n\n"
            f"دوستت بنویسه:\n"
            f"`/mario_join {lobby_code}`\n\n"
            f"۶۰ ثانیه منتظریم...",
            parse_mode="Markdown"
        )
    
    async def mario_join(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Join mario lobby"""
        if not context.args:
            await update.message.reply_text("کد لابی رو بنویس!\n/mario_join 123456")
            return
        
        code = context.args[0]
        user = update.effective_user
        
        result = mario_lobby.join_lobby(code, user.id, user.first_name)
        
        if result == "joined_waiting":
            await update.message.reply_text("✅ وارد شدی! منتظر دوستت 🎮")
            # اطلاع به دوست
            owner_id = mario_lobby.get_lobby_owner(code)
            if owner_id:
                await context.bot.send_message(
                    owner_id, 
                    f"✅ {user.first_name} وارد شد!\n\nشروع: /mario_start"
                )
        elif result == "both_ready":
            await update.message.reply_text("🎮 بازی شروع می‌شه!")
        else:
            await update.message.reply_text(f"❌ {result}")
    
    async def mario_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start mario game"""
        user_id = update.effective_user.id
        lobby_code = mario_lobby.get_user_lobby(user_id)
        
        if not lobby_code:
            await update.message.reply_text("لابی پیدا نشد!")
            return
        
        game = MarioGame(lobby_code)
        context.user_data["mario_game"] = game
        context.user_data["game_mode"] = "mario"
        
        await update.message.reply_text(
            f"🍄 *ماریو شروع شد!*\n\n{game.render()}\n\n"
            "⬆️ پرش | ⬅️ چپ | ➡️ راست",
            parse_mode="Markdown"
        )
    
    async def leaderboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show leaderboard"""
        scores = user_db.get_leaderboard(limit=10)
        
        text = "🏆 *جدول امتیازات*\n\n"
        for idx, (name, score) in enumerate(scores, 1):
            text += f"{idx}. {name} - {score} 🎯\n"
        
        await update.message.reply_text(text, parse_mode="Markdown")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle messages"""
        text = update.message.text
        user = update.effective_user
        
        # AI mode
        if context.user_data.get("ai_mode"):
            if text == "/stopchat":
                context.user_data["ai_mode"] = False
                await update.message.reply_text("✅ خاموش شد", reply_markup=self.main_menu())
                return
            
            response = ai_engine.get_response(user.id, text)
            await update.message.reply_text(response)
        
        # Mario game
        elif context.user_data.get("game_mode") == "mario":
            game = context.user_data.get("mario_game")
            if not game:
                return
            
            direction = None
            if "راست" in text or "→" in text:
                direction = "right"
            elif "چپ" in text or "←" in text:
                direction = "left"
            elif "پرش" in text or "⬆️" in text:
                direction = "up"
            
            if direction:
                result = game.move(user.id, direction)
                await update.message.reply_text(f"🍄\n{result}")
        
        # Menu
        else:
            if text == "🤖 AI":
                await self.chat_ai(update, context)
            elif text == "🍄 ماریو":
                await update.message.reply_text(
                    "🍄 انتخاب کن:\n"
                    "🔴 /mario_create - ساخت لابی\n"
                    "🟢 /mario_join [کد] - وارد شدن"
                )
            elif text == "🏆 امتیازات":
                await self.leaderboard(update, context)
            elif text == "📋 کمک":
                await self.help_command(update, context)
            else:
                # Default AI response
                response = ai_engine.get_response(user.id, text)
                await update.message.reply_text(response)
    
    def main_menu(self):
        keyboard = [
            [KeyboardButton("🤖 AI"), KeyboardButton("🍄 ماریو")],
            [KeyboardButton("🏆 امتیازات"), KeyboardButton("📋 کمک")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    def run(self):
        """Run bot"""
        self.app = Application.builder().token(TOKEN).build()
        
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("chat", self.chat_ai))
        self.app.add_handler(CommandHandler("memory", self.memory_command))
        self.app.add_handler(CommandHandler("mario_create", self.mario_create))
        self.app.add_handler(CommandHandler("mario_join", self.mario_join))
        self.app.add_handler(CommandHandler("mario_start", self.mario_start))
        self.app.add_handler(CommandHandler("leaderboard", self.leaderboard))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        logger.info("🤖 ربات شروع شد...")
        self.app.run_polling()

if __name__ == "__main__":
    bot = TelegramBot()
    bot.run()

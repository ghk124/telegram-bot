# 🤖 **ربات فارسی حرفه‌ای**

ربات تلگرام پیشرفته با **AI هوشمند**، **حافظه ۱۰۰۰ کلمه‌ای**، **ماریوی دونفره** و **جدول امتیازات**.

---

## ✨ **قابلیت‌ها**

### 🧠 **AI هوشمند**
- OpenAI GPT-3.5 Turbo
- حافظه ۱۰۰۰ کلمه‌ای برای هر کاربر
- پاسخ‌های طبیعی و منطقی
- یادآوری مکالمات قبلی

### 🍄 **بازی ماریو دونفره**
- سیستم لابی (lobby)
- ۶ رقمی کد برای دعوت
- نقشه تعاملی
- دشمنان و سکه‌ها
- جان و امتیاز

### 🏆 **جدول امتیازات**
- درجه‌بندی اصلی
- بخش ماریو
- پیگیری برد/حساب

### 👮 **مدیریت گروه**
- کنترل کاربران
- آمار گروه
- مدیریت دسترسی

---

## 📋 **دستورات**

### AI
```
/chat [متن]       - حرف زدن با AI
/memory           - نمایش حافظه
/stopchat         - خاموش کردن AI
```

### بازی
```
/mario_create     - ساخت لابی
/mario_join [کد]  - وارد شدن لابی
/mario_start      - شروع بازی
/leaderboard      - جدول امتیازات
```

### عمومی
```
/start            - شروع
/help             - راهنما
/stats            - آمار من
```

---

## 🚀 **راه اندازی**

### **محلی (Development)**

```bash
# Clone
git clone https://github.com/USERNAME/telegram-bot
cd telegram-bot

# Virtual env
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Install
pip install -r requirements.txt

# Setup .env
cp .env.example .env
# ویرایش کن و token/keys بذار

# Run
python main.py
```

### **Railway (Production)**

👉 **دقیق‌ترین راه:** `RAILWAY_SETUP.md` رو بخون

**خلاصه:**
1. GitHub ریپو بساز
2. Railway.app میں login کن
3. GitHub ریپو کو connect کن
4. Variables رو add کن (TELEGRAM_TOKEN, OPENAI_API_KEY)
5. Deploy!

---

## 🔧 **معماری**

```
main.py           ← نقطه ورودی
├── ai_engine.py      (موتور AI + حافظه)
├── game_mario.py     (ماریو + لابی)
├── user_db.py        (دیتابیس JSON)
└── requirements.txt  (پکیج‌ها)
```

---

## 💾 **ذخیره‌سازی**

### Database
```json
users_data.json
{
  "123456": {
    "id": 123456,
    "name": "احمد",
    "score": 500,
    "wins": 5,
    "stats": {...}
  }
}
```

### Memory (RAM)
- حافظه AI برای ۱۰۰۰ کلمه
- Lobbies و Games
- User sessions

---

## 🎮 **راهنمای بازی**

### شروع
```
Player1: /mario_create
Bot: "کد: 123456"

Player2: /mario_join 123456
Bot: "وارد شدی"

Player1: /mario_start
Both: بازی شروع!
```

### بازی
```
⬆️ پرش
⬅️ چپ
➡️ راست

🍄 تو
👾 دشمن
🪙 سکه
🏰 هدف
```

### نقاط
```
🪙 سکه: +10
🏰 هدف: +100
💀 دشمن: -50
❤️ جان: 3
```

---

## 🧠 **موتور AI**

### چطور کار می‌کنه

```python
1. کاربر: "سلام!"
   ↓
2. AI: "حافظه شو چک کنم..."
   ↓
3. AI: "OpenAI رو کال کنم..."
   ↓
4. OpenAI: "سلام! چطوری؟"
   ↓
5. Bot: "سلام! چطوری؟"
   ↓
6. حافظه: "سلام! → سلام! چطوری؟" (ذخیره)
```

### حافظه
- **حداکثر:** ۱۰۰۰ کلمه
- **پاک شدن:** خودکار اگر تجاوز کردند
- **بقا:** تا زمان شروع برنامه

---

## 💰 **هزینه‌ها**

### Railway
- **رایگان:** ۵۰۰ ساعت ماهانه
- **Paid:** $5-20/month

### OpenAI
- **رایگان:** $5 اول
- **Usage:** ~$0.002 per message

### Telegram Bot
- **رایگان:** کاملاً رایگان!

**ماهانه تقریباً: $0-10**

---

## 🔒 **Security**

```
✅ DO:
   - Token رو .env میں بذار
   - Variables در Railway
   - .gitignore: .env
   - HTTPS فقط
   - Rate limiting

❌ DON'T:
   - Token در GitHub
   - plaintext passwords
   - شماره تلفن log کردن
   - عمومی database
```

---

## 📊 **بهینه‌سازی**

### Performance
- Async/await برای سرعت
- Caching برای حافظه
- Database cleanup

### Reliability
- Try-except handling
- Retry logic برای API
- Health checks

### Scalability
- Multi-user support
- Database persistence
- Load distribution

---

## 🐛 **Debugging**

### Logs
```bash
# Real-time
tail -f logs.txt

# Railway
Railway Dashboard → Logs
```

### Common Issues
```
❌ "No module named telegram"
✅ pip install python-telegram-bot

❌ "Invalid token"
✅ Railway Variables رو چک کن

❌ "OpenAI error"
✅ API key صحیح؟ / Credit؟

❌ "User not found"
✅ DB cleanup کن
```

---

## 🔄 **Updates**

### جدید کردن
```bash
git pull origin main
pip install -r requirements.txt
# Railway: خود کار!
```

### Backup
```bash
# Database backup
cp users_data.json users_data.backup.json
```

---

## 📞 **پشتیبانی**

### مشکل دارید؟
1. `README.md` رو دوباره بخون
2. `RAILWAY_SETUP.md` رو چک کن
3. Railway Logs رو ببینید
4. Error message رو Google کنید

### Feature Request?
```
GitHub Issues میں بنویس!
```

---

## 📜 **لایسنس**

MIT License - برای تمام استفاده‌ها آزاد!

---

## 🎉 **خلاصه**

✅ AI قدرتمند با حافظه  
✅ بازی دونفره واقعی  
✅ جدول امتیازات  
✅ ۲۴/۷ روی Railway  
✅ کم هزینه  
✅ آسان deploy  

**شروع کن! 🚀**

---

**نوشته شده با ❤️ برای کاربران فارسی**

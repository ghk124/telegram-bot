# 🚀 **راهنمای Deploy روی Railway**

## **۱. GitHub Setup**

### ۱.۱ - ریپو بساز
```bash
git clone https://github.com/USERNAME/telegram-bot-advanced
cd telegram-bot-advanced

# فایل‌ها:
main.py
ai_engine.py
game_mario.py
user_db.py
requirements.txt
.env.example
Procfile
.gitignore
README.md
```

### ۱.۲ - Push to GitHub
```bash
git add .
git commit -m "Initial bot setup"
git push origin main
```

---

## **۲. Railway Setup**

### ۲.۱ - Account
1. برو [railway.app](https://railway.app)
2. **Sign up** (GitHub بهتره)
3. GitHub کو کانکت کن

### ۲.۲ - New Project
1. **New Project** کلیک کن
2. **Deploy from GitHub** انتخاب کن
3. ریپوی خودت رو انتخاب کن

### ۲.۳ - Environment Variables
1. **Variables** تب رو کلیک کن
2. **Add Variable** کنید:

```
TELEGRAM_TOKEN = your_token
OPENAI_API_KEY = your_openai_key
```

### ۲.۴ - Deploy
1. **Deploy** بزن
2. صبر کن ۵ دقیقه
3. ✅ شروع می‌شه!

---

## **۳. توکن‌ها کجا بگیریم؟**

### Telegram Token
```
1. @BotFather رو باز کن
2. /newbot بنویس
3. نام و username بده
4. Token کو کپی کن
```

### OpenAI Key
```
1. https://platform.openai.com/api-keys
2. Sign up یا Login
3. Create new secret key
4. کو کپی کن (فقط یک بار نمایش میشه!)
```

---

## **۴. چک کردن**

### Logs
```
Railway Dashboard → [Project] → Logs
```

### اگر error دید:
```
1. TELEGRAM_TOKEN صحیح؟
2. OPENAI_API_KEY صحیح؟
3. requirements.txt OK؟
4. Syntax errors؟
```

---

## **۵. ربات رو تست کن**

تلگرام:
```
/start → سلام
🤖 AI → چیزی بنویس
🍄 ماریو → دوستت رو دعوت کن
```

---

## **۶. Domain (اختیاری)**

اگه می‌خوای custom domain:
```
Railway Settings → Custom Domain
```

---

## **⚠️ نکات مهم**

### Railway Pricing
- **رایگان**: ۵۰۰ ساعت ماهانه (≈ 24/7)
- **Paid**: $5/month

### OpenAI Pricing
- **رایگان**: $5 credit ابتدایی
- **بعدش**: $0.002 per token (معمولاً ۲-۵ سنت در هر پیام)

### Best Practices
- OpenAI calls رو محدود کن (rate limit)
- Database cleanup روزانه
- Error handling قوی

---

## **⚡ Troubleshooting**

| مشکل | حل |
|------|-----|
| `Build failed` | `requirements.txt` رو چک کن |
| `Token not found` | Variables رو Railway میں دوباره add کن |
| `OpenAI error` | API key صحیح؟ / Credit داری؟ |
| `Bot not responding` | Logs رو چک کن |
| `Memory error` | Cleanup users_data.json |

---

## **📱 Keep it Running 24/7**

Railway خود کار restart کردن میکند.

اگر خواستی بیشتر control:
```
Railway → Service → Restart Policy → Always
```

---

## **🔒 Security**

```
❌ هرگز token یا API key در GitHub نذاری
✅ فقط .env.example بذار (بدون values)
✅ Railway → Variables میں بذار
✅ .gitignore میں .env بذار
```

---

## **📊 Monitoring**

Railway میں metrics بگیر:
```
Resources → CPU, Memory, Network
```

---

## **🎉 نتیجه**

✅ Telegram Bot ۲۴/۷ اجرا میشه  
✅ OpenAI AI قدرتمند  
✅ Database persistent  
✅ Mario game دونفره  
✅ Leaderboard  

**Enjoy! 🚀**

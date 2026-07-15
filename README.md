<div align="center">

# 🎬 MyMoviz Notify Bot

ربات تلگرام فارسی برای دنبال کردن فیلم‌ها و سریال‌های سایت [MyMoviz.co](https://mymoviz.co)

**Python 3.12 · Aiogram 3 · APScheduler · SQLite · Docker-Ready · Railway-Ready**

</div>

---

## 📋 فهرست مطالب

- [معرفی](#-معرفی)
- [✨ امکانات](#-امکانات)
- [🏗 ساختار پروژه](#-ساختار-پروژه)
- [⚙ نصب و راه‌اندازی](#-نصب-و-راهاندازی)
- [🤖 تنظیم Bot Token](#-تنظیم-bot-token)
- [📢 تنظیم کانال تلگرام](#-تنظیم-کانال-تلگرام)
- [⏰ تنظیم Cron و Scheduler](#-تنظیم-cron-و-scheduler)
- [🐳 اجرا با Docker](#-اجرا-با-docker)
- [🚀 Deploy روی Railway](#-deploy-روی-railway)
- [🧪 تست](#-تست)
- [📊 دیتابیس](#-دیتابیس)
- [🔒 امنیت](#-امنیت)
- [❓ سوالات متداول](#-سوالات-متداول)
- [📜 لایسنس](#-لایسنس)

---

## 🎯 معرفی

**MyMoviz Notify Bot** یک ربات تلگرام Production-Ready است که به شما کمک می‌کند:

- 🔎 فیلم‌ها و سریال‌های سایت MyMoviz.co را به فارسی یا انگلیسی جستجو کنید
- ⭐ موارد دلخواه را به علاقه‌مندی اضافه کنید
- 🔔 از قسمت جدید سریال‌ها، کیفیت جدید، دوبله یا زیرنویس جدید مطلع شوید
- 📢 اعلان‌ها به کانال تلگرام شما نیز ارسال شوند
- 🛠 یک پنل مدیریت کامل برای ادمین

این ربات از هر دو نسخه‌ی کلاسیک و مدرن سایت پشتیبانی می‌کند و در صورت خرابی یکی، به صورت خودکار از نسخه‌ی دیگر استفاده می‌کند.

---

## ✨ امکانات

### پنل کاربر (دکمه‌های شیشه‌ای)

| دکمه | توضیح |
|------|-------|
| 🏠 خانه | بازگشت به منوی اصلی |
| 🔎 جستجو | جستجوی فیلم/سریال با نام فارسی یا انگلیسی |
| 🎬 فیلم‌ها | لیست آخرین فیلم‌ها |
| 📺 سریال‌ها | لیست آخرین سریال‌ها |
| ⭐ علاقه‌مندی‌ها | لیست موارد ذخیره‌شده |
| 🔔 اطلاع‌رسانی‌ها | لیست اعلان‌های فعال |
| ⚙ تنظیمات | تنظیمات کاربر |
| 🕒 آخرین انتشارها | آخرین محتواهای منتشر شده |
| 🔥 محبوب‌ترین‌ها | محبوب‌ترین فیلم‌ها و سریال‌ها |
| 📊 وضعیت دانلودها | وضعیت اعلان‌های فعال |
| ℹ درباره ربات | اطلاعات ربات |

### صفحه اطلاعات

برای هر فیلم یا سریال، این اطلاعات نمایش داده می‌شود:
- پوستر
- خلاصه داستان
- ژانر
- سال انتشار
- امتیاز IMDb
- کشور سازنده
- مدت زمان
- کیفیت‌های موجود
- وضعیت دوبله و زیرنویس
- آخرین قسمت منتشر شده (برای سریال‌ها)

### دکمه‌های صفحه اطلاعات

- ⭐ افزودن/حذف به علاقه‌مندی
- 🔔 فعال/غیرفعال کردن اطلاع‌رسانی
- 📥 دانلود
- 🌐 مشاهده در سایت
- ⬅ بازگشت

### اطلاع‌رسانی خودکار

ربات هر ۱۰ دقیقه (قابل تنظیم) تمام مواردی که کاربران برایشان اطلاع‌رسانی فعال کرده‌اند را بررسی می‌کند:

- **سریال‌ها:** اگر قسمت جدید منتشر شده باشد
- **فیلم‌ها:** اگر کیفیت جدید، دوبله یا زیرنویس اضافه شده باشد

در صورت تغییر، اعلان به کاربر و کانال‌های تنظیم‌شده ارسال می‌شود.

### پنل ادمین

فقط برای ادمین‌های تعریف‌شده در `ADMIN_IDS`:

- 📊 آمار ربات (تعداد کاربران، اعلان‌ها، فیلم‌ها، سریال‌ها، خطاها)
- 📢 ارسال پیام همگانی به همه کاربران
- 🔄 بررسی فوری (بدون انتظار برای زمان بعدی)
- 🧹 پاکسازی کش

---

## 🏗 ساختار پروژه

```
mymoviz-notify-bot/
├── config/                  # تنظیمات و متغیرهای محیطی
│   ├── __init__.py
│   └── settings.py
├── database/                # دیتابیس SQLAlchemy
│   ├── __init__.py
│   ├── database.py          # Engine و Session
│   ├── models.py            # مدل‌های ORM
│   └── repositories.py      # لایه‌ی دسترسی به داده
├── scrapers/                # اسکریپرهای سایت MyMoviz
│   ├── __init__.py
│   ├── base.py              # کلاس پایه‌ی اسکریپر
│   ├── classic.py           # اسکریپر نسخه کلاسیک
│   ├── modern.py            # اسکریپر نسخه مدرن (_modern)
│   └── manager.py           # مدیریت Fallback
├── telegram/                # ربات تلگرام
│   ├── __init__.py
│   ├── dispatcher.py        # تنظیم Dispatcher
│   ├── keyboards.py         # کیبوردهای شیشه‌ای
│   ├── filters.py           # فیلترهای سفارشی (Admin)
│   ├── middlewares.py       # Middleware دیتابیس
│   └── handlers/
│       ├── __init__.py
│       ├── user.py          # /start، /menu، /help
│       ├── search.py        # جستجو
│       ├── movie.py         # صفحه اطلاعات، علاقه‌مندی، اعلان
│       ├── listings.py      # لیست فیلم‌ها، سریال‌ها، محبوب‌ها
│       └── admin.py         # پنل ادمین
├── scheduler/               # زمان‌بند خودکار
│   ├── __init__.py
│   └── jobs.py              # وظیفه بررسی هر ۱۰ دقیقه
├── utils/                   # ابزارهای کمکی
│   ├── __init__.py
│   ├── logger.py            # Loguru logger
│   ├── helpers.py           # توابع کمکی
│   └── formatters.py        # فرمت‌بندی پیام‌های فارسی RTL
├── cache/                   # کش در حافظه
│   ├── __init__.py
│   └── cache_manager.py     # TTL Cache (۳۰ دقیقه)
├── api/                     # کلاینت HTTP
│   ├── __init__.py
│   └── client.py            # aiohttp با Retry و Backoff
├── logs/                    # فایل‌های لاگ
│   └── .gitkeep
├── tests/                   # تست‌های واحد
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_scrapers.py
│   ├── test_database.py
│   └── test_cache.py
├── main.py                  # نقطه ورود برنامه
├── Dockerfile               # Docker multi-stage build
├── docker-compose.yml       # Docker Compose
├── railway.json             # تنظیمات Railway
├── Procfile                 # Procfile برای Railway/Heroku
├── requirements.txt         # پکیج‌های Python
├── pyproject.toml           # تنظیمات ابزارهای توسعه
├── .env.example             # نمونه‌ی متغیرهای محیطی
├── .gitignore
└── README.md                # این فایل
```

---

## ⚙ نصب و راه‌اندازی

### پیش‌نیازها

- Python 3.12 یا بالاتر
- (اختیاری) Docker و Docker Compose برای اجرای containerized

### راه‌اندازی محلی (Local)

```bash
# 1. کلون کردن پروژه
git clone https://github.com/be2be22/mymo.git
cd mymo

# 2. ایجاد محیط مجازی
python3.12 -m venv venv
source venv/bin/activate    # Linux/Mac
# venv\Scripts\activate     # Windows

# 3. نصب پکیج‌ها
pip install -r requirements.txt

# 4. کپی فایل تنظیمات
cp .env.example .env

# 5. ویرایش .env و تنظیم BOT_TOKEN (مرحله بعد)

# 6. اجرای ربات
python main.py
```

---

## 🤖 تنظیم Bot Token

برای دریافت Token ربات:

1. در تلگرام به [BotFather](https://t.me/BotFather) بروید.
2. دستور `/newbot` را ارسال کنید.
3. یک نام و یک username برای ربات انتخاب کنید.
4. BotFather یک Token شبیه زیر به شما می‌دهد:
   ```
   123456789:AAEXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

سپس فایل `.env` را باز کنید و این مقدار را در `BOT_TOKEN` قرار دهید:

```env
BOT_TOKEN=123456789:AAEXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### تنظیم Admin ID

برای پیدا کردن Telegram User ID خود:

1. به [GetIDs Bot](https://t.me/getidsbot) بروید.
2. دستور `/start` را بزنید تا ID شما نمایش داده شود.
3. این عدد را در `ADMIN_IDS` قرار دهید:

```env
ADMIN_IDS=123456789
```

می‌توانید چند ادمین با کاما جدا کنید:

```env
ADMIN_IDS=11111111,22222222,33333333
```

---

## 📢 تنظیم کانال تلگرام

ربات می‌تواند اعلان‌ها را به کانال‌های شما نیز ارسال کند.

### مراحل

1. یک کانال تلگرام بسازید (یا از کانال موجود استفاده کنید).
2. ربات خود را به عنوان **Administrator** به کانال اضافه کنید.
3. مطمئن شوید دسترسی **Post Messages** فعال است.
4. username کانال (یا ID عددی آن) را در `.env` قرار دهید:

```env
# با username
CHANNEL_IDS=@my_moviz_channel

# یا با ID عددی (برای کانال‌های خصوصی)
CHANNEL_IDS=-1001234567890

# یا چند کانال
CHANNEL_IDS=@channel1,@channel2,-1001234567890
```

### پیدا کردن ID کانال خصوصی

1. کانال را در تلگرام باز کنید.
2. یک پیام در کانال فوروارد کنید به [GetIDs Bot](https://t.me/getidsbot).
3. ID شبیه `-1001234567890` به شما داده می‌شود.

---

## ⏰ تنظیم Cron و Scheduler

ربات از APScheduler برای بررسی خودکار استفاده می‌کند.

### تنظیم دوره بررسی

در فایل `.env`:

```env
# بررسی هر ۱۰ دقیقه (پیش‌فرض)
CHECK_INTERVAL_MINUTES=10

# بررسی هر ۵ دقیقه
CHECK_INTERVAL_MINUTES=5

# بررسی هر ساعت
CHECK_INTERVAL_MINUTES=60
```

### منطق کار Scheduler

1. هر `CHECK_INTERVAL_MINUTES` دقیقه، ربات لیست تمام مواردی که کاربران برایشان اعلان فعال کرده‌اند را از دیتابیس می‌خواند.
2. برای هر مورد، صفحه‌ی آن دوباره از سایت MyMoviz اسکراپ می‌شود.
3. با مقایسه با داده‌ی قبلی، تغییرات تشخیص داده می‌شوند:
   - **فیلم:** کیفیت جدید، دوبله جدید، زیرنویس جدید
   - **سریال:** قسمت جدید، کیفیت جدید، دوبله جدید، زیرنویس جدید
4. برای هر تغییر، یک پیام به کاربر و کانال ارسال می‌شود.
5. برای جلوگیری از ارسال تکراری، هر اعلان در دیتابیس ثبت می‌شود (Deduplication).

### اجرای دستی بررسی

اگر ادمین بخواهد بدون انتظار، بررسی را فوری انجام دهد:

1. در ربات دستور `/admin` را بزنید.
2. روی دکمه‌ی «🔄 بررسی فوری» کلیک کنید.

---

## 🐳 اجرا با Docker

ساده‌ترین روش برای اجرای production، استفاده از Docker است.

### مرحله 1: آماده‌سازی

```bash
# کپی فایل تنظیمات و ویرایش آن
cp .env.example .env
nano .env   # یا با ویرایشگر دلخواه
```

### مرحله 2: Build و اجرا

```bash
# Build ایمیج و اجرا در background
docker compose up -d --build

# مشاهده‌ی لاگ‌ها
docker compose logs -f

# توقف ربات
docker compose down

# توقف و حذف volumeها
docker compose down -v
```

### مرحله 3: بررسی وضعیت

```bash
# وضعیت container
docker compose ps

# وضعیت سلامت
docker inspect --format='{{.State.Health.Status}}' mymoviz-bot
```

### نکات Docker

- داده‌های دیتابیس در `./data/` ذخیره می‌شوند و بین restart‌ها باقی می‌مانند.
- لاگ‌ها در `./logs/` ذخیره می‌شوند.
- Container به صورت خودکار restart می‌شود (`restart: unless-stopped`).
- محدودیت منابع: 512MB RAM و 1 CPU.

---

## 🚀 Deploy روی Railway

[Railway](https://railway.app) یک پلتفرم deploy ابری است که پشتیبانی خوبی از Docker دارد.

### مرحله 1: آماده‌سازی مخزن

مطمئن شوید کد را به GitHub پوش کرده‌اید.

### مرحله 2: ساخت پروژه در Railway

1. به [railway.app](https://railway.app) بروید و با GitHub وارد شوید.
2. **New Project** → **Deploy from GitHub repo**.
3. مخزن `mymo` را انتخاب کنید.
4. Railway به صورت خودکار `Dockerfile` را تشخیص می‌دهد و build می‌کند.

### مرحله 3: تنظیم متغیرهای محیطی

در تب **Variables** این مقادیر را اضافه کنید:

```env
BOT_TOKEN=<your_bot_token>
ADMIN_IDS=<your_telegram_id>
CHANNEL_IDS=@your_channel
DATABASE_URL=sqlite+aiosqlite:///./data/mymoviz.db
CHECK_INTERVAL_MINUTES=10
LOG_LEVEL=INFO
DEBUG=false
```

> ⚠️ برای production توصیه می‌شود از یک دیتابیس PostgreSQL استفاده کنید. در این صورت `DATABASE_URL` را به `postgresql+asyncpg://...` تغییر دهید و `asyncpg` را به `requirements.txt` اضافه کنید.

### مرحله 4: تنظیم Webhook (اختیاری)

اگر می‌خواهید به جای Long Polling از Webhook استفاده کنید:

```env
WEBHOOK_URL=https://your-app-name.up.railway.app
WEBHOOK_PORT=$PORT
WEBHOOK_PATH=/webhook
```

> Railway به صورت خودکار متغیر `PORT` را تنظیم می‌کند. در `railway.json` ما به آن اشاره کرده‌ایم.

### مرحله 5: Deploy

روی **Deploy** کلیک کنید. Railway ایمیج را build و اجرا می‌کند. لاگ‌ها در تب **Deployments** قابل مشاهده هستند.

---

## 🧪 تست

پروژه شامل تست‌های واحد برای اسکریپرها، دیتابیس و کش است.

### اجرای تست‌ها

```bash
# نصب پکیج‌های تست
pip install pytest pytest-asyncio pytest-cov

# اجرای همه تست‌ها
pytest

# اجرای با پوشش
pytest --cov=. --cov-report=term-missing

# اجرای یک فایل خاص
pytest tests/test_scrapers.py -v
```

### تست‌های موجود

| فایل | توضیح |
|------|-------|
| `tests/test_scrapers.py` | تست parsing کلاسیک و مدرن |
| `tests/test_database.py` | تست مدل‌ها و repositories |
| `tests/test_cache.py` | تست CacheManager |

---

## 📊 دیتابیس

### Schema

ربات از SQLite به صورت پیش‌فرض استفاده می‌کند. جداول اصلی:

| جدول | توضیح |
|------|-------|
| `users` | کاربران ثبت‌نام شده |
| `movies` | فیلم‌های کش‌شده از MyMoviz |
| `series` | سریال‌های کش‌شده |
| `episodes` | قسمت‌های هر سریال |
| `favorites` | علاقه‌مندی‌های کاربران |
| `subscriptions` | اعلان‌های فعال کاربران |
| `notifications` | لاگ اعلان‌های ارسال شده |

### مهاجرت به PostgreSQL

برای production با ترافیک بالا، می‌توانید از PostgreSQL استفاده کنید:

1. در `requirements.txt` این خط را اضافه کنید:
   ```
   asyncpg==0.29.0
   ```

2. در `.env`:
   ```env
   DATABASE_URL=postgresql+asyncpg://user:password@host:5432/dbname
   ```

3. در `config/settings.py` نیازی به تغییر نیست - SQLAlchemy به صورت خودکار تشخیص می‌دهد.

### بک‌آپ گیری

```bash
# بک‌آپ از SQLite
cp data/mymoviz.db data/mymoviz_backup_$(date +%Y%m%d).db

# Restore
cp data/mymoviz_backup_20250101.db data/mymoviz.db
```

---

## 🔒 امنیت

### نکات مهم

1. **هرگز** فایل `.env` را در Git commit نکنید (در `.gitignore` قرار دارد).
2. **هرگز** Bot Token خود را به اشتراک نگذارید.
3. در production، `DEBUG=false` تنظیم کنید تا stack trace‌ها در لاگ حساس نباشند.
4. اگر از Webhook استفاده می‌کنید، مطمئن شوید URL شما HTTPS است.
5. کاربر `botuser` در Dockerfile به صورت non-root اجرا می‌شود.
6. محدودیت منابع Docker را برای جلوگیری از مصرف بیش از حد تنظیم کنید.

### Rate Limiting

- بین هر درخواست HTTP به MyMoviz، حداقل `RATE_LIMIT_DELAY` ثانیه (پیش‌فرض 1.5) صبر می‌شود.
- تعداد کانکشن‌های همزمان به 20 محدود شده است.
- Retry با Backoff نمایی در صورت خطای 5xx یا 429.

---

## ❓ سوالات متداول

### ۱. ربات پاسخ نمی‌دهد

- مطمئن شوید `BOT_TOKEN` درست است.
- لاگ‌ها را در `logs/bot.log` بررسی کنید.
- مطمئن شوید ربات block نشده باشد.

### ۲. اعلان‌ها ارسال نمی‌شوند

- مطمئن شوید کاربر روی «🔔 اطلاع بده» کلیک کرده است.
- مطمئن شوید Scheduler در حال اجراست (در لاگ دنبال `⏰ Scheduler tick` بگردید).
- مطمئن شوید `CHANNEL_IDS` درست تنظیم شده و ربات در کانال admin است.

### ۳. جستجو نتیجه‌ای برنمی‌گرداند

- ممکن است سایت MyMoviz موقتاً در دسترس نباشد. ربات به صورت خودکار به نسخه‌ی دیگر سوئیچ می‌کند.
- نام را به انگلیسی امتحان کنید.
- در پنل ادمین «🔄 بررسی فوری» و «🧹 پاکسازی کش» را امتحان کنید.

### ۴. چطور یک ادمین جدید اضافه کنم؟

در `.env`:
```env
ADMIN_IDS=11111111,22222222,33333333
```
سپس ربات را restart کنید.

### ۵. چطور زمان بررسی را تغییر دهم؟

```env
CHECK_INTERVAL_MINUTES=5   # هر ۵ دقیقه
```

---

## 📜 لایسنس

این پروژه به صورت متن‌باز تحت لایسنس MIT ارائه می‌شود.

```
MIT License

Copyright (c) 2025 MyMoviz Notify Bot

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files...
```

---

## 🙏 تشکر از

- [Aiogram](https://aiogram.dev) - فریم‌ورک ربات تلگرام
- [APScheduler](https://apscheduler.readthedocs.io) - زمان‌بند
- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) - HTML parsing
- [Loguru](https://loguru.readthedocs.io) - logging
- [MyMoviz.co](https://mymoviz.co) - منبع داده

---

<div align="center">

**ساخته شده با ❤ برای کاربران فارسی‌زبان**

</div>

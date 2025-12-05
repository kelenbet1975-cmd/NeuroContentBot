print("### NeuroContent FINAL ADMIN NO LIMIT ###")

import os
import sqlite3
import requests
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# ================== НАСТРОЙКИ ==================
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")
ADMIN_ID = int(os.getenv("ADMIN_ID") or 0)

# ================== ТАРИФЫ ==================
TARIFFS = {
    "start": {"title": "🟢 Start", "price": 199, "limit": 50},
    "pro": {"title": "🔵 Pro", "price": 499, "limit": 200},
    "max": {"title": "🟣 Max", "price": 999, "limit": 999999}
}

# ================== БАЗА ==================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    is_pro INTEGER DEFAULT 0,
    requests_today INTEGER DEFAULT 0,
    total_limit INTEGER DEFAULT 5,
    tariff TEXT DEFAULT 'free'
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    content TEXT,
    created_at TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    tariff TEXT,
    amount INTEGER,
    created_at TEXT
)
""")

conn.commit()

# ================== КЛАВИАТУРЫ ==================
def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Описание товара", callback_data="type_product")],
        [InlineKeyboardButton("🌐 Текст для сайта", callback_data="type_site")],
        [InlineKeyboardButton("📣 Пост для соцсетей", callback_data="type_social")],
        [InlineKeyboardButton("💳 Купить PRO", callback_data="buy_pro")],
        [InlineKeyboardButton("📜 История", callback_data="history")]
    ])

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("💰 Доход", callback_data="admin_income")],
        [InlineKeyboardButton("⬅️ В меню", callback_data="back_to_menu")]
    ])

def tariffs_keyboard():
    rows = []
    for k, v in TARIFFS.items():
        rows.append([InlineKeyboardButton(f"{v['title']} — {v['price']} ₽", callback_data=f"buy_{k}")])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)

# ================== ЛИМИТЫ ==================
def check_limit(user_id):
    # ✅ АДМИН БЕЗ ОГРАНИЧЕНИЙ
    if user_id == ADMIN_ID:
        return True

    cursor.execute("SELECT requests_today, total_limit FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()

    if not row:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        return True

    used, total = row
    return used < total

def add_request(user_id):
    if user_id == ADMIN_ID:
        return
    cursor.execute("UPDATE users SET requests_today = requests_today + 1 WHERE user_id=?", (user_id,))
    conn.commit()

def give_tariff(user_id, tariff_key):
    tariff = TARIFFS[tariff_key]

    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    cursor.execute(
        "UPDATE users SET is_pro=1,total_limit=?,tariff=? WHERE user_id=?",
        (tariff["limit"], tariff_key, user_id)
    )
    cursor.execute(
        "INSERT INTO payments (user_id,tariff,amount,created_at) VALUES (?,?,?,?)",
        (user_id, tariff_key, tariff["price"], datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()

def save_history(user_id, text):
    cursor.execute(
        "INSERT INTO history (user_id,content,created_at) VALUES (?,?,?)",
        (user_id, text, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()

# ================== YANDEX GPT ==================
def yandex_generate(prompt):
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite",
        "completionOptions": {"temperature": 0.5, "maxTokens": 900},
        "messages": [{"role": "user", "text": prompt}]
    }

    response = requests.post(url, json=data, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()["result"]["alternatives"][0]["message"]["text"]

# ================== ШАБЛОНЫ ==================
def build_prompt(name, content_type):
    if content_type == "product":
        return f"Напиши продающее описание товара: {name}. Укажи выгоды и преимущества."
    elif content_type == "site":
        return f"Напиши SEO текст для сайта на тему: {name}."
    elif content_type == "social":
        return f"Напиши рекламный пост для соцсетей на тему: {name}."
    return name

# ================== КОМАНДЫ ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 NeuroContent AI", reply_markup=get_main_keyboard())

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Доступ запрещён")
        return
    await update.message.reply_text("🛠 Админ-панель:", reply_markup=admin_keyboard())

# ================== CALLBACK ==================
async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id

    if data.startswith("type_"):
        context.user_data.clear()
        context.user_data["type"] = data.replace("type_", "")
        context.user_data["step"] = "name"
        await query.message.reply_text("Введите название:")

    elif data == "buy_pro":
        await query.message.reply_text("Выберите тариф:", reply_markup=tariffs_keyboard())

    elif data.startswith("buy_"):
        give_tariff(uid, data.replace("buy_", ""))
        await query.message.reply_text("✅ PRO активирован!", reply_markup=get_main_keyboard())

    elif data == "confirm_yes":
        if not check_limit(uid):
            await query.message.reply_text("❌ Лимит исчерпан.")
            return

        name = context.user_data["name"]
        prompt = build_prompt(name, context.user_data["type"])
        result = yandex_generate(prompt)

        add_request(uid)
        save_history(uid, result)

        await query.message.reply_text(result)
        await query.message.reply_text("Готово ✅", reply_markup=get_main_keyboard())
        context.user_data.clear()

    elif data == "admin_stats":
        cursor.execute("SELECT COUNT(*) FROM users")
        users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM history")
        gens = cursor.fetchone()[0]
        await query.message.reply_text(f"👥 Пользователей: {users}\n🧠 Генераций: {gens}")

    elif data == "admin_income":
        cursor.execute("SELECT SUM(amount) FROM payments")
        total = cursor.fetchone()[0] or 0
        await query.message.reply_text(f"💰 Общий доход: {total} ₽")

    elif data == "back_to_menu":
        context.user_data.clear()
        await query.message.reply_text("Главное меню:", reply_markup=get_main_keyboard())

# ================== ТЕКСТ ==================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("step") == "name":
        name = update.message.text
        context.user_data["name"] = name

        await update.message.reply_text(
            f"Подтвердите генерацию:\n\n{name}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ ДА", callback_data="confirm_yes"),
                 InlineKeyboardButton("❌ НЕТ", callback_data="back_to_menu")]
            ])
        )

# ================== ЗАПУСК ==================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("✅ NeuroContent запущен (админ без лимитов)")
    app.run_polling()

if __name__ == "__main__":
    main()

import os
import json
import logging
import asyncio
import time
import requests
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

# ==================== ЗАГРУЗКА ПЕРЕМЕННЫХ ====================
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
TRONK_API_KEY = os.getenv('TRONK_API_KEY')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

BOT_VERSION = "1.2"   # при обновлении меняем цифру

# ==================== ОБЩЕЕ ХРАНИЛИЩЕ (ДЛЯ BOTHOST) ====================
SHARED_DIR = "/app/shared"
os.makedirs(SHARED_DIR, exist_ok=True)
USERS_FILE = os.path.join(SHARED_DIR, "users.json")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# ==================== ЗАГРУЗКА/СОХРАНЕНИЕ ПОЛЬЗОВАТЕЛЕЙ ====================
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return set(data.get('users', [])), data.get('version', '0')
    return set(), '0'

def save_users(users_set):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'users': list(users_set),
            'version': BOT_VERSION
        }, f, ensure_ascii=False, indent=2)

users, saved_version = load_users()

# ==================== ОПОВЕЩЕНИЕ ОБ ОБНОВЛЕНИИ ====================
async def notify_update():
    if saved_version != BOT_VERSION:
        for uid in users:
            try:
                await bot.send_message(
                    int(uid),
                    "🔔 *Бот обновился!*\n\nПожалуйста, отправьте команду /start для корректной работы.",
                    parse_mode="Markdown"
                )
                await asyncio.sleep(0.05)
            except:
                pass
        save_users(users)

# ==================== КЛАВИАТУРЫ ====================
def main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Быстрая проверка (reportnewcheck)")],
            [KeyboardButton(text="📄 Полный отчёт (reportrequest)")]
        ],
        resize_keyboard=True
    )

# ==================== ФУНКЦИИ ЗАПРОСОВ К TRONK ====================
async def quick_check(identifier: str) -> str:
    url = "https://data.tronk.info/reportnewcheck.ashx"
    params = {
        "key": TRONK_API_KEY,
        "vin": identifier if len(identifier) == 17 else None,
        "gosnumber": identifier if len(identifier) != 17 else None,
        "frame": None,  # если нужно
    }
    # Убираем None значения
    params = {k: v for k, v in params.items() if v is not None}
    try:
        r = await asyncio.to_thread(requests.get, url, params=params, timeout=20)
        data = r.json()
        if data.get("error"):
            return f"❌ Ошибка TronK: {data.get('error_msg', 'Неизвестная ошибка')}"
        result = data.get("result", {})
        msg = "🚗 *Результат быстрой проверки*\n\n"
        msg += f"• Марка: {result.get('Marka', '—')}\n"
        msg += f"• Модель: {result.get('Model', '—')}\n"
        msg += f"• Год: {result.get('Year', '—')}\n"
        msg += f"• Цвет: {result.get('Color', '—')}\n"
        msg += f"• Объём двигателя: {result.get('Volume', '—')} л.\n"
        msg += f"• Мощность: {result.get('HorsePower', '—')} л.с.\n"
        return msg
    except Exception as e:
        return f"❌ Ошибка запроса: {e}"

async def full_report(identifier: str) -> str:
    base_url = "https://data.tronk.info/reportrequest.ashx"
    # Шаг 1: Постановка в очередь (обязательно mode=setqueue)
    params = {"key": TRONK_API_KEY, "mode": "setqueue"}
    if len(identifier) == 17:
        params["vin"] = identifier
    else:
        params["gosnumber"] = identifier

    try:
        # 1. Постановка в очередь
        r = await asyncio.to_thread(requests.get, base_url, params=params, timeout=20)
        data = r.json()
        if data.get("error"):
            return f"❌ Ошибка при постановке в очередь: {data.get('error_msg')}"
        task_id = data.get("id")
        if not task_id:
            return "❌ Не удалось получить ID задачи."

        # 2. Ожидание готовности (максимум 60 секунд)
        for _ in range(12):
            await asyncio.sleep(5)
            status_params = {"key": TRONK_API_KEY, "mode": "getstatus", "id": task_id}
            s = await asyncio.to_thread(requests.get, base_url, params=status_params, timeout=10)
            status_data = s.json()
            if status_data.get("status") == "готово":
                # 3. Получение ссылки
                link_params = {"key": TRONK_API_KEY, "mode": "getlink", "id": task_id}
                l = await asyncio.to_thread(requests.get, base_url, params=link_params, timeout=10)
                link_data = l.json()
                pdf_link = link_data.get("link")
                if pdf_link:
                    return f"✅ Отчёт готов: [Скачать PDF]({pdf_link})"
                else:
                    return "❌ Отчёт сформирован, но ссылка не получена."
            elif status_data.get("error"):
                return f"❌ Ошибка при формировании: {status_data.get('error_msg')}"
        return "⏳ Время ожидания истекло. Отчёт ещё не готов."
    except Exception as e:
        return f"❌ Ошибка API: {e}"

# ==================== ОБРАБОТЧИКИ ====================
@dp.message(Command("start"))
async def start_cmd(msg: Message):
    users.add(str(msg.chat.id))
    save_users(users)
    await msg.answer(
        "👋 *Бот проверки автомобилей*\n\n"
        "Отправьте VIN (17 символов) или госномер после выбора типа проверки.\n\n"
        "Выберите действие:",
        parse_mode="Markdown",
        reply_markup=main_kb()
    )

@dp.message(Command("stats"))
async def stats_cmd(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        await msg.answer("⛔ Нет прав.")
        return
    await msg.answer(
        f"📊 *Статистика*\n"
        f"Версия: {BOT_VERSION}\n"
        f"Пользователей: {len(users)}\n"
        f"Файл: {USERS_FILE}",
        parse_mode="Markdown"
    )

@dp.message(F.text == "📋 Быстрая проверка (reportnewcheck)")
async def quick_cmd(msg: Message):
    dp["waiting_for"] = "quick"
    await msg.answer("Введите VIN (17 символов) или госномер:")

@dp.message(F.text == "📄 Полный отчёт (reportrequest)")
async def full_cmd(msg: Message):
    dp["waiting_for"] = "full"
    await msg.answer("Введите VIN (17 символов) или госномер:")

@dp.message()
async def handle_identifier(msg: Message):
    waiting = dp.get("waiting_for")
    if not waiting:
        await msg.answer("Сначала выберите тип проверки через кнопки.", reply_markup=main_kb())
        return
    identifier = msg.text.strip().upper()
    is_vin = len(identifier) == 17
    if not is_vin and not (2 <= len(identifier) <= 9):
        await msg.answer("❌ Неверный формат. VIN = 17 символов, госномер = 2‑9 символов.")
        return
    await bot.send_chat_action(msg.chat.id, "typing")
    if waiting == "quick":
        result = await quick_check(identifier, is_vin)
    else:
        result = await full_report(identifier, is_vin)
    await msg.answer(result, parse_mode="Markdown")
    dp["waiting_for"] = None

# ==================== ЗАПУСК ====================
async def main():
    await notify_update()
    print(f"✅ Бот запущен. Версия {BOT_VERSION}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

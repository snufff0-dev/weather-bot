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

BOT_VERSION = "3.4"

# ==================== ОБЩЕЕ ХРАНИЛИЩЕ ====================
SHARED_DIR = "/app/shared"
os.makedirs(SHARED_DIR, exist_ok=True)
USERS_FILE = os.path.join(SHARED_DIR, "users.json")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# ---------- пользователи ----------
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return set(data.get('users', [])), data.get('version', '0')
    return set(), '0'

def save_users(users_set):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump({'users': list(users_set), 'version': BOT_VERSION}, f, ensure_ascii=False, indent=2)

users, saved_version = load_users()

async def notify_update():
    if saved_version != BOT_VERSION:
        for uid in users:
            try:
                await bot.send_message(int(uid), "🔔 *Бот обновился!* Отправьте /start", parse_mode="Markdown")
                await asyncio.sleep(0.05)
            except:
                pass
        save_users(users)

# ---------- клавиатура ----------
def main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Быстрая проверка (reportnewcheck)")],
            [KeyboardButton(text="⚡ Онлайн-отчёт (reportrequestonline)")],
            [KeyboardButton(text="📄 PDF-отчёт (reportrequest)")]
        ],
        resize_keyboard=True
    )

# ---------- транслитерация госномеров ----------
RUS_TO_LAT = {
    'А': 'A', 'В': 'B', 'Е': 'E', 'К': 'K', 'М': 'M',
    'Н': 'H', 'О': 'O', 'Р': 'P', 'С': 'C', 'Т': 'T',
    'У': 'Y', 'Х': 'X'
}

def transliterate_gosnumber(number: str) -> str:
    return ''.join(RUS_TO_LAT.get(ch, ch) for ch in number.upper())

# ---------- МЕТОД 1: Быстрая проверка (reportnewcheck) - синхронный ----------
async def quick_check(identifier: str) -> str:
    url = "https://data.tronk.info/reportnewcheck.ashx"
    params = {"key": TRONK_API_KEY}
    if len(identifier) == 17:
        params["vin"] = identifier
    else:
        params["gosnumber"] = identifier
    try:
        r = await asyncio.to_thread(requests.get, url, params=params, timeout=20)
        data = r.json()
        if data.get("error"):
            return f"❌ Ошибка TronK: {data.get('error_msg', 'Неизвестная ошибка')}"
        result = data.get("result", {})
        if not result:
            return "❌ Данные по указанному идентификатору не найдены."
        msg = "🚗 *Быстрая проверка*\n\n"
        msg += f"• Марка: {result.get('Marka', '—')}\n"
        msg += f"• Модель: {result.get('Model', '—')}\n"
        msg += f"• Год: {result.get('Year', '—')}\n"
        msg += f"• Цвет: {result.get('Color', '—')}\n"
        msg += f"• Объём двигателя: {result.get('Volume', '—')} л\n"
        msg += f"• Мощность: {result.get('HorsePower', '—')} л.с.\n"
        return msg
    except Exception as e:
        return f"❌ Ошибка запроса: {e}"

# ---------- МЕТОД 2: Онлайн-отчёт (reportrequestonline) - асинхронный (очередь) ----------
async def online_report(identifier: str) -> str:
    base_url = "https://data.tronk.info/reportrequestonline.ashx"
    # Шаг 1: постановка в очередь
    params_queue = {"key": TRONK_API_KEY, "mode": "setqueue"}
    if len(identifier) == 17:
        params_queue["vin"] = identifier
    else:
        params_queue["gosnumber"] = identifier
    try:
        r = await asyncio.to_thread(requests.get, base_url, params=params_queue, timeout=30)
        data = r.json()
        if data.get("error"):
            return f"❌ Ошибка при постановке в очередь: {data.get('error_msg')}"
        task_id = data.get("id")
        if not task_id:
            return "❌ Не удалось получить ID задачи."

        # Шаг 2: ожидание готовности (проверка через checkqueue) – увеличенное время
        for attempt in range(24):  # 24 * 5 = 120 секунд
            await asyncio.sleep(5)
            params_status = {"key": TRONK_API_KEY, "mode": "checkqueue", "id": task_id}
            s = await asyncio.to_thread(requests.get, base_url, params=params_status, timeout=10)
            status_data = s.json()
            if status_data.get("status") == "готово":
                # Шаг 3: получение ссылки
                params_link = {"key": TRONK_API_KEY, "mode": "getlink", "id": task_id}
                l = await asyncio.to_thread(requests.get, base_url, params=params_link, timeout=10)
                link_data = l.json()
                report_url = link_data.get("url") or link_data.get("link")
                if report_url:
                    return f"✅ Онлайн-отчёт готов: [Скачать]({report_url})"
                else:
                    return "✅ Отчёт сформирован, но ссылка не получена."
            elif status_data.get("error"):
                return f"❌ Ошибка при формировании: {status_data.get('error_msg')}"
        return "⏳ Время ожидания истекло. Отчёт всё ещё не готов, попробуйте позже."
    except Exception as e:
        return f"❌ Ошибка API: {e}"

# ---------- МЕТОД 3: PDF-отчёт (reportrequest) - асинхронный (очередь) ----------
async def pdf_report(identifier: str) -> str:
    base_url = "https://data.tronk.info/reportrequest.ashx"
    # Шаг 1: постановка в очередь
    params_queue = {"key": TRONK_API_KEY, "mode": "setqueue"}
    if len(identifier) == 17:
        params_queue["vin"] = identifier
    else:
        params_queue["gosnumber"] = identifier
    try:
        r = await asyncio.to_thread(requests.get, base_url, params=params_queue, timeout=30)
        data = r.json()
        if data.get("error"):
            return f"❌ Ошибка при постановке в очередь: {data.get('error_msg')}"
        task_id = data.get("id")
        if not task_id:
            return "❌ Не удалось получить ID задачи."

        # Шаг 2: ожидание готовности (проверка через getstatus) – увеличенное время
        for attempt in range(24):  # 24 * 5 = 120 секунд
            await asyncio.sleep(5)
            params_status = {"key": TRONK_API_KEY, "mode": "getstatus", "id": task_id}
            s = await asyncio.to_thread(requests.get, base_url, params=params_status, timeout=10)
            status_data = s.json()
            if status_data.get("status") == "готово":
                # Шаг 3: получение ссылки
                params_link = {"key": TRONK_API_KEY, "mode": "getlink", "id": task_id}
                l = await asyncio.to_thread(requests.get, base_url, params=params_link, timeout=10)
                link_data = l.json()
                report_url = link_data.get("url") or link_data.get("link")
                if report_url:
                    return f"✅ PDF-отчёт готов: [Скачать]({report_url})"
                else:
                    return "✅ Отчёт сформирован, но ссылка не получена."
            elif status_data.get("error"):
                return f"❌ Ошибка при формировании: {status_data.get('error_msg')}"
        return "⏳ Время ожидания истекло. Отчёт всё ещё не готов, попробуйте позже."
    except Exception as e:
        return f"❌ Ошибка API: {e}"

# ==================== ОБРАБОТЧИКИ ====================
@dp.message(Command("start"))
async def start_cmd(msg: Message):
    users.add(str(msg.chat.id))
    save_users(users)
    await msg.answer(
        "👋 *Бот проверки автомобилей*\n\n"
        "Доступные методы:\n"
        "• 📋 Быстрая проверка – базовые данные (марка, модель, год, цвет, объём, мощность)\n"
        "• ⚡ Онлайн-отчёт – подробный отчёт (формируется до 2 минут)\n"
        "• 📄 PDF-отчёт – полный отчёт с PDF (формируется до 2 минут)\n\n"
        "Введите **VIN (17 символов)** или **госномер** (русские буквы поддерживаются).\n"
        "Выберите тип проверки:",
        parse_mode="Markdown",
        reply_markup=main_kb()
    )

@dp.message(Command("stats"))
async def stats_cmd(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        await msg.answer("⛔ Нет прав.")
        return
    await msg.answer(
        f"📊 *Статистика*\nВерсия: {BOT_VERSION}\nПользователей: {len(users)}",
        parse_mode="Markdown"
    )

@dp.message(F.text == "📋 Быстрая проверка (reportnewcheck)")
async def quick_cmd(msg: Message):
    dp["waiting_for"] = "quick"
    await msg.answer("Введите VIN или госномер:")

@dp.message(F.text == "⚡ Онлайн-отчёт (reportrequestonline)")
async def online_cmd(msg: Message):
    dp["waiting_for"] = "online"
    await msg.answer("Введите VIN или госномер:")

@dp.message(F.text == "📄 PDF-отчёт (reportrequest)")
async def pdf_cmd(msg: Message):
    dp["waiting_for"] = "pdf"
    await msg.answer("Введите VIN или госномер:")

@dp.message()
async def handle_identifier(msg: Message):
    waiting = dp.get("waiting_for")
    if not waiting:
        await msg.answer("Сначала выберите тип проверки через кнопки.", reply_markup=main_kb())
        return
    raw = msg.text.strip().upper()
    identifier = transliterate_gosnumber(raw)
    if len(identifier) != 17 and not (2 <= len(identifier) <= 9):
        await msg.answer("❌ Неверный формат. VIN = 17 символов, госномер = 2‑9 символов.")
        return
    await bot.send_chat_action(msg.chat.id, "typing")
    if waiting == "quick":
        result = await quick_check(identifier)
    elif waiting == "online":
        result = await online_report(identifier)
    else:
        result = await pdf_report(identifier)
    await msg.answer(result, parse_mode="Markdown")
    dp["waiting_for"] = None

# ==================== ЗАПУСК ====================
async def main():
    await notify_update()
    print(f"✅ Бот запущен. Версия {BOT_VERSION}")
    print("Активные методы TronK: reportnewcheck, reportrequestonline, reportrequest")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

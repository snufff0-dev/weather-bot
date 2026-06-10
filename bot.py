import os
import logging
import asyncio
import time
import requests
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
TRONK_API_KEY = os.getenv('TRONK_API_KEY')

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# ---------- КЛАВИАТУРЫ ----------
def main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Быстрая проверка (reportnewcheck)")],
            [KeyboardButton(text="📄 Полный отчёт (reportrequest)")]
        ],
        resize_keyboard=True
    )

# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ----------
async def quick_check(identifier: str) -> str:
    """Метод reportnewcheck.ashx - быстрая проверка."""
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
            return f"❌ Ошибка: {data.get('error_msg', 'Неизвестная ошибка')}"
        # Формируем читаемый ответ
        result = data.get("result", {})
        msg = f"🚗 *Результат быстрой проверки*\n"
        msg += f"• Марка: {result.get('mark', '—')}\n"
        msg += f"• Модель: {result.get('model', '—')}\n"
        msg += f"• Год: {result.get('year', '—')}\n"
        msg += f"• Цвет: {result.get('color', '—')}\n"
        msg += f"• VIN: {result.get('vin', identifier)}\n"
        return msg
    except Exception as e:
        return f"❌ Ошибка запроса: {e}"

async def full_report(identifier: str) -> str:
    """Метод reportrequest.ashx - полный отчёт с очередью."""
    url = "https://data.tronk.info/reportrequest.ashx"
    params = {"key": TRONK_API_KEY, "mode": "setqueue"}
    if len(identifier) == 17:
        params["vin"] = identifier
    else:
        params["gosnumber"] = identifier

    try:
        r = await asyncio.to_thread(requests.get, url, params=params, timeout=20)
        data = r.json()
        if data.get("error"):
            return f"❌ Ошибка: {data.get('error_msg', 'Неизвестная ошибка')}"
        task_id = data.get("id")
        if not task_id:
            return "❌ Не удалось получить ID задачи."

        # Проверяем статус отчёта (повторяем каждые 5 секунд, максимум 10 раз)
        status_url = "https://data.tronk.info/reportrequest.ashx"
        for _ in range(10):
            await asyncio.sleep(5)
            status_params = {"key": TRONK_API_KEY, "mode": "getstatus", "id": task_id}
            s = await asyncio.to_thread(requests.get, status_url, params=status_params, timeout=10)
            status_data = s.json()
            if status_data.get("status") == "готово":
                # Получаем ссылку на отчёт
                link_params = {"key": TRONK_API_KEY, "mode": "getlink", "id": task_id}
                l = await asyncio.to_thread(requests.get, status_url, params=link_params, timeout=10)
                link_data = l.json()
                pdf_link = link_data.get("link")
                return f"✅ Отчёт готов: [Скачать PDF]({pdf_link})"
            elif status_data.get("error"):
                return f"❌ Ошибка при формировании отчёта: {status_data.get('error_msg')}"
        return "⏳ Время ожидания истекло. Отчёт ещё не готов, попробуйте позже."
    except Exception as e:
        return f"❌ Ошибка запроса: {e}"

# ---------- ОБРАБОТЧИКИ ----------
@dp.message(Command("start"))
async def start_cmd(msg: Message):
    await msg.answer(
        "👋 Бот проверки автомобилей по VIN/госномеру.\n\n"
        "Выберите тип проверки:",
        parse_mode="Markdown",
        reply_markup=main_kb()
    )

@dp.message(F.text == "📋 Быстрая проверка (reportnewcheck)")
async def quick_check_cmd(msg: Message):
    await msg.answer("Введите VIN (17 символов) или госномер:")
    # Сохраняем состояние, чтобы следующий текст обработать
    dp["waiting_for"] = "quick"

@dp.message(F.text == "📄 Полный отчёт (reportrequest)")
async def full_report_cmd(msg: Message):
    await msg.answer("Введите VIN (17 символов) или госномер:")
    dp["waiting_for"] = "full"

@dp.message()
async def handle_identifier(msg: Message):
    waiting = dp.get("waiting_for")
    if not waiting:
        await msg.answer("Пожалуйста, выберите тип проверки через кнопки меню.", reply_markup=main_kb())
        return
    identifier = msg.text.strip().upper()
    # Простая проверка: если не VIN (17 символов) и не похоже на госномер
    if len(identifier) != 17 and not (2 <= len(identifier) <= 9):
        await msg.answer("❌ Неверный формат. VIN должен содержать 17 символов, госномер — 2-9 символов.")
        return
    # Отправляем "печатает"
    await bot.send_chat_action(msg.chat.id, "typing")
    if waiting == "quick":
        result = await quick_check(identifier)
    else:
        result = await full_report(identifier)
    await msg.answer(result, parse_mode="Markdown")
    dp["waiting_for"] = None  # сброс состояния

# ---------- ЗАПУСК ----------
async def main():
    print("✅ Бот запущен (только проверка авто)")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

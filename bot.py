import os
import logging
import asyncio
import threading
import time
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
import requests
import schedule

# Загружаем .env
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')
CHAT_ID = os.getenv('CHAT_ID')

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

user_cities = {}
user_subscription_time = {}
logging.basicConfig(level=logging.INFO)

# ==================== КЛАВИАТУРЫ ====================

def get_main_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🌤 Погода сейчас"), KeyboardButton(text="🚗 Советы водителю")],
            [KeyboardButton(text="⚙️ Установить город"), KeyboardButton(text="🔔 Подписка")],
            [KeyboardButton(text="❓ Помощь"), KeyboardButton(text="ℹ️ О боте")]
        ],
        resize_keyboard=True,
        input_field_placeholder="Нажмите кнопку или напишите город..."
    )
    return keyboard

def get_cities_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🇷🇺 Москва"), KeyboardButton(text="🇷🇺 Санкт-Петербург")],
            [KeyboardButton(text="🇷🇺 Новосибирск"), KeyboardButton(text="🇷🇺 Екатеринбург")],
            [KeyboardButton(text="🇷🇺 Казань"), KeyboardButton(text="🇷🇺 Омск")],
            [KeyboardButton(text="🇷🇺 Красноярск"), KeyboardButton(text="🇷🇺 Владивосток")],
            [KeyboardButton(text="⬅️ Назад в меню")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_weather_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔄 Обновить погоду"), KeyboardButton(text="🌤 Другой город")],
            [KeyboardButton(text="🔔 Подписаться на рассылку"), KeyboardButton(text="⬅️ Главное меню")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_subscription_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Подписаться"), KeyboardButton(text="❌ Отписаться")],
            [KeyboardButton(text="⏰ Выбрать время"), KeyboardButton(text="📊 Статус подписки")],
            [KeyboardButton(text="⬅️ Главное меню")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_back_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Назад в меню")]],
        resize_keyboard=True
    )
    return keyboard

# ==================== ФУНКЦИИ ПОГОДЫ ====================

def get_weather(city: str) -> dict:
    try:
        url = f"http://ru.api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
        response = requests.get(url, timeout=10)
        data = response.json()

        if response.status_code == 200:
            temp = data['main']['temp']
            feels_like = data['main']['feels_like']
            humidity = data['main']['humidity']
            pressure = data['main']['pressure'] * 0.750062
            wind_speed = data['wind']['speed']
            wind_direction = data['wind'].get('deg', 0)
            weather_desc = data['weather'][0]['description']
            clouds = data['clouds']['all']
            visibility = data.get('visibility', 10000) / 1000

            directions = ['северный', 'северо-восточный', 'восточный', 'юго-восточный',
                          'южный', 'юго-западный', 'западный', 'северо-западный']
            wind_dir = directions[int((wind_direction + 22.5) / 45) % 8]

            return {
                'success': True,
                'city': city,
                'temp': temp,
                'feels_like': feels_like,
                'humidity': humidity,
                'pressure': pressure,
                'wind_speed': wind_speed,
                'wind_dir': wind_dir,
                'description': weather_desc,
                'clouds': clouds,
                'visibility': visibility,
                'time': datetime.now().strftime('%d.%m.%Y %H:%M')
            }
        else:
            return {'success': False, 'error': 'Город не найден'}
    except Exception as e:
        return {'success': False, 'error': f'Ошибка: {e}'}

def format_weather_message(weather: dict) -> str:
    if not weather['success']:
        return f"❌ {weather['error']}"
    message = (
        f"🌍 *ПРОГНОЗ В {weather['city'].upper()}*\n"
        f"📅 {weather['time']}\n"
        f"☁️ {weather['description'].capitalize()}\n"
        f"🌡️ *{weather['temp']:.1f}°C* (ощущается {weather['feels_like']:.1f}°C)\n"
        f"💧 Влажность: {weather['humidity']}%\n"
        f"📊 Давление: {weather['pressure']:.1f} мм рт.ст.\n"
        f"💨 Ветер: {weather['wind_speed']:.1f} м/с, {weather['wind_dir']}\n"
        f"👁️ Видимость: {weather['visibility']:.1f} км\n"
        f"☁️ Облачность: {weather['clouds']}%\n\n"
        f"🚗 *СОВЕТЫ ВОДИТЕЛЮ:*\n"
    )
    if weather['temp'] < -20:
        message += "❄️ *Экстремальный холод*: проверь аккумулятор, прогревай 10-15 мин\n"
    elif weather['temp'] < -10:
        message += "❄️ *Очень холодно*: проверь антифриз, трудный запуск\n"
    elif weather['temp'] < 0:
        message += "⚠️ *Гололёд*: дистанция ×2, избегай резких движений\n"
    elif weather['temp'] > 30:
        message += "🔥 *Жара*: проверь охлаждающую жидкость, кондиционер\n"
    if weather['humidity'] > 80:
        message += "💧 *Высокая влажность*: стекла могут запотевать\n"
    if weather['wind_speed'] > 15:
        message += "💨 *Ураганный ветер*: будь осторожен на мостах\n"
    elif weather['wind_speed'] > 10:
        message += "💨 *Сильный ветер*: крепче держи руль\n"
    if weather['visibility'] < 1:
        message += "🌫️ *Очень плохая видимость*: противотуманки, снизь скорость\n"
    elif weather['visibility'] < 4:
        message += "🌫️ *Плохая видимость*: включи ближний свет\n"
    if 'дождь' in weather['description']:
        message += "🌧️ *Дождь*: проверь дворники, дистанция ×2\n"
    if 'снег' in weather['description']:
        message += "🌨️ *Снегопад*: проверь резину, чисти снег с крыши\n"
    if 'туман' in weather['description']:
        message += "🌫️ *Туман*: используй противотуманки\n"
    if 'гроза' in weather['description']:
        message += "⛈️ *Гроза*: пережди, не паркуйся под деревьями\n"
    if message.count('\n') < 12:
        message += "✅ Условия благоприятные, хорошей дороги!\n"
    return message

# ==================== ОБРАБОТЧИКИ ====================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    welcome_text = (
        "👋 *Добро пожаловать в WeatherBot!*\n\n"
        "Я помогаю водителям узнавать погоду и получать полезные советы.\n\n"
        "👇 *Нажми кнопку или напиши город:*"
    )
    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

@dp.message(F.text == "🌤 Погода сейчас")
async def weather_now(message: Message):
    chat_id = message.chat.id
    if chat_id in user_cities:
        city = user_cities[chat_id]
        weather = get_weather(city)
        await message.answer(format_weather_message(weather), parse_mode="Markdown", reply_markup=get_weather_keyboard())
    else:
        await message.answer("🌆 *Выберите город* из списка или напишите его название:", parse_mode="Markdown", reply_markup=get_cities_keyboard())

@dp.message(F.text == "🚗 Советы водителю")
async def driver_tips(message: Message):
    tips = (
        "🚗 *ПОЛЕЗНЫЕ СОВЕТЫ ВОДИТЕЛЮ*\n\n"
        "❄️ *Зимой:*\n• Возим щетку и скребок\n• Проверяем аккумулятор\n• Дистанция ×2\n\n"
        "☔ *В дождь:*\n• Включаем фары днем\n• Не влетаем в лужи\n• Проверяем дворники\n\n"
        "☀️ *В жару:*\n• Следим за антифризом\n• Не оставляем детей/животных\n• Проветриваем салон\n\n"
        "🌫️ *В туман:*\n• Противотуманки\n• Скорость ниже\n• Ориентир по разметке"
    )
    await message.answer(tips, parse_mode="Markdown", reply_markup=get_back_keyboard())

@dp.message(F.text == "⚙️ Установить город")
async def set_city_prompt(message: Message):
    await message.answer("🌆 *Напишите название вашего города* (например: Москва, Омск, Казань):", parse_mode="Markdown", reply_markup=get_back_keyboard())

@dp.message(F.text == "🔔 Подписка")
async def subscription_menu(message: Message):
    chat_id = message.chat.id
    city = user_cities.get(chat_id, "не установлен")
    sub_time = user_subscription_time.get(chat_id, "08:00")
    global CHAT_ID
    is_subscribed = (CHAT_ID and int(CHAT_ID) == chat_id)
    status = "✅ *Активна*" if is_subscribed else "❌ *Не активна*"
    text = f"🔔 *УПРАВЛЕНИЕ ПОДПИСКОЙ*\n\n🏙️ Город: *{city}*\n⏰ Текущее время: *{sub_time}*\n📊 Статус: {status}\n\nВы можете выбрать любое время от 00:00 до 23:59"
    await message.answer(text, parse_mode="Markdown", reply_markup=get_subscription_keyboard())

@dp.message(F.text == "❓ Помощь")
async def help_menu(message: Message):
    help_text = (
        "❓ *ПОМОЩЬ И КОМАНДЫ*\n\n"
        "🌤 Погода сейчас - узнать погоду\n"
        "🚗 Советы водителю - рекомендации\n"
        "⚙️ Установить город - город по умолчанию\n"
        "🔔 Подписка - настроить рассылку\n\n"
        "✅ Подписаться - включить рассылку\n"
        "❌ Отписаться - отключить рассылку\n"
        "⏰ Выбрать время - установить удобное время\n"
        "📊 Статус подписки - проверить настройки"
    )
    await message.answer(help_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

@dp.message(F.text == "ℹ️ О боте")
async def about_bot(message: Message):
    about = "ℹ️ *О БОТЕ*\n\n📦 Версия: 2.2\n👨‍💻 Разработчик: Ваше имя\n🌐 Источник: OpenWeatherMap\n\n🚗 *Для кого:*\nДля водителей, таксистов, дальнобойщиков\n\n✨ *Особенности:*\n• Умные советы по погоде\n• Ежедневная рассылка\n• Удобные кнопки"
    await message.answer(about, parse_mode="Markdown", reply_markup=get_back_keyboard())

@dp.message(F.text == "⬅️ Назад в меню")
@dp.message(F.text == "⬅️ Главное меню")
async def back_to_main_menu(message: Message):
    await message.answer("🔹 *Главное меню*", parse_mode="Markdown", reply_markup=get_main_keyboard())

@dp.message(F.text == "🔄 Обновить погоду")
async def refresh_weather(message: Message):
    chat_id = message.chat.id
    if chat_id in user_cities:
        city = user_cities[chat_id]
        weather = get_weather(city)
        await message.answer(format_weather_message(weather), parse_mode="Markdown", reply_markup=get_weather_keyboard())
    else:
        await message.answer("⚠️ Сначала установите город!", reply_markup=get_cities_keyboard())

@dp.message(F.text == "🌤 Другой город")
async def another_city(message: Message):
    await message.answer("🌆 *Выберите город* из списка или напишите его название:", parse_mode="Markdown", reply_markup=get_cities_keyboard())

@dp.message(F.text == "🔔 Подписаться на рассылку")
@dp.message(F.text == "✅ Подписаться")
async def handle_subscribe(message: Message):
    global CHAT_ID
    chat_id = message.chat.id
    if chat_id not in user_cities:
        await message.answer("⚠️ Сначала установите город!", reply_markup=get_main_keyboard())
        return
    CHAT_ID = str(chat_id)
    city = user_cities[chat_id]
    sub_time = user_subscription_time.get(chat_id, "08:00")
    await message.answer(f"✅ *Вы подписаны!*\n\n🏙️ Город: {city}\n⏰ Время: {sub_time}\n\nТеперь вы будете получать прогноз каждый день в {sub_time}.", parse_mode="Markdown", reply_markup=get_main_keyboard())

@dp.message(F.text == "❌ Отписаться")
async def handle_unsubscribe(message: Message):
    global CHAT_ID
    if CHAT_ID and int(CHAT_ID) == message.chat.id:
        CHAT_ID = None
        await message.answer("❌ *Вы отписались от рассылки*", parse_mode="Markdown")
    else:
        await message.answer("❌ Вы не были подписаны")

@dp.message(F.text == "⏰ Выбрать время")
async def select_time(message: Message):
    await message.answer("⏰ *Введите время* в формате ЧЧ:ММ (например, 08:00, 14:30):", parse_mode="Markdown", reply_markup=get_back_keyboard())

@dp.message(F.text == "📊 Статус подписки")
async def subscription_status(message: Message):
    global CHAT_ID
    if CHAT_ID and int(CHAT_ID) == message.chat.id:
        city = user_cities.get(message.chat.id, "не установлен")
        sub_time = user_subscription_time.get(message.chat.id, "08:00")
        await message.answer(f"✅ *Подписка активна*\n🏙️ Город: {city}\n⏰ Время: {sub_time}", parse_mode="Markdown")
    else:
        await message.answer("❌ *Подписка не активна*", parse_mode="Markdown")

@dp.message(F.text.startswith(("🇷🇺", "Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань", "Омск", "Красноярск", "Владивосток")))
async def handle_city_button(message: Message):
    city = message.text.replace("🇷🇺 ", "").strip()
    chat_id = message.chat.id
    weather = get_weather(city)
    if weather['success']:
        user_cities[chat_id] = city
        await message.answer(format_weather_message(weather), parse_mode="Markdown", reply_markup=get_weather_keyboard())
    else:
        await message.answer(f"❌ Не удалось получить погоду для {city}", reply_markup=get_cities_keyboard())

@dp.message()
async def handle_text(message: Message):
    text = message.text.strip()
    chat_id = message.chat.id
    if len(text) == 5 and text[2] == ':':
        try:
            hours = int(text[:2])
            minutes = int(text[3:])
            if 0 <= hours <= 23 and 0 <= minutes <= 59:
                user_subscription_time[chat_id] = text
                await message.answer(f"✅ Время установлено: *{text}*", parse_mode="Markdown", reply_markup=get_subscription_keyboard())
                return
        except:
            pass
    weather = get_weather(text)
    if weather['success']:
        user_cities[chat_id] = text
        await message.answer(format_weather_message(weather), parse_mode="Markdown", reply_markup=get_weather_keyboard())
    else:
        await message.answer(f"❌ Город '{text}' не найден.\nПроверьте название или выберите из списка:", reply_markup=get_cities_keyboard())

# ==================== ПЛАНИРОВЩИК ====================

def send_daily_weather():
    if not CHAT_ID:
        return
    chat_id = int(CHAT_ID)
    city = user_cities.get(chat_id, "Москва")
    weather = get_weather(city)
    asyncio.create_task(bot.send_message(chat_id=chat_id, text=format_weather_message(weather), parse_mode="Markdown"))

def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(30)

# ==================== ЗАПУСК ====================

async def main():
    schedule.every().day.at("08:00").do(send_daily_weather)
    threading.Thread(target=run_schedule, daemon=True).start()
    print("\n" + "="*60)
    print("✅ БОТ УСПЕШНО ЗАПУЩЕН!")
    print("="*60)
    await dp.start_polling(bot)

# Только одна точка входа
if __name__ == "__main__":
    asyncio.run(main())
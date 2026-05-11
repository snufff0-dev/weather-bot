import os
import logging
import asyncio
import threading
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
import requests
import schedule

asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')
CHAT_ID = os.getenv('CHAT_ID')

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

user_cities = {}
user_subscription_time = {}
logging.basicConfig(level=logging.INFO)

# ----- ПЕРЕВОД ДНЕЙ НА РУССКИЙ -----
DAYS_RU = {
    'Monday': 'Понедельник',
    'Tuesday': 'Вторник',
    'Wednesday': 'Среда',
    'Thursday': 'Четверг',
    'Friday': 'Пятница',
    'Saturday': 'Суббота',
    'Sunday': 'Воскресенье'
}

def get_russian_day(date: datetime) -> str:
    eng = date.strftime('%A')
    return DAYS_RU.get(eng, eng)

# ----- КЛАВИАТУРЫ -----
def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🌤 Погода сейчас"), KeyboardButton(text="📅 Прогноз на 5 дней")],
            [KeyboardButton(text="🚗 Советы водителю"), KeyboardButton(text="⚙️ Установить город")],
            [KeyboardButton(text="🔔 Подписка"), KeyboardButton(text="❓ Помощь")],
            [KeyboardButton(text="ℹ️ О боте")]
        ],
        resize_keyboard=True
    )

def get_cities_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🇷🇺 Москва"), KeyboardButton(text="🇷🇺 Санкт-Петербург")],
            [KeyboardButton(text="🇷🇺 Новосибирск"), KeyboardButton(text="🇷🇺 Екатеринбург")],
            [KeyboardButton(text="🇷🇺 Казань"), KeyboardButton(text="🇷🇺 Омск")],
            [KeyboardButton(text="🇷🇺 Красноярск"), KeyboardButton(text="🇷🇺 Владивосток")],
            [KeyboardButton(text="⬅️ Назад в меню")]
        ],
        resize_keyboard=True
    )

def get_weather_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔄 Обновить погоду"), KeyboardButton(text="📅 Прогноз на 5 дней")],
            [KeyboardButton(text="🌤 Другой город"), KeyboardButton(text="⬅️ Главное меню")]
        ],
        resize_keyboard=True
    )

def get_subscription_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Подписаться"), KeyboardButton(text="❌ Отписаться")],
            [KeyboardButton(text="⏰ Выбрать время"), KeyboardButton(text="📊 Статус подписки")],
            [KeyboardButton(text="⬅️ Главное меню")]
        ],
        resize_keyboard=True
    )

def get_back_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Назад в меню")]],
        resize_keyboard=True
    )

# ----- ФУНКЦИИ ПОГОДЫ (синхронные, как в рабочей версии) -----
def get_weather(city: str) -> dict:
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
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
            directions = ['северный','северо-восточный','восточный','юго-восточный',
                          'южный','юго-западный','западный','северо-западный']
            wind_dir = directions[int((wind_direction + 22.5) / 45) % 8]
            return {
                'success': True, 'city': city, 'temp': temp, 'feels_like': feels_like,
                'humidity': humidity, 'pressure': pressure, 'wind_speed': wind_speed,
                'wind_dir': wind_dir, 'description': weather_desc, 'clouds': clouds,
                'visibility': visibility, 'time': datetime.now().strftime('%d.%m.%Y %H:%M')
            }
        else:
            return {'success': False, 'error': 'Город не найден'}
    except Exception as e:
        return {'success': False, 'error': f'Ошибка: {e}'}

def get_5day_forecast(city: str) -> dict:
    try:
        url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
        response = requests.get(url, timeout=15)
        data = response.json()
        if response.status_code == 200:
            daily = {}
            for item in data['list']:
                dt = datetime.fromtimestamp(item['dt'])
                key = dt.strftime('%Y-%m-%d')
                if key not in daily:
                    daily[key] = {
                        'temps': [], 'descriptions': [], 'wind_speeds': [],
                        'humidity': [], 'rain': False, 'snow': False, 'date': dt
                    }
                daily[key]['temps'].append(item['main']['temp'])
                daily[key]['descriptions'].append(item['weather'][0]['description'])
                daily[key]['wind_speeds'].append(item['wind']['speed'])
                daily[key]['humidity'].append(item['main']['humidity'])
                if 'rain' in item and item['rain'].get('3h', 0) > 0:
                    daily[key]['rain'] = True
                if 'snow' in item and item['snow'].get('3h', 0) > 0:
                    daily[key]['snow'] = True
            forecasts = []
            for key, day in list(daily.items())[:5]:
                forecasts.append({
                    'date': day['date'],
                    'temp_max': max(day['temps']),
                    'temp_min': min(day['temps']),
                    'temp_day': sum(day['temps']) / len(day['temps']),
                    'description': max(set(day['descriptions']), key=day['descriptions'].count),
                    'wind_speed': max(day['wind_speeds']),
                    'humidity': sum(day['humidity']) / len(day['humidity']),
                    'rain': day['rain'],
                    'snow': day['snow']
                })
            return {'success': True, 'city': city, 'forecasts': forecasts}
        else:
            return {'success': False, 'error': 'Город не найден'}
    except Exception as e:
        return {'success': False, 'error': f'Ошибка: {e}'}

def get_driver_tips(temp, wind, humidity, desc, rain, snow):
    tips = []
    if temp < -30: tips.append("❄️❄️ ЭКСТРЕМАЛЬНЫЙ МОРОЗ: не выезжай без крайней необходимости")
    elif temp < -20: tips.append("❄️ Сильный мороз: прогревай 10-15 мин, проверь аккумулятор")
    elif temp < -10: tips.append("❄️ Холодно: дистанция ×2")
    elif temp < 0: tips.append("⚠️ Гололед: дистанция ×3, плавно")
    elif temp > 35: tips.append("🔥 Экстремальная жара: проверь охлаждающую жидкость")
    elif temp > 30: tips.append("🔥 Сильная жара: используй кондиционер")
    elif temp > 25: tips.append("☀️ Жарко: проветривай салон")
    if wind > 20: tips.append("💨 УРАГАН: будь осторожен на мостах")
    elif wind > 15: tips.append("💨 Очень сильный ветер: крепче держи руль")
    elif wind > 10: tips.append("💨 Сильный ветер: внимательней при обгоне фур")
    if rain: tips.append("🌧️ ДОЖДЬ: включи фары, дистанция ×2")
    if snow: tips.append("🌨️ СНЕГОПАД: проверь резину, чисти снег")
    if 'гроза' in desc: tips.append("⛈️ ГРОЗА: пережди в безопасном месте")
    if 'туман' in desc: tips.append("🌫️ ТУМАН: противотуманки, снизь скорость")
    if humidity > 85: tips.append("💧 Высокая влажность: стекла могут потеть")
    if not tips: tips.append("✅ Погода благоприятная, хорошей дороги!")
    return "\n".join(tips[:4])

def format_weather_message(weather: dict) -> str:
    if not weather['success']:
        return f"❌ {weather['error']}"
    msg = f"🌍 *ПОГОДА В {weather['city'].upper()}*\n📅 {weather['time']}\n☁️ {weather['description'].capitalize()}\n"
    msg += f"🌡️ *{weather['temp']:.1f}°C* (ощущается {weather['feels_like']:.1f}°C)\n"
    msg += f"💧 Влажность: {weather['humidity']}%\n📊 Давление: {weather['pressure']:.1f} мм рт.ст.\n"
    msg += f"💨 Ветер: {weather['wind_speed']:.1f} м/с, {weather['wind_dir']}\n"
    msg += f"👁️ Видимость: {weather['visibility']:.1f} км\n☁️ Облачность: {weather['clouds']}%\n\n"
    msg += f"🚗 *СОВЕТЫ:*\n{get_driver_tips(weather['temp'], weather['wind_speed'], weather['humidity'], weather['description'], 'дождь' in weather['description'], 'снег' in weather['description'])}"
    return msg

def format_forecast_message(forecast_data: dict) -> str:
    if not forecast_data['success']:
        return f"❌ {forecast_data['error']}"
    msg = f"📅 *ПРОГНОЗ НА 5 ДНЕЙ - {forecast_data['city'].upper()}*\n━"*30 + "\n\n"
    today = datetime.now().date()
    for i, day in enumerate(forecast_data['forecasts']):
        day_date = day['date'].date()
        if day_date == today:
            header = "Сегодня"
        elif day_date == today + timedelta(days=1):
            header = f"Завтра ({get_russian_day(day['date'])})"
        else:
            header = get_russian_day(day['date'])
        msg += f"📌 *{header}* {day_date.strftime('%d.%m')}\n"
        msg += f"🌡️ {day['temp_min']:.0f}°C ~ {day['temp_max']:.0f}°C\n"
        msg += f"☁️ {day['description'].capitalize()}\n💨 Ветер до {day['wind_speed']:.0f} м/с\n"
        if day['rain']: msg += "🌧️ Дожди\n"
        if day['snow']: msg += "🌨️ Снег\n"
        tips = get_driver_tips(day['temp_day'], day['wind_speed'], day['humidity'], day['description'], day['rain'], day['snow'])
        msg += f"🚗 *Советы:* {tips}\n\n─"*20 + "\n\n"
    return msg

# ----- ОБРАБОТЧИКИ -----
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 *Добро пожаловать в WeatherBot для водителей!*\n\n"
        "🚗 Я даю погоду и советы.\n👇 Нажми кнопку или напиши город:",
        parse_mode="Markdown", reply_markup=get_main_keyboard()
    )

@dp.message(F.text == "🌤 Погода сейчас")
async def weather_now(message: Message):
    cid = message.chat.id
    if cid in user_cities:
        w = get_weather(user_cities[cid])
        await message.answer(format_weather_message(w), parse_mode="Markdown", reply_markup=get_weather_keyboard())
    else:
        await message.answer("🌆 Выберите город из списка или напишите его название.", parse_mode="Markdown", reply_markup=get_cities_keyboard())

@dp.message(F.text == "📅 Прогноз на 5 дней")
async def forecast_5days(message: Message):
    cid = message.chat.id
    if cid in user_cities:
        await message.answer("🔍 Получаю прогноз...", parse_mode="Markdown")
        f = get_5day_forecast(user_cities[cid])
        await message.answer(format_forecast_message(f), parse_mode="Markdown", reply_markup=get_weather_keyboard())
    else:
        await message.answer("🌆 Сначала установите город!", reply_markup=get_cities_keyboard())

@dp.message(F.text == "🚗 Советы водителю")
async def driver_tips(message: Message):
    await message.answer(
        "🚗 *ПОЛЕЗНЫЕ СОВЕТЫ*\n\n❄️ Зимой: щетка, аккумулятор, дистанция.\n"
        "🌧️ В дождь: фары, дворники, дистанция.\n☀️ В жару: антифриз, кондиционер.\n"
        "🌫️ В туман: противотуманки, снизить скорость.\n⚠️ Гололед: плавно, торможение двигателем.",
        parse_mode="Markdown", reply_markup=get_back_keyboard()
    )

@dp.message(F.text == "⚙️ Установить город")
async def set_city_prompt(message: Message):
    await message.answer("🌆 Напишите название города (например: Москва, Омск):", parse_mode="Markdown", reply_markup=get_back_keyboard())

@dp.message(F.text == "🔔 Подписка")
async def subscription_menu(message: Message):
    cid = message.chat.id
    city = user_cities.get(cid, "не установлен")
    sub_time = user_subscription_time.get(cid, "08:00")
    global CHAT_ID
    is_sub = (CHAT_ID and int(CHAT_ID) == cid)
    status = "✅ Активна" if is_sub else "❌ Не активна"
    await message.answer(
        f"🔔 *УПРАВЛЕНИЕ ПОДПИСКОЙ*\n\n🏙️ Город: *{city}*\n⏰ Время: *{sub_time}*\n📊 Статус: {status}\n\nВыберите действие:",
        parse_mode="Markdown", reply_markup=get_subscription_keyboard()
    )

@dp.message(F.text == "❓ Помощь")
async def help_menu(message: Message):
    await message.answer(
        "❓ *Помощь*\n🌤 Погода сейчас\n📅 Прогноз на 5 дней\n🚗 Советы\n⚙️ Установить город\n🔔 Подписка",
        parse_mode="Markdown", reply_markup=get_main_keyboard()
    )

@dp.message(F.text == "ℹ️ О боте")
async def about_bot(message: Message):
    await message.answer(
        "ℹ️ *О боте*\nВерсия 3.0\nДля водителей\nИсточник: OpenWeatherMap\nСоветы по погоде",
        parse_mode="Markdown", reply_markup=get_back_keyboard()
    )

@dp.message(F.text == "⬅️ Назад в меню")
@dp.message(F.text == "⬅️ Главное меню")
async def back_to_main_menu(message: Message):
    await message.answer("🔹 Главное меню", parse_mode="Markdown", reply_markup=get_main_keyboard())

@dp.message(F.text == "🔄 Обновить погоду")
async def refresh_weather(message: Message):
    cid = message.chat.id
    if cid in user_cities:
        w = get_weather(user_cities[cid])
        await message.answer(format_weather_message(w), parse_mode="Markdown", reply_markup=get_weather_keyboard())
    else:
        await message.answer("⚠️ Сначала установите город!", reply_markup=get_cities_keyboard())

@dp.message(F.text == "🌤 Другой город")
async def another_city(message: Message):
    await message.answer("🌆 Выберите город:", parse_mode="Markdown", reply_markup=get_cities_keyboard())

@dp.message(F.text == "✅ Подписаться")
async def handle_subscribe(message: Message):
    global CHAT_ID
    cid = message.chat.id
    if cid not in user_cities:
        await message.answer("⚠️ Сначала установите город!", reply_markup=get_main_keyboard())
        return
    CHAT_ID = str(cid)
    city = user_cities[cid]
    sub_time = user_subscription_time.get(cid, "08:00")
    await message.answer(f"✅ Вы подписаны!\nГород: {city}\nВремя: {sub_time}", parse_mode="Markdown", reply_markup=get_main_keyboard())

@dp.message(F.text == "❌ Отписаться")
async def handle_unsubscribe(message: Message):
    global CHAT_ID
    if CHAT_ID and int(CHAT_ID) == message.chat.id:
        CHAT_ID = None
        await message.answer("❌ Вы отписались от рассылки", parse_mode="Markdown")
    else:
        await message.answer("❌ Вы не были подписаны", parse_mode="Markdown")

@dp.message(F.text == "⏰ Выбрать время")
async def select_time(message: Message):
    await message.answer("⏰ Введите время в формате ЧЧ:ММ (например 08:00):", parse_mode="Markdown", reply_markup=get_back_keyboard())

@dp.message(F.text == "📊 Статус подписки")
async def subscription_status(message: Message):
    global CHAT_ID
    if CHAT_ID and int(CHAT_ID) == message.chat.id:
        city = user_cities.get(message.chat.id, "не установлен")
        sub_time = user_subscription_time.get(message.chat.id, "08:00")
        await message.answer(f"✅ Подписка активна\nГород: {city}\nВремя: {sub_time}", parse_mode="Markdown")
    else:
        await message.answer("❌ Подписка не активна", parse_mode="Markdown")

@dp.message(F.text.startswith(("🇷🇺", "Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань", "Омск", "Красноярск", "Владивосток")))
async def handle_city_button(message: Message):
    city = message.text.replace("🇷🇺 ", "").strip()
    cid = message.chat.id
    w = get_weather(city)
    if w['success']:
        user_cities[cid] = city
        await message.answer(format_weather_message(w), parse_mode="Markdown", reply_markup=get_weather_keyboard())
    else:
        await message.answer(f"❌ Не удалось получить погоду для {city}", reply_markup=get_cities_keyboard())

@dp.message()
async def handle_text(message: Message):
    text = message.text.strip()
    cid = message.chat.id
    if len(text) == 5 and text[2] == ':':
        try:
            h, m = int(text[:2]), int(text[3:])
            if 0 <= h <= 23 and 0 <= m <= 59:
                user_subscription_time[cid] = text
                await message.answer(f"✅ Время установлено: {text}", parse_mode="Markdown", reply_markup=get_subscription_keyboard())
                return
        except:
            pass
    w = get_weather(text)
    if w['success']:
        user_cities[cid] = text
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🌤 Погода сейчас"), KeyboardButton(text="📅 Прогноз на 5 дней")],
                      [KeyboardButton(text="⬅️ Главное меню")]],
            resize_keyboard=True
        )
        await message.answer(f"✅ Город {text} установлен!\nЧто хотите узнать?", parse_mode="Markdown", reply_markup=kb)
    else:
        await message.answer(f"❌ Город '{text}' не найден.", reply_markup=get_cities_keyboard())

# ----- ПЛАНИРОВЩИК (рабочий) -----
def send_daily_weather():
    if not CHAT_ID:
        return
    cid = int(CHAT_ID)
    city = user_cities.get(cid, "Москва")
    forecast = get_5day_forecast(city)
    asyncio.create_task(bot.send_message(chat_id=cid, text=format_forecast_message(forecast), parse_mode="Markdown"))

def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(30)

async def main():
    schedule.every().day.at("08:00").do(send_daily_weather)
    threading.Thread(target=run_schedule, daemon=True).start()
    print("\n" + "="*60)
    print("✅ БОТ УСПЕШНО ЗАПУЩЕН!")
    print("="*60)
    print("📅 Функции: текущая погода, прогноз на 5 дней, советы, подписка")
    print("🌐 Язык дней недели: РУССКИЙ")
    print("="*60 + "\n")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

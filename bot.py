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

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')
CHAT_ID = os.getenv('CHAT_ID')

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

user_cities = {}
user_subscription_time = {}
user_car_data = {}

logging.basicConfig(level=logging.INFO)

# --------------------------------------------------------------
# ПРЕОБРАЗОВАНИЕ ГОРОДОВ
# --------------------------------------------------------------
RUS_TO_LAT = {
    'москва': 'Moscow', 'санкт-петербург': 'Saint Petersburg',
    'новосибирск': 'Novosibirsk', 'екатеринбург': 'Ekaterinburg',
    'казань': 'Kazan', 'омск': 'Omsk', 'красноярск': 'Krasnoyarsk',
    'владивосток': 'Vladivostok'
}

def city_to_latin(city_name: str) -> str:
    if city_name.startswith('🇷🇺 '):
        city_name = city_name[4:]
    city_lower = city_name.lower().strip()
    if city_lower in RUS_TO_LAT:
        return RUS_TO_LAT[city_lower]
    # простая транслитерация
    translit = {'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z',
                'и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r',
                'с':'s','т':'t','у':'u','ф':'f','х':'kh','ц':'ts','ч':'ch','ш':'sh',
                'щ':'shch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'}
    result = ''
    for ch in city_lower:
        result += translit.get(ch, ch)
    return result.title()

# --------------------------------------------------------------
# БАЗА АВТО
# --------------------------------------------------------------
CARS_DB = {
    'Toyota Vitz': {'price_new': 800000, 'reliability': 92, 'fuel': 6.5},
    'Toyota Corolla': {'price_new': 2000000, 'reliability': 95, 'fuel': 7.5},
    'KIA Rio': {'price_new': 1300000, 'reliability': 85, 'fuel': 7.3},
    'Hyundai Solaris': {'price_new': 1280000, 'reliability': 85, 'fuel': 7.2},
    'Lada Granta': {'price_new': 800000, 'reliability': 65, 'fuel': 7.0},
    'Volkswagen Polo': {'price_new': 1350000, 'reliability': 80, 'fuel': 7.2},
}

# --------------------------------------------------------------
# ФУНКЦИИ ПОГОДЫ
# --------------------------------------------------------------
def get_weather(city: str) -> dict:
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if resp.status_code == 200:
            return {
                'success': True, 'city': city,
                'temp': data['main']['temp'],
                'feels_like': data['main']['feels_like'],
                'humidity': data['main']['humidity'],
                'wind_speed': data['wind']['speed'],
                'description': data['weather'][0]['description'],
                'time': datetime.now().strftime('%d.%m.%Y %H:%M')
            }
        else:
            return {'success': False, 'error': 'Город не найден'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def get_5day_forecast(city: str) -> dict:
    try:
        url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if resp.status_code == 200:
            daily = {}
            for item in data['list']:
                dt = datetime.fromtimestamp(item['dt'])
                key = dt.strftime('%Y-%m-%d')
                if key not in daily:
                    daily[key] = {'temps': [], 'desc': [], 'wind': [], 'hum': [], 'rain': False, 'date': dt}
                daily[key]['temps'].append(item['main']['temp'])
                daily[key]['desc'].append(item['weather'][0]['description'])
                daily[key]['wind'].append(item['wind']['speed'])
                daily[key]['hum'].append(item['main']['humidity'])
                if item.get('rain', {}).get('3h', 0) > 0:
                    daily[key]['rain'] = True
            forecasts = []
            for key, d in list(daily.items())[:5]:
                forecasts.append({
                    'date': d['date'],
                    'temp_max': max(d['temps']),
                    'temp_min': min(d['temps']),
                    'temp_day': sum(d['temps'])/len(d['temps']),
                    'description': max(set(d['desc']), key=d['desc'].count),
                    'wind_speed': max(d['wind']),
                    'humidity': sum(d['hum'])/len(d['hum']),
                    'rain': d['rain']
                })
            return {'success': True, 'city': city, 'forecasts': forecasts}
        else:
            return {'success': False, 'error': 'Город не найден'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def get_driver_tips(temp, wind, hum, desc, rain):
    tips = []
    if temp < 0: tips.append("⚠️ Гололёд, осторожно")
    if temp > 30: tips.append("🔥 Жара, проверьте охлаждение")
    if wind > 15: tips.append("💨 Сильный ветер, держите руль крепче")
    if rain: tips.append("🌧️ Дождь, дистанция больше")
    if not tips: tips.append("✅ Погода благоприятная")
    return ", ".join(tips)

def format_weather(w):
    if not w['success']: return f"❌ {w['error']}"
    return (f"🌍 *{w['city'].upper()}* {w['time']}\n"
            f"🌡️ {w['temp']:.0f}°C (ощущается {w['feels_like']:.0f}°C)\n"
            f"💧 Влажность {w['humidity']}%, 💨 {w['wind_speed']:.0f} м/с\n"
            f"☁️ {w['description']}\n\n"
            f"🚗 *Совет:* {get_driver_tips(w['temp'], w['wind_speed'], w['humidity'], w['description'], False)}")

def format_forecast(f):
    if not f['success']: return f"❌ {f['error']}"
    ru_days = {'Monday':'Пн','Tuesday':'Вт','Wednesday':'Ср','Thursday':'Чт','Friday':'Пт','Saturday':'Сб','Sunday':'Вс'}
    msg = f"📅 *ПРОГНОЗ НА 5 ДНЕЙ - {f['city'].upper()}*\n━━━━━━━━━━━━━━━━━━━━━━\n"
    today = datetime.now().date()
    for day in f['forecasts']:
        d = day['date'].date()
        if d == today: header = "Сегодня"
        elif d == today + timedelta(days=1): header = "Завтра"
        else: header = ru_days.get(day['date'].strftime('%A'), day['date'].strftime('%A'))
        msg += f"\n📌 *{header}* {d.strftime('%d.%m')}\n🌡️ {day['temp_min']:.0f}~{day['temp_max']:.0f}°C\n"
        msg += f"☁️ {day['description']}\n💨 Ветер до {day['wind_speed']:.0f} м/с\n"
        if day['rain']: msg += "🌧️ Дождь\n"
        advice = get_driver_tips(day['temp_day'], day['wind_speed'], day['humidity'], day['description'], day['rain'])
        msg += f"🚗 *Совет:* {advice}\n"
    return msg

# --------------------------------------------------------------
# ОЦЕНКА АВТО
# --------------------------------------------------------------
def calc_car(model, year, km):
    age = datetime.now().year - year
    specs = CARS_DB.get(model, {'price_new': 1000000, 'reliability': 70})
    base = specs['price_new']
    depr = min(0.5, age*0.05 + (km/10000)*0.002)
    price = base * (1 - depr) * 1.55  # наценка рынка
    price = max(50000, min(base, int(price/1000)*1000))
    return f"🚗 *{model}*\n📅 {year} г. / {km:,} км\n💰 Цена: *{price:,} ₽*\n📊 Надёжность: {specs['reliability']}/100"

# --------------------------------------------------------------
# КЛАВИАТУРЫ
# --------------------------------------------------------------
def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🌤 Погода сейчас"), KeyboardButton(text="📅 Прогноз на 5 дней")],
        [KeyboardButton(text="🚗 Советы"), KeyboardButton(text="🚘 Оценить авто")],
        [KeyboardButton(text="🌆 Город"), KeyboardButton(text="🔔 Подписка")],
        [KeyboardButton(text="❓ Помощь")]
    ], resize_keyboard=True)

def cities_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🇷🇺 Москва"), KeyboardButton(text="🇷🇺 Санкт-Петербург")],
        [KeyboardButton(text="🇷🇺 Новосибирск"), KeyboardButton(text="🇷🇺 Екатеринбург")],
        [KeyboardButton(text="🇷🇺 Казань"), KeyboardButton(text="🇷🇺 Омск")],
        [KeyboardButton(text="🇷🇺 Красноярск"), KeyboardButton(text="🇷🇺 Владивосток")],
        [KeyboardButton(text="⬅️ Назад")]
    ], resize_keyboard=True)

def sub_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="✅ Подписаться"), KeyboardButton(text="❌ Отписаться")],
        [KeyboardButton(text="⏰ Время"), KeyboardButton(text="📊 Статус")],
        [KeyboardButton(text="⬅️ Назад")]
    ], resize_keyboard=True)

def back_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True)

# --------------------------------------------------------------
# ОБРАБОТЧИКИ
# --------------------------------------------------------------
@dp.message(Command("start"))
async def start(msg: Message):
    await msg.answer("Добро пожаловать! Выберите действие:", reply_markup=main_kb())

@dp.message(F.text == "🌤 Погода сейчас")
async def now_weather(msg: Message):
    cid = msg.chat.id
    if cid not in user_cities:
        await msg.answer("Сначала выберите город через кнопку \"🌆 Город\"")
        return
    w = await asyncio.to_thread(get_weather, user_cities[cid])
    await msg.answer(format_weather(w), parse_mode="Markdown", reply_markup=main_kb())

@dp.message(F.text == "📅 Прогноз на 5 дней")
async def forecast(msg: Message):
    cid = msg.chat.id
    if cid not in user_cities:
        await msg.answer("Сначала выберите город через кнопку \"🌆 Город\"")
        return
    f = await asyncio.to_thread(get_5day_forecast, user_cities[cid])
    await msg.answer(format_forecast(f), parse_mode="Markdown", reply_markup=main_kb())

@dp.message(F.text == "🚗 Советы")
async def tips(msg: Message):
    await msg.answer("❄️ Зимой проверьте аккумулятор\n🌧️ В дождь включите фары\n🌫️ В туман снизьте скорость", reply_markup=main_kb())

@dp.message(F.text == "🌆 Город")
async def choose_city_prompt(msg: Message):
    await msg.answer("Выберите город из списка или напишите название:", reply_markup=cities_kb())

@dp.message(F.text == "🔔 Подписка")
async def sub_menu(msg: Message):
    await msg.answer("Настройка рассылки:", reply_markup=sub_kb())

@dp.message(F.text == "✅ Подписаться")
async def subscribe(msg: Message):
    global CHAT_ID
    cid = msg.chat.id
    if cid not in user_cities:
        await msg.answer("Сначала установите город через кнопку \"🌆 Город\"", reply_markup=main_kb())
        return
    CHAT_ID = str(cid)
    await msg.answer("Вы подписаны на ежедневный прогноз в 08:00", reply_markup=main_kb())

@dp.message(F.text == "❌ Отписаться")
async def unsubscribe(msg: Message):
    global CHAT_ID
    if CHAT_ID and int(CHAT_ID) == msg.chat.id:
        CHAT_ID = None
        await msg.answer("Вы отписались", reply_markup=main_kb())
    else:
        await msg.answer("Вы не были подписаны", reply_markup=main_kb())

@dp.message(F.text == "⏰ Время")
async def set_time(msg: Message):
    await msg.answer("Введите время в формате ЧЧ:ММ, например 08:00", reply_markup=back_kb())

@dp.message(F.text == "📊 Статус")
async def status(msg: Message):
    global CHAT_ID
    if CHAT_ID and int(CHAT_ID) == msg.chat.id:
        city = user_cities.get(msg.chat.id, "не задан")
        time = user_subscription_time.get(msg.chat.id, "08:00")
        await msg.answer(f"✅ Подписка активна\nГород: {city}\nВремя: {time}", reply_markup=main_kb())
    else:
        await msg.answer("❌ Подписка не активна", reply_markup=main_kb())

@dp.message(F.text == "❓ Помощь")
async def help(msg: Message):
    txt = ("🌤 Погода сейчас – текущая погода с советами\n"
           "📅 Прогноз на 5 дней – подробный прогноз\n"
           "🚗 Советы – общие рекомендации\n"
           "🚘 Оценить авто – расчёт цены\n"
           "🌆 Город – выбор города\n"
           "🔔 Подписка – ежедневная рассылка")
    await msg.answer(txt, reply_markup=main_kb())

@dp.message(F.text == "🚘 Оценить авто")
async def eval_car_start(msg: Message):
    user_car_data[msg.chat.id] = {}
    await msg.answer("Введите год выпуска (4 цифры):", reply_markup=back_kb())

@dp.message(F.text == "⬅️ Назад")
async def go_back(msg: Message):
    user_car_data.pop(msg.chat.id, None)
    await msg.answer("Главное меню", reply_markup=main_kb())

# --- Обработка выбора города и ручного ввода ---
@dp.message(F.text.startswith(("🇷🇺", "Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань", "Омск", "Красноярск", "Владивосток")))
async def city_button(msg: Message):
    city_ru = msg.text.strip()
    city_lat = city_to_latin(city_ru)
    w = await asyncio.to_thread(get_weather, city_lat)
    if w['success']:
        user_cities[msg.chat.id] = city_lat
        await msg.answer(f"Город {city_ru} установлен!", reply_markup=main_kb())
        await msg.answer(format_weather(w), parse_mode="Markdown")
    else:
        await msg.answer(f"Не удалось найти {city_ru}. Попробуйте написать на латинице, например Omsk", reply_markup=cities_kb())

# --- Универсальный обработчик для ввода года, пробега, времени и города ---
@dp.message()
async def handle_text(msg: Message):
    cid = msg.chat.id
    text = msg.text.strip()
    # Логирование для отладки
    print(f"Получено сообщение: '{text}' от {cid}")

    # Режим оценки авто
    if cid in user_car_data:
        data = user_car_data[cid]
        if 'year' not in data:
            if text.isdigit() and 1970 <= int(text) <= datetime.now().year:
                data['year'] = int(text)
                await msg.answer("Введите пробег в тысячах км (например 110):")
            else:
                await msg.answer("Ошибка: введите год от 1970 до текущего")
        elif 'km' not in data:
            try:
                km = int(text)
                if 0 <= km <= 800:
                    data['km'] = km * 1000
                    # показать клавиатуру с моделями
                    car_kb = ReplyKeyboardMarkup(keyboard=[
                        [KeyboardButton(text="Toyota Vitz"), KeyboardButton(text="Toyota Corolla")],
                        [KeyboardButton(text="KIA Rio"), KeyboardButton(text="Hyundai Solaris")],
                        [KeyboardButton(text="Lada Granta"), KeyboardButton(text="Volkswagen Polo")],
                        [KeyboardButton(text="⬅️ Назад")]
                    ], resize_keyboard=True)
                    await msg.answer("Выберите модель:", reply_markup=car_kb)
                else:
                    await msg.answer("Пробег должен быть от 0 до 800 тыс. км")
            except:
                await msg.answer("Введите число")
        else:
            # выбранная модель
            if text in CARS_DB:
                car = text
                result = calc_car(car, data['year'], data['km'])
                await msg.answer(result, parse_mode="Markdown", reply_markup=main_kb())
                del user_car_data[cid]
            else:
                await msg.answer("Выберите модель из списка", reply_markup=main_kb())
        return

    # Установка времени подписки
    if len(text) == 5 and text[2] == ':' and text[:2].isdigit() and text[3:].isdigit():
        h, m = int(text[:2]), int(text[3:])
        if 0 <= h <= 23 and 0 <= m <= 59:
            user_subscription_time[cid] = text
            await msg.answer(f"Время рассылки установлено: {text}", reply_markup=sub_kb())
        else:
            await msg.answer("Неверный формат")
        return

    # Если ни одно из выше – пробуем как город, но только если не похоже на команду
    if not text.startswith('/'):
        city_lat = city_to_latin(text)
        w = await asyncio.to_thread(get_weather, city_lat)
        if w['success']:
            user_cities[cid] = city_lat
            await msg.answer(f"Город {text} установлен!", reply_markup=main_kb())
            await msg.answer(format_weather(w), parse_mode="Markdown")
        else:
            await msg.answer("Не понял. Используйте кнопки меню или напишите название города (Москва, Omsk)", reply_markup=main_kb())
    else:
        await msg.answer("Неизвестная команда. Нажмите /start для меню.", reply_markup=main_kb())

# --------------------------------------------------------------
# РАССЫЛКА
# --------------------------------------------------------------
def send_daily():
    if not CHAT_ID:
        return
    cid = int(CHAT_ID)
    city = user_cities.get(cid, "Moscow")
    f = get_5day_forecast(city)
    if f['success']:
        asyncio.create_task(bot.send_message(cid, format_forecast(f), parse_mode="Markdown"))

def schedule_loop():
    schedule.every().day.at("08:00").do(send_daily)
    while True:
        schedule.run_pending()
        time.sleep(30)

# --------------------------------------------------------------
# ЗАПУСК
# --------------------------------------------------------------
async def main():
    threading.Thread(target=schedule_loop, daemon=True).start()
    print("Бот запущен. Кнопки меню должны работать.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

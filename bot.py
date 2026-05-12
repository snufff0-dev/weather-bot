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
# ПРЕОБРАЗОВАНИЕ РУССКИХ НАЗВАНИЙ ГОРОДОВ В ЛАТИНИЦУ
# --------------------------------------------------------------
RUS_TO_LAT = {
    'москва': 'Moscow',
    'санкт-петербург': 'Saint Petersburg',
    'новосибирск': 'Novosibirsk',
    'екатеринбург': 'Ekaterinburg',
    'казань': 'Kazan',
    'омск': 'Omsk',
    'красноярск': 'Krasnoyarsk',
    'владивосток': 'Vladivostok'
}

def city_to_latin(city_name: str) -> str:
    # Удаляем флаг, если есть
    if city_name.startswith('🇷🇺 '):
        city_name = city_name[4:]
    city_lower = city_name.strip().lower()
    if city_lower in RUS_TO_LAT:
        return RUS_TO_LAT[city_lower]
    # Транслитерация для других городов (простая)
    translit = {
        'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z',
        'и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r',
        'с':'s','т':'t','у':'u','ф':'f','х':'kh','ц':'ts','ч':'ch','ш':'sh',
        'щ':'shch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'
    }
    result = ''
    for ch in city_lower:
        result += translit.get(ch, ch)
    return result.title()

# --------------------------------------------------------------
# БАЗА АВТОМОБИЛЕЙ (расширенная)
# --------------------------------------------------------------
CARS_DB = {
    'Toyota Vitz': {'price_new': 800000, 'reliability': 92, 'fuel': 6.5},
    'Toyota Corolla': {'price_new': 2000000, 'reliability': 95, 'fuel': 7.5},
    'Toyota Camry': {'price_new': 3500000, 'reliability': 95, 'fuel': 8.5},
    'KIA Rio': {'price_new': 1300000, 'reliability': 85, 'fuel': 7.3},
    'Hyundai Solaris': {'price_new': 1280000, 'reliability': 85, 'fuel': 7.2},
    'Lada Vesta': {'price_new': 1200000, 'reliability': 70, 'fuel': 7.5},
    'Lada Granta': {'price_new': 800000, 'reliability': 65, 'fuel': 7.0},
    'Volkswagen Polo': {'price_new': 1350000, 'reliability': 80, 'fuel': 7.2},
    'Chery Tiggo T11': {'price_new': 800000, 'reliability': 65, 'fuel': 9.5}
}

# --------------------------------------------------------------
# ФУНКЦИИ ПОГОДЫ (синхронные, вызываются в потоках)
# --------------------------------------------------------------
def get_weather(city: str) -> dict:
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
        r = requests.get(url, timeout=10)
        data = r.json()
        if r.status_code == 200:
            return {
                'success': True,
                'city': city,
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
        r = requests.get(url, timeout=10)
        data = r.json()
        if r.status_code == 200:
            daily = {}
            for item in data['list']:
                dt = datetime.fromtimestamp(item['dt'])
                key = dt.strftime('%Y-%m-%d')
                if key not in daily:
                    daily[key] = {
                        'temps': [], 'desc': [], 'wind': [], 'hum': [],
                        'rain': False, 'date': dt
                    }
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
                    'temp_day': sum(d['temps']) / len(d['temps']),
                    'description': max(set(d['desc']), key=d['desc'].count),
                    'wind_speed': max(d['wind']),
                    'humidity': sum(d['hum']) / len(d['hum']),
                    'rain': d['rain']
                })
            return {'success': True, 'city': city, 'forecasts': forecasts}
        else:
            return {'success': False, 'error': 'Город не найден'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def get_driver_tips(temp, wind, hum, desc, rain):
    tips = []
    if temp < 0: tips.append("⚠️ Гололёд, осторожно, дистанция больше")
    if temp > 30: tips.append("🔥 Жара, проверьте охлаждение двигателя")
    if wind > 15: tips.append("💨 Сильный ветер, крепче держите руль")
    if rain: tips.append("🌧️ Дождь, включите фары, увеличьте дистанцию")
    if 'туман' in desc: tips.append("🌫️ Туман, используйте противотуманки")
    if not tips: tips.append("✅ Погода благоприятная, хорошей дороги!")
    return "\n".join(tips[:3])

def format_weather(w):
    if not w['success']:
        return f"❌ {w['error']}"
    return (f"🌍 *{w['city'].upper()}* {w['time']}\n"
            f"🌡️ {w['temp']:.0f}°C (ощущается {w['feels_like']:.0f}°C)\n"
            f"💧 Влажность {w['humidity']}%, 💨 {w['wind_speed']:.0f} м/с\n"
            f"☁️ {w['description'].capitalize()}\n\n"
            f"🚗 *Совет:* {get_driver_tips(w['temp'], w['wind_speed'], w['humidity'], w['description'], False)}")

def format_forecast(f):
    if not f['success']:
        return f"❌ {f['error']}"
    ru_days = {'Monday':'Пн','Tuesday':'Вт','Wednesday':'Ср','Thursday':'Чт','Friday':'Пт','Saturday':'Сб','Sunday':'Вс'}
    msg = f"📅 *ПРОГНОЗ НА 5 ДНЕЙ - {f['city'].upper()}*\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
    today = datetime.now().date()
    for day in f['forecasts']:
        d = day['date'].date()
        if d == today:
            header = "Сегодня"
        elif d == today + timedelta(days=1):
            header = "Завтра"
        else:
            header = ru_days.get(day['date'].strftime('%A'), day['date'].strftime('%A'))
        msg += f"\n📌 *{header}* {d.strftime('%d.%m')}\n"
        msg += f"🌡️ {day['temp_min']:.0f}°C ~ {day['temp_max']:.0f}°C\n"
        msg += f"☁️ {day['description'].capitalize()}\n"
        msg += f"💨 Ветер до {day['wind_speed']:.0f} м/с\n"
        if day['rain']:
            msg += "🌧️ Дождь\n"
        tips = get_driver_tips(day['temp_day'], day['wind_speed'], day['humidity'], day['description'], day['rain'])
        msg += f"🚗 *Совет:* {tips}\n"
    return msg

# --------------------------------------------------------------
# ОЦЕНКА АВТОМОБИЛЯ
# --------------------------------------------------------------
def calc_car_value(model, year, km):
    age = datetime.now().year - year
    specs = CARS_DB.get(model, {'price_new': 1000000, 'reliability': 70})
    base = specs['price_new']
    depr = min(0.5, age * 0.05 + (km / 10000) * 0.002)
    price = base * (1 - depr) * 1.55  # рыночная наценка
    price = max(50000, min(base, int(price / 1000) * 1000))
    return (f"🚗 *{model}*\n"
            f"📅 {year} г. / {km:,} км\n"
            f"💰 Рыночная цена: *{price:,} ₽*\n"
            f"📊 Надёжность: {specs['reliability']}/100\n"
            f"⛽ Расход: {specs['fuel']} л/100 км\n\n"
            f"💡 Перед покупкой проверьте кузов на коррозию и двигатель.")

# --------------------------------------------------------------
# КЛАВИАТУРЫ
# --------------------------------------------------------------
def main_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🌤 Погода сейчас"), KeyboardButton(text="📅 Прогноз на 5 дней")],
        [KeyboardButton(text="🚗 Советы"), KeyboardButton(text="🚘 Оценить авто")],
        [KeyboardButton(text="🌆 Город"), KeyboardButton(text="🔔 Подписка")],
        [KeyboardButton(text="❓ Помощь")]
    ], resize_keyboard=True)

def cities_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🇷🇺 Москва"), KeyboardButton(text="🇷🇺 Санкт-Петербург")],
        [KeyboardButton(text="🇷🇺 Новосибирск"), KeyboardButton(text="🇷🇺 Екатеринбург")],
        [KeyboardButton(text="🇷🇺 Казань"), KeyboardButton(text="🇷🇺 Омск")],
        [KeyboardButton(text="🇷🇺 Красноярск"), KeyboardButton(text="🇷🇺 Владивосток")],
        [KeyboardButton(text="⬅️ Назад")]
    ], resize_keyboard=True)

def sub_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="✅ Подписаться"), KeyboardButton(text="❌ Отписаться")],
        [KeyboardButton(text="⏰ Время"), KeyboardButton(text="📊 Статус")],
        [KeyboardButton(text="⬅️ Назад")]
    ], resize_keyboard=True)

def back_keyboard():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True)

def car_model_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Toyota Vitz"), KeyboardButton(text="Toyota Corolla")],
        [KeyboardButton(text="KIA Rio"), KeyboardButton(text="Hyundai Solaris")],
        [KeyboardButton(text="Lada Granta"), KeyboardButton(text="Volkswagen Polo")],
        [KeyboardButton(text="⬅️ Назад")]
    ], resize_keyboard=True)

# --------------------------------------------------------------
# ОБРАБОТЧИКИ
# --------------------------------------------------------------
@dp.message(Command("start"))
async def start_cmd(msg: Message):
    await msg.answer("👋 Привет! Я бот для водителей:\n- Погода с советами\n- Прогноз на 5 дней\n- Оценка авто при покупке\n\nВыберите действие:", reply_markup=main_keyboard())

# ----- Основные кнопки меню -----
@dp.message(F.text == "🌤 Погода сейчас")
async def now_weather(msg: Message):
    cid = msg.chat.id
    if cid not in user_cities:
        await msg.answer("Сначала выберите город через кнопку 🌆 Город", reply_markup=cities_keyboard())
        return
    w = await asyncio.to_thread(get_weather, user_cities[cid])
    await msg.answer(format_weather(w), parse_mode="Markdown", reply_markup=main_keyboard())

@dp.message(F.text == "📅 Прогноз на 5 дней")
async def forecast_5(msg: Message):
    cid = msg.chat.id
    if cid not in user_cities:
        await msg.answer("Сначала выберите город через кнопку 🌆 Город", reply_markup=cities_keyboard())
        return
    f = await asyncio.to_thread(get_5day_forecast, user_cities[cid])
    await msg.answer(format_forecast(f), parse_mode="Markdown", reply_markup=main_keyboard())

@dp.message(F.text == "🚗 Советы")
async def tips(msg: Message):
    await msg.answer("❄️ *Зимой*: проверьте аккумулятор, используйте зимнюю резину, увеличьте дистанцию.\n🌧️ *В дождь*: включите ближний свет, не влетайте в лужи.\n🌫️ *В туман*: противотуманные фары, снизьте скорость.\n⚠️ *Гололёд*: избегайте резких движений, тормозите двигателем.", parse_mode="Markdown", reply_markup=main_keyboard())

@dp.message(F.text == "🌆 Город")
async def city_menu(msg: Message):
    await msg.answer("Выберите город из списка или напишите его название:", reply_markup=cities_keyboard())

@dp.message(F.text == "🔔 Подписка")
async def sub_menu(msg: Message):
    await msg.answer("Настройте ежедневную рассылку прогноза:", reply_markup=sub_keyboard())

@dp.message(F.text == "✅ Подписаться")
async def subscribe(msg: Message):
    global CHAT_ID
    cid = msg.chat.id
    if cid not in user_cities:
        await msg.answer("Сначала установите город через кнопку 🌆 Город", reply_markup=main_keyboard())
        return
    CHAT_ID = str(cid)
    await msg.answer("✅ Вы подписаны на ежедневный прогноз в 08:00", reply_markup=main_keyboard())

@dp.message(F.text == "❌ Отписаться")
async def unsubscribe(msg: Message):
    global CHAT_ID
    if CHAT_ID and int(CHAT_ID) == msg.chat.id:
        CHAT_ID = None
        await msg.answer("❌ Вы отписались от рассылки", reply_markup=main_keyboard())
    else:
        await msg.answer("❌ Вы не были подписаны", reply_markup=main_keyboard())

@dp.message(F.text == "⏰ Время")
async def set_time_prompt(msg: Message):
    await msg.answer("Введите время в формате ЧЧ:ММ (например, 08:00)", reply_markup=back_keyboard())

@dp.message(F.text == "📊 Статус")
async def sub_status(msg: Message):
    global CHAT_ID
    if CHAT_ID and int(CHAT_ID) == msg.chat.id:
        city = user_cities.get(msg.chat.id, "не установлен")
        cur_time = user_subscription_time.get(msg.chat.id, "08:00")
        await msg.answer(f"✅ Подписка активна\n🏙️ Город: {city}\n⏰ Время: {cur_time}", reply_markup=main_keyboard())
    else:
        await msg.answer("❌ Подписка не активна", reply_markup=main_keyboard())

@dp.message(F.text == "🚘 Оценить авто")
async def eval_start(msg: Message):
    user_car_data[msg.chat.id] = {}
    await msg.answer("Шаг 1: Введите **год выпуска** (4 цифры, например 2010):", parse_mode="Markdown", reply_markup=back_keyboard())

@dp.message(F.text == "❓ Помощь")
async def help_msg(msg: Message):
    await msg.answer(
        "📋 *Доступные команды:*\n"
        "🌤 Погода сейчас – текущая погода с советами\n"
        "📅 Прогноз на 5 дней – подробный прогноз\n"
        "🚗 Советы – рекомендации водителю\n"
        "🚘 Оценить авто – расчёт рыночной цены\n"
        "🌆 Город – выбрать или ввести город\n"
        "🔔 Подписка – ежедневная рассылка\n\n"
        "Также можно просто написать название города (Москва, Omsk).",
        parse_mode="Markdown", reply_markup=main_keyboard()
    )

@dp.message(F.text == "⬅️ Назад")
async def go_back(msg: Message):
    # Очищаем данные оценки авто, если они были
    user_car_data.pop(msg.chat.id, None)
    await msg.answer("Главное меню", reply_markup=main_keyboard())

# ----- Обработка выбора города из кнопок (с флагом и без) -----
@dp.message(F.text.startswith(("🇷🇺", "Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань", "Омск", "Красноярск", "Владивосток")))
async def city_button_handler(msg: Message):
    city_ru = msg.text.strip()
    city_lat = city_to_latin(city_ru)
    w = await asyncio.to_thread(get_weather, city_lat)
    if w['success']:
        user_cities[msg.chat.id] = city_lat
        await msg.answer(f"✅ Город {city_ru} установлен!", reply_markup=main_keyboard())
        await msg.answer(format_weather(w), parse_mode="Markdown")
    else:
        await msg.answer(f"❌ Город '{city_ru}' не найден. Попробуйте написать на латинице (например, Omsk).", reply_markup=cities_keyboard())

# ----- Обработка ручного ввода города и других текстов -----
@dp.message()
async def text_handler(msg: Message):
    cid = msg.chat.id
    text = msg.text.strip()

    # Режим оценки авто
    if cid in user_car_data:
        data = user_car_data[cid]
        if 'year' not in data:
            if text.isdigit() and 1970 <= int(text) <= datetime.now().year:
                data['year'] = int(text)
                await msg.answer("Шаг 2: Введите пробег в **тысячах км** (например, 110):", parse_mode="Markdown")
            else:
                await msg.answer("❌ Введите год цифрами от 1970 до текущего")
        elif 'km' not in data:
            try:
                km = int(text)
                if 0 <= km <= 800:
                    data['km'] = km * 1000
                    await msg.answer("Шаг 3: Выберите модель автомобиля:", reply_markup=car_model_keyboard())
                else:
                    await msg.answer("❌ Пробег должен быть от 0 до 800 тыс. км")
            except ValueError:
                await msg.answer("❌ Введите пробег цифрами")
        else:
            if text in CARS_DB:
                model = text
                result = calc_car_value(model, data['year'], data['km'])
                await msg.answer(result, parse_mode="Markdown", reply_markup=main_keyboard())
                del user_car_data[cid]
            else:
                await msg.answer("❌ Модель не найдена. Выберите из списка.", reply_markup=car_model_keyboard())
        return

    # Установка времени подписки
    if len(text) == 5 and text[2] == ':' and text[:2].isdigit() and text[3:].isdigit():
        h, m = int(text[:2]), int(text[3:])
        if 0 <= h <= 23 and 0 <= m <= 59:
            user_subscription_time[cid] = text
            await msg.answer(f"✅ Время рассылки установлено: {text}", reply_markup=sub_keyboard())
        else:
            await msg.answer("❌ Неверный формат времени")
        return

    # Если текст похож на команду или левый ввод – игнорируем, кроме городов
    if text.startswith('/'):
        await msg.answer("Неизвестная команда. Используйте кнопки меню или напишите город.", reply_markup=main_keyboard())
        return

    # Пробуем как город
    city_lat = city_to_latin(text)
    w = await asyncio.to_thread(get_weather, city_lat)
    if w['success']:
        user_cities[cid] = city_lat
        await msg.answer(f"✅ Город {text} установлен!", reply_markup=main_keyboard())
        await msg.answer(format_weather(w), parse_mode="Markdown")
    else:
        await msg.answer(f"❌ Город '{text}' не найден. Попробуйте выбрать из списка или написать на латинице (Omsk).", reply_markup=cities_keyboard())

# --------------------------------------------------------------
# ЕЖЕДНЕВНАЯ РАССЫЛКА (в 08:00)
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
    print("Бот запущен. Город Омск теперь находится, кнопки меню работают.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

import os
import logging
import asyncio
import threading
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
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
user_car_data = {}  # для хранения данных оценки авто

# ---------- ПЕРЕВОД РУССКИХ ГОРОДОВ В ЛАТИНИЦУ ----------
RUS_TO_LAT = {
    'москва': 'Moscow', 'санкт-петербург': 'Saint Petersburg',
    'новосибирск': 'Novosibirsk', 'екатеринбург': 'Ekaterinburg',
    'казань': 'Kazan', 'омск': 'Omsk', 'красноярск': 'Krasnoyarsk',
    'владивосток': 'Vladivostok'
}

def city_to_latin(name: str) -> str:
    if name.startswith('🇷🇺 '):
        name = name[4:]
    low = name.strip().lower()
    if low in RUS_TO_LAT:
        return RUS_TO_LAT[low]
    return name

# ---------- ФУНКЦИИ ПОГОДЫ ----------
def get_weather(city: str):
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
        r = requests.get(url, timeout=10)
        data = r.json()
        if r.status_code == 200:
            return {
                'ok': True, 'city': city,
                'temp': data['main']['temp'],
                'feels': data['main']['feels_like'],
                'hum': data['main']['humidity'],
                'wind': data['wind']['speed'],
                'desc': data['weather'][0]['description'],
                'time': datetime.now().strftime('%d.%m.%Y %H:%M')
            }
        else:
            return {'ok': False, 'error': 'Город не найден'}
    except Exception as e:
        return {'ok': False, 'error': str(e)}

def get_5day_forecast(city: str):
    try:
        url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
        r = requests.get(url, timeout=10)
        data = r.json()
        if r.status_code != 200:
            return {'ok': False, 'error': 'Город не найден'}
        daily = {}
        for item in data['list']:
            dt = datetime.fromtimestamp(item['dt'])
            key = dt.strftime('%Y-%m-%d')
            if key not in daily:
                daily[key] = {'temps': [], 'desc': [], 'wind': [], 'rain': False, 'date': dt}
            daily[key]['temps'].append(item['main']['temp'])
            daily[key]['desc'].append(item['weather'][0]['description'])
            daily[key]['wind'].append(item['wind']['speed'])
            if item.get('rain', {}).get('3h', 0) > 0:
                daily[key]['rain'] = True
        forecasts = []
        for k, v in list(daily.items())[:5]:
            forecasts.append({
                'date': v['date'],
                't_max': max(v['temps']),
                't_min': min(v['temps']),
                't_avg': sum(v['temps'])/len(v['temps']),
                'desc': max(set(v['desc']), key=v['desc'].count),
                'wind': max(v['wind']),
                'rain': v['rain']
            })
        return {'ok': True, 'city': city, 'forecasts': forecasts}
    except Exception as e:
        return {'ok': False, 'error': str(e)}

def driver_tips(temp, wind, desc, rain):
    tips = []
    if temp < 0:
        tips.append("⚠️ Гололед, дистанция больше")
    if temp > 30:
        tips.append("🔥 Жара, проверьте охлаждение")
    if wind > 15:
        tips.append("💨 Сильный ветер, крепче держите руль")
    if rain:
        tips.append("🌧️ Дождь, включите фары")
    if 'туман' in desc:
        tips.append("🌫️ Туман, используйте противотуманки")
    if not tips:
        tips.append("✅ Хорошей дороги!")
    return " ".join(tips[:3])

def format_weather(w):
    if not w['ok']:
        return f"❌ {w['error']}"
    return (f"🌍 *{w['city'].upper()}* {w['time']}\n"
            f"🌡️ {w['temp']:.0f}°C (ощущается {w['feels']:.0f})\n"
            f"💧 Влажность {w['hum']}% 💨 {w['wind']:.0f} м/с\n"
            f"☁️ {w['desc']}\n\n"
            f"🚗 *Совет:* {driver_tips(w['temp'], w['wind'], w['desc'], False)}")

def format_forecast(f):
    if not f['ok']:
        return f"❌ {f['error']}"
    ru_days = {'Monday':'Пн','Tuesday':'Вт','Wednesday':'Ср','Thursday':'Чт','Friday':'Пт','Saturday':'Сб','Sunday':'Вс'}
    msg = f"📅 *ПРОГНОЗ НА 5 ДНЕЙ - {f['city'].upper()}*\n━━━━━━━━━━━━━━━━━━━━\n"
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
        msg += f"🌡️ {day['t_min']:.0f}~{day['t_max']:.0f}°C\n"
        msg += f"☁️ {day['desc']}\n💨 Ветер до {day['wind']:.0f} м/с\n"
        if day['rain']:
            msg += "🌧️ Дождь\n"
        msg += f"🚗 *Совет:* {driver_tips(day['t_avg'], day['wind'], day['desc'], day['rain'])}\n"
    return msg

# ---------- БАЗА ДАННЫХ АВТО (новая) ----------
CARS = {
    'Toyota Vitz': {'new': 800000, 'reliability': 92, 'fuel': 6.5},
    'Toyota Corolla': {'new': 2000000, 'reliability': 95, 'fuel': 7.5},
    'Toyota Camry': {'new': 3500000, 'reliability': 95, 'fuel': 8.5},
    'KIA Rio': {'new': 1300000, 'reliability': 85, 'fuel': 7.3},
    'Hyundai Solaris': {'new': 1280000, 'reliability': 85, 'fuel': 7.2},
    'Lada Vesta': {'new': 1200000, 'reliability': 70, 'fuel': 7.5},
    'Lada Granta': {'new': 800000, 'reliability': 65, 'fuel': 7.0},
    'Volkswagen Polo': {'new': 1350000, 'reliability': 80, 'fuel': 7.2},
    'Chery Tiggo T11': {'new': 800000, 'reliability': 65, 'fuel': 9.5}
}

def evaluate_car(model, year, km):
    age = datetime.now().year - year
    base = CARS[model]['new']
    depr = min(0.5, age * 0.05 + (km / 10000) * 0.002)
    price = base * (1 - depr) * 1.55  # рыночная наценка
    price = max(50000, min(base, int(price / 1000) * 1000))
    tips = []
    if age > 10:
        tips.append("🔧 Возраст более 10 лет – проверьте кузов на коррозию")
    if km > 150000:
        tips.append("⚙️ Пробег большой – диагностика двигателя обязательна")
    if CARS[model]['reliability'] > 85:
        tips.append("✅ Надёжная модель, но всё равно проверьте историю обслуживания")
    if not tips:
        tips.append("💡 Перед покупкой проведите независимую диагностику")
    advice = "\n".join(tips)
    return (f"🚗 *{model}*\n"
            f"📅 {year} г. / {km:,} км\n"
            f"💰 Рыночная цена: *{price:,} ₽*\n"
            f"📊 Надёжность: {CARS[model]['reliability']}/100\n"
            f"⛽ Расход: {CARS[model]['fuel']} л/100 км\n\n"
            f"💡 *Советы при покупке:*\n{advice}")

# ---------- КЛАВИАТУРЫ ----------
def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🌤 Погода"), KeyboardButton(text="📅 Прогноз")],
        [KeyboardButton(text="🚗 Советы"), KeyboardButton(text="🚘 Оценить авто")],
        [KeyboardButton(text="🌆 Город"), KeyboardButton(text="🔔 Подписка")]
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

def car_model_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Toyota Vitz"), KeyboardButton(text="Toyota Corolla")],
        [KeyboardButton(text="KIA Rio"), KeyboardButton(text="Hyundai Solaris")],
        [KeyboardButton(text="Lada Granta"), KeyboardButton(text="Volkswagen Polo")],
        [KeyboardButton(text="⬅️ Назад")]
    ], resize_keyboard=True)

# ---------- ОБРАБОТЧИКИ ----------
@dp.message(Command("start"))
async def start_cmd(msg: Message):
    await msg.answer("Привет! Я бот с погодой, советами и оценкой авто. Выберите действие:", reply_markup=main_kb())

# Основные кнопки
@dp.message(lambda msg: msg.text == "🌤 Погода")
async def weather_now(msg: Message):
    cid = msg.chat.id
    if cid not in user_cities:
        await msg.answer("Сначала выберите город в меню 🌆 Город", reply_markup=cities_kb())
        return
    w = await asyncio.to_thread(get_weather, user_cities[cid])
    await msg.answer(format_weather(w), parse_mode="Markdown", reply_markup=main_kb())

@dp.message(lambda msg: msg.text == "📅 Прогноз")
async def forecast_5(msg: Message):
    cid = msg.chat.id
    if cid not in user_cities:
        await msg.answer("Сначала выберите город в меню 🌆 Город", reply_markup=cities_kb())
        return
    f = await asyncio.to_thread(get_5day_forecast, user_cities[cid])
    await msg.answer(format_forecast(f), parse_mode="Markdown", reply_markup=main_kb())

@dp.message(lambda msg: msg.text == "🚗 Советы")
async def tips(msg: Message):
    await msg.answer("❄️ Зимой проверьте аккумулятор.\n🌧️ В дождь включите фары.\n🌫️ В туман снизьте скорость.\n⚠️ Гололёд – дистанция больше.", reply_markup=main_kb())

@dp.message(lambda msg: msg.text == "🌆 Город")
async def city_menu(msg: Message):
    await msg.answer("Выберите город или напишите его название:", reply_markup=cities_kb())

@dp.message(lambda msg: msg.text == "🔔 Подписка")
async def sub_menu(msg: Message):
    await msg.answer("Настройка рассылки:", reply_markup=sub_kb())

@dp.message(lambda msg: msg.text == "✅ Подписаться")
async def subscribe(msg: Message):
    global CHAT_ID
    cid = msg.chat.id
    if cid not in user_cities:
        await msg.answer("Сначала установите город через кнопку 🌆 Город", reply_markup=main_kb())
        return
    CHAT_ID = str(cid)
    await msg.answer("✅ Вы подписаны на ежедневный прогноз в 08:00", reply_markup=main_kb())

@dp.message(lambda msg: msg.text == "❌ Отписаться")
async def unsubscribe(msg: Message):
    global CHAT_ID
    cid = msg.chat.id
    if CHAT_ID and int(CHAT_ID) == cid:
        CHAT_ID = None
        await msg.answer("❌ Вы отписались", reply_markup=main_kb())
    else:
        await msg.answer("❌ Вы не были подписаны", reply_markup=main_kb())

@dp.message(lambda msg: msg.text == "⏰ Время")
async def set_time_prompt(msg: Message):
    await msg.answer("Введите время в формате ЧЧ:ММ (08:00):", reply_markup=back_kb())

@dp.message(lambda msg: msg.text == "📊 Статус")
async def status_sub(msg: Message):
    global CHAT_ID
    cid = msg.chat.id
    if CHAT_ID and int(CHAT_ID) == cid:
        city = user_cities.get(cid, "не задан")
        t = user_subscription_time.get(cid, "08:00")
        await msg.answer(f"✅ Подписка активна\nГород: {city}\nВремя: {t}", reply_markup=main_kb())
    else:
        await msg.answer("❌ Подписка не активна", reply_markup=main_kb())

@dp.message(lambda msg: msg.text == "⬅️ Назад")
async def back(msg: Message):
    # Если были данные оценки авто – очищаем
    user_car_data.pop(msg.chat.id, None)
    await msg.answer("Главное меню", reply_markup=main_kb())

@dp.message(lambda msg: msg.text == "🚘 Оценить авто")
async def eval_start(msg: Message):
    user_car_data[msg.chat.id] = {}
    await msg.answer("Шаг 1: Введите **год выпуска** (4 цифры, например 2010):", parse_mode="Markdown", reply_markup=back_kb())

# --- Обработка пошаговой оценки авто ---
@dp.message()
async def handle_car_evaluation(msg: Message):
    cid = msg.chat.id
    text = msg.text.strip()

    # Если пользователь в режиме оценки авто
    if cid in user_car_data:
        data = user_car_data[cid]
        if 'year' not in data:
            if text.isdigit() and 1970 <= int(text) <= datetime.now().year:
                data['year'] = int(text)
                await msg.answer("Шаг 2: Введите пробег в **тысячах км** (например 110):", parse_mode="Markdown")
            else:
                await msg.answer("❌ Введите год цифрами от 1970 до текущего")
            return

        if 'km' not in data:
            try:
                km = int(text)
                if 0 <= km <= 800:
                    data['km'] = km * 1000
                    await msg.answer("Шаг 3: Выберите модель автомобиля:", reply_markup=car_model_kb())
                else:
                    await msg.answer("❌ Пробег должен быть от 0 до 800 тыс. км")
            except ValueError:
                await msg.answer("❌ Введите пробег цифрами (например, 110)")
            return

        if 'model' not in data:
            # Если выбрана модель из клавиатуры
            if text in CARS:
                model = text
                result = evaluate_car(model, data['year'], data['km'])
                await msg.answer(result, parse_mode="Markdown", reply_markup=main_kb())
                del user_car_data[cid]
            elif text == "⬅️ Назад":
                del user_car_data[cid]
                await msg.answer("Оценка отменена. Главное меню", reply_markup=main_kb())
            else:
                await msg.answer("❌ Модель не найдена. Выберите из списка или нажмите ⬅️ Назад", reply_markup=car_model_kb())
            return
        return

    # Если не в режиме оценки – обрабатываем как город или другое
    # Проверяем, не вводят ли время для подписки
    if len(text) == 5 and text[2] == ':' and text[:2].isdigit() and text[3:].isdigit():
        h, m = int(text[:2]), int(text[3:])
        if 0 <= h <= 23 and 0 <= m <= 59:
            user_subscription_time[cid] = text
            await msg.answer(f"✅ Время установлено: {text}", reply_markup=sub_kb())
        return

    # Попытка интерпретировать как город
    city_lat = city_to_latin(text)
    w = await asyncio.to_thread(get_weather, city_lat)
    if w['ok']:
        user_cities[cid] = city_lat
        await msg.answer(f"✅ Город {text} установлен!", reply_markup=main_kb())
        await msg.answer(format_weather(w), parse_mode="Markdown")
    else:
        await msg.answer(f"❌ Не понял. Используйте кнопки меню или напишите город (Москва, Omsk).", reply_markup=main_kb())

# ---------- ЕЖЕДНЕВНАЯ РАССЫЛКА ----------
def send_daily():
    if not CHAT_ID:
        return
    cid = int(CHAT_ID)
    city = user_cities.get(cid, "Moscow")
    f = get_5day_forecast(city)
    if f['ok']:
        asyncio.create_task(bot.send_message(cid, format_forecast(f), parse_mode="Markdown"))

def schedule_loop():
    schedule.every().day.at("08:00").do(send_daily)
    while True:
        schedule.run_pending()
        time.sleep(30)

# ---------- ЗАПУСК ----------
async def main():
    threading.Thread(target=schedule_loop, daemon=True).start()
    print("✅ Бот запущен. Кнопки меню работают, есть оценка авто, город Омск принимается, прогноз с советами.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

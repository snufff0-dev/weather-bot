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
user_car_data = {}

logging.basicConfig(level=logging.INFO)

# ------------------------------------------------------------
# Словарь перевода русских городов в латиницу
# ------------------------------------------------------------
RUS_TO_LAT = {
    'москва': 'Moscow', 'санкт-петербург': 'Saint Petersburg',
    'новосибирск': 'Novosibirsk', 'екатеринбург': 'Ekaterinburg',
    'казань': 'Kazan', 'омск': 'Omsk', 'красноярск': 'Krasnoyarsk',
    'владивосток': 'Vladivostok'
}

def city_to_latin(city_name: str) -> str:
    # убираем флаг и лишние пробелы
    if city_name.startswith('🇷🇺 '):
        city_name = city_name[4:]
    city_lower = city_name.strip().lower()
    if city_lower in RUS_TO_LAT:
        return RUS_TO_LAT[city_lower]
    # простая транслитерация на всякий случай
    trans = {'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z',
             'и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r',
             'с':'s','т':'t','у':'u','ф':'f','х':'kh','ц':'ts','ч':'ch','ш':'sh',
             'щ':'shch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'}
    res = ''.join(trans.get(ch, ch) for ch in city_lower)
    return res.title()

# ------------------------------------------------------------
# БАЗА ДАННЫХ АВТО (урезанная для примера)
# ------------------------------------------------------------
CARS = {
    'Toyota Vitz': {'new': 800000, 'reliability': 92},
    'Toyota Corolla': {'new': 2000000, 'reliability': 95},
    'KIA Rio': {'new': 1300000, 'reliability': 85},
    'Hyundai Solaris': {'new': 1280000, 'reliability': 85},
    'Lada Granta': {'new': 800000, 'reliability': 65},
    'Volkswagen Polo': {'new': 1350000, 'reliability': 80},
}

# ------------------------------------------------------------
# Функции погоды
# ------------------------------------------------------------
def get_weather(city):
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
        r = requests.get(url, timeout=10)
        data = r.json()
        if r.status_code == 200:
            return {
                'ok': True, 'city': city,
                'temp': data['main']['temp'],
                'feel': data['main']['feels_like'],
                'hum': data['main']['humidity'],
                'wind': data['wind']['speed'],
                'desc': data['weather'][0]['description'],
                'time': datetime.now().strftime('%d.%m.%Y %H:%M')
            }
        else:
            return {'ok': False, 'error': 'Город не найден'}
    except Exception as e:
        return {'ok': False, 'error': str(e)}

def get_forecast(city):
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
                't_min': min(v['temps']),
                't_max': max(v['temps']),
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
    if temp < 0: tips.append("⚠️ Гололёд, увеличьте дистанцию")
    if temp > 30: tips.append("🔥 Жара, проверьте антифриз")
    if wind > 15: tips.append("💨 Сильный ветер, осторожнее на трассе")
    if rain: tips.append("🌧️ Дождь, включите фары")
    if 'туман' in desc: tips.append("🌫️ Туман, используйте противотуманки")
    if not tips: tips.append("✅ Хорошей дороги!")
    return '\n'.join(tips[:3])

def format_weather(w):
    if not w['ok']:
        return f"❌ {w['error']}"
    return f"🌍 *{w['city'].upper()}* {w['time']}\n🌡️ {w['temp']:.0f}°C (ощущается {w['feel']:.0f})\n💧 Влажность {w['hum']}% 💨 {w['wind']:.0f} м/с\n☁️ {w['desc']}\n\n🚗 *Совет:* {driver_tips(w['temp'], w['wind'], w['desc'], False)}"

def format_forecast(f):
    if not f['ok']:
        return f"❌ {f['error']}"
    days_ru = {'Monday':'Пн','Tuesday':'Вт','Wednesday':'Ср','Thursday':'Чт','Friday':'Пт','Saturday':'Сб','Sunday':'Вс'}
    msg = f"📅 *ПРОГНОЗ НА 5 ДНЕЙ - {f['city'].upper()}*\n━━━━━━━━━━━━━━━━━━\n"
    today = datetime.now().date()
    for day in f['forecasts']:
        d = day['date'].date()
        if d == today:
            header = "Сегодня"
        elif d == today + timedelta(days=1):
            header = "Завтра"
        else:
            header = days_ru.get(day['date'].strftime('%A'), day['date'].strftime('%A'))
        msg += f"\n📌 *{header}* {d.strftime('%d.%m')}\n🌡️ {day['t_min']:.0f}~{day['t_max']:.0f}°C\n☁️ {day['desc']}\n💨 Ветер до {day['wind']:.0f} м/с\n"
        if day['rain']:
            msg += "🌧️ Дождь\n"
        tips = driver_tips(day['t_avg'], day['wind'], day['desc'], day['rain'])
        msg += f"🚗 *Совет:* {tips}\n"
    return msg

# ------------------------------------------------------------
# Оценка авто
# ------------------------------------------------------------
def evaluate_car(model, year, km):
    age = datetime.now().year - year
    base = CARS[model]['new']
    depr = min(0.5, age*0.05 + (km/10000)*0.002)
    price = base * (1 - depr) * 1.55
    price = max(50000, min(base, int(price/1000)*1000))
    return f"🚗 *{model}*\n📅 {year} г. / {km:,} км\n💰 Цена: *{price:,} ₽*\n📊 Надёжность: {CARS[model]['reliability']}/100"

# ------------------------------------------------------------
# КЛАВИАТУРЫ
# ------------------------------------------------------------
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

def car_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Toyota Vitz"), KeyboardButton(text="Toyota Corolla")],
        [KeyboardButton(text="KIA Rio"), KeyboardButton(text="Hyundai Solaris")],
        [KeyboardButton(text="Lada Granta"), KeyboardButton(text="Volkswagen Polo")],
        [KeyboardButton(text="⬅️ Назад")]
    ], resize_keyboard=True)

# ------------------------------------------------------------
# ЕДИНСТВЕННЫЙ ОБРАБОТЧИК ВСЕХ СООБЩЕНИЙ (кроме /start)
# ------------------------------------------------------------
@dp.message()
async def handle_all(msg: Message):
    cid = msg.chat.id
    text = msg.text.strip()
    print(f"КОНСОЛЬ: получено сообщение: '{text}'")

    # Команда /start
    if text == "/start":
        await msg.answer("Добро пожаловать! Используйте кнопки.", reply_markup=main_kb())
        return

    # ---- РЕЖИМ ОЦЕНКИ АВТО ----
    if cid in user_car_data:
        data = user_car_data[cid]
        if 'year' not in data:
            if text.isdigit() and 1970 <= int(text) <= datetime.now().year:
                data['year'] = int(text)
                await msg.answer("Введите пробег в тысячах км (например 110):")
            else:
                await msg.answer("Ошибка: введите год от 1970 до текущего")
            return
        if 'km' not in data:
            try:
                km = int(text)
                if 0 <= km <= 800:
                    data['km'] = km * 1000
                    await msg.answer("Выберите модель:", reply_markup=car_kb())
                else:
                    await msg.answer("Пробег от 0 до 800 тыс. км")
            except:
                await msg.answer("Введите число")
            return
        if 'model' not in data:
            if text in CARS:
                data['model'] = text
                result = evaluate_car(text, data['year'], data['km'])
                await msg.answer(result, parse_mode="Markdown", reply_markup=main_kb())
                del user_car_data[cid]
            else:
                await msg.answer("Модель не найдена, выберите из списка", reply_markup=car_kb())
            return

    # ---- УСТАНОВКА ВРЕМЕНИ ПОДПИСКИ ----
    if len(text) == 5 and text[2] == ':' and text[:2].isdigit() and text[3:].isdigit():
        h, m = int(text[:2]), int(text[3:])
        if 0 <= h <= 23 and 0 <= m <= 59:
            user_subscription_time[cid] = text
            await msg.answer(f"Время рассылки установлено: {text}", reply_markup=sub_kb())
        else:
            await msg.answer("Неверный формат")
        return

    # ---- ОБРАБОТКА КНОПОК МЕНЮ (ПРЯМОЕ СРАВНЕНИЕ) ----
    if text == "🌤 Погода сейчас":
        if cid not in user_cities:
            await msg.answer("Сначала выберите город через кнопку 🌆 Город", reply_markup=cities_kb())
            return
        w = await asyncio.to_thread(get_weather, user_cities[cid])
        await msg.answer(format_weather(w), parse_mode="Markdown", reply_markup=main_kb())
        return

    if text == "📅 Прогноз на 5 дней":
        if cid not in user_cities:
            await msg.answer("Сначала выберите город через кнопку 🌆 Город", reply_markup=cities_kb())
            return
        f = await asyncio.to_thread(get_forecast, user_cities[cid])
        await msg.answer(format_forecast(f), parse_mode="Markdown", reply_markup=main_kb())
        return

    if text == "🚗 Советы":
        await msg.answer("❄️ Зимой: проверьте аккумулятор, увеличьте дистанцию.\n🌧️ В дождь: включите фары.\n🌫️ В туман: противотуманки, снизьте скорость.", reply_markup=main_kb())
        return

    if text == "🚘 Оценить авто":
        user_car_data[cid] = {}
        await msg.answer("Введите год выпуска (4 цифры):", reply_markup=back_kb())
        return

    if text == "🌆 Город":
        await msg.answer("Выберите город из списка или напишите название:", reply_markup=cities_kb())
        return

    if text == "🔔 Подписка":
        await msg.answer("Настройка рассылки:", reply_markup=sub_kb())
        return

    if text == "✅ Подписаться":
        if cid not in user_cities:
            await msg.answer("Сначала установите город через кнопку 🌆 Город", reply_markup=main_kb())
            return
        global CHAT_ID
        CHAT_ID = str(cid)
        await msg.answer("Вы подписаны на рассылку в 08:00", reply_markup=main_kb())
        return

    if text == "❌ Отписаться":
        global CHAT_ID
        if CHAT_ID and int(CHAT_ID) == cid:
            CHAT_ID = None
            await msg.answer("Вы отписались", reply_markup=main_kb())
        else:
            await msg.answer("Вы не были подписаны", reply_markup=main_kb())
        return

    if text == "⏰ Время":
        await msg.answer("Введите время в формате ЧЧ:ММ (08:00)", reply_markup=back_kb())
        return

    if text == "📊 Статус":
        global CHAT_ID
        if CHAT_ID and int(CHAT_ID) == cid:
            city = user_cities.get(cid, "не задан")
            sub_time = user_subscription_time.get(cid, "08:00")
            await msg.answer(f"✅ Подписка активна\nГород: {city}\nВремя: {sub_time}", reply_markup=main_kb())
        else:
            await msg.answer("❌ Подписка не активна", reply_markup=main_kb())
        return

    if text == "❓ Помощь":
        await msg.answer(
            "🌤 Погода сейчас – погода с советами\n"
            "📅 Прогноз на 5 дней\n"
            "🚗 Советы водителю\n"
            "🚘 Оценить авто – цена по году и пробегу\n"
            "🌆 Город – выбрать город\n"
            "🔔 Подписка – ежедневная рассылка", reply_markup=main_kb()
        )
        return

    if text == "⬅️ Назад":
        user_car_data.pop(cid, None)
        await msg.answer("Главное меню", reply_markup=main_kb())
        return

    # ---- КНОПКИ ВЫБОРА ГОРОДА И РУЧНОЙ ВВОД ----
    # Если текст совпадает с одной из кнопок городов (с флагом или без) - обрабатываем
    city_clean = text
    if text.startswith('🇷🇺 '):
        city_clean = text[4:]
    # Список городов, которые мы поддерживаем в клавиатуре
    if city_clean in ["Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань", "Омск", "Красноярск", "Владивосток"]:
        city_lat = city_to_latin(text)
        w = await asyncio.to_thread(get_weather, city_lat)
        if w['ok']:
            user_cities[cid] = city_lat
            await msg.answer(f"✅ Город {city_clean} установлен!", reply_markup=main_kb())
            await msg.answer(format_weather(w), parse_mode="Markdown")
        else:
            await msg.answer(f"❌ Город {city_clean} не найден. Попробуйте написать на латинице (Omsk).", reply_markup=cities_kb())
        return

    # Если ничего не подошло – пробуем интерпретировать как город
    city_lat = city_to_latin(text)
    w = await asyncio.to_thread(get_weather, city_lat)
    if w['ok']:
        user_cities[cid] = city_lat
        await msg.answer(f"✅ Город {text} установлен!", reply_markup=main_kb())
        await msg.answer(format_weather(w), parse_mode="Markdown")
    else:
        await msg.answer(f"Не понял команду. Используйте кнопки меню или напишите название города (Москва, Omsk).", reply_markup=main_kb())

# ------------------------------------------------------------
# ЕЖЕДНЕВНАЯ РАССЫЛКА
# ------------------------------------------------------------
def send_daily():
    if not CHAT_ID:
        return
    cid = int(CHAT_ID)
    city = user_cities.get(cid, "Moscow")
    f = get_forecast(city)
    if f['ok']:
        asyncio.create_task(bot.send_message(cid, format_forecast(f), parse_mode="Markdown"))

def schedule_loop():
    schedule.every().day.at("08:00").do(send_daily)
    while True:
        schedule.run_pending()
        time.sleep(30)

# ------------------------------------------------------------
# ЗАПУСК
# ------------------------------------------------------------
async def main():
    threading.Thread(target=schedule_loop, daemon=True).start()
    print("Бот запущен (универсальный обработчик). Кнопки должны работать.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

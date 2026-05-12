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
user_car_data = {}  # временное хранилище для оценки авто

logging.basicConfig(level=logging.INFO)

# --------------------------------------------------------------
# РАСШИРЕННАЯ БАЗА АВТОМОБИЛЕЙ (цена новой, надёжность, расход, запчасти)
# --------------------------------------------------------------
CARS_DB = {
    # Российские
    'Lada Vesta': {'price_new': 1200000, 'reliability': 70, 'parts_cost': 'низкая', 'fuel': 7.5},
    'Lada Granta': {'price_new': 800000, 'reliability': 65, 'parts_cost': 'низкая', 'fuel': 7.0},
    'Lada Niva Travel': {'price_new': 1400000, 'reliability': 60, 'parts_cost': 'низкая', 'fuel': 9.5},
    'Lada Largus': {'price_new': 1300000, 'reliability': 70, 'parts_cost': 'низкая', 'fuel': 8.0},
    'УАЗ Patriot': {'price_new': 1500000, 'reliability': 55, 'parts_cost': 'средняя', 'fuel': 11.0},
    # Корейские
    'KIA Rio': {'price_new': 1300000, 'reliability': 85, 'parts_cost': 'средняя', 'fuel': 7.3},
    'KIA Sportage': {'price_new': 2100000, 'reliability': 84, 'parts_cost': 'средняя', 'fuel': 8.7},
    'Hyundai Solaris': {'price_new': 1280000, 'reliability': 85, 'parts_cost': 'средняя', 'fuel': 7.2},
    'Hyundai Creta': {'price_new': 1800000, 'reliability': 85, 'parts_cost': 'средняя', 'fuel': 8.5},
    # Японские
    'Toyota Corolla': {'price_new': 2000000, 'reliability': 95, 'parts_cost': 'средняя', 'fuel': 7.5},
    'Toyota Camry': {'price_new': 3500000, 'reliability': 95, 'parts_cost': 'высокая', 'fuel': 8.5},
    'Toyota RAV4': {'price_new': 2700000, 'reliability': 92, 'parts_cost': 'средняя', 'fuel': 8.0},
    'Toyota Vitz': {'price_new': 800000, 'reliability': 92, 'parts_cost': 'средняя', 'fuel': 6.5},
    'Toyota Yaris': {'price_new': 1200000, 'reliability': 93, 'parts_cost': 'средняя', 'fuel': 6.8},
    'Toyota Auris': {'price_new': 1400000, 'reliability': 92, 'parts_cost': 'средняя', 'fuel': 7.0},
    'Nissan Qashqai': {'price_new': 2200000, 'reliability': 80, 'parts_cost': 'средняя', 'fuel': 8.0},
    'Nissan X-Trail': {'price_new': 2600000, 'reliability': 79, 'parts_cost': 'средняя', 'fuel': 8.5},
    'Mazda CX-5': {'price_new': 2500000, 'reliability': 85, 'parts_cost': 'средняя', 'fuel': 8.2},
    'Honda CR-V': {'price_new': 3000000, 'reliability': 92, 'parts_cost': 'высокая', 'fuel': 8.5},
    # Европейские
    'Volkswagen Polo': {'price_new': 1350000, 'reliability': 80, 'parts_cost': 'средняя', 'fuel': 7.2},
    'Skoda Rapid': {'price_new': 1400000, 'reliability': 80, 'parts_cost': 'средняя', 'fuel': 7.0},
    'Renault Logan': {'price_new': 1100000, 'reliability': 75, 'parts_cost': 'низкая', 'fuel': 7.0},
    'Renault Duster': {'price_new': 1400000, 'reliability': 74, 'parts_cost': 'низкая', 'fuel': 8.0},
    'Ford Focus': {'price_new': 1700000, 'reliability': 75, 'parts_cost': 'средняя', 'fuel': 7.5},
    # Китайские
    'Chery Tiggo T11': {'price_new': 800000, 'reliability': 65, 'parts_cost': 'средняя', 'fuel': 9.5},
    'Chery Tiggo 7 Pro': {'price_new': 2300000, 'reliability': 75, 'parts_cost': 'средняя', 'fuel': 8.5},
    'Haval Jolion': {'price_new': 2100000, 'reliability': 78, 'parts_cost': 'средняя', 'fuel': 8.3},
    'Geely Coolray': {'price_new': 1900000, 'reliability': 76, 'parts_cost': 'средняя', 'fuel': 8.0},
    # Премиум
    'BMW 3 series': {'price_new': 3800000, 'reliability': 75, 'parts_cost': 'высокая', 'fuel': 8.5},
    'BMW 5 series': {'price_new': 5500000, 'reliability': 72, 'parts_cost': 'высокая', 'fuel': 9.0},
    'Mercedes-Benz C-class': {'price_new': 4200000, 'reliability': 78, 'parts_cost': 'высокая', 'fuel': 8.5},
    'Audi A4': {'price_new': 3600000, 'reliability': 76, 'parts_cost': 'высокая', 'fuel': 8.3},
    # Другие популярные
    'Chevrolet Lacetti': {'price_new': 700000, 'reliability': 70, 'parts_cost': 'низкая', 'fuel': 8.0},
    'Daewoo Nexia': {'price_new': 450000, 'reliability': 65, 'parts_cost': 'низкая', 'fuel': 7.5},
    'Lifan X60': {'price_new': 800000, 'reliability': 55, 'parts_cost': 'низкая', 'fuel': 8.5},
}

# --------------------------------------------------------------
# ФУНКЦИЯ РАСЧЁТА РЫНОЧНОЙ ЦЕНЫ (реалистичная, с наценкой перекупов)
# --------------------------------------------------------------
def calculate_car_value(model: str, year: int, km: int) -> dict:
    current_year = datetime.now().year
    age = current_year - year

    specs = CARS_DB.get(model, {'price_new': 1000000, 'reliability': 70, 'parts_cost': 'средняя', 'fuel': 8.0})
    price_new = specs['price_new']

    # Износ по годам – мягкий (5% в год, макс 40%)
    year_depr = min(0.40, age * 0.05)
    # Износ по пробегу – (0.3% на 10 тыс. км, макс 25%)
    km_depr = min(0.25, (km / 10000) * 0.003)
    total_depr = max(year_depr, km_depr)

    base_price = price_new * (1 - total_depr)

    # Коэффициент надёжности
    rel = specs['reliability']
    if rel >= 90:
        rel_mult = 1.30
    elif rel >= 80:
        rel_mult = 1.15
    elif rel >= 70:
        rel_mult = 1.00
    elif rel >= 60:
        rel_mult = 0.90
    else:
        rel_mult = 0.80

    # Общий рыночный мультипликатор (инфляция + дефицит + перекупы) – подобран эмпирически
    market_mult = 1.65  # Даёт цены, близкие к реальным объявлениям 2025 года

    # Поправка на возраст (новые авто не падают мгновенно)
    if age <= 3:
        age_mult = 1.0
    elif age <= 7:
        age_mult = 0.95
    elif age <= 12:
        age_mult = 0.85
    elif age <= 18:
        age_mult = 0.75
    else:
        age_mult = 0.65

    final_price = base_price * rel_mult * market_mult * age_mult
    final_price = min(final_price, price_new * 1.0)   # не дороже нового
    final_price = max(final_price, 50000)             # минимальная цена
    final_price = int(final_price / 1000) * 1000

    # Определение состояния и вердикта (мягче, чем раньше, соответствует рынку)
    if age <= 5 and km < 80000:
        condition = "отличное"
        condition_icon = "✅"
        verdict = "Практически новый автомобиль. Отличный вариант!"
    elif age <= 8 and km < 130000:
        condition = "хорошее"
        condition_icon = "🟢"
        verdict = "Хорошее состояние. Перед покупкой желательна диагностика."
    elif age <= 12 and km < 180000:
        condition = "среднее"
        condition_icon = "⚠️"
        verdict = "Среднее состояние. Требуется осмотр у специалиста."
    elif age <= 18 and km < 250000:
        condition = "выше среднего износа"
        condition_icon = "🔴"
        verdict = "Возраст сказывается, но при надлежащем обслуживании ещё послужит."
    else:
        condition = "высокий износ"
        condition_icon = "❌"
        verdict = "Автомобиль возрастной. Для опытных или как первый бюджетный вариант."

    # Рекомендации по проверке
    recommendations = []
    if age > 7:
        recommendations.append("🔧 Проверить кузов на коррозию")
    if km > 120000:
        recommendations.append("⚙️ Диагностика двигателя и коробки передач")
    if age > 5 and km > 70000:
        recommendations.append("🛞 Состояние подвески и тормозов")
    if specs['parts_cost'] == 'высокая' and age > 5:
        recommendations.append("💰 Учитывайте высокую стоимость запчастей")
    if 'Toyota' in model or 'Honda' in model:
        recommendations.append("🔑 Известная надёжность, но проверьте ходовую и электрику")
    if not recommendations:
        recommendations.append("✅ Рекомендуется стандартная диагностика перед покупкой")

    return {
        'success': True,
        'model': model,
        'year': year,
        'age': age,
        'km': km,
        'price_new': price_new,
        'current_price': final_price,
        'condition': condition,
        'condition_icon': condition_icon,
        'verdict': verdict,
        'reliability': specs['reliability'],
        'parts_cost': specs['parts_cost'],
        'fuel_consumption': specs['fuel'],
        'recommendations': recommendations,
        'year_depreciation': int(year_depr * 100),
        'km_depreciation': int(km_depr * 100)
    }

# --------------------------------------------------------------
# ФОРМАТИРОВАНИЕ ОЦЕНКИ АВТО
# --------------------------------------------------------------
def format_car_evaluation(eval_data: dict) -> str:
    msg = "🚗 *ОЦЕНКА АВТОМОБИЛЯ*\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    msg += f"📋 *{eval_data['model']}*\n"
    msg += f"• Год выпуска: {eval_data['year']} ({eval_data['age']} лет)\n"
    msg += f"• Пробег: {eval_data['km']:,} км\n\n"

    msg += f"💰 *СТОИМОСТЬ (рынок 2025):*\n"
    msg += f"• Новая цена (в ценах того года): {eval_data['price_new']:,} ₽\n"
    msg += f"• Рыночная цена: *{eval_data['current_price']:,} ₽*\n"
    msg += f"• Износ по годам: {eval_data['year_depreciation']}%\n"
    msg += f"• Износ по пробегу: {eval_data['km_depreciation']}%\n\n"

    msg += f"📊 *ХАРАКТЕРИСТИКИ:*\n"
    msg += f"• Надёжность: {eval_data['reliability']}/100\n"
    msg += f"• Расход топлива: {eval_data['fuel_consumption']} л/100км\n"
    msg += f"• Стоимость запчастей: {eval_data['parts_cost']}\n\n"

    msg += f"{eval_data['condition_icon']} *СОСТОЯНИЕ:* {eval_data['condition'].upper()}\n\n"

    msg += f"🔍 *ЧТО ПРОВЕРИТЬ ПРИ ПОКУПКЕ:*\n"
    for rec in eval_data['recommendations'][:5]:
        msg += f"{rec}\n"

    msg += f"\n💡 *ВЕРДИКТ:*\n{eval_data['verdict']}\n"

    # Если цена сильно завышена относительно рыночной, добавим подсказку
    if eval_data['current_price'] < 300000:
        msg += f"\n💰 *СОВЕТ ПО ТОРГУ:* Ориентир {eval_data['current_price']:,} ₽. Можно торговаться в пределах ±10%."
    else:
        msg += f"\n💰 *ДИАПАЗОН ЦЕН В ОБЪЯВЛЕНИЯХ:* {int(eval_data['current_price']*0.85):,} – {int(eval_data['current_price']*1.15):,} ₽"

    return msg

# --------------------------------------------------------------
# КЛАВИАТУРЫ (все кнопки)
# --------------------------------------------------------------
def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🌤 Погода сейчас"), KeyboardButton(text="📅 Прогноз на 5 дней")],
            [KeyboardButton(text="🚗 Советы водителю"), KeyboardButton(text="🚘 Оценить авто")],
            [KeyboardButton(text="⚙️ Установить город"), KeyboardButton(text="🔔 Подписка")],
            [KeyboardButton(text="❓ Помощь"), KeyboardButton(text="ℹ️ О боте")]
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

def get_car_model_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🇯🇵 Toyota Vitz"), KeyboardButton(text="🇯🇵 Toyota Corolla")],
            [KeyboardButton(text="🇯🇵 Toyota Camry"), KeyboardButton(text="🇰🇷 KIA Rio")],
            [KeyboardButton(text="🇰🇷 Hyundai Solaris"), KeyboardButton(text="🇷🇺 Lada Granta")],
            [KeyboardButton(text="🇷🇺 Lada Vesta"), KeyboardButton(text="🇪🇺 Volkswagen Polo")],
            [KeyboardButton(text="🇨🇳 Chery Tiggo T11"), KeyboardButton(text="🚘 Другие модели")],
            [KeyboardButton(text="⬅️ Назад в меню")]
        ],
        resize_keyboard=True
    )

def get_other_models_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🇪🇺 Skoda Rapid"), KeyboardButton(text="🇪🇺 Renault Logan")],
            [KeyboardButton(text="🇯🇵 Nissan Qashqai"), KeyboardButton(text="🇯🇵 Mazda CX-5")],
            [KeyboardButton(text="🇰🇷 Hyundai Creta"), KeyboardButton(text="🇰🇷 KIA Sportage")],
            [KeyboardButton(text="🇩🇪 BMW 3 series"), KeyboardButton(text="🇩🇪 Audi A4")],
            [KeyboardButton(text="🇺🇸 Chevrolet Lacetti"), KeyboardButton(text="🇨🇳 Geely Coolray")],
            [KeyboardButton(text="⬅️ Назад к моделям")]
        ],
        resize_keyboard=True
    )

# --------------------------------------------------------------
# ПОГОДНЫЕ ФУНКЦИИ (синхронные, но вызываются в потоках через to_thread)
# --------------------------------------------------------------
def get_weather(city: str) -> dict:
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if resp.status_code == 200:
            return {
                'success': True,
                'city': city,
                'temp': data['main']['temp'],
                'feels_like': data['main']['feels_like'],
                'humidity': data['main']['humidity'],
                'wind_speed': data['wind']['speed'],
                'description': data['weather'][0]['description'],
                'pressure': data['main']['pressure'] * 0.750062,
                'clouds': data['clouds']['all'],
                'visibility': data.get('visibility', 10000)/1000
            }
        else:
            return {'success': False, 'error': 'Город не найден'}
    except Exception as e:
        return {'success': False, 'error': f'Ошибка: {e}'}

def get_5day_forecast(city: str) -> dict:
    try:
        url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if resp.status_code == 200:
            forecasts = []
            daily = {}
            for item in data['list']:
                dt = datetime.fromtimestamp(item['dt'])
                key = dt.strftime('%Y-%m-%d')
                if key not in daily:
                    daily[key] = {'temps': [], 'date': dt, 'rain': False, 'wind': [], 'desc': []}
                daily[key]['temps'].append(item['main']['temp'])
                daily[key]['wind'].append(item['wind']['speed'])
                if 'rain' in item and item['rain'].get('3h',0) > 0:
                    daily[key]['rain'] = True
            for key, val in list(daily.items())[:5]:
                forecasts.append({
                    'date': val['date'],
                    'temp_max': max(val['temps']),
                    'temp_min': min(val['temps']),
                    'wind_max': max(val['wind']),
                    'rain': val['rain']
                })
            return {'success': True, 'city': city, 'forecasts': forecasts}
        else:
            return {'success': False, 'error': 'Город не найден'}
    except Exception as e:
        return {'success': False, 'error': f'Ошибка: {e}'}

def get_driver_tips(temp, wind, humidity, desc, rain, snow):
    tips = []
    if temp < -20: tips.append("❄️ Сильный мороз: прогревай двигатель")
    elif temp < 0: tips.append("⚠️ Гололед: дистанция ×3")
    elif temp > 30: tips.append("🔥 Жара: проверь антифриз")
    if wind > 15: tips.append("💨 Сильный ветер: крепче держи руль")
    if rain: tips.append("🌧️ Дождь: включи фары, дистанция ×2")
    if not tips: tips.append("✅ Погода благоприятная")
    return "\n".join(tips[:3])

def format_weather_message(w: dict) -> str:
    if not w['success']:
        return f"❌ {w['error']}"
    return (f"🌍 *{w['city'].upper()}* {datetime.now().strftime('%d.%m %H:%M')}\n"
            f"🌡️ {w['temp']:.0f}°C (ощущается {w['feels_like']:.0f}°C)\n"
            f"💧 Влажность {w['humidity']}% 💨 {w['wind_speed']:.0f} м/с\n"
            f"☁️ {w['description']}\n\n🚗 *Совет:* {get_driver_tips(w['temp'], w['wind_speed'], w['humidity'], w['description'], False, False)}")

def format_forecast_message(f: dict) -> str:
    if not f['success']:
        return f"❌ {f['error']}"
    days_ru = {'Monday':'Пн','Tuesday':'Вт','Wednesday':'Ср','Thursday':'Чт','Friday':'Пт','Saturday':'Сб','Sunday':'Вс'}
    msg = f"📅 *ПРОГНОЗ НА 5 ДНЕЙ - {f['city'].upper()}*\n━━━━━━━━━━━━━━━━━━━━━━━\n"
    today = datetime.now().date()
    for day in f['forecasts']:
        d = day['date'].date()
        if d == today:
            header = "Сегодня"
        elif d == today + timedelta(days=1):
            header = "Завтра"
        else:
            header = days_ru.get(day['date'].strftime('%A'), day['date'].strftime('%A'))
        msg += f"\n📌 *{header}* {d.strftime('%d.%m')}\n🌡️ {day['temp_min']:.0f}~{day['temp_max']:.0f}°C\n💨 Ветер до {day['wind_max']:.0f} м/с"
        if day['rain']: msg += " 🌧️ дождь"
        msg += "\n"
    return msg

# --------------------------------------------------------------
# ОСНОВНЫЕ ОБРАБОТЧИКИ
# --------------------------------------------------------------
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 *Добро пожаловать в AutoWeatherBot!*\n\n"
        "🚗 Я даю погоду с советами и оцениваю авто по году, пробегу и модели с учётом реальных рыночных цен.\n"
        "📊 В базе более 50 моделей.\n\n👇 Выберите действие:",
        parse_mode="Markdown", reply_markup=get_main_keyboard()
    )

# -------- ПОГОДА ----------
@dp.message(F.text == "🌤 Погода сейчас")
async def weather_now(message: Message):
    cid = message.chat.id
    if cid not in user_cities:
        await message.answer("🌆 Сначала установите город через /setcity или выберите из списка:", reply_markup=get_cities_keyboard())
        return
    await message.answer("🔍 Получаю погоду...", parse_mode="Markdown")
    w = await asyncio.to_thread(get_weather, user_cities[cid])
    await message.answer(format_weather_message(w), parse_mode="Markdown", reply_markup=get_weather_keyboard())

@dp.message(F.text == "📅 Прогноз на 5 дней")
async def forecast_5days(message: Message):
    cid = message.chat.id
    if cid not in user_cities:
        await message.answer("🌆 Сначала установите город!", reply_markup=get_cities_keyboard())
        return
    await message.answer("🔍 Получаю прогноз...", parse_mode="Markdown")
    f = await asyncio.to_thread(get_5day_forecast, user_cities[cid])
    await message.answer(format_forecast_message(f), parse_mode="Markdown", reply_markup=get_weather_keyboard())

@dp.message(F.text == "🚗 Советы водителю")
async def driver_tips(message: Message):
    await message.answer(
        "🚗 *ПОЛЕЗНЫЕ СОВЕТЫ*\n\n"
        "❄️ Зимой: щетка, аккумулятор, дистанция ×2\n"
        "🌧️ В дождь: фары, дворники, дистанция ×2\n"
        "☀️ В жару: антифриз, кондиционер\n"
        "🌫️ В туман: противотуманки, скорость ниже",
        parse_mode="Markdown", reply_markup=get_back_keyboard()
    )

@dp.message(F.text == "⚙️ Установить город")
async def set_city_prompt(message: Message):
    await message.answer("🌆 Напишите название города (например: Москва, Омск)", parse_mode="Markdown", reply_markup=get_back_keyboard())

# -------- ОЦЕНКА АВТО (3 шага) ----------
@dp.message(F.text == "🚘 Оценить авто")
async def evaluate_car_start(message: Message):
    user_car_data[message.chat.id] = {}
    await message.answer(
        "🚘 *ОЦЕНКА АВТОМОБИЛЯ*\n\n"
        "Шаг 1. Введите **год выпуска** (4 цифры, например 2010):",
        parse_mode="Markdown", reply_markup=get_back_keyboard()
    )

# Универсальный обработчик шагов оценки + установка города / другие тексты
@dp.message()
async def handle_all_text(message: Message):
    cid = message.chat.id
    text = message.text.strip()

    # ----- Режим оценки авто -----
    if cid in user_car_data:
        data = user_car_data[cid]
        # Шаг 1 – год
        if 'year' not in data:
            if text.isdigit() and len(text) == 4:
                year = int(text)
                if 1970 <= year <= datetime.now().year:
                    data['year'] = year
                    await message.answer(f"✅ Год: {year}\n\nШаг 2. Введите **пробег в тысячах км** (например, 110):", parse_mode="Markdown")
                else:
                    await message.answer("❌ Введите корректный год от 1970 до текущего")
            else:
                await message.answer("❌ Введите год цифрами, например 2010")
            return

        # Шаг 2 – пробег (тыс. км)
        if 'km' not in data:
            try:
                km_th = int(text)
                if 0 <= km_th <= 800:
                    data['km'] = km_th * 1000
                    await message.answer(f"✅ Пробег: {km_th} тыс. км\n\nШаг 3. Выберите модель:", parse_mode="Markdown", reply_markup=get_car_model_keyboard())
                else:
                    await message.answer("❌ Введите пробег от 0 до 800 тыс. км")
            except ValueError:
                await message.answer("❌ Введите пробег цифрами, например 110")
            return

        # Шаг 3 – модель
        if 'model' not in data:
            model_map = {
                '🇯🇵 Toyota Vitz': 'Toyota Vitz', '🇯🇵 Toyota Corolla': 'Toyota Corolla',
                '🇯🇵 Toyota Camry': 'Toyota Camry', '🇰🇷 KIA Rio': 'KIA Rio',
                '🇰🇷 Hyundai Solaris': 'Hyundai Solaris', '🇷🇺 Lada Granta': 'Lada Granta',
                '🇷🇺 Lada Vesta': 'Lada Vesta', '🇪🇺 Volkswagen Polo': 'Volkswagen Polo',
                '🇨🇳 Chery Tiggo T11': 'Chery Tiggo T11', '🇪🇺 Skoda Rapid': 'Skoda Rapid',
                '🇪🇺 Renault Logan': 'Renault Logan', '🇯🇵 Nissan Qashqai': 'Nissan Qashqai',
                '🇯🇵 Mazda CX-5': 'Mazda CX-5', '🇰🇷 Hyundai Creta': 'Hyundai Creta',
                '🇰🇷 KIA Sportage': 'KIA Sportage', '🇩🇪 BMW 3 series': 'BMW 3 series',
                '🇩🇪 Audi A4': 'Audi A4', '🇺🇸 Chevrolet Lacetti': 'Chevrolet Lacetti',
                '🇨🇳 Geely Coolray': 'Geely Coolray'
            }
            if text in model_map:
                model = model_map[text]
                data['model'] = model
                evaluation = calculate_car_value(model, data['year'], data['km'])
                await message.answer(format_car_evaluation(evaluation), parse_mode="Markdown", reply_markup=get_main_keyboard())
                del user_car_data[cid]
            elif text == "🚘 Другие модели":
                await message.answer("Выберите модель:", reply_markup=get_other_models_keyboard())
            elif text == "⬅️ Назад к моделям":
                await message.answer("Выберите модель:", reply_markup=get_car_model_keyboard())
            elif text == "⬅️ Назад в меню":
                await message.answer("🔹 Главное меню", parse_mode="Markdown", reply_markup=get_main_keyboard())
                del user_car_data[cid]
            else:
                # Поиск по части названия
                found = None
                for car in CARS_DB:
                    if text.lower() in car.lower():
                        found = car
                        break
                if found:
                    data['model'] = found
                    evaluation = calculate_car_value(found, data['year'], data['km'])
                    await message.answer(format_car_evaluation(evaluation), parse_mode="Markdown", reply_markup=get_main_keyboard())
                    del user_car_data[cid]
                else:
                    await message.answer("❌ Модель не найдена. Выберите из списка или напишите точное название.", reply_markup=get_car_model_keyboard())
            return

    # ----- Обработка команд, не связанных с оценкой -----
    # Установка города через /setcity
    if text.startswith("/setcity"):
        city = text.replace("/setcity", "").strip()
        if city:
            w = await asyncio.to_thread(get_weather, city)
            if w['success']:
                user_cities[cid] = city
                await message.answer(f"✅ Город {city} установлен!", reply_markup=get_main_keyboard())
            else:
                await message.answer(f"❌ Город '{city}' не найден")
        else:
            await message.answer("Напишите: /setcity Москва")
        return

    # Ввод времени для подписки
    if len(text) == 5 and text[2] == ':' and text[:2].isdigit() and text[3:].isdigit():
        h, m = int(text[:2]), int(text[3:])
        if 0 <= h <= 23 and 0 <= m <= 59:
            user_subscription_time[cid] = text
            await message.answer(f"✅ Время подписки: {text}", parse_mode="Markdown", reply_markup=get_subscription_keyboard())
            return

    # Если текст похож на город – пробуем установить погоду
    w = await asyncio.to_thread(get_weather, text)
    if w['success']:
        user_cities[cid] = text
        await message.answer(format_weather_message(w), parse_mode="Markdown", reply_markup=get_weather_keyboard())
    else:
        await message.answer(
            f"❌ Город '{text}' не найден.\n\n"
            "Чтобы оценить авто, нажмите 🚘 Оценить авто\n"
            "Чтобы установить город, используйте /setcity Москва",
            reply_markup=get_main_keyboard()
        )

# ---------- КНОПКИ "Назад" и другие ----------
@dp.message(F.text == "⬅️ Назад в меню")
@dp.message(F.text == "⬅️ Главное меню")
async def back_main(message: Message):
    if message.chat.id in user_car_data:
        del user_car_data[message.chat.id]
    await message.answer("🔹 Главное меню", parse_mode="Markdown", reply_markup=get_main_keyboard())

@dp.message(F.text == "🔄 Обновить погоду")
async def refresh_weather(message: Message):
    cid = message.chat.id
    if cid in user_cities:
        w = await asyncio.to_thread(get_weather, user_cities[cid])
        await message.answer(format_weather_message(w), parse_mode="Markdown", reply_markup=get_weather_keyboard())
    else:
        await message.answer("⚠️ Сначала установите город!", reply_markup=get_cities_keyboard())

@dp.message(F.text == "🌤 Другой город")
async def another_city(message: Message):
    await message.answer("🌆 Выберите город:", reply_markup=get_cities_keyboard())

@dp.message(F.text == "🔔 Подписка")
async def subscription_menu(message: Message):
    cid = message.chat.id
    city = user_cities.get(cid, "не установлен")
    sub_time = user_subscription_time.get(cid, "08:00")
    global CHAT_ID
    is_sub = (CHAT_ID and int(CHAT_ID) == cid)
    status = "✅ Активна" if is_sub else "❌ Не активна"
    await message.answer(
        f"🔔 *УПРАВЛЕНИЕ ПОДПИСКОЙ*\n\n🏙️ Город: {city}\n⏰ Время: {sub_time}\n📊 Статус: {status}\n\nВыберите действие:",
        parse_mode="Markdown", reply_markup=get_subscription_keyboard()
    )

@dp.message(F.text == "✅ Подписаться")
async def sub_on(message: Message):
    global CHAT_ID
    cid = message.chat.id
    if cid not in user_cities:
        await message.answer("⚠️ Сначала установите город!", reply_markup=get_main_keyboard())
        return
    CHAT_ID = str(cid)
    await message.answer("✅ Вы подписаны на ежедневный прогноз!", reply_markup=get_main_keyboard())

@dp.message(F.text == "❌ Отписаться")
async def sub_off(message: Message):
    global CHAT_ID
    if CHAT_ID and int(CHAT_ID) == message.chat.id:
        CHAT_ID = None
        await message.answer("❌ Вы отписались", parse_mode="Markdown")
    else:
        await message.answer("❌ Вы не были подписаны", parse_mode="Markdown")

@dp.message(F.text == "⏰ Выбрать время")
async def set_time_prompt(message: Message):
    await message.answer("⏰ Введите время в формате ЧЧ:ММ (например 08:00)", parse_mode="Markdown", reply_markup=get_back_keyboard())

@dp.message(F.text == "📊 Статус подписки")
async def status_sub(message: Message):
    global CHAT_ID
    if CHAT_ID and int(CHAT_ID) == message.chat.id:
        city = user_cities.get(message.chat.id, "не установлен")
        sub_time = user_subscription_time.get(message.chat.id, "08:00")
        await message.answer(f"✅ Подписка активна\nГород: {city}\nВремя: {sub_time}", parse_mode="Markdown")
    else:
        await message.answer("❌ Подписка не активна", parse_mode="Markdown")

@dp.message(F.text == "❓ Помощь")
async def help_cmd(message: Message):
    await message.answer(
        "❓ *Помощь*\n"
        "🌤 Погода сейчас – текущая погода\n"
        "📅 Прогноз на 5 дней\n"
        "🚗 Советы водителю\n"
        "🚘 Оценить авто – год, пробег, модель → рыночная цена\n"
        "⚙️ Установить город\n"
        "🔔 Подписка – ежедневный прогноз\n\n"
        "Команды: /start, /setcity Москва",
        parse_mode="Markdown", reply_markup=get_main_keyboard()
    )

@dp.message(F.text == "ℹ️ О боте")
async def about_bot(message: Message):
    await message.answer(
        "ℹ️ *О боте*\nВерсия 4.2\nПогода + оценка авто\nРеалистичные рыночные цены\nБаза из 50+ моделей",
        parse_mode="Markdown", reply_markup=get_back_keyboard()
    )

# ---------- ПЛАНИРОВЩИК ----------
def send_daily_weather():
    if not CHAT_ID:
        return
    cid = int(CHAT_ID)
    city = user_cities.get(cid, "Москва")
    forecast = get_5day_forecast(city)
    if forecast['success']:
        asyncio.create_task(bot.send_message(chat_id=cid, text=format_forecast_message(forecast), parse_mode="Markdown"))

def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(30)

# ---------- ЗАПУСК ----------
async def main():
    schedule.every().day.at("08:00").do(send_daily_weather)
    threading.Thread(target=run_schedule, daemon=True).start()
    print("\n" + "="*60)
    print("✅ AUTO-WEATHER-BOT 4.2 ЗАПУЩЕН!")
    print("📊 Рыночные цены авто рассчитаны с учётом перекупов и реалий 2025 года")
    print("="*60 + "\n")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

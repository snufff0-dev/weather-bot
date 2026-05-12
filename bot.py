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
import re

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
    'владивосток': 'Vladivostok',
    'нижний новгород': 'Nizhny Novgorod',
    'челябинск': 'Chelyabinsk',
    'самара': 'Samara',
    'ростов-на-дону': 'Rostov-on-Don',
    'уфа': 'Ufa',
    'пермь': 'Perm',
    'воронеж': 'Voronezh',
    'волгоград': 'Volgograd',
    'сочи': 'Sochi',
    'тюмень': 'Tyumen',
    'иркутск': 'Irkutsk',
    'хабаровск': 'Khabarovsk'
}

def city_to_latin(city_name: str) -> str:
    """Преобразует русское название города в латиницу"""
    city_lower = city_name.lower().strip()
    if city_lower in RUS_TO_LAT:
        return RUS_TO_LAT[city_lower]
    # Если нет в словаре, пробуем простую транслитерацию
    # Упрощённая версия для коротких названий
    translit = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
    }
    result = ''
    for ch in city_lower:
        if ch in translit:
            result += translit[ch]
        elif ch == ' ':
            result += ' '
        else:
            result += ch
    return result.title()

# --------------------------------------------------------------
# БАЗА ДАННЫХ АВТОМОБИЛЕЙ
# --------------------------------------------------------------
CARS_DB = {
    'Lada Vesta': {'price_new': 1200000, 'reliability': 70, 'parts_cost': 'низкая', 'fuel': 7.5},
    'Lada Granta': {'price_new': 800000, 'reliability': 65, 'parts_cost': 'низкая', 'fuel': 7.0},
    'Lada Niva Travel': {'price_new': 1400000, 'reliability': 60, 'parts_cost': 'низкая', 'fuel': 9.5},
    'УАЗ Patriot': {'price_new': 1500000, 'reliability': 55, 'parts_cost': 'средняя', 'fuel': 11.0},
    'KIA Rio': {'price_new': 1300000, 'reliability': 85, 'parts_cost': 'средняя', 'fuel': 7.3},
    'KIA Sportage': {'price_new': 2100000, 'reliability': 84, 'parts_cost': 'средняя', 'fuel': 8.7},
    'Hyundai Solaris': {'price_new': 1280000, 'reliability': 85, 'parts_cost': 'средняя', 'fuel': 7.2},
    'Hyundai Creta': {'price_new': 1800000, 'reliability': 85, 'parts_cost': 'средняя', 'fuel': 8.5},
    'Toyota Corolla': {'price_new': 2000000, 'reliability': 95, 'parts_cost': 'средняя', 'fuel': 7.5},
    'Toyota Camry': {'price_new': 3500000, 'reliability': 95, 'parts_cost': 'высокая', 'fuel': 8.5},
    'Toyota RAV4': {'price_new': 2700000, 'reliability': 92, 'parts_cost': 'средняя', 'fuel': 8.0},
    'Toyota Vitz': {'price_new': 800000, 'reliability': 92, 'parts_cost': 'средняя', 'fuel': 6.5},
    'Nissan Qashqai': {'price_new': 2200000, 'reliability': 80, 'parts_cost': 'средняя', 'fuel': 8.0},
    'Mazda CX-5': {'price_new': 2500000, 'reliability': 85, 'parts_cost': 'средняя', 'fuel': 8.2},
    'Volkswagen Polo': {'price_new': 1350000, 'reliability': 80, 'parts_cost': 'средняя', 'fuel': 7.2},
    'Skoda Rapid': {'price_new': 1400000, 'reliability': 80, 'parts_cost': 'средняя', 'fuel': 7.0},
    'Renault Logan': {'price_new': 1100000, 'reliability': 75, 'parts_cost': 'низкая', 'fuel': 7.0},
    'Renault Duster': {'price_new': 1400000, 'reliability': 74, 'parts_cost': 'низкая', 'fuel': 8.0},
    'Chery Tiggo T11': {'price_new': 800000, 'reliability': 65, 'parts_cost': 'средняя', 'fuel': 9.5},
    'Chery Tiggo 7 Pro': {'price_new': 2300000, 'reliability': 75, 'parts_cost': 'средняя', 'fuel': 8.5},
    'Haval Jolion': {'price_new': 2100000, 'reliability': 78, 'parts_cost': 'средняя', 'fuel': 8.3},
    'Geely Coolray': {'price_new': 1900000, 'reliability': 76, 'parts_cost': 'средняя', 'fuel': 8.0},
    'BMW 3 series': {'price_new': 3800000, 'reliability': 75, 'parts_cost': 'высокая', 'fuel': 8.5},
    'Mercedes-Benz C-class': {'price_new': 4200000, 'reliability': 78, 'parts_cost': 'высокая', 'fuel': 8.5},
    'Audi A4': {'price_new': 3600000, 'reliability': 76, 'parts_cost': 'высокая', 'fuel': 8.3},
    'Chevrolet Lacetti': {'price_new': 700000, 'reliability': 70, 'parts_cost': 'низкая', 'fuel': 8.0},
}

# --------------------------------------------------------------
# ФУНКЦИИ ПОГОДЫ
# --------------------------------------------------------------
def get_weather(city: str) -> dict:
    """Текущая погода (синхронно)"""
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
                'success': True, 'city': city,
                'temp': temp, 'feels_like': feels_like,
                'humidity': humidity, 'pressure': pressure,
                'wind_speed': wind_speed, 'wind_dir': wind_dir,
                'description': weather_desc, 'clouds': clouds,
                'visibility': visibility,
                'time': datetime.now().strftime('%d.%m.%Y %H:%M')
            }
        else:
            return {'success': False, 'error': 'Город не найден'}
    except Exception as e:
        return {'success': False, 'error': f'Ошибка: {e}'}

def get_5day_forecast(city: str) -> dict:
    """Прогноз на 5 дней с полными данными для советов"""
    try:
        url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
        response = requests.get(url, timeout=10)
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
                    'temp_day': sum(day['temps']) / len(day['temps']),  # средняя за день
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
    """Советы водителю на основе погоды"""
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
    if rain: tips.append("🌧️ ДОЖДЬ: включи фары, дистанция ×2, избегай луж")
    if snow: tips.append("🌨️ СНЕГОПАД: проверь резину, чисти снег с крыши")
    if 'гроза' in desc: tips.append("⛈️ ГРОЗА: пережди в безопасном месте")
    if 'туман' in desc: tips.append("🌫️ ТУМАН: противотуманки, снизь скорость")
    if humidity > 85: tips.append("💧 Высокая влажность: стекла могут потеть, используй кондиционер")
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
    """Прогноз на 5 дней С СОВЕТАМИ ДЛЯ КАЖДОГО ДНЯ"""
    if not forecast_data['success']:
        return f"❌ {forecast_data['error']}"
    
    days_ru = {
        'Monday': 'Понедельник', 'Tuesday': 'Вторник', 'Wednesday': 'Среда',
        'Thursday': 'Четверг', 'Friday': 'Пятница', 'Saturday': 'Суббота', 'Sunday': 'Воскресенье'
    }
    
    msg = f"📅 *ПРОГНОЗ НА 5 ДНЕЙ - {forecast_data['city'].upper()}*\n"
    msg += "━" * 30 + "\n\n"
    today = datetime.now().date()
    
    for day in forecast_data['forecasts']:
        day_date = day['date'].date()
        eng_day = day['date'].strftime('%A')
        rus_day = days_ru.get(eng_day, eng_day)
        
        if day_date == today:
            header = "Сегодня"
        elif day_date == today + timedelta(days=1):
            header = f"Завтра ({rus_day})"
        else:
            header = rus_day
        
        msg += f"📌 *{header}* {day_date.strftime('%d.%m')}\n"
        msg += f"🌡️ {day['temp_min']:.0f}°C ~ {day['temp_max']:.0f}°C\n"
        msg += f"☁️ {day['description'].capitalize()}\n💨 Ветер до {day['wind_speed']:.0f} м/с\n"
        if day.get('rain'): msg += "🌧️ Дожди\n"
        if day.get('snow'): msg += "🌨️ Снег\n"
        
        # Советы водителю — обязательно!
        tips = get_driver_tips(
            day['temp_day'], day['wind_speed'], day['humidity'],
            day['description'], day.get('rain', False), day.get('snow', False)
        )
        msg += f"🚗 *Советы:* {tips}\n\n"
        msg += "─" * 20 + "\n\n"
    return msg

# --------------------------------------------------------------
# ОЦЕНКА АВТОМОБИЛЕЙ (рыночная цена)
# --------------------------------------------------------------
def calculate_car_value(model: str, year: int, km: int) -> dict:
    current_year = datetime.now().year
    age = current_year - year
    specs = CARS_DB.get(model, {'price_new': 1000000, 'reliability': 70, 'parts_cost': 'средняя', 'fuel': 8.0})
    price_new = specs['price_new']

    year_depr = min(0.40, age * 0.05)
    km_depr = min(0.25, (km / 10000) * 0.003)
    total_depr = max(year_depr, km_depr)
    base_price = price_new * (1 - total_depr)

    rel = specs['reliability']
    if rel >= 90: rel_mult = 1.30
    elif rel >= 80: rel_mult = 1.15
    elif rel >= 70: rel_mult = 1.00
    elif rel >= 60: rel_mult = 0.90
    else: rel_mult = 0.80

    market_mult = 1.65
    if age <= 3: age_mult = 1.0
    elif age <= 7: age_mult = 0.95
    elif age <= 12: age_mult = 0.85
    elif age <= 18: age_mult = 0.75
    else: age_mult = 0.65

    final_price = base_price * rel_mult * market_mult * age_mult
    final_price = min(final_price, price_new * 1.0)
    final_price = max(final_price, 50000)
    final_price = int(final_price / 1000) * 1000

    if age <= 5 and km < 80000:
        condition, icon, verdict = "отличное", "✅", "Практически новый автомобиль. Отличный вариант!"
    elif age <= 8 and km < 130000:
        condition, icon, verdict = "хорошее", "🟢", "Хорошее состояние. Рекомендуется диагностика."
    elif age <= 12 and km < 180000:
        condition, icon, verdict = "среднее", "⚠️", "Среднее состояние. Требуется осмотр специалиста."
    elif age <= 18 and km < 250000:
        condition, icon, verdict = "выше среднего износа", "🔴", "Возраст сказывается, но ещё послужит."
    else:
        condition, icon, verdict = "высокий износ", "❌", "Автомобиль возрастной. Для опытных."

    recommendations = []
    if age > 7: recommendations.append("🔧 Проверить кузов на коррозию")
    if km > 120000: recommendations.append("⚙️ Диагностика двигателя и коробки")
    if age > 5 and km > 70000: recommendations.append("🛞 Состояние подвески и тормозов")
    if specs['parts_cost'] == 'высокая' and age > 5: recommendations.append("💰 Учитывайте стоимость запчастей")
    if 'Toyota' in model or 'Honda' in model: recommendations.append("🔑 Надёжная модель, но проверьте ходовую")
    if not recommendations: recommendations.append("✅ Стандартная диагностика перед покупкой")

    return {
        'success': True, 'model': model, 'year': year, 'age': age, 'km': km,
        'price_new': price_new, 'current_price': final_price,
        'condition': condition, 'condition_icon': icon, 'verdict': verdict,
        'reliability': specs['reliability'], 'parts_cost': specs['parts_cost'],
        'fuel_consumption': specs['fuel'], 'recommendations': recommendations,
        'year_depreciation': int(year_depr * 100), 'km_depreciation': int(km_depr * 100)
    }

def format_car_evaluation(eval_data: dict) -> str:
    msg = "🚗 *ОЦЕНКА АВТОМОБИЛЯ*\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    msg += f"📋 *{eval_data['model']}*\n• Год: {eval_data['year']} ({eval_data['age']} лет)\n• Пробег: {eval_data['km']:,} км\n\n"
    msg += f"💰 *СТОИМОСТЬ:*\n• Новая цена: {eval_data['price_new']:,} ₽\n• Рыночная цена: *{eval_data['current_price']:,} ₽*\n"
    msg += f"• Износ по годам: {eval_data['year_depreciation']}%\n• Износ по пробегу: {eval_data['km_depreciation']}%\n\n"
    msg += f"📊 *ХАРАКТЕРИСТИКИ:*\n• Надёжность: {eval_data['reliability']}/100\n• Расход: {eval_data['fuel_consumption']} л/100км\n• Запчасти: {eval_data['parts_cost']}\n\n"
    msg += f"{eval_data['condition_icon']} *СОСТОЯНИЕ:* {eval_data['condition'].upper()}\n\n"
    msg += f"🔍 *ЧТО ПРОВЕРИТЬ:*\n" + "\n".join(eval_data['recommendations'][:5]) + "\n\n"
    msg += f"💡 *ВЕРДИКТ:* {eval_data['verdict']}\n"
    msg += f"\n💰 *ДИАПАЗОН ЦЕН В ОБЪЯВЛЕНИЯХ:* {int(eval_data['current_price']*0.85):,} – {int(eval_data['current_price']*1.15):,} ₽"
    return msg

# --------------------------------------------------------------
# КЛАВИАТУРЫ
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
            [KeyboardButton(text="🇰🇷 KIA Rio"), KeyboardButton(text="🇰🇷 Hyundai Solaris")],
            [KeyboardButton(text="🇷🇺 Lada Granta"), KeyboardButton(text="🇷🇺 Lada Vesta")],
            [KeyboardButton(text="🇪🇺 Volkswagen Polo"), KeyboardButton(text="🇨🇳 Chery Tiggo T11")],
            [KeyboardButton(text="🚘 Другие модели"), KeyboardButton(text="⬅️ Назад в меню")]
        ],
        resize_keyboard=True
    )

def get_other_models_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🇯🇵 Toyota Camry"), KeyboardButton(text="🇯🇵 Nissan Qashqai")],
            [KeyboardButton(text="🇰🇷 KIA Sportage"), KeyboardButton(text="🇰🇷 Hyundai Creta")],
            [KeyboardButton(text="🇩🇪 BMW 3 series"), KeyboardButton(text="🇩🇪 Audi A4")],
            [KeyboardButton(text="🇺🇸 Chevrolet Lacetti"), KeyboardButton(text="🇨🇳 Geely Coolray")],
            [KeyboardButton(text="⬅️ Назад к моделям")]
        ],
        resize_keyboard=True
    )

# --------------------------------------------------------------
# ОБРАБОТЧИКИ
# --------------------------------------------------------------
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 *Добро пожаловать в AutoWeatherBot!*\n\n"
        "🚗 Я даю погоду с советами и оцениваю авто.\n"
        "📊 База: более 30 моделей.\n"
        "🌍 Города можно вводить на русском (автоматически переведу).\n\n"
        "👇 Выберите действие:",
        parse_mode="Markdown", reply_markup=get_main_keyboard()
    )

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
    await message.answer("🔍 Получаю прогноз на 5 дней...", parse_mode="Markdown")
    f = await asyncio.to_thread(get_5day_forecast, user_cities[cid])
    await message.answer(format_forecast_message(f), parse_mode="Markdown", reply_markup=get_weather_keyboard())

@dp.message(F.text == "🚗 Советы водителю")
async def driver_tips(message: Message):
    await message.answer(
        "🚗 *ПОЛЕЗНЫЕ СОВЕТЫ*\n\n"
        "❄️ Зимой: щетка, аккумулятор, дистанция ×2\n"
        "🌧️ В дождь: фары, дворники, дистанция ×2\n"
        "☀️ В жару: антифриз, кондиционер\n"
        "🌫️ В туман: противотуманки, скорость ниже\n"
        "⚠️ Гололед: плавно, торможение двигателем",
        parse_mode="Markdown", reply_markup=get_back_keyboard()
    )

@dp.message(F.text == "⚙️ Установить город")
async def set_city_prompt(message: Message):
    await message.answer("🌆 Напишите название города на русском или английском.\nНапример: Омск, Omsk, Москва", parse_mode="Markdown", reply_markup=get_back_keyboard())

@dp.message(F.text == "🚘 Оценить авто")
async def evaluate_car_start(message: Message):
    user_car_data[message.chat.id] = {}
    await message.answer(
        "🚘 *ОЦЕНКА АВТОМОБИЛЯ*\n\n"
        "Шаг 1. Введите **год выпуска** (4 цифры, например 2010):",
        parse_mode="Markdown", reply_markup=get_back_keyboard()
    )

# --------------------------------------------------------------
# УНИВЕРСАЛЬНЫЙ ОБРАБОТЧИК
# --------------------------------------------------------------
@dp.message()
async def handle_all_text(message: Message):
    cid = message.chat.id
    text = message.text.strip()

    # ----- РЕЖИМ ОЦЕНКИ АВТО -----
    if cid in user_car_data:
        data = user_car_data[cid]
        if 'year' not in data:
            if text.isdigit() and len(text) == 4:
                year = int(text)
                if 1970 <= year <= datetime.now().year:
                    data['year'] = year
                    await message.answer(f"✅ Год: {year}\n\nШаг 2. Введите **пробег в тысячах км** (например, 110):", parse_mode="Markdown")
                else:
                    await message.answer("❌ Введите год от 1970 до текущего")
            else:
                await message.answer("❌ Введите год цифрами, например 2010")
            return

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

        if 'model' not in data:
            model_map = {
                '🇯🇵 Toyota Vitz': 'Toyota Vitz', '🇯🇵 Toyota Corolla': 'Toyota Corolla', '🇯🇵 Toyota Camry': 'Toyota Camry',
                '🇰🇷 KIA Rio': 'KIA Rio', '🇰🇷 Hyundai Solaris': 'Hyundai Solaris', '🇰🇷 KIA Sportage': 'KIA Sportage',
                '🇰🇷 Hyundai Creta': 'Hyundai Creta', '🇷🇺 Lada Granta': 'Lada Granta', '🇷🇺 Lada Vesta': 'Lada Vesta',
                '🇪🇺 Volkswagen Polo': 'Volkswagen Polo', '🇨🇳 Chery Tiggo T11': 'Chery Tiggo T11',
                '🇯🇵 Nissan Qashqai': 'Nissan Qashqai', '🇩🇪 BMW 3 series': 'BMW 3 series', '🇩🇪 Audi A4': 'Audi A4',
                '🇺🇸 Chevrolet Lacetti': 'Chevrolet Lacetti', '🇨🇳 Geely Coolray': 'Geely Coolray'
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
                found = next((car for car in CARS_DB if text.lower() in car.lower()), None)
                if found:
                    data['model'] = found
                    evaluation = calculate_car_value(found, data['year'], data['km'])
                    await message.answer(format_car_evaluation(evaluation), parse_mode="Markdown", reply_markup=get_main_keyboard())
                    del user_car_data[cid]
                else:
                    await message.answer("❌ Модель не найдена. Выберите из списка или уточните название.", reply_markup=get_car_model_keyboard())
            return

    # ----- КОМАНДА УСТАНОВКИ ГОРОДА -----
    if text.startswith("/setcity"):
        city = text.replace("/setcity", "").strip()
        if city:
            city_lat = city_to_latin(city)
            w = await asyncio.to_thread(get_weather, city_lat)
            if w['success']:
                user_cities[cid] = city_lat
                await message.answer(f"✅ Город {city} установлен!", reply_markup=get_main_keyboard())
            else:
                await message.answer(f"❌ Город '{city}' не найден. Попробуйте написать на латинице (например, Omsk).")
        else:
            await message.answer("Напишите: /setcity Москва")
        return

    # ----- ВВОД ВРЕМЕНИ ДЛЯ ПОДПИСКИ -----
    if len(text) == 5 and text[2] == ':' and text[:2].isdigit() and text[3:].isdigit():
        h, m = int(text[:2]), int(text[3:])
        if 0 <= h <= 23 and 0 <= m <= 59:
            user_subscription_time[cid] = text
            await message.answer(f"✅ Время подписки: {text}", parse_mode="Markdown", reply_markup=get_subscription_keyboard())
            return

    # ----- ПОИСК ГОРОДА ДЛЯ ПОГОДЫ (с преобразованием) -----
    city_lat = city_to_latin(text)
    w = await asyncio.to_thread(get_weather, city_lat)
    if w['success']:
        user_cities[cid] = city_lat
        await message.answer(format_weather_message(w), parse_mode="Markdown", reply_markup=get_weather_keyboard())
    else:
        await message.answer(
            f"❌ Город '{text}' не найден.\n\n"
            "• Попробуйте написать на латинице (Omsk, Moscow)\n"
            "• Или используйте /setcity Москва\n"
            "• Для оценки авто нажмите 🚘 Оценить авто",
            reply_markup=get_main_keyboard()
        )

# --------------------------------------------------------------
# ОСТАЛЬНЫЕ КНОПКИ
# --------------------------------------------------------------
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
        await message.answer("❌ Вы отписались от рассылки", parse_mode="Markdown")
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
        "📅 Прогноз на 5 дней – с советами водителю\n"
        "🚗 Советы водителю – общие рекомендации\n"
        "🚘 Оценить авто – год, пробег, модель → рыночная цена\n"
        "⚙️ Установить город – можно на русском\n"
        "🔔 Подписка – ежедневный прогноз\n\n"
        "Команды: /start, /setcity Москва",
        parse_mode="Markdown", reply_markup=get_main_keyboard()
    )

@dp.message(F.text == "ℹ️ О боте")
async def about_bot(message: Message):
    await message.answer(
        "ℹ️ *О боте*\nВерсия 4.3\nПогода + оценка авто\nРеалистичные рыночные цены\n"
        "🌍 Поддержка русских названий городов\n📅 Прогноз на 5 дней включает советы водителю\n"
        "База из 30+ моделей авто",
        parse_mode="Markdown", reply_markup=get_back_keyboard()
    )

# --------------------------------------------------------------
# ЕЖЕДНЕВНАЯ РАССЫЛКА (прогноз с советами)
# --------------------------------------------------------------
def send_daily_weather():
    if not CHAT_ID:
        return
    cid = int(CHAT_ID)
    city = user_cities.get(cid, "Moscow")
    forecast = get_5day_forecast(city)
    if forecast['success']:
        asyncio.create_task(bot.send_message(chat_id=cid, text=format_forecast_message(forecast), parse_mode="Markdown"))

def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(30)

# --------------------------------------------------------------
# ЗАПУСК
# --------------------------------------------------------------
async def main():
    schedule.every().day.at("08:00").do(send_daily_weather)
    threading.Thread(target=run_schedule, daemon=True).start()
    print("\n" + "="*60)
    print("✅ AUTO-WEATHER-BOT 4.3 ЗАПУЩЕН")
    print("📅 Прогноз на 5 дней включает советы водителю")
    print("🌍 Русские названия городов автоматически переводятся в латиницу")
    print("💰 Оценка авто – реалистичные рыночные цены")
    print("="*60 + "\n")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

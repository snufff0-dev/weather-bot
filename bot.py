import os
import json
import logging
import asyncio
import threading
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import requests
import schedule

# ==================== ЗАГРУЗКА ПЕРЕМЕННЫХ ====================
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
TRONK_API_KEY = os.getenv('TRONK_API_KEY', '')   # API-ключ для сервиса TronK

BOT_VERSION = "2.5"

# ==================== ОБЩЕЕ ХРАНИЛИЩЕ (BOTHOST) ====================
SHARED_DIR = "/app/shared"
os.makedirs(SHARED_DIR, exist_ok=True)
USERS_FILE = os.path.join(SHARED_DIR, "users.json")
SUBSCRIBERS_FILE = os.path.join(SHARED_DIR, "subscribers.json")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ==================== ЗАГРУЗКА/СОХРАНЕНИЕ ДАННЫХ ====================
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('user_cities', {}), data.get('user_subscription_time', {}), data.get('version', '0')
    return {}, {}, '0'

def save_users(user_cities, user_subscription_time):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'user_cities': user_cities,
            'user_subscription_time': user_subscription_time,
            'version': BOT_VERSION
        }, f, ensure_ascii=False, indent=2)

def load_subscribers():
    if os.path.exists(SUBSCRIBERS_FILE):
        with open(SUBSCRIBERS_FILE, 'r', encoding='utf-8') as f:
            return set(json.load(f))
    return set()

def save_subscribers(subscribers):
    with open(SUBSCRIBERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(subscribers), f)

user_cities, user_subscription_time, saved_version = load_users()
subscribers = load_subscribers()          # множество chat_id подписчиков на ежедневную рассылку
user_car_data = {}
CAR_MODELS = []
ITEMS_PER_PAGE = 6

logging.basicConfig(level=logging.INFO)

# ==================== ПЕРЕВОД ГОРОДОВ ====================
RUS_TO_LAT = {
    'москва': 'Moscow', 'санкт-петербург': 'Saint Petersburg',
    'новосибирск': 'Novosibirsk', 'екатеринбург': 'Ekaterinburg',
    'казань': 'Kazan', 'омск': 'Omsk', 'красноярск': 'Krasnoyarsk',
    'владивосток': 'Vladivostok', 'нижний новгород': 'Nizhny Novgorod',
    'челябинск': 'Chelyabinsk', 'самара': 'Samara'
}

def city_to_latin(name: str) -> str:
    low = name.strip().lower()
    if low in RUS_TO_LAT:
        return RUS_TO_LAT[low]
    trans = {'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z',
             'и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r',
             'с':'s','т':'t','у':'u','ф':'f','х':'kh','ц':'ts','ч':'ch','ш':'sh',
             'щ':'shch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'}
    return ''.join(trans.get(ch, ch) for ch in low).title()

# ==================== БАЗА АВТОМОБИЛЕЙ ====================
CARS_DB = {
    'Lada Vesta': {'price_new': 1200000, 'reliability': 70, 'parts_cost': 'низкая', 'fuel': 7.5},
    'Lada Granta': {'price_new': 800000, 'reliability': 65, 'parts_cost': 'низкая', 'fuel': 7.0},
    'Lada Niva Travel': {'price_new': 1400000, 'reliability': 60, 'parts_cost': 'низкая', 'fuel': 9.5},
    'УАЗ Patriot': {'price_new': 1500000, 'reliability': 55, 'parts_cost': 'средняя', 'fuel': 11.0},
    'KIA Rio': {'price_new': 1300000, 'reliability': 85, 'parts_cost': 'средняя', 'fuel': 7.3},
    'KIA Sportage': {'price_new': 2100000, 'reliability': 84, 'parts_cost': 'средняя', 'fuel': 8.7},
    'Hyundai Solaris': {'price_new': 1280000, 'reliability': 85, 'parts_cost': 'средняя', 'fuel': 7.2},
    'Hyundai Creta': {'price_new': 1800000, 'reliability': 85, 'parts_cost': 'средняя', 'fuel': 8.5},
    'Toyota Vitz': {'price_new': 800000, 'reliability': 92, 'parts_cost': 'средняя', 'fuel': 6.5},
    'Toyota Corolla': {'price_new': 2000000, 'reliability': 95, 'parts_cost': 'средняя', 'fuel': 7.5},
    'Toyota Camry': {'price_new': 3500000, 'reliability': 95, 'parts_cost': 'высокая', 'fuel': 8.5},
    'Toyota RAV4': {'price_new': 2700000, 'reliability': 92, 'parts_cost': 'средняя', 'fuel': 8.0},
    'Nissan Qashqai': {'price_new': 2200000, 'reliability': 80, 'parts_cost': 'средняя', 'fuel': 8.0},
    'Nissan X-Trail': {'price_new': 2600000, 'reliability': 79, 'parts_cost': 'средняя', 'fuel': 8.5},
    'Mazda CX-5': {'price_new': 2500000, 'reliability': 85, 'parts_cost': 'средняя', 'fuel': 8.2},
    'Honda CR-V': {'price_new': 3000000, 'reliability': 92, 'parts_cost': 'высокая', 'fuel': 8.5},
    'Volkswagen Polo': {'price_new': 1350000, 'reliability': 80, 'parts_cost': 'средняя', 'fuel': 7.2},
    'Skoda Rapid': {'price_new': 1400000, 'reliability': 80, 'parts_cost': 'средняя', 'fuel': 7.0},
    'Renault Logan': {'price_new': 1100000, 'reliability': 75, 'parts_cost': 'низкая', 'fuel': 7.0},
    'Renault Duster': {'price_new': 1400000, 'reliability': 74, 'parts_cost': 'низкая', 'fuel': 8.0},
    'Ford Focus': {'price_new': 1700000, 'reliability': 75, 'parts_cost': 'средняя', 'fuel': 7.5},
    'Chery Tiggo T11': {'price_new': 800000, 'reliability': 65, 'parts_cost': 'средняя', 'fuel': 9.5},
    'Chery Tiggo 7 Pro': {'price_new': 2300000, 'reliability': 75, 'parts_cost': 'средняя', 'fuel': 8.5},
    'Haval Jolion': {'price_new': 2100000, 'reliability': 78, 'parts_cost': 'средняя', 'fuel': 8.3},
    'Geely Coolray': {'price_new': 1900000, 'reliability': 76, 'parts_cost': 'средняя', 'fuel': 8.0},
    'BMW 3 series': {'price_new': 3800000, 'reliability': 75, 'parts_cost': 'высокая', 'fuel': 8.5},
    'BMW 5 series': {'price_new': 5500000, 'reliability': 72, 'parts_cost': 'высокая', 'fuel': 9.0},
    'Mercedes-Benz C-class': {'price_new': 4200000, 'reliability': 78, 'parts_cost': 'высокая', 'fuel': 8.5},
    'Mercedes-Benz E-class': {'price_new': 6000000, 'reliability': 75, 'parts_cost': 'высокая', 'fuel': 9.0},
    'Audi A4': {'price_new': 3600000, 'reliability': 76, 'parts_cost': 'высокая', 'fuel': 8.3},
    'Audi A6': {'price_new': 5000000, 'reliability': 74, 'parts_cost': 'высокая', 'fuel': 8.8},
    'Chevrolet Lacetti': {'price_new': 700000, 'reliability': 70, 'parts_cost': 'низкая', 'fuel': 8.0},
    'Chevrolet Cruze': {'price_new': 900000, 'reliability': 68, 'parts_cost': 'средняя', 'fuel': 8.5},
}

CAR_MODELS = sorted(CARS_DB.keys())

def get_car_keyboard(page: int) -> InlineKeyboardMarkup:
    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    models_on_page = CAR_MODELS[start:end]
    buttons = []
    for model in models_on_page:
        buttons.append([InlineKeyboardButton(text=model, callback_data=f"car_{model}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"car_page_{page-1}"))
    if end < len(CAR_MODELS):
        nav.append(InlineKeyboardButton(text="➡️ Далее", callback_data=f"car_page_{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="car_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ==================== TRONK API (ПРОВЕРКА АВТО ПО VIN) ====================
def check_car_report(vin: str) -> str:
    if not TRONK_API_KEY:
        return "❌ API-ключ TronK не настроен. Обратитесь к администратору."
    url = "https://data.tronk.info/profile.ashx"
    params = {"key": TRONK_API_KEY, "vin": vin.upper()}
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            return f"❌ Ошибка TronK: {data.get('error_msg', 'Неизвестная ошибка')}"
        result = data.get("result", {})
        report = (
            f"🚗 *Отчёт по VIN* `{vin.upper()}`\n"
            f"• Доступов: {result.get('accessTo', 'Нет данных')}\n"
            f"• Баланс: {result.get('accountBalance', 'Н/Д')}\n"
            f"• Кликов: {result.get('leftClicks', 'Н/Д')}\n"
            "📌 *Активные методы:*\n"
        )
        methods = result.get("activeMethods", {})
        for method, enabled in methods.items():
            report += f"  - {method}: {'✅' if enabled else '❌'}\n"
        return report
    except Exception as e:
        return f"❌ Ошибка подключения к TronK: {e}"

# ==================== ПОГОДНЫЕ ФУНКЦИИ ====================
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
        tips.append("⚠️ Гололед, увеличьте дистанцию")
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

# ==================== ОЦЕНКА АВТО (МОДЕЛЬ+ГОД+ПРОБЕГ) ====================
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
        condition, icon, verdict = "хорошее", "🟢", "Хорошее состояние. Перед покупкой желательна диагностика."
    elif age <= 12 and km < 180000:
        condition, icon, verdict = "среднее", "⚠️", "Среднее состояние. Требуется осмотр у специалиста."
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
    msg += f"📋 *{eval_data['model']}*\n• Год выпуска: {eval_data['year']} ({eval_data['age']} лет)\n• Пробег: {eval_data['km']:,} км\n\n"
    msg += f"💰 *СТОИМОСТЬ (рынок 2025):*\n• Новая цена (в ценах того года): {eval_data['price_new']:,} ₽\n"
    msg += f"• Рыночная цена: *{eval_data['current_price']:,} ₽*\n• Износ по годам: {eval_data['year_depreciation']}%\n"
    msg += f"• Износ по пробегу: {eval_data['km_depreciation']}%\n\n"
    msg += f"📊 *ХАРАКТЕРИСТИКИ:*\n• Надёжность: {eval_data['reliability']}/100\n"
    msg += f"• Расход топлива: {eval_data['fuel_consumption']} л/100км\n• Стоимость запчастей: {eval_data['parts_cost']}\n\n"
    msg += f"{eval_data['condition_icon']} *СОСТОЯНИЕ:* {eval_data['condition'].upper()}\n\n"
    msg += f"🔍 *ЧТО ПРОВЕРИТЬ ПРИ ПОКУПКЕ:*\n" + "\n".join(eval_data['recommendations'][:5]) + "\n\n"
    msg += f"💡 *ВЕРДИКТ:* {eval_data['verdict']}\n"
    msg += f"\n💰 *ДИАПАЗОН ЦЕН В ОБЪЯВЛЕНИЯХ:* {int(eval_data['current_price']*0.85):,} – {int(eval_data['current_price']*1.15):,} ₽"
    return msg

# ==================== КЛАВИАТУРЫ ====================
def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🌤 Погода сейчас"), KeyboardButton(text="📅 Прогноз на 5 дней")],
        [KeyboardButton(text="🛠 Помощь при покупке авто"), KeyboardButton(text="🔎 Проверить авто (VIN)")],
        [KeyboardButton(text="🔔 Подписка"), KeyboardButton(text="❓ Помощь")]
    ], resize_keyboard=True)

def sub_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="✅ Подписаться"), KeyboardButton(text="❌ Отписаться")],
        [KeyboardButton(text="⏰ Время"), KeyboardButton(text="📊 Статус")],
        [KeyboardButton(text="⬅️ Назад")]
    ], resize_keyboard=True)

def back_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True)

# ==================== ОБРАБОТЧИКИ КОМАНД ====================
@dp.message(Command("start"))
async def start_cmd(msg: Message):
    await msg.answer(
        "👋 *Добро пожаловать в бот для водителей!*\n\n"
        "🌦 **Погода для водителей** – текущая погода и прогноз на 5 дней с полезными советами.\n"
        "🛠 **Помощь при покупке авто** – рыночная оценка автомобиля по году, пробегу и модели.\n"
        "🔎 **Проверить авто (VIN)** – получение отчёта через сервис TronK (если ключ настроен).\n\n"
        "❗️ *Важно:* для получения погоды сначала напишите название вашего города (например, *Москва* или *Omsk*).\n\n"
        "Выберите действие:",
        parse_mode="Markdown", reply_markup=main_kb()
    )

@dp.message(Command("broadcast"))
async def broadcast_cmd(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        await msg.answer("⛔ Нет прав.")
        return
    text = msg.text.replace("/broadcast", "").strip()
    if not text:
        await msg.answer("Формат: /broadcast <текст>")
        return
    count = 0
    for uid in user_cities.keys():
        try:
            await bot.send_message(int(uid), text, parse_mode="Markdown")
            count += 1
            await asyncio.sleep(0.05)
        except:
            pass
    await msg.answer(f"✅ Отправлено {count} пользователям.")

@dp.message(Command("stats"))
async def show_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Только для администратора.")
        return
    total = len(user_cities)
    subscribed = len(subscribers)
    await message.answer(
        f"📊 *Статистика бота*\n\n"
        f"👥 Всего пользователей: {total}\n"
        f"🔔 Подписано на рассылку: {subscribed}\n"
        f"📁 Файл данных: {USERS_FILE}\n"
        f"📁 Файл подписчиков: {SUBSCRIBERS_FILE}\n"
        f"💾 Размер файла: {os.path.getsize(USERS_FILE) if os.path.exists(USERS_FILE) else 0} байт",
        parse_mode="Markdown"
    )

@dp.message(Command("users_list"))
async def users_list(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Только для администратора.")
        return
    if not user_cities:
        await message.answer("📭 Список пользователей пуст.")
        return
    user_list = []
    for i, (uid, city) in enumerate(list(user_cities.items())[:20]):
        sub_time = user_subscription_time.get(uid, "не подписан")
        user_list.append(f"{i+1}. ID: `{uid}`, город: {city}, рассылка: {sub_time}")
    msg = "👥 *Список пользователей (первые 20):*\n\n" + "\n".join(user_list)
    if len(user_cities) > 20:
        msg += f"\n\n... и ещё {len(user_cities) - 20} пользователей."
    await message.answer(msg, parse_mode="Markdown")

@dp.message(Command("unsubscribe_user"))
async def unsubscribe_user(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Только для администратора.")
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Формат: /unsubscribe_user <user_id>")
        return
    uid = parts[1]
    if uid in user_cities:
        if uid in subscribers:
            subscribers.discard(uid)
            save_subscribers(subscribers)
        del user_cities[uid]
        if uid in user_subscription_time:
            del user_subscription_time[uid]
        save_users(user_cities, user_subscription_time)
        await message.answer(f"✅ Пользователь {uid} отписан и удалён из базы.")
    else:
        await message.answer(f"❌ Пользователь {uid} не найден в базе.")

@dp.message(Command("check_storage"))
async def check_storage(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Только для администратора.")
        return
    report = []
    for fpath in [USERS_FILE, SUBSCRIBERS_FILE]:
        if os.path.exists(fpath):
            report.append(f"✅ {fpath} существует, размер {os.path.getsize(fpath)} байт.")
        else:
            report.append(f"❌ {fpath} не существует.")
    test_file = os.path.join(SHARED_DIR, "test_write.txt")
    try:
        with open(test_file, 'w') as f:
            f.write("test")
        os.remove(test_file)
        report.append("✅ Права на запись в /app/shared есть.")
    except Exception as e:
        report.append(f"❌ НЕТ ПРАВ НА ЗАПИСЬ: {e}")
    await message.answer("\n".join(report), parse_mode="Markdown")

# ==================== ПОГОДА ====================
@dp.message(F.text == "🌤 Погода сейчас")
async def weather_now(msg: Message):
    cid = msg.chat.id
    if cid not in user_cities:
        await msg.answer("🌆 Сначала напишите название вашего города (например, *Москва*, *Омск*, *Omsk*).", parse_mode="Markdown")
        return
    w = await asyncio.to_thread(get_weather, user_cities[cid])
    await msg.answer(format_weather(w), parse_mode="Markdown", reply_markup=main_kb())

@dp.message(F.text == "📅 Прогноз на 5 дней")
async def forecast_5(msg: Message):
    cid = msg.chat.id
    if cid not in user_cities:
        await msg.answer("🌆 Сначала напишите название вашего города.", parse_mode="Markdown")
        return
    f = await asyncio.to_thread(get_5day_forecast, user_cities[cid])
    await msg.answer(format_forecast(f), parse_mode="Markdown", reply_markup=main_kb())

# ==================== ПОМОЩЬ ПРИ ПОКУПКЕ АВТО ====================
@dp.message(F.text == "🛠 Помощь при покупке авто")
async def eval_start(msg: Message):
    user_car_data[msg.chat.id] = {}
    await msg.answer(
        "🛠 *Помощь при покупке автомобиля*\n\n"
        "Шаг 1: Введите **год выпуска** (4 цифры, например 2010):",
        parse_mode="Markdown", reply_markup=back_kb()
    )

@dp.callback_query(lambda c: c.data.startswith(("car_page_", "car_", "car_cancel")))
async def car_navigation(callback: CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data

    if data == "car_cancel":
        await callback.message.edit_text("❌ Выбор модели отменён.")
        if user_id in user_car_data:
            del user_car_data[user_id]
        await callback.answer()
        return

    if data.startswith("car_page_"):
        page = int(data.split("_")[2])
        await callback.message.edit_reply_markup(reply_markup=get_car_keyboard(page))
        await callback.answer()
        return

    if data.startswith("car_"):
        model = data[4:]
        if user_id in user_car_data and 'year' in user_car_data[user_id] and 'km' in user_car_data[user_id]:
            eval_data = calculate_car_value(model, user_car_data[user_id]['year'], user_car_data[user_id]['km'])
            await callback.message.edit_text(format_car_evaluation(eval_data), parse_mode="Markdown")
            del user_car_data[user_id]
            await callback.answer()
            await callback.message.answer("🔹 Главное меню", reply_markup=main_kb())
        else:
            await callback.answer("Ошибка: сначала введите год и пробег.", show_alert=True)

# ==================== VIN ПРОВЕРКА (TRONK) ====================
@dp.message(F.text == "🔎 Проверить авто (VIN)")
async def ask_vin(msg: Message):
    await msg.answer(
        "Введите VIN-номер автомобиля (17 символов) или госномер.\n"
        "Пример VIN: WDB2201751A123456\n\n"
        "Если VIN не 17 символов, я всё равно отправлю запрос, но лучше проверить длину.",
        reply_markup=back_kb()
    )

# Обработчик текстового ввода VIN (без команды /checkcar, чтобы было удобнее)
# Сработает, если пользователь отправил текст, не являющийся годом/пробегом и т.д.
# Но нужно аккуратно, чтобы не перехватить другие сообщения.
# Сделаем отдельную проверку: если нажал кнопку "Проверить авто", то следующий текст считаем VIN.
# Для этого используем временное состояние.

user_vin_state = {}  # {chat_id: ожидание ввода VIN}

@dp.message(F.text == "🔎 Проверить авто (VIN)")
async def ask_vin_handler(msg: Message):
    user_vin_state[msg.chat.id] = True
    await msg.answer(
        "Отправьте VIN номер (17 символов) или государственный номер автомобиля.",
        reply_markup=back_kb()
    )

@dp.message()
async def handle_vin_input(msg: Message):
    cid = msg.chat.id
    # Если пользователь находится в режиме ожидания VIN
    if user_vin_state.get(cid):
        vin = msg.text.strip().upper().replace(" ", "")
        user_vin_state.pop(cid, None)
        if not TRONK_API_KEY:
            await msg.answer("❌ Сервис проверки VIN не настроен (отсутствует API-ключ). Обратитесь к администратору.", reply_markup=main_kb())
        else:
            report = await asyncio.to_thread(check_car_report, vin)
            await msg.answer(report, parse_mode="Markdown", reply_markup=main_kb())
        return
    # Далее обрабатываем остальные текстовые сообщения (город, время, год для оценки)
    # (код ниже взят из вашего исходного обработчика handle_text)

    # Режим оценки авто (год, пробег)
    if cid in user_car_data:
        data = user_car_data[cid]
        if 'year' not in data:
            if msg.text.isdigit() and 1970 <= int(msg.text) <= datetime.now().year:
                data['year'] = int(msg.text)
                await msg.answer("Шаг 2: Введите пробег в **тысячах км** (например 110):", parse_mode="Markdown")
            else:
                await msg.answer("❌ Введите год цифрами от 1970 до текущего")
            return
        if 'km' not in data:
            try:
                km = int(msg.text)
                if 0 <= km <= 800:
                    data['km'] = km * 1000
                    await msg.answer("Шаг 3: Выберите модель автомобиля:", reply_markup=get_car_keyboard(0))
                else:
                    await msg.answer("❌ Пробег должен быть от 0 до 800 тыс. км")
            except ValueError:
                await msg.answer("❌ Введите пробег цифрами (например, 110)")
            return

    # Установка времени подписки
    text = msg.text.strip()
    if len(text) == 5 and text[2] == ':' and text[:2].isdigit() and text[3:].isdigit():
        h, m = int(text[:2]), int(text[3:])
        if 0 <= h <= 23 and 0 <= m <= 59:
            user_subscription_time[cid] = text
            save_users(user_cities, user_subscription_time)
            await msg.answer(f"✅ Время установлено: {text}", reply_markup=sub_kb())
        else:
            await msg.answer("❌ Неверный формат времени")
        return

    # Город
    city_lat = city_to_latin(text)
    w = await asyncio.to_thread(get_weather, city_lat)
    if w['ok']:
        user_cities[cid] = city_lat
        save_users(user_cities, user_subscription_time)
        await msg.answer(f"✅ Город {text} установлен! Теперь можно запрашивать погоду.", reply_markup=main_kb())
        await msg.answer(format_weather(w), parse_mode="Markdown")
    else:
        await msg.answer(
            f"❌ Город '{text}' не найден.\n\n"
            "Попробуйте написать название на русском (Москва, Омск) или латинице (Moscow, Omsk).\n"
            "Если вы хотели оценить автомобиль, нажмите кнопку 🛠 Помощь при покупке авто.",
            reply_markup=main_kb()
        )

# ==================== ПОДПИСКА ====================
@dp.message(F.text == "🔔 Подписка")
async def sub_menu(msg: Message):
    await msg.answer("Настройка ежедневной рассылки:", reply_markup=sub_kb())

@dp.message(F.text == "✅ Подписаться")
async def subscribe(msg: Message):
    cid = msg.chat.id
    if cid not in user_cities:
        await msg.answer("Сначала установите город, написав его название.", reply_markup=main_kb())
        return
    subscribers.add(cid)
    save_subscribers(subscribers)
    await msg.answer("✅ Вы подписаны на ежедневный прогноз в 08:00", reply_markup=main_kb())

@dp.message(F.text == "❌ Отписаться")
async def unsubscribe(msg: Message):
    cid = msg.chat.id
    if cid in subscribers:
        subscribers.discard(cid)
        save_subscribers(subscribers)
        await msg.answer("❌ Вы отписались", reply_markup=main_kb())
    else:
        await msg.answer("❌ Вы не были подписаны", reply_markup=main_kb())

@dp.message(F.text == "⏰ Время")
async def set_time_prompt(msg: Message):
    await msg.answer("Введите время в формате ЧЧ:ММ (например 08:00):", reply_markup=back_kb())

@dp.message(F.text == "📊 Статус")
async def status_sub(msg: Message):
    cid = msg.chat.id
    if cid in subscribers:
        city = user_cities.get(cid, "не задан")
        t = user_subscription_time.get(cid, "08:00")
        await msg.answer(f"✅ Подписка активна\n🏙️ Город: {city}\n⏰ Время: {t}", reply_markup=main_kb())
    else:
        await msg.answer("❌ Подписка не активна", reply_markup=main_kb())

@dp.message(F.text == "❓ Помощь")
async def help_msg(msg: Message):
    await msg.answer(
        "📋 *Доступные команды:*\n"
        "🌤 Погода сейчас – текущая погода с советами\n"
        "📅 Прогноз на 5 дней – подробный прогноз\n"
        "🛠 Помощь при покупке авто – оценка стоимости и проверки\n"
        "🔎 Проверить авто (VIN) – отчёт по VIN через TronK (если ключ настроен)\n"
        "🔔 Подписка – ежедневная рассылка\n\n"
        "❗️ Чтобы получить погоду, сначала напишите название города (Москва, Омск, Omsk).",
        parse_mode="Markdown", reply_markup=main_kb()
    )

@dp.message(F.text == "⬅️ Назад")
async def back(msg: Message):
    user_car_data.pop(msg.chat.id, None)
    user_vin_state.pop(msg.chat.id, None)
    await msg.answer("Главное меню", reply_markup=main_kb())

# ==================== ЕЖЕДНЕВНАЯ РАССЫЛКА ====================
def send_daily():
    if not subscribers:
        return
    for cid in subscribers:
        city = user_cities.get(cid, "Moscow")
        f = get_5day_forecast(city)
        if f['ok']:
            asyncio.create_task(bot.send_message(cid, format_forecast(f), parse_mode="Markdown"))
        else:
            asyncio.create_task(bot.send_message(cid, "❌ Не удалось получить прогноз для вашего города."))

def schedule_loop():
    schedule.every().day.at("08:00").do(send_daily)
    while True:
        schedule.run_pending()
        time.sleep(30)

# ==================== ОПОВЕЩЕНИЕ ОБ ОБНОВЛЕНИИ ====================
async def notify_update():
    if saved_version != BOT_VERSION:
        for uid in user_cities.keys():
            try:
                await bot.send_message(int(uid), "🔔 *Бот обновился!* Пожалуйста, отправьте команду /start для корректной работы.", parse_mode="Markdown")
                await asyncio.sleep(0.05)
            except:
                pass
        save_users(user_cities, user_subscription_time)

# ==================== ЗАПУСК ====================
async def main():
    await notify_update()
    threading.Thread(target=schedule_loop, daemon=True).start()
    print(f"✅ Бот запущен. Версия {BOT_VERSION}. Доступно моделей: {len(CAR_MODELS)}")
    if not TRONK_API_KEY:
        print("⚠️ TronK API ключ не задан. Команда проверки VIN работать не будет.")
    else:
        print("✅ TronK API ключ загружен.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

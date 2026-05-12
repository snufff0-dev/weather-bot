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


load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')
CHAT_ID = os.getenv('CHAT_ID')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

BOT_VERSION = "2.3"

# Папка общего хранилища Bothost
SHARED_DIR = "/app/shared"
os.makedirs(SHARED_DIR, exist_ok=True)
USERS_FILE = os.path.join(SHARED_DIR, "users.json")   # ← УБЕРИТЕ второе присвоение ниже

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ---------- ЗАГРУЗКА/СОХРАНЕНИЕ ПОЛЬЗОВАТЕЛЕЙ ----------
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

user_cities, user_subscription_time, saved_version = load_users()
user_car_data = {}
CAR_MODELS = []      # заполнится позже
ITEMS_PER_PAGE = 6

async def notify_update():
    if saved_version != BOT_VERSION:
        for uid in user_cities.keys():
            try:
                await bot.send_message(int(uid), "🔔 *Бот обновился!* Пожалуйста, отправьте команду /start для корректной работы.", parse_mode="Markdown")
                await asyncio.sleep(0.05)
            except:
                pass
        save_users(user_cities, user_subscription_time)

logging.basicConfig(level=logging.INFO)

# ---------- ПЕРЕВОД ГОРОДОВ ----------
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

# ---------- БАЗА АВТО (35+ МОДЕЛЕЙ) ----------
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

# Сортируем модели по алфавиту
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

# ---------- ОЦЕНКА АВТО (подробная) ----------
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

# ---------- КЛАВИАТУРЫ ----------
def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🌤 Погода сейчас"), KeyboardButton(text="📅 Прогноз на 5 дней")],
        [KeyboardButton(text="🛠 Помощь при покупке авто")],
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

# ---------- ОБРАБОТЧИКИ ----------
@dp.message(Command("start"))
async def start_cmd(msg: Message):
    await msg.answer(
        "👋 *Добро пожаловать в бот для водителей!*\n\n"
        "🌦 **Погода для водителей** – текущая погода и прогноз на 5 дней с полезными советами.\n"
        "🛠 **Помощь при покупке авто** – рыночная оценка автомобиля по году, пробегу и модели.\n\n"
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

# ---------- ПОГОДА ----------
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

# ---------- ПОМОЩЬ ПРИ ПОКУПКЕ ----------
@dp.message(F.text == "🛠 Помощь при покупке авто")
async def eval_start(msg: Message):
    user_car_data[msg.chat.id] = {}
    await msg.answer(
        "🛠 *Помощь при покупке автомобиля*\n\n"
        "Шаг 1: Введите **год выпуска** (4 цифры, например 2010):",
        parse_mode="Markdown", reply_markup=back_kb()
    )

# Обработка инлайн-выбора модели
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
            # После оценки возвращаем главное меню
            await callback.message.answer("🔹 Главное меню", reply_markup=main_kb())
        else:
            await callback.answer("Ошибка: сначала введите год и пробег.", show_alert=True)

# ---------- ПОДПИСКА ----------
@dp.message(F.text == "🔔 Подписка")
async def sub_menu(msg: Message):
    await msg.answer("Настройка ежедневной рассылки:", reply_markup=sub_kb())

@dp.message(F.text == "✅ Подписаться")
async def subscribe(msg: Message):
    global CHAT_ID
    cid = msg.chat.id
    if cid not in user_cities:
        await msg.answer("Сначала установите город, написав его название.", reply_markup=main_kb())
        return
    CHAT_ID = str(cid)
    save_users(user_cities, user_subscription_time)
    await msg.answer("✅ Вы подписаны на ежедневный прогноз в 08:00", reply_markup=main_kb())

@dp.message(F.text == "❌ Отписаться")
async def unsubscribe(msg: Message):
    global CHAT_ID
    cid = msg.chat.id
    if CHAT_ID and int(CHAT_ID) == cid:
        CHAT_ID = None
        await msg.answer("❌ Вы отписались", reply_markup=main_kb())
    else:
        await msg.answer("❌ Вы не были подписаны", reply_markup=main_kb())

@dp.message(F.text == "⏰ Время")
async def set_time_prompt(msg: Message):
    await msg.answer("Введите время в формате ЧЧ:ММ (например 08:00):", reply_markup=back_kb())

@dp.message(F.text == "📊 Статус")
async def status_sub(msg: Message):
    global CHAT_ID
    cid = msg.chat.id
    if CHAT_ID and int(CHAT_ID) == cid:
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
        "🔔 Подписка – ежедневная рассылка\n\n"
        "❗️ Чтобы получить погоду, сначала напишите название города (Москва, Омск, Omsk).",
        parse_mode="Markdown", reply_markup=main_kb()
    )

@dp.message(F.text == "⬅️ Назад")
async def back(msg: Message):
    user_car_data.pop(msg.chat.id, None)
    await msg.answer("Главное меню", reply_markup=main_kb())

# ---------- ОБРАБОТКА ВВОДА (год, пробег, город, время) ----------
@dp.message()
async def handle_text(msg: Message):
    cid = msg.chat.id
    text = msg.text.strip()

    # Режим оценки авто
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
                    # Показать пагинацию со всеми моделями
                    await msg.answer("Шаг 3: Выберите модель автомобиля:", reply_markup=get_car_keyboard(0))
                else:
                    await msg.answer("❌ Пробег должен быть от 0 до 800 тыс. км")
            except ValueError:
                await msg.answer("❌ Введите пробег цифрами (например, 110)")
            return
        # Если модель уже выбрана через инлайн-кнопку, здесь ничего не делаем
        return

    # Установка времени подписки
    if len(text) == 5 and text[2] == ':' and text[:2].isdigit() and text[3:].isdigit():
        h, m = int(text[:2]), int(text[3:])
        if 0 <= h <= 23 and 0 <= m <= 59:
            user_subscription_time[cid] = text
            save_users(user_cities, user_subscription_time)
            await msg.answer(f"✅ Время установлено: {text}", reply_markup=sub_kb())
        else:
            await msg.answer("❌ Неверный формат времени")
        return

    # Город (установка)
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

# ---------- РАССЫЛКА ----------
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
    await notify_update()
    threading.Thread(target=schedule_loop, daemon=True).start()
    print(f"✅ Бот запущен. Версия {BOT_VERSION}. Доступно моделей: {len(CAR_MODELS)}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

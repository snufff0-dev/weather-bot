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

# ---------- ПЕРЕВОД РУССКИХ ГОРОДОВ В ЛАТИНИЦУ ----------
RUS_TO_LAT = {
    'москва': 'Moscow', 'санкт-петербург': 'Saint Petersburg',
    'новосибирск': 'Novosibirsk', 'екатеринбург': 'Ekaterinburg',
    'казань': 'Kazan', 'омск': 'Omsk', 'красноярск': 'Krasnoyarsk',
    'владивосток': 'Vladivostok'
}

def city_to_latin(name: str) -> str:
    name = name.strip().lower()
    if name in RUS_TO_LAT:
        return RUS_TO_LAT[name]
    return name.title()  # если не нашли, оставляем как есть с заглавной

# ---------- БАЗА ДАННЫХ АВТОМОБИЛЕЙ ----------
CARS_DB = {
    'Toyota Vitz': {'price_new': 800000, 'reliability': 92, 'parts_cost': 'средняя', 'fuel': 6.5},
    'Toyota Corolla': {'price_new': 2000000, 'reliability': 95, 'parts_cost': 'средняя', 'fuel': 7.5},
    'Toyota Camry': {'price_new': 3500000, 'reliability': 95, 'parts_cost': 'высокая', 'fuel': 8.5},
    'KIA Rio': {'price_new': 1300000, 'reliability': 85, 'parts_cost': 'средняя', 'fuel': 7.3},
    'Hyundai Solaris': {'price_new': 1280000, 'reliability': 85, 'parts_cost': 'средняя', 'fuel': 7.2},
    'Lada Vesta': {'price_new': 1200000, 'reliability': 70, 'parts_cost': 'низкая', 'fuel': 7.5},
    'Lada Granta': {'price_new': 800000, 'reliability': 65, 'parts_cost': 'низкая', 'fuel': 7.0},
    'Volkswagen Polo': {'price_new': 1350000, 'reliability': 80, 'parts_cost': 'средняя', 'fuel': 7.2},
    'Chery Tiggo T11': {'price_new': 800000, 'reliability': 65, 'parts_cost': 'средняя', 'fuel': 9.5},
    'Renault Logan': {'price_new': 1100000, 'reliability': 75, 'parts_cost': 'низкая', 'fuel': 7.0},
    'Nissan Qashqai': {'price_new': 2200000, 'reliability': 80, 'parts_cost': 'средняя', 'fuel': 8.0},
    'BMW 3 series': {'price_new': 3800000, 'reliability': 75, 'parts_cost': 'высокая', 'fuel': 8.5},
    'Mercedes-Benz C-class': {'price_new': 4200000, 'reliability': 78, 'parts_cost': 'высокая', 'fuel': 8.5},
}

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

# ---------- ОЦЕНКА АВТОМОБИЛЯ (ПОДРОБНАЯ) ----------
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

    market_mult = 1.65
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
    final_price = min(final_price, price_new * 1.0)
    final_price = max(final_price, 50000)
    final_price = int(final_price / 1000) * 1000

    if age <= 5 and km < 80000:
        condition = "отличное"
        condition_icon = "✅"
        verdict = "Практически новый автомобиль. Отличный вариант!"
    elif age <= 8 and km < 130000:
        condition = "хорошее"
        condition_icon = "🟢"
        verdict = "Хорошее состояние. Рекомендуется диагностика."
    elif age <= 12 and km < 180000:
        condition = "среднее"
        condition_icon = "⚠️"
        verdict = "Среднее состояние. Требуется осмотр специалиста."
    elif age <= 18 and km < 250000:
        condition = "выше среднего износа"
        condition_icon = "🔴"
        verdict = "Возраст сказывается, но ещё послужит."
    else:
        condition = "высокий износ"
        condition_icon = "❌"
        verdict = "Автомобиль возрастной. Для опытных."

    recommendations = []
    if age > 7:
        recommendations.append("🔧 Проверить кузов на коррозию")
    if km > 120000:
        recommendations.append("⚙️ Диагностика двигателя и коробки")
    if age > 5 and km > 70000:
        recommendations.append("🛞 Состояние подвески и тормозов")
    if specs['parts_cost'] == 'высокая' and age > 5:
        recommendations.append("💰 Учитывайте стоимость запчастей")
    if 'Toyota' in model or 'Honda' in model:
        recommendations.append("🔑 Надёжная модель, но проверьте ходовую")
    if not recommendations:
        recommendations.append("✅ Стандартная диагностика перед покупкой")

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
    msg += f"\n💰 *ДИАПАЗОН ЦЕН В ОБЪЯВЛЕНИЯХ:* {int(eval_data['current_price']*0.85):,} – {int(eval_data['current_price']*1.15):,} ₽"
    return msg

# ---------- КЛАВИАТУРЫ ----------
def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🌤 Погода сейчас"), KeyboardButton(text="📅 Прогноз на 5 дней")],
        [KeyboardButton(text="🛠 Помощь при покупке авто")],
        [KeyboardButton(text="🔔 Подписка"), KeyboardButton(text="⚙️ Настройки")]
    ], resize_keyboard=True)

def sub_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="✅ Подписаться"), KeyboardButton(text="❌ Отписаться")],
        [KeyboardButton(text="⏰ Время рассылки"), KeyboardButton(text="📊 Статус")],
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
    await msg.answer(
        "👋 Привет! Я бот для водителей.\n\n"
        "🌦 *Погода для водителей:*\n"
        "• Сначала напишите название вашего города (например, Москва или Omsk).\n"
        "• Затем используйте кнопки «Погода сейчас» и «Прогноз на 5 дней».\n\n"
        "🛠 *Помощь при покупке авто:*\n"
        "• Нажмите кнопку «Помощь при покупке авто» и следуйте шагам.\n\n"
        "🔔 *Подписка:*\n"
        "• Настройте ежедневную рассылку прогноза.\n\n"
        "👇 Выберите действие:",
        parse_mode="Markdown", reply_markup=main_kb()
    )

@dp.message(F.text == "🌤 Погода сейчас")
async def weather_now(msg: Message):
    cid = msg.chat.id
    if cid not in user_cities:
        await msg.answer("📝 Сначала напишите название вашего города (например, Москва или Omsk).", reply_markup=main_kb())
        return
    w = await asyncio.to_thread(get_weather, user_cities[cid])
    await msg.answer(format_weather(w), parse_mode="Markdown", reply_markup=main_kb())

@dp.message(F.text == "📅 Прогноз на 5 дней")
async def forecast_5(msg: Message):
    cid = msg.chat.id
    if cid not in user_cities:
        await msg.answer("📝 Сначала напишите название вашего города (например, Москва или Omsk).", reply_markup=main_kb())
        return
    f = await asyncio.to_thread(get_5day_forecast, user_cities[cid])
    await msg.answer(format_forecast(f), parse_mode="Markdown", reply_markup=main_kb())

@dp.message(F.text == "🛠 Помощь при покупке авто")
async def eval_start(msg: Message):
    user_car_data[msg.chat.id] = {}
    await msg.answer(
        "🔧 *Помощь при покупке автомобиля*\n\n"
        "Шаг 1: Введите **год выпуска** (4 цифры, например 2010):",
        parse_mode="Markdown", reply_markup=back_kb()
    )

@dp.message(F.text == "🔔 Подписка")
async def sub_menu(msg: Message):
    await msg.answer("Настройка ежедневной рассылки прогноза:", reply_markup=sub_kb())

@dp.message(F.text == "⚙️ Настройки")
async def settings(msg: Message):
    await msg.answer(
        "⚙️ *Настройки*\n\n"
        "• Город можно изменить, просто написав его название в чат.\n"
        "• Подписка настраивается в разделе 🔔 Подписка.",
        parse_mode="Markdown", reply_markup=main_kb()
    )

@dp.message(F.text == "✅ Подписаться")
async def subscribe(msg: Message):
    global CHAT_ID
    cid = msg.chat.id
    if cid not in user_cities:
        await msg.answer("📝 Сначала установите город, написав его название в чат.", reply_markup=main_kb())
        return
    CHAT_ID = str(cid)
    await msg.answer("✅ Вы подписаны на ежедневный прогноз в 08:00", reply_markup=main_kb())

@dp.message(F.text == "❌ Отписаться")
async def unsubscribe(msg: Message):
    global CHAT_ID
    cid = msg.chat.id
    if CHAT_ID and int(CHAT_ID) == cid:
        CHAT_ID = None
        await msg.answer("❌ Вы отписались от рассылки", reply_markup=main_kb())
    else:
        await msg.answer("❌ Вы не были подписаны", reply_markup=main_kb())

@dp.message(F.text == "⏰ Время рассылки")
async def set_time_prompt(msg: Message):
    await msg.answer("⏰ Введите время в формате ЧЧ:ММ (например 08:00):", reply_markup=back_kb())

@dp.message(F.text == "📊 Статус")
async def status_sub(msg: Message):
    global CHAT_ID
    cid = msg.chat.id
    if CHAT_ID and int(CHAT_ID) == cid:
        city = user_cities.get(cid, "не задан")
        t = user_subscription_time.get(cid, "08:00")
        await msg.answer(f"✅ Подписка активна\n📍 Город: {city}\n⏰ Время: {t}", reply_markup=main_kb())
    else:
        await msg.answer("❌ Подписка не активна", reply_markup=main_kb())

@dp.message(F.text == "⬅️ Назад")
async def back(msg: Message):
    user_car_data.pop(msg.chat.id, None)
    await msg.answer("Главное меню", reply_markup=main_kb())

# ---------- ОБРАБОТКА ВВОДА ГОРОДА И ОЦЕНКИ АВТО ----------
@dp.message()
async def handle_text(msg: Message):
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
            if text in CARS_DB:
                model = text
                eval_data = calculate_car_value(model, data['year'], data['km'])
                await msg.answer(format_car_evaluation(eval_data), parse_mode="Markdown", reply_markup=main_kb())
                del user_car_data[cid]
            elif text == "⬅️ Назад":
                del user_car_data[cid]
                await msg.answer("Оценка отменена. Главное меню", reply_markup=main_kb())
            else:
                await msg.answer("❌ Модель не найдена. Выберите из списка или нажмите ⬅️ Назад", reply_markup=car_model_kb())
            return

    # Установка времени подписки
    if len(text) == 5 and text[2] == ':' and text[:2].isdigit() and text[3:].isdigit():
        h, m = int(text[:2]), int(text[3:])
        if 0 <= h <= 23 and 0 <= m <= 59:
            user_subscription_time[cid] = text
            await msg.answer(f"✅ Время рассылки установлено: {text}", reply_markup=sub_kb())
        else:
            await msg.answer("❌ Неверный формат времени")
        return

    # Если ни одно из выше – пробуем как город
    city_lat = city_to_latin(text)
    w = await asyncio.to_thread(get_weather, city_lat)
    if w['ok']:
        user_cities[cid] = city_lat
        await msg.answer(f"✅ Город **{text}** установлен!", parse_mode="Markdown", reply_markup=main_kb())
        await msg.answer(format_weather(w), parse_mode="Markdown")
    else:
        await msg.answer(
            f"❌ Не удалось определить город **{text}**.\n\n"
            "Пожалуйста, напишите название города на русском или латинице (например, Москва, Omsk).",
            parse_mode="Markdown", reply_markup=main_kb()
        )

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
    print("✅ Бот запущен. Вводите город текстом, погода и прогноз с советами работают, помощь при покупке авто — подробная.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

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

# Загружаем .env
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')
CHAT_ID = os.getenv('CHAT_ID')

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

user_cities = {}
user_subscription_time = {}
logging.basicConfig(level=logging.INFO)

# Прямое соответствие английских дней русским (гарантированный перевод)
DAYS_RU = {
    'Monday': 'Понедельник',
    'Tuesday': 'Вторник',
    'Wednesday': 'Среда',
    'Thursday': 'Четверг',
    'Friday': 'Пятница',
    'Saturday': 'Суббота',
    'Sunday': 'Воскресенье'
}

# Также сопоставим для случаев, если strftime вдруг вернёт русские названия (но обычно нет)
# Эта функция гарантирует русское название в любом случае
def get_russian_day(date: datetime) -> str:
    """Возвращает название дня недели на русском языке"""
    eng_day = date.strftime('%A')
    return DAYS_RU.get(eng_day, eng_day)  # если вдруг не найдёт, вернёт как есть

# ==================== КЛАВИАТУРЫ ====================

def get_main_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🌤 Погода сейчас"), KeyboardButton(text="📅 Прогноз на 5 дней")],
            [KeyboardButton(text="🚗 Советы водителю"), KeyboardButton(text="⚙️ Установить город")],
            [KeyboardButton(text="🔔 Подписка"), KeyboardButton(text="❓ Помощь")],
            [KeyboardButton(text="ℹ️ О боте")]
        ],
        resize_keyboard=True,
        input_field_placeholder="Нажмите кнопку или напишите город..."
    )
    return keyboard

def get_cities_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🇷🇺 Москва"), KeyboardButton(text="🇷🇺 Санкт-Петербург")],
            [KeyboardButton(text="🇷🇺 Новосибирск"), KeyboardButton(text="🇷🇺 Екатеринбург")],
            [KeyboardButton(text="🇷🇺 Казань"), KeyboardButton(text="🇷🇺 Омск")],
            [KeyboardButton(text="🇷🇺 Красноярск"), KeyboardButton(text="🇷🇺 Владивосток")],
            [KeyboardButton(text="⬅️ Назад в меню")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_weather_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔄 Обновить погоду"), KeyboardButton(text="📅 Прогноз на 5 дней")],
            [KeyboardButton(text="🌤 Другой город"), KeyboardButton(text="⬅️ Главное меню")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_subscription_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Подписаться"), KeyboardButton(text="❌ Отписаться")],
            [KeyboardButton(text="⏰ Выбрать время"), KeyboardButton(text="📊 Статус подписки")],
            [KeyboardButton(text="⬅️ Главное меню")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_back_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Назад в меню")]],
        resize_keyboard=True
    )
    return keyboard

# ==================== ФУНКЦИИ ПОГОДЫ ====================

def get_weather(city: str) -> dict:
    """Текущая погода"""
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

            directions = ['северный', 'северо-восточный', 'восточный', 'юго-восточный',
                          'южный', 'юго-западный', 'западный', 'северо-западный']
            wind_dir = directions[int((wind_direction + 22.5) / 45) % 8]

            return {
                'success': True,
                'city': city,
                'temp': temp,
                'feels_like': feels_like,
                'humidity': humidity,
                'pressure': pressure,
                'wind_speed': wind_speed,
                'wind_dir': wind_dir,
                'description': weather_desc,
                'clouds': clouds,
                'visibility': visibility,
                'time': datetime.now().strftime('%d.%m.%Y %H:%M')
            }
        else:
            return {'success': False, 'error': 'Город не найден'}
    except Exception as e:
        return {'success': False, 'error': f'Ошибка: {e}'}

def get_5day_forecast(city: str) -> dict:
    """Прогноз на 5 дней (каждые 3 часа)"""
    try:
        url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
        response = requests.get(url, timeout=10)
        data = response.json()

        if response.status_code == 200:
            forecasts = []
            daily_forecasts = {}
            
            for item in data['list']:
                dt = datetime.fromtimestamp(item['dt'])
                date_key = dt.strftime('%Y-%m-%d')
                
                if date_key not in daily_forecasts:
                    daily_forecasts[date_key] = {
                        'temps': [],
                        'descriptions': [],
                        'wind_speeds': [],
                        'humidity': [],
                        'rain': False,
                        'snow': False,
                        'date': dt
                    }
                
                daily_forecasts[date_key]['temps'].append(item['main']['temp'])
                daily_forecasts[date_key]['descriptions'].append(item['weather'][0]['description'])
                daily_forecasts[date_key]['wind_speeds'].append(item['wind']['speed'])
                daily_forecasts[date_key]['humidity'].append(item['main']['humidity'])
                
                if 'rain' in item and item['rain'].get('3h', 0) > 0:
                    daily_forecasts[date_key]['rain'] = True
                if 'snow' in item and item['snow'].get('3h', 0) > 0:
                    daily_forecasts[date_key]['snow'] = True
            
            # Формируем прогноз на 5 дней
            for date_key, day_data in list(daily_forecasts.items())[:5]:
                forecasts.append({
                    'date': day_data['date'],
                    'temp_max': max(day_data['temps']),
                    'temp_min': min(day_data['temps']),
                    'temp_day': sum(day_data['temps']) / len(day_data['temps']),
                    'description': max(set(day_data['descriptions']), key=day_data['descriptions'].count),
                    'wind_speed': max(day_data['wind_speeds']),
                    'humidity': sum(day_data['humidity']) / len(day_data['humidity']),
                    'rain': day_data['rain'],
                    'snow': day_data['snow']
                })
            
            return {
                'success': True,
                'city': city,
                'forecasts': forecasts
            }
        else:
            return {'success': False, 'error': 'Город не найден'}
    except Exception as e:
        return {'success': False, 'error': f'Ошибка: {e}'}

def get_driver_tips_for_weather(temp: float, wind_speed: float, humidity: float, 
                                 description: str, rain: bool = False, snow: bool = False) -> str:
    """Советы водителю на основе погодных условий"""
    tips = []
    
    # Температурные советы
    if temp < -30:
        tips.append("❄️❄️ ЭКСТРЕМАЛЬНЫЙ МОРОЗ: не выезжай без крайней необходимости, аккумулятор может сесть мгновенно")
    elif temp < -20:
        tips.append("❄️ Сильный мороз: прогревай двигатель 10-15 минут, проверь аккумулятор и антифриз")
    elif temp < -10:
        tips.append("❄️ Холодно: возможен трудный запуск, держи дистанцию ×2")
    elif temp < 0:
        tips.append("⚠️ Гололед: избегай резких ускорений и торможений, дистанция ×3")
    elif temp > 35:
        tips.append("🔥 Экстремальная жара: проверь уровень охлаждающей жидкости, не оставляй детей в машине")
    elif temp > 30:
        tips.append("🔥 Сильная жара: используй кондиционер, следи за температурой двигателя")
    elif temp > 25:
        tips.append("☀️ Жарко: проветривай салон, не оставляй гаджеты на солнце")
    
    # Ветер
    if wind_speed > 20:
        tips.append("💨 УРАГАННЫЙ ВЕТЕР: будь предельно осторожен на мостах и эстакадах, снизь скорость")
    elif wind_speed > 15:
        tips.append("💨 Очень сильный ветер: крепче держи руль, особенно на открытых участках")
    elif wind_speed > 10:
        tips.append("💨 Сильный ветер: будь внимателен при обгоне фур")
    
    # Осадки и видимость
    if rain:
        tips.append("🌧️ ДОЖДЬ: включи фары, проверь дворники, дистанция ×2, избегай луж")
    if snow:
        tips.append("🌨️ СНЕГОПАД: проверь резину, чисти снег с крыши, включай противотуманки")
    
    if 'гроза' in description:
        tips.append("⛈️ ГРОЗА: по возможности пережди, не паркуйся под деревьями и ЛЭП")
    if 'туман' in description:
        tips.append("🌫️ ТУМАН: используй противотуманные фары, снизь скорость, ориентируйся по разметке")
    
    # Влажность
    if humidity > 85:
        tips.append("💧 Высокая влажность: стекла могут запотевать, используй кондиционер или обогрев")
    
    if not tips:
        tips.append("✅ Погода благоприятная, хорошей дороги!")
    
    return "\n".join(tips[:4])

def format_forecast_message(forecast_data: dict) -> str:
    """Форматирование прогноза на 5 дней с русскими названиями дней"""
    if not forecast_data['success']:
        return f"❌ {forecast_data['error']}"
    
    message = f"📅 *ПРОГНОЗ НА 5 ДНЕЙ - {forecast_data['city'].upper()}*\n"
    message += "━" * 30 + "\n\n"
    
    # Получаем текущую дату для определения "сегодня", "завтра"
    today = datetime.now().date()
    
    for i, day in enumerate(forecast_data['forecasts']):
        day_date = day['date'].date()
        
        # Определяем заголовок
        if day_date == today:
            day_header = "Сегодня"
        elif day_date == today + timedelta(days=1):
            # Для завтрашнего дня добавим день недели в скобках
            weekday_ru = get_russian_day(day['date'])
            day_header = f"Завтра ({weekday_ru})"
        else:
            # Для остальных дней просто день недели
            day_header = get_russian_day(day['date'])
        
        message += f"📌 *{day_header}* {day_date.strftime('%d.%m')}\n"
        message += f"🌡️ {day['temp_min']:.0f}°C ~ {day['temp_max']:.0f}°C (средняя {day['temp_day']:.0f}°C)\n"
        message += f"☁️ {day['description'].capitalize()}\n"
        message += f"💨 Ветер до {day['wind_speed']:.0f} м/с\n"
        
        # Иконки осадков
        if day['rain']:
            message += "🌧️ Ожидаются дожди\n"
        if day['snow']:
            message += "🌨️ Ожидается снег\n"
        
        # Советы водителю
        tips = get_driver_tips_for_weather(
            day['temp_day'], day['wind_speed'], day['humidity'],
            day['description'], day['rain'], day['snow']
        )
        message += f"\n🚗 *Советы:* {tips}\n\n"
        message += "─" * 20 + "\n\n"
    
    return message

def format_weather_message(weather: dict) -> str:
    """Форматирование текущей погоды"""
    if not weather['success']:
        return f"❌ {weather['error']}"
    
    message = (
        f"🌍 *ПОГОДА В {weather['city'].upper()}*\n"
        f"📅 {weather['time']}\n"
        f"☁️ {weather['description'].capitalize()}\n"
        f"🌡️ *{weather['temp']:.1f}°C* (ощущается {weather['feels_like']:.1f}°C)\n"
        f"💧 Влажность: {weather['humidity']}%\n"
        f"📊 Давление: {weather['pressure']:.1f} мм рт.ст.\n"
        f"💨 Ветер: {weather['wind_speed']:.1f} м/с, {weather['wind_dir']}\n"
        f"👁️ Видимость: {weather['visibility']:.1f} км\n"
        f"☁️ Облачность: {weather['clouds']}%\n\n"
        f"🚗 *СОВЕТЫ ВОДИТЕЛЮ:*\n"
    )
    
    tips = get_driver_tips_for_weather(
        weather['temp'], weather['wind_speed'], weather['humidity'],
        weather['description'], 'дождь' in weather['description'], 
        'снег' in weather['description']
    )
    message += tips
    
    return message

# ==================== ОБРАБОТЧИКИ ====================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    welcome_text = (
        "👋 *Добро пожаловать в WeatherBot для водителей!*\n\n"
        "🚗 Я помогаю водителям:\n"
        "• Узнавать текущую погоду\n"
        "• Получать прогноз на 5 дней\n"
        "• Даю полезные советы по вождению\n\n"
        "👇 *Нажми кнопку или напиши город:*"
    )
    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

@dp.message(F.text == "🌤 Погода сейчас")
async def weather_now(message: Message):
    chat_id = message.chat.id
    if chat_id in user_cities:
        city = user_cities[chat_id]
        weather = get_weather(city)
        await message.answer(format_weather_message(weather), parse_mode="Markdown", reply_markup=get_weather_keyboard())
    else:
        await message.answer("🌆 *Выберите город* из списка или напишите его название:", parse_mode="Markdown", reply_markup=get_cities_keyboard())

@dp.message(F.text == "📅 Прогноз на 5 дней")
async def forecast_5days(message: Message):
    chat_id = message.chat.id
    if chat_id in user_cities:
        city = user_cities[chat_id]
        await message.answer("🔍 *Получаю прогноз на 5 дней...*", parse_mode="Markdown")
        forecast = get_5day_forecast(city)
        await message.answer(format_forecast_message(forecast), parse_mode="Markdown", reply_markup=get_weather_keyboard())
    else:
        await message.answer("🌆 *Сначала установите город* в настройках!", parse_mode="Markdown", reply_markup=get_cities_keyboard())

@dp.message(F.text == "🚗 Советы водителю")
async def driver_tips(message: Message):
    tips = (
        "🚗 *ПОЛЕЗНЫЕ СОВЕТЫ ВОДИТЕЛЮ*\n\n"
        "❄️ *ЗИМА:*\n"
        "• Возим щетку и скребок\n"
        "• Проверяем аккумулятор\n"
        "• Дистанция ×2-3\n"
        "• Зимняя резина обязательна\n\n"
        
        "🌧️ *ДОЖДЬ:*\n"
        "• Включаем фары днем\n"
        "• Не влетаем в глубокие лужи\n"
        "• Проверяем дворники\n"
        "• Дистанция ×2\n\n"
        
        "☀️ *ЖАРА:*\n"
        "• Следим за антифризом\n"
        "• Не оставляем детей/животных\n"
        "• Проветриваем салон\n"
        "• Давление в шинах\n\n"
        
        "🌫️ *ТУМАН:*\n"
        "• Противотуманные фары\n"
        "• Снижаем скорость\n"
        "• Ориентир по разметке\n"
        "• Без резких маневров\n\n"
        
        "⚠️ *ГОЛОЛЕД:*\n"
        "• Плавные движения\n"
        "• Дистанция ×3\n"
        "• Торможение двигателем"
    )
    await message.answer(tips, parse_mode="Markdown", reply_markup=get_back_keyboard())

@dp.message(F.text == "⚙️ Установить город")
async def set_city_prompt(message: Message):
    await message.answer("🌆 *Напишите название вашего города* (например: Москва, Омск, Казань):", parse_mode="Markdown", reply_markup=get_back_keyboard())

@dp.message(F.text == "🔔 Подписка")
async def subscription_menu(message: Message):
    chat_id = message.chat.id
    city = user_cities.get(chat_id, "не установлен")
    sub_time = user_subscription_time.get(chat_id, "08:00")
    global CHAT_ID
    is_subscribed = (CHAT_ID and int(CHAT_ID) == chat_id)
    status = "✅ *Активна*" if is_subscribed else "❌ *Не активна*"
    text = f"🔔 *УПРАВЛЕНИЕ ПОДПИСКОЙ*\n\n🏙️ Город: *{city}*\n⏰ Текущее время: *{sub_time}*\n📊 Статус: {status}\n\nВы можете выбрать любое время от 00:00 до 23:59"
    await message.answer(text, parse_mode="Markdown", reply_markup=get_subscription_keyboard())

@dp.message(F.text == "❓ Помощь")
async def help_menu(message: Message):
    help_text = (
        "❓ *ПОМОЩЬ И КОМАНДЫ*\n\n"
        "🌤 Погода сейчас - узнать текущую погоду\n"
        "📅 Прогноз на 5 дней - подробный прогноз\n"
        "🚗 Советы водителю - общие рекомендации\n"
        "⚙️ Установить город - город по умолчанию\n"
        "🔔 Подписка - настроить ежедневную рассылку\n\n"
        "📊 Статус подписки - проверить настройки"
    )
    await message.answer(help_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

@dp.message(F.text == "ℹ️ О боте")
async def about_bot(message: Message):
    about = (
        "ℹ️ *О БОТЕ*\n\n"
        "📦 Версия: 3.1\n"
        "👨‍💻 Для водителей, таксистов, дальнобойщиков\n"
        "🌐 Источник: OpenWeatherMap\n\n"
        "✨ *Функции:*\n"
        "• Текущая погода\n"
        "• Прогноз на 5 дней\n"
        "• Умные советы по погоде\n"
        "• Ежедневная рассылка\n"
        "• Удобные кнопки\n\n"
        "💡 *Совет:* Установите свой город для удобства!"
    )
    await message.answer(about, parse_mode="Markdown", reply_markup=get_back_keyboard())

@dp.message(F.text == "⬅️ Назад в меню")
@dp.message(F.text == "⬅️ Главное меню")
async def back_to_main_menu(message: Message):
    await message.answer("🔹 *Главное меню*", parse_mode="Markdown", reply_markup=get_main_keyboard())

@dp.message(F.text == "🔄 Обновить погоду")
async def refresh_weather(message: Message):
    chat_id = message.chat.id
    if chat_id in user_cities:
        city = user_cities[chat_id]
        weather = get_weather(city)
        await message.answer(format_weather_message(weather), parse_mode="Markdown", reply_markup=get_weather_keyboard())
    else:
        await message.answer("⚠️ Сначала установите город!", reply_markup=get_cities_keyboard())

@dp.message(F.text == "🌤 Другой город")
async def another_city(message: Message):
    await message.answer("🌆 *Выберите город* из списка или напишите его название:", parse_mode="Markdown", reply_markup=get_cities_keyboard())

@dp.message(F.text == "✅ Подписаться")
async def handle_subscribe(message: Message):
    global CHAT_ID
    chat_id = message.chat.id
    if chat_id not in user_cities:
        await message.answer("⚠️ Сначала установите город!", reply_markup=get_main_keyboard())
        return
    CHAT_ID = str(chat_id)
    city = user_cities[chat_id]
    sub_time = user_subscription_time.get(chat_id, "08:00")
    await message.answer(f"✅ *Вы подписаны!*\n\n🏙️ Город: {city}\n⏰ Время: {sub_time}\n\nТеперь вы будете получать прогноз каждый день в {sub_time}.", parse_mode="Markdown", reply_markup=get_main_keyboard())

@dp.message(F.text == "❌ Отписаться")
async def handle_unsubscribe(message: Message):
    global CHAT_ID
    if CHAT_ID and int(CHAT_ID) == message.chat.id:
        CHAT_ID = None
        await message.answer("❌ *Вы отписались от рассылки*", parse_mode="Markdown")
    else:
        await message.answer("❌ Вы не были подписаны")

@dp.message(F.text == "⏰ Выбрать время")
async def select_time(message: Message):
    await message.answer("⏰ *Введите время* в формате ЧЧ:ММ (например, 08:00, 14:30):", parse_mode="Markdown", reply_markup=get_back_keyboard())

@dp.message(F.text == "📊 Статус подписки")
async def subscription_status(message: Message):
    global CHAT_ID
    if CHAT_ID and int(CHAT_ID) == message.chat.id:
        city = user_cities.get(message.chat.id, "не установлен")
        sub_time = user_subscription_time.get(message.chat.id, "08:00")
        await message.answer(f"✅ *Подписка активна*\n🏙️ Город: {city}\n⏰ Время: {sub_time}", parse_mode="Markdown")
    else:
        await message.answer("❌ *Подписка не активна*", parse_mode="Markdown")

@dp.message(F.text.startswith(("🇷🇺", "Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань", "Омск", "Красноярск", "Владивосток")))
async def handle_city_button(message: Message):
    city = message.text.replace("🇷🇺 ", "").strip()
    chat_id = message.chat.id
    weather = get_weather(city)
    if weather['success']:
        user_cities[chat_id] = city
        await message.answer(format_weather_message(weather), parse_mode="Markdown", reply_markup=get_weather_keyboard())
    else:
        await message.answer(f"❌ Не удалось получить погоду для {city}", reply_markup=get_cities_keyboard())

@dp.message()
async def handle_text(message: Message):
    text = message.text.strip()
    chat_id = message.chat.id
    
    # Проверка на ввод времени
    if len(text) == 5 and text[2] == ':':
        try:
            hours = int(text[:2])
            minutes = int(text[3:])
            if 0 <= hours <= 23 and 0 <= minutes <= 59:
                user_subscription_time[chat_id] = text
                await message.answer(f"✅ Время установлено: *{text}*", parse_mode="Markdown", reply_markup=get_subscription_keyboard())
                return
        except:
            pass
    
    # Поиск города
    await message.answer("🔍 *Ищу город...*", parse_mode="Markdown")
    weather = get_weather(text)
    if weather['success']:
        user_cities[chat_id] = text
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🌤 Погода сейчас"), KeyboardButton(text="📅 Прогноз на 5 дней")],
                [KeyboardButton(text="⬅️ Главное меню")]
            ],
            resize_keyboard=True
        )
        await message.answer(
            f"✅ Город *{text}* установлен!\n\nЧто хотите узнать?",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    else:
        await message.answer(f"❌ Город '{text}' не найден.\nПроверьте название или выберите из списка:", reply_markup=get_cities_keyboard())

# ==================== ПЛАНИРОВЩИК ====================

def send_daily_weather():
    """Отправка ежедневного прогноза"""
    if not CHAT_ID:
        return
    chat_id = int(CHAT_ID)
    city = user_cities.get(chat_id, "Москва")
    
    forecast = get_5day_forecast(city)
    asyncio.create_task(bot.send_message(
        chat_id=chat_id, 
        text=format_forecast_message(forecast), 
        parse_mode="Markdown"
    ))

def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(30)

# ==================== ЗАПУСК ====================

async def main():
    schedule.every().day.at("08:00").do(send_daily_weather)
    threading.Thread(target=run_schedule, daemon=True).start()
    
    print("\n" + "="*60)
    print("✅ БОТ УСПЕШНО ЗАПУЩЕН!")
    print("="*60)
    print("📅 Доступные функции:")
    print("  • Текущая погода")
    print("  • Прогноз на 5 дней (русские дни недели)")
    print("  • Советы водителю")
    print("  • Ежедневная рассылка")
    print("="*60 + "\n")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

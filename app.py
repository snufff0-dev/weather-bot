import os
import asyncio
import threading
from flask import Flask
from bot import bot, dp, main as bot_main

app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Weather Bot is running!"

@app.route('/health')
def health():
    return "OK", 200

def run_bot():
    """Запуск бота без обработки сигналов"""
    # Создаём новый цикл событий
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Отключаем все обработчики сигналов глобально
    import signal
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    
    # Патчим метод add_signal_handler у цикла
    original_add_signal = loop.add_signal_handler
    loop.add_signal_handler = lambda *args, **kwargs: None
    
    # Запускаем бота
    try:
        loop.run_until_complete(bot_main())
    except Exception as e:
        print(f"Ошибка бота: {e}")
    finally:
        loop.close()

# Запускаем бота
threading.Thread(target=run_bot, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 3000))
    app.run(host='0.0.0.0', port=port)

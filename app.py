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
    """Запуск бота в отдельном событийном цикле"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Отключаем обработку сигналов (они не нужны в потоке)
    loop.add_signal_handler = lambda *args, **kwargs: None
    
    loop.run_until_complete(bot_main())

# Запускаем бота в фоновом потоке
threading.Thread(target=run_bot, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 3000))
    app.run(host='0.0.0.0', port=port)

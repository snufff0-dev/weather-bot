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
    asyncio.run(bot_main())

threading.Thread(target=run_bot, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
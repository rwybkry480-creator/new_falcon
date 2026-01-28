# -----------------------------------------------------------------------------
# bot_final_working.py - v10.0 (Polling Design - The Working Way)
# -----------------------------------------------------------------------------

import os
import logging
import asyncio
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import requests

# --- Logging Setup ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Flask Web Server (for Health Checks only) ---
app = Flask(__name__)
@app.route('/')
def health_check():
    return "Falcon Scanner Bot (v10.0 - Polling) is Running!", 200
def run_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- Binance API & Analysis Functions (from our previous code) ---
SUPPORT_LEVELS = [float(x) for x in os.getenv("SUPPORT_LEVELS", "0.1530,0.1450,0.1380").split(",")]
RESISTANCE_LEVELS = [float(x) for x in os.getenv("RESISTANCE_LEVELS", "0.1594,0.1639,0.1700").split(",")]
KLINES_LIMIT = 50

def get_all_usdt_symbols():
    try:
        url = "https://api.binance.com/api/v3/exchangeInfo"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        return [s['symbol'] for s in data['symbols'] if s['quoteAsset'] == 'USDT' and s['status'] == 'TRADING']
    except requests.RequestException as e:
        logger.error(f"Error fetching symbols: {e}")
        return []

def get_binance_klines(symbol, interval="1h", limit=KLINES_LIMIT):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.warning(f"Could not fetch klines for {symbol}: {e}")
        return []

def analyze_symbol(symbol, data):
    if len(data) < 25: return None
    closes = [float(candle[4]) for candle in data]
    last_close = closes[-1]
    ema7 = sum(closes[-7:]) / 7
    ema25 = sum(closes[-25:]) / 25
    near_support = any(abs(last_close - s) / s < 0.01 for s in SUPPORT_LEVELS)
    near_resistance = any(abs(last_close - r) / r < 0.01 for r in RESISTANCE_LEVELS)
    is_uptrend = last_close > ema7 and last_close > ema25

    if is_uptrend and near_resistance:
        return (f"📈 إشارة شراء قوية (Long)\n"
                f"العملة: {symbol}\n"
                f"السعر: {last_close:.5f}\n"
                f"فوق EMA7 ({ema7:.5f}) و EMA25 ({ema25:.5f})\n"
                f"🚀 قريب من اختراق مقاومة مهمة")
    if is_uptrend and near_support:
        return (f"📈 إشارة شراء محتملة (ارتداد)\n"
                f"العملة: {symbol}\n"
                f"السعر: {last_close:.5f}\n"
                f"فوق EMA7 ({ema7:.5f}) و EMA25 ({ema25:.5f})\n"
                f"🛡️ ارتداد من دعم قوي")
    return None

def run_full_scan():
    logger.info("--- Starting a new market scan ---")
    all_symbols = get_all_usdt_symbols()
    signals = []
    if not all_symbols:
        logger.warning("Could not retrieve symbols to scan.")
        return []
    for symbol in all_symbols:
        klines = get_binance_klines(symbol)
        if klines:
            signal = analyze_symbol(symbol, klines)
            if signal:
                signals.append(signal)
    logger.info(f"--- Scan complete. Found {len(signals)} signals. ---")
    return signals

# --- Telegram Bot Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = (f"👋 أهلاً بك يا {user.mention_html()}!\n\n"
               f"أنا <b>بوت فالكون الماسح (v10.0 - Polling)</b>.\n"
               f"استخدم الأمر /scan لبدء فحص السوق.\n\n"
               f"<i>صنع بواسطة المطور عبدالرحمن محمد</i>")
    await update.message.reply_html(message, disable_web_page_preview=True)

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ جاري فحص السوق، قد يستغرق هذا بضع دقائق...")
    # We don't need asyncio.to_thread here because polling runs in its own async loop
    signals = run_full_scan()
    if not signals:
        await update.message.reply_text("✅ تم فحص السوق. لا توجد فرص واضحة حاليًا.")
    else:
        await update.message.reply_text(f"📊 تم العثور على {len(signals)} إشارة:")
        for signal in signals:
            await update.message.reply_text(signal)

# --- Main Bot Execution ---
def run_bot():
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("scan", scan))
    logger.info("--- [Falcon Scanner v10.0] Bot is ready and running (Polling Mode). ---")
    application.run_polling()

# --- Entry Point ---
if __name__ == "__main__":
    logger.info("--- [Falcon Scanner v10.0] Starting Main Application ---")
    server_thread = Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    logger.info("--- [Falcon Scanner v10.0] Web Server has been started. ---")
    run_bot()


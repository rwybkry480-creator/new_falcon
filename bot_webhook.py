# -----------------------------------------------------------------------------
# bot_webhook.py - v9.2 (with Incoming Request Logging)
# -----------------------------------------------------------------------------

import os
import logging
import asyncio
import requests
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- Logging Setup ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Flask Setup ---
app = Flask(__name__)

# --- Config ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

# --- Strategy Config from Environment ---
SUPPORT_LEVELS = [float(x) for x in os.getenv("SUPPORT_LEVELS", "0.1530,0.1450,0.1380").split(",")]
RESISTANCE_LEVELS = [float(x) for x in os.getenv("RESISTANCE_LEVELS", "0.1594,0.1639,0.1700").split(",")]
KLINES_LIMIT = 50 # Number of candles to fetch

# --- Binance API Functions (using requests) ---
def get_all_usdt_symbols():
    """Fetches all symbols that are traded against USDT."""
    symbols = []
    try:
        url = "https://api.binance.com/api/v3/exchangeInfo"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        symbols = [s['symbol'] for s in data['symbols'] if s['quoteAsset'] == 'USDT' and s['status'] == 'TRADING']
    except requests.RequestException as e:
        logger.error(f"Error fetching symbols from Binance: {e}")
    return symbols

def get_binance_klines(symbol, interval="1h", limit=KLINES_LIMIT):
    """Fetches k-line (candle) data for a specific symbol."""
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.warning(f"Could not fetch klines for {symbol}: {e}")
        return []

def analyze_symbol(symbol, data):
    """Analyzes the k-line data to find a trading signal with custom formatting."""
    if len(data) < 25:
        return None

    closes = [float(candle[4]) for candle in data]
    last_close = closes[-1]

    # Using simple moving average as per the last provided code
    ema7 = sum(closes[-7:]) / 7
    ema25 = sum(closes[-25:]) / 25

    # Check if price is near support or resistance (within 1%)
    near_support = any(abs(last_close - s) / s < 0.01 for s in SUPPORT_LEVELS)
    near_resistance = any(abs(last_close - r) / r < 0.01 for r in RESISTANCE_LEVELS)

    is_uptrend = last_close > ema7 and last_close > ema25

    if is_uptrend and near_resistance:
        signal = (
            f"📈 إشارة شراء قوية (Long)\n"
            f"العملة: {symbol}\n"
            f"السعر: {last_close:.5f}\n"
            f"فوق EMA7 ({ema7:.5f}) و EMA25 ({ema25:.5f})\n"
            f"🚀 قريب من اختراق مقاومة مهمة"
        )
        return signal

    if is_uptrend and near_support:
        signal = (
            f"📈 إشارة شراء محتملة (ارتداد)\n"
            f"العملة: {symbol}\n"
            f"السعر: {last_close:.5f}\n"
            f"فوق EMA7 ({ema7:.5f}) و EMA25 ({ema25:.5f})\n"
            f"🛡️ ارتداد من دعم قوي"
        )
        return signal

    return None

def run_full_scan():
    """The main scanning logic that iterates through all symbols."""
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

# --- Telegram Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = (f"👋 أهلاً بك يا {user.mention_html()}!\n\n"
               f"أنا <b>بوت فالكون الماسح (v9.2)</b>.\n"
               f"استخدم الأمر /scan لبدء فحص السوق بحثاً عن فرص شراء.\n\n"
               f"<i>صنع بواسطة المطور عبدالرحمن محمد</i>")
    await update.message.reply_html(message, disable_web_page_preview=True)

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ جاري فحص السوق، قد يستغرق هذا بضع دقائق...")
    
    signals = await asyncio.to_thread(run_full_scan)
    
    if not signals:
        message = "✅ تم فحص السوق. لا توجد فرص واضحة حاليًا."
        await update.message.reply_text(message)
    else:
        await update.message.reply_text(f"📊 تم العثور على {len(signals)} إشارة:")
        for signal in signals:
            await update.message.reply_text(signal)
        
# --- Webhook Setup ---
application = Application.builder().token(TELEGRAM_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("scan", scan))

@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def webhook():
    # Log the incoming request for debugging purposes
    logger.info(f"Webhook received a request: {request.json}")
    
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        application.update_queue.put_nowait(update)
    except Exception as e:
        logger.error(f"Error processing update in webhook: {e}")
    return "ok", 200

@app.route("/")
def index():
    return "Falcon Hybrid Bot (v9.2) is Running!", 200

# --- Entry Point ---
if __name__ == "__main__":
    logger.info("--- Starting Falcon Hybrid Bot Application ---")
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


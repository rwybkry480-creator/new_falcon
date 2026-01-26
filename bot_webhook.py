# -----------------------------------------------------------------------------
# bot_webhook.py - v7.2 (Final, with asyncio fix and /start command)
# -----------------------------------------------------------------------------

import os
import logging
import asyncio
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from binance.client import Client
import pandas as pd

# --- Logging Setup ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Flask Setup ---
app = Flask(__name__)

# --- Config ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.environ.get("BINANCE_SECRET_KEY")

if not TELEGRAM_TOKEN:
    logger.error("FATAL: TELEGRAM_TOKEN environment variable not set.")
else:
    logger.info("TELEGRAM_TOKEN loaded successfully.")

client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)

# --- Analysis Functions ---
def calculate_indicators(df):
    df["EMA7"] = df["close"].ewm(span=7, adjust=False).mean()
    df["EMA25"] = df["close"].ewm(span=25, adjust=False).mean()
    df["EMA99"] = df["close"].ewm(span=99, adjust=False).mean()

    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/6, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/6, adjust=False).mean()
    rs = gain / loss.replace(0, 1e-10)
    df["RSI6"] = 100 - (100 / (1 + rs))

    rsi_min = df["RSI6"].rolling(window=14).min()
    rsi_max = df["RSI6"].rolling(window=14).max()
    df["StochRSI"] = (df["RSI6"] - rsi_min) / (rsi_max - rsi_min)

    df["VolMA20"] = df["volume"].rolling(window=20).mean()
    return df.dropna()

def analyze_symbol(client, symbol):
    try:
        klines_1h = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_1HOUR, limit=120)
        if len(klines_1h) < 100:
            return "HOLD", None

        df_1h = pd.DataFrame(klines_1h, columns=["timestamp","open","high","low","close","volume","close_time","quote_av","trades","tb_base_av","tb_quote_av","ignore"])
        df_1h[["close","open","volume"]] = df_1h[["close","open","volume"]].apply(pd.to_numeric)
        df_1h = calculate_indicators(df_1h)

        last = df_1h.iloc[-1]
        current_price = last["close"]

        ema_trend_up = last["close"] > last["EMA7"] > last["EMA25"] > last["EMA99"]
        rsi_ok = 60 <= last["RSI6"] <= 80
        stoch_mid = 0.4 <= last["StochRSI"] <= 0.6
        volume_ok = last["volume"] > last["VolMA20"]
        bullish_candle = last["close"] > last["open"]

        if ema_trend_up and rsi_ok and stoch_mid and volume_ok and bullish_candle:
            return "BUY", current_price

        rsi_high = last["RSI6"] > 80
        stoch_high = last["StochRSI"] > 0.8
        bearish_candle = last["close"] < last["open"]

        if (rsi_high or stoch_high) and bearish_candle:
            return "SELL", current_price

    except Exception as e:
        if "Invalid symbol" not in str(e):
             logger.warning(f"[Binance] Could not analyze {symbol}: {e}")

    return "HOLD", None

def scan_all_symbols_under_100():
    results = []
    try:
        tickers = client.get_ticker()
        usdt_tickers = [t for t in tickers if t['symbol'].endswith("USDT") and 0 < float(t['lastPrice']) < 100]
        
        for t in usdt_tickers:
            decision, current_price = analyze_symbol(client, t['symbol'])
            if decision != "HOLD":
                results.append((t['symbol'], decision, current_price))
    except Exception as e:
        logger.error(f"Error fetching tickers from Binance: {e}")
    return results

# --- Telegram Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = (f"👋 أهلاً بك يا {user.mention_html()}!\n\n"
               f"أنا <b>بوت فالكون الماسح (Falcon Scanner)</b>.\n"
               f"استخدم الأمر /scan لبدء فحص السوق بحثاً عن فرص حسب الاستراتيجية المدمجة.\n\n"
               f"<i>صنع بواسطة المطور عبدالرحمن محمد</i>")
    await update.message.reply_html(message, disable_web_page_preview=True)

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ جاري فحص السوق، قد يستغرق هذا بضع دقائق...")
    
    # --- THE CRITICAL FIX ---
    # Run the long, blocking function in a separate thread
    results = await asyncio.to_thread(scan_all_symbols_under_100)
    
    if not results:
        message = "✅ تم فحص السوق. لا توجد فرص واضحة حاليًا."
    else:
        message = "📊 نتائج الفحص للعملات تحت 100 USDT:\n\n"
        for sym, decision, price in results:
            emoji = "📈" if decision == "BUY" else "📉"
            message += f"{emoji} {sym}: {decision} at {price:.4f}\n"
    await update.message.reply_text(message)

# --- Webhook Setup ---
application = Application.builder().token(TELEGRAM_TOKEN).build()
# Add both command handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("scan", scan))

@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def webhook():
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        application.update_queue.put_nowait(update)
    except Exception as e:
        logger.error(f"Error processing update in webhook: {e}")
    return "ok", 200

@app.route("/")
def index():
    return "Falcon Bot Webhook Service is Running!", 200

# --- Entry Point ---
if __name__ == "__main__":
    logger.info("--- Starting Falcon Scanner Webhook Application ---")
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


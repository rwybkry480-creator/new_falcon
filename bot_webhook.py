# -----------------------------------------------------------------------------
# bot_webhook.py - v7.1 (Diagnostic Version)
# -----------------------------------------------------------------------------

import os
import logging
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

# Check if token is loaded
if not TELEGRAM_TOKEN:
    logger.error("FATAL: TELEGRAM_TOKEN environment variable not set.")
    # In a real app, you might want to exit or handle this gracefully
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
        logger.error(f"[Binance] Error analyzing {symbol}: {e}")

    return "HOLD", None

def scan_all_symbols_under_100():
    results = []
    try:
        tickers = client.get_ticker()
        for t in tickers:
            symbol = t["symbol"]
            if symbol.endswith("USDT"):
                price = float(t["lastPrice"])
                if 0 < price < 100:
                    decision, current_price = analyze_symbol(client, symbol)
                    if decision != "HOLD":
                        results.append((symbol, decision, current_price))
    except Exception as e:
        logger.error(f"Error fetching tickers from Binance: {e}")
    return results

# --- Telegram Command Handlers ---
async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Scanning the market, this might take a few minutes...")
    results = scan_all_symbols_under_100()
    if not results:
        message = "✅ Market scan complete. No clear opportunities found at the moment."
    else:
        message = "📊 Scan results for coins under 100 USDT:\n\n"
        for sym, decision, price in results:
            emoji = "📈" if decision == "BUY" else "📉"
            message += f"{emoji} {sym}: {decision} at {price:.4f}\n"
    await update.message.reply_text(message)

# --- Webhook Setup ---
application = Application.builder().token(TELEGRAM_TOKEN).build()
application.add_handler(CommandHandler("scan", scan))

@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def webhook():
    # --- DIAGNOSTIC LOGS ---
    logger.info("✅ Webhook route was hit! Receiving a request...")
    
    request_data = request.get_data(as_text=True)
    logger.info(f"--- REQUEST DATA ---\n{request_data}\n--------------------")
    # --- END DIAGNOSTIC LOGS ---
    
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        application.update_queue.put_nowait(update)
        logger.info("✅ Update successfully put into the queue.")
    except Exception as e:
        logger.error(f"❌ ERROR processing update: {e}")
        
    return "ok", 200

@app.route("/")
def index():
    return "Falcon Bot Webhook Service is Running!", 200

# --- Entry Point ---
if __name__ == "__main__":
    logger.info("--- Starting Webhook Application ---")
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


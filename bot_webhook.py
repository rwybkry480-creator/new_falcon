# -----------------------------------------------------------------------------
# smc_bot_v18.0.py - (Falcon KDJ Sniper v18.0: J > K & J > D)
# -----------------------------------------------------------------------------

import os
import logging
import asyncio
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from binance.client import Client
import pandas as pd
import pandas_ta as ta

# --- الإعدادات الأساسية ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
app = Flask(__name__)

# --- إعدادات Binance ---
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)

# --- خادم الويب ---
@app.route('/')
def health_check():
    return "Falcon KDJ Sniper Bot Service (v18.0) is Running!", 200

def run_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- دوال التحليل ---
def get_binance_klines(symbol, interval='1h', limit=100):
    try:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
        return klines
    except Exception as e:
        logger.error(f"Error fetching klines for {symbol}: {e}")
        return None

def analyze_symbol_kdj(df):
    try:
        kdj_df = df.ta.kdj()
        df = pd.concat([df, kdj_df], axis=1)
        required_cols = ['J_14_3_3', 'K_14_3_3', 'D_14_3_3']
        if not all(col in df.columns for col in required_cols):
            return None, None
        df.dropna(inplace=True)
        if df.empty: 
            return None, None

        current_candle = df.iloc[-1]

        # الشرط: J أعلى من K و D
        if current_candle['J_14_3_3'] > current_candle['K_14_3_3'] and current_candle['J_14_3_3'] > current_candle['D_14_3_3']:
            return 'BUY', current_candle

    except Exception as e:
        logger.error(f"Error in analyze_symbol_kdj: {e}")
    
    return None, None

# --- وظائف البوت ---
async def scan_market(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data['chat_id']
    logger.info("--- Starting Market Scan (v18.0) ---")

    try:
        all_tickers = client.get_ticker()
        symbols_to_scan = [t['symbol'] for t in all_tickers if t['symbol'].endswith('USDT')]
        logger.info(f"Found {len(symbols_to_scan)} symbols to analyze.")
    except Exception as e:
        logger.error(f"Failed to fetch tickers: {e}")
        return

    found_signals = 0
    for symbol in symbols_to_scan:
        klines = get_binance_klines(symbol)
        if not klines: continue
        df = pd.DataFrame(klines, columns=['timestamp','open','high','low','close','volume','close_time','quote_av','trades','tb_base_av','tb_quote_av','ignore'])
        df['close'] = pd.to_numeric(df['close'])
        
        signal_type, signal_data = analyze_symbol_kdj(df)
        
        if signal_type == 'BUY':
            found_signals += 1
            message = (f"⚡️ *[KDJ 1h]* إشارة زخم إيجابي!\n\n"
                       f"• **العملة:** `{symbol}`\n"
                       f"• **السعر الحالي:** `{signal_data['close']:.5f}`\n\n"
                       f"• **J:** `{signal_data['J_14_3_3']:.2f}`\n"
                       f"• **K:** `{signal_data['K_14_3_3']:.2f}`\n"
                       f"• **D:** `{signal_data['D_14_3_3']:.2f}`")
            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
        await asyncio.sleep(0.1)

    logger.info(f"--- Scan complete. Found {found_signals} signals. ---")
    summary_message = f"✅ اكتمل الفحص.\nتم تحليل {len(symbols_to_scan)} عملة. تم العثور على {found_signals} إشارة شراء."
    await context.bot.send_message(chat_id=chat_id, text=summary_message)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_message.chat_id
    await update.message.reply_html("👋 أهلاً بك!\n\n"
                                    "أنا بوت **Falcon KDJ Sniper v18.0**.\n"
                                    "ألتقط أي عملة يكون فيها J > K و J > D على فريم 1 ساعة.\n"
                                    "سيتم الفحص تلقائيًا كل ساعة.")
    
    context.job_queue.run_repeating(scan_market, interval=3600, first=10, data={'chat_id': chat_id}, name="scheduled_scan")

async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_message.chat_id
    context.job_queue.run_once(scan_market, 1, data={'chat_id': chat_id}, name=f"scan_{chat_id}")

def run_bot():
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("scan", scan_command))
    
    job_data = {'chat_id': TELEGRAM_CHAT_ID}
    application.job_queue.run_repeating(scan_market, interval=3600, first=10, data=job_data, name="scheduled_scan")
    
    logger.info("--- Bot

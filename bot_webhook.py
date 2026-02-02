# -----------------------------------------------------------------------------
# smc_bot_v17.2.py - (Falcon KDJ Sniper v17.2: The Look-Back Sniper)
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
    return "Falcon KDJ Sniper Bot Service (v17.2 - Look-Back Sniper) is Running!", 200
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
            return None, None, None
        df.dropna(inplace=True)
        
        # يجب أن يكون لدينا شمعتان على الأقل بعد التنظيف للوصول إلى iloc[-2]
        if len(df) < 2: 
            return None, None, None

        # استراتيجية "النظر إلى الوراء": نحلل الشمعة المكتملة السابقة (iloc[-2])
        confirmed_candle = df.iloc[-2]
        current_candle = df.iloc[-1]

        # الشرط: J كان القائد في الشمعة السابقة المؤكدة
        if confirmed_candle['J_14_3_3'] > confirmed_candle['K_14_3_3'] and confirmed_candle['J_14_3_3'] > confirmed_candle['D_14_3_3']:
            # نرسل الإشارة مع بيانات الشمعة المؤكدة، ولكن نذكر السعر الحالي للإفادة
            current_price = current_candle['close']
            return 'BUY', confirmed_candle, current_price
            
    except Exception as e:
        logger.error(f"An unexpected error occurred during analysis: {e}")
    
    return None, None, None # يجب أن نرجع ثلاثة عناصر دائمًا

async def scan_market(context: ContextTypes.DEFAULT_TYPE):
    job_name = "Manual Scan" if context.job.name.startswith("scan_") else "Scheduled Scan"
    logger.info(f"--- Starting {job_name} (v17.2 - Look-Back Sniper) ---")
    chat_id = context.job.data['chat_id']
    if job_name == "Manual Scan":
        await context.bot.send_message(chat_id=chat_id, text=f"⏳ جاري {job_name} للسوق (فريم 1 ساعة، استراتيجية النظر للوراء)...")
    
    try:
        all_tickers = client.get_ticker()
        symbols_to_scan = [t['symbol'] for t in all_tickers if t['symbol'].endswith('USDT') and float(t.get('lastPrice', 0)) < 100]
        logger.info(f"Found {len(symbols_to_scan)} symbols under $100 to analyze.")
    except Exception as e:
        logger.error(f"Failed to fetch tickers for filtering: {e}")
        return

    found_signals = 0
    for symbol in symbols_to_scan:
        klines = get_binance_klines(symbol)
        if not klines: continue
        df = pd.DataFrame(klines, columns=['timestamp','open','high','low','close','volume','close_time','quote_av','trades','tb_base_av','tb_quote_av','ignore'])
        df['close'] = pd.to_numeric(df['close'])
        
        signal_type, signal_data, current_price = analyze_symbol_kdj(df)
        
        if signal_type == 'BUY':
            found_signals += 1
            message = (f"🟢 *[KDJ 1h - Look-Back]* حالة زخم إيجابي مؤكد!\n\n"
                       f"• **العملة:** `{symbol}`\n"
                       f"• **سعر الإشارة (الشمعة السابقة):** `{signal_data['close']:.5f}`\n"
                       f"• **السعر الحالي:** `{current_price:.5f}`\n\n"
                       f"• **بيانات الشمعة المؤكدة:**\n"
                       f"  - J: `{signal_data['J_14_3_3']:.2f}`\n"
                       f"  - K: `{signal_data['K_14_3_3']:.2f}`\n"
                       f"  - D: `{signal_data['D_14_3_3']:.2f}`")
            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
        await asyncio.sleep(0.1) # لإعطاء فرصة للتنفس بين الطلبات

    logger.info(f"--- {job_name} complete. Found {found_signals} signals. ---")
    if job_name == "Manual Scan":
        summary_message = f"✅ **اكتمل الفحص اليدوي.**\nتم تحليل {len(symbols_to_scan)} عملة. تم العثور على {found_signals} إشارة."
        await context.bot.send_message(chat_id=chat_id, text=summary_message)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_message.chat_id
    await update.message.reply_html(f"👋 أهلاً بك يا {user.mention_html()}!\n\n"
                                    f"أنا بوت **Falcon KDJ Sniper (v17.2 - The Look-Back Sniper)**.\n\n"
                                    f"يقوم البوت الآن بالفحص التلقائي **كل ساعة** باستخدام استراتيجية النظر للوراء الموثوقة.")
    
    # إزالة أي مهام قديمة لضمان عدم التكرار
    current_jobs = context.job_queue.get_jobs_by_name("scheduled_scan")
    for job in current_jobs:
        job.schedule_removal()
        
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
    
    logger.info("--- [Falcon KDJ Sniper v17.2] Bot is ready and running autonomously. ---")
    application.run_polling()

if __name__ == "__main__":
    logger.info("--- [Falcon KDJ Sniper v17.2] Starting Main Application ---")
    server_thread = Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    logger.info("--- [Falcon KDJ Sniper v17.2] Web Server has been started. ---")
    run_bot()


# -----------------------------------------------------------------------------
# smc_bot_v12.1.py - (Falcon Analyst v12.1: Wider Range)
# -----------------------------------------------------------------------------

import os
import logging
import asyncio
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import requests
import pandas as pd

# --- الإعدادات الأساسية ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
app = Flask(__name__)

# --- خادم الويب (للحفاظ على الخدمة نشطة على Render) ---
@app.route('/')
def health_check():
    return "Falcon Analyst Bot Service (v12.1) is Running!", 200
def run_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- دوال التحليل ---
def get_binance_klines(symbol, interval='1h', limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        res = requests.get(url)
        res.raise_for_status()
        return res.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching klines for {symbol}: {e}")
        return None

def calculate_emas(df):
    df['close'] = pd.to_numeric(df['close'])
    df['EMA7'] = df['close'].ewm(span=7, adjust=False).mean()
    df['EMA25'] = df['close'].ewm(span=25, adjust=False).mean()
    return df

def find_nearby_level(price, levels, level_type):
    for level in levels:
        # --- التغيير الرئيسي هنا ---
        # قمنا بزيادة النطاق من 0.5% إلى 1.5%
        if abs(price - level) / level < 0.015:
            return level
    return None

async def analyze_market(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data['chat_id']
    await context.bot.send_message(chat_id=chat_id, text="⏳ جاري فحص السوق بالمعايير الجديدة (نطاق 1.5%)...")
    
    try:
        tickers_res = requests.get("https://api.binance.com/api/v3/ticker/24hr")
        tickers_res.raise_for_status()
        all_symbols = [t['symbol'] for t in tickers_res.json() if t['symbol'].endswith('USDT')]
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch tickers: {e}")
        return

    SUPPORT_LEVELS = [float(x) for x in os.getenv("SUPPORT_LEVELS", "0.1530,0.1450,0.1380").split(",")]
    RESISTANCE_LEVELS = [float(x) for x in os.getenv("RESISTANCE_LEVELS", "0.1594,0.1639,0.1700").split(",")]

    found_signals = 0
    for symbol in all_symbols:
        klines = get_binance_klines(symbol)
        if not klines or len(klines) < 30:
            continue

        df = pd.DataFrame(klines, columns=['timestamp','open','high','low','close','volume','close_time','quote_av','trades','tb_base_av','tb_quote_av','ignore'])
        df = calculate_emas(df)
        last_candle = df.iloc[-1]
        last_close = last_candle['close']

        is_uptrend = last_close > last_candle['EMA7'] > last_candle['EMA25']
        if not is_uptrend:
            continue

        # --- البحث عن سيناريوهات ---
        # 1. سيناريو الاختراق
        nearby_resistance = find_nearby_level(last_close, RESISTANCE_LEVELS, 'resistance')
        if nearby_resistance:
            found_signals += 1
            message = (
                f"🎯 *سيناريو اختراق محتمل!* 🎯\n\n"
                f"• **العملة:** `{symbol}`\n"
                f"• **السعر الحالي:** `{last_close:.5f}`\n"
                f"• **مقاومة قريبة:** `{nearby_resistance:.5f}`\n\n"
                f"**الخطة المقترحة:**\n"
                f"راقب السعر. إذا اخترق المقاومة بحجم تداول قوي، قد تكون إشارة دخول. وقف الخسارة يكون أسفل المقاومة."
            )
            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')

        # 2. سيناريو الارتداد
        nearby_support = find_nearby_level(last_close, SUPPORT_LEVELS, 'support')
        if nearby_support:
            found_signals += 1
            message = (
                f"🛡️ *سيناريو ارتداد محتمل!* 🛡️\n\n"
                f"• **العملة:** `{symbol}`\n"
                f"• **السعر الحالي:** `{last_close:.5f}`\n"
                f"• **دعم قريب:** `{nearby_support:.5f}`\n\n"
                f"**الخطة المقترحة:**\n"
                f"راقب السعر. إذا ارتد من الدعم وظهرت شمعة صاعدة، قد تكون إشارة دخول. وقف الخسارة يكون أسفل الدعم."
            )
            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
        
        await asyncio.sleep(0.1) # لتجنب إغراق واجهة Binance

    if found_signals == 0:
        await context.bot.send_message(chat_id=chat_id, text="✅ اكتمل الفحص. لم يتم العثور على أي عملة تطابق الشروط الصارمة حاليًا.")

# --- أوامر البوت ودالة التشغيل ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_html(
        f"👋 أهلاً بك يا {user.mention_html()}!\n\n"
        f"أنا بوت فالكون المحلل (v12.1).\n"
        f"أبحث عن سيناريوهات الاختراق والارتداد بناءً على خطتك (بنطاق أوسع).",
    )
    # جدولة المهمة لأول مرة عند البدء
    chat_id = update.effective_message.chat_id
    context.job_queue.run_once(analyze_market, 10, chat_id=chat_id, name=str(chat_id))


def run_bot():
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    
    # إضافة البيانات اللازمة للمهمة المجدولة
    job_data = {'chat_id': TELEGRAM_CHAT_ID}
    # يمكنك هنا جدولة الفحص الدوري إذا أردت
    # application.job_queue.run_repeating(analyze_market, interval=3600, first=15, data=job_data)
    
    logger.info("--- [Falcon Analyst v12.1] Bot is ready and running. ---")
    application.run_polling()

if __name__ == "__main__":
    logger.info("--- [Falcon Analyst v12.1] Starting Main Application ---")
    server_thread = Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    logger.info("--- [Falcon Analyst v12.1] Web Server has been started. ---")
    run_bot()


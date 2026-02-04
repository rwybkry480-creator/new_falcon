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

# --- إعداد خادم الويب لـ Render ---
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Momentum Sniper Bot (v2.0 - OBV Edition) is Live!", 200

def run_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- إعدادات Binance ---
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)

# --- دوال التحليل الفني ---
def get_binance_klines(symbol, interval='1h', limit=100):
    try:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
        return klines
    except Exception as e:
        logger.error(f"Error fetching klines for {symbol}: {e}")
        return None

def analyze_momentum_strategy(df):
    """
    استراتيجية قناص الزخم المطور (v2.0):
    1. StochRSI (K) > 70 (الزخم)
    2. السعر فوق SuperTrend (الاتجاه)
    3. OBV في صعود (السيولة) - تأكيد دخول سيولة حقيقية
    """
    try:
        # 1. حساب StochRSI
        stoch_rsi = ta.stochrsi(df['close'], length=14, rsi_length=14, k=3, d=3)
        df = pd.concat([df, stoch_rsi], axis=1)
        
        # 2. حساب SuperTrend (10, 3)
        supertrend = ta.supertrend(df['high'], df['low'], df['close'], length=10, multiplier=3)
        df = pd.concat([df, supertrend], axis=1)
        
        # 3. حساب OBV
        df['obv'] = ta.obv(df['close'], df['vol'])
        df['obv_sma'] = df['obv'].rolling(window=5).mean()
        
        df.dropna(inplace=True)
        if df.empty: return None, None

        current = df.iloc[-1]
        previous = df.iloc[-2]
        
        # تسميات الأعمدة في مكتبة pandas_ta
        stoch_k = 'STOCHRSIk_14_14_3_3'
        st_direction = 'SUPERTd_10_3.0'
        
        # الشروط:
        cond_stoch = current[stoch_k] > 70
        cond_trend = current[st_direction] == 1
        cond_obv = current['obv'] > previous['obv'] and current['obv'] > current['obv_sma']
        
        if cond_stoch and cond_trend and cond_obv:
            return 'BUY', current
            
    except Exception as e:
        logger.error(f"Analysis error: {e}")
    return None, None

async def scan_market(context: ContextTypes.DEFAULT_TYPE):
    job_name = "Manual Scan" if context.job.name.startswith("scan_") else "Scheduled Scan"
    chat_id = context.job.data['chat_id']
    
    if job_name == "Manual Scan":
        await context.bot.send_message(chat_id=chat_id, text="⏳ جاري فحص السوق (استراتيجية SYN - سيولة + زخم)...")
    
    try:
        all_tickers = client.get_ticker()
        # فحص العملات التي حجم تداولها اليومي > 1 مليون دولار لضمان الجودة
        symbols = [t['symbol'] for t in all_tickers if t['symbol'].endswith('USDT') and float(t.get('quoteVolume', 0)) > 1000000]
    except Exception as e:
        logger.error(f"Ticker fetch error: {e}")
        return

    found_signals = 0
    for symbol in symbols[:100]: # فحص أفضل 100 عملة نشطة
        klines = get_binance_klines(symbol)
        if not klines: continue
        
        df = pd.DataFrame(klines, columns=['ts','open','high','low','close','vol','ct','qav','tr','tbba','tbqa','ig'])
        df['close'] = pd.to_numeric(df['close'])
        df['high'] = pd.to_numeric(df['high'])
        df['low'] = pd.to_numeric(df['low'])
        df['vol'] = pd.to_numeric(df['vol'])
        
        signal_type, data = analyze_momentum_strategy(df)
        
        if signal_type == 'BUY':
            found_signals += 1
            msg = (f"🔥 **إشارة انفجار سيولة (1ساعة)**\n\n"
                   f"• العملة: `{symbol}`\n"
                   f"• السعر: `{data['close']:.5f}`\n"
                   f"• StochRSI: `{data['STOCHRSIk_14_14_3_3']:.2f}`\n"
                   f"• الحالة: **سيولة ضخمة تدخل الآن** 💰")
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
        await asyncio.sleep(0.1)

    if job_name == "Manual Scan":
        await context.bot.send_message(chat_id=chat_id, text=f"✅ اكتمل الفحص. تم العثور على {found_signals} إشارة قوية.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text("مرحباً! بوت قناص السيولة (v2.0) يعمل الآن.\n"
                                   "أبحث عن العملات التي تحقق زخماً مثل SYN باستخدام OBV و StochRSI.")
    
    for job in context.job_queue.get_jobs_by_name("auto_scan"):
        job.schedule_removal()
    context.job_queue.run_repeating(scan_market, interval=3600, first=10, data={'chat_id': chat_id}, name="auto_scan")

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    context.job_queue.run_once(scan_market, 1, data={'chat_id': chat_id}, name=f"scan_{chat_id}")

def run_bot():
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("scan", scan_cmd))
    
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if chat_id:
        application.job_queue.run_repeating(scan_market, interval=3600, first=10, data={'chat_id': chat_id}, name="auto_scan")
    
    application.run_polling()

if __name__ == "__main__":
    Thread(target=run_server, daemon=True).start()
    run_bot()

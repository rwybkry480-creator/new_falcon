# -----------------------------------------------------------------------------
# smc_bot_v14.0.py - (Falcon KDJ Sniper v14.0: Autonomous & Filtered)
# -----------------------------------------------------------------------------

import os
import logging
import asyncio
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from binance.client import Client # <-- سنحتاج العميل الكامل الآن لفلترة الأسعار
import pandas as pd
import pandas_ta as ta

# --- الإعدادات الأساسية ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
app = Flask(__name__)

# --- إعدادات Binance ---
# تأكد من إضافة هذه المتغيرات في بيئة Render
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)


# --- خادم الويب ---
@app.route('/')
def health_check():
    return "Falcon KDJ Sniper Bot Service (v14.0 - Autonomous) is Running!", 200
def run_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- دوال التحليل (تبقى كما هي) ---
def get_binance_klines(symbol, interval='15m', limit=210):
    try:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
        return klines
    except Exception as e:
        logger.error(f"Error fetching klines for {symbol}: {e}")
        return None

def analyze_symbol_kdj(df):
    try:
        df.ta.kdj(append=True)
        df.ta.ema(length=200, append=True)
        df.dropna(inplace=True)
        if len(df) < 2: return None, None
        previous, current = df.iloc[-2], df.iloc[-1]
        
        # شروط الشراء
        if (current['close'] > current['EMA_200'] and
            (previous['J_14_3_3'] < previous['K_14_3_3'] or previous['J_14_3_3'] < previous['D_14_3_3']) and
            (current['J_14_3_3'] > current['K_14_3_3'] and current['J_14_3_3'] > current['D_14_3_3'])):
            return 'BUY', current
            
        # شروط البيع
        if (current['close'] < current['EMA_200'] and
            (previous['J_14_3_3'] > previous['K_14_3_3'] or previous['J_14_3_3'] > previous['D_14_3_3']) and
            (current['J_14_3_3'] < current['K_14_3_3'] and current['J_14_3_3'] < current['D_14_3_3'])):
            return 'SELL', current
            
    except Exception as e:
        logger.error(f"Error during analysis for symbol: {e}")
    return None, None

# --- دالة الفحص الرئيسية (معدلة) ---
async def scan_market(context: ContextTypes.DEFAULT_TYPE):
    job_name = "Manual Scan" if context.job.name.startswith("scan_") else "Scheduled Scan"
    logger.info(f"--- Starting {job_name} ---")
    
    chat_id = context.job.data['chat_id']
    
    # فقط أرسل رسالة البدء في الفحص اليدوي لتجنب الإزعاج
    if job_name == "Manual Scan":
        await context.bot.send_message(chat_id=chat_id, text=f"⏳ جاري {job_name} للسوق (فريم 15 دقيقة)...")

    # --- التغيير الأول: فلترة العملات حسب السعر ---
    try:
        all_tickers = client.get_ticker()
        symbols_to_scan = [
            t['symbol'] for t in all_tickers 
            if t['symbol'].endswith('USDT') and float(t.get('lastPrice', 0)) < 100
        ]
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

        signal_type, signal_data = analyze_symbol_kdj(df)

        if signal_type:
            found_signals += 1
            signal_emoji = "📈" if signal_type == 'BUY' else "📉"
            action_text = "شراء" if signal_type == 'BUY' else "بيع"
            trend_text = "صاعد" if signal_type == 'BUY' else "هابط"
            
            message = (
                f"{signal_emoji} *[KDJ 15m]* إشارة {action_text}!\n\n"
                f"• **العملة:** `{symbol}`\n"
                f"• **السعر:** `{signal_data['close']:.5f}`\n\n"
                f"• **السبب:**\n"
                f"  - خط J اخترق خطي K و D.\n"
                f"  - السعر في اتجاه عام {trend_text} (EMA 200)."
            )
            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')

        await asyncio.sleep(0.1)

    logger.info(f"--- {job_name} complete. Found {found_signals} signals. ---")
    # نرسل ملخصًا فقط إذا كان الفحص يدويًا
    if job_name == "Manual Scan":
        summary_message = f"✅ **اكتمل الفحص اليدوي.**\nتم تحليل {len(symbols_to_scan)} عملة. تم العثور على {found_signals} إشارة."
        await context.bot.send_message(chat_id=chat_id, text=summary_message)


# --- أوامر البوت ودالة التشغيل (معدلة) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_message.chat_id
    
    await update.message.reply_html(
        f"👋 أهلاً بك يا {user.mention_html()}!\n\n"
        f"أنا بوت **Falcon KDJ Sniper (v14.0 - Autonomous)**.\n\n"
        f"يقوم البوت الآن بالفحص التلقائي للسوق **كل 15 دقيقة** بحثًا عن فرص على فريم الـ 15 دقيقة.\n\n"
        f"يمكنك أيضًا استخدام /scan لإجراء فحص يدوي فوري."
    )
    
    # إزالة أي مهام قديمة وبدء مهمة جديدة لضمان عدم التكرار
    current_jobs = context.job_queue.get_jobs_by_name("scheduled_scan")
    for job in current_jobs:
        job.schedule_removal()
        
    # --- التغيير الثاني: جدولة الفحص التلقائي ---
    context.job_queue.run_repeating(
        scan_market, 
        interval=900,  # 900 ثانية = 15 دقيقة
        first=10,      # ابدأ أول فحص بعد 10 ثوانٍ
        data={'chat_id': chat_id}, 
        name="scheduled_scan"
    )

async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_message.chat_id
    context.job_queue.run_once(scan_market, 1, data={'chat_id': chat_id}, name=f"scan_{chat_id}")

def run_bot():
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") # سنحتاجه للجدولة عند بدء التشغيل
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # إضافة الأوامر
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("scan", scan_command))
    
    # جدولة المهمة عند بدء تشغيل البوت لأول مرة
    job_data = {'chat_id': TELEGRAM_CHAT_ID}
    application.job_queue.run_repeating(
        scan_market, 
        interval=900, 
        first=10, 
        data=job_data, 
        name="scheduled_scan"
    )
    
    logger.info("--- [Falcon KDJ Sniper v14.0] Bot is ready and running autonomously. ---")
    application.run_polling()

if __name__ == "__main__":
    logger.info("--- [Falcon KDJ Sniper v14.0] Starting Main Application ---")
    server_thread = Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    logger.info("--- [Falcon KDJ Sniper v14.0] Web Server has been started. ---")
    run_bot()


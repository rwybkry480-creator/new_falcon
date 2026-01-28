# -----------------------------------------------------------------------------
# bot_final_working.py - v12.0 (Smart Scenario Analyzer)
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

# --- Logging Setup ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Flask Web Server (for Health Checks only) ---
app = Flask(__name__)
@app.route('/')
def health_check():
    return "Falcon Scanner Bot (v12.0 - Scenario Analyzer) is Running!", 200
def run_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- Binance API & Analysis Functions ---
# يمكنك تعديل هذه المستويات من متغيرات البيئة في Render
SUPPORT_LEVELS_STR = os.getenv("SUPPORT_LEVELS", "0.1530,0.1450,0.1380")
RESISTANCE_LEVELS_STR = os.getenv("RESISTANCE_LEVELS", "0.1594,0.1639,0.1700")
SUPPORT_LEVELS = [float(x) for x in SUPPORT_LEVELS_STR.split(",")]
RESISTANCE_LEVELS = [float(x) for x in RESISTANCE_LEVELS_STR.split(",")]
KLINES_LIMIT = 50

def get_all_usdt_symbols():
    # ... (نفس الدالة بدون تغيير)
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
    # ... (نفس الدالة بدون تغيير)
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.warning(f"Could not fetch klines for {symbol}: {e}")
        return None

def analyze_symbol(symbol, data):
    """
    يحلل السوق بناءً على سيناريوهات الاختراق والارتداد المحددة.
    """
    if not data or len(data) < 26: # نحتاج شمعتين على الأقل للتحقق من الاختراق
        return None

    df = pd.DataFrame(data, columns=['timestamp','open','high','low','close','volume','time','quote_av','trades','tb_base_av','tb_quote_av','ignore'])
    df[['open', 'high', 'low', 'close']] = df[['open', 'high', 'low', 'close']].apply(pd.to_numeric)

    # حساب المتوسطات
    df['EMA7'] = df['close'].ewm(span=7, adjust=False).mean()
    df['EMA25'] = df['close'].ewm(span=25, adjust=False).mean()

    # استخراج بيانات آخر شمعتين
    prev_candle = df.iloc[-2]
    last_candle = df.iloc[-1]

    # الشرط الأساسي: الاتجاه العام يجب أن يكون صاعدًا (الشرط الصارم)
    is_strong_uptrend = last_candle['close'] > last_candle['EMA7'] > last_candle['EMA25']
    
    if not is_strong_uptrend:
        return None # إذا لم يكن الاتجاه صاعدًا، لا تكمل التحليل

    # --- الآن، نبحث عن السيناريوهات المحددة ---

    # 1. البحث عن سيناريو الاختراق (Breakout)
    for res_level in RESISTANCE_LEVELS:
        # هل الشمعة الحالية اخترقت المقاومة، بينما الشمعة السابقة كانت تحتها؟
        if last_candle['close'] > res_level and prev_candle['close'] < res_level:
            logger.info(f"Breakout scenario detected for {symbol} at resistance {res_level}")
            stop_loss = prev_candle['low'] # وقف الخسارة تحت قاع الشمعة السابقة
            return (f"🔥 **سيناريو اختراق (Breakout)** 🔥\n\n"
                    f"• **العملة:** `{symbol}`\n"
                    f"• **السعر الحالي:** `{last_candle['close']:.5f}`\n"
                    f"• **الحدث:** تم اختراق مستوى المقاومة `{res_level}` بنجاح.\n\n"
                    f"• **خطة مقترحة:**\n"
                    f"  - **الدخول:** حول السعر الحالي.\n"
                    f"  - **وقف الخسارة المقترح:** أسفل `{stop_loss:.5f}`.")

    # 2. البحث عن سيناريو الارتداد (Pullback/Bounce)
    # هل لامس قاع الشمعة منطقة الدعم (بين متوسط 7 و 25) ثم ارتد؟
    support_zone_top = max(last_candle['EMA7'], last_candle['EMA25'])
    support_zone_bottom = min(last_candle['EMA7'], last_candle['EMA25'])
    
    if support_zone_bottom <= last_candle['low'] <= support_zone_top and last_candle['close'] > last_candle['open']:
        logger.info(f"Bounce scenario detected for {symbol} from EMA support zone.")
        stop_loss = df['low'].iloc[-5:].min() # وقف الخسارة تحت أدنى قاع لآخر 5 شمعات لمزيد من الأمان
        return (f"🛡️ **سيناريو ارتداد (Bounce)** 🛡️\n\n"
                f"• **العملة:** `{symbol}`\n"
                f"• **السعر الحالي:** `{last_candle['close']:.5f}`\n"
                f"• **الحدث:** ارتد السعر من منطقة الدعم للمتوسطات المتحركة.\n\n"
                f"• **خطة مقترحة:**\n"
                f"  - **الدخول:** حول السعر الحالي (منطقة آمنة).\n"
                f"  - **وقف الخسارة المقترح:** أسفل `{stop_loss:.5f}`.")

    return None

# --- بقية الكود (run_full_scan, start, scan, etc.) تبقى كما هي بدون أي تغيير ---
def run_full_scan():
    logger.info("--- Starting a new market scan (v12.0) ---")
    all_symbols = get_all_usdt_symbols()
    signals = []
    if not all_symbols:
        logger.warning("Could not retrieve symbols to scan.")
        return []
    for symbol in all_symbols:
        klines = get_binance_klines(symbol)
        signal = analyze_symbol(symbol, klines)
        if signal:
            signals.append(signal)
        asyncio.run(asyncio.sleep(0.1))
    logger.info(f"--- Scan complete. Found {len(signals)} signals. ---")
    return signals

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = (f"👋 أهلاً بك يا {user.mention_html()}!\n\n"
               f"أنا <b>بوت فالكون المحلل (v12.0)</b>.\n"
               f"أبحث عن سيناريوهات الاختراق والارتداد بناءً على خطتك.\n\n"
               f"<i>صنع بواسطة المطور عبدالرحمن محمد</i>")
    await update.message.reply_html(message, disable_web_page_preview=True)

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ جاري تحليل السوق بحثاً عن سيناريوهات محددة...")
    signals = run_full_scan()
    if not signals:
        await update.message.reply_text("✅ تم فحص السوق. لا توجد سيناريوهات اختراق أو ارتداد واضحة حاليًا.")
    else:
        await update.message.reply_text(f"📊 تم العثور على {len(signals)} سيناريو تداول محتمل:")
        for signal in signals:
            # استخدمنا parse_mode='Markdown' لتنسيق النص (عريض ومائل)
            await update.message.reply_text(signal, parse_mode='Markdown')

def run_bot():
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("scan", scan))
    logger.info("--- [Falcon Scanner v12.0] Bot is ready and running (Polling Mode). ---")
    application.run_polling()

if __name__ == "__main__":
    logger.info("--- [Falcon Scanner v12.0] Starting Main Application ---")
    server_thread = Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    logger.info("--- [Falcon Scanner v12.0] Web Server has been started. ---")
    run_bot()


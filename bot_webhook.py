# -----------------------------------------------------------------------------
# bot_final_working.py - v11.0 (Multi-Timeframe Analysis 1H + 4H)
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
    return "Falcon Scanner Bot (v11.0 - MTFA 1H/4H) is Running!", 200
def run_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- Binance API & Analysis Functions ---
SUPPORT_LEVELS = [float(x) for x in os.getenv("SUPPORT_LEVELS", "0.1530,0.1450,0.1380").split(",")]
RESISTANCE_LEVELS = [float(x) for x in os.getenv("RESISTANCE_LEVELS", "0.1594,0.1639,0.1700").split(",")]
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

def check_uptrend(data):
    """
    دالة مساعدة للتحقق من وجود اتجاه صاعد (المنطق الأصلي v10.0).
    """
    if not data or len(data) < 25:
        return False, 0, 0, 0

    df = pd.DataFrame(data, columns=['timestamp','open','high','low','close','volume','time','quote_av','trades','tb_base_av','tb_quote_av','ignore'])
    df['close'] = pd.to_numeric(df['close'])
    
    ema7 = df['close'].ewm(span=7, adjust=False).mean().iloc[-1]
    ema25 = df['close'].ewm(span=25, adjust=False).mean().iloc[-1]
    last_close = df['close'].iloc[-1]

    # المنطق الأصلي الفضفاض
    is_uptrend = last_close > ema7 and last_close > ema25
    return is_uptrend, last_close, ema7, ema25

def analyze_symbol(symbol):
    """
    التحليل باستخدام فلتر الأطر الزمنية المتعددة (1H و 4H).
    """
    # 1. جلب بيانات كلا الإطارين الزمنيين
    klines_1h = get_binance_klines(symbol, interval="1h")
    klines_4h = get_binance_klines(symbol, interval="4h")

    # 2. التحقق من وجود اتجاه صاعد على كلا الإطارين
    uptrend_1h, last_close_1h, ema7_1h, ema25_1h = check_uptrend(klines_1h)
    uptrend_4h, _, _, _ = check_uptrend(klines_4h) # لا نحتاج تفاصيل الـ 4 ساعات، فقط التأكيد

    # 3. الشرط الأساسي الجديد: يجب أن يكون الاتجاه صاعدًا على كلا الفريمين
    if uptrend_1h and uptrend_4h:
        logger.info(f"Confirmation on {symbol}: 1H uptrend and 4H uptrend are both true.")
        
        # 4. الآن فقط، نتحقق من شروط الدعم والمقاومة على فريم الساعة
        near_support = any(abs(last_close_1h - s) / s < 0.01 for s in SUPPORT_LEVELS)
        near_resistance = any(abs(last_close_1h - r) / r < 0.01 for r in RESISTANCE_LEVELS)

        if near_resistance:
            return (f"📈 إشارة شراء قوية (Long - MTFA)\n"
                    f"العملة: {symbol}\n"
                    f"السعر: {last_close_1h:.5f}\n"
                    f"تأكيد 1H ✅ | تأكيد 4H ✅\n"
                    f"🚀 قريب من اختراق مقاومة مهمة")
        if near_support:
            return (f"📈 إشارة شراء محتملة (ارتداد - MTFA)\n"
                    f"العملة: {symbol}\n"
                    f"السعر: {last_close_1h:.5f}\n"
                    f"تأكيد 1H ✅ | تأكيد 4H ✅\n"
                    f"🛡️ ارتداد من دعم قوي")
    return None

# --- بقية الكود (run_full_scan, start, scan, etc.) تبقى كما هي بدون أي تغيير ---
def run_full_scan():
    logger.info("--- Starting a new market scan (v11.0 - MTFA) ---")
    all_symbols = get_all_usdt_symbols()
    signals = []
    if not all_symbols:
        logger.warning("Could not retrieve symbols to scan.")
        return []
    for symbol in all_symbols:
        signal = analyze_symbol(symbol)
        if signal:
            signals.append(signal)
        asyncio.run(asyncio.sleep(0.2)) # زدنا الفاصل قليلاً لأننا نطلب بيانات مضاعفة
    logger.info(f"--- Scan complete. Found {len(signals)} signals. ---")
    return signals

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = (f"👋 أهلاً بك يا {user.mention_html()}!\n\n"
               f"أنا <b>بوت فالكون الماسح (v11.0 - MTFA)</b>.\n"
               f"أبحث عن فرص يتوافق فيها اتجاه الساعة مع الأربع ساعات.\n\n"
               f"<i>صنع بواسطة المطور عبدالرحمن محمد</i>")
    await update.message.reply_html(message, disable_web_page_preview=True)

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ جاري فحص السوق (بفلتر 1H/4H)، قد يستغرق هذا بضع دقائق...")
    signals = run_full_scan()
    if not signals:
        await update.message.reply_text("✅ تم فحص السوق. لا توجد فرص يتوافق فيها الإطاران الزمنيان حاليًا.")
    else:
        await update.message.reply_text(f"📊 تم العثور على {len(signals)} إشارة عالية الجودة (MTFA):")
        for signal in signals:
            await update.message.reply_text(signal)

def run_bot():
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("scan", scan))
    logger.info("--- [Falcon Scanner v11.0] Bot is ready and running (Polling Mode). ---")
    application.run_polling()

if __name__ == "__main__":
    logger.info("--- [Falcon Scanner v11.0] Starting Main Application ---")
    server_thread = Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    logger.info("--- [Falcon Scanner v11.0] Web Server has been started. ---")
    run_bot()


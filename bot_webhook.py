# -----------------------------------------------------------------------------
# smc_bot_v13.1.py - (Falcon KDJ Sniper v13.1: Pure J-Line Breakout)
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
import pandas_ta as ta # <-- مكتبة التحليل الفني القوية

# --- الإعدادات الأساسية ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
app = Flask(__name__)

# --- خادم الويب (للحفاظ على الخدمة نشطة على Render) ---
@app.route('/')
def health_check():
    return "Falcon KDJ Sniper Bot Service (v13.1) is Running!", 200
def run_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- دوال التحليل ---
def get_binance_klines(symbol, interval='1h', limit=210): # نطلب شموع أكثر قليلاً لضمان دقة EMA 200
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        res = requests.get(url)
        res.raise_for_status()
        return res.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching klines for {symbol}: {e}")
        return None

def analyze_symbol_kdj(df):
    """
    يحلل الداتا فريم بناءً على استراتيجية تقاطع خط J.
    """
    try:
        # 1. حساب المؤشرات المطلوبة باستخدام pandas-ta
        df.ta.kdj(append=True) # يحسب K, D, J
        df.ta.ema(length=200, append=True) # يحسب EMA 200

        # إزالة الصفوف التي لا تحتوي على قيم كاملة للمؤشرات
        df.dropna(inplace=True)
        if len(df) < 2:
            return None, None # لا يمكن المقارنة إذا لم يكن لدينا شمعتان على الأقل

        # 2. تحديد الشمعة الحالية والشمعة السابقة
        previous = df.iloc[-2]
        current = df.iloc[-1]

        # 3. تطبيق شروط استراتيجية الشراء
        price_above_ema200 = current['close'] > current['EMA_200']
        # هل كان J تحت K أو D في الشمعة السابقة؟
        j_was_below = previous['J_14_3_3'] < previous['K_14_3_3'] or previous['J_14_3_3'] < previous['D_14_3_3']
        # هل J الآن فوق K و D؟
        j_is_above = current['J_14_3_3'] > current['K_14_3_3'] and current['J_14_3_3'] > current['D_14_3_3']

        if price_above_ema200 and j_was_below and j_is_above:
            signal_type = 'BUY'
            return signal_type, current

        # 4. تطبيق شروط استراتيجية البيع
        price_below_ema200 = current['close'] < current['EMA_200']
        # هل كان J فوق K أو D في الشمعة السابقة؟
        j_was_above = previous['J_14_3_3'] > previous['K_14_3_3'] or previous['J_14_3_3'] > previous['D_14_3_3']
        # هل J الآن تحت K و D؟
        j_is_below = current['J_14_3_3'] < current['K_14_3_3'] and current['J_14_3_3'] < current['D_14_3_3']

        if price_below_ema200 and j_was_above and j_is_below:
            signal_type = 'SELL'
            return signal_type, current

    except Exception as e:
        logger.error(f"Error during analysis: {e}")

    return None, None


async def scan_market(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data['chat_id']
    await context.bot.send_message(chat_id=chat_id, text="⏳ جاري فحص السوق باستخدام استراتيجية KDJ Sniper...")

    try:
        tickers_res = requests.get("https://api.binance.com/api/v3/ticker/24hr")
        tickers_res.raise_for_status()
        all_symbols = [t['symbol'] for t in tickers_res.json() if t['symbol'].endswith('USDT')]
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch tickers: {e}")
        await context.bot.send_message(chat_id=chat_id, text="⚠️ فشل في جلب قائمة العملات من Binance.")
        return

    found_signals = 0
    for symbol in all_symbols:
        klines = get_binance_klines(symbol)
        if not klines:
            continue

        df = pd.DataFrame(klines, columns=['timestamp','open','high','low','close','volume','close_time','quote_av','trades','tb_base_av','tb_quote_av','ignore'])
        df['close'] = pd.to_numeric(df['close'])

        signal_type, signal_data = analyze_symbol_kdj(df)

        if signal_type == 'BUY':
            found_signals += 1
            message = (
                f"📈 *[KDJ Sniper]* إشارة شراء قوية!\n\n"
                f"• **العملة:** `{symbol}`\n"
                f"• **السعر:** `{signal_data['close']:.5f}`\n\n"
                f"• **السبب:**\n"
                f"  - خط J اخترق خطي K و D للأعلى.\n"
                f"  - السعر فوق متوسط 200 (اتجاه عام صاعد)."
            )
            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')

        elif signal_type == 'SELL':
            found_signals += 1
            message = (
                f"📉 *[KDJ Sniper]* إشارة بيع قوية!\n\n"
                f"• **العملة:** `{symbol}`\n"
                f"• **السعر:** `{signal_data['close']:.5f}`\n\n"
                f"• **السبب:**\n"
                f"  - خط J كسر خطي K و D للأسفل.\n"
                f"  - السعر تحت متوسط 200 (اتجاه عام هابط)."
            )
            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')

        await asyncio.sleep(0.1)

    summary_message = f"✅ **اكتمل فحص KDJ.**\nتم تحليل {len(all_symbols)} عملة. تم العثور على {found_signals} إشارة."
    await context.bot.send_message(chat_id=chat_id, text=summary_message)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_message.chat_id
    await update.message.reply_html(
        f"👋 أهلاً بك يا {user.mention_html()}!\n\n"
        f"أنا بوت **Falcon KDJ Sniper (v13.1)**.\n"
        f"استخدم الأمر /scan لبدء فحص السوق بحثًا عن تقاطعات خط J."
    )

async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_message.chat_id
    await update.message.reply_text("✅ تم استلام أمر الفحص. سأبدأ الآن في الخلفية...")
    context.job_queue.run_once(scan_market, 1, data={'chat_id': chat_id}, name=f"scan_{chat_id}")


def run_bot():
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("scan", scan_command))
    logger.info("--- [Falcon KDJ Sniper v13.1] Bot is ready and running. ---")
    application.run_polling()

if __name__ == "__main__":
    logger.info("--- [Falcon KDJ Sniper v13.1] Starting Main Application ---")
    server_thread = Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    logger.info("--- [Falcon KDJ Sniper v13.1] Web Server has been started. ---")
    run_bot()


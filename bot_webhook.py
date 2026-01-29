# -----------------------------------------------------------------------------
# smc_bot_v13.2.py - (Falcon KDJ Sniper v13.2: 15-Minute Frame)
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
import pandas_ta as ta

# --- الإعدادات الأساسية ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
app = Flask(__name__)

# --- خادم الويب ---
@app.route('/')
def health_check():
    return "Falcon KDJ Sniper Bot Service (v13.2 - 15min) is Running!", 200
def run_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- دوال التحليل ---
def get_binance_klines(symbol, interval='15m', limit=210): # تم التغيير إلى فريم 15 دقيقة
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        res = requests.get(url)
        res.raise_for_status()
        return res.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching klines for {symbol}: {e}")
        return None

def analyze_symbol_kdj(df):
    try:
        df.ta.kdj(append=True)
        df.ta.ema(length=200, append=True)
        df.dropna(inplace=True)
        if len(df) < 2:
            return None, None

        previous = df.iloc[-2]
        current = df.iloc[-1]

        price_above_ema200 = current['close'] > current['EMA_200']
        j_was_below = previous['J_14_3_3'] < previous['K_14_3_3'] or previous['J_14_3_3'] < previous['D_14_3_3']
        j_is_above = current['J_14_3_3'] > current['K_14_3_3'] and current['J_14_3_3'] > current['D_14_3_3']

        if price_above_ema200 and j_was_below and j_is_above:
            return 'BUY', current

        price_below_ema200 = current['close'] < current['EMA_200']
        j_was_above = previous['J_14_3_3'] > previous['K_14_3_3'] or previous['J_14_3_3'] > previous['D_14_3_3']
        j_is_below = current['J_14_3_3'] < current['K_14_3_3'] and current['J_14_3_3'] < current['D_14_3_3']

        if price_below_ema200 and j_was_above and j_is_below:
            return 'SELL', current

    except Exception as e:
        logger.error(f"Error during analysis for symbol: {e}")
    return None, None

async def scan_market(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data['chat_id']
    await context.bot.send_message(chat_id=chat_id, text="⏳ جاري فحص السوق (فريم 15 دقيقة) باستراتيجية KDJ Sniper...")

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
                f"📈 *[KDJ 15m]* إشارة شراء!\n\n"
                f"• **العملة:** `{symbol}`\n"
                f"• **السعر:** `{signal_data['close']:.5f}`\n\n"
                f"• **السبب:**\n"
                f"  - خط J اخترق K و D للأعلى.\n"
                f"  - السعر فوق متوسط 200."
            )
            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')

        elif signal_type == 'SELL':
            found_signals += 1
            message = (
                f"📉 *[KDJ 15m]* إشارة بيع!\n\n"
                f"• **العملة:** `{symbol}`\n"
                f"• **السعر:** `{signal_data['close']:.5f}`\n\n"
                f"• **السبب:**\n"
                f"  - خط J كسر K و D للأسفل.\n"
                f"  - السعر تحت متوسط 200."
            )
            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')

        await asyncio.sleep(0.1)

    summary_message = f"✅ **اكتمل فحص KDJ (15m).**\nتم تحليل {len(all_symbols)} عملة. تم العثور على {found_signals} إشارة."
    await context.bot.send_message(chat_id=chat_id, text=summary_message)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_html(
        f"👋 أهلاً بك يا {user.mention_html()}!\n\n"
        f"أنا بوت **Falcon KDJ Sniper (v13.2 - 15min)**.\n"
        f"استخدم الأمر /scan لبدء فحص السوق."
    )

async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_message.chat_id
    await update.message.reply_text("✅ تم استلام أمر الفحص (15 دقيقة). سأبدأ الآن في الخلفية...")
    context.job_queue.run_once(scan_market, 1, data={'chat_id': chat_id}, name=f"scan_{chat_id}")

def run_bot():
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("scan", scan_command))
    logger.info("--- [Falcon KDJ Sniper v13.2] Bot is ready and running. ---")
    application.run_polling()

if __name__ == "__main__":
    logger.info("--- [Falcon KDJ Sniper v13.2] Starting Main Application ---")
    server_thread = Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    logger.info("--- [Falcon KDJ Sniper v13.2] Web Server has been started. ---")
    run_bot()


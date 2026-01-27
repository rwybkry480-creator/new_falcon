import os
import requests
import time
import telebot
from datetime import datetime

# قراءة المتغيرات من البيئة
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

INTERVAL = "1h"   # فريم الساعة
LIMIT = 50        # عدد الشموع المطلوبة

# مستويات الدعم والمقاومة من البيئة (يمكنك تعديلها في المنصة)
SUPPORT_LEVELS = [float(x) for x in os.getenv("SUPPORT_LEVELS", "0.1530,0.1450,0.1380").split(",")]
RESISTANCE_LEVELS = [float(x) for x in os.getenv("RESISTANCE_LEVELS", "0.1594,0.1639,0.1700").split(",")]

def get_all_symbols():
    url = "https://api.binance.com/api/v3/exchangeInfo"
    response = requests.get(url)
    data = response.json()
    symbols = [s['symbol'] for s in data['symbols'] if s['quoteAsset'] == 'USDT']
    return symbols

def get_binance_data(symbol, interval=INTERVAL, limit=LIMIT):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url)
    data = response.json()
    return data

def calculate_signal(symbol, data):
    closes = [float(candle[4]) for candle in data]  # سعر الإغلاق
    if len(closes) < 25:
        return None

    ema7 = sum(closes[-7:]) / 7
    ema25 = sum(closes[-25:]) / 25
    last_close = closes[-1]

    # تحقق من الدعم والمقاومة
    near_support = any(abs(last_close - s) / s < 0.01 for s in SUPPORT_LEVELS)
    near_resistance = any(abs(last_close - r) / r < 0.01 for r in RESISTANCE_LEVELS)

    if last_close > ema7 and last_close > ema25 and near_resistance:
        signal = (
            f"📈 إشارة شراء قوية (Long)\n"
            f"العملة: {symbol}\n"
            f"السعر: {last_close:.5f}\n"
            f"فوق EMA7 ({ema7:.5f}) و EMA25 ({ema25:.5f})\n"
            f"🚀 قريب من اختراق مقاومة مهمة"
        )
        return signal

    if last_close > ema7 and last_close > ema25 and near_support:
        signal = (
            f"📈 إشارة شراء محتملة (ارتداد)\n"
            f"العملة: {symbol}\n"
            f"السعر: {last_close:.5f}\n"
            f"فوق EMA7 ({ema7:.5f}) و EMA25 ({ema25:.5f})\n"
            f"🛡️ ارتداد من دعم قوي"
        )
        return signal

    return None

def send_signal(signal):
    bot.send_message(CHAT_ID, signal)

def main():
    while True:
        try:
            symbols = get_all_symbols()
            for symbol in symbols:
                try:
                    data = get_binance_data(symbol)
                    signal = calculate_signal(symbol, data)
                    if signal:
                        send_signal(signal)
                        print(f"[{datetime.now()}] أُرسلت إشارة: {signal}")
                except Exception as e:
                    print(f"خطأ في {symbol}: {e}")
            time.sleep(3600)  # تحديث كل ساعة
        except Exception as e:
            print("خطأ عام:", e)
            time.sleep(60)

if __name__ == "__main__":
    main()

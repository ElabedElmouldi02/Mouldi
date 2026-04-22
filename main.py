import os
import requests
import ccxt
import pandas as pd
import numpy as np
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# --- إعدادات التلجرام للمجموعة ---
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"

# أضف هنا أرقام الـ ID الخاصة بأصدقائك (تأكد أن كل صديق قد ضغط Start للبوت)
FRIENDS_IDS = [
    "5067771509", # الـ ID الخاص بك
    "2107567005", # الـ ID الصديق الأول
]
# قائمة العملات المستقرة والعملات غير المرغوبة لاستبعادها
STABLE_COINS = [
    'USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'USDP', 'USDD', 
    'FDUSD', 'EUR', 'GBP', 'JPY', 'AEUR', 'USDS'
]

def send_to_all_friends(message):
    for chat_id in FRIENDS_IDS:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        try:
            requests.post(url, json=payload, timeout=10)
        except:
            pass

def scan_mega_explosion():
    print("🔎 فحص العملات المتذبذبة (استبعاد المستقرة)...")
    try:
        exchange = ccxt.binance()
        tickers = exchange.fetch_tickers()
        
        # فلترة العملات: يجب أن تنتهي بـ USDT وألا تكون في القائمة السوداء
        symbols = [
            s for s in tickers 
            if s.endswith('/USDT') 
            and s.split('/')[0] not in STABLE_COINS # هذا هو الفلتر الجديد
        ]
        
        for symbol in symbols:
            ticker = tickers[symbol]
            daily_volume = ticker['quoteVolume']
            
            # فلتر السيولة الذهبي (بين 10 و 250 مليون دولار)
            if 10_000_000 <= daily_volume <= 250_000_000:
                
                bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
                df = pd.DataFrame(bars, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                
                # حساب ضغط البولنجر (Squeeze)
                df['MA20'] = df['c'].rolling(20).mean()
                df['STD'] = df['c'].rolling(20).std()
                df['Width'] = (df['STD'] * 4) / df['MA20'] * 100
                
                # حساب RSI
                delta = df['c'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / (loss + 1e-9)
                df['RSI'] = 100 - (100 / (1 + rs))
                
                last = df.iloc[-1]
                
                # شروط الانفجار الصارمة (RSI 55-65 وضغط < 1.2%)
                if not np.isnan(last['Width']) and last['Width'] < 1.2 and 55 <= last['RSI'] <= 65:
                    
                    price = last['c']
                    target = price * 1.10
                    stop = price * 0.96
                    
                    name = symbol.replace('/USDT', '')
                    msg = (
                        f"🌋 **إشارة انفجار حقيقي (+10%)**\n"
                        f"العملة: #{name}\n\n"
                        f"📊 **حالة الضغط:** `{last['Width']:.2f}%`\n"
                        f"📈 **القوة (RSI):** `{last['RSI']:.2f}`\n"
                        f"💰 **سيولة 24h:** `${daily_volume/1e6:.1f}M`\n\n"
                        f"📥 **دخول:** `{price:.4f}`\n"
                        f"🎯 **الهدف:** `{target:.4f}`\n"
                        f"🛑 **الوقف:** `{stop:.4f}`"
                    )
                    send_to_all_friends(msg)
                    
    except Exception as e:
        print(f"Error: {e}")

# المجدول الزمني
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(scan_mega_explosion, 'interval', minutes=15)
scheduler.start()

@app.route('/')
def index():
    return "Bot is Filtering Stables and Searching for Booms!"

if __name__ == "__main__":
    scan_mega_explosion()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

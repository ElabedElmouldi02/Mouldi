import asyncio
import ccxt.pro as ccxt
import pandas as pd
import requests
import threading
import os
from datetime import datetime
from flask import Flask
from waitress import serve

# ======================== 1. الإعدادات ========================
TELEGRAM_TOKEN = '8643715664:AAH-Th6cUZasbUrOJe6elCJuV_Fn6oTfd5g'
TELEGRAM_CHAT_IDS = ['5067771509', '-1003692815602'] 

INVESTMENT_PER_TRADE = 100  
TIMEFRAME = '15m'
EXCHANGE = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})

sent_signals_tracker = {}

def send_telegram_msg(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for chat_id in TELEGRAM_CHAT_IDS:
        try: requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# ======================== 2. الحسابات الفنية ========================

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_score(df):
    try:
        if len(df) < 30: return 0
        df['ema10'] = df['close'].ewm(span=10, adjust=False).mean()
        df['rsi'] = calculate_rsi(df['close'])
        
        last = df.iloc[-1]
        score = 0
        
        # شرط 1: السعر فوق المتوسط (2 نقطة)
        if last['close'] > last['ema10']: score += 2
        
        # شرط 2: انفجار السيولة (2 نقطة)
        avg_vol = df['vol'].rolling(20).mean().iloc[-2]
        if last['vol'] > avg_vol * 1.5: score += 2
        
        # شرط 3: شمعة شرائية قوية (1 نقطة)
        if last['close'] > last['open']: score += 1
        
        # فلتر الأمان RSI
        if last['rsi'] > 80 or last['rsi'] < 25: score = 0
            
        return score
    except: return 0

# ======================== 3. المحرك (فلترة 5/5) ========================

async def elite_scan_v12():
    current_time = datetime.now()
    to_delete = [s for s, t in sent_signals_tracker.items() if (current_time - t).total_seconds() > 21600]
    for s in to_delete: del sent_signals_tracker[s]

    try:
        all_tickers = await EXCHANGE.fetch_tickers()
        top_100 = sorted(
            [s for s in all_tickers if '/USDT' in s and 'UP/' not in s and 'DOWN/' not in s],
            key=lambda x: all_tickers[x]['quoteVolume'] or 0, reverse=True
        )[:100]
        
        for sym in top_100:
            if sym in sent_signals_tracker: continue
            
            try:
                bars = await EXCHANGE.fetch_ohlcv(sym, timeframe=TIMEFRAME, limit=50)
                df = pd.DataFrame(bars, columns=['ts','open','high','low','close','vol'])
                score = get_score(df)
                
                # التعديل الجوهري: إرسال الصفقات الكاملة فقط (5 من 5)
                if score == 5:
                    sent_signals_tracker[sym] = datetime.now()
                    price = df['close'].iloc[-1]
                    qty = INVESTMENT_PER_TRADE / price
                    
                    msg = (f"💎 *فرصة ذهبية (كاملة المواصفات 5/5)*\n"
                           f"⏰ الوقت: `{datetime.now().strftime('%H:%M:%S')}`\n"
                           f" العملة: `{sym}`\n"
                           f"📊 القوة: `100% (5/5)`\n"
                           f"💵 ادخل بـ: `100$` | الكمية: `{qty:.2f}`\n"
                           f"💰 السعر: `{price:.6f}`\n"
                           f"🛑 الوقف: `-2.5%` | 🎯 الهدف: `+5%` ")
                    send_telegram_msg(msg)
                
                await asyncio.sleep(0.05)
            except: continue

    except Exception as e: print(f"Error: {e}")

async def main_loop():
    send_telegram_msg("👑 *تم تفعيل نسخة النخبة (5/5) فقط*\n📍 السيرفر: Amsterdam\n🚀 البوت يبحث عن الصفقات المثالية الآن...")
    while True:
        try:
            await elite_scan_v12()
            await asyncio.sleep(600) # فحص كل 10 دقائق لملاحقة الفرص الذهبية
        except: await asyncio.sleep(60)

# ======================== 4. السيرفر ========================
app = Flask('')
@app.route('/')
def home(): return "Elite Bot Running"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    threading.Thread(target=lambda: serve(app, host='0.0.0.0', port=port), daemon=True).start()
    asyncio.run(main_loop())

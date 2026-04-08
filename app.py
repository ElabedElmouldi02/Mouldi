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

# ======================== 2. الحسابات الفنية (يدوياً) ========================

def calculate_rsi(series, period=14):
    """حساب مؤشر RSI يدوياً بدون مكتبات خارجية"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_score(df):
    try:
        if len(df) < 30: return 0
        
        # حساب المؤشرات يدوياً باستخدام pandas
        df['ema10'] = df['close'].ewm(span=10, adjust=False).mean()
        df['rsi'] = calculate_rsi(df['close'])
        
        last = df.iloc[-1]
        score = 0
        
        # شرط 1: السعر فوق المتوسط
        if last['close'] > last['ema10']: score += 2
        
        # شرط 2: انفجار السيولة (1.3 ضعف المتوسط)
        avg_vol = df['vol'].rolling(20).mean().iloc[-2]
        if last['vol'] > avg_vol * 1.3: score += 2
        
        # شرط 3: شمعة إيجابية
        if last['close'] > last['open']: score += 1
        
        # فلتر الأمان RSI
        if last['rsi'] > 82 or last['rsi'] < 20: score = 0
            
        return score
    except: return 0

# ======================== 3. المحرك التشغيلي ========================

async def stable_scan_v12():
    current_time = datetime.now()
    # تنظيف الذاكرة (6 ساعات)
    to_delete = [s for s, t in sent_signals_tracker.items() if (current_time - t).total_seconds() > 21600]
    for s in to_delete: del sent_signals_tracker[s]

    try:
        all_tickers = await EXCHANGE.fetch_tickers()
        top_100 = sorted(
            [s for s in all_tickers if '/USDT' in s and 'UP/' not in s and 'DOWN/' not in s],
            key=lambda x: all_tickers[x]['quoteVolume'] or 0, reverse=True
        )[:100]
        
        candidates = []
        for sym in top_100:
            if sym in sent_signals_tracker: continue
            
            try:
                bars = await EXCHANGE.fetch_ohlcv(sym, timeframe=TIMEFRAME, limit=50)
                df = pd.DataFrame(bars, columns=['ts','open','high','low','close','vol'])
                score = get_score(df)
                
                if score >= 3:
                    candidates.append({"sym": sym, "score": score, "price": df['close'].iloc[-1]})
                await asyncio.sleep(0.05)
            except: continue

        # جلب أفضل 10 صفقات
        top_10 = sorted(candidates, key=lambda x: x['score'], reverse=True)[:10]

        for item in top_10:
            sent_signals_tracker[item['sym']] = datetime.now()
            qty = INVESTMENT_PER_TRADE / item['price']
            msg = (f"🛡️ *إشارة مستقرة (V12.1)*\n"
                   f"⏰ الوقت: `{datetime.now().strftime('%H:%M:%S')}`\n"
                   f"💎 العملة: `{item['sym']}`\n"
                   f"📊 القوة: `{item['score']}/5`\n"
                   f"💵 المبلغ: `100$` | الكمية: `{qty:.2f}`\n"
                   f"💰 السعر: `{item['price']:.6f}`")
            send_telegram_msg(msg)

    except Exception as e: print(f"Error: {e}")

async def main_loop():
    send_telegram_msg("✅ *تم تفعيل النسخة V12.1 بنجاح (بدون إضافات)*\n📍 السيرفر: Amsterdam\n🚀 البوت يبدأ المسح الآن...")
    while True:
        try:
            await stable_scan_v12()
            await asyncio.sleep(900) 
        except: await asyncio.sleep(60)

# ======================== 4. السيرفر ========================
app = Flask('')
@app.route('/')
def home(): return "Bot is Alive"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    threading.Thread(target=lambda: serve(app, host='0.0.0.0', port=port), daemon=True).start()
    asyncio.run(main_loop())

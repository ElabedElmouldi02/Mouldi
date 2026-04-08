import asyncio
import ccxt.pro as ccxt
import pandas as pd
import pandas_ta as ta
import requests
import threading
import os
from flask import Flask
from datetime import datetime, timedelta
from waitress import serve

# ======================== 1. الإعدادات ========================
TELEGRAM_TOKEN = '8643715664:AAH-Th6cUZasbUrOJe6elCJuV_Fn6oTfd5g'
TELEGRAM_CHAT_IDS = ['5067771509', '-1003692815602'] 

INVESTMENT_PER_TRADE = 100  
TIMEFRAME = '15m'
EXCHANGE = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})

# ذاكرة لتخزين العملات المرسلة مع وقت إرسالها
sent_signals_tracker = {}

def send_telegram_msg(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for chat_id in TELEGRAM_CHAT_IDS:
        try: requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# ======================== 2. محرك الفحص والفلترة ========================
def get_score(df):
    try:
        if len(df) < 25: return 0
        df['rsi'] = ta.rsi(df['close'], length=14)
        df['ema10'] = ta.ema(df['close'], length=10)
        
        last = df.iloc[-1]
        score = 0
        
        if last['close'] > last['ema10']: score += 2
        avg_vol = df['vol'].rolling(20).mean().iloc[-2]
        if last['vol'] > avg_vol * 1.3: score += 2
        if last['close'] > df['open'].iloc[-1]: score += 1
        
        # فلتر الأمان: لا تشترِ عند تشبع جنوني
        if last['rsi'] > 82: score = 0
            
        return score
    except: return 0

async def weekly_stable_scan():
    # تنظيف الذاكرة من الإشارات التي مر عليها أكثر من 6 ساعات
    current_time = datetime.now()
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
            if sym in sent_signals_tracker: continue # تخطي إذا أُرسلت مؤخراً
            
            try:
                bars = await EXCHANGE.fetch_ohlcv(sym, timeframe=TIMEFRAME, limit=40)
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
            msg = (f"🔔 *إشارة استراتيجية (توب 10)*\n"
                   f"🗓 التاريخ: `{datetime.now().strftime('%Y-%m-%d')}`\n"
                   f"⏰ الوقت: `{datetime.now().strftime('%H:%M:%S')}`\n"
                   f"💎 العملة: `{item['sym']}`\n"
                   f"📊 القوة: `{item['score']}/5`\n"
                   f"💵 دخول بـ: `100$` | الكمية: `{qty:.2f}`\n"
                   f"💰 السعر: `{item['price']:.6f}`")
            send_telegram_msg(msg)

    except Exception as e: print(f"Error: {e}")

async def main_loop():
    send_telegram_msg("🛠 *بدء وضع التشغيل المستمر لمدة أسبوع* (V12.0)\n📍 السيرفر: Amsterdam\n⚖️ إدارة المخاطر: مفعلة")
    while True:
        try:
            await weekly_stable_scan()
            await asyncio.sleep(900) # فحص كل 15 دقيقة (أفضل للاستمرار الطويل)
        except: await asyncio.sleep(60)

# ======================== 3. الويب ========================
app = Flask('')
@app.route('/')
def home(): return "Stable Bot Running"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    threading.Thread(target=lambda: serve(app, host='0.0.0.0', port=port), daemon=True).start()
    asyncio.run(main_loop())

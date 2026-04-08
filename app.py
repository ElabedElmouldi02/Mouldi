import asyncio
import ccxt.pro as ccxt
import pandas as pd
import pandas_ta as ta
import requests
import threading
import os
from flask import Flask
from datetime import datetime
from waitress import serve

# ======================== 1. الإعدادات ========================
TELEGRAM_TOKEN = '8643715664:AAH-Th6cUZasbUrOJe6elCJuV_Fn6oTfd5g'
TELEGRAM_CHAT_IDS = ['5067771509', '-1003692815602'] 

INVESTMENT_PER_TRADE = 100  
TIMEFRAME = '15m'
EXCHANGE = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})

def send_telegram_msg(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for chat_id in TELEGRAM_CHAT_IDS:
        try: requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# ======================== 2. شروط دخول مخففة جداً ========================
def calculate_flexible_score(df):
    try:
        if len(df) < 20: return 0
        df['rsi'] = ta.rsi(df['close'], length=14)
        df['ema10'] = ta.ema(df['close'], length=10)
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        score = 0
        
        # شرط 1: السعر فوق المتوسط (سهل جداً)
        if last['close'] > last['ema10']: score += 2
        
        # شرط 2: زيادة بسيطة في السيولة (1.2 مرة فقط)
        avg_vol = df['vol'].rolling(15).mean().iloc[-2]
        if last['vol'] > avg_vol * 1.2: score += 2
        
        # شرط 3: شمعة خضراء (أي إغلاق فوق الافتتاح)
        if last['close'] > last['open']: score += 1
        
        # شرط أمان: عدم الشراء في تشبع جنوني (RSI فوق 85)
        if last['rsi'] > 85: score = 0
            
        return score
    except: return 0

# ======================== 3. المحرك الهجومي ========================
async def aggressive_top10_scan():
    now_time = datetime.now().strftime("%H:%M")
    send_telegram_msg(f"🚀 *جاري البحث عن أفضل 10 فرص حالياً...* \n⏰ `{now_time}`")
    
    try:
        all_tickers = await EXCHANGE.fetch_tickers()
        top_100 = sorted(
            [s for s in all_tickers if '/USDT' in s and 'UP/' not in s and 'DOWN/' not in s],
            key=lambda x: all_tickers[x]['quoteVolume'] or 0, reverse=True
        )[:100]
        
        scored_opportunities = []

        for sym in top_100:
            try:
                bars = await EXCHANGE.fetch_ohlcv(sym, timeframe=TIMEFRAME, limit=30)
                df = pd.DataFrame(bars, columns=['ts','open','high','low','close','vol'])
                
                score = calculate_flexible_score(df)
                
                if score >= 3: # شرط دخول سهل (تحقيق شرطين فقط يكفي)
                    price = df['close'].iloc[-1]
                    scored_opportunities.append({
                        "symbol": sym,
                        "score": score,
                        "price": price
                    })
                await asyncio.sleep(0.05) # سرعة عالية في الفحص
            except: continue

        # ترتيب النتائج لجلب أعلى 10 سكور
        top_10_results = sorted(scored_opportunities, key=lambda x: x['score'], reverse=True)[:10]

        if not top_10_results:
            send_telegram_msg("ℹ️ لم يتم العثور على أي حركة إيجابية حالياً.")
            return

        for item in top_10_results:
            qty = INVESTMENT_PER_TRADE / item['price']
            msg = (f"🔥 *فرصة (توب 10): {item['symbol']}* \n"
                   f"📊 السكور: `{item['score']}/5` \n"
                   f"💵 ادخل بـ: `100 USDT` \n"
                   f"🛒 الكمية: `{qty:.2f}` \n"
                   f"💰 السعر: `{item['price']:.6f}`")
            send_telegram_msg(msg)
            await asyncio.sleep(1) # فاصل بسيط لإرسال التنبيهات

    except Exception as e:
        print(f"Error: {e}")

async def main_loop():
    send_telegram_msg("⚔️ *تم تفعيل نظام الهجوم V11.6* \n✅ سأقوم بجلب أفضل 10 صفقات في كل مسحة.")
    while True:
        try:
            await aggressive_top10_scan()
            await asyncio.sleep(600) # فحص كل 10 دقائق
        except: await asyncio.sleep(60)

# ======================== 4. تشغيل السيرفر ========================
app = Flask('')
@app.route('/')
def home(): return "Attack Mode Active"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    threading.Thread(target=lambda: serve(app, host='0.0.0.0', port=port), daemon=True).start()
    asyncio.run(main_loop())

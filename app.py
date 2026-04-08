import asyncio
import ccxt.pro as ccxt
import pandas as pd
import requests
import threading
from flask import Flask
from datetime import datetime
from waitress import serve

# ======================== 1. الإعدادات ========================
TELEGRAM_TOKEN = '8643715664:AAH-Th6cUZasbUrOJe6elCJuV_Fn6oTfd5g'
TELEGRAM_CHAT_IDS = ['5067771509', '-1003692815602'] 

TIMEFRAME = '15m'
# تفعيل Rate Limit في المكتبة نفسها
EXCHANGE = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})
monitored_coins = {}

# ======================== 2. نظام الإشعارات ========================
def send_telegram_msg(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for chat_id in TELEGRAM_CHAT_IDS:
        try:
            requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# ======================== 3. المحرك الفني ========================
def calculate_score(df):
    try:
        if len(df) < 100: return 0
        close = df['close']
        last = df.iloc[-1]
        score = 0
        
        ema50 = close.ewm(span=50).mean().iloc[-1]
        if last['close'] > ema50: score += 1
        
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9)))).iloc[-1]
        if 40 < rsi < 70: score += 1
        
        avg_vol = df['vol'].rolling(20).mean().iloc[-2]
        if last['vol'] > avg_vol * 1.3: score += 1 
        
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        bw = ((4 * std20) / sma20).iloc[-1]
        if bw < 0.06: score += 2 
        
        return score
    except: return 0

# ======================== 4. المسح الآمن (Safe Scan) ========================
async def scan_and_capture():
    try:
        start_time = datetime.now()
        send_telegram_msg("🔄 *بدء المسح الآمن (1000 عملة)...*")
        
        markets = await EXCHANGE.fetch_tickers()
        # فلتر إضافي: استبعاد العملات ذات السيولة الضعيفة جداً (أقل من 1 مليون USDT) لتوفير الطلبات
        symbols = [s for s in markets.keys() if '/USDT' in s and 'UP/' not in s and 'DOWN/' not in s]
        active_symbols = [s for s in symbols if markets[s]['quoteVolume'] > 1000000][:1000]
        
        all_candidates = []
        count = 0
        
        # تقسيم العملات لمجموعات (كل مجموعة 20 عملة)
        for i in range(0, len(active_symbols), 20):
            batch = active_symbols[i:i+20]
            for sym in batch:
                try:
                    bars = await EXCHANGE.fetch_ohlcv(sym, timeframe=TIMEFRAME, limit=105)
                    df = pd.DataFrame(bars, columns=['ts','open','high','low','close','vol'])
                    score = calculate_score(df)
                    if score > 0:
                        all_candidates.append({"sym": sym, "score": score, "price": df['close'].iloc[-1]})
                    count += 1
                    # زيادة وقت الانتظار بين كل طلب (0.05 ثانية)
                    await asyncio.sleep(0.05) 
                except Exception as e:
                    if "429" in str(e): # إذا حدث حظر حقيقي
                        send_telegram_msg("⚠️ تم رصد حظر مؤقت (429). سأنتظر دقيقتين...")
                        await asyncio.sleep(120)
                    continue
            
            # راحة بين كل مجموعة وأخرى (نصف ثانية)
            await asyncio.sleep(0.5)

        duration = (datetime.now() - start_time).seconds
        
        if all_candidates:
            best_pick = max(all_candidates, key=lambda x: x['score'])
            sym = best_pick['sym']
            if sym not in monitored_coins:
                monitored_coins[sym] = {
                    "entry_p": best_pick['price'], "time": datetime.now(),
                    "max_p": best_pick['price'], "min_p": best_pick['price'],
                    "score": best_pick['score']
                }
            
            report = (f"✅ *اكتمل المسح الآمن ({count} عملة)*\n"
                      f"⏱ الزمن: `{duration}` ثانية\n\n"
                      f"🎯 *الأفضل:* `{sym}` | السكور: `{best_pick['score']}`")
        else:
            report = f"✅ *تم المسح!* لم تتوفر شروط في {count} عملة حالياً."
        
        send_telegram_msg(report)
                
    except Exception as e:
        send_telegram_msg(f"❌ خطأ تقني: `{str(e)[:100]}`")

# ======================== 5. النظام والتشغيل ========================
async def main_loop():
    send_telegram_msg("🚀 *تفعيل رادار V8.8 الآمن*")
    while True:
        try:
            await scan_and_capture()
            # انتظار 10 دقائق بين دورات المسح
            await asyncio.sleep(600) 
        except Exception as e:
            await asyncio.sleep(60)

app = Flask('')
@app.route('/')
def home(): return f"Safety System Active. Tracking {len(monitored_coins)}."

if __name__ == "__main__":
    threading.Thread(target=lambda: serve(app, host='0.0.0.0', port=8080), daemon=True).start()
    asyncio.run(main_loop())

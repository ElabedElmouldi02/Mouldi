import asyncio
import ccxt.pro as ccxt
import pandas as pd
import requests
import threading
import os
from flask import Flask
from datetime import datetime
from waitress import serve

# ======================== 1. الإعدادات الأساسية ========================
TELEGRAM_TOKEN = '8643715664:AAH-Th6cUZasbUrOJe6elCJuV_Fn6oTfd5g'
TELEGRAM_CHAT_IDS = ['5067771509', '-1003692815602'] 

TIMEFRAME = '15m'
EXCHANGE = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'},
    'headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
    }
})

active_virtual_trades = {}

# ======================== 2. وظائف التواصل ========================
def send_telegram_msg(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for chat_id in TELEGRAM_CHAT_IDS:
        try: 
            requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        except: 
            pass

# ======================== 3. منطق الجودة (خوارزمية الانفجار) ========================
def check_explosion_quality(df):
    try:
        if len(df) < 50: return 0
        close = df['close']
        score = 0
        
        # 1. الاتجاه: السعر فوق المتوسط المتحرك 50
        ema50 = close.ewm(span=50).mean().iloc[-1]
        if close.iloc[-1] > ema50: score += 1
        
        # 2. الحجم: انفجار السيولة (أكثر من ضعف المتوسط)
        avg_vol = df['vol'].rolling(20).mean().iloc[-2]
        if df['vol'].iloc[-1] > avg_vol * 2.0: 
            score += 2
        
        # 3. الشكل: شمعة شرائية قوية (جسم الشمعة يمثل 60% من طولها)
        body = abs(df['close'].iloc[-1] - df['open'].iloc[-1])
        full_range = df['high'].iloc[-1] - df['low'].iloc[-1]
        if full_range > 0 and (body / full_range) > 0.6:
            score += 1

        return score
    except:
        return 0

# ======================== 4. المحرك التشغيلي (المسح التفاعلي) ========================
async def ultra_stable_scan():
    try:
        # رسالة نبض: البوت بدأ العمل الآن
        send_telegram_msg("🔍 *بدء مسح السوق الآن (V10.7)...*")
        
        all_tickers = await EXCHANGE.fetch_tickers()
        potential_symbols = [
            s for s, t in all_tickers.items() 
            if '/USDT' in s and 'UP/' not in s and 'DOWN/' not in s 
        ]
        
        # اختيار أفضل 30 عملة من حيث حجم التداول
        top_active = sorted(potential_symbols, key=lambda x: all_tickers[x]['quoteVolume'] or 0, reverse=True)[:30]
        
        found_any = False
        for sym in top_active:
            if sym in active_virtual_trades: continue
            
            try:
                bars = await EXCHANGE.fetch_ohlcv(sym, timeframe=TIMEFRAME, limit=60)
                df = pd.DataFrame(bars, columns=['ts','open','high','low','close','vol'])
                
                score = check_explosion_quality(df)
                if score >= 3:
                    found_any = True
                    active_virtual_trades[sym] = {
                        "entry_price": df['close'].iloc[-1], 
                        "time": datetime.now().strftime("%H:%M")
                    }
                    send_telegram_msg(f"🎯 *رصد انفجار: {sym}*\n📊 السكور: `{score}/4`\n💰 السعر: `{df['close'].iloc[-1]:.6f}`")
                
                await asyncio.sleep(1.2) # تأخير لمنع الحظر
            except:
                continue

        if not found_any:
            send_telegram_msg("ℹ️ *انتهى المسح:* لم يتم العثور على فرص مطابقة للمعايير حالياً.")

        await monitor_trades()

    except Exception as e:
        if "451" in str(e) or "403" in str(e):
            send_telegram_msg("🚨 *خطأ جغرافي:* السيرفر موجود في منطقة محظورة (أمريكا). يرجى نقله لأوروبا.")
        else:
            send_telegram_msg(f"⚠️ *خطأ تقني:* `{str(e)[:50]}`")

async def monitor_trades():
    if not active_virtual_trades: return
    report = "📋 *متابعة الصفقات النشطة:*\n"
    for sym, data in list(active_virtual_trades.items()):
        try:
            ticker = await EXCHANGE.fetch_ticker(sym)
            pnl = ((ticker['last'] - data['entry_price']) / data['entry_price']) * 100
            report += f"`{sym}`: {pnl:.2f}% {'🍏' if pnl>=0 else '🍎'}\n"
        except: continue
    send_telegram_msg(report)

# ======================== 5. حلقة التشغيل والربط ========================
async def main_loop():
    send_telegram_msg("🛡️ *تم تفعيل الرادار V10.7 بنجاح*")
    while True:
        try:
            await ultra_stable_scan()
            # المسح كل 15 دقيقة (900 ثانية)
            await asyncio.sleep(900) 
        except: 
            await asyncio.sleep(60)

app = Flask('')
@app.route('/')
def home(): return "Bot Status: Online and Scanning."

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    threading.Thread(target=lambda: serve(app, host='0.0.0.0', port=port), daemon=True).start()
    asyncio.run(main_loop())

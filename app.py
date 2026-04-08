
import asyncio
import ccxt.pro as ccxt
import pandas as pd
import requests
import threading
import os
from flask import Flask
from datetime import datetime
from waitress import serve

# ======================== 1. الإعدادات ========================
TELEGRAM_TOKEN = '8643715664:AAH-Th6cUZasbUrOJe6elCJuV_Fn6oTfd5g'
TELEGRAM_CHAT_IDS = ['5067771509', '-1003692815602'] 

TIMEFRAME = '15m'
EXCHANGE = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'},
    'headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
})

active_virtual_trades = {}

# ======================== 2. محرك الجودة (Quality Engine) ========================
def send_telegram_msg(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for chat_id in TELEGRAM_CHAT_IDS:
        try: requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        except: pass

def is_exploding(df):
    """معادلة الجودة: تكتشف الانفجار الحقيقي بناءً على السعر والحجم"""
    try:
        if len(df) < 50: return 0
        close = df['close']
        vol = df['vol']
        
        score = 0
        # 1. اختراق المتوسط المتحرك 50 بقوة
        ema50 = close.ewm(span=50).mean().iloc[-1]
        if close.iloc[-1] > ema50 * 1.005: score += 1
        
        # 2. انفجار الحجم (يجب أن يكون الحجم الحالي ضعف متوسط آخر 20 شمعة)
        avg_vol = vol.rolling(20).mean().iloc[-2]
        if vol.iloc[-1] > avg_vol * 2.2: score += 2
        
        # 3. شرط الشمعة الممتلئة (البقاء بعيداً عن الذيول الطويلة)
        body_size = abs(df['close'].iloc[-1] - df['open'].iloc[-1])
        candle_range = df['high'].iloc[-1] - df['low'].iloc[-1]
        if body_size > (candle_range * 0.6): score += 1 # جودة الشمعة

        return score
    except: return 0

# ======================== 3. المسح الذكي المنخفض الضغط ========================
async def smart_quality_scan():
    try:
        send_telegram_msg("🎯 *بدء صيد الفرص النوعية (V10.0)...*")
        
        # الخطوة 1: جلب ملخص السوق لفلترة العملات النشطة فقط (توفير جهد كبير)
        tickers = await EXCHANGE.fetch_tickers()
        # نختار فقط العملات التي حققت ارتفاعاً ولو بسيطاً أو حجماً محترماً
        potential_symbols = [
            s for s, t in tickers.items() 
            if '/USDT' in s and 'UP/' not in s and 'DOWN/' not in s 
            and t['percentage'] > 0.5  # فقط العملات التي بدأت تتحرك فعلاً
        ]
        
        # نركز على أفضل 50 عملة "نشطة حالياً" بدلاً من مسح كل شيء
        top_active = sorted(potential_symbols, key=lambda x: tickers[x]['quoteVolume'] or 0, reverse=True)[:50]
        
        candidates = []
        for sym in top_active:
            if sym in active_virtual_trades: continue
            
            try:
                # طلب بيانات الشموع
                bars = await EXCHANGE.fetch_ohlcv(sym, timeframe=TIMEFRAME, limit=60)
                df = pd.DataFrame(bars, columns=['ts','open','high','low','close','vol'])
                
                score = is_exploding(df)
                if score >= 3:
                    candidates.append({"sym": sym, "price": df['close'].iloc[-1], "score": score})
                
                # تأخير طويل نسبياً لراحة السيرفر وضمان الاستمرارية
                await asyncio.sleep(0.8) 
            except Exception as e:
                if "429" in str(e): 
                    await asyncio.sleep(30) # تبريد إجباري لمدة نصف دقيقة
                continue

        if candidates:
            # اختيار الأقوى فقط
            best = max(candidates, key=lambda x: x['score'])
            active_virtual_trades[best['sym']] = {"entry_price": best['price'], "time": datetime.now().strftime("%H:%M")}
            send_telegram_msg(f"🔥 *تم رصد انفجار محتمل: {best['sym']}*\n📊 قوة الإشارة: `{best['score']}/4`\n💰 السعر الحالي: `{best['price']:.6f}`")

        await update_performance()

    except Exception as e:
        send_telegram_msg(f"💤 *السيرفر في وضع التبريد:* سأعود للعمل تلقائياً بعد قليل.")

async def update_performance():
    if not active_virtual_trades: return
    report = "📋 *متابعة الصفقات النشطة:*\n"
    for sym, data in list(active_virtual_trades.items()):
        try:
            t = await EXCHANGE.fetch_ticker(sym)
            pnl = ((t['last'] - data['entry_price']) / data['entry_price']) * 100
            report += f"`{sym}`: {pnl:.2f}% {'✅' if pnl>=0 else '❌'}\n"
        except: continue
    send_telegram_msg(report)

# ======================== 4. التشغيل الدائم ========================
async def main_loop():
    send_telegram_msg("🛡️ *نظام الاستمرارية القصوى يعمل*\nتم تفعيل فلاتر الجودة وتخفيف الضغط.")
    while True:
        try:
            await smart_quality_scan()
            # المسح كل 20 دقيقة (كافٍ جداً لفريم 15 دقيقة)
            await asyncio.sleep(1200) 
        except: await asyncio.sleep(60)

app = Flask('')
@app.route('/')
def home(): return "Quality Bot Active."

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    threading.Thread(target=lambda: serve(app, host='0.0.0.0', port=port), daemon=True).start()
    asyncio.run(main_loop())

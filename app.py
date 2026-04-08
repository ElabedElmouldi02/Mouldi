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
# إعداد المحرك مع تقليل الطلبات وتفعيل ميزة كشف الحظر
EXCHANGE = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'},
    'headers': {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'
    }
})

active_virtual_trades = {} 

# ======================== 2. الوظائف المساعدة ========================
def send_telegram_msg(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for chat_id in TELEGRAM_CHAT_IDS:
        try:
            requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        except: pass

def calculate_score(df):
    try:
        if len(df) < 50: return 0
        close = df['close']
        score = 0
        # اتجاه السعر (فوق المتوسط المتحرك 50)
        ema = close.ewm(span=50).mean().iloc[-1]
        if close.iloc[-1] > ema: score += 1
        # انفجار حجم التداول (Volume Spike)
        avg_vol = df['vol'].rolling(20).mean().iloc[-2]
        if df['vol'].iloc[-1] > avg_vol * 1.8: score += 2 # رفعنا المعيار لضمان القوة
        return score
    except: return 0

# ======================== 3. المحرك المخفف (Low Pressure Scan) ========================
async def scan_markets_safe():
    try:
        send_telegram_msg("⚡ *بدء المسح الآمن (ضغط منخفض)...*")
        
        # جلب الأسعار بشكل سريع لفلترة السيولة
        tickers = await EXCHANGE.fetch_tickers()
        symbols = [s for s in tickers.keys() if '/USDT' in s and 'UP/' not in s and 'DOWN/' not in s]
        
        # نكتفي بأفضل 80 عملة سيولة لضمان عدم الحظر
        top_80 = sorted(symbols, key=lambda x: tickers[x]['quoteVolume'] or 0, reverse=True)[:80]
        
        candidates = []
        for sym in top_80:
            if sym in active_virtual_trades: continue
            
            try:
                # نطلب 60 شمعة فقط بدلاً من 100 لتخفيف حجم البيانات
                bars = await EXCHANGE.fetch_ohlcv(sym, timeframe=TIMEFRAME, limit=60)
                df = pd.DataFrame(bars, columns=['ts','open','high','low','close','vol'])
                
                score = calculate_score(df)
                if score >= 3:
                    candidates.append({"sym": sym, "price": df['close'].iloc[-1], "score": score})
                
                # وقت انتظار أطول (0.5 ثانية) بين كل عملة لراحة السيرفر
                await asyncio.sleep(0.5) 
            except Exception as e:
                if "429" in str(e): # إذا اكتشفنا ضغطاً زائداً
                    await asyncio.sleep(10) # توقف تماماً لمدة 10 ثوانٍ
                continue

        if candidates:
            best = max(candidates, key=lambda x: x['score'])
            active_virtual_trades[best['sym']] = {"entry_price": best['price'], "time": datetime.now().strftime("%H:%M")}
            send_telegram_msg(f"🌟 *فرصة ذهبية: {best['sym']}*\n💰 السعر: `{best['price']:.6f}`\n📊 السكور: `{best['score']}`")

        # تقرير مختصر للأداء
        await report_portfolio_summary()

    except Exception as e:
        send_telegram_msg(f"⚠️ تنبيه: السيرفر يحتاج للراحة. سأحاول مجدداً لاحقاً.\n`{str(e)[:40]}`")

async def report_portfolio_summary():
    if not active_virtual_trades: return
    report = "📊 *مراقبة الصفقات المفتوحة:*\n"
    for sym, data in list(active_virtual_trades.items()):
        try:
            t = await EXCHANGE.fetch_ticker(sym)
            pnl = ((t['last'] - data['entry_price']) / data['entry_price']) * 100
            report += f"`{sym}`: {pnl:.2f}% {'🟢' if pnl>=0 else '🔴'}\n"
        except: continue
    send_telegram_msg(report)

# ======================== 4. حلقة التشغيل والربط ========================
async def main_loop():
    send_telegram_msg("🚀 *الرادار V9.6 قيد العمل*\nنظام: الضغط المنخفض (Safe Mode)")
    while True:
        try:
            await scan_markets_safe()
            # فحص كل 20 دقيقة بدلاً من 15 لتقليل استهلاك الموارد السحابية
            await asyncio.sleep(1200) 
        except:
            await asyncio.sleep(60)

app = Flask('')
@app.route('/')
def home(): return "Stabilized Bot Running."

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    threading.Thread(target=lambda: serve(app, host='0.0.0.0', port=port), daemon=True).start()
    asyncio.run(main_loop())

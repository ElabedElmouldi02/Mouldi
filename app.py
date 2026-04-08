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
# ملاحظة: تأكد من صحة التوكن والـ ID
TELEGRAM_TOKEN = '8643715664:AAH-Th6cUZasbUrOJe6elCJuV_Fn6oTfd5g'
TELEGRAM_CHAT_IDS = ['5067771509', '-1003692815602'] 

TRADE_AMOUNT_VIRTUAL = 50.0  
TIMEFRAME = '15m'

# إعداد المحرك مع تقنية التمويه (Headers) لتجنب الحظر
EXCHANGE = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'},
    'headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
})

# محفظة الصفقات الافتراضية
active_virtual_trades = {} 

# ======================== 2. نظام الإشعارات ========================
def send_telegram_msg(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for chat_id in TELEGRAM_CHAT_IDS:
        try:
            requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        except Exception as e:
            print(f"Telegram Error: {e}")

# ======================== 3. منطق الحسابات الذكي ========================
def calculate_score(df):
    try:
        if len(df) < 100: return 0
        close = df['close']
        score = 0
        
        # مؤشر EMA 50
        ema50 = close.ewm(span=50).mean().iloc[-1]
        if close.iloc[-1] > ema50: score += 1
        
        # مؤشر حجم التداول (Volume Spike)
        avg_vol = df['vol'].rolling(20).mean().iloc[-2]
        if df['vol'].iloc[-1] > avg_vol * 1.5: 
            score += 2
            
        return score
    except:
        return 0

# ======================== 4. المراقبة والمسح ========================
async def report_portfolio():
    if not active_virtual_trades: return
    
    report = "📈 *تقرير أداء المحفظة الافتراضية:*\n"
    for sym, data in active_virtual_trades.items():
        try:
            ticker = await EXCHANGE.fetch_ticker(sym)
            curr_p = ticker['last']
            pnl = ((curr_p - data['entry_price']) / data['entry_price']) * 100
            icon = "🍏" if pnl >= 0 else "🍎"
            report += f"{icon} `{sym}`: {pnl:.2f}% | دخول: `{data['entry_price']:.4f}`\n"
        except: continue
    send_telegram_msg(report)

async def scan_markets():
    try:
        send_telegram_msg("🔍 *بدء دورة مسح جديدة على Railway...*")
        markets = await EXCHANGE.fetch_tickers()
        # فحص أعلى 200 عملة سيولة لتجنب الضغط على الـ API
        symbols = [s for s in markets.keys() if '/USDT' in s and 'UP/' not in s and 'DOWN/' not in s]
        top_symbols = sorted(symbols, key=lambda x: markets[x]['quoteVolume'] or 0, reverse=True)[:200]
        
        candidates = []
        for sym in top_symbols:
            if sym in active_virtual_trades: continue
            try:
                bars = await EXCHANGE.fetch_ohlcv(sym, timeframe=TIMEFRAME, limit=105)
                df = pd.DataFrame(bars, columns=['ts','open','high','low','close','vol'])
                score = calculate_score(df)
                if score >= 3:
                    candidates.append({"sym": sym, "price": df['close'].iloc[-1], "score": score})
                await asyncio.sleep(0.02) # تأخير بسيط لتجنب الحظر
            except: continue

        if candidates:
            best = max(candidates, key=lambda x: x['score'])
            active_virtual_trades[best['sym']] = {
                "entry_price": best['price'],
                "score": best['score']
            }
            send_telegram_msg(f"🚀 *صفقة افتراضية جديدة*\n🪙 العملة: `{best['sym']}`\n📊 السكور: `{best['score']}`\n💰 السعر: `{best['price']:.6f}`")
        
        await report_portfolio()
    except Exception as e:
        send_telegram_msg(f"⚠️ خطأ أثناء المسح: `{str(e)[:100]}`")

# ======================== 5. التشغيل المستمر ========================
async def main_loop():
    send_telegram_msg("✅ *تم تفعيل الرادار V9.4 على Railway*\nالوضع: تداول افتراضي + منع تكرار")
    while True:
        try:
            await scan_markets()
            await asyncio.sleep(900) # فحص كل 15 دقيقة
        except:
            await asyncio.sleep(60)

# إعداد سيرفر Flask للبقاء مستيقظاً
app = Flask('')
@app.route('/')
def home():
    return f"Bot is running. Active trades: {len(active_virtual_trades)}"

if __name__ == "__main__":
    # قراءة المنفذ من Railway تلقائياً
    port = int(os.environ.get("PORT", 8080))
    # تشغيل السيرفر في الخلفية
    threading.Thread(target=lambda: serve(app, host='0.0.0.0', port=port), daemon=True).start()
    # تشغيل حلقة البوت الأساسية
    asyncio.run(main_loop())

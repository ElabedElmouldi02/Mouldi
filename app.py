import asyncio
import ccxt.pro as ccxt
import pandas as pd
import pandas_ta as ta  # تأكد من إضافة هذه المكتبة في التحليل
import requests
import threading
import os
from flask import Flask
from datetime import datetime
from waitress import serve

# ======================== 1. الإعدادات والتمويل ========================
TELEGRAM_TOKEN = '8643715664:AAH-Th6cUZasbUrOJe6elCJuV_Fn6oTfd5g'
TELEGRAM_CHAT_IDS = ['5067771509', '-1003692815602'] 

INVESTMENT_PER_TRADE = 100  
TIMEFRAME = '15m'
EXCHANGE = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
active_signals = {}

def send_telegram_msg(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for chat_id in TELEGRAM_CHAT_IDS:
        try: requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        except: pass

# ======================== 2. فلاتر الأمان الاحترافية ========================

async def is_market_safe():
    """فحص حالة البيتكوين قبل إرسال أي صفقة"""
    try:
        btc_bars = await EXCHANGE.fetch_ohlcv('BTC/USDT', timeframe='15m', limit=5)
        last_close = btc_bars[-1][4]
        prev_close = btc_bars[-2][4]
        # إذا هبط البيتكوين أكثر من 1% في آخر 15 دقيقة، السوق غير آمن
        change = ((last_close - prev_close) / prev_close) * 100
        return change > -1.0
    except: return True

def get_indicators(df):
    """حساب RSI و المتوسطات"""
    df['rsi'] = ta.rsi(df['close'], length=14)
    df['ema20'] = ta.ema(df['close'], length=20)
    return df

# ======================== 3. المحرك التشغيلي المطور ========================
async def professional_scan():
    now_time = datetime.now().strftime("%H:%M")
    
    # 1. فحص أمان السوق أولاً
    if not await is_market_safe():
        print("⚠️ هبوط حاد في البيتكوين - تعليق الصفقات مؤقتاً.")
        return

    send_telegram_msg(f"🕵️ *رادار V11.5 يفحص الـ 100 عملة...* \n⏰ `{now_time}`")
    
    try:
        all_tickers = await EXCHANGE.fetch_tickers()
        top_100 = sorted(
            [s for s in all_tickers if '/USDT' in s and 'UP/' not in s and 'DOWN/' not in s],
            key=lambda x: all_tickers[x]['quoteVolume'] or 0, reverse=True
        )[:100]
        
        for sym in top_100:
            if sym in active_signals and (datetime.now() - active_signals[sym]).seconds > 3600:
                del active_signals[sym]
            if sym in active_signals: continue
            
            try:
                bars = await EXCHANGE.fetch_ohlcv(sym, timeframe=TIMEFRAME, limit=50)
                df = pd.DataFrame(bars, columns=['ts','open','high','low','close','vol'])
                df = get_indicators(df)
                
                last_price = df['close'].iloc[-1]
                last_rsi = df['rsi'].iloc[-1]
                avg_vol = df['vol'].rolling(20).mean().iloc[-2]
                
                # --- شروط الدخول الاحترافية ---
                score = 0
                if last_price > df['ema20'].iloc[-1]: score += 1      # اتجاه صاعد
                if df['vol'].iloc[-1] > avg_vol * 1.3: score += 1      # انفجار سيولة
                
                # التحقق من فلتر الـ RSI (لا تشتري عملة متضخمة)
                if score >= 2 and last_rsi < 80:
                    active_signals[sym] = datetime.now()
                    qty = INVESTMENT_PER_TRADE / last_price
                    
                    msg = (f"🎯 *فرصة دخول ذكية* \n"
                           f"💎 العملة: `{sym}` \n"
                           f"📈 RSI: `{last_rsi:.1f}` (آمن) \n"
                           f"💵 ادخل بـ: `100 USDT` \n"
                           f"🛒 الكمية: `{qty:.2f}` \n"
                           f"💰 السعر: `{last_price:.6f}` \n"
                           f"🛑 الوقف: `-2.5%` | 🎯 الهدف: `+4%` ")
                    send_telegram_msg(msg)
                
                await asyncio.sleep(0.1)
            except: continue

    except Exception as e:
        print(f"Error: {e}")

async def main_loop():
    send_telegram_msg("🛡️ *تم تفعيل نظام الحماية V11.5* \n✅ تم دمج فلتر RSI ورادار البيتكوين.")
    while True:
        try:
            await professional_scan()
            await asyncio.sleep(600) 
        except: await asyncio.sleep(60)

# ======================== 4. تشغيل السيرفر ========================
app = Flask('')
@app.route('/')
def home(): return "Pro Bot Active"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    threading.Thread(target=lambda: serve(app, host='0.0.0.0', port=port), daemon=True).start()
    asyncio.run(main_loop())

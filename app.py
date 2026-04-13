import asyncio
import ccxt.pro as ccxt
import pandas as pd
import requests
import threading
import os
from datetime import datetime, timedelta
from flask import Flask
from waitress import serve

# ======================== 1. الإعدادات ========================
TELEGRAM_TOKEN = '8643715664:AAH-Th6cUZasbUrOJe6elCJuV_Fn6oTfd5g'
TELEGRAM_CHAT_IDS = ['5067771509', '-1003692815602']

# إعدادات المحفظة الافتراضية
TOTAL_BALANCE = 1000.0
INVESTMENT_PER_TRADE = 50.0
MAX_OPEN_TRADES = 20
TIMEFRAME = '15m'
EXCHANGE = ccxt.binance({'enableRateLimit': True})

# إعدادات التتبع السعري (Trailing Stop)
TRAILING_ACTIVATION_PCT = 0.03  # يبدأ عند ربح 3%
TRAILING_CALLBACK_PCT = 0.02    # يبيع إذا نزل 2% من القمة

# مخازن البيانات
active_trades = {}  # الصفقات المفتوحة حالياً
trade_history = []  # تاريخ الصفقات المغلقة
sent_signals_tracker = {}
last_report_time = datetime.now()

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
        if last['close'] > last['ema10']: score += 2
        avg_vol = df['vol'].rolling(20).mean().iloc[-2]
        if last['vol'] > avg_vol * 1.5: score += 2
        if last['close'] > last['open']: score += 1
        if last['rsi'] > 80 or last['rsi'] < 25: score = 0
        return score
    except: return 0

# ======================== 3. منطق التداول الافتراضي ========================

async def manage_active_trades():
    """تحديث الصفقات المفتوحة ومتابعة التتبع السعري"""
    global TOTAL_BALANCE
    symbols = list(active_trades.keys())
    if not symbols: return

    try:
        tickers = await EXCHANGE.fetch_tickers(symbols)
        for sym in symbols:
            current_price = tickers[sym]['last']
            trade = active_trades[sym]
            
            # حساب الربح الحالي
            profit_pct = (current_price - trade['entry_price']) / trade['entry_price']
            
            # تحديث أعلى سعر وصل له (للتتبع السعري)
            if current_price > trade['highest_price']:
                active_trades[sym]['highest_price'] = current_price
            
            # منطق الخروج
            exit_reason = None
            
            # 1. التتبع السعري (Trailing Stop)
            if profit_pct >= TRAILING_ACTIVATION_PCT:
                activation_price = trade['entry_price'] * (1 + TRAILING_ACTIVATION_PCT)
                drop_from_peak = (trade['highest_price'] - current_price) / trade['highest_price']
                if drop_from_peak >= TRAILING_CALLBACK_PCT:
                    exit_reason = "Trailing Stop 📉"

            # 2. وقف خسارة ثابت (لحماية المحفظة)
            if profit_pct <= -0.05: # وقف خسارة طوارئ 5%
                exit_reason = "Emergency Stop Loss 🛑"

            if exit_reason:
                profit_usd = (current_price - trade['entry_price']) * trade['quantity']
                TOTAL_BALANCE += (INVESTMENT_PER_TRADE + profit_usd)
                
                msg = (f"✅ *إغلاق صفقة ({exit_reason})*\n"
                       f"🪙 العملة: `{sym}`\n"
                       f"💰 سعر الخروج: `{current_price}`\n"
                       f"💵 الربح/الخسارة: `{profit_usd:.2f}$ ({profit_pct*100:.2f}%)`\n"
                       f"🏦 الرصيد الحالي: `{TOTAL_BALANCE:.2f}$`")
                send_telegram_msg(msg)
                
                trade['exit_price'] = current_price
                trade['exit_time'] = datetime.now()
                trade['profit_final'] = profit_usd
                trade_history.append(trade)
                del active_trades[sym]

    except Exception as e:
        print(f"Update Error: {e}")

async def send_periodic_report():
    """إرسال تقرير كل ساعتين"""
    global last_report_time
    if datetime.now() - last_report_time >= timedelta(hours=2):
        open_msg = "\n".join([f"- {s}: {((v['highest_price']/v['entry_price']-1)*100):.2f}%" for s, v in active_trades.items()])
        report = (f"📊 *تقرير التداول الدوري (ساعتين)*\n"
                  f"💰 الرصيد المتوفر: `{TOTAL_BALANCE:.2f}$`\n"
                  f"active صفقات مفتوحة: `{len(active_trades)}`\n"
                  f"✅ صفقات منتهية: `{len(trade_history)}`\n\n"
                  f"*الصفقات الحالية:* \n{open_msg if open_msg else 'لا يوجد'}")
        send_telegram_msg(report)
        last_report_time = datetime.now()

# ======================== 4. المحرك الرئيسي ========================

async def main_loop():
    send_telegram_msg("🚀 *بدء بوت التداول الافتراضي (نسخة 5/5)*\n💰 المحفظة: `1000$`\n📈 التتبع السعري مفعل.")
    
    while True:
        try:
            # 1. تحديث الصفقات الحالية أولاً
            await manage_active_trades()
            
            # 2. إرسال التقرير الدوري
            await send_periodic_report()

            # 3. البحث عن فرص جديدة إذا توفرت سيولة ومكان
            if len(active_trades) < MAX_OPEN_TRADES and TOTAL_BALANCE >= INVESTMENT_PER_TRADE:
                all_tickers = await EXCHANGE.fetch_tickers()
                top_100 = sorted(
                    [s for s in all_tickers if '/USDT' in s and 'UP/' not in s and 'DOWN/' not in s],
                    key=lambda x: all_tickers[x]['quoteVolume'] or 0, reverse=True
                )[:100]

                for sym in top_100:
                    if sym in active_trades or sym in sent_signals_tracker: continue
                    if len(active_trades) >= MAX_OPEN_TRADES: break

                    bars = await EXCHANGE.fetch_ohlcv(sym, timeframe=TIMEFRAME, limit=50)
                    df = pd.DataFrame(bars, columns=['ts','open','high','low','close','vol'])
                    score = get_score(df)

                    if score == 5:
                        price = df['close'].iloc[-1]
                        qty = INVESTMENT_PER_TRADE / price
                        
                        # تنفيذ صفقة افتراضية
                        active_trades[sym] = {
                            'entry_price': price,
                            'highest_price': price,
                            'quantity': qty,
                            'entry_time': datetime.now()
                        }
                        global TOTAL_BALANCE
                        TOTAL_BALANCE -= INVESTMENT_PER_TRADE
                        
                        send_telegram_msg(f"🔔 *فتح صفقة جديدة (5/5)*\n🪙 العملة: `{sym}`\n💵 الدخول: `{price}`\n📦 الكمية: `{qty:.2f}`")
                        sent_signals_tracker[sym] = datetime.now()
                    
                    await asyncio.sleep(0.1)

            await asyncio.sleep(30) # فحص التحديثات كل 30 ثانية
        except Exception as e:
            print(f"Main Loop Error: {e}")
            await asyncio.sleep(60)

# ======================== 5. السيرفر ========================
app = Flask('')
@app.route('/')
def home(): return f"Bot Running. Balance: {TOTAL_BALANCE}$, Active: {len(active_trades)}"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    threading.Thread(target=lambda: serve(app, host='0.0.0.0', port=port), daemon=True).start()
    asyncio.run(main_loop())

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
# إعداد المحرك بنمط "الاستهلاك المنخفض" لتجنب حظر الـ IP
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

# ======================== 3. منطق الجودة (القنص الذكي) ========================
def check_explosion_quality(df):
    """خوارزمية تصفية العملات: تركز على السيولة، الاتجاه، وقوة الشمعة"""
    try:
        if len(df) < 50: return 0
        close = df['close']
        score = 0
        
        # 1. السعر فوق المتوسط المتحرك 50 (اتجاه صاعد)
        ema50 = close.ewm(span=50).mean().iloc[-1]
        if close.iloc[-1] > ema50: score += 1
        
        # 2. انفجار حجم التداول (Volume Spike) - معيار صارم للجودة
        avg_vol = df['vol'].rolling(20).mean().iloc[-2]
        current_vol = df['vol'].iloc[-1]
        if current_vol > avg_vol * 2.5: # يجب أن يكون الحجم أكثر من ضعفين ونصف
            score += 2
        
        # 3. قوة جسم الشمعة (تجنب الذيول الطويلة التي تعني انعكاس السعر)
        candle_high = df['high'].iloc[-1]
        candle_low = df['low'].iloc[-1]
        candle_close = df['close'].iloc[-1]
        candle_open = df['open'].iloc[-1]
        
        body_size = abs(candle_close - candle_open)
        total_range = candle_high - candle_low
        if total_range > 0 and (body_size / total_range) > 0.6:
            score += 1

        return score
    except:
        return 0

# ======================== 4. المحرك التشغيلي (Ultra-Stable Scan) ========================
async def ultra_stable_scan():
    try:
        # خطوة ذكية: جلب ملخص السوق بطلب واحد لتوفير مئات الطلبات
        all_tickers = await EXCHANGE.fetch_tickers()
        
        # تصفية العملات: USDT فقط + صاعدة بنسبة بسيطة على الأقل (لبدء الرصد)
        potential_symbols = [
            s for s, t in all_tickers.items() 
            if '/USDT' in s and 'UP/' not in s and 'DOWN/' not in s 
            and (t['percentage'] or 0) > 0.3
        ]
        
        # نكتفي بأفضل 30 عملة "نشطة" حالياً لضمان عدم إرهاق السيرفر
        top_active = sorted(potential_symbols, key=lambda x: all_tickers[x]['quoteVolume'] or 0, reverse=True)[:30]
        
        candidates = []
        for sym in top_active:
            if sym in active_virtual_trades: continue
            
            try:
                # جلب 60 شمعة فقط (كافية للتحليل وتوفر في حجم البيانات)
                bars = await EXCHANGE.fetch_ohlcv(sym, timeframe=TIMEFRAME, limit=60)
                df = pd.DataFrame(bars, columns=['ts','open','high','low','close','vol'])
                
                score = check_explosion_quality(df)
                if score >= 3:
                    candidates.append({"sym": sym, "price": df['close'].iloc[-1], "score": score})
                
                # وقت انتظار طويل (1.2 ثانية) بين العملات لضمان هدوء الـ API
                await asyncio.sleep(1.2) 
            except Exception as e:
                if "429" in str(e): # استشعار ضغط الـ API
                    await asyncio.sleep(60) # تبريد كامل لمدة دقيقة
                continue

        if candidates:
            best = max(candidates, key=lambda x: x['score'])
            active_virtual_trades[best['sym']] = {
                "entry_price": best['price'],

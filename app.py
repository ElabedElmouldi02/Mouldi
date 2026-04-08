import asyncio
import ccxt.pro as ccxt
import pandas as pd
import requests
import threading
import os
from datetime import datetime
from flask import Flask
from waitress import serve

# ======================== 1. الإعدادات الأساسية ========================
TELEGRAM_TOKEN = '8643715664:AAH-Th6cUZasbUrOJe6elCJuV_Fn6oTfd5g'
TELEGRAM_CHAT_IDS = ['5067771509', '-1003692815602'] 

INVESTMENT_PER_TRADE = 100  # المبلغ لكل صفقة
TIMEFRAME = '15m'
EXCHANGE = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})

# ذاكرة مؤقتة لمنع تكرار التنبيهات لنفس العملة (لمدة 6 ساعات)
sent_signals_tracker = {}

def send_telegram_msg(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for chat_id in TELEGRAM_CHAT_IDS:
        try: 
            requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        except: 
            pass

# ======================== 2. الحسابات الفنية اليدوية ========================

def calculate_rsi(series, period=14):
    """حساب RSI يدوياً لضمان عدم الاعتماد على مكتبات خارجية"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_score(df):
    """تقييم قوة العملة بناءً على 5 نقاط"""
    try:
        if len(df) < 30: return 0
        
        # حساب المؤشرات باستخدام pandas الأساسية
        df['ema10'] = df['close'].ewm(span=10, adjust=False).mean()
        df['rsi'] = calculate_rsi(df['close'])
        
        last = df.iloc[-1]
        score = 0
        
        # شرط 1: السعر فوق المتوسط (قوة اتجاه)
        if last['close'] > last['ema10']: score += 2
        
        # شرط 2: انفجار السيولة (1.3 ضعف المتوسط)
        avg_vol = df['vol'].rolling(20).mean().iloc[-2]
        if last['vol'] > avg_vol * 1.3: score += 2
        
        # شرط 3: شمعة إيجابية (إغلاق أعلى من الافتتاح)
        if last['close'] > last['open']: score += 1
        
        # فلتر الأمان: استبعاد التشبع الشرائي الخطير
        if last['rsi'] > 82 or last['rsi'] < 20: score = 0
            
        return score
    except:
        return 0

# ======================== 3. المحرك التشغيلي (الرادار) ========================

async def weekly_stable_scan():
    current_time = datetime.now()
    
    # تنظيف العملات القديمة من الذاكرة كل دورة (التي مر عليها 6 ساعات)
    to_delete = [s for s, t in sent_signals_tracker.items() if (current_time - t).total_seconds() > 21600]
    for s in to_delete: del sent_signals_tracker[s]

    try:
        # جلب أسعار جميع العملات
        all_tickers = await EXCHANGE.fetch_tickers()
        
        # اختيار أفضل 100 عملة من حيث الحجم (USDT فقط)
        top_100 = sorted(
            [s for s in all_tickers if '/USDT' in s and 'UP/' not in s and 'DOWN/' not in s],
            key=lambda x: all_tickers[x]['quoteVolume'] or 0, reverse

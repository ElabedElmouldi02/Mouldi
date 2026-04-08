import asyncio
import ccxt.pro as ccxt
import pandas as pd
import requests
import threading
import os
from flask import Flask
from datetime import datetime
from waitress import serve

# ======================== 1. الإعدادات والربط ========================
TELEGRAM_TOKEN = '8643715664:AAH-Th6cUZasbUrOJe6elCJuV_Fn6oTfd5g'
TELEGRAM_CHAT_IDS = ['5067771509', '-1003692815602'] 

TRADE_AMOUNT_VIRTUAL = 50.0  
TIMEFRAME = '15m'

# إعداد المحرك مع تقنية التمويه لتجاوز حظر الـ IP
exchange_config = {
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'},
    'headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
        'Accept': 'application/json',
    }
}
EXCHANGE = ccxt.binance(exchange_config)

# محفظة الصفقات الافتراضية لمنع التكرار
active_virtual_trades = {} 

# ======================== 2. نظام الإشعارات ========================
def send_telegram_msg(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for chat_id in TELEGRAM_CHAT_IDS:
        try:
            requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        except:
            pass

# ======================== 3. منطق السكور الذكي ========================
def calculate_score(df):
    try:
        if len(df) < 60: return 0
        close = df['close']
        score = 0
        
        # مؤشر EMA 50 (اتجاه السوق)
        ema50 = close.ewm(span=50).mean().iloc[-1]
        if close.iloc[-1] > ema50: 
            score += 1
        
        # مؤشر حجم التداول (Volume Spike)
        avg_vol = df['vol'].rolling(20).mean().iloc[-2]
        if df['vol'].iloc[-1] > avg_vol * 1.5: 
            score += 2
            
        return score
    except:
        return 0

# ======================== 4. المسح والمراقبة الدوري ========================
async def report_portfolio():
    if not active_virtual_trades: return
    
    report = "📈 *تحديث أداء الصفقات الافتراضية:*\n"
    report += "---------------------------\n"
    for sym, data in list(active_virtual_trades.items()):
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
        send_telegram_msg("🔍 *جاري مسح السوق الآن...*")
        # جلب جميع الأسعار الحالية
        markets = await EXCHANGE.fetch_tickers()
        
        # تصفية العملات (USDT فقط، بدون رموز الرافعة المالية)
        symbols = [s for s in markets.keys() if '/USDT' in s and 'UP/' not in s and 'DOWN/' not in s]
        # اختيار أعلى 150 عملة سيولة لتقليل الضغط وتجنب الحظر
        top_symbols = sorted(symbols, key=lambda x: markets[x]['quoteVolume'] or 0, reverse=True)[:150]
        
        candidates = []
        for sym in top_symbols:

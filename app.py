import asyncio
import ccxt.pro as ccxt
import pandas as pd
import requests
import threading
from flask import Flask
from datetime import datetime
from waitress import serve

# ======================== 1. الإعدادات الأساسية ========================
TELEGRAM_TOKEN = '8643715664:AAH-Th6cUZasbUrOJe6elCJuV_Fn6oTfd5g'
TELEGRAM_CHAT_IDS = ['5067771509', '-1003692815602'] 

TRADE_AMOUNT_VIRTUAL = 50.0  
TIMEFRAME = '15m'
EXCHANGE = ccxt.binance({'enableRateLimit': True})

# سجل الصفقات الافتراضية النشطة (المحفظة)
active_virtual_trades = {} 

# ======================== 2. نظام الإشعارات والتقارير ========================
def send_telegram_msg(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for chat_id in TELEGRAM_CHAT_IDS:
        try: requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        except: pass

async def report_portfolio_status():
    """هذه الدالة ترسل تقرير المراقبة الدوري لجميع العملات المقترحة"""
    if not active_virtual_trades:
        return # لا ترسل شيئاً إذا كانت المحفظة فارغة

    report = "📊 *تقرير مراقبة العملات المقترحة:*\n"
    report += "---------------------------\n"
    
    total_pnl = 0
    for sym, data in active_virtual_trades.items():
        try:
            ticker = await EXCHANGE.fetch_ticker(sym)
            current_price = ticker['last']
            # حساب نسبة الربح/الخسارة
            pnl_percent = ((current_price - data['entry_price']) / data['entry_price']) * 100
            total_pnl += pnl_percent
            
            status_emoji = "✅" if pnl_percent >= 0 else "🔻"
            report += f"{status_emoji} `{sym}`\n"
            report += f"   💰 الدخول: `{data['entry_price']:.4f}`\n"
            report += f"   📈 الحالي: `{current_price:.4f}`\n"
            report += f"   💵 الربح: `{pnl_percent:.2f}%`\n"
            report += "---------------------------\n"
        except:
            continue
            
    avg_pnl = total_pnl / len(active_virtual_trades)
    report += f"💰 *إجمالي أداء المحفظة:* `{avg_pnl:.2f}%`"
    send_telegram_msg(report)

# ======================== 3. منطق البحث والمسح ========================
def calculate_score(df):
    try:
        if len(df) < 100: return 0
        close = df['close']
        score = 0
        ema50 = close.ewm(span=50).mean().iloc[-1]
        if close.iloc[-1] > ema50: score += 1
        # حجم التداول
        avg_vol = df['vol'].rolling(20).mean().iloc[-2]
        if df['vol'].iloc[-1] > avg_vol * 1.

import time
import json
import os
import requests
import ccxt
import pandas as pd
import numpy as np

# =========================
# ⚙️ CONFIG
# =========================
TOKEN = "8439548325:AAHOBBHy7EwcX3J5neIaf6iJuSjyGJCuZ68"
CHAT_ID = "5067771509"
ENABLE_TELEGRAM = True

DB_FILE = "trades.json"

INITIAL_BALANCE = 1000
TRADE_SIZE = 100

exchange = ccxt.kucoin({"enableRateLimit": True})
markets = exchange.load_markets()
symbols = [s for s in markets if s.endswith("/USDT")]

# =========================
# 📲 TELEGRAM
# =========================
def send(msg):
    if not ENABLE_TELEGRAM:
        print(msg)
        return
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except:
        pass

# =========================
# 💾 DATABASE (JSON)
# =========================
def load_data():
    if not os.path.exists(DB_FILE):
        return {"balance": INITIAL_BALANCE, "open": {}, "closed": []}
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

portfolio = load_data()

# =========================
# 📊 DATA
# =========================
def get(symbol, tf="15m"):
    try:
        df = pd.DataFrame(
            exchange.fetch_ohlcv(symbol, tf, limit=120),
            columns=["t","o","h","l","c","v"]
        )
        return df
    except:
        return None

# =========================
# 📈 INDICATORS
# =========================
def indicators(df):
    df["ema9"] = df["c"].ewm(span=9).mean()
    df["ema21"] = df["c"].ewm(span=21).mean()
    df["returns"] = df["c"].pct_change()
    df["volatility"] = df["returns"].rolling(20).std()
    df["volume_avg"] = df["v"].rolling(10).mean()
    return df

# =========================
# 🔔 SETUP
# =========================
def setup_score(df):
    score = 0
    reasons = []

    if df["volatility"].iloc[-1] < np.mean(df["volatility"])*0.8:
        score += 30
        reasons.append("Volatility squeeze")

    if abs(df["ema9"].iloc[-1] - df["ema21"].iloc[-1]) < df["c"].mean()*0.002:
        score += 20
        reasons.append("EMA compression")

    if df["v"].iloc[-1] > df["volume_avg"].iloc[-1]:
        score += 20
        reasons.append("Volume build")

    return score, reasons

# =========================
# 🚀 TRIGGER
# =========================
def trigger_score(df):
    score = 0
    reasons = []

    if df["v"].iloc[-1] > df["v"].mean()*2:
        score += 30
        reasons.append("Volume spike")

    if df["c"].iloc[-1] > df["c"].rolling(20).max().iloc[-2]:
        score += 30
        reasons.append("Breakout")

    if df["c"].iloc[-1] > df["c"].iloc[-3]:
        score += 20
        reasons.append("Momentum")

    return score, reasons

# =========================
# 📊 PROBABILITY
# =========================
def probability(setup, trigger):
    return (setup*0.5 + trigger*0.5)

# =========================
# 📥 ENTRY
# =========================
def open_trade(symbol, price, prob, setup_r, trigger_r):

    if symbol in portfolio["open"]:
        return

    portfolio["open"][symbol] = {
        "entry": price,
        "sl": price*0.98,
        "tp": price*1.05,
        "trail": price*1.03,
        "time": time.time()
    }

    save_data(portfolio)

    send(f"""
🚀 ENTRY

💰 {symbol}
📊 Prob: {round(prob,1)}%

💵 Entry: {price}
🎯 TP: {round(price*1.05,4)}
🛑 SL: {round(price*0.98,4)}

🧠 Setup:
- """ + "\n- ".join(setup_r) + """

⚡ Trigger:
- """ + "\n- ".join(trigger_r)
    )

# =========================
# 📤 EXIT
# =========================
def close_trade(symbol, price, reason):

    t = portfolio["open"].pop(symbol)

    pnl = ((price - t["entry"]) / t["entry"]) * TRADE_SIZE

    trade = {
        "symbol": symbol,
        "entry": t["entry"],
        "exit": price,
        "pnl": pnl,
        "reason": reason
    }

    portfolio["closed"].append(trade)
    portfolio["balance"] += pnl

    save_data(portfolio)

    send(f"""
📤 EXIT

💰 {symbol}
📊 PnL: {round(pnl,2)}$
📌 {reason}
""")

# =========================
# 🔄 MANAGE
# =========================
def manage(symbol, price):

    t = portfolio["open"][symbol]

    if price <= t["sl"]:
        close_trade(symbol, price, "STOP LOSS")
        return

    if price >= t["tp"]:
        close_trade(symbol, price, "TAKE PROFIT")
        return

    if price >= t["trail"]:
        t["sl"] = price * 0.98

# =========================
# 🔍 SCAN
# =========================
def scan():

    results = []

    for s in symbols[:150]:

        df = get(s)
        if df is None:
            continue

        df = indicators(df)

        setup, setup_r = setup_score(df)

        if setup < 60:
            continue

        trigger, trigger_r = trigger_score(df)
        prob = probability(setup, trigger)

        if prob > 80:
            results.append((s, prob, setup_r, trigger_r

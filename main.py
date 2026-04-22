
import asyncio
import sqlite3
import ccxt.async_support as ccxt_async
import pandas as pd
import numpy as np
import json
import os
import httpx
import csv
from datetime import datetime, time, timedelta
from dataclasses import dataclass, field

# =========================================================
# ⚙️ الإعدادات العامة (قابلة للتعديل بسهولة)
# =========================================================
TELEGRAM_TOKEN = "8716390236:AAEjPGJSYXN5FrqsuI845KhQoVzMfM_Suoo"
TELEGRAM_CHAT_ID = "5067771509"

LOG_DIR = "/tmp/trading_logs"
DB_FILE = os.path.join(LOG_DIR, "empire_v26.db")
REAL_CSV = os.path.join(LOG_DIR, "real_trades.csv")
MISSED_CSV = os.path.join(LOG_DIR, "missed_trades.csv")
OPPORTUNITIES_CSV = os.path.join(LOG_DIR, "opportunities.csv")
os.makedirs(LOG_DIR, exist_ok=True)

# ========== إعدادات التداول (مخففة) ==========
MAX_CONCURRENT_TRADES = 10
RISK_PER_TRADE = 0.02          # 2% مخاطرة لكل صفقة
STOP_LOSS_PCT = 0.025          # 2.5%
TRAILING_ACTIVATE_PCT = 2.0
TRAILING_DISTANCE_PCT = 1.5
PARTIAL_TP_PCT = 4.0
PARTIAL_CLOSE_RATIO = 0.5
FINAL_TP_PCT = 8.0

# ========== إعدادات المسح ==========
TOTAL_SYMBOLS_TO_SCAN = 1000
SCAN_INTERVAL = 10
BATCH_SIZE = 50

# ========== شروط الاختيار (مخففة مقارنة بالإصدارات السابقة) ==========
MIN_VOTES = 3                  # خفضنا من 4 إلى 3 (أسهل للقبول)
MIN_SCORE_FOR_ENTRY = 90       # دخول فقط إذا السكور >= 90 (كان 120)
MIN_SCORE_FOR_WATCH = 60       # مراقبة إذا السكور بين 60 و 90

# ========== فلاتر إضافية (يمكن تعطيلها) ==========
ENABLE_EXPLOSION_FILTER = True   # يمكن تعطيله إلى False لتخفيف أكثر
EXPLOSION_FILTER_MIN_CONDITIONS = 2  # خفضنا من 3 إلى 2
MIN_24H_VOLUME_USD = 300000     # خفضنا من 500k إلى 300k
MAX_SPREAD_PCT = 0.2            # زدنا من 0.1 إلى 0.2 (تسامح أكبر)

# ========== فلتر الوقت (اختياري – يمكن تعطيله) ==========
ENABLE_TIME_FILTER = False       # False = تداول 24/7, True = تفعيل الفلتر
TIME_FILTER_START = 14           # ساعة البدء (UTC)
TIME_FILTER_END = 22             # ساعة النهاية

# =========================================================
# هيكل البيانات
# =========================================================
@dataclass
class TrainSignal:
    symbol: str
    entry_price: float
    expected_pump_pct: float
    votes: int
    strategies: list
    score: float
    candle_patterns: list = field(default_factory=list)
    reason: str = ""
    entry_point: float = 0.0
    extra_scores: dict = field(default_factory=dict)
    time_found: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))

@dataclass
class TradeInfo:
    symbol: str
    signal: TrainSignal
    entry_price: float
    invested: float
    highest_price: float
    stop_loss: float
    take_profit: float
    entry_time: str = field(default_factory=lambda: datetime.now().isoformat())
    partial_closed: bool = False

# =========================================================
# المحرك الرئيسي (معدل للشروط المخففة)
# =========================================================
class EmpireEngineV26:
    def __init__(self):
        self.active_trades = {}
        self.missed_trades = []
        self.watchlist = []
        self.all_opportunities = []
        self.balance = 2000.0
        self.stats = {"scanned": 0, "opportunities_found": 0, "last_scan_time": None}
        self._init_storage()
        self._init_opportunities_csv()

    def _init_storage(self):
        conn = sqlite3.connect(DB_FILE)
        conn.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value REAL)")
        if not conn.execute("SELECT value FROM config WHERE key='balance'").fetchone():
            conn.execute("INSERT INTO config VALUES ('balance', 2000.0)")
        conn.commit()
        conn.close()
        for f in [REAL_CSV, MISSED_CSV]:
            if not os.path.exists(f):
                with open(f, 'w', newline='') as csvfile:
                    csv.writer(csvfile).writerow(['Time', 'Symbol', 'Entry', 'Exit', 'PNL%'])

    def _init_opportunities_csv(self):
        if not os.path.exists(OPPORTUNITIES_CSV):
            with open(OPPORTUNITIES_CSV, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Time', 'Symbol', 'Price', 'EntryPoint', 'ExpectedPump%', 'Votes', 'Score', 'Reason', 'Strategies', 'CandlePatterns', 'ExtraScores'])

    def log_opportunity(self, symbol, price, entry_point, expected_pump, votes, score, reason, strategies, candle_patterns=None, extra_scores=None):
        with open(OPPORTUNITIES_CSV, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                symbol, price, entry_point, expected_pump, votes, f"{score:.2f}",
                reason, ", ".join(strategies), ", ".join(candle_patterns) if candle_patterns else "",
                json.dumps(extra_scores or {})
            ])

    def _save_balance(self):
        conn = sqlite3.connect(DB_FILE)
        conn.execute("UPDATE config SET value = ? WHERE key = 'balance'", (self.balance,))
        conn.commit()
        conn.close()

    # ---------- فلتر الانفجار السريع (معدل للشروط المخففة) ----------
    async def explosion_filter(self, df):
        if len(df) < 30:
            return False, []
        avg_volume = df['v'].rolling(20).mean().iloc[-2]
        current_volume = df['v'].iloc[-1]
        volume_ok = (current_volume > avg_volume * 1.5) if avg_volume > 0 else False  # خفضنا من 1.8 إلى 1.5
        price_change_3 = (df['c'].iloc[-1] - df['c'].iloc[-4]) / df['c'].iloc[-4] * 100
        momentum_ok = price_change_3 > 1.0  # خفضنا من 1.5 إلى 1.0
        sma = df['c'].rolling(20).mean()
        std = df['c'].rolling(20).std()
        upper_bb = sma + (1.5 * std)
        bb_break_ok = df['c'].iloc[-1] > upper_bb.iloc[-1]
        lower_bb = sma - (2 * std)
        bw = (upper_bb - lower_bb) / sma
        squeeze_ok = bw.iloc[-1] < 0.07  # خفضنا من 0.05 إلى 0.07
        delta = df['c'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + gain / (loss + 1e-9)))
        rsi_val = rsi.iloc[-1]
        rsi_increasing = rsi.iloc[-1] > rsi.iloc[-2] > rsi.iloc[-3]
        rsi_ok = rsi_val > 50 or rsi_increasing  # خفضنا من 55 إلى 50
        conditions = []
        if volume_ok: conditions.append("VolumeSpike")
        if momentum_ok: conditions.append("Momentum3")
        if bb_break_ok: conditions.append("BBBreak")
        if squeeze_ok: conditions.append("Squeeze")
        if rsi_ok: conditions.append("RSI_Dynamic")
        passed = len(conditions) >= EXPLOSION_FILTER_MIN_CONDITIONS
        return passed, conditions

    # ---------- أنماط الشموع اليابانية (نفسها) ----------
    def detect_candlestick_patterns(self, df):
        if len(df) < 30:
            return 0, 0, [], False
        bullish_score = 0
        bearish_score = 0
        patterns = []
        is_exit = False
        avg_volume = df['v'].rolling(20).mean().iloc[-1]
        if avg_volume == 0:
            avg_volume = df['v'].iloc[-1]
        # Three Line Strike
        if len(df) >= 4:
            last_4 = df.iloc[-4:]
            if (all(last_4['c'].iloc[i] < last_4['c'].iloc[i-1] for i in range(1, 4)) and
                last_4['c'].iloc[-1] > last_4['h'].iloc[-2] and
                last_4['c'].iloc[-1] > last_4['o'].iloc[-1] and
                df['v'].iloc[-1] > avg_volume * 1.5):
                bullish_score += 25
                patterns.append("ThreeLineStrike")
        # Hammer
        body = abs(df['c'].iloc[-1] - df['o'].iloc[-1])
        lower_wick = min(df['o'].iloc[-1], df['c'].iloc[-1]) - df['l'].iloc[-1]
        upper_wick = df['h'].iloc[-1] - max(df['o'].iloc[-1], df['c'].iloc[-1])
        if body > 0 and lower_wick > body * 2 and upper_wick < body * 0.5:
            if df['v'].iloc[-1] > avg_volume * 1.2:
                bullish_score += 15
                patterns.append("Hammer")
        # Bullish Engulfing
        if len(df) >= 2:
            if (df['c'].iloc[-1] > df['o'].iloc[-1] and 
                df['o'].iloc[-1] < df['c'].iloc[-2] and 
                df['c'].iloc[-1] > df['o'].iloc[-2] and
                df['v'].iloc[-1] > avg_volume * 1.3):
                bullish_score += 15
                patterns.append("BullishEngulfing")
        # Morning Star
        if len(df) >= 3:
            last_3 = df.iloc[-3:]
            if (last_3['c'].iloc[-3] < last_3['o'].iloc[-3] and
                abs(last_3['c'].iloc[-2] - last_3['o'].iloc[-2]) < abs(last_3['c'].iloc[-3] - last_3['o'].iloc[-3]) * 0.3 and
                last_3['c'].iloc[-1] > last_3['o'].iloc[-1] and
                last_3['c'].iloc[-1] > (last_3['h'].iloc[-3] + last_3['l'].iloc[-3]) / 2 and
                df['v'].iloc[-1] > avg_volume * 1.2):
                bullish_score += 18
                patterns.append("MorningStar")
        # Piercing Line
        if len(df) >= 2:
            if (df['c'].iloc[-2] < df['o'].iloc[-2] and
                df['c'].iloc[-1] > df['o'].iloc[-1] and
                df['o'].iloc[-1] < df['c'].iloc[-2] and
                df['c'].iloc[-1] > (df['c'].iloc[-2] + df['o'].iloc[-2]) / 2 and
                df['v'].iloc[-1] > avg_volume * 1.2):
                bullish_score += 12
                patterns.append("PiercingLine")
        # Three Black Crows
        if len(df) >= 3:
            last_3 = df.iloc[-3:]
            if (all(last_3['c'].iloc[i] < last_3['c'].iloc[i-1] for i in range(1, 3)) and
                all(last_3['h'].iloc[i] - last_3['l'].iloc[i] > (df['h'].iloc[-5] - df['l'].iloc[-5]) * 0.7 for i in range(3))):
                bearish_score += 20
                patterns.append("ThreeBlackCrows")
                is_exit = True
        # Evening Star
        if len(df) >= 3:
            last_3 = df.iloc[-3:]
            if (last_3['c'].iloc[-3] > last_3['o'].iloc[-3] and
                abs(last_3['c'].iloc[-2] - last_3['o'].iloc[-2]) < abs(last_3['c'].iloc[-3] - last_3['o'].iloc[-3]) * 0.3 and
                last_3['c'].iloc[-1] < last_3['o'].iloc[-1] and
                last_3['c'].iloc[-1] < (last_3['l'].iloc[-3] + last_3['h'].iloc[-3]) / 2):
                bearish_score += 15
                patterns.append("EveningStar")
                is_exit = True
        # Shooting Star
        if body > 0 and upper_wick > body * 2 and lower_wick < body * 0.5:
            bearish_score += 12
            patterns.append("ShootingStar")
            is_exit = True
        return bullish_score, bearish_score, patterns, is_exit

    # ---------- حالة السوق والتقاطع الذهبي ----------
    async def get_market_condition_score(self, ex, symbol):
        try:
            ohlcv_15 = await ex.fetch_ohlcv(symbol, timeframe='15m', limit=30)
            ohlcv_1h = await ex.fetch_ohlcv(symbol, timeframe='1h', limit=100)
            if len(ohlcv_15) < 30 or len(ohlcv_1h) < 50:
                return 0, "Insufficient data"
            df_15 = pd.DataFrame(ohlcv_15, columns=['t','o','h','l','c','v'])
            df_1h = pd.DataFrame(ohlcv_1h, columns=['t','o','h','l','c','v'])
            price_15 = df_15['c'].iloc[-1]
            ema50_15 = df_15['c'].ewm(span=50).mean().iloc[-1]
            ema50_1h = df_1h['c'].ewm(span=50).mean().iloc[-1]
            ema200_1h = df_1h['c'].ewm(span=200).mean().iloc[-1]
            if price_15 > ema50_15 and ema50_1h > ema200_1h:
                return 15, "Strong Uptrend"
            elif price_15 > ema50_15:
                return 5, "Weak Uptrend"
            elif price_15 < ema50_15:
                return -15, "Downtrend"
            else:
                return -5, "Sideways"
        except:
            return 0, "Error"

    async def get_golden_cross_score(self, ex, symbol):
        try:
            ohlcv_4h = await ex.fetch_ohlcv(symbol, timeframe='4h', limit=100)
            if len(ohlcv_4h) < 50:
                return 0, None
            df = pd.DataFrame(ohlcv_4h, columns=['t','o','h','l','c','v'])
            ema50 = df['c'].ewm(span=50).mean()
            ema200 = df['c'].ewm(span=200).mean()
            for i in range(-3, 0):
                if ema50.iloc[i] > ema200.iloc[i] and ema50.iloc[i-1] <= ema200.iloc[i-1]:
                    return 10, "Golden Cross (4h)"
            return 0, None
        except:
            return 0, None

    # ---------- التحليل الأساسي (معدل للشروط المخففة) ----------
    async def analyze(self, ex, symbol):
        reason = None
        try:
            # فلتر الوقت (اختياري)
            if ENABLE_TIME_FILTER:
                now_utc = datetime.utcnow().time()
                if not (time(TIME_FILTER_START,0) <= now_utc <= time(TIME_FILTER_END,0)):
                    reason = f"وقت غير مناسب (خارج {TIME_FILTER_START}-{TIME_FILTER_END} UTC)"
                    return None, reason

            # فريم 15 دقيقة (خففنا الشرط: نحتاج فقط سعر > EMA50 وليس شرط EMA50 > EMA200)
            ohlcv_15 = await ex.fetch_ohlcv(symbol, timeframe='15m', limit=30)
            if len(ohlcv_15) < 30:
                reason = "بيانات 15 دقيقة غير كافية"
                return None, reason
            df_15 = pd.DataFrame(ohlcv_15, columns=['t','o','h','l','c','v'])
            ema50_15 = df_15['c'].ewm(span=50).mean().iloc[-1]
            if df_15['c'].iloc[-1] < ema50_15:
                reason = "اتجاه هابط على 15 دقيقة"
                return None, reason

            # بيانات 5 دقائق
            ohlcv = await ex.fetch_ohlcv(symbol, timeframe='5m', limit=100)
            if len(ohlcv) < 60:
                reason = "بيانات 5 دقائق غير كافية"
                return None, reason
            df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])

            # فلتر الانفجار السريع (يمكن تعطيله)
            if ENABLE_EXPLOSION_FILTER:
                passed, conds = await self.explosion_filter(df)
                if not passed:
                    reason = f"فلتر الانفجار: {','.join(conds) if conds else 'لا توجد شروط كافية'}"
                    return None, reason

            # السيولة والسبريد (مخفف)
            ticker = await ex.fetch_ticker(symbol)
            vol_24h = ticker['quoteVolume'] if 'quoteVolume' in ticker else ticker['volume'] * ticker['last']
            spread = (ticker['ask'] - ticker['bid']) / ticker['last'] * 100 if ticker['ask'] and ticker['bid'] else 100
            if vol_24h < MIN_24H_VOLUME_USD:
                reason = f"حجم 24h منخفض ({vol_24h/1000:.0f}K$)"
                return None, reason
            if spread > MAX_SPREAD_PCT:
                reason = f"سبريد عالٍ ({spread:.2f}%)"
                return None, reason

            # المؤشرات الأساسية
            sma = df['c'].rolling(20).mean()
            std = df['c'].rolling(20).std()
            upper_bb = sma + (2 * std)
            lower_bb = sma - (2 * std)
            bw = (upper_bb - lower_bb) / sma

            delta = df['c'].diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rsi = 100 - (100 / (1 + gain / (loss + 1e-9)))
            rsi_val = rsi.iloc[-1]
            if rsi_val < 25 or rsi_val > 88:  # خففنا التشبع (كان 30-85)
                reason = f"RSI مشبع ({rsi_val:.1f})"
                return None, reason

            # ATR (تخفيف)
            atr = (df['h'].rolling(14).max() - df['l'].rolling(14).min()) / 14
            volatility = atr.iloc[-1] / df['c'].iloc[-1] * 100
            if volatility > 6.0:  # خففنا من 5% إلى 6%
                reason = f"تقلب عالي ({volatility:.1f}%)"
                return None, reason

            # MACD
            exp1 = df['c'].ewm(span=12).mean()
            exp2 = df['c'].ewm(span=26).mean()
            macd = exp1 - exp2
            macd_signal = macd.ewm(span=9).mean()
            macd_hist = macd - macd_signal
            macd_bullish = macd.iloc[-1] > macd_signal.iloc[-1] and macd_hist.iloc[-1] > macd_hist.iloc[-2]

            # Divergence بسيط
            divergence = None
            if len(df) >= 20:
                price_lows = []
                rsi_lows = []
                for i in range(-20, -1):
                    if df['c'].iloc[i] <= df['c'].iloc[i-1] and df['c'].iloc[i] <= df['c'].iloc[i+1]:
                        price_lows.append(df['c'].iloc[i])
                    if rsi.iloc[i] <= rsi.iloc[i-1] and rsi.iloc[i] <= rsi.iloc[i+1]:
                        rsi_lows.append(rsi.iloc[i])
                if len(price_lows) >= 2 and len(rsi_lows) >= 2:
                    if price_lows[-1] < price_lows[-2] and rsi_lows[-1] > rsi_lows[-2]:
                        divergence = "bullish"
                    elif price_lows[-1] > price_lows[-2] and rsi_lows[-1] < rsi_lows[-2]:
                        divergence = "bearish"

            market_score, market_reason = await self.get_market_condition_score(ex, symbol)
            golden_score, golden_reason = await self.get_golden_cross_score(ex, symbol)

            avg_volume = df['v'].rolling(20).mean().iloc[-2]
            volume_ratio = df['v'].iloc[-1] / avg_volume if avg_volume > 0 else 1

            # جمع الأصوات (خففنا شروط بعض الأصوات)
            votes = []
            if bw.iloc[-1] < bw.rolling(30).min().iloc[-2] * 1.2:  # خففنا من 1.1 إلى 1.2
                votes.append("Squeeze")
            if df['c'].iloc[-1] > sma.iloc[-1]:
                votes.append("Uptrend")
            if volume_ratio > 1.8:  # خففنا من 2 إلى 1.8
                votes.append("Volume")
            if rsi_val > 52:  # خففنا من 55 إلى 52
                votes.append("Momentum")
            if df['c'].iloc[-1] > upper_bb.iloc[-1]:
                votes.append("Breakout")
            if macd_bullish:
                votes.append("MACD")
            if divergence == "bullish":
                votes.append("BullishDivergence")

            # حساب السكور الأساسي
            base_score = len(votes) * 10
            rsi_score = max(0, (rsi_val - 50) / 6) if rsi_val > 50 else 0  # خففنا القسمة
            volume_score = min(volume_ratio * 4, 12)  # خففنا من ×5 إلى ×4
            bw_score = max(0, (0.5 - bw.iloc[-1]) * 15) if bw.iloc[-1] < 0.5 else 0  # خففنا من ×20 إلى ×15
            liquidity_score = 10 if vol_24h > 200_000_000 else (7 if vol_24h > 50_000_000 else (3 if vol_24h > 5_000_000 else 0))
            spread_score = 8 if spread < 0.08 else 0  # خففنا من 0.05 إلى 0.08
            volume_spike_score = 15 if volume_ratio >= 5 else (10 if volume_ratio >= 3 else (5 if volume_ratio >= 1.8 else 0))

            total_score = base_score + rsi_score + volume_score + bw_score + liquidity_score + spread_score + volume_spike_score + market_score + (golden_score or 0)
            if divergence == "bullish":
                total_score += 15  # خففنا من 20 إلى 15
            total_score = round(total_score, 2)

            # أنماط الشموع
            candle_bullish, candle_bearish, candle_patterns, exit_signal = self.detect_candlestick_patterns(df)
            if candle_bearish >= 15:
                reason = f"نمط شموع هابط: {', '.join(candle_patterns)}"
                return None, reason
            total_score += candle_bullish

            # النسبة المتوقعة للارتفاع
            expected_pump = (volume_ratio * 1.2) + (bw.iloc[-1] * 40) + (rsi_val / 25)
            expected_pump = min(expected_pump, 12.0)

            ask_price = ticker['ask'] if ticker['ask'] else df['c'].iloc[-1] * (1 + spread/100)
            entry_point = ask_price

            if len(votes) >= MIN_VOTES:
                extra_scores = {
                    'base': base_score, 'rsi': round(rsi_score,2), 'volume': volume_score,
                    'bw': round(bw_score,2), 'liquidity': liquidity_score, 'spread': spread_score,
                    'spike': volume_spike_score, 'market': market_score, 'golden': golden_score or 0,
                    'divergence': 15 if divergence == 'bullish' else 0,
                    'candle_bullish': candle_bullish
                }
                signal = TrainSignal(
                    symbol=symbol,
                    entry_price=df['c'].iloc[-1],
                    expected_pump_pct=round(expected_pump, 2),
                    votes=len(votes),
                    strategies=votes,
                    score=total_score,
                    candle_patterns=candle_patterns,
                    entry_point=round(entry_point, 8),
                    extra_scores=extra_scores
                )
                return signal, None
            else:
                reason = f"أصوات غير كافية ({len(votes)}/{MIN_VOTES})"
                return None, reason
        except Exception as e:
            reason = f"خطأ: {str(e)[:50]}"
            return None, reason

    # ---------- تحديث الصفقات المفتوحة ----------
    async def update_trades(self, ex):
        for sym, trade in list(self.active_trades.items()):
            try:
                ticker = await ex.fetch_ticker(sym)
                curr = ticker['last']
                pnl = (curr - trade.entry_price) / trade.entry_price * 100
                if curr > trade.highest_price:
                    trade.highest_price = curr

                if not trade.partial_closed and pnl >= PARTIAL_TP_PCT:
                    close_amount = trade.invested * PARTIAL_CLOSE_RATIO
                    profit_partial = close_amount * (pnl / 100)
                    self.balance += close_amount + profit_partial
                    trade.invested -= close_amount
                    trade.partial_closed = True
                    await send_tg(f"📊 *جني أرباح جزئي {sym}*\nالربح: {pnl:.2f}% | المتبقي: {trade.invested:.2f} USDT")

                if pnl >= TRAILING_ACTIVATE_PCT:
                    new_stop = trade.entry_price * (1 + (pnl - TRAILING_DISTANCE_PCT)/100)
                    if new_stop > trade.stop_loss:
                        trade.stop_loss = new_stop

                exit_reason = None
                if pnl <= -STOP_LOSS_PCT * 100:
                    exit_reason = "Stop Loss"
                elif trade.partial_closed and pnl <= (TRAILING_ACTIVATE_PCT - 1):
                    exit_reason = "Trailing Stop (remainder)"
                elif pnl >= FINAL_TP_PCT:
                    exit_reason = "Final Take Profit"
                elif curr <= trade.stop_loss and trade.stop_loss > trade.entry_price:
                    exit_reason = "Trailing Stop"

                if exit_reason:
                    total_pnl = (curr - trade.entry_price) / trade.entry_price * 100
                    self.balance += trade.invested * (1 + total_pnl/100)
                    self._save_balance()
                    with open(REAL_CSV, 'a', newline='') as f:
                        csv.writer(f).writerow([datetime.now().isoformat(), sym, trade.entry_price, curr, f"{total_pnl:.2f}"])
                    await send_tg(
                        f"🏁 *إغلاق {sym}*\n"
                        f"الربح: `{total_pnl:.2f}%`\n"
                        f"السبب: {exit_reason}\n"
                        f"الرصيد: {self.balance:.2f} USDT\n"
                        f"أعلى سعر: {trade.highest_price:.8f}"
                    )
                    del self.active_trades[sym]
            except Exception as e:
                pass

# =========================================================
# دوال تلغرام (إرسال واستقبال الأوامر)
# =========================================================
async def send_tg(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    except:
        pass

async def send_document(file_path, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    try:
        async with httpx.AsyncClient() as client:
            with open(file_path, 'rb') as f:
                files = {'document': f}
                data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': caption}
                await client.post(url, data=data, files=files)
    except Exception as e:
        print("Error sending file:", e)

async def handle_telegram_commands():
    last_update_id = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={last_update_id+1}&timeout=30"
            async with httpx.AsyncClient() as client:
                resp = await client.get(url)
                data = resp.json()
                if data['ok']:
                    for update in data['result']:
                        last_update_id = update['update_id']
                        if 'message' in update and 'text' in update['message']:
                            text = update['message']['text'].strip()
                            if text == '/start':
                                await send_tg("مرحباً! بوت التداول Empire V26 (شروط مخففة)\nالأوامر:\n/download_real - تحميل سجل الصفقات\n/download_missed - تحميل الفرص الضائعة\n/download_opp - تحميل كل الفرص\n/status - حالة البوت")
                            elif text == '/download_real':
                                if os.path.exists(REAL_CSV):
                                    await send_document(REAL_CSV, "📊 سجل الصفقات الحقيقية")
                                else:
                                    await send_tg("⚠️ الملف غير موجود بعد.")
                            elif text == '/download_missed':
                                if os.path.exists(MISSED_CSV):
                                    await send_document(MISSED_CSV, "📊 الفرص الضائعة")
                                else:
                                    await send_tg("⚠️ الملف غير موجود بعد.")
                            elif text == '/download_opp':
                                if os.path.exists(OPPORTUNITIES_CSV):
                                    await send_document(OPPORTUNITIES_CSV, "📊 سجل جميع الفرص")
                                else:
                                    await send_tg("⚠️ الملف غير موجود بعد.")
                            elif text == '/status':
                                await send_tg(f"📈 *حالة البوت*\nالرصيد: {engine.balance:.2f} USDT\nصفقات مفتوحة: {len(engine.active_trades)}/{MAX_CONCURRENT_TRADES}\nآخر مسح: {engine.stats['last_scan_time'] or '—'}\nإجمالي الفرص: {engine.stats['opportunities_found']}")
        except Exception as e:
            print("Telegram polling error:", e)
        await asyncio.sleep(2)

# =========================================================
# الحلقة الرئيسية للمسح مع إرسال أفضل عملة
# =========================================================
async def main_loop():
    ex = ccxt_async.gateio({'enableRateLimit': True})
    await send_tg("🚀 *Empire V26 démarré*\n✅ شروط مخففة\n✅ فلتر الوقت: " + ("ON" if ENABLE_TIME_FILTER else "OFF"))
    markets = await ex.fetch_markets()
    symbols = [m['symbol'] for m in markets if m['symbol'].endswith('/USDT') and m['active']]
    symbols = symbols[:TOTAL_SYMBOLS_TO_SCAN]
    await send_tg(f"📊 {len(symbols)} عملة جاهزة للمسح")
    
    while True:
        try:
            scan_start = datetime.now()
            engine.stats["scanned"] = 0
            engine.stats["opportunities_found"] = 0
            random_symbols = np.random.choice(symbols, min(len(symbols), TOTAL_SYMBOLS_TO_SCAN), replace=False)
            all_signals = []
            
            for i in range(0, len(random_symbols), BATCH_SIZE):
                batch = random_symbols[i:i+BATCH_SIZE]
                tasks = [engine.analyze(ex, s) for s in batch]
                results = await asyncio.gather(*tasks)
                for (sig, reason), symbol in zip(results, batch):
                    if sig:
                        all_signals.append(sig)
                        engine.stats["opportunities_found"] += 1
                        engine.log_opportunity(sig.symbol, sig.entry_price, sig.entry_point, sig.expected_pump_pct,
                                               sig.votes, sig.score, "إشارة قوية", sig.strategies, sig.candle_patterns, sig.extra_scores)
                        engine.all_opportunities.append(sig)
                    else:
                        dummy = TrainSignal(symbol=symbol, entry_price=0, expected_pump_pct=0, votes=0,
                                            strategies=[], score=0, reason=reason or "لا توجد إشارة", entry_point=0)
                        engine.all_opportunities.append(dummy)
                        engine.log_opportunity(symbol, 0, 0, 0, 0, 0, reason or "لا توجد إشارة", [], [], {})
                        if len(engine.all_opportunities) > 500:
                            engine.all_opportunities = engine.all_opportunities[-500:]
                engine.stats["scanned"] += len(batch)
                await asyncio.sleep(0.1)
            
            # ترتيب الإشارات حسب السكور
            all_signals.sort(key=lambda x: x.score, reverse=True)
            
            # إرسال أفضل عملة
            if all_signals:
                best = all_signals[0]
                await send_tg(
                    f"🏆 *أفضل عملة في هذا المسح*\n"
                    f"العملة: {best.symbol}\n"
                    f"السعر: {best.entry_price:.8f}\n"
                    f"السكور: {best.score}\n"
                    f"الأصوات: {best.votes}/6\n"
                    f"الارتفاع المتوقع: {best.expected_pump_pct}%\n"
                    f"الأنماط: {', '.join(best.candle_patterns) if best.candle_patterns else '-'}\n"
                    f"الاستراتيجيات: {', '.join(best.strategies)}"
                )
            
            # معالجة الإشارات حسب السكور (دخول أو مراقبة)
            engine.watchlist.clear()
            for sig in all_signals:
                if sig.symbol in engine.active_trades:
                    continue
                if sig.score >= MIN_SCORE_FOR_ENTRY:
                    risk_amount = engine.balance * RISK_PER_TRADE
                    position_size = risk_amount / STOP_LOSS_PCT
                    invest = min(position_size, engine.balance)
                    if len(engine.active_trades) < MAX_CONCURRENT_TRADES and engine.balance >= invest:
                        stop_loss_price = sig.entry_point * (1 - STOP_LOSS_PCT)
                        take_profit_price = sig.entry_point * (1 + FINAL_TP_PCT/100)
                        trade = TradeInfo(
                            symbol=sig.symbol,
                            signal=sig,
                            entry_price=sig.entry_point,
                            invested=invest,
                            highest_price=sig.entry_point,
                            stop_loss=stop_loss_price,
                            take_profit=take_profit_price,
                            partial_closed=False
                        )
                        engine.active_trades[sig.symbol] = trade
                        engine.balance -= invest
                        engine._save_balance()
                        await send_tg(
                            f"🟢 *شراء {sig.symbol}*\n"
                            f"💰 السعر: {sig.entry_point:.8f}\n"
                            f"📈 الارتفاع المتوقع: {sig.expected_pump_pct}%\n"
                            f"⭐ السكور: {sig.score}\n"
                            f"🎫 الأصوات: {sig.votes}/6\n"
                            f"🕯️ الأنماط: {', '.join(sig.candle_patterns) if sig.candle_patterns else '-'}\n"
                            f"📊 الاستراتيجيات: {', '.join(sig.strategies)}\n"
                            f"💵 المستثمر: {invest:.2f} USDT\n"
                            f"🛑 وقف الخسارة: {stop_loss_price:.8f}\n"
                            f"🎯 الهدف: {take_profit_price:.8f}"
                        )
                        engine.log_opportunity(sig.symbol, sig.entry_price, sig.entry_point, sig.expected_pump_pct,
                                               sig.votes, sig.score, "✅ تم الدخول", sig.strategies, sig.candle_patterns, sig.extra_scores)
                    else:
                        sig.reason = f"حد الصفقات أو رصيد (مفتوحة: {len(engine.active_trades)})"
                        engine.missed_trades.append(sig)
                        engine.log_opportunity(sig.symbol, sig.entry_price, sig.entry_point, sig.expected_pump_pct,
                                               sig.votes, sig.score, sig.reason, sig.strategies, sig.candle_patterns, sig.extra_scores)
                elif MIN_SCORE_FOR_WATCH <= sig.score < MIN_SCORE_FOR_ENTRY:
                    engine.watchlist.append(sig)
                    engine.log_opportunity(sig.symbol, sig.entry_price, sig.entry_point, sig.expected_pump_pct,
                                           sig.votes, sig.score, "مراقبة", sig.strategies, sig.candle_patterns, sig.extra_scores)
                else:
                    engine.log_opportunity(sig.symbol, sig.entry_price, sig.entry_point, sig.expected_pump_pct,
                                           sig.votes, sig.score, "سكور منخفض", sig.strategies, sig.candle_patterns, sig.extra_scores)
            
            if len(engine.missed_trades) > 100:
                engine.missed_trades = engine.missed_trades[-100:]
            if len(engine.watchlist) > 50:
                engine.watchlist = engine.watchlist[-50:]
            
            engine.stats["last_scan_time"] = scan_start.strftime("%H:%M:%S")
            await engine.update_trades(ex)
            
        except Exception as e:
            print("Main loop error:", e)
            await send_tg(f"⚠️ خطأ: {str(e)[:100]}")
            await asyncio.sleep(5)
        await asyncio.sleep(SCAN_INTERVAL)

# =========================================================
# تشغيل البوت
# =========================================================
async def main():
    asyncio.create_task(handle_telegram_commands())
    await main_loop()

if __name__ == "__main__":
    asyncio.run(main())

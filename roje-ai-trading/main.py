import os
import time
import threading
import requests
import yfinance as yf
import pandas as pd

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN")

URL = f"https://api.telegram.org/bot{TOKEN}"

# تجاهل رقم الحساب الشخصي؛ نلتقط رقم المجموعة من /start داخلها
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
if CHAT_ID and not CHAT_ID.startswith("-"):
    CHAT_ID = None

SYMBOLS = [
    "GC=F",       # Gold
    "SI=F",       # Silver
    "EURUSD=X",
    "GBPUSD=X",
    "USDJPY=X",
    "AUDUSD=X",
    "USDCAD=X",
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "SPY",
    "QQQ",
    "DIA",
    "^GSPC",
    "^NDX",
    "^DJI"
]

SCAN_SECONDS = 300

offset = 0
last_signal = {}
open_trades = {}
lock = threading.Lock()

print("ROJE AI TRADING BOT STARTED")


def send_message(message):
    global CHAT_ID

    if not CHAT_ID:
        print("Waiting for group ID. Send /start in the group.")
        return

    try:
        r = requests.post(
            f"{URL}/sendMessage",
            json={
                "chat_id": CHAT_ID,
                "text": message
            },
            timeout=15
        )
        print("Telegram:", r.text[:300])

    except Exception as e:
        print("Send error:", e)


def get_data(symbol):
    try:
        df = yf.download(
            symbol,
            period="5d",
            interval="5m",
            progress=False,
            auto_adjust=True
        )

        if df is None or df.empty:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        required = ["Open", "High", "Low", "Close"]

        if not all(x in df.columns for x in required):
            return None

        df = df.dropna()

        if len(df) < 30:
            return None

        return df

    except Exception as e:
        print("Data error:", symbol, e)
        return None


def calculate_indicators(df):
    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    ema9 = close.ewm(span=9, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1/14, adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1/14, adjust=False
    ).mean()

    rs = avg_gain / avg_loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + rs))

    previous_close = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - previous_close).abs(),
        (low - previous_close).abs()
    ], axis=1).max(axis=1)

    atr = tr.ewm(span=14, adjust=False).mean()

    return ema9, ema21, rsi, atr


def check_signal(symbol, df):
    ema9, ema21, rsi, atr = calculate_indicators(df)

    if len(df) < 30:
        return None

    previous_fast = float(ema9.iloc[-2])
    previous_slow = float(ema21.iloc[-2])

    fast = float(ema9.iloc[-1])
    slow = float(ema21.iloc[-1])

    current_rsi = float(rsi.iloc[-1])
    current_atr = float(atr.iloc[-1])
    price = float(df["Close"].iloc[-1])

    if pd.isna(current_rsi) or pd.isna(current_atr):
        return None

    if current_atr <= 0:
        return None

    direction = None

    if previous_fast <= previous_slow and fast > slow:
        if 50 < current_rsi < 70:
            direction = "BUY"

    elif previous_fast >= previous_slow and fast < slow:
        if 30 < current_rsi < 50:
            direction = "SELL"

    if not direction:
        return None

    distance = current_atr * 1.5

    if direction == "BUY":
        sl = price - distance
        tp1 = price + distance
        tp2 = price + distance * 2
        tp3 = price + distance * 3

    else:
        sl = price + distance
        tp1 = price - distance
        tp2 = price - distance * 2
        tp3 = price - distance * 3

    return {
        "symbol": symbol,
        "direction": direction,
        "entry": price,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "rsi": current_rsi,
        "time": str(df.index[-1])
    }


def price_text(value):
    return f"{value:.5f}"


def send_signal(signal):
    symbol = signal["symbol"]
    direction = signal["direction"]

    message = (
        "🚀 ROJE AI TRADING\n"
        "━━━━━━━━━━━━━━\n"
        f"📊 السوق: {symbol}\n"
        f"📍 الإشارة: {direction}\n"
        f"💰 Entry: {price_text(signal['entry'])}\n"
        f"🛑 Stop Loss: {price_text(signal['sl'])}\n"
        f"🎯 TP1: {price_text(signal['tp1'])}\n"
        f"🎯 TP2: {price_text(signal['tp2'])}\n"
        f"🎯 TP3: {price_text(signal['tp3'])}\n"
        f"📈 RSI: {signal['rsi']:.2f}\n"
        "━━━━━━━━━━━━━━\n"
        "السبب: تقاطع EMA 9 و EMA 21 مع فلتر RSI.\n"
        "⚠️ إشارة فنية آلية وليست ضماناً للربح."
    )

    send_message(message)


def monitor_trade(symbol, df):
    with lock:
        trade = open_trades.get(symbol)

    if not trade:
        return

    candle_time = str(df.index[-1])

    if trade.get("last_checked") == candle_time:
        return

    high = float(df["High"].iloc[-1])
    low = float(df["Low"].iloc[-1])

    direction = trade["direction"]
    sl = trade["sl"]

    # إذا لمس السعر الوقف والهدف في نفس الشمعة،
    # نعتبر الوقف أولاً بشكل محافظ.
    if direction == "BUY" and low <= sl:
        send_message(
            f"🛑 ROJE UPDATE\n{symbol}\n"
            "تم الوصول إلى Stop Loss."
        )
        with lock:
            open_trades.pop(symbol, None)
        return

    if direction == "SELL" and high >= sl:
        send_message(
            f"🛑 ROJE UPDATE\n{symbol}\n"
            "تم الوصول إلى Stop Loss."
        )
        with lock:
            open_trades.pop(symbol, None)
        return

    for number in (1, 2, 3):
        key = f"tp{number}"

        if trade.get(key + "_hit"):
            continue

        target = trade[key]

        hit = (
            high >= target if direction == "BUY"
            else low <= target
        )

        if hit:
            send_message(
                f"🎯 ROJE UPDATE\n"
                f"{symbol}\n"
                f"تم الوصول إلى TP{number}."
            )

            with lock:
                if symbol in open_trades:
                    open_trades[symbol][key + "_hit"] = True

            if number == 3:
                with lock:
                    open_trades.pop(symbol, None)
                return

    with lock:
        if symbol in open_trades:
            open_trades[symbol]["last_checked"] = candle_time


def scan_markets():
    print("ROJE scanner started")

    while True:
        try:
            for symbol in SYMBOLS:
                df = get_data(symbol)

                if df is None:
                    print("No data:", symbol)
                    continue

                monitor_trade(symbol, df)

                signal = check_signal(symbol, df)

                if signal:
                    candle_time = signal["time"]

                    if last_signal.get(symbol) == candle_time:
                        continue

                    with lock:
                        already_open = symbol in open_trades

                    if already_open:
                        continue

                    last_signal[symbol] = candle_time

                    with lock:
                        open_trades[symbol] = {
                            **signal,
                            "tp1_hit": False,
                            "tp2_hit": False,
                            "tp3_hit": False,
                            "last_checked": candle_time
                        }

                    send_signal(signal)

                time.sleep(1)

        except Exception as e:
            print("Scanner error:", e)

        print("Next scan in 5 minutes")
        time.sleep(SCAN_SECONDS)


def telegram_listener():
    global offset, CHAT_ID

    while True:
        try:
            response = requests.get(
                f"{URL}/getUpdates",
                params={
                    "offset": offset,
                    "timeout": 10,
                    "allowed_updates": ["message"]
                },
                timeout=15
            ).json()

            if not response.get("ok"):
                print("Telegram API error:", response)
                time.sleep(5)
                continue

            for update in response.get("result", []):
                offset = update["update_id"] + 1

                message = update.get("message", {})
                chat = message.get("chat", {})
                chat_id = chat.get("id")
                chat_type = chat.get("type")
                command = message.get("text", "").strip()

                if not chat_id:
                    continue

                if command.startswith("/start"):
                    if chat_type in ("group", "supergroup"):
                        CHAT_ID = str(chat_id)
                        print("GROUP ID DETECTED:", CHAT_ID)

                        requests.post(
                            f"{URL}/sendMessage",
                            json={
                                "chat_id": CHAT_ID,
                                "text": (
                                    "🚀 ROJE AI TRADING\n"
                                    "تم ربط المجموعة بنجاح!\n"
                                    "نظام مراقبة الأسواق بدأ."
                                )
                            },
                            timeout=15
                        )

                    else:
                        requests.post(
                            f"{URL}/sendMessage",
                            json={
                                "chat_id": chat_id,
                                "text": (
                                    "أهلاً بك في ROJE AI TRADING!\n"
                                    "افتح المجموعة واكتب /start لربطها."
                                )
                            },
                            timeout=15
                        )

                elif command.startswith("/status"):
                    requests.post(
                        f"{URL}/sendMessage",
                        json={
                            "chat_id": chat_id,
                            "text": (
                                "🟢 ROJE AI TRADING ONLINE\n"
                                f"الأسواق: {len(SYMBOLS)}\n"
                                f"الصفقات المفتوحة: {len(open_trades)}\n"
                                "الفحص: كل 5 دقائق"
                            )
                        },
                        timeout=15
                    )

        except Exception as e:
            print("Telegram listener error:", e)
            time.sleep(5)


if __name__ == "__main__":
    try:
        requests.post(
            f"{URL}/deleteWebhook",
            json={"drop_pending_updates": False},
            timeout=15
        )

        threading.Thread(
            target=telegram_listener,
            daemon=True
        ).start()

        threading.Thread(
            target=scan_markets,
            daemon=True
        ).start()

        while True:
            time.sleep(60)

    except Exception as e:
        print("Startup error:", e)

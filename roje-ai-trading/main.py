import os, time, logging, threading
from datetime import datetime, timezone
import requests
import yfinance as yf
import pandas as pd

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
SCAN_SECONDS = int(os.getenv("SCAN_SECONDS", "300"))
SYMBOLS = [s.strip() for s in os.getenv(
    "SYMBOLS",
    "GC=F,SI=F,EURUSD=X,GBPUSD=X,USDJPY=X,BTC-USD,ETH-USD,SPY,QQQ"
).split(",") if s.strip()]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("roje")

if not TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN environment variable")

API = f"https://api.telegram.org/bot{TOKEN}"
offset = 0
last_sent = {}

def telegram(method, payload=None, timeout=35):
    r = requests.post(f"{API}/{method}", json=payload or {}, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(str(data))
    return data.get("result")

def send(text, chat_id=None):
    target = chat_id or CHAT_ID
    if not target:
        log.info("No TELEGRAM_CHAT_ID yet; waiting for /start in the group.")
        return
    telegram("sendMessage", {"chat_id": target, "text": text, "disable_web_page_preview": True})

def handle_updates():
    global offset
    while True:
        try:
            updates = telegram("getUpdates", {"offset": offset, "timeout": 25}, timeout=35)
            for u in updates:
                offset = u["update_id"] + 1
                msg = u.get("message") or u.get("channel_post")
                if not msg:
                    continue
                chat = msg.get("chat", {})
                text = (msg.get("text") or "").strip().lower()
                if text.startswith("/start") or text.startswith("/connect"):
                    send("✅ ROJE AI TRADING متصل بنجاح.\nسأرسل تنبيهات تجريبية عند ظهور شروط فنية. هذه ليست توصية مضمونة ولا تنفيذ صفقات.", chat.get("id"))
                    log.info("Telegram chat connected: %s", chat.get("id"))
        except Exception as e:
            log.exception("Telegram polling error: %s", e)
            time.sleep(5)

def calculate_signal(symbol):
    # Yahoo Finance intraday history availability varies by symbol and provider.
    df = yf.download(symbol, period="5d", interval="5m", progress=False, auto_adjust=False, threads=False)
    if df is None or df.empty or len(df) < 60:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        close = df["Close"].iloc[:, 0]
        high = df["High"].iloc[:, 0]
        low = df["Low"].iloc[:, 0]
    else:
        close, high, low = df["Close"], df["High"], df["Low"]
    close, high, low = close.dropna(), high.dropna(), low.dropna()
    data = pd.concat([close.rename("close"), high.rename("high"), low.rename("low")], axis=1).dropna()
    if len(data) < 60:
        return None
    c = data["close"]
    ema9 = c.ewm(span=9, adjust=False).mean()
    ema21 = c.ewm(span=21, adjust=False).mean()
    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    tr = pd.concat([
        data["high"] - data["low"],
        (data["high"] - c.shift()).abs(),
        (data["low"] - c.shift()).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    price = float(c.iloc[-1])
    e9, e21 = float(ema9.iloc[-1]), float(ema21.iloc[-1])
    rv = float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else 50
    av = float(atr.iloc[-1]) if pd.notna(atr.iloc[-1]) else 0
    if av <= 0:
        return None
    direction = None
    if e9 > e21 and 52 <= rv <= 68 and price > e9:
        direction = "BUY 🟢"
        sl, tp1, tp2, tp3 = price - 1.5*av, price + 1.5*av, price + 2.5*av, price + 3.5*av
    elif e9 < e21 and 32 <= rv <= 48 and price < e9:
        direction = "SELL 🔴"
        sl, tp1, tp2, tp3 = price + 1.5*av, price - 1.5*av, price - 2.5*av, price - 3.5*av
    if not direction:
        return None
    return {
        "direction": direction, "price": price, "sl": sl,
        "tp1": tp1, "tp2": tp2, "tp3": tp3, "rsi": rv,
        "bar": str(data.index[-1])
    }

def scanner():
    log.info("ROJE scanner started. Symbols=%s", SYMBOLS)
    while True:
        for symbol in SYMBOLS:
            try:
                sig = calculate_signal(symbol)
                if not sig:
                    continue
                key = f"{symbol}:{sig['direction']}"
                if last_sent.get(symbol) == (key, sig["bar"]):
                    continue
                last_sent[symbol] = (key, sig["bar"])
                message = (
                    f"📊 ROJE AI TRADING — تنبيه تجريبي\n"
                    f"الأصل: {symbol}\n"
                    f"الاتجاه: {sig['direction']}\n"
                    f"دخول مرجعي: {sig['price']:.5f}\n"
                    f"وقف الخسارة: {sig['sl']:.5f}\n"
                    f"TP1: {sig['tp1']:.5f}\nTP2: {sig['tp2']:.5f}\nTP3: {sig['tp3']:.5f}\n"
                    f"RSI: {sig['rsi']:.1f}\n"
                    f"الإطار: 5 دقائق | وقت الشمعة: {sig['bar']}\n\n"
                    f"ملاحظة: إشارة آلية مبنية على EMA/RSI/ATR وليست ذكاءً اصطناعياً متعلماً أو ضماناً للربح. تحقق من السعر والتنفيذ والأخبار قبل أي قرار."
                )
                send(message)
                log.info("Signal generated for %s", symbol)
            except Exception as e:
                log.exception("Scan failed for %s: %s", symbol, e)
        time.sleep(SCAN_SECONDS)

if __name__ == "__main__":
    log.info("ROJE AI TRADING BOT STARTED")
    threading.Thread(target=handle_updates, daemon=True).start()
    scanner()

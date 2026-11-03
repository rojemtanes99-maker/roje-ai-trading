# ROJE AI TRADING — starter

This is a **starter alert bot**, not a proven AI trading system and not an auto-trader.
It scans a configurable watchlist using 5-minute EMA(9/21), RSI(14), and ATR(14) rules.
It sends educational/demo alerts to the Telegram chat that sends `/start` or `/connect`.

## Railway variables
- `TELEGRAM_BOT_TOKEN`: token from BotFather (keep secret; never commit it)
- `TELEGRAM_CHAT_ID`: optional. If omitted, add the bot to your group and send `/start` in the group; the bot replies there.
- `SYMBOLS`: optional comma-separated Yahoo Finance symbols. Default: `GC=F,SI=F,EURUSD=X,GBPUSD=X,USDJPY=X,BTC-USD,ETH-USD,SPY,QQQ`
- `SCAN_SECONDS`: optional, default `300`

## Important
Yahoo Finance intraday coverage and delay vary by instrument and may fail or be unavailable.
Do not use these alerts with real money until you independently verify the feed, backtest, and forward-test.
No win rate or profit is promised. The bot does not place orders.

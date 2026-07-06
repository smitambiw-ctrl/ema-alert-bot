# ============================================================
# EMA CROSSOVER ALERT BOT - Render Deployment
# Runs 24/7, checks signals every 5 minutes during market hours
# ============================================================

import os
import time
import threading
import warnings
from datetime import datetime
from flask import Flask
import schedule
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import pytz

# Suppress warnings
warnings.filterwarnings('ignore')

# ============================================================
# CONFIGURATION
# ============================================================

# --- Telegram Credentials (REPLACE THESE) ---
TELEGRAM_TOKEN = "8867149849:AAE7i-xBOJxwhbGvSmFJJWvlbF1vl6h97yM"   # From @BotFather
TELEGRAM_CHAT_ID = "2075943988"   # From getUpdates

# --- Strategy Parameters ---
FAST_EMA = 9
SLOW_EMA = 15
TIMEFRAME = "30m"        # 30-minute candles
MIN_DATA_POINTS = 20     # Minimum candles needed for EMA

# --- Duplicate Alert Prevention (seconds) ---
DUPLICATE_WINDOW = 1800  # 30 minutes

# --- Track sent signals to avoid duplicates ---
sent_signals = {}  # key: ticker, value: last_signal_time

# --- Stock Watchlist (Large Cap + Mid Cap) ---
WATCHLIST = [
    # NIFTY 50 (Large Cap)
    'RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'INFY.NS', 'ICICIBANK.NS',
    'HINDUNILVR.NS', 'ITC.NS', 'SBIN.NS', 'BAJFINANCE.NS', 'KOTAKBANK.NS',
    'BHARTIARTL.NS', 'LT.NS', 'WIPRO.NS', 'ASIANPAINT.NS', 'HCLTECH.NS',
    'AXISBANK.NS', 'MARUTI.NS', 'SUNPHARMA.NS', 'TITAN.NS', 'ULTRACEMCO.NS',
    'NTPC.NS', 'ONGC.NS', 'POWERGRID.NS', 'NESTLEIND.NS', 'M&M.NS',
    'TECHM.NS', 'JSWSTEEL.NS', 'HDFCLIFE.NS', 'SBILIFE.NS', 'DRREDDY.NS',
    'BAJAJFINSV.NS', 'TATAMOTORS.NS', 'COALINDIA.NS', 'BRITANNIA.NS',
    'GRASIM.NS', 'EICHERMOT.NS', 'DIVISLAB.NS', 'HINDALCO.NS', 'INDUSINDBK.NS',
    'UPL.NS', 'BPCL.NS', 'SHREECEM.NS', 'CIPLA.NS', 'TATASTEEL.NS',
    'HEROMOTOCO.NS', 'ADANIPORTS.NS', 'APOLLOHOSP.NS', 'BAJAJ-AUTO.NS',
    'ADANIENT.NS', 'PIDILITIND.NS',
    # Nifty Midcap 100 (selection)
    'MUTHOOTFIN.NS', 'SRTRANSFIN.NS', 'BHARATFORG.NS', 'PAGEIND.NS', 'LUPIN.NS',
    'MARICO.NS', 'DABUR.NS', 'GODREJCP.NS', 'HAVELLS.NS', 'TORNTPHARM.NS',
    'MOTHERSUMI.NS', 'VEDL.NS', 'ICICIPRULI.NS', 'ICICIGI.NS', 'MPHASIS.NS',
    'BIOCON.NS', 'COLPAL.NS', 'AMBUJACEM.NS', 'ACC.NS', 'SIEMENS.NS',
    'ABB.NS', 'CUMMINSIND.NS', 'BANKBARODA.NS', 'PNB.NS', 'CANBK.NS',
    'INDIGO.NS', 'JUBLFOOD.NS', 'GODREJPROP.NS'
]
# If you want to test with fewer stocks initially, uncomment this:
# WATCHLIST = WATCHLIST[:10]

print(f"📊 Watchlist loaded: {len(WATCHLIST)} stocks")

# ============================================================
# TELEGRAM SENDER
# ============================================================

def send_telegram_message(message):
    """Send a message via Telegram bot with error handling"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Telegram credentials missing!")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code == 200:
            print(f"✅ Telegram sent: {message[:60]}...")
            return True
        else:
            print(f"❌ Telegram error: {response.status_code} - {response.text}")
            return False
    except requests.exceptions.Timeout:
        print("❌ Telegram timeout")
        return False
    except Exception as e:
        print(f"❌ Telegram exception: {e}")
        return False

# ============================================================
# MARKET HOURS CHECK (IST)
# ============================================================

def is_market_hours():
    """Check if current time is within market hours (9:15 AM - 3:30 PM IST)"""
    ist = pytz.timezone('Asia/Kolkata')
    now_ist = datetime.now(ist)

    # Weekend check (Saturday=5, Sunday=6)
    if now_ist.weekday() >= 5:
        return False

    # Market hours
    market_open = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)

    return market_open <= now_ist <= market_close

# ============================================================
# CORE SIGNAL DETECTION
# ============================================================

def check_signals(force=False):
    """
    Fetch latest 30-min data for all stocks and detect EMA crossovers.
    Sends Telegram alert when a new signal appears.
    
    Args:
        force (bool): If True, bypass market hours check (used for testing)
    """
    print(f"\n🔍 Checking signals at {datetime.now().strftime('%H:%M:%S')} IST")

    # Skip if market is closed (unless forced)
    if not force and not is_market_hours():
        print("⏰ Market closed. Skipping scan.")
        return

    signals_found = 0

    for ticker in WATCHLIST:
        try:
            # 1. Fetch data
            stock = yf.Ticker(ticker)
            df = stock.history(period="5d", interval=TIMEFRAME)

            if df.empty or len(df) < MIN_DATA_POINTS:
                continue

            # 2. Calculate EMAs
            df['EMA_9'] = df['Close'].ewm(span=FAST_EMA, adjust=False).mean()
            df['EMA_15'] = df['Close'].ewm(span=SLOW_EMA, adjust=False).mean()

            # 3. Detect crossover (current vs previous)
            current_ema9 = df['EMA_9'].iloc[-1]
            current_ema15 = df['EMA_15'].iloc[-1]
            prev_ema9 = df['EMA_9'].iloc[-2]
            prev_ema15 = df['EMA_15'].iloc[-2]

            current_candle = df.iloc[-1]
            prev_candle = df.iloc[-2]

            current_price = current_candle['Close']
            prev_high = prev_candle['High']
            prev_low = prev_candle['Low']

            signal_type = None
            entry_price = None
            sl_price = None
            tp_prices = {}

            # --- Bullish Crossover ---
            if prev_ema9 <= prev_ema15 and current_ema9 > current_ema15:
                signal_type = "BUY 🟢"
                entry_price = current_price
                sl_price = prev_low  # Stop Loss = low of crossover candle
                risk = entry_price - sl_price

                if risk > 0:
                    tp_ratios = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
                    for r in tp_ratios:
                        tp_prices[f"1:{r:.1f}"] = entry_price + (risk * r)

            # --- Bearish Crossover ---
            elif prev_ema9 >= prev_ema15 and current_ema9 < current_ema15:
                signal_type = "SELL 🔴"
                entry_price = current_price
                sl_price = prev_high  # Stop Loss = high of crossover candle
                risk = sl_price - entry_price

                if risk > 0:
                    tp_ratios = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
                    for r in tp_ratios:
                        tp_prices[f"1:{r:.1f}"] = entry_price - (risk * r)

            if signal_type is None:
                continue

            # 4. Prevent duplicate alerts (same ticker within DUPLICATE_WINDOW)
            last_sent = sent_signals.get(ticker)
            if last_sent and (datetime.now() - last_sent).total_seconds() < DUPLICATE_WINDOW:
                print(f"⏳ Skipping duplicate signal for {ticker}")
                continue

            # 5. Build alert message
            message = f"""
╔════════════════════════════════════════╗
║  🚨 <b>EMA CROSSOVER SIGNAL</b> 🚨
╠════════════════════════════════════════╣
║  <b>Ticker:</b> {ticker}
║  <b>Signal:</b> {signal_type}
║  <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST
║
║  📊 <b>Current Price:</b> ₹{current_price:.2f}
║  📉 <b>Stop Loss:</b> ₹{sl_price:.2f}
║  📈 <b>Risk per share:</b> ₹{abs(entry_price - sl_price):.2f}
║
║  🎯 <b>Take Profit Targets:</b>
"""
            for label, price in tp_prices.items():
                # Calculate percentage gain/loss
                if signal_type == "BUY 🟢":
                    pct = ((price - entry_price) / entry_price * 100)
                else:
                    pct = ((entry_price - price) / entry_price * 100)
                message += f"║    {label}: ₹{price:.2f} ({pct:+.2f}%)\n"

            message += f"""
║
║  💡 <b>Suggested Action:</b>
║  Entry @ ₹{entry_price:.2f}
║  SL @ ₹{sl_price:.2f}
║  Start with 1:1, trail to higher ratios
╚════════════════════════════════════════╝
"""

            # 6. Send alert
            if send_telegram_message(message):
                sent_signals[ticker] = datetime.now()
                signals_found += 1
                print(f"✅ Alert sent for {ticker} - {signal_type}")
            else:
                print(f"❌ Failed to send alert for {ticker}")

        except Exception as e:
            print(f"❌ Error checking {ticker}: {e}")
            time.sleep(0.5)  # Avoid hitting Yahoo rate limits

    if signals_found == 0:
        print("ℹ️ No new signals found.")

# ============================================================
# FLASK WEB APP (for Render)
# ============================================================

app = Flask(__name__)

@app.route('/')
def health_check():
    """Root health check for Render"""
    return "✅ EMA Alert Bot is running!", 200

@app.route('/ping')
def ping():
    """Ping endpoint to keep the app alive (used by cron-job.org)"""
    return "pong", 200

@app.route('/test_telegram')
def test_telegram():
    """Manual test to verify Telegram connection"""
    success = send_telegram_message("🧪 <b>Test Alert</b>\nBot is connected and working correctly!")
    if success:
        return "✅ Test message sent to Telegram!", 200
    else:
        return "❌ Failed to send test message. Check logs.", 500

@app.route('/force_check')
def force_check():
    """
    Force a signal scan immediately (bypasses market hours for testing)
    """
    # Run the check with force=True to skip market hours
    check_signals(force=True)
    return "✅ Manual check triggered! Check Telegram for alerts.", 200

@app.route('/status')
def status():
    """Show bot status"""
    now = datetime.now(pytz.timezone('Asia/Kolkata'))
    return {
        "status": "running",
        "time": now.strftime('%Y-%m-%d %H:%M:%S %Z'),
        "market_open": is_market_hours(),
        "stocks_watchlist": len(WATCHLIST),
        "duplicate_window_seconds": DUPLICATE_WINDOW,
        "sent_signals_count": len(sent_signals)
    }

# ============================================================
# SCHEDULER (runs in background thread)
# ============================================================

def run_scheduler():
    """Run the scheduler in a background thread"""
    # Schedule the job every 5 minutes
    schedule.every(5).minutes.do(check_signals)

    # Also run once at startup
    check_signals()

    while True:
        try:
            schedule.run_pending()
            time.sleep(10)
        except Exception as e:
            print(f"❌ Scheduler error: {e}")
            time.sleep(30)

# ============================================================
# STARTUP
# ============================================================

if __name__ == '__main__':
    print("=" * 60)
    print("🤖 EMA CROSSOVER ALERT BOT STARTING...")
    print("=" * 60)
    print(f"📊 Watchlist: {len(WATCHLIST)} stocks")
    print(f"⚡ Timeframe: {TIMEFRAME} | EMAs: {FAST_EMA}/{SLOW_EMA}")
    print(f"🕒 Market hours: 9:15 AM - 3:30 PM IST (Monday-Friday)")
    print(f"📱 Telegram: {'✅ Configured' if TELEGRAM_TOKEN != 'YOUR_BOT_TOKEN_HERE' else '❌ Missing Token'}")
    print("=" * 60)

    # Send startup notification
    if TELEGRAM_TOKEN != "YOUR_BOT_TOKEN_HERE" and TELEGRAM_CHAT_ID != "YOUR_CHAT_ID_HERE":
        send_telegram_message("🤖 <b>EMA Alert Bot is ONLINE!</b>\nMonitoring your watchlist for crossover signals.\n\n⏰ Will run every 5 minutes during market hours.")

    # Start the scheduler in a background thread
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    print("🔄 Scheduler thread started.")

    # Run Flask app
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Starting Flask server on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False)

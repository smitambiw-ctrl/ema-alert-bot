import os
import threading
import time
import schedule
from datetime import datetime

from flask import Flask

# ----------------------
# Optional: strategy imports
# ----------------------
# NOTE: Replace the body of check_signals() with your EMA crossover logic.

app = Flask(__name__)


def check_signals():
    """Your existing signal checking function.

    Replace the placeholder logic below with your EMA crossover logic.
    If you use Telegram bot sending, keep it here.
    """
    # Placeholder example (do nothing)
    # print(f"Checking signals at {datetime.utcnow().isoformat()}Z")
    return


def run_scheduler():
    """Run the scheduler in a background thread"""
    schedule.every(5).minutes.do(check_signals)

    # Run once at startup (useful for fast verification)
    try:
        check_signals()
    except Exception:
        # Avoid crashing the scheduler thread
        pass

    while True:
        schedule.run_pending()
        time.sleep(10)


@app.route('/')
def health_check():
    """Health check endpoint for Render and cron-job.org"""
    return "EMA Alert Bot is running!", 200


@app.route('/ping')
def ping():
    """Ping endpoint to keep the app alive"""
    return "pong", 200


if __name__ == '__main__':
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    port = int(os.environ.get('PORT', '10000'))
    # Render requires host=0.0.0.0
    app.run(host='0.0.0.0', port=port)


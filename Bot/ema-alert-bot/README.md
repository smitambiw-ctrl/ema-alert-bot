# EMA Alert Bot (Render-ready)

Flask web server + background scheduler (runs every 5 minutes).

## Endpoints
- `GET /`  -> health check
- `GET /ping` -> keep-alive ping

## Configuration
Set your Telegram bot token / chat id and EMA settings via environment variables inside `main.py` where you implement `check_signals()`.

## Run locally
```bash
cd ema-alert-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

Then open: http://localhost:10000/


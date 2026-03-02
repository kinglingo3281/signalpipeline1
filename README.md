# Signal Pipeline

A standalone Python signal engine that generates trading signals from exchange data via CCXT and delivers them to multiple endpoints — Telegram for notifications and an SSE server for real-time client distribution.

## Architecture

This is one of multiple signal pipelines that feed into a central SSE server, which then streams signals to a trading terminal client:

```
                                        ┌─────────────────┐
  ┌──────────────────┐   webhook POST   │                 │   SSE stream
  │  Signal Pipeline │ ───────────────> │   SSE Server    │ ────────────> Trading Terminal
  │  (this repo)     │                  │                 │
  └──────────────────┘                  └─────────────────┘
         │                                      ▲
         │ Telegram                              │ file watcher
         ▼                                      │
  ┌──────────────────┐               ┌─────────────────┐
  │  Telegram Bot    │               │ Analysis Pipeline│
  │  (notifications) │               │ (writes JSON)    │
  └──────────────────┘               └─────────────────┘
```

### Signal Flow

1. **Data fetch** — CCXT pulls OHLCV candle data from exchanges (Gate.io primary, Binance/Bybit fallback)
2. **Local calculation** — ATR, support/resistance levels, Fibonacci retracements computed with pandas
3. **Signal generation** — Engine evaluates price vs pivots, groups, and risk parameters to produce long/short scalping signals
4. **Multi-delivery**:
   - **Telegram** — Formatted signal message sent to your bot
   - **SSE Server webhook** — Signal POSTed to the SSE server's `/api/v3-signal` endpoint for real-time client distribution

## Features

- Direct data acquisition from exchanges via CCXT (no external API keys needed)
- Local calculation of ATR and support/resistance levels
- Configurable signal generation with rate limiting per asset
- Telegram delivery with formatted messages
- Webhook delivery to SSE server for trading terminal integration
- Web UI for managing all configuration (pairs, risk, notifications, schedule)
- Scheduled execution at configurable intervals
- Signal deduplication and tracking

## Setup

### Prerequisites

- Python 3.8 or higher
- A Telegram bot with a webhook URL

### Installation

1. Clone the repository
2. Install the required packages:

```bash
pip install -r requirements.txt
```

3. Edit `config.py` or use the web UI to configure:
   - Telegram webhook URL
   - Trading pairs list
   - Risk parameters (default: 0.3% per trade)
   - Default vault balance (default: $500)
   - Execution schedule (default: every 30 minutes)

### Running

**Signal engine (headless):**
```bash
python main.py
```

**Web UI (configuration dashboard):**
```bash
python ui_server.py
```
Then open `http://localhost:5000` in your browser.

## Components

| File | Purpose |
|------|---------|
| `main.py` | Orchestrator — runs signal generation on schedule |
| `config.py` | Static default configuration |
| `config_manager.py` | Dynamic config manager — reads/writes JSON config files |
| `data_provider.py` | CCXT data fetcher — OHLCV, ATR, support/resistance calculation |
| `signal_engine.py` | Core signal generation algorithm |
| `signal_tracker.py` | Signal deduplication and rate limiting |
| `telegram_sender.py` | Multi-endpoint delivery (Telegram + SSE webhook) |
| `ui_server.py` | Flask web UI for configuration management |
| `config/` | JSON config files (pairs, risk, notifications, schedule, etc.) |
| `templates/` | HTML templates for the web UI |

## Configuration (via Web UI or JSON)

- **Trading Pairs** — Which assets to monitor (`config/trading_pairs.json`)
- **Risk Parameters** — Vault balance, long/short risk % (`config/risk_parameters.json`)
- **Signal Parameters** — Detailed engine tuning (`config/signal_parameters.json`)
- **Signal Limits** — Max signals per period per direction (`config/signal_limits.json`)
- **Notifications** — Telegram webhook URL and enable/disable (`config/notification.json`)
- **Schedule** — Which minutes past the hour to run (`config/schedule.json`)
- **Data Parameters** — ATR interval, price interval, result count (`config/data_parameters.json`)

## Monitoring

All system activities are logged to:
- Console output
- `trading_signals.log` file

## Troubleshooting

- **No signals generated** — Check exchange connectivity and symbol availability
- **Signal generation errors** — Inspect the log file for details
- **Telegram delivery failures** — Verify the webhook URL is correct
- **SSE webhook failures** — Ensure the SSE server is running and accessible

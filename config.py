"""
Configuration module for the trading signal system.
Centralizes all configurable parameters in one place.
"""

# Exchange configuration
EXCHANGE = "gateio"  # Primary exchange for data fetching via CCXT

# Trading pairs to monitor (replace with your actual pairs)
TRADING_PAIRS = [
    "WIFI/USDT",
    "BCH/USDT", 
    "MKR/USDT", 
    "JUP/USDT", 
    "TIA/USDT",
    "APT/USDT", 
    "HYPE/USDT", 
    "MOVE/USDT", 
    "POPCAT/USDT", 
    "WLD/USDT", 
    "AIXBT/USDT", 
    "INJ/USDT"
]

# Telegram configuration
# Configured with your Telegram chat ID
TELEGRAM_WEBHOOK_URL = "https://api.telegram.org/bot[YOUR_BOT_TOKEN]/sendMessage?chat_id=[YOUR_CHAT_ID]"

# Risk management
DEFAULT_VAULT_BALANCE = 500  # Default balance for position sizing
LONG_RISK = 0.003            # Risk per trade for long positions (0.3%)
SHORT_RISK = 0.003           # Risk per trade for short positions (0.3%)

# Data fetching configuration
ATR_INTERVAL = "1h"          # Interval for ATR calculation
PRICE_INTERVAL = "5m"        # Interval for price data
PRICE_RESULTS = 300          # Number of price results to fetch

# Execution schedule
RUN_AT_MINUTES = [1, 31]    # Run at 01 and 31 minutes past each hour

# Development settings
DEV_MODE = False          # When True, bypasses rate limiting for signals
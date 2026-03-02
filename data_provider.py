"""
Data Provider module.
Fetches price data and calculates technical indicators using CCXT + pandas.
"""

import logging
import time
import ccxt
import pandas as pd
from config_manager import ConfigManager

logger = logging.getLogger('DataProvider')

class DataProvider:
    """
    Handles all data acquisition from exchanges via CCXT.
    Fetches OHLCV data and calculates ATR, support/resistance locally.
    """
    
    def __init__(self):
        """Initialize the Data Provider with CCXT exchanges"""
        self.config_manager = ConfigManager()
        
        # Get exchange info from config
        api_credentials = self.config_manager.get_api_credentials()
        self.primary_exchange = api_credentials.get('primary_exchange', 'gateio')
        self.backup_exchanges = api_credentials.get('backup_exchanges', [])
        
        # For backward compatibility
        if 'exchange' in api_credentials and 'primary_exchange' not in api_credentials:
            self.primary_exchange = api_credentials.get('exchange')
        
        # Initialize CCXT exchanges (no API keys needed for public data)
        self.exchanges = {}
        all_exchange_names = [self.primary_exchange] + self.backup_exchanges
        
        for name in all_exchange_names:
            try:
                # Get the exchange class from ccxt module
                exchange_class = getattr(ccxt, name, None)
                if exchange_class is None:
                    logger.warning(f"Exchange {name} not found in CCXT")
                    continue
                    
                self.exchanges[name] = exchange_class({
                    'enableRateLimit': True,
                    'timeout': 30000,
                })
                logger.info(f"Initialized CCXT exchange: {name}")
            except Exception as e:
                logger.warning(f"Failed to initialize exchange {name}: {e}")
        
        # Get data parameters from config
        self.data_params = self.config_manager.get_data_parameters()
        
        # Get risk parameters from config
        self.risk_params = self.config_manager.get_risk_parameters()
    
    def get_support_resistance(self, symbol, retries=3, backoff=2, exchange=None):
        """
        Calculate support/resistance levels locally using CCXT daily OHLCV data
        
        Args:
            symbol (str): Trading pair symbol (e.g., "BTC/USDT")
            retries (int): Number of retry attempts
            backoff (int): Exponential backoff factor
            exchange (str): Exchange to use, defaults to primary exchange
            
        Returns:
            dict: Dictionary with support and resistance levels or None if failed
        """
        # Build list of exchanges to try
        if exchange is not None:
            exchanges_to_try = [exchange]
        else:
            exchanges_to_try = [self.primary_exchange] + self.backup_exchanges
        
        # Need at least 14 days of daily data
        limit = 30  # Get 30 days for safety
        
        for exch_name in exchanges_to_try:
            if exch_name not in self.exchanges:
                logger.warning(f"Exchange {exch_name} not initialized, skipping")
                continue
                
            exch = self.exchanges[exch_name]
            
            for attempt in range(retries):
                try:
                    logger.info(f"Fetching daily OHLCV for S/R: {symbol} from {exch_name}")
                    
                    ohlcv = exch.fetch_ohlcv(symbol, '1d', limit=limit)
                    
                    if not ohlcv or len(ohlcv) < 14:
                        logger.warning(f"Insufficient daily data from {exch_name}: got {len(ohlcv) if ohlcv else 0}")
                        break  # Try next exchange
                    
                    # Create DataFrame
                    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    
                    # Calculate resistance levels (highs over various periods)
                    # Calculate support levels (lows over various periods)
                    sr_data = {
                        "resistance": {
                            "max_14d": float(df['high'].tail(14).max()),
                            "max_7d": float(df['high'].tail(7).max()),
                            "max_4d": float(df['high'].tail(4).max()),
                            "max_1d": float(df['high'].iloc[-1]),
                        },
                        "support": {
                            "swing_low": float(df['low'].tail(14).min()),  # Simplified swing low
                            "min_14d": float(df['low'].tail(14).min()),
                            "min_7d": float(df['low'].tail(7).min()),
                            "min_4d": float(df['low'].tail(4).min()),
                        }
                    }
                    
                    # Log the values retrieved
                    resistance_values = [v for v in sr_data["resistance"].values() if v is not None]
                    support_values = [v for v in sr_data["support"].values() if v is not None]
                    
                    logger.info(f"Retrieved {len(resistance_values)} resistance levels and {len(support_values)} support levels from {exch_name}")
                    logger.debug(f"Resistance: {sr_data['resistance']}")
                    logger.debug(f"Support: {sr_data['support']}")
                    return sr_data
                    
                except ccxt.RateLimitExceeded:
                    wait_time = backoff ** attempt
                    logger.warning(f"Rate limited on {exch_name}, waiting {wait_time}s")
                    time.sleep(wait_time)
                    
                except ccxt.ExchangeError as e:
                    logger.error(f"Exchange error calculating S/R from {exch_name}: {e}")
                    break  # Try next exchange
                    
                except Exception as e:
                    logger.error(f"Error calculating S/R from {exch_name}: {e}")
                    break  # Try next exchange
        
        logger.error(f"Failed to calculate S/R for {symbol}")
        return None

    def get_atr(self, symbol, retries=3, backoff=2, exchange=None, period=14):
        """
        Calculate ATR locally using CCXT OHLCV data + pandas
        
        Args:
            symbol (str): Trading pair symbol (e.g., "BTC/USDT")
            retries (int): Number of retry attempts
            backoff (int): Exponential backoff factor
            exchange (str): Exchange to use, defaults to primary exchange
            period (int): ATR period (default 14)
            
        Returns:
            float: ATR value or None if failed
        """
        # Build list of exchanges to try
        if exchange is not None:
            exchanges_to_try = [exchange]
        else:
            exchanges_to_try = [self.primary_exchange] + self.backup_exchanges
        
        # ATR uses 1h timeframe per config
        timeframe = self.data_params.get('intervals', {}).get('atr', '1h')
        
        # Need period + extra candles for ATR calculation
        limit = period + 50
        
        for exch_name in exchanges_to_try:
            if exch_name not in self.exchanges:
                logger.warning(f"Exchange {exch_name} not initialized, skipping")
                continue
                
            exch = self.exchanges[exch_name]
            
            for attempt in range(retries):
                try:
                    logger.info(f"Fetching OHLCV for ATR: {symbol} from {exch_name} ({timeframe})")
                    
                    ohlcv = exch.fetch_ohlcv(symbol, timeframe, limit=limit)
                    
                    if not ohlcv or len(ohlcv) < period + 1:
                        logger.warning(f"Insufficient data for ATR from {exch_name}: got {len(ohlcv) if ohlcv else 0}")
                        break  # Try next exchange
                    
                    # Create DataFrame
                    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    
                    # Calculate True Range components
                    df['prev_close'] = df['close'].shift(1)
                    df['tr1'] = df['high'] - df['low']
                    df['tr2'] = abs(df['high'] - df['prev_close'])
                    df['tr3'] = abs(df['low'] - df['prev_close'])
                    
                    # True Range is the max of the three components
                    df['true_range'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
                    
                    # ATR is the Simple Moving Average of True Range
                    df['atr'] = df['true_range'].rolling(window=period).mean()
                    
                    # Get latest ATR value
                    atr_value = df['atr'].iloc[-1]
                    
                    if pd.isna(atr_value):
                        logger.warning(f"ATR calculation returned NaN from {exch_name}")
                        break  # Try next exchange
                    
                    atr_float = float(atr_value)
                    logger.info(f"ATR for {symbol}: {atr_float:.6f}")
                    return atr_float
                    
                except ccxt.RateLimitExceeded:
                    wait_time = backoff ** attempt
                    logger.warning(f"Rate limited on {exch_name}, waiting {wait_time}s")
                    time.sleep(wait_time)
                    
                except ccxt.ExchangeError as e:
                    logger.error(f"Exchange error calculating ATR from {exch_name}: {e}")
                    break  # Try next exchange
                    
                except Exception as e:
                    logger.error(f"Error calculating ATR from {exch_name}: {e}")
                    break  # Try next exchange
        
        logger.error(f"Failed to calculate ATR for {symbol}")
        return None
    
    def get_prices(self, symbol, retries=3, backoff=2, exchange=None):
        """
        Get historical close prices for a symbol using CCXT
        
        Args:
            symbol (str): Trading pair symbol (e.g., "BTC/USDT")
            retries (int): Number of retry attempts
            backoff (int): Exponential backoff factor
            exchange (str): Exchange to use, defaults to primary
            
        Returns:
            list: List of close price floats (target: 200-300 points)
        """
        # Build list of exchanges to try
        if exchange is not None:
            exchanges_to_try = [exchange]
        else:
            exchanges_to_try = [self.primary_exchange] + self.backup_exchanges
        
        # Get timeframe and limit from config
        timeframe = self.data_params.get('intervals', {}).get('price', '5m')
        limit = self.data_params.get('results', {}).get('price', 300)
        
        for exch_name in exchanges_to_try:
            if exch_name not in self.exchanges:
                logger.warning(f"Exchange {exch_name} not initialized, skipping")
                continue
                
            exch = self.exchanges[exch_name]
            
            for attempt in range(retries):
                try:
                    logger.info(f"Fetching {limit} candles for {symbol} from {exch_name} ({timeframe})")
                    
                    # CCXT fetch_ohlcv returns [[timestamp, open, high, low, close, volume], ...]
                    ohlcv = exch.fetch_ohlcv(symbol, timeframe, limit=limit)
                    
                    if not ohlcv:
                        logger.warning(f"{exch_name} returned empty data for {symbol}")
                        break  # Try next exchange
                    
                    if len(ohlcv) < 15:
                        logger.warning(f"{exch_name} returned only {len(ohlcv)} candles for {symbol}")
                        break  # Try next exchange
                    
                    # Extract close prices (index 4 in OHLCV)
                    prices = [float(candle[4]) for candle in ohlcv]
                    
                    logger.info(f"Success: Got {len(prices)} prices from {exch_name} for {symbol}")
                    logger.debug(f"Price range: {min(prices):.4f} - {max(prices):.4f}")
                    return prices
                    
                except ccxt.RateLimitExceeded:
                    wait_time = backoff ** attempt
                    logger.warning(f"Rate limited on {exch_name}, waiting {wait_time}s")
                    time.sleep(wait_time)
                    
                except ccxt.NetworkError as e:
                    logger.warning(f"Network error on {exch_name}: {e}")
                    time.sleep(backoff ** attempt)
                    
                except ccxt.ExchangeError as e:
                    logger.error(f"Exchange error on {exch_name} for {symbol}: {e}")
                    break  # Try next exchange - symbol might not exist
                    
                except Exception as e:
                    logger.error(f"Unexpected error fetching prices from {exch_name}: {e}")
                    break  # Try next exchange
        
        logger.error(f"All exchanges failed to get prices for {symbol}")
        return []
    
    def get_all_pair_data(self, symbol):
        """
        Get all required data for a trading pair
        
        Args:
            symbol (str): Trading pair symbol (e.g., "WIFI/USDT")
            
        Returns:
            dict: All data required for signal generation
        """
        logger.info(f"Getting all data for {symbol}")
        try:
            # Get prices first (most important)
            prices = self.get_prices(symbol)
            
            # Track which exchange was successfully used
            used_exchange = self.primary_exchange
            
            # Check if we got prices from a backup exchange
            if not prices and self.backup_exchanges:
                for backup_exchange in self.backup_exchanges:
                    prices = self.get_prices(symbol, exchange=backup_exchange)
                    if prices:
                        used_exchange = backup_exchange
                        logger.info(f"Using backup exchange {used_exchange} for {symbol}")
                        break
            
            # For signal generation, we'll need at least some data points
            # Let's reduce the minimum required from 30 to 15 since we're limited by the API
            if not prices or len(prices) < 15:  # Ensure we have enough data
                logger.error(f"Insufficient price data for {symbol}, got {len(prices) if prices else 0} points")
                return None
                
            logger.info(f"Successfully retrieved {len(prices)} price points for {symbol}")
            
            # Get current price (last price)
            current_price = prices[-1]
            
            # Calculate price85Value (THE CORE OF THE SIGNAL)
            sorted_prices = sorted(prices)
            price85_index = int(len(sorted_prices) * 0.85)
            price85_value = sorted_prices[price85_index]
            
            # Get ATR using the same exchange that worked for prices
            logger.info(f"Using exchange {used_exchange} to get ATR for {symbol}")
            atr = self.get_atr(symbol, retries=4, backoff=2, exchange=used_exchange)
            
            if atr is None:
                logger.error(f"Failed to get ATR for {symbol}")
                return None
                
            logger.info(f"Successfully retrieved ATR value of {atr} for {symbol}")
            
            # Calculate Fibonacci levels from the entire price array
            # Changed to match Zapier implementation which uses full dataset
            recent_prices = prices
            recent_high = max(recent_prices)
            recent_low = min(recent_prices)
            range_diff = recent_high - recent_low
            
            fibo_levels = {
                'FIBO786': recent_low + 0.786 * range_diff,
                'FIBO618': recent_low + 0.618 * range_diff,
                'FIBO500': recent_low + 0.500 * range_diff,
                'FIBO382': recent_low + 0.382 * range_diff,
                'FIBO236': recent_low + 0.236 * range_diff
            }
            
            # Fetch support and resistance levels using CCXT
            sr_data = self.get_support_resistance(symbol, retries=4, backoff=2, exchange=used_exchange)
            
            if sr_data is None:
                logger.error(f"Failed to get support/resistance data for {symbol}")
                return None
                
            logger.info(f"Successfully retrieved support/resistance data for {symbol}")
            
            # Process the support and resistance levels
            try:
                # Extract resistance and support levels
                resistance_data = sr_data.get('resistance', {})
                support_data = sr_data.get('support', {})
                
                # Collect all valid resistance levels
                resistance_levels = []
                for name, value in resistance_data.items():
                    if value and value > 0:
                        resistance_levels.append(float(value))
                        logger.info(f"Added resistance level from {name}: {value:.4f}")
                
                # Collect all valid support levels
                support_levels = []
                for name, value in support_data.items():
                    if value and value > 0:
                        support_levels.append(float(value))
                        logger.info(f"Added support level from {name}: {value:.4f}")
                
                # Sort levels from highest to lowest
                resistance_levels.sort(reverse=True)
                support_levels.sort()
                
                logger.info(f"Found {len(resistance_levels)} resistance and {len(support_levels)} support levels")
                
                # Setup pivot points using resistance and support levels
                # Assign the four pivot points using resistance and support levels
                if len(resistance_levels) >= 3 and len(support_levels) >= 1:
                    # Use top 3 resistance levels and top 1 support level
                    pivot = resistance_levels[0]  # Highest resistance
                    r1 = resistance_levels[1]     # Second highest resistance
                    r2 = resistance_levels[2]     # Third highest resistance
                    s1 = support_levels[0]        # Highest support (lowest price)
                    
                elif len(resistance_levels) >= 2 and len(support_levels) >= 2:
                    # Use top 2 resistance levels and top 2 support levels
                    pivot = resistance_levels[0]  # Highest resistance
                    r1 = resistance_levels[1]     # Second highest resistance 
                    r2 = support_levels[1]        # Second highest support
                    s1 = support_levels[0]        # Highest support (lowest price)
                    
                elif len(resistance_levels) >= 1 and len(support_levels) >= 1:
                    # Use available levels and derive the rest
                    pivot = resistance_levels[0]  # Highest resistance
                    r1 = pivot * 0.99            # Slightly below highest resistance
                    r2 = support_levels[0] * 1.05 # Above highest support
                    s1 = support_levels[0]        # Highest support
                    
                else:
                    # Fallback if we don't have enough levels
                    logger.warning(f"Not enough resistance/support levels, using fallback calculation")
                    pivot = recent_high           # Use recent high as pivot
                    r1 = recent_high * 0.97       # 3% below high
                    r2 = recent_high * 0.94       # 6% below high
                    s1 = recent_low               # Use recent low as support
                
                # Setup 10 group levels using resistance and support levels (more spread out)
                group_levels = []
                
                # Add all resistance levels to group levels
                for level in resistance_levels:
                    if len(group_levels) < 5:  # Use up to 5 resistance levels
                        group_levels.append(level)
                
                # Add all support levels to group levels
                for level in support_levels:
                    if len(group_levels) < 10:  # Fill up to 10 total levels
                        group_levels.append(level)
                
                # If we still need more levels, generate them between highest and lowest
                if len(group_levels) < 10:
                    highest = max(group_levels) if group_levels else recent_high
                    lowest = min(group_levels) if group_levels else recent_low
                    range_diff = highest - lowest
                    
                    # Calculate how many more levels we need
                    levels_needed = 10 - len(group_levels)
                    
                    # Generate evenly distributed levels between highest and lowest
                    for i in range(1, levels_needed + 1):
                        new_level = lowest + (range_diff * i / (levels_needed + 1))
                        group_levels.append(new_level)
                
                # Ensure we have exactly 10 group levels sorted from highest to lowest
                group_levels = sorted(group_levels, reverse=True)[:10]
                
                # If we don't have enough levels (less than 10), add more
                while len(group_levels) < 10:
                    # We'll add levels near the existing ones with small variations
                    if len(group_levels) % 2 == 0:  # Even - add near the top
                        base_level = group_levels[0] if group_levels else recent_high
                        new_level = base_level * (1 - 0.01 * len(group_levels))
                    else:  # Odd - add near the bottom
                        base_level = group_levels[-1] if group_levels else recent_low
                        new_level = base_level * (1 + 0.01 * len(group_levels))
                    group_levels.append(new_level)
                    # Re-sort after each addition
                    group_levels = sorted(group_levels, reverse=True)
                
                # Extract the group values
                group1, group2, group3, group4, group5 = group_levels[0:5]
                group6, group7, group8, group9, group10 = group_levels[5:10]
                
                logger.info(f"Successfully processed S/R levels from simple method:")
                logger.info(f"Pivot={pivot:.4f}, R1={r1:.4f}, R2={r2:.4f}, S1={s1:.4f}")
                logger.info(f"Group levels range: {group1:.4f} to {group10:.4f}")
                
                # Log the distribution of values
                value_range = max(group_levels) - min(group_levels)
                logger.info(f"S/R level range: {value_range:.4f} ({min(group_levels):.4f} - {max(group_levels):.4f})")
                logger.info(f"Group levels: {', '.join([f'{g:.4f}' for g in group_levels])}")
                
            except Exception as e:
                logger.error(f"Error processing S/R data: {e}")
                # Fallback to standard calculation if processing fails
                logger.warning(f"Using fallback calculation for pivot and group levels")
                pivot = (recent_high + recent_low + prices[-1]) / 3
                r1 = (2 * pivot) - recent_low
                r2 = pivot + (recent_high - recent_low)
                s1 = (2 * pivot) - recent_high
                s2 = pivot - (recent_high - recent_low)
                
                # Generate group levels as fallback
                group1 = recent_high * 0.98
                group2 = recent_high * 0.96
                group3 = recent_high * 0.94
                group4 = recent_high * 0.92
                group5 = recent_low * 1.08
                group6 = recent_low * 1.06
                group7 = recent_low * 1.04
                group8 = recent_low * 1.02
                group9 = (recent_high + recent_low) / 2 * 0.99
                group10 = (recent_high + recent_low) / 2 * 1.01
            # Handle the case when no valid support/resistance data is available
            if not sr_data or (not sr_data.get('resistance') and not sr_data.get('support')):
                # Fallback to standard pivot calculation if API doesn't return expected format
                logger.warning(f"Support/resistance API returned no data, using fallback calculation")
                last_price = prices[-1]  # Last price (close)
                pivot = recent_high         # Use recent high as pivot
                r1 = recent_high * 0.97     # 3% below high
                r2 = recent_high * 0.94     # 6% below high
                s1 = recent_low             # Use recent low as support
            
            # Determine market bias - adjust for fewer data points
            short_ma = sum(prices[-min(len(prices), 10):]) / min(len(prices), 10)
            long_ma = sum(prices) / len(prices)
            
            if short_ma > long_ma * 1.03:
                bullish = "On"  # Bullish
            elif short_ma < long_ma * 0.97:
                bullish = "Off"  # Bearish
            else:
                bullish = "NA"  # Neutral
            
            # For standard calculation case, also calculate group levels
            if 'group1' not in locals():
                # Calculate group levels using standard formulas
                group1 = recent_low * 0.985
                group2 = recent_low * 0.995
                group3 = recent_low * 1.005
                group4 = recent_low * 1.015
                group5 = recent_high * 0.985
                group6 = recent_high * 0.995
                group7 = recent_high * 1.005
                group8 = recent_high * 1.015
                group9 = (recent_high + recent_low) / 2 * 0.99
                group10 = (recent_high + recent_low) / 2 * 1.01
                
            # Build data dictionary (same structure as inputData in JS)
            # Ensure all values are properly converted to strings where needed
            pair_data = {
                "Pair": symbol,
                "price": ",".join(map(str, prices)),  # Join prices as comma-separated string
                "ATR": str(atr),  # Convert ATR to string to avoid formatting issues
                "Bullish": bullish,
                "Vault": str(self.risk_params.get('default_vault_balance', 500)),
                
                # Fibonacci levels
                "FIBO786": fibo_levels['FIBO786'],
                "FIBO618": fibo_levels['FIBO618'],
                "FIBO500": fibo_levels['FIBO500'],
                "FIBO382": fibo_levels['FIBO382'],
                "FIBO236": fibo_levels['FIBO236'],
                
                # Pivot levels (from sup-res API or calculations)
                "pivot1": pivot,
                "pivot2": r1,
                "pivot3": r2,
                "pivot4": s1,
                
                # Group levels (from API or calculations)
                "group1": group1,
                "group2": group2,
                "group3": group3,
                "group4": group4,
                "group5": group5,
                "group6": group6,
                "group7": group7,
                "group8": group8,
                "group9": group9,
                "group10": group10
            }
            
            logger.info(f"Successfully prepared all data for {symbol}")
            return pair_data
            
        except Exception as e:
            logger.error(f"Error getting all pair data for {symbol}: {e}")
            return None
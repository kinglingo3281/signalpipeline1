"""
Configuration Manager module.
Handles loading, validating, and saving configuration from JSON files.
Implements file locking to prevent concurrent read/write issues.
"""

import json
import os
import logging
import time
import tempfile
import shutil
import random
from pathlib import Path

logger = logging.getLogger('ConfigManager')

class ConfigManager:
    """
    Handles loading and saving configuration settings from JSON files.
    Implements file locking to prevent concurrent access issues.
    """
    
    def __init__(self, config_dir=None):
        """Initialize the Configuration Manager"""
        if config_dir is None:
            # Default to 'config' directory in the same location as this file
            self.config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config')
        else:
            self.config_dir = config_dir
            
        # Ensure config directory exists
        os.makedirs(self.config_dir, exist_ok=True)
        
        # Define config file paths
        self.trading_pairs_file = os.path.join(self.config_dir, 'trading_pairs.json')
        self.api_credentials_file = os.path.join(self.config_dir, 'api_credentials.json')
        self.risk_parameters_file = os.path.join(self.config_dir, 'risk_parameters.json')
        self.data_parameters_file = os.path.join(self.config_dir, 'data_parameters.json')
        self.schedule_file = os.path.join(self.config_dir, 'schedule.json')
        self.signal_limits_file = os.path.join(self.config_dir, 'signal_limits.json')
        self.notification_file = os.path.join(self.config_dir, 'notification.json')
        self.signal_parameters_file = os.path.join(self.config_dir, 'signal_parameters.json')
        
        # Cache for configurations to avoid frequent disk reads
        self.config_cache = {}
        
    def _acquire_lock(self, file_path, timeout=5):
        """
        Acquire a lock on a file using lockfile approach
        
        Args:
            file_path (str): Path to the file to lock
            timeout (int): Maximum time to wait for lock in seconds
            
        Returns:
            bool: True if lock acquired, False otherwise
        """
        lock_file = f"{file_path}.lock"
        start_time = time.time()
        
        # Create the file if it doesn't exist
        if not os.path.exists(file_path):
            with open(file_path, 'w') as f:
                f.write('{}')
        
        while time.time() - start_time < timeout:
            try:
                # Try to create the lock file
                if not os.path.exists(lock_file):
                    with open(lock_file, 'w') as f:
                        f.write(str(os.getpid()))
                    return True
                else:
                    # Check if the lock is stale (older than 30 seconds)
                    if os.path.exists(lock_file) and time.time() - os.path.getmtime(lock_file) > 30:
                        os.remove(lock_file)
                        continue
                        
                    # File is locked by another process
                    logger.debug(f"Waiting for lock on {file_path}")
                    time.sleep(0.1 + random.uniform(0, 0.1))  # Add jitter to avoid deadlocks
            except Exception as e:
                logger.error(f"Error acquiring lock: {e}")
                time.sleep(0.2)
                
        logger.error(f"Could not acquire lock on {file_path} after {timeout} seconds")
        return False
    
    def _release_lock(self, file_path):
        """
        Release a lock on a file
        
        Args:
            file_path (str): Path to the file to unlock
        """
        lock_file = f"{file_path}.lock"
        try:
            if os.path.exists(lock_file):
                os.remove(lock_file)
        except Exception as e:
            logger.error(f"Error releasing file lock: {e}")
    
    def _read_config_file(self, file_path, default=None):
        """
        Read a configuration file with locking
        
        Args:
            file_path (str): Path to the configuration file
            default (dict): Default configuration if file doesn't exist or is invalid
            
        Returns:
            dict: Configuration data
        """
        if default is None:
            default = {}
            
        # Check if in cache and not in development mode
        cache_key = os.path.basename(file_path)
        if cache_key in self.config_cache:
            return self.config_cache[cache_key]
            
        try:
            if self._acquire_lock(file_path):
                try:
                    with open(file_path, 'r') as f:
                        config_data = json.load(f)
                    # Update cache
                    self.config_cache[cache_key] = config_data
                    return config_data
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON in {file_path}, using default configuration")
                    return default
                except FileNotFoundError:
                    logger.warning(f"Configuration file {file_path} not found, using default configuration")
                    return default
                except Exception as e:
                    logger.error(f"Error reading {file_path}: {e}")
                    return default
                finally:
                    self._release_lock(file_path)
            else:
                logger.error(f"Failed to acquire lock on {file_path}, using default configuration")
                return default
        except Exception as e:
            logger.error(f"Unexpected error reading config: {e}")
            return default
    
    def _write_config_file(self, file_path, config_data):
        """
        Write a configuration file with locking and atomic operations
        
        Args:
            file_path (str): Path to the configuration file
            config_data (dict): Configuration data to write
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if self._acquire_lock(file_path):
                try:
                    # Write to a temporary file first (atomic write)
                    temp_fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(file_path))
                    with os.fdopen(temp_fd, 'w') as temp_file:
                        json.dump(config_data, temp_file, indent=2)
                        
                    # Replace the target file with our temporary file (atomic operation on most filesystems)
                    shutil.move(temp_path, file_path)
                    
                    # Update cache
                    cache_key = os.path.basename(file_path)
                    self.config_cache[cache_key] = config_data
                    
                    return True
                except Exception as e:
                    logger.error(f"Error writing {file_path}: {e}")
                    return False
                finally:
                    self._release_lock(file_path)
            else:
                logger.error(f"Failed to acquire lock on {file_path}")
                return False
        except Exception as e:
            logger.error(f"Unexpected error writing config: {e}")
            return False
            
    def get_trading_pairs_config(self):
        """
        Get the complete trading pairs configuration
        
        Returns:
            dict: Trading pairs configuration
        """
        default = {"pairs": [{"symbol": "BTC/USDT", "enabled": True}]}
        return self._read_config_file(self.trading_pairs_file, default)
    
    def get_trading_pairs(self):
        """
        Get the list of trading pairs to monitor
        
        Returns:
            list: List of enabled trading pair symbols
        """
        config = self.get_trading_pairs_config()
        
        # Extract just the symbols of enabled pairs
        enabled_pairs = [pair["symbol"] for pair in config.get("pairs", []) if pair.get("enabled", True)]
        
        if not enabled_pairs:
            logger.warning("No enabled trading pairs found, using default BTC/USDT")
            return ["BTC/USDT"]
            
        return enabled_pairs
    
    def add_trading_pair(self, symbol, enabled=True):
        """
        Add a new trading pair
        
        Args:
            symbol (str): Trading pair symbol (e.g., "ETH/USDT")
            enabled (bool): Whether the pair is enabled
            
        Returns:
            bool: True if successful, False otherwise
        """
        config = self._read_config_file(self.trading_pairs_file, {"pairs": []})
        
        # Check if pair already exists
        for pair in config.get("pairs", []):
            if pair.get("symbol") == symbol:
                pair["enabled"] = enabled
                return self._write_config_file(self.trading_pairs_file, config)
        
        # Add new pair
        config.get("pairs", []).append({"symbol": symbol, "enabled": enabled})
        return self._write_config_file(self.trading_pairs_file, config)
    
    def update_trading_pair(self, symbol, enabled):
        """
        Update the enabled status of a trading pair
        
        Args:
            symbol (str): Trading pair symbol (e.g., "ETH/USDT")
            enabled (bool): Whether the pair is enabled
            
        Returns:
            bool: True if successful, False otherwise
        """
        config = self._read_config_file(self.trading_pairs_file, {"pairs": []})
        
        found = False
        for pair in config.get("pairs", []):
            if pair.get("symbol") == symbol:
                pair["enabled"] = enabled
                found = True
                break
                
        if found:
            return self._write_config_file(self.trading_pairs_file, config)
        else:
            logger.warning(f"Trading pair {symbol} not found")
            return False
    
    def remove_trading_pair(self, symbol):
        """
        Remove a trading pair
        
        Args:
            symbol (str): Trading pair symbol (e.g., "ETH/USDT")
            
        Returns:
            bool: True if successful, False otherwise
        """
        config = self._read_config_file(self.trading_pairs_file, {"pairs": []})
        
        original_length = len(config.get("pairs", []))
        config["pairs"] = [pair for pair in config.get("pairs", []) if pair.get("symbol") != symbol]
        
        if len(config.get("pairs", [])) < original_length:
            return self._write_config_file(self.trading_pairs_file, config)
        else:
            logger.warning(f"Trading pair {symbol} not found")
            return False
    
    def get_api_credentials(self):
        """Get the API credentials from the config"""
        default = {
            "primary_exchange": "gateio",
            "backup_exchanges": ["binance", "bybit"]
        }
        credentials = self._read_config_file(self.api_credentials_file, default)
        
        # Handle backward compatibility with older config format
        if 'exchange' in credentials and 'primary_exchange' not in credentials:
            credentials['primary_exchange'] = credentials['exchange']
            credentials['backup_exchanges'] = []
            
        return credentials
    
    def update_api_credentials(self, primary_exchange=None, backup_exchanges=None):
        """
        Update API credentials
        
        Args:
            primary_exchange (str): Primary exchange name
            backup_exchanges (list): List of backup exchanges
            
        Returns:
            bool: True if successful, False otherwise
        """
        config = self._read_config_file(self.api_credentials_file, {
            "primary_exchange": "gateio",
            "backup_exchanges": ["binance", "bybit"]
        })
            
        if primary_exchange is not None:
            config["primary_exchange"] = primary_exchange
            
        if backup_exchanges is not None:
            config["backup_exchanges"] = backup_exchanges
            
        # For backward compatibility
        if "primary_exchange" in config:
            config["exchange"] = config["primary_exchange"]
            
        return self._write_config_file(self.api_credentials_file, config)
        
    def set_api_credentials(self, api_credentials):
        """
        Set the complete API credentials
        
        Args:
            api_credentials (dict): Complete API credentials dictionary
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Validate API credentials
        if not isinstance(api_credentials, dict):
            raise ValueError("API credentials must be a dictionary")
            
        # Handle both old and new config format
        if 'exchange' in api_credentials and 'primary_exchange' not in api_credentials:
            api_credentials['primary_exchange'] = api_credentials['exchange']
            api_credentials['backup_exchanges'] = []
            
        if 'primary_exchange' not in api_credentials:
            api_credentials['primary_exchange'] = "gateio"
            
        if 'backup_exchanges' not in api_credentials:
            api_credentials['backup_exchanges'] = []
            
        # For backward compatibility
        api_credentials['exchange'] = api_credentials['primary_exchange']
            
        # Save the API credentials
        return self._write_config_file(self.api_credentials_file, api_credentials)
    
    def get_risk_parameters(self):
        """
        Get risk management parameters
        
        Returns:
            dict: Risk management parameters
        """
        default = {
            "default_vault_balance": 500,
            "long_risk": 0.003,
            "short_risk": 0.003
        }
        return self._read_config_file(self.risk_parameters_file, default)
    
    def update_risk_parameters(self, default_vault_balance=None, long_risk=None, short_risk=None):
        """
        Update risk management parameters
        
        Args:
            default_vault_balance (float): Default vault balance
            long_risk (float): Risk per trade for long positions
            short_risk (float): Risk per trade for short positions
            
        Returns:
            bool: True if successful, False otherwise
        """
        config = self._read_config_file(self.risk_parameters_file, {
            "default_vault_balance": 500,
            "long_risk": 0.003,
            "short_risk": 0.003
        })
        
        if default_vault_balance is not None:
            config["default_vault_balance"] = default_vault_balance
            
        if long_risk is not None:
            config["long_risk"] = long_risk
            
        if short_risk is not None:
            config["short_risk"] = short_risk
            
        return self._write_config_file(self.risk_parameters_file, config)
    
    def get_data_parameters(self):
        """
        Get data fetching parameters
        
        Returns:
            dict: Data fetching parameters
        """
        default = {
            "intervals": {
                "atr": "1h",
                "price": "5m"
            },
            "results": {
                "price": 300
            }
        }
        return self._read_config_file(self.data_parameters_file, default)
    
    def update_data_parameters(self, atr_interval=None, price_interval=None, price_results=None):
        """
        Update data fetching parameters
        
        Args:
            atr_interval (str): Interval for ATR calculation
            price_interval (str): Interval for price data
            price_results (int): Number of price results to fetch
            
        Returns:
            bool: True if successful, False otherwise
        """
        config = self._read_config_file(self.data_parameters_file, {
            "intervals": {
                "atr": "1h",
                "price": "5m"
            },
            "results": {
                "price": 300
            }
        })
        
        if atr_interval is not None:
            if "intervals" not in config:
                config["intervals"] = {}
            config["intervals"]["atr"] = atr_interval
            
        if price_interval is not None:
            if "intervals" not in config:
                config["intervals"] = {}
            config["intervals"]["price"] = price_interval
            
        if price_results is not None:
            if "results" not in config:
                config["results"] = {}
            config["results"]["price"] = price_results
            
        return self._write_config_file(self.data_parameters_file, config)
    
    def get_schedule(self):
        """
        Get execution schedule parameters
        
        Returns:
            dict: Schedule parameters
        """
        default = {"run_at_minutes": [1, 31]}
        return self._read_config_file(self.schedule_file, default)
    
    def update_schedule(self, run_at_minutes=None):
        """
        Update execution schedule parameters
        
        Args:
            run_at_minutes (list): List of minutes to run at
            
        Returns:
            bool: True if successful, False otherwise
        """
        config = self._read_config_file(self.schedule_file, {"run_at_minutes": [1, 31]})
        
        if run_at_minutes is not None:
            # Validate minutes (0-59)
            validated_minutes = []
            for minute in run_at_minutes:
                if isinstance(minute, int) and 0 <= minute <= 59:
                    validated_minutes.append(minute)
                else:
                    logger.warning(f"Invalid minute value: {minute}, must be 0-59")
            
            if validated_minutes:
                config["run_at_minutes"] = validated_minutes
            else:
                logger.error("No valid minute values provided")
                return False
            
        return self._write_config_file(self.schedule_file, config)
    
    def get_notification(self):
        """
        Get notification parameters
        
        Returns:
            dict: Notification parameters
        """
        default = {
            "telegram": {
                "webhook_url": "",
                "enabled": True
            }
        }
        return self._read_config_file(self.notification_file, default)
    
    def update_notification(self, telegram_webhook_url=None, telegram_enabled=None):
        """
        Update notification parameters
        
        Args:
            telegram_webhook_url (str): Telegram webhook URL
            telegram_enabled (bool): Whether Telegram notifications are enabled
            
        Returns:
            bool: True if successful, False otherwise
        """
        config = self._read_config_file(self.notification_file, {
            "telegram": {
                "webhook_url": "",
                "enabled": True
            }
        })
        
        if telegram_webhook_url is not None:
            if "telegram" not in config:
                config["telegram"] = {}
            config["telegram"]["webhook_url"] = telegram_webhook_url
            
        if telegram_enabled is not None:
            if "telegram" not in config:
                config["telegram"] = {}
            config["telegram"]["enabled"] = telegram_enabled
            
        return self._write_config_file(self.notification_file, config)
    
    def get_signal_parameters(self):
        """
        Get signal generation parameters
        
        Returns:
            dict: Signal generation parameters
        """
        default = {
            "fibonacci_levels": {
                "level1": 0.786,
                "level2": 0.618,
                "level3": 0.500,
                "level4": 0.382,
                "level5": 0.236
            },
            "atr_multipliers": {
                "long_sl": 1.5,
                "long_tp": 2.0,
                "short_sl": 1.5,
                "short_tp": 2.0
            },
            "price_percentiles": {
                "counter_trend_percentile": 0.85
            },
            "support_resistance": {
                "minimum_distance_percent": 1.0,
                "maximum_distance_percent": 5.0
            }
        }
        return self._read_config_file(self.signal_parameters_file, default)
    
    def update_signal_parameters(self, fibonacci_levels=None, atr_multipliers=None, 
                              price_percentiles=None, support_resistance=None):
        """
        Update signal generation parameters
        
        Args:
            fibonacci_levels (dict): Fibonacci levels dictionary
            atr_multipliers (dict): ATR multipliers dictionary
            price_percentiles (dict): Price percentiles dictionary
            support_resistance (dict): Support/resistance parameters dictionary
            
        Returns:
            bool: True if successful, False otherwise
        """
        config = self._read_config_file(self.signal_parameters_file, {
            "fibonacci_levels": {
                "level1": 0.786,
                "level2": 0.618,
                "level3": 0.500,
                "level4": 0.382,
                "level5": 0.236
            },
            "atr_multipliers": {
                "long_sl": 1.5,
                "long_tp": 2.0,
                "short_sl": 1.5,
                "short_tp": 2.0
            },
            "price_percentiles": {
                "counter_trend_percentile": 0.85
            },
            "support_resistance": {
                "minimum_distance_percent": 1.0,
                "maximum_distance_percent": 5.0
            }
        })
        
        if fibonacci_levels is not None:
            config["fibonacci_levels"] = fibonacci_levels
            
        if atr_multipliers is not None:
            config["atr_multipliers"] = atr_multipliers
            
        if price_percentiles is not None:
            config["price_percentiles"] = price_percentiles
            
        if support_resistance is not None:
            config["support_resistance"] = support_resistance
            
        return self._write_config_file(self.signal_parameters_file, config)
    
    def get_signal_limits(self):
        """Get signal rate limiting configuration"""
        default = {
            "signal_period_hours": 6,
            "max_long_signals": 1,
            "max_short_signals": 1
        }
        return self._read_config_file(self.signal_limits_file, default)
        
    def update_signal_limits(self, signal_period_hours=None, max_long_signals=None, max_short_signals=None):
        """Update signal rate limiting configuration"""
        config = self.get_signal_limits()
        
        if signal_period_hours is not None:
            config['signal_period_hours'] = int(signal_period_hours)
        
        if max_long_signals is not None:
            config['max_long_signals'] = int(max_long_signals)
            
        if max_short_signals is not None:
            config['max_short_signals'] = int(max_short_signals)
            
        self._write_config_file(self.signal_limits_file, config)
        return config
    
    def clear_cache(self):
        """Clear the configuration cache to force reload from disk"""
        self.config_cache = {}
        logger.info("Configuration cache cleared")

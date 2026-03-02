import os
import json
import time
import logging
import threading
from datetime import datetime, timedelta
import sys

# Import config to check DEV_MODE
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger('SignalTracker')

class SignalTracker:
    """
    Tracks signals sent for each pair to enforce rate limiting
    """
    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        self.data_file = os.path.join('data', 'signal_history.json')
        self.lock = threading.Lock()
        
        # Create data directory if it doesn't exist
        os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
        
        # Default limits (will be overridden by config)
        self.signal_period_hours = 6
        self.max_long_signals = 1
        self.max_short_signals = 1
        
        # Load limits from config if available
        if self.config_manager:
            self._load_limits_from_config()
    
    def _load_limits_from_config(self):
        """Load signal limits from configuration"""
        try:
            limits = self.config_manager.get_signal_limits()
            self.signal_period_hours = limits.get('signal_period_hours', 6)
            self.max_long_signals = limits.get('max_long_signals', 1)
            self.max_short_signals = limits.get('max_short_signals', 1)
            logger.info(f"Loaded signal limits: {self.signal_period_hours}h period, "
                      f"{self.max_long_signals} long, {self.max_short_signals} short")
        except Exception as e:
            logger.error(f"Error loading signal limits: {e}")
    
    def _load_signal_history(self):
        """Load signal history from file"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"Error loading signal history: {e}")
            return {}
    
    def _save_signal_history(self, history):
        """Save signal history to file"""
        try:
            with open(self.data_file, 'w') as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving signal history: {e}")
    
    def _clean_old_signals(self, history):
        """Remove signals older than the configured period"""
        now = time.time()
        cutoff = now - (self.signal_period_hours * 3600)
        
        for pair in list(history.keys()):
            for signal_type in list(history[pair].keys()):
                # Filter out timestamps older than cutoff
                history[pair][signal_type] = [
                    ts for ts in history[pair][signal_type] 
                    if ts > cutoff
                ]
                
                # Clean up empty lists
                if not history[pair][signal_type]:
                    del history[pair][signal_type]
            
            # Clean up empty pairs
            if not history[pair]:
                del history[pair]
        
        return history
    
    def can_send_signal(self, pair, signal_type):
        """
        Check if a signal can be sent for this pair/type
        
        Args:
            pair (str): Trading pair (e.g., 'BTC/USDT')
            signal_type (str): 'long' or 'short'
            
        Returns:
            bool: True if signal can be sent, False otherwise
        """
        # Always allow signals in dev mode
        if hasattr(config, 'DEV_MODE') and config.DEV_MODE:
            logger.info(f"DEV_MODE enabled: Bypassing rate limiting for {pair} {signal_type}")
            return True
        with self.lock:
            # Load and clean history
            history = self._load_signal_history()
            history = self._clean_old_signals(history)
            
            # Check if we've reached the limit
            pair_history = history.get(pair, {})
            signals = pair_history.get(signal_type, [])
            
            max_signals = self.max_long_signals if signal_type == 'long' else self.max_short_signals
            
            logger.info(f"DEBUG [{pair}] Rate limit check for {signal_type}: {len(signals)}/{max_signals} signals in last {self.signal_period_hours}h")
            
            if signals:
                # Log the times of previous signals
                signal_times = [datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S') for ts in signals]
                logger.info(f"DEBUG [{pair}] Previous {signal_type} signals at: {', '.join(signal_times)}")
            
            can_send = len(signals) < max_signals
            
            if not can_send:
                # Calculate when the next signal can be sent
                oldest_signal = min(signals) if signals else 0
                next_available = datetime.fromtimestamp(oldest_signal + (self.signal_period_hours * 3600))
                now = datetime.now()
                time_until_next = next_available - now
                hours, remainder = divmod(time_until_next.total_seconds(), 3600)
                minutes, seconds = divmod(remainder, 60)
                
                logger.info(f"DEBUG [{pair}] RATE LIMITED: {signal_type} signal blocked. {len(signals)}/{max_signals} limit reached")
                logger.info(f"DEBUG [{pair}] Next {signal_type} signal available in {int(hours)}h {int(minutes)}m ({next_available})")
            
            return can_send
    
    def record_signal(self, pair, signal_type):
        """
        Record that a signal was sent
        
        Args:
            pair (str): Trading pair (e.g., 'BTC/USDT')
            signal_type (str): 'long' or 'short'
        """
        with self.lock:
            # Load and clean history
            history = self._load_signal_history()
            history = self._clean_old_signals(history)
            
            # Record the new signal
            if pair not in history:
                history[pair] = {}
            
            if signal_type not in history[pair]:
                history[pair][signal_type] = []
            
            # Add current timestamp
            history[pair][signal_type].append(time.time())
            
            # Save updated history
            self._save_signal_history(history)
            
            logger.info(f"Recorded {signal_type} signal for {pair}")
    
    def get_signal_counts(self):
        """
        Get current signal counts for all pairs
        
        Returns:
            dict: {pair: {'long': count, 'short': count}}
        """
        with self.lock:
            history = self._load_signal_history()
            history = self._clean_old_signals(history)
            
            counts = {}
            for pair, signals in history.items():
                counts[pair] = {
                    'long': len(signals.get('long', [])),
                    'short': len(signals.get('short', []))
                }
            
            return counts

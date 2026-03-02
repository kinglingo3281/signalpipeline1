"""
Signal Engine module.
Implements the core trading signal generation algorithm.
Direct translation of the JavaScript code to Python.
"""

import random
import math
import logging
import traceback
from config_manager import ConfigManager

logger = logging.getLogger('SignalEngine')

class SignalEngine:
    """
    Implements the core signal generation algorithm.
    This is a direct translation of the JavaScript code.
    """
    
    def __init__(self):
        """Initialize the Signal Engine"""
        self.config_manager = ConfigManager()
        
        # Get risk parameters
        risk_params = self.config_manager.get_risk_parameters()
        self.long_risk = risk_params.get('long_risk', 0.003)
        self.short_risk = risk_params.get('short_risk', 0.003)
        
        # Get signal parameters
        signal_params = self.config_manager.get_signal_parameters()
        
        # Fibonacci levels
        self.fib_levels = signal_params.get('fibonacci_levels', {
            "level1": 0.786,
            "level2": 0.618,
            "level3": 0.500,
            "level4": 0.382,
            "level5": 0.236
        })
        
        # ATR multipliers
        self.atr_multipliers = signal_params.get('atr_multipliers', {
            "long_sl": 1.5,
            "long_tp": 2.0,
            "short_sl": 1.5,
            "short_tp": 2.0
        })
        
        # Price percentiles
        self.price_percentiles = signal_params.get('price_percentiles', {
            "counter_trend_percentile": 0.85
        })
        
        # Support/resistance parameters
        self.sr_params = signal_params.get('support_resistance', {
            "minimum_distance_percent": 1.0,
            "maximum_distance_percent": 5.0
        })
    
    def generate_signals(self, pair_data):
        """
        Generate trading signals for a pair
        
        Args:
            pair_data (dict): Dictionary with pair data
            
        Returns:
            list: List of signal dictionaries
        """
        try:
            # Check if we have valid data
            if not pair_data:
                logger.warning("No pair data available for signal generation")
                return [{"signal_text": "No Scalping Signal"}]
                
            # Validate all required fields are present and not None
            required_fields = ['price', 'ATR', 'Pair', 'Bullish', 'Vault']
            for field in required_fields:
                if field not in pair_data or pair_data[field] is None:
                    logger.error(f"Missing required field: {field}")
                    return [{"signal_text": "No Scalping Signal"}]
            
            # Parse inputs
            price_array = list(map(float, pair_data["price"].split(',')))
            pair = pair_data["Pair"]
            symbol = pair.split('/')[0]
            bullish = pair_data["Bullish"]
            
            # Get vault balance
            vault_balance = float(pair_data["Vault"])
            
            # Get all input values and sort them
            all_inputs = [
                float(pair_data["pivot1"]),
                float(pair_data["pivot2"]),
                float(pair_data["pivot3"]),
                float(pair_data["pivot4"]),
                float(pair_data["group1"]),
                float(pair_data["group2"]),
                float(pair_data["group3"]),
                float(pair_data["group4"]),
                float(pair_data["group5"]),
                float(pair_data["group6"]),
                float(pair_data["group7"]),
                float(pair_data["group8"]),
                float(pair_data["group9"]),
                float(pair_data["group10"])
            ]
            all_inputs.sort(reverse=True)  # Sort descending
            
            # Parse Fibonacci levels
            fibo_levels = [
                float(pair_data["FIBO786"]),
                float(pair_data["FIBO618"]),
                float(pair_data["FIBO500"]),
                float(pair_data["FIBO382"]),
                float(pair_data["FIBO236"])
            ]
            
            # Get ATR
            atr = float(pair_data["ATR"])
            
            # Get current price and calculate price percentile value
            current_price = price_array[-1]
            percentile = self.price_percentiles.get('counter_trend_percentile', 0.85)
            price_percentile_index = int(len(price_array) * percentile)
            price85_value = sorted(price_array)[price_percentile_index]
            
            # Debug logging for key values
            logger.info(f"DEBUG [{pair}] Current price: {current_price:.4f}, 85th percentile price: {price85_value:.4f}, ATR: {atr:.4f}")
            
            # Signal arrays
            signals = []          # Counter-trend signals
            trend_signals = []    # Trend-following signals
            
            # ========== COUNTER-TREND LONG LOGIC ==========
            # Find valid trigger inputs
            trigger_inputs = [input_val for input_val in all_inputs 
                             if price85_value > input_val and current_price < input_val]
            
            # Debug logging for Counter-trend Long
            logger.info(f"DEBUG [{pair}] Counter-trend Long - Found {len(trigger_inputs)} trigger inputs meeting criteria: price85_value > input_val and current_price < input_val")
            if trigger_inputs:
                logger.info(f"DEBUG [{pair}] Counter-trend Long - Valid trigger inputs: {', '.join([f'{val:.4f}' for val in trigger_inputs[:5]])}{'...' if len(trigger_inputs) > 5 else ''}")
            
            if trigger_inputs:
                # Get the closest trigger input to current price
                closest_trigger_input = self._safe_min(trigger_inputs)
                
                if closest_trigger_input is not None:
                    # Find possible entry levels
                    possible_entries = [x for x in all_inputs if x < closest_trigger_input]
                    entry = None
                    signal_type = "A"  # Default signal type
                    
                    if possible_entries:
                        # Get the highest possible entry
                        entry = self._safe_max(possible_entries)
                        
                        # Get minimum entry multiple based on bullish and position type
                        min_entry_multiple = self._get_min_entry_multiple(True, bullish)
                        
                        # Validate entry using ATR multiple based on bullish
                        if entry is None or current_price - entry < atr * min_entry_multiple:
                            entry = self._get_entry_with_random_distance(current_price, True, bullish, atr)
                            signal_type = "B"  # Entry generated by random distance
                    else:
                        entry = self._get_entry_with_random_distance(current_price, True, bullish, atr)
                        signal_type = "B"  # Entry generated by random distance
                    
                    # Check if price is in range BEFORE adjustment
                    if self._is_price_in_range(current_price, entry):
                        # Store original entry for comparison
                        original_entry = entry
                        
                        # Calculate original TP for comparison and adjustment
                        original_tp = self._calculate_long_tp(original_entry, all_inputs, atr, bullish)
                        
                        # Apply Fibonacci adjustment with originalTP
                        adjustment = self._adjust_long_entry_and_tp(
                            entry, current_price, fibo_levels, price85_value, 
                            original_tp, atr, bullish, all_inputs
                        )
                        is_adjusted = adjustment["adjustedTP"] is not None
                        entry = adjustment["entry"]
                        
                        # Find nearest support and resistance levels
                        nearest_levels = self._find_nearest_levels(current_price, all_inputs, fibo_levels)
                        
                        # Skip further processing if no valid support/resistance levels found
                        if nearest_levels is None:
                            logger.info(f"Skipping signal due to missing support/resistance levels")
                            # Skip to the next iteration or signal type without generating a signal
                            return signals if 'counter-trend long' in locals() else []
                        
                        # Use adjustedSL if available, otherwise use originalSL
                        sl = adjustment["adjustedSL"] if is_adjusted and adjustment["adjustedSL"] is not None else \
                             adjustment["originalSL"] if adjustment["originalSL"] is not None else \
                             self._calculate_long_sl(entry, all_inputs, atr, bullish)
                        
                        tp = adjustment["adjustedTP"] if is_adjusted else original_tp
                        
                        # Generate adjustment text
                        adjustment_text = self._generate_adjustment_text(
                            is_adjusted, original_entry, entry, original_tp, tp, True
                        )
                        
                        # Calculate position size
                        try:
                            size = (self.long_risk * 1000) / (1 - (sl / entry))
                            real_position_size = (self.long_risk * vault_balance) / (1 - (sl / entry))
                            divided_position_size = real_position_size / 5
                        except ZeroDivisionError:
                            logger.warning(f"Division by zero when calculating position size for {pair}")
                            size = 0
                            real_position_size = 0
                            divided_position_size = 0
                        
                        # Format signal text
                        signal_text = self._escape_markdown_v2(f"""Long C2 Scalping_{pair}
- Entry: `{entry:.4f}`
- SL: `{sl:.4f}` {(abs((sl - entry) / entry) * 100):.2f}%
- TP: `{tp:.4f}` {((tp - entry) / entry * 100):.2f}%
+ Price when signal is generated: {current_price:.4f}
+ Signal Type: {signal_type}
+ H1 ATR: {atr:.4f}
+ Pivot Level: {price85_value:.4f}
+ {adjustment_text}
+ Support: {self._get_support_resistance_text(nearest_levels, 'support')}
+ Resistance: {self._get_support_resistance_text(nearest_levels, 'resistance')}

PVP:
`/limit long {symbol} 5x {entry:.4f} {divided_position_size:.2f}`
Example Balance: {vault_balance:.2f}
⚠️ ORDER EXPIRY: CANCEL IF UNFILLED WITHIN 6 HOURS ⚠️""")
                        
                        logger.info(f"DEBUG [{pair}] Counter-trend Long - SIGNAL GENERATED")
                        signals.append({"signal_text": signal_text, "position": "long"})
            
            # ========== COUNTER-TREND SHORT LOGIC ==========
            # Find valid trigger inputs
            trigger_inputs = [input_val for input_val in all_inputs 
                             if price85_value < input_val and current_price > input_val]
            
            # Debug logging for Counter-trend Short
            logger.info(f"DEBUG [{pair}] Counter-trend Short - Found {len(trigger_inputs)} trigger inputs meeting criteria: price85_value < input_val and current_price > input_val")
            if trigger_inputs:
                logger.info(f"DEBUG [{pair}] Counter-trend Short - Valid trigger inputs: {', '.join([f'{val:.4f}' for val in trigger_inputs[:5]])}{'...' if len(trigger_inputs) > 5 else ''}")
            
            if trigger_inputs:
                # Get the closest trigger input to current price
                closest_trigger_input = self._safe_max(trigger_inputs)
                
                if closest_trigger_input is not None:
                    # Find possible entry levels
                    possible_entries = [x for x in all_inputs if x > closest_trigger_input]
                    entry = None
                    signal_type = "A"  # Default signal type
                    
                    if possible_entries:
                        # Get the lowest possible entry
                        entry = self._safe_min(possible_entries)
                        
                        # Get minimum entry multiple based on bullish and position type
                        min_entry_multiple = self._get_min_entry_multiple(False, bullish)
                        
                        # Validate entry using ATR multiple based on bullish
                        if entry is None or entry - current_price < atr * min_entry_multiple:
                            entry = self._get_entry_with_random_distance(current_price, False, bullish, atr)
                            signal_type = "B"  # Entry generated by random distance
                    else:
                        entry = self._get_entry_with_random_distance(current_price, False, bullish, atr)
                        signal_type = "B"  # Entry generated by random distance
                    
                    # Check if price is in range BEFORE adjustment
                    if self._is_price_in_range(current_price, entry):
                        # Store original entry for comparison
                        original_entry = entry
                        
                        # Calculate original TP for comparison and adjustment
                        original_tp = self._calculate_short_tp(original_entry, all_inputs, atr, bullish)
                        
                        # Apply Fibonacci adjustment for short with originalTP
                        adjustment = self._adjust_short_entry_and_tp(
                            entry, current_price, fibo_levels, price85_value, 
                            original_tp, atr, bullish, all_inputs
                        )
                        is_adjusted = adjustment["adjustedTP"] is not None
                        entry = adjustment["entry"]
                        
                        # Find nearest support and resistance levels
                        nearest_levels = self._find_nearest_levels(current_price, all_inputs, fibo_levels)
                        
                        # Skip further processing if no valid support/resistance levels found
                        if nearest_levels is None:
                            logger.info(f"Skipping signal due to missing support/resistance levels")
                            # Skip to the next iteration or signal type without generating a signal
                            return signals if 'counter-trend long' in locals() else []
                        
                        # Use adjustedSL if available, otherwise use originalSL
                        sl = adjustment["adjustedSL"] if is_adjusted and adjustment["adjustedSL"] is not None else \
                             adjustment["originalSL"] if adjustment["originalSL"] is not None else \
                             self._calculate_short_sl(entry, all_inputs, atr, bullish)
                        
                        tp = adjustment["adjustedTP"] if is_adjusted else original_tp
                        
                        # Generate adjustment text
                        adjustment_text = self._generate_adjustment_text(
                            is_adjusted, original_entry, entry, original_tp, tp, False
                        )
                        
                        # Calculate position size
                        try:
                            size = (self.short_risk * 1000) / (1 - (entry / sl))
                            real_position_size = (self.short_risk * vault_balance) / (1 - (entry / sl))
                            divided_position_size = real_position_size / 5
                        except ZeroDivisionError:
                            logger.warning(f"Division by zero when calculating position size for {pair}")
                            size = 0
                            real_position_size = 0
                            divided_position_size = 0
                        
                        # Format signal text
                        signal_text = self._escape_markdown_v2(f"""Short C2 Scalping_{pair}
- Entry: `{entry:.4f}`
- SL: `{sl:.4f}` {(abs((entry - sl) / entry) * 100):.2f}%
- TP: `{tp:.4f}` {((entry - tp) / entry * 100):.2f}%
+ Price when signal is generated: {current_price:.4f}
+ Signal Type: {signal_type}
+ H1 ATR: {atr:.4f}
+ Pivot Level: {price85_value:.4f}
+ {adjustment_text}
+ Support: {self._get_support_resistance_text(nearest_levels, 'support')}
+ Resistance: {self._get_support_resistance_text(nearest_levels, 'resistance')}

PVP:
`/limit short {symbol} 5x {entry:.4f} {divided_position_size:.2f}`
Example Balance: {vault_balance:.2f}
⚠️ ORDER EXPIRY: CANCEL IF UNFILLED WITHIN 6 HOURS ⚠️""")
                        
                        logger.info(f"DEBUG [{pair}] Counter-trend Short - SIGNAL GENERATED")
                        signals.append({"signal_text": signal_text, "position": "short"})
            
            # ========== TREND-FOLLOWING LONG LOGIC ==========
            # Find valid trigger inputs
            trigger_inputs = [input_val for input_val in all_inputs 
                             if price85_value > input_val and current_price > input_val]
            
            # Debug logging for Trend-following Long
            logger.info(f"DEBUG [{pair}] Trend-following Long - Found {len(trigger_inputs)} trigger inputs meeting criteria: price85_value > input_val and current_price > input_val")
            if trigger_inputs:
                logger.info(f"DEBUG [{pair}] Trend-following Long - Valid trigger inputs: {', '.join([f'{val:.4f}' for val in trigger_inputs[:5]])}{'...' if len(trigger_inputs) > 5 else ''}")
            
            if trigger_inputs:
                # Get the closest trigger input to current price
                closest_trigger_input = self._safe_max(trigger_inputs)
                
                if closest_trigger_input is not None:
                    # Get minimum entry multiple based on bullish and position type
                    min_entry_multiple = self._get_min_entry_multiple(True, bullish)
                    
                    # Find possible entry levels with ATR-based filter
                    possible_entries = [x for x in all_inputs 
                                      if x < closest_trigger_input and current_price - x >= atr * min_entry_multiple]
                    entry = None
                    signal_type = "A"  # Default signal type
                    
                    if possible_entries:
                        # Get the highest possible entry
                        entry = self._safe_max(possible_entries)
                        
                        # Fallback if entry is null
                        if entry is None:
                            entry = self._get_entry_with_random_distance(current_price, True, bullish, atr)
                            signal_type = "B"  # Entry generated by random distance
                    else:
                        entry = self._get_entry_with_random_distance(current_price, True, bullish, atr)
                        signal_type = "B"  # Entry generated by random distance
                    
                    # Check if price is in range BEFORE adjustment
                    if self._is_price_in_range(current_price, entry):
                        # Store original entry for comparison
                        original_entry = entry
                        
                        # Calculate original TP for comparison and adjustment
                        original_tp = self._calculate_long_tp(original_entry, all_inputs, atr, bullish)
                        
                        # Apply Fibonacci adjustment with originalTP
                        adjustment = self._adjust_long_entry_and_tp(
                            entry, current_price, fibo_levels, price85_value, 
                            original_tp, atr, bullish, all_inputs
                        )
                        is_adjusted = adjustment["adjustedTP"] is not None
                        entry = adjustment["entry"]
                        
                        # Find nearest support and resistance levels
                        nearest_levels = self._find_nearest_levels(current_price, all_inputs, fibo_levels)
                        
                        # Skip further processing if no valid support/resistance levels found
                        if nearest_levels is None:
                            logger.info(f"Skipping signal due to missing support/resistance levels")
                            # Skip to the next iteration or signal type without generating a signal
                            return signals if 'counter-trend long' in locals() else []
                        
                        # Use adjustedSL if available, otherwise use originalSL
                        sl = adjustment["adjustedSL"] if is_adjusted and adjustment["adjustedSL"] is not None else \
                             adjustment["originalSL"] if adjustment["originalSL"] is not None else \
                             self._calculate_long_sl(entry, all_inputs, atr, bullish)
                        
                        tp = adjustment["adjustedTP"] if is_adjusted else original_tp
                        
                        # Generate adjustment text
                        adjustment_text = self._generate_adjustment_text(
                            is_adjusted, original_entry, entry, original_tp, tp, True
                        )
                        
                        # Calculate position size
                        try:
                            size = (self.long_risk * 1000) / (1 - (sl / entry))
                            real_position_size = (self.long_risk * vault_balance) / (1 - (sl / entry))
                            divided_position_size = real_position_size / 5
                        except ZeroDivisionError:
                            logger.warning(f"Division by zero when calculating position size for {pair}")
                            size = 0
                            real_position_size = 0
                            divided_position_size = 0
                        
                        # Format signal text
                        signal_text = self._escape_markdown_v2(f"""Long T2 Scalping_{pair}
- Entry: `{entry:.4f}`
- SL: `{sl:.4f}` {(abs((sl - entry) / entry) * 100):.2f}%
- TP: `{tp:.4f}` {((tp - entry) / entry * 100):.2f}%
+ Price when signal is generated: {current_price:.4f}
+ Signal Type: {signal_type}
+ H1 ATR: {atr:.4f}
+ Pivot Level: {price85_value:.4f}
+ {adjustment_text}
+ Support: {self._get_support_resistance_text(nearest_levels, 'support')}
+ Resistance: {self._get_support_resistance_text(nearest_levels, 'resistance')}

PVP:
`/limit long {symbol} 5x {entry:.4f} {divided_position_size:.2f}`
Example Balance: {vault_balance:.2f}
⚠️ ORDER EXPIRY: CANCEL IF UNFILLED WITHIN 6 HOURS ⚠️""")
                        
                        logger.info(f"DEBUG [{pair}] Trend-following Long - SIGNAL GENERATED")
                        trend_signals.append({"signal_text": signal_text, "position": "long"})
            
            # ========== TREND-FOLLOWING SHORT LOGIC ==========
            # Find valid trigger inputs
            trigger_inputs = [input_val for input_val in all_inputs 
                             if input_val > current_price and input_val < price85_value]
            
            # Debug logging for Trend-following Short
            logger.info(f"DEBUG [{pair}] Trend-following Short - Found {len(trigger_inputs)} trigger inputs meeting criteria: input_val > current_price and input_val < price85_value")
            if trigger_inputs:
                logger.info(f"DEBUG [{pair}] Trend-following Short - Valid trigger inputs: {', '.join([f'{val:.4f}' for val in trigger_inputs[:5]])}{'...' if len(trigger_inputs) > 5 else ''}")
            
            if trigger_inputs:
                # Get the closest trigger input to current price
                closest_trigger_input = self._safe_min(trigger_inputs)
                
                if closest_trigger_input is not None:
                    # Get minimum entry multiple based on bullish and position type
                    min_entry_multiple = self._get_min_entry_multiple(False, bullish)
                    
                    # Find possible entry levels with ATR-based filter
                    possible_entries = [x for x in all_inputs 
                                      if x > closest_trigger_input and x - current_price >= atr * min_entry_multiple]
                    entry = None
                    signal_type = "A"  # Default signal type
                    
                    if possible_entries:
                        # Get the lowest possible entry
                        entry = self._safe_min(possible_entries)
                        
                        # Fallback if entry is null
                        if entry is None:
                            entry = self._get_entry_with_random_distance(current_price, False, bullish, atr)
                            signal_type = "B"  # Entry generated by random distance
                    else:
                        entry = self._get_entry_with_random_distance(current_price, False, bullish, atr)
                        signal_type = "B"  # Entry generated by random distance
                    
                    # Check if price is in range BEFORE adjustment
                    if self._is_price_in_range(current_price, entry):
                        # Store original entry for comparison
                        original_entry = entry
                        
                        # Calculate original TP for comparison and adjustment
                        original_tp = self._calculate_short_tp(original_entry, all_inputs, atr, bullish)
                        
                        # Apply Fibonacci adjustment for short with originalTP
                        adjustment = self._adjust_short_entry_and_tp(
                            entry, current_price, fibo_levels, price85_value, 
                            original_tp, atr, bullish, all_inputs
                        )
                        is_adjusted = adjustment["adjustedTP"] is not None
                        entry = adjustment["entry"]
                        
                        # Find nearest support and resistance levels
                        nearest_levels = self._find_nearest_levels(current_price, all_inputs, fibo_levels)
                        
                        # Skip further processing if no valid support/resistance levels found
                        if nearest_levels is None:
                            logger.info(f"Skipping signal due to missing support/resistance levels")
                            # Skip to the next iteration or signal type without generating a signal
                            return signals if 'counter-trend long' in locals() else []
                        
                        # Use adjustedSL if available, otherwise use originalSL
                        sl = adjustment["adjustedSL"] if is_adjusted and adjustment["adjustedSL"] is not None else \
                             adjustment["originalSL"] if adjustment["originalSL"] is not None else \
                             self._calculate_short_sl(entry, all_inputs, atr, bullish)
                        
                        tp = adjustment["adjustedTP"] if is_adjusted else original_tp
                        
                        # Generate adjustment text
                        adjustment_text = self._generate_adjustment_text(
                            is_adjusted, original_entry, entry, original_tp, tp, False
                        )
                        
                        # Calculate position size
                        try:
                            size = (self.short_risk * 1000) / (1 - (entry / sl))
                            real_position_size = (self.short_risk * vault_balance) / (1 - (entry / sl))
                            divided_position_size = real_position_size / 5
                        except ZeroDivisionError:
                            logger.warning(f"Division by zero when calculating position size for {pair}")
                            size = 0
                            real_position_size = 0
                            divided_position_size = 0
                        
                        # Format signal text
                        signal_text = self._escape_markdown_v2(f"""Short T2 Scalping_{pair}
- Entry: `{entry:.4f}`
- SL: `{sl:.4f}` {(abs((sl - entry) / entry) * 100):.2f}%
- TP: `{tp:.4f}` {(abs((tp - entry) / entry) * 100):.2f}%
+ Price when signal is generated: {current_price:.4f}
+ Signal Type: {signal_type}
+ H1 ATR: {atr:.4f}
+ Pivot Level: {price85_value:.4f}
+ {adjustment_text}
+ Support: {"N/A" if nearest_levels["support"] is None else f"{nearest_levels["support"]:.4f}"}
+ Resistance: {"N/A" if nearest_levels["resistance"] is None else f"{nearest_levels["resistance"]:.4f}"}

PVP:
`/limit short {symbol} 5x {entry:.4f} {divided_position_size:.2f}`
Example Balance: {vault_balance:.2f}
⚠️ ORDER EXPIRY: CANCEL IF UNFILLED WITHIN 6 HOURS ⚠️""")
                        
                        logger.info(f"DEBUG [{pair}] Trend-following Short - SIGNAL GENERATED")
                        trend_signals.append({"signal_text": signal_text, "position": "short"})
            
            # Combine counter-trend and trend-following signals
            all_signals = signals + trend_signals
            if not all_signals:
                # Check counter-trend conditions
                counter_trend_long = any(price85_value > input_val and current_price < input_val for input_val in all_inputs)
                counter_trend_short = any(price85_value < input_val and current_price > input_val for input_val in all_inputs)
                
                # Check trend-following conditions
                trend_following_long = any(price85_value < input_val and current_price > input_val for input_val in all_inputs)
                trend_following_short = any(price85_value > input_val and current_price < input_val for input_val in all_inputs)
                
                logger.info(f"No valid trade setup for {pair}: " + 
                           f"Counter-trend long: {'YES' if counter_trend_long else 'NO'}, " +
                           f"Counter-trend short: {'YES' if counter_trend_short else 'NO'}, " +
                           f"Trend-following long: {'YES' if trend_following_long else 'NO'}, " +
                           f"Trend-following short: {'YES' if trend_following_short else 'NO'}")
                
                return [{"signal_text": "No Scalping Signal"}]  # Keep this for zapflow.js compatibility
            return all_signals
            
        except Exception as e:
            logger.error(f"Error generating signals: {e}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            
            # Additional debug info about the input data
            if pair_data:
                logger.debug(f"Input data keys: {pair_data.keys()}")
                for key, value in pair_data.items():
                    logger.debug(f"Key: {key}, Type: {type(value)}, Value: {value if key != 'price' else 'price data (truncated)'}")
            
            return [{"signal_text": "No Scalping Signal"}]
    
    # ========== HELPER FUNCTIONS ==========
    # These are direct translations of the JavaScript helper functions
    
    def _safe_min(self, arr, default_value=None):
        """Get minimum value from array, or default if empty"""
        return min(arr) if arr else default_value
    
    def _safe_max(self, arr, default_value=None):
        """Get maximum value from array, or default if empty"""
        return max(arr) if arr else default_value
    
    def _escape_markdown_v2(self, text):
        """Escape Telegram MarkdownV2 reserved characters"""
        for char in ['-', '.', '_', '(', ')', '+', '|', '#']:
            text = text.replace(char, f'\\{char}')
        return text
    
    def _get_entry_with_random_distance(self, current_price, is_long, bullish, atr):
        """Generate an entry at a random distance from current price using ATR"""
        # Use true random values to match JavaScript behavior
        if bullish == 'NA':
            # For both long and short: random between 3.5-4.5
            entry_multiple = random.uniform(3.5, 4.5)
        elif bullish == 'On':
            if is_long:
                # For long: random between 2.5-4.5
                entry_multiple = random.uniform(2.5, 4.5)
            else:
                # For short: random between 4.5-6.5
                entry_multiple = random.uniform(4.5, 6.5)
        elif bullish == 'Off':
            if is_long:
                # For long: random between 4.5-6.5
                entry_multiple = random.uniform(4.5, 6.5)
            else:
                # For short: random between 2.5-3.5
                entry_multiple = random.uniform(2.5, 3.5)
        else:
            # Default fallback - random
            entry_multiple = random.uniform(3.5, 4.5)
        
        # For long signals, entry should be below current price
        if is_long:
            return current_price - (atr * entry_multiple)
        # For short signals, entry should be above current price
        else:
            return current_price + (atr * entry_multiple)
    
    def _get_min_entry_multiple(self, is_long, bullish):
        """Get the min entry multiple based on bullish and position type"""
        if bullish == 'NA':
            return 3.5  # Both long and short
        elif bullish == 'On':
            return 2.5 if is_long else 4.5  # Long: 2.5, Short: 4.5
        elif bullish == 'Off':
            return 4.5 if is_long else 2.5  # Long: 4.5, Short: 2.5
        return 3.5  # Default fallback
    
    def _is_price_in_range(self, price, entry):
        """Check if price is within 10% range of entry"""
        max_diff_percent = 0.1  # 10%
        diff_percent = abs(price - entry) / entry
        result = diff_percent <= max_diff_percent
        if not result:
            logger.info(f"Price range check FAILED: Current price {price:.4f} is {diff_percent*100:.2f}% away from entry {entry:.4f} (max allowed: 10%)")
        return result
    
    def _calculate_long_sl(self, entry, all_inputs, atr, bullish):
        """Calculate stop loss for long positions"""
        # Filter inputs below entry
        lower_levels = [x for x in all_inputs if x < entry]
        
        if lower_levels:
            # Get highest level below entry
            max_lower_level = self._safe_max(lower_levels)
            
            if max_lower_level is not None:
                # Calculate SL using the highest level minus ATR
                sl = max_lower_level - atr
                
                # Get ATR range based on bullish parameter from config
                if bullish == 'NA':
                    min_sl_multiple = self.atr_multipliers.get('long_sl_na_min', 2.5)
                    max_sl_multiple = self.atr_multipliers.get('long_sl_na_max', 3.5)
                elif bullish == 'On':
                    min_sl_multiple = self.atr_multipliers.get('long_sl_on_min', 3.5)
                    max_sl_multiple = self.atr_multipliers.get('long_sl_on_max', 4.5)
                elif bullish == 'Off':
                    min_sl_multiple = self.atr_multipliers.get('long_sl_off_min', 2.5)
                    max_sl_multiple = self.atr_multipliers.get('long_sl_off_max', 3.5)
                
                min_sl_distance = entry - (atr * max_sl_multiple)
                max_sl_distance = entry - (atr * min_sl_multiple)
                
                if sl > max_sl_distance or sl < min_sl_distance:
                    # Try next level if available
                    filtered_levels = [x for x in lower_levels if x != max_lower_level]
                    
                    if filtered_levels:
                        next_max = self._safe_max(filtered_levels)
                        if next_max is not None:
                            sl = next_max - atr
                            
                            # Check again if within range
                            if sl > max_sl_distance or sl < min_sl_distance:
                                # Use random value instead of fixed midpoint
                                random_multiple = random.uniform(min_sl_multiple, max_sl_multiple)
                                sl = entry - (atr * random_multiple)
                        else:
                            # Use random value within the defined range, matching JS behavior
                            random_multiple = random.uniform(min_sl_multiple, max_sl_multiple)
                            sl = entry - (atr * random_multiple)
                    else:
                        # Use random value within the defined range, matching JS behavior
                        random_multiple = random.uniform(min_sl_multiple, max_sl_multiple)
                        sl = entry - (atr * random_multiple)
            else:
                # Use random value within the defined range, matching JS behavior
                if bullish == 'NA':
                    min_sl_multiple = self.atr_multipliers.get('long_sl_na_min', 2.5)
                    max_sl_multiple = self.atr_multipliers.get('long_sl_na_max', 3.5)
                elif bullish == 'On':
                    min_sl_multiple = self.atr_multipliers.get('long_sl_on_min', 3.5)
                    max_sl_multiple = self.atr_multipliers.get('long_sl_on_max', 4.5)
                elif bullish == 'Off':
                    min_sl_multiple = self.atr_multipliers.get('long_sl_off_min', 2.5)
                    max_sl_multiple = self.atr_multipliers.get('long_sl_off_max', 3.5)
                
                random_multiple = random.uniform(min_sl_multiple, max_sl_multiple)
                sl = entry - (atr * random_multiple)
        else:
            # No levels below entry, use random ATR multiple
            if bullish == 'NA':
                min_sl_multiple = self.atr_multipliers.get('long_sl_na_min', 2.5)
                max_sl_multiple = self.atr_multipliers.get('long_sl_na_max', 3.5)
            elif bullish == 'On':
                min_sl_multiple = self.atr_multipliers.get('long_sl_on_min', 3.5)
                max_sl_multiple = self.atr_multipliers.get('long_sl_on_max', 4.5)
            elif bullish == 'Off':
                min_sl_multiple = self.atr_multipliers.get('long_sl_off_min', 2.5)
                max_sl_multiple = self.atr_multipliers.get('long_sl_off_max', 3.5)
            
            random_multiple = random.uniform(min_sl_multiple, max_sl_multiple)
            sl = entry - (atr * random_multiple)
            
        return sl
    
    def _calculate_long_tp(self, entry, all_inputs, atr, bullish):
        """Calculate take profit for long positions"""
        # Filter inputs above entry
        higher_levels = [x for x in all_inputs if x > entry]
        
        if higher_levels:
            # Get lowest level above entry
            min_higher_level = self._safe_min(higher_levels)
            
            if min_higher_level is not None:
                # Calculate TP using the lowest level plus ATR
                tp = min_higher_level + atr
                
                # Get ATR range based on bullish parameter from config
                if bullish == 'NA':
                    min_tp_multiple = self.atr_multipliers.get('long_tp_na_min', 2.5)
                    max_tp_multiple = self.atr_multipliers.get('long_tp_na_max', 3.5)
                elif bullish == 'On':
                    min_tp_multiple = self.atr_multipliers.get('long_tp_on_min', 3.5)
                    max_tp_multiple = self.atr_multipliers.get('long_tp_on_max', 4.5)
                elif bullish == 'Off':
                    min_tp_multiple = self.atr_multipliers.get('long_tp_off_min', 1.5)
                    max_tp_multiple = self.atr_multipliers.get('long_tp_off_max', 2.5)
                
                min_tp_distance = entry + (atr * min_tp_multiple)
                max_tp_distance = entry + (atr * max_tp_multiple)
                
                if tp < min_tp_distance or tp > max_tp_distance:
                    # Try next level if available
                    filtered_levels = [x for x in higher_levels if x != min_higher_level]
                    
                    if filtered_levels:
                        next_min = self._safe_min(filtered_levels)
                        if next_min is not None:
                            tp = next_min + atr
                            
                            # Check again if within range
                            if tp < min_tp_distance or tp > max_tp_distance:
                                # Use random value instead of fixed midpoint
                                random_multiple = random.uniform(min_tp_multiple, max_tp_multiple)
                                tp = entry + (atr * random_multiple)
                        else:
                            # Use random value
                            random_multiple = random.uniform(min_tp_multiple, max_tp_multiple)
                            tp = entry + (atr * random_multiple)
                    else:
                        # Use random value
                        random_multiple = random.uniform(min_tp_multiple, max_tp_multiple)
                        tp = entry + (atr * random_multiple)
            else:
                # Fallback to random value
                if bullish == 'NA':
                    min_tp_multiple = self.atr_multipliers.get('long_tp_na_min', 2.5)
                    max_tp_multiple = self.atr_multipliers.get('long_tp_na_max', 3.5)
                elif bullish == 'On':
                    min_tp_multiple = self.atr_multipliers.get('long_tp_on_min', 3.5)
                    max_tp_multiple = self.atr_multipliers.get('long_tp_on_max', 4.5)
                elif bullish == 'Off':
                    min_tp_multiple = self.atr_multipliers.get('long_tp_off_min', 1.5)
                    max_tp_multiple = self.atr_multipliers.get('long_tp_off_max', 2.5)
                
                random_multiple = random.uniform(min_tp_multiple, max_tp_multiple)
                tp = entry + (atr * random_multiple)
        else:
            # No levels above entry, use random ATR multiple
            if bullish == 'NA':
                min_tp_multiple = self.atr_multipliers.get('long_tp_na_min', 2.5)
                max_tp_multiple = self.atr_multipliers.get('long_tp_na_max', 3.5)
            elif bullish == 'On':
                min_tp_multiple = self.atr_multipliers.get('long_tp_on_min', 3.5)
                max_tp_multiple = self.atr_multipliers.get('long_tp_on_max', 4.5)
            elif bullish == 'Off':
                min_tp_multiple = self.atr_multipliers.get('long_tp_off_min', 1.5)
                max_tp_multiple = self.atr_multipliers.get('long_tp_off_max', 2.5)
            
            random_multiple = random.uniform(min_tp_multiple, max_tp_multiple)
            tp = entry + (atr * random_multiple)
        
        return tp
    
    def _calculate_short_sl(self, entry, all_inputs, atr, bullish):
        """Calculate stop loss for short positions"""
        # Filter inputs above entry
        higher_levels = [x for x in all_inputs if x > entry]
        
        if higher_levels:
            # Get lowest level above entry
            min_higher_level = self._safe_min(higher_levels)
            
            if min_higher_level is not None:
                # Calculate SL using the lowest level plus ATR
                sl = min_higher_level + atr
                
                # Get ATR range based on bullish parameter from config
                if bullish == 'NA':
                    min_sl_multiple = self.atr_multipliers.get('short_sl_na_min', 2.5)
                    max_sl_multiple = self.atr_multipliers.get('short_sl_na_max', 3.5)
                elif bullish == 'On':
                    min_sl_multiple = self.atr_multipliers.get('short_sl_on_min', 2.5)
                    max_sl_multiple = self.atr_multipliers.get('short_sl_on_max', 3.5)
                elif bullish == 'Off':
                    min_sl_multiple = self.atr_multipliers.get('short_sl_off_min', 3.5)
                    max_sl_multiple = self.atr_multipliers.get('short_sl_off_max', 4.5)
                
                min_sl_distance = entry + (atr * min_sl_multiple)
                max_sl_distance = entry + (atr * max_sl_multiple)
                
                if sl < min_sl_distance or sl > max_sl_distance:
                    # Try next level if available
                    filtered_levels = [x for x in higher_levels if x != min_higher_level]
                    
                    if filtered_levels:
                        next_min = self._safe_min(filtered_levels)
                        if next_min is not None:
                            sl = next_min + atr
                            
                            # Check again if within range
                            if sl < min_sl_distance or sl > max_sl_distance:
                                # Random SL based on ATR multiple
                                random_multiple = random.uniform(min_sl_multiple, max_sl_multiple)
                                sl = entry + (atr * random_multiple)
                        else:
                            # Random SL based on ATR multiple
                            random_multiple = random.uniform(min_sl_multiple, max_sl_multiple)
                            sl = entry + (atr * random_multiple)
                    else:
                        # Random SL based on ATR multiple
                        random_multiple = random.uniform(min_sl_multiple, max_sl_multiple)
                        sl = entry + (atr * random_multiple)
            else:
                # Fallback to random SL based on ATR multiple
                if bullish == 'NA':
                    min_sl_multiple, max_sl_multiple = 2.5, 3.5
                elif bullish == 'On':
                    min_sl_multiple, max_sl_multiple = 2.5, 3.5
                elif bullish == 'Off':
                    min_sl_multiple, max_sl_multiple = 3.5, 4.5
                
                random_multiple = random.uniform(min_sl_multiple, max_sl_multiple)
                sl = entry + (atr * random_multiple)
        else:
            # No levels above entry, use random ATR multiple
            if bullish == 'NA':
                min_sl_multiple, max_sl_multiple = 2.5, 3.5
            elif bullish == 'On':
                min_sl_multiple, max_sl_multiple = 2.5, 3.5
            elif bullish == 'Off':
                min_sl_multiple, max_sl_multiple = 3.5, 4.5
            
            random_multiple = random.uniform(min_sl_multiple, max_sl_multiple)
            sl = entry + (atr * random_multiple)
        
        return sl
    
    def _calculate_short_tp(self, entry, all_inputs, atr, bullish):
        """Calculate take profit for short positions"""
        # Filter inputs below entry
        lower_levels = [x for x in all_inputs if x < entry]
        
        if lower_levels:
            # Get highest level below entry
            max_lower_level = self._safe_max(lower_levels)
            
            if max_lower_level is not None:
                # Calculate TP using the highest level minus ATR
                tp = max_lower_level - atr
                
                # Get ATR range based on bullish parameter from config
                if bullish == 'NA':
                    min_tp_multiple = self.atr_multipliers.get('short_tp_na_min', 2.5)
                    max_tp_multiple = self.atr_multipliers.get('short_tp_na_max', 3.5)
                elif bullish == 'On':
                    min_tp_multiple = self.atr_multipliers.get('short_tp_on_min', 1.5)
                    max_tp_multiple = self.atr_multipliers.get('short_tp_on_max', 2.5)
                elif bullish == 'Off':
                    min_tp_multiple = self.atr_multipliers.get('short_tp_off_min', 3.5)
                    max_tp_multiple = self.atr_multipliers.get('short_tp_off_max', 4.5)
                
                min_tp_distance = entry - (atr * max_tp_multiple)
                max_tp_distance = entry - (atr * min_tp_multiple)
                
                if tp > max_tp_distance or tp < min_tp_distance:
                    # Try next level if available
                    filtered_levels = [x for x in lower_levels if x != max_lower_level]
                    
                    if filtered_levels:
                        next_max = self._safe_max(filtered_levels)
                        if next_max is not None:
                            tp = next_max - atr
                            
                            # Check again if within range
                            if tp > max_tp_distance or tp < min_tp_distance:
                                # Random TP based on ATR multiple
                                random_multiple = random.uniform(min_tp_multiple, max_tp_multiple)
                                tp = entry - (atr * random_multiple)
                        else:
                            # Random TP based on ATR multiple
                            random_multiple = random.uniform(min_tp_multiple, max_tp_multiple)
                            tp = entry - (atr * random_multiple)
                    else:
                        # Random TP based on ATR multiple
                        random_multiple = random.uniform(min_tp_multiple, max_tp_multiple)
                        tp = entry - (atr * random_multiple)
            else:
                # Fallback to random TP based on ATR multiple
                if bullish == 'NA':
                    min_tp_multiple, max_tp_multiple = 2.5, 3.5
                elif bullish == 'On':
                    min_tp_multiple, max_tp_multiple = 1.5, 2.5
                elif bullish == 'Off':
                    min_tp_multiple, max_tp_multiple = 3.5, 4.5
                
                random_multiple = random.uniform(min_tp_multiple, max_tp_multiple)
                tp = entry - (atr * random_multiple)
        else:
            # No levels below entry, use random ATR multiple
            if bullish == 'NA':
                min_tp_multiple, max_tp_multiple = 2.5, 3.5
            elif bullish == 'On':
                min_tp_multiple, max_tp_multiple = 1.5, 2.5
            elif bullish == 'Off':
                min_tp_multiple, max_tp_multiple = 3.5, 4.5
            
            random_multiple = random.uniform(min_tp_multiple, max_tp_multiple)
            tp = entry - (atr * random_multiple)
        
        return tp
    
    def _adjust_long_entry_and_tp(self, entry, current_price, fibo_levels, price85_value, 
                                 original_tp, atr, bullish, all_inputs):
        """Adjust entry and TP based on Fibonacci levels for Long signals"""
        # Ensure we have a valid entry before proceeding
        if entry is None:
            return {"entry": entry, "adjustedTP": None, "originalSL": None, "adjustedSL": None}
        
        # Calculate original SL to preserve it
        original_sl = self._calculate_long_sl(entry, all_inputs, atr, bullish)
        
        # Sort Fibonacci levels
        sorted_fibo_levels = sorted(fibo_levels)
        
        # Find the two Fibonacci levels closest to current price (one above, one below)
        sup = None
        res = None
        
        # Find support level (below current price)
        for level in reversed(sorted_fibo_levels):
            if level < current_price:
                sup = level
                break
        
        # Find resistance level (above current price)
        for level in sorted_fibo_levels:
            if level > current_price:
                res = level
                break
        
        # If can't find both support and resistance, return original entry
        if sup is None or res is None:
            return {"entry": entry, "adjustedTP": None, "originalSL": original_sl, "adjustedSL": None}
        
        # Check condition: support below both price85 and currentPrice, resistance above both
        condition_met = (sup < price85_value and sup < current_price and 
                        res > price85_value and res > current_price)
        
        # If condition not met, return original entry
        if not condition_met:
            return {"entry": entry, "adjustedTP": None, "originalSL": original_sl, "adjustedSL": None}
        
        # Calculate normalized distance from currentPrice to support (0 to 1)
        # 0 means currentPrice is at support, 1 means currentPrice is at resistance
        total_range = res - sup
        distance_from_sup = current_price - sup
        normalized_distance = distance_from_sup / total_range
        
        # Adjust entry based on normalized distance tiers using ATR multiples
        if normalized_distance < 0.1:
            # Very close to support - highest entry adjustment
            adjusted_entry = entry + (atr * 1.5)  # 2% -> 1.5 ATR
        elif normalized_distance < 0.3:
            # Moderately close to support
            adjusted_entry = entry + (atr * 1.125)  # 1.5% -> 1.125 ATR
        elif normalized_distance < 0.5:
            # Somewhat close to support
            adjusted_entry = entry + (atr * 0.75)  # 1% -> 0.75 ATR
        elif normalized_distance < 0.7:
            # Somewhat close to resistance
            adjusted_entry = entry - (atr * 0.75)  # 1% -> 0.75 ATR
        elif normalized_distance < 0.9:
            # Moderately close to resistance
            adjusted_entry = entry - (atr * 1.125)  # 1.5% -> 1.125 ATR
        else:
            # Very close to resistance
            adjusted_entry = entry - (atr * 1.5)  # 2% -> 1.5 ATR
        
        # Always generate a new adjustedSL with random ATR multiple
        if bullish == 'NA':
            min_sl_multiple, max_sl_multiple = 2.5, 3.5
        elif bullish == 'On':
            min_sl_multiple, max_sl_multiple = 3.5, 4.5
        elif bullish == 'Off':
            min_sl_multiple, max_sl_multiple = 2.5, 3.5
        
        random_sl_multiple = random.uniform(min_sl_multiple, max_sl_multiple)
        adjusted_sl = adjusted_entry - (atr * random_sl_multiple)
        
        # Recalculate TP using adjusted entry with ATR multiples
        if normalized_distance < 0.1:
            # Very close to support - widest TP
            tp_multiple = random.uniform(5.25, 6.75)  # 7-9% -> 5.25-6.75 ATR
        elif normalized_distance < 0.3:
            # Moderately close to support
            tp_multiple = random.uniform(4.5, 6.0)  # 6-8% -> 4.5-6.0 ATR
        elif normalized_distance < 0.5:
            # Somewhat close to support
            tp_multiple = random.uniform(3.75, 5.25)  # 5-7% -> 3.75-5.25 ATR
        elif normalized_distance < 0.7:
            # Somewhat close to resistance
            tp_multiple = random.uniform(2.25, 3.75)  # 3-5% -> 2.25-3.75 ATR
        elif normalized_distance < 0.9:
            # Moderately close to resistance
            tp_multiple = random.uniform(1.5, 3.0)  # 2-4% -> 1.5-3.0 ATR
        else:
            # Very close to resistance - narrowest TP
            tp_multiple = random.uniform(1.5, 3.0)  # 2-4% -> 1.5-3.0 ATR
        
        adjusted_tp = adjusted_entry + (atr * tp_multiple)
        
        return {
            "entry": adjusted_entry, 
            "adjustedTP": adjusted_tp, 
            "originalSL": original_sl, 
            "adjustedSL": adjusted_sl
        }
    
    def _adjust_short_entry_and_tp(self, entry, current_price, fibo_levels, price85_value, 
                                  original_tp, atr, bullish, all_inputs):
        """Adjust entry and TP based on Fibonacci levels for Short signals"""
        # Ensure we have a valid entry before proceeding
        if entry is None:
            return {"entry": entry, "adjustedTP": None, "originalSL": None, "adjustedSL": None}
        
        # Calculate original SL to preserve it
        original_sl = self._calculate_short_sl(entry, all_inputs, atr, bullish)
        
        # Sort Fibonacci levels
        sorted_fibo_levels = sorted(fibo_levels)
        
        # Find the two Fibonacci levels closest to current price (one above, one below)
        sup = None
        res = None
        
        # Find support level (below current price)
        for level in reversed(sorted_fibo_levels):
            if level < current_price:
                sup = level
                break
        
        # Find resistance level (above current price)
        for level in sorted_fibo_levels:
            if level > current_price:
                res = level
                break
        
        # If can't find both support and resistance, return original entry
        if sup is None or res is None:
            return {"entry": entry, "adjustedTP": None, "originalSL": original_sl, "adjustedSL": None}
        
        # Check condition: support below both price85 and currentPrice, resistance above both
        # Using same condition as long for consistency
        condition_met = (sup < price85_value and sup < current_price and 
                        res > price85_value and res > current_price)
        
        # If condition not met, return original entry
        if not condition_met:
            return {"entry": entry, "adjustedTP": None, "originalSL": original_sl, "adjustedSL": None}
        
        # Calculate normalized distance from currentPrice to resistance (0 to 1)
        # 0 means currentPrice is at support, 1 means currentPrice is at resistance
        total_range = res - sup
        distance_from_sup = current_price - sup
        normalized_distance = distance_from_sup / total_range
        
        # Adjust entry based on normalized distance tiers using ATR multiples
        if normalized_distance < 0.1:
            # Very close to support - highest entry adjustment
            adjusted_entry = entry + (atr * 1.5)  # 2% -> 1.5 ATR
        elif normalized_distance < 0.3:
            # Moderately close to support
            adjusted_entry = entry + (atr * 1.125)  # 1.5% -> 1.125 ATR
        elif normalized_distance < 0.5:
            # Somewhat close to support
            adjusted_entry = entry + (atr * 0.75)  # 1% -> 0.75 ATR
        elif normalized_distance < 0.7:
            # Somewhat close to resistance
            adjusted_entry = entry - (atr * 0.75)  # 1% -> 0.75 ATR
        elif normalized_distance < 0.9:
            # Moderately close to resistance
            adjusted_entry = entry - (atr * 1.125)  # 1.5% -> 1.125 ATR
        else:
            # Very close to resistance
            adjusted_entry = entry - (atr * 1.5)  # 2% -> 1.5 ATR
        
        # Always generate a new adjustedSL with random ATR multiple
        if bullish == 'NA':
            min_sl_multiple, max_sl_multiple = 2.5, 3.5
        elif bullish == 'On':
            min_sl_multiple, max_sl_multiple = 2.5, 3.5
        elif bullish == 'Off':
            min_sl_multiple, max_sl_multiple = 3.5, 4.5
        
        random_sl_multiple = random.uniform(min_sl_multiple, max_sl_multiple)
        adjusted_sl = adjusted_entry + (atr * random_sl_multiple)
        
        # Recalculate TP using adjusted entry with ATR multiples
        if normalized_distance < 0.1:
            # Very close to support - narrowest TP for short
            tp_multiple = random.uniform(1.5, 3.0)  # 2-4% -> 1.5-3.0 ATR
        elif normalized_distance < 0.3:
            # Moderately close to support
            tp_multiple = random.uniform(1.5, 3.0)  # 2-4% -> 1.5-3.0 ATR
        elif normalized_distance < 0.5:
            # Somewhat close to support
            tp_multiple = random.uniform(2.25, 3.75)  # 3-5% -> 2.25-3.75 ATR
        elif normalized_distance < 0.7:
            # Somewhat close to resistance
            tp_multiple = random.uniform(3.75, 5.25)  # 5-7% -> 3.75-5.25 ATR
        elif normalized_distance < 0.9:
            # Moderately close to resistance
            tp_multiple = random.uniform(4.5, 6.0)  # 6-8% -> 4.5-6.0 ATR
        else:
            # Very close to resistance - widest TP for short
            tp_multiple = random.uniform(5.25, 6.75)  # 7-9% -> 5.25-6.75 ATR
        
        adjusted_tp = adjusted_entry - (atr * tp_multiple)
        
        return {
            "entry": adjusted_entry, 
            "adjustedTP": adjusted_tp, 
            "originalSL": original_sl, 
            "adjustedSL": adjusted_sl
        }
    
    def _find_nearest_levels(self, current_price, all_inputs, fibo_levels):
        """Find the nearest support and resistance levels with minimum 5% distance"""
        # Combine all levels
        all_levels = all_inputs + fibo_levels
        
        # Filter out invalid values
        valid_levels = [x for x in all_levels if not math.isnan(x) and x > 0]
        invalid_count = len(all_levels) - len(valid_levels)
        if invalid_count > 0:
            logger.warning(f"Filtered out {invalid_count} invalid levels (NaN or <= 0)")
        
        # Sort levels for better logging
        sorted_levels = sorted(valid_levels)
        logger.info(f"Found {len(sorted_levels)} total valid levels to check for S/R")
        
        # Calculate 5% thresholds - EXACT match with Zapier implementation
        min_support_threshold = current_price * 0.95  # 5% below current price
        max_resistance_threshold = current_price * 1.05  # 5% above current price
        logger.info(f"Current price: {current_price:.4f}, Support threshold: {min_support_threshold:.4f}, Resistance threshold: {max_resistance_threshold:.4f}")
        
        # Find supports below threshold
        supports = [level for level in valid_levels if level <= min_support_threshold]
        logger.info(f"Found {len(supports)} support candidates below threshold")
        if supports:
            supports_str = ', '.join([f"{s:.4f}" for s in sorted(supports)[-5:]])
            logger.info(f"Top 5 support candidates: {supports_str}")
        
        # Find resistances above threshold
        resistances = [level for level in valid_levels if level >= max_resistance_threshold]
        logger.info(f"Found {len(resistances)} resistance candidates above threshold")
        if resistances:
            resistances_str = ', '.join([f"{r:.4f}" for r in sorted(resistances)[:5]])
            logger.info(f"Top 5 resistance candidates: {resistances_str}")
        
        # Take nearest support (if available)
        support = max(supports) if supports else None
        
        # Take nearest resistance (if available)
        resistance = min(resistances) if resistances else None
        
        # For display purposes, also find the nearest levels regardless of threshold
        levels_below_price = [level for level in valid_levels if level < current_price]
        levels_above_price = [level for level in valid_levels if level > current_price]
        
        # Nearest display levels (might be outside the threshold)
        display_support = max(levels_below_price) if levels_below_price else None
        display_resistance = min(levels_above_price) if levels_above_price else None
        
        if support is not None and resistance is not None:
            logger.info(f"Selected support: {support:.4f}, resistance: {resistance:.4f}")
        else:
            if support is None:
                logger.warning("NO SUPPORT LEVEL FOUND - verify data source matches Zapier (should be gateio)")
                if display_support is not None:
                    logger.info(f"Display support available but outside threshold: {display_support:.4f}")
            if resistance is None:
                logger.warning("NO RESISTANCE LEVEL FOUND - verify data source matches Zapier (should be gateio)")
                if display_resistance is not None:
                    logger.info(f"Display resistance available but outside threshold: {display_resistance:.4f}")
        
        return {"support": support, "resistance": resistance, "display_support": display_support, "display_resistance": display_resistance}

    def _get_support_resistance_text(self, nearest_levels, level_type):
        """Helper to get support/resistance text with fallback to display values"""
        # level_type should be 'support' or 'resistance'
        display_key = f"display_{level_type}"
        
        if nearest_levels[level_type] is not None:
            # If we have a valid level within threshold, use it
            return f"{nearest_levels[level_type]:.4f}"
        elif display_key in nearest_levels and nearest_levels[display_key] is not None:
            # If we have a display level outside threshold, use it
            return f"{nearest_levels[display_key]:.4f}"
        else:
            # No level available
            return "N/A"
    
    def _generate_adjustment_text(self, is_adjusted, original_entry, adjusted_entry, 
                                 original_tp, adjusted_tp, is_long):
        """Generate adjustment text with percentage differences"""
        if not is_adjusted:
            return "Adjustment: ORIGINAL"
        
        entry_diff_percent = ((adjusted_entry - original_entry) / original_entry * 100)
        tp_diff_percent = ((adjusted_tp - original_tp) / original_tp * 100)
        
        entry_sign = '+' if entry_diff_percent >= 0 else ''
        tp_sign = '+' if tp_diff_percent >= 0 else ''
        
        if is_long:
            # For long positions
            if adjusted_entry > original_entry:
                adjustment_type = "AGGRESSIVE"
            else:
                adjustment_type = "CAUTIOUS"
        else:
            # For short positions
            if adjusted_entry > original_entry:
                adjustment_type = "CAUTIOUS"
            else:
                adjustment_type = "AGGRESSIVE"
        
        return f"Adjustment: {adjustment_type} - Entry {entry_sign}{entry_diff_percent:.2f}% - TP {tp_sign}{tp_diff_percent:.2f}%"
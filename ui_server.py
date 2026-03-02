"""
UI Server module.
Provides a web interface for configuring the trading signal system.
"""

import logging
import threading
import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from config_manager import ConfigManager
from signal_engine import SignalEngine
from telegram_sender import TelegramSender
from signal_tracker import SignalTracker

# Configure logging
logger = logging.getLogger('UIServer')

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)  # For flash messages

# Initialize config manager
config_manager = ConfigManager()

# Register routes in nav bar
nav_items = [
    {'route': '/', 'label': 'Dashboard'},
    {'route': '/trading-pairs', 'label': 'Trading Pairs'},
    {'route': '/api-config', 'label': 'API Configuration'},
    {'route': '/risk-parameters', 'label': 'Risk Parameters'},
    {'route': '/data-parameters', 'label': 'Data Parameters'},
    {'route': '/signal-parameters', 'label': 'Signal Parameters'},
    {'route': '/signal-limits', 'label': 'Signal Limits'},
    {'route': '/schedule', 'label': 'Schedule'},
]

@app.route('/')
def index():
    """Render the main dashboard"""
    return render_template('index.html')

@app.route('/signal-parameters', methods=['GET', 'POST'])
def signal_parameters():
    """Manage signal generation parameters"""
    if request.method == 'POST':
        form_type = request.form.get('form_type')
        
        try:
            # Handle different parameter sections
            if form_type == 'fibonacci':
                # Update Fibonacci levels
                fibonacci_levels = {
                    "level1": float(request.form.get('fib_level1', 0.786)),
                    "level2": float(request.form.get('fib_level2', 0.618)),
                    "level3": float(request.form.get('fib_level3', 0.500)),
                    "level4": float(request.form.get('fib_level4', 0.382)),
                    "level5": float(request.form.get('fib_level5', 0.236))
                }
                
                # Validate values are between 0 and 1
                for key, value in fibonacci_levels.items():
                    if value < 0 or value > 1:
                        flash(f"Fibonacci level {key} must be between 0 and 1", "error")
                        return redirect(url_for('signal_parameters'))
                
                config_manager.update_signal_parameters(fibonacci_levels=fibonacci_levels)
                flash("Fibonacci levels updated", "success")
                
            elif form_type == 'atr':
                # Update ATR multipliers
                atr_multipliers = {
                    "long_sl": float(request.form.get('long_sl', 1.5)),
                    "long_tp": float(request.form.get('long_tp', 2.0)),
                    "short_sl": float(request.form.get('short_sl', 1.5)),
                    "short_tp": float(request.form.get('short_tp', 2.0))
                }
                
                # Validate values are positive
                for key, value in atr_multipliers.items():
                    if value <= 0:
                        flash(f"ATR multiplier {key} must be greater than 0", "error")
                        return redirect(url_for('signal_parameters'))
                
                config_manager.update_signal_parameters(atr_multipliers=atr_multipliers)
                flash("ATR multipliers updated", "success")
                
            elif form_type == 'percentiles':
                # Update price percentiles
                counter_trend_percentile = float(request.form.get('counter_trend_percentile', 0.85))
                
                # Validate value is between 0 and 1
                if counter_trend_percentile < 0 or counter_trend_percentile > 1:
                    flash("Counter-trend percentile must be between 0 and 1", "error")
                    return redirect(url_for('signal_parameters'))
                
                price_percentiles = {"counter_trend_percentile": counter_trend_percentile}
                config_manager.update_signal_parameters(price_percentiles=price_percentiles)
                flash("Price percentiles updated", "success")
                
            elif form_type == 'support_resistance':
                # Update support & resistance parameters
                min_distance = float(request.form.get('min_distance', 1.0))
                max_distance = float(request.form.get('max_distance', 5.0))
                
                # Validate values are positive and min < max
                if min_distance <= 0:
                    flash("Minimum distance must be greater than 0", "error")
                    return redirect(url_for('signal_parameters'))
                    
                if max_distance <= min_distance:
                    flash("Maximum distance must be greater than minimum distance", "error")
                    return redirect(url_for('signal_parameters'))
                
                support_resistance = {
                    "minimum_distance_percent": min_distance,
                    "maximum_distance_percent": max_distance
                }
                config_manager.update_signal_parameters(support_resistance=support_resistance)
                flash("Support & resistance parameters updated", "success")
                
            # Clear cache to ensure we get the latest config
            config_manager.clear_cache()
                
        except ValueError:
            flash("Invalid number format. Please enter valid numbers.", "error")
            
    # Get signal parameters configuration
    signal_params = config_manager.get_signal_parameters()
    return render_template('signal_parameters.html', signal_params=signal_params)

@app.route('/trading-pairs', methods=['GET', 'POST'])
def trading_pairs():
    """Manage trading pairs"""
    if request.method == 'POST':
        if 'add_pair' in request.form:
            # Add a new trading pair
            symbol = request.form.get('symbol', '').strip()
            enabled = request.form.get('enabled') == 'on'
            
            if symbol:
                if '/' in symbol:
                    config_manager.add_trading_pair(symbol, enabled)
                    flash(f"Added trading pair: {symbol}", "success")
                else:
                    flash("Invalid trading pair format. Use BASE/QUOTE (e.g., BTC/USDT)", "error")
            else:
                flash("Trading pair symbol is required", "error")
                
        elif 'update_pairs' in request.form:
            # Update existing pairs
            pairs = request.form.getlist('pair_symbol')
            enabled_pairs = request.form.getlist('pair_enabled')
            
            # Get current pairs from config
            current_config = config_manager.get_trading_pairs_config()
            
            # Process each pair
            for pair_data in current_config.get('pairs', []):
                symbol = pair_data.get('symbol')
                if symbol in pairs:
                    enabled = symbol in enabled_pairs
                    config_manager.update_trading_pair(symbol, enabled)
            
            flash("Trading pairs updated", "success")
            
        elif 'remove_pair' in request.form:
            # Remove a trading pair
            symbol = request.form.get('remove_symbol')
            if symbol:
                config_manager.remove_trading_pair(symbol)
                flash(f"Removed trading pair: {symbol}", "success")
                
        # Clear cache to ensure we get the latest config
        config_manager.clear_cache()
                
    # Get trading pairs configuration
    pairs_config = config_manager.get_trading_pairs_config()
    return render_template('trading_pairs.html', pairs_config=pairs_config)

@app.route('/api-config', methods=['GET', 'POST'])
def api_config():
    """Manage exchange configuration"""
    if request.method == 'POST':
        # Update exchange configuration
        primary_exchange = request.form.get('primary_exchange', '').strip()
        
        # Handle backup exchanges as comma-separated list
        backup_exchanges_str = request.form.get('backup_exchanges', '').strip()
        backup_exchanges = [ex.strip() for ex in backup_exchanges_str.split(',') if ex.strip()]
        
        config_manager.update_api_credentials(
            primary_exchange=primary_exchange if primary_exchange else None,
            backup_exchanges=backup_exchanges if backup_exchanges else None
        )
        flash("Exchange configuration updated", "success")
        
        # Clear cache to ensure we get the latest config
        config_manager.clear_cache()
            
    # Get API configuration
    config = config_manager.get_api_credentials()
    return render_template('api_config.html', config=config)

@app.route('/risk-parameters', methods=['GET', 'POST'])
def risk_parameters():
    """Manage risk parameters"""
    if request.method == 'POST':
        try:
            # Update risk parameters
            vault_balance = request.form.get('vault_balance', '').strip()
            long_risk = request.form.get('long_risk', '').strip()
            short_risk = request.form.get('short_risk', '').strip()
            
            # Convert and validate values
            vault_balance = float(vault_balance) if vault_balance else None
            long_risk = float(long_risk) if long_risk else None
            short_risk = float(short_risk) if short_risk else None
            
            # Check for valid values
            if vault_balance is not None and vault_balance <= 0:
                flash("Vault balance must be greater than zero", "error")
            elif long_risk is not None and (long_risk <= 0 or long_risk > 1):
                flash("Long risk must be between 0 and 1", "error")
            elif short_risk is not None and (short_risk <= 0 or short_risk > 1):
                flash("Short risk must be between 0 and 1", "error")
            else:
                config_manager.update_risk_parameters(
                    default_vault_balance=vault_balance,
                    long_risk=long_risk,
                    short_risk=short_risk
                )
                flash("Risk parameters updated", "success")
                
                # Clear cache to ensure we get the latest config
                config_manager.clear_cache()
                
        except ValueError:
            flash("Invalid number format. Please enter valid numbers.", "error")
            
    # Get risk parameters configuration
    risk_config = config_manager.get_risk_parameters()
    return render_template('risk_parameters.html', risk_config=risk_config)

@app.route('/data-parameters', methods=['GET', 'POST'])
def data_parameters():
    """Manage data fetching parameters"""
    if request.method == 'POST':
        try:
            # Update data parameters
            atr_interval = request.form.get('atr_interval', '').strip()
            price_interval = request.form.get('price_interval', '').strip()
            price_results = request.form.get('price_results', '').strip()
            
            # Convert and validate values
            price_results = int(price_results) if price_results else None
            
            # Check for valid values
            if price_results is not None and price_results < 50:
                flash("Price results must be at least 50", "error")
            else:
                config_manager.update_data_parameters(
                    atr_interval=atr_interval if atr_interval else None,
                    price_interval=price_interval if price_interval else None,
                    price_results=price_results
                )
                flash("Data parameters updated", "success")
                
                # Clear cache to ensure we get the latest config
                config_manager.clear_cache()
                
        except ValueError:
            flash("Invalid number format. Please enter valid numbers.", "error")
            
    # Get data parameters configuration
    data_config = config_manager.get_data_parameters()
    return render_template('data_parameters.html', data_config=data_config)

@app.route('/signal-limits', methods=['GET', 'POST'])
def signal_limits():
    """Manage signal rate limiting"""
    signal_tracker = SignalTracker(config_manager)
    
    if request.method == 'POST':
        # Update signal limits
        signal_period_hours = request.form.get('signal_period_hours', '6')
        max_long_signals = request.form.get('max_long_signals', '1')
        max_short_signals = request.form.get('max_short_signals', '1')
        
        try:
            config_manager.update_signal_limits(
                signal_period_hours=int(signal_period_hours),
                max_long_signals=int(max_long_signals),
                max_short_signals=int(max_short_signals)
            )
            flash("Signal limit settings updated", "success")
        except ValueError:
            flash("Invalid values provided. Please enter numbers only.", "danger")
        
        # Clear cache to ensure we get the latest config
        config_manager.clear_cache()
    
    # Get signal limits configuration
    config = config_manager.get_signal_limits()
    
    # Get current signal counts
    signal_counts = signal_tracker.get_signal_counts()
    
    return render_template('signal_limits.html', config=config, signal_counts=signal_counts)

@app.route('/schedule', methods=['GET', 'POST'])
def schedule():
    """Manage execution schedule"""
    if request.method == 'POST':
        try:
            # Update schedule
            minutes_str = request.form.get('run_at_minutes', '').strip()
            
            if minutes_str:
                # Parse comma-separated minutes
                minutes = [int(m.strip()) for m in minutes_str.split(',')]
                
                # Validate minutes
                invalid_minutes = [m for m in minutes if m < 0 or m > 59]
                
                if invalid_minutes:
                    flash(f"Invalid minutes: {invalid_minutes}. Minutes must be between 0 and 59.", "error")
                else:
                    config_manager.update_schedule(run_at_minutes=minutes)
                    flash("Schedule updated", "success")
                    
                    # Clear cache to ensure we get the latest config
                    config_manager.clear_cache()
                    
        except ValueError:
            flash("Invalid format. Please enter valid numbers separated by commas.", "error")
            
    # Get schedule configuration
    schedule_config = config_manager.get_schedule()
    return render_template('schedule.html', schedule_config=schedule_config)

@app.route('/notification', methods=['GET', 'POST'])
def notification():
    """Manage notification settings"""
    if request.method == 'POST':
        # Update notification settings
        webhook_url = request.form.get('webhook_url', '').strip()
        enabled = request.form.get('enabled') == 'on'
        
        config_manager.update_notification(
            telegram_webhook_url=webhook_url if webhook_url else None,
            telegram_enabled=enabled
        )
        flash("Notification settings updated", "success")
        
        # Clear cache to ensure we get the latest config
        config_manager.clear_cache()
            
    # Get notification configuration
    notification_config = config_manager.get_notification()
    return render_template('notification.html', notification_config=notification_config)

@app.route('/api/check-config')
def check_config():
    """API endpoint to check if configuration is valid and return configuration data"""
    # Check all configuration
    trading_pairs = config_manager.get_trading_pairs()
    api_credentials = config_manager.get_api_credentials()
    risk_params = config_manager.get_risk_parameters()
    data_params = config_manager.get_data_parameters()
    schedule_config = config_manager.get_schedule()
    notification_config = config_manager.get_notification()
    
    # Basic validation - just need trading pairs and an exchange
    is_valid = (
        len(trading_pairs) > 0 and
        api_credentials.get('primary_exchange', '') != ''
    )
    
    return jsonify({
        "valid": is_valid,
        "trading_pairs_count": len(trading_pairs),
        "trading_pairs": trading_pairs,
        "primary_exchange": api_credentials.get('primary_exchange', 'gateio'),
        "backup_exchanges": api_credentials.get('backup_exchanges', []),
        "exchange": api_credentials.get('primary_exchange', 'gateio'), # For backward compatibility
        "data_params": {
            "atr_interval": data_params.get('intervals', {}).get('atr', '1h'),
            "price_interval": data_params.get('intervals', {}).get('price', '5m'),
            "price_results": data_params.get('results', {}).get('price', 300)
        },
        "schedule": schedule_config.get('run_at_minutes', [1, 31]),
        "risk": {
            "vault_balance": risk_params.get('default_vault_balance', 500),
            "long_risk": risk_params.get('long_risk', 0.003),
            "short_risk": risk_params.get('short_risk', 0.003)
        },
        "notifications": {
            "telegram_enabled": notification_config.get('telegram', {}).get('enabled', True)
        }
    })

def start_ui_server(host='0.0.0.0', port=5000, debug=False):
    """Start the UI server in a separate thread"""
    def run_server():
        # Create templates directory if it doesn't exist
        os.makedirs('templates', exist_ok=True)
        
        # Create static directory if it doesn't exist
        os.makedirs('static', exist_ok=True)
        
        logger.info(f"Starting UI server on {host}:{port}")
        app.run(host=host, port=port, debug=debug, use_reloader=False)
    
    server_thread = threading.Thread(target=run_server)
    server_thread.daemon = True  # Allow the thread to exit when the main thread exits
    server_thread.start()
    
    logger.info("UI server thread started")
    return server_thread

if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Start the UI server in the main thread when running this file directly
    app.run(host='0.0.0.0', port=5000, debug=True)

"""
Main application entry point for trading signal system.
Orchestrates the workflow and manages scheduling.
"""

import schedule
import time
import logging
import sys
import argparse
import random
from datetime import datetime

from config_manager import ConfigManager
from ui_server import start_ui_server
from data_provider import DataProvider
from signal_engine import SignalEngine
from telegram_sender import TelegramSender
from signal_tracker import SignalTracker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("trading_signals.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger('Main')

# Initialize config manager
config_manager = ConfigManager()

def run_signal_generation():
    """
    Main workflow function that runs the signal generation process.
    1. Fetches data for each trading pair
    2. Generates signals based on the data
    3. Sends valid signals to Telegram
    """
    start_time = datetime.now()
    logger.info(f"Starting signal generation at {start_time}")
    
    try:
        # Initialize components
        data_provider = DataProvider()
        signal_engine = SignalEngine()
        telegram_sender = TelegramSender()
        signal_tracker = SignalTracker(config_manager)
        
        # Get trading pairs
        trading_pairs = config_manager.get_trading_pairs()
        
        # Randomize the order of trading pairs for each run
        random.shuffle(trading_pairs)  # In-place randomization
        
        # Track signal stats
        pairs_processed = 0
        signals_generated = 0
        signals_sent = 0
        errors_encountered = 0
        
        # Process each trading pair
        for pair in trading_pairs:
            try:
                logger.info(f"Processing {pair}...")
                
                # Get data for this pair
                pair_data = data_provider.get_all_pair_data(pair)
                
                if not pair_data:
                    logger.warning(f"No data available for {pair}, skipping")
                    continue
                
                pairs_processed += 1
                
                # Generate signals
                logger.info(f"DEBUG [{pair}] Calling signal_engine.generate_signals with current price {pair_data.get('price', 'N/A').split(',')[-1] if pair_data.get('price') else 'N/A'}")
                signals = signal_engine.generate_signals(pair_data)
                
                if not signals:
                    logger.warning(f"DEBUG [{pair}] No signals generated at all")
                    continue
                    
                # Only count actual trading signals, not "No Scalping Signal" messages
                real_signals = [s for s in signals if s.get('signal_text') != "No Scalping Signal"]
                
                # Debug log for signal filtering
                if len(signals) > 0:
                    logger.info(f"DEBUG [{pair}] Signal breakdown: {len(signals)} total signals generated")
                    logger.info(f"DEBUG [{pair}] Signal types: {[s.get('position', 'unknown') for s in signals]}")
                    
                    no_signal_count = len([s for s in signals if s.get('signal_text') == "No Scalping Signal"])
                    if no_signal_count > 0:
                        logger.info(f"DEBUG [{pair}] Filtered: {no_signal_count} 'No Scalping Signal' messages removed")
                
                if real_signals:
                    signals_generated += len(real_signals)
                    logger.info(f"DEBUG [{pair}] Generated {len(real_signals)} actual trading signals")
                    
                    # Send valid signals
                    for signal in real_signals:
                        signal_text = signal.get('signal_text')
                        
                        if not signal_text:
                            logger.warning(f"Empty signal_text for {pair}, skipping send")
                            continue
                            
                        # Extract position type (long/short) from signal
                        position_type = signal.get('position', '').lower()
                        
                        # Check if signal can be sent based on tracker
                        if position_type in ['long', 'short']:
                            can_send = signal_tracker.can_send_signal(pair, position_type)
                            logger.info(f"DEBUG [{pair}] Signal tracker check for {position_type}: {'PASSED' if can_send else 'FAILED (rate-limited)'}")
                            
                            if can_send:
                                logger.info(f"DEBUG [{pair}] Attempting to send {position_type} signal for {pair}: {signal_text[:50]}...")
                                if telegram_sender.send_signal(signal_text):
                                    # Record that signal was sent
                                    signal_tracker.record_signal(pair, position_type)
                                    signals_sent += 1
                                    logger.info(f"DEBUG [{pair}] Signal sent SUCCESSFULLY")
                                else:
                                    logger.error(f"Failed to send signal for {pair}")
                        else:
                            logger.info(f"Skipping {position_type} signal for {pair} due to rate limiting")
                
            except Exception as e:
                errors_encountered += 1
                logger.error(f"Error processing {pair}: {e}", exc_info=True)
        
        # Log completion statistics
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.info("="*50)
        logger.info(f"SIGNAL GENERATION SUMMARY:")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info(f"Pairs processed: {pairs_processed}/{len(trading_pairs)}")
        logger.info(f"Signals generated: {signals_generated}")
        logger.info(f"Signals sent: {signals_sent}")
        logger.info(f"Signals filtered: {signals_generated - signals_sent} (by rate limiting or other filters)")
        logger.info(f"Errors encountered: {errors_encountered}")
        
        # Log telegram statistics
        stats = telegram_sender.get_statistics()
        logger.info(f"Telegram delivery stats: {stats['sent']} sent, {stats['failed']} failed, {stats['success_rate']:.1f}% success rate")
        logger.info("="*50)
        
        return {
            "success": True,
            "pairs_processed": pairs_processed,
            "signals_generated": signals_generated,
            "signals_sent": signals_sent,
            "errors": errors_encountered,
            "duration": duration
        }
        
    except Exception as e:
        logger.error(f"Critical error in signal generation: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }

def main(start_ui=True, ui_port=5000):
    """
    Main application entry point.
    Sets up scheduling and manages the application lifecycle.
    
    Args:
        start_ui (bool): Whether to start the UI server
        ui_port (int): Port to run the UI server on
    """
    logger.info("=" * 80)
    logger.info("TRADING SIGNAL SYSTEM STARTING")
    
    # Start UI server if requested
    if start_ui:
        logger.info(f"Starting UI server on port {ui_port}...")
        start_ui_server(port=ui_port)
    
    # Get configuration
    trading_pairs = config_manager.get_trading_pairs()
    schedule_config = config_manager.get_schedule()
    run_at_minutes = schedule_config.get('run_at_minutes', [1, 31])
    
    logger.info(f"Monitoring {len(trading_pairs)} trading pairs")
    logger.info(f"Scheduled to run at minutes {', '.join(str(m) for m in run_at_minutes)} past each hour")
    logger.info("=" * 80)
    
    # Run once immediately on startup
    logger.info("Running initial signal generation...")
    result = run_signal_generation()
    
    if not result.get('success', False):
        logger.warning("Initial run completed with errors. Check logs for details.")
    else:
        logger.info(f"Initial run completed successfully. Sent {result.get('signals_sent', 0)} signals.")
    
    # Schedule runs at specific minutes past each hour
    for minute in run_at_minutes:
        schedule.every().hour.at(f":{minute:02d}").do(run_signal_generation)
        logger.info(f"Scheduled to run at :{minute:02d} minutes past each hour")
    
    logger.info(f"Signal generation will run at minutes: {', '.join(str(m) for m in run_at_minutes)} past each hour")
    
    # Keep running
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")
    except Exception as e:
        logger.critical(f"Critical error: {e}")
    finally:
        logger.info("=" * 80)
        logger.info("TRADING SIGNAL SYSTEM STOPPED")
        logger.info("=" * 80)

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='AutoZAP Trading Signal System')
    parser.add_argument('--no-ui', action='store_true', help='Disable the UI server')
    parser.add_argument('--ui-port', type=int, default=5000, help='Port for the UI server')
    args = parser.parse_args()
    
    # Start the main application
    main(start_ui=not args.no_ui, ui_port=args.ui_port)

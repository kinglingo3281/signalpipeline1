"""
Telegram Sender module.
Handles formatting and delivery of trading signals to Telegram.
"""

import requests
import urllib3
import json as json_lib
import logging
import time
from datetime import datetime
import re

from config_manager import ConfigManager
from signal_tracker import SignalTracker

logger = logging.getLogger('TelegramSender')

class TelegramSender:
    """
    Handles sending trading signals to Telegram via webhook.
    Manages formatting, retries, and error handling.
    """
    
    def __init__(self):
        """Initialize the Telegram Sender"""
        self.config_manager = ConfigManager()
        self.signal_tracker = SignalTracker(self.config_manager)
        self.sent_count = 0
        self.failed_count = 0
        
    def _extract_pair(self, message):
        """Extract trading pair from message"""
        pair_match = re.search(r'([A-Z0-9]{2,10})/([A-Z]{2,5})', message)
        if pair_match:
            return pair_match.group(0)
        return None
    
    def _extract_signal_type(self, message):
        """Extract signal type (long or short) from message"""
        if "LONG" in message:
            return "long"
        elif "SHORT" in message:
            return "short"
        return None
        
    def _format_message(self, message):
        """Format the message for Telegram (adds emojis, etc)"""
        # Add emoji based on signal type
        if "LONG" in message:
            message = "🟢 " + message  # Green circle for LONG
        elif "SHORT" in message:
            message = "🔴 " + message  # Red circle for SHORT
        else:
            message = "ℹ️ " + message  # Info symbol for other messages
            
        return message
    
    def send_signal(self, message, retries=3):
        """Send a signal message to the Telegram bot"""
        # Make sure we have content to send
        if not message or message == "No Scalping Signal":
            logger.debug(f"Empty or 'No Scalping Signal' message, skipping: {message}")
            return True
            
        # Extract trading pair and signal type from the message
        pair = self._extract_pair(message)
        signal_type = self._extract_signal_type(message)
        
        # Check if we've hit the rate limit for this pair/signal type
        if pair and signal_type:
            if not self.signal_tracker.can_send_signal(pair, signal_type):
                logger.info(f"Rate limit reached for {pair} {signal_type}, skipping signal")
                return False
        
        try:
            # Get notification config and log it for debugging
            notification_config = self.config_manager.get_notification()
            logger.info(f"Notification config: {notification_config}")
            
            telegram_enabled = notification_config.get('telegram', {}).get('enabled', True)
            telegram_webhook = notification_config.get('telegram', {}).get('webhook_url', '')
            
            logger.info(f"Telegram enabled: {telegram_enabled}, Webhook URL set: {'Yes' if telegram_webhook else 'No'}")
            
            # Only check if notifications are disabled
                
            if not telegram_enabled:
                logger.info("Telegram notifications are disabled in config")
                return True
                
            if not telegram_webhook:
                logger.error("Telegram webhook URL is not set in config")
                return False
                
            # Prepare payload
            payload = {
                "text": self._format_message(message),
                "parse_mode": "MarkdownV2"
            }
            
            # Send with retry logic
            max_retries = retries
            retry_count = 0
            
            while retry_count < max_retries:
                try:
                    logger.info(f"Sending signal (attempt {retry_count + 1}/{max_retries})...")
                    
                    # Send to Telegram webhook
                    response = requests.post(
                        self.config_manager.get_notification().get('telegram', {}).get('webhook_url', ''),
                        json=payload,
                        timeout=10  # 10 second timeout
                    )
                    
                    # Also send to secondary webhook with a cleaned payload
                    # Remove escape characters used by Telegram markdown
                    clean_message = message
                    if clean_message:
                        # Remove markdown escape characters (backslashes before special chars)
                        clean_message = re.sub(r'\\([_*[\]()~`>#+-=|{}.!])', r'\1', clean_message)
                        # Remove markdown formatting
                        clean_message = re.sub(r'`([^`]+)`', r'\1', clean_message)
                    
                    webhook_payload = {
                        "signal": self._format_message(clean_message)
                    }
                    
                    logger.info(f"Sending to secondary webhook: {webhook_payload}")
                    
                    # Use urllib3 directly to avoid requests connection pooling
                    http = urllib3.PoolManager(num_pools=1, maxsize=1, block=False)
                    
                    webhook_response = http.request(
                        'POST',
                        'http://localhost:3001/signal',
                        body=json_lib.dumps(webhook_payload),
                        headers={'Content-Type': 'application/json'},
                        timeout=10.0
                    )
                    http.clear()  # Clear connection pool
                    
                    if webhook_response.status != 200:
                        logger.warning(f"Failed to send to secondary webhook: {webhook_response.status}, {webhook_response.data.decode('utf-8')}")
                    
                    # ALSO send to SSE server for database insertion and V4 client distribution
                    try:
                        # Use urllib3 directly for SSE server too
                        sse_http = urllib3.PoolManager(num_pools=1, maxsize=1, block=False)
                        
                        sse_response = sse_http.request(
                            'POST',
                            'http://localhost:3002/api/v3-signal',
                            body=json_lib.dumps(webhook_payload),
                            headers={
                                "Authorization": "Bearer [YOUR_SIGNAL_AUTH_TOKEN]",
                                "Content-Type": "application/json"
                            },
                            timeout=10.0
                        )
                        sse_http.clear()  # Clear connection pool
                        
                        if sse_response.status == 200:
                            logger.info(f"V3 signal sent to SSE server successfully")
                        else:
                            logger.warning(f"SSE server returned {sse_response.status}: {sse_response.data.decode('utf-8')}")
                            
                    except Exception as e:
                        logger.error(f"Failed to send V3 signal to SSE server: {e}")
                        # Don't fail the whole operation if SSE server is down
                    
                    # Check response
                    if response.status_code == 200:
                        self.sent_count += 1
                        logger.info(f"Signal sent successfully ({self.sent_count} total sent)")
                        
                        # Record this signal if we extracted the pair and type
                        if pair and signal_type:
                            self.signal_tracker.record_signal(pair, signal_type)
                        
                        return True
                    
                    # Handle rate limiting
                    elif response.status_code == 429:
                        retry_after = int(response.headers.get('Retry-After', 1))
                        logger.warning(f"Rate limited. Waiting {retry_after} seconds.")
                        time.sleep(retry_after)
                    
                    # Other errors
                    else:
                        logger.error(f"Error sending signal: {response.status_code}, {response.text}")
                        time.sleep(1)  # 1 second delay before retry
                    
                    retry_count += 1
                    
                except requests.RequestException as e:
                    logger.error(f"Request exception: {e}")
                    time.sleep(1)  # 1 second delay before retry
                    retry_count += 1
            
            # If we reach here, all retries failed
            self.failed_count += 1
            logger.error(f"Failed to send signal after {max_retries} attempts ({self.failed_count} total failures)")
            return False
            
        except Exception as e:
            self.failed_count += 1
            logger.error(f"Unexpected error sending signal: {e}")
            return False
    
    def get_statistics(self):
        """
        Get delivery statistics
        
        Returns:
            dict: Statistics about message delivery
        """
        total = self.sent_count + self.failed_count
        success_rate = (self.sent_count / total * 100) if total > 0 else 0
        
        return {
            "sent": self.sent_count,
            "failed": self.failed_count,
            "total": total,
            "success_rate": success_rate
        }

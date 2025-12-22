"""SMS service using Twilio."""
import logging

logger = logging.getLogger("sms_service")

try:
    from twilio.rest import Client
    from config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN
    
    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
        twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        logger.info("✅ Twilio SMS client initialized")
    else:
        twilio_client = None
        logger.warning("⚠️ Twilio credentials not found - SMS disabled")
except ImportError:
    twilio_client = None
    logger.warning("⚠️ Twilio SDK not installed - SMS disabled")


async def send_sms(from_number: str, to_number: str, message: str) -> bool:
    """Send SMS via Twilio.
    
    Args:
        from_number: Sender phone number (E.164 format)
        to_number: Recipient phone number (E.164 format)
        message: SMS message body
        
    Returns:
        True if SMS sent successfully, False otherwise
    """
    if not twilio_client:
        logger.warning("⚠️ Twilio not configured - cannot send SMS")
        return False
    
    if not from_number:
        logger.error("❌ No sender number available for SMS")
        return False
    
    try:
        result = twilio_client.messages.create(
            to=to_number,
            from_=from_number,
            body=message
        )
        logger.info(f"✅ SMS sent from {from_number} to {to_number}: {result.sid}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to send SMS to {to_number}: {e}")
        return False

"""SMS service using Twilio."""
import logging

logger = logging.getLogger("sms_service")

try:
    from twilio.rest import Client
    from config import (
        TWILIO_ACCOUNT_SID, 
        TWILIO_AUTH_TOKEN, 
        TWILIO_API_KEY_SID, 
        TWILIO_API_KEY_SECRET,
        TWILIO_FROM_NUMBER
    )
    
    # Try API Key authentication first (more secure), then fall back to Auth Token
    if TWILIO_API_KEY_SID and TWILIO_API_KEY_SECRET and TWILIO_ACCOUNT_SID:
        twilio_client = Client(TWILIO_API_KEY_SID, TWILIO_API_KEY_SECRET, TWILIO_ACCOUNT_SID)
        logger.info("✅ Twilio SMS client initialized (API Key)")
    elif TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
        twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        logger.info("✅ Twilio SMS client initialized (Auth Token)")
    else:
        twilio_client = None
        logger.warning("⚠️ Twilio credentials not found - SMS disabled")
    
    # Validate A2P certified number is configured
    if twilio_client and TWILIO_FROM_NUMBER:
        logger.info(f"✅ A2P certified sender number configured: {TWILIO_FROM_NUMBER}")
    elif twilio_client:
        logger.warning("⚠️ TWILIO_FROM_NUMBER not configured - SMS may fail")
        
except ImportError:
    twilio_client = None
    TWILIO_FROM_NUMBER = None
    logger.warning("⚠️ Twilio SDK not installed - SMS disabled")


async def send_sms(to_number: str, message: str, from_number: str = None) -> bool:
    """Send SMS via Twilio using the A2P certified number.
    
    Args:
        to_number: Recipient phone number (E.164 format)
        message: SMS message body
        from_number: Optional sender phone number (defaults to TWILIO_FROM_NUMBER)
        
    Returns:
        True if SMS sent successfully, False otherwise
    """
    if not twilio_client:
        logger.warning("⚠️ Twilio not configured - cannot send SMS")
        return False
    
    # Use A2P certified number as default
    sender = from_number or TWILIO_FROM_NUMBER
    
    if not sender:
        logger.error("❌ No sender number available for SMS (TWILIO_FROM_NUMBER not configured)")
        return False
    
    try:
        result = twilio_client.messages.create(
            to=to_number,
            from_=sender,
            body=message
        )
        logger.info(f"✅ SMS sent from {sender} to {to_number}: {result.sid}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to send SMS to {to_number}: {e}")
        return False


async def send_mms(to_number: str, message: str, media_urls: list[str], from_number: str = None) -> bool:
    """Send MMS (SMS with images) via Twilio using the A2P certified number.
    
    Args:
        to_number: Recipient phone number (E.164 format)
        message: SMS message body
        media_urls: List of public URLs to images (JPEG, PNG, GIF up to 5MB each, max 10 images)
        from_number: Optional sender phone number (defaults to TWILIO_FROM_NUMBER)
        
    Returns:
        True if MMS sent successfully, False otherwise
    """
    if not twilio_client:
        logger.warning("⚠️ Twilio not configured - cannot send MMS")
        return False
    
    # Use A2P certified number as default
    sender = from_number or TWILIO_FROM_NUMBER
    
    if not sender:
        logger.error("❌ No sender number available for MMS (TWILIO_FROM_NUMBER not configured)")
        return False
    
    if not media_urls:
        logger.error("❌ No media URLs provided for MMS")
        return False
    
    try:
        result = twilio_client.messages.create(
            to=to_number,
            from_=sender,
            body=message,
            media_url=media_urls
        )
        logger.info(f"✅ MMS sent from {sender} to {to_number} with {len(media_urls)} images: {result.sid}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to send MMS to {to_number}: {e}")
        return False

"""Reservation tools."""
from livekit.agents import function_tool, RunContext
from typing import Optional
import logging
from config import BASE_URL
from services.sms_service import send_sms

logger = logging.getLogger("reservation_tools")


def create_reservation_tools(assistant):
    """Create reservation-related tools for the assistant."""
    
    @function_tool()
    async def make_reservation(
        ctx: RunContext,
        customer_name: str,
        date: str,
        time: str,
        party_size: int,
        customer_phone: Optional[str] = None,
    ) -> str:
        """Make reservation after collecting all info: name, date (YYYY-MM-DD), time (HH:MM), party size.
        
        Args:
            customer_name: Name
            date: YYYY-MM-DD
            time: HH:MM (24-hour)
            party_size: Number of people
            customer_phone: Optional phone
        """
        logger.info(f"📅 Making reservation for {customer_name} on {date} at {time} for {party_size}")
        
        if not assistant.api_session:
            return "Error: API session not available"

        if not assistant.store_id:
            logger.error("No store ID available")
            return "Error: Unable to make reservation"

        reservation_data = {
            "storeId": assistant.store_id,
            "customerName": customer_name,
            "customerPhone": customer_phone or assistant.caller_phone,
            "date": date,
            "time": time,
            "partySize": party_size
        }

        logger.info(f"Submitting reservation: {reservation_data}")
        async with assistant.api_session.post(
            f"{BASE_URL}/api/reservations", 
            json=reservation_data
        ) as resp:
            if resp.status in (200, 201):
                result = await resp.json()
                logger.info(f"✅ Reservation confirmed: {result}")
                
                # Send SMS confirmation to customer
                customer_phone_number = customer_phone or assistant.caller_phone
                if customer_phone_number:
                    try:
                        # Format date and time for SMS
                        from datetime import datetime
                        try:
                            date_obj = datetime.strptime(date, "%Y-%m-%d")
                            formatted_date = date_obj.strftime("%B %d, %Y")  # e.g., "December 25, 2025"
                        except:
                            formatted_date = date
                        
                        try:
                            time_obj = datetime.strptime(time, "%H:%M")
                            formatted_time = time_obj.strftime("%I:%M %p")  # e.g., "07:00 PM"
                        except:
                            formatted_time = time
                        
                        store_name = getattr(assistant, 'store_name', 'our restaurant')
                        sms_message = (
                            f"🎉 Reservation Confirmed!\n\n"
                            f"Name: {customer_name}\n"
                            f"Date: {formatted_date}\n"
                            f"Time: {formatted_time}\n"
                            f"Party Size: {party_size} people\n"
                            f"Location: {store_name}\n\n"
                            f"We look forward to seeing you! Call (618) 258-1888 if you need to modify."
                        )
                        
                        await send_sms(customer_phone_number, sms_message)
                        logger.info(f"✅ Reservation confirmation SMS sent to {customer_phone_number}")
                    except Exception as sms_error:
                        logger.error(f"❌ Failed to send reservation SMS: {sms_error}")
                        # Don't fail the reservation if SMS fails
                
                return f"Perfect! Your reservation for {party_size} people on {date} at {time} is confirmed."
            else:
                details = await resp.text()
                logger.error(f"❌ Reservation failed: {resp.status} - {details}")
                return "I'm sorry, I couldn't complete your reservation. Please try calling back."
    
    return [make_reservation]

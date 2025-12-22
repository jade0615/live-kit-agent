"""Reservation tools."""
from livekit.agents import function_tool, RunContext
from typing import Optional
import logging
from config import BASE_URL

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
                return f"Perfect! Your reservation for {party_size} people on {date} at {time} is confirmed."
            else:
                details = await resp.text()
                logger.error(f"❌ Reservation failed: {resp.status} - {details}")
                return "I'm sorry, I couldn't complete your reservation. Please try calling back."
    
    return [make_reservation]

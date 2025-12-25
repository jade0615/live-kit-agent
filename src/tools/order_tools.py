"""Order placement and SMS notification tools."""
from livekit.agents import function_tool, RunContext
from datetime import datetime, timedelta
import pytz
import logging
from config import BASE_URL

logger = logging.getLogger("order_tools")


def create_order_tools(assistant):
    """Create order-related tools for the assistant."""
    
    @function_tool()
    async def place_order(
        ctx: RunContext,
        items: list[str],
        customer_name: str,
        pickup_time: str = "",
    ) -> str:
        """
        Place order and send SMS notifications to customer and merchant.
        Does NOT end the call - customer may want to add more items.
        
        Args:
            items: Item names to order
            customer_name: Customer's name (MUST ask first)
            pickup_time: When customer wants to pick up (e.g., "11:30 AM", "in 20 minutes", "tomorrow at 1 PM")
                         If not provided, defaults to 20 minutes from now
        """
        logger.info(f"📦 Placing order for {customer_name}: {items}, pickup: {pickup_time or 'in 20 min'}")
        
        if not assistant.api_session:
            return "Error: API session not available"
        
        if not assistant.menu_by_category:
            from services.api_client import load_menu
            assistant.menu_by_category = await load_menu(assistant.store_id, assistant.api_session)
        
        # Build order from menu items
        item_lookup = {}
        for category, category_items in assistant.menu_by_category.items():
            for item in category_items:
                item_lookup[item['name'].lower()] = item
    
        order_items = []
        total = 0.0
        found_items = []
        
        for item_name in items:
            item_info = item_lookup.get(item_name.lower())
            if item_info:
                price = float(item_info['price'])
                order_items.append({
                    "name": item_info['name'],
                    "quantity": 1,
                    "price": price,
                    "id": item_info.get('id')
                })
                total += price
                found_items.append(item_info['name'])
        
        if not order_items:
            return "No valid items found in the order."

        # Calculate pickup time for SMS
        cst = pytz.timezone('America/Chicago')
        
        if pickup_time:
            # Customer specified a time - use it directly
            formatted_pickup = pickup_time
        else:
            # Default to 20 minutes from now
            formatted_pickup = (datetime.now(cst) + timedelta(minutes=20)).strftime("%I:%M %p")
        
        logger.info(f"🕐 Pickup time for SMS: {formatted_pickup}")

        # Submit order to API (WITHOUT pickup_time)
        order_data = {
            "storeId": assistant.store_id,
            "customerName": customer_name,
            "customerPhone": assistant.caller_phone,
            "items": order_items,
            "total": f"{total:.2f}"
        }
        
        async with assistant.api_session.post(
            f"{BASE_URL}/api/orders", 
            json=order_data
        ) as response:
            if response.status not in (200, 201):
                logger.error(f"❌ Order failed: {response.status}")
                return "I'm sorry, there was an issue placing your order. Please try calling back."
        
        logger.info(f"✅ Order placed successfully: {found_items}")
        
        # Generate payment link
        payment_link = f"https://www.miaojieai.com/pay/{assistant.store_id}/order"
        
        # Send SMS to customer (WITH pickup time)
        from services.sms_service import send_sms
        
        # Use hardcoded test number for now
        test_customer_phone = "+13239529493"  # Your friend's number for testing
        
        customer_sms = (
            f"Hi {customer_name}! Order confirmed at {assistant.store_name}. "
            f"Total: ${total:.2f}. Pickup: {formatted_pickup}. "
            f"Pay here: {payment_link}"
        )
        await send_sms(test_customer_phone, customer_sms)
        logger.info(f"✅ Order SMS sent to TEST number: {test_customer_phone}")
        
        # Send SMS to merchant (WITH pickup time)
        # Use hardcoded test merchant number for now
        test_merchant_phone = "+12173186661"
        
        items_list = ", ".join(found_items)
        merchant_sms = (
            f"🔔 New Order! {customer_name} - {test_customer_phone}. "
            f"Items: {items_list}. Total: ${total:.2f}. Pickup: {formatted_pickup}"
        )
        await send_sms(test_merchant_phone, merchant_sms)
        logger.info(f"✅ Order notification SMS sent to TEST merchant: {test_merchant_phone}")
        
        # Return success (WITH pickup time in confirmation)
        return f"Perfect! Your order for {', '.join(found_items)} totaling ${total:.2f} is confirmed for pickup at {formatted_pickup}. You'll receive a text message with payment details shortly."
    
    return [place_order]

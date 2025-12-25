"""Menu-related tools for the assistant."""
from livekit.agents import function_tool, RunContext
from typing import List
import logging

logger = logging.getLogger("menu_tools")


def create_menu_tools(assistant):
    """Create menu-related tools for the assistant."""
    
    @function_tool()
    async def get_menu_by_category(ctx: RunContext, category: str) -> List[str]:
        """Get items in a category.
        
        Args:
            category: Category name (e.g., "Chicken", "Beef")
        """
        logger.info(f"Fetching category: {category}")
        
        if not assistant.menu_by_category:
            from services.api_client import load_menu
            assistant.menu_by_category = await load_menu(assistant.store_id, assistant.api_session)
        
        for cat_name, items in assistant.menu_by_category.items():
            if cat_name.lower() == category.lower():
                item_names = [item['name'] for item in items]
                logger.info(f"Found {len(item_names)} items in '{cat_name}'")
                return item_names
        
        logger.warning(f"Category '{category}' not found")
        return [f"Category '{category}' not available"]

    @function_tool()
    async def search_menu_items(ctx: RunContext, item_names: list[str]) -> str:
        """Search for specific items across ALL menu categories with smart keyword matching.
        
        Use this when customer mentions specific items they want to order.
        Searches the entire menu with fuzzy matching - finds partial matches.
        
        Args:
            item_names: List of item names customer mentioned (e.g., ["Orange Chicken", "Fried Rice"])
        
        Returns:
            String with found items or suggestions for close matches
        """
        logger.info(f"🔍 Searching entire menu for: {item_names}")
        
        if not assistant.menu_by_category:
            from services.api_client import load_menu
            assistant.menu_by_category = await load_menu(assistant.store_id, assistant.api_session)
        
        # Build list of all items with their details
        all_items = []
        for category, items in assistant.menu_by_category.items():
            for item in items:
                all_items.append({
                    'name': item['name'],
                    'name_lower': item['name'].lower(),
                    'price': float(item['price']),
                    'category': category
                })
        
        results = []
        
        for search_term in item_names:
            search_lower = search_term.lower().strip()
            search_words = set(search_lower.split())
            
            # Try exact match first
            exact_match = None
            for item in all_items:
                if item['name_lower'] == search_lower:
                    exact_match = item
                    break
            
            if exact_match:
                results.append(f"✓ Found: {exact_match['name']} (${exact_match['price']:.2f})")
                logger.info(f"✅ Exact match: {exact_match['name']}")
                continue
            
            # Smart keyword matching - score each item
            matches = []
            for item in all_items:
                item_words = set(item['name_lower'].split())
                
                # Score based on matching words
                matching_words = search_words & item_words
                if not matching_words:
                    continue
                
                # Calculate match score
                match_ratio = len(matching_words) / len(search_words)
                
                # Bonus for substring match
                substring_bonus = 0
                if search_lower in item['name_lower']:
                    substring_bonus = 0.5
                
                score = match_ratio + substring_bonus
                
                matches.append({
                    'item': item,
                    'score': score,
                    'matching_words': len(matching_words)
                })
            
            # Sort by score (best first)
            matches.sort(key=lambda x: (x['score'], x['matching_words']), reverse=True)
            
            if matches:
                # If best match has high confidence (>= 80%), return it
                if matches[0]['score'] >= 0.8:
                    best = matches[0]['item']
                    results.append(f"✓ Found: {best['name']} (${best['price']:.2f})")
                    logger.info(f"✅ High-confidence match for '{search_term}': {best['name']} (score: {matches[0]['score']:.2f})")
                else:
                    # Return top 3 suggestions for confirmation
                    top_matches = matches[:3]
                    suggestions = []
                    for i, match in enumerate(top_matches, 1):
                        item = match['item']
                        suggestions.append(f"{i}. {item['name']} (${item['price']:.2f})")
                    
                    results.append(
                        f"❓ Did you mean one of these for '{search_term}'?\n" + 
                        "\n".join(suggestions) +
                        "\nWhich one would you like?"
                    )
                    logger.info(f"🤔 Multiple matches for '{search_term}': {[m['item']['name'] for m in top_matches]}")
            else:
                results.append(f"✗ Sorry, couldn't find '{search_term}' on our menu.")
                logger.warning(f"❌ No matches found for '{search_term}'")
        
        return "\n\n".join(results)

    @function_tool()
    async def get_item_prices(ctx: RunContext, item_names: list[str]) -> str:
        """Get prices for one or more menu items and calculate total.
        
        Use when customer asks about price(s) for items they mentioned.
        The LLM should track items mentioned in conversation context.
        
        Args:
            item_names: List of menu item names (can be 1 or more items)
        
        Returns:
            Formatted string with individual prices and total (if multiple items)
        """
        logger.info(f"Looking up prices for: {item_names}")
        
        if not assistant.menu_by_category:
            from services.api_client import load_menu
            assistant.menu_by_category = await load_menu(assistant.store_id, assistant.api_session)
        
        # Build a lookup dictionary for fast searching
        item_lookup = {}
        for category, items in assistant.menu_by_category.items():
            for item in items:
                item_lookup[item['name'].lower()] = {
                    'name': item['name'],  # Preserve original capitalization
                    'price': float(item['price'])
                }
        
        found_items = []
        not_found = []
        total = 0.0
        
        # Look up each item
        for item_name in item_names:
            item_info = item_lookup.get(item_name.lower())
            if item_info:
                found_items.append(item_info)
                total += item_info['price']
            else:
                not_found.append(item_name)
        
        # Format response
        if not found_items and not_found:
            return f"Sorry, I couldn't find: {', '.join(not_found)}"
        
        response_parts = []
        
        # List individual items and prices
        for item in found_items:
            response_parts.append(f"{item['name']}: ${item['price']:.2f}")
        
        # Add total if multiple items
        if len(found_items) > 1:
            response_parts.append(f"Total: ${total:.2f}")
        
        # Mention not found items
        if not_found:
            response_parts.append(f"(Couldn't find: {', '.join(not_found)})")
        
        logger.info(f"✅ Found {len(found_items)} items, total: ${total:.2f}")
        return "\n".join(response_parts)
    
    @function_tool()
    async def send_menu_pictures(ctx: RunContext) -> str:
        """Send menu pictures to customer via SMS/MMS.
        
        Use this when customer requests to see the full menu or menu pictures.
        Sends the complete menu images to their phone number.
        
        Returns:
            Success or failure message
        """
        test_customer_phone = "+13239529493"  # Hardcoded test customer
        logger.info(f"📸 Sending menu pictures to customer: {test_customer_phone}")
        
        try:
            from services.sms_service import send_mms
            from config import MENU_IMAGE_URLS
            
            # Check if menu URLs are configured
            if not MENU_IMAGE_URLS or all(url.startswith("https://your-server.com") for url in MENU_IMAGE_URLS):
                logger.error("❌ Menu image URLs not configured")
                return "Sorry, menu pictures are currently unavailable. Please ask about specific items or categories."
            
            # Send MMS with menu images
            message = f"Here's our complete menu from {assistant.store_name}! 📋🍜"
            success = await send_mms(
                to_number=test_customer_phone,
                message=message,
                media_urls=MENU_IMAGE_URLS
            )
            
            if success:
                logger.info(f"✅ Menu pictures sent successfully to {test_customer_phone}")
                return f"Perfect! I've sent the complete menu to your phone. You should receive it in a moment. Take your time looking it over!"
            else:
                logger.error(f"❌ Failed to send menu pictures to {test_customer_phone}")
                return "Sorry, I had trouble sending the menu pictures. Would you like me to tell you about specific categories instead?"
                
        except Exception as e:
            logger.error(f"❌ Error sending menu pictures: {e}")
            return "Sorry, I had trouble sending the menu pictures. Would you like me to tell you about specific categories instead?"
    
    return [get_menu_by_category, search_menu_items, get_item_prices, send_menu_pictures]

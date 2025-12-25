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
    
    return [get_menu_by_category, get_item_prices]

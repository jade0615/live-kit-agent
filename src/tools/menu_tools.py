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
    async def get_item_price(ctx: RunContext, item_name: str) -> str:
        """Get price ONLY when customer explicitly asks "how much".
        
        Args:
            item_name: Menu item name
        """
        logger.info(f"Looking up price for: {item_name}")
        
        if not assistant.menu_by_category:
            from services.api_client import load_menu
            assistant.menu_by_category = await load_menu(assistant.store_id, assistant.api_session)
        
        item_lower = item_name.lower()
        for category, items in assistant.menu_by_category.items():
            for item in items:
                if item['name'].lower() == item_lower:
                    price = item['price']
                    logger.info(f"Price for '{item['name']}': ${price}")
                    return f"${price}"
        
        return f"Item '{item_name}' not found"
    
    return [get_menu_by_category, get_item_price]

"""Knowledge base search tools."""
from livekit.agents import function_tool, RunContext
from datetime import datetime
import pytz
import logging
from typing import Dict, List

logger = logging.getLogger("knowledge_tools")


def create_knowledge_tools(assistant):
    """Create knowledge base search tools for the assistant."""
    
    @function_tool()
    async def search_knowledge_base(ctx: RunContext, query: str) -> str:
        """Search FAQs for hours, policies, location, delivery, etc.
        
        Args:
            query: Keywords (e.g., "hours", "delivery", "location")
        """
        logger.info(f"🔍 Searching knowledge base for: {query}")
        
        if not assistant.knowledge_base:
            from services.api_client import load_knowledge_base
            assistant.knowledge_base = await load_knowledge_base(assistant.store_id, assistant.api_session)
        
        if not assistant.knowledge_base:
            return "I don't have that information. Please call us directly."
        
        query_lower = query.lower()
        results = []
        
        for entry in assistant.knowledge_base:
            question = entry.get('question', '').lower()
            answer = entry.get('answer', '')
            
            if query_lower in question or any(word in question for word in query_lower.split()):
                results.append(f"Q: {entry.get('question', '')}\nA: {answer}")
        
        if results:
            logger.info(f"Found {len(results)} matches")
            return "\n\n".join(results[:3])
        else:
            logger.info("No matches found")
            return f"I don't have info about '{query}'. Anything else I can help with?"

    @function_tool()
    async def check_current_time(ctx: RunContext) -> str:
        """Get current date and time in CST timezone. Use this to:
        - Check if restaurant is open
        - Calculate pickup times (e.g., "in 20 minutes" = current time + 20 min)
        - Handle reservations (e.g., "tomorrow at 7 PM" = tomorrow's date + 19:00)
        - Validate times are in the future
        """
        cst = pytz.timezone('America/Chicago')
        current_time = datetime.now(cst)
        
        current_time_str = current_time.strftime("%I:%M %p")
        current_day = current_time.strftime("%A")
        current_date = current_time.strftime("%Y-%m-%d")
        current_time_24h = current_time.strftime("%H:%M")
        
        logger.info(f"🕐 Current CST time: {current_time_str} on {current_day}")
        
        return f"""Current date and time (CST):
- Day: {current_day}, {current_date}
- Time: {current_time_str} (24h: {current_time_24h})

Use this to calculate:
- "in 20 minutes" = add 20 minutes to current time
- "tomorrow" = {current_date} + 1 day
- Validate that order/reservation times are in the future"""

    @function_tool()
    async def get_knowledge_base(ctx: RunContext) -> List[Dict]:
        """Get raw FAQ data. Use search_knowledge_base instead for better results."""
        logger.info(f"Fetching knowledge base for store: {assistant.store_id}")
        
        if not assistant.api_session:
            return {"error": "API session not available"}
        
        from config import BASE_URL
        async with assistant.api_session.get(
            f"{BASE_URL}/api/knowledge-base/{assistant.store_id}"
        ) as response:
            if response.status == 200:
                return await response.json()
            return {"error": f"Failed to fetch knowledge base: {response.status}"}

    @function_tool()
    async def get_store(ctx: RunContext) -> Dict:
        """Get store details. Use search_knowledge_base for customer questions."""
        logger.info(f"Fetching store details: {assistant.store_id}")
        
        if not assistant.api_session:
            return {"error": "API session not available"}
        
        from config import BASE_URL
        async with assistant.api_session.get(
            f"{BASE_URL}/api/stores/{assistant.store_id}"
        ) as response:
            if response.status == 200:
                return await response.json()
            return {"error": f"Failed to fetch store: {response.status}"}
    
    return [search_knowledge_base, check_current_time, get_knowledge_base, get_store]

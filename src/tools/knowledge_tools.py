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
        """Search FAQs for hours, policies, location, pricing, menu items, etc.
        
        Use SPECIFIC search terms for best results:
        - For pricing: "kids pricing", "adult pricing", "crab legs price", "lunch price"  
        - For menu: "crab legs", "sushi", "vegetarian"
        - For info: "hours", "location", "payment", "delivery"
        
        Returns the most relevant FAQ entries ranked by relevance.
        
        Args:
            query: Specific keywords or question (e.g., "kids pricing", "crab legs")
        """
        logger.info(f"🔍 Searching knowledge base for: {query}")
        
        if not assistant.knowledge_base:
            from services.api_client import load_knowledge_base
            assistant.knowledge_base = await load_knowledge_base(assistant.store_id, assistant.api_session)
        
        if not assistant.knowledge_base:
            return "I don't have that information. Please call us directly."
        
        query_lower = query.lower().strip()
        
        # Synonym mapping for better matching
        synonyms = {
            'kids': ['children', 'kid', 'child'],
            'children': ['kids', 'kid', 'child'],
            'price': ['cost', 'pricing', 'how much'],
            'cost': ['price', 'pricing', 'how much'],
            'hours': ['open', 'close', 'time'],
            'crab legs': ['crab', 'seafood boil'],
            'takeout': ['to-go', 'take out', 'carryout'],
            'to-go': ['takeout', 'take out', 'carryout']
        }
        
        # Expand query with synonyms
        query_words = set(query_lower.split())
        for word in list(query_words):
            if word in synonyms:
                query_words.update(synonyms[word])
        
        scored_results = []
        
        for entry in assistant.knowledge_base:
            question = entry.get('question', '').lower()
            answer = entry.get('answer', '')
            score = 0
            
            # 1. Exact question match (highest score)
            if query_lower == question:
                score += 1000
            
            # 2. Query is substring of question (very high score)
            elif query_lower in question:
                score += 500
            
            # 3. Question is substring of query (high score)
            elif question in query_lower:
                score += 400
            
            # 4. Word overlap scoring
            question_words = set(question.split())
            common_words = query_words & question_words
            
            # Filter out common stopwords for better matching
            stopwords = {'do', 'you', 'have', 'is', 'are', 'the', 'a', 'an', 'what', 'how', 'when', 'where', 'can', 'i'}
            meaningful_common = common_words - stopwords
            
            if meaningful_common:
                # Score based on percentage of meaningful words matched
                score += len(meaningful_common) * 50
                
                # Bonus for matching multiple important words
                if len(meaningful_common) >= 2:
                    score += 100
            
            # 5. Bonus for matching key terms
            key_terms = ['free', 'crab legs', 'pricing', 'hours', 'location', 'delivery', 'takeout', 'to-go', 'kids', 'children']
            for term in key_terms:
                if term in query_lower and term in question:
                    score += 150
            
            # Only include results with meaningful matches (score threshold)
            if score >= 50:  # Minimum threshold to filter out weak matches
                scored_results.append({
                    'entry': entry,
                    'score': score,
                    'question': entry.get('question', ''),
                    'answer': answer
                })
        
        # Sort by score (highest first)
        scored_results.sort(key=lambda x: x['score'], reverse=True)
        
        if scored_results:
            # Log scoring details for debugging
            logger.info(f"Found {len(scored_results)} matches (top score: {scored_results[0]['score']})")
            if len(scored_results) > 1:
                logger.info(f"Top 3 scores: {[r['score'] for r in scored_results[:3]]}")
            
            # Return ALL relevant results (but limit to top 5 for efficiency)
            # This ensures we don't overwhelm the LLM while still providing complete info
            top_results = scored_results[:5]
            formatted_results = [f"Q: {r['question']}\nA: {r['answer']}" for r in top_results]
            
            return "\n\n".join(formatted_results)
        else:
            logger.info("No matches found")
            return f"I don't have specific info about '{query}'. You can call us at (618) 258-1888 for details."

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

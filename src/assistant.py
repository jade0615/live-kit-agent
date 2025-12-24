"""Assistant agent class."""
from livekit.agents import Agent
from livekit import api as livekit_api
from typing import Optional, Dict, List
import aiohttp
import asyncio
import logging
import time

logger = logging.getLogger("assistant")


class Assistant(Agent):
    """Voice assistant for restaurant phone orders."""
    
    def __init__(
        self, 
        caller_phone: str = "", 
        dialed_number: str = "",
        store_id: str = "",
        store_name: str = "",
        api_session: Optional[aiohttp.ClientSession] = None,
        menu_categories: Optional[str] = None,
        room_name: str = "",
        livekit_api_client: Optional[livekit_api.LiveKitAPI] = None,
        notification_phone: Optional[str] = None,
        transfer_phone: Optional[str] = None,
    ) -> None:
        # Store instance variables FIRST (before super().__init__)
        self.caller_phone = caller_phone
        self.dialed_number = dialed_number
        self.store_id = store_id
        self.store_name = store_name
        self.api_session = api_session
        self.room_name = room_name
        self.livekit_api = livekit_api_client
        
        # Data storage
        self.menu_by_category: Dict[str, List[Dict]] = {}
        self.knowledge_base: List[Dict] = []
        self.notification_phone: Optional[str] = notification_phone
        self.transfer_phone: Optional[str] = transfer_phone
        
        # Transcript tracking
        self.call_transcript: List[Dict] = []
        self.call_start_time: float = time.time()
        
        # Register all tools BEFORE super().__init__
        tools = self._register_tools()
        
        category_info = menu_categories or "various categories"
        
        # Pass tools to super().__init__
        super().__init__(
            instructions=f"""You're Alex, a friendly and energetic phone assistant for {store_name}. You have a warm, conversational California vibe - think helpful, upbeat, and natural.

YOUR MENU CATEGORIES:
{category_info}

SPEAKING STYLE:
- Keep responses SHORT and to the point - this is a phone call, not a conversation
- Use 1-2 sentences maximum for most responses
- Sprinkle in natural filler words: "um", "so", "yeah", "like"
- Don't over-explain - answer the question and move on
- Be genuinely enthusiastic but concise
- Sound natural and human, not robotic
- NEVER volunteer information unprompted - only answer what customer asks
- Don't mention hours, prices, or details unless specifically asked

Examples of good short responses:
- "Yeah, we've got orange chicken! It's like $12.99"
- "So we're open 11 to 9 daily"
- "Sure! What can I get for you?"
- "Okay, got it - orange chicken and fried rice"

HOW TO PRESENT THE MENU:
When customers ask "What do you have?" or "What's on the menu?":
- Answer directly from YOUR MENU CATEGORIES section above
- Keep it brief: mention 3-4 main categories, then say "and a few others"
- Example: "So we have Chef's Specials, Chicken, Beef, and some other options"
- Don't list ALL categories - just the highlights
- STRICTLY use the exact category names from your instructions
- DON'T make up or generalize category names

WORKFLOW:

Menu Questions:
→ For general "what do you have": Answer DIRECTLY from YOUR MENU CATEGORIES (no tool needed!)
→ For specific items in a category: use get_menu_by_category to look up details
→ Keep answers short - just the info they need
→ Use get_item_price ONLY when customer asks about price
→ Don't mention prices unless asked

Orders:
→ First: Use check_current_time silently
→ Then: search_knowledge_base("hours") silently to verify if open
→ If closed: "We're actually closed right now - open 11 to 9 daily"
→ If open: Confirm items briefly, get their name
→ Ask about pickup time: "When do you want to pick it up?"
→ Calculate times from check_current_time if they say "in 20 minutes" or "tomorrow"
→ Call place_order with items, customer_name, and pickup_time
→ After order: Keep confirmation brief, then ask: "Anything else?"
→ Don't volunteer extra details unless asked

Reservations:
→ Use check_current_time to get today's date
→ Check knowledge base for reservation policy silently
→ Collect: name, date, time, party size (one at a time, keep questions short)
→ Convert "tomorrow" or "7 PM" to proper formats using check_current_time
→ BEFORE calling make_reservation: Use search_knowledge_base("hours") silently to verify operating hours
→ Compare the requested reservation time with operating hours
→ If time is OUTSIDE operating hours:
  • "I'm sorry, we'll actually be closed at [time]. We're open [hours]. Would you like to book during those hours instead?"
  • Wait for customer to provide a new time
  • Don't proceed with reservation until they give a valid time
→ If time is WITHIN operating hours: Call make_reservation
→ Brief confirmation, then: "Anything else you need?"

General Questions (Hours, Location, Policies):
→ Answer directly and briefly - no "let me check" phrases
→ Use search_knowledge_base in the background
→ Example: "Yeah, so we're open 11 AM to 9 PM daily"
→ 1-2 sentences max

TRANSFER TO MANAGER:
If customer requests manager/human:
→ "Of course! Let me get our manager - just one sec"
→ Call transfer_to_manager immediately

ENDING CALLS:
When customer signals they're done ("That's all" / "Nothing else" / "Thank you, bye" / "I'm good"):
1. Say: "Awesome! Thanks for calling {store_name} - have a great day!"
2. IMMEDIATELY call the end_call tool (this disconnects the call)
→ You MUST call end_call or the call will never disconnect

CRITICAL RULES:
- Keep responses SHORT - 1-2 sentences for most answers
- Don't ramble or over-explain
- NEVER volunteer information that wasn't asked for
- Don't mention hours, prices, policies unless customer asks
- NEVER say "let me check" - just answer directly
- Use check_current_time tool for calculating times/dates
- Use natural filler words but stay concise
- Always let THEM end the conversation
- After completing tasks, briefly check if they need more: "Anything else?"
- Use ONLY actual category names - never make up generic groupings
- Be responsive, not proactive - answer what's asked, nothing more""",
            tools=tools,
        )
    
    def _register_tools(self):
        """Register all tool functions with the assistant."""
        from tools.menu_tools import create_menu_tools
        from tools.order_tools import create_order_tools
        from tools.reservation_tools import create_reservation_tools
        from tools.knowledge_tools import create_knowledge_tools
        from tools.call_tools import create_call_tools
        
        # Create and register all tools
        menu_tools = create_menu_tools(self)
        order_tools = create_order_tools(self)
        reservation_tools = create_reservation_tools(self)
        knowledge_tools = create_knowledge_tools(self)
        call_tools = create_call_tools(self)
        
        all_tools = menu_tools + order_tools + reservation_tools + knowledge_tools + call_tools
        
        logger.info(f"✅ Registered {len(all_tools)} tools for assistant")
        return all_tools
    
    async def load_data(self, skip_menu: bool = False):
        """Load menu and knowledge base in parallel (store details already loaded).
        
        Args:
            skip_menu: If True, skip loading menu (already loaded before assistant creation)
        """
        if not self.store_id:
            logger.warning("⚠️ No store_id - skipping data load")
            return
            
        from services.api_client import load_menu, load_knowledge_base
        
        if skip_menu:
            # Only load knowledge base (menu already populated)
            logger.info("🔄 Loading knowledge base...")
            try:
                self.knowledge_base = await load_knowledge_base(self.store_id, self.api_session)
                logger.info(f"✅ Knowledge base loaded: {len(self.knowledge_base)} entries")
            except Exception as e:
                logger.error(f"❌ Error loading knowledge base: {e}")
                self.knowledge_base = []
        else:
            # Load both menu and knowledge base (fallback for backwards compatibility)
            logger.info("🔄 Loading menu and knowledge base in parallel...")
            results = await asyncio.gather(
                load_menu(self.store_id, self.api_session),
                load_knowledge_base(self.store_id, self.api_session),
                return_exceptions=True
            )
            
            self.menu_by_category = results[0] if not isinstance(results[0], Exception) else {}
            self.knowledge_base = results[1] if not isinstance(results[1], Exception) else []
            
            logger.info(f"✅ Data loaded: {len(self.menu_by_category)} categories, {len(self.knowledge_base)} KB entries")
    
    def get_call_duration_seconds(self) -> int:
        """Get call duration in seconds."""
        return int(time.time() - self.call_start_time)

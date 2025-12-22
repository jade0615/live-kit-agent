from livekit import rtc
import aiohttp
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import logging
import asyncio
from dotenv import load_dotenv
from livekit.agents import (
    NOT_GIVEN,
    Agent,
    AgentFalseInterruptionEvent,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    RoomInputOptions,
    WorkerOptions,
    cli,
    metrics,
    function_tool,
    RunContext,
)
from livekit.plugins import cartesia, deepgram, noise_cancellation, openai,assemblyai, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel


logger = logging.getLogger("agent")
load_dotenv(".env.local")


class Assistant(Agent):
    def __init__(
        self, 
        caller_phone: str = "", 
        dialed_number: str = "",
        store_id: str = "",
        store_name: str = "",
        api_session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        super().__init__(
            instructions=f"""You're a voice assistant for {store_name}. Be natural and brief.

Menu: Use get_menu_categories for "what do you have", get_menu_by_category for items, get_item_price ONLY when asked price.

Orders: Confirm items, ask name, call place_order.

Questions: For hours/location/policies/delivery, use search_knowledge_base.

Reservations: Check knowledge base first. Collect name/date/time/party_size, call make_reservation.

Always use tools. Never guess."""
        )
        
        self.base_url = "https://www.miaojieai.com"
        self.api_session = api_session
        self.caller_phone = caller_phone
        self.dialed_number = dialed_number
        self.store_id = store_id
        self.store_name = store_name
        self.menu_by_category: Dict[str, List[Dict]] = {}
        self.knowledge_base: List[Dict] = []

    async def load_menu(self):
        """Background task to load menu data."""
        if self.menu_by_category:
            return
            
        logger.info(f"📋 Background: Loading menu for store {self.store_id}")
        
        if not self.api_session:
            logger.error("No API session available")
            return
        
        async with self.api_session.get(f"{self.base_url}/api/menu/{self.store_id}") as response:
            if response.status != 200:
                logger.warning(f"Could not fetch menu: {response.status}")
                return
            
            menu_data = await response.json()
            
            menu_by_category = defaultdict(list)
            for item in menu_data:
                category = item.get('category', 'Other')
                menu_by_category[category].append({
                    'name': item.get('name'),
                    'price': item.get('basePrice'),
                    'id': item.get('id'),
                })
            
            self.menu_by_category = dict(menu_by_category)
            logger.info(f"✅ Menu loaded: {len(self.menu_by_category)} categories, {sum(len(items) for items in self.menu_by_category.values())} items")

    async def load_knowledge_base(self):
        """Background task to load knowledge base (FAQs)."""
        if self.knowledge_base:
            return
            
        logger.info(f"📚 Background: Loading knowledge base for store {self.store_id}")
        
        if not self.api_session:
            logger.error("No API session available")
            return
        
        async with self.api_session.get(f"{self.base_url}/api/knowledge-base/{self.store_id}") as response:
            if response.status != 200:
                logger.warning(f"Could not fetch knowledge base: {response.status}")
                return
            
            kb_data = await response.json()
            self.knowledge_base = kb_data if isinstance(kb_data, list) else []
            logger.info(f"✅ Knowledge base loaded: {len(self.knowledge_base)} entries")

    async def load_data(self):
        """Load both menu and knowledge base in parallel."""
        if not self.store_id:
            logger.warning("⚠️ No store_id - skipping data load")
            return
            
        logger.info("🔄 Loading menu and knowledge base in parallel...")
        await asyncio.gather(
            self.load_menu(),
            self.load_knowledge_base(),
            return_exceptions=True
        )

    @function_tool()
    async def get_menu_categories(self, ctx: RunContext) -> List[str]:
        """Get menu categories when customer asks what's available."""
        logger.info("Fetching menu categories")
        
        await ctx.session.say("Just a moment, let me pull up our menu.")
        
        if not self.menu_by_category:
            await self.load_menu()
        
        main_categories = []
        addon_categories = []
        
        for category in sorted(self.menu_by_category.keys()):
            cat_lower = category.lower()
            if any(keyword in cat_lower for keyword in ['add-on', 'side', 'extra', 'sauce', 'drink', 'beverage']):
                addon_categories.append(category)
            else:
                main_categories.append(category)
        
        all_categories = main_categories + addon_categories
        logger.info(f"Returning {len(all_categories)} categories")
        return all_categories

    @function_tool()
    async def get_menu_by_category(self, ctx: RunContext, category: str) -> List[str]:
        """Get items in a category.
        
        Args:
            category: Category name (e.g., "Chicken", "Beef")
        """
        logger.info(f"Fetching category: {category}")
        
        await ctx.session.say(f"Let me get our {category} options.")
        
        if not self.menu_by_category:
            await self.load_menu()
        
        for cat_name, items in self.menu_by_category.items():
            if cat_name.lower() == category.lower():
                item_names = [item['name'] for item in items]
                logger.info(f"Found {len(item_names)} items in '{cat_name}'")
                return item_names
        
        logger.warning(f"Category '{category}' not found")
        return [f"Category '{category}' not available"]

    @function_tool()
    async def get_item_price(self, ctx: RunContext, item_name: str) -> str:
        """Get price ONLY when customer explicitly asks "how much".
        
        Args:
            item_name: Menu item name
        """
        logger.info(f"Looking up price for: {item_name}")
        
        await ctx.session.say("Let me check that price.")
        
        if not self.menu_by_category:
            await self.load_menu()
        
        item_lower = item_name.lower()
        for category, items in self.menu_by_category.items():
            for item in items:
                if item['name'].lower() == item_lower:
                    price = item['price']
                    logger.info(f"Price for '{item['name']}': ${price}")
                    return f"${price}"
        
        return f"Item '{item_name}' not found"

    @function_tool()
    async def search_knowledge_base(self, ctx: RunContext, query: str) -> str:
        """Search FAQs for hours, policies, location, delivery, etc.
        
        Args:
            query: Keywords (e.g., "hours", "delivery", "location")
        """
        logger.info(f"🔍 Searching knowledge base for: {query}")
        
        await ctx.session.say("Let me look that up.")
        
        if not self.knowledge_base:
            await self.load_knowledge_base()
        
        if not self.knowledge_base:
            return "I don't have that information. Please call us directly."
        
        query_lower = query.lower()
        results = []
        
        for entry in self.knowledge_base:
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
    async def place_order(
        self,
        ctx: RunContext,
        items: list[str],
        customer_name: str,
    ) -> str:
        """Place order after confirming items and getting customer name.
        
        Args:
            items: Item names to order
            customer_name: Customer's name (MUST ask first)
        """
        logger.info(f"Placing order for {customer_name}: {items}")
        
        await ctx.session.say("Perfect! Let me get that order placed.")
        
        if not self.api_session:
            return "Error: API session not available"
        
        if not self.menu_by_category:
            await self.load_menu()
        
        item_lookup = {}
        for category, category_items in self.menu_by_category.items():
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

        data = {
            "storeId": self.store_id,
            "customerName": customer_name,
            "customerPhone": self.caller_phone,
            "items": order_items,
            "total": f"{total:.2f}"
        }
        
        async with self.api_session.post(
            f"{self.base_url}/api/orders", 
            json=data
        ) as response:
            if response.status in (200, 201):
                logger.info(f"Order placed successfully: {found_items}")
                return f"Success: Order placed for {', '.join(found_items)}"
            else:
                logger.error(f"Order failed: {response.status}")
                return f"Error: Failed to place order"

    @function_tool()
    async def make_reservation(
        self,
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
        
        await ctx.session.say("Perfect! Let me book that reservation.")
        
        if not self.api_session:
            return "Error: API session not available"

        if not self.store_id:
            logger.error("No store ID available")
            return "Error: Unable to make reservation"

        reservation_data = {
            "storeId": self.store_id,
            "customerName": customer_name,
            "customerPhone": customer_phone or self.caller_phone,
            "date": date,
            "time": time,
            "partySize": party_size
        }

        logger.info(f"Submitting reservation: {reservation_data}")
        async with self.api_session.post(
            f"{self.base_url}/api/reservations", 
            json=reservation_data
        ) as resp:
            if resp.status in (200, 201):
                result = await resp.json()
                logger.info(f"✅ Reservation confirmed: {result}")
                return f"Success: Reservation confirmed for {customer_name} on {date} at {time} for {party_size} people"
            else:
                details = await resp.text()
                logger.error(f"❌ Reservation failed: {resp.status} - {details}")
                return f"Error: Unable to complete reservation. Please try again or call us."

    @function_tool()
    async def get_knowledge_base(self, ctx: RunContext) -> List[Dict]:
        """Get raw FAQ data. Use search_knowledge_base instead for better results."""
        logger.info(f"Fetching knowledge base for store: {self.store_id}")
        
        if not self.api_session:
            return {"error": "API session not available"}
        
        async with self.api_session.get(
            f"{self.base_url}/api/knowledge-base/{self.store_id}"
        ) as response:
            if response.status == 200:
                return await response.json()
            return {"error": f"Failed to fetch knowledge base: {response.status}"}

    @function_tool()
    async def get_store(self, ctx: RunContext) -> Dict:
        """Get store details. Use search_knowledge_base for customer questions."""
        logger.info(f"Fetching store details: {self.store_id}")
        
        if not self.api_session:
            return {"error": "API session not available"}
        
        async with self.api_session.get(
            f"{self.base_url}/api/stores/{self.store_id}"
        ) as response:
            if response.status == 200:
                return await response.json()
            return {"error": f"Failed to fetch store: {response.status}"}


async def fetch_store_info(dialed_number: str) -> Tuple[Optional[str], str, Optional[aiohttp.ClientSession]]:
    """Fetch store ID and name, return authenticated session.
    
    Returns:
        Tuple of (store_id, store_name, api_session)
    """
    base_url = "https://www.miaojieai.com"
    email = "midge6115@gmail.com"
    password = "bd7c90cbea692aa1"
    
    session = aiohttp.ClientSession()
    
    try:
        async with session.post(
            f"{base_url}/api/auth/login",
            json={"email": email, "password": password}
        ) as resp:
            if resp.status != 200:
                logger.error(f"❌ Login failed: {resp.status}")
                await session.close()
                return None, "Unknown Restaurant", None
        
        logger.info(f"📞 Fetching store info for: {dialed_number}")
        
        async def get_store_id():
            async with session.get(f"{base_url}/api/stores/by-phone/{dialed_number}") as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("id") or data.get("_id")
                return None
        
        async def get_store_details(store_id):
            if not store_id:
                return "Unknown Restaurant"
            async with session.get(f"{base_url}/api/stores/{store_id}") as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("name", "Unknown Restaurant")
                return "Unknown Restaurant"
        
        store_id = await get_store_id()
        store_name = await get_store_details(store_id)
        
        logger.info(f"✅ Store: {store_name} (ID: {store_id})")
        return store_id, store_name, session
        
    except Exception as e:
        logger.error(f"❌ Error fetching store info: {e}")
        await session.close()
        return None, "Unknown Restaurant", None


def prewarm(proc: JobProcess):
    """Prewarm VAD model."""
    proc.userdata["vad"] = silero.VAD.load(
        min_silence_duration=0.25,
        prefix_padding_duration=0.1,
        deactivation_threshold=0.35,
        sample_rate=8000,
    )


async def entrypoint(ctx: JobContext):
    """Main entrypoint for the voice agent."""
    ctx.log_context_fields = {"room": ctx.room.name}
    await ctx.connect()

    caller_phone = ""
    dialed_number = ""

    def on_participant_connected(participant: rtc.RemoteParticipant):
        nonlocal caller_phone, dialed_number
        
        if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
            attrs = participant.attributes or {}
            caller_phone = attrs.get("sip.phoneNumber", "")
            dialed_number = attrs.get("sip.trunkPhoneNumber", "")
            logger.info(f"📞 SIP participant: Caller={caller_phone}, Dialed={dialed_number}")
            
            ctx.log_context_fields["caller_phone"] = caller_phone
            ctx.log_context_fields["dialed_number"] = dialed_number

    ctx.room.on("participant_connected", on_participant_connected)

    # Wait for SIP participant with retry
    await asyncio.sleep(0.3)
    
    for participant in ctx.room.remote_participants.values():
        if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
            attrs = participant.attributes or {}
            caller_phone = attrs.get("sip.phoneNumber", "")
            dialed_number = attrs.get("sip.trunkPhoneNumber", "")
            logger.info(f"📞 Existing SIP participant found")
            ctx.log_context_fields["caller_phone"] = caller_phone
            ctx.log_context_fields["dialed_number"] = dialed_number
            break

    # Fetch store info
    store_id = None
    store_name = "our restaurant"
    api_session = None
    
    if dialed_number:
        formatted_number = dialed_number if dialed_number.startswith('+') else f'+{dialed_number}'
        logger.info(f"🚀 Fetching store info for {formatted_number}...")
        store_id, store_name, api_session = await fetch_store_info(formatted_number)
        
        if store_id:
            ctx.log_context_fields["store_id"] = store_id
            ctx.log_context_fields["store_name"] = store_name
    else:
        logger.warning("⚠️ No dialed number - using defaults")

    # ✅ Create assistant EARLY
    assistant = Assistant(
        caller_phone=caller_phone,
        dialed_number=dialed_number,
        store_id=store_id or "",
        store_name=store_name,
        api_session=api_session,
    )

    # ✅ LOAD MENU/KB IMMEDIATELY (before session starts!)
    if store_id and api_session:
        logger.info("🔄 Pre-loading menu and knowledge base...")
        asyncio.create_task(assistant.load_data())
        await asyncio.sleep(0.05)  # Tiny head start

    async def cleanup_session():
        if api_session:
            logger.info("🔒 Closing API session")
            await api_session.close()
    
    ctx.add_shutdown_callback(cleanup_session)

    # Initialize session
    session = AgentSession(
        llm=openai.LLM(
            model="gpt-4.1-mini",  # ✅ Correct model name
            temperature=0.7,
        ),
        stt=assemblyai.STT(model="universal-streaming-english"),
        tts=cartesia.TTS(
            voice="6f84f4b8-58a2-430c-8c79-688dad597532",
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=True,
    )

    @session.on("agent_false_interruption")
    def _on_agent_false_interruption(ev: AgentFalseInterruptionEvent):
        logger.info("False interruption detected - resuming")
        session.generate_reply(instructions=ev.extra_instructions or NOT_GIVEN)

    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Session usage: {summary}")

    ctx.add_shutdown_callback(log_usage)

    logger.info("🎯 Starting agent session...")
    await session.start(
        agent=assistant,
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVCTelephony(),
        ),
    )
    
    # Shorter greeting
    greeting = f"Thank you for calling {store_name}. How may I help you?"
    logger.info(f"💬 Sending greeting: {greeting}")
    await session.generate_reply(instructions=f"Say exactly: '{greeting}'")


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name="telephony_agent",
        )
    )

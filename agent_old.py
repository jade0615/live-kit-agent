from livekit import rtc
from livekit import api as livekit_api
import aiohttp
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import logging
import asyncio
from datetime import datetime, timedelta
import pytz
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
from livekit.plugins import cartesia, deepgram, noise_cancellation, openai, assemblyai, silero
from livekit.plugins.turn_detector.english import EnglishModel
import os

logger = logging.getLogger("agent")
load_dotenv(".env.local")

def prewarm(proc: JobProcess):
        # Build dynamic instructions with hardcoded categories
        category_info = menu_categories or "various categories"
        
        super().__init__(
            instructions=f"""You're Alex, a friendly phone assistant for {store_name}.

YOUR PERSONALITY:
Use natural, minimal acknowledgments (e.g., "Sure", "Let me check", "Okay") to stay warm and responsive. Keep them brief—1-2 words max. Never leave long silences.

YOUR MENU CATEGORIES:
{category_info}

WORKFLOW:

Menu Questions:
- When asked about the menu, directly mention these categories
- Use get_menu_by_category to get specific items
- Use get_item_price ONLY when asked

Orders:
→ First: check_current_time to verify hours
→ Then: search_knowledge_base("hours") to see if the store is open. Donot say this to the customer.
→ If closed: Apologize and share hours
→ If open: Confirm items, get name, then call place_order
→ After placing order, ask: "Is there anything else I can help you with?"

General Questions:
→ Use search_knowledge_base for hours/location/policies

Reservations:
→ Check knowledge base for policy first
→ Collect: name, date, time, party size
→ Call make_reservation
→ After reservation, ask if they need anything else

TRANSFER TO MANAGER:
If customer asks to speak to a manager or human:
- "I want to talk to your manager"
- "Can I speak to someone"
- "Transfer me to a real person"
→ Say: "Of course! Let me transfer you to our manager. Please hold."
→ Then call transfer_to_manager immediately

ENDING THE CALL:
Only call end_call when customer clearly indicates they're done:
- "That's all"
- "Nothing else"
- "Thank you, goodbye"
- "No, I'm good"
- "That'll be it"

Before calling end_call, ALWAYS say: "Thank you for calling {store_name}! Have a great day!"

CRITICAL RULES:
- NEVER end the call immediately after placing an order
- ALWAYS ask if they need anything else after completing a task
- Only end when customer explicitly signals they're done
- Be warm, efficient, and let THEM end the conversation
- If asked for a manager, transfer immediately - don't try to handle it yourself

REMEMBER:
- Brief, natural acknowledgments - not scripted phrases
- Call tools immediately after acknowledging
- Always give customer a chance to add more"""
        )
        
        self.base_url = "https://www.miaojieai.com"
        self.api_session = api_session
        self.caller_phone = caller_phone
        self.dialed_number = dialed_number
        self.store_id = store_id
        self.store_name = store_name
        self.menu_by_category: Dict[str, List[Dict]] = {}
        self.knowledge_base: List[Dict] = []
        self.room_name = room_name
        self.livekit_api = livekit_api_client
        self.notification_phone: Optional[str] = None
        self.transfer_phone: Optional[str] = None  # ✅ NEW

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

    async def load_store_details(self):
        """Load store details including notification phone and transfer phone."""
        if not self.store_id or not self.api_session:
            return
            
        logger.info(f"🏪 Loading store details for: {self.store_id}")
        
        try:
            async with self.api_session.get(f"{self.base_url}/api/stores/{self.store_id}") as response:
                if response.status == 200:
                    store_data = await response.json()
                    self.notification_phone = store_data.get("notificationPhone")
                    self.transfer_phone = store_data.get("transferPhone")  # ✅ NEW
                    logger.info(f"✅ Merchant notification phone: {self.notification_phone}")
                    logger.info(f"✅ Transfer phone: {self.transfer_phone}")
                else:
                    logger.warning(f"Could not fetch store details: {response.status}")
        except Exception as e:
            logger.error(f"Error loading store details: {e}")

    async def load_data(self):
        """Load menu, knowledge base, and store details in parallel."""
        if not self.store_id:
            logger.warning("⚠️ No store_id - skipping data load")
            return
            
        logger.info("🔄 Loading menu, knowledge base, and store details in parallel...")
        await asyncio.gather(
            self.load_menu(),
            self.load_knowledge_base(),
            self.load_store_details(),
            return_exceptions=True
        )

    async def send_sms(self, to_phone: str, message: str) -> bool:
        """Send SMS via Twilio using dialed_number as sender."""
        if not twilio_client:
            logger.warning("⚠️ Twilio not configured - cannot send SMS")
            return False
        
        if not self.dialed_number:
            logger.error("❌ No dialed_number available for SMS sender")
            return False
        
        try:
            result = twilio_client.messages.create(
                to=to_phone,
                from_=self.dialed_number,  # ✅ Use dialed_number as sender
                body=message
            )
            logger.info(f"✅ SMS sent from {self.dialed_number} to {to_phone}: {result.sid}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to send SMS to {to_phone}: {e}")
            return False

    @function_tool()
    async def get_menu_categories(self, ctx: RunContext) -> str:
        """Get menu categories when customer asks what's available."""
        logger.info("Fetching menu categories")
        
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
        
        # Build concise summary
        if not main_categories:
            return "No menu categories available."
        
        # Take first 3-4 main categories as examples
        featured = main_categories[:4]
        remaining_count = len(main_categories) - 4
        
        summary = f"Main categories: {', '.join(featured)}"
        
        if remaining_count > 0:
            summary += f" (plus {remaining_count} more)"
        
        if addon_categories:
            summary += f". Also available: sides, drinks, and extras."
        
        logger.info(f"Returning summary: {summary}")
        return summary

    @function_tool()
    async def get_menu_by_category(self, ctx: RunContext, category: str) -> List[str]:
        """Get items in a category.
        
        Args:
            category: Category name (e.g., "Chicken", "Beef")
        """
        logger.info(f"Fetching category: {category}")
        
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
    async def transfer_to_manager(self, ctx: RunContext) -> str:
        """
        Transfer the call to a live manager/human agent.
        Use when customer explicitly requests:
        - "I want to talk to your manager"
        - "Can I speak to someone"
        - "Transfer me to a person"
        
        Before calling this, say: "Of course! Let me transfer you to our manager. Please hold."
        """
        logger.info("📞 Transferring call to manager...")
        
        if not self.transfer_phone:
            logger.error("❌ No transfer phone configured for this store")
            return "I'm sorry, I don't have a manager number configured. Please call back and ask for assistance."
        
        if not self.livekit_api or not self.room_name:
            logger.error("❌ Cannot transfer - missing LiveKit API or room name")
            return "I'm sorry, I'm unable to transfer calls right now."
        
        # Format phone number for SIP transfer (must be E.164 format with tel: prefix)
        transfer_to = self.transfer_phone if self.transfer_phone.startswith('tel:') else f"tel:{self.transfer_phone}"
        
        logger.info(f"🔄 Initiating transfer to: {transfer_to}")
        
        try:
            # ✅ Find the actual SIP participant identity from the room
            participants = await self.livekit_api.room.list_participants(
                livekit_api.ListParticipantsRequest(room=self.room_name)
            )
            
            sip_participant_identity = None
            for participant in participants.participants:
                if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
                    sip_participant_identity = participant.identity
                    logger.info(f"✅ Found SIP participant: {sip_participant_identity}")
                    break
            
            if not sip_participant_identity:
                logger.error("❌ No SIP participant found in room")
                return "I'm sorry, I couldn't find the active call to transfer."
            
            # Use LiveKit's SIP transfer API with correct participant identity
            await self.livekit_api.sip.transfer_sip_participant(
                livekit_api.TransferSIPParticipantRequest(
                    room_name=self.room_name,
                    participant_identity=sip_participant_identity,  # ✅ CORRECT - e.g., "sip_+923115029332"
                    transfer_to=transfer_to,
                )
            )
            logger.info("✅ Call transfer initiated successfully")
            return "Transferring you now. Please hold."
            
        except Exception as e:
            logger.error(f"❌ Call transfer failed: {e}")
            return "I'm sorry, I couldn't transfer the call. Let me see if I can help you instead."
    
    @function_tool()
    async def search_knowledge_base(self, ctx: RunContext, query: str) -> str:
        """Search FAQs for hours, policies, location, delivery, etc.
        
        Args:
            query: Keywords (e.g., "hours", "delivery", "location")
        """
        logger.info(f"🔍 Searching knowledge base for: {query}")
        
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
        """
        Place order and send SMS notifications to customer and merchant.
        Does NOT end the call - customer may want to add more items.
        
        Args:
            items: Item names to order
            customer_name: Customer's name (MUST ask first)
        """
        logger.info(f"📦 Placing order for {customer_name}: {items}")
        
        if not self.api_session:
            return "Error: API session not available"
        
        if not self.menu_by_category:
            await self.load_menu()
        
        # Build order from menu items
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

        # Submit order to API
        order_data = {
            "storeId": self.store_id,
            "customerName": customer_name,
            "customerPhone": self.caller_phone,
            "items": order_items,
            "total": f"{total:.2f}"
        }
        
        async with self.api_session.post(
            f"{self.base_url}/api/orders", 
            json=order_data
        ) as response:
            if response.status not in (200, 201):
                logger.error(f"❌ Order failed: {response.status}")
                return "I'm sorry, there was an issue placing your order. Please try calling back."
        
        logger.info(f"✅ Order placed successfully: {found_items}")
        
        # Calculate pickup time (20 minutes from now)
        cst = pytz.timezone('America/Chicago')
        pickup_time = (datetime.now(cst) + timedelta(minutes=20)).strftime("%I:%M %p")
        
        # Generate payment link
        payment_link = f"https://www.miaojieai.com/pay/{self.store_id}/order"
        
        # ✅ Send SMS to customer
        customer_sms = (
            f"Hi {customer_name}! Order confirmed at {self.store_name}. "
            f"Total: ${total:.2f}. Pickup: {pickup_time}. "
            f"Pay here: {payment_link}"
        )
        await self.send_sms(self.caller_phone, customer_sms)
        
        # ✅ Send SMS to merchant
        if self.notification_phone:
            items_list = ", ".join(found_items)
            merchant_sms = (
                f"🔔 New Order! {customer_name} - {self.caller_phone}. "
                f"Items: {items_list}. Total: ${total:.2f}. Pickup: {pickup_time}"
            )
            await self.send_sms(self.notification_phone, merchant_sms)
        else:
            logger.warning("⚠️ No notification phone - merchant SMS not sent")
        
        # ✅ Return success - agent will ask if they need anything else
        return f"Perfect! Your order for {', '.join(found_items)} totaling ${total:.2f} is confirmed. You'll receive a text message with payment details and pickup time shortly."

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
                return f"Perfect! Your reservation for {party_size} people on {date} at {time} is confirmed."
            else:
                details = await resp.text()
                logger.error(f"❌ Reservation failed: {resp.status} - {details}")
                return "I'm sorry, I couldn't complete your reservation. Please try calling back."

    @function_tool()
    async def end_call(self, ctx: RunContext) -> str:
        """
        End the phone call. ONLY use when customer clearly indicates they're done:
        - "That's all"
        - "Nothing else"
        - "Thank you, goodbye"
        - "No, I'm good"
        
        Before calling this tool, you MUST say: "Thank you for calling [Store Name]! Have a great day!"
        Then wait for the goodbye message to finish before disconnecting.
        """
        logger.info("📞 Customer is done - scheduling call end after goodbye...")
        
        # ✅ Give the agent time to finish speaking the goodbye message
        # Wait 3-4 seconds to ensure the TTS completes
        await asyncio.sleep(3.5)
        
        if not self.livekit_api or not self.room_name:
            logger.warning("⚠️ Cannot end call - missing LiveKit API or room name")
            return "Call ending..."
        
        try:
            # Find and remove SIP participant
            participants = await self.livekit_api.room.list_participants(
                livekit_api.ListParticipantsRequest(room=self.room_name)
            )
            
            for participant in participants.participants:
                if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
                    logger.info(f"🔌 Disconnecting SIP participant: {participant.identity}")
                    await self.livekit_api.room.remove_participant(
                        livekit_api.RoomParticipantIdentity(
                            room=self.room_name,
                            identity=participant.identity
                        )
                    )
                    logger.info("✅ Call ended successfully")
                    return "Call ended. Goodbye!"
            
            logger.warning("⚠️ No SIP participant found to disconnect")
            return "Call ending..."
            
        except Exception as e:
            logger.error(f"❌ Error ending call: {e}")
            return "Call ending..."

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

    @function_tool()
    async def check_current_time(self, ctx: RunContext) -> str:
        """Get current time in CST timezone to check if restaurant is open."""
        cst = pytz.timezone('America/Chicago')
        current_time = datetime.now(cst)
        
        current_time_str = current_time.strftime("%I:%M %p")
        current_day = current_time.strftime("%A")
        
        logger.info(f"🕐 Current CST time: {current_time_str} on {current_day}")
        
        return f"Current time is {current_time_str} CST on {current_day}"


def prewarm(proc: JobProcess):
    """Pre-warm VAD model for faster startup."""
    proc.userdata["vad"] = silero.VAD.load(
        min_silence_duration=0.15,
        prefix_padding_duration=0.08,
        activation_threshold=0.65,
        deactivation_threshold=0.20,
        sample_rate=8000,
    )


async def entrypoint(ctx: JobContext):
    """Main entrypoint for the voice agent."""
    ctx.log_context_fields = {"room": ctx.room.name}
    await ctx.connect()

    # Initialize LiveKit API client
    lk_api = livekit_api.LiveKitAPI(LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)

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
    await asyncio.sleep(0.8)
    
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

    # Load menu data first
    if store_id and api_session:
        temp_assistant = Assistant(
            caller_phone="", dialed_number="", 
            store_id=store_id, store_name=store_name, 
            api_session=api_session
        )
        await temp_assistant.load_menu()
        categories = ", ".join(sorted(temp_assistant.menu_by_category.keys()))
        
        # ✅ Add cleanup:
        del temp_assistant
        import gc
        gc.collect()
        
        # NOW create the real assistant with categories baked in
        assistant = Assistant(
            caller_phone=caller_phone,
            dialed_number=dialed_number,
            store_id=store_id,
            store_name=store_name,
            api_session=api_session,
            menu_categories=f"Main dishes: {categories}",
            room_name=ctx.room.name,
            livekit_api_client=lk_api,
        )
    else:
        # ✅ CREATE ASSISTANT WITHOUT MENU CATEGORIES
        assistant = Assistant(
            caller_phone=caller_phone,
            dialed_number=dialed_number,
            store_id=store_id or "",
            store_name=store_name,
            api_session=api_session,
            room_name=ctx.room.name,
            livekit_api_client=lk_api,
        )

    # ✅ LOAD MENU/KB/STORE DETAILS IMMEDIATELY (before session starts!)
    if store_id and api_session:
        logger.info("🔄 Pre-loading menu, knowledge base, and store details...")
        asyncio.create_task(assistant.load_data())
        await asyncio.sleep(0.05)  # Tiny head start

    async def cleanup_session():
        if api_session:
            logger.info("🔒 Closing API session")
            await api_session.close()
        await lk_api.aclose()
    
    ctx.add_shutdown_callback(cleanup_session)

    # Initialize session
    session = AgentSession(
        llm=openai.LLM(
            model="gpt-4.1-mini",
            temperature=0,
        ),
        stt=deepgram.STT(
            model="nova-2-phonecall",
            language="en-US",
        ),
        tts=cartesia.TTS(
            voice="6f84f4b8-58a2-430c-8c79-688dad597532",
            sample_rate=8000
        ),
        vad=ctx.proc.userdata["vad"],
        preemptiveCARTESIA_VOICE_ID
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
    
    # Shorter greeting with personality
    greeting = f"Thank you for calling {store_name}, this is Alex. How may I help you?"
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

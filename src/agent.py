"""Main agent entrypoint."""
from livekit import rtc
from livekit import api as livekit_api
import logging
import asyncio
import datetime
import json
from livekit.agents import (
    NOT_GIVEN,
    AgentFalseInterruptionEvent,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    RoomInputOptions,
    WorkerOptions,
    UserInputTranscribedEvent,
    ConversationItemAddedEvent,
    cli,
    metrics,
)
from livekit.plugins import cartesia, deepgram, noise_cancellation, openai, silero

from assistant import Assistant
from services.api_client import fetch_store_info, load_menu
from config import LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, CARTESIA_VOICE_ID

logger = logging.getLogger("agent")


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
    twilio_call_sid = None

    def on_participant_connected(participant: rtc.RemoteParticipant):
        nonlocal caller_phone, dialed_number, twilio_call_sid
        
        if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
            attrs = participant.attributes or {}
            
            # 🔍 DEBUG: Log ALL attributes (can remove after confirming it works)
            logger.info(f"🔍 ALL SIP Attributes: {json.dumps(attrs, indent=2)}")
            
            caller_phone = attrs.get("sip.phoneNumber", "")
            dialed_number = attrs.get("sip.trunkPhoneNumber", "")
            
            # Extract Twilio CallSid from SIP attributes
            twilio_call_sid = attrs.get("sip.twilio.callSid", "")
            
            logger.info(f"📞 SIP participant: Caller={caller_phone}, Dialed={dialed_number}")
            logger.info(f"📼 Twilio CallSid: {twilio_call_sid}")
            if not twilio_call_sid:
                logger.warning(f"⚠️ CallSid not found in sip.twilio.callSid attribute!")
            
            ctx.log_context_fields["caller_phone"] = caller_phone
            ctx.log_context_fields["dialed_number"] = dialed_number
            ctx.log_context_fields["twilio_call_sid"] = twilio_call_sid

    ctx.room.on("participant_connected", on_participant_connected)

    # Wait for SIP participant
    await asyncio.sleep(0.8)
    
    for participant in ctx.room.remote_participants.values():
        if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
            attrs = participant.attributes or {}
            
            # 🔍 DEBUG: Log ALL attributes (can remove after confirming it works)
            logger.info(f"🔍 ALL SIP Attributes: {json.dumps(attrs, indent=2)}")
            
            caller_phone = attrs.get("sip.phoneNumber", "")
            dialed_number = attrs.get("sip.trunkPhoneNumber", "")
            
            # Extract Twilio CallSid from SIP attributes
            twilio_call_sid = attrs.get("sip.twilio.callSid", "")
            
            logger.info(f"📞 Existing SIP participant found")
            logger.info(f"📼 Twilio CallSid: {twilio_call_sid}")
            if not twilio_call_sid:
                logger.warning(f"⚠️ CallSid not found in sip.twilio.callSid attribute!")
            
            ctx.log_context_fields["caller_phone"] = caller_phone
            ctx.log_context_fields["dialed_number"] = dialed_number
            ctx.log_context_fields["twilio_call_sid"] = twilio_call_sid
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

    # Load menu data first to get categories
    menu_categories = None
    if store_id and api_session:
        menu_data = await load_menu(store_id, api_session)
        if menu_data:
            categories = ", ".join(sorted(menu_data.keys()))
            menu_categories = f"Main dishes: {categories}"
    
    # Create assistant
    assistant = Assistant(
        caller_phone=caller_phone,
        dialed_number=dialed_number,
        store_id=store_id or "",
        store_name=store_name,
        api_session=api_session,
        menu_categories=menu_categories,
        room_name=ctx.room.name,
        livekit_api_client=lk_api,
    )

    # Pre-load all data
    if store_id and api_session:
        logger.info("🔄 Pre-loading menu, knowledge base, and store details...")
        asyncio.create_task(assistant.load_data())
        await asyncio.sleep(0.05)

    # ✅ IMPORTANT: Register save callback FIRST (before cleanup)
    # This ensures the session is still open when saving
    async def save_and_cleanup():
        """Save conversation, then cleanup session."""
        # STEP 1: Save conversation
        if assistant.call_transcript:
            logger.info(f"💾 Call ended - saving {len(assistant.call_transcript)} transcript entries...")
            from services.api_client import create_conversation
            
            try:
                # Build AI analysis with CallSid for recording integration
                ai_analysis = {
                    "callSid": twilio_call_sid,
                    "recordingPending": True if twilio_call_sid else False,
                    "callEndTime": datetime.datetime.now(datetime.timezone.utc).isoformat()
                }
                
                result = await create_conversation(
                    store_id=assistant.store_id,
                    customer_phone=assistant.caller_phone,
                    transcript={"messages": assistant.call_transcript},
                    duration=assistant.get_call_duration_seconds(),
                    session=assistant.api_session,
                    ai_analysis=ai_analysis
                )
                
                if "error" not in result:
                    logger.info("✅ Conversation saved successfully")
                    if twilio_call_sid:
                        logger.info(f"📼 CallSid saved for recording: {twilio_call_sid}")
                else:
                    logger.error(f"❌ Failed to save conversation: {result.get('error')}")
            except Exception as e:
                logger.error(f"❌ Exception while saving conversation: {e}", exc_info=True)
        else:
            logger.warning("⚠️ No transcripts captured - nothing to save")
        
        # STEP 2: Now cleanup (after save completes)
        if api_session:
            logger.info("🔒 Closing API session")
            await api_session.close()
        await lk_api.aclose()

    ctx.add_shutdown_callback(save_and_cleanup)


    # Initialize session
    session = AgentSession(
        llm=openai.LLM(model="gpt-4.1-mini", temperature=0),
        stt=deepgram.STT(model="nova-3", language="multi"),
       tts=cartesia.TTS(
      model="sonic-3",
      voice="b7d50908-b17c-442d-ad8d-810c63997ed9",
      sample_rate=8000
   ),
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

    # ✅ HANDLER 1: Capture user speech (STT transcripts from Deepgram)
    @session.on("user_input_transcribed")
    def on_user_input_transcribed(event: UserInputTranscribedEvent):
        """Called whenever user speech is transcribed by STT."""
        text = event.transcript.strip()
        if not text:
            return
        
        # Only save final transcripts to avoid duplicates
        if not event.is_final:
            logger.info(f"📝 [customer] ...: {text}")
            return
        
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        # Build transcript entry
        entry = {
            "role": "customer",
            "content": text,
            "timestamp": timestamp
        }
        
        # Append to transcript
        assistant.call_transcript.append(entry)
        
        # Log the final transcript
        logger.info(f"📝 [customer] ✓: {text}")

    # ✅ HANDLER 2: Capture AI agent responses (LLM output text)
    @session.on("conversation_item_added")
    def on_conversation_item_added(event: ConversationItemAddedEvent):
        """Called whenever the agent adds a message to the conversation."""
        item = event.item
        
        # ✅ FIX: Only capture assistant messages (skip user messages)
        # User messages are already captured by on_user_input_transcribed
        if item.role != "assistant":
            return
        
        # Only capture text messages (no images/audio etc)
        if not isinstance(item.text_content, str):
            return
        
        text = item.text_content.strip()
        if not text:
            return
        
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        entry = {
            "role": "agent",
            "content": text,
            "timestamp": timestamp
        }
        
        assistant.call_transcript.append(entry)
        
        # Log the agent's response
        logger.info(f"🤖 [agent] ✓: {text}")

    logger.info("🎯 Starting agent session...")
    
    # Start session
    await session.start(
        agent=assistant,
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVCTelephony(),
        ),
    )
    
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

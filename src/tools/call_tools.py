"""Call management tools (transfer and end call)."""
from livekit.agents import function_tool, RunContext
from livekit import rtc, api as livekit_api
from services.sms_service import send_sms

import asyncio
import logging

logger = logging.getLogger("call_tools")


def create_call_tools(assistant):
    """Create call management tools for the assistant."""
    
    @function_tool()
    async def transfer_to_manager(ctx: RunContext) -> str:
        """
        Transfer the call to a live manager/human agent.
        Use when customer explicitly requests:
        - "I want to talk to your manager"
        - "Can I speak to someone"
        - "Transfer me to a person"
        
        Before calling this, say: "Of course! Let me transfer you to our manager. Please hold."
        """
        logger.info("📞 Transferring call to manager...")
        
        if not assistant.transfer_phone:
            logger.error("❌ No transfer phone configured for this store")
            return "I'm sorry, I don't have a manager number configured. Please call back and ask for assistance."
        
        if not assistant.livekit_api or not assistant.room_name:
            logger.error("❌ Cannot transfer - missing LiveKit API or room name")
            return "I'm sorry, I'm unable to transfer calls right now."
        
        # Format phone number for SIP transfer (must be E.164 format with tel: prefix)
        transfer_to = assistant.transfer_phone if assistant.transfer_phone.startswith('tel:') else f"tel:{assistant.transfer_phone}"
        
        logger.info(f"🔄 Initiating transfer to: {transfer_to}")
        
        try:
            # Find the actual SIP participant identity from the room
            participants = await assistant.livekit_api.room.list_participants(
                livekit_api.ListParticipantsRequest(room=assistant.room_name)
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
            await assistant.livekit_api.sip.transfer_sip_participant(
                livekit_api.TransferSIPParticipantRequest(
                    room_name=assistant.room_name,
                    participant_identity=sip_participant_identity,
                    transfer_to=transfer_to,
                )
            )
            logger.info("✅ Call transfer initiated successfully")
            return "Transferring you now. Please hold."
            
        except Exception as e:
            logger.error(f"❌ Call transfer failed: {e}")
            return "I'm sorry, I couldn't transfer the call. Let me see if I can help you instead."

    @function_tool()
    async def end_call(ctx: RunContext) -> str:
        """
        Disconnect and end the phone call after saying goodbye.
        
        WHEN TO USE: Customer says "That's all" / "Nothing else" / "Bye" / "Thank you, goodbye"
        
        HOW TO USE:
        1. First say: "Awesome! Thanks for calling [Store Name] - have a great day!"
        2. Then IMMEDIATELY call this tool to disconnect the call
        3. The tool waits 10 seconds for your goodbye to finish, then disconnects
        
        CRITICAL: You must call this tool or the call will never end!
        """
        logger.info("📞 Customer is done - scheduling call end after goodbye...")
        
        # Give the agent time to finish speaking the goodbye message
        await asyncio.sleep(10.0)
        
        if not assistant.livekit_api or not assistant.room_name:
            logger.warning("⚠️ Cannot end call - missing LiveKit API or room name")
            return "Call ending..."
        
        try:
            # Find and remove SIP participant
            participants = await assistant.livekit_api.room.list_participants(
                livekit_api.ListParticipantsRequest(room=assistant.room_name)
            )
            
            for participant in participants.participants:
                if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
                    logger.info(f"🔌 Disconnecting SIP participant: {participant.identity}")
                    await assistant.livekit_api.room.remove_participant(
                        livekit_api.RoomParticipantIdentity(
                            room=assistant.room_name,
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
    async def save_conversation(ctx: RunContext) -> str:
        """
        Save the conversation transcript and details to the database.
        This is automatically called when the call ends.
        """
        logger.info("💾 Saving conversation...")
        
        if not assistant.call_transcript:
            logger.warning("⚠️ No transcript to save")
            return "No conversation data to save"
        
        if not assistant.store_id or not assistant.caller_phone:
            logger.error("❌ Missing store_id or caller_phone")
            return "Missing required information to save conversation"
        
        if not assistant.api_session:
            logger.error("❌ No API session available")
            return "API session not available"
        
        from services.api_client import create_conversation
        
        transcript_payload = {"messages": assistant.call_transcript}
        duration = assistant.get_call_duration_seconds()
        
        logger.info(f"📊 Conversation stats: {len(assistant.call_transcript)} messages, {duration}s duration")
        
        result = await create_conversation(
            store_id=assistant.store_id,
            customer_phone=assistant.caller_phone,
            transcript=transcript_payload,
            duration=duration,
            session=assistant.api_session
        )
        
        if "error" in result:
            logger.error(f"❌ Failed to save conversation: {result['error']}")
            return f"Failed to save conversation"
        
        logger.info(f"✅ Conversation saved successfully")
        return "Conversation saved successfully"
    
    @function_tool()
    async def handle_transfer_request(
        self,
        ctx: RunContext,
        customer_name: str,
        customer_phone: str,
        reason: str = "Inquiry",
        manager_phone: str = "(618) 258-1388"
    ):
        """Handle transfer/callback flow per client expectations."""
        
        # 1️⃣ Ask preference
        await ctx.say(
            "I can transfer you to our manager, or they can call you back within 5 minutes. "
            "Which would you prefer?"
        )
        customer_choice = await ctx.listen()  # Should return "transfer" or "callback"
        
        if "transfer" in customer_choice.lower():
            # 2️⃣ Attempt transfer
            await ctx.say(
                f"I'll transfer you now. If they don't answer, we'll call you back at {customer_phone}."
            )
            
            try:
                transfer_success = await self.transfer_to_manager(ctx, manager_phone)
                if not transfer_success:
                    raise Exception("Transfer failed")
            except Exception:
                # Transfer failed → send SMS to customer & store
                await send_sms(self.dialed_number, customer_phone,
                    f"Thank you! We'll call you back at {customer_phone} within 5 minutes."
                )
                if self.notification_phone:
                    await send_sms(
                        self.dialed_number,
                        self.notification_phone,
                        f"🔔 CALLBACK NEEDED\nCustomer: {customer_name}\nPhone: {customer_phone}\nReason: {reason}\n⚠️ Transfer attempted but may have failed\nPlease call back within 5 minutes!"
                    )
                return "Transfer failed; callback SMS sent."

        else:
            # 3️⃣ Customer chose callback
            await ctx.say(
                f"Perfect! Our manager will call you at {customer_phone} within 5 minutes. Goodbye!"
            )
            if self.notification_phone:
                await send_sms(
                    self.dialed_number,
                    self.notification_phone,
                    f"🔔 CALLBACK REQUESTED\nCustomer: {customer_name}\nPhone: {customer_phone}\nReason: {reason}\nPlease call back within 5 minutes!"
                )
            return "Callback scheduled."
    
    return [transfer_to_manager, end_call, save_conversation, handle_transfer_request]

    


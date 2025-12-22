"""API client for store and menu data."""
import logging
from typing import Optional, Tuple, Dict, List
from collections import defaultdict
import aiohttp
from config import BASE_URL, API_EMAIL, API_PASSWORD

logger = logging.getLogger("api_client")


async def fetch_store_info(dialed_number: str) -> Tuple[Optional[str], str, Optional[aiohttp.ClientSession]]:
    """Fetch store ID and name, return authenticated session.
    
    Args:
        dialed_number: Phone number that was dialed
        
    Returns:
        Tuple of (store_id, store_name, api_session)
    """
    session = aiohttp.ClientSession()
    
    try:
        # Login
        async with session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": API_EMAIL, "password": API_PASSWORD}
        ) as resp:
            if resp.status != 200:
                logger.error(f"❌ Login failed: {resp.status}")
                await session.close()
                return None, "Unknown Restaurant", None
        
        logger.info(f"📞 Fetching store info for: {dialed_number}")
        
        # Get store ID
        async with session.get(f"{BASE_URL}/api/stores/by-phone/{dialed_number}") as response:
            if response.status == 200:
                data = await response.json()
                store_id = data.get("id") or data.get("_id")
            else:
                store_id = None
        
        # Get store details
        if store_id:
            async with session.get(f"{BASE_URL}/api/stores/{store_id}") as response:
                if response.status == 200:
                    data = await response.json()
                    store_name = data.get("name", "Unknown Restaurant")
                else:
                    store_name = "Unknown Restaurant"
        else:
            store_name = "Unknown Restaurant"
        
        logger.info(f"✅ Store: {store_name} (ID: {store_id})")
        return store_id, store_name, session
        
    except Exception as e:
        logger.error(f"❌ Error fetching store info: {e}")
        await session.close()
        return None, "Unknown Restaurant", None


async def load_menu(store_id: str, session: aiohttp.ClientSession) -> Dict[str, List[Dict]]:
    """Load menu data from API.
    
    Args:
        store_id: Store identifier
        session: Authenticated aiohttp session
        
    Returns:
        Dictionary mapping category names to lists of menu items
    """
    try:
        async with session.get(f"{BASE_URL}/api/menu/{store_id}") as response:
            if response.status != 200:
                logger.warning(f"Could not fetch menu: {response.status}")
                return {}
            
            menu_data = await response.json()
            menu_by_category = defaultdict(list)
            
            for item in menu_data:
                category = item.get('category', 'Other')
                menu_by_category[category].append({
                    'name': item.get('name'),
                    'price': item.get('basePrice'),
                    'id': item.get('id'),
                })
            
            return dict(menu_by_category)
    except Exception as e:
        logger.error(f"Error loading menu: {e}")
        return {}


async def load_knowledge_base(store_id: str, session: aiohttp.ClientSession) -> List[Dict]:
    """Load knowledge base from API.
    
    Args:
        store_id: Store identifier
        session: Authenticated aiohttp session
        
    Returns:
        List of FAQ entries
    """
    try:
        async with session.get(f"{BASE_URL}/api/knowledge-base/{store_id}") as response:
            if response.status != 200:
                logger.warning(f"Could not fetch knowledge base: {response.status}")
                return []
            
            kb_data = await response.json()
            return kb_data if isinstance(kb_data, list) else []
    except Exception as e:
        logger.error(f"Error loading knowledge base: {e}")
        return []


async def load_store_details(store_id: str, session: aiohttp.ClientSession) -> Tuple[Optional[str], Optional[str]]:
    """Load store details including notification and transfer phones.
    
    Args:
        store_id: Store identifier
        session: Authenticated aiohttp session
        
    Returns:
        Tuple of (notification_phone, transfer_phone)
    """
    try:
        async with session.get(f"{BASE_URL}/api/stores/{store_id}") as response:
            if response.status == 200:
                store_data = await response.json()
                notification_phone = store_data.get("notificationPhone")
                transfer_phone = store_data.get("transferPhone")
                logger.info(f"✅ Merchant notification phone: {notification_phone}")
                logger.info(f"✅ Transfer phone: {transfer_phone}")
                return notification_phone, transfer_phone
            else:
                logger.warning(f"Could not fetch store details: {response.status}")
                return None, None
    except Exception as e:
        logger.error(f"Error loading store details: {e}")
        return None, None


async def create_conversation(
    store_id: str,
    customer_phone: str,
    transcript: Dict,
    duration: int,
    session: aiohttp.ClientSession,
    ai_analysis: Optional[Dict] = None
) -> Dict:
    """Create/Save a call conversation record.
    
    Args:
        store_id: Store identifier
        customer_phone: Customer's phone number
        transcript: Dictionary with 'messages' list containing conversation
        duration: Call duration in seconds
        session: Authenticated aiohttp session
        ai_analysis: Optional AI analysis data
        
    Returns:
        Created conversation data
    """
    try:
        data = {
            "storeId": store_id,
            "customerPhone": customer_phone,
            "transcript": transcript,
            "duration": duration,
            "callStatus": "completed"
        }
        
        if ai_analysis:
            data["aiAnalysis"] = ai_analysis
        
        async with session.post(
            f"{BASE_URL}/api/conversations",
            json=data
        ) as response:
            if response.status in (200, 201):
                result = await response.json()
                logger.info(f"✅ Conversation saved: {result.get('id')}")
                return result
            else:
                error_text = await response.text()
                logger.error(f"❌ Failed to create conversation: {response.status} - {error_text}")
                return {"error": f"Failed to create conversation: {response.status}"}
    except Exception as e:
        logger.error(f"❌ Exception while creating conversation: {e}")
        return {"error": str(e)}

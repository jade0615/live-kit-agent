"""Configuration and environment variables."""
import os
from dotenv import load_dotenv

load_dotenv(".env.local")

# API Configuration
BASE_URL = "https://www.miaojieai.com"
API_EMAIL = "midge6115@gmail.com"
API_PASSWORD = "bd7c90cbea692aa1"

# LiveKit Configuration
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")

# Twilio Configuration
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_API_KEY_SID = os.getenv("TWILIO_API_KEY_SID")
TWILIO_API_KEY_SECRET = os.getenv("TWILIO_API_KEY_SECRET")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")  # A2P certified number for sending SMS

# Voice Configuration
CARTESIA_VOICES = {
    "sarah_friendly": "6f84f4b8-58a2-430c-8c79-688dad597532",  # Current
    "rachel_professional": "79a125e8-cd45-4c13-8a67-188112f4dd22",  # Friendly female
    "mark_warm": "41534e16-2966-4c6b-9670-111411def906",  # Warm male
    "olivia_energetic": "b7d50908-b17c-442d-ad8d-810c63997ed9",  # Energetic female
}

# Use default
CARTESIA_VOICE_ID = CARTESIA_VOICES["olivia_energetic"]

# Menu Images Configuration
# NOTE: These must be publicly accessible URLs for Twilio MMS to work
# Upload your menu images to your server, AWS S3, Cloudinary, or similar service
MENU_IMAGE_URLS = [
    os.getenv("MENU_IMAGE_1", "https://your-server.com/menu-page1.jpg"),  # Replace with actual URL
    os.getenv("MENU_IMAGE_2", "https://your-server.com/menu-page2.jpg")   # Replace with actual URL
]

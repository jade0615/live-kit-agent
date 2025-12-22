# LiveKit Voice Agent - Developer Guide

Restaurant voice AI agent built with LiveKit Agents SDK. Handles phone calls via SIP for orders, reservations, FAQs, and call transfers.

---

## 📁 Project Structure

```
Testing_agent/
├── src/
│   ├── agent.py                  # Main entry point
│   ├── assistant.py              # AI agent personality & tools
│   ├── config.py                 # Environment configuration
│   ├── services/
│   │   ├── api_client.py        # Backend API integration
│   │   └── sms_service.py       # Twilio SMS
│   └── tools/
│       ├── menu_tools.py        # Menu browsing
│       ├── order_tools.py       # Order placement
│       ├── reservation_tools.py # Reservations
│       ├── knowledge_tools.py   # FAQ & time lookup
│       └── call_tools.py        # Transfer & hang up
├── tests/
│   └── test_agent.py
├── pyproject.toml               # Dependencies
├── livekit.toml                 # Deployment config
├── Dockerfile
└── .env.local                   # Environment vars (DO NOT COMMIT)
```

**Key Files:**
- `agent.py` - Entry point, session management, transcript handling
- `assistant.py` - Agent personality, tool registration, workflows
- `tools/*.py` - Individual AI tools (menu, order, reservation, FAQ, call)
- `services/api_client.py` - Backend API (store/menu/KB/conversations)
- `services/sms_service.py` - SMS notifications (Twilio)

---

## 🚀 Setup

### Install uv Package Manager
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Install Dependencies
```bash
cd Testing_agent
uv sync
```

### Configure Environment
Create `.env.local`:
```env
# LiveKit
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your_api_key
LIVEKIT_API_SECRET=your_api_secret

# Backend API
BACKEND_URL=https://miaojieai.com
STORE_ID=your_store_id
USERNAME=your_username
PASSWORD=your_password

# Twilio SMS
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
TWILIO_PHONE_NUMBER=+1234567890

# Voice (optional)
CARTESIA_VOICE_ID=95856005-0332-41b0-935f-352e296aa0df
```

---

## 🧪 Testing

```bash
# Run tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Local development
python src/agent.py dev
```

---

## 🌐 Deployment

### First Time
```bash
# Authenticate
lk cloud auth

# Create agent (generates livekit.toml)
lk agent create
```

### Deploy Updates
```bash
lk agent deploy
```

### View Logs
```bash
# Live logs
lk agent logs --follow

# Recent logs
lk agent logs
```

---

## 📝 Common Tasks

### Add New Tool
1. Create function in `src/tools/my_tool.py`
2. Import and register in `assistant.py`
3. Test locally: `python src/agent.py dev`

### Modify Personality
Edit instructions in `assistant.py`

### Debug Issues
```bash
# Local debugging
python src/agent.py dev --log-level DEBUG

# Production logs
lk agent logs --follow
```

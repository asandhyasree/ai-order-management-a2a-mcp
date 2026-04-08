# Legendary Margherita - AI Pizza Ordering System

An AI-powered pizza ordering system demonstrating **Agent-to-Agent (A2A) communication**, **Model Context Protocol (MCP)**, and **Google Calendar integration**.

## Architecture

```
                         ┌─────────────────────┐
                         │     STREAMLIT UI    │
                         │    (app.py)         │
                         └──────────┬──────────┘
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────┐
│                      ORDERING AGENT                           │
│  ┌─────────────────────┐    ┌───────────────────────────────┐│
│  │     MCP TOOLS       │    │         A2A TOOLS             ││
│  │  • get_menu         │    │  • a2a_schedule_delivery()    ││
│  │  • place_order      │    │  • a2a_confirm_and_create_    ││
│  │  • track_order      │    │    calendar_event()           ││
│  └──────────┬──────────┘    └──────────────┬────────────────┘│
└─────────────┼───────────────────────────────┼────────────────┘
              │                               │
              ▼                               ▼
┌─────────────────────────┐    ┌────────────────────────────────┐
│   MCP SERVER (:8000)    │    │      SCHEDULING AGENT          │
│   OpenAPI → MCP Tools   │    │  • tool_check_conflicts        │
└──────────┬──────────────┘    │  • tool_find_next_free_slot    │
           │                   │  • tool_create_delivery_event  │
           ▼                   └──────────────┬─────────────────┘
┌─────────────────────────┐                   │
│  FASTAPI BACKEND (:9000)│                   ▼
│  • /menu                │    ┌────────────────────────────────┐
│  • /order               │    │     GOOGLE CALENDAR API        │
│  • /orders              │    └────────────────────────────────┘
└─────────────────────────┘
```

## Features

- **Natural Language Ordering**: Order pizzas using conversational AI
- **A2A Communication**: Ordering Agent delegates scheduling to Scheduling Agent
- **MCP Integration**: Auto-generated tools from OpenAPI specification
- **Calendar Integration**: Automatic delivery scheduling with conflict detection
- **Real-time Order Tracking**: Live order status updates
- **Beautiful UI**: Custom-styled Streamlit interface

## Tech Stack

| Component | Technology |
|-----------|------------|
| **AI Framework** | Google ADK (Agent Development Kit) |
| **LLM** | Gemini 2.5 Flash |
| **MCP** | FastMCP (OpenAPI to MCP conversion) |
| **Backend** | FastAPI + Uvicorn |
| **Frontend** | Streamlit |
| **Calendar** | Google Calendar API (OAuth 2.0) |
| **Data** | JSON file storage |

## Prerequisites

- Python 3.10+
- Google Cloud account (for Calendar API)
- Gemini API key

## Setup

### 1. Clone and Install Dependencies

```bash
cd Pizza_Ordering
pip install -r requirements.txt
```

### 2. Environment Variables

Create a `.env` file:

```env
GOOGLE_API_KEY=your_gemini_api_key_here
```

### 3. Google Calendar Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable **Google Calendar API**
4. Create **OAuth 2.0 credentials** (Desktop application)
5. Download and save as `credentials.json` in project root
6. First run will open browser for OAuth consent
7. Token saved to `token.json` for subsequent runs

## Running the Application

Open **3 separate terminals**:

### Terminal 1: FastAPI Backend
```bash
uvicorn mock_backend:app --port 9000
```

### Terminal 2: MCP Server
```bash
python mcp_generator.py
```

### Terminal 3: Streamlit App
```bash
streamlit run app.py
```

Then open http://localhost:8501 in your browser.

## Project Structure

```
Pizza_Ordering/
├── app.py                 # Main Streamlit app with A2A agents
├── mock_backend.py        # FastAPI pizza shop backend
├── mcp_generator.py       # OpenAPI to MCP server generator
├── calendar_tools.py      # Google Calendar integration
├── menu.json              # Pizza menu data
├── openapi.json           # API specification
├── orders.json            # Order persistence (auto-generated)
├── credentials.json       # Google OAuth credentials (user provides)
├── token.json             # OAuth token (auto-generated)
├── requirements.txt       # Python dependencies
└── .env                   # Environment variables
```

## Usage Flow

### 1. Place an Order
```
User: "I want 2 large Margherita pizzas"
```

### 2. Agent Places Order & Schedules Delivery
```
Agent: [Calls place_order via MCP]
Agent: [Calls a2a_schedule_delivery → Scheduling Agent]
Agent: "Order confirmed! Delivery between 3:00 PM - 3:30 PM. Add to calendar?"
```

### 3. Confirm Calendar Event
```
User: "yes"
Agent: [Calls a2a_confirm_and_create_calendar_event]
Agent: "Done! Added to your calendar."
```

### 4. Track Order
```
User: "Track my order LM-ABC123"
Agent: [Calls track_order via MCP]
Agent: "Your order is currently being prepared..."
```

## API Endpoints (Backend :9000)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/menu` | Get pizza menu |
| POST | `/order` | Place new order |
| GET | `/order/{order_id}` | Track order status |
| GET | `/orders` | List all orders |

## Agent Details

### Ordering Agent
- **Model**: Gemini 2.5 Flash
- **Tools**: MCP tools (menu, order, track) + A2A tools (scheduling)
- **Role**: Customer-facing agent for pizza orders

### Scheduling Agent
- **Model**: Gemini 2.5 Flash
- **Tools**: Calendar tools (conflicts, free slots, events)
- **Role**: Background agent for delivery scheduling (called via A2A)

## A2A Communication

The A2A pattern allows agents to delegate tasks:

```python
# Ordering Agent calls A2A tool
result = a2a_schedule_delivery(order_id, pizza_name, estimated_minutes)

# Inside a2a_schedule_delivery():
#   1. tool_calculate_delivery_time(minutes)
#   2. tool_check_conflicts(start, end)
#   3. tool_find_next_free_slot() if conflict
#   4. Store in session_state for later
```

## Menu

| Category | Items |
|----------|-------|
| **Veg Pizzas** | Margherita, Farmhouse, Peppy Paneer, Veggie Paradise |
| **Non-Veg Pizzas** | Chicken Golden Delight, Chicken Dominator |
| **Pizza Mania** | Onion Pizza, Golden Corn Pizza |
| **Sides & Desserts** | Garlic Breadsticks, Stuffed Garlic Bread, Choco Lava Cake |

**Sizes**: Regular, Medium, Large

## Order Status Lifecycle

```
Order Received → Preparing → Baking → Quality Check → Out for Delivery → Delivered
```

## Troubleshooting

### "Backend Offline" Error
```bash
# Ensure backend is running
uvicorn mock_backend:app --port 9000
```

### "MCP Server Offline" Error
```bash
# Ensure MCP server is running
python mcp_generator.py
```

### Calendar Authentication Error
1. Delete `token.json`
2. Restart app
3. Complete OAuth flow in browser

### "No delivery scheduled" Error
- Ensure you place an order first before confirming calendar event
- The scheduling state is stored in Streamlit session

## Dependencies

```
google-adk>=1.0.0
fastmcp>=2.0.0
fastapi>=0.100.0
uvicorn>=0.23.0
httpx>=0.24.0
python-dotenv>=1.0.0
google-auth-oauthlib>=1.0.0
google-api-python-client>=2.100.0
google-auth>=2.22.0
pydantic>=2.0.0
streamlit
```

## Key Concepts Demonstrated

1. **OpenAPI to MCP Transformation**: Automatic tool generation from API specs
2. **Multi-Agent Architecture**: Ordering Agent + Scheduling Agent
3. **A2A Protocol**: Agent-to-agent task delegation
4. **Tool Calling**: LLM invoking external functions
5. **Session Management**: Persisting state across interactions
6. **OAuth Integration**: Google Calendar authentication



import streamlit as st
import asyncio
import json
import httpx
import socket
import html
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

from google.adk.agents import Agent
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import SseConnectionParams
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.genai import types

from calendar_tools import (
    get_current_time,
    check_conflicts,
    find_next_free_slot,
    create_delivery_event,
    list_upcoming_events
)

# ============================================================================
# PAGE CONFIG & CSS
# ============================================================================

st.set_page_config(
    page_title="Legendary Margherita Pizza",
    page_icon="🍕",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap');
    * { font-family: 'Poppins', sans-serif; }
    .stApp { background: linear-gradient(135deg, #FFF5E6 0%, #FFE4CC 100%); }
    .main-header {
        background: linear-gradient(135deg, #D62828 0%, #F77F00 50%, #FCBF49 100%);
        padding: 2rem 3rem; border-radius: 20px; text-align: center; margin-bottom: 2rem;
        box-shadow: 0 10px 40px rgba(214, 40, 40, 0.3);
    }
    .main-header h1 { color: white; font-size: 3rem; margin: 0; text-shadow: 3px 3px 6px rgba(0,0,0,0.3); }
    .main-header p { color: #FFF8E7; font-size: 1.2rem; margin-top: 0.5rem; }
    .user-message {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white; padding: 1rem 1.5rem; border-radius: 20px 20px 5px 20px;
        margin: 0.8rem 0; max-width: 75%; margin-left: auto;
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
    }
    .assistant-message {
        background: linear-gradient(135deg, #D62828 0%, #F77F00 100%);
        color: white; padding: 1rem 1.5rem; border-radius: 20px 20px 20px 5px;
        margin: 0.8rem 0; max-width: 75%;
        box-shadow: 0 4px 15px rgba(214, 40, 40, 0.3);
    }
    .menu-category {
        background: linear-gradient(135deg, #D62828 0%, #F77F00 100%);
        color: white; padding: 0.8rem 1.2rem; border-radius: 15px;
        margin: 1rem 0 0.5rem 0; font-weight: 600; text-align: center;
    }
    .pizza-card {
        background: white; border-radius: 15px; padding: 1rem; margin: 0.5rem 0;
        box-shadow: 0 3px 15px rgba(0,0,0,0.08); border-left: 4px solid #F77F00;
    }
    .pizza-card:hover { transform: translateX(5px); box-shadow: 0 5px 20px rgba(0,0,0,0.15); }
    .pizza-name { font-weight: 600; color: #D62828; margin-bottom: 0.3rem; }
    .pizza-desc { color: #666; font-size: 0.8rem; margin-bottom: 0.5rem; }
    .price-row { display: flex; gap: 0.5rem; flex-wrap: wrap; }
    .price-tag { background: linear-gradient(135deg, #FCBF49 0%, #F77F00 100%); color: white; padding: 0.25rem 0.6rem; border-radius: 15px; font-size: 0.75rem; font-weight: 600; }
    section[data-testid="stSidebar"] { background: linear-gradient(180deg, #FFF8F0 0%, #FFE8D6 100%); }
    .stTextInput > div > div > input { border-radius: 25px !important; border: 2px solid #F77F00 !important; padding: 0.8rem 1.5rem !important; }
    .stButton > button { background: linear-gradient(135deg, #D62828 0%, #F77F00 100%) !important; color: white !important; border: none !important; border-radius: 25px !important; }
    .status-online { background: #2A9D8F; color: white; padding: 0.4rem 1rem; border-radius: 20px; font-size: 0.85rem; }
    .status-offline { background: #E63946; color: white; padding: 0.4rem 1rem; border-radius: 20px; font-size: 0.85rem; }
    .agent-badge { padding: 0.3rem 0.8rem; border-radius: 15px; font-size: 0.75rem; font-weight: 600; }
    .agent-ordering { background: #3498DB; color: white; }
    .agent-scheduling { background: #2ECC71; color: white; }
    .a2a-arrow { color: #9B59B6; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# MENU DATA
# ============================================================================

from pathlib import Path

def load_menu_data():
    menu_path = Path(__file__).parent / "menu.json"
    with open(menu_path, "r") as f:
        menu = json.load(f)
    category_emojis = {"Veg Pizzas": "🥬", "Non-Veg Pizzas": "🍗", "Pizza Mania": "🎉", "Sides & Desserts": "🍰"}
    item_emojis = {"v1": "🧀", "v2": "🍄", "v3": "🧈", "v4": "🥬", "nv1": "🍗", "nv2": "🔥", "m1": "🧅", "m2": "🌽", "s1": "🥖", "s2": "🧄", "s3": "🍫"}
    menu_data = {}
    for category in menu.get("categories", []):
        cat_name = category["name"]
        display_name = f"{cat_name} {category_emojis.get(cat_name, '')}"
        items = []
        for item in category.get("items", []):
            prices = item.get("prices", {"Single": item.get("price", 0)})
            items.append({"id": item["id"], "name": item["name"], "desc": item.get("description", ""), "prices": prices, "emoji": item_emojis.get(item["id"], "🍕")})
        menu_data[display_name] = items
    return menu_data

MENU_DATA = load_menu_data()
MCP_SERVER_URL = "http://localhost:8000/sse"

# ============================================================================
# SCHEDULING AGENT (A2A Target)
# ============================================================================

SCHEDULING_AGENT_INSTRUCTION = """
You are the Scheduling Agent. You handle calendar and delivery scheduling.

TOOLS:
- tool_get_current_time: Get current date/time
- tool_calculate_delivery_time: Calculate delivery window
- tool_check_conflicts: Check calendar conflicts
- tool_find_next_free_slot: Find available slot
- tool_create_delivery_event: Create calendar event
- tool_list_upcoming_events: List events

When asked to schedule delivery:
1. Calculate delivery time from estimated_minutes
2. Check for conflicts
3. If conflict, find next free slot
4. Create calendar event when confirmed

Return clear, concise results.
"""

def tool_get_current_time() -> dict:
    """Get the current date and time."""
    return get_current_time()

def tool_calculate_delivery_time(minutes_from_now: int) -> dict:
    """Calculate delivery time window from now."""
    now = datetime.now()
    delivery_start = now + timedelta(minutes=minutes_from_now)
    delivery_end = delivery_start + timedelta(minutes=30)
    date_str = delivery_start.strftime("%B %d, %Y")
    return {
        "delivery_start_iso": delivery_start.isoformat(),
        "delivery_end_iso": delivery_end.isoformat(),
        "delivery_date": date_str,
        "delivery_start_readable": delivery_start.strftime("%I:%M %p"),
        "delivery_end_readable": delivery_end.strftime("%I:%M %p"),
        "full_delivery_window": f"{date_str}, {delivery_start.strftime('%I:%M %p')} - {delivery_end.strftime('%I:%M %p')}"
    }

def tool_check_conflicts(start_time: str, end_time: str) -> dict:
    """Check calendar conflicts during a time window."""
    return check_conflicts(start_time, end_time)

def tool_find_next_free_slot(after_time: str, duration_minutes: int = 30) -> dict:
    """Find next available calendar slot."""
    return find_next_free_slot(after_time, duration_minutes)

def tool_create_delivery_event(order_id: str, pizza_name: str, delivery_time: str, estimated_arrival: str) -> dict:
    """Create a calendar event for pizza delivery."""
    return create_delivery_event(order_id, pizza_name, delivery_time, estimated_arrival)

def tool_list_upcoming_events(hours_ahead: int = 4) -> dict:
    """List upcoming calendar events."""
    return list_upcoming_events(hours_ahead)

def create_scheduling_agent():
    """Create the Scheduling Agent with calendar tools."""
    return Agent(
        model="gemini-2.5-flash",
        name="scheduling_agent",
        description="Handles delivery scheduling with Google Calendar",
        instruction=SCHEDULING_AGENT_INSTRUCTION,
        tools=[
            tool_get_current_time,
            tool_calculate_delivery_time,
            tool_check_conflicts,
            tool_find_next_free_slot,
            tool_create_delivery_event,
            tool_list_upcoming_events
        ]
    )

# ============================================================================
# A2A TOOLS - Scheduling Agent Functions (Called by Ordering Agent)
# ============================================================================

def _get_scheduling_state():
    """Get scheduling state from Streamlit session."""
    if "last_scheduling" not in st.session_state:
        st.session_state.last_scheduling = {}
    return st.session_state.last_scheduling

def _set_scheduling_state(data):
    """Set scheduling state in Streamlit session."""
    st.session_state.last_scheduling = data

def a2a_schedule_delivery(order_id: str, pizza_name: str, estimated_minutes: int) -> dict:
    """
    [A2A TOOL] Schedule a pizza delivery - delegates to Scheduling Agent.

    Args:
        order_id: The pizza order ID (e.g., "LM-ABC123")
        pizza_name: Description of pizza (e.g., "2 Large Margherita")
        estimated_minutes: Estimated preparation time in minutes

    Returns:
        dict with delivery time window
    """
    try:
        # Calculate delivery time
        delivery_info = tool_calculate_delivery_time(estimated_minutes)

        # Check for conflicts
        conflict_check = tool_check_conflicts(
            delivery_info["delivery_start_iso"],
            delivery_info["delivery_end_iso"]
        )

        # If conflict, find next free slot
        if conflict_check.get("has_conflict"):
            free_slot = tool_find_next_free_slot(delivery_info["delivery_start_iso"], 30)
            if free_slot.get("found"):
                _set_scheduling_state({
                    "order_id": order_id,
                    "pizza_name": pizza_name,
                    "delivery_time_iso": free_slot["slot_start_iso"],
                    "delivery_time_readable": free_slot["slot_start"]
                })
                return {
                    "success": True,
                    "delivery_time": f"{free_slot['slot_start']} - {free_slot['slot_end']}",
                    "message": f"Conflict found. Alternative time: {free_slot['slot_start']} - {free_slot['slot_end']}"
                }

        # No conflict
        _set_scheduling_state({
            "order_id": order_id,
            "pizza_name": pizza_name,
            "delivery_time_iso": delivery_info["delivery_start_iso"],
            "delivery_time_readable": delivery_info["delivery_start_readable"]
        })
        return {
            "success": True,
            "delivery_time": f"{delivery_info['delivery_start_readable']} - {delivery_info['delivery_end_readable']}",
            "message": f"Delivery available: {delivery_info['delivery_start_readable']} - {delivery_info['delivery_end_readable']}"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def a2a_confirm_and_create_calendar_event() -> dict:
    """
    [A2A TOOL] Confirm delivery and create calendar event.

    Call this when the customer confirms the delivery time.
    Uses the scheduling details from the previous a2a_schedule_delivery call.

    Returns:
        dict with calendar event creation result
    """
    try:
        scheduling = _get_scheduling_state()
        if not scheduling:
            return {"success": False, "error": "No delivery scheduled yet. Use a2a_schedule_delivery first."}

        result = tool_create_delivery_event(
            scheduling["order_id"],
            scheduling["pizza_name"],
            scheduling["delivery_time_iso"],
            scheduling["delivery_time_readable"]
        )

        if result.get("success"):
            # Clear after successful creation
            _set_scheduling_state({})
            return {
                "success": True,
                "message": f"Calendar event created for {scheduling['delivery_time_readable']}",
                "event_link": result.get("event_link", "")
            }
        else:
            return {"success": False, "error": result.get("error", "Failed to create event")}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ============================================================================
# ORDERING AGENT (Main Agent with A2A Tools)
# ============================================================================

ORDERING_AGENT_INSTRUCTION = """
You are the Ordering Agent for Legendary Margherita Pizza.

## YOUR TOOLS

### MCP Tools (Pizza Operations):
- get_menu: Get the pizza menu
- place_order: Place an order (customer_name="Vidya", items=[{id, size, quantity}])
- track_order: Track order by ID

### A2A Tools (Calls Scheduling Agent):
- a2a_schedule_delivery: Schedule delivery time
- a2a_confirm_and_create_calendar_event: Create calendar event when user confirms

## MENU ITEMS

### Veg Pizzas (have sizes: Regular, Medium, Large):
- v1 = Margherita
- v2 = Farmhouse
- v3 = Peppy Paneer
- v4 = Veggie Paradise

### Non-Veg Pizzas (have sizes: Regular, Medium, Large):
- nv1 = Chicken Golden Delight
- nv2 = Chicken Dominator

### Pizza Mania (NO sizes - flat price, just use quantity):
- m1 = Onion Pizza (₹59)
- m2 = Golden Corn Pizza (₹79)

### Sides & Desserts (NO sizes - flat price, just use quantity):
- s1 = Garlic Breadsticks (₹109)
- s2 = Stuffed Garlic Bread (₹159)
- s3 = Choco Lava Cake (₹109)

## ORDERING RULES
- For Veg/Non-Veg pizzas: include "size" (Regular/Medium/Large)
- For Pizza Mania and Sides: do NOT include "size", only "id" and "quantity"

## WORKFLOW

1. **Customer orders:**
   - place_order(customer_name="Vidya", items=[...])
   - Get order_id and estimated_minutes

2. **Schedule delivery:**
   - a2a_schedule_delivery(order_id, pizza_name, estimated_minutes)
   - Tell customer the delivery time and ask if it works

3. **Customer confirms:**
   - a2a_confirm_and_create_calendar_event()
   - Tell customer the event is added

## EXAMPLES

Example 1 - Pizza with size:
Customer: "I want 2 large Margherita"
→ place_order(customer_name="Vidya", items=[{"id":"v1", "size":"Large", "quantity":2}])

Example 2 - Pizza Mania (no size):
Customer: "I want 3 Onion Pizzas"
→ place_order(customer_name="Vidya", items=[{"id":"m1", "quantity":3}])

Example 3 - Sides (no size):
Customer: "Add 2 Choco Lava Cakes"
→ place_order(customer_name="Vidya", items=[{"id":"s3", "quantity":2}])

Example 4 - Mixed order:
Customer: "1 large Farmhouse and 2 Garlic Breadsticks"
→ place_order(customer_name="Vidya", items=[{"id":"v2", "size":"Large", "quantity":1}, {"id":"s1", "quantity":2}])

Be friendly and concise!
"""

async def create_ordering_agent():
    """Create the Ordering Agent with MCP and A2A tools."""
    mcp_tools = McpToolset(
        connection_params=SseConnectionParams(url=MCP_SERVER_URL)
    )

    return Agent(
        model="gemini-2.5-flash",
        name="ordering_agent",
        description="Pizza ordering agent with A2A connection to Scheduling Agent",
        instruction=ORDERING_AGENT_INSTRUCTION,
        tools=[
            mcp_tools,  # MCP: get_menu, place_order, track_order
            a2a_schedule_delivery,  # A2A: schedule delivery
            a2a_confirm_and_create_calendar_event  # A2A: create calendar event
        ]
    )

# ============================================================================
# AGENT RESPONSE HANDLER
# ============================================================================

async def get_agent_response(user_message: str, conversation_history: list):
    """Get response from the Ordering Agent (which can call Scheduling Agent via A2A)."""
    agent = await create_ordering_agent()

    session_service = InMemorySessionService()
    runner = Runner(
        agent=agent,
        app_name="legendary_margherita",
        session_service=session_service
    )

    session = await session_service.create_session(
        app_name="legendary_margherita",
        user_id="user"
    )

    # Build context
    context_parts = []
    if len(conversation_history) > 1:
        context_parts.append("Previous conversation:\n")
        for msg in conversation_history[:-1]:
            role = "Customer" if msg["role"] == "user" else "Assistant"
            context_parts.append(f"{role}: {msg['content']}\n")
        context_parts.append("\nCurrent message: ")

    full_message = "".join(context_parts) + user_message

    user_content = types.Content(
        role="user",
        parts=[types.Part(text=full_message)]
    )

    response_text = ""
    async for event in runner.run_async(
        user_id="user",
        session_id=session.id,
        new_message=user_content
    ):
        if hasattr(event, 'content') and event.content:
            if hasattr(event.content, 'parts'):
                for part in event.content.parts:
                    if hasattr(part, 'text') and part.text:
                        response_text += part.text

    # Clean up artifacts
    response_text = re.sub(r'```tool_[^`]+```', '', response_text)
    response_text = re.sub(r'```python\s*tool_[^`]+```', '', response_text)

    return response_text.strip()

# ============================================================================
# SIDEBAR
# ============================================================================

with st.sidebar:
    st.markdown("""
    <div style="text-align: center; padding: 1rem 0;">
        <span style="font-size: 4rem;">🍕</span>
        <h2 style="color: #D62828; margin: 0.5rem 0;">Our Menu</h2>
    </div>
    """, unsafe_allow_html=True)

    for category, items in MENU_DATA.items():
        st.markdown(f'<div class="menu-category">{category}</div>', unsafe_allow_html=True)
        for item in items:
            prices_html = " ".join([f'<span class="price-tag">{size}: ₹{price}</span>' for size, price in item["prices"].items()])
            st.markdown(f"""
            <div class="pizza-card">
                <div class="pizza-name">{item["emoji"]} {item["name"]}</div>
                <div class="pizza-desc">{item["desc"]}</div>
                <div class="price-row">{prices_html}</div>
                <div style="color: #999; font-size: 0.7rem; margin-top: 0.3rem;">ID: {item["id"]}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")

    # Orders
    st.markdown('<h3 style="color: #D62828; text-align: center;">📦 Orders</h3>', unsafe_allow_html=True)

    if st.button("🔄 Refresh", use_container_width=True):
        st.rerun()

    try:
        response = httpx.get("http://localhost:9000/orders", timeout=3)
        if response.status_code == 200:
            orders = response.json().get("orders", [])
            if orders:
                for order in reversed(orders[-5:]):
                    status = order.get("status", "Unknown")
                    status_emoji = {"Order Received": "📝", "Preparing": "👨‍🍳", "Baking": "🔥", "Quality Check": "✅", "Out for Delivery": "🚗", "Delivered": "🎉"}.get(status, "📦")
                    items = order.get("items", [])
                    item_names = ", ".join([f"{i.get('quantity')}x {i.get('name', i.get('id'))}" for i in items])
                    st.markdown(f"""
                    <div style="background: white; border-radius: 10px; padding: 0.8rem; margin: 0.5rem 0; border-left: 4px solid #D62828;">
                        <div style="font-weight: 600; color: #D62828;">#{order.get('order_id')}</div>
                        <div style="font-size: 0.75rem; color: #666;">{item_names}</div>
                        <div style="font-size: 0.8rem;">{status_emoji} {status}</div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("No orders yet")
    except:
        st.caption("Start backend to see orders")

# ============================================================================
# MAIN
# ============================================================================

st.markdown("""
<div class="main-header">
    <h1>🍕 Legendary Margherita</h1>
</div>
""", unsafe_allow_html=True)

# Status
col1, col2, col3 = st.columns(3)
with col1:
    try:
        httpx.get("http://localhost:9000/menu", timeout=2)
        st.markdown('<span class="status-online">✅ Backend</span>', unsafe_allow_html=True)
    except:
        st.markdown('<span class="status-offline">❌ Backend</span>', unsafe_allow_html=True)

with col2:
    def check_port(host, port):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except:
            return False
    if check_port("localhost", 8000):
        st.markdown('<span class="status-online">✅ MCP Server</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-offline">❌ MCP Server</span>', unsafe_allow_html=True)

with col3:
    ct = get_current_time()
    st.markdown(f'<span class="status-online">🕐 {ct["current_time"]}</span>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# Session state
if "messages" not in st.session_state:
    st.session_state.messages = [{
        "role": "assistant",
        "content": "Hi Vidya! Welcome to Legendary Margherita. I'm the Ordering Agent - I can take your pizza orders and coordinate with the Scheduling Agent for delivery times. What would you like today?"
    }]

# Chat
st.markdown("### 💬 Chat")
for message in st.session_state.messages:
    safe_content = html.escape(message["content"]).replace('\n', '<br>')
    if message["role"] == "user":
        st.markdown(f'<div style="display: flex; justify-content: flex-end; margin: 0.5rem 0;"><div class="user-message">{safe_content}</div></div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div style="display: flex; justify-content: flex-start; margin: 0.5rem 0;"><div class="assistant-message">{safe_content}</div></div>', unsafe_allow_html=True)

st.markdown("---")

def process_input():
    user_input = st.session_state.input_box
    if not user_input or not user_input.strip():
        return
    user_input = user_input.strip()
    st.session_state.messages.append({"role": "user", "content": user_input})
    st.session_state.messages.append({"role": "assistant", "content": "🔄 Processing (Ordering Agent → Scheduling Agent)..."})

    try:
        response = asyncio.run(get_agent_response(user_input, st.session_state.messages[:-1]))
        st.session_state.messages.pop()
        st.session_state.messages.append({"role": "assistant", "content": response if response else "Could not process request."})
    except Exception as e:
        st.session_state.messages.pop()
        st.session_state.messages.append({"role": "assistant", "content": f"Error: {str(e)}"})

    st.session_state.input_box = ""

def clear_chat():
    st.session_state.messages = [{"role": "assistant", "content": "Hi Vidya! What would you like to order?"}]

col1, col2 = st.columns([1, 5])
with col1:
    st.button("🔄 Clear", on_click=clear_chat, use_container_width=True)

st.text_input(
    "Order",
    placeholder="e.g., 'I want 2 large Margherita pizzas'",
    key="input_box",
    on_change=process_input,
    label_visibility="collapsed"
)

st.markdown("---")


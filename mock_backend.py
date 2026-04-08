import json
import uuid
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path

app = FastAPI(
    title="Legendary Margherita Backend",
    description="Pizza ordering API for AI agents",
    version="1.0.0"
)

# Get the directory where this script is located
BASE_DIR = Path(__file__).parent
ORDERS_FILE = BASE_DIR / "orders.json"

# Ingest menu.json as the source of truth
def load_menu():
    try:
        menu_path = BASE_DIR / "menu.json"
        with open(menu_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"error": "menu.json not found. Please create it first."}

# Load orders from file (persistence)
def load_orders():
    try:
        if ORDERS_FILE.exists():
            with open(ORDERS_FILE, "r") as f:
                return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        pass
    return {}

# Save orders to file (persistence)
def save_orders():
    with open(ORDERS_FILE, "w") as f:
        json.dump(orders_db, f, indent=2)

# Load existing orders on startup
orders_db = load_orders()

# Data Models
class OrderItem(BaseModel):
    id: str
    quantity: int
    size: Optional[str] = "Regular"

class OrderRequest(BaseModel):
    customer_name: str
    items: List[OrderItem]

class OrderResponse(BaseModel):
    order_id: str
    customer: str
    items: List[dict]
    status: str
    estimated_minutes: int
    estimated_delivery_time: str

# Helper to get pizza name from menu
def get_pizza_name(pizza_id: str) -> str:
    menu = load_menu()
    for category in menu.get("categories", []):
        for item in category.get("items", []):
            if item.get("id") == pizza_id:
                return item.get("name", pizza_id)
    return pizza_id

# Endpoints for Phase 1 requirements
@app.get("/menu")
async def get_menu():
    """Returns the full menu including the Legendary Margherita and all categories."""
    return load_menu()

@app.post("/order", status_code=201)
async def place_order(order: OrderRequest):
    """Processes a new order and returns tracking info with delivery estimate."""
    order_id = f"LM-{str(uuid.uuid4())[:6].upper()}"
    estimated_minutes = 25

    # Calculate estimated delivery time
    now = datetime.now()
    delivery_time = now + timedelta(minutes=estimated_minutes)

    # Build items list with names
    items_with_names = []
    for item in order.items:
        items_with_names.append({
            "id": item.id,
            "name": get_pizza_name(item.id),
            "size": item.size,
            "quantity": item.quantity
        })

    order_details = {
        "order_id": order_id,
        "customer": order.customer_name,
        "items": items_with_names,
        "status": "Preparing",
        "estimated_minutes": estimated_minutes,
        "estimated_delivery_time": delivery_time.strftime("%I:%M %p"),
        "created_at": now.isoformat()
    }
    orders_db[order_id] = order_details
    save_orders()  # Persist to file
    return order_details

def get_order_status(order: dict) -> dict:
    """Calculate current status based on time elapsed since order."""
    created_at = datetime.fromisoformat(order["created_at"])
    elapsed_minutes = (datetime.now() - created_at).total_seconds() / 60

    # Status progression based on time
    if elapsed_minutes < 5:
        status = "Order Received"
        message = "Your order has been received and sent to the kitchen!"
    elif elapsed_minutes < 12:
        status = "Preparing"
        message = "Our chefs are preparing your delicious pizza!"
    elif elapsed_minutes < 20:
        status = "Baking"
        message = "Your pizza is in the oven, getting crispy and golden!"
    elif elapsed_minutes < 25:
        status = "Quality Check"
        message = "Final quality check before packaging!"
    elif elapsed_minutes < 30:
        status = "Out for Delivery"
        message = "Your pizza is on its way to you!"
    else:
        status = "Delivered"
        message = "Your pizza has been delivered. Enjoy!"

    # Return updated order with current status
    updated_order = order.copy()
    updated_order["status"] = status
    updated_order["status_message"] = message
    updated_order["elapsed_minutes"] = round(elapsed_minutes, 1)

    return updated_order

@app.get("/order/{order_id}")
async def track_order(order_id: str):
    """Retrieves real-time status for the agent including delivery time."""
    if order_id not in orders_db:
        raise HTTPException(status_code=404, detail="Order not found")

    # Get order with calculated current status
    return get_order_status(orders_db[order_id])

@app.get("/orders")
async def list_orders():
    """Lists all orders with current status."""
    return {"orders": [get_order_status(order) for order in orders_db.values()]}

if __name__ == "__main__":
    import uvicorn
    # Run the shop backend on port 9000 (MCP server will use 8000)
    uvicorn.run(app, host="0.0.0.0", port=9000)
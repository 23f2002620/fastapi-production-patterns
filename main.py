import base64
from collections import defaultdict, deque
import time
from typing import Any, Dict, Optional

from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Assigned Values
TOTAL_ORDERS = 50
RATE_LIMIT_R = 15
RATE_LIMIT_WINDOW = 10.0  # seconds

app = FastAPI(title="Production-Grade Orders API")

# Enable CORS for cross-origin browser verification
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After", "*"],
)

# -----------------------------------------------------------------------------
# In-Memory Stores
# -----------------------------------------------------------------------------
# Fixed catalog strictly populated with IDs 1..50
FIXED_CATALOG: list[dict[str, Any]] = [
    {
        "id": i,
        "item": f"Production Item #{i}",
        "quantity": (i % 5) + 1,
        "status": "completed",
    }
    for i in range(1, TOTAL_ORDERS + 1)
]

# Separate storage for POST creation to keep FIXED_CATALOG clean
created_orders_db: list[dict[str, Any]] = []

# Idempotency key mapping: key -> order_dict
idempotency_store: dict[str, dict[str, Any]] = {}

# Sliding log for rate limiting: client_id -> deque of request timestamps
client_buckets: dict[str, deque] = defaultdict(deque)


# -----------------------------------------------------------------------------
# Middleware: Per-Client Rate Limiting (R = 15 / 10s)
# -----------------------------------------------------------------------------
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Allow CORS preflight requests without consuming rate limit
    if request.method == "OPTIONS":
        return await call_next(request)

    # Extract client ID from X-Client-Id header (fallback to host if missing)
    client_id = (
        request.headers.get("X-Client-Id")
        or request.headers.get("x-client-id")
        or (request.client.host if request.client else "anonymous")
    )

    now = time.time()
    timestamps = client_buckets[client_id]

    # Evict timestamps older than 10 seconds
    while timestamps and timestamps[0] <= now - RATE_LIMIT_WINDOW:
        timestamps.popleft()

    # Check limit exceedance
    if len(timestamps) >= RATE_LIMIT_R:
        oldest_ts = timestamps[0]
        retry_after_sec = max(1, int((oldest_ts + RATE_LIMIT_WINDOW) - now) + 1)

        return Response(
            content='{"detail": "Rate limit exceeded. Too many requests."}',
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            media_type="application/json",
            headers={
                "Retry-After": str(retry_after_sec),
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*",
                "Access-Control-Allow-Methods": "*",
                "Access-Control-Expose-Headers": "Retry-After, *",
            },
        )

    timestamps.append(now)
    return await call_next(request)


# -----------------------------------------------------------------------------
# Helper Functions: Cursor Encoding / Decoding
# -----------------------------------------------------------------------------
def encode_cursor(order_id: int) -> str:
    raw = f"order_cursor:{order_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor_str: str) -> int:
    try:
        decoded = base64.urlsafe_b64decode(cursor_str.encode()).decode()
        if ":" in decoded:
            return int(decoded.split(":")[-1])
        return int(decoded)
    except Exception:
        try:
            return int(cursor_str)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid cursor token.",
            )


# -----------------------------------------------------------------------------
# Data Schemas
# -----------------------------------------------------------------------------
class OrderCreate(BaseModel):
    item: Optional[str] = "Standard Widget"
    quantity: Optional[int] = 1


# -----------------------------------------------------------------------------
# API Endpoints
# -----------------------------------------------------------------------------
@app.get("/orders")
async def list_orders(limit: int = 10, cursor: Optional[str] = None):
    """
    Cursor-based pagination endpoint.
    Serves orders strictly from FIXED_CATALOG (IDs 1 through 50).
    """
    start_after_id = decode_cursor(cursor) if cursor else 0

    filtered_orders = [o for o in FIXED_CATALOG if o["id"] > start_after_id]
    page_items = filtered_orders[:limit]

    next_cursor = None
    if len(filtered_orders) > limit and page_items:
        last_item_id = page_items[-1]["id"]
        next_cursor = encode_cursor(last_item_id)

    return {"items": page_items, "next_cursor": next_cursor}


@app.post("/orders", status_code=status.HTTP_201_CREATED)
async def create_order(
    request: Request,
    payload: Optional[OrderCreate] = None,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    key = idempotency_key or request.headers.get("idempotency-key")

    if key and key in idempotency_store:
        return idempotency_store[key]

    new_id = TOTAL_ORDERS + len(created_orders_db) + 1
    item_name = payload.item if payload and payload.item else "Standard Widget"
    qty = payload.quantity if payload and payload.quantity else 1

    new_order = {
        "id": new_id,
        "item": item_name,
        "quantity": qty,
        "status": "pending",
    }

    created_orders_db.append(new_order)

    if key:
        idempotency_store[key] = new_order

    return new_order


@app.get("/health")
async def health_check():
    return {"status": "ok", "fixed_catalog_size": len(FIXED_CATALOG)}
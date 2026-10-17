# FastAPI Production Engineering Patterns

A production-oriented FastAPI service demonstrating three essential API engineering patterns: **idempotent POST requests, opaque cursor-based pagination, and per-client sliding-window rate limiting**. The project focuses on reliable request handling, predictable pagination, and transparent rate-limit metadata.

**Live API Base URL:** https://fastapi-production-patterns.onrender.com

![Python](https://img.shields.io/badge/Python-3.10+-3776AB.svg?style=flat&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-REST%20API-009688.svg?style=flat&logo=fastapi&logoColor=white)
![Pagination](https://img.shields.io/badge/Pagination-Cursor--Based-blue.svg?style=flat)
![Rate Limiting](https://img.shields.io/badge/Rate%20Limiting-Sliding%20Window-orange.svg?style=flat)
![Deployment](https://img.shields.io/badge/Deployed%20on-Render-46E3B7.svg?style=flat&logo=render&logoColor=white)

---

## ✨ Key Features

- **Idempotent Order Creation:** Uses an `Idempotency-Key` header to prevent duplicate order creation when clients retry requests.
- **Opaque Cursor-Based Pagination:** Uses Base64-encoded cursors to navigate a fixed catalog of 50 orders.
- **Per-Client Rate Limiting:** Enforces a limit of 15 requests per 10-second sliding window for each client ID.
- **Retry Metadata:** Returns a `Retry-After` header when a client exceeds the rate limit.
- **CORS Header Exposure:** Configures `Access-Control-Expose-Headers` so browser clients can read rate-limit metadata when CORS permits access.
- **Catalog Isolation:** Keeps dynamically created orders separate from the fixed 50-item pagination catalog.
- **RESTful API Design:** Uses standard HTTP methods and status codes for order creation, listing, and rate-limit errors.

## 🏗️ Architecture and Design Patterns

### 1. Idempotent Order Creation

**Endpoint:** `POST /orders`

**Header:** `Idempotency-Key`

The endpoint associates a unique idempotency key with the result of an order-creation request.

**Behavior:**

- A new key creates an order and returns `201 Created`.
- A repeated request with the same key returns the previously created result rather than creating another order.
- Repeated requests should not create duplicate records when the same key is reused.
- A robust implementation should define how it handles the same key with a different request payload.

Example:

```http
POST /orders
Idempotency-Key: 9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d
Content-Type: application/json

{
  "item": "Standard Widget",
  "quantity": 2
}
```

### 2. Opaque Cursor-Based Pagination

**Endpoint:** `GET /orders?limit=P&cursor=C`

The service exposes a fixed catalog containing 50 orders, with IDs from `1` through `50`.

**Behavior:**

- Uses Base64-encoded cursors to represent pagination positions.
- Returns a limited collection of orders for each request.
- Provides `next_cursor` when another page is available.
- Keeps dynamically created orders separate from the fixed catalog scan.
- Supports stateless pagination without requiring the server to store a separate session for every client.

Base64 encoding makes a cursor opaque by convention, but it does not encrypt or secure its contents.

### 3. Per-Client Sliding-Window Rate Limiting

**Client header:** `X-Client-Id`

| Setting | Value |
|---|---|
| Rate limit | 15 requests |
| Time window | 10 seconds |
| Limiting strategy | Sliding-window log |
| Client identifier | `X-Client-Id` |
| Exceeded-limit status | `429 Too Many Requests` |
| Retry metadata | `Retry-After` |

**Behavior:**

- Tracks request timestamps independently for each client.
- Removes expired timestamps from the sliding window.
- Rejects requests that exceed the configured limit.
- Returns a `Retry-After` header indicating when the client can retry.
- Exposes rate-limit metadata to browser JavaScript through the appropriate CORS response configuration.

For deployments with multiple workers or instances, a shared rate-limit store is needed to enforce a consistent global limit across instances.

## 🚀 Live API Reference

**Base URL**

```text
https://fastapi-production-patterns.onrender.com
```

### 1. List Orders

**Endpoint:** `GET /orders`

**Query parameters**

| Parameter | Type | Description |
|---|---|---|
| `limit` | Integer | Maximum number of catalog orders to return |
| `cursor` | String | Optional opaque cursor for continuing pagination |

**Example request**

```bash
curl -i \
  "https://fastapi-production-patterns.onrender.com/orders?limit=10"
```

**Example response**

```json
{
  "items": [
    {
      "id": 1,
      "item": "Production Item #1",
      "quantity": 2,
      "status": "completed"
    }
  ],
  "next_cursor": "b3JkZXJfY3Vyc29yOjEw"
}
```

The response above is illustrative. Actual page contents, cursor values, and item counts depend on the implementation.

### 2. Create an Order

**Endpoint:** `POST /orders`

**Request headers**

```http
Content-Type: application/json
Idempotency-Key: test-key-100
X-Client-Id: client-alpha
```

**Request body**

```json
{
  "item": "Standard Widget",
  "quantity": 2
}
```

**Example response — `201 Created`**

```json
{
  "id": 51,
  "item": "Standard Widget",
  "quantity": 2,
  "status": "pending"
}
```

The order ID is illustrative. The actual ID depends on the service's order-creation logic.

### 3. Rate Limit Exceeded

When a client exceeds the configured request limit, the service returns `429 Too Many Requests`.

**Example response**

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 8
Access-Control-Expose-Headers: Retry-After
Content-Type: application/json
```

```json
{
  "detail": "Rate limit exceeded. Too many requests."
}
```

The `Retry-After` value is an example and should reflect the implementation's calculated retry interval.

The `Access-Control-Expose-Headers` response header makes `Retry-After` readable by browser JavaScript for permitted cross-origin requests. It does not itself enable CORS or authorize an origin.

## 🧪 Local Verification

### 1. Test Cursor-Based Pagination

```bash
curl -s "http://localhost:8000/orders?limit=15"
```

To request another page, pass the returned cursor:

```bash
curl -s \
  --get "http://localhost:8000/orders" \
  --data-urlencode "limit=15" \
  --data-urlencode "cursor=YOUR_NEXT_CURSOR"
```

Replace `YOUR_NEXT_CURSOR` with the actual `next_cursor` returned by the preceding request.

### 2. Test Idempotent Order Creation

Run the same request twice using the same idempotency key.

```bash
curl -i -X POST "http://localhost:8000/orders" \
  -H "Idempotency-Key: test-key-100" \
  -H "Content-Type: application/json" \
  -d '{"item": "Widget A", "quantity": 1}'
```

Run the command again without changing the key or payload.

**Expected behavior:** Both requests refer to the same created order, and the second request does not create a duplicate record.

The status code and response headers on a repeated request depend on the API's documented idempotency policy.

### 3. Test the Rate Limiter

The following Bash loop sends 16 requests rapidly using the same client ID.

```bash
for i in {1..16}; do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -H "X-Client-Id: test-client" \
    "http://localhost:8000/orders?limit=1"
done
```

**Expected behavior:** With an initially empty bucket and all requests inside the same 10-second window, no more than 15 requests should be accepted under the configured limit. The excess request should return `429`.

Wait until the rate-limit window expires before repeating the test.

## 🛠️ Local Development and Setup

### Prerequisites

- Python 3.10 or later
- pip
- Git

### 1. Clone the Repository

Replace `YOUR_USERNAME` with your GitHub username.

```bash
git clone https://github.com/YOUR_USERNAME/fastapi-production-patterns.git
cd fastapi-production-patterns
```

### 2. Create a Virtual Environment

**Linux / macOS**

```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows**

```powershell
python -m venv venv
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
python -m pip install --upgrade pip
pip install fastapi uvicorn pydantic
```

If the repository contains a `requirements.txt` file, install the project's pinned dependencies instead:

```bash
pip install -r requirements.txt
```

### 4. Run the Application

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The local service will be available at:

- API base URL: http://127.0.0.1:8000
- Order listing: http://127.0.0.1:8000/orders?limit=10
- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

## 📁 Project Structure

```text
fastapi-production-patterns/
├── main.py             # FastAPI application and API endpoints
├── requirements.txt    # Python dependencies (if present)
└── README.md           # Project documentation
```

Add any additional source files and test modules present in your actual repository.

## 🧰 Technology Stack

| Technology | Purpose |
|---|---|
| Python | Core programming language |
| FastAPI | REST API framework |
| Pydantic | Request and response validation |
| Uvicorn | ASGI server |
| Base64 | Cursor encoding |
| Sliding-window log | Request rate limiting |
| HTTP headers | Idempotency and rate-limit metadata |
| Render | Cloud deployment |

## 🔒 Production Considerations

- Store idempotency keys and their associated results durably when duplicate prevention must survive restarts.
- Enforce atomic idempotency-key handling to prevent concurrent requests from creating duplicate orders.
- Validate order payloads and reject reuse of an idempotency key with an incompatible payload.
- Validate cursor values and define behavior for malformed or expired cursors.
- Apply consistent ordering to the catalog so pagination remains deterministic.
- Use a shared store such as Redis for rate limiting across multiple application instances.
- Calculate `Retry-After` from the actual sliding-window state.
- Configure CORS explicitly if browser clients need to read rate-limit response headers.
- Add automated tests for duplicate requests, pagination boundaries, and rate-limit behavior.

---

**Built with FastAPI to demonstrate reliable order creation, cursor-based pagination, and client-aware rate limiting.**

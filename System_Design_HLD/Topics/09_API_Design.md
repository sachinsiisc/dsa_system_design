# Topic 9: API Design
## HLD Deep Dive | MAANG Interview Ready

---

## 1. REST Design Principles

```
REST = Representational State Transfer. 6 constraints by Roy Fielding (2000).

1. Client-Server:   UI separated from backend. Each evolves independently.
2. Stateless:       Server stores NO session state. Each request self-contained.
3. Cacheable:       Responses explicitly labeled as cacheable or not.
4. Uniform Interface: Standard resource-based URLs, HTTP methods.
5. Layered System:  Client doesn't know if hitting server or load balancer.
6. Code on Demand (optional): Server can send executable code (JavaScript).

KEY PRINCIPLE: Resources are NOUNS. Actions are HTTP METHODS (verbs).
```

---

## 2. Resource Design — URLs and Methods

```
RESOURCE NAMING (nouns, not verbs):

BAD:
  POST /createUser
  GET  /getUser?id=123
  POST /deleteUser/123
  POST /updateUserStatus
  GET  /getUserOrders?user_id=123

GOOD:
  POST   /users             → create user
  GET    /users/123         → get user 123
  PUT    /users/123         → replace user 123 completely
  PATCH  /users/123         → update specific fields of user 123
  DELETE /users/123         → delete user 123
  GET    /users/123/orders  → get all orders for user 123

HTTP METHODS AND IDEMPOTENCY:
  Method  │ Effect      │ Idempotent │ Safe │ Cacheable
  ────────┼─────────────┼────────────┼──────┼──────────
  GET     │ Read        │ YES        │ YES  │ YES
  HEAD    │ Read headers│ YES        │ YES  │ YES
  POST    │ Create      │ NO         │ NO   │ NO
  PUT     │ Replace all │ YES        │ NO   │ NO
  PATCH   │ Update part │ YES*       │ NO   │ NO
  DELETE  │ Delete      │ YES        │ NO   │ NO
  OPTIONS │ CORS check  │ YES        │ YES  │ YES

Idempotent: calling the same request multiple times has the same effect as calling once.
  DELETE /users/123: first call deletes. Second call: user already gone (still 200 or 404).
  GET /users/123: same result each time. Safe to retry.
  POST /users: each call creates ANOTHER user. NOT idempotent.

*PATCH can be idempotent if implemented correctly: PATCH /users/123 {name: "Alice"}.
 Calling twice: second call sets name to "Alice" again → same result. Idempotent.

NESTED RESOURCES (relationships):
  GET  /users/123/orders         → all orders by user 123
  GET  /users/123/orders/456     → specific order 456 by user 123
  POST /users/123/orders         → create order for user 123
  
  DELETE /users/123/orders/456   → delete order 456 (only if it belongs to user 123)
  
  Rule: max 2-3 levels of nesting. Beyond that: use flat resources with filters.
  Too deep: /users/123/orders/456/items/789/returns/101 → unwieldy.
  Better: GET /returns/101 with return_id that implies order and user.

FILTERING, SORTING, PAGINATION:
  GET /products?category=electronics&min_price=500&max_price=2000
  GET /orders?status=pending&sort=-created_at   # - prefix = descending
  GET /users?fields=id,name,email               # sparse fieldsets
```

---

## 3. HTTP Status Codes

```
2xx SUCCESS:
  200 OK                → request succeeded, body has result.
  201 Created           → POST success, new resource created.
                          Include Location: /users/123 header.
  202 Accepted          → Request accepted, processing async (e.g., queued job).
  204 No Content        → Success, no response body (DELETE, some PATCHes).
  206 Partial Content   → Range request (video streaming: byte range response).

3xx REDIRECTION:
  301 Moved Permanently → Resource permanently moved. Cache this redirect.
  302 Found             → Temporary redirect. Don't cache.
  304 Not Modified      → Client's cached version is current. No body. ETag/If-None-Match.

4xx CLIENT ERRORS:
  400 Bad Request       → Malformed request, validation failed.
                          Body: {"error": "invalid_input", "field": "email", "message": "Invalid format"}
  401 Unauthorized      → Not authenticated. Missing or invalid token.
                          Header: WWW-Authenticate: Bearer
  403 Forbidden         → Authenticated but not authorized for this action.
  404 Not Found         → Resource doesn't exist.
  405 Method Not Allowed→ POST /users/123 when POST not supported (use PUT).
  409 Conflict          → Conflict with current state (duplicate username).
  410 Gone              → Resource permanently deleted.
  422 Unprocessable     → Request valid syntax but semantic errors (FK violation).
  429 Too Many Requests → Rate limited. Include Retry-After: 60 header.

5xx SERVER ERRORS:
  500 Internal Server Error → Generic server bug. Log the error, return generic message.
  502 Bad Gateway           → Upstream service returned invalid response.
  503 Service Unavailable   → Server overloaded or down for maintenance.
                              Include Retry-After header.
  504 Gateway Timeout       → Upstream service timed out.

ERROR RESPONSE FORMAT:
  Always return consistent error format:
  {
    "error": {
      "code": "VALIDATION_ERROR",          // machine-readable
      "message": "Email format is invalid", // human-readable
      "field": "email",                     // which field (for form display)
      "request_id": "req_abc123xyz"         // for debugging/tracing
    }
  }
  
  Never expose: stack traces, internal paths, database errors (security risk).
```

---

## 4. Pagination

```
OFFSET PAGINATION (simple but has problems):
  GET /posts?page=2&limit=20
  
  SQL: SELECT * FROM posts ORDER BY created_at DESC LIMIT 20 OFFSET 20;
  
  Response:
  {
    "data": [...],
    "pagination": {
      "page": 2,
      "limit": 20,
      "total": 1000,
      "total_pages": 50
    }
  }
  
  Problems:
    If new post added between page 1 and page 2 request: 
    page 2 sees the old page 1's last item (skipped) or sees it again (duplicate).
    Performance: OFFSET 10000 → DB scans 10,020 rows, discards 10,000. Slow.

CURSOR PAGINATION (best for large datasets, infinite scroll):
  GET /posts?limit=20
  GET /posts?cursor=eyJpZCI6MTIzfQ==&limit=20   # next page
  
  Cursor: opaque token encoding position (e.g., base64 of {id: 123, created_at: "..."})
  
  SQL: SELECT * FROM posts WHERE id < 123 ORDER BY id DESC LIMIT 20;
  → Uses index. No offset scan. Fast for any page.
  
  Response:
  {
    "data": [...],
    "pagination": {
      "next_cursor": "eyJpZCI6MTAzfQ==",
      "has_next": true
    }
  }
  
  Limitations:
    Can't jump to page 5 directly (must follow cursors).
    Can't show "Page 2 of 50".
    New items inserted: don't affect pages (stable cursor).

KEYSET PAGINATION:
  Based on indexed column value.
  GET /posts?after_id=103&limit=20
  
  SQL: SELECT * FROM posts WHERE id > 103 ORDER BY id ASC LIMIT 20;
  Simple cursor using primary key.

COMPARISON:
  Use offset for: admin panels, small datasets, user needs "go to page N."
  Use cursor for: infinite scroll, large datasets, social feeds, mobile apps.
```

---

## 5. Versioning

```
WHY VERSION:
  Your API has clients (mobile apps, web, third-party).
  Breaking changes break clients.
  Version = non-breaking migration path.

APPROACH 1: URL Versioning (most common)
  /api/v1/users
  /api/v2/users
  
  Pros: visible, cacheable, easy to route.
  Cons: URL is a resource identifier — version in URL is technically non-RESTful.
  Used by: Stripe, Twitter, GitHub.

APPROACH 2: Header Versioning
  GET /api/users
  Accept: application/vnd.myapi.v2+json
  
  or: API-Version: 2
  
  Pros: clean URLs, "correct" REST.
  Cons: harder to test (can't just paste URL in browser), not cacheable by default.
  Used by: GitHub (via custom Accept header).

APPROACH 3: Query Parameter
  GET /api/users?version=2
  
  Pros: easy to test.
  Cons: pollutes query params, easily forgotten.

APPROACH 4: No Versioning (Continuous Evolution)
  Never break backward compatibility. Add new fields, never remove.
  Clients ignore unknown fields.
  Used by: Google (API design guide recommends this for internal APIs).

VERSIONING STRATEGY:
  v1: still supported, deprecated notice.
  v2: current stable.
  v3: beta/preview.
  
  Deprecation timeline: give clients 12-18 months to migrate.
  Sunset header: Sunset: Sat, 15 March 2025 00:00:00 GMT
```

---

## 6. Authentication and Authorization

```
AUTHENTICATION: Who are you?
AUTHORIZATION: What are you allowed to do?

API KEY (simplest):
  Client sends key in header: X-API-Key: sk_live_abc123
  Server validates key against database.
  
  Good for: server-to-server, rate limiting by key.
  Bad for: user-facing (can't scope per user), no expiry.

JWT (JSON Web Token) — Stateless Auth:
  Structure: header.payload.signature (base64url encoded)
  
  Header: {"alg": "RS256", "typ": "JWT"}
  Payload: {"sub": "user_123", "role": "admin", "exp": 1726458600, "iat": 1726455000}
  Signature: RS256(base64(header) + "." + base64(payload), private_key)
  
  Token: eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyXzEyMyJ9.SIG...
  
  Validation: verify signature with PUBLIC key. No DB lookup needed!
  
  # Python validation:
  import jwt
  
  def validate_token(token: str) -> dict:
      try:
          payload = jwt.decode(token, PUBLIC_KEY, algorithms=["RS256"])
          return payload  # {"sub": "user_123", "role": "admin"}
      except jwt.ExpiredSignatureError:
          raise AuthError("Token expired")
      except jwt.InvalidTokenError:
          raise AuthError("Invalid token")
  
  PROS: Stateless (no DB lookup per request). Scalable. Self-contained.
  CONS: Can't invalidate before expiry (use short expiry + refresh tokens).
        Payload visible (don't put sensitive data in JWT — it's encoded, not encrypted).

OAUTH 2.0:
  Authorization framework. Not authentication (OpenID Connect adds that).
  User grants your app access to THEIR data on another service.
  
  Flow: 
    1. User clicks "Login with Google."
    2. Your app redirects to Google.
    3. User authenticates with Google, grants permission.
    4. Google redirects back with auth code.
    5. Your app exchanges code for access_token (and refresh_token).
    6. Your app calls Google APIs with access_token.
  
  Token types:
    access_token: short-lived (1 hour). Used for API calls.
    refresh_token: long-lived (30 days). Used to get new access_token.
    id_token (OIDC): JWT with user identity info.

mTLS (Mutual TLS) — for microservices:
  Both client AND server present certificates.
  Server verifies client cert → client is a trusted service.
  No tokens needed. Certificate-based identity.
  Used by: Kubernetes (istio service mesh), Google internal services.
```

---

## 7. Rate Limiting

```
WHY:
  Protect API from abuse, ensure fair usage, prevent DoS.

ALGORITHMS:

Token Bucket (most flexible):
  Bucket with capacity N tokens. Refills at rate R tokens/second.
  Request: consume 1 token. If bucket empty: 429.
  Burst allowed: up to N requests if bucket was full.
  
  Stripe: 100 requests/second steady, burst up to 200.

Fixed Window:
  Count requests in fixed time window (e.g., per minute).
  Simple. Problem: 120 requests allowed at 11:59:59 PM.
  120 more allowed at 12:00:00 AM. 240 in 2 seconds.
  "Window boundary attack."

Sliding Window Log:
  Store timestamp of each request.
  On each request: count requests in last 60 seconds.
  Exact. Problem: memory usage for high-traffic (store all timestamps).

Sliding Window Counter:
  Approximate sliding window using two fixed windows.
  current_count = prev_count × (overlap%) + current_window_count
  Memory efficient. ~0.1% error rate. Good compromise.

RATE LIMITING HEADERS:
  Response always includes:
  X-RateLimit-Limit: 100       # total allowed per window
  X-RateLimit-Remaining: 47    # remaining in current window
  X-RateLimit-Reset: 1726459200 # Unix timestamp when window resets
  Retry-After: 60              # (on 429) seconds until retry allowed

IMPLEMENTATION:
  # Redis Lua script (atomic token bucket):
  local key = KEYS[1]
  local capacity = tonumber(ARGV[1])
  local refill_rate = tonumber(ARGV[2])
  local now = tonumber(ARGV[3])
  
  local state = redis.call("HMGET", key, "tokens", "last_refill")
  local tokens = tonumber(state[1]) or capacity
  local last_refill = tonumber(state[2]) or now
  
  local elapsed = math.max(0, now - last_refill)
  tokens = math.min(capacity, tokens + elapsed * refill_rate)
  
  if tokens >= 1 then
      tokens = tokens - 1
      redis.call("HMSET", key, "tokens", tokens, "last_refill", now)
      redis.call("EXPIRE", key, 3600)
      return {1, tokens}  -- allowed, remaining
  else
      return {0, 0}  -- rate limited
  end

TIERED RATE LIMITS:
  Free tier:    100 requests/minute
  Pro tier:     10,000 requests/minute
  Enterprise:   Unlimited (with SLA)
  
  Key: "ratelimit:{api_key}:{window}" → count
```

---

## 8. API Security

```
INPUT VALIDATION:
  Never trust client data.
  Validate: type, format, length, range, allowed values.
  
  # Pydantic (Python) — automatic validation:
  from pydantic import BaseModel, EmailStr, Field
  
  class CreateUserRequest(BaseModel):
      name:     str = Field(min_length=1, max_length=100)
      email:    EmailStr
      age:      int = Field(ge=0, le=150)  # 0 <= age <= 150
      role:     Literal["admin", "user", "viewer"]

SQL INJECTION PREVENTION:
  NEVER: f"SELECT * FROM users WHERE email = '{email}'"
  ALWAYS: parameterized queries:
    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
  
  Or ORM: User.query.filter_by(email=email).first()

CORS (Cross-Origin Resource Sharing):
  Browser blocks API calls from different origins by default.
  Server must explicitly allow origins.
  
  Response headers:
  Access-Control-Allow-Origin: https://app.example.com    # specific origin
  Access-Control-Allow-Methods: GET, POST, PUT, DELETE
  Access-Control-Allow-Headers: Content-Type, Authorization
  Access-Control-Max-Age: 86400  # preflight result cached 24h

HTTPS ONLY:
  Always redirect HTTP → HTTPS.
  HSTS header: Strict-Transport-Security: max-age=31536000; includeSubDomains
  Preload HSTS list: browser enforces HTTPS before first request.

SENSITIVE DATA:
  Never log: passwords, credit card numbers, tokens, SSN.
  Mask in logs: user_123 instead of actual email.
  Response: never include sensitive fields unless necessary.
```

---

## 9. API Design Principles (Google Cloud Style)

```
1. RESOURCE-ORIENTED DESIGN:
   Think in resources, not actions.
   users, orders, products, payments — not createUser, processOrder.

2. STANDARD METHODS FIRST:
   List, Get, Create, Update, Delete cover 80% of needs.
   Custom methods only when standard don't fit.
   POST /users/123:sendVerificationEmail (custom, verb in URL OK for custom methods)

3. PARTIAL RESPONSES:
   Only return fields the client needs.
   GET /users/123?fields=id,name,email
   Reduces payload, bandwidth, client parsing time.

4. ERROR DETAILS:
   Always include: machine-readable code, human-readable message, request_id.
   For validation errors: include which field failed and why.

5. LONG-RUNNING OPERATIONS:
   Some operations take seconds/minutes (ML inference, video encoding).
   POST /videos returns immediately with: {"operation_id": "op_abc123"}
   GET /operations/op_abc123 → {"status": "processing", "progress": 45}
   GET /operations/op_abc123 → {"status": "done", "result": {...}}

6. IDEMPOTENCY KEYS:
   POST endpoints should accept Idempotency-Key header.
   Same key → same result (no duplicate create).
   Store: SET idempotency:{key} {response} NX EX 86400
```

---

## 10. Interview Questions

```
Q1: "Design the API for a URL shortener."
A: POST /urls  Body: {long_url: "...", custom_alias: "optional", expires_in_days: 30}
              Response: {short_url: "https://sho.rt/abc123", created_at: "..."}
   GET /urls/{code}  Response: 302 redirect to long_url.
   GET /urls/{code}/stats  Response: {clicks: 1234, created_at: "...", expires_at: "..."}
   DELETE /urls/{code}  Response: 204 No Content.

Q2: "What's the difference between PUT and PATCH?"
A: PUT replaces the ENTIRE resource. Must send all fields.
   PATCH updates specific fields. Send only changed fields.
   PUT /users/123 {name:"Alice", email:"a@b.com"} → if you omit email, it's deleted.
   PATCH /users/123 {name:"Alice"} → only name updated. Email unchanged.

Q3: "How do you handle pagination at scale?"
A: Cursor-based for large datasets (feeds, history). Encode last seen ID or timestamp.
   Offset for admin UIs where user needs to jump to specific page.
   Never use OFFSET on tables > 1M rows (performance degrades).

Q4: "How would you version your API?"
A: URL versioning (/api/v1/, /api/v2/) for public APIs — visible, easy to route.
   Header versioning for internal APIs.
   Provide 12-18 month deprecation window. Use Sunset header.

Q5: "How do you prevent API abuse?"
A: Rate limiting (token bucket in Redis) per API key or user.
   API key rotation. OAuth scope limiting.
   Input validation to prevent injection.
   Request size limits (reject > 10MB body).
   CAPTCHA for user-facing forms.
   WAF (Cloudflare) for IP-level blocking.
```


---

## HOW THESE HLD CONCEPTS APPEAR IN THE CASE STUDIES

### Scalability (this file) — Case Study Connections

**CS04 Uber:** Horizontal scaling of ride-service. Stateless pods. Geo-shard drivers.
Adding India capacity: deploy more pods. No code change. Just config.

**CS06 YouTube:** CDN scales video delivery without scaling origin servers.
Async transcode queue: upload completes in 2s. Transcode takes 10 min in background.

**CS09 Payment Gateway:** Idempotency makes any node retry-safe. Horizontal scale-friendly.
Stateless: transaction state in PostgreSQL. Any instance handles any request.

### Load Balancing (HLD 03) — Case Study Connections

**CS04 Uber:** L4 LB at TCP level (fast). L7 routes by URL path to microservices.
/api/rides/* → ride-service. /api/payments/* → payment-service.

**CS01 URL Shortener:** L4 round-robin. All nodes identical (same Redis data). Millions of redirects/s.

**CS08 Twitter:** Fanout workers use consistent hashing LB on user_id. Same user → same worker.

### Caching (HLD 04) — Case Study Connections

**CS04 Uber:** Redis for driver locations (TTL 30s). Fare estimate cache 60s.
LLD link: CachingDecorator (T04) wraps DriverLocationService.

**CS06 YouTube:** CDN edge caches video segments (Cache-Control: max-age=86400).
Redis caches: metadata, search results (TTL 300s). LLD: CachingSearchDecorator.

**CS07 Google Search:** Top 1000 query results in in-memory cache. PageRank cached weekly.

**CS09 Payment Gateway:** Fraud scores cached per session. Exchange rates cached 60s.

### Databases (HLD 05) — Case Study Connections

**CS04 Uber:** PostgreSQL (trips, ACID). Redis (locations, TTL). Cassandra (analytics, high writes).

**CS06 YouTube:** MySQL (metadata, joins). Bigtable (counts, high write throughput). GCS (binary blobs).

**CS09 Payment Gateway:** PostgreSQL (payments, ACID — money never loses consistency).
Redis (idempotency keys, fast check). Elasticsearch (search transaction history).

### Message Queues (HLD 06) — Case Study Connections

**CS06 YouTube:** Kafka — upload event → transcode + notification + analytics workers.
Dead-letter queue for failed transcode jobs.
LLD link: Command pattern (TranscodeCommand object published to queue).

**CS08 Twitter:** Kafka — tweet published → fanout workers. Partitioned by user_id.
Consumer group pattern. One partition per worker. In-order delivery per user.

**CS09 Payment Gateway:** Kafka — PaymentCompleted event consumed by inventory, ledger, fraud.
Outbox pattern: DB write + Kafka publish in same transaction (no lost events).

### CAP Theorem (HLD 07) — Case Study Connections

**CS04 Uber (AP):** Driver location: show stale GPS during partition. Don't block ride requests.
Availability > perfect consistency for location data.

**CS09 Payment Gateway (CP):** During partition: REFUSE payment. No double-charge risk.
Consistency > availability for money. User retries later after partition heals.

**CS01 URL Shortener (AP):** New URL: replication lag ok (1-2s). User waits 2s then shares link.
Read-your-write: route creator's first redirect to primary DB.

### Consistency Models (HLD 08) — Case Study Connections

**CS08 Twitter:** Eventual consistency for follower timelines (fanout takes 100ms-5s).
Strong consistency for your own tweets: you see them immediately (read-your-write).

**CS05 Netflix:** Strong consistency for "continue watching" (your progress, read-your-write).
Eventual consistency for global trending content lists (updated every few minutes).

**CS09 Payment:** Strong (ACID) for account balance. Cannot ever be eventually consistent for money.

### API Design (HLD 09) — Case Study Connections

**CS04 Uber:** POST /api/v1/rides → create. WebSocket for real-time driver location push.
REST for commands. WebSocket for streaming state updates.

**CS09 Payment:** POST /v1/payments with Idempotency-Key header. Webhook on completion.
Async pattern: respond PENDING immediately, webhook when CAPTURED/FAILED.

**CS11 AI Systems:** POST /v1/chat/completions. SSE for streaming tokens to client.
Compatible with OpenAI API format (LLD: Adapter pattern for multiple providers).

### Rate Limiting (HLD 12) — Case Study Connections

**CS09 Payment Gateway:** Per-merchant 1000 req/s (token bucket). Per-card 10/hour (sliding window).
LLD link: RateLimitDecorator (T04) wraps PaymentProcessor.

**CS11 AI Systems:** Per-user 60 req/min. Redis ZADD + ZCOUNT sliding window.
LLD link: RateLimitDecorator wraps LLMAdapter.

**CS04 Uber:** 5 ride requests/min per user. Gateway enforces before service sees it.

### Consistent Hashing (HLD 11) — Case Study Connections

**CS04 Uber:** Driver geo-sharding. Adding new city shard: only that geo-hash remaps.
Simple modulo would remap ALL drivers on scale event (bad for production).

**CS01 URL Shortener:** Redis cluster. Consistent hashing: adding node remaps only 1/N keys.
Simple modulo: adding node remaps ALL keys → cache miss storm.

**CS08 Twitter:** Kafka partition by user_id = consistent hashing at infra level.
Same user's fanout always goes to same worker. Ordering guaranteed.

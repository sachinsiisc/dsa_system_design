# 12 — Rate Limiting — Google Level

## Why Rate Limiting

- **API abuse prevention** — scrapers, DDoS
- **Fair usage** — one client can't starve others
- **Cost control** — expensive downstream calls (LLM APIs, SMS)
- **SLA enforcement** — guarantee latency for paying tiers

---

## Algorithms

### 1. Token Bucket (most common)

```
Bucket holds max N tokens.
Tokens refill at rate R per second.
Each request consumes 1 token.
If bucket empty → reject request.
```

```python
import time

class TokenBucket:
    def __init__(self, capacity, refill_rate):
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate = refill_rate  # tokens per second
        self.last_refill = time.time()

    def allow(self):
        now = time.time()
        elapsed = now - self.last_refill
        # Add tokens based on elapsed time
        self.tokens = min(self.capacity,
                          self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False
```

**Properties:**
- Allows bursts up to `capacity` tokens
- Smooth average rate = `refill_rate` per second
- Memory: O(1) per user

---

### 2. Leaky Bucket

```
Requests enter a queue (bucket).
Requests leave at a fixed rate (leak rate).
If queue full → reject.
```

```python
import time
from collections import deque

class LeakyBucket:
    def __init__(self, capacity, leak_rate):
        self.capacity = capacity
        self.leak_rate = leak_rate   # requests per second
        self.queue = deque()

    def allow(self):
        now = time.time()
        # Remove old requests that have "leaked"
        while self.queue and now - self.queue[0] >= 1.0 / self.leak_rate:
            self.queue.popleft()

        if len(self.queue) < self.capacity:
            self.queue.append(now)
            return True
        return False
```

**Properties:**
- Smoothes out bursts — output always at fixed rate
- No bursts allowed through (unlike token bucket)

---

### 3. Fixed Window Counter

```
Divide time into windows (e.g., each minute).
Count requests in current window.
If count > limit → reject.
Reset counter at window start.
```

```python
class FixedWindowCounter:
    def __init__(self, limit, window_size):
        self.limit = limit
        self.window_size = window_size
        self.counter = 0
        self.window_start = time.time()

    def allow(self):
        now = time.time()
        if now - self.window_start >= self.window_size:
            self.counter = 0
            self.window_start = now

        if self.counter < self.limit:
            self.counter += 1
            return True
        return False
```

**Problem:** Boundary spike — 100 req at end of minute + 100 at start of next = 200 in 1 second.

---

### 4. Sliding Window Log

```
Store timestamp of every request.
Count requests in last [window_size] seconds.
```

```python
class SlidingWindowLog:
    def __init__(self, limit, window_size):
        self.limit = limit
        self.window_size = window_size
        self.log = deque()

    def allow(self):
        now = time.time()
        # Remove requests outside the window
        while self.log and now - self.log[0] > self.window_size:
            self.log.popleft()

        if len(self.log) < self.limit:
            self.log.append(now)
            return True
        return False
```

**Properties:** Accurate but memory intensive — stores every request timestamp.

---

### 5. Sliding Window Counter (Best: accurate + memory efficient)

```
Weighted blend of previous window count + current window count.
current_count = prev_window * (1 - elapsed_ratio) + current_window
```

```python
class SlidingWindowCounter:
    def __init__(self, limit, window_size):
        self.limit = limit
        self.window_size = window_size
        self.prev_count = 0
        self.curr_count = 0
        self.window_start = time.time()

    def allow(self):
        now = time.time()
        elapsed = now - self.window_start

        if elapsed >= self.window_size:
            self.prev_count = self.curr_count
            self.curr_count = 0
            self.window_start = now
            elapsed = 0

        ratio = elapsed / self.window_size
        estimated = self.prev_count * (1 - ratio) + self.curr_count

        if estimated < self.limit:
            self.curr_count += 1
            return True
        return False
```

---

## Distributed Rate Limiting (Production)

Single server: easy. Distributed: **need shared state**.

### Redis-based (most common in production)

```python
import redis

class RedisRateLimiter:
    def __init__(self, redis_client, limit, window_seconds):
        self.redis = redis_client
        self.limit = limit
        self.window = window_seconds

    def allow(self, user_id):
        key = f"rate:{user_id}:{int(time.time() // self.window)}"
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, self.window * 2)
        count, _ = pipe.execute()
        return count <= self.limit

    # Token bucket in Redis using Lua script (atomic)
    TOKEN_BUCKET_SCRIPT = """
    local key = KEYS[1]
    local capacity = tonumber(ARGV[1])
    local rate = tonumber(ARGV[2])
    local now = tonumber(ARGV[3])

    local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
    local tokens = tonumber(bucket[1]) or capacity
    local last_refill = tonumber(bucket[2]) or now

    local elapsed = now - last_refill
    tokens = math.min(capacity, tokens + elapsed * rate)

    if tokens >= 1 then
        tokens = tokens - 1
        redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
        redis.call('EXPIRE', key, 3600)
        return 1
    end
    return 0
    """
```

---

## Where to Implement Rate Limiting

```
Client → API Gateway (first line of defense)
              ↓ (if passes)
         Service (secondary, per-endpoint limits)
              ↓
         Redis (shared state for distributed)
```

**API Gateway rate limiting:**
- By IP, by user_id, by API key
- Different tiers: free=100/min, pro=10000/min
- Return 429 Too Many Requests with `Retry-After` header

---

## Algorithm Comparison

| Algorithm | Burst | Accuracy | Memory | Complexity |
|-----------|-------|----------|--------|------------|
| Token Bucket | ✅ Allows | Good | O(1) | Simple |
| Leaky Bucket | ❌ Smoothed | Good | O(n) | Simple |
| Fixed Window | ✅ Allows | Poor (boundary) | O(1) | Simplest |
| Sliding Window Log | ✅ | Exact | O(n) | Simple |
| Sliding Window Counter | Limited | Very good | O(1) | Medium |

**Google/Stripe/GitHub recommendation: Token Bucket for most APIs.**

---

## Interview Q&A

**Q: Which algorithm would you use for a public API?**
A: Token bucket — allows controlled bursts (good UX for occasional heavy users) while maintaining average rate. Implemented in Redis with Lua script for atomicity.

**Q: How to rate limit in a distributed system?**
A: Centralized counter in Redis. Each API gateway node checks Redis before allowing request. Use Redis pipelines/Lua scripts for atomicity. Trade-off: Redis becomes critical path — add replica for HA.

**Q: What HTTP status code for rate limited requests?**
A: 429 Too Many Requests. Include headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After`.

**Q: What's the boundary problem with fixed window?**
A: If limit is 100/min, a user can send 100 at 11:59 and 100 at 12:00 = 200 in 2 seconds. Sliding window fixes this.


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

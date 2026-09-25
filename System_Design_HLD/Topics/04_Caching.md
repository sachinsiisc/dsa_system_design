# Topic 4: Caching
## HLD Deep Dive | MAANG Interview Ready

---

## 1. Why Cache?

```
Database query:      50-100ms
Redis in-memory:     < 1ms
L1 CPU cache:        1 ns

1,000 users read "Top 10 trending articles":
  Without cache: 1,000 DB queries × 100ms = 100 seconds total DB load
  With cache:    1 DB query + 999 Redis hits × 1ms ≈ 1 second total

Cache = pre-computed answers stored close to the requester.
       Trades memory for speed and DB load reduction.
```

---

## 2. Cache Hit and Miss

```
Cache HIT:  Data found in cache → return in < 1ms.
Cache MISS: Data not in cache → query DB → store in cache → return.

Cache Hit Rate = hits / (hits + misses)

Target: > 90% hit rate for most use cases.
  90% hit rate: only 10% of requests hit the DB.
  50% hit rate: cache helping but not much; reconsider caching strategy.

MEASURING HIT RATE IN REDIS:
  redis-cli INFO stats | grep -E "keyspace_hits|keyspace_misses"
  # keyspace_hits:1000000
  # keyspace_misses:50000
  # Hit rate = 1000000 / 1050000 = 95.2%

HIT RATE BY DATA TYPE:
  User profile:    high (users read their profile many times per session)
  Product details: high (millions of users view same products)
  Search results:  medium (query varies per user)
  Order history:   low (unique per user, read rarely)
  Real-time stock: 0% (changes every millisecond — not cacheable)
```

---

## 3. Cache Eviction Policies

```
Cache has limited memory. When full: must evict something.

LRU — Least Recently Used:
  Evict item not accessed longest.
  Intuition: if you haven't used it recently, you probably won't soon.
  
  Implementation: doubly linked list + hash map.
  O(1) get and put.
  
  Redis: allkeys-lru eviction policy.
  Use: general purpose. Browser caches, DB query caches.
  
  # Python LRU Cache (built-in):
  from functools import lru_cache
  
  @lru_cache(maxsize=1000)
  def get_user_profile(user_id: int) -> dict:
      return db.query("SELECT * FROM users WHERE id = ?", user_id)
  # Automatically evicts LRU entries when maxsize reached.

LFU — Least Frequently Used:
  Evict item accessed fewest times (across its entire cache lifetime).
  Better for long-term popular items (popular items accumulate high count).
  Worse for recently popular items (new items start with count=1, evicted early).
  
  Redis: allkeys-lfu eviction policy.
  Use: content that has stable popularity (home page, popular product pages).

TTL — Time To Live (Expiration):
  Each item expires after N seconds. Auto-evicted.
  Simplest. Good for time-sensitive data.
  
  redis.set("weather:mumbai", json.dumps(weather_data), ex=300)  # expires in 5min
  
  Use: weather, stock prices, trending topics, exchange rates.
  NOT for: user data that might change and needs immediate invalidation.

FIFO — First In First Out:
  Evict oldest-inserted item.
  Ignores access patterns. Rarely optimal.
  Use: message queues, circular buffers (not typical LRU caches).

RANDOM:
  Evict random item. Simple. Surprisingly decent at scale.
  Redis: allkeys-random.
  Use: very uniform access patterns where any item is equally likely to be needed.

REDIS EVICTION POLICIES:
  noeviction:     return error when memory full (default, often wrong choice)
  allkeys-lru:    evict any key LRU style (most common for cache)
  volatile-lru:   evict only keys with TTL, LRU style
  allkeys-lfu:    evict any key LFU style
  allkeys-random: evict any key randomly
  volatile-ttl:   evict key with shortest TTL first

  # Set in redis.conf:
  maxmemory 4gb
  maxmemory-policy allkeys-lru
```

---

## 4. Cache Invalidation Strategies

```
"There are only two hard things in CS: cache invalidation and naming things." — Phil Karlton

STRATEGY 1: TTL (Time-Based Expiry) — Simplest
  Cache item for N seconds. Let it expire naturally.
  
  Pros: Simple. No explicit invalidation code.
  Cons: Stale data for up to TTL seconds after source changes.
  
  Good for: data that changes on a schedule (weather every 5min, trending every 1hr).
  Bad for: data changed by user action (profile update should be immediate).

STRATEGY 2: Cache-Aside (Lazy Loading) — Most Common
  Read:  check cache → miss → read DB → write to cache → return.
  Write: write to DB → DELETE from cache (not update).
  Next read: cache miss → reads fresh from DB → re-caches.
  
  def get_user(user_id: int) -> dict:
      # 1. Check cache
      cached = redis.get(f"user:{user_id}")
      if cached:
          return json.loads(cached)  # cache hit
      
      # 2. Miss: query DB
      user = db.query_one("SELECT * FROM users WHERE id = %s", user_id)
      
      # 3. Populate cache
      redis.setex(f"user:{user_id}", 300, json.dumps(user))  # TTL: 5 min
      return user
  
  def update_user(user_id: int, data: dict):
      db.execute("UPDATE users SET ... WHERE id = %s", user_id)
      redis.delete(f"user:{user_id}")  # invalidate, not update
      # Next get_user will miss → re-populate from DB

  Why DELETE not UPDATE cache on write?
    If you UPDATE cache: race condition.
    Thread 1: writes to DB, about to update cache.
    Thread 2: reads DB (gets new value), updates cache.
    Thread 1: updates cache with OLD value. Cache is wrong.
    DELETE is atomic and safe.

STRATEGY 3: Write-Through — Cache Always Consistent
  Write: write to DB AND update cache simultaneously. Always in sync.
  
  Pros: Cache always has fresh data. No stale reads.
  Cons: Write penalty (2 writes). Cache stores data that may never be read.
  
  Use: read-heavy data that must always be fresh. Financial dashboards.

STRATEGY 4: Write-Behind (Write-Back) — Fastest Writes
  Write: write to cache only → immediately return to user.
  Background: async flush from cache to DB.
  
  Pros: Very fast writes (no DB wait).
  Cons: Data loss if cache crashes before flush to DB.
  
  Use: analytics counters, high-volume event tracking, rate limit counters.
       Data where occasional loss is acceptable.

STRATEGY 5: Read-Through — Cache as Primary Data Layer
  App always reads from cache. Cache handles DB read on miss (cache does it, not app).
  
  Pros: App code simpler (just read from cache, never DB directly).
  Cons: Cache library must support read-through. Cold start has no data.
  
  Use: Vitess, Amazon ElastiCache with read-through capability.

COMPARISON TABLE:
  Strategy        | Consistency | Write Speed | Complexity | Use Case
  ────────────────┼─────────────┼─────────────┼────────────┼──────────────────
  TTL             | Eventual    | Fast        | Low        | Time-sensitive data
  Cache-Aside     | Eventual    | Medium      | Low        | Most use cases ✓
  Write-Through   | Strong      | Slow        | Medium     | Always-fresh needed
  Write-Behind    | Eventual    | Very fast   | High       | High-write, loss-ok
```

---

## 5. Cache Problems at Scale

```
PROBLEM 1: CACHE STAMPEDE (Thundering Herd)
─────────────────────────────────────────────
Scenario: "trending_products" key expires (TTL up).
1000 simultaneous requests all miss.
→ 1000 concurrent DB queries for same data!
→ DB overwhelmed → slow → cascade failure.

Fix 1: Mutex Lock (best for most cases)
  On cache miss:
    1. Try to acquire lock: SET lock:trending_products 1 NX EX 30
    2. If lock acquired: fetch from DB → set cache → release lock.
    3. If lock NOT acquired: wait and retry (lock holder is fetching).
  
  # Python Redis mutex:
  import time
  
  def get_trending_with_lock():
      cached = redis.get("trending_products")
      if cached:
          return json.loads(cached)
      
      lock_acquired = redis.set("lock:trending", 1, nx=True, ex=30)
      if lock_acquired:
          try:
              products = db.query("SELECT * FROM products ORDER BY views DESC LIMIT 10")
              redis.setex("trending_products", 300, json.dumps(products))
              return products
          finally:
              redis.delete("lock:trending")
      else:
          # Another request is fetching. Wait and retry.
          time.sleep(0.1)
          return get_trending_with_lock()  # retry

Fix 2: Probabilistic Early Expiry (XFetch)
  Don't wait for TTL to expire. Randomly start refreshing BEFORE expiry.
  
  def xfetch(key, delta, beta=1.0):
      value, expiry = redis.get_with_ttl(key)
      remaining_ttl = expiry - time.now()
      if remaining_ttl - delta * beta * math.log(random.random()) <= 0:
          # Re-compute early (probabilistically)
          value = recompute(key)
          redis.setex(key, new_ttl, value)
      return value

Fix 3: Background Refresh
  Background job refreshes cache BEFORE TTL expires.
  Cache key has 5-min TTL. Job refreshes every 4 minutes.
  Users always get cached data; refresh is invisible.

PROBLEM 2: CACHE PENETRATION
─────────────────────────────
Requests for keys that DON'T EXIST in DB.
  GET /user/99999999 → cache miss → DB query → nothing found → not cached.
  Next request: same thing. Every request hits DB.
  Malicious actor: flood with fake user IDs → DDoS your DB.

Fix 1: Cache Negative Results
  If DB returns nothing: cache "NULL" with short TTL.
  redis.setex("user:99999999", 60, "NULL")
  Next request: hits cache → sees "NULL" → return 404. DB not hit.

Fix 2: Bloom Filter
  Probabilistic data structure. Space-efficient.
  "Does user 99999999 exist?" → Bloom filter says NO → don't even query DB.
  False positive rate: ~1% (might say "exists" for something that doesn't).
  False negative rate: 0% (never says "doesn't exist" for something that does).
  
  # Redis Bloom Filter (RedisBloom module):
  redis.bf().create("user_ids", 0.01, 1_000_000)  # 1% error rate, 1M items
  redis.bf().madd("user_ids", *all_user_ids)        # populate at startup
  
  def get_user(user_id):
      if not redis.bf().exists("user_ids", user_id):
          return None  # definitely doesn't exist
      # might exist → check cache → check DB

PROBLEM 3: CACHE AVALANCHE
────────────────────────────
Many keys expire simultaneously → sudden DB spike.
Scenario: You set TTL=300s for ALL product pages at 9:00 PM.
At 9:05 PM: all 10,000 product caches expire → 10,000 DB queries at once.

Fix: TTL Jitter
  Instead of fixed TTL, randomize it:
  ttl = 300 + random.randint(-30, 30)  # 270-330 seconds
  Expiries spread out → DB load spread out.

Fix: Stagger Cache Population
  When warming cache at startup: don't populate all at once.
  for i, product_id in enumerate(product_ids):
      populate_cache(product_id)
      if i % 100 == 0:
          time.sleep(0.1)  # throttle to avoid thundering herd at startup
```

---

## 6. Redis Data Structures for Caching Patterns

```
STRING — simple key-value:
  redis.set("user:123", json.dumps(user_data), ex=300)
  redis.get("user:123")
  Use: user profiles, session tokens, any JSON object.

HASH — field-value pairs:
  redis.hset("product:456", mapping={"name": "Laptop", "price": "999", "stock": "42"})
  redis.hget("product:456", "price")    # get one field
  redis.hmget("product:456", "name", "price")  # get multiple fields
  Use: objects where you only need some fields (avoid deserializing entire JSON).

SORTED SET — score-ordered set:
  # Leaderboard: user_id → score
  redis.zadd("leaderboard:weekly", {"user_1": 9500, "user_2": 8200, "user_3": 7800})
  redis.zrevrange("leaderboard:weekly", 0, 9, withscores=True)  # top 10
  redis.zrank("leaderboard:weekly", "user_2")  # user_2's rank
  Use: leaderboards, rate limiting (timestamp as score), feed timelines.

LIST — ordered list:
  redis.lpush("feed:user_123", "post_789", "post_456")  # prepend (newest first)
  redis.lrange("feed:user_123", 0, 19)                  # get latest 20
  redis.ltrim("feed:user_123", 0, 999)                  # keep only latest 1000
  Use: user feed (pre-computed), activity logs, recent searches.

SET — unique members:
  redis.sadd("online_users", "user_1", "user_2", "user_3")
  redis.sismember("online_users", "user_1")  # True/False
  redis.scard("online_users")                 # count
  Use: online users, deduplication, set operations (who follows both A and B).

HyperLogLog — approximate unique count:
  redis.pfadd("daily_unique_visitors", *visitor_ids)
  redis.pfcount("daily_unique_visitors")  # ~1% error, but uses only 12KB!
  Use: unique visitor counts, unique user counts per event. At 1B unique items:
       exact count = ~8GB. HyperLogLog = 12KB. Trade-off: 1% error.

GEO — geospatial:
  redis.geoadd("drivers", -73.9857, 40.7484, "driver_1")  # lng, lat, member
  redis.georadius("drivers", -73.99, 40.75, 5, "km", count=10, sort="ASC")
  Use: nearby drivers (Uber), nearby restaurants (Swiggy), geo-fencing.
```

---

## 7. Multi-Level Caching

```
LEVELS:
  L1: In-process cache (application memory, fastest, server-local)
  L2: Shared distributed cache (Redis, shared across all app servers)
  L3: DB / Source of truth

EXAMPLE (E-commerce product page):

  def get_product(product_id: int) -> dict:
      # L1: Check in-process LRU cache (< 0.1ms)
      product = local_cache.get(product_id)
      if product:
          return product
      
      # L2: Check Redis (< 1ms)
      cached = redis.get(f"product:{product_id}")
      if cached:
          product = json.loads(cached)
          local_cache.set(product_id, product, ttl=60)  # populate L1
          return product
      
      # L3: Query DB (50ms)
      product = db.query_one("SELECT * FROM products WHERE id = %s", product_id)
      redis.setex(f"product:{product_id}", 300, json.dumps(product))  # populate L2
      local_cache.set(product_id, product, ttl=60)                    # populate L1
      return product

L1 TTL shorter than L2 TTL:
  L1: 60 seconds (local, server-specific — we don't want indefinitely stale)
  L2: 300 seconds (shared — invalidation is explicit here)
  
  On product update:
    redis.delete(f"product:{product_id}")  # invalidate L2
    L1 expires naturally within 60 seconds (or send internal event to clear it)
```

---

## 8. Interview Questions

```
Q1: "How would you design a caching strategy for a news feed?"
A: Cache-Aside pattern. Key: "feed:{user_id}" → sorted list of post IDs.
   TTL: 10 minutes. Invalidation: add new post → invalidate cache for that user's followers.
   For celebrities: cache the celebrity's posts separately. Merge at read time.

Q2: "What is cache stampede and how do you prevent it?"
A: Many requests simultaneously miss the same key.
   Prevention: Redis mutex (SET NX), probabilistic early expiry, background refresh.

Q3: "When should you NOT use a cache?"
A: Financial transactions (must be consistent, not stale).
   Unique per-user data with low read frequency (cache miss > cache hit).
   Real-time data changing > 1/second (TTL would be too short to help).
   Writes more frequent than reads (cache always being invalidated).

Q4: "What's the difference between write-through and write-behind caching?"
A: Write-through: write DB + cache simultaneously. Consistent, slower writes.
   Write-behind: write cache only, flush to DB async. Fast writes, risk of data loss.

Q5: "How does a Bloom filter help with cache penetration?"
A: Bloom filter answers "definitely not in set" or "probably in set".
   Before any DB query: check Bloom filter. If "definitely no" → return 404, skip DB.
   False negative rate is 0% — safe to use as a guard.
   Memory: 1% error rate for 1M items needs only ~1.14 MB.
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

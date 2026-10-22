# CS01: Design a URL Shortener (TinyURL / bit.ly)
## Full HLD Case Study | MAANG Interview Ready

---

## STEP 1 — Requirements Clarification (say this in interview)

```
"Before I start, let me clarify the requirements."

FUNCTIONAL:
  1. Given a long URL → return a short URL (e.g., sho.rt/abc123)
  2. Given a short URL → redirect to the original long URL
  3. Custom alias: user can specify their own code (e.g., sho.rt/my-link)
  4. URL expiry: URLs can expire after N days (optional)
  5. User accounts: track who created which short URL (optional)

NON-FUNCTIONAL:
  - Scale: 100M URL shortenings/day, 10B redirects/day (100:1 read:write ratio)
  - Latency: redirect must be < 10ms p99 (user is waiting for the page)
  - Availability: 99.99% uptime (link rot is a bad user experience)
  - URLs must be unique (no two long URLs should have same short code)
  - Security: no way to predict/enumerate other people's URLs

OUT OF SCOPE:
  - Analytics dashboard (beyond basic click counting)
  - Browser extensions, QR codes, mobile apps
```

---

## STEP 2 — Back-of-Envelope Estimation

```
WRITE (URL Shortening):
  100M shortenings/day ÷ 86,400 = 1,157 writes/sec (avg)
  Peak (5×): 5,785 writes/sec

READ (Redirects):
  10B redirects/day ÷ 86,400 = 115,740 redirects/sec (avg)
  Peak (5×): 578,700 redirects/sec ← this is the bottleneck!

STORAGE:
  Per record:
    short_code:  7 bytes
    long_url:    500 bytes avg (URLs are long)
    user_id:     8 bytes
    created_at:  8 bytes
    expires_at:  8 bytes
    click_count: 8 bytes
    Total:       ~539 bytes ≈ 600 bytes

  Records per day: 100M
  5 years: 100M × 365 × 5 = 182.5 Billion records
  Storage: 182.5B × 600 bytes = 109.5 TB ≈ 110 TB (just data)
  With 3× replication: 330 TB

  Is sharding needed? 110 TB > 5 TB typical single DB limit → YES, shard.

SHORT CODE SPACE:
  Characters: [a-z, A-Z, 0-9] = 62
  7 chars: 62^7 = 3.5 trillion unique codes
  At 100M/day: 3.5T ÷ 100M = 35,000 days ≈ 95 years before exhaustion
  → 7-character base62 code is SUFFICIENT.

CACHE:
  80% of clicks on top 20% of URLs (Pareto principle).
  Cache those 20%: 20M URLs × 600B = 12 GB — fits in Redis (16 GB instance).
  Cache hit rate target: 80%.
  DB reads: 578,700 × 20% = ~115,000 DB reads/sec → read replicas needed.
```

---

## STEP 3 — High-Level Architecture

```
WRITE FLOW:
  User                  →   [API Gateway]   →   [URL Shortener Service]
  POST /shorten                                         │
  {long_url: "..."}                             [ID Generator]
                                                (Snowflake ID → base62)
                                                         │
                                                [PostgreSQL (Sharded)]
                                                 INSERT (short_code, long_url, ...)
                                                         │
                                                [Redis Cache]
                                                 SET short:abc123 → long_url

READ FLOW:
  User                   →   [API Gateway]   →   [Redirect Service]
  GET /abc123                                           │
                                              1. Redis.get("short:abc123")
                                              2. HIT: return 302 to long_url
                                              3. MISS: query PostgreSQL shard
                                              4. Set in Redis (TTL 24h)
                                              5. Return 302

ARCHITECTURE DIAGRAM:

  ┌────────────────────────────────────────────────────────────┐
  │                     CLIENTS (Browsers / Apps)              │
  └───────────────────────┬────────────────────┬───────────────┘
                          │                    │
               POST /shorten              GET /{code}
                          │                    │
  ┌───────────────────────▼────────────────────▼───────────────┐
  │           API GATEWAY (rate limiting, auth, SSL)            │
  └───────────────────────┬────────────────────┬───────────────┘
                          │                    │
         ┌────────────────▼──────┐    ┌────────▼──────────────┐
         │  URL Shortener Service│    │  Redirect Service      │
         │  - validate input     │    │  - stateless, many     │
         │  - generate short code│    │    instances           │
         │  - store in DB+cache  │    │  - 578K req/sec        │
         └────────────────┬──────┘    └────────┬──────────────┘
                          │                    │
  ┌───────────────────────▼────────────────────▼───────────────┐
  │              Redis Cluster (Cache Layer)                     │
  │    key: "short:{code}" → {long_url, expires_at}             │
  │    TTL: 24h.    Hit rate: 80%.    Size: 12 GB.             │
  └─────────────────────────────┬──────────────────────────────┘
                                │ (cache miss)
  ┌─────────────────────────────▼──────────────────────────────┐
  │              PostgreSQL Cluster (Sharded)                    │
  │    Shard by: hash(short_code) % 10                          │
  │    10 shards × (primary + 2 replicas each)                  │
  │    Total: 30 PostgreSQL instances                            │
  └────────────────────────────────────────────────────────────┘
```

---

## STEP 4 — Deep-Dive: Short Code Generation

```
THE PROBLEM: Generate a globally unique 7-character code at 5,785/sec.
Must be: unique, short, not sequential (prevent enumeration).

APPROACH A: Hash-based (MD5/SHA256)
  hash = md5(long_url)[:7]
  
  PROBLEMS:
    1. Collision: two different long_urls → same 7 chars. Need to handle.
    2. Same long URL from different users → same code. Is that desired?
    3. Case sensitivity matters (hash includes uppercase).
  
  IF different users can get different short codes for same long URL:
    Add user_id or random salt: hash = md5(long_url + user_id + random)[:7]
  
  Collision handling: check DB → if exists → add +1 to salt → rehash → repeat.

APPROACH B: Snowflake ID → Base62 (RECOMMENDED)
  
  Step 1: Generate globally unique 64-bit integer (Snowflake ID).
  
  Snowflake structure:
    ┌─────────────────────────────────────────────────────┐
    │ 41 bits timestamp │ 10 bits worker_id │ 12 bits seq │
    └─────────────────────────────────────────────────────┘
    
    - timestamp: milliseconds since epoch. ~70 year range.
    - worker_id: each ID service instance has unique ID (1024 possible).
    - seq: 4096 IDs per millisecond per worker (no coordination needed).
    
    Globally unique without central coordination.
  
  Step 2: Encode 64-bit integer as base62.
  
  def encode_base62(num: int) -> str:
      CHARS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
      result = []
      while num > 0:
          result.append(CHARS[num % 62])
          num //= 62
      return ''.join(reversed(result)) or '0'
  
  encode_base62(100_000_000)  → "6LAze"   (5 chars)
  encode_base62(1_000_000_000) → "15FTGf" (6 chars)
  encode_base62(62**7 - 1)     → "zzzzzzz" (7 chars, maximum)
  
  Current Snowflake ID (~2T range) encodes to ~11 base62 chars.
  Fix: use only lower 40 bits → encodes to 7 chars.
  Or: use sequential DB ID (auto-increment per shard, prefix with shard ID).

APPROACH C: Pre-generated Code Pool
  Background job generates 10M random 7-char codes, stores in "available_codes" table.
  
  On shorten request:
    1. Pop one code: SELECT code FROM available_codes LIMIT 1 FOR UPDATE SKIP LOCKED
    2. DELETE from available_codes WHERE code = ?
    3. INSERT into urls table with this code.
  
  PROS: No collision possible. Simple at request time.
  CONS: Background job must keep pool replenished. Extra table.

FINAL ANSWER FOR INTERVIEW:
  "I'd use Snowflake IDs encoded in base62.
   Snowflake gives globally unique IDs without coordination.
   Base62 encoding produces short, URL-safe strings.
   No collision handling needed."

COLLISION HANDLING (if hash-based):
  def generate_short_code(long_url: str, user_id: int) -> str:
      for attempt in range(5):
          code = base62(md5(f"{long_url}{user_id}{attempt}"))[:7]
          if not db.exists(f"SELECT 1 FROM urls WHERE short_code = ?", code):
              return code
      raise Exception("Failed to generate unique code after 5 attempts")
```

---

## STEP 5 — Deep-Dive: Redirect Service

```
THE HOTTEST PATH: 578,700 redirects/sec at peak. Must be < 10ms.

FLOW:
  def redirect(short_code: str) -> str:
      # 1. Redis lookup (< 1ms)
      cached = redis.get(f"short:{short_code}")
      if cached:
          data = json.loads(cached)
          if data.get("expires_at") and data["expires_at"] < now():
              return 410  # Gone
          return 302, data["long_url"]
      
      # 2. DB lookup (2-5ms, only on cache miss)
      result = db.query_one(
          "SELECT long_url, expires_at FROM urls WHERE short_code = ?",
          short_code
      )
      if not result:
          return 404  # Short code doesn't exist
      
      # 3. Cache it
      redis.setex(f"short:{short_code}", 86400, json.dumps(result))
      
      # 4. Async: increment click count (don't block redirect)
      kafka.publish("click-events", {"short_code": short_code, "timestamp": now()})
      
      return 302, result["long_url"]

301 vs 302 REDIRECT:
  301 Permanent: Browser caches redirect. Next time: goes directly to long URL.
    → Less load on our servers.
    → Analytics broken (browser doesn't ask us again).
    Used by: TinyURL (cheap, minimal analytics).
  
  302 Temporary: Every redirect hits our server.
    → We count every click.
    → More server load.
    Used by: Bit.ly (they sell analytics!).

CLICK COUNTING (async):
  Don't increment click_count in DB synchronously on every redirect.
  578K redirects/sec → 578K writes/sec → DB overwhelmed.
  
  Solution: Kafka + batch aggregation.
    Redirect: publish event to Kafka ("short_code: abc123, timestamp: ...")
    Analytics worker: reads Kafka, aggregates counts every minute.
    Batch UPDATE: UPDATE urls SET click_count = click_count + {batch_count}
    Result: DB gets 578K/min writes instead of 578K/sec.

REDIS CACHE DESIGN:
  Key: "short:{short_code}"
  Value: {"long_url": "...", "expires_at": 1726458600, "owner_id": 123}
  TTL: 24 hours
  
  Why 24h TTL:
    Popular links stay in cache.
    Old, never-accessed links expire naturally.
    Memory efficient.
  
  Cache invalidation: when URL is deleted → redis.delete("short:{short_code}")
```

---

## STEP 6 — Database Schema

```sql
-- Sharded by hash(short_code) % 10
CREATE TABLE urls (
    short_code   VARCHAR(10)  PRIMARY KEY,
    long_url     TEXT         NOT NULL,
    owner_id     BIGINT,                        -- null for anonymous
    created_at   TIMESTAMP    DEFAULT NOW(),
    expires_at   TIMESTAMP,                     -- null = never expires
    is_active    BOOLEAN      DEFAULT TRUE,
    click_count  BIGINT       DEFAULT 0
);

CREATE INDEX idx_urls_owner ON urls(owner_id);  -- for "my links" dashboard
CREATE INDEX idx_urls_expires ON urls(expires_at) WHERE expires_at IS NOT NULL;

-- Expiry cleanup job:
-- DELETE FROM urls WHERE expires_at < NOW() - INTERVAL '1 day';

-- Optional: custom aliases stored with same schema
-- custom_alias IS NULL → generated code; NOT NULL → user-provided.
CREATE UNIQUE INDEX idx_urls_short_code ON urls(short_code);
```

---

## STEP 7 — Bottlenecks and Solutions

```
BOTTLENECK 1: Redirect service at 578K req/sec
  Current: Redis handles 1M ops/sec. We're at 578K → Redis is fine.
  BUT: Cache miss rate 20% = 115,600 DB reads/sec.
  Single PostgreSQL primary handles 50K reads/sec max → PROBLEM.
  
  Fix: Add 3 read replicas per shard. 
  Each shard: primary + 3 replicas → 200K reads/sec per shard.
  10 shards: 2M DB reads/sec capacity vs 115K demand. Safe.

BOTTLENECK 2: Redis is a SPOF
  Single Redis crashes → 100% cache miss → all traffic hits DB → cascade failure.
  
  Fix: Redis Sentinel (HA) or Redis Cluster.
  Redis Cluster: 6+ nodes (3 primary + 3 replicas). Auto failover < 1 second.

BOTTLENECK 3: Click count updates
  578K clicks/sec. Can't UPDATE db 578K/sec.
  
  Fix: Kafka + batch writer (as described above).
  Or: Redis INCR for fast atomic counter, sync to DB every minute.
  redis.incr("clicks:abc123")  # O(1), atomic, fast
  Periodic job: read Redis counters → batch UPDATE PostgreSQL.

BOTTLENECK 4: API Gateway is SPOF
  Fix: Multiple API Gateway instances behind AWS ALB.
  ALB: managed, auto-scales, 99.99% SLA. Not a SPOF.

BOTTLENECK 5: ID generation at 5,785/sec
  Snowflake ID generation: each app server is a Snowflake worker.
  5,785/sec << 4096/ms capacity per worker → no bottleneck.
```

---

## STEP 8 — Trade-offs Made

```
TRADE-OFF 1: Snowflake ID vs random code
  Snowflake: sequential → predictable patterns. Security concern?
  Random: no collision guarantee, collision checking needed.
  Decision: XOR/shuffle Snowflake bits before base62 encoding → obfuscates sequence.

TRADE-OFF 2: 302 vs 301 redirect
  302: every click logged (analytics), more server load.
  301: cached by browser, less load, no analytics.
  Decision: 302 for analytics visibility. Load is manageable with Redis.

TRADE-OFF 3: TTL of 24h vs event-driven invalidation
  24h TTL: simple. Stale if URL deleted mid-day (user sees it for up to 24h).
  Event-driven: delete from Redis when URL deleted. No staleness. More complex.
  Decision: 24h TTL. URL deletions are rare. Stale redirect for < 24h is acceptable.

TRADE-OFF 4: Shard by short_code vs by user_id
  Short_code: redirects always go to one shard (optimal for reads).
  User_id: "show my URLs" query is one shard (optimal for user management).
  Decision: shard by short_code (redirects are 100× more frequent than user queries).
  For "show my URLs": maintain a separate table or use Elasticsearch.
```

---

## STEP 9 — Follow-Up Questions

```
Q: "How would you handle custom aliases?"
A: Store custom_alias in same table. Add UNIQUE constraint on short_code.
   When user provides alias: check if exists → if taken, return 409 Conflict.
   Custom aliases have same code length limit (max 20 chars for UX).

Q: "How would you implement URL expiry?"
A: Store expires_at timestamp in DB and cache.
   Redirect service: check if expires_at < now() → return 410 Gone.
   Background cleanup job: daily cron → DELETE WHERE expires_at < NOW().

Q: "How would you add click analytics (by country, device)?"
A: Kafka click event: {short_code, timestamp, ip_address, user_agent, referer}.
   GeoIP lookup → country from IP.
   User-agent parsing → device/browser.
   Store in ClickHouse (columnar, fast aggregation) or BigQuery.
   Dashboard: GROUP BY country, device → click counts per URL.

Q: "What if a URL has 10B clicks (viral)?"
A: That URL's Redis key is a "hot key."
   Multiple Redis reads per second for same key.
   Fix: local in-process cache at each Redirect Service instance (LRU, 10 second TTL).
   Viral URL served from RAM of each server. Redis not even consulted.

Q: "How do you prevent abuse (malicious URLs)?"
A: Google Safe Browsing API: check URL before shortening → reject if phishing/malware.
   Rate limiting per user/IP for shortening.
   Async re-scan of existing URLs daily.
   Report mechanism: user reports bad URL → flagged → manual review.
```

---

## STEP 10 — Extended Deep-Dive: API Rate Limiting

```
PROBLEM:
  A competitor bot creates 50M short URLs/hour to exhaust our short code space.
  Or: a DDoS attack creates 100K redirect requests/sec to one short code.
  Rate limiting is CRITICAL for a public URL shortener.

RATE LIMITING ALGORITHM: Token Bucket (recommended for this use case)

  CONCEPT:
    Each user/IP has a "bucket" with capacity C tokens.
    Each request consumes 1 token.
    Tokens refill at rate R per second.
    If bucket empty: request rejected (429 Too Many Requests).
  
  Our limits:
    Anonymous users: 10 shortens/hour, 100 redirects/hour
    Registered users: 1000 shortens/day, unlimited redirects
    Premium accounts: 100K shortens/day, unlimited redirects
  
  IMPLEMENTATION WITH REDIS:
  
  Using the "Token Bucket" with Redis + Lua script (atomic):
  
  local key = KEYS[1]          -- e.g., "ratelimit:shorten:{ip_or_user_id}"
  local capacity = tonumber(ARGV[1])     -- max tokens
  local refill_rate = tonumber(ARGV[2]) -- tokens added per second
  local now = tonumber(ARGV[3])         -- current timestamp (float seconds)
  local requested = tonumber(ARGV[4])   -- tokens needed (usually 1)
  
  local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
  local tokens = tonumber(bucket[1]) or capacity
  local last_refill = tonumber(bucket[2]) or now
  
  -- Add tokens for time elapsed since last call
  local elapsed = now - last_refill
  tokens = math.min(capacity, tokens + elapsed * refill_rate)
  
  if tokens >= requested then
      -- Allow: consume token
      redis.call('HMSET', key, 'tokens', tokens - requested, 'last_refill', now)
      redis.call('EXPIRE', key, 86400)   -- cleanup after 1 day of inactivity
      return 1  -- allowed
  else
      -- Deny: not enough tokens
      redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
      return 0  -- rate limited
  end
  
  WHY LUA SCRIPT?
    Redis is single-threaded, but HMGET + computation + HMSET is NOT atomic if done in app.
    Two concurrent requests could both read same token count → both consume.
    Lua scripts execute atomically in Redis (no interleaving). Race condition impossible.

  SLIDING WINDOW LOG (alternative — more precise):
    Store timestamps of each request in Redis ZSET.
    On each request: ZADD + ZREMRANGEBYSCORE (remove old entries) + ZCOUNT.
    If ZCOUNT > limit → reject.
    Pros: perfectly accurate (no approximation).
    Cons: O(N) storage per user. High memory for users with many requests.
    
    Token bucket is O(1) storage per user. Preferred at scale.

RATE LIMIT RESPONSE HEADERS:
  X-RateLimit-Limit: 1000           ← max per window
  X-RateLimit-Remaining: 347        ← left this window
  X-RateLimit-Reset: 1726459200     ← when window resets (Unix timestamp)
  Retry-After: 3600                  ← seconds until allowed to retry (if 429)
  
  These headers allow API clients to self-throttle before being rate limited.
```

---

## STEP 11 — Extended Deep-Dive: Analytics Deep-Dive

```
CLICK ANALYTICS AT SCALE:
  578,700 redirects/sec at peak → 578,700 click events/sec.
  Each event: {short_code, timestamp, ip, user_agent, referer, country}.
  Per event: ~200 bytes. 578,700 × 200B = 115 MB/sec ingestion rate.
  
  Cannot write directly to analytics DB: too slow.
  Solution: Kafka → ClickHouse pipeline.

FULL ANALYTICS ARCHITECTURE:

  [Redirect Service]
      │ publish event (async, < 1ms)
      ▼
  [Kafka Cluster]
  Topic: "click-events"
  Partitioned by: short_code (related events on same partition → ordering guaranteed)
  Retention: 7 days (can replay if analytics processing fails)
      │
      │ consume (batch)
      ▼
  [ClickHouse Cluster]  ← columnar OLAP database
  Table: clicks
  
  CREATE TABLE clicks (
      short_code  LowCardinality(String),
      clicked_at  DateTime,
      ip_hash     FixedString(32),  -- hash of IP (privacy: no raw IP stored)
      country     LowCardinality(String),   -- GeoIP lookup result
      city        LowCardinality(String),
      device      Enum8('desktop'=1, 'mobile'=2, 'tablet'=3, 'bot'=4),
      browser     LowCardinality(String),   -- 'Chrome', 'Safari', etc.
      os          LowCardinality(String),   -- 'iOS', 'Android', 'Windows'
      referer     String,                  -- 'twitter.com', 'direct', etc.
      session_id  FixedString(16)          -- anonymous session (cookie)
  ) ENGINE = MergeTree()
  PARTITION BY toYYYYMM(clicked_at)  -- partition by month for easy archival
  ORDER BY (short_code, clicked_at)  -- sorted for fast range queries per URL
  TTL clicked_at + INTERVAL 2 YEAR   -- auto-delete data older than 2 years;

ANALYTICS QUERIES (all < 1s on ClickHouse):

  -- Total clicks for a URL in last 30 days
  SELECT count() FROM clicks
  WHERE short_code = 'abc123'
  AND clicked_at >= now() - INTERVAL 30 DAY;

  -- Clicks by country (pie chart)
  SELECT country, count() as clicks
  FROM clicks
  WHERE short_code = 'abc123'
  AND clicked_at >= now() - INTERVAL 7 DAY
  GROUP BY country
  ORDER BY clicks DESC
  LIMIT 10;

  -- Clicks by hour (line chart)
  SELECT toStartOfHour(clicked_at) as hour, count()
  FROM clicks
  WHERE short_code = 'abc123'
  AND clicked_at >= now() - INTERVAL 24 HOUR
  GROUP BY hour
  ORDER BY hour;

  -- Unique visitors (deduplicated by ip_hash per day)
  SELECT countDistinct(ip_hash) as unique_visitors
  FROM clicks
  WHERE short_code = 'abc123'
  AND clicked_at >= now() - INTERVAL 7 DAY;

IP GEOLOCATION:
  GeoIP2 Lite database (MaxMind): IP → country, city, lat/lng.
  Loaded in-memory in Redirect Service (~70 MB).
  Lookup: O(log N) binary search in IP range table.
  Latency: < 0.1ms. Zero external API call needed.
  Update: database updated weekly (IP allocations change).
  
  Privacy: never store raw IP. Store: MD5(IP + daily_salt).
  Same IP = same hash within a day → dedup works.
  Different days = different hash → can't track user across days.

USER AGENT PARSING:
  User-Agent: "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)..."
  Libraries: ua-parser (Python), ua-parser-js (Node.js).
  Extracts: device_type, OS, OS_version, browser, browser_version.
  Results cached in Redis: "ua_cache:{hash(user_agent)}" → parsed result.
  Why cache? Same browser sends identical User-Agent → parse once, cache for 24h.
```

---

## STEP 12 — Extended Deep-Dive: Multi-Region Deployment

```
PROBLEM: Single datacenter has ~100ms latency to users in India from US-East-1.
         Redirect must be < 10ms p99. Single region cannot achieve this globally.

MULTI-REGION ARCHITECTURE:

  ┌──────────────────────────────────────────────────────────────────────────────┐
  │  DNS Layer: AWS Route 53 (Latency-based routing)                             │
  │  User in India → Route53 → us-east-1? or ap-south-1? → nearest!             │
  └──────────────────┬───────────────────────────────────────────────────────────┘
                     │ routes to nearest region
         ┌───────────┴───────────┐
         │                       │
  ┌──────▼──────────┐    ┌───────▼───────────┐
  │  US-East-1      │    │  AP-South-1       │
  │  (US/EU users)  │    │  (India users)    │
  │  Redirect + DB  │    │  Redirect + Cache │
  └─────────────────┘    └───────────────────┘
         │  (replication)       │
         └──────────────────────┘

  WRITE (URL shortening): always to primary region (US-East-1 if that's primary).
  Why: writes must be consistent. Two-phase commit across regions is too slow.
  Solution: route ALL write requests to primary region (add ~100ms for Indian writers, acceptable).
  Writes are rare (1,157/sec) vs reads (578K/sec). Worth the latency trade-off.

  READ (redirects): served from nearest region.
  Redis Cluster in each region: populated either:
    Option A: write-through: when URL created in primary → replicate to all regional Redis caches.
    Option B: lazy: regional Redis is empty on first request → reads from primary DB → populates.
  
  Option A: lower read latency (pre-populated). More complex. Chosen if redirect SLA is tight.
  Option B: simpler. First redirect per region is slightly slower. Fine for most use cases.

  DATABASE REPLICATION:
    PostgreSQL primary: US-East-1.
    Read replicas: AP-South-1, EU-West-1.
    Replication lag: 10-50ms (async streaming replication).
    Reads: can hit nearest regional read replica.
    Writes: always to primary.
    Consistency: eventual (redirect service reads replica → might be 50ms behind primary).
    Is 50ms stale read acceptable? YES — a URL that was just shortened takes 50ms extra to redirect globally. Not user-visible.

EDGE CACHING (CDN for redirect service):
  Can we put 301/302 redirects in a CDN? Technically YES for 301 (permanent).
  
  301 redirect at CDN layer:
    User's first request: hits CDN PoP → CDN misses → asks Redirect Service → 301.
    CDN caches the 301 response.
    User's second request to same URL: CDN responds directly. Redirect Service NOT contacted.
    Latency: < 5ms (CDN PoP is physically close to user).
  
  Trade-off: Can't invalidate 301 cached at CDN if URL is deleted (CDN cached indefinitely).
  Fix: use 301 with Cache-Control: max-age=86400 (1 day max CDN cache).
  Or: use 302 (not cacheable by default) + Cache-Control: no-store.
  Bit.ly's approach: 302 (never CDN-cached). They want all traffic for analytics.
  TinyURL's approach: 301 (CDN-cacheable). They optimize for minimum latency.
```

---

## STEP 13 — System Evolution (How to Present Scaling Journey)

```
"In interviews, it's impressive to discuss how the system evolves as it grows."

STAGE 1: MVP (0-10K users)
  Single server: Flask/Express + PostgreSQL on one EC2.
  No Redis. No Kafka. Simple HTTP redirect.
  Short code: MD5 hash.
  10K users → 100K URLs → 10K redirects/day. Single server handles this easily.
  
  Latency: ~50ms (DB query on every redirect).
  Availability: single point of failure. Outage = downtime.
  Cost: ~$50/month.

STAGE 2: Growth (10K-1M users)
  Add Redis cache (ElastiCache): cache reduces DB load by 80%.
  Add read replicas to PostgreSQL: reads scale independently.
  Move to Snowflake IDs (replace MD5 hash).
  Add basic rate limiting (Redis token bucket).
  
  Latency: < 5ms for cached URLs (80% of traffic).
  Availability: Redis + DB replica provides failover.
  Cost: ~$500/month.

STAGE 3: Scale (1M-100M users)
  Shard PostgreSQL (10 shards × primary + 2 replicas = 30 instances).
  Add Kafka for async click analytics.
  Add ClickHouse for analytics queries.
  Multi-region deployment (US + EU).
  Add Kubernetes for service orchestration.
  API Gateway with rate limiting.
  
  Throughput: 578K redirects/sec.
  Latency: < 10ms p99 globally.
  Cost: ~$50K/month.

STAGE 4: Hyper-scale (100M+ users / bit.ly/TinyURL scale)
  Custom CDN (or Cloudflare) for redirect caching.
  Global DB replication to 5+ regions.
  ML-based spam detection for URL shortening requests.
  SLA: 99.99% uptime.
  Cost: $500K+/month.
```


---

## DEEP-DIVE IMPROVEMENT: Short Code Generation — Mathematical Guarantees

```
PROBABILITY OF COLLISION (the math interviewers love):
  Total space: 62^7 = 3,521,614,606,208 (3.5 trillion unique codes).
  At our scale: 500M URLs stored.
  
  BIRTHDAY PROBLEM — probability of at least ONE collision among N codes:
    P(collision) ≈ 1 - e^(-N^2 / (2 * M))
    Where: N = number of codes generated, M = total code space.
    
    N = 500M = 5×10^8, M = 3.5×10^12
    P ≈ 1 - e^(-(5×10^8)^2 / (2 × 3.5×10^12))
    P ≈ 1 - e^(-25×10^16 / 7×10^12)
    P ≈ 1 - e^(-35714)
    P ≈ 1 (almost certain collision after 500M codes!)
    
  WAIT — that can't be right. Let me recalculate at what N collisions become likely:
    P(collision) = 0.5 when N ≈ sqrt(2 × M × ln(2))
    N ≈ sqrt(2 × 3.5×10^12 × 0.693)
    N ≈ sqrt(4.85×10^12)
    N ≈ 2.2 million
    
  At only 2.2M URLs, we have 50% collision probability!
  This means with MD5 and no collision check, we'd have rampant collisions.
  
  THE FIX: Collision check + retry (as implemented in code):
    On collision: increment 'attempt' counter → different hash input → different code.
    Retry 5 times. With 500M/3.5T = 14% occupancy, probability all 5 attempts collide:
    (0.14)^5 = 0.0000054% → essentially impossible.
  
  BETTER FIX: Snowflake ID → counter-based (no hash, no collision possible)
    Worker ID (10 bits) + Timestamp (41 bits) + Sequence (12 bits) = 63 bits → Base62 encode.
    Sequence: increment per millisecond per worker (max 4096 codes/ms/worker).
    At 1,157 writes/sec peak: one worker can handle it (1.157 codes/ms << 4096/ms).
    Collision probability: ZERO (deterministic counter, never repeats).

WHY BASE62 OVER BASE64:
  Base64 uses: A-Z, a-z, 0-9, +, /  (or URL-safe: -, _)
  Base62 uses: A-Z, a-z, 0-9 (no special chars)
  
  URL safety: "https://sho.rt/a+b" → browser might URL-encode '+' → "https://sho.rt/a%2Bb"
  Base62 avoids this. Every character is a URL-safe alphanumeric.
  
  Code space sacrifice: 62 vs 64 chars → 62^7 vs 64^7 = 3.5T vs 4.4T codes.
  Sacrifice: 0.9T codes (21% less space). Absolutely worth URL-safety.

HASH FUNCTION CHOICE (MD5 vs SHA-256 vs MurmurHash):
  MD5:
    Output: 128 bits (32 hex chars)
    Speed: very fast (~1 ns/hash in hardware)
    Cryptographic: NO (broken for security, but fine for URL generation)
    Why for URL shortening: we need speed and distribution, not security. MD5 is perfect.
  
  SHA-256:
    Output: 256 bits
    Speed: 3-5× slower than MD5
    Cryptographic: YES
    Not needed here: we don't need security guarantees for short code generation.
  
  MurmurHash3:
    Output: 32 or 128 bits
    Speed: fastest (2× faster than MD5, no cryptographic overhead)
    Distribution: excellent (very uniform → low collision in practice)
    BEST CHOICE for URL shortening in production (non-cryptographic hash is fine here).
    
    Python: mmh3 library. Java: com.google.common.hash.Hashing.murmur3_128().

CUSTOM ALIAS DEEP-DIVE:
  Allowed characters: a-z, A-Z, 0-9, hyphen, underscore (URL-safe).
  Max length: 20 chars (for readability in tweets/messages).
  Min length: 3 chars (to prevent single-char aliasing abuse).
  Reserved aliases: "api", "static", "admin", "health", "metrics" → blocked.
  
  Validation regex: ^[a-zA-Z0-9_-]{3,20}$
  
  Race condition: two users submit same alias simultaneously.
    Both call: repo.exists(alias) → both see False → both proceed → conflict.
    Fix: DB UNIQUE constraint on short_code column.
    One INSERT succeeds. Other gets IntegrityError (or equivalent).
    Catch IntegrityError → return 409 Conflict to user.
    This is "optimistic locking" — assume no conflict, handle error if it happens.
    Faster than pessimistic locking (SELECT FOR UPDATE) for low-contention scenarios.
```

---

## DEEP-DIVE IMPROVEMENT: Cache Architecture — Multi-Layer Caching

```
CACHE HIERARCHY (like CPU cache — L1, L2, L3):

  L1 — In-Process Cache (local JVM/Python process memory):
    Every Redirect Service pod has local LRU cache (10,000 entries, 500 MB).
    Hit: < 0.1ms (RAM access within same process, no network).
    Miss: go to L2.
    TTL: 10 seconds (short, to prevent stale data accumulating).
    Eviction: LRU (least recently used).
    
    WHY SO SHORT TTL? 
    Redirect service has 50 pods. 50 separate local caches.
    If URL is deleted: must update 50 caches. Impossible to notify all.
    Instead: 10s TTL means stale entries auto-expire quickly.
    User deletes URL → may still redirect for up to 10 seconds. Acceptable trade-off.
  
  L2 — Redis Cluster (shared across all pods):
    Single shared cache. All 50 pods read/write same Redis.
    Hit: 1-2ms (network + Redis processing).
    Miss: go to L3 (database).
    TTL: 24 hours (or same as URL TTL if URL has expiry).
    Eviction: allkeys-lru (evict least-recently-used keys when memory full).
    Memory: 50GB Redis cluster (handles ~25M cached URLs at 2KB each).
    
    REDIS DATA STRUCTURE:
    Key: "url:abc123"
    Value: "https://www.google.com/..." (just the string, not the full UrlEntry)
    Why just the URL string? Redirect only needs destination. Saves memory.
    For stats/metadata: separate key "meta:abc123" → JSON with click_count, owner, etc.
    
    Hot key problem: viral URL "sho.rt/election" gets 100K reads/sec.
    Single Redis key → single Redis node → bottleneck.
    Fix: key replication. Store same URL at:
      "url:abc123:0", "url:abc123:1", ..., "url:abc123:9" (10 copies)
    Read: randomly pick one of 10 → load spread across 10 Redis nodes.
    Write: write to all 10 (on URL creation or cache warm).
    Read: pick random → load 10× more distributed.
  
  L3 — PostgreSQL (sharded):
    Source of truth. Always correct.
    Hit: 5-20ms (network + DB query + disk/SSD I/O).
    Always hits (unless URL doesn't exist → return 404).

CACHE INVALIDATION STRATEGY:
  The "two hardest things in CS": naming things, cache invalidation, off-by-one errors.
  
  Case 1: URL is DELETED.
    Delete from L3 (DB). ✓
    Delete from L2 (Redis): redis.delete("url:abc123"). ✓
    Delete from L1 (each pod's local cache): CANNOT notify 50 pods efficiently.
    Fix: accept up to 10s stale serving from L1. After 10s TTL, auto-evicts.
    
    Alternative (if strict): pub/sub invalidation.
      Redis Pub/Sub: publish "invalidate:abc123" to channel.
      All pods subscribe to this channel.
      On message: each pod deletes from local cache.
      Pro: immediate invalidation. Con: pub/sub adds complexity and latency.
  
  Case 2: URL is UPDATED (long URL changed for same short code).
    Same as deletion: delete L2 key + accept L1 stale for 10s.
    In practice: URL updates are rare. Most users just create new short URLs.
  
  Case 3: URL EXPIRES.
    DB: expires_at timestamp stored. RedirectService checks on DB hit.
    Redis: set TTL on Redis key = URL's expires_at - now.
      Redis automatically evicts when TTL fires.
      No manual invalidation needed. ✓
    L1: same URL cached for 10s max. May serve expired URL briefly. Acceptable.

CACHE WARM-UP ON SERVER RESTART:
  Pod restarts. L1 cache is empty. First N requests all miss L1 → hit L2.
  Redis: 25M cached URLs. Pod comes online → cold start = more L2 hits. Fine.
  
  Optional optimization: pre-warm L1 on startup.
    On pod start: GET top 1000 URLs from Redis ("most-accessed" sorted set).
    Load into L1. Pod starts "warm".
    Impact: 1000 pre-warmed entries → 10% of typical cache hits pre-seeded.
    Trade-off: startup time +50ms vs cold-start Redis load.
```

---

## DEEP-DIVE IMPROVEMENT: Database Sharding Deep-Dive

```
SHARDING STRATEGY — RANGE vs HASH vs DIRECTORY-BASED:

RANGE-BASED SHARDING:
  Shard 1: short_codes A* to F*
  Shard 2: short_codes G* to M*
  Shard 3: short_codes N* to S*
  Shard 4: short_codes T* to Z*
  
  PROS: range queries are efficient (all 'A*' codes on one shard).
  CONS: "hot spots." If 80% of codes are generated starting with 'a' (hash distribution):
        Shard 1 gets 80% of traffic. Shard 4 gets nothing. Unbalanced!
  VERDICT: BAD for URL shortener (random code distribution → random load, but hard to predict).

HASH-BASED SHARDING (what we use):
  shard_id = hash(short_code) % N_SHARDS
  
  PROS: perfectly uniform distribution (hash function is uniform by design).
  CONS: range queries impossible ("all URLs expiring today" spans ALL shards).
  VERDICT: PERFECT for URL shortener. Our only query is point lookup by short_code.
  
  Implementation:
    def get_shard(short_code: str) -> int:
        # Use a stable hash (not Python's hash() which changes per process restart)
        return int(hashlib.md5(short_code.encode()).hexdigest(), 16) % N_SHARDS
    
    N_SHARDS = 10 (start here; can expand to 20, 40, 80 as needed)
    
  RESHARDING PROBLEM:
    Current: 10 shards. Growing. Need 20 shards.
    hash(code) % 10 → hash(code) % 20: DIFFERENT shard for most keys!
    If you just resize: 90% of keys are on wrong shard → massive data migration.
    
    FIX: Consistent Hashing Ring.
      Virtual nodes: each physical shard owns multiple "slots" on a ring (0-360 degrees).
      Adding a new shard: only the adjacent slots "move" to the new shard.
      Keys moved: 1/N fraction (not 90%). Minimal disruption.
      
      Production: add one shard at a time. Run double-write (old + new shards).
      After data migration completes: switch reads to new shard. Remove old.

DIRECTORY-BASED SHARDING (alternative):
  Dedicated lookup service: "Which shard does short_code X live on?"
  Lookup service returns shard_id → route request to that shard.
  
  PROS: completely flexible. Can move any key to any shard. Hotspot mitigation.
  CONS: lookup service is a single point of failure. Extra network hop.
  Mitigation: cache directory lookups. Directory service is read-heavy → easy to scale.
  Used by: Pinterest, Airbnb. More complex but handles uneven data much better.

CROSS-SHARD ANALYTICS:
  Problem: "how many total URLs created today?" spans all 10 shards.
  
  Option A: scatter-gather. Query all 10 shards, sum results.
    SELECT COUNT(*) FROM urls WHERE created_at > NOW() - INTERVAL 1 DAY;
    Run on all 10 shards. Sum the 10 counts. Return total.
    Latency: max(shard_1_latency, ..., shard_10_latency) ≈ single shard latency.
    Works well for aggregations.
  
  Option B: separate analytics DB (ClickHouse/BigQuery).
    Write events to Kafka. Kafka → ClickHouse.
    Analytics queries hit ClickHouse (not production shards).
    Production shards never touched for analytics. ✓
  
  Recommendation: Option B for production. Keeps OLTP (transactional) separate from OLAP (analytics).
```

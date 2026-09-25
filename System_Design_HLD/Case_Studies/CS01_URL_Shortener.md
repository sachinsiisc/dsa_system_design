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

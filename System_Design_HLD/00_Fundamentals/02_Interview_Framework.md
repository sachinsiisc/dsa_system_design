# HLD Interview Framework — Step-by-Step Template
## Use This in Every MAANG HLD Interview

---

```
TIME BUDGET FOR A 45-MINUTE HLD INTERVIEW:

  0:00 –  2:00  → Step 1: Clarify requirements          (2 min)
  2:00 –  7:00  → Step 2: Back-of-envelope estimation   (5 min)
  7:00 – 12:00  → Step 3: High-level architecture       (5 min)
 12:00 – 30:00  → Step 4: Deep-dive key components      (18 min)
 30:00 – 38:00  → Step 5: Bottlenecks and solutions     (8 min)
 38:00 – 42:00  → Step 6: Trade-offs                    (4 min)
 42:00 – 45:00  → Interviewer questions / wrap-up       (3 min)

GOLDEN RULE: Talk continuously. Never sit silently.
             Think out loud. Interviewers grade reasoning, not just answers.
```

---

## STEP 1: CLARIFY REQUIREMENTS (2 minutes)

```
NEVER start designing immediately.
Ask 4-5 clarifying questions first. This shows seniority.

QUESTIONS TO ALWAYS ASK:

Scale:
  "How many daily active users do we expect?"
  "What's the read:write ratio?"
  "Are we designing for MVP or at scale (Google/Netflix level)?"

Functional scope:
  "Should I include user authentication or assume it exists?"
  "Is real-time required or is eventual consistency (1-5 seconds) acceptable?"
  "What are the must-have features vs nice-to-haves?"

Constraints:
  "Any latency SLA? (e.g., p99 < 200ms)"
  "Any geographic constraints? Global or single region?"
  "Any budget/cost constraints?"

TEMPLATE (say these words):
  "Before I start designing, let me clarify a few things.
   
   First, on scale: are we building for [X million users] or is this more MVP scope?
   
   Second, on features: I assume we need [core feature]. Should I include [optional feature]?
   
   Third, consistency: is eventual consistency acceptable for [feed/notifications/etc.] 
   or do we need strong consistency?
   
   Great, so to summarize the requirements:
   - [Functional requirement 1]
   - [Functional requirement 2]  
   - [Non-functional: X MAU, Y writes/sec, Z latency SLA]
   Does that sound right?"
```

---

## STEP 2: BACK-OF-ENVELOPE ESTIMATION (5 minutes)

```
DO THIS FOR EVERY INTERVIEW. It scopes the design.
Shows you understand scale implications.

ESTIMATION FORMULA:

QPS (queries per second):
  QPS = (DAU × actions_per_day) / 86,400
  Peak QPS = average QPS × 5  (assume 5× peak for safety)

Storage:
  Storage = records_per_day × avg_record_size × retention_days

Bandwidth:
  Read bandwidth = QPS × avg_response_size
  Write bandwidth = write_QPS × avg_payload_size

TEMPLATE (write this on the board):

"Let me do a quick back-of-envelope calculation.

Users: __ DAU.
Writes: __ actions/user/day → __ writes/day → __ writes/sec avg, __ peak.
Reads: __ : __ read:write ratio → __ reads/sec avg, __ peak.

Storage per record: __ bytes.
Total storage/day: __ GB/day.
Total storage/5 years: __ TB (need sharding? if > 5TB, yes).

Bandwidth: __ writes/sec × __ bytes = __ MB/sec write throughput.
            __ reads/sec × __ bytes = __ MB/sec read throughput.

Based on this:
- __ servers can handle __ req/sec each → need __ servers.
- Cache: top 20% of data = 80% of traffic → cache __ GB in Redis.
- DB: sharding needed if > __ TB or > __ writes/sec."

COMMON NUMBERS TO REMEMBER:
  86,400   seconds/day
  10,000   req/sec per typical web server
  1,000,000 ops/sec Redis can handle
  1 MB/sec = 86 GB/day
  1 Gbps   = 108 GB/hour
```

---

## STEP 3: HIGH-LEVEL ARCHITECTURE (5 minutes)

```
Draw the boxes and arrows. Keep it simple first.
You'll deep-dive later.

STANDARD COMPONENTS (use these as building blocks):

  [Client] → [CDN] → [API Gateway / Load Balancer]
                              │
                    ┌─────────┴─────────┐
                    │                   │
              [Service A]         [Service B]
                    │                   │
              [Message Queue]     [Cache (Redis)]
                    │                   │
              [Worker Pool]       [Database]
                    │                   │
              [Object Store]    [Read Replicas]

COMPONENT CHEAT SHEET:

  API Gateway:      Rate limiting, auth, routing, SSL termination
  Load Balancer:    L4 (IP/port routing) or L7 (HTTP-aware routing)
  CDN:              Static content, video, images. Low latency global reads.
  Redis:            Caching, session storage, rate limiting, pub/sub, sorted sets
  Kafka/SQS:        Async job queue, event bus, decoupling services
  PostgreSQL:       ACID transactions, complex queries, relational data
  Cassandra:        High write throughput, time-series, append-mostly
  DynamoDB:         Key-value at any scale, managed, AP by default
  Elasticsearch:    Full-text search, autocomplete
  S3 / Blob Store:  Large files: images, videos, logs, backups
  
TEMPLATE (draw while saying):

  "At a high level, I see these main components:

  1. [Client] makes requests to an [API Gateway] that handles auth and rate limiting.
  
  2. The gateway routes to [Service X] for [core feature A] 
     and [Service Y] for [core feature B].
  
  3. For reads: [Service X] checks [Redis cache] first.
     Cache miss: query [PostgreSQL/Cassandra].
     
  4. For writes: [Service X] writes to [DB], 
     then publishes event to [Kafka] for async processing by [Worker].
     
  5. [Static content / media] served via [CDN] — never hits our servers.
  
  Let me draw this..."
```

---

## STEP 4: DEEP-DIVE (18 minutes)

```
Pick 2-3 most interesting/critical components. Offer the choice:
"Which component would you like to deep-dive first? I'd suggest [X] because it's the 
most challenging part of this system."

COMMON DEEP-DIVES BY SYSTEM TYPE:

FEEDS / SOCIAL:
  - Fan-out strategy (on-write vs on-read vs hybrid)
  - Feed storage schema in Redis sorted sets
  - Pagination (cursor-based vs offset)

MESSAGING:
  - Message delivery and receipts
  - Offline storage strategy
  - WebSocket connection management across servers

SEARCH:
  - Inverted index construction
  - Typeahead/autocomplete (prefix trie in Redis)
  - Search ranking (TF-IDF, PageRank, ML ranking)

GEO / RIDE-SHARING:
  - Geospatial indexing (H3, QuadTree, Redis GEO)
  - Real-time driver tracking
  - Matching algorithm

VIDEO STREAMING:
  - CDN strategy (push vs pull)
  - Adaptive bitrate (HLS segments)
  - Encoding pipeline

RATE LIMITING (comes up in EVERY system):

  Token Bucket (most common):
    Each user has a bucket of N tokens.
    Each request consumes 1 token.
    Tokens refill at rate R per second.
    
    Redis Lua script (atomic check + decrement):
    
    local key = KEYS[1]
    local capacity = tonumber(ARGV[1])
    local refill_rate = tonumber(ARGV[2])
    local now = tonumber(ARGV[3])
    
    local bucket = redis.call("HMGET", key, "tokens", "last_refill")
    local tokens = tonumber(bucket[1]) or capacity
    local last_refill = tonumber(bucket[2]) or now
    
    -- Add tokens based on elapsed time
    local elapsed = now - last_refill
    tokens = math.min(capacity, tokens + elapsed * refill_rate)
    
    if tokens >= 1 then
        tokens = tokens - 1
        redis.call("HMSET", key, "tokens", tokens, "last_refill", now)
        redis.call("EXPIRE", key, 3600)
        return 1  -- allowed
    else
        return 0  -- rate limited
    end

  Alternatives:
    Sliding Window Log:  exact but high memory (store all request timestamps)
    Fixed Window:        simple but allows 2× burst at window boundary
    Sliding Window Counter: approximation of sliding window, low memory

DATABASE SCHEMA (show at least one schema):

  "For [entity], I'd use this schema:
  
  CREATE TABLE [entity] (
      id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      [field]     [type] NOT NULL,
      created_at  TIMESTAMP DEFAULT NOW(),
      updated_at  TIMESTAMP DEFAULT NOW()
  );
  
  INDEX on [frequently queried column]:
  CREATE INDEX idx_[name] ON [entity]([column]);
  
  Shard key: [reason for choosing this column]"
```

---

## STEP 5: BOTTLENECKS AND SOLUTIONS (8 minutes)

```
Proactively identify failure modes. Don't wait for interviewer to ask.
Shows senior thinking: "here's what breaks and here's how I'd fix it."

CHECKLIST OF COMMON BOTTLENECKS:

☐ Single Point of Failure (SPOF)
  "What happens if [service X] crashes?"
  Fix: Multiple instances behind load balancer. Health checks.

☐ Database overload
  "At [peak QPS], does our DB handle it?"
  Fix: Read replicas, caching, sharding, connection pooling.

☐ Cache stampede
  "What if [popular item] expires and 10,000 requests all miss?"
  Fix: Redis SET NX mutex, probabilistic early expiry, pre-warming.

☐ Message queue backlog
  "What if workers can't keep up with Kafka?"
  Fix: Scale consumer group, increase partition count, dead-letter queue.

☐ Network partition
  "What if our DB becomes unreachable?"
  Fix: Circuit breaker, fallback to cache, graceful degradation.

☐ Hot spots / hot keys
  "What if one user generates 10× more traffic than others (celebrity)?"
  Fix: Local caching, fan-out optimization, write shielding.

☐ Clock skew in distributed systems
  "If we order events by timestamp across servers, clocks differ by ~100ms."
  Fix: Logical clocks, NTP, TrueTime (Google), or monotonic event IDs.

TEMPLATE:
  "Let me go through potential bottlenecks:

  First, [Service X] is currently a single instance — SPOF.
  Fix: Run 3 replicas behind load balancer with health checks.
  
  Second, at 100,000 reads/sec, our DB will be overwhelmed.
  Fix: Redis cache with 95% hit rate → only 5,000 reads hit DB.
       If still too many: read replicas.
  
  Third, for our [Kafka consumer]: if message processing is slow,
  backlog builds. Fix: auto-scaling consumer group with Kubernetes HPA.
  Monitor: consumer lag metric → if lag > 10,000 messages → scale up."
```

---

## STEP 6: TRADE-OFFS (4 minutes)

```
Every design decision has trade-offs. State them explicitly.
Interviewers want to know you understand the alternatives.

TRADE-OFF FRAMEWORK:
  "I chose [X] over [Y] because [reason].
   The downside of [X] is [cost].
   I'd consider [Y] if [condition changed]."

COMMON TRADE-OFFS:

Consistency vs Availability (CAP):
  "I chose AP because [use case] tolerates [N seconds] staleness.
   If we needed strong consistency (e.g., financial data), I'd switch to CP
   and accept the availability trade-off."

SQL vs NoSQL:
  "I chose Cassandra for high write throughput. 
   Downside: no JOINs, no transactions.
   If we needed complex queries or transactions, I'd use PostgreSQL instead."

Fan-out on write vs read:
  "Fan-out on write: fast reads, expensive writes. Chosen here.
   Fan-out on read: slow reads, cheap writes. Better when follower count >> followed count."

Synchronous vs Asynchronous:
  "Made [step X] async via Kafka. 
   Downside: eventual consistency — user won't see the effect immediately.
   If we needed immediate feedback (payment confirmation), I'd make it synchronous."

Monolith vs Microservices:
  "I designed as microservices for independent scaling.
   Downside: network calls between services add latency and complexity.
   For a startup MVP, I'd start with a monolith and extract services later."

Push vs Pull for notifications:
  "WebSocket push: real-time. Requires persistent connections (~50KB RAM/connection).
   HTTP polling: simple. But wasteful (most polls return nothing).
   Long polling: middle ground. Used when WebSocket is overkill."
```

---

## THE MASTER CHEAT SHEET

```
PROBLEM → SOLUTION MAPPING:

Problem                          → Best Solution
─────────────────────────────────────────────────────
Read latency too high            → Redis cache (< 1ms)
Write throughput too high        → Cassandra or horizontal sharding
Too many DB connections          → PgBouncer connection pooler
Static content slow globally     → CDN (Cloudflare, CloudFront)
Real-time updates to client      → WebSocket or SSE
Fan-out to millions of users     → Kafka + async workers
Rate limiting                    → Token bucket in Redis (Lua)
Unique ID generation             → Snowflake (timestamp + worker + seq)
Search / autocomplete            → Elasticsearch + Redis prefix trie
Geospatial queries               → Redis GEO / H3 / PostGIS
Message delivery guarantee       → Kafka with consumer offsets
Idempotent retries               → Redis idempotency key (SET NX)
Session storage                  → Redis (TTL = session timeout)
Distributed transactions         → Saga pattern or 2PC
Avoid double-processing          → Exactly-once with message ID dedup
Count millions of items fast     → HyperLogLog in Redis
Cache stampede                   → Redis SET NX mutex / probabilistic expiry
Consistent hashing               → Add/remove nodes with minimal key movement
Leader election                  → Zookeeper / etcd / Raft consensus
Service discovery                → Consul / Eureka
Circuit breaker                  → Hystrix / Resilience4j
API versioning                   → /api/v1/ in URL (most common)
File upload (large)              → Pre-signed S3 URL (bypass server)
Scheduled jobs                   → Celery beat / Airflow / Cron + SQS
AB testing / feature flags       → Split.io / LaunchDarkly / Unleash
```

---

## INTERVIEW PHRASES THAT SHOW SENIORITY

```
Instead of:              Say:
─────────────────────────────────────────────────────────────
"I'll use a database"    "I'd use PostgreSQL here because we need ACID transactions
                          for [reason]. If write throughput became a bottleneck,
                          I'd switch to Cassandra or shard the PostgreSQL."

"I'll add a cache"       "I'd add Redis with cache-aside pattern. TTL of 5 minutes.
                          Invalidation: delete on write, not update — safer.
                          Expected hit rate: ~90% based on Pareto distribution."

"It scales"              "This scales horizontally — each [service] is stateless,
                          so we can add instances behind the load balancer.
                          The bottleneck then becomes [DB/cache/queue], which we'd
                          address by [solution]."

"It's fast"              "p99 latency should be < 50ms. Here's why: Redis at 1ms,
                          DB query with index at 5ms, network overhead ~10ms.
                          Total ~16ms. We have headroom."

"It won't fail"          "If [service] fails, we use a circuit breaker.
                          Fallback: serve cached data / degraded response.
                          Alert via PagerDuty. SLA: 99.99% = 52 min downtime/year."
```

---

*See `01_Case_Studies.md` for 5 complete worked examples using this framework.*

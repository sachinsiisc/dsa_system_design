# Topic 2: Scalability — Handling Growing Load
## HLD Deep Dive | MAANG Interview Ready

---

## 1. What Is Scalability?

```
Scalability = the system's ability to handle increasing load without degradation.

Load can mean:
  - More users (DAU grows from 1M to 100M)
  - More data (storage grows from 1TB to 1PB)
  - More complexity (new features, new data types)
  - More requests per second (traffic spikes on Black Friday, IPL final)

A scalable system handles 10× load with:
  - Less than 10× cost
  - No code rewrites
  - Acceptable latency (doesn't become 10× slower)
```

---

## 2. Vertical vs Horizontal Scaling

```
VERTICAL SCALING ("Scale Up"):
  Replace server with bigger one.
  
  Example progression:
    t3.medium: 2 vCPU, 4GB RAM, $0.04/hr  → handles 1,000 req/sec
    t3.xlarge: 4 vCPU, 16GB RAM, $0.17/hr → handles 4,000 req/sec
    c6i.8xlarge: 32 vCPU, 64GB RAM, $1.36/hr → handles 30,000 req/sec
  
  Advantages:
    - No code change (same binary, bigger machine)
    - No distributed systems complexity
    - Good for databases (especially stateful systems)
  
  Limits:
    - Single point of failure (one machine dies = system down)
    - Physical ceiling exists (AWS largest: u-24tb1.metal = 24TB RAM, 448 vCPU)
    - Cost grows super-linearly (2× RAM ≠ 2× cost, often 3-4×)
    - Downtime for upgrade (stop → resize → restart)

HORIZONTAL SCALING ("Scale Out"):
  Add more machines of the same size.
  
  Example:
    1 × t3.medium: 1,000 req/sec, $0.04/hr
    10 × t3.medium: 10,000 req/sec, $0.40/hr  (same cost per unit)
  
  Advantages:
    - No single point of failure (one dies → others handle traffic)
    - Theoretically infinite scale
    - Cheaper (commodity hardware)
    - Can add/remove dynamically (auto-scaling)
  
  Requires:
    - Load balancer to distribute traffic
    - Stateless application (any server can handle any request)
    - Shared state externalized (Redis for sessions, not local memory)

RULE:
  Stateless services (web servers, API servers) → horizontal scaling (easy)
  Stateful services (databases) → vertical first, then sharding (harder)
```

---

## 3. Stateless vs Stateful Design

```
STATELESS:
  Server holds no memory of previous requests.
  Any server can handle any request.
  Session data stored externally (Redis, database).
  
  Example (stateless login):
    1. User logs in → server issues JWT token.
    2. Token contains: user_id, role, expiry (signed with server secret).
    3. User sends token with every request.
    4. ANY server validates token (just verifies signature — no DB needed).
    5. Server goes down → user just hits another server → no problem.

STATEFUL:
  Server remembers state between requests.
  Client must return to SAME server.
  
  Example (bad: in-memory session):
    1. User logs in → Server A stores session in local memory.
    2. Next request hits Server B → "Who are you? I don't know you." → 401.
    3. Load balancer must use sticky sessions (IP hash) → defeats load balancing.
  
  Fix: Move state to Redis.
    1. User logs in → Server A stores session in Redis: "session:abc123" → user data.
    2. Next request hits Server B → checks Redis → finds session → knows user.
    3. Any server can handle any request → true horizontal scaling.

  # Session storage in Redis:
  import redis
  import uuid, json

  r = redis.Redis(host='redis-cluster', port=6379)

  def create_session(user_data: dict) -> str:
      session_id = str(uuid.uuid4())
      r.setex(
          f"session:{session_id}",
          3600,                        # TTL: 1 hour
          json.dumps(user_data)        # value: user info
      )
      return session_id  # sent to client as cookie

  def get_session(session_id: str) -> dict:
      data = r.get(f"session:{session_id}")
      return json.loads(data) if data else None
```

---

## 4. The Bottleneck Checklist

```
When your app slows down, bottleneck is ONE of these. Find it first.

DIAGNOSIS APPROACH:
  1. Add metrics/logs to every layer.
  2. Load test (Apache JMeter, Locust, k6).
  3. Watch: where does latency spike? Where does CPU/memory spike?

BOTTLENECK 1: CPU-bound
  Symptom: CPU at 100%. Server slow under load.
  Causes: Heavy computation (image processing, encryption, ML inference, regex).
  
  Fixes:
    - Scale horizontally (add more servers)
    - Move to faster language (Python → Go/Rust for hot paths)
    - Use async processing (offload CPU work to background workers via Kafka)
    - Move ML inference to GPU instances
  
  Example: Stripe moves all heavy crypto operations to dedicated crypto servers.

BOTTLENECK 2: Memory-bound
  Symptom: RAM near 100%. Garbage collection pauses. OOM errors.
  Causes: Large in-memory caches, unbounded queues, memory leaks.
  
  Fixes:
    - Paginate queries (don't load entire result set into memory)
    - External cache (Redis) instead of in-process LRU
    - Limit queue sizes, add backpressure
    - Find and fix memory leaks (profiler: py-spy, async-profiler)
  
  Example: Java Spring apps: tune -Xmx, use G1GC for large heaps.

BOTTLENECK 3: Disk I/O
  Symptom: DB queries slow. Disk await time high (iostat).
  Causes: Missing indexes, full table scans, too many writes.
  
  Fixes:
    - Add indexes for WHERE/JOIN/ORDER BY columns
    - Add read replicas
    - Caching layer (Redis in front of DB)
    - Sharding (distribute writes across multiple DB servers)
    - SSD over HDD (10-100× faster random I/O)

BOTTLENECK 4: Network I/O
  Symptom: Service A calls Service B 10 times per request. Total: 300ms network.
  Causes: Chatty microservices. Large payloads. Many small requests.
  
  Fixes:
    - Batch requests (one call returns 10 items vs 10 calls for 1 item each)
    - Compress payloads (gzip, Brotli)
    - Use CDN for static content
    - Co-locate frequently communicating services (same VPC, same AZ)
    - gRPC instead of REST (binary, smaller payload, HTTP/2 multiplexing)

BOTTLENECK 5: Database connections
  Symptom: "Too many connections" errors. Connections timing out.
  Causes: Too many threads/processes, each holding a DB connection.
  
  Fixes:
    - PgBouncer connection pooler
    - Reduce connection hold time (don't hold connection during network calls)
    - Read replicas for reads
    - Connection pool sizing: pool_size = cores × 2 + 1 (rule of thumb)

BOTTLENECK 6: Single-threaded bottleneck
  Symptom: One queue/worker is at 100%, others idle.
  Example: Single Redis Lua script processing payments.
  
  Fixes:
    - Partition work (multiple queues, partition by user_id or tenant_id)
    - Sharding (Redis Cluster instead of single Redis)
```

---

## 5. Auto-Scaling

```
REACTIVE AUTO-SCALING:
  Monitor metric → threshold crossed → add/remove instances.
  
  AWS Auto Scaling Group:
    Scale-out trigger: CPU > 70% for 2 minutes → add 2 instances
    Scale-in  trigger: CPU < 30% for 10 minutes → remove 1 instance
    Min instances: 2 (always at least 2 for HA)
    Max instances: 20 (cost cap)
  
  Cooldown period: 300 seconds after scale-out before scaling again.
  Reason: new instances take time to warm up. Don't scale too aggressively.

PREDICTIVE AUTO-SCALING:
  Analyze historical traffic patterns.
  Pre-scale BEFORE traffic arrives.
  
  Example: E-commerce flash sale at 12:00 PM.
    10:00 AM: System at 5 instances.
    11:45 AM: Predictive scaler adds 15 more instances (pre-warming).
    12:00 PM: Sale starts. Traffic spikes 10×. Already scaled. No users impacted.
    1:00 PM: Sale over. Traffic drops. Scale back in.
  
  AWS: "Predictive Scaling" policy. Uses ML to forecast from CloudWatch metrics.

KUBERNETES HPA (Horizontal Pod Autoscaler):
  apiVersion: autoscaling/v2
  kind: HorizontalPodAutoscaler
  spec:
    scaleTargetRef:
      name: api-deployment
    minReplicas: 3
    maxReplicas: 50
    metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 60
    - type: External
      external:
        metric:
          name: kafka_consumer_lag    # scale based on queue depth too
        target:
          type: AverageValue
          averageValue: "1000"

SCALE TRIGGER CHOICES:
  CPU: general purpose, reactive
  Memory: careful — usually not a good scaler (memory doesn't drop fast)
  Request rate: good for web services
  Queue depth: good for worker services (consumer lag in Kafka)
  Custom metric: P99 latency > 500ms → scale out (latency-based)
```

---

## 6. Database Scalability Patterns

```
READ SCALING:
  Problem: 100,000 reads/sec on one PostgreSQL primary.
  Solution: Read replicas.
  
  Route: Write → Primary. Read → Round-robin across replicas.
  Replication lag: async replicas may be 0.1-2 seconds behind primary.
  
  If read-your-own-writes needed:
    After write: redirect that user's reads to primary for 5 seconds.
    Or: use synchronous replication (slower writes).

WRITE SCALING:
  Problem: 50,000 writes/sec on one PostgreSQL primary.
  Solution: Sharding.
  
  Shard by user_id:
    shard = user_id % num_shards
    shard 0: user_ids 0, 4, 8, 12, ...
    shard 1: user_ids 1, 5, 9, 13, ...
    shard 2: user_ids 2, 6, 10, 14, ...
    shard 3: user_ids 3, 7, 11, 15, ...
  
  Problem: cross-shard JOINs (get all orders for all users → multiple shard queries)
  Fix: Denormalize. Duplicate data across shards where needed.

WRITE-APPEND SCALING:
  Cassandra / DynamoDB: optimized for write-heavy, time-series patterns.
  
  Cassandra write path:
    Write → commit log (sequential write, fast) + memtable (in-memory)
    Memtable full → flush to SSTables (sorted immutable files on disk)
    Compaction: periodically merges SSTables, removes tombstones
  
  Result: writes are always sequential → ~1M writes/sec on commodity hardware.
  Reads: slightly slower (merge multiple SSTables). Read-heavy? Use PostgreSQL.
```

---

## 7. The CAP Trade-off in Scaling

```
When scaling horizontally, you create distributed system challenges:

SCENARIO: User updates username.
  Shard A receives write: username = "Alice_new"
  Shard B hasn't received replication yet: username = "Alice_old"
  
  If another request reads from Shard B immediately: stale data.
  
  Solutions:
    Strong consistency: write to quorum (2/3 shards confirm) before returning.
      Slower writes. Consistent reads. Use for financial data.
    
    Eventual consistency: return to user immediately after writing to one shard.
      Fast writes. Stale reads possible for ~100ms. Use for social feeds.

REPLICATION FACTOR:
  Cassandra: replicas=3. Write to all 3 by default.
  Read/Write quorum: if replicas=3, quorum=2.
  Write quorum: 2 of 3 must confirm → then return success.
  Read quorum: 2 of 3 must agree → return value.
  Result: tolerate 1 node failure. Reads always see most recent quorum write.
```

---

## 8. Scalability Anti-Patterns

```
ANTI-PATTERN 1: Premature optimisation
  "Let me design for 1 billion users from day 1"
  Reality: 99% of startups never reach 1M users.
  Fix: Build for 10× current scale. Re-architect when needed.
  "Make it work, make it right, make it fast."

ANTI-PATTERN 2: Shared mutable state
  All servers share one in-memory counter for active sessions.
  One server updates it → others don't see it → inconsistency.
  Fix: Externalize all shared state (Redis, database). No server-local state.

ANTI-PATTERN 3: Synchronous fan-out
  User posts tweet → synchronously notify all 1M followers before returning.
  User waits 30 seconds for "Tweet posted" confirmation.
  Fix: Async fan-out. Return immediately. Process followers in background via Kafka.

ANTI-PATTERN 4: Database as a queue
  Using PostgreSQL LISTEN/NOTIFY or polling a "jobs" table as a message queue.
  Fine at small scale. At high scale: DB table becomes bottleneck.
  Fix: Use a real queue (Kafka, RabbitMQ, SQS) designed for this.

ANTI-PATTERN 5: Monolithic database
  All services write to one giant PostgreSQL.
  Schema locks: "I can't deploy because Marketing's migration locks the users table."
  Bottleneck: all services competing for same DB connections.
  Fix: Each service owns its own database. Cross-service data: via API or async events.
```

---

## 9. Interview Questions

```
Q1: "How would you scale your system from 100 to 10 million users?"
A: Phase 1 (100→10K): Vertical scale. Single server. CDN for static.
   Phase 2 (10K→100K): Add load balancer. Horizontal app servers. Redis cache. Read replicas.
   Phase 3 (100K→1M): Sharding DB. Kafka for async. Multi-region.
   Phase 4 (1M→10M): Microservices. Region-specific deployment. Global CDN.

Q2: "When would you choose vertical over horizontal scaling?"
A: Databases (especially early on). Vertical is simpler — no distributed system complexity.
   Horizontal for stateless services. Until you hit the vertical ceiling or need HA.

Q3: "How do you handle state in a horizontally scaled system?"
A: Externalize all state. Sessions in Redis. DB for persistent data.
   App servers are stateless — any server handles any request.
   JWT tokens are self-contained state (no server storage needed).

Q4: "How do you detect scalability bottlenecks?"
A: Metrics + profiling. CPU, memory, disk I/O, network I/O, DB connection count.
   Load testing (k6 / Locust) to find where it breaks.
   APM tools (Datadog, New Relic) for distributed tracing across services.
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

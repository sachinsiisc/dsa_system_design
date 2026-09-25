# HLD Prerequisites — Exercises
## Beginner → MAANG-level practice questions with full answers

---

## SECTION A: Conceptual Exercises (Write out your answer, then check)

---

### Exercise 1 — DNS and Networking
**Q: A user in India types `amazon.com` in their browser. List EVERY step that happens before they see the Amazon homepage. Include DNS, TCP, HTTP.**

**Answer:**
```
1. Browser checks local DNS cache (OS cache).
   No entry → checks router's DNS cache.
   No entry → asks ISP's DNS resolver.

2. ISP DNS resolver:
   Checks its own cache.
   If miss: asks Root DNS server → "Who handles .com?"
   Root → "Ask the .com TLD nameserver"
   .com TLD → "Ask amazon.com's authoritative nameserver"
   amazon.com nameserver → "amazon.com is at 205.251.242.103"
   ISP caches this (TTL: typically 300 seconds), returns to browser.

3. Browser has IP: 205.251.242.103
   TCP 3-way handshake with Amazon's server (or load balancer):
     SYN → SYN-ACK → ACK
   
4. TLS handshake (HTTPS):
   ClientHello (cipher suites) → ServerHello + Certificate →
   Client verifies certificate with CA → Key exchange → Session key established
   All further traffic encrypted.

5. HTTP/2 GET Request:
   GET / HTTP/2
   Host: amazon.com
   Accept: text/html, ...

6. Amazon's infrastructure:
   Load balancer receives request → routes to web server in closest region.
   Web server checks cache (Redis/Memcached) for homepage content.
   Cache hit → return immediately. Miss → query DB/services → assemble response.

7. HTTP Response:
   HTTP/2 200 OK
   Content-Type: text/html
   [HTML body]

8. Browser parses HTML → discovers linked resources (CSS, JS, images).
   Many of these served from CDN (CloudFront) close to user in India.
   Browser renders DOM → user sees Amazon homepage.

Key bottlenecks prevented:
   DNS: cached at multiple levels → fast.
   Static content: CDN → ~5ms from India instead of ~100ms from US.
   SSL termination: at load balancer, not origin servers.
```

---

### Exercise 2 — Caching Decision

**Q: Design the caching strategy for a food delivery app. What data do you cache? With what TTL? What invalidation strategy?**

**Answer:**
```
Data to Cache and Why:

1. Restaurant menu items
   Read: Very frequently (every user viewing restaurant page)
   Write: Rarely (restaurant updates menu maybe daily)
   Cache: YES. Key: "menu:{restaurant_id}"
   TTL: 30 minutes (menu changes are infrequent)
   Strategy: Cache-Aside + explicit invalidation when restaurant edits menu
   
2. Restaurant list near user location
   Depends on: user lat/lng, time of day (some restaurants close)
   Cache: Yes, but location-specific. Key: "restaurants:{lat_bucket}:{lng_bucket}"
   TTL: 5 minutes (restaurant availability can change)
   
3. User profile (name, address, payment methods)
   Read: At checkout
   Write: User updates profile
   Cache: YES. Key: "user:{user_id}"
   TTL: 5 minutes. Invalidate on write (Cache-Aside).
   
4. Live order status (preparing, out for delivery, delivered)
   Constantly changing. DB must be source of truth.
   Cache: NO. Or very short TTL of 5-10 seconds.
   Better: WebSocket push when status changes.

5. Delivery driver location
   Updates every 10 seconds. Extremely dynamic.
   Cache: Redis Geo (geospatial index). Key: "driver:{driver_id}:location"
   TTL: 30 seconds. Rider app overwrites every 10 seconds.
   
6. Surge pricing multiplier
   Changes based on supply/demand.
   Cache: YES in memory. Key: "surge:{zone_id}:{time_bucket}"
   TTL: 1 minute. Recomputed by pricing service every minute.

What NOT to cache:
   - Active order items being modified
   - Payment transaction data
   - User's current cart (session storage / Redis with user session)

Cache infrastructure:
   Use Redis Cluster for distributed caching.
   2 Redis replicas for high availability.
   Memory: 32GB Redis per cluster.
```

---

### Exercise 3 — Database Decisions

**Q: You're designing the database layer for a social network like LinkedIn. Identify the main entities and choose SQL vs NoSQL for each. Justify.**

**Answer:**
```
Entities and database choices:

1. Users (profiles, settings, connections count)
   Storage: PostgreSQL (SQL)
   Why: Structured data. JOINs with connections, posts. Strong consistency needed.
        "User not found" is worse than slight read latency.
   Schema: users(id, name, email, headline, location, created_at)

2. User connections (who follows whom)
   Data shape: Edges in a social graph. (user_id, connected_user_id)
   At scale: 900M users × 500 avg connections = 450B edges.
   Storage: 
     Small scale: PostgreSQL (connections table)
     Large scale: Graph DB (Neo4j) or custom graph store
   Why graph at scale: "Find 2nd-degree connections" → graph traversal is natural.
   LinkedIn actually uses: Custom graph service (Voyager) on top of RocksDB.

3. Posts / Articles
   Structure: Flexible (text, media, polls, different formats over time)
   Storage: MongoDB or DynamoDB (Document DB)
   Why: Schema evolution without migration. Posts vary in structure.
   Each post = JSON document with flexible fields.

4. Comments, Reactions
   High write volume. Simple structure.
   Storage: DynamoDB or Cassandra
   Partition key: post_id → all reactions/comments for a post on same shard.
   Why Cassandra: Write-optimized. Can handle 1M writes/sec.

5. News Feed (which posts to show each user)
   Precomputed feed per user. List of post IDs.
   Storage: Redis (for hot/active users) + Cassandra (for persistent storage)
   Key: "feed:{user_id}" → sorted list of recent post IDs

6. Messages (InMail)
   Storage: Cassandra
   Schema: (conversation_id, timestamp, sender_id, content)
   Partition key: conversation_id (all messages in same conversation on same node)
   Clustering key: timestamp (sorted by time)

7. Analytics / Metrics (who viewed your profile, post impressions)
   Storage: ClickHouse or BigQuery (columnar analytics DB)
   Why: Aggregation queries over large datasets. Write-append-only.

Summary:
  PostgreSQL → users, core relational data
  MongoDB    → posts, flexible documents
  Cassandra  → messages, reactions (high write volume)
  Redis      → feeds, caching, sessions
  Neo4j      → graph queries (connections)
  ClickHouse → analytics
```

---

### Exercise 4 — Load Balancing

**Q: You have 5 web servers. Server 1 has 8 cores, servers 2-5 have 4 cores each. Design the load balancing strategy.**

**Answer:**
```
Strategy: Weighted Round Robin

Server 1: weight = 2 (8 cores)
Servers 2-5: weight = 1 each (4 cores each)

Traffic pattern per cycle:
  Server 1: receives 2 requests
  Server 2: 1 request
  Server 3: 1 request
  Server 4: 1 request
  Server 5: 1 request
  Cycle: [1, 2, 1, 3, 1, 4, 5] (2:1:1:1:1 ratio)
  Total capacity = 8 + 4×4 = 24 "units" of work.
  Server 1 handles 2/6 = 33% of traffic. Each small server handles 1/6 ≈ 17%.

Health checks:
  GET /health every 10 seconds.
  If server doesn't respond in 2s or returns 5xx → mark unhealthy.
  After 2 consecutive failures → remove from pool.
  After 3 consecutive successes → re-add to pool.

Session handling:
  Stateless app: no session concern. Any server can handle any request.
  If stateful: Store sessions in Redis (not on server).
  → Any server can read any session → works with any load balancing algorithm.

Monitoring:
  Track per-server: request rate, p99 latency, error rate.
  If one server's latency spikes (p99 > 500ms) → reduce its weight or remove.
```

---

### Exercise 5 — CAP Theorem Application

**Q: For each scenario, choose between CP and AP and justify:**

**a) Online multiplayer game leaderboard**
```
Choice: AP (Availability + Partition Tolerance)

Why: Leaderboard can be slightly stale (1-2 seconds) — acceptable.
     Players care that the game works, not that rank updates within 10ms.
     If you choose CP: during network partition, leaderboard becomes unavailable.
     "Service unavailable" in a game is much worse than "slightly stale rank."
     
Implementation: Cassandra or DynamoDB with eventual consistency.
Eventual convergence: All nodes agree on final leaderboard within seconds.
```

**b) Medical prescription system**
```
Choice: CP (Consistency + Partition Tolerance)

Why: A doctor must see the LATEST prescription list. If another doctor prescribed
     morphine 1 minute ago, the current doctor must NOT see stale data and 
     accidentally prescribe again → patient overdose risk.
     
     Availability sacrifice: "System unavailable" is better than "wrong prescription."
     Downtime: users wait → inconvenient.
     Wrong data: patient harmed → catastrophic.

Implementation: PostgreSQL with synchronous replication. 
                Read from primary only.
```

**c) Instagram likes count**
```
Choice: AP (Availability + Partition Tolerance)

Why: Seeing "1,234 likes" vs "1,237 likes" due to 2-second lag is completely
     acceptable. Users don't notice or care about exact real-time counts.
     
     If CP: every like requires coordination across data centers → high latency.
     Users can't like posts → terrible experience.

Implementation: Cassandra counters. 
CRDT (Conflict-free Replicated Data Types): counters that merge correctly
even with concurrent updates on different nodes. Eventual consistency guaranteed.
```

**d) ATM cash withdrawal**
```
Choice: CP (Consistency + Partition Tolerance)

Why: If network partitions, do NOT allow withdrawal.
     "ATM temporarily unavailable" → customer annoyed but money safe.
     Stale balance → customer withdraws more than available → bank loses money.
     
     Or design: Allow offline with a CONSERVATIVE limit.
     ATM knows account limit is $200/day. Without network, allow withdrawal only
     if daily_offline_withdrawals + amount < $200.
     This is an AP design with bounded inconsistency (conservative approximation).
```

---

### Exercise 6 — Back-of-Envelope Estimation

**Q: Estimate storage requirements for WhatsApp.**
```
Assumptions:
  2 billion users
  60% DAU = 1.2 billion daily active
  Each user sends 50 messages/day
  Messages: 60% text, 30% images, 10% videos
  Avg text message = 100 bytes
  Avg image message = 100KB (compressed)
  Avg video message = 5MB (short video, compressed)

Daily messages:
  Total messages = 1.2B × 50 = 60 billion messages/day

Daily data:
  Text: 60B × 0.6 × 100 bytes = 3.6 TB/day
  Images: 60B × 0.3 × 100KB = 1.8 PB/day ... that's too high
  Wait: 1.2B × 50 = 60B messages × 30% images = 18B image messages × 100KB = 1.8 PB/day
  
  That's extreme. Let me re-check assumptions.
  Typical WhatsApp: avg ~30 messages/day, avg image = 30KB (WhatsApp compresses heavily)
  
  Revised:
  Text:  60B × 0.6 × 100B = 3.6 TB/day
  Images: 60B × 0.3 × 30KB = 540 TB/day
  Videos: 60B × 0.1 × 1MB  = 6 PB/day (even compressed)

This is why WhatsApp uses:
  - Heavy compression for all media (images compressed to 30KB)
  - Messages stored for 30 days max (not forever)
  - End-to-end encrypted → stored only on device, not server
  - Actual server storage: much less, as messages deleted after delivery

  If messages stored 30 days: 540 TB/day × 30 = 16.2 PB for images
  Infrastructure: Object storage (S3-like) with CDN.

QPS:
  60B messages/day ÷ 86,400 sec = 694,000 messages/sec
  Peak (assume 5× average) = 3.5 million messages/sec
```

---

### Exercise 7 — Design a Caching Layer

**Q: Design the caching layer for an e-commerce product page that gets 10,000 requests/second.**

**Answer:**
```
Analysis:
  10,000 req/s to DB would overwhelm a single DB server (~10,000 queries/sec max)
  But 99% of reads are the same products (long-tail distribution: top 10% of products = 90% of traffic)
  
  Cache those top 10% → cache hit rate ~90%
  Actual DB load = 10,000 × 10% = 1,000 req/s → manageable

Cache layers (multi-level):

L1: In-process cache (application memory)
  - Library: Python: functools.lru_cache or cachetools. Java: Caffeine.
  - Each web server caches ~1000 most popular products.
  - TTL: 60 seconds (short, since local and not shared)
  - Latency: < 0.1ms
  - Miss: go to L2

L2: Redis cluster (shared cache)
  - All app servers share same Redis.
  - Stores: product details, prices, inventory count
  - Key: "product:{product_id}:v2"
  - TTL: 5 minutes for product details, 30 seconds for inventory count
  - Latency: ~0.5-1ms
  - Cache size: Redis 32GB × 3 nodes
  - Miss: go to DB

L3: PostgreSQL (primary store)
  - Source of truth.
  - Handles ~1,000 req/s (10% of traffic)
  - Read replicas: 3 replicas handle ~3,000 read req/s if needed

Cache invalidation:
  Product price update:
    Admin updates price → DB write → publish event to Kafka "product-updated"
    Kafka consumer: delete "product:{id}" from Redis, update L1 on each server.
  Inventory update (every purchase):
    Happens frequently → short TTL (30s) on inventory count.
    Or: Update Redis directly (Lua script for atomic decrement).

Hot product problem (cache stampede):
  New iPhone released → 10,000 simultaneous cache misses.
  Fix: Use Redis SET NX (mutex). First miss holds lock, fetches from DB, stores.
  Others wait for lock, then read from cache.
  
  Or: Pre-warm cache. Marketing knows about launches → admin endpoint
      to pre-populate cache before launch.
```

---

## SECTION B: Draw-the-Architecture Exercises

### Exercise 8
**Q: Draw the architecture for YouTube video upload. What happens from the moment a user selects a video file?**

```
User → [Browser]
         |
         | 1. POST /upload (multipart form)
         ↓
    [API Gateway] ← rate limiting, auth
         |
         ↓
    [Upload Service]
      - Receive chunks (resumable upload: client sends 4MB chunks)
      - Store in temporary object store (S3 raw bucket)
      - Generate upload_id, return to client
         |
         | 2. Publish to Kafka topic "video-uploaded"
         ↓
    [Kafka: video-uploaded topic]
         |
    ┌────┴────────────────────────┐
    ↓                             ↓                 ↓
[Transcoding Service]     [Thumbnail Service]   [Content Moderation]
  - Pull from S3 raw         - Extract frame        - Run ML model
  - Generate: 1080p,         - Resize to thumb        (NSFW detection)
    720p, 480p, 360p         - Store in S3          - Flag or approve
  - HLS segments                                    - Notify review queue
  - Store in S3 CDN
         |
         | 3. Update DB: video status = "processing" → "ready"
         ↓
    [Video DB (Cassandra)]
    - video metadata
    - transcript_url
    - thumbnail_url
    - manifest_url (HLS)

    [Notification Service]
         ↓
    Email/Push: "Your video is ready"

Watch flow:
User → CDN (CloudFront) → HLS manifest → CDN video segments
    If CDN miss → S3 → cache at CDN
```

---

## SECTION C: Rapid-Fire Q&A

| Question | Answer |
|----------|--------|
| When does HTTP vs WebSocket? | HTTP: request-response. WS: real-time bidirectional (chat, gaming) |
| CDN best for? | Static content: images, CSS, JS, videos. NOT dynamic personalised data. |
| Why load balancer + health checks? | Automatic failover when server crashes. No SPOF. |
| LRU vs TTL eviction? | LRU: keep recently used. TTL: auto-expire after time. Use both together. |
| Read replica purpose? | Scale reads. Primary = writes only. Replicas = reads. |
| Sharding vs replication? | Sharding = split data across nodes. Replication = copy data to multiple nodes. |
| CAP real choice? | CP or AP (P always required in distributed system). |
| Cache-aside vs write-through? | Cache-aside: app manages cache. Write-through: every write updates cache+DB. |
| Kafka vs RabbitMQ? | Kafka: high-throughput, replay, pub/sub. Rabbit: complex routing, task queues. |
| Consistent hashing use? | Add/remove nodes with minimal data movement (Redis Cluster, Cassandra). |

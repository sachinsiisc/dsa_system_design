# HLD Fundamentals — Prerequisites for System Design
## Complete Beginner to MAANG Interview Ready

---

## 🗺️ What You Need to Know Before Designing Any System

```
Every large system is built on 8 building blocks:

1. Networking basics  → How computers talk to each other
2. Scalability        → How to handle growing load
3. Load Balancing     → How to spread work across servers
4. Caching            → How to make reads fast
5. Databases          → How to store data reliably
6. Message Queues     → How to decouple services
7. CAP Theorem        → The fundamental trade-off
8. Consistency Models → How "fresh" is the data?

Master these 8 → you can design ANY system.
```

---

## TOPIC 1: How the Internet Works (Networking Basics)

### 1.1 What Happens When You Type google.com?

This is the MOST common starter question in system design. Know every step.

```
Step 1: DNS Resolution
  Browser checks: cache → OS → Router → ISP DNS → Root → TLD → google.com DNS
  google.com → 142.250.64.14  (IP address)
  
  Why DNS? Humans remember names (google.com), computers use numbers (IP).
  DNS = Phone book of the internet.

Step 2: TCP Connection (3-Way Handshake)
  Client → Server:  SYN   (I want to connect)
  Server → Client:  SYN-ACK (OK, I'm ready)
  Client → Server:  ACK   (Great, let's talk)
  
  Now a reliable connection exists. Like calling someone and both saying "hello".

Step 3: TLS Handshake (for HTTPS)
  Client → Server:  ClientHello (here are my supported cipher suites)
  Server → Client:  ServerHello + Certificate (here's my identity proof)
  Client:           Verify certificate with Certificate Authority
  Both:             Exchange keys, derive session key
  Now: all data encrypted. Third parties can't eavesdrop.

Step 4: HTTP Request
  GET / HTTP/1.1
  Host: google.com
  Accept: text/html

Step 5: Server processes request
  Load balancer receives it → routes to web server → web server queries DB/cache →
  assembles HTML response

Step 6: HTTP Response
  HTTP/1.1 200 OK
  Content-Type: text/html
  <html>...</html>

Step 7: Browser renders HTML
  Parses HTML → requests CSS/JS/images → renders DOM
```

### 1.2 HTTP vs HTTPS vs HTTP/2 vs WebSocket

```
HTTP/1.1:
  One request = one connection. Browser needs 6 images → opens 6 connections.
  Sequential requests → slow.

HTTP/2:
  Multiplexing: many requests over ONE connection simultaneously.
  Header compression: reduces overhead.
  Used by: most modern web apps.

HTTPS:
  HTTP over TLS. Same protocol, encrypted transport.
  All data encrypted → safe on public wifi.

WebSocket:
  Persistent, bidirectional connection. Server can PUSH data to client without client asking.
  Use when: chat, live notifications, stock prices, online gaming.
  
  Regular HTTP:
    Client: "Any new messages?" (polling every 5 seconds)
    Server: "No."  (99% of the time)
    → Wasteful
  
  WebSocket:
    Client connects once.
    Server: "New message just arrived!" (whenever it arrives)
    → Efficient for real-time

REST vs GraphQL:
  REST: Fixed endpoints. GET /users/123, GET /users/123/posts (multiple round trips)
  GraphQL: One endpoint. Client specifies exactly what fields it needs.
    → Useful when clients have varying data needs (mobile vs web)
```

### 1.3 CDN (Content Delivery Network)

```
Problem: User in Mumbai requests image stored in US server.
  Distance = 13,000 km. Speed of light ≈ 200,000 km/s in fiber.
  Round trip latency ≈ 130ms just for physics. Plus processing = 200-300ms.
  Terrible for interactive apps.

Solution: CDN
  Cache static content (images, CSS, JS, videos) at 200+ locations worldwide.
  
  Without CDN:
    User in Mumbai → US server → 300ms

  With CDN (edge server in Mumbai):
    First request: Mumbai CDN → US origin → 300ms (cache miss)
    Second request: Mumbai CDN → 5ms (cache hit! content already there)

  CDN handles: Netflix (videos), Cloudflare, Akamai, AWS CloudFront.

What belongs on CDN:
  ✓ Images, videos, CSS, JavaScript, fonts, HTML (static)
  ✗ Personalised data, real-time data, server-rendered pages with user data
```

---

## TOPIC 2: Scalability — Handling More Load

### 2.1 Vertical vs Horizontal Scaling

```
VERTICAL SCALING ("Scale Up"):
  Buy a bigger machine. Add more RAM/CPU/disk.
  
  Example: Your web server has 8GB RAM, 4 cores.
  Traffic grows → upgrade to 64GB RAM, 32 cores.
  
  Pros:  Simple (same code, no architecture change)
  Cons:  LIMIT exists — there's a maximum machine size.
         Single point of failure — if it dies, everything dies.
         Expensive (big machines cost exponentially more)
         Downtime during upgrade.

HORIZONTAL SCALING ("Scale Out"):
  Add more machines. Same code runs on 10 machines instead of 1.
  
  Example: 10 identical 8GB/4-core machines behind a load balancer.
  
  Pros:  Theoretically infinite scale.
         No single point of failure (SPOF).
         Cheaper (commodity hardware).
  Cons:  More complex. Stateful apps are hard to scale horizontally.
         Need to coordinate between machines (distributed systems).

RULE: Stateless services scale horizontally easily. 
      Stateful services (databases) require special handling (sharding, replication).
```

### 2.2 The Scalability Bottleneck Checklist

```
When your app is slow, bottleneck is usually ONE of:

1. CPU: computation-bound tasks (image processing, ML inference)
   Fix: scale horizontally, use worker queues, move to GPU

2. Memory: too much in-memory state
   Fix: Redis/Memcached for caching, paginate queries

3. Disk I/O: slow database queries
   Fix: add indexes, read replicas, caching layer, sharding

4. Network I/O: too many network calls
   Fix: batch requests, use CDN, move services closer, reduce payload size

5. Database connections: too many concurrent connections
   Fix: connection pooling (PgBouncer), read replicas

DIAGNOSIS: Before designing, identify what's currently the bottleneck.
```

---

## TOPIC 3: Load Balancing

### 3.1 What Is a Load Balancer?

```
You have 3 web servers (Server A, B, C), each can handle 100 req/s.
Total capacity = 300 req/s.

Without load balancer: all 300 req/s hit Server A → overloaded. B and C idle.
With load balancer: routes ~100 req/s to each → all three balanced.

Load balancer = traffic cop. Distributes incoming requests across available servers.
```

### 3.2 Load Balancing Algorithms

```
ROUND ROBIN:
  Requests go 1→A, 2→B, 3→C, 4→A, 5→B, 6→C, ...
  Simple. Works when all servers are identical.
  Problem: Server A gets a heavy request while B,C get light ones → still unbalanced by work.

WEIGHTED ROUND ROBIN:
  Server A: weight=3, Server B: weight=2, Server C: weight=1.
  Pattern: A,A,A,B,B,C,A,A,A,B,B,C,...
  Use when: servers have different capacities.

LEAST CONNECTIONS:
  Route to server with FEWEST active connections.
  Better than round robin for long-lived connections (e.g., file uploads).
  
  State: A=5 connections, B=3 connections, C=8 connections.
  Next request → B (fewest).

IP HASH (Sticky Sessions):
  hash(client_IP) % num_servers → always same server for same client.
  Use when: server stores session state (user is logged in).
  Problem: if that server dies, session lost. Better: use Redis for session storage.

LEAST RESPONSE TIME:
  Route to server with lowest average response time AND fewest connections.
  Most sophisticated. Used by Nginx.
```

### 3.3 Layer 4 vs Layer 7 Load Balancing

```
LAYER 4 (Transport Layer — IP + Port):
  Routes based on IP/TCP header only. Can't see HTTP content.
  Faster (no HTTP parsing). Used for raw TCP routing.
  Example: AWS NLB (Network Load Balancer)

LAYER 7 (Application Layer — HTTP):
  Reads HTTP request. Can route based on URL path, headers, cookies.
  Example:
    /api/* → API servers
    /static/* → CDN or static file servers
    Host: mobile.app.com → mobile-optimised servers
  Slower (more processing) but smarter.
  Example: AWS ALB (Application Load Balancer), Nginx

FOR INTERVIEWS: Usually assume L7 load balancer unless stated otherwise.
```

### 3.4 Health Checks

```
Load balancer constantly pings each server:
  GET /health → 200 OK → server is healthy
  GET /health → timeout/500 → server is unhealthy → stop routing traffic

Without health checks: traffic gets sent to crashed servers → user errors.
With health checks: failed server removed automatically within seconds.

Health check includes: HTTP status, response time, DB connectivity check.
```

---

## TOPIC 4: Caching

### 4.1 Why Cache?

```
Database query: 50-100ms
In-memory cache (Redis): < 1ms

If 1000 users read the same "Top trending articles" page:
  Without cache: 1000 × 100ms = 100 seconds of DB time (1000 concurrent queries)
  With cache: 1 × 100ms (first query) + 999 × 1ms = ~1 second

Cache = pre-computed answers stored close to the requester.
```

### 4.2 Cache Hit / Cache Miss

```
Cache HIT:  Data found in cache → return immediately. 
Cache MISS: Data NOT in cache → fetch from DB → store in cache → return.

Cache Hit Rate = hits / (hits + misses)
Good caching: > 90% hit rate.
If hit rate = 30%: cache not worth it for that use case.

Example: "User profile" query
  User opens app: MISS (first time today) → DB query → cache for 5 min
  User refreshes: HIT → instant response
  User refreshes again: HIT
  ...
  5 minutes later: MISS (cache expired) → DB query again
```

### 4.3 Cache Eviction Policies

```
Cache has LIMITED space. What to remove when full?

LRU (Least Recently Used): Remove the item not used longest.
  Items: [A, B, C, D]. Cache size = 3.
  Access order: A, B, C, A, D
    After A: [A]
    After B: [A, B]
    After C: [A, B, C] — full
    Access A: [B, C, A] — A moved to front (most recent)
    Access D: cache full → evict B (least recently used) → [C, A, D]
  
  Used by: Redis (allkeys-lru), most browser caches.

LFU (Least Frequently Used): Remove item accessed fewest times.
  Better for long-term popular items. More complex to implement.

TTL (Time-To-Live): Items expire after N seconds.
  Simplest. Good for time-sensitive data (stock prices, trending topics).

FIFO: Evict oldest-inserted item. Simple but ignores access patterns.
```

### 4.4 Cache Invalidation — The Hardest Problem

```
"There are only two hard things in CS: cache invalidation and naming things." — Phil Karlton

Problem: User updates their profile. Old profile is cached for 10 minutes.
→ Cache has STALE data. User sees old name.

Strategies:

1. TTL (Time-based expiry):
   Cache profile for 5 minutes. Auto-expires.
   Pros: Simple. 
   Cons: Stale for up to 5 minutes. Balance: shorter TTL = more DB load.

2. Cache-Aside (Lazy Loading):
   Read: check cache → miss → read DB → write cache → return
   Write: update DB → DELETE from cache (not update!)
   Next read: miss → reads fresh data from DB → recaches
   
   Code pattern:
     def get_user(user_id):
       user = cache.get(f"user:{user_id}")
       if not user:
           user = db.query("SELECT * FROM users WHERE id=?", user_id)
           cache.set(f"user:{user_id}", user, ttl=300)
       return user
     
     def update_user(user_id, data):
       db.execute("UPDATE users SET ... WHERE id=?", user_id)
       cache.delete(f"user:{user_id}")   # invalidate, not update
   
   Most common pattern. Simple. Resilient (cache failure → falls back to DB).

3. Write-Through:
   Write to cache AND DB simultaneously on every write.
   Pros: Cache always consistent.
   Cons: Write penalty (2 writes). Cache fills with data that may not be read again.

4. Write-Behind (Write-Back):
   Write to cache only → async flush to DB later.
   Pros: Very fast writes.
   Cons: Data loss risk if cache dies before flush.
   Use: High-write workloads where some loss is acceptable (analytics counters).
```

### 4.5 Cache Problems at Scale

```
CACHE STAMPEDE (Thundering Herd):
  Popular item's TTL expires. 1000 simultaneous requests all miss.
  → 1000 concurrent DB queries for same data!

  Fix: Mutex lock on cache miss. Only one request fetches from DB, rest wait.
  Fix: Probabilistic early expiry (extend TTL randomly near expiry)
  Fix: Background refresh (async refresh before TTL expires)

CACHE PENETRATION:
  User requests item that DOESN'T EXIST in DB.
  Cache miss → DB query → nothing found → not cached → next request: same thing.
  Malicious actor can spam fake IDs → DDoS your DB.
  
  Fix: Cache negative results ("user:9999 → NULL") with short TTL.
  Fix: Bloom filter. Fast probabilistic check: "does user 9999 exist?" 
       Bloom filter says NO → don't even query DB.

CACHE AVALANCHE:
  Many cached items expire simultaneously (same TTL set for all).
  → Sudden spike of DB queries.
  
  Fix: Random TTL jitter. Instead of all expiring at 300s:
       TTL = 300 + random.randint(-30, 30)
  Fix: Stagger cache warming on startup.
```

---

## TOPIC 5: Databases

### 5.1 SQL vs NoSQL — When to Use What

```
SQL (Relational):
  Data stored in tables with fixed schema (rows and columns).
  Strong ACID guarantees (Atomicity, Consistency, Isolation, Durability).
  JOINs for related data.
  Examples: PostgreSQL, MySQL, SQLite

  Use when:
    - Data has clear relationships (users ↔ orders ↔ products)
    - Need complex queries (aggregations, JOINs)
    - Data is structured and unlikely to change schema often
    - Strong consistency required (banking, inventory)

NoSQL:
  Document DB (MongoDB): JSON-like documents. Flexible schema.
    Use when: Varying document structure, content management, user profiles
    
  Key-Value (Redis, DynamoDB): Simple get/set by key.
    Use when: Caching, sessions, real-time leaderboards
    
  Wide-Column (Cassandra, HBase): Rows with dynamic columns.
    Use when: Time-series data, IoT sensor data, write-heavy workloads
    
  Graph (Neo4j): Nodes and edges.
    Use when: Social graphs, recommendation engines, fraud detection

COMMON MISTAKE: Choosing NoSQL just because it sounds "modern."
SQL with proper indexing handles millions of rows easily.
```

### 5.2 Indexing — The Most Important Performance Tool

```
Without index: query scans EVERY row (O(n)).
With index: B-tree lookup O(log n) or hash lookup O(1).

CREATE INDEX idx_user_email ON users(email);
SELECT * FROM users WHERE email = 'alice@example.com';
  Without index: scan all 10 million users → 5 seconds
  With index: tree lookup → 1 ms

How B-tree index works:
  B-tree is a balanced tree. Leaf nodes contain actual row references.
  
  emails sorted in tree: alice@ → bob@ → charlie@ → ...
  Search for alice@: 
    root → compare → right branch → compare → leaf → row pointer → 1ms!

Cost of indexes:
  - Every INSERT/UPDATE/DELETE must also update all indexes.
  - Each index uses disk space (~10-30% of table size).
  - Too many indexes: write slowdown.
  - Rule: Index columns used in WHERE, JOIN ON, ORDER BY. Not all columns.

Composite Index:
  INDEX (user_id, created_at)  → supports queries like:
    WHERE user_id = 123 AND created_at > '2024-01-01'  → uses index ✓
    WHERE user_id = 123  → uses index ✓ (leftmost prefix)
    WHERE created_at > '2024-01-01'  → CANNOT use index ✗ (not leftmost prefix)
```

### 5.3 Database Replication

```
ONE DB server → single point of failure. If it crashes, everything crashes.
One server can only handle so many read queries.

Solution: Replication
  Primary (Master): handles all WRITES
  Replicas (Slaves): copies of primary, handle READS
  Async replication: writes go to primary → periodically synced to replicas

Example (Instagram-scale):
  10 million read queries/sec, 100,000 write queries/sec
  → 10 replicas each handling 1M reads/sec
  → Primary handles 100K writes/sec

Replication lag:
  Async replication: primary might be 1-2 seconds ahead of replicas.
  User writes post → immediately reads it → replica hasn't caught up → sees old version.
  
  Fix: Read your own writes: route user's reads to primary for 5 seconds after write.
  Fix: Wait for replication acknowledgement (sync replication) — slower writes.
```

### 5.4 Database Sharding (Partitioning)

```
Single DB: maximum ~10TB storage, ~100K writes/sec. What if you need more?

Sharding: split data across multiple DB servers.
Each shard handles a subset of data.

Example: Users table with 1 billion rows.
  Shard by user_id:
    Shard 0: user_id 0 to 249,999,999
    Shard 1: user_id 250,000,000 to 499,999,999
    Shard 2: user_id 500,000,000 to 749,999,999
    Shard 3: user_id 750,000,000 to 999,999,999

  Query "get user 350,000,000":
    shard = user_id // 250,000,000 = 1 → query Shard 1

Sharding strategies:
  1. Range sharding: shard by value range (above). Simple but uneven (hot shards).
  2. Hash sharding: shard = hash(key) % num_shards. Even distribution.
  3. Directory sharding: lookup table maps key → shard. Most flexible.

Problems with sharding:
  - JOINs across shards: hard! Must denormalise or do in application code.
  - Transactions across shards: very hard! Use Saga pattern.
  - Resharding: adding more shards requires moving data (consistent hashing helps).
  - Hot shards: if one shard gets disproportionate traffic.
```

### 5.5 Consistent Hashing

```
Problem with naive hash sharding:
  4 shards: shard = hash(key) % 4
  You add a 5th shard: now shard = hash(key) % 5
  ALMOST EVERY KEY maps to a different shard! Need to move ~80% of data. 

Consistent Hashing:
  Arrange shard IDs on a circle (hash ring) 0 to 2^32.
  Place shard nodes at positions on the ring.
  Place each key on the ring at hash(key).
  Key belongs to the nearest shard in clockwise direction.

  Ring: ──[Shard A]──────[Shard B]──────[Shard C]──────[Shard D]──
  Key K1 lands between A and B → belongs to B.
  Key K2 lands between C and D → belongs to D.

  Add Shard E between B and C:
  Only keys between B and E move to E!
  All other keys stay where they are.
  → Only ~1/N of keys need to move (N = number of shards).

Virtual nodes (vnodes): Each physical shard has multiple positions on ring.
  → Better load distribution.
  → When a shard is removed, its load spreads evenly.

Used by: Amazon DynamoDB, Apache Cassandra, Redis Cluster.
```

---

## TOPIC 6: Message Queues

### 6.1 Why Message Queues?

```
Scenario: User uploads photo on Instagram.
  App needs to:
  1. Store original photo in S3
  2. Generate 5 thumbnail sizes
  3. Run content moderation ML model
  4. Update user's feed
  5. Notify followers

Without queue:
  All done synchronously before returning response.
  User waits 10 seconds. CPU spikes on photo upload.
  If step 3 fails: whole request fails and user gets error.

With message queue:
  App stores photo → puts message in queue → responds "uploaded!" to user immediately.
  Background workers consume message and do steps 2-5 asynchronously.
  User gets instant response. Steps 2-5 happen in background over next few seconds.
  If step 3 fails: message goes back to queue → retry automatically.
```

### 6.2 Queue vs Pub/Sub

```
QUEUE (Point-to-Point):
  One producer, one consumer per message.
  Message consumed by ONE worker, then deleted.
  Use when: task distribution (one task done by one worker).
  
  Producers → [Queue] → Worker A handles msg 1
                      → Worker B handles msg 2
                      → Worker C handles msg 3
  
  Example: Email job queue. Each email sent by exactly one worker.

PUB/SUB (Publish-Subscribe):
  One publisher, MANY subscribers.
  Each subscriber gets a copy of each message.
  
  Photo uploaded (event) → ALL of these happen:
    Thumbnail service receives it
    Moderation service receives it
    Analytics service receives it
    Notification service receives it
  
  Each service gets its OWN copy.
  Use when: broadcasting events to multiple consumers.
  Example: Kafka, Google Pub/Sub, AWS SNS+SQS.

RULE: Use Queue for tasks, Pub/Sub for events.
```

### 6.3 Kafka Architecture (Used by LinkedIn, Uber, Netflix)

```
Kafka concepts:

TOPIC: Named stream of messages. Like a table in DB.
  "user-clicks", "payment-events", "photo-uploads"

PARTITION: Topic split into ordered, append-only logs.
  "payment-events" → Partition 0, Partition 1, Partition 2 (on different machines)
  → Parallel processing, fault tolerance.

PRODUCER: Writes messages to a topic.
  message = { key: "user_123", value: "{event: 'click', page: '/home'}", timestamp: ... }

CONSUMER GROUP: Set of workers that together consume a topic.
  Each partition consumed by exactly one consumer in the group.
  3 partitions + 3 consumers → parallel processing.

OFFSET: Position of consumer in partition. Consumer tracks its own offset.
  Can replay from any offset → reprocessing historical data.

Retention: Kafka retains messages for N days (default 7), not just until consumed.
  Multiple consumer groups can read same topic independently.
  Analytics job reads all events. Real-time service reads same events. Neither affects the other.

Throughput: Millions of messages per second. Used for:
  - Real-time analytics (Uber driver location updates)
  - Event sourcing (audit logs)
  - Data pipelines (ETL)
```

---

## TOPIC 7: CAP Theorem

### 7.1 The Three Properties

```
Every distributed system can provide at most 2 of these 3 guarantees:

C — Consistency:
  Every read receives the MOST RECENT write or an error.
  All nodes see the SAME data at the same time.
  Example: After you transfer $100, your balance immediately shows the correct amount
           from any server anywhere.

A — Availability:
  Every request receives a response (not necessarily most recent data).
  The system is always up and responding (even if data might be slightly stale).
  Example: You always get a response, even if a server is down.

P — Partition Tolerance:
  System continues operating even when network messages are dropped or delayed
  (network partition = some servers can't communicate with others).

WHY ONLY 2 OF 3?
  In a distributed system, network partitions are INEVITABLE.
  (Networks fail, packets get lost, servers reboot)
  
  So in practice: you must choose P.
  Real choice: CP or AP.

CP (Consistency + Partition Tolerance):
  When partition occurs: refuse some requests (sacrifice Availability) to stay consistent.
  Example: "I'd rather say 'error, try later' than give you wrong data."
  Systems: HBase, MongoDB (strong consistency mode), Zookeeper
  Use for: banking, inventory, medical records — correctness critical.

AP (Availability + Partition Tolerance):
  When partition occurs: continue serving requests (may return stale data).
  Example: "I'll give you my best guess of the data, might be slightly old."
  Systems: Cassandra, DynamoDB, CouchDB
  Use for: social feeds, product recommendations — slight staleness OK.
```

### 7.2 Real-World Example

```
Amazon Shopping Cart: AP system
  You add items to cart on your phone. Network flakiness.
  AP choice: cart is always available. Adds go through even if servers partitioned.
  Eventual consistency: all servers eventually agree on cart contents.
  Downside: might briefly see stale cart count.
  
  Why not CP? You'd rather be able to add items (availability) than get an error.

Bank Transfer: CP system
  Transfer $1000 from Account A to Account B.
  Must deduct from A AND credit to B atomically.
  Network partition? Return error. Do NOT proceed with partial transfer.
  
  Why not AP? "Your $1000 is gone but the receiver might not have it yet" is unacceptable.
```

---

## TOPIC 8: Consistency Models

```
Strongest to weakest:

LINEARIZABILITY (Strong Consistency):
  After write completes, ALL subsequent reads see that write.
  Every operation appears instantaneous.
  Like a single-threaded program. Most intuitive.
  Cost: High latency (must coordinate across all nodes).

SEQUENTIAL CONSISTENCY:
  All operations appear in some total order. 
  Each node sees all writes in same order, but may not see other node's writes immediately.
  Less strict than linearizability.

CAUSAL CONSISTENCY:
  If operation A causes operation B, everyone sees A before B.
  Unrelated operations can be in any order.
  Example: Comment on post must appear after post. Other unrelated posts can appear in any order.

EVENTUAL CONSISTENCY:
  Given no new updates, all replicas will EVENTUALLY converge to same value.
  No guarantee on how long. Could be milliseconds or seconds.
  Most available, least consistent.
  
  Example: DNS. Update domain → can take 24-48 hours to propagate worldwide.
           During that time, different DNS servers return different IPs.
           Eventually: all servers see the correct IP.
  
  Example: Cassandra reads. Might see slightly stale data. Usually within milliseconds.
```

---

## TOPIC 9: API Design

### 9.1 REST Design Principles

```
REST = Representational State Transfer. 6 constraints:
1. Client-Server: UI and backend separated.
2. Stateless: Server stores no session state. Each request self-contained.
3. Cacheable: Responses labeled as cacheable or not.
4. Uniform Interface: Standard resource-based URLs.
5. Layered System: Client doesn't know if talking to server directly or load balancer.

GOOD REST API DESIGN:

Resource Naming (nouns, not verbs):
  ✓ GET /users/123           (get user 123)
  ✗ GET /getUser?id=123      (verb in URL)
  
  ✓ POST /users              (create user)
  ✗ POST /createUser         
  
  ✓ DELETE /users/123        (delete user)
  ✗ POST /deleteUser/123     (wrong method)

HTTP Methods:
  GET:    Read. No side effects. Safe to retry. Cacheable.
  POST:   Create. Not idempotent (calling twice creates two resources).
  PUT:    Replace entire resource. Idempotent.
  PATCH:  Update partial resource. Idempotent.
  DELETE: Remove. Idempotent.

Nested Resources:
  GET /users/123/posts        (all posts by user 123)
  GET /users/123/posts/456    (specific post by user 123)
  POST /users/123/posts       (create post for user 123)

Status Codes:
  200 OK             Request succeeded
  201 Created        POST successful, new resource created
  204 No Content     DELETE successful
  400 Bad Request    Client error (validation failed)
  401 Unauthorized   Not authenticated
  403 Forbidden      Authenticated but not allowed
  404 Not Found      Resource doesn't exist
  429 Too Many Requests  Rate limited
  500 Internal Server Error  Server bug

Pagination:
  GET /posts?page=2&limit=20             (page-based)
  GET /posts?cursor=eyJpZCI6MTAwfQ==     (cursor-based — better for large datasets)
  Response includes: {data: [...], next_cursor: "...", has_more: true}

Versioning:
  /api/v1/users   vs   /api/v2/users   (URL versioning — most common)
  Accept: application/vnd.api.v2+json  (header versioning)
```

---

```

---

## TOPIC 10: Numbers Every Engineer Should Know

```
Memory latency hierarchy:
  L1 cache:    ~1 ns        (reading same machine's RAM cache)
  L2 cache:    ~4 ns
  RAM:         ~100 ns
  SSD:         ~100 μs      (1,000× slower than RAM)
  HDD:         ~10 ms       (100,000× slower than RAM)
  Network (same DC): ~1 ms
  Network (cross-region): ~100 ms

Common throughput:
  Single server: ~10,000 req/s (typical web app)
  Redis: ~1,000,000 ops/sec
  Kafka: ~1,000,000 msg/sec per partition
  PostgreSQL: ~100,000 read queries/sec (with good hardware)
  MySQL write: ~10,000 writes/sec

Storage:
  1 char = 1 byte
  UUID = 36 bytes
  Average tweet = 280 chars = 280 bytes
  Average photo = 3 MB
  1GB = 10^9 bytes
  1TB = 10^12 bytes

Time:
  1 day = 86,400 seconds ≈ 10^5
  1 month = 2.6M seconds
  1 year = 31.5M seconds

CAPACITY ESTIMATION EXAMPLE (Twitter):
  300M users. 50% daily active = 150M DAU.
  Each user tweets 0.5x/day average = 75M tweets/day.
  Tweets/sec = 75M / 86400 ≈ 870 tweets/sec (TPS).
  Peak TPS = 10× average = 8,700 TPS.
  
  Storage per tweet = 140 chars + metadata = ~500 bytes.
  Storage/day = 75M × 500 bytes = 37.5 GB/day.
  Storage/year = 37.5 × 365 = ~14 TB/year.
  5 years: 70 TB of tweet data.
```

---

## TOPIC 11: Real-World Examples — One Per Building Block

> These are the anchors to use in interviews: "Facebook does X because…", "Uber solved this by…"

---

### 11.1 Networking — How Cloudflare Works

```
Problem: Cloudflare serves 55 million HTTP requests/second across 300 cities.

Key decisions:
  1. Anycast routing: ALL Cloudflare data centres share the SAME IP address.
     Your DNS request routes you to the NEAREST data centre automatically.
     Result: User in Mumbai → Mumbai PoP (5ms), not Virginia (200ms).

  2. TLS termination at the edge:
     Cloudflare decrypts HTTPS at the nearest PoP, then forwards
     plain HTTP (or re-encrypted) to origin server.
     Result: TLS handshake is cheap (geographically close).

  3. HTTP/2 push:
     Cloudflare sends CSS and JS to browser BEFORE it asks for them,
     by reading the HTML and predicting what will be needed.
     Result: Eliminates 1-2 round trips per page load.

Real numbers:
  Without Cloudflare CDN: India → US TLS handshake = 280ms
  With Cloudflare:        India → Mumbai PoP       =  12ms
  Speedup: 23×
```

---

### 11.2 Scalability — How Twitter Scaled to 400M Users

```
Problem: Twitter's "celebrity problem." Lady Gaga has 140M followers.
When she tweets, 140M users' home timelines must be updated.

Naive approach: Fan-out on read.
  User opens app → query "give me latest tweets from everyone I follow"
  → JOIN across 140M followed users → takes 10 seconds. Unusable.

Twitter's solution: Fan-out on write (pre-computed timelines).
  Lady Gaga tweets → worker pushes tweet ID to 140M timelines.
  User opens app → reads their pre-computed timeline from Redis.
  Result: Read = 1ms (Redis lookup). Write = slow but happens in background.

Problem with fan-out on write: 140M writes take ~3 minutes for one tweet.
  During those 3 minutes, some followers see tweet, others don't.

Hybrid approach (what Twitter actually does):
  For regular users (< 50,000 followers): fan-out on write.
  For celebrities (> 50,000 followers): fan-out on read.
  At read time: merge pre-computed timeline + celebrity tweets.
  Best of both: fast reads, manageable write volume.

Data store:
  Home timeline: Redis (sorted set, key=user_id, score=timestamp, value=tweet_id)
  Timeline size cap: store only latest 800 tweet IDs per user.
  Tweet content: MySQL (source of truth). Redis only stores tweet IDs.
```

---

### 11.3 Load Balancing — How Netflix Routes 1 Billion Hours/Day

```
Netflix architecture:
  All traffic enters via AWS (eu-west, us-east, etc.).
  Zuul = Netflix's custom API gateway (open source, now widely used).

Zuul does:
  1. Authentication check (validate JWT token)
  2. Rate limiting (per user, per device)
  3. A/B routing (10% of users → experimental service)
  4. Dynamic routing (canary deployments)

# Simplified Zuul routing config (conceptual):
routes:
  - path: /api/account/**
    service: account-service
    filters:
      - AuthFilter      # validates token
      - RateLimitFilter # 100 req/min per user
  - path: /api/streaming/**
    service: streaming-service
    canary:
      percentage: 5     # 5% → new version, 95% → stable

Health check strategy:
  Eureka (Netflix's service registry) tracks which instances are healthy.
  Each service reports heartbeat every 30 seconds.
  If no heartbeat for 90 seconds → Eureka removes instance from pool.
  Zuul reads Eureka → automatically stops routing to dead instances.

Result: Netflix handles 500,000+ concurrent streams without manual intervention.
```

---

### 11.4 Caching — How Instagram Caches 500M Stories/Day

```
Instagram caching layers for Stories:

L1: TAO (Graph cache, Facebook-built):
    Caches social graph: who follows whom.
    Stored in sharded Redis-like store.
    Hit rate: ~99%. Almost no story-view needs a DB graph query.
    
L2: Memcache cluster (for story content metadata):
    Key: "story:{story_id}" → {owner_id, url, created_at, expires_at}
    TTL: 24 hours (stories expire in 24h anyway — TTL = natural expiry).
    Cache hit rate: ~95% for popular stories.
    
L3: Cassandra (story index per user):
    Key: user_id → [list of story IDs, sorted by timestamp].
    Stories deleted from Cassandra after 24h (TTL column in Cassandra).

Cache invalidation (the interesting part):
  Stories can't be "invalidated early" by users — Instagram doesn't support
  deleting a story from cache. Instead: check expiry at read time.
  Read story → check if expires_at < now → if expired, return empty. Simple.

Cold start problem (new user):
  New users have no cache. Every new follower triggers cache miss.
  Fix: Consistent hashing ensures new user's data always goes to same Redis shard.
  First follower → miss → DB → populate. Second follower → hit.

Numbers:
  Instagram serves 6 billion story views/day.
  Without caching: 6B × 5ms DB query = 8.3 hours of DB time per second. Impossible.
  With cache (95% hit): 300M DB queries/day vs 6B → 20× fewer DB calls.
```

---

### 11.5 Database Indexing — Uber's Trip Lookup

```
Problem: Uber stores 10 billion trips. Driver needs to see their last 30 days.
  Query: SELECT * FROM trips WHERE driver_id = 123 AND started_at > (now - 30d)
         ORDER BY started_at DESC LIMIT 50;

Without index: Full table scan 10B rows. Even on fast SSD: ~100 seconds.

Index design:
  CREATE INDEX idx_driver_trips 
  ON trips (driver_id, started_at DESC);
  
  Now query hits the index:
  → B-tree finds driver_id = 123 leaf in milliseconds
  → Scans only that driver's rows sorted by date descending
  → Stops after 50 rows
  → Total: ~2ms

Why composite index (driver_id, started_at), not just (driver_id)?
  Single-column index on driver_id: narrows to all trips for that driver (could be 50,000).
  Still needs to scan and sort by started_at → slow.
  Composite with started_at: rows already sorted in index → no sort step → fast.

Partial index (advanced):
  CREATE INDEX idx_active_trips ON trips (driver_id)
  WHERE status IN ('requested', 'in_progress');
  
  Most queries are about ACTIVE trips, not historical.
  Partial index is 100× smaller → faster lookup → less memory.
  
  Uber has billions of historical trips but only thousands active at any time.
  Index the 0.001% that matters for real-time operations.
```

---

### 11.6 Message Queue — How Airbnb Uses Kafka for Search Updates

```
Problem: Host updates listing (new photos, price change).
  → Search index must update within 5 minutes.
  → But search index (Elasticsearch) is eventually consistent.

Direct DB → ES sync (WRONG approach):
  On every DB write: immediately call ES.update() synchronously.
  → Every listing update adds 200ms latency to the update endpoint.
  → If ES is down, listing update fails entirely (cascading failure).
  → Search and booking are now COUPLED (fragile).

Kafka approach (Airbnb's actual design):
  
  Listing Service writes to DB.
  DB (PostgreSQL) → Debezium CDC → Kafka topic "listing-changes"
  
  Kafka topic "listing-changes":
    Partitioned by listing_id (ensures order per listing)
    Retention: 7 days
  
  Consumers:
    [Search Indexer] → reads from Kafka → updates Elasticsearch
    [Photo CDN]      → reads from Kafka → purges stale CDN cache
    [Analytics]      → reads from Kafka → updates BI dashboards
    [Recommendations]→ reads from Kafka → rebuilds recommendation features

Benefits:
  Listing update endpoint is fast (just DB write, no ES coupling).
  ES can be down: Kafka buffers events, replays when ES recovers.
  New consumer (e.g., fraud detection): just subscribe to Kafka, no listing service change.
  
# Kafka consumer code (Python, simplified):
from confluent_kafka import Consumer

consumer = Consumer({
    "bootstrap.servers": "kafka-cluster:9092",
    "group.id": "search-indexer-group",
    "auto.offset.reset": "earliest"
})
consumer.subscribe(["listing-changes"])

while True:
    msg = consumer.poll(timeout=1.0)
    if msg and not msg.error():
        listing = json.loads(msg.value())
        es_client.index(index="listings", id=listing["id"], body=listing)
        # Kafka auto-commits offset after processing
```

---

### 11.7 CAP Theorem — Amazon Shopping Cart (AP) vs Bank Ledger (CP)

```
AMAZON CART — AP (Dynamo paper, 2007):
  Key insight: Amazon would rather accept a duplicate item in cart
  than show "Service Unavailable" during network partition.
  
  Implementation: DynamoDB with eventual consistency.
  Conflict resolution: last-write-wins OR CRDT (add-only counter for item quantities).
  
  CRDT cart example:
    Node A: {item: "shoes", qty: 2}  (user added 1 more on mobile)
    Node B: {item: "shoes", qty: 2}  (network partition, missed the update)
    On merge: take the MAX → qty = 2. Correct.
  
  User impact: During 1-second partition, cart might show 1 shoe instead of 2.
               When connectivity restored: merges correctly.
               Better than: "Cart unavailable during checkout." (lost sale!)

BANK LEDGER — CP (Strong consistency):
  $1000 transfer from Account A to Account B.
  Must be ATOMIC: deduct A AND credit B or neither.
  
  Implementation: PostgreSQL with ACID transactions.
  
  -- This transaction is atomic:
  BEGIN;
    UPDATE accounts SET balance = balance - 1000 WHERE id = 'A' AND balance >= 1000;
    UPDATE accounts SET balance = balance + 1000 WHERE id = 'B';
    INSERT INTO transactions (from_id, to_id, amount) VALUES ('A', 'B', 1000);
  COMMIT;
  
  Network partition? ROLLBACK. Return error to user.
  User impact: "Transfer unavailable right now. Try again." (annoying but safe.)
  Better than: partial transfer where $1000 leaves A but never reaches B.
  
LESSON: There is no "correct" choice. It depends entirely on what failure is worse.
  Cart: inconsistency is worse than unavailability? No → choose AP.
  Bank: inconsistency is worse than unavailability? YES → choose CP.
```

---

### 11.8 Consistency Models — How Google Spanner Achieves Linearizability

```
Google Spanner: globally distributed SQL database. Used by Google Ads (= billions of dollars).

Challenge: Data in data centres across US, EU, Asia.
Goal: Linearizability (every read sees the most recent write, globally).

Problem: Speed of light means US → Asia takes 130ms. 
         How can a write in US be visible in Asia "instantly"?

Spanner's solution: TrueTime API.
  GPS receivers + atomic clocks in every Google data centre.
  TrueTime.now() returns: [earliest, latest] — a time interval, not a point.
  Uncertainty: typically ±7ms.

  Write protocol:
    1. Start transaction. Record TrueTime.now() → [T_early, T_late].
    2. Write data.
    3. Commit, but WAIT until T_late has definitively passed (commit wait ~14ms).
    4. Now timestamp is definitely in the past for ALL clocks everywhere.
    5. Any read with timestamp > T_late will see this write.

  Result: Global linearizability at the cost of ~14ms commit wait.
  This is WHY Google Ads never shows you a stale price — billions depend on it.

For interviews:
  "Spanner solves this with atomic clocks and commit wait."
  Most interviewers will be impressed. Few candidates know this.
  
  Alternative (most systems): Use logical clocks (Lamport timestamps, vector clocks)
  instead of physical clocks. No 14ms wait but weaker guarantees.
```

---

### 11.9 API Design — Stripe's Idempotency Key Pattern

```
Problem: Network error during payment.
  Client sends POST /charges (charge $100).
  Network drops response AFTER Stripe processes it.
  Client retries → charges $100 AGAIN → double charge!

Solution: Idempotency Keys.

Client generates a unique key per request attempt:
  key = f"order_{order_id}_attempt_{attempt_number}"  # e.g., "order_9921_attempt_1"

Request:
  POST /v1/charges
  Idempotency-Key: order_9921_attempt_1
  Body: {amount: 10000, currency: "usd", customer: "cus_123"}

Stripe's server:
  1. Check Redis: has key "idempotency:order_9921_attempt_1" been seen before?
  2. NO (first time):
     - Process charge → store result in Redis (key → response, TTL: 24h) → return response.
  3. YES (duplicate request):
     - Return CACHED response. Do NOT process again.

Redis operation (atomic):
  SET idempotency:{key} {response} NX EX 86400
  # NX = only set if NOT EXISTS. Atomic. Safe for concurrent duplicates.

Result:
  Client can safely retry on network error.
  Stripe never double-charges.
  Key expires after 24h (clients shouldn't retry after 24h).

This pattern works for any non-idempotent operation:
  Order creation, fund transfers, SMS sends, email sends.
  
INTERVIEW: "How do you handle retries safely?" → "Idempotency keys stored in Redis."
```

---

### 11.10 Capacity Estimation — Designing for Netflix Scale

```
Given: Netflix
  220 million subscribers. 100 million+ daily active.
  1 billion hours of video watched per day.

Step 1: QPS (requests per second)
  Daily video start requests:
    100M DAU × 2 sessions/day = 200M sessions/day
    Sessions/sec = 200M / 86,400 ≈ 2,300 sessions/sec
    Peak = 5× average = 11,500 req/sec (prime time, 8-10 PM)

Step 2: Bandwidth for streaming
  1B hours/day of video.
  Average bitrate: 5 Mbps (HD streaming).
  Total bandwidth = 1B hours × 3600 sec × 5 Mbps 
                  = 18 × 10^15 bits/day
                  = 18 Petabits/day
                  = 208 Gbps average, peak ~1 Tbps
  
  This is why Netflix uses CDN (Open Connect):
    Netflix has its own CDN hardware in ISP data centres.
    ISP caches Netflix content locally.
    Actual traffic to Netflix origin = ~1% of what users consume.
    Other 99% served from ISP-local Netflix appliances.

Step 3: Storage for content library
  15,000 titles × multiple formats/resolutions.
  Each title → 10 encoding profiles (480p, 720p, 1080p, 4K, HDR, each ~20GB).
  15,000 × 10 × 20GB = 3 Petabytes of content (compressed).
  Replicated 3× across regions = 9 PB.
  Stored on: Amazon S3 (Netflix runs on AWS).

Step 4: Recommendation system scale
  Every user rated 200+ titles = 220M × 200 = 44 billion ratings.
  Matrix factorization model: 44B data points.
  Retrained: weekly (batch), real-time feedback: within session.
  This is why Netflix's homepage is personalized — 200 different homepages
  shown to 200 different users simultaneously.

Interview answer: "Netflix serves ~1 Tbps at peak. They solve it with a custom CDN
(Open Connect) co-located at ISPs. I'd design similarly: origin stores masters,
CDN pushes popular content to edge, 99% of traffic never reaches origin."
```

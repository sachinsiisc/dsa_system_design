# Topic 5: Databases
## HLD Deep Dive | MAANG Interview Ready

---

## 1. SQL vs NoSQL — Decision Framework

```
The most common interview question about databases.
Not "which is better" but "which for THIS use case."

SQL (Relational):
  Data in tables (rows + columns). Fixed schema.
  ACID guarantees: Atomicity, Consistency, Isolation, Durability.
  JOINs for related data.
  Examples: PostgreSQL, MySQL, SQLite, SQL Server, Aurora.

NoSQL:
  Flexible schema. Various data models. Usually BASE (basically available).
  Designed for specific access patterns.
  Types: Document, Key-Value, Wide-Column, Graph, Time-Series.

CHOOSE SQL WHEN:
  ✓ Data has clear relationships (users → orders → products)
  ✓ Need complex queries (multi-table JOINs, aggregations, GROUP BY)
  ✓ Strong consistency required (banking, inventory, medical records)
  ✓ Schema is stable (not changing every sprint)
  ✓ You need ACID transactions (money transfers, order placement)
  ✓ Team knows SQL well (lower learning curve)

CHOOSE NoSQL WHEN:
  ✓ Schema varies per record (documents with different fields)
  ✓ Need horizontal write scaling beyond what one primary can handle
  ✓ Specific access pattern: key lookup, time-series, graph traversal
  ✓ Eventual consistency is acceptable
  ✓ Need flexible schema evolution (add fields without migration)

COMMON MISTAKE: Choosing NoSQL just because it sounds "web scale."
  PostgreSQL with proper indexing handles millions of rows easily.
  Start with PostgreSQL. Switch to NoSQL when you have a specific reason.
```

---

## 2. NoSQL Database Types — When to Use Each

```
DOCUMENT DATABASE (MongoDB, Firestore, DynamoDB):
  Data stored as JSON/BSON documents.
  Each document can have different fields.
  
  Use cases:
    - User profiles (different users have different optional fields)
    - Product catalog (electronics have "voltage", clothing has "size" — different attributes)
    - CMS (blog posts, articles — varying rich text structure)
    - E-commerce catalogs
  
  Schema example:
    {
      "_id": "product_123",
      "name": "Laptop",
      "price": 999.99,
      "specs": { "ram": "16GB", "ssd": "512GB" },  // nested object
      "tags": ["electronics", "sale"],               // array
      "reviews": [...]                               // embedded array
    }
  
  Query: db.products.find({"specs.ram": "16GB", "price": {"$lt": 1000}})
  
  NOT good for: multi-document transactions (improved in MongoDB 4.0+, but still slower).
               Complex relational queries across many document types.

KEY-VALUE STORE (Redis, DynamoDB, Memcached):
  Simplest model: key → value. Only lookup by key.
  Extremely fast O(1) reads and writes.
  
  Use cases:
    - Session storage: "session:abc123" → user data
    - Caching: "product:456" → JSON
    - Rate limiting: "ratelimit:user_123" → count
    - Distributed locks: "lock:payment_789" → 1
    - Feature flags: "feature:dark_mode:user_123" → true/false
  
  Limitation: can only look up by exact key. No range queries.
              Need to know the key upfront.

WIDE-COLUMN STORE (Cassandra, HBase, Google Bigtable):
  Row key + dynamic columns. Columns can differ per row.
  Optimized for massive write throughput and time-series patterns.
  
  Cassandra data model:
    Primary key = partition key + clustering key.
    Partition key: determines which node stores the row.
    Clustering key: determines sort order within partition.
  
  CREATE TABLE messages (
      conversation_id UUID,       -- partition key (all messages in same conversation on same node)
      sent_at         TIMEUUID,   -- clustering key (time-ordered)
      sender_id       UUID,
      content         TEXT,
      PRIMARY KEY ((conversation_id), sent_at)
  ) WITH CLUSTERING ORDER BY (sent_at DESC);
  
  Query: SELECT * FROM messages WHERE conversation_id = ? LIMIT 20;
  → Reads one partition (fast). Never reads across partitions.
  
  Use cases: messaging (WhatsApp), time-series (IoT, metrics), activity feeds.
  
  NOT good for: ad-hoc queries (no multi-column WHERE without index).
               Transactions across multiple partitions.

GRAPH DATABASE (Neo4j, Amazon Neptune):
  Data stored as nodes (entities) and edges (relationships).
  Optimized for graph traversal (find connected nodes).
  
  Use cases:
    - Social networks: "friends of friends" queries
    - Recommendation: "users who bought X also bought Y"
    - Fraud detection: "transactions that form a cycle"
    - Knowledge graphs
  
  Cypher query (Neo4j):
    MATCH (alice:User {name: "Alice"})-[:FOLLOWS]->(bob:User)-[:FOLLOWS]->(carol:User)
    WHERE NOT (alice)-[:FOLLOWS]->(carol)
    RETURN carol.name AS recommendation  // people Alice might want to follow
  
  NOT good for: tabular data, high-volume writes, simple key lookups.

TIME-SERIES DATABASE (InfluxDB, TimescaleDB, Prometheus):
  Optimized for timestamped data (sensor readings, metrics, events).
  Automatic compression of historical data.
  Built-in downsampling (reduce precision of old data).
  
  Use cases: IoT sensor data, application metrics, financial tick data.
  
  InfluxDB example:
    Write: cpu_usage,host=server1,region=us-east value=78.5 1726458600000000000
    Query: SELECT mean(value) FROM cpu_usage WHERE time > now()-1h GROUP BY time(5m)
```

---

## 3. Indexing — The Most Important Performance Tool

```
WITHOUT INDEX: Full table scan — reads every row. O(n).
WITH B-TREE INDEX: Tree lookup. O(log n). 
WITH HASH INDEX: O(1) exact lookup.

CREATE INDEX idx_user_email ON users(email);
SELECT * FROM users WHERE email = 'alice@example.com';

Without index (10M rows): 5 seconds (full scan).
With index: 1ms (B-tree).

HOW B-TREE INDEX WORKS:
  B-tree = balanced tree of sorted keys.
  Each internal node: pointers to ranges.
  Leaf nodes: pointers to actual table rows.
  
  emails sorted in leaf nodes:
    alice@... → row 492
    bob@... → row 1843
    charlie@... → row 7291
  
  Search for 'bob@...': root → left half → bob range → leaf → row pointer → 1ms!

INDEX TYPES:
  B-Tree (default):   Equality (=), range (<, >, BETWEEN), ORDER BY, LIKE 'prefix%'
  Hash:               Equality only (=). Cannot do ranges. Faster than B-tree for =.
  GiST / SP-GiST:    Geometric data, full-text search, IP ranges.
  GIN:                Full-text search, JSONB keys, array elements.
  BRIN:               Very large tables where data is naturally ordered (time-series).
                      Only stores min/max per range of pages. Tiny index size.

COMPOSITE INDEX:
  INDEX (user_id, created_at)
  
  Works for:
    WHERE user_id = 123 AND created_at > '2024-01-01'  ✓ (both columns used)
    WHERE user_id = 123                                 ✓ (leftmost prefix)
    ORDER BY user_id, created_at                        ✓
  
  Does NOT work for:
    WHERE created_at > '2024-01-01'                     ✗ (not leftmost prefix)
  
  RULE: Most selective column first. user_id (narrows to ~1000 rows) before created_at.

PARTIAL INDEX:
  Index only rows matching a condition.
  CREATE INDEX idx_active_orders ON orders(user_id) WHERE status = 'active';
  
  80% of orders are 'completed'. Only 20% are 'active'.
  Partial index is 80% smaller → faster, less memory.
  Works for: SELECT * FROM orders WHERE user_id = 123 AND status = 'active'

COVERING INDEX (Index-Only Scan):
  Index contains ALL columns needed by query.
  PostgreSQL can answer query from index alone, without touching the table.
  
  CREATE INDEX idx_user_summary ON users(user_id) INCLUDE (name, email);
  SELECT user_id, name, email FROM users WHERE user_id = 123;
  → Never reads the table row. Pure index scan. Very fast.

INDEX COSTS:
  Every INSERT/UPDATE/DELETE must update all indexes.
  Each index: ~10-30% of table size on disk.
  Too many indexes: write slowdown.
  
  RULE: Index columns in WHERE, JOIN ON, ORDER BY.
        Don't index low-cardinality columns (gender: M/F) — not selective enough.
        Don't index columns never used in WHERE.
```

---

## 4. Replication

```
PRIMARY-REPLICA REPLICATION:
  Primary: handles all WRITES.
  Replicas: copies of primary, handle READS.
  
  Write path: app → primary → write → replicate to replicas.
  Read path:  app → any replica → read.

ASYNC REPLICATION (default):
  Primary writes data, returns success to client.
  Replication to replicas happens ASYNCHRONOUSLY afterwards.
  
  Replication lag: 0.1ms to 2 seconds typically.
  
  Problem: Read-your-own-writes.
    User writes profile update.
    User reads profile (hits replica that hasn't caught up yet).
    User sees old profile. Confusing.
    
    Fix options:
      1. Read from primary for 5 seconds after write (route based on timestamp).
      2. Read from primary always for that user (sticky primary reads).
      3. Sync replication for critical data.

SYNC REPLICATION:
  Primary waits for AT LEAST ONE replica to confirm before returning success.
  Pros: No data loss (replica has confirmed copy).
  Cons: Write latency = max(primary + replica replication time). Slower.
  
  PostgreSQL: synchronous_commit = on
  Tradeoff: slower writes for stronger durability guarantee.

SEMI-SYNC REPLICATION (MySQL):
  Primary waits for ONE replica to acknowledge receiving the data (not applying it).
  Compromise: some durability + acceptable write latency.

MULTI-PRIMARY REPLICATION:
  Multiple nodes accept writes (active-active).
  Write conflicts possible: two nodes write same row simultaneously.
  Requires conflict resolution: last-write-wins, CRDTs, or application-level merge.
  
  Examples: Cassandra (multi-master by design), CockroachDB, YugabyteDB.
  Use when: need write availability in multiple regions simultaneously.
```

---

## 5. Sharding (Horizontal Partitioning)

```
WHEN: One DB server can't handle the load.
  Single PostgreSQL: ~10TB storage, ~50K writes/sec max practical.
  Need 1PB storage or 500K writes/sec → shard across 100 servers.

SHARDING STRATEGIES:

1. HASH SHARDING:
   shard_id = hash(key) % num_shards
   
   Example: user_id = 12345
   shard_id = md5("12345") % 10 = 7 → Shard 7
   
   Pros: Uniform distribution (if hash is good).
   Cons: Adding/removing shards → rehash ALL keys → massive data migration.
         Fix: Consistent hashing (see Topic 10).

2. RANGE SHARDING:
   Shard 0: user_id 0 to 9,999,999
   Shard 1: user_id 10,000,000 to 19,999,999
   ...
   
   Pros: Simple. Range queries easy (all users in range → same shard).
   Cons: Hot shards. New users all have high IDs → Shard N overloaded.
         Old shards nearly empty. Uneven distribution over time.

3. DIRECTORY SHARDING:
   Lookup table: user_id → shard_id.
   Any user can be on any shard. Most flexible.
   
   Pros: Can rebalance any user to any shard. No rehashing.
   Cons: Lookup table is itself a potential bottleneck/SPOF.
         Cache the lookup table in Redis.

CROSS-SHARD QUERIES:
  "Find all users who signed up in January 2024":
  → Must query ALL shards → aggregate results.
  → Slow. Expensive. Avoid if possible.
  
  Design principle: keep queries that need to be fast to ONE shard.
    All data for user 123: on Shard 7. Never cross-shard for user queries.
    Analytics: use separate analytics DB (ClickHouse, BigQuery) that aggregates all shards.

CROSS-SHARD TRANSACTIONS:
  Transfer money from user 123 (Shard 7) to user 456 (Shard 3):
  → Can't do a single ACID transaction across shards.
  
  Solutions:
    Saga Pattern: break transaction into steps, each on one shard.
                  Compensating transactions for rollback.
    2PC (Two-Phase Commit): coordinator asks both shards to commit.
                            Slow. Coordinator is SPOF.
    Design around it: keep related data on same shard.
```

---

## 6. Consistent Hashing

```
PROBLEM WITH NAIVE HASHING:
  4 shards: shard = hash(key) % 4
  Add 5th shard: shard = hash(key) % 5
  → hash % 4 ≠ hash % 5 for almost all keys
  → ~80% of all keys map to different shards!
  → Must move 80% of data. Catastrophic for production.

CONSISTENT HASHING:
  Arrange ALL nodes AND keys on a virtual ring (0 to 2^32).
  Each key assigned to the NEXT node clockwise.
  
  Ring: ──[S-A: 100]──────[S-B: 300]──────[S-C: 700]──────[S-D: 900]──
  
  Key "user_123" hashes to position 450:
    → Clockwise: next node is S-C at 700.
    → user_123 stored on S-C.
  
  Add node S-E at position 500:
    → Only keys between 300 and 500 (previously on S-C) move to S-E.
    → Keys before 300 and after 500: unchanged.
    → Only 1/N keys move (N = number of nodes). Minimal disruption.
  
  Remove node S-C at 700:
    → Only S-C's keys move to S-D (next clockwise).
    → Everyone else: unchanged.

VIRTUAL NODES:
  Problem: With only 4 real nodes on ring, distribution might be uneven.
  Solution: Each physical node has K virtual positions on ring (K=150 typically).
  S-A has positions: 15, 87, 234, 561, 789, 1023, ...  (150 spread-out positions)
  
  Benefits:
    - Even distribution across nodes.
    - When node removed: its load spreads evenly across ALL remaining nodes.
      (Without vnodes: removed node's load all goes to ONE next node → hotspot.)

USED BY: Redis Cluster, Cassandra, DynamoDB, consistent hash-based caches.
```

---

## 7. ACID vs BASE

```
ACID (SQL databases):
  Atomicity:   All or nothing. Either all operations succeed or all fail.
               Transfer $100: DEDUCT from A AND CREDIT to B — or neither.
  
  Consistency: Transaction takes DB from valid state to valid state.
               Foreign key constraints maintained. Balance never goes negative.
  
  Isolation:   Concurrent transactions don't interfere.
               Read uncommitted → Read committed → Repeatable read → Serializable.
               (Higher isolation = slower due to more locking)
  
  Durability:  Committed transaction persists even on crash.
               WAL (Write-Ahead Log) ensures data is written to disk.

BASE (NoSQL, eventual consistency):
  Basically Available:   System is usually available (AP in CAP).
  Soft state:            State may be inconsistent (replicas haven't synced).
  Eventually consistent: All replicas eventually converge to same value.
  
  Acceptable when: "likes count is 1,234 or 1,237 — user doesn't care"
  Not acceptable when: "balance shows $1,000 but it's actually $0"

ISOLATION LEVELS (SQL):
  READ UNCOMMITTED: Sees dirty reads (uncommitted data from other transactions). Fast.
  READ COMMITTED:   Only sees committed data. Prevents dirty reads. Default in PostgreSQL.
  REPEATABLE READ:  Re-reading same row in transaction returns same result. Prevents phantom reads in most DBs.
  SERIALIZABLE:     Transactions behave as if executed one after another. Slowest. Safest.

CHOOSING ISOLATION LEVEL:
  Banking: SERIALIZABLE (never show inconsistent balance)
  Social feed: READ COMMITTED (stale "likes" count OK)
  Analytics: READ UNCOMMITTED (approximate counts fine, maximum throughput)
```

---

## 8. Database Schema Design Patterns

```
NORMALIZATION vs DENORMALIZATION:

Normalized (avoid duplication):
  users(id, name, email)
  orders(id, user_id, total)
  order_items(id, order_id, product_id, qty, price)
  products(id, name, description, price)
  
  Pros: No data duplication. Update in one place.
  Cons: JOINs needed for every query. Complex queries. Slower reads.

Denormalized (duplicate for read speed):
  orders(id, user_id, user_name, user_email, total, items_json)
  # user_name stored with order (denormalized from users table)
  
  Pros: Single table read. Fast. Simple.
  Cons: If user name changes → all their orders have wrong name.
        OK for: "order was placed when user was named Alice" (historical accuracy).
        Not OK for: address — use address_id, look up separately.

EVENT SOURCING:
  Don't store current state. Store ALL events (immutable log).
  
  events table:
    (user_id, event_type, event_data, timestamp)
    
    {user: 123, event: "order_placed", data: {items: [...], total: 99.99}}
    {user: 123, event: "order_shipped", data: {tracking: "UPS123"}}
    {user: 123, event: "order_delivered", data: {}}
  
  Current state: replay events from beginning.
  Pros: Full audit log. Can replay history. Great for debugging.
  Cons: State computation can be slow (need snapshots for performance).
  
  Used by: financial systems, audit-critical systems, Kafka as event store.

SOFT DELETE:
  Instead of DELETE row: set deleted_at = NOW().
  
  ALTER TABLE users ADD COLUMN deleted_at TIMESTAMP;
  UPDATE users SET deleted_at = NOW() WHERE id = 123;  # "delete"
  SELECT * FROM users WHERE deleted_at IS NULL;         # active users only
  
  Pros: recoverable. audit trail.
  Cons: queries need WHERE deleted_at IS NULL on every query.
  Fix: partial index on deleted_at IS NULL, or create view.
```

---

## 9. Interview Questions

```
Q1: "How do you choose between PostgreSQL and Cassandra?"
A: PostgreSQL for ACID, complex queries, relational data, JOINs.
   Cassandra for high write throughput (1M writes/sec), time-series, 
   data access pattern is always "get all records for partition key."
   
   Key question: "What's the primary access pattern?"
   If: "get all messages in a conversation" → Cassandra (partition by conversation_id).
   If: "complex analytics JOIN across 5 tables" → PostgreSQL.

Q2: "What is database sharding and what problems does it create?"
A: Splitting data across multiple DB servers.
   Problems: cross-shard queries (slow, must aggregate), 
             cross-shard transactions (use Saga), 
             resharding (use consistent hashing).

Q3: "How would you design the database for a ride-sharing app?"
A: PostgreSQL for users, drivers (ACID, rich queries).
   Cassandra for trips (high write volume, time-series, partition by driver_id or user_id).
   Redis for driver locations (in-memory, geospatial, ephemeral).
   ClickHouse for analytics (columnar, fast aggregations).

Q4: "What's the difference between READ COMMITTED and SERIALIZABLE isolation?"
A: READ COMMITTED: only see committed data, but two reads in same transaction 
   can return different results (non-repeatable read, phantom read possible).
   SERIALIZABLE: transactions behave as if sequential. No anomalies. 
   Cost: 2-5× slower (more locking/MVCC overhead).

Q5: "How does a composite index work? What's the leftmost prefix rule?"
A: Composite index (a, b, c) stores data sorted by a, then b, then c.
   Can use index for queries filtering on: (a), (a,b), (a,b,c).
   Cannot use for: (b), (c), (b,c) — doesn't start from leftmost column.
   Put most selective column first. Put equality column before range column.
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

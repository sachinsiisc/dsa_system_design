# Topic 7: CAP Theorem
## HLD Deep Dive | MAANG Interview Ready

---

## 1. What Is CAP Theorem?

```
Brewer's Theorem (2000): A distributed system can guarantee at most 2 of these 3:

C — Consistency:    Every read returns the most recent write (or an error).
A — Availability:   Every request receives a response (not necessarily most recent).
P — Partition Tolerance: System continues operating despite network partition.

NETWORK PARTITION: Some nodes can't communicate with others.
  Example: Data centre A and B. Network link between them fails.
  A's nodes cannot reach B's nodes.

WHY ONLY 2 OF 3?
  In distributed systems, network partitions are INEVITABLE.
  Networks fail. Cables cut. Packets lost. Servers reboot.
  → P (partition tolerance) is NOT optional. You MUST handle partitions.
  → Real choice: CP or AP.

CP: System stays Consistent during partition (at cost of Availability).
    "I'd rather say ERROR than give you wrong data."
    Systems: HBase, Zookeeper, etcd, MongoDB (strong mode), PostgreSQL (sync replication).
    Use: banking, inventory, medical, anything where wrong data = catastrophe.

AP: System stays Available during partition (at cost of Consistency).
    "I'll give you my best guess. Might be slightly stale."
    Systems: Cassandra, DynamoDB, CouchDB, DNS.
    Use: social feeds, likes, user profiles, shopping cart.
```

---

## 2. Understanding Each Property

```
CONSISTENCY (C) — "All nodes see the same data at the same time":

  Bank balance: Alice has $1,000.
  Alice transfers $500 to Bob.
  
  Consistent: After transfer completes:
    Any server queried: "Alice has $500, Bob has $1,500." ← same answer everywhere.
  
  Inconsistent (without C): 
    Server A: "Alice has $500" (saw the write).
    Server B: "Alice has $1,000" (hasn't replicated yet).
    Two different answers for same question at same moment.

AVAILABILITY (A) — "System always responds":

  Even if some nodes crash, the surviving nodes keep serving requests.
  Response may be stale but it IS a response (not an error).
  
  Netflix: if one server dies, your movie keeps playing.
           You might see a stale recommendation list.
           That's fine. Stale data > no service.

PARTITION TOLERANCE (P) — "Handles network split":

  DC-1 and DC-2 connected by fibre. Fibre cut → partition.
  Without P: entire system goes down when partition happens. Unacceptable.
  With P: system continues operating. Either:
    CP: some nodes return errors (sacrifice A).
    AP: nodes return potentially stale data (sacrifice C).
```

---

## 3. CP vs AP: Real-World Decision Making

```
CP EXAMPLES:

1. Bank Transfer (PostgreSQL with sync replication):
   Transfer $1,000 from Account A → Account B.
   
   Network partition occurs mid-transaction.
   CP choice: ROLLBACK. Return error: "Transaction failed. Try again."
   
   User: "That's annoying."
   Bank: "Better than your $1,000 disappearing."
   
   Code:
   BEGIN;
   UPDATE accounts SET balance = balance - 1000 WHERE id = 'A';
   UPDATE accounts SET balance = balance + 1000 WHERE id = 'B';
   COMMIT;
   -- If network partition: COMMIT fails → both updates rollback → safe.

2. Distributed Lock (Zookeeper):
   Service A and B both want to write to same resource.
   Acquire lock in Zookeeper before writing.
   
   Partition occurs: Zookeeper minority partition refuses lock requests.
   CP: Service B cannot acquire lock → waits → consistent access guaranteed.
   AP would mean: both A and B acquire lock → both write → conflict.

3. Leader Election (etcd in Kubernetes):
   Kubernetes needs ONE scheduler. Must be exactly one at a time.
   etcd uses Raft consensus: 3 nodes. Need 2/3 majority for any decision.
   If partition isolates 1 node: it cannot make decisions (CP).
   2 nodes still have quorum → continue. 1 isolated node → refuses. Consistent.

AP EXAMPLES:

1. Amazon Shopping Cart (DynamoDB AP mode):
   User adds item on mobile. Network flaky.
   AP choice: accept the add. Record in local node. Sync later.
   
   Cart state across nodes may be temporarily inconsistent.
   Merge: when partition heals, merge all additions.
   CRDT (Conflict-free Replicated Data Type) ensures correct merge.
   
   Worst case: user adds "Shoes" twice (once on each partition side).
   Result: 2 shoes in cart. Amazon prefers this to "Cannot add to cart."

2. Netflix Watch History (Cassandra AP):
   User watches Episode 3 of a show.
   Progress stored in Cassandra.
   
   Next day: user on different device. Reads from different Cassandra node.
   Node hasn't synced yet: shows Episode 2 progress.
   
   User: "Oh, I was further than that." Clicks to correct episode.
   Cost: minor UX annoyance.
   Alternative (CP): entire platform unavailable when nodes partition.
   Decision: AP is correct here.

3. Social Media Likes (Cassandra counter):
   Post has 1,000 likes. You like it.
   Your like recorded on Partition A.
   Your friend reads from Partition B: sees 1,000 (not 1,001).
   5 seconds later, partition heals: both see 1,001.
   
   Acceptable: nobody needs real-time exact like counts.
```

---

## 4. PACELC — Beyond CAP

```
CAP only talks about behavior DURING partitions.
PACELC extends it to normal operation:

PACELC:
  If Partition: choose A or C (this is CAP).
  Else (no partition): choose L (Latency) or C (Consistency).

Even without partition, there's a trade-off:
  Strong consistency: write must propagate to all replicas before returning.
  → Higher latency (wait for all acks).
  
  Eventual consistency: write to one node, return immediately.
  → Lower latency. Replicas catch up asynchronously.

PACELC EXAMPLES:
  System          │ During Partition │ Normal Operation
  ────────────────┼──────────────────┼──────────────────────
  Cassandra       │ AP               │ EL (low latency, eventual consistency)
  HBase           │ CP               │ EC (consistent but higher latency)
  DynamoDB        │ AP               │ EL (by default; strong consistency available)
  MongoDB         │ CP               │ EC (readConcern: majority = consistent)
  PostgreSQL (sync)│ CP              │ EC (waits for replica ack)

INTERVIEW: "Name a system that trades latency for consistency."
A: DynamoDB with strong consistency reads (default is eventual).
   Each strongly-consistent read has 2× latency vs eventually-consistent.
   But you're guaranteed to see the most recent write.
```

---

## 5. Quorum — The Middle Ground

```
Problem: CP is too strict (unavailable on partition), AP is too loose (stale reads).
Solution: QUORUM — a middle ground.

Setup: 3 replicas. Quorum = majority = 2.
  W (write quorum): write must succeed on W replicas before returning.
  R (read  quorum): read must succeed on R replicas, return most recent.
  
  For consistency: W + R > N (N = total replicas).
  Standard: N=3, W=2, R=2. W+R=4 > 3. ✓ Consistent.
  
  Write: write to replicas 1 and 2 (W=2). Return success.
         Replica 3 gets it later (async).
  Read:  read from replicas 1 and 3 (R=2). Take most recent.
         Since at least one of 1,3 has the latest write → consistent.

TUNEABLE QUORUM (Cassandra):
  # For each query, choose consistency level:
  
  # Strongest consistency (must wait for all 3):
  SELECT * FROM users WHERE id = 123 USING CONSISTENCY ALL
  # Very slow. Unavailable if any replica down.
  
  # Quorum (W+R > N, consistent):
  INSERT INTO users ... USING CONSISTENCY QUORUM
  SELECT * FROM users ... USING CONSISTENCY QUORUM
  # Balanced: tolerates 1 replica failure.
  
  # Eventual consistency (fastest, least consistent):
  SELECT * FROM users ... USING CONSISTENCY ONE
  # One replica responds. Might be stale.

FORMULA: W + R > N ensures you always read your own writes.
  If W=1, R=1: might miss latest write (ONE reader doesn't overlap ONE writer).
  If W=2, R=2: always at least 1 overlap → see latest write.
  
  Strong consistency: W=N (write to all). Slow writes.
  High availability:  W=1 (write to one). May not be readable immediately from all.
```

---

## 6. Network Partitions in Practice

```
PARTITION TYPES:

1. Complete partition: DC-A and DC-B cannot reach each other.
2. Partial partition: Some nodes in DC-A can reach DC-B, others can't.
3. Slow network: Not a hard partition, but latency 10s+ (effectively a partition for timeouts).

HOW SYSTEMS DETECT PARTITION:
  Heartbeats: nodes send "I'm alive" messages every 1s.
  Timeout: if no heartbeat for 5s → assume node is down/partitioned.
  Challenge: Is the node actually down, or is the network slow?
             A node might wrongly think another is down → split brain.

SPLIT BRAIN:
  Two nodes both think they're the primary. Both accept writes.
  Each has different data. When partition heals: conflict!
  
  Prevention: fencing (STONITH: Shoot The Other Node In The Head)
              Quorum: must have majority to be primary.
              Lease-based: primary has time-limited lease from a quorum.

EXAMPLE: PostgreSQL with 2 nodes (no quorum):
  Node A (primary) and Node B (replica).
  Network partition. Both think they're primary.
  Node A: writes 100 transactions.
  Node B (promoted itself): writes 200 different transactions.
  Partition heals: conflict! Who wins?
  
  Prevention: always have 3+ nodes. Use quorum.
              With 3 nodes, partition splits 2+1 or 1+2. Minority refuses.
```

---

## 7. Interview Q&A with Deep Answers

```
Q1: "Explain CAP theorem."
A: Three properties: Consistency (all reads see most recent write), 
   Availability (every request gets a response), 
   Partition Tolerance (system works despite network failures).
   In distributed systems, P is mandatory. Real choice: CP or AP.
   CP: error on partition (bank, medical). AP: stale data OK (social, cache).

Q2: "Where does Cassandra sit in CAP?"
A: AP. Cassandra prioritizes availability and partition tolerance.
   Tunable consistency: can move toward CP by using QUORUM or ALL consistency levels.
   Default: eventual consistency (ONE). Best for: high write throughput, fault tolerance.

Q3: "Is a single-node system CP or AP?"
A: Neither applies. CAP is about distributed systems only.
   A single node has no partition problem (it's one node).
   Single node PostgreSQL: ACID (consistent). If node crashes: unavailable. But that's not CAP.

Q4: "You're designing a healthcare system. CP or AP?"
A: CP without question. Wrong medication or wrong dosage due to stale data = patient harm.
   "System unavailable, try again" > "I gave you data from 30 seconds ago."
   Implementation: PostgreSQL with synchronous replication. Reads from primary only.

Q5: "Can you achieve all three (CAP) simultaneously?"
A: No in theory (Brewer's proof). In practice, with very reliable networks,
   partitions are rare enough that you get CAP-like behavior most of the time.
   Spanner (Google) achieves near-C + A + P using atomic clocks + commit wait.
   But in theory, given an adversarial network: you can always create a partition.
```

---

## 8. Practical CAP Decision Checklist

```
Answer these questions to choose CP vs AP:

1. If a user gets stale data, what's the worst case?
   - They see an old like count → AP is fine
   - They don't see that a doctor added a medication → CP required

2. If the system returns an error, what's the worst case?
   - User can retry → CP is OK
   - Emergency service unavailable → AP required (better stale than unavailable)

3. What are the business/legal requirements?
   - PCI DSS (payment): strong consistency required
   - GDPR (right to delete): must be consistent
   - Social feature: eventual consistency acceptable

4. How tolerable is delay?
   - Real-time trading: CP at sub-millisecond cost is unacceptable → AP with CRDT
   - Banking: CP even at 100ms cost is acceptable

CHEAT SHEET:
  Banking, finance:         CP always
  Inventory (limited qty):  CP (overselling = problem)
  Medical records:          CP always
  Social likes, views:      AP
  User profile:             AP (minor staleness OK)
  Shopping cart:            AP (Dynamo paper)
  Session/auth:             Depends (AP OK with short TTL, or CP for security)
  Distributed lock:         CP (that's the whole point)
  Leaderboard:              AP (2-second lag on scores is fine)
  DNS:                      AP (designed for high availability, eventual consistency)
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

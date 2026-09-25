# Topic 8: Consistency Models
## HLD Deep Dive | MAANG Interview Ready

---

## 1. Why Consistency Models Matter

```
In distributed systems, multiple replicas of data exist.
When you write to one replica, others need to sync.
The CONSISTENCY MODEL defines: what does a reader see and when?

From strongest (most restrictive) to weakest (most permissive):

  LINEARIZABILITY (Strong Consistency)   ← strictest, most intuitive
  SEQUENTIAL CONSISTENCY
  CAUSAL CONSISTENCY
  EVENTUAL CONSISTENCY                   ← weakest, most available

Stronger = more intuitive, higher latency, lower availability.
Weaker   = less intuitive, lower latency, higher availability.

REAL-WORLD ANALOGY:
  Imagine you're editing a Google Doc shared with 5 people.
  
  Linearizability: everyone sees your keystrokes in real time. Instant sync.
  Sequential:      everyone sees same order, but might see it 2s later.
  Causal:          if you reply to Alice's comment, everyone sees Alice's comment before yours.
                   But unrelated edits by Bob can appear in any order.
  Eventual:        eventually all see the same document, but during editing, views differ.
```

---

## 2. Linearizability (Strong Consistency)

```
DEFINITION:
  After a write completes, ALL subsequent reads from ANY node return that write.
  Every operation appears instantaneous and in real-time order.
  
  "The system behaves as if there's only ONE copy of the data."

EXAMPLE:
  T1 = 0ms:  Write: balance = $1,000 → committed.
  T2 = 1ms:  Read  from Node A: must return $1,000.
  T3 = 1ms:  Read  from Node B: must return $1,000.
  T4 = 2ms:  Write: balance = $500 → committed.
  T5 = 3ms:  Read  from any node: must return $500.
  
  ALL reads after write at T4 see $500. No node returns stale $1,000 after T4.

HOW TO ACHIEVE:
  Read from primary only (no replicas).
  Synchronous replication: write to all replicas before acknowledging.
  Consensus protocol (Raft/Paxos): majority must agree on value.
  
  Google Spanner: uses TrueTime API (atomic clocks) + commit wait.
    Write completes at TrueTime T.
    Commit wait: delay return until clock uncertainty passes (~14ms).
    Any read with timestamp > T guaranteed to see this write.

COST:
  High latency: must wait for consensus (all nodes must agree).
  Lower availability: if any node unreachable, write may stall.
  
USE WHEN:
  Financial transactions, inventory counts, distributed locks.
  Any "exactly-one" requirement (only one leader, only one job runs).

SYSTEMS: Google Spanner, FoundationDB, etcd (with linearizable reads), PostgreSQL (primary reads).
```

---

## 3. Sequential Consistency

```
DEFINITION:
  All operations appear to execute in SOME sequential order.
  Each node sees all operations in the same sequence.
  Operations from each client appear in program order.
  
  WEAKER than linearizability: doesn't require real-time ordering.
  A write may appear "late" but everyone sees it in the same relative order.

EXAMPLE:
  Linearizable: if write completes at 1ms, read at 2ms MUST see it.
  Sequential:   write completes at 1ms, read at 2ms MIGHT see old value.
                But ALL clients see the SAME OLD VALUE until it's updated.

  Alice posts "Photo A" at T=100.
  Bob posts "Photo B" at T=101 (unrelated).
  
  Sequential consistent view: could be "Photo A first, Photo B second"
                              or "Photo B first, Photo A first"
                              but ALL clients see SAME ORDER.
  
  Not linearizable: either order is ok even if Alice's was "earlier" in real time.

USE: Multi-core CPU memory models (Java memory model, C++ memory model).
     Some database replication modes.
     Shared memory in distributed computing.
```

---

## 4. Causal Consistency

```
DEFINITION:
  Operations that are causally related (A caused B) are seen in causal order by all nodes.
  Causally unrelated operations can be in any order.
  
  Captures: "You can only reply to a message you've seen."

WHAT COUNTS AS CAUSAL:
  - A writes X. B reads X. B writes Y. A and Y are causally related.
  - Alice posts comment. Bob likes Alice's comment. 
    You must see Alice's comment before Bob's like.

EXAMPLE (social network):
  Alice posts: "Who wants pizza?"
  Bob replies: "I do!" (Bob read Alice's post → causal dependency)
  Carol replies: "Me too!" (Carol read Alice's post → causal dependency)
  
  Causal consistency guarantees:
    Everyone sees Alice's post BEFORE Bob's or Carol's reply.
    Bob's and Carol's replies can appear in any order (unrelated to each other).
  
  Violation of causal consistency:
    User sees Bob's reply "I do!" BEFORE seeing Alice's original "Who wants pizza?"
    Context makes no sense.

IMPLEMENTATION: Vector clocks.
  Each node maintains a vector clock [node1_time, node2_time, ..., nodeN_time].
  
  Message includes vector clock.
  Receiver delays message until all causally preceding messages received.
  
  Vector clock example (2 nodes: A and B):
    A writes: VC = [1, 0] (A incremented)
    B reads A's write: VC = [1, 0]
    B writes reply: VC = [1, 1] (B incremented, carries A's timestamp)
    
    Receiver sees B's message with VC=[1,1]:
    Must have already seen A's message with VC=[1,0].
    If not: hold B's message until A's arrives.

SYSTEMS: MongoDB (causal consistency sessions), Amazon DynamoDB streams.
USE WHEN: Social media (comment threads must appear in context), 
          collaborative editing, chat applications.
```

---

## 5. Eventual Consistency

```
DEFINITION:
  Given no new updates, all replicas will EVENTUALLY converge to same value.
  No guarantee on WHEN. Could be milliseconds or seconds.
  During convergence: different replicas may return different values.

EXAMPLE:
  DNS: Update example.com to point to new IP 5.6.7.8.
  Root nameservers updated immediately.
  ISP DNS caches: may still return old IP for up to TTL (e.g., 300 seconds).
  During propagation: some users reach new server, others reach old.
  After TTL expires everywhere: all users reach new server.
  DNS is EVENTUALLY consistent.

STRONGER VARIANTS OF EVENTUAL CONSISTENCY:

Monotonic Read Consistency:
  Once you read a value, you'll never read an OLDER value.
  If you read balance=$500, you won't then read $1,000 (old value).
  DOESN'T guarantee you see latest write. Just prevents going backwards.
  
  Implementation: always read from same replica, or include timestamp in request.

Read-Your-Own-Writes:
  After you write, YOU always see your own write.
  Other users might not see it immediately, but you do.
  
  Example: Post a tweet. You immediately see it.
  Implementation: after write, route your reads to primary for N seconds.
                  Or: include your write timestamp in requests → replica delays response
                  until it has caught up to that timestamp.

Monotonic Write Consistency:
  Your writes appear in the order you sent them.
  If you write X=1 then X=2: no node ever applies X=2 before X=1.

Session Consistency:
  Within a session, you see monotonic reads AND read-your-own-writes.
  Cross-session: might see stale data.
  
  MongoDB: session consistency maintained within a single connection session.

REAL-WORLD EXAMPLES:
  DynamoDB (default): eventually consistent. Strongly consistent optional (2× cost).
  Cassandra (ONE consistency): eventual.
  S3: strong read-after-write consistency (since Dec 2020, previously eventual).
  ElasticSearch: eventually consistent (index refresh every 1 second by default).
  CDN: cache expiry = eventual consistency (stale until TTL expires).
```

---

## 6. Conflict Resolution

```
In AP/eventual consistency systems: two nodes might write same key simultaneously.
When they sync: CONFLICT. Who wins?

RESOLUTION STRATEGIES:

1. LAST WRITE WINS (LWW):
   Compare timestamps. Most recent wins.
   
   Node A writes key="price" value="100" at T=100.
   Node B writes key="price" value="200" at T=101.
   On sync: T=101 wins → price = "200".
   
   Problem: clock skew. Node B's clock is 50ms ahead.
            Node B's "T=101" might actually be earlier in real time.
   Fix: Use logical clocks (Lamport timestamps) not wall clock.
   
   Used by: Cassandra (default), DynamoDB.
   Risk: data loss (node A's write is overwritten).

2. CRDT (Conflict-free Replicated Data Type):
   Data structure where all concurrent operations can be MERGED automatically.
   No conflicts by design.
   
   G-Counter (grow-only counter):
     Each node has own counter. Add only. Never decrement.
     Node A: likes = [A:5, B:3, C:2]
     Node B: likes = [A:5, B:4, C:2]
     Merge: take MAX of each: [A:5, B:4, C:2]. Total = 11.
     Always correct regardless of merge order.
   
   LWW-Register (Last Write Wins register with logical clock):
     Attach Lamport timestamp to each write.
     Merge: take value with highest logical timestamp.
   
   Observed-Remove Set (OR-Set):
     Each element has unique ID when added.
     Remove: mark specific-ID as removed.
     Add and remove of same element at same time: add wins.
   
   Used by: Amazon shopping cart (Dynamo paper), Riak, Redis Enterprise.

3. APPLICATION-LEVEL CONFLICT RESOLUTION:
   Present conflicts to user or application for manual resolution.
   
   Google Docs: operational transformation (OT) to merge simultaneous edits.
   Git: shows merge conflicts for user to resolve.
   CouchDB: stores all conflicting versions; app picks winner.

4. VERSION VECTORS (Vector Clocks):
   Track causal history of each value.
   Node A: balance = $100, VC = [A:1, B:0]
   Node B: balance = $150, VC = [A:0, B:1]
   On sync: neither dominates the other → CONFLICT (concurrent writes).
   Application decides: which is authoritative? Or merge somehow.
   
   If VC = [A:1, B:0] vs VC = [A:2, B:0]: A:2 dominates A:1 → no conflict (A:2 wins).
```

---

## 7. How Google Spanner Achieves Global Linearizability

```
CHALLENGE: Data centres in US, EU, Asia. Speed of light: US→Asia = 130ms.
GOAL: Every read anywhere sees latest write from anywhere.

NAIVE ATTEMPT: 2-Phase Commit.
  Write to US primary → replicate to EU, Asia → all ack → return.
  Latency: 130ms × 2 (round trip to Asia) = 260ms minimum. Unacceptable for interactive apps.

SPANNER'S SOLUTION: TrueTime API + Commit Wait.

TrueTime API:
  Every Google data centre has GPS receivers + atomic clocks.
  TrueTime.now() returns: [earliest, latest] time interval.
  Interval width: typically ±4ms (uncertainty due to NTP drift).
  
  Example: TrueTime.now() = [10:00:00.996, 10:00:01.004]
  True time is DEFINITELY in this 8ms window.

Commit Wait Protocol:
  1. Transaction starts: note T_start = TrueTime.now().earliest.
  2. Write data to Paxos leader (US).
  3. WAIT until TrueTime.now().earliest > T_start.latest (until uncertainty passes).
  4. Now: the commit timestamp is definitely in the PAST for ALL clocks everywhere.
  5. Commit. Return to client. Update read timestamp.
  
  Wait time ≈ 2ε (epsilon = clock uncertainty ≈ 4ms → wait ~8ms).
  Result: any read that starts after commit timestamp is guaranteed to see this write.
  
Linearizability achieved via clock physics instead of consensus rounds.
Cost: ~14ms write latency. Much cheaper than 260ms 2PC across continents.

Used by: Google Ads, F1 (Google's global financial database), Cloud Spanner.
```

---

## 8. Consistency Model Cheat Sheet

```
Model            │ All same?  │ Real-time? │ Latency │ Availability │ Use Case
─────────────────┼────────────┼────────────┼─────────┼──────────────┼──────────────────────
Linearizability  │ YES        │ YES        │ High    │ Lower        │ Banking, locks
Sequential       │ Same order │ NO         │ Medium  │ Medium       │ CPU memory models
Causal           │ Causally   │ NO         │ Medium  │ Good         │ Social, chat
Read-your-writes │ Only self  │ Self only  │ Low     │ Good         │ User profile updates
Monotonic read   │ No rollback│ NO         │ Low     │ Good         │ Analytics dashboards
Eventual         │ Eventually │ NO         │ Lowest  │ Highest      │ DNS, social likes, CDN

INTERVIEW SOUNDBITES:
  "Linearizability: one copy illusion. Every read sees latest write."
  "Causal: A causes B → everyone sees A before B. Unrelated events: any order."
  "Eventual: all replicas converge. No guarantee when. DNS is classic example."
  "Read-your-own-writes: YOU see your writes. Others might not. Good for user-facing."
  "CRDT: conflict-free data types. Concurrent updates always merge correctly."
```

---

## 9. Interview Questions

```
Q1: "What is the difference between linearizability and sequential consistency?"
A: Linearizability: real-time ordering (write at T=1ms → read at T=2ms MUST see it).
   Sequential: all ops in same order, but not necessarily real-time.
   Write at T=1ms → read at T=2ms MIGHT see old value, but all clients see same order.

Q2: "What is causal consistency? Give an example."
A: Causally related operations (A causes B) appear in order for all nodes.
   If you reply to a tweet, everyone sees the original tweet before your reply.
   Unrelated tweets can appear in any order.
   Vector clocks track causality.

Q3: "What is eventual consistency? Is it dangerous?"
A: All replicas converge eventually. No guarantee on when.
   Not dangerous for: likes, view counts, DNS, CDN cache.
   Very dangerous for: bank balance, inventory, medical prescriptions.
   Key: understand what "wrong data" means for your use case.

Q4: "What is a CRDT?"
A: Conflict-free Replicated Data Type. Concurrent updates always merge correctly.
   G-Counter: grow-only, merge by taking MAX.
   OR-Set: concurrent add/remove → add wins.
   Used by: Amazon shopping cart, collaborative text editing.

Q5: "How does eventual consistency relate to CAP theorem?"
A: AP systems (Cassandra, DynamoDB) use eventual consistency.
   They sacrifice C (strong consistency) for A (availability) + P.
   Eventual consistency IS the "weak C" that AP systems provide.
   CAP's C specifically means linearizability. AP gives something weaker.
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

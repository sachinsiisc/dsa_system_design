# 11 — Consistent Hashing — Google Level Deep Dive

## The Problem with Simple Hashing

```
node = hash(key) % N   (N = number of servers)
```

If N changes (add/remove server):
- All keys remapped → massive cache invalidation
- N=3→4: ~75% of keys move to different servers
- Catastrophic for distributed caches

---

## Consistent Hashing

```
Arrange servers on a ring (0 to 2^32 - 1)
Each server hashes to a position on the ring
A key maps to the first server clockwise from its hash position
```

```
         hash ring (0 ... 2^32-1)
                  0
              /       \
          S3           S1
        /                \
       2^31           hash(key)→S1
        \                /
          S2           
              \       /
               (2^32-1)
```

**On server add:** Only keys between new server and its predecessor move.
**On server remove:** Only keys on that server move to next server clockwise.
**Expected:** Only K/N keys move (K = total keys, N = servers).

---

## Implementation

```python
import hashlib
from bisect import bisect, insort

class ConsistentHash:
    def __init__(self, num_replicas=150):
        self.num_replicas = num_replicas   # virtual nodes per server
        self.ring = {}                      # hash → server
        self.sorted_keys = []              # sorted hash positions

    def _hash(self, key):
        return int(hashlib.md5(key.encode()).hexdigest(), 16)

    def add_server(self, server):
        for i in range(self.num_replicas):
            virtual_key = f"{server}#{i}"
            h = self._hash(virtual_key)
            self.ring[h] = server
            insort(self.sorted_keys, h)

    def remove_server(self, server):
        for i in range(self.num_replicas):
            virtual_key = f"{server}#{i}"
            h = self._hash(virtual_key)
            del self.ring[h]
            self.sorted_keys.remove(h)

    def get_server(self, key):
        if not self.ring:
            return None
        h = self._hash(key)
        idx = bisect(self.sorted_keys, h) % len(self.sorted_keys)
        return self.ring[self.sorted_keys[idx]]
```

---

## Virtual Nodes — Why They Matter

Without virtual nodes (1 position per server):
```
Server A at position 10,  Server B at position 50,  Server C at position 90
Keys 11-50 → B   Keys 51-90 → C   Keys 91-10 → A
Problem: uneven distribution if hashes cluster
```

With 150 virtual nodes:
- Each server has 150 positions on the ring
- Load distributed much more evenly
- Heterogeneous servers: stronger server gets more virtual nodes

**Rule of thumb:** 150-200 virtual nodes per physical server.

---

## Where Consistent Hashing Is Used

| System | Use |
|--------|-----|
| Amazon DynamoDB | Partition key → node assignment |
| Apache Cassandra | Token ring for partition distribution |
| Memcached / Redis Cluster | Key → cache node routing |
| CDN | User's request → nearest edge server |
| Nginx upstream hashing | Session affinity / sticky routing |

---

## Data Replication on Ring

For fault tolerance: replicate each key to next N nodes clockwise.

```python
def get_servers(self, key, n):
    """Return n servers responsible for this key (replication)."""
    if not self.ring:
        return []
    h = self._hash(key)
    idx = bisect(self.sorted_keys, h) % len(self.sorted_keys)
    servers = []
    seen = set()
    while len(servers) < n:
        server = self.ring[self.sorted_keys[idx % len(self.sorted_keys)]]
        if server not in seen:
            servers.append(server)
            seen.add(server)
        idx += 1
    return servers
```

**DynamoDB / Cassandra:** replication factor = 3 → key stored on 3 consecutive nodes.

---

## Hotspot Problem

One key massively popular → all traffic to one server.

**Fix 1:** Further split — add more virtual nodes for that key's range.
**Fix 2:** Prefix/suffix key with timestamp or random number for write distribution.
**Fix 3:** Cache hot keys in a separate hot-data layer.

---

## Gossip Protocol (how nodes discover each other)

Used in Cassandra, DynamoDB:
- Each node periodically sends its state to N random peers
- State propagates like an epidemic
- O(log N) rounds to reach all nodes
- No central coordinator needed
- Used for: membership (who is alive), ring state, key ranges

---

## Interview Q&A

**Q: Why consistent hashing over modulo hashing?**
A: Modulo hashing remaps almost all keys when N changes. Consistent hashing only remaps K/N keys — critical for large distributed caches.

**Q: Why virtual nodes?**
A: Even load distribution. Without virtual nodes, a server might get a large arc of the ring → hotspot. With 150 virtual nodes, each server gets 150 small arcs spread around the ring.

**Q: What happens when a server fails?**
A: Its virtual nodes are removed. Keys that were on those positions now route to the next server clockwise. If replication factor is 3, data is already on 2 other nodes — no data loss.

**Q: How does consistent hashing relate to DynamoDB?**
A: DynamoDB uses a token ring. Each node owns a range of tokens (virtual nodes). Partition key is hashed to a token → determines which node owns it. Replication: next 2 nodes also store replicas.


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

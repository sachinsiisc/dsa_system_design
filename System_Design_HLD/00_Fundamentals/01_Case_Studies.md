# HLD Case Studies — 5 Complete End-to-End Designs
## MAANG Interview Ready

---

```
HOW TO USE THESE CASE STUDIES:

Each case study follows the same 6-step HLD interview framework:

  Step 1 → Clarify Requirements      (2-3 min)
  Step 2 → Estimate Scale            (3-5 min)
  Step 3 → High-Level Architecture   (5 min)
  Step 4 → Deep-Dive Key Components  (15-20 min)
  Step 5 → Handle Bottlenecks        (5 min)
  Step 6 → State Trade-offs          (2-3 min)

Read through each case top-to-bottom.
Then cover the answer and try to reconstruct it from memory.
```

---

## CASE STUDY 1: URL Shortener (TinyURL / bit.ly)

### Step 1 — Requirements

```
Functional:
  - Given a long URL, generate a short URL (e.g., tinyurl.com/abc123)
  - Given a short URL, redirect to original long URL
  - Custom aliases: user can pick their own short code (optional)
  - Expiry: URLs expire after N days (optional)

Non-Functional:
  - 100:1 read:write ratio (heavy reads — redirects >> creations)
  - Low latency redirect: < 10ms p99 (user is waiting)
  - High availability: 99.99% uptime (link rot = bad UX)
  - Short URLs must be unique
  - System must handle URLs that don't exist gracefully (404)

Out of scope: analytics dashboard, user accounts, link preview
```

### Step 2 — Scale Estimation

```
Write (shorten):
  100M URLs/day → 100M / 86,400 ≈ 1,200 writes/sec
  Peak (5×): 6,000 writes/sec

Read (redirect):
  100:1 ratio → 10 billion redirects/day → 115,000 redirects/sec
  Peak: 575,000 redirects/sec

Storage:
  Each record: short_code(7B) + long_url(500B avg) + metadata(100B) ≈ 607B
  100M URLs/day × 365 × 5 years = 182 billion URLs
  182B × 607 bytes ≈ 110 TB over 5 years  (manageable with sharding)

Short code length:
  Characters available: [a-z, A-Z, 0-9] = 62 chars
  7 characters: 62^7 = 3.5 trillion unique codes
  At 100M/day: 3.5T / 100M = 35,000 days ≈ 95 years of unique codes
  → 7-character base62 code is sufficient
```

### Step 3 — High-Level Architecture

```
                    ┌──────────────────────────────────────────────┐
                    │                 CLIENT (Browser)              │
                    └──────────────┬──────────────────┬────────────┘
                                   │                  │
                        POST /shorten           GET /abc123
                                   │                  │
                    ┌──────────────▼──────────────────▼────────────┐
                    │               API GATEWAY                     │
                    │      (rate limiting, auth, routing)           │
                    └──────────────┬──────────────────┬────────────┘
                                   │                  │
                    ┌──────────────▼──────┐  ┌───────▼──────────────┐
                    │  URL Shortener      │  │  Redirect Service     │
                    │  Service            │  │                       │
                    │  - generate code    │  │  1. Check Redis cache │
                    │  - store mapping    │  │  2. Miss → query DB   │
                    │  - return short URL │  │  3. 301/302 redirect  │
                    └──────────────┬──────┘  └───────┬──────────────┘
                                   │                  │
                    ┌──────────────▼──────────────────▼────────────┐
                    │             Redis Cache                        │
                    │     key: "short:abc123" → long_url            │
                    │     TTL: 24 hours. Hit rate target: ~98%      │
                    └─────────────────────────┬─────────────────────┘
                                              │ (cache miss)
                    ┌─────────────────────────▼─────────────────────┐
                    │          PostgreSQL (sharded by short_code)    │
                    │  Table: urls(short_code, long_url,             │
                    │              created_at, expires_at, owner_id) │
                    └────────────────────────────────────────────────┘
```

### Step 4 — Deep-Dive: Code Generation

```
APPROACH 1: MD5 / SHA256 Hash of long URL → take first 7 chars
  Pros:  Same long URL always gets same short code (idempotent).
  Cons:  Collisions possible (two different URLs → same 7-char prefix).
         Must handle collision: check DB, re-hash with salt. Complex.

APPROACH 2: Auto-increment ID → Base62 encode
  DB generates auto-increment ID: 1, 2, 3, ..., 100000000
  Encode to base62: 100000000 → "6LAze" (5 chars)
  
  def encode_base62(num):
      chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
      result = []
      while num:
          result.append(chars[num % 62])
          num //= 62
      return ''.join(reversed(result)) or '0'
  
  Pros:  No collision by definition (each ID is unique).
         Simple and fast.
  Cons:  Sequential IDs are predictable. User can enumerate URLs.
         Distributed ID generation needs coordination (Snowflake ID or similar).

APPROACH 3: Pre-generate random codes (Ticket Server)
  Background job pre-generates 1M random 7-char codes, stores in "available_codes" table.
  On shorten request: pop one code from the table (atomic DB operation).
  
  Pros:  No collision. No coordination. Fast at write time.
  Cons:  Upfront storage cost. Must keep table replenished.

RECOMMENDED (for interviews): Approach 2 with Snowflake IDs.
  Snowflake ID = 64-bit integer = timestamp(41b) + worker_id(10b) + sequence(12b)
  Globally unique without central coordination. Then base62 encode.

REDIRECT: 301 vs 302
  301 Permanent: Browser caches redirect. Next time: browser goes directly.
    Pros: less load on our servers.
    Cons: analytics broken (browser bypasses us).
  
  302 Temporary: Every redirect hits our server.
    Pros: we count every redirect for analytics.
    Cons: more server load.
  
  If analytics matter → 302. If reducing server load matters → 301.
  TinyURL: uses 301. Bit.ly: uses 302 (they sell analytics).
```

### Step 5 — Bottlenecks and Solutions

```
BOTTLENECK 1: Redirect latency
  575,000 redirects/sec. Each needs short_code → long_url lookup.
  
  Fix: Redis cache with high hit rate.
  Redis can handle 1M ops/sec. Cache most popular short codes.
  Top 20% of URLs = 80% of traffic (Pareto). Cache those 20%.
  Cache size: if 100M total URLs and top 20% = 20M × 607 bytes ≈ 12 GB of cache.
  Redis 16GB instance handles it.

BOTTLENECK 2: Single DB write bottleneck
  6,000 writes/sec. Single PostgreSQL handles ~10,000 writes/sec. Currently OK.
  Future: shard by first character of short_code (62 shards).
  Each shard handles ~100 writes/sec. Easily manageable.

BOTTLENECK 3: Single point of failure
  Redirect Service must be 99.99% available.
  Fix: 3+ stateless Redirect Service instances behind load balancer.
  Fix: Redis Sentinel or Redis Cluster for HA cache.
  Fix: PostgreSQL primary + 2 read replicas.
```

### Step 6 — Trade-offs Made

```
Trade-off 1: 302 vs 301 redirect
  Chose 302 → analytics visibility at cost of more server load.
  Alternative: 301 if we want to minimize infrastructure costs.

Trade-off 2: Cache TTL of 24 hours
  If URL is updated/deleted, cache serves stale redirect for up to 24h.
  Alternative: event-driven cache invalidation via Kafka. More complex.
  Acceptable here: URL updates are rare. 24h staleness is fine.

Trade-off 3: Snowflake IDs (predictable-ish, not truly random)
  Users can guess nearby IDs. Privacy concern for sensitive URLs.
  Alternative: Random UUID → no guessability. But collision handling needed.
  Fix: hash the snowflake ID to obfuscate it before returning.
```

---

## CASE STUDY 2: Instagram (Photo Feed)

### Step 1 — Requirements

```
Functional:
  - User uploads a photo with caption
  - User follows/unfollows other users
  - User sees a feed of recent photos from people they follow
  - User can like and comment on photos
  - User can view another user's profile (their photo grid)

Non-Functional:
  - 1 billion users, 500M DAU
  - 100M photos uploaded/day
  - Feed should load in < 200ms
  - Eventual consistency acceptable for feed (seeing a photo 1 second late is fine)
  - Photos must never be lost (durable storage)
  - High availability: users expect Instagram to always work
```

### Step 2 — Scale Estimation

```
Photo uploads:
  100M photos/day → 1,150 uploads/sec → peak ~6,000/sec
  Avg photo size after compression: 300KB
  Storage: 100M × 300KB = 30 TB/day → 11 PB/year

Feed reads:
  500M DAU × 10 feed opens/day = 5 billion feed requests/day
  5B / 86,400 ≈ 58,000 feed reads/sec → peak ~300,000/sec

Likes:
  500M users × 50 likes/day = 25B likes/day → 289,000 likes/sec
```

### Step 3 — High-Level Architecture

```
UPLOAD FLOW:
User → [Mobile App] → [API Gateway]
                           │
                    [Upload Service]
                       │         │
               [Object Store]  [Kafka: photo-uploaded]
                  (S3/GCS)         │
                                   ├──► [Thumbnail Worker] → CDN
                                   ├──► [Feed Fan-out Worker] → Redis feeds
                                   └──► [Content Moderation] → Review queue

FEED READ FLOW:
User → [API Gateway] → [Feed Service]
                              │
                      [Redis: feed:{user_id}]  ← pre-computed feed
                              │ (miss or celebrity tweet merge)
                      [Post Metadata DB (Cassandra)]
                              │
                      [CDN for photo URLs]
                      → Return: list of {photo_url, caption, like_count, ...}
```

### Step 4 — Deep-Dive: Feed Generation (Fan-out on Write)

```
THE PROBLEM: User A has 2M followers. A posts a photo.
  Naive: when User B opens feed, query "photos from everyone B follows" → slow JOIN.

INSTAGRAM'S APPROACH: Fan-out on write (pre-computed feeds).

On upload:
  1. Photo stored in S3.
  2. Event published to Kafka: {photo_id, author_id, created_at}
  3. Fan-out workers read event:
     
     def fan_out(photo_id, author_id):
         followers = db.get_followers(author_id)  # e.g., 2M followers
         for follower_id in followers:
             redis.lpush(f"feed:{follower_id}", photo_id)
             redis.ltrim(f"feed:{follower_id}", 0, 999)  # keep latest 1000

On feed read:
  photo_ids = redis.lrange(f"feed:{user_id}", 0, 19)  # get latest 20
  photos = [fetch_photo_metadata(pid) for pid in photo_ids]
  return photos  # hydrate with URLs, captions, likes

PROBLEM: Celebrities with 100M followers.
  100M Redis writes per post × popular creator = massive write spike.
  
FIX: Hybrid approach (same as Twitter).
  Regular users (< 1M followers): fan-out on write.
  Celebrities (> 1M followers): fan-out on read.
  
  Feed read for celebrity posts:
    user_feed = redis.lrange(f"feed:{user_id}", 0, 19)  # fan-out-on-write posts
    celebrity_posts = db.get_recent_posts_by_celebrities(user_follows_celebrities)
    merged = merge_by_timestamp(user_feed, celebrity_posts)[:20]
    return merged
```

### Step 5 — Deep-Dive: Photo Storage and CDN

```
UPLOAD:
  Mobile → direct upload to S3 via pre-signed URL (bypasses Instagram servers).
  Instagram server: just stores metadata (who uploaded what, when).
  
  Pre-signed URL flow:
    1. Mobile: POST /photos/prepare → server returns {upload_url, photo_id}
    2. Mobile: PUT {upload_url} (direct to S3) with photo bytes
    3. Mobile: POST /photos/complete?photo_id=abc → server marks as ready
  
  Why: avoids routing large payloads through Instagram's own servers.
  Instagram servers handle JSON (small), S3 handles binary (large).

PROCESSING (after upload):
  Kafka event triggers:
  - Resize to: 1080×1080, 640×640, 150×150 (thumbnail)
  - Convert to WebP (30% smaller than JPEG at same quality)
  - Store all variants in S3
  - Push CDN paths to metadata DB

CDN DISTRIBUTION:
  Instagram uses: Facebook's own CDN + Akamai + IPFS-like P2P for older content.
  Photo URL: cdn.instagram.com/{photo_id}_{resolution}.webp
  CDN has edge servers in 200+ cities.
  Popular photos (viral): cache hit rate 99.9%. Rarely fetches from S3.
  Old photos (2-year-old posts): may not be in CDN. Fetch from S3, cache for 1 hour.
  
  Cache-Control: max-age=86400 (CDN caches for 24h)
  Photos never change (immutable), so long TTL is safe.
```

### Step 6 — Trade-offs Made

```
Trade-off 1: Fan-out on write → high storage, write amplification
  Storing 1000 post IDs per user in Redis.
  500M users × 1000 IDs × 8 bytes = 4 TB of Redis storage.
  Alternative: fan-out on read (no storage, but slow reads).
  Decision: storage is cheap. Latency is expensive.

Trade-off 2: Eventual consistency for feed
  User A posts → followers see it within 3-5 seconds (fan-out time).
  During those 5 seconds: some followers see post, others don't.
  Alternative: synchronous fan-out → post confirmed only after all 2M fans notified.
  Decision: 5 seconds of inconsistency is invisible to users. Sync fan-out is 1000× slower.

Trade-off 3: Direct S3 upload (bypassing servers)
  Pros: no Instagram server handles photo bytes → massive bandwidth saving.
  Cons: client must make 3 API calls instead of 1. More complex mobile code.
  Decision: scale benefit >> complexity cost.
```

---

## CASE STUDY 3: WhatsApp (Messaging)

### Step 1 — Requirements

```
Functional:
  - 1-to-1 messaging (text, images, voice notes)
  - Group messaging (up to 512 members)
  - Delivery receipts: sent ✓, delivered ✓✓, read ✓✓ (blue)
  - Online/Last seen status
  - End-to-end encryption (E2EE)

Non-Functional:
  - 2 billion users, 100M messages/min (peak)
  - Message delivery: < 1 second for online recipient
  - Messages stored for offline delivery up to 30 days
  - E2EE: server must NOT be able to read message content
  - High availability: messages must never be lost
```

### Step 2 — Scale Estimation

```
Messages:
  100M messages/minute = 1.67M messages/sec (peak)
  Average: ~500K messages/sec

Storage:
  Text message: 100 bytes avg
  Image: 30KB (compressed by WhatsApp)
  Voice note: 60KB/min
  
  Assume 80% text, 15% image, 5% voice:
  Per message avg: 0.8×100B + 0.15×30KB + 0.05×60KB = 80B + 4.5KB + 3KB ≈ 7.6KB avg
  
  500K msg/sec × 7.6KB = 3.8 GB/sec
  Per day: 3.8GB × 86,400 = 328 TB/day
  
  BUT: WhatsApp stores messages max 30 days AND only until delivery confirmed.
  For delivered messages: delete from server. Keep only "in-flight" messages.
  Actual server storage: much less.

Connections:
  2B users. Peak concurrent connections: ~500M WebSocket connections.
  Each WebSocket = ~1 TCP connection = ~50KB memory.
  500M × 50KB = 25 TB RAM for connections alone.
  → Must shard across many connection servers.
```

### Step 3 — High-Level Architecture

```
SEND MESSAGE FLOW:
Alice (online) → [WebSocket to Connection Server A]
                         │
               [Message Service]
                   │            │
         [Message Store]   [Delivery Service]
         (Cassandra)            │
                          Is Bob online?
                          │           │
                    Bob online    Bob offline
                          │           │
               Push via WS    Store in Cassandra
               to Bob's       until Bob comes online
               Connection     (up to 30 days)
               Server

STATUS FLOW:
Alice opens app → connects WebSocket → 
  Presence Service marks Alice as online
  Notifies Alice's contacts who have Alice in their contact list
  Contacts receive: {user: Alice, status: online, last_seen: now}
```

### Step 4 — Deep-Dive: Message Delivery and Receipts

```
MESSAGE STATES:
  CLIENT_SENT    → Message left Alice's device
  SERVER_RECEIVED → Our server got it (✓)
  DELIVERED      → Bob's device received it (✓✓)
  READ           → Bob opened the conversation (✓✓ blue)

DELIVERY PROTOCOL:

1. Alice sends message (WebSocket):
   {
     "id": "msg_8721",
     "to": "bob_id",
     "content": "<encrypted bytes>",
     "timestamp": 1726458600
   }

2. Server receives it:
   - Store in Cassandra: messages(conversation_id, timestamp, sender, content, status)
   - Return ACK to Alice: {msg_id: "msg_8721", status: "SERVER_RECEIVED"}
   - Alice's UI shows ✓

3. Server checks if Bob is online:
   - Query Presence Service (Redis): is "bob_id" connected? Which server?
   - Yes → Bob's Connection Server B has his WebSocket
   - Route message to Connection Server B → push to Bob's WebSocket

4. Bob's device receives it:
   - Bob's client sends ACK back: {msg_id: "msg_8721", status: "DELIVERED"}
   - Server updates Cassandra status → notifies Alice
   - Alice's UI shows ✓✓

5. Bob opens conversation:
   - Bob's client sends READ receipt: {msg_id: "msg_8721", status: "READ"}
   - Server → Alice → Alice's UI shows ✓✓ (blue)

OFFLINE DELIVERY:
  Bob is offline. Message stored in Cassandra.
  Bob comes online → WebSocket reconnected → 
  Server: SELECT messages WHERE recipient=bob AND status=PENDING ORDER BY timestamp
  → Push all pending messages → Bob sends batch ACKs
  
  Cassandra schema for messages:
  CREATE TABLE messages (
    conversation_id UUID,
    message_id      TIMEUUID,    -- time-ordered UUID
    sender_id       UUID,
    content         BLOB,         -- encrypted bytes (E2EE: server can't read)
    status          TEXT,
    PRIMARY KEY (conversation_id, message_id)
  ) WITH CLUSTERING ORDER BY (message_id DESC);
  
  Partition key: conversation_id → all messages in one chat on same shard.
  Clustering key: message_id (time-ordered) → natural chronological order.
  Reads: O(1) to get latest messages. Perfect for chat.
```

### Step 5 — Deep-Dive: End-to-End Encryption

```
E2EE means: WhatsApp servers see ONLY encrypted bytes. Cannot read content.

Setup (Signal Protocol — what WhatsApp actually uses):
  Alice and Bob each have:
  - Identity key pair (long-term)
  - Signed pre-key pair (medium-term, rotated monthly)
  - One-time pre-keys (single-use)
  
  All public keys registered with WhatsApp Key Server.

Alice sends first message to Bob:
  1. Alice fetches Bob's public keys from Key Server.
  2. Alice computes a shared secret using Diffie-Hellman (never sent over network).
  3. Alice encrypts message with shared secret → ciphertext.
  4. Alice sends: {sender: alice, content: ciphertext, session_data: ...}
  5. Server routes ciphertext to Bob (cannot decrypt it).
  6. Bob uses his private keys + session_data → same shared secret → decrypts.

WhatsApp server never has:
  - Message content (only ciphertext)
  - The shared secret (never transmitted)
  - Private keys (stay on devices)

Server has:
  - Ciphertext (useless without keys)
  - Metadata: who messaged whom, when, how often (NOT content)
  - Public keys only
  
INTERVIEW: "How do you implement E2EE?" → Signal Protocol. 
Key exchange: X3DH (Extended Triple Diffie-Hellman).
Message encryption: Double Ratchet Algorithm (forward secrecy).
```

### Step 6 — Trade-offs Made

```
Trade-off 1: Store-and-forward vs peer-to-peer
  P2P: messages go directly device-to-device, no server storage.
    Pros: true privacy, no server storage cost.
    Cons: both must be online simultaneously. Offline delivery impossible.
  Store-and-forward: server buffers messages.
    Pros: offline delivery. Works with unreliable mobile connections.
    Cons: server must be trusted not to read messages (mitigated by E2EE).
  WhatsApp chose: store-and-forward with E2EE. Best of both.

Trade-off 2: Read receipts are opt-out, not opt-in
  Privacy concern: Alice knows when Bob read her message.
  WhatsApp allows disabling read receipts in settings.
  Disabling yours: others also can't see yours. Reciprocal.

Trade-off 3: Group size limit (512 members)
  Large groups require fan-out to 512 connections per message.
  512 × (push notification + Cassandra write) = manageable.
  10,000 members would require different architecture (pub/sub channels).
```

---

## CASE STUDY 4: Uber (Ride-Sharing)

### Step 1 — Requirements

```
Functional:
  - Rider requests a ride with pickup and dropoff location
  - Driver accepts/declines ride requests
  - Real-time matching: find nearest available driver
  - Real-time tracking: rider sees driver on map (updates every 5s)
  - Dynamic pricing (surge pricing based on supply/demand)
  - Trip completion and payment

Non-Functional:
  - 5M rides/day → ~60 rides/sec, peak ~300/sec
  - Driver location updates: every 5 seconds from 5M active drivers
  - Matching latency: < 1 second (rider shouldn't wait 10s to see "driver found")
  - GPS precision: ±10 meters
  - High availability: can't be down during surge (Super Bowl, New Year's)
```

### Step 2 — Scale Estimation

```
Driver location updates:
  5M active drivers × 1 update/5s = 1M location updates/sec
  Each location: {driver_id, lat, lng, timestamp, heading} ≈ 60 bytes
  Throughput: 1M × 60 bytes = 60 MB/sec of location data

Ride requests:
  5M rides/day / 86,400 = 58 req/sec average, ~300/sec peak

Matching:
  For each ride request: find all drivers within 5km radius.
  5M drivers. Geographic search. Must complete in < 100ms.
  → Geospatial indexing required. Cannot do linear scan.

Storage:
  Driver location: write-heavy, high cardinality, low retention (only need current + last 1h).
  Trips: write once, read many (for receipts, history, analytics).
```

### Step 3 — High-Level Architecture

```
DRIVER APP:
  Driver App → [Location Service] → Redis Geo / H3 Grid
                                         │
RIDER REQUEST:                    [Dispatch Service]
  Rider App → [Request Service]         │
                   │              Find nearby drivers
                   └──────────────► Match → notify driver
                                         │
                              [Driver App WebSocket]
                                         │
                              Driver accepts → Trip starts
                                         │
                          [Trip Tracking Service]
                          (both rider and driver WebSocket)
                                         │
                          [Maps Service] (ETA, route)
                                         │
                    [Pricing Service] (surge, fare estimate)
                                         │
                    [Payment Service] (charge at trip end)
```

### Step 4 — Deep-Dive: Driver Location and Geo-Search

```
DRIVER LOCATION STORAGE:

Option 1: Redis GEOADD
  redis.geoadd("drivers:active", longitude, latitude, driver_id)
  redis.georadius("drivers:active", rider_lng, rider_lat, 5, "km", 
                  count=20, sort="ASC")
  
  Pros: built-in. Simple.
  Cons: All drivers in ONE Redis key. Can't shard by geography easily.
        At 5M drivers: ~500MB in one key. Hard to scale.

Option 2: H3 Hexagonal Grid (what Uber actually uses)
  H3 = Uber's open-source geospatial indexing library.
  World divided into hexagonal cells at various resolutions.
  
  Resolution 7 (≈ 1.2 km² cells):
    Driver's location → H3 cell index (12-digit integer)
    Store: Redis hash per H3 cell.
    
  Rider requests ride:
    1. Compute rider's H3 cell.
    2. Get adjacent cells (ring of 7 hexagons covers ≈ 3-4 km radius).
    3. Union of drivers in those 7 cells = nearby drivers.
    4. Sort by actual distance → top 10 candidates.
    
  driver_location_update(driver_id, lat, lng):
    old_cell = get_current_cell(driver_id)
    new_cell = h3.geo_to_h3(lat, lng, resolution=7)
    if old_cell != new_cell:
        redis.srem(f"cell:{old_cell}", driver_id)
        redis.sadd(f"cell:{new_cell}", driver_id)
    redis.hset(f"driver:{driver_id}", mapping={"lat": lat, "lng": lng, "ts": now()})
  
  Pros: horizontally scalable (each cell = separate Redis key).
        Natural sharding by geography.
        Lookup is O(1) for cell, O(k) where k = drivers in nearby cells (small).

MATCHING ALGORITHM (simplified):
  1. Find all active drivers in H3 radius (≈20 drivers typically).
  2. Filter: is driver accepting rides? Not on another trip?
  3. Rank by: distance + driver rating + car type.
  4. Offer to #1 ranked driver → 15-second acceptance window.
  5. If declined: offer to #2. Repeat until accepted.
  6. If all decline: expand search radius.
```

### Step 5 — Deep-Dive: Surge Pricing

```
GOAL: Price rises when demand > supply in a zone, to attract more drivers.

APPROACH:
  Every minute, for each geographic zone (H3 cell at resolution 5 ≈ 252 km²):
    supply = count of active drivers in zone
    demand = count of pending ride requests in zone
    
    if demand / supply > 2.0:
        surge = 2.0x
    elif demand / supply > 1.5:
        surge = 1.5x
    else:
        surge = 1.0x (no surge)
  
  Store: redis.set(f"surge:{zone_id}", 2.0, ex=60)  # recalculate every 60s

WHY REDIS:
  Read by every ride request (rider gets fare estimate).
  115,000 reads/sec. Redis at 1M ops/sec handles this easily.
  Tolerable staleness: 60 seconds (surge is approximate anyway).

EDGE CASE: New Year's Eve in NYC.
  10,000 ride requests in 1 minute in a 5km zone. 200 active drivers.
  demand/supply = 50× → surge cap (usually 5-10×).
  Uber caps surge to avoid PR backlash.
  Notification to rider: "Prices are 4.2× higher than normal."
```

### Step 6 — Trade-offs Made

```
Trade-off 1: Eventual consistency for driver location
  Driver location in Redis. If driver moves, we update Redis.
  Rider sees location with ~5 second lag (driver sends update every 5s).
  Alternative: real-time via P2P WebRTC → complex, battery-intensive.
  Decision: 5-second lag is imperceptible to humans in a car.

Trade-off 2: Driver matching is centralized, not P2P
  Dispatch service has global view of all drivers → optimal matching.
  Decentralized (driver apps talk to each other) → harder coordination.
  Decision: centralized is simpler and more controllable.

Trade-off 3: H3 over simple radius search
  H3 adds code complexity (Uber had to open-source a library).
  Benefit: geographic sharding that Redis GEO can't do.
  Decision: at 5M drivers, scale wins over simplicity.
```

---

## CASE STUDY 5: Netflix (Video Streaming)

### Step 1 — Requirements

```
Functional:
  - Browse catalog (search, recommendations, categories)
  - Stream videos (1080p HD, 4K HDR)
  - Resume watching from where you left off (watch progress)
  - Download for offline viewing
  - Continue watching list / watchlist

Non-Functional:
  - 220M subscribers, 100M+ daily active
  - 1 billion hours watched/day
  - Video start latency < 2 seconds (player loads fast)
  - Zero rebuffering (no spinner while watching)
  - Global: users in 190+ countries
  - Content library: 15,000+ titles
```

### Step 2 — Scale Estimation

```
(Already computed in Prerequisites.md Topic 11.10)
  Peak bandwidth: ~1 Tbps
  Storage: ~9 PB (content, 3× replicated)
  Concurrent streams at peak: 15-20 million simultaneous streams
  Video start requests: ~11,500/sec at peak

Encoding:
  Each title encoded in 10+ profiles: 240p, 360p, 480p, 720p, 1080p, 4K, HDR10, Dolby Vision.
  Each profile: split into 10-second HLS segments.
  15,000 titles × 10 profiles × avg 2-hour movie × 6 segments/min = 180M segments
  Total segments: 180M × avg 5MB/segment = 900 TB of segments
  With 3× replication: 2.7 PB just for segments.
```

### Step 3 — High-Level Architecture

```
BROWSE:
User → [API Gateway] → [Catalog Service] → [Recommendation Model]
                               │
                    [ElasticSearch] (search)
                    [DynamoDB] (metadata: title, cast, genre)
                    [Redis] (top charts, featured content)

PLAY:
User clicks Play → [Playback Service]
                       │
              [Open Connect CDN] ← nearest ISP-embedded appliance
                       │
              [HLS Video Segments] → streamed to player
              
              Meanwhile:
              [Adaptive Bitrate Controller] ← monitors bandwidth
              Switches quality: 4K → 1080p → 720p (automatic, seamless)

CONTINUE WATCHING:
Every 30s while watching:
User player → [Watch Progress Service] → Cassandra
                                         {user_id, content_id, progress_seconds}
On next login: read progress → resume from that timestamp.
```

### Step 4 — Deep-Dive: CDN Strategy (Open Connect)

```
PROBLEM: 1 Tbps of video traffic. AWS bandwidth costs = ~$100M/month at standard rates.

NETFLIX'S SOLUTION: Open Connect
  Netflix manufactures custom CDN servers.
  Deploys them inside ISP data centres (free of charge for ISP — saves ISP bandwidth).
  Content pre-loaded nightly by Netflix.
  
  HOW IT WORKS:
    1. Netflix predicts which content will be popular tomorrow (recommendation model).
    2. Overnight: push those video segments to Open Connect appliances at each ISP.
    3. During the day: 99% of streams served from Open Connect (inside ISP network).
    4. User's traffic never leaves their ISP → zero transit bandwidth cost for Netflix.
    5. ISP happy: they're not paying transit bandwidth either.

  Open Connect hardware:
    Each appliance: 200+ TB of storage (SSD + HDD), 100 Gbps NIC.
    ~17,000 appliances deployed in 6,000+ locations globally.

ADAPTIVE BITRATE STREAMING (ABR):
  Video encoded as: 240p, 360p, 480p, 720p, 1080p, 4K.
  Each quality split into 10-second segments.
  
  HLS Manifest:
    #EXTM3U
    #EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360
    /segments/360p/seg_{n}.ts
    #EXT-X-STREAM-INF:BANDWIDTH=3000000,RESOLUTION=1920x1080
    /segments/1080p/seg_{n}.ts
    #EXT-X-STREAM-INF:BANDWIDTH=8000000,RESOLUTION=3840x2160
    /segments/4k/seg_{n}.ts

  Player logic:
    measure_bandwidth = total_bytes_received / time
    if bandwidth > 8Mbps: request 4K segments
    if bandwidth drops to 3Mbps: switch to 1080p (seamless, mid-playback)
    if bandwidth drops to 500Kbps: switch to 240p (stutter prevention)
    
    Buffer: player pre-loads 60 seconds of video ahead of playback position.
    Why: absorbs network fluctuations. User doesn't see rebuffering if brief dropout.
    
  BUFFER SIZE TRADE-OFF:
    60s buffer: needs 60 × segment_size downloaded ahead → uses memory and bandwidth.
    5s buffer: less memory, but brief network hiccup → rebuffering.
    Netflix tested: users tolerate 0 rebuffering but not 0 quality.
    Decision: larger buffer, let ABR drop quality before rebuffering.
```

### Step 5 — Deep-Dive: Recommendations (Collaborative Filtering)

```
220M users × 15,000 titles = 3.3 billion potential user-title interactions.

MATRIX FACTORIZATION (simplified):
  Matrix: users (rows) × titles (columns). Values: ratings (1-5) or implicit (watched?).
  Most entries are 0 (user hasn't watched most titles).
  
  Decompose: M ≈ Users × Titles (two smaller matrices, k=100 latent factors)
  Each user = 100-dimensional vector (captures preferences: likes comedy, prefers 2h movies, etc.)
  Each title = 100-dimensional vector (captures: it's a comedy, 2h long, etc.)
  
  Recommendation: for user U, multiply U's vector by ALL title vectors.
  Top 20 highest dot-product titles = recommendations.
  
  Scale:
    220M users × 100 dims × 4 bytes = 88 GB (user matrix — fits in memory cluster)
    15,000 titles × 100 dims × 4 bytes = 6 MB (title matrix — fits in single machine RAM)
    
  Inference time: 220M dot products = fast with GPU/matrix ops.
  
  TRAINING: Weekly batch job (Spark on EMR).
  PERSONALIZATION: Real-time signals (last 10 interactions) update recommendations within session.

WHY 90 ROWS IN YOUR NETFLIX HOME:
  "Continue Watching", "New Releases", "Top 10 in India", 
  "Because you watched Stranger Things", "Trending Now"...
  
  Each row is a different recommendation algorithm result.
  Netflix A/B tests which row ordering leads to more watches.
  The homepage you see is the result of thousands of A/B tests over years.
```

### Step 6 — Trade-offs Made

```
Trade-off 1: Own CDN (Open Connect) vs third-party CDN
  Third-party (Akamai, Cloudflare): pay per GB, no hardware investment.
  Own CDN: hardware cost (~$500M), but saves ~$1B+/year in bandwidth.
  Decision: at Netflix's scale, owning CDN saves money AND gives control.

Trade-off 2: Push content to CDN proactively vs on-demand
  On-demand CDN: first user in each ISP region triggers fetch from origin.
  Proactive: Netflix pushes content nightly based on predictions.
  Decision: proactive wins because Netflix can predict well (recommendation model).
  10,000 users in Mumbai will ALL want to watch the new Squid Game episode Friday night.
  Better to pre-push it at 3am than have 10,000 simultaneous origin fetches at 8pm.

Trade-off 3: Centralized recommendation vs federated
  Federated: model trained on-device (privacy-preserving).
  Centralized: all user data aggregated → better model accuracy.
  Netflix chose: centralized (better recommendations). Trade-off: user data on Netflix's servers.
  Mitigated by: strong security, compliance with GDPR (users can delete data).
```

---

## QUICK REFERENCE: Case Study Comparison

| System | Core Challenge | Key Technology | CAP Choice |
|--------|---------------|----------------|------------|
| URL Shortener | High read throughput, unique code generation | Redis cache, base62 encoding, Snowflake ID | AP (reads are slightly stale from cache — fine) |
| Instagram | Fan-out at celebrity scale, media storage | Redis timelines, S3+CDN, hybrid fan-out | AP (feed staleness ok) |
| WhatsApp | Message delivery guarantees, E2EE, offline | Cassandra, Signal Protocol, WebSocket | CP for delivery (no message loss), AP for status |
| Uber | Real-time geo-search, matching, surge | Redis Geo + H3, WebSocket, Kafka | AP (5-second location lag is fine) |
| Netflix | 1Tbps bandwidth, global delivery | Open Connect CDN, ABR, matrix factorization | AP (different quality levels = availability) |

---

*See `02_Interview_Framework.md` for the step-by-step template to use in any HLD interview.*

# Topic 10: Numbers Every Engineer Must Know
## HLD Deep Dive — Back-of-Envelope Estimation Reference

---

## 1. Latency Numbers (2024 Reference)

```
OPERATION                     │ LATENCY      │ NOTES
──────────────────────────────┼──────────────┼────────────────────────────
L1 cache reference            │ 1 ns         │ CPU cache
L2 cache reference            │ 4 ns         │ 4× L1
RAM read                      │ 100 ns       │ 100× L1
SSD random read (4KB)         │ 100 μs       │ 100,000 ns. NVMe: 20-50μs
HDD seek + read               │ 10 ms        │ 10,000,000 ns. 100,000× L1
Redis GET (local network)     │ < 1 ms       │ In-memory. Target: 0.5ms
PostgreSQL query (with index) │ 1-5 ms       │ Simple indexed query
PostgreSQL query (full scan)  │ 10ms–10s     │ Depends on table size
Network: same DC (round trip) │ 0.5-1 ms     │ Within one data centre
Network: same region (RTT)    │ 1-10 ms      │ US-East to US-East2
Network: cross-region (RTT)   │ 30-100 ms    │ US-East to EU-West
Network: cross-continent      │ 100-300 ms   │ US to India/Asia
DNS lookup (cached ISP)       │ 1-10 ms      │ Cached resolution
DNS lookup (full resolution)  │ 50-200 ms    │ Root → TLD → authoritative
TLS handshake (TLS 1.3)       │ 1 RTT        │ 1 round trip after TCP
TCP handshake                 │ 1 RTT        │ SYN → SYN-ACK → ACK
Kafka produce (async)         │ < 1 ms       │ Local buffer, not flushed
Kafka produce (sync, acks=all)│ 5-15 ms      │ Wait for all replicas
Elasticsearch index           │ 1s per batch │ Default refresh interval

RULE OF THUMB FOR ESTIMATION:
  In-memory operations: nanoseconds.
  Disk I/O (SSD):       microseconds.
  Network (same DC):    milliseconds.
  Network (cross-region): tens of milliseconds.
  Human perception:     > 100ms feels slow, > 1s feels broken.
```

---

## 2. Throughput Numbers

```
SYSTEM                        │ THROUGHPUT       │ NOTES
──────────────────────────────┼──────────────────┼──────────────────────────
Redis single instance         │ 100K-1M ops/sec  │ GET/SET. Scales with cluster.
Redis Cluster (10 nodes)      │ 5-10M ops/sec    │ Horizontally sharded
Kafka single partition        │ 100K msg/sec     │ Write + consume
Kafka broker (3 partitions)   │ 1M msg/sec       │ Parallelism across partitions
Kafka cluster (large)         │ 10M+ msg/sec     │ LinkedIn: 7 trillion msg/day
PostgreSQL writes             │ 10K-50K/sec      │ With WAL, ACID compliance
PostgreSQL reads (with index) │ 100K/sec         │ Simple indexed reads
Cassandra writes              │ 1M/sec           │ Per node. Single-shard
MySQL reads (SSD)             │ 100K/sec         │ Simple indexed reads
Nginx requests                │ 50K-100K req/sec │ Static files
Single app server             │ 1K-10K req/sec   │ Typical web API (Python/Java)
Go/Rust service               │ 10K-100K req/sec │ Compiled, async
DynamoDB                      │ Unlimited        │ Managed auto-scaling
S3 GET                        │ 5,500 req/sec    │ Per prefix. More with prefixes
S3 PUT                        │ 3,500 req/sec    │ Per prefix
HTTP download (1 Gbps link)   │ 125 MB/sec       │ Network limit

NETWORK BANDWIDTH:
  1 Gbps NIC:  125 MB/sec = 125,000 KB/sec
  10 Gbps NIC: 1.25 GB/sec (typical in DCs)
  100 Gbps NIC: 12.5 GB/sec (high-throughput servers, Kafka)
  AWS cross-AZ: up to 25 Gbps (within region)
```

---

## 3. Storage Size Reference

```
DATA TYPE                     │ SIZE          │ NOTES
──────────────────────────────┼───────────────┼───────────────────────────────
1 ASCII character             │ 1 byte        │
1 Unicode character (UTF-8)   │ 1-4 bytes     │ Avg 1.5 bytes for English text
UUID (string)                 │ 36 bytes      │ "550e8400-e29b-41d4-a716-..."
UUID (binary)                 │ 16 bytes      │ Stored as BINARY(16) in DB
Integer (32-bit)              │ 4 bytes       │
Long/BigInt (64-bit)          │ 8 bytes       │
Float (64-bit)                │ 8 bytes       │
Timestamp                     │ 4-8 bytes     │ Unix epoch: 4 bytes. With microseconds: 8
JSON overhead                 │ ~30-100 bytes │ Keys + braces + quotes
Average tweet                 │ 300 bytes     │ 280 chars + metadata
Average REST API response     │ 1-10 KB       │ JSON body
Average image (JPEG, mobile)  │ 3 MB          │ Before compression
Average image (WhatsApp)      │ 30-100 KB     │ Heavily compressed
Average video (1 minute, HD)  │ 150 MB        │ h264
Average video (1 minute, 4K)  │ 500 MB        │ h265/HEVC compressed
Average audio (MP3, 1 min)    │ 1 MB          │ 128 kbps
Average song (MP3)            │ 5 MB          │ 4-6 min at 128 kbps
Average ebook                 │ 2 MB          │
Netflix show episode (1080p)  │ 2-4 GB        │ Uncompressed source
Netflix show episode (stream) │ 700 MB-2 GB   │ Multiple encoded profiles

STORAGE UNITS:
  1 KB  = 10^3 bytes  = 1,000 bytes
  1 MB  = 10^6 bytes  = 1,000 KB
  1 GB  = 10^9 bytes  = 1,000 MB
  1 TB  = 10^12 bytes = 1,000 GB
  1 PB  = 10^15 bytes = 1,000 TB
  1 EB  = 10^18 bytes = 1,000 PB
  
  Instagram: ~100M photos/day × 300KB = 30 TB/day ≈ 10 PB/year.
  WhatsApp: ~100B messages/day × ~1KB avg = 100 TB/day.
  Netflix: 15,000 titles × 10 profiles × 20GB = 3 PB content library.
  YouTube: 500 hours of video uploaded every minute.
```

---

## 4. Time Constants

```
TIME UNIT                     │ SECONDS       │ COMMON USE
──────────────────────────────┼───────────────┼───────────────────────────
1 minute                      │ 60            │ TTL for volatile cache
5 minutes                     │ 300           │ Common Redis TTL for user data
1 hour                        │ 3,600         │ Session TTL
1 day                         │ 86,400        │ Daily reports, CDN TTL for assets
1 week                        │ 604,800       │ Kafka retention default
30 days                       │ 2,592,000     │ WhatsApp message retention
1 year                        │ 31,536,000    │ Certificate validity
5 years                       │ 157,680,000   │ Long-term data retention

USEFUL APPROXIMATIONS:
  1 million seconds ≈ 11.5 days
  1 billion seconds ≈ 31.7 years
  
  Seconds per day: 86,400 ≈ 10^5 (use this for estimation!)
  Seconds per year: ~31.5 million ≈ π × 10^7

REQUEST RATE CONVERSION:
  1M requests/day    = 1M / 86,400  ≈ 12 req/sec
  10M requests/day   ≈ 116 req/sec
  100M requests/day  ≈ 1,160 req/sec
  1B requests/day    ≈ 11,600 req/sec
  10B requests/day   ≈ 116,000 req/sec
  
  Instagram: 500M DAU × 10 feed opens/day = 5B opens/day ≈ 58,000 opens/sec
  Twitter: 350M users × 0.5 tweets/day = 175M tweets/day ≈ 2,000 tweets/sec
```

---

## 5. Worked Estimation Examples

```
EXAMPLE 1: ESTIMATE STORAGE FOR TWITTER

Given:
  350M users, 50% daily active = 175M DAU
  Each user: 0.5 tweets/day avg
  Keep data 5 years

Daily tweets:
  175M × 0.5 = 87.5M tweets/day

Storage per tweet:
  tweet_id: 8 bytes (BigInt)
  user_id: 8 bytes
  text: 300 bytes avg (280 chars + unicode overhead)
  created_at: 8 bytes
  metadata: 50 bytes (likes_count, retweets, language, source)
  Total: ~374 bytes ≈ 400 bytes/tweet

Daily storage:
  87.5M × 400 bytes = 35 GB/day

5-year storage:
  35 GB/day × 365 × 5 = 63,875 GB ≈ 64 TB

With 3× replication: 192 TB

Media (photos/videos, 20% of tweets):
  17.5M media tweets/day
  50% images avg 200KB, 50% videos avg 5MB
  Images: 8.75M × 200KB = 1.75 TB/day
  Videos: 8.75M × 5MB  = 43.75 TB/day
  Total media: ~45 TB/day × 365 × 5 years = 82 PB (images + videos, 5 years)

Read QPS:
  Timeline reads: 175M DAU × 10 opens/day = 1.75B reads/day ≈ 20,000 reads/sec
  Peak (5×): 100,000 reads/sec

Write QPS:
  87.5M tweets/day ÷ 86,400 ≈ 1,000 writes/sec. Peak: 5,000/sec

CONCLUSIONS:
  Text storage: 64 TB (5 years) — manageable with sharding
  Media: 82 PB — object store (S3), CDN for reads
  Read QPS: 100K peak — Redis cache, multiple read replicas
  Write QPS: 5,000/sec — manageable with good DB setup (PostgreSQL sharded)

───────────────────────────────────────────────────────────────────────

EXAMPLE 2: ESTIMATE REQUIREMENTS FOR UBER

Given:
  5M active drivers globally
  5M rides/day

Ride creation:
  5M/day ÷ 86,400 ≈ 58 rides/sec. Peak (6PM-8PM): 300 rides/sec.

Driver location updates:
  5M drivers × 1 update/5 seconds = 1M updates/sec
  Each update: driver_id(8B) + lat(8B) + lng(8B) + timestamp(8B) + heading(4B) ≈ 36 bytes
  Throughput: 1M × 36B = 36 MB/sec writes

Storage for locations:
  Only need current + last 1 hour (for tracking history).
  5M drivers × 3600 seconds = 18B location records/hour
  At 36 bytes each = 648 GB/hour → only keep last 10 min: 108 GB in Redis
  Use Redis GEO: 5M drivers × ~50 bytes = 250 MB for current positions

Trip storage:
  5M trips/day × 365 = 1.825B trips/year
  Per trip: 500 bytes (start/end location, timestamps, driver, rider, price)
  Storage: 1.825B × 500 = 912 GB/year ≈ 1 TB/year → 5 TB in 5 years (manageable)

CONCLUSIONS:
  Location updates: 1M/sec — Redis cluster (not SQL), H3 geospatial indexing
  Matching: must complete in <1s — in-memory geospatial query (Redis GEO / H3)
  Trips: 5 TB in 5 years — PostgreSQL with sharding by city/region

───────────────────────────────────────────────────────────────────────

EXAMPLE 3: DESIGN YOUTUBE — ESTIMATE STORAGE

Given:
  2B users, 500M DAU
  500 hours of video uploaded every minute
  1B hours watched every day

Upload storage:
  500 hours/minute × 60 minutes = 30,000 hours/hour
  30,000 hours × 3,600 seconds × 5 Mbps (upload bitrate) = 540 TB/hour
  Wait, let me recalculate:
  500 hours/min raw video. After encoding (10 profiles):
  1 hour raw → encode to 10 profiles × avg 2GB/hour = 20GB
  500 hours × 20GB = 10,000 GB = 10 TB per minute of upload
  Per day: 10 TB/min × 1440 min = 14.4 PB/day

That's extreme because 500 hours/minute is massive.
YouTube actually stores videos compressed:
  1 hour 1080p h265: ~1.5 GB per profile
  500 hours/minute × 10 profiles × 1.5 GB = 7.5 TB/minute → 10.8 PB/day

For estimation purposes:
  With CDN and popular content caching:
  95% of views from CDN cache.
  Only 5% from origin = 50M hours/day served from origin.
  Origin bandwidth: 50M × 3600 × 5 Mbps = 900 PB/day in bits = 112 TB/sec

This is why YouTube has massive CDN infrastructure.

Storage growth: ~1 PB/day of new content (after compression).
5-year storage: ~1,800 PB = 1.8 EB of video content.

That's why YouTube's storage costs are enormous.
```

---

## 6. QPS → Infrastructure Sizing

```
RULE OF THUMB:
  1 app server (Python/Django):  1,000 req/sec
  1 app server (Java/Go):        10,000 req/sec
  1 PostgreSQL primary:          10,000-50,000 reads/sec (indexed)
  1 PostgreSQL primary:          5,000-10,000 writes/sec
  1 Redis node:                  100,000-500,000 ops/sec
  1 Kafka broker:                500,000 msg/sec produce/consume

SIZING A SYSTEM AT 10,000 req/sec (peak):
  App tier:  10 Python servers (1K each) or 1-2 Go servers
  Cache:     1 Redis node (handles 100× req/sec) — hits on 90% → 1000 DB req/sec
  DB reads:  1 PostgreSQL primary (50K) handles 1000 DB req/sec easily
             + 2 read replicas for safety
  DB writes: (say 10% of requests are writes = 1000 writes/sec)
             1 PostgreSQL primary handles this

SIZING A SYSTEM AT 1,000,000 req/sec (peak):
  App tier:  100 Go servers or 1000 Python servers (auto-scaling)
  Cache:     Redis Cluster (10+ nodes). Hit rate 95% → 50K DB req/sec
  DB reads:  10 read replicas
  DB writes: 10K writes/sec → consider sharding (each shard handles 1K writes)
  Message queue: Kafka (not optional at this scale — decouple everything)
  CDN: 90%+ of requests served from CDN (never reach app servers)
```

---

## 7. Estimation Template

```
USE THIS TEMPLATE IN EVERY INTERVIEW:

Step 1: Users
  DAU = ?
  MAU = ?

Step 2: Requests
  Writes per user per day = ?
  Reads per user per day = ?
  
  Write QPS = DAU × writes_per_day / 86,400
  Read QPS  = DAU × reads_per_day  / 86,400
  Peak QPS  = average × 5

Step 3: Storage
  Record size = ? bytes
  Records per day = write_QPS × 86,400
  Retention = ? years
  Total storage = records_per_day × record_size × 365 × years
  With replication (3×) = total × 3

Step 4: Bandwidth
  Write bandwidth = write_QPS × request_size
  Read bandwidth  = read_QPS  × response_size

Step 5: Cache
  What % of reads can be cached? (usually 80-95% for read-heavy)
  DB reads = read_QPS × (1 - cache_hit_rate)
  Cache size = hot_data_size (top 20% data = 80% traffic by Pareto)

Step 6: Servers
  App servers needed = peak_QPS / per_server_capacity
  DB: can primary handle write_QPS? If not → shard.
  DB: can read_replicas handle DB_read_QPS? Add replicas if needed.

PRINT/WRITE THIS OUT:
  Users:   [X] DAU
  Writes:  [X] QPS avg, [Y] QPS peak
  Reads:   [X] QPS avg, [Y] QPS peak
  Storage: [X] GB/day, [Y] TB/5-years
  Cache:   [X]% hit rate, [Y] GB Redis needed
```

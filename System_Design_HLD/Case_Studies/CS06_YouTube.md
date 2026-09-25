# CS06 — YouTube at Scale

## Core Requirements

**Functional:**
- Upload videos (up to 10GB, multiple formats)
- Stream video (adaptive bitrate, any device/connection)
- Search videos by title, description, tags
- Like, comment, subscribe, notifications
- Recommendations / homepage feed

**Non-functional:**
- 2B+ users, 500 hours of video uploaded per minute
- 1B+ video views per day
- Read-heavy (100:1 read/write)
- Eventual consistency acceptable for counts (likes/views)
- Low latency streaming (<2s to start)
- High availability (99.99%)

**Capacity (back of envelope):**
- 500 hrs uploaded/min = ~30,000 min/min → encode 3 formats (360p, 720p, 1080p)
- Storage: 500 hrs * 60 * ~1MB/sec (raw) ≈ 30TB/min → compressed ~2TB/min
- 1B views/day = ~11,500 views/sec (peak 3x = 35,000/sec)
- CDN serves 99% of traffic — origin barely hit

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────┐
│                   CLIENTS                            │
│         Web / Mobile / Smart TV                      │
└──────────────┬───────────────────────────────────────┘
               │
               ▼
        ┌──────────────┐
        │  API Gateway │  Auth, Rate Limiting, Routing
        └──────────────┘
         /      |       \
        ▼       ▼        ▼
   [Upload]  [View]   [Search]
   Service  Service   Service
     │         │          │
     ▼         ▼          ▼
[Raw Storage] [CDN]  [Elasticsearch]
[Transcoding]
[Metadata DB]
```

---

## Upload Pipeline

```
Creator → Upload Service → Raw Storage (S3)
                         → Message Queue (Kafka topic: "video.uploaded")
                                         ↓
                              Transcoding Workers (pick from queue)
                              ├── encode 360p → Object Store
                              ├── encode 720p → Object Store
                              └── encode 1080p → Object Store
                                         ↓
                              Thumbnail Generator
                                         ↓
                              Metadata Service → Write to DB
                                         ↓
                              CDN Propagation (push to edge nodes)
                                         ↓
                              Status Update → Creator notified
```

### Transcoding
- Raw video → multiple resolutions + bitrates (HLS segments)
- Each segment = 5-10 second chunk (.ts files) + manifest (.m3u8)
- Workers are stateless, horizontally scalable
- Use GPU instances for encoding speed
- Handle failures: each segment independently retried

---

## Video Storage & Delivery

### Object Storage (S3/GCS)
- Videos stored as HLS segments (not one big file)
- Each video has unique video_id → `videos/{video_id}/720p/{segment}.ts`
- Immutable once stored

### CDN (Content Delivery Network)
- 100+ edge PoPs worldwide
- On first request → CDN misses → fetches from origin → caches at edge
- Subsequent requests → served from edge (< 50ms)
- Popular videos: pushed proactively to CDN before users request
- Adaptive bitrate: client measures bandwidth → switches manifest → different resolution segments

---

## Metadata Database

```sql
-- Videos
CREATE TABLE videos (
    video_id    UUID PRIMARY KEY,
    title       TEXT,
    description TEXT,
    channel_id  UUID,
    status      ENUM('processing', 'ready', 'deleted'),
    duration_s  INT,
    created_at  TIMESTAMP
);

-- Sharding: shard by video_id (hash-based)
-- Read replicas for high read traffic
```

**Denormalization:**
- Cache view count in Redis (flush to DB every N seconds)
- Don't hit DB for every view — too expensive at 11,500 views/sec

---

## View Count — Eventual Consistency

```
User clicks play
    ↓
View Event → Kafka (topic: view_events)
    ↓
View Count Consumer → Redis INCR video:{video_id}:views
    ↓ (every 30 seconds)
Batch Job → flush Redis → UPDATE videos SET views = X WHERE id = Y
```

**Why not update DB directly?** 11,500 views/sec × DB write = too expensive.
Redis INCR is O(1) and in-memory — handles millions/sec.

---

## Search

- Elasticsearch indexes: title, description, tags, channel_name, transcript
- On video upload: write to Kafka → Search Indexer consumes → updates ES
- Query: multi-field search with BM25 relevance + recency boost
- Autocomplete: Trie or ES completion suggester

---

## Recommendations

- Collaborative filtering: users who watched X also watched Y
- Feature store: user watch history, liked videos, search queries
- ML model: candidate generation (hundreds from millions) → ranking → top 20
- Precompute for each user: batch job every few hours
- Real-time signal: incorporate last 1 hour of activity for freshness

---

## Notifications (Fan-out on Subscribe)

```
Creator uploads video
    ↓
Notification Service → reads subscriber list (can be millions)
    ↓
Fan-out: push to Kafka (partition by user_id)
    ↓
Push Workers → send via FCM/APNs (mobile) or WebSocket/SSE (web)
```

**Hot creator problem:** MrBeast has 200M subscribers.
Fan-out to 200M users simultaneously = millions of DB reads + queue writes.
**Fix:** Pull model for large channels — client polls on open (lazy fan-out).

---

## Key Design Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Video storage | Object Store (S3) + CDN | Infinite scale, low latency delivery |
| Video format | HLS segments | Adaptive bitrate, seekable, CDN-friendly |
| View count | Redis → async flush | Too many writes for DB directly |
| Transcoding | Async via Kafka | Decoupled, retryable, scalable |
| Search | Elasticsearch | Full-text, relevance ranking, scalable |
| Metadata DB | PostgreSQL + read replicas | ACID for video metadata |
| Recommendations | Offline batch + feature store | Too expensive real-time at scale |

---

## Google Interview Focus Points

1. **Why HLS over single file?** Seekable, adaptive bitrate, CDN-cacheable segments
2. **How to handle view count at scale?** Redis counter → async DB flush
3. **CDN cache invalidation?** Use immutable URLs with version (video never changes once transcoded)
4. **Transcoding failure?** Kafka offset commit only on success → retry
5. **Database sharding?** Shard by video_id for videos, by user_id for watch history
6. **Fan-out for top creators?** Hybrid: push for small channels, pull for large

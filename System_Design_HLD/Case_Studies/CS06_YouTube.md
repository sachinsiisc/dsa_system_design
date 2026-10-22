# CS06: Design YouTube (Video Platform)
## Full HLD Case Study | MAANG Interview Ready

---

## STEP 1 — Requirements Clarification (say this in interview)

```
"Before I start designing, let me clarify requirements and set scope."

FUNCTIONAL:
  1. Video upload: creators upload videos up to 10 GB, any format (MP4, MOV, AVI, MKV)
  2. Video streaming: adaptive bitrate, any device (mobile/desktop/TV), any connection speed
  3. Search: full-text search by title, description, tags, transcript (auto-generated)
  4. Recommendations: personalized homepage feed and sidebar
  5. Engagement: likes, dislikes, comments, subscribe to channels
  6. Notifications: subscribers notified when channel uploads
  7. Analytics: creator dashboard — views, watch time, revenue, traffic sources
  8. Live streaming (out of scope for this session, can discuss as follow-up)

NON-FUNCTIONAL:
  - Scale: 2B+ registered users, 500M DAU
  - Upload: 500 hours of video uploaded EVERY MINUTE
  - Views: 1B+ video views/day
  - Read-heavy: 100:1 read/write ratio
  - Video start latency: < 2 seconds (startup time is a key UX metric)
  - Zero rebuffering: once playing, never pauses for loading
  - Availability: 99.99% for playback (upload can tolerate brief failures)
  - Eventually consistent: view counts, like counts can be slightly delayed
  - Global: 190+ countries, CDN required for < 50ms video delivery worldwide
  - Content safety: CSAM detection, copyright (ContentID) enforcement

OUT OF SCOPE:
  - YouTube Premium (paid tier), YouTube Music
  - Live streaming pipeline
  - Monetization/Ads auction system
```

---

## STEP 2 — Back-of-Envelope Estimation

```
UPLOAD:
  500 hours/minute = 30,000 minutes/minute of video uploaded
  In seconds: 30,000 × 60 = 1,800,000 seconds of raw video/minute
  At 1 MB/sec raw (uncompressed HD): 1,800,000 MB/min = 1.8 TB/min raw ingestion
  After compression (h.265 at 1080p = ~5 Mbps): ~1.8 TB/min × 0.05 = ~90 GB/min compressed
  Encoding queue depth: 500 hrs × 3 resolutions (360p, 720p, 1080p) × ~1 hour encode each
  → need thousands of encoding workers running in parallel

  Storage (per uploaded video, all profiles):
    360p:  0.3 Mbps × 3600s = 135 MB/hr
    720p:  2.5 Mbps × 3600s = 1.1 GB/hr
    1080p: 5.0 Mbps × 3600s = 2.25 GB/hr
    4K:   15.0 Mbps × 3600s = 6.75 GB/hr
    Total per 1-hr video: ~10 GB across all profiles
  
  Daily upload: 500 hrs/min × 60 min × 10 GB/hr = 300 TB/day new storage
  5-year storage: 300 TB × 365 × 5 = 547 PB (why YouTube has petabytes of storage)

READS (Views):
  1B views/day ÷ 86,400 = 11,574 views/sec avg
  Peak (3×): ~35,000 views/sec
  
  Bandwidth per stream: avg 5 Mbps (mix of mobile + HD + 4K)
  Peak concurrent viewers: assume 5M (peak 8-10 PM)
  Peak bandwidth: 5M × 5 Mbps = 25 Tbps — impossible without CDN!

METADATA:
  Per video: title(500B) + description(5KB) + tags + channel_id + timestamps = ~10KB
  500M videos: 500M × 10KB = 5 TB (metadata DB, fits in sharded PostgreSQL)

SEARCH INDEX:
  500M videos × avg 500 tokens/video = 250B index entries
  Each entry: term(20B) + doc_id(8B) + position(4B) = 32B
  Index size: 250B × 32B = 8 TB (Elasticsearch cluster)

COMMENTS:
  500M DAU × 0.5 comments/day = 250M comments/day
  250M ÷ 86,400 = 2,894 writes/sec (manageable)

CACHE (Redis):
  Cache top 20% of videos (covers 80% of views — Pareto):
  500M × 0.2 = 100M videos
  Per video cached metadata: 2KB avg
  100M × 2KB = 200 GB — needs Redis Cluster (6+ nodes)
```

---

## STEP 3 — High-Level Architecture

```
UPLOAD FLOW:
  ┌──────────┐ POST /upload/init    ┌──────────────────┐
  │ Creator  │──────────────────►  │  Upload Service   │
  │  Client  │◄── {upload_id,       │  (allocates ID,   │
  └──────────┘     presigned URL}   │   presigned URL)  │
       │                            └──────────────────┘
       │ PUT raw video (direct to GCS/S3)
       ▼
  ┌──────────────────────────────────┐
  │  Object Store (Google Cloud      │
  │  Storage / S3) — raw-uploads     │
  └───────────────┬──────────────────┘
                  │ trigger
                  ▼
  ┌──────────────────────────────────┐
  │  Kafka: topic "video.raw.uploaded"│
  └───────────────┬──────────────────┘
         ┌────────┼────────────────────┐
         ▼        ▼                    ▼
  [Transcoding] [Metadata          [Content
   Workers]      Extractor]         Safety]
   (GPU fleet)   (title/thumb)      (CSAM scan)
         │
         ▼
  Object Store: encoded/
    {video_id}/360p/{seg_N}.ts
    {video_id}/720p/{seg_N}.ts
    {video_id}/1080p/{seg_N}.ts
    {video_id}/4k/{seg_N}.ts
    {video_id}/master.m3u8       ← HLS master manifest
         │
         ▼
  [CDN Propagation: push to 200+ PoPs]
         │
         ▼
  [Metadata DB: status = "ready", set CDN URLs]
         │
         ▼
  [Notification Service: notify subscribers via Kafka]


VIEW FLOW:
  ┌──────────┐  GET /watch?v={video_id}  ┌───────────────────────┐
  │  Client  │─────────────────────────► │  Video Service        │
  └──────────┘                           │  1. Auth check        │
                                         │  2. Geo check (region │
                                         │     restrictions)     │
                                         │  3. Return manifest   │
                                         │     URL + CDN token   │
                                         └───────────┬───────────┘
                                                     │
                                         ┌───────────▼───────────┐
                                         │  CDN PoP (nearest)    │
                                         │  Serve HLS segments   │
                                         └───────────────────────┘


FULL ARCHITECTURE DIAGRAM:

  ┌────────────────────────────────────────────────────────────────────────────┐
  │                       CLIENTS (Web / Mobile / TV)                          │
  └─────────────────────────────────┬──────────────────────────────────────────┘
                                    │
  ┌─────────────────────────────────▼──────────────────────────────────────────┐
  │                    API GATEWAY (Cloud Endpoints / Envoy)                    │
  │         Auth, Rate Limiting, SSL termination, Request routing               │
  └──────┬───────────────┬────────────────┬────────────────┬────────────────────┘
         │               │                │                │
  ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
  │  Upload     │ │  Video      │ │  Search     │ │  User /     │
  │  Service    │ │  Service    │ │  Service    │ │  Feed Svc   │
  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
         │               │                │                │
  ┌──────▼────────────────▼────────────────▼────────────────▼──────┐
  │                         Kafka (Event Bus)                        │
  │  Topics: video.uploaded | video.ready | view.event | like.event │
  └──────┬─────────────────────────────────────────┬────────────────┘
         │                                         │
  ┌──────▼──────┐                         ┌────────▼──────────┐
  │ Transcoding │                         │  Analytics        │
  │  Workers    │                         │  (ClickHouse/BQ)  │
  │  (GPU pool) │                         └───────────────────┘
  └──────┬──────┘
         │
  ┌──────▼──────────────────────────────────────────────────────────┐
  │                    STORAGE LAYER                                  │
  │  GCS/S3 (video segments) │ PostgreSQL (metadata, sharded)        │
  │  Redis Cluster (cache)   │ Elasticsearch (search)                │
  │  Bigtable (watch history) │ Spanner (user accounts, subs)        │
  └─────────────────────────────────────────────────────────────────┘
         │
  ┌──────▼───────────────────────────────────────────────────────────┐
  │                      CDN (200+ global PoPs)                       │
  │  YouTube uses Google's own CDN (Google Global Cache / GGC)        │
  │  Co-located inside ISPs (like Netflix Open Connect)               │
  └──────────────────────────────────────────────────────────────────┘
```

---

## STEP 4 — Deep-Dive: Video Upload Pipeline

```
WHY DIRECT OBJECT STORE UPLOAD (not through app server):
  500 hrs/min × avg 1 GB/video = enormous bandwidth.
  Routing through app servers = bandwidth bottleneck.
  Solution: Pre-signed URL → client uploads DIRECTLY to GCS/S3.
  App server only handles small JSON. Zero video bandwidth through backend.

RESUMABLE UPLOADS (critical for large files):
  10 GB upload over mobile. Connection drops at 8 GB. User has to restart? NO.
  
  Solution: GCS/S3 Resumable Upload protocol.
  
  Step 1: POST /upload/init
    Server: create upload session
    Return: {upload_id, session_uri: "https://gcs.googleapis.com/upload/..."}
  
  Step 2: Client chunks file into 5 MB chunks. Upload sequentially.
    PUT {session_uri}
    Content-Range: bytes 0-5242879/10737418240
    → GCS returns "308 Resume Incomplete"
  
  Step 3: Resume after failure:
    PUT {session_uri}
    Content-Range: bytes */10737418240   (query what was received)
    → GCS returns: "last byte received = 8388607"
    → Client resumes from byte 8388608
  
  Result: reliably upload huge files on unreliable mobile networks.

DUPLICATE DETECTION (before encoding):
  Two creators upload same copyrighted movie.
  Solution: compute fingerprint (perceptual hash) on raw upload.
  If fingerprint matches known video → reject/flag before transcoding (saves compute).
  
  Perceptual hash: compute DCT of 8×8 frame grid → normalize → binary hash.
  Two similar frames: Hamming distance < 10 → "same video".
  YouTube's ContentID system uses this + audio fingerprinting.

TRANSCODING PIPELINE (critical path):
  Raw video → 10+ encoded profiles → HLS segments → S3 → CDN
  
  Parallelization: don't encode one profile at a time.
  Split video into 1-minute chunks → encode all chunks in parallel.
  
  For a 2-hour movie:
    120 chunks × 4 profiles = 480 parallel encoding jobs
    Each job: 1 GPU worker × ~30 seconds = 15 min total (vs 4 hours sequential)
  
  ENCODING PROFILES:
    Profile    │ Bitrate  │ Codec  │ Segment size
    ───────────┼──────────┼────────┼─────────────
    144p       │ 0.1 Mbps │ H.264  │ 75 KB/segment
    360p       │ 0.5 Mbps │ H.264  │ 375 KB
    480p       │ 1.0 Mbps │ H.264  │ 750 KB
    720p30     │ 2.5 Mbps │ H.265  │ 1.9 MB
    720p60     │ 4.0 Mbps │ H.265  │ 3.0 MB
    1080p30    │ 5.0 Mbps │ H.265  │ 3.75 MB
    1080p60    │ 8.0 Mbps │ H.265  │ 6.0 MB
    1440p      │ 12 Mbps  │ VP9    │ 9.0 MB
    4K SDR     │ 20 Mbps  │ VP9    │ 15 MB
    4K HDR     │ 25 Mbps  │ VP9    │ 18.75 MB
  
  Segment duration: 2 seconds (YouTube uses 2s; Netflix uses 10s).
  Shorter segments = faster quality switching response for ABR.
  
  HLS output structure:
    /videos/{video_id}/master.m3u8            ← master manifest
    /videos/{video_id}/1080p/playlist.m3u8    ← profile manifest
    /videos/{video_id}/1080p/seg_000001.ts    ← 2s segment
    /videos/{video_id}/1080p/seg_000002.ts
    ...
  
  FAULT TOLERANCE in encoding:
    Each segment job idempotent (retryable).
    Kafka consumer: only commit offset after ALL segments for that chunk succeed.
    Failed chunk: another worker picks it up from Kafka.
    Exactly-once: segment stored with content hash → duplicate write = no-op.

THUMBNAIL GENERATION:
  Extract frame at t=5s, t=30s, t=60s → 3 candidate thumbnails.
  ML model scores thumbnails: faces, brightness, composition.
  Highest-scored thumbnail = auto-selected.
  Creator can also upload custom thumbnail.
  
  YouTube's A/B testing: different thumbnails shown to different users.
  Highest CTR thumbnail auto-selected (called "YT Auto-generated thumbnail testing").
```

---

## STEP 5 — Deep-Dive: Video Delivery and CDN

```
THE BANDWIDTH PROBLEM:
  5M concurrent viewers × 5 Mbps = 25 Tbps at peak.
  This is the entire world's internet capacity from one datacenter? Impossible.
  Solution: YouTube uses Google Global Cache (GGC) — ISP-embedded CDN nodes.
  Same concept as Netflix Open Connect.

GOOGLE GLOBAL CACHE (GGC):
  Google deploys custom servers INSIDE ISP networks.
  ISP gets free hardware + reduced transit bandwidth costs.
  YouTube gets sub-10ms video delivery to 90%+ of global users.
  
  Deployment: 200+ ISPs globally × avg 5 GGC nodes each = 1000+ nodes.
  Each node: 200 TB SSD + 100 Gbps NIC.
  Total CDN cache capacity: 200 PB (covers entire YouTube catalog multiple times).

CDN CACHING STRATEGY:
  Popular videos (top 1%): proactively pushed to ALL GGC nodes worldwide.
  Regional popular videos: pushed to GGC nodes in that region.
  Long-tail videos: pulled from origin on first request → cached locally.
  
  Cache key: {video_id}/{profile}/{segment_number}
  Cache TTL: effectively infinite (video segments never change once encoded).
  Content-addressed storage: URL = hash of content → automatic deduplication.
  
  Cache hit rate: > 99% for popular videos (same segment served millions of times).
  Origin hit rate: < 1% of requests reach YouTube's origin servers.

ADAPTIVE BITRATE STREAMING (ABR):
  Player has 30-second buffer. Starts at lowest quality → upgrades as it goes.
  
  def select_next_segment_quality(bandwidth_mbps, buffer_seconds):
      # Safety: if buffer < 5s, be conservative
      safety_factor = 0.6 if buffer_seconds < 5 else 0.9
      available = bandwidth_mbps * safety_factor
      
      # Choose highest quality fitting in available bandwidth
      profiles = [4K_HDR, 4K, 1440p, 1080p60, 1080p30, 720p60, 720p30,
                  480p, 360p, 240p, 144p]
      for p in profiles:
          if p.bitrate <= available:
              return p
      return lowest_quality  # emergency fallback
  
  Quality switch: seamless at 2-second segment boundary.
  User experience: quality changes are invisible during normal playback.
  
  BOLA (Buffer-Based ABR Algorithm - what YouTube uses):
    Not just bandwidth-based. Buffer-based too.
    Full buffer → increase quality aggressively.
    Low buffer → reduce quality immediately (avoid rebuffering at all cost).
    Rebuffering penalty: worse UX than lower quality.

PROGRESSIVE DOWNLOAD vs HLS:
  Old YouTube (pre-2010): progressive download (MP4). Seekable but wastes bandwidth.
  Modern YouTube: DASH (Dynamic Adaptive Streaming over HTTP) — similar to HLS.
  YouTube actually uses MPEG-DASH + VP9/AV1 for web; HLS for Apple devices.
  
  Key difference from progressive download:
    You jump to t=10:00 in a 2-hr video → only downloads segment from t=10:00.
    No wasted bandwidth for segments you won't watch.
```

---

## STEP 6 — Deep-Dive: Video Metadata and Search

```
DATABASE CHOICE:
  Metadata (title, description, channel): PostgreSQL (sharded by video_id).
  Watch history: Bigtable (wide-column, massive write throughput, TTL support).
  Subscriptions: Cloud Spanner (globally consistent, shard-free).
  Comments: Cassandra (time-series, partition by video_id).
  Like/dislike counts: Redis + async flush to PostgreSQL.

METADATA SCHEMA (PostgreSQL — sharded by hash(video_id) % 256):

  CREATE TABLE videos (
      video_id        CHAR(11) PRIMARY KEY,     -- YouTube's 11-char base64 ID
      channel_id      UUID NOT NULL,
      title           VARCHAR(100) NOT NULL,
      description     TEXT,
      tags            TEXT[],
      duration_sec    INT NOT NULL,
      status          TEXT DEFAULT 'processing', -- processing, ready, deleted
      visibility      TEXT DEFAULT 'public',     -- public, unlisted, private
      category_id     SMALLINT,
      language        CHAR(5),                   -- 'en-US', 'hi-IN'
      default_thumb   TEXT,                      -- CDN URL of default thumbnail
      uploaded_at     TIMESTAMP DEFAULT NOW(),
      published_at    TIMESTAMP,                  -- null if still processing
      view_count      BIGINT DEFAULT 0,           -- synced from Redis periodically
      like_count      BIGINT DEFAULT 0,
      dislike_count   BIGINT DEFAULT 0,           -- hidden from public but tracked
      comment_count   BIGINT DEFAULT 0
  );
  
  CREATE INDEX idx_video_channel ON videos(channel_id, published_at DESC);
  CREATE INDEX idx_video_status ON videos(status) WHERE status != 'deleted';

VIDEO_ID GENERATION:
  YouTube uses 11-character base64 IDs (e.g., "dQw4w9WgXcQ").
  62^11 ≈ 52 trillion unique IDs. At 500 hrs/min: runs for millions of years.
  Generated: UUID → take first 11 chars base64-encoded → collision check → done.

SEARCH PIPELINE:
  Elasticsearch cluster (Google uses its own indexing infra, but ES for this discussion).
  
  On video upload (async, via Kafka):
    Search Indexer consumes "video.ready" event.
    Extracts: title, description, tags, auto-generated transcript.
    Indexes document to Elasticsearch.
  
  Index document:
  {
    "video_id": "dQw4w9WgXcQ",
    "title": "Rick Astley - Never Gonna Give You Up",
    "description": "Official music video...",
    "tags": ["rick astley", "80s", "pop", "music video"],
    "transcript": "We're no strangers to love...",  ← auto-generated by Whisper/ASR
    "channel_name": "Rick Astley",
    "view_count": 1500000000,
    "like_count": 15000000,
    "published_at": "2009-10-25T06:57:33Z",
    "duration_sec": 213,
    "category": "Music"
  }
  
  SEARCH QUERY:
  GET /search?q=rick+astley
  → Elasticsearch multi-field search:
  {
    "query": {
      "function_score": {
        "query": {
          "multi_match": {
            "query": "rick astley",
            "fields": ["title^4", "tags^3", "channel_name^2", "description^1", "transcript^0.5"],
            "type": "best_fields"
          }
        },
        "functions": [
          {"field_value_factor": {"field": "view_count", "modifier": "log2", "factor": 0.5}},
          {"gauss": {"published_at": {"scale": "90d", "decay": 0.5}}}  // recency boost
        ]
      }
    }
  }
  
  WHY LOG(view_count) INSTEAD OF view_count?
    Raw view count = viral videos dominate everything.
    Log scale: gap between 10M and 100M views << gap between 100 and 1000 views.
    More balanced with content relevance.

VIEW COUNT — EVENTUAL CONSISTENCY:
  Problem: 11,574 views/sec. Updating PostgreSQL directly = 11,574 writes/sec.
  Single table row updates at this rate → massive lock contention.
  
  Solution: Redis counter → async DB sync.
  
  def record_view(video_id: str, user_id: str):
      # 1. Dedup: has this user viewed this video in last 5 minutes?
      view_key = f"viewed:{user_id}:{video_id}"
      if redis.get(view_key):
          return  # don't count duplicate views
      redis.setex(view_key, 300, 1)  # TTL 5 min
      
      # 2. Increment counter
      redis.incr(f"views:{video_id}")
      
      # 3. Publish event to Kafka for analytics
      kafka.publish("view.events", {
          "video_id": video_id,
          "user_id": user_id,
          "timestamp": now(),
          "device": device_type,
          "country": get_country(ip)
      })
  
  Background job every 60 seconds:
    videos = redis.keys("views:*")
    for video_id in videos:
        count = int(redis.getdel(f"views:{video_id}"))
        db.execute("UPDATE videos SET view_count = view_count + ? WHERE video_id = ?",
                   count, video_id)
  
  Analytics pipeline: Kafka → ClickHouse (columnar DB, fast GROUP BY).
  Creator dashboard: "views by country, device, traffic source" — all from ClickHouse.
```

---

## STEP 7 — Deep-Dive: Recommendations

```
THE SCALE:
  2B users × 500M videos = 10^17 possible user-video pairs.
  Can't compute scores for all pairs. Need two-stage approach.

STAGE 1: CANDIDATE GENERATION (narrow from 500M to 500)
  Goal: given user, find ~500 potentially relevant videos quickly.
  
  Approach A: Collaborative Filtering (Matrix Factorization)
    User matrix: [user_id → 128-dim embedding vector]
    Video matrix: [video_id → 128-dim embedding vector]
    User likes video ↔ dot product of embeddings is high.
    
    Training: implicit feedback (watch, like, comment, share).
    Offline batch: train weekly on Spark (terabytes of watch history).
    
    At inference: user embedding → ANN search (FAISS) → top-500 by embedding similarity.
    FAISS (Facebook AI Similarity Search): approximate nearest neighbor.
    500M videos in 128-dim space → FAISS indexes in ~25 GB RAM → query < 10ms.
  
  Approach B: Content-Based Filtering
    User watched "Python tutorial" → find videos similar to "Python tutorial".
    Similarity: video embedding similarity (same method).
    Use last 10 watched videos → find similar videos → deduplicate → add to candidates.
  
  Approach C: Trending + Fresh Content
    Add trending videos (last 24h) to candidates.
    New videos need exposure even before collaborative signal builds up.
    "Cold start": a new video can't appear in recommendations until it has views.
    Fix: randomly inject new videos into a % of users → gather signal → improve ranking.

STAGE 2: RANKING (narrow from 500 to 20)
  Deep learning ranking model (DNN).
  Input features:
    User features:
      - Watch history embeddings (last 100 videos)
      - Search history (last 20 queries)
      - Device type (mobile → shorter videos preferred)
      - Time of day (morning → news/podcasts; evening → entertainment)
      - Country/language
    
    Video features:
      - Days since published
      - Views/hour growth rate (velocity)
      - Like ratio (likes / (likes + dislikes))
      - Average watch percentage (watch time / duration)
      - Click-through rate (impressions → clicks)
      - Comment rate (comments / views)
    
    User-Video features (interaction):
      - User embedding × video embedding (dot product)
      - Same channel as recently watched?
      - Same topic as recent searches?
  
  Output: score per video → rank → top 20 for homepage.
  
  Training: minimize "not-satisfied" watching (user closes after 10 seconds = negative signal).
  Optimize for: "watch time" (YouTube's North Star metric, not clicks).

HOMEPAGE ASSEMBLY:
  "Continue Watching" row: always first. Shows in-progress videos.
  "Recommended" row: personalized ML output.
  "Trending" row: global + regional.
  "Because you watched X" rows: content-based similarity.
  
  Final output is cached per user in Redis: "homepage:{user_id}" → JSON of video IDs.
  TTL: 1 hour. Refreshed on next open after TTL expires.

COLD START PROBLEM:
  New user: no watch history → can't personalize.
  Solutions:
    1. Demographics: country → show regional popular content.
    2. Onboarding: ask "what topics interest you?" → 5 choices → seed recommendations.
    3. Trending: globally popular videos (safe choice for any user).
    4. Session-based: first 3 clicks → immediately update recommendations.
```

---

## STEP 8 — Deep-Dive: Fan-out Notifications for Subscribers

```
PROBLEM:
  MrBeast uploads a video. He has 350M subscribers.
  350M notifications must be sent within minutes.
  Push model: iterate 350M rows → send push → 350M × 1 DB read = millions of DB ops.
  
  At 100K notifications/sec → 350M ÷ 100K = 3,500 seconds = ~1 hour delay. Unacceptable.

HYBRID PUSH/PULL STRATEGY:
  
  Fan-out on WRITE for small channels (< 100K subscribers):
    When creator uploads:
    → Kafka event → Fan-out Worker reads subscriber list.
    → Insert notification record per subscriber.
    → Push to FCM/APNs.
    100K subscribers × 1 DB write = manageable.
  
  Fan-out on READ for large channels (> 100K subscribers — MrBeast, T-Series):
    When creator uploads:
    → Store ONE notification record in creator's notification table.
    → Do NOT iterate subscribers.
    When subscriber opens YouTube:
    → Check: "do any creators I subscribe to have new videos since last open?"
    → Query: SELECT * FROM creator_uploads WHERE channel_id IN (my subscriptions) AND timestamp > last_seen
    → Return new videos as "bell notifications."
    
    This converts 350M writes → 0 writes on upload.
    Cost: O(creator_count) query per user open instead (fast — user follows ~50 creators max).

NOTIFICATION DEDUPLICATION:
  User opens YouTube 5 times in an hour. 5 notification queries, same new video.
  Fix: "last_notification_seen_at" per user per channel.
  Only show notification if new video uploaded after last_notification_seen_at.
  Stored in Redis: "notif_seen:{user_id}:{channel_id}" → timestamp.

PUSH DELIVERY:
  FCM (Android, Web): handles delivery, retry, offline queuing.
  APNs (iOS): Apple's push system.
  Notification payload: {video_id, title, channel_name, thumbnail_url}
  Throttling: YouTube doesn't push every upload if user has 500 subscriptions.
    → Filter: user hasn't opened YouTube in 24h → batch into one "X new videos" notification.
```

---

## STEP 9 — Bottlenecks and Solutions

```
BOTTLENECK 1: Transcoding queue during viral events
  500 hrs/min upload → but during news events (election, sports) → spike to 1000 hrs/min.
  Transcoding workers: auto-scale (Kubernetes + node pools on preemptible GCE instances).
  Priority queue in Kafka: paid channels / verified creators get priority encoding.
  SLA: video visible within 30 minutes (not real-time, so some delay acceptable).

BOTTLENECK 2: View count DB contention
  11,574 views/sec to same popular video → row-level lock contention.
  Fix: Redis counter + async flush (as described above).
  Further fix: shard view counter. "views:{video_id}:shard:{0..15}" → 16 shards.
  Read: SUM all 16 shards. Write: increment random shard. No contention.

BOTTLENECK 3: Comment section at viral scale
  A viral video: 100K concurrent users all loading comments simultaneously.
  Comments DB: Cassandra (partition by video_id).
  Top-level comments page 1: high traffic → cache in Redis.
  Key: "comments:{video_id}:page:1" → JSON. TTL: 30 seconds.
  New comments: invalidate cache. Next request: repopulate.

BOTTLENECK 4: Search during trending topics
  "Drake Kendrick" trending → millions search this simultaneously.
  Same Elasticsearch query hits → can cache query results.
  Redis: "search_cache:{hash(query)}" → JSON results. TTL: 60 seconds.
  Trade-off: results can be 60s stale → acceptable for non-breaking-news queries.

BOTTLENECK 5: Recommendation serving latency
  Serving personalized recommendations for 500M DAU.
  Real-time DNN inference for every homepage open → expensive.
  Fix: pre-compute recommendations hourly. Store in Redis.
  Key: "rec:{user_id}" → [video_id_1, ..., video_id_50]. TTL: 1 hour.
  On TTL expiry: background job re-computes.
  First open after TTL: slightly stale (last computed 1hr ago). Acceptable.
```

---

## STEP 10 — Database Summary

```
Service               │ Database           │ Why
──────────────────────┼────────────────────┼─────────────────────────────────────────
Video metadata        │ PostgreSQL (sharded│ ACID, complex queries, relational
                       │ by video_id)       │
Watch history         │ Bigtable           │ High write throughput, TTL, wide-column
Comments              │ Cassandra          │ Write-heavy, partition by video_id
Subscriptions         │ Cloud Spanner      │ Globally consistent, no sharding pain
View/like counts      │ Redis → PostgreSQL │ Atomic incr, async flush (avoid write storm)
Recommendations       │ Redis (cache)      │ Pre-computed, fast read
                      │ + offline Spark    │ ML training
Search index          │ Elasticsearch      │ Full-text, relevance ranking, fast
Upload state          │ Redis              │ Ephemeral, fast lookup during upload
Analytics             │ ClickHouse/BigQuery│ Columnar, fast GROUP BY, petabytes
Content store         │ GCS / S3           │ Cheap, infinite, geo-replicated
Sessions              │ Redis              │ Fast auth token lookup
```

---

## STEP 11 — Trade-offs

```
TRADE-OFF 1: HLS segments (2s) vs longer segments (10s Netflix)
  2s segments: faster quality switch response (ABR reacts in 2s).
  2s segments: 5× more HTTP requests per minute. More CDN load.
  10s segments: fewer requests, larger cache granularity.
  Decision: 2s for YouTube (interactive seeking), 10s for Netflix (lean-back viewing).

TRADE-OFF 2: View count eventual consistency vs strong consistency
  Strong consistency: every view → DB write → accurate count.
  Eventual: Redis counter → batch flush → count lags by 60s.
  Decision: users don't notice ±60s lag on view count. Eventual consistency saves 11,574 DB writes/sec.

TRADE-OFF 3: Batch recommendations vs real-time
  Real-time: DNN inference on every homepage open → < 50ms, expensive GPU fleet.
  Batch: pre-compute hourly → stale by up to 1 hour.
  Decision: Batch + session-based real-time adjustments (last 3 clicks update candidates).

TRADE-OFF 4: CDN push vs pull
  Push (proactive): YouTube fills CDN overnight with top 1% videos.
  Pull (lazy): CDN fetches from origin on first cache miss.
  Decision: Hybrid. Push for top 1% (covers 80% of views). Pull for long tail.
  Proactive push waste rate: < 5% (very accurate demand prediction).

TRADE-OFF 5: Video search latency vs freshness
  Elasticsearch indexing lag: ~30 seconds for new uploads.
  Alternative: synchronous index on upload → slower upload acknowledgment.
  Decision: 30s lag is fine. New video uploaded → not expected to appear instantly in search.
```

---

## STEP 12 — Follow-Up Questions

```
Q: "How would you implement YouTube Live?"
A: Very different pipeline:
   Creator → OBS → RTMP ingest → Live Transcoding (real-time, not batch).
   Low Latency HLS (LL-HLS): 2s segments reduced to 200ms partial segments.
   DVR: buffer last 4 hours → "rewind live" feature.
   Chat: separate WebSocket service (Redis Pub/Sub for message fan-out).
   No pre-encoding, no CDN fill — live segments streamed as generated.

Q: "How do you implement ContentID (copyright detection)?"
A: Audio fingerprinting: extract spectral features every 3 seconds → binary hash.
   Video fingerprinting: perceptual hash of key frames.
   New upload → compute fingerprint → compare against ContentID database (1B+ fingerprints).
   Match found → policy applied: block, monetize for rights holder, track, or allow.
   Fingerprint matching: approximate nearest neighbor at scale (like FAISS for video).

Q: "How would you handle chapters (timestamps in video)?"
A: Chapters are metadata: [{"title": "Intro", "start": 0}, {"title": "Part 2", "start": 120}]
   Stored in videos metadata table.
   CDN: can now pre-fetch segments near chapter marks (predicted seek points).
   Player: shows chapter markers in progress bar.

Q: "How do you implement Speed Control (0.5× to 2× playback)?"
A: All done client-side. Player decodes and plays frames at different rates.
   ABR still works (same segments, different playback rate).
   Pitch correction: apply PSOLA algorithm to preserve audio pitch at 2× speed.

Q: "How do you handle geographic content restrictions?"
A: Country restrictions: stored in video metadata (restricted_countries: ["DE", "FR"]).
   Video Service checks user's country (from IP → GeoIP lookup → country code).
   If country in restricted list → return 403 Forbidden.
   CDN: country-aware token signed with country claim.
   CDN edge node verifies token before serving segment.
```


---

## DEEP-DIVE IMPROVEMENT: ABR Algorithm — Mathematical Deep Dive

```
THE FUNDAMENTAL TRADEOFF:
  High quality: fewer artifacts, better experience. But: needs more bandwidth.
  Low quality: less bandwidth. But: pixelated, bad UX.
  Rebuffering: worst of all outcomes. User's video stops. Engagement drops 20-30%.
  
  ABR goal: maximize quality subject to "never rebuffer."
  This is an optimization problem with a hard constraint.

BUFFER MODEL:
  The video player maintains a buffer (pre-downloaded future segments).
  Buffer = number of seconds of video downloaded ahead of current playback position.
  
  State:
    B(t) = buffer size at time t (seconds)
    Q(t) = quality level selected at time t (bitrate in Mbps)
    C(t) = estimated network bandwidth at time t (Mbps)
  
  Buffer dynamics:
    B(t+1) = B(t) + segment_duration - download_time
    download_time = segment_size / C(t)
               = Q(t) × segment_duration / C(t)
    
    If C(t) > Q(t): buffer grows (download faster than playback). ✓
    If C(t) < Q(t): buffer drains. Eventually → rebuffer. ✗

THROUGHPUT-BASED ABR (simplest):
  Estimate bandwidth: C(t) = average download speed of last 3 segments.
  Select quality: highest Q such that Q ≤ C(t) × safety_factor (0.85).
  
  def select_quality_throughput(bandwidth_estimate_mbps, safety=0.85):
      available = bandwidth_estimate_mbps * safety
      profiles = [15, 8, 5, 2.5, 1.0, 0.5, 0.1]  # 4K → 144p in Mbps
      return next((p for p in profiles if p <= available), profiles[-1])
  
  Problem: bandwidth estimation is noisy.
    Segment 1: 10 Mbps → select 8 Mbps quality.
    Segment 2: suddenly drops to 3 Mbps → must switch DOWN.
    Quality switch: visible as resolution change. Bad UX.
    Frequent switches: oscillation. Even worse UX.
  
  Improvement: EWMA (Exponentially Weighted Moving Average):
    C(t) = alpha × C_measured(t) + (1-alpha) × C(t-1)
    alpha = 0.3 (recent measurements weighted, but smoothed by history)
    Less responsive to single segment spikes. More stable quality selection.

BOLA (Buffer-Occupancy based Lyapunov Algorithm) — YouTube's approach:
  Don't just look at throughput. Look at BUFFER LEVEL.
  
  INTUITION:
    If buffer is full (30s): we're comfortably ahead. Select HIGH quality.
    If buffer is low (5s): we're in danger. Select LOW quality immediately.
    Buffer level is a more reliable indicator than throughput estimation.
  
  BOLA utility function:
    For each quality level q, BOLA computes a "utility":
    V(q, B) = log(bitrate_q) + gamma × B / segment_duration
    
    Where:
      log(bitrate_q): logarithm of quality bitrate (diminishing returns for quality increase)
      B: current buffer level in seconds
      gamma: tuning parameter (how much buffer matters vs quality)
      segment_duration: 2 seconds for YouTube
    
    Decision: select quality q* = argmax V(q, B)
    High buffer → V(q_high) > V(q_low) → select high quality.
    Low buffer → V(q_low) > V(q_high) → select low quality.
  
  BOLA guarantees (mathematically proven):
    1. Stall probability bounded (rebuffering is minimized, not just avoided by luck).
    2. Time-average video quality is maximized given bandwidth constraint.
    3. Provably optimal under the Lyapunov stability framework.
    
    These aren't just empirically good — they're MATHEMATICALLY PROVEN optimal.
    YouTube published the BOLA paper in IEEE INFOCOM 2016. Available publicly.

PRACTICAL BOLA IMPLEMENTATION IN YOUTUBE PLAYER:

  class BOLAController:
      GAMMA = 5.0        # Buffer sensitivity coefficient (tuned empirically)
      SEGMENT_DUR = 2.0  # 2-second segments
      MIN_BUFFER = 10.0  # Never let buffer drop below 10s (safety margin)
      
      def __init__(self):
          self.buffer_seconds = 0.0
          self.profiles = [0.1, 0.5, 1.0, 2.5, 5.0, 8.0, 15.0]  # Mbps
      
      def select_quality(self) -> float:
          """Select quality using BOLA utility function."""
          best_q = self.profiles[0]  # start with lowest
          best_utility = float('-inf')
          
          for q in self.profiles:
              # Utility = log quality + buffer bonus, minus "cost" of downloading
              # (how long it takes to download this segment at estimated bandwidth)
              utility = math.log(q) + self.GAMMA * self.buffer_seconds / self.SEGMENT_DUR
              
              if utility > best_utility:
                  # Can we download this quality without draining buffer below MIN_BUFFER?
                  estimated_download_time = (q * self.SEGMENT_DUR) / self._estimate_bandwidth()
                  projected_buffer = self.buffer_seconds + self.SEGMENT_DUR - estimated_download_time
                  
                  if projected_buffer >= self.MIN_BUFFER:  # safety constraint
                      best_utility = utility
                      best_q = q
          
          return best_q
      
      def _estimate_bandwidth(self) -> float:
          """EWMA of recent download throughput."""
          # ... implementation using download history
          pass
      
      def update_buffer(self, segment_download_time: float, segment_duration: float):
          """Update buffer model after each segment download."""
          self.buffer_seconds = max(0, 
              self.buffer_seconds + segment_duration - segment_download_time)

SEEK OPERATION AND ABR INTERACTION:
  User jumps to t=45:00 in a 1-hour video.
  
  Problem: buffer is empty at new position. Must start fresh.
  ABR response: immediately drop to lowest quality (empty buffer = danger).
  Behavior: "you see low-res for 2-3 seconds after seeking, then quality improves."
  This is intentional BOLA behavior. Safety first (no rebuffer), quality second.
  
  YouTube optimization: pre-fetch segments near chapter markers.
  When video has chapters at t=10:00, t=20:00, t=45:00:
    Player: proactively downloads 5s of video at each chapter start.
    "Hot segments": if user seeks to chapter marker, pre-fetched segments available.
    Seek experience at chapters: instant quality, no low-res fallback.
```

---

## DEEP-DIVE IMPROVEMENT: Content ID and Copyright Detection

```
THE PROBLEM AT SCALE:
  500 hours of video uploaded per minute.
  Some portion contains copyrighted music, movies, sports clips.
  YouTube must: detect copyright, apply rights holder's policy (block/monetize/track).
  
  Manual review: impossible at 500 hours/minute. Must be automated.
  ContentID: YouTube's system that does this automatically in seconds.

AUDIO FINGERPRINTING — HOW IT WORKS:

  Step 1: Reference fingerprint generation (done once per copyrighted work):
    Rights holder submits master track to ContentID.
    Audio processing pipeline:
      → Decode audio to raw PCM (pulse-code modulation) samples.
      → Divide into 30ms overlapping windows.
      → Apply FFT (Fast Fourier Transform) to each window.
        FFT: converts time-domain signal → frequency-domain.
        Result: spectrum of frequencies in that 30ms window.
      → Extract dominant frequencies (top 5) per window.
      → Compute difference between consecutive windows' dominant frequencies.
      → Binary hash of differences → 32-bit fingerprint per 30ms window.
    
    Result: a time-series of 32-bit fingerprints, one every 30ms.
    For a 3-minute song: 3×60/0.03 = 6,000 fingerprint values.
    These fingerprints are content-addressed: the same song produces the same fingerprints.
    Even compressed, re-sampled, or pitch-shifted versions produce SIMILAR fingerprints.
  
  Step 2: Query fingerprinting (for every uploaded video):
    Extract audio from uploaded video.
    Compute same fingerprint sequence.
    
    Comparison challenge:
      Reference: 6,000 fingerprints (3-min song).
      Video: might be 60,000 fingerprints (30-min video).
      Song may appear at any position in video. Must search all offsets.
      Naive: O(N × M) = O(60000 × 6000) = 360M comparisons per song per video. Too slow.
    
    SOLUTION: Locality Sensitive Hashing (LSH).
      Fingerprint lookup table: for each 32-bit fingerprint chunk → list of (song_id, time_offset).
      Query: for each fingerprint of uploaded video, lookup table.
      Find: multiple video fingerprints match a song at consistent time offsets.
      Consistent offset = the song appears in this video at this timestamp.
      
      Example:
        Video fp[1000] = 0xABCD matches song "Song X" at its fp[100].
        Video fp[1001] = 0x1234 matches song "Song X" at its fp[101].
        Video fp[1002] = 0x5678 matches song "Song X" at its fp[102].
        Three consecutive matches at consistent offsets → MATCH with 98% confidence.
      
      This is like aligning two sequences and finding sliding window matches.
      Implementation: prefix hashing makes lookup O(1) per fingerprint.
      Total: O(M) = O(60,000) fingerprint lookups per video. Manageable!
  
  Step 3: Video fingerprinting (for movie/TV clips):
    Similar idea but for video frames instead of audio.
    Sample 1 frame per second. Apply DCT (Discrete Cosine Transform).
    DCT coefficients → normalize → binary hash = "perceptual hash" (pHash).
    pHash is robust: even blurry, rotated, recolored videos produce similar pHashes.
    Hamming distance < 10 bits → "same video." (10 bit threshold is Shazam/YouTube standard).

POLICY APPLICATION:
  Match found: rights holder's policy applied:
    BLOCK: video removed from platform.
    MONETIZE: ads shown, revenue goes to rights holder (not uploader).
    TRACK: no monetization, but rights holder sees viewership data.
    ALLOW: rights holder explicitly allows this type of use.
  
  Policies are per-country:
    Sony Music might allow use in US but block in Germany (different licensing territory).
    ContentID checks user's country → applies per-country policy.
  
  Dispute: uploader claims "fair use":
    Uploader: click "Dispute claim."
    Rights holder: must respond within 30 days (else ContentID match expires).
    If rights holder escalates: DMCA takedown notice (legal, not just automated).
    If uploader believes it's fair use: they can submit counter-notice (triggers legal process).
    YouTube: neutral intermediary (safe harbor under DMCA if it acts on notices promptly).
```

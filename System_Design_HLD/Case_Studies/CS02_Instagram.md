# CS02: Design Instagram (Photo Sharing + Feed)
## Full HLD Case Study | MAANG Interview Ready

---

## STEP 1 — Requirements

```
FUNCTIONAL:
  1. User uploads photos with captions and hashtags
  2. User follows/unfollows other users
  3. User sees a feed of recent photos from followed accounts
  4. User can like and comment on photos
  5. User can search for users and hashtags
  6. User can view any user's profile grid (their photos)
  7. Stories: photos that expire after 24 hours

NON-FUNCTIONAL:
  - 1 billion registered users, 500M DAU
  - 100M photos uploaded/day
  - 500M stories viewed/day
  - Feed load time: < 200ms
  - Photo upload: async (show "processing" is OK for a few seconds)
  - High availability: 99.99%
  - Eventual consistency acceptable for feed (seeing a post 5s late is fine)
  - Photos must never be lost (durable storage)
  - Photos served globally with < 50ms latency (CDN required)
```

---

## STEP 2 — Scale Estimation

```
PHOTO UPLOADS:
  100M photos/day ÷ 86,400 = 1,157 uploads/sec avg
  Peak: 5,785 uploads/sec

  Storage: 100M × 300KB avg (compressed JPEG) = 30 TB/day
  Media storage over 5 years: 30 TB × 365 × 5 = 54.75 PB

  Encoding: each photo → 5 sizes: 1080p, 640p, 320p, 160p, thumbnail.
  Per photo: 5 sizes × avg 200KB = ~1MB total storage per photo.
  5 years: 100M/day × 1MB × 365 × 5 = 182.5 PB total (with encoding profiles)

FEED READS:
  500M DAU × 10 feed opens/day = 5B feed requests/day
  5B ÷ 86,400 = 57,870 feed reads/sec avg
  Peak: ~290,000 feed reads/sec

LIKES:
  500M DAU × 50 likes/day = 25B likes/day
  289,351 likes/sec avg → peak: ~1.4M likes/sec (likes are fire-and-forget)

COMMENTS:
  500M DAU × 5 comments/day = 2.5B comments/day
  28,935 comments/sec avg

STORAGE FOR METADATA (user data, posts, relationships):
  Per post: post_id(8) + user_id(8) + caption(500) + created_at(8) = ~524 bytes
  100M posts/day × 524B = 52.4 GB/day → 95 TB over 5 years

FOLLOW GRAPH:
  1B users × avg 300 following each = 300B follow relationships
  Per edge: 16 bytes (follower_id + followee_id) = 4.8 TB for follow graph
  Store in graph-optimized structure or denormalized lookup table.

CACHE:
  Home feed (pre-computed): store 1000 post IDs per user
  500M users × 1000 IDs × 8 bytes/ID = 4 TB of Redis feed data
  Redis Cluster required (4TB >> single node capacity).
```

---

## STEP 3 — High-Level Architecture

```
UPLOAD FLOW:
  ┌──────────┐   POST /photos/prepare   ┌──────────────────┐
  │ Mobile   │ ─────────────────────► │  Upload Service   │
  │ App      │ ◄─── {upload_url, photo_id}               │
  │          │                         └──────────────────┘
  │          │   PUT {upload_url}       ┌──────────────────┐
  │          │ ─────────────────────► │  AWS S3          │ (direct upload)
  │          │                         └──────────────────┘
  │          │   POST /photos/confirm   ┌──────────────────┐
  │          │ ─────────────────────► │  Upload Service   │
  └──────────┘                         │  → Kafka publish  │
                                       └──────────────────┘

KAFKA EVENT: "photo-uploaded" {photo_id, user_id, s3_key, caption, hashtags}
                     │
          ┌──────────┼─────────────────────────────┐
          │          │                             │
  [Thumbnail     [Feed Fan-out            [Search
   Worker]        Worker]                  Indexer]
   Encode 5     Push to 2M                Elasticsearch
   sizes → S3   followers' feeds          hashtag index

FEED READ FLOW:
  ┌──────────┐   GET /feed    ┌──────────────────┐   ┌─────────────────────┐
  │ Mobile   │ ─────────────► │  Feed Service    │ → │  Redis (feed cache) │
  │ App      │ ◄──────────── │  merge + hydrate  │   │  "feed:{user_id}"   │
  └──────────┘                └──────────────────┘   └─────────────────────┘
                                       │ (hydrate post metadata)
                              ┌────────▼────────┐
                              │  Cassandra       │
                              │  posts metadata  │
                              └────────┬────────┘
                                       │ (photo URLs)
                              ┌────────▼────────┐
                              │  CDN             │
                              │  (photos at edge)│
                              └─────────────────┘
```

---

## STEP 4 — Deep-Dive: Feed Generation

```
THE CELEBRITY PROBLEM:
  Lady Gaga has 140M followers. She posts.
  Fan-out on write: push to 140M Redis feeds = 140M Redis writes.
  At 1M Redis ops/sec per node: 140 seconds. Unacceptable.

INSTAGRAM'S HYBRID APPROACH:

RULE:
  Regular users (< 1M followers): fan-out on WRITE.
  Celebrities (≥ 1M followers): fan-out on READ.

FAN-OUT ON WRITE (regular users):
  def on_photo_posted(photo_id: str, author_id: str):
      followers = db.get_followers(author_id)  # might be 50,000 for regular user
      pipeline = redis.pipeline()
      for follower_id in followers:
          pipeline.lpush(f"feed:{follower_id}", photo_id)
          pipeline.ltrim(f"feed:{follower_id}", 0, 999)  # keep latest 1000 post IDs
      pipeline.execute()
      # ~50,000 operations. At 1M ops/sec: < 50ms. Acceptable!

FAN-OUT ON READ (celebrities):
  When building feed for user:
  1. Get pre-computed feed from Redis: [post_1, post_2, ..., post_20]
     (These are from regular users the reader follows — already fan-out-on-write.)
  2. Get list of celebrities this user follows (stored separately).
  3. For each celebrity: get their latest 5 posts from DB.
  4. Merge all lists by timestamp.
  5. Return top 20.

  def get_feed(user_id: str) -> list:
      # Step 1: Pre-computed feed (regular followed users)
      post_ids = redis.lrange(f"feed:{user_id}", 0, 19)  # latest 20 IDs
      
      # Step 2: Celebrity posts (fan-out on read)
      celebrity_ids = redis.smembers(f"follows:celebrities:{user_id}")  # user's celeb follows
      celebrity_posts = []
      for celeb_id in celebrity_ids:
          posts = redis.lrange(f"posts:{celeb_id}", 0, 4)  # celeb's latest 5 posts
          celebrity_posts.extend(posts)
      
      # Step 3: Merge and sort by timestamp
      all_post_ids = post_ids + celebrity_posts
      return sorted(fetch_metadata(all_post_ids), key="created_at", reverse=True)[:20]

FEED HYDRATION:
  Feed service has list of [post_id_1, post_id_2, ...].
  Must fetch: photo URL, caption, like count, comment count, author info.
  
  # Batch fetch metadata from Cassandra:
  posts = cassandra.execute(
      "SELECT * FROM posts WHERE post_id IN ?",
      (tuple(post_ids),)
  )
  
  # Batch fetch authors from cache:
  author_ids = [p["user_id"] for p in posts]
  authors = redis.mget([f"user:{uid}" for uid in author_ids])  # batch get
  
  # Merge and return:
  return [merge(post, author, cdn_url(post)) for post, author in zip(posts, authors)]

  CDN URL: f"https://cdn.instagram.com/{photo_id}_640.webp"
  (Photo URL = deterministic from photo_id → no DB needed for URL)
```

---

## STEP 5 — Deep-Dive: Photo Upload and Storage

```
WHY DIRECT S3 UPLOAD (pre-signed URL):
  100M photos/day = 1,157 uploads/sec × avg 3 MB = 3.5 GB/sec of photo bytes.
  If routed through Instagram's API servers → 3.5 GB/sec through app tier.
  App servers need massive bandwidth. Very expensive.
  
  Fix: Direct S3 upload. API server handles only JSON (small).
  
  FLOW:
    Step 1: Mobile → POST /photos/prepare
            Server: allocate photo_id, generate S3 pre-signed URL.
            Server responds: {photo_id: "ph_123", upload_url: "https://s3.amazonaws.com/...?sig=..."}
    
    Step 2: Mobile → PUT {upload_url} with photo bytes
            Direct to S3. Instagram API servers not involved. Zero bandwidth used by Instagram servers.
    
    Step 3: Mobile → POST /photos/confirm {photo_id: "ph_123", caption: "..."}
            Server: creates metadata record. Publishes Kafka event.
    
    # S3 pre-signed URL generation (Python):
    import boto3
    s3 = boto3.client('s3')
    
    upload_url = s3.generate_presigned_url(
        'put_object',
        Params={
            'Bucket': 'instagram-photos-raw',
            'Key': f'raw/{photo_id}.jpg',
            'ContentType': 'image/jpeg',
            'ContentLength': 10_000_000,  # max 10MB
        },
        ExpiresIn=3600  # URL valid for 1 hour
    )

ENCODING PIPELINE:
  Kafka event triggers Thumbnail Worker:
  
  def process_photo(photo_id: str, s3_key: str):
      # Download original from S3
      raw = s3.get_object("instagram-photos-raw", s3_key)
      img = PIL.Image.open(raw)
      
      profiles = [
          ("1080", 1080), ("640", 640), ("320", 320),
          ("160", 160), ("thumb", 150)
      ]
      for name, size in profiles:
          resized = img.resize((size, size), PIL.Image.LANCZOS)
          webp_bytes = resized.save(format='WEBP', quality=85)
          s3.put_object(
              "instagram-photos-cdn",
              f"{photo_id}_{name}.webp",
              webp_bytes,
              ContentType='image/webp',
              CacheControl='max-age=31536000'  # 1 year — photos never change
          )
      
      # Mark as ready in DB
      db.execute("UPDATE posts SET status='ready' WHERE photo_id = ?", photo_id)

CDN STRATEGY:
  photos-cdn.instagram.com/{photo_id}_{size}.webp
  CDN: Akamai + Facebook's own CDN (Edge Network).
  Cache-Control: max-age=31536000 (1 year — images are immutable)
  
  Why immutable? Photo_id never changes → URL never changes → cache forever.
  No invalidation needed. Edit caption ≠ edit photo. Photo data is append-only.
  
  CDN hit rate: > 99% for popular photos (same photo served millions of times).
  Cold (new photo): CDN miss → fetch from S3 → cache at all edges → future hits.
```

---

## STEP 6 — Deep-Dive: Stories (24-Hour Expiry)

```
STORIES ARCHITECTURE:
  Stories are photos/videos that expire after 24 hours.
  User sees stories from followed accounts at top of feed.

STORAGE:
  Cassandra table with TTL:
  
  CREATE TABLE stories (
      story_id    UUID,
      author_id   UUID,
      media_url   TEXT,
      created_at  TIMESTAMP,
      PRIMARY KEY (author_id, story_id)
  ) WITH CLUSTERING ORDER BY (story_id DESC)
    AND default_time_to_live = 86400;  -- 24 hours TTL (Cassandra native)
  
  INSERT INTO stories (story_id, author_id, ...) VALUES (...)
  USING TTL 86400;  -- auto-deleted after 24h
  
  Get user's stories: SELECT * FROM stories WHERE author_id = ?
  Cassandra returns only non-expired stories (TTL enforced at storage layer).

STORY VIEWING ORDER:
  Stories from unread users appear first.
  Within each user: sorted by created_at.
  
  Track who has viewed your story:
  CREATE TABLE story_views (
      story_id    UUID,
      viewer_id   UUID,
      viewed_at   TIMESTAMP,
      PRIMARY KEY (story_id, viewer_id)
  ) WITH default_time_to_live = 86400;  -- auto-delete with story

STORY FEED CONSTRUCTION:
  1. Get list of users this user follows.
  2. For each followed user: check if they have recent stories (< 24h).
  3. Sort: unviewed first, then by latest story created_at.
  
  Optimization: Redis cache per user for "which followed users have stories today."
  Key: "stories_today:{user_id}" → [user_id_1, user_id_2, ...] (TTL: 10 minutes)
```

---

## STEP 7 — Search: Users and Hashtags

```
USER SEARCH:
  Elasticsearch index for user profiles.
  Fields: username (exact match, prefix), full_name (text search), bio.
  
  Search query:
  {
    "query": {
      "multi_match": {
        "query": "alice",
        "fields": ["username^3", "full_name^1"],  // username weighted 3×
        "type": "phrase_prefix"
      }
    },
    "size": 10
  }
  
  Typeahead (as user types):
  GET /search/users?q=alic → top 5 users matching prefix "alic"
  Use Redis ZADD "prefix:alic" for last 10 searches from this user (personalized suggestions).

HASHTAG SEARCH:
  Elasticsearch for hashtag search.
  
  Per hashtag: {tag: "sunset", post_count: 5_000_000}
  Per post: {post_id, hashtags: ["sunset", "travel"], created_at}
  
  GET /hashtags/sunset?sort=recent → posts with #sunset, sorted by time
  GET /hashtags/sunset?sort=top    → posts with #sunset, sorted by likes
  
  Trending hashtags: count hashtag usage in last 1 hour (Kafka stream → Redis sorted set).
  redis.zincrby("trending:hashtags:hourly", 1, "sunset")
  redis.zrevrange("trending:hashtags:hourly", 0, 9)  # top 10 trending
```

---

## STEP 8 — Trade-offs

```
TRADE-OFF 1: Fan-out on write vs read
  Fan-out on write: fast reads (pre-computed), expensive writes (push to all followers).
  Fan-out on read: slow reads (real-time aggregation), cheap writes.
  
  Decision: Hybrid. Fan-out on write for regular users (fast feed, manageable write volume).
  Fan-out on read for celebrities (can't push to 140M users in < 1s).

TRADE-OFF 2: Redis feed storage (4 TB) vs no feed pre-computation
  4 TB of Redis = significant infrastructure cost.
  Benefit: 290K feed reads/sec served in < 1ms.
  Alternative: compute feed on-demand (slow, expensive DB query).
  Decision: Storage is cheap. Latency is expensive. Pre-compute.

TRADE-OFF 3: Eventual consistency for feed (5-second delay for fan-out)
  During fan-out: some followers see new post, others don't (up to 5 seconds).
  Alternative: synchronous fan-out before confirming post (very slow).
  Decision: 5 seconds of inconsistency is invisible to users. Async fan-out is 1000× faster.

TRADE-OFF 4: WebP format vs JPEG
  WebP: 30% smaller at same quality. Better for mobile bandwidth.
  JPEG: universally supported by all browsers.
  Decision: WebP with JPEG fallback (use <picture> element in HTML).
  Progressive loading: serve low-res immediately, swap to high-res when loaded.
```

---

## STEP 9 — Follow-Up Questions

```
Q: "How do you handle a user with 1 billion followers (e.g., official Instagram account)?"
A: Pure fan-out on read. Don't push anything.
   Store their post in a separate "mega_celebrity_posts" table.
   At feed read time: always merge celebrity posts with user's pre-computed feed.
   Super-celebrity treated like a system broadcast, not a regular follow.

Q: "How do you implement infinite scroll on the feed?"
A: Cursor-based pagination.
   First page: GET /feed → returns {posts: [...], next_cursor: "eyJpZCI6MTIzfQ=="}
   Next page: GET /feed?cursor=eyJpZCI6MTIzfQ== → next 20 posts.
   Cursor encodes: last_post_id + last_post_timestamp.
   Redis: LRANGE feed:{user_id} 0 19, then 20 39, then 40 59... (offset in Redis list).

Q: "How do you rank the feed (not just chronological)?"
A: ML ranking model (Instagram's EdgeRank successor).
   Features: post age, your relationship strength with author, post engagement rate,
             your content preferences (you like travel photos → travel ranked higher).
   Apply ML score on top of candidate posts from Redis feed.
   Rerank: return top 20 after ML scoring.

Q: "What if a user uploads a video instead of a photo?"
A: Same pre-signed S3 upload flow. Kafka event triggers Video Transcoding Worker.
   Transcode to: HLS format (segments), multiple bitrates for adaptive streaming.
   Longer processing time: notify user when done.
   Video thumbnails: extract frame at 1s, use as cover image.
```


---

## STEP 10 — Deep-Dive: Notification System

```
EVENTS TRIGGERING NOTIFICATIONS:
  Like on post    -> notify post author
  Comment on post -> notify post author
  Follow          -> notify followed user
  @Mention        -> notify mentioned user
  Story view      -> aggregate viewers list, not individual push

ARCHITECTURE:
  User action -> [API Service] -> write DB -> publish Kafka event
  Kafka topic: "notification.events" (partitioned by recipient_user_id)
  [Notification Worker] consumes:
    1. Determine recipient
    2. Check: muted? blocked? notifications disabled for this type?
    3. Store in Cassandra notifications table
    4. Push via APNs (iOS) or FCM (Android)

NOTIFICATION BATCHING (avoiding spam):
  100 likes in 2 hours: don't send 100 pushes.
  Batch: "sachdev and 99 others liked your photo."
  
  Redis counter: "notif_batch:{post_id}:likes" with 15-min TTL.
  First like: push immediately, set Redis counter = 1.
  Subsequent likes: INCR counter, no push.
  On TTL expiry: if count > 1, send "X others also liked."

NOTIFICATION STORAGE (Cassandra):

  CREATE TABLE notifications (
      user_id     UUID,
      notif_id    TIMEUUID,
      type        TEXT,
      actor_id    UUID,
      post_id     UUID,
      is_read     BOOLEAN DEFAULT FALSE,
      PRIMARY KEY (user_id, notif_id)
  ) WITH CLUSTERING ORDER BY (notif_id DESC)
    AND default_time_to_live = 7776000;  -- 90-day TTL
  
  Partition = all notifications for one user on one node.
  TIMEUUID = time-ordered (newest first for free, no secondary index).
```

---

## STEP 11 — Deep-Dive: Like and Comment Counters

```
LIKE COUNTER PROBLEM:
  25B likes/day = 289K likes/sec avg; peak 1.4M likes/sec.
  Cannot write directly to DB at this rate.

SOLUTION: Redis INCR + Async Flush

  def like_post(post_id, user_id):
      # Idempotent check
      is_new = redis.sadd(f"liked_by:{post_id}", user_id)
      if not is_new:
          return  # already liked
      
      new_count = redis.incr(f"likes:{post_id}")
      kafka.publish("notification.events", {"type": "LIKE", "actor_id": user_id, "post_id": post_id})
      return {"likes": new_count}
  
  Async flush (every 30s):
    for key in redis.scan_iter("likes:*"):
        delta = redis.getdel(key)
        db.execute("UPDATE posts SET like_count = like_count + ? WHERE post_id = ?", delta, post_id)
  
  "liked_by" SET only kept in Redis for posts active in last 48h.
  Older posts: query Cassandra post_likes table:
    CREATE TABLE post_likes (post_id UUID, user_id UUID, PRIMARY KEY (post_id, user_id));

COMMENT STORAGE (Cassandra):
  CREATE TABLE comments (
      post_id    UUID,
      comment_id TIMEUUID,
      author_id  UUID,
      content    VARCHAR(2200),
      reply_to   UUID,
      like_count INT DEFAULT 0,
      PRIMARY KEY (post_id, comment_id)
  ) WITH CLUSTERING ORDER BY (comment_id DESC);
  
  Cursor pagination: WHERE comment_id < {cursor} LIMIT 20 -- O(1) per page flip.
```

---

## STEP 12 — Deep-Dive: Database Architecture

```
INSTAGRAM'S ACTUAL DATABASE STACK (2023):

PostgreSQL (CitusDB sharding):
  What: user accounts, follows, post metadata.
  Shard key: user_id for user-centric queries; post_id for post-centric.
  Scale: 10,000+ logical shards across ~100 physical DB clusters.
  Why: Instagram built on Django/PostgreSQL. Scaled via sharding, not DB replacement.

Cassandra:
  What: comments (time-series), notifications, activity feeds.
  Why: high write throughput, TTL support, natural time-ordered access pattern.

Memcached:
  What: DB query caching (pure read cache, no data structures).
  Why: simpler and slightly faster than Redis for pure key-value caching.
  mcrouter: Facebook-built Memcached proxy (consistent hashing, failover, replication).

Redis Cluster:
  What: pre-computed feeds (1000 post IDs per user), like/view counts,
        trending hashtags, sessions, rate limiting.
  Total: 4 TB+ across cluster.

S3 + Facebook CDN:
  What: all photo/video media.
  Cache-Control: max-age=31536000 (1 year, immutable URLs).
  CDN hit rate: >99% for popular content.

DUAL-SHARDING STRATEGY:
  posts_by_user (shard by user_id): for profile grid and user's history.
  posts_by_id (shard by post_id): for direct post access and comments.
  Writes: write to both shards (Saga pattern for consistency).
  Reads: route to relevant shard based on query type.
```

---

## STEP 13 — Deep-Dive: ML Feed Ranking

```
PROBLEM: User follows 1000 accounts. Opens Instagram after 8 hours.
  ~8,000 available posts. Must surface the 20 most relevant.

TWO-STAGE APPROACH:

STAGE 1: CANDIDATE GENERATION (8,000 -> 1,500)
  Pre-computed Redis feed (fan-out on write for regular users): ~800 posts.
  Celebrity follows (fan-out on read): ~200 posts.
  Reels/Explore recommendations: ~300 posts.
  Followed hashtags recent posts: ~200 posts.
  Total candidates: ~1,500.

STAGE 2: ML RANKING (1,500 -> top 50 -> final 20)

  KEY FEATURES:
  
  Post features:
    age_hours: exponential decay for older posts.
    engagement_velocity: likes per impression in first hour.
    post_type: photo/reel/carousel (user-specific type preference).
  
  User-Author relationship (STRONGEST signals):
    direct_interaction_score: how often user likes/comments author's posts.
    profile_visit_recency: visited author's profile in last 7 days?
    dm_history: ever sent a DM to this author? Very strong signal.
  
  User preference:
    topic_affinity: food? fitness? travel? (derived from last 50 likes).
    session_context: time of day + device type.

  PREDICTED OUTPUTS:
    P(like), P(comment), P(save) -- save weighted HIGHEST (strongest intent)
    P(not_interested) -- penalized heavily

  COMPOSITE SCORE:
    score = 2.0*P(save) + 1.0*P(like) + 1.5*P(comment) - 3.0*P(not_interested)
    
    Weights tuned via A/B testing to maximize long-term retention.

  FINAL ASSEMBLY:
    1500 scored -> top 50 selected.
    Dedup: max 2 consecutive posts from same author.
    Diversity: inject 1 "Discovery" post (non-followed account) every 7 posts.
    Return top 20 to client.

RETRAINING:
  Weekly retraining on 100M+ interaction events/day.
  PyTorch on Meta's ML cluster. Served via Triton Inference Server.
  Inference: <10ms for 1500 candidates.
```


---

## DEEP-DIVE IMPROVEMENT: Photo Upload Pipeline — Every Step Explained

```
FIVE STAGES OF A PHOTO UPLOAD (end-to-end):

STAGE 1: CLIENT-SIDE PREPROCESSING (on user's device before any network call)
  
  a) Compression:
     Original: iPhone 14 photo = 8MB RAW.
     Instagram client: detect format (HEIC/JPG/PNG) → convert to JPEG.
     Resize to max 1080×1080 (Instagram's max display resolution).
     JPEG quality = 85% (visually lossless, reduces to ~200-500KB).
     Why client-side? Saves bandwidth. 8MB → 300KB = 96% less data uploaded.
  
  b) Metadata stripping:
     EXIF data: contains GPS coordinates, camera serial number, timestamp.
     Privacy: Instagram strips GPS coordinates from EXIF (user option).
     Kept: camera model, orientation (for correct display rotation).
  
  c) Blurhash generation:
     Before upload: compute Blurhash of photo (20-byte string representing colors).
     "iVBO=.xZ3c01..." = placeholder shown while full photo loads.
     Sent inline in the post creation request (no separate upload).
     Why: allows server to show colored placeholder immediately — much better UX than grey box.

STAGE 2: PRE-SIGNED URL ACQUISITION
  
  Client → POST /api/media/initiate
  Request: {filename: "photo.jpg", filesize: 312000, mime_type: "image/jpeg"}
  
  Server (Upload Service):
    1. Validate: filesize < 10MB, mime_type allowed, user within storage quota.
    2. Generate S3 pre-signed URL:
       s3.generate_presigned_url(
           "put_object",
           Params={
               "Bucket": "instagram-uploads-raw",
               "Key": f"raw/{user_id}/{upload_id}/original.jpg",
               "ContentType": "image/jpeg",
               "ContentLength": 312000,
               "ServerSideEncryption": "AES256",  # encrypted at rest
           },
           ExpiresIn=3600  # URL valid for 1 hour
       )
    3. Store upload session in Redis: "upload:{upload_id}" → {user_id, status: "pending", expiry: ...}
    4. Return: {upload_id: "...", presigned_url: "https://instagram-uploads-raw.s3.amazonaws.com/..."}
  
  Why pre-signed URL instead of uploading through Instagram's server?
    Without: Client → Instagram Server → S3. Instagram server handles upload bandwidth.
    With: Client → S3 directly. Instagram Server handles only tiny JSON request.
    Instagram's servers: zero video/photo bandwidth. They scale for API calls, not file transfers.

STAGE 3: DIRECT UPLOAD TO S3
  
  Client: PUT {presigned_url} with photo bytes in body.
  S3 receives file. Verifies ContentLength matches. Stores in raw bucket.
  S3 emits event: S3:ObjectCreated to EventBridge / SNS.
  
  Multipart upload (for files > 5MB):
    Split into 5MB chunks. Upload each chunk independently.
    S3 assembles on finalize.
    If one chunk fails: retry only that chunk.
    Client: show upload progress bar (chunk_received / total_chunks).
  
  For Instagram photos (< 5MB after compression): single PUT. No multipart needed.
  For Instagram videos (up to 1GB): multipart critical.

STAGE 4: PROCESSING PIPELINE (async, post-upload)
  
  Trigger: S3 ObjectCreated event → Kafka "media.uploaded" topic.
  
  Multiple consumers in parallel:
  
  a) Image Processing Worker (most critical):
     Read raw JPEG from S3.
     Generate multiple sizes:
       Thumbnail:   150×150 (profile grid, search results)
       Square:      640×640 (main feed on mobile)
       Standard:    1080×1080 (full resolution display)
       High-DPI:    1440×1440 (retina displays)
     Apply: sharpening filter, color normalization.
     Encode all as JPEG (quality 90%) and WebP (30% smaller, for modern browsers).
     Upload all 8 variants to CDN bucket: cdn.instagram.com/media/{post_id}/...
     Publish: "media.processed" Kafka event.
  
  b) Content Safety Worker:
     PhotoDNA: perceptual hash → compare against CSAM database (required by law).
     NSFW classifier: ML model → score 0.0 to 1.0 (nudity/violence probability).
     Score > 0.9: automatically block post. Score 0.7-0.9: flag for human review.
     If blocked: publish "media.blocked" → post status = REJECTED.
  
  c) Machine Learning Worker:
     Object detection: what's in the photo? (food, face, nature, product, etc.)
     Face detection: how many faces? (used for suggesting tags/mentions)
     Alt-text generation: auto-generate accessibility text ("Two people at sunset beach").
     Landmark detection: recognize famous places → suggest location tag.
     These ML results stored in post metadata → used for recommendations + search.
  
  d) Thumbnail Extraction (videos only):
     Extract frame at t=1s → use as video cover thumbnail.
     Multiple candidate frames: user can pick which one.

STAGE 5: POST CREATION (after processing completes)
  
  "media.processed" event consumed by Post Service.
  Post status: PENDING → PUBLISHED.
  CDN URLs stored in posts table.
  Fan-out to followers' feeds (Kafka "post.published" event).
  Notification: "media.processed" → notify creator ("Your photo is ready!").
  
  Total time from upload complete to visible in feed: ~5-15 seconds.
  Why not instant? Distributed processing takes time.
  Instagram shows "Processing..." spinner during this window.
  
  Optimization for simple photos (no processing needed):
    For photos that pass initial safety check instantly:
    Show post in creator's own feed immediately ("optimistic publishing").
    Processing continues in background.
    If processing rejects it: pull from feed + notify user. Rare (< 0.01%).
```

---

## DEEP-DIVE IMPROVEMENT: Story Architecture (24-Hour Ephemerality)

```
STORIES ARE ARCHITECTURALLY DIFFERENT FROM POSTS:
  Posts: permanent (unless deleted), stored in postgres, indexed.
  Stories: ephemeral (24h TTL), ordered ring by user, viewer tracking.

KEY DIFFERENCES:
  1. TTL (Time to Live): stories auto-expire after 24 hours.
  2. View tracking: who viewed your story (unlike posts which only count views).
  3. Ring ordering: stories shown in a ring (left to right chronologically).
  4. Disappearing: 24h after posting, story disappears completely.

STORY DATA MODEL:

  CREATE TABLE stories (
      story_id       CHAR(11) PRIMARY KEY,           -- ULID for time-ordering
      author_id      UUID NOT NULL,
      media_url      TEXT NOT NULL,                   -- CDN URL
      media_type     TEXT NOT NULL,                   -- 'image' or 'video'
      duration_ms    INT DEFAULT 5000,                -- how long to show (5s default)
      thumbnail_url  TEXT,                            -- video thumbnail
      created_at     TIMESTAMP DEFAULT NOW(),
      expires_at     TIMESTAMP,                       -- created_at + 24 hours
      text_overlay   JSONB,                           -- stickers, text, drawings
      music_track_id UUID                             -- optional background music
  );
  CREATE INDEX idx_story_author ON stories(author_id, expires_at DESC);
  
  Stories TTL enforcement:
    PostgreSQL: expires_at column. Query: WHERE expires_at > NOW() (only active stories).
    Background job: DELETE FROM stories WHERE expires_at < NOW() - INTERVAL '1 hour'.
      Run hourly. Cleanup stories 1 hour past expiry (give CDN time to stop serving).
    CDN: story media has Cache-Control: max-age=86400 (24h). After 24h, CDN auto-expires.
    Why not Redis TTL? Stories table is in PostgreSQL (relational, for complex queries).
      Redis TTL only works for Redis keys, not PostgreSQL rows.

VIEW TRACKING — WHO SAW YOUR STORY:

  CREATE TABLE story_views (
      story_id   CHAR(11),
      viewer_id  UUID,
      viewed_at  TIMESTAMP DEFAULT NOW(),
      PRIMARY KEY (story_id, viewer_id)  -- composite PK prevents duplicate views
  );
  
  INSERT INTO story_views (story_id, viewer_id)
  VALUES (?, ?)
  ON CONFLICT (story_id, viewer_id) DO NOTHING;  -- idempotent: view twice = counted once
  
  Query "who viewed my story":
    SELECT viewer_id, viewed_at FROM story_views WHERE story_id = ?
    ORDER BY viewed_at DESC;
  
  This table is HUGE:
    1B users × 5 stories/day × avg 100 viewers = 500B rows/day.
    After 24h: these rows become useless (story expired).
    
    TTL strategy:
    Option A: Delete rows when story expires (cascade delete).
      DELETE FROM story_views WHERE story_id IN (SELECT story_id FROM stories WHERE expires_at < NOW()).
      Runs with the story cleanup job.
    
    Option B: Cassandra for story_views (better at TTL + high write volume).
      CREATE TABLE story_views (...) WITH default_time_to_live = 86400;
      Cassandra auto-purges rows after 24h. Zero maintenance needed.
      WINNER: Instagram uses Cassandra for story views.

STORY RING (the horizontal scroll of avatars):
  When you open Instagram: see a row of circles at top = who has stories.
  
  HOW IT'S BUILT:
    Redis Sorted Set per user: "story_ring:{user_id}"
    Score = latest_story_timestamp for each followed user who has an active story.
    Member = followed_user_id.
    
    When @bob posts a story:
      For each of Bob's followers: ZADD "story_ring:{follower_id}" {now} "bob_id"
    
    When Bob's story expires:
      ZREM "story_ring:{follower_id}" "bob_id" (fan-out to all followers)
      OR: just let Redis TTL handle it (if we set TTL on the score/member? Not possible with ZSET)
      Better: lazy removal: when building ring, filter out users with no active stories.
    
    Get story ring for Alice:
      ZRANGE "story_ring:{alice_id}" -1 0 REV WITHSCORES
      → Returns Bob, Carol, etc. sorted by most recent story first.
    
    Red dot (unviewed vs viewed):
      Unviewed: red/colored ring around avatar.
      Viewed: grey ring.
      Stored: Redis SET "stories_viewed:{alice_id}:{date}" → set of story_ids Alice viewed today.
      For each story in ring: check if any unviewed stories exist from that user.
      Result: show colored ring if user has unviewed stories; grey otherwise.
```

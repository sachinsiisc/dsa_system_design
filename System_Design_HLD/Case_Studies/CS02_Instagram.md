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

# CS08: Design Twitter / X (Social Media Platform)
## Full HLD Case Study | MAANG Interview Ready

---

## STEP 1 — Requirements Clarification

```
"Let me clarify scope and requirements before designing."

FUNCTIONAL:
  1. Post tweets: text (280 chars), images, videos, polls
  2. Follow / unfollow users
  3. Home timeline: chronological + ranked feed of tweets from people you follow
  4. Likes, retweets, replies, quote tweets
  5. Trending topics / hashtags: top topics globally and per-region in last 1 hour
  6. Search: full-text search across all tweets, users, hashtags
  7. Notifications: likes, retweets, replies, follows, mentions
  8. Direct Messages (simplified version — no E2EE focus here)
  9. Twitter Spaces (audio rooms) — out of scope

NON-FUNCTIONAL:
  - Scale: 400M registered users, 200M DAU
  - Tweets: 500M tweets posted/day → 5,787 tweets/sec avg; peak ~30,000/sec
  - Timeline reads: 200M DAU × 20 opens/day = 4B reads/day → 46,296/sec avg; peak 250K/sec
  - Read:Write ratio → 8:1 (reads dominate — optimize for reads)
  - Timeline load latency: < 200ms (user is looking at spinner)
  - Tweet fan-out latency: < 5 seconds (your tweet visible to followers within 5s)
  - High availability: 99.99% (Twitter going down is literally breaking news)
  - Eventual consistency acceptable for feed (seeing tweet 5s late is fine)
  - Global: 190+ countries, multilingual, per-country trending topics

OUT OF SCOPE:
  - Twitter Ads / Monetization
  - Twitter Blue / verified account features
  - Twitter Spaces (live audio)
```

---

## STEP 2 — Back-of-Envelope Estimation

```
WRITES (Tweets):
  500M tweets/day ÷ 86,400 = 5,787 tweets/sec avg
  Peak (3am UTC = peak US/Europe evening): 30,000 tweets/sec
  
  Per tweet storage:
    tweet_id (8B) + author_id (8B) + content (560B — 280 chars UTF-16) +
    created_at (8B) + reply_to (8B) + retweet_of (8B) + media_urls (100B) = ~700B
  
  Daily tweet storage: 500M × 700B = 350 GB/day
  Per year: 350 GB × 365 = 128 TB/year (text-only tweets)
  With media: 500M × 20% have images/video × avg 500KB = 50 TB/day media

READS (Timeline):
  4B timeline reads/day ÷ 86,400 = 46,296 reads/sec avg
  Peak: 250,000 reads/sec
  
  Each timeline read fetches 20 tweets. Each tweet: ~2KB.
  Bandwidth: 250,000 × 20 × 2KB = 10 GB/sec peak API bandwidth.

FOLLOWER GRAPH:
  400M users × avg 200 follows each = 80B follow relationships.
  Per edge: follower_id (8B) + followee_id (8B) + created_at (8B) = 24B.
  Total: 80B × 24B = 1.92 TB (just the graph, fits in sharded PostgreSQL).

LIKE COUNTS:
  200M DAU × 100 likes/day = 20B likes/day → 231K likes/sec avg.
  Peak: ~1.2M likes/sec. Cannot update DB directly.
  Solution: Redis INCR + async flush.

FAN-OUT ESTIMATION:
  Each tweet from user with 1000 followers: 1000 Redis writes.
  5,787 tweet/sec × 1000 followers avg = 5.787M Redis writes/sec for fan-out.
  Redis Cluster handles 10M ops/sec → manageable (with caveats for celebrities).
  
  But: Elon Musk (140M followers) tweets → 140M Redis writes.
  At 1M writes/sec per node: 140 seconds. UNACCEPTABLE.
  → Hybrid fan-out strategy needed (see Deep-Dive 1).

STORAGE:
  Redis timelines: 200M users × 800 tweet IDs × 8 bytes = 1.28 TB.
  Redis Cluster: 6+ nodes, 256 GB each → 1.5 TB total. Fits.
  
  Tweet metadata cache: top 10M tweets × 2KB = 20 GB.
  Cassandra (tweet store): 128 TB/year → sharded cluster.

SEARCH INDEX:
  500M tweets/day × avg 20 tokens/tweet = 10B new index entries/day.
  Recent tweet index (30 days): 10B × 30 = 300B entries.
  Elasticsearch cluster: 300B × 50B each ≈ 15 TB.
```

---

## STEP 3 — High-Level Architecture

```
WRITE PATH (tweet creation):

  ┌──────────┐  POST /tweets          ┌──────────────────────────────────────────┐
  │  Client  │──────────────────────► │  API Gateway (Kong / AWS API GW)         │
  └──────────┘                        │  Auth, rate limit (300 tweets/3hr/user)  │
                                      └────────────────────┬─────────────────────┘
                                                           │
                                              ┌────────────▼────────────────┐
                                              │  Tweet Service               │
                                              │  1. Validate (280 chars)     │
                                              │  2. Generate tweet_id (ULID) │
                                              │  3. Write to Cassandra        │
                                              │  4. Return tweet to client   │
                                              └────────────┬────────────────┘
                                                           │
                                              ┌────────────▼────────────────┐
                                              │  Kafka: "tweet.created"      │
                                              └─────┬──────────┬────────────┘
                                                    │          │
                              ┌─────────────────────┼──────────┼──────────────────┐
                              │                     │          │                  │
                   ┌──────────▼──────┐    ┌─────────▼───┐ ┌───▼──────────┐ ┌────▼────────┐
                   │  Fan-out Worker │    │  Search     │ │  Notification│ │  Media      │
                   │  (push to Redis │    │  Indexer    │ │  Worker      │ │  Processor  │
                   │  timelines)     │    │  (ES index) │ │  (push/FCM)  │ │  (S3 + CDN) │
                   └─────────────────┘    └─────────────┘ └──────────────┘ └─────────────┘

READ PATH (home timeline):

  ┌──────────┐  GET /home_timeline    ┌──────────────────────────────────────────┐
  │  Client  │──────────────────────► │  Timeline Service                        │
  └──────────┘ ◄────────────────────  │  1. Get pre-computed timeline from Redis │
                {tweets: [...]}        │  2. Merge celebrity tweets (fan-out read)│
                                       │  3. Hydrate tweet IDs → full tweet data  │
                                       │  4. Apply ML ranking (optional)          │
                                       └──────────────────────────────────────────┘

FULL ARCHITECTURE DIAGRAM:

  ┌────────────────────────────────────────────────────────────────────────────────┐
  │                   CLIENTS (Web / iOS / Android)                                │
  └───────────────────────────────────┬────────────────────────────────────────────┘
                                      │
  ┌───────────────────────────────────▼────────────────────────────────────────────┐
  │                   API GATEWAY (Kong + AWS ALB)                                  │
  │         Auth (JWT), Rate Limiting, SSL, Request Routing                         │
  └──────┬──────────────┬─────────────────┬─────────────────┬────────────────────── ┘
         │              │                 │                 │
  ┌──────▼──────┐ ┌─────▼──────┐ ┌───────▼────────┐ ┌─────▼──────────────┐
  │  Tweet      │ │  Timeline  │ │  User / Follow │ │  Notification      │
  │  Service    │ │  Service   │ │  Service       │ │  Service           │
  └──────┬──────┘ └─────┬──────┘ └───────┬────────┘ └────────────────────┘
         │              │                 │
  ┌──────▼────────────────▼─────────────────▼──────────────────────────────────┐
  │                       KAFKA (Event Bus)                                      │
  │  Topics: tweet.created | tweet.liked | follow.created | media.uploaded      │
  └──────┬──────────────────────────────────────────────────────────────────────┘
         │
  ┌──────▼──────────────────────────────────────────────────────────────────────┐
  │                    DATA TIER                                                  │
  │  ┌─────────────────────┐  ┌─────────────────────┐  ┌────────────────────┐  │
  │  │  Cassandra Cluster  │  │  Redis Cluster      │  │  Elasticsearch     │  │
  │  │  (tweets store,     │  │  (timelines cache,  │  │  (tweet search,    │  │
  │  │  notifications)     │  │  tweet metadata,    │  │  user search,      │  │
  │  │                     │  │  like counts,       │  │  trending topics)  │  │
  │  │                     │  │  trending)          │  │                    │  │
  │  └─────────────────────┘  └─────────────────────┘  └────────────────────┘  │
  │  ┌─────────────────────┐  ┌─────────────────────┐                          │
  │  │  PostgreSQL         │  │  S3 + CloudFront    │                          │
  │  │  (users, follows,   │  │  (media: images,    │                          │
  │  │  DMs)               │  │  videos)            │                          │
  │  └─────────────────────┘  └─────────────────────┘                          │
  └─────────────────────────────────────────────────────────────────────────────┘
```

---

## STEP 4 — Deep-Dive: Timeline Fan-out Architecture

```
THE CORE PROBLEM:
  Home timeline = tweets from everyone you follow, sorted by time (or ranked).
  Option A: Precompute on write (fan-out on write)
  Option B: Compute on read (fan-out on read)
  Option C: Hybrid

APPROACH A — FAN-OUT ON WRITE:
  When @User posts:
    1. Get their follower list (50K followers → 50K IDs)
    2. For each follower: push tweet_id to their timeline Redis list
    
  Timeline structure in Redis:
    Key: "timeline:{user_id}" → Redis LIST of tweet_ids (most recent first)
    Max size: 800 tweet IDs per user (ltrim to 800)
  
  Pros:
    Timeline reads are instant: LRANGE timeline:{user_id} 0 19 = 20 tweet IDs
    No computation at read time
  
  Cons:
    Elon Musk (140M followers) tweets → 140M Redis LPUSH operations
    At 500K Redis ops/sec per node: 140M / 500K = 280 seconds. UNACCEPTABLE.

APPROACH B — FAN-OUT ON READ:
  No pre-computation on tweet creation.
  When user opens timeline:
    1. Get list of 200 users they follow
    2. For each followed user: GET their latest 5 tweets
    3. Merge 200 × 5 = 1000 tweets → sort by timestamp → return top 20
  
  Pros: tweet creation is instant (no fan-out work)
  Cons:
    Timeline read = 200 DB queries in parallel = slow, expensive.
    Even with Redis: 200 Redis calls per timeline open.
    Timeline load = 1+ second = BAD UX.

APPROACH C — TWITTER'S HYBRID STRATEGY (ACTUAL):

  THRESHOLD: 10,000 followers.
  
  Regular users (< 10K followers) → FAN-OUT ON WRITE:
    → Push tweet_id to all followers' Redis timelines.
    → 10K Redis writes = < 50ms. Acceptable.
  
  Celebrity users (≥ 10K followers) → FAN-OUT ON READ:
    → Don't push to followers' timelines.
    → Store tweet in celebrity's own Redis list: "celeb_timeline:{celeb_id}"
    → At read time: merge each celebrity's list with user's pre-computed timeline.
  
  At READ TIME (get home timeline for @NormalUser):
  
    def get_home_timeline(user_id: str, count: int = 20) -> list[dict]:
        # Step 1: Pre-computed timeline from regular follows (fan-out-on-write)
        tweet_ids = redis.lrange(f"timeline:{user_id}", 0, 99)
        # This is fast: O(1) Redis read, already populated.
        
        # Step 2: Celebrity follows (fan-out-on-read)
        celeb_ids = redis.smembers(f"celeb_follows:{user_id}")
        # Store separately: which celebrities does this user follow?
        
        celeb_tweet_ids = []
        if celeb_ids:
            pipeline = redis.pipeline()
            for cid in celeb_ids:
                pipeline.lrange(f"celeb_timeline:{cid}", 0, 19)
            celeb_results = pipeline.execute()
            for tweets in celeb_results:
                celeb_tweet_ids.extend(tweets)
        
        # Step 3: Merge both lists, deduplicate, sort
        # tweet_ids are ULIDs: time-ordered, so sorting is O(N log N)
        all_ids = list(set(tweet_ids + celeb_tweet_ids))
        all_ids.sort(reverse=True)  # ULID sort = chronological sort
        top_ids = all_ids[:count]
        
        # Step 4: Hydrate tweet IDs → full tweet data
        return hydrate_tweets(top_ids)
    
    def hydrate_tweets(tweet_ids: list) -> list[dict]:
        """Fetch tweet content. Try Redis first, fall back to Cassandra."""
        pipe = redis.pipeline()
        for tid in tweet_ids:
            pipe.get(f"tweet:{tid}")
        cached = pipe.execute()
        
        result = []
        uncached_ids = []
        for tid, data in zip(tweet_ids, cached):
            if data:
                result.append(json.loads(data))
            else:
                uncached_ids.append(tid)
        
        if uncached_ids:
            # Batch fetch from Cassandra
            db_tweets = cassandra.execute(
                "SELECT * FROM tweets WHERE tweet_id IN ?",
                (tuple(uncached_ids),)
            )
            pipe = redis.pipeline()
            for tweet in db_tweets:
                pipe.setex(f"tweet:{tweet['tweet_id']}", 3600, json.dumps(tweet))
                result.append(tweet)
            pipe.execute()
        
        return sorted(result, key=lambda x: x['tweet_id'], reverse=True)

FAN-OUT WORKER (async, from Kafka):

  class FanoutWorker:
      CELEBRITY_THRESHOLD = 10_000
      MAX_TIMELINE_SIZE = 800
      
      def process(self, event: dict):
          tweet_id = event['tweet_id']
          author_id = event['author_id']
          
          author = user_service.get(author_id)
          
          if author.follower_count >= self.CELEBRITY_THRESHOLD:
              # Celebrity: only update their own celeb_timeline cache
              redis.lpush(f"celeb_timeline:{author_id}", tweet_id)
              redis.ltrim(f"celeb_timeline:{author_id}", 0, 199)
              # → 2 Redis ops regardless of follower count. O(1)!
              return
          
          # Regular user: push to ALL followers' timelines
          followers = db.get_followers_paginated(author_id, page_size=5000)
          for batch in followers:
              pipeline = redis.pipeline()
              for follower_id in batch:
                  pipeline.lpush(f"timeline:{follower_id}", tweet_id)
                  pipeline.ltrim(f"timeline:{follower_id}", 0, self.MAX_TIMELINE_SIZE - 1)
              pipeline.execute()  # one round-trip per batch of 5000
          # 10K followers → 2 batches → 2 Redis round-trips. Fast!

TIMELINE REFRESH (cursor-based pagination):
  First load: GET /timeline → {tweets: [...], cursor: "ulid_XXXXX"}
  Scroll down: GET /timeline?cursor=ulid_XXXXX → 20 more tweets before cursor
  Pull to refresh: GET /timeline?since=ulid_YYYYY → tweets newer than since
  
  Implementation:
    Redis LRANGE with offset for pagination.
    cursor = last tweet_id of current page.
    Next page: LPOS to find cursor position → LRANGE from cursor+1.
```

---

## STEP 5 — Deep-Dive: Tweet Storage (Cassandra)

```
WHY CASSANDRA:
  Write throughput: 30,000 tweets/sec peak. Cassandra: millions of writes/sec.
  Access pattern: "get tweet by tweet_id" (point lookup) OR "get all tweets by user" (range scan).
  These map naturally to Cassandra partition + clustering keys.
  TTL: can auto-expire old tweets after N years (storage management).
  No JOINs needed: tweets are self-contained.
  Linear scalability: add nodes → proportionally more capacity.

TWEET STORAGE SCHEMA:

  -- Primary tweet store (partition by tweet_id for point lookups)
  CREATE TABLE tweets (
      tweet_id      TEXT,          -- ULID (time-ordered unique ID, e.g., "01J8K4E9Z3...")
      author_id     UUID,
      content       VARCHAR(560),  -- 280 chars × max 2 bytes UTF-16 = 560 bytes
      media_urls    LIST<TEXT>,    -- CDN URLs for images/videos
      reply_to_id   TEXT,          -- null if original tweet
      retweet_of_id TEXT,          -- null if not a retweet
      is_quote      BOOLEAN DEFAULT FALSE,
      hashtags      SET<TEXT>,     -- ["python", "systemdesign"]
      mentions      SET<TEXT>,     -- ["sachdev", "elonmusk"]
      lang          TEXT,          -- 'en', 'es', 'ja'
      geo_lat       FLOAT,         -- optional geotagging
      geo_lng       FLOAT,
      like_count    COUNTER,
      retweet_count COUNTER,
      reply_count   COUNTER,
      quote_count   COUNTER,
      created_at    TIMESTAMP,
      PRIMARY KEY (tweet_id)       -- global point lookup by tweet_id
  );
  
  -- User's tweet timeline (for profile page: "all tweets by @user")
  CREATE TABLE user_tweets (
      author_id    UUID,
      tweet_id     TEXT,          -- ULID sorts chronologically
      created_at   TIMESTAMP,
      PRIMARY KEY (author_id, tweet_id)
  ) WITH CLUSTERING ORDER BY (tweet_id DESC);   -- newest first
  
  -- For thread/conversation view: "all replies to tweet X"
  CREATE TABLE tweet_replies (
      root_tweet_id TEXT,         -- top of the thread
      tweet_id      TEXT,
      author_id     UUID,
      created_at    TIMESTAMP,
      PRIMARY KEY (root_tweet_id, tweet_id)
  ) WITH CLUSTERING ORDER BY (tweet_id ASC);    -- oldest first for threads

WHY ULID INSTEAD OF UUID FOR TWEET_ID:
  UUID: random → no time ordering → range queries need full scan.
  ULID (Universally Unique Lexicographically Sortable ID):
    48 bits: millisecond timestamp → sorts chronologically.
    80 bits: random → globally unique without coordination.
    Example: "01J8K4E9Z3THJN8H5YP25BSJME"
    
    Benefits:
      Sorting by tweet_id = sorting by creation time. Free ordering!
      No separate created_at column needed for sorting.
      B-tree indexes efficient (sequential inserts, no random hot spots).
  
  Twitter's actual choice: Snowflake IDs (same principle — 41 bits timestamp).
  Snowflake: 41-bit timestamp | 10-bit machine ID | 12-bit sequence = 64-bit integer.
  Encodes to ~19 digits (their public tweet IDs).

LIKE COUNTER DESIGN:
  Cassandra COUNTER columns: atomic increment, no read-modify-write.
  Problem: COUNTER columns can't be in same table as regular columns.
  Fix: separate table.
  
  -- Separate counter table
  CREATE TABLE tweet_counters (
      tweet_id    TEXT PRIMARY KEY,
      like_count  COUNTER,
      retweet_count COUNTER,
      reply_count  COUNTER
  );
  
  UPDATE tweet_counters SET like_count = like_count + 1 WHERE tweet_id = ?
  -- Cassandra makes this atomic even at high concurrency. No locking needed.
  
  Alternative (faster): Redis INCR per tweet.
  redis.incr(f"likes:{tweet_id}")
  → Periodic sync to Cassandra (every 30 seconds).
  → Redis INCR: O(1), in-memory, atomic. Handles 1.2M like/sec easily.
  → Trade-off: if Redis crashes, lose up to 30s of like counts. Acceptable.
```

---

## STEP 6 — Deep-Dive: Trending Topics

```
GOAL: show top 10 trending hashtags/topics in last 1 hour, per region.

NAIVE APPROACH:
  For every tweet: INSERT hashtag occurrence into DB.
  Query: SELECT hashtag, COUNT(*) FROM occurrences WHERE created_at > NOW()-3600 GROUP BY hashtag.
  Problem: 500M tweets/day × avg 2 hashtags = 1B insertions/day.
  GROUP BY on 1B rows = slow, expensive. Won't work in real-time.

APPROACH: SLIDING WINDOW WITH REDIS SORTED SETS

  Key insight: count per hashtag per 1-minute bucket.
  
  class TrendingService:
      # Time windows for trending
      WINDOWS = {"1h": 3600, "24h": 86400}
      
      def record_hashtags(self, tweet_id: str, hashtags: list[str], timestamp: int):
          """Called from Kafka consumer for every tweet created."""
          # Bucket timestamp to nearest minute
          minute_bucket = timestamp // 60
          
          pipeline = redis.pipeline()
          for tag in hashtags:
              for window_name, window_secs in self.WINDOWS.items():
                  key = f"trending:{window_name}:{minute_bucket}"
                  pipeline.zincrby(key, 1, tag)           # increment score for tag
                  pipeline.expire(key, window_secs + 600)  # keep bucket alive for window + buffer
          pipeline.execute()
      
      def get_trending(self, window: str = "1h", region: str = "global", count: int = 10):
          """Get top trending hashtags by merging relevant minute buckets."""
          now = int(time.time())
          window_secs = self.WINDOWS[window]
          num_buckets = window_secs // 60  # 60 buckets for 1-hour window
          
          # Get all relevant minute bucket keys
          buckets = [
              f"trending:{window}:{now // 60 - i}"
              for i in range(num_buckets)
          ]
          
          # ZUNIONSTORE: sum all bucket counts into a temporary key
          temp_key = f"trending_union:{window}:{region}:{now // 60}"
          redis.zunionstore(temp_key, buckets, aggregate="SUM")
          redis.expire(temp_key, 300)  # cache merged result for 5 min
          
          # Get top K by score (count)
          return redis.zrevrange(temp_key, 0, count - 1, withscores=True)
          # Returns: [("#AI", 1420000), ("#Python", 980000), ...]
  
  OPTIMIZATION: don't recompute ZUNIONSTORE every request.
    Cache result: "trending_result:{window}:{region}:{now // 300}" (5-min cache).
    Same trending topics for 5 minutes → acceptable lag.
    Popular feature → many parallel reads hit same cached key → fast.
  
  REGIONAL TRENDING:
    Track per-region too: key "trending:{window}:{minute}:{country_code}"
    When user in India: query "trending:1h:IN" not "trending:1h:global".
    Country detected from user IP via GeoIP lookup.

FILTERING TRENDING TOPICS:
  Problem: "mass shooting in city X" → naturally trending. Should it be in trending?
  Problem: spam/bot accounts inflating a hashtag.
  
  Bot filtering:
    Each hashtag increment weighted by account quality.
    New accounts (< 30 days old): weight = 0.1.
    Verified accounts: weight = 2.0.
    redis.zincrby(key, account_quality_weight, tag)  # not just +1
  
  Content sensitivity filtering:
    Blocklist: never trend certain sensitive topics.
    ML classifier: score trending topics → filter score > threshold → removed from trending.
  
  Velocity filtering: trend requires sustained engagement, not a spike.
    Trend must grow across multiple consecutive minute buckets.
    Single-minute spike (one coordinated bot attack) → filtered out.
```

---

## STEP 7 — Deep-Dive: Notification System

```
EVENTS THAT TRIGGER NOTIFICATIONS:
  Like       → notify tweet author
  Retweet    → notify tweet author
  Reply      → notify tweet author
  Follow     → notify followed user
  Mention    → notify @mentioned user
  Quote tweet→ notify quoted tweet author

ARCHITECTURE:

  Tweet event → Kafka → Notification Worker → determines recipients
             → Notification Store (Cassandra)
             → Push Dispatcher → iOS: APNs | Android: FCM | Web: WebSocket

NOTIFICATION WORKER:
  
  def handle_event(event: dict):
      event_type = event['type']  # 'like', 'retweet', 'reply', 'follow', 'mention'
      
      if event_type == 'like':
          tweet = cassandra.get_tweet(event['tweet_id'])
          recipient_id = tweet['author_id']
          
          # Don't notify if actor == recipient (liking your own tweet)
          if event['actor_id'] == recipient_id:
              return
          
          # Don't notify if recipient has muted actor
          if is_muted(recipient_id, event['actor_id']):
              return
          
          notif = {
              'notif_id': ulid.new(),
              'user_id': recipient_id,
              'type': 'like',
              'actor_id': event['actor_id'],
              'tweet_id': event['tweet_id'],
              'created_at': now(),
              'read': False
          }
          
          # Store in Cassandra
          cassandra.insert_notification(notif)
          
          # Push immediately if user is online
          if presence_service.is_online(recipient_id):
              websocket_service.push(recipient_id, {
                  'type': 'notification',
                  'notification': notif
              })
          else:
              # Push to mobile
              push_service.send(recipient_id, {
                  'title': f'@{actor_username} liked your tweet',
                  'body': tweet['content'][:100],
                  'data': {'type': 'like', 'tweet_id': event['tweet_id']}
              })

NOTIFICATION BATCHING (avoid notification spam):
  Viral tweet gets 50K likes in 1 hour → 50K individual notifications? NO.
  Twitter batches: "50,000 people liked your tweet" instead of 50K notifications.
  
  Batching logic:
    After first notification: set timer "batch:{tweet_id}:{author_id}" for 60 seconds.
    During 60s: count additional likes, don't send more.
    After 60s: send batch notification "X more people liked your tweet".
    Redis: "pending_batch:{tweet_id}:{author_id}:{type}" → count. TTL 60s.
    After TTL fires: Lua script reads count → sends batch notification.

NOTIFICATION STORAGE (Cassandra):

  CREATE TABLE notifications (
      user_id     UUID,       -- partition key: all notifs for one user on one node
      notif_id    TEXT,       -- ULID: time-ordered, newest first
      type        TEXT,       -- LIKE, RETWEET, REPLY, FOLLOW, MENTION
      actor_id    UUID,       -- who did the action
      tweet_id    TEXT,       -- target tweet (nullable for FOLLOW notifications)
      read        BOOLEAN DEFAULT FALSE,
      created_at  TIMESTAMP,
      PRIMARY KEY (user_id, notif_id)
  ) WITH CLUSTERING ORDER BY (notif_id DESC)
    AND default_time_to_live = 7776000;  -- auto-expire after 90 days

PUSH DELIVERY:
  iOS    → APNs (Apple Push Notification Service):
    Requires: device_token (registered at app launch), auth key from Apple.
    Payload max: 4 KB. Always delivered (APNs queues if device offline).
  
  Android → FCM (Firebase Cloud Messaging):
    Requires: registration_token per device.
    Payload max: 4 KB. Queues if device offline (up to 4 weeks).
  
  Web    → Web Push API (browser's push service):
    Standard protocol. Works on Chrome, Firefox, Safari.
    Requires VAPID keys for authentication.
  
  Twitter maintains device_token store:
    user_id → [device_token_1 (iOS), device_token_2 (Android)]
    User can have multiple devices. Send to ALL.
    Stored in Redis: "devices:{user_id}" → SET of device_tokens.
```

---

## STEP 8 — Deep-Dive: Search

```
REQUIREMENTS:
  Full-text search across 500M tweets/day (15B+ tweets indexable).
  Must be < 100ms latency.
  Results boosted by: recency, like_count, author follower count, relevance.

ELASTICSEARCH CLUSTER:
  Index 500M new tweets/day = 5,787 tweets/sec → 5,787 Elasticsearch writes/sec.
  Elasticsearch handles 100K+ writes/sec across cluster → no problem.
  
  INDEX SCHEMA:
  {
    "tweet_id": "01J8K4E9Z3THJN8H5YP25BSJME",
    "content": "Just deployed my distributed cache and it cut latency by 80%!",
    "author_id": "user_abc123",
    "author_username": "sachdev",
    "author_followers": 15000,
    "hashtags": ["distributed", "cache", "systemdesign"],
    "mentions": [],
    "lang": "en",
    "like_count": 423,
    "retweet_count": 89,
    "reply_count": 12,
    "created_at": "2026-09-21T08:00:00Z",
    "has_media": false
  }
  
  SEARCH QUERY: "distributed cache latency"
  → Elasticsearch BM25 scoring on content field
  → Boosted by: recency (newer tweets score higher), like_count (social proof)
  
  {
    "query": {
      "function_score": {
        "query": {
          "bool": {
            "must": [
              {"multi_match": {
                "query": "distributed cache latency",
                "fields": ["content^3", "hashtags^2", "author_username^1"]
              }}
            ],
            "filter": [
              {"range": {"created_at": {"gte": "now-7d"}}}  // last 7 days by default
            ]
          }
        },
        "functions": [
          // Boost by log(like_count): viral tweets score higher
          {"field_value_factor": {"field": "like_count", "modifier": "log2", "factor": 0.3}},
          // Recency decay: tweets age reduces score over time
          {"gauss": {"created_at": {"scale": "6h", "decay": 0.5, "offset": "1h"}}},
          // Author authority: high follower count = authoritative
          {"field_value_factor": {"field": "author_followers", "modifier": "log1p", "factor": 0.1}}
        ],
        "score_mode": "sum",
        "boost_mode": "multiply"
      }
    },
    "size": 20
  }

SEARCH INDEXING PIPELINE:
  1. Kafka: tweet.created event consumed by Search Indexer Worker.
  2. Worker: creates ES document, indexes to Elasticsearch.
  3. Indexing lag: ~10-30 seconds (acceptable — not real-time).
  
  At scale: 5,787 docs/sec → Elasticsearch bulk API (batch 1000 at a time).
  Bulk insert: 1000 tweets every ~173ms. ES handles this trivially.

TIERED SEARCH SHARDS:
  Hot shard: last 30 days (SSD, lots of RAM for in-memory index)
  Cold shard: older tweets (HDD, cheaper)
  Archive: tweets > 1 year old (not searchable by default; "All time" filter enables)
  
  Why: 90% of searches want recent tweets. Hot shard: fast SSD, small index.
  Searching old tweets: slower → user opted in by selecting "From any time".

HASHTAG SEARCH:
  Special treatment: #python is an exact token.
  Hashtag field: exact-match, not analyzed.
  {"term": {"hashtags": "systemdesign"}} vs full-text search on content.
  Hashtag results sorted by time (not relevance) — users expect chronological.

USER SEARCH:
  Different index (users, not tweets).
  Fields: username (exact + prefix), display_name (full-text), bio.
  Prefix search: "sachd" → "@sachdev" via ES completion suggester.
  Ranked by: follower count (verified/popular users first).
```

---

## STEP 9 — Database Schema Summary

```
Service          │ DB            │ Schema Details
─────────────────┼───────────────┼──────────────────────────────────────────────
Tweets (primary) │ Cassandra     │ PK: tweet_id (ULID). Counter cols for likes.
User tweets      │ Cassandra     │ PK: (author_id, tweet_id DESC). Profile page.
Tweet replies    │ Cassandra     │ PK: (root_id, tweet_id ASC). Thread view.
Users            │ PostgreSQL    │ PK: user_id. Indexed: username (unique).
Follow graph     │ PostgreSQL    │ Composite: (follower_id, followee_id).
Notifications    │ Cassandra     │ PK: (user_id, notif_id DESC). 90-day TTL.
Redis timelines  │ Redis LIST    │ Key: "timeline:{user_id}". Max 800 entries.
Celeb timelines  │ Redis LIST    │ Key: "celeb_timeline:{celeb_id}". Max 200.
Tweet metadata   │ Redis STRING  │ Key: "tweet:{tweet_id}". TTL: 1 hour.
Like counts      │ Redis INCR    │ Key: "likes:{tweet_id}". Async flush to DB.
Trending         │ Redis ZSET    │ Key: "trending:{window}:{minute}:{region}".
Device tokens    │ Redis SET     │ Key: "devices:{user_id}".
Search index     │ Elasticsearch │ Full tweet documents. Hot (30d) + cold shards.
Media files      │ S3            │ Path: /tweets/{tweet_id}/{filename}.
```

---

## STEP 10 — Bottlenecks and Solutions

```
BOTTLENECK 1: Timeline fan-out for celebrities
  Problem: Elon Musk tweets → 140M Redis writes → 280 seconds.
  Solution: hybrid fan-out. Celebrity tweets stored in separate Redis list.
  Read-time merge: O(celeb_count_followed × 20 tweets) ≈ trivial.
  Cost: slightly slower read (merge 5 celeb lists + personal list).

BOTTLENECK 2: Like count at 1.2M likes/sec
  Problem: 1.2M DB writes/sec → Cassandra overloaded.
  Solution: Redis INCR (atomic, O(1), in-memory).
  Async flush to Cassandra every 30 seconds.
  Trade-off: up to 30s stale like count. Users don't notice.
  Crash safety: Redis persistence (AOF mode) → at most 1-second loss.

BOTTLENECK 3: Timeline Redis storage (1.28 TB)
  200M users × 800 tweet IDs × 8B = 1.28 TB.
  Single Redis node: max ~100 GB RAM. Can't fit.
  Solution: Redis Cluster with consistent hashing.
  Shard by user_id → 16+ nodes. 1.28 TB / 16 nodes = 80 GB/node. Fits.

BOTTLENECK 4: Fan-out worker falling behind during spike
  30,000 tweets/sec × avg 1000 followers = 30M Redis ops/sec during peak.
  Redis Cluster max: 10M ops/sec per node, with 16 nodes = 160M ops/sec.
  30M < 160M → handles peak.
  But: Kafka consumer lag can grow if tweets spike (e.g., breaking news).
  Solution: autoscale fan-out workers (Kubernetes HPA based on Kafka consumer lag).

BOTTLENECK 5: Search indexing lag grows during high tweet volume
  Peak: 30,000 tweets/sec → 30,000 ES writes/sec.
  Elasticsearch cluster can handle this with enough nodes and bulk API.
  Trade-off: latency may grow to 1-2 minutes during extreme spikes (World Cup final).
  Solution: pre-scale ES cluster before known high-traffic events.
  Failure mode: indexing lag grows → search temporarily shows old content.
  Detection: monitor Kafka consumer group lag for search indexer topic.
```

---

## STEP 11 — Trade-offs

```
TRADE-OFF 1: Fan-out on write vs read vs hybrid
  Fan-out write: fast reads, expensive writes. Fails for celebrities.
  Fan-out read: cheap writes, slow reads. Fails at scale.
  Hybrid: best of both. Complexity: must track which follows are celebrities.
  Celebrity threshold (10K followers): configurable. Can adjust to tune cost/latency.
  Decision: Hybrid. Industry standard for social media platforms at this scale.

TRADE-OFF 2: Timeline pre-computation (Redis) vs on-demand DB query
  Pre-computed: 1.28 TB of Redis. Instant reads. Stale by seconds.
  On-demand: DB query "SELECT tweet_id FROM tweets WHERE author_id IN (follows)" = slow.
  Decision: pre-compute. Storage cost (1.28 TB Redis) << latency cost (bad UX).
  
TRADE-OFF 3: ULID vs UUID for tweet_id
  UUID: globally unique but random → index fragmentation in B-trees.
  ULID: time-ordered unique → sequential B-tree inserts → 50% better write performance.
  Decision: ULID. Better write throughput, free chronological sorting.

TRADE-OFF 4: Like count eventual consistency vs strong consistency
  Strong: every like → DB write → accurate count.
  Eventual: Redis → flush every 30s → count lag.
  Decision: eventual. "42" vs "43" likes makes zero UX difference.
  Cost of strong consistency: 1.2M writes/sec vs Cassandra's 100K writes/sec limit. Impossible.

TRADE-OFF 5: Trending topics freshness vs cost
  5-minute cache on trending topics → stale by up to 5 minutes.
  1-minute cache → 5× more Redis computation.
  Decision: 5 minutes. Twitter users don't notice 5-min stale trending topics.
  Exception: breaking news mode → Twitter can reduce to 1 minute manually.
```

---

## STEP 12 — Follow-Up Questions

```
Q: "How would you handle a 'trending' manipulation attack (bot farms using a hashtag)?"
A: Bot detection at multiple layers:
   1. Account age: new accounts (< 7 days) weighted very low in trending.
   2. Behavior: accounts tweeting same hashtag without prior engagement = suspicious.
   3. Velocity: hashtag going from 0 to 1M uses in 5 min = unnatural spike → flagged.
   4. Device fingerprinting: same device/IP posting many accounts.
   5. ML model: trained on historical bot activity → score each account.
   Weight trending contributions by account quality score.
   Coordinated inauthentic behavior → entire batch discounted.

Q: "How would you implement Twitter Spaces (live audio)?"
A: Completely different stack — WebRTC-based, not HTTP.
   - Room service: creates/manages audio room metadata (host, speakers, listeners).
   - Media server: SFU (Selective Forwarding Unit) — receives host's audio, forwards to listeners.
   - Scale: one SFU can handle ~100 listeners. Celebrity with 1M listeners: 10,000 SFUs.
   - Fan-out: SFUs form a tree — SFU-1 forwards to SFU-2 and SFU-3 → each serves listeners.
   - Low latency: WebRTC with OPUS audio codec → 50-100ms end-to-end.
   - Recording: capture from SFU → store in S3 → replayable after.

Q: "How do you implement tweet deletion?"
A: Soft delete: set deleted_at = now() in Cassandra (no actual delete).
   Redis: delete from tweet cache and all timelines? Impossible — too many Redis keys.
   Solution: don't delete from Redis immediately.
   → When timeline is served: filter out deleted tweets (check deleted_at).
   → TTL: tweet cache expires after 1h anyway → deleted tweet gone from cache.
   → Long-term: background job sweeps and hard-deletes from Cassandra after 30 days.
   
   Legal hold: for DMCA/legal requests, tweets may need to be preserved. 
   → Separate archival table before deletion.

Q: "How would you implement Twitter's algorithm (non-chronological feed)?"
A: Ranking model on top of candidate tweets from fan-out.
   Features per tweet:
     - Author's follower count (authority)
     - Tweet engagement rate (likes/views in first hour)
     - User's past interactions with this author
     - Topic match with user's interest graph
     - Time decay (newer is better, but not always)
   
   Two-stage: 
     Stage 1: candidate generation (Redis fan-out → 200 candidates).
     Stage 2: ML ranking model → score 200 → return top 20.
   
   ML model served as gRPC microservice.
   Inference per timeline read: 200 candidates × 20 features = fast enough.
   
   "For you" vs "Following" tabs:
     "Following": strict chronological, no ranking.
     "For you": ML ranked, includes tweets from non-follows (wider candidates).

Q: "How do you handle retweets in the timeline?"
A: Retweet creates a new tweet record referencing original (retweet_of_id = original_tweet_id).
   Fan-out: same as regular tweet — push retweet_id to followers' timelines.
   Display: when hydrating timeline, if tweet has retweet_of_id:
     → Show original tweet content with "Retweeted by @X" header.
   Deduplication: if you follow both @Elon and @Sachdev, and @Sachdev retweets @Elon:
     → Both @Elon's original and @Sachdev's retweet would appear.
     → Fix: LPOS check → if original tweet already in your timeline → skip the retweet.
     → Tradeoff: slightly more complex timeline assembly but better UX.
```


---

## DEEP-DIVE IMPROVEMENT: Twitter's WebSocket Connection Management

```
THE CONNECTION PROBLEM AT SCALE:
  200M DAU. Many using Twitter simultaneously. Each open browser tab = 1 WebSocket.
  Peak: 50M concurrent WebSocket connections.
  
  Why WebSocket vs HTTP polling?
    HTTP polling: client asks "any new tweets?" every 5 seconds.
    50M users × 1 request / 5 seconds = 10M HTTP requests/second just for polling.
    Each request: open TCP, TLS handshake, HTTP request, response, close TCP.
    Cost: 50M × 5 round-trips × 10 bytes overhead = enormous. Plus server work per request.
    
    WebSocket: one persistent connection per user. Server PUSHES new tweets instantly.
    50M connections × 1 connection each = 50M persistent sockets.
    New tweet: server sends immediately. No polling needed.
    Result: 99% reduction in connection overhead. Much lower server cost. Better UX.

WEBSOCKET PROTOCOL DETAILS:
  
  Upgrade handshake (HTTP → WebSocket):
    Client: 
      GET /streaming HTTP/1.1
      Upgrade: websocket
      Connection: Upgrade
      Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==  ← random base64 key
      Sec-WebSocket-Version: 13
    
    Server:
      HTTP/1.1 101 Switching Protocols
      Upgrade: websocket
      Connection: Upgrade
      Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=  ← HMAC of key + magic string
    
    After 101: HTTP connection "upgraded" to WebSocket.
    No more HTTP framing. Raw WebSocket frames instead.
    
  WebSocket frame format:
    FIN bit (1): is this the final frame of a message?
    Opcode (4 bits): 0x1=text, 0x2=binary, 0x8=close, 0x9=ping, 0xA=pong
    Mask bit (1): client→server frames must be masked (XOR with random key)
    Payload length (7-64 bits): variable-length encoding
    Masking key (32 bits): if mask bit set
    Payload data: actual message content (masked or not)
    
  Twitter uses: text frames (JSON messages).
  Alternative: binary frames + Protocol Buffers (3× smaller. Twitter uses for mobile).

CONNECTION SERVER INTERNALS:

  Each Connection Server (CS): handles 1M WebSocket connections.
  Language: Erlang/Elixir (massively concurrent, lightweight processes).
  
  Why Erlang? 
    Erlang's actor model: one "process" (not OS process, much lighter) per connection.
    50M connections → 50M Erlang processes. Memory: ~300 bytes each.
    50M × 300 bytes = 15 GB RAM. Fits on 256 GB server.
    OS threads: 2 MB stack each. 50M × 2 MB = 100 TB. Impossible.
    Erlang's "soft real-time" guarantees: processes never block each other.
    
    Node.js alternative: single-threaded event loop.
    Also handles millions of connections efficiently (non-blocking I/O).
    Twitter's actual implementation: JVM-based (Netty framework for async NIO).
  
  Process per connection (Erlang model):
    Each WebSocket = one lightweight Erlang process.
    Process state: {user_id, conn_id, subscribed_streams, last_heartbeat}.
    Process mailbox: receives messages from fan-out workers, sends to socket.
    
    Fan-out delivery:
      Tweet published → fan-out worker → send Erlang message to each follower's process.
      Erlang message delivery: O(1) per process (message sent to process mailbox).
      50M followers: 50M Erlang message sends. Erlang is optimized for this.
  
  Heartbeat / keepalive:
    Problem: NAT/proxies/firewalls close idle TCP connections (typically 60-300 second timeout).
    Fix: WebSocket ping/pong every 30 seconds.
      Server → client: ping frame (0x9).
      Client → server: pong frame (0xA) within 5s.
      If pong not received: client disconnected → close socket → clean up process.
    
    Twitter's implementation: server pings every 30s. Client must respond within 10s.
    Client-side: if no message received for 45s → reconnect (assume connection dropped).

STREAMING API (Twitter's developer API):
  Twitter exposes streaming API for developers (bots, monitoring tools).
  
  Filtered stream:
    Developer connects to streaming endpoint.
    Server streams all matching tweets in real-time.
    Filter: specific hashtags, users, keywords.
    
    POST /2/tweets/search/stream/rules
    {"add": [{"value": "python OR system design", "tag": "tech tweets"}]}
    
    GET /2/tweets/search/stream
    Connection: upgrade stream to HTTP/2 chunked transfer.
    Server pushes: {"data": {"id": "...", "text": "..."}} as each tweet matches.
    
    Implementation: fan-out workers check tweet against all active stream rules.
    Rule matching: Aho-Corasick algorithm (multi-pattern string matching, O(text_length)).
    Matching tweets: pushed to developer's streaming connection.
    Developer has N streaming connections: server picks their connection via connection registry.

MOBILE PUSH vs WebSocket — WHEN TO USE WHICH:
  
  WebSocket: user has app OPEN in foreground.
    Deliver in real-time (tweets, likes, DMs).
    Battery efficient: one persistent connection vs repeated HTTP.
    Closed when app goes to background (iOS/Android kill background network connections).
  
  FCM / APNs push notifications: app is in background.
    System-level push. Works even when app is closed.
    Payload: small (< 4 KB). Cannot stream large amounts of data.
    Delivery: not guaranteed in real-time (delay up to 10 min in power-save modes).
    Twitter uses for: "X new notifications", "@user mentioned you", "new DM".
    
  Hybrid:
    App opens → establish WebSocket → server knows "user is online."
    App goes to background → WebSocket closes → server switches to FCM/APNs.
    User returns → WebSocket re-established → server switches back.
    Presence service: tracks whether user has active WebSocket → determines delivery method.
```

---

## DEEP-DIVE IMPROVEMENT: Consistent Hashing for Twitter's Distributed Services

```
WHY CONSISTENT HASHING:
  Twitter's Redis Cluster: 16 nodes. Each node owns a range of key space.
  Simple modulo: shard = hash(key) % 16.
  Add node 17: shard = hash(key) % 17. ALL KEYS REMAPPED. 16/17 = 94% of keys now on wrong node.
  Migration: move 94% of data. Weeks of work. Twitter cannot afford this downtime.
  
  Consistent Hashing: adding/removing ONE node → only O(1/N) keys need to move.
  At N=16: add one node → only 6% of keys move. 94% stay on same node.

CONSISTENT HASHING ALGORITHM:

  CONCEPT: hash space is a ring (0 to 2^32, wrapping around).
  
  Step 1: Place nodes on ring.
    For each of 16 Redis nodes: compute hash(node_name) → position on ring.
    Node "redis-01" → hash = 1,023,456,789 (position on the ring).
    Node "redis-02" → hash = 3,567,890,123.
    ... (16 nodes scattered around ring)
  
  Step 2: For each key, find its node.
    Compute hash(key) → position on ring.
    Walk clockwise from position → find FIRST node encountered → that's the owner.
    
    Example: key "timeline:alice" → hash = 2,100,000,000.
    Between redis-01 (1,023,456,789) and redis-02 (3,567,890,123).
    Walking clockwise: reach redis-02 first.
    Owner: redis-02. ✓
  
  Step 3: Add new node (redis-17).
    redis-17 → hash = 2,800,000,000 (lands between redis-01 and redis-02).
    Now: keys with hash between 2,100,000,000 and 2,800,000,000 move from redis-02 to redis-17.
    These keys: only ~6% of redis-02's keys (proportional to arc covered).
    All other nodes: unaffected. ✓

VIRTUAL NODES (vnodes):
  Problem: 16 real nodes on ring → uneven distribution (arcs of different sizes).
  One node might own 30% of ring. Another only 3%. Imbalanced load.
  
  Solution: each physical node has V virtual nodes (V=150 is common).
  16 nodes × 150 vnodes each = 2400 points on ring. Very evenly distributed.
  
  Data: "timeline:alice" → find nearest vnode → look up which physical node owns that vnode.
  Distribution: each physical node owns 2400/16 ≈ 150 vnodes = ~6.25% of key space. Very balanced.
  
  Replication: each key replicated to next N-1 vnodes (not just the owner).
  For N=3 replicas: key stored on 3 consecutive vnodes (3 different physical nodes).
  Guarantees: losing any 2 out of 3 replicas → still can read data. (RF=3, QUORUM = 2)

TWITTER'S REDIS CLUSTER SPECIFICS:
  
  Timeline sharding (fan-out storage):
    Key: "timeline:{user_id}"
    user_id is UUID. hash(user_id) → ring position → node assignment.
    With 16 nodes: each node owns 1/16 = ~12.5M user timelines (at 200M users).
    
  Hot user problem (Elon Musk's timeline key):
    Elon's user_id hashes to one node. That node handles all reads of Elon's timeline.
    But: does Elon's timeline need MORE than one node?
    
    In practice: Elon's timeline is not stored on the ring at all.
    He's a celebrity → fan-out on READ.
    His timeline key doesn't exist → no shard hotspot.
    Fan-out on read: query celeb_timeline:{elon_id} on ONE dedicated "celebrity node."
    PLUS his followers merge at read time. No single hot shard for reads.
  
  REBALANCING PROCEDURE (rolling, zero downtime):
    Step 1: Add new Redis node redis-17. Register in Zookeeper.
    Step 2: Consistent hashing: identify keys moving from redis-02 to redis-17.
    Step 3: Double-write mode: all new writes to redis-02 ALSO written to redis-17.
    Step 4: Migrate existing keys from redis-02 to redis-17 (background process).
    Step 5: Once migration 100% complete: switch reads to redis-17 for its assigned keys.
    Step 6: Remove double-write. redis-02 no longer handles migrated keys.
    
    At no point is there downtime. During migration, reads still served from redis-02.
    The new redis-17 serves reads only after data is fully migrated.
    
    Twitter's migration tools: custom scripts using SCAN + DUMP + RESTORE commands.
    SCAN: iterate keys without blocking. DUMP: serialize key. RESTORE: import on new node.
```

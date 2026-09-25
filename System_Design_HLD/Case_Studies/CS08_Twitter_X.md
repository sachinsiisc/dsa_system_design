# CS08 — Twitter / X at Scale

## Core Requirements

**Functional:**
- Post tweets (text 280 chars, images, videos)
- Follow / unfollow users
- Home timeline: see tweets from people you follow
- Trending topics / hashtags
- Search tweets
- Notifications (likes, retweets, replies, follows)

**Non-functional:**
- 400M users, 200M DAU
- 500M tweets posted/day
- Timeline load < 200ms
- Eventual consistency for feed is acceptable
- High availability — Twitter going down is news
- Global: 190+ countries, multilingual

---

## Scale Estimation

```
Tweet writes:
  500M tweets/day → 5,800 tweets/sec → peak ~30,000/sec

Timeline reads:
  200M DAU × 20 timeline opens/day = 4B reads/day
  4B / 86,400 ≈ 46,000 reads/sec → peak ~250,000/sec
  Read:Write ≈ 8:1

Follower graph:
  Avg user follows 200. 400M users.
  400M × 200 = 80B follower relationships
  Storage: 80B × 16 bytes (user_id pair) = 1.3 TB just for follow graph

Tweet storage:
  500M × 300 bytes (avg tweet + metadata) = 150 GB/day
  Per year: 55 TB/year (text-only)
  With media: ~1 PB/year
```

---

## High-Level Architecture

```
WRITE PATH (Tweet):
User → [API Gateway]
           │
    [Tweet Service]
       │         │
  [Cassandra]  [Kafka: tweet-created]
  (tweets DB)       │
                     ├──► [Fan-out Worker] → Redis timelines
                     ├──► [Search Indexer] → Elasticsearch
                     ├──► [Notification Worker] → push notifications
                     └──► [Media Processor] → S3 + CDN (images/video)

READ PATH (Timeline):
User → [API Gateway]
           │
   [Timeline Service]
           │
   [Redis: timeline:{user_id}]  ← pre-computed list of tweet IDs
           │ (miss or merge needed)
   [Tweet Metadata Cache (Redis)] ← tweet content by ID
           │ (miss)
   [Cassandra: tweets table]
           │
   Return: [{tweet_content, author, like_count, ...}, ...]
```

---

## Deep-Dive 1: Timeline Fan-out Architecture

### The Core Problem

```
User A has 50M followers (e.g., Elon Musk).
A tweets.
Naive approach: 50M Redis LPUSH operations = massive write spike.
At 10K writes/sec: takes 5,000 SECONDS to fan out one tweet.
```

### Twitter's Hybrid Fan-out Strategy

```
RULE:
  Regular users  (< 10,000 followers)  → Fan-out on WRITE
  Celebrity users (> 10,000 followers) → Fan-out on READ

FAN-OUT ON WRITE (regular user):
  When @RegularUser posts:
    followers = db.get_followers("regular_user")  # 500 followers
    for follower_id in followers:
        redis.lpush(f"timeline:{follower_id}", tweet_id)
        redis.ltrim(f"timeline:{follower_id}", 0, 799)  # keep 800 tweets
    # 500 Redis writes → done in milliseconds

FAN-OUT ON READ (celebrity):
  @CelebrityUser's tweets NOT pre-pushed to followers' timelines.
  When you open your timeline:
    my_timeline = redis.lrange(f"timeline:{me}", 0, 19)       # from fan-out-on-write
    celebrities_i_follow = get_celebrities_i_follow(me)
    for celeb in celebrities_i_follow:
        celeb_tweets = redis.lrange(f"timeline:celeb:{celeb}", 0, 19)  # separate per-celeb cache
        # Celebrities have their OWN dedicated timeline cache (small)
    merged = merge_by_timestamp(my_timeline, celeb_tweets)[:20]
    return merged

IMPLEMENTATION:
```

```python
class TimelineService:
    def __init__(self, redis, cassandra, user_service):
        self.redis = redis
        self.cassandra = cassandra
        self.user_service = user_service
        self.CELEBRITY_THRESHOLD = 10_000
        self.MAX_TIMELINE_SIZE = 800

    # ── WRITE PATH ────────────────────────────────────────────────────────────
    def on_tweet_created(self, tweet_id: str, author_id: str):
        """Fan-out worker: called asynchronously after Kafka event."""
        author = self.user_service.get_user(author_id)
        followers = self.user_service.get_followers(author_id)

        if author.follower_count < self.CELEBRITY_THRESHOLD:
            # Fan-out on write
            self._fanout_write(tweet_id, followers)
        else:
            # Celebrity: only update their own cache (not all followers)
            self.redis.lpush(f"celeb_timeline:{author_id}", tweet_id)
            self.redis.ltrim(f"celeb_timeline:{author_id}", 0, 199)

    def _fanout_write(self, tweet_id: str, follower_ids: list):
        pipeline = self.redis.pipeline()   # batch commands
        for fid in follower_ids:
            pipeline.lpush(f"timeline:{fid}", tweet_id)
            pipeline.ltrim(f"timeline:{fid}", 0, self.MAX_TIMELINE_SIZE - 1)
        pipeline.execute()  # single round-trip to Redis

    # ── READ PATH ─────────────────────────────────────────────────────────────
    def get_home_timeline(self, user_id: str, count: int = 20) -> list[dict]:
        # Step 1: Get pre-computed timeline (regular users)
        tweet_ids = self.redis.lrange(f"timeline:{user_id}", 0, 99)

        # Step 2: Merge in celebrity tweets
        celeb_ids = self.user_service.get_celebrity_follows(user_id)
        celeb_tweet_ids = []
        for cid in celeb_ids:
            celeb_tweet_ids.extend(
                self.redis.lrange(f"celeb_timeline:{cid}", 0, 19)
            )

        # Step 3: Merge and sort by timestamp (tweet_id is time-sorted ULID)
        all_ids = sorted(set(tweet_ids + celeb_tweet_ids), reverse=True)[:count]

        # Step 4: Hydrate tweet IDs → full tweet data
        return self._hydrate(all_ids)

    def _hydrate(self, tweet_ids: list) -> list[dict]:
        """Fetch tweet content. Check Redis cache first, fallback to Cassandra."""
        result = []
        for tid in tweet_ids:
            # Try Redis tweet cache
            tweet_json = self.redis.get(f"tweet:{tid}")
            if tweet_json:
                result.append(json.loads(tweet_json))
            else:
                # Fallback to Cassandra
                tweet = self.cassandra.get_tweet(tid)
                if tweet:
                    self.redis.setex(f"tweet:{tid}", 3600, json.dumps(tweet))
                    result.append(tweet)
        return result
```

---

## Deep-Dive 2: Tweet Storage (Cassandra)

```sql
-- Primary tweets table
CREATE TABLE tweets (
    tweet_id     TIMEUUID,         -- time-ordered UUID (sorting for free)
    author_id    UUID,
    content      TEXT,
    media_urls   LIST<TEXT>,
    reply_to     UUID,             -- null if original tweet
    retweet_of   UUID,             -- null if not a retweet
    like_count   COUNTER,          -- Cassandra counter column
    retweet_count COUNTER,
    created_at   TIMESTAMP,
    PRIMARY KEY (tweet_id)
);

-- For fetching a user's own tweets (profile page)
CREATE TABLE user_tweets (
    author_id    UUID,
    tweet_id     TIMEUUID,
    PRIMARY KEY (author_id, tweet_id)
) WITH CLUSTERING ORDER BY (tweet_id DESC);

-- WHY CASSANDRA:
-- Partition by tweet_id → each tweet on one node.
-- TIMEUUID → time-ordered → range queries by time work naturally.
-- Counter columns → like_count increments without read-modify-write.
-- Write-optimized → 500M tweets/day is extremely write-heavy.
-- Linear horizontal scaling → add nodes to increase write throughput.
```

---

## Deep-Dive 3: Trending Topics

```python
# Approach: Sliding window count with Redis sorted set

class TrendingService:
    WINDOWS = {
        "1h":  3600,
        "24h": 86400,
    }

    def on_tweet_created(self, tweet_id: str, hashtags: list[str], timestamp: int):
        """Called from Kafka consumer for every new tweet."""
        for tag in hashtags:
            for window_name, window_secs in self.WINDOWS.items():
                # Bucket by minute for efficiency
                minute_bucket = timestamp // 60
                key = f"trending:{window_name}:{minute_bucket}"

                self.redis.zincrby(key, 1, tag)   # increment score
                self.redis.expire(key, window_secs + 300)  # auto-expire

    def get_trending(self, window: str = "1h", count: int = 10) -> list[tuple]:
        """Merge last N minute buckets and return top K hashtags."""
        now = int(time.time())
        window_secs = self.WINDOWS[window]
        buckets = [
            f"trending:{window}:{now // 60 - i}"
            for i in range(window_secs // 60)
        ]
        # ZUNIONSTORE: merge all bucket sorted sets into a temporary key
        temp_key = f"trending_union:{window}:{now // 60}"
        self.redis.zunionstore(temp_key, buckets)
        self.redis.expire(temp_key, 300)  # cache result for 5 min

        # Get top K by score (highest tweet count)
        return self.redis.zrevrange(temp_key, 0, count - 1, withscores=True)

# Returns: [("AI", 142000), ("WorldCup", 98000), ("#Python", 45000), ...]
# Recomputed at most every 5 minutes. Fast enough for "trending".
```

---

## Deep-Dive 4: Notification System

```
Events that trigger notifications:
  Like        → notify tweet author
  Retweet     → notify tweet author
  Reply       → notify tweet author
  Follow      → notify followed user
  Mention     → notify @mentioned user

Architecture:
  Event → Kafka → Notification Worker → Notification Store (Cassandra)
                                      → Push Dispatcher (APNs / FCM)

Push paths:
  iOS  → APNs (Apple Push Notification Service)
  Android → FCM (Firebase Cloud Messaging)
  Web  → WebSocket or Web Push API

Notification table (Cassandra):
  CREATE TABLE notifications (
      user_id     UUID,             -- recipient
      notif_id    TIMEUUID,
      type        TEXT,             -- LIKE, RETWEET, FOLLOW, MENTION
      actor_id    UUID,             -- who did the action
      tweet_id    UUID,             -- target tweet (nullable)
      read        BOOLEAN,
      PRIMARY KEY (user_id, notif_id)
  ) WITH CLUSTERING ORDER BY (notif_id DESC);

  Partition = all notifications for one user → single-node fetch.
  Latest first → most recent 20 in one disk read.
```

---

## Search Architecture

```
Full-text search on 500M tweets/day:

APPROACH: Elasticsearch
  On tweet creation → Kafka → Search Indexer → Elasticsearch index tweet

Index document:
  {
    "tweet_id": "abc123",
    "text":     "Python is amazing for system design",
    "author":   "sachdev",
    "created_at": "2026-09-21T08:00:00Z",
    "hashtags": ["Python", "systemdesign"],
    "like_count": 42
  }

Query: "python system design" →
  Elasticsearch:
    - Full-text match on `text` field
    - Boost by: recency + like_count + author_follower_count
    - Return top 20 results in < 50ms

Sharding: Elasticsearch shards by tweet_id range.
Retention: Recent tweets (30 days) in hot shards (SSD).
            Older tweets in cold shards (HDD). Older than 1 year: archive only.

Scale:
  500M tweets/day × 300 bytes = 150 GB/day indexing.
  Twitter runs thousands of Elasticsearch nodes.
```

---

## Key Numbers

| Metric | Value |
|--------|-------|
| Tweets/day | 500M |
| Timeline reads/sec | 250,000 (peak) |
| Cassandra write throughput | 30,000 tweets/sec |
| Redis timeline size | 800 tweet IDs/user |
| Fan-out latency (regular) | < 5 seconds |
| Celebrity threshold | 10,000 followers |
| Search index lag | ~30 seconds |

---

## Interview Focus Points

1. **Fan-out on write vs read** — why the hybrid approach. Celebrity threshold.
2. **Timeline is pre-computed** — stored in Redis as sorted tweet IDs. Hydration is separate.
3. **Cassandra for tweets** — why (write-heavy, TIMEUUID, linear scaling). Not MySQL.
4. **Trending via Redis sorted set** — sliding window with minute buckets.
5. **Notifications via Kafka** — async, decoupled. APNs/FCM for mobile push.
6. **Search via Elasticsearch** — not Cassandra (Cassandra can't full-text search).
7. **Trade-off: eventual consistency** — feed freshness vs system cost.

---

## Trade-offs

```
Trade-off 1: Fan-out amplification
  Celebrity with 50M followers posts → 50M Redis writes if fan-out on write.
  Fix: celebrity fan-out on read. But: timeline read is slower (merge needed).
  Decision: merge of 5 celebrity feeds + 1 personal feed = fast enough.

Trade-off 2: Feed freshness vs pre-computation
  Pre-computed feed = fast reads. But: stale by seconds.
  If user unfollows someone → their tweets still in your Redis feed for seconds.
  Fix: TTL on timeline cache. Re-fetch on explicit refresh. Acceptable.

Trade-off 3: Like count consistency
  Cassandra COUNTER columns = eventual consistency (no locking).
  Like count may be off by a few for milliseconds.
  Alternative: Redis counter → sync to Cassandra async.
  Decision: ±1 like display accuracy is perfectly fine for a social network.
```

# CS08: LLD — Twitter / X
## Social Media Feed | Every Line Explained | Python + Java + C++

---

> **WHAT WE'RE BUILDING:**
> Twitter's core: posting tweets, following users, and generating the home feed.
>
> **THE CORE ENGINEERING CHALLENGE — The Fanout Problem:**
> When a celebrity with 100M followers tweets, who gets the tweet in their feed?
> PUSH model: write tweet to all 100M followers' timelines → 100M writes in < 5 seconds.
> PULL model: on each visit, fetch tweets from all followed users → expensive per read.
> Twitter uses a HYBRID: push for normal users, pull for celebrities (> 1M followers).

---

## STEP 1 — Requirements & Entities

```
FUNCTIONAL REQUIREMENTS:
  1. Post a tweet (text, images, videos, polls — we cover text)
  2. Reply to a tweet
  3. Retweet (with or without comment)
  4. Like a tweet
  5. Follow / Unfollow a user
  6. Home timeline (tweets from followed users + recommendations)
  7. User profile timeline (all tweets by a user)
  8. Search tweets by hashtag or keyword
  9. Trending topics (what's hot right now — by volume in last hour)
  10. Notifications (new follower, reply, like, retweet)
  11. Direct Messages (DMs) — briefly described

KEY ENTITIES:
  User          — registered account with profile
  Tweet         — 280-character post (can be original, reply, or retweet)
  TweetType     — ORIGINAL, REPLY, RETWEET, QUOTE_TWEET
  Follow        — directional relationship (User A follows User B)
  Like          — thumbs up on a tweet
  Hashtag       — #tag → index for topic-based search
  Timeline      — per-user ordered list of tweets for home feed
  FanoutService — distributes new tweets to followers' timelines
  TrendingService — tracks hashtag/keyword volume over time windows
  NotificationService — sends push/email/in-app notifications

NON-FUNCTIONAL:
  500M tweets/day = ~5800 tweets/sec
  1B daily active users → 1B home timeline loads/day
  Post tweet: < 5 seconds to appear in followers' feeds
  Timeline load: < 200ms
  Trending topics: updated every 5 minutes
```

---

## STEP 2 — Class Diagram

```
[User]                        [Tweet]                     [TweetType]
──────                        ───────                     ───────────
- id: UUID                    - id: UUID                  ORIGINAL
- username: str               - author: User              REPLY
- display_name: str           - content: str (≤280 chars) RETWEET
- bio: str                    - type: TweetType           QUOTE_TWEET
- follower_count: int         - parent_tweet: Tweet?
- following_count: int        - liked_by: Set[user_id]    [Like]
- is_verified: bool           - like_count: int           ──────
- created_at: datetime        - retweet_count: int        - user_id: str
──────                        - reply_count: int          - tweet_id: str
+ post_tweet(): Tweet         - hashtags: List[str]       - created_at: datetime
+ retweet(): Tweet            - view_count: int
+ like(): void                - is_deleted: bool          [Timeline]
+ follow(User): Follow        - created_at: datetime      ─────────
+ unfollow(User): void        ───────                     - user_id: str
                              + get_age(): str            - tweets: List[Tweet]
[Follow]                      + is_visible(): bool        (ordered: newest first)
────────                                                  - last_refreshed: datetime
- follower: User              [Hashtag]
- following: User             ─────────
- followed_at: datetime       - tag: str (without #)
                              - tweets: List[Tweet]       [Notification]
[Trending]                    - tweet_count: int          ─────────────
─────────                     ─────────                   - recipient: User
- hashtag: str                + add_tweet(): void         - sender: User
- volume_1h: int                                          - type: NotificationType
- volume_24h: int                                         - tweet: Tweet?
- rank: int                                               - is_read: bool

PATTERNS:
  Observer    → FanoutService (tweet published → propagate to followers' timelines)
  Strategy    → TimelineBuildStrategy (push for normal users, pull for celebrities)
  State       → Tweet.is_deleted (soft delete preserves reply threads)
  CQRS        → Write path (post tweet, like) separate from Read path (timeline, search)
  Composite   → Tweet tree (tweet → replies → replies of replies)
  Builder     → TweetBuilder for constructing complex tweets (media, polls, tags)
```

---

## STEP 3 — Python Implementation (Every Line Explained)

```python
# twitter_lld.py
from __future__ import annotations

import re
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Callable


# ══════════════════════════════════════════════════════════════════════════════
# ENUMS
# ══════════════════════════════════════════════════════════════════════════════

class TweetType(Enum):
    """
    A tweet can be:
    ORIGINAL:     New tweet from scratch.
    REPLY:        Response to another tweet (has parent_tweet).
    RETWEET:      Share another tweet unchanged (has parent_tweet, no added content).
    QUOTE_TWEET:  Share another tweet + add your own comment.
    """
    ORIGINAL    = "original"
    REPLY       = "reply"
    RETWEET     = "retweet"
    QUOTE_TWEET = "quote_tweet"

class NotificationType(Enum):
    NEW_FOLLOWER = "new_follower"    # Someone followed you
    LIKE         = "like"           # Someone liked your tweet
    RETWEET      = "retweet"        # Someone retweeted you
    REPLY        = "reply"          # Someone replied to your tweet
    MENTION      = "mention"        # Someone @mentioned you
    DM           = "dm"             # New direct message


# ══════════════════════════════════════════════════════════════════════════════
# TWEET
# ══════════════════════════════════════════════════════════════════════════════

class Tweet:
    """
    A tweet — the fundamental unit of Twitter.
    
    IMMUTABLE CONTENT: Once posted, tweet text cannot be changed (Twitter policy).
    You can only DELETE and repost. This is a design decision — preserves accountability.
    
    SOFT DELETE: Deleting a tweet sets is_deleted=True.
    The record stays in DB because:
    1. Replies reference this tweet → they'd have broken parent references if hard-deleted.
    2. Analytics and moderation require history.
    3. GDPR: user can request actual data deletion later (separate process).
    """

    MAX_CHARS = 280   # Twitter's 280-character limit (was 140 before Nov 2017)

    def __init__(self, author: User, content: str,
                 tweet_type: TweetType = TweetType.ORIGINAL,
                 parent_tweet: Optional[Tweet] = None):
        
        # Validate tweet length
        if len(content) > self.MAX_CHARS:
            raise ValueError(
                f"Tweet exceeds {self.MAX_CHARS} characters "
                f"(got {len(content)})"
            )

        self.id            = str(uuid.uuid4())
        self.author        = author
        self.content       = content
        self.type          = tweet_type
        self.parent_tweet  = parent_tweet   # For REPLY, RETWEET, QUOTE_TWEET

        # Extract hashtags from content automatically
        self.hashtags: List[str] = self._extract_hashtags(content)
        # Example: "Loving #Python and #LLD today!" → ["python", "lld"]

        # Extract @mentions from content
        self.mentions: List[str] = self._extract_mentions(content)
        # Example: "@sachin great work!" → ["sachin"]

        # Engagement metrics (atomic: modified by multiple threads)
        self._like_count:    int = 0
        self._retweet_count: int = 0
        self._reply_count:   int = 0
        self._view_count:    int = 0
        self._liked_by:      Set[str] = set()   # Set of user_ids (deduplication)
        self._retweeted_by:  Set[str] = set()

        self.created_at    = datetime.utcnow()
        self._is_deleted   = False
        self._lock         = threading.RLock()

    def _extract_hashtags(self, content: str) -> List[str]:
        """
        Find all hashtags in tweet content.
        
        re.findall(pattern, string):
        Returns ALL matches of pattern in string as a list.
        
        Pattern r'#(\w+)':
        #   → literal hash character
        \w  → word character: [a-zA-Z0-9_]
        +   → one or more
        ()  → capture group: what's INSIDE the parentheses is captured
              (not the # itself, just the tag text)
        
        "Loving #Python and #LLD today!" → ["Python", "LLD"]
        .lower() on each → ["python", "lld"]
        """
        tags = re.findall(r'#(\w+)', content)
        return [t.lower() for t in tags]

    def _extract_mentions(self, content: str) -> List[str]:
        """
        Find all @mentions in tweet content.
        Pattern r'@(\w+)': same as hashtags but with @ instead of #.
        "@sachin great work!" → ["sachin"]
        """
        mentions = re.findall(r'@(\w+)', content)
        return [m.lower() for m in mentions]

    def like(self, user: User) -> bool:
        """
        Like this tweet. Returns True if like added, False if already liked.
        
        WHY SET for liked_by?
        Set guarantees uniqueness: adding the same user_id twice has no effect.
        O(1) add and "in" check (hash-based).
        """
        with self._lock:
            if user.id in self._liked_by:
                return False   # Already liked — no duplicate likes

            self._liked_by.add(user.id)
            self._like_count += 1
            return True

    def unlike(self, user: User) -> bool:
        """Remove a like. Returns True if unlike happened, False if wasn't liked."""
        with self._lock:
            if user.id not in self._liked_by:
                return False
            self._liked_by.discard(user.id)
            # discard: like remove, but doesn't raise error if not present (safe)
            self._like_count -= 1
            return True

    def record_retweet(self, user: User) -> bool:
        """Record that this tweet was retweeted."""
        with self._lock:
            if user.id in self._retweeted_by:
                return False
            self._retweeted_by.add(user.id)
            self._retweet_count += 1
            return True

    def increment_reply_count(self) -> None:
        with self._lock:
            self._reply_count += 1

    def increment_view(self) -> None:
        with self._lock:
            self._view_count += 1

    def delete(self) -> None:
        """Soft delete this tweet."""
        with self._lock:
            self._is_deleted = True
            self.content     = "[This tweet was deleted]"
            # Replace content with placeholder (GDPR compliance: data minimization)
            # But keep the record (for reply threads).

    def get_age_str(self) -> str:
        """Human-readable age: "2m", "3h", "5d"."""
        delta = datetime.utcnow() - self.created_at
        # timedelta: represents a duration.
        # datetime.utcnow() - self.created_at = timedelta since creation

        if delta.seconds < 60:              return f"{delta.seconds}s"
        if delta.seconds < 3600:           return f"{delta.seconds // 60}m"
        if delta.total_seconds() < 86400:  return f"{int(delta.total_seconds() // 3600)}h"
        return f"{delta.days}d"
        # 86400 = 60 seconds × 60 minutes × 24 hours = seconds in a day

    def is_visible(self) -> bool:
        """Can this tweet be shown to users?"""
        return not self._is_deleted

    @property
    def like_count(self) -> int:
        with self._lock: return self._like_count

    @property
    def retweet_count(self) -> int:
        with self._lock: return self._retweet_count

    @property
    def reply_count(self) -> int:
        with self._lock: return self._reply_count

    @property
    def is_deleted(self) -> bool:
        with self._lock: return self._is_deleted

    def __repr__(self) -> str:
        return f"Tweet(@{self.author.username}: {self.content[:50]!r})"


# ══════════════════════════════════════════════════════════════════════════════
# USER
# ══════════════════════════════════════════════════════════════════════════════

class User:
    """
    A Twitter/X user account.
    
    FOLLOW GRAPH:
    Twitter is a DIRECTED graph: A follows B ≠ B follows A.
    (Facebook: undirected — both must accept before being "friends")
    
    Storage:
    - self._following: Set of user_ids this user follows (outbound edges)
    - self._followers: Set of user_ids that follow this user (inbound edges)
    
    WHY SET not List?
    1. O(1) lookup: "does user X follow user Y?" → O(1) with set, O(n) with list.
    2. Uniqueness: can't follow same user twice.
    3. Efficient unfollow: O(1) set.remove() vs O(n) list.remove().
    
    SCALE PROBLEM:
    Katy Perry: 100M followers. Her User object's _followers set = 100M items.
    That's ~800MB for a single user in memory.
    In production: followers stored in Redis sorted sets (disk-backed, not RAM only).
    Follower count stored separately as an integer (no need to load all followers to get count).
    """

    CELEBRITY_THRESHOLD = 1_000_000   # Users with > 1M followers get special handling

    def __init__(self, username: str, display_name: str):
        self.id           = str(uuid.uuid4())
        self.username     = username.lower().strip()   # Always lowercase: "@Sachin" → "sachin"
        self.display_name = display_name
        self.bio          = ""
        self.is_verified  = False
        self.created_at   = datetime.utcnow()

        self._following:      Set[str] = set()   # User IDs this user follows
        self._followers:      Set[str] = set()   # User IDs that follow this user
        self._follower_count: int = 0
        self._following_count: int = 0
        self._lock = threading.RLock()

    def follow(self, other: User) -> bool:
        """
        Follow another user.
        Returns True if follow added, False if already following.
        
        BIDIRECTIONAL UPDATE:
        Must update BOTH users' data:
        - self._following.add(other.id)    (self's outbound edges)
        - other._followers.add(self.id)    (other's inbound edges)
        
        DEADLOCK RISK:
        Thread 1: A.follow(B) — locks A, then tries to lock B
        Thread 2: B.follow(A) — locks B, then tries to lock A
        Result: deadlock!
        
        SOLUTION: Always acquire locks in consistent order.
        Lock user with smaller id first.
        """
        if self.id == other.id:
            raise ValueError("Cannot follow yourself")

        # Consistent lock ordering (smaller ID first) to prevent deadlock
        first, second = sorted([self, other], key=lambda u: u.id)
        with first._lock:
            with second._lock:
                if other.id in self._following:
                    return False   # Already following
                self._following.add(other.id)
                self._following_count += 1
                other._followers.add(self.id)
                other._follower_count += 1
        return True

    def unfollow(self, other: User) -> bool:
        """Unfollow another user."""
        first, second = sorted([self, other], key=lambda u: u.id)
        with first._lock:
            with second._lock:
                if other.id not in self._following:
                    return False
                self._following.discard(other.id)
                self._following_count -= 1
                other._followers.discard(self.id)
                other._follower_count -= 1
        return True

    def is_following(self, other: User) -> bool:
        """Does this user follow 'other'?"""
        with self._lock:
            return other.id in self._following

    def is_celebrity(self) -> bool:
        """Is this user's follower count above celebrity threshold?"""
        with self._lock:
            return self._follower_count >= self.CELEBRITY_THRESHOLD

    def get_followers(self) -> Set[str]:
        with self._lock: return set(self._followers)   # Return copy

    def get_following(self) -> Set[str]:
        with self._lock: return set(self._following)

    @property
    def follower_count(self) -> int:
        with self._lock: return self._follower_count

    @property
    def following_count(self) -> int:
        with self._lock: return self._following_count

    def __repr__(self) -> str:
        return f"User(@{self.username}, followers={self._follower_count})"


# ══════════════════════════════════════════════════════════════════════════════
# TIMELINE — Redis Sorted Set simulation
# ══════════════════════════════════════════════════════════════════════════════

class Timeline:
    """
    A user's home timeline: ordered list of tweets from followed users.
    
    REAL TWITTER:
    Implemented as Redis Sorted Set.
    
    REDIS SORTED SET:
    A data structure that stores (score, member) pairs.
    Always sorted by score (ascending). O(log N) insertion.
    
    For Twitter timeline:
    - score = tweet creation timestamp (unix timestamp)
    - member = tweet_id
    
    ZADD timeline:user_123 {timestamp} {tweet_id}  → insert tweet
    ZREVRANGE timeline:user_123 0 49               → get latest 50 tweets
    
    WHY SORTED SET?
    - New tweet appended: ZADD is O(log N)
    - Fetch timeline: ZREVRANGE is O(K) where K = tweets returned
    - Trim old tweets: ZREMRANGEBYRANK timeline:user 0 -5001 → keep latest 5000
    
    Timeline is MATERIALIZED (pre-built) — not computed at read time.
    This makes reads VERY fast at the cost of more writes (fanout).
    """

    MAX_SIZE = 5000   # Keep at most 5000 tweets per user's timeline

    def __init__(self, user_id: str):
        self.user_id = user_id
        # deque: O(1) append to right + O(1) pop from left
        # maxlen=MAX_SIZE: automatically removes oldest when at capacity
        self._tweets: deque[Tweet] = deque(maxlen=self.MAX_SIZE)
        # deque(maxlen=N): AUTOMATIC TRIMMING.
        # When you append beyond maxlen, the leftmost (oldest) is auto-removed.
        # No explicit trim needed — extremely efficient.
        self._lock   = threading.RLock()

    def add_tweet(self, tweet: Tweet) -> None:
        """
        Add a tweet to this timeline.
        Called by FanoutService when a followed user posts.
        """
        with self._lock:
            self._tweets.append(tweet)
            # Appends to RIGHT (newest end). Oldest are auto-removed from LEFT if at maxlen.

    def get_tweets(self, limit: int = 50, offset: int = 0) -> List[Tweet]:
        """
        Get latest tweets for this user's feed.
        
        PAGINATION: offset + limit allows loading more tweets ("Load more" button).
        Offset 0: first page (newest 50). Offset 50: second page (next 50), etc.
        
        We return newest first (reversed).
        """
        with self._lock:
            # Convert deque to list (needed for slicing)
            all_tweets = list(self._tweets)
            # deque doesn't support slicing directly → convert to list first
            
            # Reverse: newest first (deque appends to right = newest at right)
            all_tweets.reverse()
            # .reverse() modifies in-place. Now newest is at index 0.
            
            # Filter deleted tweets
            visible = [t for t in all_tweets if t.is_visible()]
            
            return visible[offset: offset + limit]
            # Slice: [offset: offset+limit] = elements from 'offset' to 'offset+limit-1'
            # offset=0, limit=50: [0:50] = first 50 elements

    def size(self) -> int:
        with self._lock: return len(self._tweets)


# ══════════════════════════════════════════════════════════════════════════════
# FANOUT SERVICE — Observer Pattern + Strategy
# ══════════════════════════════════════════════════════════════════════════════

class FanoutService:
    """
    When a user posts a tweet, DISTRIBUTE it to all their followers' timelines.
    
    FANOUT = One tweet "fans out" to N followers.
    
    THE CELEBRITY PROBLEM:
    Normal user: 500 followers → 500 timeline writes. Fine.
    Celebrity: 100M followers → 100M timeline writes in 5 seconds. IMPOSSIBLE synchronously.
    
    SOLUTION: HYBRID FANOUT
    
    PUSH (for normal users, < 1M followers):
    Post tweet → immediately write to all followers' Redis timelines.
    Followers see it fast. Write amplification: tweet × follower_count writes.
    
    PULL (for celebrities, > 1M followers):
    DON'T write to followers' timelines.
    When follower loads their timeline: fetch celebrity tweets separately.
    Then MERGE: follower's push-based timeline + celebrity's pull timeline.
    Higher read cost, but avoids 100M writes per celebrity tweet.
    
    REAL TWITTER:
    Actually uses push for everyone < some threshold + lazy pull merge at read time.
    Active users' timelines are pre-built (push). Inactive users: rebuild lazily on login.
    """

    def __init__(self):
        # user_id → Timeline
        self._timelines: Dict[str, Timeline] = {}
        self._lock = threading.RLock()

    def get_or_create_timeline(self, user_id: str) -> Timeline:
        """Get a user's timeline, creating it if it doesn't exist."""
        with self._lock:
            if user_id not in self._timelines:
                self._timelines[user_id] = Timeline(user_id)
            return self._timelines[user_id]

    def fanout_push(self, tweet: Tweet, followers: Set[str]) -> int:
        """
        PUSH FANOUT: write tweet to all followers' timelines.
        
        In production: done ASYNCHRONOUSLY via Kafka.
        1. Post tweet → publish to Kafka topic "new_tweets"
        2. Fanout workers consume from Kafka → write to Redis timelines
        3. Workers auto-scale based on Kafka lag
        
        WHY KAFKA?
        - Celebrity tweets would block API response for 30+ seconds if done synchronously
        - Kafka decouples: tweet is committed in < 10ms, fanout happens in background
        - If fanout workers fail/restart: Kafka retains the message → no tweet lost
        
        RETURNS: number of timelines written to.
        """
        count = 0
        for follower_id in followers:
            timeline = self.get_or_create_timeline(follower_id)
            timeline.add_tweet(tweet)
            count += 1
        return count

    def get_celebrity_tweets(self, celebrity: User,
                             count: int = 20) -> List[Tweet]:
        """
        PULL: Fetch recent tweets from a celebrity.
        Called at timeline READ time for users who follow celebrities.
        Returns the celebrity's recent tweets to merge into the follower's feed.
        """
        celebrity_timeline = self.get_or_create_timeline(celebrity.id)
        return celebrity_timeline.get_tweets(limit=count)
        # The celebrity's OWN timeline always has their tweets (self-fanout)

    def get_user_timeline(self, user: User, limit: int = 50) -> List[Tweet]:
        """
        Read a user's timeline.
        Merge: pre-built push timeline + celebrity pull tweets.
        """
        timeline = self.get_or_create_timeline(user.id)
        return timeline.get_tweets(limit=limit)

    def add_to_own_timeline(self, tweet: Tweet) -> None:
        """Every tweet is added to the author's own timeline too (for their profile page)."""
        timeline = self.get_or_create_timeline(tweet.author.id)
        timeline.add_tweet(tweet)


# ══════════════════════════════════════════════════════════════════════════════
# TRENDING SERVICE
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class TrendingTopic:
    """A currently trending hashtag or topic."""
    tag:        str     # "#python" or "Python" (without #)
    volume_1h:  int     # Tweets in last hour
    rank:       int     # Rank (1 = most trending)


class TrendingService:
    """
    Tracks trending hashtags over time windows.
    
    REAL TWITTER:
    Uses a SLIDING WINDOW algorithm.
    Every tweet → extract hashtags → INCR in Redis with 1-hour expiry.
    Redis key: trending:{hashtag}:{window_bucket}
    
    Every 5 minutes: query Redis for top-K keys → trending topics.
    
    WHY SLIDING WINDOW vs simple count?
    Simple count: total ever. "#python" has 10M tweets all-time. Not useful.
    Sliding window (last 1 hour): "#WorldCup2026" suddenly has 50K tweets/hour → trending.
    Shows VELOCITY (rate of growth), not just total volume.
    
    WE SIMULATE: maintain a deque of (hashtag, timestamp) entries.
    Count entries in last hour → top-K = trending.
    """

    def __init__(self, window_hours: int = 1, top_k: int = 10):
        self._window        = timedelta(hours=window_hours)
        # timedelta: represents a duration. hours=1 → 1 hour duration.
        self._top_k         = top_k     # Show top 10 trending topics
        
        # hashtag → deque of timestamps (when each tweet with this tag was posted)
        self._events: Dict[str, deque] = defaultdict(deque)
        # defaultdict(deque): if key doesn't exist, create empty deque automatically
        
        self._lock = threading.RLock()

    def record_tweet(self, tweet: Tweet) -> None:
        """Record a tweet's hashtags for trending calculation."""
        now = datetime.utcnow()
        with self._lock:
            for tag in tweet.hashtags:
                self._events[tag].append(now)
                # O(1): append to deque right end
                # We'll prune old events lazily when computing trends

    def get_trending(self) -> List[TrendingTopic]:
        """
        Get current top-K trending topics.
        
        ALGORITHM:
        1. For each hashtag: count events in the last window_hours.
        2. Prune events older than window (lazy cleanup).
        3. Sort by count descending → top-K.
        """
        now = datetime.utcnow()
        cutoff = now - self._window   # Timestamps before this are "too old"
        
        tag_counts: Dict[str, int] = {}
        
        with self._lock:
            for tag, timestamps in self._events.items():
                # Remove old events from the LEFT (oldest end) of deque
                while timestamps and timestamps[0] < cutoff:
                    timestamps.popleft()
                    # popleft(): O(1). Remove oldest timestamp.
                    # Stop when the oldest remaining timestamp is within our window.
                
                count = len(timestamps)
                if count > 0:
                    tag_counts[tag] = count

        # Sort by count descending
        sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
        # .items(): returns (key, value) pairs
        # sorted(..., key=lambda x: x[1]): sort by value (count), not key (tag)
        # reverse=True: descending (highest count first)

        trending = []
        for rank, (tag, volume) in enumerate(sorted_tags[:self._top_k], start=1):
            # enumerate(iterable, start=1): gives (rank, item) starting from 1
            trending.append(TrendingTopic(tag=f"#{tag}", volume_1h=volume, rank=rank))

        return trending


# ══════════════════════════════════════════════════════════════════════════════
# NOTIFICATION SERVICE — Observer Pattern
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Notification:
    """A notification sent to a user."""
    recipient:    User
    sender:       User
    notif_type:   NotificationType
    tweet:        Optional[Tweet] = None
    message:      str = ""
    is_read:      bool = False
    created_at:   datetime = field(default_factory=datetime.utcnow)


class NotificationService:
    """
    OBSERVER PATTERN:
    Users are "observers" of events (follows, likes, retweets, replies).
    NotificationService stores and delivers notifications.
    
    IN PRODUCTION:
    - Push notifications: FCM (Android), APNs (iOS)
    - Email: SendGrid / Mailgun
    - In-app: WebSocket connection or long-polling
    - SMS: Twilio
    
    Notification flow (async):
    Event (like) → Kafka topic "user_events" → Notification consumer
    → Fan out to push/email/in-app based on user preferences
    """

    def __init__(self):
        # user_id → List of notifications (ordered: newest first)
        self._inbox: Dict[str, List[Notification]] = defaultdict(list)
        self._lock  = threading.RLock()

    def notify(self, recipient: User, sender: User,
               notif_type: NotificationType,
               tweet: Optional[Tweet] = None) -> Notification:
        """Create and store a notification."""
        # Generate human-readable message
        messages = {
            NotificationType.NEW_FOLLOWER: f"@{sender.username} followed you",
            NotificationType.LIKE:         f"@{sender.username} liked your tweet",
            NotificationType.RETWEET:      f"@{sender.username} retweeted your tweet",
            NotificationType.REPLY:        f"@{sender.username} replied to your tweet",
            NotificationType.MENTION:      f"@{sender.username} mentioned you in a tweet",
        }
        message = messages.get(notif_type, "New notification")

        notif = Notification(
            recipient=recipient,
            sender=sender,
            notif_type=notif_type,
            tweet=tweet,
            message=message
        )
        with self._lock:
            self._inbox[recipient.id].insert(0, notif)
            # insert(0, item): add at position 0 (beginning of list) → O(n).
            # In production: Redis List with LPUSH (O(1)).
            # Here: Python list is fine for demo.

        print(f"🔔 Notification: {message}")
        return notif

    def get_notifications(self, user: User, limit: int = 20) -> List[Notification]:
        """Get user's latest notifications."""
        with self._lock:
            return self._inbox[user.id][:limit]

    def mark_read(self, user: User) -> None:
        """Mark all notifications as read."""
        with self._lock:
            for notif in self._inbox[user.id]:
                notif.is_read = True

    def unread_count(self, user: User) -> int:
        with self._lock:
            return sum(1 for n in self._inbox[user.id] if not n.is_read)


# ══════════════════════════════════════════════════════════════════════════════
# TWEET REPOSITORY
# ══════════════════════════════════════════════════════════════════════════════

class TweetRepository:
    """
    Stores tweets. In production: PostgreSQL or Cassandra.
    
    WHY CASSANDRA FOR TWEETS?
    - Write-heavy: 500M tweets/day = 5800 writes/sec. Cassandra handles millions/sec.
    - Time-ordered queries: "get all tweets by @sachin since yesterday" → efficient with time-based partitioning.
    - Wide rows: one Cassandra partition = one user's tweets, ordered by timestamp.
    - No single point of failure: distributed, no master (peer-to-peer).
    
    CASSANDRA SCHEMA:
    CREATE TABLE tweets (
      user_id  UUID,
      tweet_id UUID,    ← TimeUUID (contains timestamp, so naturally time-ordered)
      content  TEXT,
      ...
      PRIMARY KEY (user_id, tweet_id)
    ) WITH CLUSTERING ORDER BY (tweet_id DESC);
    -- user_id = partition key (all tweets by one user in one partition)
    -- tweet_id = clustering key (ordered within partition)
    -- DESC: newest first
    """

    def __init__(self):
        self._tweets: Dict[str, Tweet] = {}   # tweet_id → Tweet
        self._user_tweets: Dict[str, List[Tweet]] = defaultdict(list)
        # user_id → list of tweets by this user (chronological)
        self._lock = threading.RLock()

    def save(self, tweet: Tweet) -> None:
        with self._lock:
            self._tweets[tweet.id] = tweet
            self._user_tweets[tweet.author.id].append(tweet)

    def find_by_id(self, tweet_id: str) -> Optional[Tweet]:
        with self._lock:
            return self._tweets.get(tweet_id)

    def find_by_user(self, user_id: str,
                     limit: int = 50, before: datetime = None) -> List[Tweet]:
        """
        Get tweets by a user, newest first, optionally before a given time.
        'before' enables cursor-based pagination (Twitter's preferred approach).
        """
        with self._lock:
            tweets = self._user_tweets.get(user_id, [])
        
        if before:
            tweets = [t for t in tweets if t.created_at < before]
            # Filter: only tweets created before the cursor time

        # Sort: newest first
        tweets = sorted(tweets, key=lambda t: t.created_at, reverse=True)
        return tweets[:limit]

    def search_by_hashtag(self, hashtag: str) -> List[Tweet]:
        """Find all tweets with a specific hashtag."""
        tag = hashtag.lstrip('#').lower()
        # lstrip('#'): remove leading # if present. "#python" → "python"
        with self._lock:
            return [t for t in self._tweets.values()
                    if tag in t.hashtags and t.is_visible()]


# ══════════════════════════════════════════════════════════════════════════════
# TWITTER SERVICE — Facade
# ══════════════════════════════════════════════════════════════════════════════

class TwitterService:
    """
    FACADE: the main entry point for all Twitter operations.
    """

    def __init__(self):
        self._users:    Dict[str, User]  = {}   # username → User
        self._tweet_repo = TweetRepository()
        self._fanout     = FanoutService()
        self._trending   = TrendingService()
        self._notifs     = NotificationService()
        self._lock       = threading.RLock()

    def register_user(self, username: str, display_name: str) -> User:
        with self._lock:
            if username.lower() in self._users:
                raise ValueError(f"Username @{username} already taken")
            user = User(username, display_name)
            self._users[username.lower()] = user
        print(f"✅ Registered: @{user.username} ({user.display_name})")
        return user

    def post_tweet(self, author: User, content: str,
                   reply_to: Optional[Tweet] = None) -> Tweet:
        """
        Post a new tweet.
        
        FLOW:
        1. Create Tweet object
        2. Save to repository
        3. Add to author's own timeline
        4. Fanout to followers' timelines (push if normal user)
        5. Record hashtags for trending
        6. Send mentions notifications
        7. Send reply notification (if it's a reply)
        """
        tweet_type = TweetType.REPLY if reply_to else TweetType.ORIGINAL
        tweet = Tweet(author, content, tweet_type, parent_tweet=reply_to)

        # Save to DB
        self._tweet_repo.save(tweet)

        # Author's own timeline gets the tweet
        self._fanout.add_to_own_timeline(tweet)

        # Fanout to followers
        followers = author.get_followers()
        if not author.is_celebrity():
            # PUSH: write to all followers' timelines immediately
            n_pushed = self._fanout.fanout_push(tweet, followers)
            print(f"📢 Pushed to {n_pushed} followers' timelines")
        else:
            # PULL: celebrity tweet — followers will pull when loading their timeline
            print(f"⭐ Celebrity tweet by @{author.username} — followers pull on demand")

        # Update reply count on parent
        if reply_to:
            reply_to.increment_reply_count()
            self._notifs.notify(reply_to.author, author,
                                NotificationType.REPLY, tweet)

        # Trending hashtag recording
        self._trending.record_tweet(tweet)

        # Mention notifications
        for mentioned_username in tweet.mentions:
            mentioned_user = self._users.get(mentioned_username)
            if mentioned_user and mentioned_user.id != author.id:
                self._notifs.notify(mentioned_user, author,
                                    NotificationType.MENTION, tweet)

        print(f"🐦 @{author.username}: {content[:60]}")
        return tweet

    def retweet(self, user: User, original_tweet: Tweet,
                comment: str = "") -> Tweet:
        """
        Retweet a tweet, optionally with a comment (Quote Tweet).
        """
        if comment:
            rt_content = f"{comment}\n\nRT @{original_tweet.author.username}: {original_tweet.content[:200]}"
            tweet_type = TweetType.QUOTE_TWEET
        else:
            rt_content = f"RT @{original_tweet.author.username}: {original_tweet.content}"
            tweet_type = TweetType.RETWEET

        tweet = Tweet(user, rt_content[:280], tweet_type, parent_tweet=original_tweet)
        original_tweet.record_retweet(user)   # Update original's retweet count
        self._tweet_repo.save(tweet)
        self._fanout.add_to_own_timeline(tweet)
        self._fanout.fanout_push(tweet, user.get_followers())
        self._notifs.notify(original_tweet.author, user,
                            NotificationType.RETWEET, original_tweet)
        print(f"🔁 @{user.username} retweeted @{original_tweet.author.username}")
        return tweet

    def like(self, user: User, tweet: Tweet) -> bool:
        """Like a tweet. Notify author."""
        liked = tweet.like(user)
        if liked and tweet.author.id != user.id:
            self._notifs.notify(tweet.author, user, NotificationType.LIKE, tweet)
        return liked

    def follow(self, follower: User, target: User) -> bool:
        """Follow a user. Notify target."""
        success = follower.follow(target)
        if success:
            self._notifs.notify(target, follower, NotificationType.NEW_FOLLOWER)
        return success

    def get_home_timeline(self, user: User, limit: int = 50) -> List[Tweet]:
        """Get user's home feed."""
        return self._fanout.get_user_timeline(user, limit)

    def get_profile_timeline(self, user: User, limit: int = 20) -> List[Tweet]:
        """Get all tweets by a specific user (their profile page)."""
        return self._tweet_repo.find_by_user(user.id, limit)

    def get_trending(self, location: str = "worldwide") -> List[TrendingTopic]:
        """Get current trending topics."""
        return self._trending.get_trending()

    def search_hashtag(self, hashtag: str) -> List[Tweet]:
        """Search for tweets with a hashtag."""
        results = self._tweet_repo.search_by_hashtag(hashtag)
        # Sort: most recent first
        return sorted(results, key=lambda t: t.created_at, reverse=True)

    def get_notifications(self, user: User) -> List[Notification]:
        return self._notifs.get_notifications(user)


# ══════════════════════════════════════════════════════════════════════════════
# DEMO
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    twitter = TwitterService()

    # Create users
    elon   = twitter.register_user("elonmusk",   "Elon Musk")
    sachin = twitter.register_user("sachin_dev",  "Sachin Kumar")
    priya  = twitter.register_user("priya_coder", "Priya Sharma")

    print("\n" + "="*60)
    print("FOLLOW RELATIONSHIPS")
    print("="*60)
    twitter.follow(sachin, elon)      # sachin follows elon
    twitter.follow(priya, elon)       # priya follows elon
    twitter.follow(sachin, priya)     # sachin follows priya
    twitter.follow(priya, sachin)     # priya follows sachin (mutual)

    print("\n" + "="*60)
    print("TWEETING")
    print("="*60)
    t1 = twitter.post_tweet(elon, 
        "Just shipped a new AI model. X is the future of everything! #AI #Tech")
    t2 = twitter.post_tweet(sachin,
        "Just cracked the #LLD interview at Amazon! #SystemDesign #Python wins!")
    t3 = twitter.post_tweet(priya,
        "Great resource: @sachin_dev's #LLD notes are gold! #Python #Coding")

    print("\n" + "="*60)
    print("REPLIES AND LIKES")
    print("="*60)
    r1 = twitter.post_tweet(sachin,
        "Congrats on the new model @elonmusk! What's the context window?",
        reply_to=t1)
    twitter.like(priya, t2)
    twitter.like(elon, t2)

    print("\n" + "="*60)
    print("RETWEET")
    print("="*60)
    twitter.retweet(priya, t2, comment="Yaasss! #LLD is life! 🔥")

    print("\n" + "="*60)
    print("SACHIN'S HOME TIMELINE")
    print("="*60)
    feed = twitter.get_home_timeline(sachin)
    for tweet in feed[:5]:
        print(f"  [{tweet.get_age_str()}] @{tweet.author.username}: {tweet.content[:60]}")

    print("\n" + "="*60)
    print("TRENDING TOPICS")
    print("="*60)
    trends = twitter.get_trending()
    for trend in trends:
        print(f"  {trend.rank}. {trend.tag} — {trend.volume_1h} tweets/hr")

    print("\n" + "="*60)
    print("SACHIN'S NOTIFICATIONS")
    print("="*60)
    notifs = twitter.get_notifications(sachin)
    for n in notifs[:5]:
        print(f"  {'✓' if n.is_read else '●'} {n.message}")

    print("\n" + "="*60)
    print("HASHTAG SEARCH")
    print("="*60)
    lld_tweets = twitter.search_hashtag("#LLD")
    print(f"Found {len(lld_tweets)} tweets with #LLD:")
    for t in lld_tweets:
        print(f"  @{t.author.username}: {t.content[:60]}")
```

---

## STEP 4 — Java Key Patterns

```java
// Java: Thread-safe Set for likes with ConcurrentHashMap
class Tweet {
    // ConcurrentHashMap as a Set: map where keys = set elements, values = placeholder
    private final Set<String> likedByUserIds
        = ConcurrentHashMap.newKeySet();
    // ConcurrentHashMap.newKeySet(): creates a thread-safe Set backed by ConcurrentHashMap.
    // All set operations (add, contains, remove) are thread-safe.
    
    private final AtomicInteger likeCount = new AtomicInteger(0);
    // AtomicInteger: thread-safe integer. No synchronized block needed.
    // .incrementAndGet(): atomically increments and returns new value. O(1).
    
    boolean like(String userId) {
        // add() returns true if the element was NOT already in the set (new like)
        if (likedByUserIds.add(userId)) {
            likeCount.incrementAndGet();
            return true;  // Like added
        }
        return false;  // Already liked
    }
    
    boolean unlike(String userId) {
        if (likedByUserIds.remove(userId)) {
            likeCount.decrementAndGet();
            return true;
        }
        return false;
    }
}

// Java: Timeline with ArrayDeque (bounded circular buffer)
class Timeline {
    private final int maxSize = 5000;
    private final ArrayDeque<Tweet> tweets = new ArrayDeque<>(maxSize);
    // ArrayDeque: double-ended queue backed by array. Faster than LinkedList (no object per node).
    
    synchronized void addTweet(Tweet tweet) {
        if (tweets.size() >= maxSize) {
            tweets.pollFirst();  // Remove oldest. pollFirst = removeFirst without exception.
        }
        tweets.addLast(tweet);  // Add newest at end.
    }
    
    // ReadLock for reads (multiple threads can read simultaneously):
    // In production with many readers: use ReadWriteLock instead of synchronized.
}
```

---

## STEP 5 — C++ Key Patterns

```cpp
// C++: Tweet with atomic counters
#include <atomic>
#include <unordered_set>
#include <shared_mutex>

class Tweet {
    std::atomic<int> likeCount_{0};
    // atomic<int>: machine-level atomic operations (no lock needed for increments).
    // On x86-64: single instruction LOCK XADD (atomic increment).

    std::unordered_set<std::string> likedBy_;  // user_ids
    mutable std::shared_mutex likeMtx_;
    // shared_mutex: readers don't block each other. Writers are exclusive.
    // Good for likedBy_ (checked on many reads, modified rarely).

public:
    bool like(const std::string& userId) {
        std::unique_lock lock(likeMtx_);   // Exclusive lock (write)
        if (likedBy_.count(userId) > 0) return false;  // Already liked
        likedBy_.insert(userId);
        likeCount_.fetch_add(1, std::memory_order_relaxed);
        // fetch_add: atomic increment. Returns old value.
        // memory_order_relaxed: no ordering constraints needed (just need atomicity of count).
        return true;
    }

    int getLikeCount() const {
        return likeCount_.load(std::memory_order_acquire);
        // acquire: see all writes that happened before the corresponding release.
    }
    
    bool isLikedBy(const std::string& userId) const {
        std::shared_lock lock(likeMtx_);   // Shared lock (read)
        return likedBy_.count(userId) > 0;  // count: returns 0 or 1 for set (O(1))
    }
};

// C++: Consistent lock ordering (deadlock prevention for follow)
void follow(User& follower, User& target) {
    // Sort by address: always lock lower-address object first.
    User* first  = &follower < &target ? &follower : &target;
    User* second = &follower < &target ? &target : &follower;
    // Pointer comparison: consistent ordering regardless of which direction follow() is called.
    // Thread 1: A.follow(B) → locks A (0x100), then B (0x200)
    // Thread 2: B.follow(A) → also locks A (0x100) first, then B (0x200)
    // Both threads lock in same order → no deadlock possible.
    
    std::scoped_lock locks(first->mtx_, second->mtx_);
    // scoped_lock: RAII lock for multiple mutexes simultaneously.
    // Uses deadlock avoidance algorithm (std::lock internally).
    // Automatically released when leaving scope.
    
    follower.following_.insert(target.id_);
    target.followers_.insert(follower.id_);
    // ... update counts
}
```

---

## STEP 6 — Trade-offs

```
TRADE-OFF 1: Push vs Pull fanout (THE key Twitter interview question)
  PUSH (fan-out on write):
    When tweet is posted: immediately write to all followers' timelines.
    Reads are O(1): just load the pre-built timeline.
    Problem: celebrities. Lady Gaga tweets → 100M writes synchronously → system melts.
    
  PULL (fan-out on read):
    When user loads feed: fetch tweets from all followed users → merge → display.
    No write amplification.
    Problem: if following 1000 users → 1000 DB queries per timeline load. Slow.
    
  HYBRID (Twitter actual):
    Normal users (< 1M followers): PUSH.
    Celebrities (> 1M followers): PULL (their tweets are fetched lazily).
    At timeline load: display pre-built push timeline + merge celebrity tweets.
    
  DATA:
    Twitter threshold is estimated at ~1M followers for celebrity treatment.
    ~500 celebrity accounts do MOST of the fan-out damage.

TRADE-OFF 2: Soft delete for tweets
  WHY SOFT DELETE?
  Tweets can be replied to. Replies reference parent_tweet.
  Hard-delete the parent → replies have broken reference.
  
  With soft delete: parent stays in DB with content replaced.
  Replies thread remains intact.
  
  Downsides: DB grows larger (deleted tweets never removed).
  GDPR: users can request their data be truly deleted → separate "right to erasure" job.

TRADE-OFF 3: Cassandra vs PostgreSQL for tweet storage
  PostgreSQL: ACID transactions, complex queries (JOIN, GROUP BY), strong consistency.
  Best for: financial data, user profiles, relationships.
  Problem: write throughput. Max ~10K writes/sec on standard PostgreSQL.
  5800 tweets/sec → fine. But with 1B users and likes/views: easily 100K writes/sec.
  
  Cassandra: designed for write-heavy workloads. 100K+ writes/sec easily.
  Partitioned: tweets partitioned by user_id → user's tweets in one partition.
  Problem: no JOINs, no complex queries. Must design schema around access patterns.
  
  Twitter uses Manhattan (their own distributed DB) + MySQL/Postgres for profiles.

TRADE-OFF 4: Trending calculation — batch vs streaming
  Batch (Hadoop/Spark): process last hour's tweets every 5 minutes.
  Simple. Can handle historical data. But: 5-minute delay in trending updates.
  
  Streaming (Apache Flink/Storm): process each tweet event in real-time.
  Trending updates < 1 minute delay. More complex to implement.
  
  Twitter uses streaming (Apache Storm → later Heron, their own system).
  Our TrendingService uses sliding window with deque (streaming-style, in-memory).

TRADE-OFF 5: Timeline read performance — deque vs sorted set
  deque (what we built): O(1) append, O(1) popleft. 
  Cannot query by time range (must iterate).
  Good for: exact sequential access (latest N tweets).
  
  Redis Sorted Set (production):
  ZADD: O(log N) insert. ZREVRANGE: O(K) fetch. ZRANGEBYSCORE: query by time range.
  Also supports: ZREM (delete tweet from timeline), ZCARD (count).
  Persisted to disk (Redis AOF/RDB). Survives server restart.
  
  Twitter stores up to 5000 tweets per timeline in Redis.
  Older tweets: re-fetched from Cassandra on demand ("load more").
```

---

## STEP 7 — Interview Follow-Ups

```
Q: "How does Twitter handle the 'thundering herd' problem?"
A:
  Thundering herd: celebrities tweet → millions of followers' timeline refreshes 
  simultaneously hit the DB.
  
  Solution 1: Pre-materialized timelines (Redis). Read never hits DB directly.
  
  Solution 2: Request coalescing. If 1000 requests for same celebrity's latest tweets
  arrive simultaneously: send ONE request to DB, fan out response to all 1000 waiters.
  
  Solution 3: CDN caching for public (non-personalized) feeds.
  Trending topics, explore page: same content for all users → cache in CDN.

Q: "How does Twitter implement DMs (Direct Messages)?"
A:
  DMs are a private messaging system.
  LLD parallels: WhatsApp chat (see CS03_WhatsApp.md).
  
  Key differences from tweets:
  - End-to-end encrypted (E2EE) since 2023 for some conversations
  - Group DMs: conversation has multiple participants
  - Read receipts: "Seen 3:45 PM"
  - No fanout: message goes to ONE inbox, not all followers
  
  Storage: Conversation table + Message table (similar to WhatsApp).
  Delivery: WebSocket connection for real-time delivery.
  Inbox: Redis sorted set per user (like timeline) ordered by timestamp.

Q: "How does Twitter's search work?"
A:
  Real-time search: Bluebird (Twitter's internal search engine).
  
  Unlike Google (crawl → index → query): Twitter needs near-real-time indexing.
  Tweets must be searchable within SECONDS of posting.
  
  Architecture:
  Tweet posted → Kafka → Earlybird (indexing service) → Inverted index shard.
  Query → distributed search across all shards → merge → rank → return.
  
  The inverted index is DISTRIBUTED across many machines.
  Each machine holds a subset of tweets (by time range or hash of tweet_id).
  "Scatter-gather": query fans out to all shards, each returns local results,
  coordinator merges and returns top results.
  
  Ranking factors: recency (freshness), author authority (verified?), engagement.
```

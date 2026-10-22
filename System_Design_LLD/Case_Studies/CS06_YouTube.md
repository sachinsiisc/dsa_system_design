# CS06: LLD — YouTube
## Video Platform | Every Line Explained | Python + Java + C++

---

> **WHAT WE'RE BUILDING:**
> YouTube's core backend — upload, transcode, serve videos, manage channels,
> comments, likes, subscriptions, and recommendation feeds.
>
> **THE CORE ENGINEERING CHALLENGE:**
> 500 hours of video uploaded every minute. 1 billion hours watched daily.
> Videos must be transcoded to multiple resolutions (360p, 720p, 1080p, 4K).
> Served globally in < 2 seconds from CDN edge nodes.

---

## STEP 1 — Requirements & Entities

```
FUNCTIONAL REQUIREMENTS:
  1. User registers, creates a Channel
  2. Upload video (raw file → transcoded → published)
  3. Watch video (stream from CDN based on bandwidth)
  4. Like / Dislike video
  5. Comment on video (and reply to comments)
  6. Subscribe to a channel
  7. Homepage feed (subscriptions + recommendations)
  8. Search videos by title, description, tags
  9. Video analytics (views, watch time, CTR)
  10. Monetization: mark video as eligible for ads

KEY ENTITIES:
  User          — registered account
  Channel       — a creator's publishing entity (one User → one Channel)
  Video         — the uploaded content (metadata + stream URLs)
  VideoFile     — raw uploaded file (before transcoding)
  VideoVariant  — transcoded version (360p, 720p, 1080p, 4K)
  Comment       — user comment on a video
  CommentThread — tree of replies (parent + children)
  Like          — thumbs up/down on a video or comment
  Subscription  — user subscribes to a channel
  Playlist      — user-curated list of videos
  WatchHistory  — what a user has watched and how much
  TranscodeJob  — async job to convert uploaded video to multiple resolutions
  FeedService   — generates homepage feed (subscriptions + recommendations)

NON-FUNCTIONAL:
  Upload: 500 hrs video/min → ~8 hrs/sec → async processing mandatory
  Watch: 1B hours/day → ~11.5M concurrent streams
  Search: < 1 second response
  CDN edge nodes in 200+ countries
```

---

## STEP 2 — Class Diagram

```
[User]                        [Channel]                   [VideoVariant]
──────                        ─────────                   ──────────────
- id: UUID                    - id: UUID                  - resolution: str ("720p")
- username: str               - name: str                 - cdn_url: str
- email: str                  - owner: User               - bitrate_kbps: int
- channel: Channel?           - description: str          - file_size_bytes: int
- created_at: datetime        - subscriber_count: int     - codec: str ("H.264")
──────                        - thumbnail_url: str        - status: VariantStatus
+ create_channel(): Channel   - is_monetized: bool        (PROCESSING/READY/FAILED)
+ subscribe(Channel): void
+ get_feed(): List[Video]     [Video]                     [TranscodeJob]
                              ───────                     ─────────────
[Subscription]                - id: UUID                  - id: UUID
──────────────                - channel: Channel          - video: Video
- subscriber: User            - title: str                - status: JobStatus
- channel: Channel            - description: str          - queued_at: datetime
- subscribed_at: datetime     - tags: List[str]           - started_at: datetime?
- notify_new_uploads: bool    - duration_seconds: int     - completed_at: datetime?
                              - thumbnail_url: str        - error_msg: str?
[Comment]                     - status: VideoStatus       ─────────────
─────────                     (UPLOADING/PROCESSING/      + process(): void
- id: UUID                     PUBLISHED/UNLISTED/PRIVATE)
- video: Video                - view_count: int           [Like]
- author: User                - like_count: int           ──────
- content: str                - dislike_count: int        - user: User
- parent: Comment?            - variants: List[Variant]   - target_id: str (video/comment)
- created_at: datetime        ───────                     - target_type: str
- like_count: int             + get_best_variant(): Variant - is_like: bool (True=👍)
- is_deleted: bool            + is_playable(): bool       - created_at: datetime
─────────
+ reply(content): Comment

PATTERNS:
  Observer    → Subscription (channel publishes → subscribers notified)
  State       → Video.status, TranscodeJob.status
  Strategy    → AdaptiveBitrateStrategy (choose best variant for bandwidth)
  Composite   → CommentThread (comment tree with replies)
  Template    → TranscodeJob.process() skeleton, workers fill in codec step
  Factory     → VideoFactory.create() builds Video + initial TranscodeJob
  Repository  → VideoRepository (decoupled storage)
```

---

## STEP 3 — Python Implementation (Every Line Explained)

```python
# youtube_lld.py
from __future__ import annotations

import uuid
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional, List, Dict, Set, Callable


# ══════════════════════════════════════════════════════════════════════════════
# ENUMS
# ══════════════════════════════════════════════════════════════════════════════

class VideoStatus(Enum):
    """
    STATE MACHINE for a Video:
    
    UPLOADING   → Raw file being received from creator's browser/app.
    PROCESSING  → File received, transcoding in progress (converting to multiple resolutions).
    PUBLISHED   → Available to all users.
    UNLISTED    → Available only to users with the direct link (not in search/feed).
    PRIVATE     → Only the creator can view.
    REMOVED     → Deleted by creator or by YouTube for policy violation.
    
    This is why YouTube shows "Processing..." after uploading — it's in PROCESSING state.
    """
    UPLOADING  = "uploading"
    PROCESSING = "processing"
    PUBLISHED  = "published"
    UNLISTED   = "unlisted"
    PRIVATE    = "private"
    REMOVED    = "removed"

class JobStatus(Enum):
    """
    STATE MACHINE for transcoding jobs.
    QUEUED → PROCESSING → COMPLETED or FAILED.
    """
    QUEUED      = "queued"
    PROCESSING  = "processing"
    COMPLETED   = "completed"
    FAILED      = "failed"

class VariantStatus(Enum):
    """Is this resolution variant ready to stream?"""
    PROCESSING = "processing"   # Being transcoded
    READY      = "ready"        # Can be streamed
    FAILED     = "failed"       # Transcoding failed for this resolution


# ══════════════════════════════════════════════════════════════════════════════
# VIDEO VARIANT — One resolution of a video
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class VideoVariant:
    """
    One transcoded version of a video.
    
    YouTube stores MULTIPLE versions of each video:
    - 360p:  low quality, mobile data users
    - 720p:  HD, standard desktop viewing
    - 1080p: Full HD, good internet connection
    - 4K:    Premium quality, powerful device + fast internet
    
    WHY MULTIPLE VARIANTS?
    Adaptive Bitrate Streaming (ABR):
    - User starts watching on WiFi → 1080p
    - User goes to elevator → bandwidth drops → switches to 360p (no buffering)
    - User comes back → bandwidth recovers → switches back to 1080p
    This is seamless — user doesn't notice the switch.
    YouTube uses DASH (Dynamic Adaptive Streaming over HTTP) for this.
    """
    video_id:        str           # Which video this variant belongs to
    resolution:      str           # "360p", "720p", "1080p", "2160p" (4K)
    cdn_url:         str           # CDN URL where this variant's .m3u8 file lives
    bitrate_kbps:    int           # Data rate: 360p≈700kbps, 1080p≈5000kbps
    file_size_bytes: int           # Total file size on disk
    codec:           str = "H.264" # Video codec: H.264 (compatible) or H.265 (smaller files)
    status:          VariantStatus = VariantStatus.PROCESSING

    def is_ready(self) -> bool:
        return self.status == VariantStatus.READY

    def required_bandwidth_kbps(self) -> int:
        """Minimum bandwidth needed to stream this without buffering."""
        return int(self.bitrate_kbps * 1.2)   # 20% headroom above bitrate


# ══════════════════════════════════════════════════════════════════════════════
# ADAPTIVE BITRATE STRATEGY
# ══════════════════════════════════════════════════════════════════════════════

class IAdaptiveBitrateStrategy(ABC):
    """
    STRATEGY PATTERN for selecting the best video variant to stream.
    
    The same video has variants at 360p, 720p, 1080p, 4K.
    We pick the BEST one the user's bandwidth can handle without buffering.
    
    Strategies:
    - BandwidthAwareStrategy: pick highest quality that fits in available bandwidth.
    - QualityFirstStrategy: always prefer highest quality (may buffer).
    - DataSaverStrategy: always pick lowest quality (minimize data usage).
    """

    @abstractmethod
    def select(self, variants: List[VideoVariant],
               available_bandwidth_kbps: int) -> Optional[VideoVariant]: ...


class BandwidthAwareStrategy(IAdaptiveBitrateStrategy):
    """Pick the BEST quality that won't cause buffering."""

    # Resolution priority order (best to worst)
    RESOLUTION_PRIORITY = ["2160p", "1440p", "1080p", "720p", "480p", "360p", "240p"]

    def select(self, variants: List[VideoVariant],
               available_bandwidth_kbps: int) -> Optional[VideoVariant]:
        """
        Filter variants that fit in bandwidth, then pick the best quality.
        
        LOGIC:
        1. Get all READY variants
        2. Filter: only those whose required bandwidth ≤ available bandwidth
        3. Sort by resolution quality (best first)
        4. Return the first (= best fitting quality)
        """
        ready = [v for v in variants if v.is_ready()]
        # List comprehension: only include variants where is_ready() returns True

        fits  = [v for v in ready
                 if v.required_bandwidth_kbps() <= available_bandwidth_kbps]
        # Filter: only variants whose bandwidth requirement fits in available bandwidth

        if not fits:
            # Even 360p doesn't fit → return lowest quality available
            if ready:
                return min(ready, key=lambda v: v.bitrate_kbps)
            return None   # No variants ready at all

        # Sort by resolution priority (index in RESOLUTION_PRIORITY list)
        def priority(variant: VideoVariant) -> int:
            try:
                return self.RESOLUTION_PRIORITY.index(variant.resolution)
                # index() returns position in list: "1080p" → 2 (lower = better quality)
            except ValueError:
                return 999   # Unknown resolution → lowest priority

        return min(fits, key=priority)
        # min by priority index: index 0 (2160p) is "smallest" index = best quality


# ══════════════════════════════════════════════════════════════════════════════
# VIDEO
# ══════════════════════════════════════════════════════════════════════════════

class Video:
    """
    A YouTube video — the central entity of the platform.
    
    Lifecycle:
    1. Creator uploads raw file
    2. System creates Video in UPLOADING state
    3. Raw file received → PROCESSING state
    4. TranscodeWorker creates variants → publishes to CDN
    5. All variants ready → PUBLISHED state
    6. Users can watch, like, comment
    """

    def __init__(self, channel: Channel, title: str, description: str, tags: List[str]):
        self.id              = str(uuid.uuid4())
        self.channel         = channel
        self.title           = title
        self.description     = description
        self.tags            = [t.lower().strip() for t in tags]
        # Normalize tags: lowercase + strip whitespace
        # "Python " → "python", "JAVA" → "java"
        # WHY: makes search/filter consistent regardless of how creator typed tags

        self.thumbnail_url   = ""     # Set after upload or auto-generated
        self.duration_sec    = 0      # Set after transcoding (before unknown)
        self._status         = VideoStatus.UPLOADING
        self.uploaded_at     = datetime.utcnow()
        self.published_at:   Optional[datetime] = None

        # Atomic counters (thread-safe increments)
        self._view_count     = 0
        self._like_count     = 0
        self._dislike_count  = 0

        # Transcoded variants (multiple resolutions)
        self._variants:      List[VideoVariant] = []
        self._lock           = threading.RLock()

    def add_variant(self, variant: VideoVariant) -> None:
        """Add a transcoded variant when ready."""
        with self._lock:
            self._variants.append(variant)

    def get_variants(self) -> List[VideoVariant]:
        """Return all variants (for adaptive streaming player)."""
        with self._lock:
            return list(self._variants)

    def get_best_variant(self, bandwidth_kbps: int,
                         strategy: IAdaptiveBitrateStrategy = None) -> Optional[VideoVariant]:
        """Select best variant for given bandwidth (uses ABR strategy)."""
        if strategy is None:
            strategy = BandwidthAwareStrategy()
        with self._lock:
            return strategy.select(self._variants, bandwidth_kbps)

    def publish(self) -> None:
        """Mark video as published (all critical variants are ready)."""
        with self._lock:
            if self._status != VideoStatus.PROCESSING:
                raise ValueError(f"Cannot publish from status {self._status.value}")
            self._status    = VideoStatus.PUBLISHED
            self.published_at = datetime.utcnow()

    def record_view(self) -> None:
        """Increment view count (called when user watches > 30 seconds)."""
        with self._lock:
            self._view_count += 1
            # In production: this is async via Kafka.
            # At 11.5M concurrent streams, synchronous increments would be impossible.
            # Real YouTube: buffer in Redis, batch flush to DB every minute.

    def like(self) -> None:
        with self._lock: self._like_count += 1

    def dislike(self) -> None:
        with self._lock: self._dislike_count += 1

    def is_playable(self) -> bool:
        """Can users watch this video right now?"""
        with self._lock:
            playable_statuses = {VideoStatus.PUBLISHED, VideoStatus.UNLISTED}
            return (self._status in playable_statuses
                    and any(v.is_ready() for v in self._variants))
            # Must be in a viewable status AND have at least one ready variant

    def matches_search(self, query: str) -> bool:
        """Does this video match a search query?"""
        q = query.lower()
        return (q in self.title.lower()
                or q in self.description.lower()
                or any(q in tag for tag in self.tags))

    @property
    def status(self) -> VideoStatus:
        with self._lock: return self._status

    @property
    def view_count(self) -> int:
        with self._lock: return self._view_count

    @property
    def like_count(self) -> int:
        with self._lock: return self._like_count

    def __repr__(self) -> str:
        return f"Video({self.title!r}, {self.status.value}, views={self._view_count})"


# ══════════════════════════════════════════════════════════════════════════════
# TRANSCODE JOB — Template Method
# ══════════════════════════════════════════════════════════════════════════════

class TranscodeJob:
    """
    Async job that converts raw uploaded video to multiple resolutions.
    
    WHY ASYNC?
    Transcoding a 1-hour video to 4 resolutions takes 30+ minutes.
    We CAN'T block the upload API for 30 minutes.
    Solution: accept the upload → immediately return job_id → process in background.
    Creator can see: "Video is processing — usually takes 30-60 minutes."
    
    REAL YOUTUBE:
    - Raw video uploaded to Google Cloud Storage
    - Job message published to Pub/Sub (like Kafka)
    - Transcode workers pull from Pub/Sub
    - Each worker handles one video, creates all variants
    - Workers run on Google Cloud Run (auto-scale based on queue size)
    - At 500 hours/min upload rate: thousands of transcode workers running simultaneously
    
    TARGET RESOLUTIONS (most to least quality):
    4K (2160p), 1440p, 1080p, 720p, 480p, 360p, 144p
    Not all videos get 4K — depends on source resolution.
    """

    # Resolutions to transcode to (in order of quality)
    TARGET_RESOLUTIONS = [
        ("2160p", 15000),   # 4K,    15 Mbps
        ("1080p",  5000),   # FHD,    5 Mbps
        ("720p",   2500),   # HD,   2.5 Mbps
        ("480p",   1000),   # SD,     1 Mbps
        ("360p",    700),   # LD,   0.7 Mbps
    ]

    def __init__(self, video: Video, raw_file_path: str):
        self.id            = str(uuid.uuid4())
        self.video         = video
        self.raw_file_path = raw_file_path   # Where the uploaded file is stored
        self._status       = JobStatus.QUEUED
        self.queued_at     = datetime.utcnow()
        self.started_at:   Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.error_msg:    Optional[str]      = None
        self._lock         = threading.Lock()

    def process(self) -> bool:
        """
        TEMPLATE METHOD:
        Defines the transcoding algorithm skeleton.
        Steps are separated for clarity — in production each step is more complex.
        """
        with self._lock:
            self._status    = JobStatus.PROCESSING
            self.started_at = datetime.utcnow()

        try:
            # Step 1: Validate raw file (is it a valid video format?)
            self._validate_raw_file()

            # Step 2: Set video duration (read from file metadata)
            self._extract_metadata()

            # Step 3: Transcode to each target resolution
            for resolution, bitrate in self.TARGET_RESOLUTIONS:
                variant = self._transcode_to_resolution(resolution, bitrate)
                self.video.add_variant(variant)

            # Step 4: Generate thumbnail from first frame
            self._generate_thumbnail()

            # Step 5: Publish the video (all main variants ready)
            self.video.publish()

            with self._lock:
                self._status      = JobStatus.COMPLETED
                self.completed_at = datetime.utcnow()

            print(f"✅ Transcoding complete for: {self.video.title}")
            return True

        except Exception as e:
            with self._lock:
                self._status  = JobStatus.FAILED
                self.error_msg = str(e)
            print(f"❌ Transcoding FAILED for {self.video.title}: {e}")
            return False

    def _validate_raw_file(self) -> None:
        """Validate uploaded file is a real video (not a fake/corrupt file)."""
        # In production: check file header bytes (magic numbers), run ffprobe
        if not self.raw_file_path.endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm')):
            raise ValueError(f"Unsupported format: {self.raw_file_path}")
        print(f"✓ File validated: {self.raw_file_path}")

    def _extract_metadata(self) -> None:
        """
        Read video duration, frame rate, resolution from file metadata.
        In production: runs ffprobe (FFmpeg's metadata extraction tool).
        ffprobe -v quiet -print_format json -show_streams input.mp4
        """
        self.video.duration_sec = 600   # Simulate 10-minute video
        print(f"✓ Metadata: {self.video.duration_sec}s duration")

    def _transcode_to_resolution(self, resolution: str, bitrate_kbps: int) -> VideoVariant:
        """
        Convert raw video to a specific resolution.
        
        In production: shell command to FFmpeg:
        ffmpeg -i input.mp4 -vf scale=1920:1080 -b:v 5000k \
               -c:v libx264 -preset fast output_1080p.mp4
        
        Then upload output file to CDN (Google Cloud CDN / CloudFront).
        """
        print(f"  Transcoding → {resolution} @ {bitrate_kbps}kbps...")
        time.sleep(0.01)   # Simulate transcoding time

        cdn_url = f"https://cdn.youtube.com/videos/{self.video.id}/{resolution}.m3u8"
        # .m3u8 = HLS (HTTP Live Streaming) playlist file
        # It contains URLs to video segments (each ~6 seconds long)
        # Player downloads segments sequentially, can switch resolution between segments

        return VideoVariant(
            video_id=self.video.id,
            resolution=resolution,
            cdn_url=cdn_url,
            bitrate_kbps=bitrate_kbps,
            file_size_bytes=bitrate_kbps * self.video.duration_sec * 128,
            # Rough size: bitrate (kbps) × duration (sec) × 128 = bytes
            # × 128 = convert kbps×sec to bytes (1kbps = 1000 bits/sec, /8 bits/byte, ×1000 ≈ 125)
            codec="H.264",
            status=VariantStatus.READY
        )

    def _generate_thumbnail(self) -> None:
        """Extract a frame from the video to use as thumbnail."""
        self.video.thumbnail_url = f"https://img.youtube.com/{self.video.id}/hqdefault.jpg"
        print(f"✓ Thumbnail generated")

    @property
    def status(self) -> JobStatus:
        with self._lock: return self._status


# ══════════════════════════════════════════════════════════════════════════════
# COMMENT — Composite Pattern (tree of replies)
# ══════════════════════════════════════════════════════════════════════════════

class Comment:
    """
    A comment on a video (or reply to another comment).
    
    COMPOSITE PATTERN (simplified):
    Comment can have child Comments (replies).
    comment.get_replies() → list of Comment
    reply.get_replies() → list of Comment (nested replies)
    
    YouTube: only 2 levels (comment + replies). No infinite nesting.
    Reddit: infinite nesting (true Composite pattern).
    """

    def __init__(self, video: Video, author: User, content: str,
                 parent: Optional[Comment] = None):
        self.id         = str(uuid.uuid4())
        self.video      = video
        self.author     = author
        self.content    = content
        self.parent     = parent    # None = top-level comment, not None = reply
        self.created_at = datetime.utcnow()
        self._like_count = 0
        self._is_deleted = False
        self._replies:  List[Comment] = []
        self._lock      = threading.Lock()

    def reply(self, author: User, content: str) -> Comment:
        """Add a reply to this comment."""
        with self._lock:
            if self.parent is not None:
                raise ValueError("Cannot reply to a reply (YouTube only allows 2 levels)")
            child = Comment(self.video, author, content, parent=self)
            self._replies.append(child)
            return child

    def get_replies(self) -> List[Comment]:
        with self._lock:
            return [r for r in self._replies if not r._is_deleted]
            # Filter out deleted replies

    def like(self) -> None:
        with self._lock: self._like_count += 1

    def delete(self) -> None:
        """Soft delete — keep in DB but mark as deleted (content replaced with '[deleted]')."""
        with self._lock:
            self._is_deleted = True
            self.content     = "[deleted]"
            # WHY SOFT DELETE? Replies to this comment still need to show.
            # If we hard-delete, the reply thread would be broken.

    @property
    def like_count(self) -> int:
        with self._lock: return self._like_count

    @property
    def is_deleted(self) -> bool:
        with self._lock: return self._is_deleted

    def __repr__(self) -> str:
        return f"Comment({self.author.username!r}: {self.content[:30]!r})"


# ══════════════════════════════════════════════════════════════════════════════
# SUBSCRIPTION — Observer Pattern
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Subscription:
    """
    OBSERVER PATTERN:
    Subscriber (User) observes a Channel.
    When Channel publishes a new video (event): notify all subscribers.
    
    YouTube's Notification System:
    - Bell icon (🔔): subscriber gets notifications for ALL uploads
    - No bell: subscriber sees videos in feed but no push notification
    - is_notified: equivalent to bell icon ON
    """
    subscriber:        User
    channel:           Channel
    subscribed_at:     datetime = field(default_factory=datetime.utcnow)
    is_notified:       bool = True   # Bell icon: True = get push notification on upload


# ══════════════════════════════════════════════════════════════════════════════
# CHANNEL
# ══════════════════════════════════════════════════════════════════════════════

class Channel:
    """
    A creator's publishing entity on YouTube.
    
    OBSERVER PATTERN:
    Channel is the "Subject" (Observable).
    Subscribers are "Observers".
    When new video is published → notify all subscribers.
    """

    def __init__(self, owner: User, name: str, description: str = ""):
        self.id               = str(uuid.uuid4())
        self.owner            = owner
        self.name             = name
        self.description      = description
        self.thumbnail_url    = ""
        self.is_monetized     = False
        self._videos:         List[Video]        = []
        self._subscriptions:  List[Subscription] = []  # Observers list
        self._subscriber_count = 0
        self._lock            = threading.RLock()

    def upload_video(self, title: str, description: str, tags: List[str],
                     raw_file_path: str) -> tuple[Video, TranscodeJob]:
        """
        Creator uploads a video.
        
        RETURNS: (Video, TranscodeJob)
        Video: created immediately (UPLOADING status)
        TranscodeJob: the async job to convert the video
        
        The TranscodeJob should be queued to a worker thread/message queue.
        """
        video = Video(self, title, description, tags)
        video._status = VideoStatus.PROCESSING   # Raw file received, now processing

        job = TranscodeJob(video, raw_file_path)

        with self._lock:
            self._videos.append(video)

        print(f"Video created: {video.id[:8]}... Transcode job queued.")
        return video, job

    def publish_video(self, video: Video) -> None:
        """
        Called when transcoding completes → notify all subscribers.
        
        OBSERVER NOTIFY:
        Iterate through all subscriptions and call their notification handler.
        """
        with self._lock:
            self._subscriber_count   # Access under lock
            notified_subscribers = [s for s in self._subscriptions if s.is_notified]

        # Send notifications (in production: async via notification microservice + Kafka)
        for sub in notified_subscribers:
            self._notify_subscriber(sub.subscriber, video)

        print(f"📢 Notified {len(notified_subscribers)} subscribers about: {video.title}")

    def _notify_subscriber(self, user: User, video: Video) -> None:
        """Send push notification / email to a subscriber."""
        print(f"  🔔 Notifying {user.username}: New video '{video.title}' from {self.name}")
        # In production: publish to Kafka → notification service → FCM/APNs/Email

    def add_subscription(self, subscription: Subscription) -> None:
        """Add a new subscriber (observer)."""
        with self._lock:
            self._subscriptions.append(subscription)
            self._subscriber_count += 1

    def remove_subscription(self, user: User) -> bool:
        """Unsubscribe a user."""
        with self._lock:
            for i, sub in enumerate(self._subscriptions):
                if sub.subscriber.id == user.id:
                    del self._subscriptions[i]
                    self._subscriber_count -= 1
                    return True
            return False

    def get_videos(self, published_only: bool = True) -> List[Video]:
        with self._lock:
            if published_only:
                return [v for v in self._videos if v.status == VideoStatus.PUBLISHED]
            return list(self._videos)

    @property
    def subscriber_count(self) -> int:
        with self._lock: return self._subscriber_count

    def __repr__(self) -> str:
        return f"Channel({self.name!r}, {self.subscriber_count} subs)"


# ══════════════════════════════════════════════════════════════════════════════
# USER
# ══════════════════════════════════════════════════════════════════════════════

class User:
    """A YouTube user (can be viewer and/or creator)."""

    def __init__(self, username: str, email: str):
        self.id              = str(uuid.uuid4())
        self.username        = username
        self.email           = email
        self.channel:        Optional[Channel] = None   # Creator's channel (optional)
        self.created_at      = datetime.utcnow()
        self._subscriptions: Dict[str, Subscription] = {}  # channel_id → Subscription
        self._liked_videos:  Set[str] = set()   # Set of video IDs
        self._watch_history: Dict[str, int] = {}   # video_id → watched_seconds
        self._lock           = threading.RLock()

    def create_channel(self, name: str, description: str = "") -> Channel:
        """Create a YouTube channel for this user."""
        if self.channel:
            raise ValueError(f"User {self.username} already has a channel")
        channel = Channel(self, name, description)
        self.channel = channel
        return channel

    def subscribe(self, channel: Channel, notify: bool = True) -> Subscription:
        """Subscribe to a channel."""
        with self._lock:
            if channel.id in self._subscriptions:
                raise ValueError(f"Already subscribed to {channel.name}")
            sub = Subscription(self, channel, is_notified=notify)
            self._subscriptions[channel.id] = sub
        channel.add_subscription(sub)
        print(f"✅ {self.username} subscribed to {channel.name}")
        return sub

    def unsubscribe(self, channel: Channel) -> None:
        """Unsubscribe from a channel."""
        with self._lock:
            if channel.id not in self._subscriptions:
                return
            del self._subscriptions[channel.id]
        channel.remove_subscription(self)

    def like_video(self, video: Video) -> None:
        """Like a video (thumbs up)."""
        with self._lock:
            if video.id not in self._liked_videos:
                self._liked_videos.add(video.id)
                video.like()

    def record_watch(self, video: Video, watched_seconds: int) -> None:
        """Record that user watched this video for N seconds."""
        with self._lock:
            self._watch_history[video.id] = watched_seconds
        if watched_seconds >= 30:
            video.record_view()
            # YouTube convention: only count a "view" after 30 seconds of watching

    def get_feed(self) -> List[Video]:
        """Get videos from subscribed channels (chronological)."""
        with self._lock:
            channels = [sub.channel for sub in self._subscriptions.values()]
        
        all_videos = []
        for channel in channels:
            all_videos.extend(channel.get_videos(published_only=True))

        # Sort: most recently published first
        all_videos.sort(key=lambda v: v.published_at or datetime.min, reverse=True)
        # datetime.min = the smallest possible datetime — None videos sort to the end
        return all_videos[:50]   # Return top 50 most recent

    def get_subscribed_channels(self) -> List[Channel]:
        with self._lock:
            return [sub.channel for sub in self._subscriptions.values()]


# ══════════════════════════════════════════════════════════════════════════════
# LIKE SERVICE
# ══════════════════════════════════════════════════════════════════════════════

class LikeService:
    """
    Manages likes and dislikes for videos and comments.
    
    CHALLENGE: Prevent a user from liking the same video twice.
    Use a Set<user_id> per video (or a DB table with UNIQUE constraint on user_id + video_id).
    """

    def __init__(self):
        # video_id → {user_id: is_like (True=like, False=dislike)}
        self._video_likes: Dict[str, Dict[str, bool]] = defaultdict(dict)
        self._lock = threading.RLock()

    def like_video(self, user: User, video: Video) -> None:
        """Thumbs up. Toggle if already liked."""
        with self._lock:
            current = self._video_likes[video.id].get(user.id)
            if current is True:
                # Already liked → toggle off (unlike)
                del self._video_likes[video.id][user.id]
                video._like_count -= 1
            else:
                if current is False:
                    # Currently disliked → change to like (remove dislike first)
                    video._dislike_count -= 1
                self._video_likes[video.id][user.id] = True
                video._like_count += 1

    def dislike_video(self, user: User, video: Video) -> None:
        """Thumbs down (private count since 2021 YouTube update)."""
        with self._lock:
            current = self._video_likes[video.id].get(user.id)
            if current is False:
                del self._video_likes[video.id][user.id]
                video._dislike_count -= 1
            else:
                if current is True:
                    video._like_count -= 1
                self._video_likes[video.id][user.id] = False
                video._dislike_count += 1

    def get_user_reaction(self, user: User, video: Video) -> Optional[bool]:
        """True=liked, False=disliked, None=no reaction."""
        with self._lock:
            return self._video_likes[video.id].get(user.id)


# ══════════════════════════════════════════════════════════════════════════════
# SEARCH SERVICE
# ══════════════════════════════════════════════════════════════════════════════

class VideoSearchService:
    """
    In-memory video search. Production: Elasticsearch.
    
    Elasticsearch advantages:
    - Full-text search with relevance ranking
    - Fuzzy matching ("pythn" matches "python")
    - Faceted search (filter by duration, upload date, resolution)
    - Suggest/autocomplete
    """

    def __init__(self):
        self._videos: List[Video] = []
        self._lock   = threading.Lock()

    def index(self, video: Video) -> None:
        """Add video to search index (called after publishing)."""
        with self._lock:
            self._videos.append(video)

    def search(self, query: str, max_results: int = 20) -> List[Video]:
        """Search for videos matching the query."""
        q = query.lower().strip()
        with self._lock:
            # Filter: published videos matching query
            results = [v for v in self._videos
                       if v.status == VideoStatus.PUBLISHED and v.matches_search(q)]

        # Rank by view count (simplified — real YouTube uses complex ranking)
        results.sort(key=lambda v: v.view_count, reverse=True)
        return results[:max_results]


# ══════════════════════════════════════════════════════════════════════════════
# YOUTUBE SERVICE — Facade
# ══════════════════════════════════════════════════════════════════════════════

class YouTubeService:
    """Main facade for all YouTube operations."""

    def __init__(self):
        self._users:   Dict[str, User]    = {}
        self._channels: Dict[str, Channel] = {}
        self._videos:  Dict[str, Video]   = {}
        self._jobs:    Dict[str, TranscodeJob] = {}
        self._likes    = LikeService()
        self._search   = VideoSearchService()
        self._lock     = threading.RLock()

    def register_user(self, username: str, email: str) -> User:
        with self._lock:
            user = User(username, email)
            self._users[user.id] = user
        return user

    def create_channel(self, user: User, name: str) -> Channel:
        channel = user.create_channel(name)
        with self._lock:
            self._channels[channel.id] = channel
        return channel

    def upload_video(self, channel: Channel, title: str,
                     description: str, tags: List[str],
                     file_path: str) -> tuple[Video, TranscodeJob]:
        """Upload and begin transcoding a video."""
        video, job = channel.upload_video(title, description, tags, file_path)
        with self._lock:
            self._videos[video.id] = video
            self._jobs[job.id]     = job

        # In production: push job to queue (Kafka/Pub-Sub)
        # Here: run synchronously for demo
        success = job.process()
        if success:
            self._search.index(video)    # Add to search index after publishing
            channel.publish_video(video) # Notify subscribers

        return video, job

    def watch(self, user: User, video_id: str,
              bandwidth_kbps: int = 5000) -> Optional[str]:
        """
        User watches a video.
        Returns: CDN URL to the best variant for their bandwidth.
        """
        video = self._videos.get(video_id)
        if not video or not video.is_playable():
            return None

        variant = video.get_best_variant(bandwidth_kbps)
        if not variant:
            return None

        user.record_watch(video, 60)   # Simulate watching 60 seconds
        print(f"▶ Streaming: {video.title} at {variant.resolution} "
              f"({variant.bitrate_kbps}kbps)")
        return variant.cdn_url

    def comment(self, user: User, video_id: str, content: str) -> Optional[Comment]:
        """Post a comment on a video."""
        video = self._videos.get(video_id)
        if not video: return None
        cmt = Comment(video, user, content)
        print(f"💬 {user.username}: {content[:50]}")
        return cmt

    def search(self, query: str) -> List[Video]:
        """Search for videos."""
        results = self._search.search(query)
        print(f"Search '{query}': {len(results)} results")
        return results


# ══════════════════════════════════════════════════════════════════════════════
# DEMO
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    yt = YouTubeService()

    # Create users
    sachin = yt.register_user("sachin_codes", "sachin@gmail.com")
    priya  = yt.register_user("priya_learns", "priya@gmail.com")
    viewer = yt.register_user("viewer_xyz",   "viewer@gmail.com")

    # Sachin creates a channel
    sachin_channel = yt.create_channel(sachin, "Sachin Codes — System Design")

    # Viewer subscribes
    viewer.subscribe(sachin_channel, notify=True)   # Bell ON
    priya.subscribe(sachin_channel, notify=False)   # Bell OFF

    print("\n" + "="*60)
    print("UPLOADING VIDEO")
    print("="*60)
    video, job = yt.upload_video(
        sachin_channel,
        title="LLD Interview — URL Shortener in 30 minutes",
        description="Complete LLD solution for URL Shortener. Python + Java + C++.",
        tags=["LLD", "System Design", "Python", "Interview"],
        file_path="lld_url_shortener.mp4"
    )
    # ↑ This triggers transcoding + CDN upload + subscriber notification

    print("\n" + "="*60)
    print("WATCHING VIDEO")
    print("="*60)
    url = yt.watch(viewer, video.id, bandwidth_kbps=3000)  # Average WiFi
    print(f"Stream URL: {url}")

    print("\n" + "="*60)
    print("COMMENTING")
    print("="*60)
    cmt1 = yt.comment(viewer, video.id, "This is exactly what I needed for my Amazon interview!")
    cmt2 = yt.comment(priya, video.id, "Can you do HLD next?")
    reply = cmt2.reply(sachin, "Yes! HLD video is in progress! 🔥")

    print("\n" + "="*60)
    print("SEARCH")
    print("="*60)
    results = yt.search("LLD interview")
    for r in results:
        print(f"  {r.title} | {r.view_count} views | {r.status.value}")
```

---

## STEP 4 — Trade-offs

```
TRADE-OFF 1: Transcoding pipeline — synchronous vs asynchronous
  Synchronous: upload API waits for transcoding to complete.
  A 1-hour video transcoding takes 30-60 minutes. API call times out. Bad UX.
  
  Asynchronous (YouTube actual):
  Upload → Store raw → Return immediately (creator sees "Processing...") → Worker handles transcoding.
  Implementation: Upload API publishes job to Pub/Sub.
                  Transcode workers (Google Cloud Run, auto-scaled) pull jobs.
                  At 500 hrs/min: thousands of workers running simultaneously.
  Our demo runs synchronously for simplicity — in interview, describe async approach.

TRADE-OFF 2: View count consistency vs performance
  Exact count: every view increments DB counter. At 11.5M concurrent streams → 11.5M writes/sec.
  PostgreSQL max: ~10K writes/sec. Would crash instantly.
  
  YouTube's approach (approximate counts):
  1. Each view event published to Kafka.
  2. Counter aggregator (Apache Flink) consumes events, aggregates per video.
  3. Flush aggregated counts to DB every 60 seconds.
  Tradeoff: count is approximate (may be 5-10 minutes delayed). Acceptable for YouTube.
  
  Redis-based buffering: video_id → count in Redis (atomic INCR). Flush to DB every minute.
  Redis INCR: ~500K ops/sec on single node. Handles the load.

TRADE-OFF 3: CDN for video delivery
  Without CDN: video server in us-east-1. Indian user → 200ms round trip per segment.
  Each 6-second segment → 33ms is fine. But peak load: millions of users + one server.
  
  With CDN (Google Global Cache / AWS CloudFront):
  200+ PoPs (Points of Presence) worldwide. Indian user → cdn.youtube.com → Mumbai PoP.
  Video segment cached at Mumbai → < 10ms. Perfect.
  
  Cache-busting: video URLs are content-addressed (URL contains hash of content).
  URL never changes for same content → cached forever at CDN.
  New upload → new URL → fresh fetch from origin.

TRADE-OFF 4: HLS vs DASH for adaptive streaming
  HLS (Apple): .m3u8 playlist + .ts segment files. Works natively on iOS.
  DASH (Google): .mpd manifest + .mp4 segments. Better compression.
  
  YouTube uses DASH for web/Android, HLS for iOS (Apple requirement).
  Our VideoVariant.cdn_url points to .m3u8 (HLS) for simplicity.
  Production: serve both formats, player picks based on device.

TRADE-OFF 5: Comment storage — flat table vs nested (adjacency list)
  Flat table: every comment has parent_id (NULL for top-level, comment_id for replies).
  Query top-level: SELECT * FROM comments WHERE video_id=? AND parent_id IS NULL
  Query replies: SELECT * FROM comments WHERE parent_id = ?
  Simple. Works for 2-level nesting (YouTube style).
  
  Closure table: stores ALL ancestor-descendant pairs. Fast for any depth queries.
  Better for Reddit-style infinite nesting. Overkill for YouTube's 2-level.
```


---

## STEP 8 — Extended Deep-Dives: Advanced Design Patterns in Practice

```
CONCURRENT ACCESS PATTERNS — THE SUBTLETIES:

  WHY ConcurrentHashMap.newKeySet() in Java:
    Set<String> followers = new HashSet<>();  // NOT thread-safe
    Thread A: followers.add("alice");
    Thread B: followers.add("bob");
    Result: potential data corruption. HashSet.add() is NOT atomic.
    
    Set<String> followers = ConcurrentHashMap.newKeySet();  // thread-safe
    Internally: ConcurrentHashMap<String, Boolean>. All operations atomic.
    Why not Collections.synchronizedSet()?
      synchronizedSet wraps with synchronized block.
      add() and remove(): one thread at a time. Works but LOW THROUGHPUT.
      ConcurrentHashMap.newKeySet(): lock-free reads via CAS (Compare-And-Swap).
      Much higher throughput for read-heavy access (followers list is read very often).
  
  THE READ-WRITE LOCK PATTERN (Java ReentrantReadWriteLock):
    Scenario: followers list accessed thousands of times per second for reads.
    Writing (follow/unfollow): rare (maybe 100 times/day for average user).
    
    synchronized(lock): allows ONLY ONE thread at a time — both reads AND writes exclusive.
    ReadWriteLock: multiple readers simultaneously. Only one writer at a time.
    
    private final ReadWriteLock lock = new ReentrantReadWriteLock();
    
    // Read: acquire read lock (multiple threads can hold read lock simultaneously)
    public int getFollowerCount() {
        lock.readLock().lock();
        try {
            return followers.size();  // can be read by 1000 threads simultaneously
        } finally {
            lock.readLock().unlock();
        }
    }
    
    // Write: acquire write lock (exclusive — waits for all readers to finish)
    public boolean follow(User target) {
        lock.writeLock().lock();
        try {
            return following.add(target.getId());
        } finally {
            lock.writeLock().unlock();
        }
    }
    
    Performance gain: 100× read throughput vs plain synchronized.
    Read-heavy workload (99% reads, 1% writes) → ReadWriteLock is dramatically faster.
    
    When NOT to use ReadWriteLock:
      Write-heavy workloads: write lock contention → worse than synchronized.
      Very short critical sections: overhead of RWLock > benefit.
      Rule of thumb: reads > 10× writes → ReadWriteLock wins.

ATOMIC OPERATIONS IN JAVA — WHEN TO USE WHAT:
  
  AtomicInteger vs volatile vs synchronized:
  
  volatile int counter = 0;
  counter++;  // NOT thread-safe! Three operations: read, increment, write.
  // Thread A reads 5, Thread B reads 5, A writes 6, B writes 6. Incremented ONCE. Wrong.
  
  AtomicInteger counter = new AtomicInteger(0);
  counter.incrementAndGet();  // THREAD-SAFE. Single atomic hardware instruction (LOCK ADD).
  
  int count = counter.get();  // Thread-safe read.
  counter.compareAndSet(expected, newValue);  // CAS: only updates if current == expected.
  
  When to use AtomicInteger:
    Single-field counter that only increments/decrements.
    Like: clickCount, likeCount, retryCount.
  
  When AtomicInteger is NOT enough:
    Need to update TWO related fields atomically.
    E.g., "transfer $100: decrease account A, increase account B" — need synchronized.
    AtomicInteger: each field is atomic, but the COMBINATION isn't. Race condition possible.
    Fix: synchronized block covering BOTH updates, or compare-and-swap loop.

IMMUTABILITY AS A CONCURRENCY TOOL:
  
  Location is a frozen dataclass (Python) / Java record.
  Immutable = no setters = shared freely between threads without locking.
  
  Why immutability is the BEST concurrency solution:
    No mutation → no race condition possible → no locks needed → faster.
  
  Make as many objects immutable as possible:
    All "value objects" (Location, MediaMeta, UrlEntry): immutable. ✓
    All "service objects" (UrlShortener, FeedService): mutable (have state). Use locks.
  
  In Java: use records (Java 16+) for immutable value objects.
  In C++: use const member variables + no setters.
  In Python: use @dataclass(frozen=True).
```

---

## STEP 9 — System Design Upgrade Paths

```
HOW THIS LLD EVOLVES TO PRODUCTION:

LEVEL 1: Single Process (current LLD)
  InMemoryRepository: dict in RAM.
  LRUCache: OrderedDict in process.
  Single thread or very limited concurrency.
  Scale: up to 100K entries. Suitable for demo.

LEVEL 2: Single Machine, Multiple Threads
  Replace dict with PostgreSQL + connection pool (psycopg2/asyncpg).
  Replace LRUCache with Redis (redisio library).
  Uvicorn/Gunicorn: 4 workers × 8 threads = 32 concurrent request handlers.
  Scale: millions of entries, thousands requests/sec.
  Code change: only change what gets INJECTED (Strategy Pattern saves us).
    repo = PostgresUrlRepository(db_pool)  # one line change
    cache = RedisCacheLayer(redis_client)  # one line change
    shortener = UrlShortener(repo, cache)  # zero changes to this class

LEVEL 3: Multi-Machine (Microservices)
  UrlShortener → ShortenService (containerized, stateless, scale horizontally).
  RedirectService → RedirectService (separate container, optimized for reads).
  PostgreSQL → PostgreSQL cluster (1 primary + 3 read replicas + Pgpool-II load balancer).
  Redis → Redis Cluster (6 nodes, 3 primary + 3 replica).
  API Gateway → Kong (handles auth, rate limiting, routing).
  Scale: millions of requests/sec. 99.99% availability.

LEVEL 4: Global Scale (bit.ly / TinyURL scale)
  Database → sharded PostgreSQL (10 shards × consistent hashing).
  CDN → Cloudflare (redirects served at CDN edge, < 5ms globally).
  Analytics → ClickHouse (50B click events/day, < 1s aggregation queries).
  Multi-region → US + EU + APAC (3 regions × full stack).
  Scale: 100M URLs, 10B redirects/day. < 10ms p99 globally.
  Code changes: none to core business logic. Only infra config changes.
  The LLD design held up to 100,000× scale increase. This is the power of good OOP design.

INTERVIEW TIP — HOW TO TRANSITION FROM LLD TO HLD:
  After showing LLD code, interviewer asks "how would this scale?"
  
  1. Identify the bottleneck (InMemoryRepository can't handle 578K reads/sec).
  2. Replace the specific component (not the entire system):
     "I'd replace InMemoryUrlRepository with a sharded PostgreSQL repository.
     The IUrlRepository interface means UrlShortener doesn't change at all."
  3. Discuss the HLD implications (sharding, caching, CDN) in terms of your LLD design.
  4. Show you understand the PROGRESSION from clean OOP to distributed systems.
  
  This answer demonstrates: LLD mastery + HLD thinking + evolutionary design mindset.
  MAANG interviewers specifically look for this progression.
```

# CS02: LLD — Instagram
## Class Design, Patterns, Full Code | Python + Java + C++

---

## STEP 1 — Requirements & Entities

```
FUNCTIONAL (LLD scope):
  1. User registers, logs in, updates profile
  2. Upload photo/video as a Post (with caption, tags, location)
  3. Follow / Unfollow another user
  4. Like / Unlike a post
  5. Comment on a post (nested comments)
  6. View feed (posts from followed users, sorted by time)
  7. View notifications (likes, comments, follows)
  8. Search users and hashtags

KEY ENTITIES (nouns → classes):
  User           — profile, follower graph node
  Post           — media + metadata
  Comment        — nested tree on a post
  Like           — association User × Post
  FollowRelation — directed edge User → User
  Feed           — ordered list of posts for a user
  Notification   — event log for a user
  HashTag        — indexed tag associated with posts
  MediaUploader  — handles chunked media upload

KEY BEHAVIOURS:
  User.follow(target)               → FollowRelation
  User.unfollow(target)             → bool
  Post.like(user) / Post.unlike()   → bool
  Post.addComment(user, text)       → Comment
  FeedService.getFeed(userId)       → List[Post]
  NotificationService.notify(event) → None
  SearchService.searchUsers(query)  → List[User]
  SearchService.searchTags(query)   → List[HashTag]
```

---

## STEP 2 — Class Diagram (UML ASCII)

```
[User]                      [Post]                       [Comment]
──────                      ──────                       ─────────
- id: UUID                  - id: UUID                   - id: UUID
- username: str             - author: User               - author: User
- email: str                - mediaUrl: str              - post: Post
- passwordHash: str         - caption: str               - parentComment: Comment?
- bio: str                  - tags: List[HashTag]        - text: str
- avatarUrl: str            - location: str              - createdAt: datetime
- createdAt: datetime       - likeCount: int (cache)     - likeCount: int
──────                      - commentCount: int          - replies: List[Comment]
+ follow(User): bool        - createdAt: datetime        ─────────
+ unfollow(User): bool      - isDeleted: bool            + addReply(Comment): void
+ isFollowing(User): bool   ──────                       + delete(): void
+ getFollowers(): List      + like(User): bool
+ getFollowing(): List      + unlike(User): bool         [Like]
+ updateProfile(): void     + addComment(User,str): Comment  ──────
                            + deleteComment(cid): bool   - userId: UUID
[FollowRelation]            + getComments(): List        - postId: UUID
─────────────               + getTags(): List            - createdAt: datetime
- followerId: UUID
- followeeId: UUID          [HashTag]                    [Notification]
- createdAt: datetime       ─────────                    ─────────────
                            - tag: str                   - id: UUID
[Feed]                      - postCount: int             - recipientId: UUID
──────                      ─────────                    - type: NotifType
- userId: UUID              + getTopPosts(): List        - actorId: UUID
- posts: List[Post]                                      - postId: UUID?
- lastRefreshed: datetime   [MediaUploader]              - isRead: bool
──────                      ─────────────                - createdAt: datetime
+ refresh(): void           - chunkSize: int
+ paginate(page,n): List    - uploadedChunks: dict
                            ─────────────
                            + initiateUpload(meta): str
                            + uploadChunk(id,n,data): bool
                            + finalizeUpload(id): str
                            + getUploadProgress(id): float

RELATIONSHIPS:
  User 1 ──◆ * Post           (Composition: post owned by user)
  Post 1 ──◆ * Comment        (Composition: comment owned by post)
  Comment ──► Comment?        (Self-referential: reply tree)
  User * ──► * User           (FollowRelation: many-to-many)
  User * ──► * Post           (Like: many-to-many via Like entity)
  Post * ──◆ * HashTag        (Aggregation: tag exists independently)
  User ──► * Notification     (Aggregation)

PATTERNS USED:
  Observer    → NotificationService observes Post events (like, comment)
  Strategy    → FeedStrategy (ChronologicalFeed vs RankedFeed)
  Builder     → PostBuilder (complex post creation with optional fields)
  Composite   → Comment tree (leaf Comment vs CommentNode with replies)
  Facade      → InstagramService (hides all sub-services)
  Repository  → IUserRepository, IPostRepository (DIP-compliant)
  Factory     → NotificationFactory (creates correct Notification subtype)
```

---

## STEP 3 — Python Implementation (Deep)

```python
# instagram_lld.py
from __future__ import annotations
import uuid
import time
import threading
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional, List, Dict, Callable
from collections import defaultdict


# ── ENUMS ─────────────────────────────────────────────────────────────────────

class NotifType(Enum):
    LIKE    = auto()
    COMMENT = auto()
    FOLLOW  = auto()
    MENTION = auto()

class PostVisibility(Enum):
    PUBLIC  = auto()
    PRIVATE = auto()
    FRIENDS = auto()


# ── VALUE OBJECTS ─────────────────────────────────────────────────────────────

@dataclass
class MediaMeta:
    """Immutable metadata about a media file."""
    url:         str
    mime_type:   str          # "image/jpeg", "video/mp4"
    size_bytes:  int
    width:       int = 0
    height:      int = 0
    duration_ms: int = 0      # for videos

@dataclass(frozen=True)
class Location:
    """Immutable GPS + display name."""
    latitude:  float
    longitude: float
    name:      str = ""


# ── DOMAIN ENTITIES ───────────────────────────────────────────────────────────

class User:
    def __init__(self, username: str, email: str, password: str):
        self.id            = str(uuid.uuid4())
        self.username      = username
        self.email         = email
        self._password_hash = self._hash(password)
        self.bio           = ""
        self.avatar_url    = ""
        self.created_at    = datetime.utcnow()
        self.is_private    = False
        self._followers: set[str] = set()   # user IDs
        self._following: set[str] = set()

    @staticmethod
    def _hash(password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    def verify_password(self, password: str) -> bool:
        return self._password_hash == self._hash(password)

    def follow(self, target: User) -> bool:
        if target.id == self.id:
            return False                        # can't follow self
        if target.id in self._following:
            return False                        # already following
        self._following.add(target.id)
        target._followers.add(self.id)
        return True

    def unfollow(self, target: User) -> bool:
        if target.id not in self._following:
            return False
        self._following.discard(target.id)
        target._followers.discard(self.id)
        return True

    def is_following(self, target: User) -> bool:
        return target.id in self._following

    @property
    def follower_count(self) -> int: return len(self._followers)

    @property
    def following_count(self) -> int: return len(self._following)

    def __repr__(self) -> str:
        return f"User(@{self.username})"


class HashTag:
    def __init__(self, tag: str):
        self.tag        = tag.lower().lstrip('#')
        self.post_count = 0
        self._post_ids: list[str] = []

    def add_post(self, post_id: str) -> None:
        self._post_ids.append(post_id)
        self.post_count += 1

    def get_top_posts(self, limit: int = 20) -> list[str]:
        return self._post_ids[-limit:]   # simplification: recency = top

    def __repr__(self) -> str:
        return f"#{self.tag}({self.post_count})"


class Comment:
    """
    COMPOSITE PATTERN:
      - Leaf: comment with no replies
      - Node: comment with a list of child Comments
    Both share the same interface.
    """
    def __init__(self, author: User, post_id: str, text: str,
                 parent: Optional[Comment] = None):
        self.id             = str(uuid.uuid4())
        self.author         = author
        self.post_id        = post_id
        self.text           = text
        self.parent         = parent           # None = top-level comment
        self.replies:  List[Comment] = []
        self.like_count     = 0
        self.created_at     = datetime.utcnow()
        self.is_deleted     = False

    def add_reply(self, reply: Comment) -> None:
        if self.is_deleted:
            raise ValueError("Cannot reply to a deleted comment")
        self.replies.append(reply)

    def delete(self) -> None:
        self.is_deleted = True
        self.text = "[deleted]"       # soft-delete; replies still visible

    def total_reply_count(self) -> int:
        """Recursive count — works for any depth."""
        return len(self.replies) + sum(
            r.total_reply_count() for r in self.replies
        )

    def __repr__(self) -> str:
        return f"Comment({self.author.username}: {self.text[:30]!r})"


class Like:
    def __init__(self, user_id: str, post_id: str):
        self.user_id    = user_id
        self.post_id    = post_id
        self.created_at = datetime.utcnow()


class Post:
    """
    BUILDER PATTERN used for Post construction.
    Post itself is the product; PostBuilder handles optional params.
    """
    def __init__(self, author: User, media: MediaMeta, caption: str):
        self.id           = str(uuid.uuid4())
        self.author       = author
        self.media        = media
        self.caption      = caption
        self.tags:  List[HashTag] = []
        self.location: Optional[Location] = None
        self.visibility   = PostVisibility.PUBLIC
        self.created_at   = datetime.utcnow()
        self.is_deleted   = False

        self._likes: Dict[str, Like] = {}           # user_id → Like
        self._comments: List[Comment] = []
        self._lock = threading.RLock()

    # ── Like operations (thread-safe) ─────────────────────────────────────────
    def like(self, user: User) -> bool:
        with self._lock:
            if user.id in self._likes:
                return False                        # already liked
            self._likes[user.id] = Like(user.id, self.id)
            return True

    def unlike(self, user: User) -> bool:
        with self._lock:
            if user.id not in self._likes:
                return False
            del self._likes[user.id]
            return True

    def is_liked_by(self, user: User) -> bool:
        with self._lock:
            return user.id in self._likes

    @property
    def like_count(self) -> int:
        with self._lock:
            return len(self._likes)

    # ── Comment operations ────────────────────────────────────────────────────
    def add_comment(self, author: User, text: str,
                    parent_id: Optional[str] = None) -> Comment:
        with self._lock:
            parent = self._find_comment(parent_id) if parent_id else None
            comment = Comment(author, self.id, text, parent)
            if parent:
                parent.add_reply(comment)
            else:
                self._comments.append(comment)
            return comment

    def delete_comment(self, comment_id: str, requestor: User) -> bool:
        with self._lock:
            comment = self._find_comment(comment_id)
            if not comment:
                return False
            if comment.author.id != requestor.id and self.author.id != requestor.id:
                raise PermissionError("Only author or post owner can delete")
            comment.delete()
            return True

    def get_top_level_comments(self) -> List[Comment]:
        with self._lock:
            return [c for c in self._comments if not c.is_deleted]

    def _find_comment(self, comment_id: str) -> Optional[Comment]:
        """BFS search through nested comments."""
        queue = list(self._comments)
        while queue:
            c = queue.pop(0)
            if c.id == comment_id:
                return c
            queue.extend(c.replies)
        return None

    @property
    def comment_count(self) -> int:
        with self._lock:
            return sum(1 + c.total_reply_count() for c in self._comments
                       if not c.is_deleted)

    def __repr__(self) -> str:
        return f"Post({self.author.username}, ❤{self.like_count})"


# ── POST BUILDER ──────────────────────────────────────────────────────────────

class PostBuilder:
    """
    Builder Pattern: Step-by-step construction of a Post.
    Handles all optional fields cleanly.
    """
    def __init__(self, author: User, media: MediaMeta, caption: str):
        self._author  = author
        self._media   = media
        self._caption = caption
        self._tags:     List[HashTag]       = []
        self._location: Optional[Location] = None
        self._visibility = PostVisibility.PUBLIC

    def with_tags(self, tags: List[HashTag]) -> PostBuilder:
        self._tags = tags
        return self

    def with_location(self, location: Location) -> PostBuilder:
        self._location = location
        return self

    def with_visibility(self, visibility: PostVisibility) -> PostBuilder:
        self._visibility = visibility
        return self

    def build(self) -> Post:
        post = Post(self._author, self._media, self._caption)
        post.tags     = self._tags
        post.location = self._location
        post.visibility = self._visibility
        for tag in self._tags:
            tag.add_post(post.id)
        return post


# ── NOTIFICATION SYSTEM (Observer Pattern) ────────────────────────────────────

class Notification:
    def __init__(self, recipient_id: str, notif_type: NotifType,
                 actor: User, post: Optional[Post] = None):
        self.id           = str(uuid.uuid4())
        self.recipient_id = recipient_id
        self.type         = notif_type
        self.actor        = actor
        self.post         = post
        self.is_read      = False
        self.created_at   = datetime.utcnow()

    def mark_read(self) -> None:
        self.is_read = True

    def __repr__(self) -> str:
        return f"Notif({self.type.name} from @{self.actor.username})"


class INotificationObserver(ABC):
    @abstractmethod
    def on_event(self, event_type: NotifType, actor: User,
                 recipient: User, post: Optional[Post]) -> None: ...


class NotificationService(INotificationObserver):
    """
    OBSERVER: Receives events from posts/users and creates notifications.
    Also manages the inbox per user.
    """
    def __init__(self):
        self._inbox: Dict[str, List[Notification]] = defaultdict(list)
        self._lock  = threading.RLock()

    def on_event(self, event_type: NotifType, actor: User,
                 recipient: User, post: Optional[Post] = None) -> None:
        if actor.id == recipient.id:
            return                                  # don't notify self
        notif = Notification(recipient.id, event_type, actor, post)
        with self._lock:
            self._inbox[recipient.id].insert(0, notif)
            # keep max 200 notifications
            self._inbox[recipient.id] = self._inbox[recipient.id][:200]

    def get_notifications(self, user_id: str,
                          unread_only: bool = False) -> List[Notification]:
        with self._lock:
            notifs = self._inbox.get(user_id, [])
            return [n for n in notifs if not n.is_read] if unread_only else list(notifs)

    def mark_all_read(self, user_id: str) -> None:
        with self._lock:
            for n in self._inbox.get(user_id, []):
                n.mark_read()

    def unread_count(self, user_id: str) -> int:
        with self._lock:
            return sum(1 for n in self._inbox.get(user_id, []) if not n.is_read)


# ── FEED SERVICE (Strategy Pattern) ──────────────────────────────────────────

class IFeedStrategy(ABC):
    @abstractmethod
    def build_feed(self, user: User, posts: List[Post],
                   limit: int) -> List[Post]: ...

class ChronologicalFeed(IFeedStrategy):
    """Simple: newest first. O(n log n) sort."""
    def build_feed(self, user: User, posts: List[Post],
                   limit: int) -> List[Post]:
        sorted_posts = sorted(posts, key=lambda p: p.created_at, reverse=True)
        return sorted_posts[:limit]

class RankedFeed(IFeedStrategy):
    """
    Engagement-ranked: score = likes * 2 + comments * 3 - age_penalty.
    In prod: ML model scores each post.
    """
    def build_feed(self, user: User, posts: List[Post],
                   limit: int) -> List[Post]:
        now = datetime.utcnow()

        def score(p: Post) -> float:
            age_hours = (now - p.created_at).total_seconds() / 3600
            return p.like_count * 2 + p.comment_count * 3 - age_hours * 0.5

        return sorted(posts, key=score, reverse=True)[:limit]


class FeedService:
    def __init__(self, strategy: IFeedStrategy = None):
        self._strategy = strategy or ChronologicalFeed()
        # In-memory post store keyed by author_id:
        self._posts: Dict[str, List[Post]] = defaultdict(list)
        self._lock  = threading.RLock()

    def set_strategy(self, strategy: IFeedStrategy) -> None:
        self._strategy = strategy

    def add_post(self, post: Post) -> None:
        with self._lock:
            self._posts[post.author.id].insert(0, post)

    def get_feed(self, user: User, limit: int = 20) -> List[Post]:
        with self._lock:
            candidate_posts: List[Post] = []
            for followed_id in user._following:
                candidate_posts.extend(self._posts.get(followed_id, []))
        return self._strategy.build_feed(user, candidate_posts, limit)


# ── MEDIA UPLOADER (Chunked Upload) ──────────────────────────────────────────

class UploadSession:
    def __init__(self, upload_id: str, total_size: int, mime_type: str):
        self.upload_id    = upload_id
        self.total_size   = total_size
        self.mime_type    = mime_type
        self.chunks: Dict[int, bytes] = {}
        self.started_at   = datetime.utcnow()
        self.finalized    = False

    def progress(self) -> float:
        if self.total_size == 0: return 0.0
        return min(sum(len(c) for c in self.chunks.values()) / self.total_size, 1.0)


class MediaUploader:
    CHUNK_SIZE = 5 * 1024 * 1024   # 5 MB chunks (like S3 multipart)

    def __init__(self):
        self._sessions: Dict[str, UploadSession] = {}
        self._lock = threading.RLock()

    def initiate_upload(self, total_size: int, mime_type: str) -> str:
        upload_id = str(uuid.uuid4())
        with self._lock:
            self._sessions[upload_id] = UploadSession(upload_id, total_size, mime_type)
        return upload_id

    def upload_chunk(self, upload_id: str, chunk_num: int, data: bytes) -> bool:
        with self._lock:
            session = self._sessions.get(upload_id)
            if not session or session.finalized:
                return False
            session.chunks[chunk_num] = data
            return True

    def get_progress(self, upload_id: str) -> float:
        with self._lock:
            session = self._sessions.get(upload_id)
            return session.progress() if session else 0.0

    def finalize_upload(self, upload_id: str) -> Optional[str]:
        with self._lock:
            session = self._sessions.get(upload_id)
            if not session or session.finalized:
                return None
            # In prod: assemble chunks → S3/GCS → return CDN URL
            session.finalized = True
            url = f"https://cdn.instagram.com/{upload_id}"
            return url


# ── SEARCH SERVICE ────────────────────────────────────────────────────────────

class SearchService:
    def __init__(self):
        self._users: Dict[str, User] = {}       # username → User
        self._tags:  Dict[str, HashTag] = {}    # tag → HashTag
        self._lock   = threading.RLock()

    def index_user(self, user: User) -> None:
        with self._lock:
            self._users[user.username.lower()] = user

    def index_tag(self, tag: HashTag) -> None:
        with self._lock:
            self._tags[tag.tag.lower()] = tag

    def search_users(self, query: str) -> List[User]:
        q = query.lower()
        with self._lock:
            return [u for un, u in self._users.items() if q in un]

    def search_tags(self, query: str) -> List[HashTag]:
        q = query.lower().lstrip('#')
        with self._lock:
            return [t for tk, t in self._tags.items() if q in tk]


# ── INSTAGRAM FACADE ──────────────────────────────────────────────────────────

class InstagramService:
    """
    FACADE: Single entry point. Hides all sub-services.
    Client code only talks to InstagramService.
    """
    def __init__(self):
        self._users:    Dict[str, User] = {}      # user_id → User
        self._posts:    Dict[str, Post] = {}      # post_id → Post
        self._tags:     Dict[str, HashTag] = {}
        self._notif     = NotificationService()
        self._feed      = FeedService(ChronologicalFeed())
        self._uploader  = MediaUploader()
        self._search    = SearchService()
        self._lock      = threading.RLock()

    # ── User Management ───────────────────────────────────────────────────────
    def register(self, username: str, email: str, password: str) -> User:
        with self._lock:
            if any(u.username == username for u in self._users.values()):
                raise ValueError(f"Username '{username}' already taken")
            user = User(username, email, password)
            self._users[user.id] = user
            self._search.index_user(user)
            return user

    def follow(self, actor: User, target: User) -> bool:
        success = actor.follow(target)
        if success:
            self._notif.on_event(NotifType.FOLLOW, actor, target)
        return success

    def unfollow(self, actor: User, target: User) -> bool:
        return actor.unfollow(target)

    # ── Post Management ───────────────────────────────────────────────────────
    def create_post(self, author: User, media: MediaMeta, caption: str,
                    tag_names: List[str] = None,
                    location: Location = None) -> Post:
        tags = []
        if tag_names:
            for name in tag_names:
                tag = self._get_or_create_tag(name)
                tags.append(tag)

        builder = (
            PostBuilder(author, media, caption)
            .with_tags(tags)
        )
        if location:
            builder = builder.with_location(location)

        post = builder.build()
        with self._lock:
            self._posts[post.id] = post
        self._feed.add_post(post)

        # extract @mentions from caption and notify
        self._notify_mentions(caption, author, post)
        return post

    def like_post(self, user: User, post: Post) -> bool:
        success = post.like(user)
        if success:
            self._notif.on_event(NotifType.LIKE, user, post.author, post)
        return success

    def comment_on_post(self, user: User, post: Post, text: str,
                        parent_id: str = None) -> Comment:
        comment = post.add_comment(user, text, parent_id)
        self._notif.on_event(NotifType.COMMENT, user, post.author, post)
        self._notify_mentions(text, user, post)
        return comment

    def get_feed(self, user: User, limit: int = 20) -> List[Post]:
        return self._feed.get_feed(user, limit)

    def get_notifications(self, user: User,
                          unread_only: bool = False) -> List[Notification]:
        return self._notif.get_notifications(user.id, unread_only)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _get_or_create_tag(self, name: str) -> HashTag:
        name = name.lower().lstrip('#')
        with self._lock:
            if name not in self._tags:
                self._tags[name] = HashTag(name)
                self._search.index_tag(self._tags[name])
            return self._tags[name]

    def _notify_mentions(self, text: str, actor: User,
                         post: Post) -> None:
        for word in text.split():
            if word.startswith('@'):
                username = word[1:].rstrip('.,!?')
                target = next((u for u in self._users.values()
                               if u.username == username), None)
                if target:
                    self._notif.on_event(NotifType.MENTION, actor, target, post)


# ── DEMO ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    insta = InstagramService()

    # Users
    alice = insta.register("alice", "alice@ig.com", "pass123")
    bob   = insta.register("bob",   "bob@ig.com",   "pass456")
    carol = insta.register("carol", "carol@ig.com", "pass789")

    # Follow
    insta.follow(alice, bob)
    insta.follow(carol, bob)
    print(f"Bob followers: {bob.follower_count}")  # 2

    # Post
    media = MediaMeta("https://s3/photo.jpg", "image/jpeg", 1_200_000, 1080, 1080)
    post  = insta.create_post(bob, media, "Beautiful day! @alice #nature #travel",
                              tag_names=["nature", "travel"],
                              location=Location(28.6, 77.2, "New Delhi"))
    print(f"Post: {post}")

    # Like & Comment
    insta.like_post(alice, post)
    insta.like_post(carol, post)
    c1 = insta.comment_on_post(alice, post, "Amazing shot!")
    c2 = insta.comment_on_post(carol, post, "Love it!", parent_id=c1.id)  # reply
    print(f"Likes: {post.like_count}, Comments: {post.comment_count}")

    # Feed
    feed = insta.get_feed(alice)
    print(f"Alice's feed: {[str(p) for p in feed]}")

    # Notifications for Bob
    notifs = insta.get_notifications(bob)
    print(f"Bob's notifications ({len(notifs)}):")
    for n in notifs:
        print(f"  {n}")
```

---

## STEP 4 — Java Implementation (Deep)

```java
// instagram_lld.java — Production-depth Java LLD

import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.concurrent.locks.*;
import java.time.Instant;
import java.util.stream.*;
import java.util.function.*;

// ── ENUMS ─────────────────────────────────────────────────────────────────────
enum NotifType   { LIKE, COMMENT, FOLLOW, MENTION }
enum PostVisibility { PUBLIC, PRIVATE, FRIENDS }

// ── VALUE OBJECTS (Records — Java 16+) ────────────────────────────────────────
record MediaMeta(String url, String mimeType, long sizeBytes, int width, int height, int durationMs) {}
record Location(double lat, double lng, String name) {}

// ── USER ──────────────────────────────────────────────────────────────────────
class User {
    private final String id = UUID.randomUUID().toString();
    private final String username, email;
    private String passwordHash, bio = "", avatarUrl = "";
    private final Instant createdAt = Instant.now();
    private final Set<String> followers = ConcurrentHashMap.newKeySet();
    private final Set<String> following = ConcurrentHashMap.newKeySet();

    public User(String username, String email, String password) {
        this.username     = username;
        this.email        = email;
        this.passwordHash = hash(password);
    }

    private String hash(String pw) {
        try {
            var md = java.security.MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(md.digest(pw.getBytes()));
        } catch (Exception e) { throw new RuntimeException(e); }
    }

    public boolean follow(User target) {
        if (target.id.equals(this.id)) return false;
        if (!following.add(target.id)) return false;
        target.followers.add(this.id);
        return true;
    }

    public boolean unfollow(User target) {
        if (!following.remove(target.id)) return false;
        target.followers.remove(this.id);
        return true;
    }

    public boolean isFollowing(User target) { return following.contains(target.id); }
    public Set<String> getFollowing()       { return Collections.unmodifiableSet(following); }
    public int getFollowerCount()           { return followers.size(); }
    public String getId()                   { return id; }
    public String getUsername()             { return username; }
    @Override public String toString()      { return "@" + username; }
}

// ── COMMENT (Composite Pattern) ───────────────────────────────────────────────
class Comment {
    private final String id       = UUID.randomUUID().toString();
    private final User   author;
    private final String postId;
    private volatile String text;
    private final Comment parent;     // null = top-level
    private final List<Comment> replies = new CopyOnWriteArrayList<>();
    private final AtomicInteger likeCount = new AtomicInteger(0);
    private volatile boolean deleted = false;
    private final Instant createdAt = Instant.now();

    public Comment(User author, String postId, String text, Comment parent) {
        this.author = author; this.postId = postId;
        this.text   = text;   this.parent = parent;
    }

    public void addReply(Comment reply) {
        if (deleted) throw new IllegalStateException("Cannot reply to deleted comment");
        replies.add(reply);
    }

    public void softDelete() { deleted = true; text = "[deleted]"; }

    public int totalReplyCount() {
        return replies.size() + replies.stream()
            .mapToInt(Comment::totalReplyCount).sum();
    }

    public List<Comment> getReplies()  { return Collections.unmodifiableList(replies); }
    public String getId()              { return id; }
    public User getAuthor()            { return author; }
    public String getText()            { return text; }
    public boolean isDeleted()         { return deleted; }
}

// ── POST ──────────────────────────────────────────────────────────────────────
class Post {
    private final String id = UUID.randomUUID().toString();
    private final User author;
    private final MediaMeta media;
    private final String caption;
    private List<String> tagNames = new ArrayList<>();
    private Location location;
    private PostVisibility visibility = PostVisibility.PUBLIC;
    private final Instant createdAt = Instant.now();

    // Thread-safe internals
    private final Map<String, Instant> likes = new ConcurrentHashMap<>();
    private final List<Comment> comments      = new CopyOnWriteArrayList<>();
    private final ReadWriteLock lock          = new ReentrantReadWriteLock();

    // Package-private for Builder
    Post(User author, MediaMeta media, String caption) {
        this.author  = author;
        this.media   = media;
        this.caption = caption;
    }

    public boolean like(User user) {
        return likes.putIfAbsent(user.getId(), Instant.now()) == null;
    }

    public boolean unlike(User user) {
        return likes.remove(user.getId()) != null;
    }

    public int getLikeCount() { return likes.size(); }

    public Comment addComment(User author, String text, Comment parent) {
        Comment c = new Comment(author, id, text, parent);
        if (parent != null) parent.addReply(c);
        else comments.add(c);
        return c;
    }

    public Optional<Comment> findComment(String commentId) {
        // BFS through comment tree
        Queue<Comment> queue = new LinkedList<>(comments);
        while (!queue.isEmpty()) {
            Comment c = queue.poll();
            if (c.getId().equals(commentId)) return Optional.of(c);
            queue.addAll(c.getReplies());
        }
        return Optional.empty();
    }

    public int getCommentCount() {
        return comments.stream().mapToInt(c -> 1 + c.totalReplyCount()).sum();
    }

    public User getAuthor()    { return author; }
    public String getId()      { return id; }
    public Instant getCreatedAt() { return createdAt; }
    public List<Comment> getTopLevelComments() { return comments; }
    @Override public String toString() {
        return String.format("Post(%s, ❤%d)", author, getLikeCount());
    }
}

// ── POST BUILDER ──────────────────────────────────────────────────────────────
class PostBuilder {
    private final User author; private final MediaMeta media; private final String caption;
    private List<String> tagNames = new ArrayList<>();
    private Location location;
    private PostVisibility visibility = PostVisibility.PUBLIC;

    public PostBuilder(User author, MediaMeta media, String caption) {
        this.author = author; this.media = media; this.caption = caption;
    }
    public PostBuilder withTags(List<String> tags) { tagNames = tags; return this; }
    public PostBuilder withLocation(Location loc)  { location = loc;  return this; }
    public PostBuilder withVisibility(PostVisibility v) { visibility = v; return this; }

    public Post build() {
        Post p = new Post(author, media, caption);
        p.tagNames   = tagNames;
        p.location   = location;
        p.visibility = visibility;
        return p;
    }
}

// ── NOTIFICATION ──────────────────────────────────────────────────────────────
record Notification(String id, String recipientId, NotifType type,
                    User actor, Post post, Instant createdAt, boolean isRead) {
    public Notification { id = UUID.randomUUID().toString(); }
    Notification(String recipientId, NotifType type, User actor, Post post) {
        this(null, recipientId, type, actor, post, Instant.now(), false);
    }
    Notification markRead() {
        return new Notification(id, recipientId, type, actor, post, createdAt, true);
    }
}

// ── OBSERVER INTERFACE ────────────────────────────────────────────────────────
interface NotificationObserver {
    void onEvent(NotifType type, User actor, User recipient, Post post);
}

// ── NOTIFICATION SERVICE ──────────────────────────────────────────────────────
class NotificationService implements NotificationObserver {
    private final Map<String, List<Notification>> inbox = new ConcurrentHashMap<>();
    private static final int MAX_NOTIF = 200;

    @Override
    public void onEvent(NotifType type, User actor, User recipient, Post post) {
        if (actor.getId().equals(recipient.getId())) return;
        inbox.computeIfAbsent(recipient.getId(), k -> new CopyOnWriteArrayList<>())
             .add(0, new Notification(recipient.getId(), type, actor, post));
        trimInbox(recipient.getId());
    }

    private void trimInbox(String userId) {
        List<Notification> list = inbox.get(userId);
        if (list != null && list.size() > MAX_NOTIF)
            list.subList(MAX_NOTIF, list.size()).clear();
    }

    public List<Notification> getNotifications(String userId, boolean unreadOnly) {
        var list = inbox.getOrDefault(userId, List.of());
        return unreadOnly ? list.stream().filter(n -> !n.isRead()).toList() : list;
    }

    public long unreadCount(String userId) {
        return getNotifications(userId, true).size();
    }
}

// ── FEED STRATEGY ─────────────────────────────────────────────────────────────
interface FeedStrategy {
    List<Post> buildFeed(User user, List<Post> candidates, int limit);
}

class ChronologicalFeed implements FeedStrategy {
    public List<Post> buildFeed(User user, List<Post> posts, int limit) {
        return posts.stream()
            .sorted(Comparator.comparing(Post::getCreatedAt).reversed())
            .limit(limit).toList();
    }
}

class RankedFeed implements FeedStrategy {
    public List<Post> buildFeed(User user, List<Post> posts, int limit) {
        Instant now = Instant.now();
        return posts.stream()
            .sorted(Comparator.comparingDouble(p -> -score(p, now)))
            .limit(limit).toList();
    }
    private double score(Post p, Instant now) {
        double ageHours = (now.toEpochMilli() - p.getCreatedAt().toEpochMilli()) / 3_600_000.0;
        return p.getLikeCount() * 2.0 + p.getCommentCount() * 3.0 - ageHours * 0.5;
    }
}

// ── FEED SERVICE ──────────────────────────────────────────────────────────────
class FeedService {
    private FeedStrategy strategy;
    private final Map<String, List<Post>> postsByAuthor = new ConcurrentHashMap<>();

    public FeedService(FeedStrategy strategy) { this.strategy = strategy; }
    public void setStrategy(FeedStrategy s)   { this.strategy = s; }

    public void addPost(Post p) {
        postsByAuthor.computeIfAbsent(p.getAuthor().getId(),
                                      k -> new CopyOnWriteArrayList<>()).add(0, p);
    }

    public List<Post> getFeed(User user, int limit) {
        List<Post> candidates = user.getFollowing().stream()
            .flatMap(fid -> postsByAuthor.getOrDefault(fid, List.of()).stream())
            .collect(Collectors.toList());
        return strategy.buildFeed(user, candidates, limit);
    }
}

// ── INSTAGRAM FACADE ──────────────────────────────────────────────────────────
class InstagramService {
    private final Map<String, User> usersById   = new ConcurrentHashMap<>();
    private final Map<String, Post> postsById   = new ConcurrentHashMap<>();
    private final NotificationService notif     = new NotificationService();
    private final FeedService         feed      = new FeedService(new ChronologicalFeed());

    public User register(String username, String email, String password) {
        boolean taken = usersById.values().stream()
            .anyMatch(u -> u.getUsername().equals(username));
        if (taken) throw new IllegalArgumentException("Username taken: " + username);
        User u = new User(username, email, password);
        usersById.put(u.getId(), u);
        return u;
    }

    public boolean follow(User actor, User target) {
        boolean ok = actor.follow(target);
        if (ok) notif.onEvent(NotifType.FOLLOW, actor, target, null);
        return ok;
    }

    public Post createPost(User author, MediaMeta media, String caption,
                           List<String> tags, Location loc) {
        Post post = new PostBuilder(author, media, caption)
            .withTags(tags).withLocation(loc).build();
        postsById.put(post.getId(), post);
        feed.addPost(post);
        notifyMentions(caption, author, post);
        return post;
    }

    public boolean likePost(User user, Post post) {
        boolean ok = post.like(user);
        if (ok) notif.onEvent(NotifType.LIKE, user, post.getAuthor(), post);
        return ok;
    }

    public Comment commentOnPost(User user, Post post, String text, Comment parent) {
        Comment c = post.addComment(user, text, parent);
        notif.onEvent(NotifType.COMMENT, user, post.getAuthor(), post);
        return c;
    }

    public List<Post>         getFeed(User u, int n) { return feed.getFeed(u, n); }
    public List<Notification> getNotifications(User u, boolean unread) {
        return notif.getNotifications(u.getId(), unread);
    }

    private void notifyMentions(String text, User actor, Post post) {
        for (String word : text.split("\\s+")) {
            if (word.startsWith("@")) {
                String username = word.substring(1).replaceAll("[.,!?]$", "");
                usersById.values().stream()
                    .filter(u -> u.getUsername().equals(username))
                    .findFirst()
                    .ifPresent(target ->
                        notif.onEvent(NotifType.MENTION, actor, target, post));
            }
        }
    }
}

// ── DEMO ──────────────────────────────────────────────────────────────────────
class InstagramMain {
    public static void main(String[] args) {
        var insta = new InstagramService();
        var alice = insta.register("alice", "a@ig.com", "pass");
        var bob   = insta.register("bob",   "b@ig.com", "pass");
        var carol = insta.register("carol", "c@ig.com", "pass");

        insta.follow(alice, bob);
        insta.follow(carol, bob);
        System.out.println("Bob followers: " + bob.getFollowerCount()); // 2

        var media = new MediaMeta("cdn/photo.jpg", "image/jpeg", 1200000, 1080, 1080, 0);
        var post  = insta.createPost(bob, media,
            "Beautiful day! @alice #nature", List.of("nature"), new Location(28.6, 77.2, "Delhi"));

        insta.likePost(alice, post);
        insta.likePost(carol, post);
        var c1 = insta.commentOnPost(alice, post, "Amazing!", null);
        insta.commentOnPost(carol, post, "Love it!", c1);

        System.out.println("Post: " + post);
        System.out.printf("Likes: %d, Comments: %d%n", post.getLikeCount(), post.getCommentCount());

        var notifs = insta.getNotifications(bob, false);
        notifs.forEach(n -> System.out.println("  " + n.type() + " from " + n.actor()));
    }
}
```

---

## STEP 5 — C++ Implementation (Deep)

```cpp
// instagram_lld.cpp
// g++ -std=c++20 -pthread instagram_lld.cpp -o instagram
#include <iostream>
#include <string>
#include <vector>
#include <unordered_map>
#include <unordered_set>
#include <memory>
#include <mutex>
#include <shared_mutex>
#include <atomic>
#include <algorithm>
#include <functional>
#include <chrono>
#include <sstream>
#include <queue>
#include <optional>
#include <variant>

using Clock = std::chrono::system_clock;
using TP    = std::chrono::time_point<Clock>;

// ── Forward declarations ───────────────────────────────────────────────────────
class User; class Post; class Comment;

// ── Enums ─────────────────────────────────────────────────────────────────────
enum class NotifType { LIKE, COMMENT, FOLLOW, MENTION };
enum class PostVisibility { PUBLIC, PRIVATE, FRIENDS };

// ── Value Objects ─────────────────────────────────────────────────────────────
struct MediaMeta {
    std::string url, mimeType;
    long sizeBytes{0};
    int width{0}, height{0}, durationMs{0};
};

struct Location {
    double lat{0}, lng{0};
    std::string name;
};

// ── Comment (Composite) ───────────────────────────────────────────────────────
class Comment : public std::enable_shared_from_this<Comment> {
    std::string  id_;
    std::weak_ptr<User>    author_;
    std::string  postId_, text_;
    std::weak_ptr<Comment> parent_;   // weak to avoid cycles
    std::vector<std::shared_ptr<Comment>> replies_;
    std::atomic<int> likeCount_{0};
    bool         deleted_{false};
    TP           createdAt_;
    mutable std::shared_mutex mtx_;

public:
    Comment(std::shared_ptr<User> author, std::string postId,
            std::string text, std::shared_ptr<Comment> parent = nullptr);

    void addReply(std::shared_ptr<Comment> reply) {
        if (deleted_) throw std::runtime_error("Cannot reply to deleted comment");
        std::unique_lock lk(mtx_);
        replies_.push_back(reply);
    }

    void softDelete() {
        std::unique_lock lk(mtx_);
        deleted_ = true; text_ = "[deleted]";
    }

    int totalReplyCount() const {
        std::shared_lock lk(mtx_);
        int count = (int)replies_.size();
        for (auto& r : replies_) count += r->totalReplyCount();
        return count;
    }

    const std::string& getId()   const { return id_; }
    const std::string& getText() const { return text_; }
    bool isDeleted()             const { return deleted_; }

    std::vector<std::shared_ptr<Comment>> getReplies() const {
        std::shared_lock lk(mtx_);
        return replies_;
    }
};

// ── User ──────────────────────────────────────────────────────────────────────
class User : public std::enable_shared_from_this<User> {
    std::string id_, username_, email_, passwordHash_, bio_;
    TP createdAt_;
    std::unordered_set<std::string> followers_, following_;
    mutable std::shared_mutex mtx_;

    static std::string hash(const std::string& pw) {
        // simplified — use bcrypt in prod
        std::hash<std::string> h;
        return std::to_string(h(pw));
    }

public:
    User(std::string username, std::string email, std::string password)
        : username_(std::move(username)), email_(std::move(email))
        , passwordHash_(hash(password)), createdAt_(Clock::now()) {
        // simple UUID sim
        static std::atomic<int> counter{0};
        id_ = "user_" + std::to_string(++counter);
    }

    bool follow(std::shared_ptr<User> target) {
        if (!target || target->id_ == id_) return false;
        std::unique_lock lk1(mtx_, std::defer_lock);
        std::unique_lock lk2(target->mtx_, std::defer_lock);
        std::lock(lk1, lk2);  // deadlock-safe dual lock
        if (following_.count(target->id_)) return false;
        following_.insert(target->id_);
        target->followers_.insert(id_);
        return true;
    }

    bool unfollow(std::shared_ptr<User> target) {
        if (!target) return false;
        std::unique_lock lk1(mtx_, std::defer_lock);
        std::unique_lock lk2(target->mtx_, std::defer_lock);
        std::lock(lk1, lk2);
        if (!following_.count(target->id_)) return false;
        following_.erase(target->id_);
        target->followers_.erase(id_);
        return true;
    }

    bool isFollowing(const std::string& uid) const {
        std::shared_lock lk(mtx_);
        return following_.count(uid) > 0;
    }

    std::unordered_set<std::string> getFollowing() const {
        std::shared_lock lk(mtx_);
        return following_;
    }

    int followerCount() const {
        std::shared_lock lk(mtx_);
        return (int)followers_.size();
    }

    const std::string& getId()       const { return id_; }
    const std::string& getUsername() const { return username_; }
};

// ── Post ──────────────────────────────────────────────────────────────────────
class Post {
    std::string id_;
    std::shared_ptr<User> author_;
    MediaMeta media_;
    std::string caption_;
    std::optional<Location> location_;
    PostVisibility visibility_{PostVisibility::PUBLIC};
    TP createdAt_;

    std::unordered_map<std::string, TP> likes_;   // userId → likedAt
    std::vector<std::shared_ptr<Comment>> comments_;
    mutable std::shared_mutex mtx_;

    static std::string makeId() {
        static std::atomic<int> c{0};
        return "post_" + std::to_string(++c);
    }

public:
    Post(std::shared_ptr<User> author, MediaMeta media, std::string caption)
        : id_(makeId()), author_(author)
        , media_(std::move(media)), caption_(std::move(caption))
        , createdAt_(Clock::now()) {}

    bool like(std::shared_ptr<User> user) {
        std::unique_lock lk(mtx_);
        return likes_.emplace(user->getId(), Clock::now()).second;
    }

    bool unlike(std::shared_ptr<User> user) {
        std::unique_lock lk(mtx_);
        return likes_.erase(user->getId()) > 0;
    }

    int getLikeCount() const {
        std::shared_lock lk(mtx_);
        return (int)likes_.size();
    }

    std::shared_ptr<Comment> addComment(
        std::shared_ptr<User> author, const std::string& text,
        std::shared_ptr<Comment> parent = nullptr) {

        auto c = std::make_shared<Comment>(author, id_, text, parent);
        std::unique_lock lk(mtx_);
        if (parent) parent->addReply(c);
        else comments_.push_back(c);
        return c;
    }

    std::shared_ptr<Comment> findComment(const std::string& cid) const {
        std::shared_lock lk(mtx_);
        std::queue<std::shared_ptr<Comment>> q;
        for (auto& c : comments_) q.push(c);
        while (!q.empty()) {
            auto c = q.front(); q.pop();
            if (c->getId() == cid) return c;
            for (auto& r : c->getReplies()) q.push(r);
        }
        return nullptr;
    }

    int getCommentCount() const {
        std::shared_lock lk(mtx_);
        int total = 0;
        for (auto& c : comments_)
            total += 1 + c->totalReplyCount();
        return total;
    }

    std::shared_ptr<User> getAuthor() const { return author_; }
    const std::string&    getId()     const { return id_; }
    TP                    getCreatedAt() const { return createdAt_; }
};

// Comment constructor (defined after User/Post are fully declared)
Comment::Comment(std::shared_ptr<User> author, std::string postId,
                 std::string text, std::shared_ptr<Comment> parent)
    : author_(author), postId_(std::move(postId))
    , text_(std::move(text)), parent_(parent)
    , createdAt_(Clock::now()) {
    static std::atomic<int> c{0};
    id_ = "comment_" + std::to_string(++c);
}

// ── Notification ──────────────────────────────────────────────────────────────
struct Notification {
    std::string id;
    std::string recipientId;
    NotifType   type;
    std::shared_ptr<User> actor;
    std::shared_ptr<Post> post;
    TP          createdAt;
    bool        isRead{false};
};

// ── NotificationService (Observer) ────────────────────────────────────────────
class NotificationService {
    std::unordered_map<std::string, std::vector<Notification>> inbox_;
    mutable std::mutex mtx_;
    static constexpr int MAX = 200;
    static int counter_;

public:
    void onEvent(NotifType type, std::shared_ptr<User> actor,
                 std::shared_ptr<User> recipient,
                 std::shared_ptr<Post> post = nullptr) {
        if (!actor || !recipient) return;
        if (actor->getId() == recipient->getId()) return;

        Notification n;
        n.id          = "notif_" + std::to_string(++counter_);
        n.recipientId = recipient->getId();
        n.type        = type;
        n.actor       = actor;
        n.post        = post;
        n.createdAt   = Clock::now();

        std::lock_guard lk(mtx_);
        auto& list = inbox_[recipient->getId()];
        list.insert(list.begin(), std::move(n));
        if ((int)list.size() > MAX) list.resize(MAX);
    }

    std::vector<Notification> getNotifications(const std::string& userId,
                                               bool unreadOnly = false) const {
        std::lock_guard lk(mtx_);
        auto it = inbox_.find(userId);
        if (it == inbox_.end()) return {};
        if (!unreadOnly) return it->second;
        std::vector<Notification> out;
        std::copy_if(it->second.begin(), it->second.end(),
                     std::back_inserter(out), [](const Notification& n){ return !n.isRead; });
        return out;
    }
};
int NotificationService::counter_ = 0;

// ── Feed Strategy ─────────────────────────────────────────────────────────────
class IFeedStrategy {
public:
    virtual ~IFeedStrategy() = default;
    virtual std::vector<std::shared_ptr<Post>> buildFeed(
        std::shared_ptr<User> user,
        std::vector<std::shared_ptr<Post>> candidates, int limit) = 0;
};

class ChronologicalFeed : public IFeedStrategy {
public:
    std::vector<std::shared_ptr<Post>> buildFeed(
        std::shared_ptr<User>, std::vector<std::shared_ptr<Post>> posts, int limit) override {
        std::sort(posts.begin(), posts.end(),
            [](auto& a, auto& b){ return a->getCreatedAt() > b->getCreatedAt(); });
        if ((int)posts.size() > limit) posts.resize(limit);
        return posts;
    }
};

// ── Feed Service ──────────────────────────────────────────────────────────────
class FeedService {
    std::unique_ptr<IFeedStrategy> strategy_;
    std::unordered_map<std::string, std::vector<std::shared_ptr<Post>>> postsByAuthor_;
    mutable std::shared_mutex mtx_;

public:
    explicit FeedService(std::unique_ptr<IFeedStrategy> s) : strategy_(std::move(s)) {}

    void addPost(std::shared_ptr<Post> p) {
        std::unique_lock lk(mtx_);
        postsByAuthor_[p->getAuthor()->getId()].insert(
            postsByAuthor_[p->getAuthor()->getId()].begin(), p);
    }

    std::vector<std::shared_ptr<Post>> getFeed(std::shared_ptr<User> user, int limit) {
        std::shared_lock lk(mtx_);
        std::vector<std::shared_ptr<Post>> candidates;
        for (const auto& uid : user->getFollowing()) {
            auto it = postsByAuthor_.find(uid);
            if (it != postsByAuthor_.end())
                candidates.insert(candidates.end(), it->second.begin(), it->second.end());
        }
        return strategy_->buildFeed(user, std::move(candidates), limit);
    }
};

// ── Instagram Facade ──────────────────────────────────────────────────────────
class InstagramService {
    std::unordered_map<std::string, std::shared_ptr<User>> usersById_;
    std::unordered_map<std::string, std::shared_ptr<Post>> postsById_;
    NotificationService notif_;
    FeedService feed_{std::make_unique<ChronologicalFeed>()};
    mutable std::mutex mtx_;

public:
    std::shared_ptr<User> registerUser(const std::string& username,
                                       const std::string& email,
                                       const std::string& password) {
        std::lock_guard lk(mtx_);
        for (auto& [id, u] : usersById_)
            if (u->getUsername() == username)
                throw std::runtime_error("Username taken: " + username);
        auto user = std::make_shared<User>(username, email, password);
        usersById_[user->getId()] = user;
        return user;
    }

    bool follow(std::shared_ptr<User> actor, std::shared_ptr<User> target) {
        bool ok = actor->follow(target);
        if (ok) notif_.onEvent(NotifType::FOLLOW, actor, target);
        return ok;
    }

    std::shared_ptr<Post> createPost(std::shared_ptr<User> author,
                                     MediaMeta media, std::string caption) {
        auto post = std::make_shared<Post>(author, std::move(media), std::move(caption));
        {
            std::lock_guard lk(mtx_);
            postsById_[post->getId()] = post;
        }
        feed_.addPost(post);
        return post;
    }

    bool likePost(std::shared_ptr<User> user, std::shared_ptr<Post> post) {
        bool ok = post->like(user);
        if (ok) notif_.onEvent(NotifType::LIKE, user, post->getAuthor(), post);
        return ok;
    }

    std::shared_ptr<Comment> commentOnPost(std::shared_ptr<User> user,
                                           std::shared_ptr<Post> post,
                                           const std::string& text,
                                           std::shared_ptr<Comment> parent = nullptr) {
        auto c = post->addComment(user, text, parent);
        notif_.onEvent(NotifType::COMMENT, user, post->getAuthor(), post);
        return c;
    }

    std::vector<std::shared_ptr<Post>> getFeed(std::shared_ptr<User> u, int n = 20) {
        return feed_.getFeed(u, n);
    }
};

// ── Demo ──────────────────────────────────────────────────────────────────────
int main() {
    InstagramService insta;

    auto alice = insta.registerUser("alice", "a@ig.com", "pass");
    auto bob   = insta.registerUser("bob",   "b@ig.com", "pass");
    auto carol = insta.registerUser("carol", "c@ig.com", "pass");

    insta.follow(alice, bob);
    insta.follow(carol, bob);
    std::cout << "Bob followers: " << bob->followerCount() << "\n"; // 2

    MediaMeta media{"cdn/photo.jpg", "image/jpeg", 1200000, 1080, 1080, 0};
    auto post = insta.createPost(bob, media, "Beautiful day! @alice #nature");

    insta.likePost(alice, post);
    insta.likePost(carol, post);
    auto c1 = insta.commentOnPost(alice, post, "Amazing shot!");
    insta.commentOnPost(carol, post, "Love it!", c1);

    std::cout << "Post likes: "    << post->getLikeCount()    << "\n";
    std::cout << "Post comments: " << post->getCommentCount() << "\n";

    auto feed = insta.getFeed(alice, 10);
    std::cout << "Alice's feed size: " << feed.size() << "\n";
    return 0;
}
```

---

## STEP 6 — Deep Concurrency Analysis

```
PYTHON:
  threading.RLock in Post (reentrant — same thread can re-acquire for nested calls)
  threading.RLock in InMemoryStore
  CopyOnWrite pattern via list copy in hot-read scenarios

JAVA:
  ConcurrentHashMap for User.followers/following → lock-free reads, segment locks on writes
  CopyOnWriteArrayList for Post.comments → snapshot iteration, write is expensive but rare
  AtomicInteger for clickCount → no lock needed, CAS instruction
  ReentrantReadWriteLock in LRUCache → many concurrent readers, exclusive writers
  double-checked locking in Singleton (volatile ensures visibility after write)

C++:
  std::shared_mutex in Post → many concurrent reads (getLikeCount), exclusive writes (like)
  std::lock() with defer_lock for deadlock-safe dual-lock in User.follow()
  std::atomic<int> for like/comment counters → lock-free via hardware CAS
  weak_ptr for Comment.parent → avoids circular reference memory leak
  std::enable_shared_from_this → safe to capture `this` in lambdas passed to threads

DEADLOCK RISK: User.follow(target)
  WRONG:  lock(this->mtx_); then lock(target->mtx_) → deadlock if A.follow(B) + B.follow(A) concurrently
  RIGHT:  std::lock(lk1, lk2) — acquires both or neither, in consistent order → no deadlock
```

---

## STEP 7 — Trade-offs

```
TRADE-OFF 1: CopyOnWriteArrayList for comments vs synchronized List
  COW: reads are lock-free (iterate snapshot). Writes copy entire array.
  sync List: writes faster (no copy), reads contend on lock.
  Instagram: reads >> writes → COW is correct choice.

TRADE-OFF 2: Soft delete vs hard delete for Comments
  Soft: comment marked [deleted], replies remain visible. Better UX.
  Hard: comment and all replies cascade deleted. Simpler storage.
  Decision: soft delete (Reddit/Instagram model) — replies provide context.

TRADE-OFF 3: Inline mention parsing vs async
  Inline: simple, consistent, slightly slows post creation.
  Async (Kafka): fast post creation, eventual notification (1-2 sec delay).
  Decision: async in prod; inline shown here for clarity.

TRADE-OFF 4: Feed denormalization (FeedService.postsByAuthor map)
  Push model: on post, store in all followers' feeds (fan-out on write).
  Pull model: on request, pull from all followees (shown here).
  Decision: pull for celebrities with 10M followers (push would be O(10M) writes).
  Hybrid: push for normal users (<10K followers), pull for celebrities.

TRADE-OFF 5: C++ weak_ptr for Comment.parent
  shared_ptr parent: Comment keeps parent alive → cycle if parent holds Comment too.
  weak_ptr: parent may be destroyed; child checks if parent is still alive via lock().
  Decision: weak_ptr is correct to avoid memory leak in tree structures.
```

---

## STEP 8 — Interview Follow-Ups

```
Q: "How would you implement Stories (24h expiring posts)?"
A: Post with expiresAt = createdAt + 24h. Separate StoryService queries
   only non-expired posts. Background job sweeps every hour.
   Redis EXPIREAT for cache auto-eviction.

Q: "How would you implement a trending hashtag system?"
A: Sliding window counter per hashtag (Redis sorted set).
   ZINCRBY trending:<15min-bucket> 1 <tag> on each post.
   Top-K query: ZREVRANGE trending:<bucket> 0 9.
   Rotate buckets every 15 min (4 buckets = 1 hour window).

Q: "Handle a celebrity with 100M followers posting — fan-out problem?"
A: Hybrid push/pull: if author.followerCount < 10K → push to all followers.
   Otherwise → pull model: fetch celebrity's posts on read, merge with pushed feed.
   Gate on a threshold stored in User (is_celebrity flag).

Q: "Consistency in like_count if 1M concurrent likes?"
A: AtomicInteger / ConcurrentHashMap.putIfAbsent is optimistic (no lock).
   DB: UPDATE posts SET like_count = like_count + 1 (atomic at DB level).
   Cache: Redis INCR is atomic. Periodic sync to DB.
   Eventual consistency is acceptable for like counts (±few % during peak).

Q: "How would you handle image storage and CDN?"
A: Client uploads to MediaUploader → gets upload_id.
   Chunks assembled → stored in S3 (original + thumbnails via Lambda).
   CDN (CloudFront) serves from S3 bucket with 1yr cache-control.
   Post stores CDN URL, not S3 URL.
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

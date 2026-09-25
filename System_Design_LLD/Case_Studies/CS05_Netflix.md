# CS05: LLD — Netflix
## Streaming Platform | Every Line Explained | Python + Java + C++

---

## STEP 1 — Requirements & Entities

```
WHAT WE'RE BUILDING:
  Netflix — stream movies/shows to millions of concurrent users.
  Focus: content catalog, user profiles, watch history, recommendations, streaming session.

FUNCTIONAL REQUIREMENTS:
  1. User registers, creates sub-profiles (parent + kids profile)
  2. Browse catalog: movies, shows, episodes
  3. Search content by title, genre, actor
  4. Start streaming a video (get streaming URL + quality)
  5. Pause / Resume — resume from exact timestamp
  6. Mark as watched / add to watchlist
  7. Rate content (thumbs up / thumbs down)
  8. Get personalized recommendations
  9. Download for offline viewing

KEY ENTITIES:
  User              — account (1 account = up to 5 profiles)
  Profile           — sub-account within user (separate watch history)
  Content           — base class for all streamable content
  Movie             — extends Content (single file)
  Show              — extends Content (has seasons)
  Season            — group of episodes in a show
  Episode           — single episode of a show
  WatchSession      — tracks current streaming session (timestamp, quality, device)
  WatchHistory      — log of what a profile has watched and where they stopped
  WatchlistEntry    — content a user wants to watch later
  Rating            — thumbs up/down on content
  RecommendationEngine — suggests content based on history and ratings
  StreamingService  — returns CDN URL + video quality for a session
```

---

## STEP 2 — Class Diagram

```
[Content] (Abstract)              [Movie]               [Show]
─────────────────────             ───────               ──────
- id: UUID                        extends Content       extends Content
- title: str                      - duration_min: int   - seasons: List[Season]
- description: str                - release_year: int   ──────
- genres: List[str]               - rating: str (PG-13) + get_season(n): Season
- content_rating: str             ───────               + total_episodes(): int
- thumbnail_url: str              + get_stream_url(): str
- is_available: bool
- added_at: datetime              [Season]              [Episode]
─────────────────────             ────────              ─────────
+ get_stream_url(): str           - show: Show          - season: Season
+ get_thumbnail(): str            - number: int         - number: int
+ matches_search(q): bool         - episodes: List      - title: str
                                  ────────              - duration_min: int
[User]                            + get_episode(n): Ep  - stream_url: str
──────
- id: UUID                        [Profile]
- email: str                      ────────
- subscription: SubscriptionTier  - id: UUID
- profiles: List[Profile]         - user: User
- created_at: datetime            - name: str
──────                            - age_limit: int   (0=adult, 13=teen, 7=kids)
+ add_profile(name): Profile      - avatar_url: str
+ get_profile(id): Profile        - language: str
                                  ────────
[WatchSession]                    + can_watch(content): bool
──────────────                    + get_history(): List[WatchHistory]
- id: UUID                        + get_watchlist(): List[WatchlistEntry]
- profile: Profile                + get_recommendations(): List[Content]
- content: Content
- device: DeviceType              [WatchHistory]
- quality: StreamQuality          ─────────────
- position_sec: int (resume pt)   - profile: Profile
- started_at: datetime            - content: Content
- last_updated: datetime          - watched_seconds: int
- is_active: bool                 - is_complete: bool
──────────────                    - watched_at: datetime
+ update_position(sec): void
+ pause(): void                   [RecommendationEngine]
+ resume(): void                  ─────────────────────
                                  - history: WatchHistory store
PATTERNS USED:                    - ratings: Rating store
  Template Method → Content.get_stream_url() is abstract,       ─────────────────────
                    Movie overrides differently from Episode      + recommend(profile): List[Content]
  Composite → Show contains Seasons contains Episodes
  Strategy  → RecommendationEngine (collaborative vs content-based)
  State     → WatchSession (PLAYING → PAUSED → PLAYING → COMPLETED)
  Factory   → ContentFactory.create(type, data) → Movie or Show
  Observer  → WatchHistory observes WatchSession position updates
```

---

## STEP 3 — Python Implementation (Every Line Explained)

```python
# netflix_lld.py
from __future__ import annotations
import uuid
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional, List, Dict, Set


# ══════════════════════════════════════════════════════════════════════════════
# ENUMS
# ══════════════════════════════════════════════════════════════════════════════

class SubscriptionTier(Enum):
    """
    Netflix pricing tiers — each has different capabilities.
    MOBILE: SD quality, 1 screen, mobile only.
    BASIC:  SD quality, 1 screen, any device.
    STANDARD: HD quality, 2 screens.
    PREMIUM: 4K quality, 4 screens, downloads.
    """
    MOBILE   = auto()
    BASIC    = auto()
    STANDARD = auto()
    PREMIUM  = auto()

class StreamQuality(Enum):
    """Video resolution — higher requires more bandwidth."""
    SD    = "480p"    # Standard Definition: 480p — ~0.7 GB/hr
    HD    = "720p"    # High Definition: 720p — ~3 GB/hr
    FHD   = "1080p"   # Full HD: 1080p — ~7 GB/hr
    UHD4K = "4K"      # Ultra HD: 4K — ~15 GB/hr

class DeviceType(Enum):
    MOBILE   = auto()
    TV       = auto()
    LAPTOP   = auto()
    TABLET   = auto()

class SessionState(Enum):
    """STATE MACHINE: PLAYING → PAUSED → PLAYING → COMPLETED"""
    PLAYING   = auto()
    PAUSED    = auto()
    COMPLETED = auto()
    BUFFERING = auto()   # Waiting for network


# ══════════════════════════════════════════════════════════════════════════════
# CONTENT — Template Method Pattern
# ══════════════════════════════════════════════════════════════════════════════

class Content(ABC):
    """
    ABSTRACT BASE CLASS for all streamable content.
    
    TEMPLATE METHOD PATTERN:
    get_stream_info() defines the ALGORITHM SKELETON:
      1. Check availability
      2. Get the stream URL (different for Movie vs Episode)
      3. Select quality based on subscription
    Step 2 is abstract — subclasses fill it in.
    
    WHY NOT JUST USE DUCK TYPING (no ABC)?
    Python doesn't enforce method implementation at definition time.
    A class that "forgets" to implement get_stream_url() would only fail
    at RUNTIME when called. ABC catches this at CLASS DEFINITION time.
    """

    def __init__(self, title: str, description: str, genres: List[str],
                 content_rating: str, thumbnail_url: str):
        self.id             = str(uuid.uuid4())
        self.title          = title
        self.description    = description
        self.genres         = genres          # e.g., ["Action", "Thriller"]
        self.content_rating = content_rating  # "U", "UA", "A", "PG-13", "R"
        self.thumbnail_url  = thumbnail_url
        self.is_available   = True
        self.added_at       = datetime.utcnow()

    @abstractmethod
    def get_stream_url(self) -> str:
        """
        Returns the CDN URL for streaming this content.
        Movie: returns its single video URL.
        Episode: returns its specific episode URL.
        ABSTRACT: each subclass MUST implement this.
        """
        ...

    @abstractmethod
    def get_duration_minutes(self) -> int:
        """Duration of the content in minutes."""
        ...

    def matches_search(self, query: str) -> bool:
        """
        Simple search: does this content match the search query?
        
        WHY ALL LOWERCASE?
        Case-insensitive search: "BATMAN" and "batman" should both find "The Dark Knight".
        .lower() converts to lowercase before comparison.
        """
        q = query.lower()
        return (q in self.title.lower()                          # Title contains query
                or any(q in g.lower() for g in self.genres)     # Any genre matches
                or q in self.description.lower())                 # Description contains query

    def get_thumbnail(self) -> str:
        return self.thumbnail_url

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.title!r})"


class Movie(Content):
    """A standalone film. Has a single stream URL."""

    def __init__(self, title: str, description: str, genres: List[str],
                 content_rating: str, thumbnail_url: str,
                 stream_url: str, duration_min: int, release_year: int):
        super().__init__(title, description, genres, content_rating, thumbnail_url)
        # super().__init__() calls the parent class (Content) constructor
        # MUST be called first to initialize all Content fields
        
        self._stream_url   = stream_url      # CDN URL for the movie file
        self._duration_min = duration_min    # Movie length in minutes
        self.release_year  = release_year

    def get_stream_url(self) -> str:
        """Returns the single CDN URL for this movie."""
        return self._stream_url

    def get_duration_minutes(self) -> int:
        return self._duration_min


class Episode(Content):
    """A single episode of a TV show."""

    def __init__(self, title: str, season: Season, episode_number: int,
                 stream_url: str, duration_min: int):
        super().__init__(
            title=title,
            description=f"S{season.number}E{episode_number} of {season.show.title}",
            genres=season.show.genres,       # Episodes inherit show's genres
            content_rating=season.show.content_rating,
            thumbnail_url=season.show.thumbnail_url
        )
        self.season         = season
        self.episode_number = episode_number
        self._stream_url    = stream_url
        self._duration_min  = duration_min

    def get_stream_url(self) -> str:
        return self._stream_url

    def get_duration_minutes(self) -> int:
        return self._duration_min


class Season:
    """
    COMPOSITE PATTERN:
    Season is a container of Episodes.
    Show is a container of Seasons.
    Accessing episodes flows: show.get_season(2).get_episode(3)
    """

    def __init__(self, show: Show, number: int):
        self.show    = show     # Reference back to parent Show
        self.number  = number   # Season number (1, 2, 3...)
        self._episodes: Dict[int, Episode] = {}   # episode_number → Episode
        self._lock   = threading.Lock()

    def add_episode(self, episode: Episode) -> None:
        with self._lock:
            self._episodes[episode.episode_number] = episode

    def get_episode(self, number: int) -> Optional[Episode]:
        with self._lock:
            return self._episodes.get(number)    # None if episode doesn't exist

    @property
    def episode_count(self) -> int:
        with self._lock:
            return len(self._episodes)

    @property
    def episodes(self) -> List[Episode]:
        with self._lock:
            # Sorted by episode number (in case they were added out of order)
            return sorted(self._episodes.values(), key=lambda e: e.episode_number)


class Show(Content):
    """
    A TV series with multiple seasons.
    COMPOSITE PATTERN: Show → Season → Episode (tree structure)
    """

    def __init__(self, title: str, description: str, genres: List[str],
                 content_rating: str, thumbnail_url: str):
        super().__init__(title, description, genres, content_rating, thumbnail_url)
        self._seasons: Dict[int, Season] = {}    # season_number → Season
        self._lock    = threading.Lock()

    def add_season(self, season: Season) -> None:
        with self._lock:
            self._seasons[season.number] = season

    def get_season(self, number: int) -> Optional[Season]:
        with self._lock:
            return self._seasons.get(number)

    def get_stream_url(self) -> str:
        """Show itself is not directly streamable — get first episode's URL."""
        with self._lock:
            if not self._seasons: return ""
            first_season = self._seasons.get(1) or next(iter(self._seasons.values()))
            first_ep = first_season.get_episode(1)
            return first_ep.get_stream_url() if first_ep else ""

    def get_duration_minutes(self) -> int:
        """Total runtime across ALL episodes."""
        with self._lock:
            return sum(ep.get_duration_minutes()
                       for s in self._seasons.values()
                       for ep in s.episodes)

    def total_episodes(self) -> int:
        with self._lock:
            return sum(s.episode_count for s in self._seasons.values())


# Forward declare Show for Episode's type hint (circular reference):
# Season references Show, and Show references Season. Python handles this
# with the 'from __future__ import annotations' import at the top.


# ══════════════════════════════════════════════════════════════════════════════
# USER AND PROFILE
# ══════════════════════════════════════════════════════════════════════════════

class Profile:
    """
    A sub-account within a Netflix account.
    One Netflix account can have 5 profiles: "Sachin", "Mom", "Kids", etc.
    Each profile has its own watch history and recommendations.
    WHY SEPARATE FROM USER?
    Different family members have completely different viewing preferences.
    Mixing histories would ruin recommendations for everyone.
    """

    MAX_AGE_LIMIT_ADULT = 100   # Adults can watch anything
    KIDS_AGE_LIMIT      = 7     # Kids profile: only G-rated content

    def __init__(self, user: User, name: str, age_limit: int = 100):
        self.id         = str(uuid.uuid4())
        self.user       = user
        self.name       = name
        self.age_limit  = age_limit    # 7 for kids, 13 for teens, 100 for adults
        self.avatar_url = ""
        self.language   = "en"
        
        # Per-profile data stores
        self._watch_history: Dict[str, WatchHistory] = {}   # content_id → WatchHistory
        self._watchlist:     Set[str]                 = set()  # Set of content IDs
        self._ratings:       Dict[str, float]         = {}     # content_id → -1 or +1
        self._lock = threading.RLock()

    def can_watch(self, content: Content) -> bool:
        """
        Content restriction based on profile age limit.
        A kids profile cannot watch content rated for adults.
        
        Rating mappings (simplified):
        "U" → 0 (universal, everyone)
        "UA" → 7 (children with parental guidance)
        "A" → 18 (adults only)
        "PG-13" → 13 (parental guidance for under 13)
        "R" → 17 (restricted)
        """
        rating_age_map = {"U": 0, "UA": 7, "PG-13": 13, "A": 18, "R": 17, "NC-17": 18}
        required_age = rating_age_map.get(content.content_rating, 0)
        return self.age_limit >= required_age
        # If profile's age limit is >= required age → allowed. Otherwise → blocked.

    def record_watch(self, content: Content, watched_seconds: int,
                     is_complete: bool = False) -> None:
        """Update or create a watch history entry for this content."""
        with self._lock:
            if content.id in self._watch_history:
                entry = self._watch_history[content.id]
                entry.watched_seconds = watched_seconds   # Update position
                entry.is_complete     = is_complete
                entry.watched_at      = datetime.utcnow() # Refresh timestamp
            else:
                self._watch_history[content.id] = WatchHistory(
                    self, content, watched_seconds, is_complete
                )

    def get_resume_position(self, content: Content) -> int:
        """
        Where did the user stop watching?
        Returns 0 if never watched (start from beginning).
        Returns exact second to resume from.
        """
        with self._lock:
            entry = self._watch_history.get(content.id)
            return entry.watched_seconds if entry else 0
            # dict.get() with no default returns None
            # 'if entry' checks if it's not None

    def add_to_watchlist(self, content: Content) -> None:
        with self._lock:
            self._watchlist.add(content.id)

    def remove_from_watchlist(self, content: Content) -> None:
        with self._lock:
            self._watchlist.discard(content.id)
            # discard = remove if present, no error if not present

    def rate_content(self, content: Content, thumbs_up: bool) -> None:
        """Thumbs up (+1) or thumbs down (-1)."""
        with self._lock:
            self._ratings[content.id] = 1.0 if thumbs_up else -1.0

    def get_history(self) -> List[WatchHistory]:
        with self._lock:
            # Sort by most recently watched
            return sorted(self._watch_history.values(),
                          key=lambda h: h.watched_at, reverse=True)

    def get_liked_genres(self) -> List[str]:
        """
        Derive which genres the profile likes from their ratings.
        Used by recommendation engine.
        """
        with self._lock:
            genre_scores: Dict[str, float] = {}
            # genre → sum of ratings (positive = liked, negative = disliked)
            
            for content_id, rating in self._ratings.items():
                # We need the content to check genres, but we only have IDs here
                # In production: query content service. Here: simplified.
                pass  # This would hit ContentService.get_by_id(content_id)
            
            return [g for g, score in genre_scores.items() if score > 0]


@dataclass
class WatchHistory:
    """
    Records WHERE a user stopped watching a piece of content.
    Enables "Continue Watching" feature.
    """
    profile:         Profile
    content:         Content
    watched_seconds: int          # Resume from this timestamp
    is_complete:     bool         # True if watched to the end
    watched_at:      datetime = field(default_factory=datetime.utcnow)

    @property
    def completion_percent(self) -> float:
        """What percentage of the content was watched?"""
        duration_secs = self.content.get_duration_minutes() * 60
        if duration_secs == 0: return 0.0
        return min(100.0, (self.watched_seconds / duration_secs) * 100)


class User:
    """A Netflix account (can have multiple profiles)."""
    MAX_PROFILES = 5

    def __init__(self, email: str, tier: SubscriptionTier = SubscriptionTier.STANDARD):
        self.id           = str(uuid.uuid4())
        self.email        = email
        self.subscription = tier
        self._profiles:   List[Profile] = []
        self._lock        = threading.Lock()

    def add_profile(self, name: str, age_limit: int = 100) -> Profile:
        with self._lock:
            if len(self._profiles) >= self.MAX_PROFILES:
                raise ValueError(f"Max {self.MAX_PROFILES} profiles per account")
            profile = Profile(self, name, age_limit)
            self._profiles.append(profile)
            return profile

    def get_profile(self, profile_id: str) -> Optional[Profile]:
        with self._lock:
            return next((p for p in self._profiles if p.id == profile_id), None)
            # next(iterator, default): get first matching item or return default

    def get_max_screens(self) -> int:
        """How many devices can stream simultaneously?"""
        limits = {
            SubscriptionTier.MOBILE:   1,
            SubscriptionTier.BASIC:    1,
            SubscriptionTier.STANDARD: 2,
            SubscriptionTier.PREMIUM:  4,
        }
        return limits[self.subscription]
        # Dict lookup by enum key — clean alternative to if/elif chain

    def get_max_quality(self) -> StreamQuality:
        """What's the maximum video quality for this subscription?"""
        limits = {
            SubscriptionTier.MOBILE:   StreamQuality.SD,
            SubscriptionTier.BASIC:    StreamQuality.SD,
            SubscriptionTier.STANDARD: StreamQuality.FHD,
            SubscriptionTier.PREMIUM:  StreamQuality.UHD4K,
        }
        return limits[self.subscription]


# ══════════════════════════════════════════════════════════════════════════════
# WATCH SESSION — State Machine
# ══════════════════════════════════════════════════════════════════════════════

class WatchSession:
    """
    Tracks an ACTIVE streaming session.
    
    STATE MACHINE:
    (Created) PLAYING → pause() → PAUSED → resume() → PLAYING → complete() → COMPLETED
    
    Real Netflix sends "heartbeats" every 10 seconds from the player app.
    Each heartbeat calls update_position() with current timestamp.
    This keeps the resume position accurate.
    """

    def __init__(self, profile: Profile, content: Content, device: DeviceType,
                 quality: StreamQuality, start_position: int = 0):
        self.id             = str(uuid.uuid4())
        self.profile        = profile
        self.content        = content
        self.device         = device
        self.quality        = quality
        self.position_sec   = start_position   # Current playback position in seconds
        self.started_at     = datetime.utcnow()
        self.last_updated   = datetime.utcnow()
        self._state         = SessionState.PLAYING   # Initial state: immediately playing
        self._lock          = threading.Lock()

    def update_position(self, position_seconds: int) -> None:
        """
        Called every 10 seconds by the Netflix player app (heartbeat).
        Updates resume position so user can continue on another device.
        """
        with self._lock:
            if self._state == SessionState.COMPLETED:
                return   # Can't update a finished session
            self.position_sec = position_seconds
            self.last_updated = datetime.utcnow()
            # Also update watch history:
            self.profile.record_watch(self.content, position_seconds)

    def pause(self) -> None:
        with self._lock:
            if self._state == SessionState.PLAYING:
                self._state = SessionState.PAUSED
                self.profile.record_watch(self.content, self.position_sec)
                # Save position immediately on pause (important for resume)

    def resume(self) -> None:
        with self._lock:
            if self._state == SessionState.PAUSED:
                self._state = SessionState.PLAYING

    def complete(self) -> None:
        """Mark as fully watched (reached the end)."""
        with self._lock:
            self._state = SessionState.COMPLETED
            total_secs  = self.content.get_duration_minutes() * 60
            self.profile.record_watch(self.content, total_secs, is_complete=True)

    def change_quality(self, new_quality: StreamQuality) -> None:
        """
        User changes video quality (e.g., switches to SD on mobile data).
        Or adaptive bitrate algorithm auto-adjusts based on bandwidth.
        """
        with self._lock:
            max_quality = self.profile.user.get_max_quality()
            # Clamp to subscription's max quality
            # In a real enum comparison: compare by value order
            # Simplified here: just assign
            self.quality = new_quality

    @property
    def state(self) -> SessionState:
        with self._lock: return self._state

    def __repr__(self) -> str:
        return f"Session({self.profile.name}, {self.content.title}, {self.state.name})"


# ══════════════════════════════════════════════════════════════════════════════
# RECOMMENDATION ENGINE — Strategy Pattern
# ══════════════════════════════════════════════════════════════════════════════

class IRecommendationStrategy(ABC):
    """
    STRATEGY for recommendation algorithm.
    Strategies:
    - ContentBased: recommend content similar to what you've watched
    - CollaborativeFiltering: recommend what similar users watch
    - HybridStrategy: combine both (what Netflix actually does)
    """

    @abstractmethod
    def recommend(self, profile: Profile,
                  catalog: List[Content], limit: int) -> List[Content]: ...


class ContentBasedStrategy(IRecommendationStrategy):
    """
    Recommend content in the same genres as highly-rated watched content.
    
    ALGORITHM:
    1. Get genres the profile has liked (thumbs up or high completion %)
    2. Score each content item by how many liked genres it has
    3. Return top-N by score
    """

    def recommend(self, profile: Profile,
                  catalog: List[Content], limit: int) -> List[Content]:
        # Get genres the user has watched (simplified: use all genres from history)
        watched_genres: Dict[str, float] = {}   # genre → preference score
        for entry in profile.get_history():
            # More completed = higher preference for that genre
            weight = entry.completion_percent / 100.0  # 0.0 to 1.0
            for genre in entry.content.genres:
                watched_genres[genre] = watched_genres.get(genre, 0.0) + weight
                # Accumulate genre scores

        if not watched_genres:
            # New user with no history — return most popular (no info to personalize)
            return catalog[:limit]

        # Score each content item
        watched_ids = {e.content.id for e in profile.get_history()}
        # Set of already-watched content IDs (don't recommend already-watched)

        scored: List[tuple[float, Content]] = []
        for content in catalog:
            if content.id in watched_ids: continue   # Already watched — skip
            if not profile.can_watch(content): continue  # Age restricted — skip

            score = sum(watched_genres.get(g, 0.0) for g in content.genres)
            # Total score = sum of watched_genres preference for each of content's genres
            
            if score > 0:
                scored.append((score, content))

        # Sort by score descending — highest score = best recommendation
        scored.sort(key=lambda x: x[0], reverse=True)
        return [content for _, content in scored[:limit]]
        # List comprehension: for each (score, content) tuple, take just the content


class RecommendationEngine:
    def __init__(self, strategy: IRecommendationStrategy = None):
        self._strategy = strategy or ContentBasedStrategy()

    def set_strategy(self, strategy: IRecommendationStrategy) -> None:
        self._strategy = strategy

    def recommend(self, profile: Profile,
                  catalog: List[Content], limit: int = 20) -> List[Content]:
        return self._strategy.recommend(profile, catalog, limit)


# ══════════════════════════════════════════════════════════════════════════════
# CONTENT CATALOG SERVICE
# ══════════════════════════════════════════════════════════════════════════════

class ContentCatalog:
    """
    Manages the Netflix content library.
    Supports search by title, genre, and actor.
    In production: backed by Elasticsearch for full-text search.
    """

    def __init__(self):
        self._catalog: Dict[str, Content] = {}   # content_id → Content
        self._lock    = threading.RLock()

    def add(self, content: Content) -> None:
        with self._lock:
            self._catalog[content.id] = content

    def get_by_id(self, content_id: str) -> Optional[Content]:
        with self._lock:
            return self._catalog.get(content_id)

    def search(self, query: str, genre: str = None) -> List[Content]:
        """
        Text search across all content.
        Optional genre filter.
        
        IN PRODUCTION: This would call Elasticsearch with:
        GET /content/_search
        { "query": { "multi_match": { "query": "batman", "fields": ["title", "description", "genres"] } } }
        """
        with self._lock:
            results = []
            for content in self._catalog.values():
                if not content.is_available: continue   # Skip unavailable content
                if not content.matches_search(query): continue  # Doesn't match search
                if genre and genre.lower() not in [g.lower() for g in content.genres]:
                    continue   # Genre filter doesn't match
                results.append(content)
            return sorted(results, key=lambda c: c.title)

    def get_by_genre(self, genre: str) -> List[Content]:
        with self._lock:
            return [c for c in self._catalog.values()
                    if genre.lower() in [g.lower() for g in c.genres]
                    and c.is_available]

    def all_content(self) -> List[Content]:
        with self._lock:
            return list(self._catalog.values())


# ══════════════════════════════════════════════════════════════════════════════
# STREAMING SERVICE
# ══════════════════════════════════════════════════════════════════════════════

class StreamingService:
    """
    Starts and manages streaming sessions.
    
    WHAT IT DOES:
    1. Validates user can start a new stream (screen limit check)
    2. Determines video quality based on subscription
    3. Gets resume position if user previously watched
    4. Returns a WatchSession with the CDN streaming URL
    
    IN PRODUCTION:
    - Returns a signed CDN URL that expires after 24 hours
    - URL is signed with a secret key so only this user can use it
    - CDN serves video from edge location nearest to the user
    """

    def __init__(self, catalog: ContentCatalog, recommender: RecommendationEngine):
        self._catalog    = catalog
        self._recommender = recommender
        self._active_sessions: Dict[str, List[WatchSession]] = {}  # user_id → sessions
        self._lock = threading.RLock()

    def start_stream(self, profile: Profile, content_id: str,
                     device: DeviceType) -> WatchSession:
        """
        Start or resume streaming a piece of content.
        Returns a WatchSession object.
        """
        content = self._catalog.get_by_id(content_id)
        if not content:
            raise ValueError(f"Content {content_id} not found")
        if not content.is_available:
            raise ValueError(f"{content.title} is not available in your region")
        if not profile.can_watch(content):
            raise ValueError(f"{content.title} is age-restricted for this profile")

        user = profile.user
        # Check concurrent stream limit
        self._enforce_stream_limit(user)

        # Get resume position (0 if never watched)
        resume_pos = profile.get_resume_position(content)

        # Determine quality based on subscription tier
        quality = user.get_max_quality()

        # Create session
        session = WatchSession(profile, content, device, quality, resume_pos)
        
        with self._lock:
            if user.id not in self._active_sessions:
                self._active_sessions[user.id] = []
            self._active_sessions[user.id].append(session)

        print(f"▶ Streaming: {content.title} | Q:{quality.value} | "
              f"Resume: {resume_pos}s | URL: {content.get_stream_url()}")
        return session

    def _enforce_stream_limit(self, user: User) -> None:
        """
        Check if user has hit their screen limit.
        E.g., STANDARD plan = max 2 simultaneous streams.
        """
        with self._lock:
            active = [s for s in self._active_sessions.get(user.id, [])
                      if s.state == SessionState.PLAYING]
            if len(active) >= user.get_max_screens():
                raise ValueError(
                    f"Stream limit reached ({user.get_max_screens()} screens). "
                    f"Pause another stream first."
                )

    def end_stream(self, session: WatchSession) -> None:
        """Called when user exits the player or finishes content."""
        session.complete()
        with self._lock:
            user_sessions = self._active_sessions.get(session.profile.user.id, [])
            user_sessions.remove(session)   # Remove from active sessions list

    def get_recommendations(self, profile: Profile, limit: int = 20) -> List[Content]:
        """Get personalized content recommendations for a profile."""
        all_content = self._catalog.all_content()
        return self._recommender.recommend(profile, all_content, limit)


# ══════════════════════════════════════════════════════════════════════════════
# CONTENT FACTORY — Factory Method Pattern
# ══════════════════════════════════════════════════════════════════════════════

class ContentFactory:
    """
    FACTORY METHOD PATTERN:
    Creates the right type of Content object based on input data.
    
    WHY FACTORY?
    Caller says "create content from this data" without knowing
    whether it's a Movie or Show constructor call.
    The factory decides based on a 'type' field.
    Adding a new content type (Podcast, Short Film) = add to factory only.
    """

    @staticmethod
    def create_movie(title: str, description: str, genres: List[str],
                     content_rating: str, thumbnail_url: str,
                     stream_url: str, duration_min: int, release_year: int) -> Movie:
        return Movie(title, description, genres, content_rating, thumbnail_url,
                     stream_url, duration_min, release_year)

    @staticmethod
    def create_show(title: str, description: str, genres: List[str],
                    content_rating: str, thumbnail_url: str) -> Show:
        return Show(title, description, genres, content_rating, thumbnail_url)


# ══════════════════════════════════════════════════════════════════════════════
# NETFLIX SERVICE — Facade
# ══════════════════════════════════════════════════════════════════════════════

class NetflixService:
    """FACADE: Single entry point for all Netflix operations."""

    def __init__(self):
        self._users:    Dict[str, User] = {}
        self._catalog   = ContentCatalog()
        self._recommender = RecommendationEngine(ContentBasedStrategy())
        self._streaming = StreamingService(self._catalog, self._recommender)
        self._lock = threading.Lock()

    def register_user(self, email: str, tier: SubscriptionTier) -> User:
        with self._lock:
            if any(u.email == email for u in self._users.values()):
                raise ValueError(f"Email already registered: {email}")
            user = User(email, tier)
            self._users[user.id] = user
            return user

    def add_content(self, content: Content) -> None:
        self._catalog.add(content)

    def search(self, query: str, genre: str = None) -> List[Content]:
        return self._catalog.search(query, genre)

    def stream(self, profile: Profile, content_id: str,
               device: DeviceType = DeviceType.TV) -> WatchSession:
        return self._streaming.start_stream(profile, content_id, device)

    def stop_stream(self, session: WatchSession) -> None:
        self._streaming.end_stream(session)

    def get_recommendations(self, profile: Profile) -> List[Content]:
        return self._streaming.get_recommendations(profile)


# ══════════════════════════════════════════════════════════════════════════════
# DEMO
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    netflix = NetflixService()

    # Register user
    sachin = netflix.register_user("sachin@gmail.com", SubscriptionTier.PREMIUM)
    adult_profile = sachin.add_profile("Sachin", age_limit=100)
    kids_profile  = sachin.add_profile("Kids", age_limit=7)

    # Add movies
    inception = ContentFactory.create_movie(
        "Inception", "A thief enters dreams",
        genres=["Sci-Fi", "Thriller"], content_rating="PG-13",
        thumbnail_url="cdn/inception.jpg", stream_url="cdn/videos/inception.mp4",
        duration_min=148, release_year=2010
    )
    frozen = ContentFactory.create_movie(
        "Frozen", "An ice princess",
        genres=["Animation", "Family"], content_rating="U",
        thumbnail_url="cdn/frozen.jpg", stream_url="cdn/videos/frozen.mp4",
        duration_min=102, release_year=2013
    )
    netflix.add_content(inception)
    netflix.add_content(frozen)

    # Add a show
    stranger_things = ContentFactory.create_show(
        "Stranger Things", "Sci-fi horror show",
        genres=["Sci-Fi", "Horror"], content_rating="A",
        thumbnail_url="cdn/stranger_things.jpg"
    )
    season1 = Season(stranger_things, number=1)
    ep1 = Episode("Chapter One: The Vanishing", season1, 1,
                  "cdn/videos/st_s1e1.mp4", duration_min=47)
    season1.add_episode(ep1)
    stranger_things.add_season(season1)
    netflix.add_content(stranger_things)

    # Kids can't watch age-restricted content
    print(f"Kids can watch Inception: {kids_profile.can_watch(inception)}")   # False (PG-13 > 7)
    print(f"Kids can watch Frozen: {kids_profile.can_watch(frozen)}")         # True  (U = 0)
    print(f"Kids can watch ST: {kids_profile.can_watch(stranger_things)}")    # False (A = 18)

    # Stream content
    session1 = netflix.stream(adult_profile, inception.id, DeviceType.TV)
    session1.update_position(3600)   # 1 hour in
    session1.pause()
    print(f"Resume position: {adult_profile.get_resume_position(inception)}s")  # 3600

    # Resume on another device
    session2 = netflix.stream(adult_profile, inception.id, DeviceType.LAPTOP)
    print(f"Session 2 starts at: {session2.position_sec}s")   # 3600 (resumed!)

    # Search
    results = netflix.search("inception")
    print(f"Search results: {results}")

    # Recommendations
    adult_profile.rate_content(inception, thumbs_up=True)
    recs = netflix.get_recommendations(adult_profile)
    print(f"Recommendations: {recs}")
```

---

## STEP 4 — Java Key Patterns

```java
// netflix_lld.java — Key Java implementations

// ── Content Hierarchy (Template Method + Composite) ────────────────────────────
abstract class Content {
    protected final String id = UUID.randomUUID().toString();
    protected final String title, description, contentRating, thumbnailUrl;
    protected final List<String> genres;
    protected volatile boolean isAvailable = true;

    Content(String title, String description, List<String> genres,
            String contentRating, String thumbnailUrl) {
        this.title = title; this.description = description; this.genres = genres;
        this.contentRating = contentRating; this.thumbnailUrl = thumbnailUrl;
    }

    // Template method: subclasses MUST implement these
    public abstract String getStreamUrl();
    public abstract int getDurationMinutes();

    public boolean matchesSearch(String query) {
        String q = query.toLowerCase();
        return title.toLowerCase().contains(q)
            || genres.stream().anyMatch(g -> g.toLowerCase().contains(q))
            || description.toLowerCase().contains(q);
        // stream().anyMatch() = iterate genres, return true if ANY matches
    }
    public String getId()    { return id; }
    public String getTitle() { return title; }
    @Override public String toString() { return getClass().getSimpleName() + "(" + title + ")"; }
}

class Movie extends Content {
    private final String streamUrl;
    private final int durationMin;
    private final int releaseYear;

    Movie(String title, String desc, List<String> genres, String rating,
          String thumb, String url, int dur, int year) {
        super(title, desc, genres, rating, thumb);
        streamUrl = url; durationMin = dur; releaseYear = year;
    }

    @Override public String getStreamUrl()       { return streamUrl; }
    @Override public int    getDurationMinutes() { return durationMin; }
}

class Season {
    final Show show;
    final int number;
    private final Map<Integer, Episode> episodes = new ConcurrentHashMap<>();

    Season(Show show, int number) { this.show = show; this.number = number; }
    void addEpisode(Episode ep) { episodes.put(ep.getEpisodeNumber(), ep); }
    Optional<Episode> getEpisode(int n) { return Optional.ofNullable(episodes.get(n)); }
    int getEpisodeCount() { return episodes.size(); }
    List<Episode> getEpisodes() {
        return episodes.values().stream()
            .sorted(Comparator.comparingInt(Episode::getEpisodeNumber))
            .collect(java.util.stream.Collectors.toList());
    }
}

class Show extends Content {
    private final Map<Integer, Season> seasons = new ConcurrentHashMap<>();

    Show(String title, String desc, List<String> genres, String rating, String thumb) {
        super(title, desc, genres, rating, thumb);
    }

    void addSeason(Season s) { seasons.put(s.number, s); }

    Optional<Season> getSeason(int n) { return Optional.ofNullable(seasons.get(n)); }

    @Override public String getStreamUrl() {
        return getSeason(1).flatMap(s -> s.getEpisode(1))
            .map(Episode::getStreamUrl).orElse("");
        // Chained Optionals: get season 1 → get episode 1 → get URL → or ""
    }

    @Override public int getDurationMinutes() {
        return seasons.values().stream()
            .flatMap(s -> s.getEpisodes().stream())   // Flatten all episodes across all seasons
            .mapToInt(Episode::getDurationMinutes)      // Map each to its duration
            .sum();                                     // Sum all durations
    }
}

class Episode extends Content {
    private final Season season;
    private final int episodeNumber;
    private final String streamUrl;
    private final int durationMin;

    Episode(String title, Season season, int num, String url, int dur) {
        super(title, "S" + season.number + "E" + num + " of " + season.show.title,
              season.show.genres, season.show.contentRating, season.show.thumbnailUrl);
        this.season = season; episodeNumber = num; streamUrl = url; durationMin = dur;
    }

    @Override public String getStreamUrl()       { return streamUrl; }
    @Override public int    getDurationMinutes() { return durationMin; }
    public    int    getEpisodeNumber()          { return episodeNumber; }
}

// ── WatchSession (State Machine) ───────────────────────────────────────────────
class WatchSession {
    enum State { PLAYING, PAUSED, COMPLETED, BUFFERING }

    private final String id = UUID.randomUUID().toString();
    private final Profile profile;
    private final Content content;
    private volatile int positionSec;
    private volatile State state = State.PLAYING;
    private final java.time.Instant startedAt = java.time.Instant.now();

    WatchSession(Profile profile, Content content, int startPos) {
        this.profile = profile; this.content = content; positionSec = startPos;
    }

    synchronized void updatePosition(int sec) {
        if (state == State.COMPLETED) return;
        positionSec = sec;
        profile.recordWatch(content, sec, false);  // Update resume point
    }

    synchronized void pause() {
        if (state == State.PLAYING) {
            state = State.PAUSED;
            profile.recordWatch(content, positionSec, false);
        }
    }

    synchronized void resume() { if (state == State.PAUSED) state = State.PLAYING; }

    synchronized void complete() {
        state = State.COMPLETED;
        profile.recordWatch(content, content.getDurationMinutes() * 60, true);
    }

    State getState()      { return state; }
    int   getPositionSec(){ return positionSec; }
}

// ── RecommendationEngine (Strategy) ────────────────────────────────────────────
interface RecommendationStrategy {
    List<Content> recommend(Profile profile, List<Content> catalog, int limit);
}

class ContentBasedStrategy implements RecommendationStrategy {
    @Override
    public List<Content> recommend(Profile profile, List<Content> catalog, int limit) {
        // Build genre preference map from watch history
        Map<String, Double> genreScores = new HashMap<>();
        for (WatchHistoryEntry entry : profile.getHistory()) {
            double weight = entry.completionPercent() / 100.0;
            for (String genre : entry.content().genres)
                genreScores.merge(genre, weight, Double::sum);
                // merge(key, value, remappingFn): if key exists, apply fn(existing, new)
                // Double::sum = method reference to Double.sum(a, b) = a + b
        }

        if (genreScores.isEmpty())
            return catalog.stream().limit(limit).collect(java.util.stream.Collectors.toList());

        Set<String> watchedIds = profile.getHistory().stream()
            .map(e -> e.content().getId()).collect(java.util.stream.Collectors.toSet());

        return catalog.stream()
            .filter(c -> !watchedIds.contains(c.getId()))
            .filter(c -> profile.canWatch(c))
            .sorted(Comparator.comparingDouble(c ->
                -c.genres.stream().mapToDouble(g -> genreScores.getOrDefault(g, 0.0)).sum()))
                // - prefix = negate score → sort descending (highest score first)
            .limit(limit)
            .collect(java.util.stream.Collectors.toList());
    }
}

// ── Profile ────────────────────────────────────────────────────────────────────
record WatchHistoryEntry(Content content, int watchedSeconds, boolean isComplete, java.time.Instant watchedAt) {
    double completionPercent() {
        int dur = content.getDurationMinutes() * 60;
        return dur == 0 ? 0 : Math.min(100.0, watchedSeconds * 100.0 / dur);
    }
}

class Profile {
    private final String id = UUID.randomUUID().toString();
    private final User user;
    private final String name;
    private final int ageLimit;
    private final Map<String, WatchHistoryEntry> watchHistory = new ConcurrentHashMap<>();
    private final Set<String> watchlist = ConcurrentHashMap.newKeySet();
    private final Map<String, Double> ratings = new ConcurrentHashMap<>();

    Profile(User user, String name, int ageLimit) {
        this.user = user; this.name = name; this.ageLimit = ageLimit;
    }

    boolean canWatch(Content c) {
        Map<String, Integer> ageMap = Map.of("U",0,"UA",7,"PG-13",13,"A",18,"R",17);
        return ageLimit >= ageMap.getOrDefault(c.contentRating, 0);
    }

    void recordWatch(Content c, int secs, boolean complete) {
        watchHistory.put(c.getId(), new WatchHistoryEntry(c, secs, complete, java.time.Instant.now()));
    }

    int getResumePosition(Content c) {
        WatchHistoryEntry e = watchHistory.get(c.getId());
        return e != null ? e.watchedSeconds() : 0;
    }

    List<WatchHistoryEntry> getHistory() {
        return watchHistory.values().stream()
            .sorted(Comparator.comparing(WatchHistoryEntry::watchedAt).reversed())
            .collect(java.util.stream.Collectors.toList());
    }

    User   getUser()  { return user; }
    String getName()  { return name; }
}
```

---

## STEP 5 — Trade-offs

```
TRADE-OFF 1: Content inheritance (Movie/Show) vs Composition
  Inheritance: Movie extends Content. Works fine here (IS-A relationship is clear).
  Composition: Content has a ContentType + ContentMetadata (type-specific data).
  When to use which?
  - 2-3 content types that rarely change: inheritance fine.
  - 10+ content types (podcasts, shorts, live streams, trailers): composition scales better.
  
  Netflix actually uses: microservice per content type. No inheritance across services.

TRADE-OFF 2: ConcurrentHashMap for watchHistory vs synchronized Map
  ConcurrentHashMap: lock-free reads, fine-grained writes. Each key-value pair has its own lock.
  Heartbeats (every 10 sec per user) update watchHistory → very frequent writes.
  ConcurrentHashMap handles concurrent heartbeats from multiple devices.
  
  Limitation: ConcurrentHashMap doesn't guarantee ordering.
  To get sorted history: use TreeMap (sorted) with ReentrantReadWriteLock.
  Or: sort at query time (as we do in getHistory()).

TRADE-OFF 3: Recommendation in-process vs microservice
  In-process (what we built): recommendation runs in same JVM/process as streaming.
  Fast (no network call). Simple.
  
  Real Netflix: Recommendation is a separate microservice (Jupyter notebooks → Python models).
  Why separate? ML model updates (retrain every hour) shouldn't require Netflix restart.
  Interface stays the same: recommendFor(profileId) → List<contentId>.
  Implementation can be updated independently.

TRADE-OFF 4: Resume position heartbeat vs event-driven
  Heartbeat (what we have): player sends position every 10 seconds.
  Pros: simple, works even if server doesn't send ack.
  Cons: at 200M users × 10 second heartbeat = 20M writes/sec on watch-history service.
  
  Event-driven: only send on pause, seek, or significant milestone (25%, 50%, 75%, 100%).
  Reduces writes to maybe 10% of heartbeat frequency.
  Real Netflix uses this approach with Kafka.

TRADE-OFF 5: Signed streaming URLs vs session tokens
  Open CDN URL: anyone who gets the URL can stream the content.
  Signed URL: URL includes signature = f(content_id, user_id, expiry, secret_key).
  CDN validates signature on every request. Expired or tampered → 403 Forbidden.
  
  Netflix: signed URLs with 24-hour expiry. Generated fresh per session.
  This prevents URL sharing (you can't share a Netflix link and have it work for someone else).
```

---

## STEP 6 — Interview Follow-Ups

```
Q: "How does Netflix handle 200M concurrent users streaming?"
A: 
  - 99% of traffic served from Open Connect Appliances (OCA) co-located with ISPs.
  - Each ISP gets a server with local copies of popular content.
  - User in Mumbai streams from Jio's data center — never hits Netflix AWS.
  - Remaining 1% (rare content, new content): served from AWS CloudFront CDN.
  
  In LLD: StreamingService.getStreamUrl() returns a CDN URL.
  The CDN handles scale — the app server only generates the URL.

Q: "How does the recommendation system actually work (Netflix Prize)?"
A:
  Two main approaches, combined:
  1. Collaborative Filtering: "Users similar to you also liked..."
     Find users with similar watch history → recommend what they watched but you haven't.
     ALS (Alternating Least Squares) matrix factorization in Apache Spark.
  
  2. Content-Based: "Because you watched Inception (Sci-Fi, Thriller)..."
     Find content with similar genre/actor/director metadata.
     Word embeddings for description similarity.
  
  3. Contextual: "On Friday evening, you usually watch Action movies."
     Time of day, day of week, device type affect recommendations.
  
  In LLD: Show IRecommendationStrategy as the interface. ContentBasedStrategy as one impl.
  "In prod we'd add CollaborativeFilteringStrategy and HybridStrategy."

Q: "How do you implement download for offline viewing?"
A:
  DRM (Digital Rights Management):
  1. User requests download → server returns a Widevine/FairPlay license.
  2. License has: content key + expiry time (e.g., 30 days, 48 hours after first play).
  3. Video is encrypted with content key. Stored on device.
  4. At play time: DRM library decrypts on-the-fly. Key in secure enclave (can't extract).
  
  In LLD:
  DownloadService.requestDownload(profile, content_id)
  → returns DownloadedContent(encrypted_file_path, license, expiry_at)
  
  License check on play: if now > expiry_at → DownloadExpiredException → must re-download.

Q: "Multiple profiles sharing one account — how do you prevent cross-contamination?"
A:
  Profile ID is the key for ALL data stores:
  - watchHistory is keyed by profile.id (not user.id)
  - ratings keyed by profile.id
  - recommendations computed per profile.id
  
  The only thing shared at user level: subscription tier (screen limit, quality limit).
  Everything else is profile-scoped. "Sachin" profile's horror ratings don't affect "Kids" profile.
```

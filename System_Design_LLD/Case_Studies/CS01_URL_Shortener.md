# CS01: LLD — URL Shortener (TinyURL / bit.ly)
## Every Line Explained | Python + Java + C++ | MAANG Interview Ready

---

> **HOW TO READ THIS FILE**
> Every code block has two parts:
> 1. The actual code
> 2. A `# WHAT THIS DOES:` comment or plain-English explanation immediately after
> Read BOTH. The explanations are NOT optional.

---

## STEP 1 — Requirements & Entities

```
WHAT WE'RE BUILDING:
  A service that takes a long URL and returns a short code.
  E.g.: https://www.google.com/very/long/search?q=system+design → sho.rt/a3Xz9kP

FUNCTIONAL REQUIREMENTS (what it must DO):
  1. ShortenUrl(longUrl) → shortCode
     ↳ User gives us a long URL, we give back a 7-character code
  
  2. GetLongUrl(shortCode) → longUrl (or None if not found)
     ↳ User gives us a code, we redirect them to the original URL
  
  3. DeleteUrl(shortCode) → bool
     ↳ User can delete their short link
  
  4. Custom alias support
     ↳ User can request their own custom code: sho.rt/my-brand
  
  5. URL expiry (TTL)
     ↳ URLs can be set to expire after N seconds
```

**WHAT THIS MEANS:**
- Start EVERY LLD interview by writing functional requirements. This shows the interviewer you think before coding.
- "Functional" = what the user can DO with the system.
- "Non-functional" = how fast/available/reliable it is (latency, uptime, scale).

```
KEY ENTITIES (nouns → classes):
  UrlEntry       — the data model (longUrl, shortCode, expiry, ownerId)
  CodeGenerator  — generates unique 7-char base62 codes
  UrlRepository  — CRUD against storage (in-memory or DB-backed)
  CacheLayer     — wraps repository with Redis-like LRU cache
  UrlShortener   — main service orchestrating the above
  RedirectService— resolves shortCode → longUrl (read-heavy path)
```

**WHAT "KEY ENTITIES" MEANS:**
- Look at your requirements. Find all the **nouns** (things). Each noun becomes a class.
- `UrlEntry` = the thing that gets stored (a URL record)
- `CodeGenerator` = the thing that makes short codes
- `UrlRepository` = the thing that reads/writes to the database
- `CacheLayer` = the thing that provides fast lookup (avoids hitting DB every time)
- `UrlShortener` = the main controller that orchestrates everything
- `RedirectService` = the thing optimized for the READ path (578K reads/sec)

---

## STEP 2 — Class Diagram (UML ASCII)

```
[CodeGenerator]         [UrlEntry]                 [IUrlRepository]
───────────────         ──────────                 ────────────────
- CHARS: str            - shortCode: str           + save(entry): None
- _instance: Self       - longUrl: str             + find(code): UrlEntry?
───────────────         - ownerId: int             + delete(code): bool
+ generate(url): str    - createdAt: datetime      + exists(code): bool
+ encode(n): str        - expiresAt: datetime?
+ decode(s): int        - isActive: bool           [InMemoryUrlRepository]
                        ──────────                 implements IUrlRepository
                        + is_expired(): bool
                        + to_dict(): dict          [ICacheLayer]
                                                   ──────────────
[UrlShortener]          [RedirectService]          + get(key): str?
──────────────          ────────────────           + set(key, val, ttl): None
- _repo: IUrlRepository - _repo: IUrlRepository   + delete(key): None
- _cache: ICacheLayer   - _cache: ICacheLayer
- _gen: CodeGenerator   ────────────────           [LRUCache]
──────────────          + resolve(code): str       implements ICacheLayer
+ shorten(url): str     + is_healthy(): bool
+ delete(code): bool
+ get_stats(): dict

RELATIONSHIPS:
  UrlShortener HAS-A IUrlRepository  (injected — DIP)
  UrlShortener HAS-A ICacheLayer     (injected — DIP)
  UrlShortener HAS-A CodeGenerator   (composition)
  RedirectService HAS-A IUrlRepository + ICacheLayer

PATTERNS USED:
  Singleton    → CodeGenerator (one instance, globally shared)
  Strategy     → IUrlRepository (swap in-memory ↔ PostgreSQL — same interface)
  Facade       → UrlShortener (hides all sub-components behind one simple API)
  Proxy        → CacheLayer wraps repository (transparent caching — caller doesn't know)
```

**WHAT THE DIAGRAM MEANS:**
- `+` before a method = public (anyone can call it)
- `-` before a field = private (only the class itself can access it)
- `IUrlRepository` = an **interface** (a contract). The `I` prefix is a naming convention for interfaces.
- `implements IUrlRepository` = `InMemoryUrlRepository` promises to provide all methods defined in `IUrlRepository`.
- **HAS-A** = one class contains another as a member variable. UrlShortener HAS-A repository.
- **DIP (Dependency Inversion Principle)** = UrlShortener depends on the abstract `IUrlRepository` interface, NOT on the concrete `InMemoryUrlRepository`. This means you can swap PostgreSQL in without touching UrlShortener.

---

## STEP 3 — Python Implementation (Every Line Explained)

```python
# ─────────────────────────────────────────────────────────────────────────────
# WHAT THIS FILE IS:
# A complete, runnable implementation of a URL shortener in Python.
# Every class and every line is explained.
# ─────────────────────────────────────────────────────────────────────────────

# WHY "from __future__ import annotations":
# Without this, "Optional[CodeGenerator]" in a class body would fail because
# CodeGenerator isn't defined yet when Python reads that line.
# This import makes ALL type hints strings (evaluated lazily), solving the problem.
from __future__ import annotations

import time        # for time.time() — current Unix timestamp as float
import hashlib     # for MD5 hashing (to generate short codes from URLs)
import threading   # for thread locks (make code safe when multiple threads run simultaneously)

from abc import ABC, abstractmethod
# ABC = Abstract Base Class. Classes that inherit ABC cannot be instantiated directly.
# abstractmethod = marks a method as "must be overridden by subclass"
# WHY: We want IUrlRepository to be a contract — you can't create it, you must implement it.

from collections import OrderedDict
# OrderedDict = a dict that remembers insertion order
# WHY: We use it for LRU cache — we need to track which item was accessed most recently

from dataclasses import dataclass, field
# @dataclass = decorator that auto-generates __init__, __repr__, __eq__ for a class
# field() = needed for mutable default values in dataclasses (e.g., field(default_factory=datetime.utcnow))
# WHY: UrlEntry is a simple data container. @dataclass saves writing 30 lines of boilerplate.

from typing import Optional
# Optional[X] means "either X or None"
# e.g., Optional[datetime] = either a datetime object, or None (meaning "no expiry")

from datetime import datetime, timedelta
# datetime = a point in time (year, month, day, hour, minute, second)
# timedelta = a duration (e.g., timedelta(seconds=3600) = 1 hour)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1: VALUE OBJECT — UrlEntry
# A "Value Object" = a class whose purpose is to hold data, not do business logic.
# ══════════════════════════════════════════════════════════════════════════════

@dataclass          # AUTO-GENERATES: __init__, __repr__, __eq__ based on the fields below
class UrlEntry:
    """Represents one stored URL record."""

    # WHY "short_code: str" instead of just a variable?
    # This is a "field declaration" in @dataclass syntax.
    # When you write UrlEntry("abc123", "https://..."), Python auto-assigns these.
    short_code: str          # The 7-character code we generated (e.g., "a3Xz9kP")
    long_url:   str          # The original URL the user submitted
    owner_id:   int      = 0 # 0 = anonymous. If user is logged in, their user ID goes here.

    # field(default_factory=...) is needed for mutable defaults.
    # WHY NOT just "created_at: datetime = datetime.utcnow()"?
    # That would call datetime.utcnow() ONCE when the class is defined, sharing one timestamp.
    # field(default_factory=...) calls datetime.utcnow() each time a new UrlEntry is created.
    created_at: datetime = field(default_factory=datetime.utcnow)

    expires_at: Optional[datetime] = None  # None means "never expires"
    is_active:  bool     = True            # False = soft-deleted (not visible but still in DB)
    click_count: int     = 0               # How many times this URL was accessed

    def is_expired(self) -> bool:
        """Returns True if this URL has passed its expiry time."""
        if self.expires_at is None:        # No expiry set → never expires
            return False
        return datetime.utcnow() > self.expires_at  # Current time is past the expiry time

    def is_valid(self) -> bool:
        """Returns True if this URL can be used (active AND not expired)."""
        return self.is_active and not self.is_expired()
        # Both conditions must be true:
        # - is_active: the URL hasn't been deleted
        # - not is_expired: the URL's time limit hasn't passed

    def increment_clicks(self) -> None:
        """Records one more redirect through this URL."""
        self.click_count += 1
        # NOTE: In production, this would be done asynchronously via Kafka
        # to avoid holding up the redirect. Incrementing here is simplified for LLD.


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2: CODE GENERATOR — Singleton Pattern + Base62 Encoding
# ══════════════════════════════════════════════════════════════════════════════

class CodeGenerator:
    """
    Generates unique 7-character short codes.
    
    SINGLETON PATTERN: Only ONE instance of CodeGenerator ever exists.
    WHY SINGLETON HERE? The generator has no state that varies between calls.
    Creating a new one each time wastes memory. One shared instance is enough.
    
    BASE62 ENCODING: We convert a large number to a string using 62 characters
    (0-9, a-z, A-Z). Like base-10 (decimal) or base-16 (hex), but base-62.
    WHY BASE62? 62^7 = 3.5 trillion unique codes. URL-safe (no special chars).
    """

    # Class-level constants (shared by ALL instances and accessible on the class itself)
    CHARS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    # CHARS has 62 characters: digits (10) + lowercase letters (26) + uppercase letters (26)
    # This is our "alphabet" for encoding numbers

    BASE  = 62    # We're working in base 62 (like decimal is base 10)
    CODE_LEN = 7  # We want exactly 7 characters in our short code

    # These are CLASS-LEVEL VARIABLES (not instance variables):
    # Shared across ALL instances. Used for Singleton pattern.
    _instance: Optional[CodeGenerator] = None  # Holds the single instance (or None)
    _lock = threading.Lock()  # Mutex lock to make Singleton creation thread-safe

    def __new__(cls) -> CodeGenerator:
        """
        __new__ is called BEFORE __init__. It's responsible for creating the object.
        We override it to implement the Singleton pattern.
        
        DOUBLE-CHECKED LOCKING:
        1. First check (without lock): if instance exists, return it immediately (fast path)
        2. Only acquire lock if instance is None (slow path)
        3. Second check (with lock): another thread might have created instance while we waited for lock
        """
        if cls._instance is None:                # FIRST CHECK: no lock, fast
            with cls._lock:                      # Acquire lock (only one thread at a time)
                if cls._instance is None:        # SECOND CHECK: inside lock, safe
                    cls._instance = super().__new__(cls)  # Actually create the object
        return cls._instance                     # Return the (only ever) instance

    def encode(self, num: int) -> str:
        """
        Convert an integer to a base62 string.
        
        EXAMPLE: encode(100_000_000)
          100000000 % 62 = 52 → CHARS[52] = 'Q'
          100000000 // 62 = 1612903
          1612903 % 62 = 57 → CHARS[57] = 'V'
          ... repeat until num = 0
          Reverse the characters → final code
        
        Think of it like converting decimal to hex, but base 62.
        """
        if num == 0:
            return self.CHARS[0]  # Edge case: 0 encodes to "0"
        result = []
        while num > 0:
            result.append(self.CHARS[num % self.BASE])  # Take the rightmost "digit"
            num //= self.BASE                           # Shift right (integer division)
        return ''.join(reversed(result))                # Reverse because we built it backwards

    def decode(self, code: str) -> int:
        """
        Reverse of encode: base62 string → integer.
        EXAMPLE: decode("a3") = 10*62 + 3 = 623
        """
        result = 0
        for char in code:
            # Like reading a decimal number: 'a3' = (value_of_a * 62) + value_of_3
            result = result * self.BASE + self.CHARS.index(char)
        return result

    def generate(self, long_url: str, user_id: int = 0, attempt: int = 0) -> str:
        """
        Generate a 7-char short code from a URL.
        
        HOW:
        1. Combine: long_url + user_id + attempt number + current time (nanoseconds)
           ↳ "attempt" is used when we retry because of a collision (same code already exists)
           ↳ time.time_ns() adds nanosecond timestamp to ensure uniqueness even for same URL
        2. MD5 hash the combined string → 128-bit hash (as a hex string)
        3. Convert hex string → integer
        4. Reduce to 7-char range: integer % (62^7) 
        5. Encode to base62 → 7-character code
        """
        raw = f"{long_url}{user_id}{attempt}{time.time_ns()}"
        # Combine all inputs into one string to hash

        hashed = int(hashlib.md5(raw.encode()).hexdigest(), 16)
        # md5() = hash function that produces a 128-bit number
        # .encode() = convert Python str to bytes (md5 requires bytes input)
        # .hexdigest() = return hash as a 32-character hex string like "a1b2c3..."
        # int(..., 16) = convert hex string to a Python integer (base 16)

        code = self.encode(hashed % (self.BASE ** self.CODE_LEN))
        # hashed % (62^7) = reduce to a number that can be encoded in 7 base62 chars
        # encode() = convert that number to our 7-char string

        return code.zfill(self.CODE_LEN)[:self.CODE_LEN]
        # zfill(7) = pad with '0' on the left if shorter than 7 chars
        # [:7] = ensure exactly 7 chars (trim if somehow longer)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3: REPOSITORY INTERFACE — Strategy Pattern
# ══════════════════════════════════════════════════════════════════════════════

class IUrlRepository(ABC):
    """
    INTERFACE: Defines the contract for URL storage.
    
    STRATEGY PATTERN:
    - IUrlRepository is the "strategy interface"
    - InMemoryUrlRepository = strategy for development/testing
    - PostgresUrlRepository = strategy for production
    - UrlShortener only knows about IUrlRepository, not the concrete implementation
    
    WHY THIS MATTERS:
    - In interviews: you can swap storage without touching UrlShortener
    - In testing: use InMemoryUrlRepository instead of real PostgreSQL
    - In migration: swap PostgreSQL → DynamoDB by writing new class, not changing existing code
    """

    @abstractmethod
    def save(self, entry: UrlEntry) -> None:
        """Store a UrlEntry. Overwrites if short_code already exists."""
        pass    # 'pass' = empty body. Subclasses MUST implement this.

    @abstractmethod
    def find(self, short_code: str) -> Optional[UrlEntry]:
        """Find a UrlEntry by its short code. Returns None if not found."""
        pass

    @abstractmethod
    def delete(self, short_code: str) -> bool:
        """Delete a UrlEntry. Returns True if deleted, False if not found."""
        pass

    @abstractmethod
    def exists(self, short_code: str) -> bool:
        """Returns True if this short_code is already taken."""
        pass


class InMemoryUrlRepository(IUrlRepository):
    """
    IN-MEMORY IMPLEMENTATION of IUrlRepository.
    Stores everything in a Python dict. Lost on restart. Good for testing.
    
    THREAD SAFETY:
    Uses threading.RLock() — a Reentrant Lock.
    WHY RLock instead of Lock?
      - RLock allows the SAME thread to acquire the lock multiple times (re-entrantly).
      - If method A (holding lock) calls method B (needs same lock), RLock works; Lock would deadlock.
    """

    def __init__(self):
        self._store: dict[str, UrlEntry] = {}
        # _store: Python dict from short_code string → UrlEntry object
        # Underscore prefix (_store) = "private by convention" — don't access from outside

        self._lock  = threading.RLock()
        # RLock = Reentrant Lock. One thread can acquire it multiple times without deadlocking.

    def save(self, entry: UrlEntry) -> None:
        with self._lock:           # Acquire lock. Released automatically when block exits.
            self._store[entry.short_code] = entry  # Store: key = code, value = UrlEntry

    def find(self, short_code: str) -> Optional[UrlEntry]:
        with self._lock:
            return self._store.get(short_code)
            # dict.get(key) returns None if key doesn't exist (vs dict[key] which raises KeyError)

    def delete(self, short_code: str) -> bool:
        with self._lock:
            if short_code in self._store:
                del self._store[short_code]        # Remove the key
                return True                        # Confirm deletion
            return False                           # Nothing to delete

    def exists(self, short_code: str) -> bool:
        with self._lock:
            return short_code in self._store       # 'in' operator checks dict keys


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4: CACHE LAYER — Proxy Pattern + LRU Eviction
# ══════════════════════════════════════════════════════════════════════════════

class ICacheLayer(ABC):
    """
    INTERFACE for the caching layer.
    In production: this would be backed by Redis.
    In this LLD: we implement a simple in-memory LRU cache.
    
    PROXY PATTERN:
    - CacheLayer sits between UrlShortener and IUrlRepository
    - Caller asks cache → if hit, returns immediately (fast)
    - If miss, cache transparently fetches from real storage (slow)
    - Caller doesn't know whether it got a cache hit or miss
    """

    @abstractmethod
    def get(self, key: str) -> Optional[str]: pass
    # Returns the cached string value, or None if not cached

    @abstractmethod
    def set(self, key: str, value: str, ttl_secs: int = 86400) -> None: pass
    # Cache this key→value pair for ttl_secs seconds (default 24 hours)

    @abstractmethod
    def delete(self, key: str) -> None: pass
    # Remove from cache (called when URL is deleted/updated)


class LRUCache(ICacheLayer):
    """
    LRU = Least Recently Used.
    When cache is full, evicts the item that was LEAST recently accessed.
    
    HOW:
    Uses an OrderedDict — a dict that remembers access order.
    On every get(), we move that item to the END (most recently used).
    When capacity exceeded, we remove from the FRONT (least recently used).
    
    ALSO supports TTL: each value stores its expiry timestamp.
    On get(), if expired → remove and return None (as if not cached).
    """

    def __init__(self, capacity: int = 1000):
        self._cap   = capacity   # Max number of items to store
        # OrderedDict preserves insertion/access order
        # We store: key → (value, expiry_timestamp_as_float)
        self._cache: OrderedDict[str, tuple[str, float]] = OrderedDict()
        self._lock  = threading.RLock()

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            if key not in self._cache:
                return None         # Cache miss → return None

            value, expires_at = self._cache[key]
            # Unpack the tuple: first element = value string, second = expiry timestamp

            if time.time() > expires_at:
                # time.time() = current time as Unix timestamp (seconds since 1970)
                # If current time > expiry → this entry has expired
                del self._cache[key]    # Evict expired entry
                return None             # Treat as cache miss

            # MOVE TO END = mark as "most recently used"
            # OrderedDict.move_to_end(key) moves item to back of order
            self._cache.move_to_end(key)
            return value

    def set(self, key: str, value: str, ttl_secs: int = 86400) -> None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)    # Already exists: update and move to front
            self._cache[key] = (value, time.time() + ttl_secs)
            # Store: value + expiry timestamp (current time + TTL seconds)

            if len(self._cache) > self._cap:
                # Cache is overfull — evict the LEAST recently used item
                # last=False means pop from the FRONT (oldest/LRU end)
                self._cache.popitem(last=False)

    def delete(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)
            # pop(key, default) — if key exists, remove and return it. If not, return None.
            # We use None as default so it doesn't raise KeyError if key doesn't exist.


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5: URL SHORTENER — Facade Pattern
# ══════════════════════════════════════════════════════════════════════════════

class UrlShortener:
    """
    FACADE PATTERN:
    Hides the complexity of CodeGenerator + IUrlRepository + ICacheLayer
    behind a single, simple interface.
    
    The caller (client code) only talks to UrlShortener.
    It doesn't know about repositories, caches, or code generation.
    
    WHY FACADE?
    - Without Facade: caller must create CodeGenerator, IUrlRepository, ICacheLayer,
      call them in the right order, handle their interactions. Complex!
    - With Facade: caller calls shortener.shorten("https://..."). Done.
    """

    CACHE_PREFIX = "short:"
    # All cache keys are prefixed with "short:" to avoid namespace collisions
    # e.g., "short:a3Xz9kP" in cache
    # WHY: If you also cache user data in the same Redis, keys like "a3Xz9kP" might
    # collide with user IDs. Prefix namespaces the keys.

    MAX_ATTEMPTS = 5
    # If the generated code already exists (collision), try up to 5 times.
    # After 5 failures, something is wrong — raise an error.

    def __init__(self, repo: IUrlRepository, cache: ICacheLayer):
        # DEPENDENCY INJECTION: repo and cache are PASSED IN, not created here.
        # WHY: UrlShortener doesn't decide WHICH storage or cache to use.
        # The caller decides. This is the Dependency Inversion Principle (DIP).
        self._repo  = repo      # Storage backend (InMemory or Postgres)
        self._cache = cache     # Caching layer (LRU or Redis)
        self._gen   = CodeGenerator()   # Singleton — same instance every time

    def shorten(
        self,
        long_url:  str,
        user_id:   int = 0,
        alias:     Optional[str] = None,    # Custom alias (e.g., "my-brand")
        ttl_secs:  Optional[int] = None,    # Expiry in seconds (None = never)
    ) -> str:
        """
        Main method: take a long URL, return a short code.
        
        FLOW:
        1. Validate URL format
        2. Determine short code (alias or auto-generated)
        3. Build UrlEntry with expiry
        4. Save to repository (database)
        5. Warm the cache (so first read is fast)
        6. Return the code
        """

        # VALIDATION: Only allow http:// and https:// URLs
        if not long_url.startswith(("http://", "https://")):
            raise ValueError(f"Invalid URL scheme: {long_url}")
        # startswith() can take a TUPLE of strings to check multiple prefixes

        short_code = self._resolve_code(long_url, user_id, alias)
        # Figure out the code to use (either use the alias or generate one)

        # CALCULATE EXPIRY TIME:
        expires_at = None
        if ttl_secs:
            expires_at = datetime.utcnow() + timedelta(seconds=ttl_secs)
            # datetime.utcnow() = current time in UTC (universal time, not local time)
            # timedelta(seconds=N) = a duration of N seconds
            # Adding them gives us the exact time when the URL should expire

        # CREATE THE RECORD:
        entry = UrlEntry(
            short_code=short_code,
            long_url=long_url,
            owner_id=user_id,
            expires_at=expires_at,
        )

        # SAVE TO STORAGE (database layer):
        self._repo.save(entry)

        # WARM THE CACHE:
        # Why cache IMMEDIATELY on write?
        # The URL was JUST created. It might be shared/clicked immediately.
        # Pre-caching avoids a DB lookup on the very first redirect.
        self._cache.set(
            f"{self.CACHE_PREFIX}{short_code}",   # key: "short:a3Xz9kP"
            long_url,                              # value: the original URL
            ttl_secs or 86400                      # TTL: use custom TTL or default 24h
            # "ttl_secs or 86400" = if ttl_secs is None (falsy), use 86400 (24h)
        )

        return short_code

    def _resolve_code(self, long_url: str, user_id: int,
                      alias: Optional[str]) -> str:
        """
        Determine what short code to use.
        If alias is provided: validate it's available.
        Otherwise: auto-generate and retry on collision.
        """
        if alias:
            if self._repo.exists(alias):
                raise ValueError(f"Alias '{alias}' is already taken")
                # User wants 'my-brand' but it's already used → error
            return alias
            # Alias is available → use it

        # AUTO-GENERATE: try up to MAX_ATTEMPTS times
        for attempt in range(self.MAX_ATTEMPTS):
            code = self._gen.generate(long_url, user_id, attempt)
            # attempt=0,1,2,3,4 — each attempt adds a different salt, producing a different hash

            if not self._repo.exists(code):
                return code         # Found a code that doesn't exist yet → use it

        # All 5 attempts had collisions (extremely unlikely but handle gracefully)
        raise RuntimeError("Could not generate unique code after 5 attempts")

    def delete(self, short_code: str) -> bool:
        """
        Delete a short URL (both from storage and cache).
        Returns True if deleted, False if didn't exist.
        """
        deleted = self._repo.delete(short_code)
        if deleted:
            # IMPORTANT: Remove from cache too, or redirects will still work
            # (cache serves stale data after deletion — a bug!)
            self._cache.delete(f"{self.CACHE_PREFIX}{short_code}")
        return deleted

    def get_stats(self, short_code: str) -> Optional[dict]:
        """Return metadata about a short URL (for the creator's dashboard)."""
        entry = self._repo.find(short_code)
        if not entry:
            return None     # URL doesn't exist
        return {
            "short_code": entry.short_code,
            "long_url":   entry.long_url,
            "clicks":     entry.click_count,
            "expired":    entry.is_expired(),
            "active":     entry.is_active,
        }
        # dict literal: {"key": value, ...} creates a Python dictionary


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6: REDIRECT SERVICE — Optimized Read Path
# ══════════════════════════════════════════════════════════════════════════════

class RedirectService:
    """
    Optimized for the READ-HEAVY path.
    The redirect service handles 578,700 requests/sec at peak.
    The shortener service handles only 5,785 writes/sec.
    
    WHY SEPARATE CLASS?
    Single Responsibility Principle: RedirectService has ONE job — fast resolution.
    It doesn't create/delete URLs. Only resolves shortCode → longUrl.
    
    FLOW:
    1. Check cache (< 1ms) → Cache HIT: return immediately ✓
    2. Check DB (2-5ms)   → DB HIT: cache it, then return ✓
    3. Neither            → 404 (not found) or 410 (expired) ✗
    """

    CACHE_PREFIX = "short:"

    def __init__(self, repo: IUrlRepository, cache: ICacheLayer):
        self._repo  = repo
        self._cache = cache

    def resolve(self, short_code: str) -> tuple[int, Optional[str]]:
        """
        Returns: (http_status_code, long_url_or_None)
        
        Status codes:
          200 → Found! Redirect to this URL.
          404 → Short code doesn't exist.
          410 → Gone. URL existed but was deleted/expired. (410 = "permanently gone")
        
        WHY RETURN A TUPLE?
        The caller (HTTP handler) needs both the status code (for HTTP response)
        and the URL (for the Location header in the redirect response).
        """

        # ── STEP 1: FAST PATH — Cache lookup ──────────────────────────────────
        # Redis/LRU lookup is < 1ms. This handles 80% of traffic.
        cached = self._cache.get(f"{self.CACHE_PREFIX}{short_code}")
        if cached:
            # CACHE HIT: return immediately without touching the DB
            return 200, cached
            # HTTP 200 means "OK". In practice the HTTP handler does a 302 redirect.

        # ── STEP 2: SLOW PATH — Database lookup ───────────────────────────────
        # Only reached on cache miss (~20% of requests)
        entry = self._repo.find(short_code)
        if not entry:
            # Code doesn't exist at all
            return 404, None    # HTTP 404 = Not Found

        if not entry.is_valid():
            # Exists but expired or deactivated
            return 410, None    # HTTP 410 = Gone (different from 404 — 410 says "existed but removed")

        # ── STEP 3: Warm cache + count click ──────────────────────────────────
        # Cache the result so next request is a CACHE HIT:
        self._cache.set(
            f"{self.CACHE_PREFIX}{short_code}",
            entry.long_url,
            86400           # Cache for 24 hours
        )

        # Increment click count:
        entry.increment_clicks()
        # NOTE: In production, this would be published to Kafka for async processing.
        # Synchronous DB update on every redirect at 578K/sec would crush the database.
        # Kafka approach: fire and forget, batch update click_count every minute.

        return 200, entry.long_url


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7: DEMO — Showing Everything Working Together
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # "__main__" check: this block only runs when you execute this file directly.
    # If this file is imported by another file, this block is SKIPPED.
    # WHY: Allows both "run as script" AND "import as module" behavior.

    # ── Wire up the dependencies ───────────────────────────────────────────────
    repo    = InMemoryUrlRepository()   # In-memory storage (use PostgresRepo in prod)
    cache   = LRUCache(capacity=500)    # LRU cache with 500-item limit (use Redis in prod)
    service = UrlShortener(repo, cache) # Facade: pass in repo and cache
    redir   = RedirectService(repo, cache)  # Read-path: shares same repo and cache

    # ── Test: Basic URL shortening ─────────────────────────────────────────────
    code1 = service.shorten("https://www.google.com/search?q=system+design", user_id=1)
    # code1 will be something like "a3Xz9kP" — a random 7-char string

    code2 = service.shorten(
        "https://github.com/sachin",
        user_id=1,
        alias="gh-sachin"   # Custom alias: sho.rt/gh-sachin
    )
    # code2 = "gh-sachin" (user chose this)

    code3 = service.shorten(
        "https://temp.com/page",
        ttl_secs=60         # Expires in 60 seconds
    )

    print(f"code1 = {code1}")   # e.g. "a3Xz9kP"
    print(f"code2 = {code2}")   # "gh-sachin"

    # ── Test: Redirect ─────────────────────────────────────────────────────────
    status, url = redir.resolve(code1)
    # Unpack tuple: first value → status, second value → url
    print(f"Resolve {code1}: {status} → {url}")
    # Expected: Resolve a3Xz9kP: 200 → https://www.google.com/search?q=system+design

    status, url = redir.resolve("notexist")
    print(f"Resolve notexist: {status} → {url}")
    # Expected: Resolve notexist: 404 → None

    # ── Test: Stats ────────────────────────────────────────────────────────────
    print(service.get_stats(code1))
    # Expected: {'short_code': 'a3Xz9kP', 'long_url': '...', 'clicks': 1, 'expired': False, 'active': True}
    # Note: clicks=1 because we called redir.resolve(code1) once above

    # ── Test: Delete ───────────────────────────────────────────────────────────
    print(service.delete(code2))        # Expected: True (deleted successfully)
    status, _ = redir.resolve(code2)    # Try to redirect after deletion
    print(f"After delete: {status}")    # Expected: 404 (no longer exists)
    # The underscore _ is a Python convention for "I don't care about this value"
```

---

## STEP 4 — Java Implementation (Every Line Explained)

```java
// ─────────────────────────────────────────────────────────────────────────────
// WHAT JAVA DOES DIFFERENTLY from Python:
// 1. Explicit types everywhere (int, String, Optional<UrlEntry>, etc.)
// 2. ConcurrentHashMap instead of dict + RLock (thread-safe built-in)
// 3. volatile keyword for fields accessed by multiple threads
// 4. synchronized keyword or java.util.concurrent classes for thread safety
// 5. record keyword (Java 16+) for immutable value objects
// ─────────────────────────────────────────────────────────────────────────────

import java.security.MessageDigest;   // For MD5 hashing
import java.time.Instant;             // Instant = point in time (like Python's datetime)
import java.util.*;                   // Map, List, LinkedHashMap, etc.
import java.util.concurrent.*;        // ConcurrentHashMap, CopyOnWriteArrayList
import java.util.concurrent.locks.*;  // ReentrantReadWriteLock, ReentrantLock


// ── UrlEntry: VALUE OBJECT ────────────────────────────────────────────────────
// WHY NOT A record? Records are immutable (no setters). UrlEntry has mutable
// clickCount and isActive. So we use a regular class.
class UrlEntry {
    private final String shortCode;   // final = can't be changed after construction
    private final String longUrl;
    private final int    ownerId;
    private final Instant createdAt;
    private final Instant expiresAt;  // null = never expires (Instant is nullable)

    // volatile: ensures changes are immediately visible to ALL threads.
    // Without volatile, one thread changing isActive might not be seen by another thread.
    private volatile boolean isActive = true;

    // AtomicInteger: thread-safe integer. clickCount++ would NOT be thread-safe
    // because ++ is not atomic (read + increment + write = 3 steps = race condition).
    // AtomicInteger.incrementAndGet() does all 3 as one atomic hardware instruction.
    private final java.util.concurrent.atomic.AtomicInteger clickCount
        = new java.util.concurrent.atomic.AtomicInteger(0);

    public UrlEntry(String shortCode, String longUrl, int ownerId, Instant expiresAt) {
        this.shortCode = shortCode;
        this.longUrl   = longUrl;
        this.ownerId   = ownerId;
        this.createdAt = Instant.now();   // Record when this entry was created
        this.expiresAt = expiresAt;       // null if no expiry
    }

    public boolean isExpired() {
        // If expiresAt is null → no expiry → not expired
        // Otherwise: check if current time is after the expiry time
        return expiresAt != null && Instant.now().isAfter(expiresAt);
        // Instant.now() = current UTC time
        // isAfter() = is current time AFTER the expiry? If yes → expired.
    }

    public boolean isValid() {
        return isActive && !isExpired();
        // Both conditions: active (not deleted) AND not expired
    }

    public void incrementClicks() {
        clickCount.incrementAndGet();  // Atomic: read+increment+write in one CPU instruction
    }

    // GETTERS: Java requires explicit getters (unlike Python where fields are accessed directly)
    public String  getShortCode()  { return shortCode; }
    public String  getLongUrl()    { return longUrl; }
    public int     getClickCount() { return clickCount.get(); }
    public boolean getIsActive()   { return isActive; }
    public void    deactivate()    { this.isActive = false; }
    // volatile write: all threads immediately see isActive = false
}

// ── IUrlRepository: STRATEGY INTERFACE ────────────────────────────────────────
// In Java, interfaces use 'interface' keyword (no ABC/abstractmethod needed)
// Methods in Java interfaces are implicitly abstract
interface IUrlRepository {
    void save(UrlEntry entry);               // Store an entry
    Optional<UrlEntry> find(String code);    // Optional = either UrlEntry or "empty"
    boolean delete(String code);             // Returns true if deleted
    boolean exists(String code);             // Returns true if code already used
}
// Optional<UrlEntry> is Java's way of saying "might be null, might be UrlEntry"
// This forces callers to explicitly handle the null case (better than NullPointerException)

// ── InMemoryUrlRepository: CONCRETE IMPLEMENTATION ────────────────────────────
class InMemoryUrlRepository implements IUrlRepository {
    // ConcurrentHashMap: thread-safe version of HashMap.
    // Multiple threads can READ simultaneously (no lock).
    // Writes use fine-grained segment locks (not one global lock like synchronized HashMap).
    private final Map<String, UrlEntry> store = new ConcurrentHashMap<>();

    @Override  // Annotation: documents this INTENTIONALLY overrides the interface method
    public void save(UrlEntry entry) {
        store.put(entry.getShortCode(), entry);  // ConcurrentHashMap.put is thread-safe
    }

    @Override
    public Optional<UrlEntry> find(String code) {
        return Optional.ofNullable(store.get(code));
        // store.get(code) returns null if not found
        // Optional.ofNullable(x) wraps x in Optional: if x is null → Optional.empty()
        // This forces the caller to call .isPresent() or .get() safely
    }

    @Override
    public boolean delete(String code) {
        return store.remove(code) != null;
        // store.remove(code) returns the REMOVED value, or null if key didn't exist
        // If returned value != null → deletion happened → return true
    }

    @Override
    public boolean exists(String code) {
        return store.containsKey(code);  // Returns true if key exists in map
    }
}

// ── ICacheLayer: CACHE INTERFACE (Proxy Pattern) ───────────────────────────────
interface ICacheLayer {
    Optional<String> get(String key);                    // Get cached value
    void set(String key, String value, int ttlSeconds);  // Cache with TTL
    void delete(String key);                             // Remove from cache
}

// ── LRUCache: CONCRETE CACHE IMPLEMENTATION ────────────────────────────────────
class LRUCache implements ICacheLayer {
    private final int capacity;

    // LinkedHashMap with accessOrder=true: moves accessed items to end of order
    // (most recently used at end, least recently used at front)
    private final LinkedHashMap<String, CacheEntry> cache;

    // ReadWriteLock: allows many concurrent readers BUT only one writer at a time
    // Better than synchronized(this) which allows only one thread at a time even for reads
    private final ReadWriteLock lock = new ReentrantReadWriteLock();

    // record: Java 16+ shorthand for immutable data class (auto-generates constructor, getters)
    // This is equivalent to Python @dataclass(frozen=True)
    record CacheEntry(String value, long expiresAt) {}
    // expiresAt is Unix timestamp in milliseconds

    public LRUCache(int capacity) {
        this.capacity = capacity;
        // Anonymous class that overrides removeEldestEntry to auto-evict LRU items:
        this.cache = new LinkedHashMap<>(capacity, 0.75f, true) {
            // capacity: initial size. 0.75f: load factor (resize when 75% full). true: access order
            @Override
            protected boolean removeEldestEntry(Map.Entry<String, CacheEntry> e) {
                return size() > capacity;
                // Automatically remove the oldest entry when size exceeds capacity
            }
        };
    }

    @Override
    public Optional<String> get(String key) {
        // Need WRITE lock (not read lock) because get() modifies order in LinkedHashMap
        lock.writeLock().lock();
        try {
            CacheEntry entry = cache.get(key);  // Also moves key to "most recently used" position
            if (entry == null) return Optional.empty();  // Cache miss

            if (System.currentTimeMillis() > entry.expiresAt()) {
                // currentTimeMillis() = current time in milliseconds
                // If current time > expiry → expired
                cache.remove(key);
                return Optional.empty();
            }
            return Optional.of(entry.value());  // Cache hit — return the value
        } finally {
            lock.writeLock().unlock();  // ALWAYS release lock, even if exception thrown
            // 'finally' block runs whether or not an exception occurs
        }
    }

    @Override
    public void set(String key, String value, int ttlSeconds) {
        lock.writeLock().lock();
        try {
            cache.put(key, new CacheEntry(
                value,
                System.currentTimeMillis() + (long) ttlSeconds * 1000
                // Convert ttlSeconds to milliseconds and add to current time
            ));
            // LinkedHashMap.removeEldestEntry is called automatically if over capacity
        } finally { lock.writeLock().unlock(); }
    }

    @Override
    public void delete(String key) {
        lock.writeLock().lock();
        try { cache.remove(key); }
        finally { lock.writeLock().unlock(); }
    }
}

// ── CodeGenerator: SINGLETON ──────────────────────────────────────────────────
class CodeGenerator {
    private static final String CHARS =
        "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";
    private static final int BASE     = 62;
    private static final int CODE_LEN = 7;

    // SINGLETON pattern in Java — Double-Checked Locking:
    private static volatile CodeGenerator INSTANCE;   // volatile: visibility guarantee
    private static final Object LOCK = new Object();  // Object to synchronize on

    private CodeGenerator() {}  // private constructor prevents "new CodeGenerator()"

    public static CodeGenerator getInstance() {
        if (INSTANCE == null) {          // First check (no lock, fast path)
            synchronized (LOCK) {        // Acquire lock (only one thread at a time)
                if (INSTANCE == null) {  // Second check (inside lock, safe)
                    INSTANCE = new CodeGenerator();
                }
            }
        }
        return INSTANCE;
    }

    public String encode(long num) {
        if (num == 0) return String.valueOf(CHARS.charAt(0));
        StringBuilder sb = new StringBuilder();
        while (num > 0) {
            sb.append(CHARS.charAt((int)(num % BASE)));  // charAt(index) gets char at position
            num /= BASE;
        }
        return sb.reverse().toString();  // StringBuilder.reverse() reverses in place
    }

    public String generate(String longUrl, int userId, int attempt) {
        try {
            String raw = longUrl + userId + attempt + System.nanoTime();
            // System.nanoTime() = nanoseconds since JVM start. Ensures uniqueness.

            MessageDigest md = MessageDigest.getInstance("MD5");
            // MessageDigest is Java's hashing library.
            // getInstance("MD5") creates an MD5 hasher.

            byte[] hash = md.digest(raw.getBytes());
            // raw.getBytes() = convert String to byte[] (UTF-8 bytes)
            // md.digest() = compute the MD5 hash → returns 16-byte array

            // Convert first 8 bytes of hash to a long (64-bit integer):
            long num = 0;
            for (int i = 0; i < 8; i++)
                num = (num << 8) | (hash[i] & 0xFF);
            // << 8 = shift left by 8 bits (multiply by 256)
            // hash[i] & 0xFF = treat byte as unsigned (Java bytes are signed)
            // | = bitwise OR: combine the shifted value with the new byte

            num = Math.abs(num) % (long) Math.pow(BASE, CODE_LEN);
            // Math.abs() = absolute value (remove sign)
            // Math.pow(62, 7) = 62^7 = max value for 7-char base62 code
            // % = modulo: reduce to [0, 62^7)

            String code = encode(num);
            // Pad to exactly CODE_LEN characters:
            return String.format("%" + CODE_LEN + "s", code).replace(' ', '0')
                         .substring(0, CODE_LEN);
            // String.format("%" + 7 + "s", code) = right-align in 7-char field (padded with spaces)
            // .replace(' ', '0') = replace space-padding with zero-padding
            // .substring(0, 7) = take first 7 chars

        } catch (Exception e) {
            throw new RuntimeException("Code generation failed", e);
            // Wrap checked exceptions in RuntimeException (unchecked) for cleaner code
        }
    }
}

// ── UrlShortener: FACADE ───────────────────────────────────────────────────────
class UrlShortener {
    private final IUrlRepository  repo;
    private final ICacheLayer     cache;
    private final CodeGenerator   gen = CodeGenerator.getInstance();
    private static final String   PREFIX = "short:";
    private static final int      MAX_ATTEMPTS = 5;

    public UrlShortener(IUrlRepository repo, ICacheLayer cache) {
        this.repo  = repo;    // Dependency Injection via constructor
        this.cache = cache;   // Caller decides which repo/cache to use
    }

    public String shorten(String longUrl, int userId,
                          String alias, Integer ttlSeconds) {
        // Integer (capital I) = nullable int. Can be null for "no TTL".
        // int (lowercase) = primitive, can't be null.

        if (!longUrl.startsWith("http://") && !longUrl.startsWith("https://"))
            throw new IllegalArgumentException("Invalid URL: " + longUrl);

        String code = resolveCode(longUrl, userId, alias);

        // Calculate expiry:
        Instant expiresAt = ttlSeconds != null
            ? Instant.now().plusSeconds(ttlSeconds)  // Ternary: condition ? yes : no
            : null;
        // If ttlSeconds is provided → set expiry. Otherwise → null (no expiry).

        repo.save(new UrlEntry(code, longUrl, userId, expiresAt));
        cache.set(PREFIX + code, longUrl, ttlSeconds != null ? ttlSeconds : 86400);
        return code;
    }

    private String resolveCode(String longUrl, int userId, String alias) {
        if (alias != null) {
            if (repo.exists(alias))
                throw new IllegalStateException("Alias '" + alias + "' already taken");
            return alias;
        }
        for (int i = 0; i < MAX_ATTEMPTS; i++) {
            String code = gen.generate(longUrl, userId, i);
            if (!repo.exists(code)) return code;  // Found a free code
        }
        throw new RuntimeException("Could not generate unique code");
    }

    public boolean delete(String code) {
        boolean deleted = repo.delete(code);
        if (deleted) cache.delete(PREFIX + code);  // Remove from cache too!
        return deleted;
    }

    public Map<String, Object> getStats(String code) {
        // Map.of() is Java 9+ shorthand for creating immutable maps
        return repo.find(code).map(e -> Map.of(
            "shortCode",  e.getShortCode(),
            "longUrl",    e.getLongUrl(),
            "clicks",     e.getClickCount(),
            "active",     e.getIsActive()
        )).orElse(null);
        // .map(e -> ...) transforms the Optional<UrlEntry> to Optional<Map>
        // .orElse(null) extracts the value or returns null if Optional was empty
    }
}

// ── RedirectService ────────────────────────────────────────────────────────────
class RedirectService {
    private final IUrlRepository repo;
    private final ICacheLayer    cache;
    private static final String  PREFIX = "short:";

    // record for the result (status + url together)
    record ResolveResult(int status, String url) {}
    // In Python this was: return tuple[int, Optional[str]]
    // In Java: using a record is more readable (named fields vs tuple)

    public RedirectService(IUrlRepository repo, ICacheLayer cache) {
        this.repo  = repo;
        this.cache = cache;
    }

    public ResolveResult resolve(String shortCode) {
        // 1. Cache hit
        Optional<String> cached = cache.get(PREFIX + shortCode);
        if (cached.isPresent()) return new ResolveResult(200, cached.get());
        // .isPresent() = true if Optional has a value
        // .get() = extract the value (safe after isPresent() check)

        // 2. DB lookup
        Optional<UrlEntry> entry = repo.find(shortCode);
        if (entry.isEmpty()) return new ResolveResult(404, null);
        // .isEmpty() = true if Optional has no value (Java 11+)

        if (!entry.get().isValid()) return new ResolveResult(410, null);

        // 3. Warm cache + count
        cache.set(PREFIX + shortCode, entry.get().getLongUrl(), 86400);
        entry.get().incrementClicks();
        return new ResolveResult(200, entry.get().getLongUrl());
    }
}
```

---

## STEP 5 — C++ Implementation (Every Line Explained)

```cpp
// url_shortener.cpp
// Compile: g++ -std=c++20 -pthread url_shortener.cpp -lssl -lcrypto -o url_shortener
// WHY c++20? We use structured bindings, concepts, and better std::optional support.
// WHY -pthread? We use std::mutex and std::thread — requires POSIX threads library.
// WHY -lssl -lcrypto? We use OpenSSL's MD5 function.

#include <iostream>     // std::cout, std::cerr
#include <string>       // std::string
#include <unordered_map>// hash map (like Python dict / Java HashMap)
#include <optional>     // std::optional (like Python Optional / Java Optional)
#include <memory>       // std::shared_ptr, std::unique_ptr, std::make_shared
#include <mutex>        // std::mutex, std::lock_guard
#include <chrono>       // std::chrono::steady_clock for timestamps
#include <list>         // std::list for LRU cache (doubly linked list)
#include <stdexcept>    // std::invalid_argument, std::runtime_error
#include <atomic>       // std::atomic<int> for lock-free counters
#include <openssl/md5.h>// MD5() function

// WHY #include FILES (not import)?
// C++ doesn't have a module system like Java/Python (until C++20 modules).
// #include literally copies the header file's content at that spot.
// The header declares WHAT functions exist; the library contains HOW they work.

using Clock = std::chrono::steady_clock;
// 'using' = type alias. Now we can write 'Clock' instead of 'std::chrono::steady_clock'
// steady_clock = a clock that never goes backwards (unlike system_clock which can be adjusted)

using TP = std::chrono::time_point<Clock>;
// TP = "time point" — a specific moment measured by our Clock


// ── UrlEntry ──────────────────────────────────────────────────────────────────
struct UrlEntry {
    // struct vs class in C++: the ONLY difference is default visibility
    // struct: members are PUBLIC by default
    // class: members are PRIVATE by default
    // We use struct here because UrlEntry is just a data bag (all public)

    std::string  shortCode;
    std::string  longUrl;
    int          ownerId{0};        // {0} = in-class initializer (default value)
    TP           createdAt;
    std::optional<TP> expiresAt;   // optional<TP>: either a time point or nothing
    bool         isActive{true};

    // std::atomic<int>: thread-safe integer, just like Java's AtomicInteger
    // clickCount++ on a regular int is NOT thread-safe (3 CPU instructions: read, add, write)
    // atomic<int>.fetch_add() is ONE atomic CPU instruction (no race condition)
    std::atomic<int> clickCount{0};

    // Constructor: initializes all fields
    UrlEntry(std::string code, std::string url, int owner,
             std::optional<TP> exp = std::nullopt)
        : shortCode(std::move(code))    // move() = transfer ownership (avoid copying string)
        , longUrl(std::move(url))       // std::move is an optimization: no string copy needed
        , ownerId(owner)
        , createdAt(Clock::now())       // Record creation time
        , expiresAt(exp) {}             // exp may be nullopt (no expiry)

    // WHY std::move?
    // Without move: "longUrl = url" copies the entire string character by character.
    // With move: longUrl "steals" the internal buffer from url (O(1) instead of O(n)).
    // url becomes empty after the move (you shouldn't use it after).

    bool isExpired() const {
        // 'const' at the end means this method doesn't modify the object
        if (!expiresAt) return false;  // !expiresAt = expiresAt is nullopt (empty)
        return Clock::now() > *expiresAt;
        // *expiresAt = dereference the optional to get the TP value
        // (like Python: expiresAt.value())
    }

    bool isValid() const { return isActive && !isExpired(); }

    void incrementClicks() {
        clickCount.fetch_add(1, std::memory_order_relaxed);
        // fetch_add(1) = atomically add 1 (like Java AtomicInteger.incrementAndGet())
        // memory_order_relaxed: don't enforce ordering with other memory operations
        // (safe for a simple counter that doesn't depend on other variables)
    }
};


// ── IUrlRepository (Pure Abstract Class = Interface in C++) ────────────────────
class IUrlRepository {
public:
    virtual ~IUrlRepository() = default;
    // virtual destructor: REQUIRED for base classes with virtual methods.
    // Without this, deleting a derived class via base pointer causes undefined behavior.
    // = default: generate the default destructor automatically.

    virtual void                              save(std::shared_ptr<UrlEntry> entry) = 0;
    virtual std::shared_ptr<UrlEntry>         find(const std::string& code) = 0;
    virtual bool                              del(const std::string& code)  = 0;
    virtual bool                              exists(const std::string& code) = 0;
    // = 0 means "pure virtual" — this class cannot be instantiated.
    // Any class inheriting IUrlRepository MUST implement these methods.
    // This is C++'s equivalent of Java's 'interface' or Python's ABC + @abstractmethod.
};

// WHY std::shared_ptr<UrlEntry>?
// In C++, memory management is manual (unlike Java/Python's garbage collection).
// shared_ptr = "shared ownership" smart pointer. It automatically deletes the object
// when no more shared_ptrs point to it.
// Without smart pointers: you'd need manual delete — very error-prone.
// const std::string& = reference, not copy. "&" = pass by reference (no string copy).


// ── InMemoryUrlRepository ─────────────────────────────────────────────────────
class InMemoryUrlRepository : public IUrlRepository {
    // ': public IUrlRepository' = inheritance (like Python's 'class Foo(Base)')
    // 'public' = the inherited methods remain public in this class

    std::unordered_map<std::string, std::shared_ptr<UrlEntry>> store_;
    // unordered_map = hash map (O(1) average lookup, like Python dict or Java HashMap)
    // Key: std::string (short code)
    // Value: shared_ptr<UrlEntry> (managed pointer to URL record)
    // Trailing underscore (_) = naming convention for private member variables

    mutable std::mutex mtx_;
    // std::mutex: mutual exclusion lock. Only one thread can hold it at a time.
    // 'mutable' = this field can be modified even in 'const' methods.
    // WHY mutable? Our find() is const (doesn't logically modify the object)
    // but it needs to acquire the mutex (which modifies the mutex's state).

public:
    void save(std::shared_ptr<UrlEntry> entry) override {
        // 'override' keyword: compile-time check that this actually overrides a virtual method
        // Without it, a typo in the method name silently creates a new unrelated method!

        std::lock_guard<std::mutex> lk(mtx_);
        // std::lock_guard = RAII lock wrapper.
        // Constructor acquires the lock. Destructor releases it.
        // WHY RAII? If an exception is thrown, the lock is AUTOMATICALLY released.
        // In Java, you'd need try-finally. In C++, RAII handles it automatically.

        store_[entry->shortCode] = entry;
        // operator-> on shared_ptr dereferences and accesses member: entry->shortCode
    }

    std::shared_ptr<UrlEntry> find(const std::string& code) override {
        std::lock_guard<std::mutex> lk(mtx_);  // Acquire lock (shared_ptr reads are not thread-safe)
        auto it = store_.find(code);            // 'auto' = compiler deduces type automatically
        return it != store_.end() ? it->second : nullptr;
        // store_.end() = iterator pointing past the last element (means "not found")
        // If found: it->second = the value (shared_ptr<UrlEntry>)
        // If not found: return nullptr (shared_ptr with nullptr is like Python's None)
    }

    bool del(const std::string& code) override {
        std::lock_guard<std::mutex> lk(mtx_);
        return store_.erase(code) > 0;
        // store_.erase(code) returns the NUMBER of elements erased (0 or 1 for unordered_map)
        // > 0 means "at least one element was erased" = true (deleted)
    }

    bool exists(const std::string& code) override {
        std::lock_guard<std::mutex> lk(mtx_);
        return store_.count(code) > 0;
        // count(key) returns 0 or 1 for unordered_map (keys are unique)
    }
};


// ── ICacheLayer (pure abstract) ───────────────────────────────────────────────
class ICacheLayer {
public:
    virtual ~ICacheLayer() = default;
    virtual std::optional<std::string> get(const std::string& key) = 0;
    // optional<string> = either a string value OR empty (nothing)
    // Like Python's Optional[str] or Java's Optional<String>

    virtual void set(const std::string& key, const std::string& val, int ttlSec) = 0;
    virtual void del(const std::string& key) = 0;
};


// ── LRUCache ──────────────────────────────────────────────────────────────────
class LRUCache : public ICacheLayer {
    struct Node {
        // A node in the doubly-linked list for LRU ordering
        std::string key, value;
        TP expiresAt;
    };

    int capacity_;
    std::list<Node> list_;
    // std::list = doubly linked list
    // WHY list and not vector? list supports O(1) insertion/deletion anywhere.
    // vector O(n) for middle insertions/deletions (must shift all elements).
    // LRU needs to frequently move items to front → list is perfect.

    std::unordered_map<std::string, std::list<Node>::iterator> map_;
    // Maps key → iterator (pointer into the linked list)
    // WHY store iterator? When we get(key), we need to move the node to the front.
    // With the iterator, we can do it in O(1). Without it, we'd need O(n) to find it.

    mutable std::mutex mtx_;  // mutable so const methods can lock it

public:
    explicit LRUCache(int cap) : capacity_(cap) {}
    // 'explicit' = prevents implicit conversion (no accidental LRUCache lru = 500; )
    // : capacity_(cap) = member initializer list (runs before constructor body)

    std::optional<std::string> get(const std::string& key) override {
        std::lock_guard<std::mutex> lk(mtx_);
        auto it = map_.find(key);
        if (it == map_.end()) return std::nullopt;  // Cache miss: return empty optional

        if (Clock::now() > it->second->expiresAt) {
            // Expired: remove from both list and map
            list_.erase(it->second);   // O(1) with iterator!
            map_.erase(it);
            return std::nullopt;
        }

        list_.splice(list_.begin(), list_, it->second);
        // splice(): moves one element from a list to another position IN O(1)
        // list_.begin() = the front of the list (most recently used position)
        // it->second = the iterator to the node we want to move
        // Effect: moves this node to the FRONT (marks as most recently used)

        return it->second->value;  // Return the cached value
    }

    void set(const std::string& key, const std::string& val, int ttlSec) override {
        std::lock_guard<std::mutex> lk(mtx_);
        auto expires = Clock::now() + std::chrono::seconds(ttlSec);
        // std::chrono::seconds(ttlSec) = a duration of ttlSec seconds
        // Adding to Clock::now() gives the expiry time point

        auto it = map_.find(key);
        if (it != map_.end()) {
            // Key already exists: update value and move to front
            it->second->value     = val;
            it->second->expiresAt = expires;
            list_.splice(list_.begin(), list_, it->second);
            return;
        }

        // New entry: add to front of list
        list_.push_front({key, val, expires});  // {key, val, expires} = Node initialization
        map_[key] = list_.begin();              // Store iterator to the new front node

        if ((int)map_.size() > capacity_) {
            // Over capacity: evict least recently used (last element in list)
            map_.erase(list_.back().key);  // Remove from map
            list_.pop_back();              // Remove from list
        }
    }

    void del(const std::string& key) override {
        std::lock_guard<std::mutex> lk(mtx_);
        auto it = map_.find(key);
        if (it != map_.end()) {
            list_.erase(it->second);   // Remove from list
            map_.erase(it);            // Remove from map
        }
    }
};


// ── CodeGenerator (Meyers Singleton) ──────────────────────────────────────────
class CodeGenerator {
    static constexpr const char CHARS[] =
        "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";
    // constexpr = evaluated at compile time (zero runtime cost)
    // const char[] = an array of chars (a C-style string)

    static constexpr int BASE     = 62;
    static constexpr int CODE_LEN = 7;

    CodeGenerator() = default;
    // private constructor: prevents external construction via 'new CodeGenerator()'

public:
    static CodeGenerator& getInstance() {
        static CodeGenerator instance;
        // MEYERS SINGLETON: local static variable.
        // In C++11+, the initialization of a local static is GUARANTEED to be thread-safe.
        // "static" here means: initialized only ONCE, the first time this line runs.
        // Subsequent calls just return the existing instance.
        // This is SIMPLER and SAFER than Java's double-checked locking.
        return instance;
    }

    // DELETE copy constructor and assignment operator:
    // Prevents: CodeGenerator cg2 = cg1; (would create a second instance)
    CodeGenerator(const CodeGenerator&)            = delete;
    CodeGenerator& operator=(const CodeGenerator&) = delete;

    std::string encode(long long num) {
        if (num == 0) return std::string(1, CHARS[0]);  // string of 1 character
        std::string result;
        while (num > 0) {
            result += CHARS[num % BASE];  // Append the "digit"
            num /= BASE;
        }
        std::reverse(result.begin(), result.end());  // Reverse the built string
        // std::reverse works on iterators: begin() = first char, end() = past last char
        return result;
    }

    std::string generate(const std::string& url, int userId, int attempt) {
        std::string raw = url + std::to_string(userId)
                        + std::to_string(attempt)
                        + std::to_string(Clock::now().time_since_epoch().count());
        // std::to_string() = convert int/long to string (like Python str())
        // .time_since_epoch().count() = nanoseconds since epoch (unique per call)

        unsigned char digest[MD5_DIGEST_LENGTH];
        // MD5_DIGEST_LENGTH = 16 bytes
        // unsigned char = byte (values 0-255, not signed -128 to 127)

        MD5(reinterpret_cast<const unsigned char*>(raw.c_str()), raw.size(), digest);
        // MD5() from OpenSSL: compute MD5 hash of raw bytes into digest array
        // raw.c_str() = get C-style char* from std::string
        // reinterpret_cast = force-convert char* to unsigned char* (type punning)
        // raw.size() = number of bytes to hash

        long long num = 0;
        for (int i = 0; i < 8; i++)
            num = (num << 8) | digest[i];
        // Same as Python: build a 64-bit int from 8 bytes of the hash
        // << 8 = left shift (multiply by 256)
        // | = bitwise OR (combine)

        num = std::abs(num) % (long long)std::pow(BASE, CODE_LEN);
        // std::abs = absolute value
        // std::pow(62, 7) = 62^7

        std::string code = encode(num);
        while ((int)code.size() < CODE_LEN) code = "0" + code;  // Left-pad with zeros
        return code.substr(0, CODE_LEN);  // substr(start, length) = first 7 chars
    }
};


// ── UrlShortener (Facade) ─────────────────────────────────────────────────────
class UrlShortener {
    std::shared_ptr<IUrlRepository> repo_;
    std::shared_ptr<ICacheLayer>    cache_;
    CodeGenerator&                  gen_;  // Reference: CodeGenerator is a Singleton
    static constexpr const char*    PREFIX = "short:";
    static constexpr int            MAX_ATTEMPTS = 5;

public:
    UrlShortener(std::shared_ptr<IUrlRepository> repo,
                 std::shared_ptr<ICacheLayer>    cache)
        : repo_(repo), cache_(cache)
        , gen_(CodeGenerator::getInstance()) {}
    // Get the Singleton reference on construction

    std::string shorten(const std::string& longUrl, int userId = 0,
                        std::string alias = "",
                        std::optional<int> ttlSec = std::nullopt) {
        // optional<int>: either an int TTL or nothing (no expiry)

        if (longUrl.rfind("http", 0) != 0)  // rfind("http", 0) = starts with "http"?
            throw std::invalid_argument("Invalid URL: " + longUrl);

        std::string code = resolveCode(longUrl, userId, alias);

        std::optional<TP> expires;
        if (ttlSec) {
            // *ttlSec: dereference optional to get the int value
            expires = Clock::now() + std::chrono::seconds(*ttlSec);
        }

        auto entry = std::make_shared<UrlEntry>(code, longUrl, userId, expires);
        // make_shared: creates a UrlEntry on the heap and wraps it in a shared_ptr
        // More efficient than: shared_ptr<UrlEntry>(new UrlEntry(...))

        repo_->save(entry);
        cache_->set(PREFIX + code, longUrl, ttlSec.value_or(86400));
        // value_or(default): if optional has a value, return it. Otherwise return default.
        // Same as Python's: ttl_secs or 86400

        return code;
    }

    bool del(const std::string& code) {
        bool deleted = repo_->del(code);
        if (deleted) cache_->del(PREFIX + code);
        return deleted;
    }

private:
    std::string resolveCode(const std::string& url, int userId, const std::string& alias) {
        if (!alias.empty()) {    // empty() = string has zero characters
            if (repo_->exists(alias))
                throw std::runtime_error("Alias '" + alias + "' already taken");
            return alias;
        }
        for (int i = 0; i < MAX_ATTEMPTS; i++) {
            auto code = gen_.generate(url, userId, i);
            if (!repo_->exists(code)) return code;
        }
        throw std::runtime_error("Could not generate unique code");
    }
};


// ── RedirectService ────────────────────────────────────────────────────────────
class RedirectService {
    std::shared_ptr<IUrlRepository> repo_;
    std::shared_ptr<ICacheLayer>    cache_;
    static constexpr const char*    PREFIX = "short:";

public:
    struct Result {
        int status;
        std::string url;
    };
    // struct Result: a simple way to return two values together
    // In Python: return (int, Optional[str])
    // In Java: record ResolveResult(int status, String url)
    // In C++: struct Result { int status; std::string url; }

    RedirectService(std::shared_ptr<IUrlRepository> repo,
                    std::shared_ptr<ICacheLayer>    cache)
        : repo_(repo), cache_(cache) {}

    Result resolve(const std::string& code) {
        // 1. Cache hit
        auto cached = cache_->get(PREFIX + code);
        if (cached) return {200, *cached};
        // 'cached' as bool = true if optional has a value
        // *cached = dereference to get the string value
        // {200, *cached} = initialize Result struct

        // 2. DB lookup
        auto entry = repo_->find(code);
        if (!entry) return {404, ""};
        // !entry: shared_ptr converts to bool (true if not null)
        // If find() returned nullptr → not found → 404

        if (!entry->isValid()) return {410, ""};

        // 3. Warm cache + count
        cache_->set(PREFIX + code, entry->longUrl, 86400);
        entry->incrementClicks();
        return {200, entry->longUrl};
    }
};


// ── Demo ──────────────────────────────────────────────────────────────────────
int main() {
    // In C++, main() MUST return int. 0 = success. Non-zero = error.

    auto repo  = std::make_shared<InMemoryUrlRepository>();
    auto cache = std::make_shared<LRUCache>(500);
    // 'auto' = compiler deduces type: std::shared_ptr<InMemoryUrlRepository>

    UrlShortener   svc(repo, cache);
    RedirectService redir(repo, cache);
    // Both share the SAME repo and cache objects.
    // shared_ptr reference counting: both svc and redir hold a shared_ptr to repo.
    // repo is deleted only when BOTH svc and redir are destroyed.

    auto code1 = svc.shorten("https://google.com/search?q=lld", 1);
    auto code2 = svc.shorten("https://github.com/sachin", 1, "gh-sachin");

    std::cout << "code1 = " << code1 << "\n";
    std::cout << "code2 = " << code2 << "\n";
    // std::cout = standard output (like Python's print)
    // << = stream insertion operator (chain multiple values)
    // "\n" = newline (or use std::endl but "\n" is faster)

    auto r = redir.resolve(code1);
    std::cout << "Resolve: " << r.status << " -> " << r.url << "\n";

    svc.del(code2);
    auto r2 = redir.resolve(code2);
    std::cout << "After delete: " << r2.status << "\n";  // 404

    return 0;  // 0 = program succeeded
}
```

---

## STEP 6 — Trade-offs (With Explanations)

```
TRADE-OFF 1: Singleton CodeGenerator
  WHAT IT IS: Only ONE CodeGenerator object ever exists across the entire program.
  PRO:  No state to sync. No re-initialization cost. Thread-safe (Meyers Singleton in C++).
  CON:  Hard to mock in unit tests. Testing UrlShortener means you always use the real generator.
  FIX:  Make CodeGenerator an interface. Inject a MockCodeGenerator in tests.
        This is a common interview follow-up question.

TRADE-OFF 2: LRU vs TTL — why we use BOTH
  LRU alone: viral URL never gets evicted (good), but stale data lives forever (bad).
  TTL alone: hot URL evicted every 24h even if it's been accessed a billion times (bad).
  BOTH: LRU evicts cold items when capacity full. TTL ensures no stale data survives
        past its time. The combination is what Redis uses by default.

TRADE-OFF 3: Synchronous click counting vs Kafka
  Current (synchronous): entry.increment_clicks() inside resolve() holds up the response.
  At 578K redirects/sec, each increment is a memory write = fine for in-memory.
  But if persisting to DB: 578K DB writes/sec would crash PostgreSQL.
  Production fix: publish to Kafka (fire and forget), consumer batch-updates click_count
  every 60 seconds. Reduces 578K writes/sec to ~1 batch write/minute.

TRADE-OFF 4: Java ConcurrentHashMap vs synchronized(this)
  synchronized(this): entire map is locked. One thread at a time for reads AND writes.
  ConcurrentHashMap: 16 segment locks (Java 8+). Multiple reads simultaneously.
     Writes lock only the affected segment. Much higher throughput.
  For URL repository: reads >> writes → ConcurrentHashMap wins clearly.

TRADE-OFF 5: C++ shared_ptr vs unique_ptr
  unique_ptr: one owner only. Faster (no reference counting). Can't share.
  shared_ptr: multiple owners. Slight overhead (atomic reference count).
  Here: repo and cache are shared between UrlShortener AND RedirectService.
  Two owners → must use shared_ptr. unique_ptr would require one to "give up" ownership.
```

---

## STEP 7 — Interview Follow-Ups (Every Answer Explained)

```
Q: "How would you make CodeGenerator thread-safe in C++?"
```
**ANSWER:**
- C++ Meyers Singleton (`static CodeGenerator instance;` inside getInstance()) is guaranteed thread-safe in C++11+. The standard says: if multiple threads reach the initialization of a local static simultaneously, only one proceeds; others wait.
- The `generate()` method itself is stateless (takes inputs, computes output, no shared state modified). Stateless functions are inherently thread-safe — no lock needed.

```
Q: "How would you swap InMemory for PostgreSQL without changing UrlShortener?"
```
**ANSWER:**
- Write a new class `PostgresUrlRepository` that `implements IUrlRepository` (Java) / inherits `IUrlRepository` (C++) / inherits `ABC` (Python).
- In its `save()`, run `INSERT INTO urls ...`. In `find()`, run `SELECT * FROM urls WHERE short_code = ?`. Etc.
- Pass `new PostgresUrlRepository(connectionString)` to `UrlShortener`'s constructor instead of `InMemoryUrlRepository`.
- UrlShortener code is **zero changes**. This is Dependency Inversion Principle in action.

```
Q: "What happens if the cache server goes down?"
```
**ANSWER:**
- All requests become cache misses → fall through to DB lookup (2-5ms instead of <1ms).
- System **degrades gracefully** — still works, just slower.
- At scale (578K reads/sec × 80% cache miss rate = 462K DB reads/sec), DB cannot handle this without read replicas.
- **Add a circuit breaker:** if cache is down, route all reads to a secondary cache or hot-standby Redis Replica. Prevents thundering herd on DB.

```
Q: "How would you handle 10 billion entries (can't fit in one machine)?"
```
**ANSWER:**
- `IUrlRepository` is your **sharding boundary**.
- Write `ShardedUrlRepository` that contains N `InMemoryUrlRepository` instances.
- `ShardedUrlRepository.find(code)`:
  ```
  shard_index = hash(code) % N
  return shards[shard_index].find(code)
  ```
- UrlShortener passes `ShardedUrlRepository` to its constructor. **Zero changes to UrlShortener.** This is the power of the Strategy/Repository pattern.

```
Q: "Why return HTTP 410 vs 404?"
```
**ANSWER:**
- **404 Not Found:** This URL *never* existed. The client shouldn't cache this.
- **410 Gone:** This URL *did* exist but was permanently removed. The client/CDN CAN cache this (no point trying again). Bots and crawlers stop indexing the link.
- For our URL shortener: a user-deleted URL returns 410. A code that was never created returns 404. Different semantics, different behavior for callers.


---

## STEP 8 — Extended Deep-Dives: Production Patterns

```
DESIGN PATTERN DEEP-DIVE: DECORATOR PATTERN FOR ANALYTICS

  Instead of modifying RedirectService, WRAP it with analytics tracking.
  Open/Closed Principle: open for extension (wrap), closed for modification.

  class AnalyticsRedirectService:
      """
      DECORATOR: Wraps any IRedirectService with click analytics.
      The wrapped service does not know it is being decorated.
      """
      def __init__(self, inner: RedirectService, kafka_producer):
          self._inner = inner
          self._kafka = kafka_producer
      
      def resolve(self, short_code: str, request_context: dict) -> tuple:
          # 1. Call inner service (unchanged behavior)
          status, url = self._inner.resolve(short_code)
          
          # 2. Augment with analytics (decoration)
          if status == 200:
              self._kafka.send("click-events", {
                  "short_code": short_code,
                  "timestamp": time.time(),
                  "ip_hash": hashlib.md5(request_context["ip"].encode()).hexdigest(),
                  "user_agent": request_context.get("user_agent", ""),
                  "referer": request_context.get("referer", "direct"),
                  "country": request_context.get("country", "XX"),
              })
          
          return status, url
  
  # Usage: wrap at composition root (main.py)
  base_service = RedirectService(repo, cache)
  analytics_service = AnalyticsRedirectService(base_service, kafka_producer)
  # Now analytics_service IS-A redirect service with bonus tracking.
  
  WHY DECORATOR OVER INHERITANCE?
    Inheritance: AnalyticsRedirectService extends RedirectService.
    Problem: extends = tightly coupled. If RedirectService changes, child breaks.
    Problem: can't mix-and-match (e.g., Analytics + RateLimiting + Logging decorators).
    
    Decorator: compose behavior at runtime.
    ratelimited_analytics_logging = 
        LoggingDecorator(
            RateLimitDecorator(
                AnalyticsDecorator(RedirectService(repo, cache))
            )
        )
    Each decorator adds one responsibility. Each class is small and focused (SRP).

TEMPLATE METHOD PATTERN FOR CODE GENERATION:

  Different strategies for generating codes: MD5-hash-based vs counter-based vs random.
  Template method: defines the algorithm structure, subclasses fill in steps.
  
  class BaseCodeGenerator(ABC):
      """Template method: generate() calls abstract steps."""
      
      def generate(self, long_url: str, user_id: int = 0) -> str:
          raw_input = self._prepare_input(long_url, user_id)  # HOOK 1: subclass defines
          number = self._compute_number(raw_input)              # HOOK 2: subclass defines
          code = self._encode(number)                          # SHARED: same encoding
          return self._postprocess(code)                        # HOOK 3: subclass can override
      
      @abstractmethod
      def _prepare_input(self, long_url: str, user_id: int) -> str: ...
      
      @abstractmethod
      def _compute_number(self, raw: str) -> int: ...
      
      def _encode(self, num: int) -> str:
          """SHARED — base62 encoding. Subclasses don't override this."""
          CHARS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
          result = []
          while num > 0:
              result.append(CHARS[num % 62])
              num //= 62
          return ''.join(reversed(result)).zfill(7)[:7]
      
      def _postprocess(self, code: str) -> str:
          return code  # default: no postprocessing. Subclasses override if needed.
  
  
  class HashBasedGenerator(BaseCodeGenerator):
      def _prepare_input(self, url, uid): return f"{url}{uid}{time.time_ns()}"
      def _compute_number(self, raw): return int(hashlib.md5(raw.encode()).hexdigest(), 16)
  
  class SnowflakeGenerator(BaseCodeGenerator):
      """Counter-based: no collision possible."""
      def __init__(self, worker_id: int):
          self._worker_id = worker_id & 0x3FF  # 10-bit worker ID
          self._sequence = 0
          self._last_ms = 0
          self._lock = threading.Lock()
      
      def _prepare_input(self, url, uid): return ""  # not needed for counter-based
      
      def _compute_number(self, raw) -> int:
          with self._lock:
              ms = int(time.time() * 1000)
              if ms == self._last_ms:
                  self._sequence = (self._sequence + 1) & 0xFFF  # 12 bits
                  if self._sequence == 0:
                      while ms <= self._last_ms:  # wait for next millisecond
                          ms = int(time.time() * 1000)
              else:
                  self._sequence = 0
              self._last_ms = ms
              # Snowflake: 41 bits timestamp | 10 bits worker | 12 bits sequence
              return ((ms - 1609459200000) << 22) | (self._worker_id << 12) | self._sequence
  
  BENEFIT: switching from hash-based to snowflake = swap one object in DI container.
  UrlShortener: zero code changes. Just inject different generator.
  This is why Template Method + DI is so powerful in interviews.

FULL PRODUCTION FLOW: REQUEST → RESPONSE:

  # This is what the HTTP handler looks like (e.g., FastAPI or Flask)
  
  @app.get("/{short_code}")
  async def redirect(short_code: str, request: Request):
      # 1. Input sanitization: reject non-alphanumeric codes (prevent injection)
      if not re.match(r'^[a-zA-Z0-9_-]{1,20}$', short_code):
          raise HTTPException(400, "Invalid short code format")
      
      # 2. Rate limiting (check before any processing)
      ip = request.client.host
      if not rate_limiter.allow(ip, limit=100, window_secs=60):
          raise HTTPException(429, "Rate limit exceeded", headers={"Retry-After": "60"})
      
      # 3. Resolve (with analytics decoration)
      context = {
          "ip": ip,
          "user_agent": request.headers.get("user-agent", ""),
          "referer": request.headers.get("referer", "direct"),
          "country": geoip.lookup(ip),
      }
      status, url = analytics_redirect_service.resolve(short_code, context)
      
      # 4. Return appropriate HTTP response
      if status == 200:
          return RedirectResponse(url=url, status_code=302)
          # 302 (temporary redirect) vs 301 (permanent):
          # 302: browser asks server every time (we WANT this for click tracking + deletion support)
          # 301: browser caches permanently, never asks again (breaks analytics + deletion)
      elif status == 404:
          raise HTTPException(404, f"Short code '{short_code}' not found")
      elif status == 410:
          raise HTTPException(410, f"Short code '{short_code}' has expired or been deleted")
  
  # Performance profile of this endpoint:
  # Cache hit: ~2ms total (rate limit check 0.5ms + Redis 1ms + response 0.5ms)
  # Cache miss: ~10ms total (same + DB query 7ms + cache write 0.5ms)
  # Concurrent: asyncio allows thousands of concurrent requests on one event loop
  # Zero thread blocking: all I/O is async (aioredis, asyncpg, etc.)
```

---

## STEP 9 — Design Principles Checklist

```
SOLID PRINCIPLES — HOW THIS DESIGN SATISFIES EACH:

S — Single Responsibility Principle (SRP):
  CodeGenerator: ONLY generates codes. Nothing else.
  UrlShortener: ONLY orchestrates (creates URLs). Doesn't know HOW code is generated.
  RedirectService: ONLY resolves codes. Doesn't know how URLs are stored.
  LRUCache: ONLY caches. Doesn't know it's being used for URL resolution.
  InMemoryUrlRepository: ONLY stores URLs in memory. Doesn't know about caching or codes.
  EACH CLASS: one reason to change. ✓

O — Open/Closed Principle (OCP):
  New storage backend: add PostgresUrlRepository. Don't modify existing classes. ✓
  New code generation: add SnowflakeGenerator. Don't modify UrlShortener. ✓
  New caching layer: add RedisCache. Don't modify RedirectService. ✓
  New analytics: use Decorator pattern. Don't modify RedirectService. ✓

L — Liskov Substitution Principle (LSP):
  InMemoryUrlRepository can be substituted anywhere IUrlRepository is expected. ✓
  LRUCache can be substituted anywhere ICacheLayer is expected. ✓
  All subclasses honor the contract (find() returns Optional[UrlEntry], etc.). ✓

I — Interface Segregation Principle (ISP):
  IUrlRepository: only URL-specific methods (save, find, delete, exists).
  ICacheLayer: only cache-specific methods (get, set, delete).
  No "fat interface" combining unrelated methods. ✓
  If we needed stats tracking: add IStatsRepository separately.

D — Dependency Inversion Principle (DIP):
  UrlShortener depends on IUrlRepository (abstract), not InMemoryUrlRepository (concrete). ✓
  UrlShortener depends on ICacheLayer (abstract), not LRUCache (concrete). ✓
  High-level module (UrlShortener) doesn't depend on low-level details. ✓
  Direction of dependency: both point to the INTERFACE. ✓

GANG OF FOUR PATTERNS USED — SUMMARY:
  Singleton    → CodeGenerator (thread-safe, double-checked locking)
  Strategy     → IUrlRepository (swap storage backends at runtime)
  Proxy        → CacheLayer (transparent caching in front of real storage)
  Facade       → UrlShortener (simple API hiding complex subsystem)
  Decorator    → AnalyticsRedirectService (add behavior without modification)
  Template Method → BaseCodeGenerator (algorithm skeleton, subclass fills steps)
  Builder      → (can be added for UrlEntry with many optional fields)
  Observer     → (can be added: event bus for URL-created, URL-deleted events)

INTERVIEW SCORING RUBRIC:
  What interviewers score you on for LLD:
  ✓ Class diagram before code (shows planning)
  ✓ Interfaces for every dependency (DIP)
  ✓ Thread safety addressed (locks, AtomicInteger, ConcurrentHashMap)
  ✓ At least 2 design patterns named + explained
  ✓ Error handling (collision, duplicate alias, cache miss)
  ✓ Code runnable/testable (not pseudocode)
  ✓ Follow-ups: how to scale, extend, swap components

  What drops scores:
  ✗ Hardcoding storage (new InMemoryRepo() inside business logic)
  ✗ No interfaces → can't test, can't swap
  ✗ No thread safety discussion
  ✗ Static methods everywhere (not OOP)
  ✗ One giant class with all logic
```

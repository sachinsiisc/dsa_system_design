# 00: LLD Master Index & Interview Reference
## Quick-access guide to all case studies | Last updated: Sep 2026

---

## 📚 All Case Studies at a Glance

| # | System | Core Patterns | Key Interview Topics |
|---|--------|---------------|----------------------|
| [CS01](CS01_URL_Shortener.md) | URL Shortener | Singleton, Facade, Strategy | Base62, collision handling, custom slugs |
| [CS04](CS04_Uber.md) | Uber | Strategy, Composite, Factory, Facade | Geohash, fare calc, driver matching |
| [CS05](CS05_Netflix.md) | Netflix | Template Method, Composite, Strategy | Adaptive streaming, content tree, recommendations |
| [CS06](CS06_YouTube.md) | YouTube | Template Method, Observer, Strategy | Transcoding pipeline, ABR streaming, fanout |
| [CS07](CS07_Google_Search.md) | Google Search | Builder, Facade | Inverted Index, TF-IDF, PageRank, phrase search |
| [CS08](CS08_Twitter.md) | Twitter | Observer, Strategy, Composite | Fanout, timeline, trending, follow graph |
| [CS09](CS09_Payment_Gateway.md) | Payment Gateway | Strategy, Template Method, Observer | Idempotency, 2-step auth+capture, fraud |
| [CS10](CS10_MakeMyTrip.md) | MakeMyTrip | Strategy, Template Method, Factory | Seat hold, inventory, cancellation policies |
| [CS11](CS11_AI_Systems.md) | AI Systems | Strategy, Adapter, Template | RAG, embeddings, token counter, rate limiter |

---

## 🔑 Pattern Cheat Sheet

```
STRATEGY (most important pattern for interviews):
  When: behavior varies at runtime. Multiple algorithms for same operation.
  Examples:
  - Fare calculation: SurgePricingStrategy, FixedPricingStrategy (Uber)
  - Payment method: CardProcessor, UPIProcessor, WalletProcessor (Payment)
  - Recommendation: CollaborativeFiltering, ContentBased, Hybrid (Netflix/YouTube)
  - Cancellation: FlexiblePolicy, ModeratePolicy, StrictPolicy (MakeMyTrip)
  - ABR: BandwidthAwareStrategy, QualityFirstStrategy (YouTube/Netflix)
  Interview signal: "Different behaviors → Strategy Pattern"

OBSERVER (event-driven systems):
  When: one event → multiple listeners need to react.
  Examples:
  - Tweet posted → all followers' timelines updated (Twitter Fanout)
  - Video published → subscribers notified (YouTube Channel)
  - Payment completed → webhook sent to merchant (Payment Gateway)
  - PriceAlert triggered → user notified (MakeMyTrip)
  Interview signal: "Event happens → multiple places need to know → Observer"

TEMPLATE METHOD (algorithms with variable steps):
  When: algorithm skeleton is fixed, but some steps vary by subtype.
  Examples:
  - TranscodeJob.process(): validate → extract metadata → transcode → publish (YouTube)
  - PaymentProcessor.process(): validate → authorize → capture (Payment Gateway)
  - StreamingSession.start(): authenticate → select quality → connect CDN (Netflix)
  Interview signal: "Same flow but different details for subtypes → Template Method"

FACADE (simplify complex subsystems):
  When: many complex components → expose simple interface.
  Examples:
  - UberService (rides, geohash, fare, driver) → simple book_ride() API
  - PaymentGatewayService → simple process_payment() API
  - YouTubeService, TwitterService, MakeMyTripService, SearchEngine
  Interview signal: "Many subsystems, need simple entry point → Facade"

STATE (objects with lifecycle):
  When: object transitions between states, different behavior in each state.
  Examples:
  - Payment: PENDING → PROCESSING → COMPLETED/FAILED/REFUNDED
  - Video: UPLOADING → PROCESSING → PUBLISHED/PRIVATE/REMOVED
  - Tweet: ACTIVE → DELETED (soft)
  - FlightBooking: HELD → CONFIRMED → COMPLETED/CANCELLED
  Interview signal: "Object has status enum with valid transitions → State Pattern"

SINGLETON (global unique instance):
  When: exactly one instance needed globally (connection pool, config, cache).
  Examples:
  - CodeGenerator (URL shortener counter)
  - Database connection pool
  Interview signal: "One global instance → Singleton (with double-checked locking in Java)"

COMPOSITE (tree structures):
  When: individual items and groups of items treated uniformly.
  Examples:
  - YouTube: Comment + replies (Comment tree)
  - Netflix: ContentItem (Movie + Series + Episode hierarchy)
  - Twitter: Tweet + thread of replies
  Interview signal: "Tree structure, parent-child relationship → Composite"

FACTORY (object creation):
  When: creation logic is complex or depends on a type parameter.
  Examples:
  - PaymentMethodFactory: creates Card/UPI/Wallet based on type
  - BookingFactory: creates FlightBooking or HotelBooking
  - LLMAdapterFactory: creates OpenAI/Anthropic/Google adapter
  Interview signal: "Complex creation, multiple types → Factory"
```

---

## 🧵 Concurrency Cheat Sheet

```
PYTHON:
  threading.RLock()       → Reentrant lock (same thread can re-acquire)
  threading.Lock()        → Simple lock (non-reentrant)
  threading.Condition()   → Lock + wait/notify (producer-consumer)
  collections.deque()     → Thread-safe for append/popleft
  with lock:              → RAII pattern (auto-release on exception)

JAVA:
  ConcurrentHashMap       → Thread-safe HashMap (16 segments)
  CopyOnWriteArrayList    → Thread-safe list (snapshot reads)
  AtomicInteger           → Lock-free atomic increment
  AtomicReference         → Lock-free atomic reference update (CAS loops)
  ReadWriteLock           → Multiple concurrent readers OR one writer
  synchronized method     → Lock on 'this' object
  volatile field          → Visibility guarantee (no lock)

C++:
  std::mutex              → Basic mutual exclusion
  std::shared_mutex       → Multiple readers OR one writer
  std::unique_lock        → RAII exclusive lock
  std::shared_lock        → RAII shared (read) lock
  std::scoped_lock        → RAII lock for MULTIPLE mutexes (deadlock-safe)
  std::atomic<T>          → Atomic operations (fetch_add, compare_exchange_strong)
  std::memory_order       → Control CPU/compiler reordering
```

---

## 💰 Money in Code — NEVER USE FLOAT

```python
# Python — Decimal (no floating point errors)
from decimal import Decimal, ROUND_HALF_UP
amount = Decimal("999.50")   # Always use string constructor!
amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
```

```java
// Java — BigDecimal
BigDecimal amount = new BigDecimal("999.50");   // String constructor!
amount = amount.setScale(2, RoundingMode.HALF_UP);
// NEVER: new BigDecimal(999.50) — binary float imprecision!
```

```cpp
// C++ — Integer paisa/cents (most reliable)
using Paisa = long long;   // ₹999.50 = 99950 paisa
// Integer arithmetic has NO floating point errors.
// Display: amount_paisa / 100 + "." + (amount_paisa % 100 < 10 ? "0" : "") + to_string(amount_paisa % 100)
```

---

## 🔒 Security Patterns

```
HASHING API KEYS:
  Never store plain-text secrets.
  Store: SHA-256 hash of the key.
  Verify: hash provided key → compare hashes (constant-time).
  
  Python: hashlib.sha256(key.encode()).hexdigest()
  Java:   MessageDigest.getInstance("SHA-256").digest(key.getBytes())
  C++:    (use OpenSSL or Botan library)

TIMING ATTACK PREVENTION:
  Problem: naive '==' short-circuits on first mismatch → reveals key length.
  Solution: constant-time comparison (always same duration).
  
  Python: hmac.compare_digest(hash_a, hash_b)
  Java:   MessageDigest.isEqual(bytes_a, bytes_b)
  C++:    std::equal with volatile keyword or crypto library

TOKEN BUCKET RATE LIMITER:
  Fill rate: N requests/minute → N/60 tokens/second
  Bucket capacity: N tokens (burst allowed up to capacity)
  Request: consume 1 token. Deny if bucket empty.
  Key: monotonic clock (time.monotonic in Python, System.nanoTime() in Java)
```

---

## 🎯 Top Interview Questions & Answers

```
Q: "Design a system that never double-charges a payment."
A: Idempotency keys.
   Merchant includes unique key per transaction.
   Gateway stores key → payment_id mapping.
   Duplicate key → return same response. No new charge.
   DB: UNIQUE constraint on idempotency_key column as final safety net.

Q: "How do you handle 100M celebrity followers on Twitter?"
A: Hybrid fanout.
   Normal users (< 1M followers): PUSH (write to all timelines immediately).
   Celebrities: PULL (don't fan out; followers fetch celebrity tweets lazily at read time).
   Timeline read: pre-built push timeline + merge celebrity tweets from DB.

Q: "How do you make video search on YouTube fast?"
A: Inverted index (same as Google).
   At index time: tokenize titles, descriptions, tags → build inverted index.
   At query time: O(1) lookup in index → intersect → rank by engagement.
   Storage: Elasticsearch in production (distributed inverted index).

Q: "What's the difference between RAG and fine-tuning?"
A: RAG: inject relevant documents at query time. Knowledge is external, updateable.
   Fine-tuning: bake knowledge into model weights. Expensive. Stale.
   Default recommendation: use RAG first (cheaper, updatable, citations).
   Fine-tune only if domain-specific style/behavior is needed.

Q: "How do you prevent the inverted index from growing infinitely?"
A: Stop words removal: "the", "is", "a" → excluded.
   Index pruning: only top-K postings per term (skip very low-ranked docs).
   Tiered index: fresh index (last 30 days) + main index (older).
   Compression: VByte encoding, delta encoding of doc IDs.

Q: "How does adaptive streaming (ABR) work?"
A: Video encoded into multiple bitrates: 360p/720p/1080p/4K.
   Player downloads small segments (~6s each) at the best fitting quality.
   After each segment: check bandwidth → upgrade or downgrade resolution.
   No buffering because switch happens at segment boundaries.

Q: "How do you handle a seat being taken between search and booking?"
A: Seat hold pattern.
   Search: show available seats.
   User selects seat: HOLD for 10 minutes (block, not book).
   User provides details + pays: CONFIRM (hold → permanent booking).
   If payment fails/timeout: RELEASE (hold → available again).
   Concurrency: hold() uses a lock (Python) or SELECT FOR UPDATE (SQL).
```

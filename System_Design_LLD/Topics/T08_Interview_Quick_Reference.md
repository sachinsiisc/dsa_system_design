# LLD Topic 08: Interview Patterns & Quick Reference
## Approach Framework | Common Mistakes | Java vs C++ Quick Diff

---

## THE 6-STEP LLD INTERVIEW APPROACH

```
TIME: 45-60 minutes. Follow this structure strictly.

STEP 1 (5 min): CLARIFY REQUIREMENTS
  Ask: "What's the scope? What are the key features?"
  Don't: Start coding immediately. Interviewers penalize this.
  Do: Write requirements on the whiteboard. Get agreement.
  
  TEMPLATE:
  "Let me clarify: we need [feature 1], [feature 2], [feature 3].
  Should I handle [edge case]? Is [feature X] in scope?"

STEP 2 (5 min): IDENTIFY ENTITIES (Nouns → Classes)
  Read requirements. Underline NOUNS → each noun is a potential class.
  "User requests a ride" → User, Ride (or Trip)
  "Driver accepts" → Driver
  "Calculate fare" → FareCalculator (a service class)
  
  TEMPLATE entities to always consider:
  - The core entity (User, Product, Video, Tweet, Payment)
  - The status/state enum
  - Service classes (XService, XManager, XRepository)
  - Value objects (Location, Money, DateRange)
  - Relationship entities (Order, Booking, Subscription)

STEP 3 (5 min): IDENTIFY BEHAVIOURS (Verbs → Methods)
  Read requirements. Underline VERBS → each verb is a potential method.
  "User requests a ride" → user.requestRide() or TripService.createRequest()
  "Driver accepts" → driver.acceptRide() or TripService.acceptRequest()
  "Calculate fare" → FareCalculator.calculate()

STEP 4 (10 min): DRAW CLASS DIAGRAM
  Whiteboard: draw boxes (classes) and arrows (relationships).
  Show: inheritance, interfaces, associations.
  Mark: + public, - private, # protected
  
  Don't draw: all internal details. Just the key relationships.
  Most important: interfaces and their implementors.

STEP 5 (25 min): CODE KEY CLASSES
  Priority order:
  1. Core entity class (User, Video, Tweet, Payment)
  2. Interface/abstract class (the key abstraction)
  3. One concrete implementation
  4. Service/Facade class
  5. Anything time allows
  
  Show: encapsulation (private fields), exceptions, thread safety (if asked).

STEP 6 (5 min): DISCUSS TRADE-OFFS
  "What would break at scale?"
  "What design choices did you make and why?"
  "How would you extend this for [new requirement]?"
```

---

## PATTERN SELECTION GUIDE

```
"New payment type added → zero existing code changes?"
→ STRATEGY + FACTORY. New PaymentStrategy class. Register in factory.

"When event X happens, multiple places need to react?"
→ OBSERVER. Subject notifies all registered observers.

"Algorithm skeleton same but details differ per type?"
→ TEMPLATE METHOD. Abstract base with final template + abstract steps.

"I need exactly one global instance?"
→ SINGLETON. Private constructor + static getInstance().

"Complex object with many optional fields?"
→ BUILDER. Builder.withX().withY().build().

"Need undo/redo for operations?"
→ COMMAND. Each operation = Command object. Stack for history.

"Object behaviour changes based on its state?"
→ STATE. Each state = separate class. Context delegates to current state.

"Incompatible interfaces need to work together?"
→ ADAPTER. Wrapper translates interface B → interface A.

"Add features (logging, caching) without modifying class?"
→ DECORATOR. Wraps same interface, adds before/after delegating.

"Simplify access to complex subsystem?"
→ FACADE. One class with simple methods. Hides complexity.

"Tree structure: items and groups treated uniformly?"
→ COMPOSITE. Leaf and Composite implement same interface.

"Clone expensive objects instead of recreating?"
→ PROTOTYPE. Clone registry. Customize the clone.

"Control access to an object (lazy, secure, remote)?"
→ PROXY. Same interface as real object. Intercepts calls.
```

---

## JAVA vs C++ QUICK SYNTAX DIFF

```java
// ─────────── JAVA ──────────────────────────────────────────────────────────

// Class with inheritance:
public class Car extends Vehicle implements Drivable, Serializable {
    private final String brand;      // final = immutable
    protected int speed;             // accessible in subclasses
    static int count = 0;           // class-level variable

    public Car(String brand) {
        super();                     // Call parent constructor (optional if no-arg)
        this.brand = brand;
        count++;
    }
    
    @Override
    public void drive() { speed = 60; }
    
    public final void stop() { speed = 0; }  // Cannot be overridden
}

// Interface (pure abstraction):
public interface Drivable {
    void drive();                    // abstract by default
    default void honk() {           // default: has implementation
        System.out.println("Beep!");
    }
    static Drivable create() {      // static method in interface
        return new Car("Default");
    }
}

// Abstract class:
public abstract class Vehicle {
    abstract double fuelEfficiency();  // must be overridden
    void refuel() { System.out.println("Refueling..."); }  // inherited as-is
}

// Generics:
public <T extends Comparable<T>> T findMax(List<T> list) { ... }

// Anonymous class:
Runnable r = new Runnable() {
    @Override
    public void run() { System.out.println("Running"); }
};

// Lambda (functional interface):
Runnable r = () -> System.out.println("Running");
Comparator<String> cmp = (a, b) -> a.compareTo(b);

// Stream operations:
list.stream()
    .filter(x -> x > 0)
    .map(x -> x * 2)
    .sorted()
    .collect(Collectors.toList());

// Optional:
Optional<String> opt = Optional.of("hello");
opt.ifPresent(System.out::println);
String val = opt.orElse("default");

// Switch expression (Java 14+):
String result = switch (status) {
    case ACTIVE  -> "Active";
    case BLOCKED -> "Blocked";
    default      -> "Unknown";
};

// Try-with-resources:
try (FileReader fr = new FileReader("f.txt")) {
    // fr auto-closed on exit
} catch (IOException e) { ... }
```

```cpp
// ─────────── C++ ───────────────────────────────────────────────────────────

// Class with inheritance:
class Car : public Vehicle, public IDrivable {  // Multiple inheritance
    std::string brand_;    // trailing _ = private by convention
protected:
    int speed_ = 0;
public:
    static int count;      // Declaration (define in .cpp: int Car::count = 0;)
    
    explicit Car(std::string brand) : brand_(std::move(brand)) { ++count; }
    // explicit: no implicit conversion. std::move: no copy.
    
    void drive() override { speed_ = 60; }
    
    void stop() final { speed_ = 0; }  // Cannot be overridden further
    
    virtual ~Car() = default;  // MANDATORY for base classes!
};

// Abstract base (C++ "interface"):
class IDrivable {
public:
    virtual void drive() = 0;   // pure virtual = abstract
    virtual void honk() { std::cout << "Beep!\n"; }  // has default impl
    virtual ~IDrivable() = default;
};

// Templates (C++ generics):
template<typename T>
requires std::totally_ordered<T>  // C++20 concept
T findMax(const std::vector<T>& list);

// Lambda:
auto r = []{ std::cout << "Running\n"; };  // No capture
auto add = [](int a, int b) -> int { return a + b; };  // With params
int x = 5;
auto capture = [x]{ std::cout << x; };       // Capture by value
auto captureRef = [&x]{ x++; };             // Capture by reference
auto captureAll = [=]{ /* all by value */ };
auto captureAllRef = [&]{ /* all by ref */ };

// STL algorithms:
auto filtered = std::views::filter(vec, [](int x){ return x > 0; });  // C++20
std::sort(vec.begin(), vec.end());
auto it = std::find_if(vec.begin(), vec.end(), pred);

// std::optional (C++17):
std::optional<std::string> opt = std::make_optional("hello");
if (opt) std::cout << *opt;            // Dereference if present
std::string val = opt.value_or("default");  // Or default

// Switch (C++ 17 with [[fallthrough]]):
switch (status) {
    case Status::Active:  result = "Active"; break;
    case Status::Blocked: result = "Blocked"; break;
    default:              result = "Unknown"; break;
}

// RAII (no try-with-resources. Use destructors):
{   // Block scope
    std::ifstream file("f.txt");  // Opens in constructor
    // ... use file ...
}   // file.close() called in destructor. Even on exception!
```

---

## MEMORY: Java vs C++

```
JAVA:
  Memory management: GARBAGE COLLECTOR (GC). You don't free memory.
  All objects on HEAP (created with 'new').
  Primitives (int, double, boolean): on STACK (fast, auto-managed).
  
  Potential issues:
  - Memory leaks still possible: strong references prevent GC.
    (e.g., static collections holding old objects: observers never removed).
  - GC pauses: stop-the-world pauses (ms to seconds in old Java; modern GC: < 10ms).
  
  Best practices:
  - Remove from collections when done (removeObserver, unsubscribe).
  - Use WeakReference for caches (GC can collect if memory needed).
  - Close Closeable resources with try-with-resources.

C++:
  Memory management: MANUAL (your responsibility).
  Stack: local variables, function parameters. Auto-freed when scope exits.
  Heap: 'new' operator. Must 'delete' or use smart pointers.
  
  Smart pointers (USE THESE, NOT RAW new/delete):
  
  unique_ptr<T>:
    EXCLUSIVE OWNERSHIP. Cannot copy. Can move.
    Destroyed when: goes out of scope, or = nullptr, or moved from.
    Use: most cases. Composition. Single owner.
    Perf: zero overhead vs raw pointer.
    
  shared_ptr<T>:
    SHARED OWNERSHIP. Reference counted.
    Destroyed when: last shared_ptr to it is destroyed.
    Use: multiple owners (Observer pattern: multiple observers holding shared subjects).
    Perf: atomic reference count operations (slight overhead vs unique_ptr).
    
  weak_ptr<T>:
    NON-OWNING reference to shared_ptr-managed object.
    Does NOT prevent destruction. Must lock() to access (returns shared_ptr or nullptr).
    Use: break circular references (A → B → A via weak_ptr breaks the cycle).
         Observer pattern: observers hold weak_ptr to subject (don't keep subject alive).

  RULE: "New" code should not use raw new/delete. Use make_unique / make_shared.
  RULE: RAII: acquire resources in constructors, release in destructors.
  
  Potential issues:
  - Dangling pointer: raw pointer to freed memory.
  - Double free: deleting same memory twice.
  - Memory leak: heap memory not freed.
  - All solved by: smart pointers + RAII.
```

---

## COMMON LLD INTERVIEW MISTAKES

```
MISTAKE 1: Starting to code immediately.
  FIX: Always ask requirements first. 5 minutes of clarification saves 30 minutes of rework.

MISTAKE 2: God class (one class does everything).
  SIGNAL: Your class has 20+ methods. It knows about DB, UI, business logic, and networking.
  FIX: SRP. Split into: XService (business), XRepository (data), XController (API).

MISTAKE 3: Hardcoding future extension points.
  SIGNAL: "if (paymentType.equals('card')) { ... } else if (...UPI...) { ... }"
  FIX: Strategy + Factory. New payment type = new class. Zero modification of existing.

MISTAKE 4: Ignoring thread safety when interviewer hints at it.
  SIGNAL: "This will be used by multiple threads / high concurrency / lots of requests."
  FIX: synchronized methods, ReentrantLock, AtomicInteger, ConcurrentHashMap.
  Mention: "I'd use AtomicInteger for the counter because it's faster than synchronized."

MISTAKE 5: Using float/double for money.
  SIGNAL: "Calculate fare", "process payment", "price", "amount".
  FIX: Java: BigDecimal. C++: integer cents/paisa.
  Say: "I'll use BigDecimal here because floating point has precision issues with money."

MISTAKE 6: No validation in methods.
  FIX: Always validate inputs in constructor + public methods.
  throw new IllegalArgumentException("Amount must be positive: " + amount);
  Interviewers notice defensive programming. Shows production mindset.

MISTAKE 7: Ignoring equals/hashCode in Java.
  SIGNAL: Using objects as HashMap keys without overriding equals/hashCode.
  FIX: Override both. Use same fields in both.
  Rule: "If two objects are equals(), their hashCodes MUST be equal."

MISTAKE 8: Forgetting to use 'override' in C++.
  FIX: Always use 'override' keyword on derived class virtual methods.
       Without it: typo in method name → silently creates NEW method instead of overriding.
       With it: compiler error on mismatch → catches bugs early.

MISTAKE 9: Forgetting virtual destructor in C++.
  SIGNAL: Base class has virtual methods but no virtual destructor.
  FIX: Always add: virtual ~BaseClass() = default;
       Without: delete base_ptr → only base destructor called → derived resources leaked.

MISTAKE 10: Not explaining WHAT and WHY while coding.
  FIX: Talk while coding. "I'm making this private to enforce encapsulation."
       "I'm using Strategy here because we might add new algorithms later."
       "I'm using AtomicInteger instead of synchronized for better performance."
       Interviewers evaluate THINKING, not just the final code.
```

---

## TOP INTERVIEW QUESTIONS: PATTERN ANSWER TEMPLATE

```
Q: "How would you make the URL shortener thread-safe?"
A: "The critical shared state is the code generator counter and the URL map.
    For the counter: I'd use AtomicLong (Java) or std::atomic<uint64_t> (C++) for lock-free 
    increment. For the URL map: ConcurrentHashMap (Java) or unordered_map with shared_mutex (C++)
    to allow concurrent reads with exclusive writes."

Q: "How would you add a new notification type without changing existing code?"
A: "This is the Open/Closed Principle + Strategy pattern.
    I'd define a NotificationChannel interface with a send() method.
    For each new type: create a new class implementing NotificationChannel.
    Register it in a factory (map of name → creator).
    The NotificationService holds List<NotificationChannel> and iterates.
    Zero changes to NotificationService when adding new channels."

Q: "How would you handle the double-payment problem?"
A: "Idempotency keys. Each payment request carries a unique key (UUID generated by caller).
    Before processing: check if this key was already processed (lookup in DB).
    If found: return the SAME result as before (no new charge).
    If not found: process + store key → result atomically (in a transaction).
    DB: UNIQUE constraint on idempotency_key column as the last line of defense."

Q: "What pattern would you use for undo/redo?"
A: "Command pattern.
    Each user action = a Command object with execute() and undo() methods.
    Executed commands go to a history stack (Deque).
    Undo: pop from history, call undo(). Push to redo stack.
    Redo: pop from redo stack, call execute(). Push back to history.
    This approach also enables: replay (execute all commands from beginning) and
    persistence (serialize command objects to DB for crash recovery)."

Q: "How would you design the class diagram for a parking lot?"
A: "Entities: ParkingLot, ParkingFloor, ParkingSpot, Vehicle, Ticket, Payment.
    Relationships:
    - ParkingLot COMPOSES ParkingFloors (1 lot has many floors).
    - ParkingFloor COMPOSES ParkingSpots (1 floor has many spots).
    - ParkingSpot has-a Vehicle (when occupied), nullable.
    - Ticket has: vehicle, spot, entry_time. Created on entry.
    - Payment: calculates fee from Ticket (exit_time - entry_time) × hourly_rate.
    Patterns:
    - Strategy: PricingStrategy (flat, hourly, monthly).
    - Factory: SpotFactory.create(type) → HeavyVehicleSpot, MotorcycleSpot, CompactSpot.
    - Singleton: ParkingLot (one lot, global).
    - Observer: SpotAvailabilityObserver (display boards update when spot status changes)."
```

---

## HOW CASE STUDIES MAP TO INTERVIEW SCENARIOS

```
"Design Uber" → CS04_Uber.md:
  Classes: TripRequest, Trip, Driver, User, FareCalculator, DriverMatcher, LocationService.
  Patterns: Strategy (fare), Observer (trip events), State (trip status), Factory (fare type).
  Concurrency: ConcurrentHashMap for driver locations, AtomicLong for trip IDs.
  Thread safety: synchronized DriverPool.assign(), volatile GPS tracking flag.
  SOLID: UberService (facade) depends on IFareStrategy (DIP), not concrete classes.

"Design YouTube / Netflix" → CS06_YouTube.md, CS05_Netflix.md:
  Classes: Video, VideoVariant, TranscodeJob, Channel, Subscription, StreamingSession.
  Patterns: Template Method (transcode pipeline), Strategy (ABR), Observer (subscriptions).
  Composite: Playlist contains Videos and sub-Playlists.
  Concurrency: ThreadPool for transcoding, ReadWriteLock on content catalog.

"Design URL Shortener" → CS01_URL_Shortener.md:
  Classes: UrlEntry, SequenceGenerator, UrlStore, RedirectService.
  Patterns: Singleton (SequenceGenerator), Builder (UrlEntry), Facade (UrlShortenerService).
  Concurrency: AtomicLong counter, ConcurrentHashMap for URL store.
  Expiry: Scheduler + cleanup worker thread.

"Design Payment Gateway" → CS09_Payment_Gateway.md:
  Classes: PaymentRequest, PaymentGatewayService, IPaymentProcessor, IdempotencyStore.
  Patterns: Strategy (processors), Decorator (fraud + logging), Factory (processor routing).
  Idempotency: synchronized check-and-store or DB UNIQUE constraint on idempotency_key.
  Money: BigDecimal (Java) or integer paisa (C++). Never float.
  State: PaymentStatus enum with transition rules.

"Design Google Search" → CS07_Google_Search.md:
  Classes: Tokenizer, InvertedIndex, PageRankEngine, QueryParser, Ranker, SearchEngine.
  Patterns: Facade (SearchEngine), Template Method (search pipeline).
  Data structure: HashMap<String, List<PostingEntry>> for inverted index.
  Concurrency: ReadWriteLock on index (reads >> writes).
  TF-IDF + PageRank: both scores combined in Ranker.

"Design Twitter" → CS08_Twitter.md:
  Classes: Tweet, User, Timeline, FanoutService, TweetPublisher.
  Patterns: Observer (fanout to followers), Command (PostTweetCommand for queuing).
  Concurrency: Kafka for async fanout. Thread-safe timeline writes.
  BigDecimal for follower count? No — use AtomicLong (it's just a counter).

"Design AI System / Chatbot" → CS11_AI_Systems.md:
  Classes: LLMService, ILLMAdapter, VectorStore, RAGService, ConversationHistory.
  Patterns: Adapter (OpenAI/Anthropic/Gemini), Strategy (chunking), Facade (LLMService).
  Concurrency: ThreadPool for parallel chunk embedding, ConcurrentHashMap for vector cache.
  Context management: rolling window + token counting.
```

## HLD CONCEPTS THAT APPEAR IN LLD CASE STUDIES

> The boundary between HLD and LLD is NOT sharp.
> These HLD concepts appear directly in LLD class designs:

```
Caching (HLD Topic 04) in LLD:
  CS04 Uber: DriverLocationCache (in-memory Map, TTL 30s).
  CS06 YouTube: CachingSearchDecorator (wraps SearchService, Redis-backed).
  CS11 AI Systems: PromptCacheProxy (semantic hash → LLMResponse mapping).
  
  In LLD code: CachingDecorator pattern. Cache is a Decorator wrapping the real service.

Rate Limiting (HLD Topic 12) in LLD:
  CS06 YouTube: RateLimitDecorator wraps SearchService. N requests/second.
  CS11 AI Systems: LLMRateLimiter with token bucket algorithm.
  
  In LLD code: Decorator pattern. RateLimitDecorator wraps any service.

Message Queues (HLD Topic 06) in LLD:
  CS08 Twitter: FanoutService submits PostTweetCommand to Kafka queue.
  CS06 YouTube: TranscodeJobQueue submits jobs. Workers consume from queue.
  
  In LLD code: Command pattern. Commands are queued messages.

Consistent Hashing (HLD Topic 11) in LLD:
  CS04 Uber: DriverShardingService assigns drivers to shards by geo-hash.
  CS01 URL Shortener: multiple counter nodes. Each handles a range of IDs.
  
  In LLD code: This is a utility class used by the service layer.

API Design (HLD Topic 09) in LLD:
  Every case study has a service facade class whose public methods ARE the API.
  UberService.request_ride() = the ride API.
  PaymentGatewayService.process_payment() = the payment API.
  The facade IS the API surface, just implemented in code instead of HTTP endpoints.
```

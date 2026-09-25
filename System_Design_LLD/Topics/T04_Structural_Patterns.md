# LLD Topic 04: Design Patterns — Structural
## Adapter, Decorator, Facade, Composite, Proxy | Java + C++ | Every Keyword

---

> **STRUCTURAL PATTERNS** deal with how classes and objects are COMPOSED together
> to form larger structures. The key insight:
> "How do I assemble these pieces to get the right structure?"

---

## PATTERN 1: ADAPTER

```
PROBLEM: Two incompatible interfaces need to work together.
         You have code that expects Interface A. You have a library with Interface B.
         You can't change either (legacy code or third-party library).
         
ADAPTER: A wrapper that makes Interface B look like Interface A.

REAL EXAMPLES:
  - Java's InputStreamReader: adapts InputStream (bytes) → Reader (characters).
  - USB-C to HDMI adapter: laptop speaks USB-C, monitor speaks HDMI. Adapter translates.
  - Payment gateway: your code calls pay(), Razorpay API expects createOrder().
  - Indian plug → USA socket: different interfaces, adapter converts.
```

### Java — Adapter

```java
// ── Adapter: Third-party payment library integration ──────────────────────────

// YOUR existing interface (what your code expects):
interface PaymentGateway {
    boolean charge(double amount, String cardNumber);
    boolean refund(String transactionId);
}

// THIRD-PARTY LIBRARY (incompatible interface — you can't change this):
class RazorpaySDK {
    //  ↑ Imagine this comes from an external JAR file.
    //    Methods have different names, different parameters, different return types.

    public String createOrder(int amountInPaisa, String currency) {
        //  ↑ Takes amount in PAISA (not rupees!), returns order ID string.
        System.out.printf("Razorpay: Creating order for %d paisa%n", amountInPaisa);
        return "order_" + System.nanoTime();
        //  ↑ System.nanoTime(): high-resolution timer. Used to generate a unique order ID.
    }

    public boolean capturePayment(String orderId, String cardToken) {
        //  ↑ Different method name ('capturePayment' not 'charge').
        //    Different parameters (orderId + cardToken, not amount + cardNumber).
        System.out.printf("Razorpay: Capturing payment for order %s%n", orderId);
        return true;
    }

    public boolean initiateRefund(String orderId, int amountInPaisa) {
        //  ↑ 'initiateRefund' not 'refund'. Different signature.
        System.out.printf("Razorpay: Refunding %d paisa for order %s%n", amountInPaisa, orderId);
        return true;
    }
}

// ADAPTER: makes RazorpaySDK look like PaymentGateway:
class RazorpayAdapter implements PaymentGateway {
    //  ↑ implements PaymentGateway: this adapter LOOKS like a PaymentGateway to your code.
    //    Your code calls charge() → adapter translates → calls RazorpaySDK methods.

    private final RazorpaySDK razorpay;
    //  ↑ Has-A relationship: adapter WRAPS the Razorpay SDK (composition, not inheritance).
    //    The adapted object (adaptee) is stored as a field.

    public RazorpayAdapter(RazorpaySDK razorpay) {
        this.razorpay = razorpay;
    }

    @Override
    public boolean charge(double amountInRupees, String cardNumber) {
        //  ↑ Your code calls this with rupees and card number.
        //    Adapter TRANSLATES: rupees → paisa, card number → token.

        int amountInPaisa = (int)(amountInRupees * 100);
        //  ↑ Razorpay uses paisa. 1 rupee = 100 paisa.
        //  ↑ (int)(...): cast to int. Razorpay expects int, not double.

        String cardToken = tokenize(cardNumber);
        //  ↑ Real: Razorpay's card tokenization. Here: simplified.

        String orderId = razorpay.createOrder(amountInPaisa, "INR");
        //  ↑ Step 1: Create order (Razorpay's flow requires this first).

        return razorpay.capturePayment(orderId, cardToken);
        //  ↑ Step 2: Capture the payment.
        //    From your code's perspective: one charge() call.
        //    Internally: two Razorpay API calls + data transformation. Transparent.
    }

    @Override
    public boolean refund(String transactionId) {
        return razorpay.initiateRefund(transactionId, 0);
        //  ↑ Full refund (amount=0 in this simulation).
        //    Translates: refund(transactionId) → initiateRefund(orderId, amount).
    }

    private String tokenize(String cardNumber) {
        return "tok_" + cardNumber.substring(cardNumber.length() - 4);
        //  ↑ Simplified tokenization: just use last 4 digits prefixed with "tok_".
        //    Real: cryptographic tokenization replacing card number with secure token.
    }
}

// USAGE: your code never changes even if payment provider changes:
// PaymentGateway gateway = new RazorpayAdapter(new RazorpaySDK());
// gateway.charge(999.0, "4111111111111111");
// gateway.refund("order_12345");
//
// Switch to Stripe: just swap adapter. Your charge() calls unchanged.
// PaymentGateway gateway = new StripeAdapter(new StripeSDK("sk_test_..."));
```

---

## PATTERN 2: DECORATOR

```
PROBLEM: Add new behaviour to an object WITHOUT modifying its class.
         Multiple features can be combined flexibly (mix and match).
         
WITHOUT DECORATOR:
  class LoggedCachedAuthenticatedPaymentService extends PaymentService { ... }
  // Explosion of subclasses for every feature combination! (2^n combinations)

WITH DECORATOR:
  base = new PaymentService()
  service = new LoggingDecorator(service)      // Add logging
  service = new CachingDecorator(service)      // Add caching
  service = new AuthDecorator(service)         // Add authentication
  // Mix and match features without subclass explosion.

REAL EXAMPLES:
  - Java IO: new BufferedInputStream(new FileInputStream("file.txt"))
    BufferedInputStream DECORATES FileInputStream with buffering.
  - HTTP middleware (Express.js): request → auth middleware → logging → handler
  - Coffee shop: Coffee + Milk + Sugar + Whip = decorated coffee order
```

### Java — Decorator

```java
// ── Decorator: Search Service with Caching + Logging ──────────────────────────

// COMPONENT INTERFACE (what decorator and real service both implement):
interface SearchService {
    List<String> search(String query);
    //  ↑ Both the real service and all decorators implement this.
    //    Caller interacts with SearchService interface — doesn't know if it's the real
    //    implementation or a chain of decorators.
}

// CONCRETE COMPONENT (the real service):
class ElasticsearchService implements SearchService {
    @Override
    public List<String> search(String query) {
        System.out.println("Elasticsearch: searching for '" + query + "'...");
        // Simulate 200ms DB call:
        try { Thread.sleep(200); }
        //  ↑ Thread.sleep(ms): pause current thread for N milliseconds.
        //    Simulates a slow database search.
        catch (InterruptedException e) { Thread.currentThread().interrupt(); }
        //  ↑ Thread.currentThread().interrupt(): re-set the interrupted flag.
        //    Best practice: never swallow InterruptedException silently.
        return List.of("Result 1 for " + query, "Result 2 for " + query);
        //  ↑ List.of(...): creates an IMMUTABLE list. Java 9+.
        //    Cannot add/remove elements. Good for fixed-size collections.
    }
}

// ABSTRACT DECORATOR BASE (optional but clean structure):
abstract class SearchServiceDecorator implements SearchService {
    //  ↑ Decorator implements the same interface as the component.
    //    This is what makes decoration transparent to the caller.

    protected final SearchService wrapped;
    //  ↑ The wrapped component. Could be the real service OR another decorator.
    //    This is the "decoration chain": Decorator → Decorator → ... → RealService.
    //  ↑ protected: subclass decorators can access it.
    //  ↑ final: the wrapped component is set once and never replaced.

    public SearchServiceDecorator(SearchService wrapped) {
        this.wrapped = wrapped;
    }
}

// DECORATOR 1: Caching
class CachingDecorator extends SearchServiceDecorator {
    //  ↑ Adds caching without modifying ElasticsearchService.

    private final Map<String, List<String>> cache = new HashMap<>();
    //  ↑ Simple in-memory cache: query → results.
    //    Production: Redis with TTL.
    private final int maxCacheSize;

    public CachingDecorator(SearchService wrapped, int maxCacheSize) {
        super(wrapped);   // super(wrapped) calls SearchServiceDecorator constructor
        this.maxCacheSize = maxCacheSize;
    }

    @Override
    public List<String> search(String query) {
        // CHECK CACHE FIRST:
        if (cache.containsKey(query)) {
            //  ↑ containsKey(): O(1) hash check. True if key exists in map.
            System.out.println("Cache HIT for: '" + query + "'");
            return cache.get(query);
            //  ↑ Return cached result instantly. No DB call. Very fast.
        }

        // CACHE MISS → call the wrapped service:
        System.out.println("Cache MISS for: '" + query + "' → forwarding...");
        List<String> results = wrapped.search(query);
        //  ↑ Delegate to the wrapped service (could be Elasticsearch or another decorator).

        // STORE IN CACHE:
        if (cache.size() < maxCacheSize) {
            //  ↑ Simple eviction: stop caching when full.
            //    Production: LRU eviction (remove least recently used when full).
            cache.put(query, results);
        }
        return results;
    }
}

// DECORATOR 2: Logging
class LoggingDecorator extends SearchServiceDecorator {
    //  ↑ Adds timing + logging without touching ElasticsearchService or CachingDecorator.

    public LoggingDecorator(SearchService wrapped) {
        super(wrapped);
    }

    @Override
    public List<String> search(String query) {
        long startMs = System.currentTimeMillis();
        //  ↑ currentTimeMillis(): wall clock time in milliseconds since epoch.
        //    Used to measure elapsed time.

        System.out.printf("[LOG] Search started: '%s'%n", query);
        List<String> results = wrapped.search(query);   // Delegate

        long elapsedMs = System.currentTimeMillis() - startMs;
        System.out.printf("[LOG] Search completed: '%s' → %d results in %dms%n",
                          query, results.size(), elapsedMs);

        return results;
    }
}

// DECORATOR 3: Rate Limiting
class RateLimitDecorator extends SearchServiceDecorator {
    //  ↑ Adds rate limiting: max N searches per second per caller.

    private int requestsThisSecond = 0;
    private long windowStart = System.currentTimeMillis();
    private final int maxPerSecond;

    public RateLimitDecorator(SearchService wrapped, int maxPerSecond) {
        super(wrapped);
        this.maxPerSecond = maxPerSecond;
    }

    @Override
    public synchronized List<String> search(String query) {
        //  ↑ synchronized: only one thread can call this at a time.
        //    Prevents race condition on requestsThisSecond counter.
        long now = System.currentTimeMillis();
        if (now - windowStart >= 1000) {
            //  ↑ New second started: reset counter.
            requestsThisSecond = 0;
            windowStart = now;
        }
        if (requestsThisSecond >= maxPerSecond) {
            throw new RuntimeException("Rate limit exceeded: max " + maxPerSecond + "/second");
        }
        requestsThisSecond++;
        //  ↑ Count this request.
        return wrapped.search(query);
    }
}

// USAGE — chain decorators:
// SearchService base    = new ElasticsearchService();
// SearchService cached  = new CachingDecorator(base, 100);
// SearchService logged  = new LoggingDecorator(cached);
// SearchService limited = new RateLimitDecorator(logged, 10);
//
// limited.search("python tutorial");
// Call chain: RateLimit → Logging → Caching → Elasticsearch
// Each decorator adds its behaviour, then delegates to wrapped.
//
// // Second call (same query):
// limited.search("python tutorial");
// Call chain: RateLimit → Logging → Caching (HIT!) → returns immediately. No Elasticsearch call!
```

---

## PATTERN 3: FACADE

```
PROBLEM: A subsystem has many complex classes. Calling code must coordinate many objects.
         Direct use is complicated and verbose.
         
FACADE: One simple class that hides ALL the complexity.
        Callers only know the facade. The subsystem internals are hidden.

THINK: Hotel concierge. You say "book me a tour." 
       Concierge (facade) calls: taxi company, tour guide, restaurant, hotel.
       You don't manage any of those directly.

REAL EXAMPLES:
  - Spring Boot JpaRepository: one interface for all DB operations (save, find, delete)
  - YouTubeService (our CS06): one class, hides crawler, index, ranker, fanout
  - PaymentGatewayService (our CS09): one class, hides card processor, fraud check, webhook
```

### Java — Facade

```java
// ── Facade: Home Theater ────────────────────────────────────────────────────────

// COMPLEX SUBSYSTEM COMPONENTS:
class Projector {
    private boolean on = false;
    public void turnOn()  { on = true;  System.out.println("Projector: ON"); }
    public void turnOff() { on = false; System.out.println("Projector: OFF"); }
    public void setInput(String input) {
        System.out.println("Projector: input set to " + input);
    }
}

class SoundSystem {
    private int volume = 30;
    public void turnOn()  { System.out.println("Sound: ON"); }
    public void turnOff() { System.out.println("Sound: OFF"); }
    public void setVolume(int v) {
        volume = Math.max(0, Math.min(100, v));
        //  ↑ Clamp volume between 0 and 100.
        System.out.println("Sound: volume = " + volume);
    }
    public void setSurroundMode(String mode) {
        System.out.println("Sound: mode = " + mode);
    }
}

class StreamingPlayer {
    public void turnOn() { System.out.println("Player: ON"); }
    public void play(String movie) { System.out.println("Player: playing '" + movie + "'"); }
    public void stop() { System.out.println("Player: STOP"); }
    public void turnOff() { System.out.println("Player: OFF"); }
}

class Lights {
    public void dim(int percent) { System.out.println("Lights: dimmed to " + percent + "%"); }
    public void brighten() { System.out.println("Lights: full brightness"); }
}

// WITHOUT FACADE: caller must coordinate 4 objects:
// projector.turnOn();
// projector.setInput("HDMI 1");
// sound.turnOn();
// sound.setVolume(60);
// sound.setSurroundMode("Dolby 5.1");
// lights.dim(20);
// player.turnOn();
// player.play("Inception");
// ... 8 method calls just to watch a movie. Error-prone.

// FACADE: Simple interface hiding all this complexity:
class HomeTheaterFacade {
    //  ↑ ONE class to rule them all.

    private final Projector     projector;
    private final SoundSystem   sound;
    private final StreamingPlayer player;
    private final Lights        lights;

    public HomeTheaterFacade(Projector proj, SoundSystem sound,
                              StreamingPlayer player, Lights lights) {
        this.projector = proj;
        this.sound     = sound;
        this.player    = player;
        this.lights    = lights;
    }

    // SIMPLE METHODS for common operations:
    public void watchMovie(String movie) {
        //  ↑ ONE method call replaces 8 coordinated method calls.
        System.out.println("--- Watch Movie Mode ---");
        projector.turnOn();
        projector.setInput("HDMI 1");
        sound.turnOn();
        sound.setVolume(60);
        sound.setSurroundMode("Dolby 5.1");
        lights.dim(20);
        player.turnOn();
        player.play(movie);
    }

    public void endMovie() {
        //  ↑ Reverse of watchMovie(). Turns everything off in correct order.
        System.out.println("--- End Movie ---");
        player.stop();
        player.turnOff();
        sound.turnOff();
        projector.turnOff();
        lights.brighten();
    }

    public void partyMode() {
        sound.setVolume(100);
        sound.setSurroundMode("Bass Boost");
        lights.dim(10);
        System.out.println("--- Party Mode ON ---");
    }
}

// USAGE: caller only knows the facade. Doesn't need to know Projector, SoundSystem, etc.
// HomeTheaterFacade theater = new HomeTheaterFacade(
//     new Projector(), new SoundSystem(), new StreamingPlayer(), new Lights());
// theater.watchMovie("Inception");   // Simple. Clean. One method.
// theater.endMovie();
```

---

## PATTERN 4: COMPOSITE

```
PROBLEM: You need to treat INDIVIDUAL objects and GROUPS of objects uniformly.
         The structure is tree-like (hierarchy).
         
EXAMPLES:
  - File system: File and Folder. Folder contains Files and other Folders.
    getSize() on File → file's size. getSize() on Folder → sum of all children's sizes.
  - UI components: Button, TextBox are leaves. Panel/Window are composites (contain others).
  - Organization chart: Employee is leaf. Manager is composite (has reports).
  - Netflix content (our CS05): Movie is leaf. Series is composite (contains Episodes).
  - Comment tree (our CS06): Comment is leaf. But has child comments (composite).
  
STRUCTURE:
  Component (interface): the common interface. Both leaf and composite implement it.
  Leaf: no children. Does the real work.
  Composite: has children. Delegates work to children.
```

### Java — Composite

```java
// ── Composite: File System ────────────────────────────────────────────────────

import java.util.ArrayList;
import java.util.List;

// COMPONENT: common interface for both File and Directory:
interface FileSystemEntry {
    String getName();
    long   getSize();    // Bytes
    void   print(String indent);   // Display with indentation for tree view
}

// LEAF: has no children. Does its own work.
class File implements FileSystemEntry {
    private final String name;
    private final long   sizeBytes;

    public File(String name, long sizeBytes) {
        this.name      = name;
        this.sizeBytes = sizeBytes;
    }

    @Override
    public String getName() { return name; }

    @Override
    public long getSize() { return sizeBytes; }
    //  ↑ LEAF: just return its own size. No delegation.

    @Override
    public void print(String indent) {
        System.out.printf("%s📄 %s (%,d bytes)%n", indent, name, sizeBytes);
        //  ↑ %,d: integer with comma separator (1,234,567 instead of 1234567). More readable.
    }
}

// COMPOSITE: contains other FileSystemEntry objects (Files or Directories).
class Directory implements FileSystemEntry {
    private final String name;
    private final List<FileSystemEntry> children = new ArrayList<>();
    //  ↑ children: holds both Files and other Directories.
    //    FileSystemEntry (interface) type: can hold any subtype (File or Directory).
    //    This is the key to Composite: children are the SAME interface type.

    public Directory(String name) { this.name = name; }

    public void add(FileSystemEntry entry) {
        children.add(entry);
        //  ↑ Add any FileSystemEntry (File or Directory) as a child.
    }

    public boolean remove(FileSystemEntry entry) {
        return children.remove(entry);
        //  ↑ List.remove(Object): removes first occurrence of this object.
        //    Returns true if the entry was found and removed.
        //    Equality check uses entry.equals() (or reference equality by default).
    }

    @Override
    public String getName() { return name; }

    @Override
    public long getSize() {
        return children.stream()
                       .mapToLong(FileSystemEntry::getSize)   // Each child → its size
                       .sum();
        //  ↑ COMPOSITE: delegate getSize() to ALL children, sum the results.
        //    If child is a File: returns file's bytes.
        //    If child is a Directory: recursively sums ITS children's sizes.
        //    This RECURSIVE delegation is the core of Composite pattern.
        //  ↑ mapToLong: converts to LongStream (for longs, not ints).
        //    Long can hold sizes up to 9 petabytes. Safer than int for file sizes.
    }

    @Override
    public void print(String indent) {
        System.out.printf("%s📁 %s/ (%,d bytes)%n", indent, name, getSize());
        for (FileSystemEntry child : children) {
            child.print(indent + "  ");
            //  ↑ Recursive: each child prints itself with increased indentation.
            //    File: prints one line.
            //    Directory: prints itself + all its children (recursively).
            //    Result: tree-like display.
        }
    }
}

// USAGE:
// Directory root = new Directory("root");
// Directory src  = new Directory("src");
// Directory test = new Directory("test");
//
// src.add(new File("Main.java",  5_000));
// src.add(new File("Utils.java", 3_000));
// test.add(new File("MainTest.java", 2_000));
//
// root.add(src);
// root.add(test);
// root.add(new File("README.md", 1_024));
//
// root.print("");       // Prints entire tree
// root.getSize();       // Recursively sums all file sizes: 11,024
//
// BEAUTY: calling getSize() on root (Directory) works the same way as on a File.
// Caller treats File and Directory UNIFORMLY through FileSystemEntry interface.
```

---

## PATTERN 5: PROXY

```
PROBLEM: Control access to an object. Add behaviour before/after delegating.
         Common use cases:
         
PROXY TYPES:
  1. VIRTUAL PROXY: Lazy initialization. Create expensive object only when first needed.
  2. PROTECTION PROXY: Access control. Check permissions before delegating.
  3. REMOTE PROXY: Object is in different address space (RPC stub).
  4. CACHING PROXY: Cache results to avoid expensive repeated operations.
  5. LOGGING PROXY: Log all method calls (for debugging/auditing).

KEY DIFFERENCE FROM DECORATOR:
  Decorator: ADDS behaviour. Client knows it's a decorator. Typically composes multiple.
  Proxy: CONTROLS access. Client thinks it's the real object. Usually one proxy.
```

### Java — Proxy (Virtual + Protection)

```java
// ── Proxy: Image Loader (Virtual Proxy + Access Control) ─────────────────────

// SUBJECT INTERFACE: both real image and proxy implement this:
interface Image {
    void display();
    int getWidth();
    int getHeight();
    String getFilename();
}

// REAL SUBJECT: expensive to create (loads from disk):
class RealImage implements Image {
    private final String filename;
    private int width, height;
    private byte[] pixelData;  // Large byte array!

    public RealImage(String filename) {
        this.filename = filename;
        loadFromDisk(); // EXPENSIVE: reads file from disk. Called immediately on construction.
    }

    private void loadFromDisk() {
        System.out.printf("Loading image from disk: %s (this takes 500ms)%n", filename);
        try { Thread.sleep(500); }   // Simulate slow disk read
        catch (InterruptedException e) { Thread.currentThread().interrupt(); }
        width     = 1920;
        height    = 1080;
        pixelData = new byte[width * height * 4]; // RGBA: 8MB for 1920×1080!
        System.out.printf("Loaded: %s (%dx%d, %dMB)%n", filename, width, height,
                          pixelData.length / 1_048_576);
        //  ↑ 1_048_576 = 2^20 = bytes per MB.
    }

    @Override public void display() { System.out.println("Displaying: " + filename); }
    @Override public int getWidth()  { return width; }
    @Override public int getHeight() { return height; }
    @Override public String getFilename() { return filename; }
}

// VIRTUAL PROXY: lazy initialization + access control:
class ImageProxy implements Image {
    //  ↑ Implements same interface as RealImage.
    //    Client can't tell if it's talking to proxy or real image. Transparent.

    private final String filename;
    private RealImage realImage = null;   // null = not yet loaded (lazy)
    //  ↑ null at start. RealImage is NOT created yet.
    //    Created only when display() is first called.
    //    If only getFilename() or getWidth() is called: real image NEVER loaded.
    //    This is the VIRTUAL PROXY: defers expensive creation until actually needed.

    private final String currentUser;
    private final Set<String> allowedUsers;
    //  ↑ PROTECTION PROXY: only certain users can see this image.

    public ImageProxy(String filename, String currentUser, Set<String> allowedUsers) {
        this.filename     = filename;
        this.currentUser  = currentUser;
        this.allowedUsers = new HashSet<>(allowedUsers); // Defensive copy
        // Note: RealImage NOT created here. Delayed until display() is called.
    }

    @Override
    public void display() {
        // Step 1: Access control check (Protection Proxy):
        if (!allowedUsers.contains(currentUser)) {
            throw new SecurityException(
                "User " + currentUser + " is not authorized to view: " + filename);
        }
        //  ↑ if fails: throw immediately. RealImage never loaded. Efficient.

        // Step 2: Lazy initialization (Virtual Proxy):
        if (realImage == null) {
            //  ↑ First call to display(): realImage is null → create it now.
            realImage = new RealImage(filename);
            //  ↑ EXPENSIVE operation happens here, not at construction time.
            //    If display() is never called: this line never runs → no wasted resources.
        }

        realImage.display();   // Delegate to real image
    }

    // Metadata methods that DON'T need the real image loaded:
    @Override public String getFilename() { return filename; }

    @Override
    public int getWidth() {
        // Width doesn't need the pixel data — return a default (or load separately)
        return realImage != null ? realImage.getWidth() : 0;
        //  ↑ Ternary: if real image exists → return its width. Otherwise: 0.
        //    Avoids loading the full image just to know its dimensions.
        //    Production: store dimensions in a metadata DB separate from pixel data.
    }

    @Override public int getHeight() { return realImage != null ? realImage.getHeight() : 0; }
}

// USAGE:
// Set<String> admins = Set.of("sachin", "priya");
// Image img = new ImageProxy("design_secret.png", "sachin", admins);
//
// String name = img.getFilename(); // Instant. No disk read. Proxy returns its own field.
// img.display();                   // NOW loads from disk (first call). Displays.
// img.display();                   // SECOND call: realImage already loaded. Instant.
//
// Image img2 = new ImageProxy("design_secret.png", "hacker", admins);
// img2.display();  // → SecurityException: "hacker" not in allowedUsers.
```

---

## C++ Key Patterns

```cpp
// ── C++ Decorator with unique_ptr ─────────────────────────────────────────────
class SearchService {
public:
    virtual ~SearchService() = default;
    virtual std::vector<std::string> search(const std::string& query) = 0;
};

class ElasticsearchService : public SearchService {
public:
    std::vector<std::string> search(const std::string& query) override {
        printf("Elasticsearch: searching '%s'\n", query.c_str());
        return {"Result 1", "Result 2"};
    }
};

// BASE DECORATOR:
class SearchDecorator : public SearchService {
protected:
    std::unique_ptr<SearchService> wrapped_;
    //  ↑ unique_ptr: owns the wrapped service. Cannot be copied (ownership is exclusive).
    //    When decorator is destroyed: wrapped_ is also destroyed automatically.
    //    No memory leak. RAII.

public:
    explicit SearchDecorator(std::unique_ptr<SearchService> wrapped)
        : wrapped_(std::move(wrapped)) {}
        //  ↑ Move unique_ptr: transfer ownership from caller to this decorator.
        //    After move: caller's pointer is null. Decorator owns the wrapped object.
};

class CachingDecorator : public SearchDecorator {
    std::unordered_map<std::string, std::vector<std::string>> cache_;

public:
    using SearchDecorator::SearchDecorator; // Inherit constructor (C++11)
    //  ↑ using Base::Base: inherit all base class constructors.
    //    No need to re-write constructor that just calls super.

    std::vector<std::string> search(const std::string& query) override {
        auto it = cache_.find(query);
        if (it != cache_.end()) {
            printf("Cache HIT: %s\n", query.c_str());
            return it->second; // Return cached vector
        }
        auto results = wrapped_->search(query); // Delegate
        cache_[query] = results;                // Cache the results
        return results;
    }
};

// USAGE:
// auto base    = std::make_unique<ElasticsearchService>();
// auto cached  = std::make_unique<CachingDecorator>(std::move(base));
// cached->search("python");  // First call: miss → Elasticsearch
// cached->search("python");  // Second call: HIT → cache
//  ↑ std::move(base): transfer ownership into CachingDecorator.
//    After move: base is null. Only cached owns the ElasticsearchService.

// ── C++ Composite ──────────────────────────────────────────────────────────────
class FileSystemEntry {
public:
    virtual ~FileSystemEntry() = default;
    virtual std::string name() const = 0;
    virtual long size() const = 0;
    virtual void print(const std::string& indent = "") const = 0;
};

class File : public FileSystemEntry {
    std::string name_;
    long size_;
public:
    File(std::string n, long s) : name_(std::move(n)), size_(s) {}
    std::string name()  const override { return name_; }
    long        size()  const override { return size_; }
    void print(const std::string& indent) const override {
        printf("%s📄 %s (%ld bytes)\n", indent.c_str(), name_.c_str(), size_);
    }
};

class Directory : public FileSystemEntry {
    std::string name_;
    std::vector<std::unique_ptr<FileSystemEntry>> children_;
    //  ↑ vector of unique_ptr: owns all children.
    //    When Directory is destroyed: all children are automatically destroyed. No leaks.
    //    unique_ptr in vector: move semantics required (cannot copy unique_ptr).
public:
    explicit Directory(std::string n) : name_(std::move(n)) {}

    void add(std::unique_ptr<FileSystemEntry> entry) {
        children_.push_back(std::move(entry));
        //  ↑ push_back + move: transfer ownership of entry into children_ vector.
    }

    std::string name() const override { return name_; }

    long size() const override {
        long total = 0;
        for (const auto& child : children_)
            total += child->size();
        //  ↑ Recursive delegation to all children.
        return total;
    }

    void print(const std::string& indent) const override {
        printf("%s📁 %s/ (%ld bytes)\n", indent.c_str(), name_.c_str(), size());
        for (const auto& child : children_)
            child->print(indent + "  ");
        //  ↑ Each child prints itself with extra indentation.
    }
};
```

---

## Pattern Summary

```
ADAPTER: Convert incompatible interface → compatible.
  Real: Java IO (InputStreamReader), payment gateway wrappers.
  Signal: "Third-party library has different interface than what my code expects."
  
DECORATOR: Add behaviour without modifying class. Stack multiple features.
  Real: Java BufferedInputStream, Express.js middleware.
  Signal: "I want to add logging/caching/auth independently, mix and match."

FACADE: Simplify complex subsystem with one clean interface.
  Real: Every microservice's API surface, Spring JpaRepository.
  Signal: "Callers shouldn't need to know about X, Y, Z — just one clean method."

COMPOSITE: Treat individual items and groups uniformly. Tree structures.
  Real: File system, UI components, org chart, Netflix episodes.
  Signal: "Part and whole should be treated the same way."

PROXY: Control access to an object. Looks identical to the real object.
  Real: Hibernate lazy loading, RPC stubs, security proxies.
  Signal: "I need lazy loading / access control / remote delegation transparent to caller."

ADAPTER vs DECORATOR vs PROXY:
  All three WRAP another object. How to tell them apart:
  ADAPTER: changes the INTERFACE. Client uses interface A, wrapped object is interface B.
  DECORATOR: same interface. Adds behaviour. Multiple can be stacked.
  PROXY: same interface. Controls access. Usually one. Client thinks it IS the real object.
```

---

## HOW STRUCTURAL PATTERNS APPEAR IN THE LLD CASE STUDIES

### ADAPTER — Where it appears

```
CS09 Payment Gateway (CS09_Payment_Gateway.md):
  RazorpayAdapter wraps RazorpaySDK's non-standard API.
  Your code: processor.charge(amount, cardNumber) — simple, standard.
  Internally: adapter calls createOrder(amountInPaisa, "INR") then capturePayment(orderId, token).
  The TRANSLATION from your interface to Razorpay's interface = Adapter.
  
  StripeAdapter wraps StripeSDK. Same pattern.
  Your PaymentGatewayService never changes when you add a new payment provider.
  Each provider gets its own Adapter class.

CS11 AI Systems (CS11_AI_Systems.md):
  OpenAIAdapter adapts OpenAI's REST API to ILLMAdapter.generate(prompt, params).
  AnthropicAdapter adapts Anthropic's API to the same interface.
  GeminiAdapter adapts Google's API.
  LLMService calls adapter.generate(). Same call. Different HTTP bodies under the hood.
  
  The "translation" of params dict → vendor-specific JSON request body = Adapter pattern.

CS07 Google Search:
  ExternalDataSourceAdapter: adapts various crawler outputs (HTML, PDF, RSS)
  to a common Document format that InvertedIndex understands.
  Crawler returns raw HTML; Adapter translates to { url, title, body_text, links }.

WHEN TO SPOT IT: "Third-party library has different method names/signatures than what I need."
```

### DECORATOR — Where it appears

```
CS04 Uber:
  LoggingFareDecorator wraps IFareStrategy.
  base_strategy = NormalPricingStrategy()
  logged_strategy = LoggingFareDecorator(base_strategy)
  called_strategy = RateLimitedFareDecorator(logged_strategy)
  UberService uses called_strategy — same IFareStrategy interface. Multiple features stacked.

CS06 YouTube:
  SearchService chain:
  base    = ElasticsearchService()
  cached  = CachingSearchDecorator(base)       # adds Redis caching
  logged  = LoggingSearchDecorator(cached)     # adds timing logs
  limited = RateLimitDecorator(logged, 100)    # adds rate limiting
  
  All implement SearchService interface. Stacked like onion layers.
  Adding a new feature (e.g., A/B testing): wrap with ABTestDecorator. Zero existing changes.

CS11 AI Systems:
  LLMService chain:
  base        = RawLLMAdapter(api_key)
  with_retry  = RetryDecorator(base, max_retries=3)     # adds retry on 429/500
  with_cache  = PromptCacheDecorator(with_retry)         # adds semantic cache
  with_audit  = AuditLogDecorator(with_cache)            # logs all prompts
  
  All implement ILLMAdapter. Same generate() call at top level.

CS09 Payment Gateway:
  PaymentProcessor chain:
  base        = StripeCardProcessor(api_key)
  with_fraud  = FraudCheckDecorator(base)      # adds fraud scoring before charge
  with_log    = AuditDecorator(with_fraud)     # logs every charge/refund
  with_retry  = RetryDecorator(with_log)       # retries on transient errors

WHEN TO SPOT IT: "I want to add X, Y, Z features WITHOUT modifying the original class."
```

### FACADE — Where it appears

```
CS04 Uber (CS04_Uber.md):
  UberService IS the facade.
  Hides: LocationTracker, DriverMatcher, FareCalculator, TripRepository, NotificationService.
  Mobile app calls: uber_service.request_ride(user, pickup, dropoff).
  ONE method. Internally: find drivers → match → calculate fare → create trip → notify driver.
  App doesn't coordinate 5 services. UberService does.

CS07 Google Search (CS07_Google_Search.md):
  SearchEngine IS the facade.
  Hides: Tokenizer, InvertedIndex, PageRankEngine, QueryParser, Ranker, Snippet generator.
  Caller calls: search_engine.search("python tutorial") → gets results.
  Internally: parse → tokenize → lookup → score → rank → snippets → return.
  
CS09 Payment Gateway:
  PaymentGatewayService IS the facade.
  Hides: FraudDetector, CardProcessor, UPIProcessor, IdempotencyStore, WebhookNotifier.
  Merchant calls: gateway.process_payment(request) → gets result.

CS11 AI Systems:
  LLMService IS the facade.
  Hides: ILLMAdapter, PromptBuilder, ConversationHistoryManager, TokenCounter, VectorStore.
  App calls: llm_service.chat(user_message) → gets response.

WHEN TO SPOT IT: "The caller should only need ONE simple method, not coordinate N classes."
```

### COMPOSITE — Where it appears

```
CS05 Netflix (CS05_Netflix.md):
  ContentItem (interface) — both leaf and composite implement it.
  Episode (leaf): get_stream_url() → direct URL.
  Series (composite): contains Episodes. get_stream_url() → playlist of episode URLs.
  
  get_total_duration(): Series recursively sums all episode durations.
  Caller: for item in library: print(item.get_total_duration())
  Works for Episode (single value) and Series (recursive sum). Composite pattern.

CS06 YouTube:
  Playlist (composite) contains Videos (leaf) and other Playlists (composite).
  get_all_videos(): recursively collects all videos from nested playlists.
  Caller treats playlist and video uniformly: player.play(content).

CS10 MakeMyTrip:
  TravelPackage (composite) contains: FlightBooking (leaf), HotelBooking (leaf), 
  ActivityBooking (leaf), and sub-packages (composite).
  total_price() → recursively sums all components.
  cancel() → recursively cancels all components. Clean tree structure.

WHEN TO SPOT IT: "Tree structure where you want to treat leaf and branch the same way."
```

### PROXY — Where it appears

```
CS01 URL Shortener:
  Short URL redirect = VIRTUAL PROXY behavior.
  http://short.ly/abc → proxy lookup → redirect to real URL.
  Caller thinks they're accessing the real resource. Proxy intercepts and redirects.

CS06 YouTube:
  LazyVideoLoader: proxy for Video objects.
  Video metadata (title, thumbnail) loaded immediately.
  Actual video segments: loaded only when user presses play (Virtual Proxy / Lazy Loading).
  HLS CDN proxy: client requests from CDN edge (proxy). Edge fetches from origin if not cached.

CS09 Payment Gateway:
  3DS authentication proxy: before actual payment processing.
  PaymentProxy.charge() → check if 3DS required → if yes: redirect to 3DS flow.
  Actual CardProcessor.charge() only called after authentication passes.
  Caller: just calls gateway.charge(). Proxy handles the 3DS decision transparently.

CS11 AI Systems:
  PromptCacheProxy: wraps LLMAdapter.
  On generate(prompt): compute semantic hash of prompt → check cache.
  Cache hit: return immediately (no API call, no cost).
  Cache miss: delegate to real LLMAdapter, then store result in cache.
  Caller sees same interface. Doesn't know about the cache.

WHEN TO SPOT IT: "I want to intercept calls to the real object to add: caching / auth / lazy-load / logging."
```

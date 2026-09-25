# LLD Topic 03: Design Patterns — Creational
## Singleton, Factory, Builder, Prototype | Java + C++ | Every Keyword

---

> **WHAT ARE DESIGN PATTERNS?**
> Reusable solutions to COMMONLY OCCURRING problems in software design.
> NOT code you copy-paste. It's a TEMPLATE for solving a type of problem.
> 23 classic patterns from "Gang of Four" (GoF) book (1994).
>
> **THREE CATEGORIES:**
> CREATIONAL → How objects are created
> STRUCTURAL → How objects are composed (T04)
> BEHAVIORAL → How objects communicate (T05)

---

## PATTERN 1: SINGLETON

```
PROBLEM: We need EXACTLY ONE instance of a class to exist globally.
         Multiple instances would cause bugs or waste resources.

EXAMPLES:
  - Database connection pool (one pool, shared)
  - Logger (all code logs to same file)
  - Configuration manager (one config object loaded once)
  - Thread pool (one pool of threads, reused)
  - Sequence generator (URL shortener counter — ONE counter globally)

WHY NOT GLOBAL VARIABLE?
  Global variable: no encapsulation, no lazy initialization, no thread safety.
  Singleton: encapsulates the single instance, controls creation, thread-safe.
```

### Java — Singleton (Double-Checked Locking)

```java
// ── Singleton: Database Connection Pool ──────────────────────────────────────

public final class ConnectionPool {
    //  ↑ final class: cannot be extended (subclassing a singleton breaks the pattern).
    //    Why? If you subclass: new SubConnectionPool() and new ConnectionPool() → 2 instances!

    // THE ONE INSTANCE (static = belongs to the class, not to any object):
    private static volatile ConnectionPool instance = null;
    //  ↑ static: shared across ALL instances. There is ONLY one copy of 'instance'.
    //    Lives in the class (method area), not in any object's heap space.
    //  ↑ volatile: CRITICAL for multi-threading.
    //    Ensures every thread reads this variable from MAIN MEMORY, not CPU cache.
    //    Without volatile: Thread A creates instance → writes to its CPU cache.
    //    Thread B checks instance: reads its own cache → sees null → creates ANOTHER instance!
    //    With volatile: write to instance → immediately visible to ALL threads.
    //  ↑ = null: starts as null (not yet created). Lazy initialization.
    //    Only created when first getInstance() is called. Not at class loading.

    private final List<Connection> connections;
    //  ↑ final: the list reference never changes (the list itself can be modified).
    //    (This is the connection pool — a list of reusable DB connections.)

    private final int poolSize;

    // PRIVATE CONSTRUCTOR: prevents anyone from doing "new ConnectionPool()":
    private ConnectionPool(int poolSize) {
        //  ↑ private constructor: key to Singleton!
        //    No external class can call "new ConnectionPool()" → compile error.
        //    ONLY this class's getInstance() can call the constructor.
        this.poolSize   = poolSize;
        this.connections = new ArrayList<>(poolSize);
        for (int i = 0; i < poolSize; i++) {
            connections.add(new Connection("jdbc:mysql://localhost/mydb"));
            //  ↑ Create poolSize connections at startup. Reuse them for all DB calls.
            //    Creating a DB connection is expensive (3-way TCP handshake, auth).
            //    Connection pool: create once, reuse many times.
        }
        System.out.println("ConnectionPool created with " + poolSize + " connections");
    }

    // THE ONLY WAY TO GET THE INSTANCE:
    public static ConnectionPool getInstance() {
        //  ↑ static method: called on the CLASS, not on an instance.
        //    ConnectionPool.getInstance() — note: no object before the dot.
        //    This IS the global access point.

        if (instance == null) {
            //  ↑ FIRST CHECK (no lock): 99% of calls come here and skip the sync block.
            //    If instance already exists: return immediately. Fast path.
            //    Avoids acquiring lock on every call (locking is expensive).

            synchronized (ConnectionPool.class) {
                //  ↑ synchronized: acquires a LOCK on ConnectionPool.class object.
                //    ConnectionPool.class = the Class object representing ConnectionPool.
                //    Only ONE thread at a time can enter this block.
                //    Other threads WAIT (block) until the lock is released.
                //
                //    WHY NOT synchronize the whole method?
                //    synchronized method locks on 'this' (or class for static).
                //    Every getInstance() call would need the lock → slow.
                //    DOUBLE-CHECKED LOCKING: lock only when instance might be null.

                if (instance == null) {
                    //  ↑ SECOND CHECK (inside lock): needed because between the first check
                    //    and acquiring the lock, another thread might have created the instance.
                    //    Thread A: first check → null → waiting for lock.
                    //    Thread B: first check → null → acquires lock → creates instance → releases lock.
                    //    Thread A: acquires lock → WITHOUT second check: creates ANOTHER instance! BUG!
                    //    WITH second check: Thread A sees instance != null → skips creation. Correct!
                    instance = new ConnectionPool(10);
                    //  ↑ Instance created ONCE and ONLY ONCE. Thread-safe.
                }
            }
        }
        return instance;
    }

    public synchronized Connection acquire() {
        //  ↑ synchronized method: locks on 'this' (the ConnectionPool object).
        //    Only one thread can call acquire() at a time.
        //    Prevents two threads from getting the SAME connection.
        if (connections.isEmpty()) {
            throw new RuntimeException("No connections available — pool exhausted");
        }
        return connections.remove(connections.size() - 1);
        //  ↑ remove(last index): take last connection and remove from list. O(1).
        //    Removing from end is O(1) for ArrayList. Removing from front is O(n).
    }

    public synchronized void release(Connection connection) {
        //  ↑ synchronized: prevent race condition where two threads release simultaneously.
        connections.add(connection);
        //  ↑ Return connection to pool. Now available for next acquire().
        System.out.println("Connection returned. Pool size: " + connections.size());
    }
}

// USAGE:
// ConnectionPool pool = ConnectionPool.getInstance();   // First call: creates
// ConnectionPool pool2 = ConnectionPool.getInstance();  // Returns same instance
// System.out.println(pool == pool2);  // true: same object reference
// Connection conn = pool.acquire();
// // ... use connection ...
// pool.release(conn);
```

### C++ — Singleton (Meyers Singleton)

```cpp
// ── C++ Singleton: Scott Meyers' elegant approach ─────────────────────────────
// Meyers Singleton: uses function-local static.
// C++11 guarantee: initialization of local static is THREAD-SAFE.
// No need for locks or volatile!

class ConnectionPool {
public:
    // DELETE copy constructor and assignment operator:
    ConnectionPool(const ConnectionPool&) = delete;
    //  ↑ = delete: explicitly DISABLES this function.
    //    Without this: compiler auto-generates a copy constructor.
    //    Someone could do: ConnectionPool copy = *pool; → second instance! Bug!
    //    With = delete: ConnectionPool copy = *pool; → COMPILE ERROR. Safe.

    ConnectionPool& operator=(const ConnectionPool&) = delete;
    //  ↑ Disable copy assignment too.
    //    Without this: ConnectionPool a = ...; ConnectionPool b; b = a; → copy. Bug!

    // THE ACCESS POINT:
    static ConnectionPool& getInstance() {
        //  ↑ Returns REFERENCE to the single instance.
        //    Reference (not pointer) = cannot be null. Cannot be deleted by caller.

        static ConnectionPool instance(10);
        //  ↑ LOCAL STATIC VARIABLE.
        //    Key C++11 guarantee: if two threads call getInstance() simultaneously,
        //    ONLY ONE of them initializes 'instance'. Other waits. Thread-safe.
        //    (This is why Meyers Singleton is preferred over DCLP in C++.)
        //    'static': persists for the lifetime of the program (not destroyed at end of function).
        //    Created the FIRST time this function is called (lazy initialization).

        return instance;
        //  ↑ Return reference to the static local object.
    }

    Connection acquire() {
        std::unique_lock<std::mutex> lock(mutex_);
        //  ↑ unique_lock: RAII lock. Acquires mutex_ in constructor.
        //    Released automatically when 'lock' goes out of scope (end of function).
        //    std::mutex: mutual exclusion object. Only one thread holds it at a time.
        if (connections_.empty()) {
            throw std::runtime_error("Connection pool exhausted");
            //  ↑ std::runtime_error: C++ standard exception for runtime errors.
            //    throw: sends exception up the call stack.
        }
        Connection conn = connections_.back();
        //  ↑ .back(): reference to last element. O(1).
        connections_.pop_back();
        //  ↑ pop_back(): remove last element. O(1).
        return conn;
    }

    void release(Connection conn) {
        std::unique_lock<std::mutex> lock(mutex_);
        connections_.push_back(std::move(conn));
        //  ↑ push_back + move: add to end of vector without copying.
    }

private:
    explicit ConnectionPool(int poolSize) {
        //  ↑ private constructor: only getInstance() can call this.
        connections_.reserve(poolSize);
        //  ↑ reserve: pre-allocate capacity for poolSize elements.
        //    Avoids repeated memory reallocation as we push_back.
        for (int i = 0; i < poolSize; ++i) {
            connections_.emplace_back("jdbc:mysql://localhost/mydb");
            //  ↑ emplace_back: construct Connection IN PLACE at end of vector.
            //    More efficient than push_back (no temporary object created).
            //  ↑ ++i: pre-increment. Preferred over i++ for iterators/objects.
            //    (For int it's the same speed. Good habit for all types.)
        }
    }

    std::vector<Connection> connections_;
    std::mutex mutex_;
    //  ↑ mutex_: mutual exclusion. Protects connections_ from concurrent access.
    //    mutable could be added if we need to lock in const methods.
};

// USAGE:
// ConnectionPool& pool = ConnectionPool::getInstance();  // First call: creates
// ConnectionPool& pool2 = ConnectionPool::getInstance(); // Returns same instance
// Connection conn = pool.acquire();
// pool.release(std::move(conn));
```

---

## PATTERN 2: FACTORY METHOD

```
PROBLEM: You need to create objects, but you don't know the exact type at compile time.
         The type is determined at runtime (based on config, user input, DB value).

WITHOUT FACTORY:
  if (type == "mysql")   return new MySQLDB();
  if (type == "mongo")   return new MongoDB();
  if (type == "redis")   return new RedisDB();
  → Every caller has this if/else block. Duplicate. Violates OCP.

WITH FACTORY:
  One place creates objects. All callers call factory.create(type).
  Add new type: update factory only. Callers unchanged.

REAL EXAMPLES:
  - Database drivers (JDBC: Class.forName("com.mysql.jdbc.Driver") → factory)
  - UI frameworks (ButtonFactory.create("mac") → MacButton or WinButton)
  - Payment gateway (PaymentProcessorFactory.create("card") → CardProcessor)
```

### Java — Factory Method

```java
// ── Notification Factory ────────────────────────────────────────────────────────

// Step 1: Product interface
interface Notification {
    void send(String recipient, String message);
    String getChannelName();
}

// Step 2: Concrete products
class EmailNotification implements Notification {
    @Override
    public void send(String recipient, String message) {
        System.out.printf("📧 Email → %s: %s%n", recipient, message);
    }

    @Override
    public String getChannelName() { return "EMAIL"; }
}

class SMSNotification implements Notification {
    @Override
    public void send(String recipient, String message) {
        System.out.printf("📱 SMS → %s: %s%n", recipient, message);
    }

    @Override
    public String getChannelName() { return "SMS"; }
}

class PushNotification implements Notification {
    @Override
    public void send(String recipient, String message) {
        System.out.printf("🔔 Push → %s: %s%n", recipient, message);
    }

    @Override
    public String getChannelName() { return "PUSH"; }
}

// Step 3: Factory (creator)
class NotificationFactory {
    //  ↑ One class responsible for ALL object creation decisions.
    //    Add new notification type: update THIS class only.
    //    All callers of create() are unaffected.

    public static Notification create(String channel) {
        //  ↑ static factory method: called as NotificationFactory.create("email")
        //    No need to create a factory object. Clean call syntax.

        return switch (channel.toUpperCase()) {
            //  ↑ switch expression (Java 14+): returns a value directly.
            //  ↑ .toUpperCase(): normalize input (case-insensitive matching).
            //    "email", "EMAIL", "Email" → all become "EMAIL".

            case "EMAIL" -> new EmailNotification();
            //  ↑ Arrow case (Java 14+): cleaner than case + break.
            //    If channel is "EMAIL": return new EmailNotification(). No fall-through.

            case "SMS"   -> new SMSNotification();
            case "PUSH"  -> new PushNotification();

            default -> throw new IllegalArgumentException(
                "Unknown notification channel: " + channel
            );
            //  ↑ default: catch-all for unexpected values.
            //    Fail fast: throw immediately rather than silently returning null.
        };
    }
}

// ABSTRACT FACTORY (factory of factories):
interface NotificationSender {
    Notification createEmailNotification();
    Notification createSMSNotification();
    // Returns related family of objects (all for one country/region).
}

class IndiaNotificationSender implements NotificationSender {
    @Override
    public Notification createEmailNotification() {
        return new EmailNotification(); // Indian email server config
    }
    @Override
    public Notification createSMSNotification() {
        return new SMSNotification(); // Indian SMS provider (Twilio India)
    }
}

// USAGE:
// Notification n = NotificationFactory.create("email");
// n.send("sachin@gmail.com", "Your order shipped!");
//
// Adding WhatsApp:
// 1. Create WhatsAppNotification implements Notification.
// 2. Add case "WHATSAPP" -> new WhatsAppNotification() in factory.
// 3. Done. Zero changes to callers.
```

### C++ — Factory

```cpp
// ── C++ Factory ────────────────────────────────────────────────────────────────
#pragma once
#include <memory>
#include <string>
#include <stdexcept>
#include <functional>
#include <unordered_map>

class Notification {
public:
    virtual ~Notification() = default;
    virtual void send(const std::string& recipient, const std::string& message) const = 0;
    virtual std::string channelName() const = 0;
};

class EmailNotification : public Notification {
public:
    void send(const std::string& r, const std::string& m) const override {
        printf("📧 Email → %s: %s\n", r.c_str(), m.c_str());
    }
    std::string channelName() const override { return "EMAIL"; }
};

class SMSNotification : public Notification {
public:
    void send(const std::string& r, const std::string& m) const override {
        printf("📱 SMS → %s: %s\n", r.c_str(), m.c_str());
    }
    std::string channelName() const override { return "SMS"; }
};

// FACTORY using registration map (extensible without modifying factory code):
class NotificationFactory {
public:
    using Creator = std::function<std::unique_ptr<Notification>()>;
    //  ↑ using: type alias. Creator = a function that takes nothing and returns a unique_ptr<Notification>.
    //  ↑ std::function<ReturnType(Params)>: wrapper for any callable (lambda, function pointer, etc.)

    static NotificationFactory& getInstance() {
        static NotificationFactory factory;
        return factory;
    }

    void registerChannel(const std::string& name, Creator creator) {
        creators_[name] = std::move(creator);
        //  ↑ Register: add channel name → creator function mapping.
        //    New channel: call registerChannel("whatsapp", []{ return make_unique<WhatsAppNotification>(); });
        //    Factory code doesn't change. Open/Closed Principle satisfied.
    }

    std::unique_ptr<Notification> create(const std::string& channel) const {
        auto it = creators_.find(channel);
        //  ↑ find(): O(1) hash lookup. Returns iterator.
        if (it == creators_.end()) {
            throw std::invalid_argument("Unknown channel: " + channel);
        }
        return it->second();
        //  ↑ it->second: the Creator function. () calls it → returns unique_ptr<Notification>.
    }

private:
    std::unordered_map<std::string, Creator> creators_;
    //  ↑ Maps channel name → factory function. Registration-based approach.
};

// REGISTRATION AT STARTUP:
// NotificationFactory::getInstance().registerChannel("email",
//     []{ return std::make_unique<EmailNotification>(); });
// NotificationFactory::getInstance().registerChannel("sms",
//     []{ return std::make_unique<SMSNotification>(); });
//
// USAGE:
// auto notif = NotificationFactory::getInstance().create("email");
// notif->send("sachin@gmail.com", "Hello!");
```

---

## PATTERN 3: BUILDER

```
PROBLEM: An object has many optional fields. Constructor becomes messy.
         "Telescoping constructor" anti-pattern:
         
  new User(name, email)
  new User(name, email, phone)
  new User(name, email, phone, address)
  new User(name, email, phone, address, age, gender, ...)  ← confusing!
  
  What does this mean? User("Sachin", null, null, "Delhi", 25, null)
  → Hard to read. Easy to make mistakes (wrong argument order).

BUILDER PATTERN:
  User user = new User.Builder("Sachin", "sachin@gmail.com")
                      .withPhone("+91-9876543210")
                      .withAge(28)
                      .withCity("Mumbai")
                      .build();   ← readable. Each field is named. Order doesn't matter.
```

### Java — Builder

```java
// ── Builder Pattern: HTTP Request ───────────────────────────────────────────────

import java.util.HashMap;
import java.util.Map;

public class HttpRequest {
    //  ↑ Immutable object built by Builder. All fields final.

    private final String url;          // REQUIRED
    private final String method;       // REQUIRED: "GET", "POST", "PUT", "DELETE"
    private final Map<String, String> headers;  // OPTIONAL
    private final String body;         // OPTIONAL (null for GET requests)
    private final int timeoutMs;       // OPTIONAL, default 30000
    private final boolean followRedirects; // OPTIONAL, default true
    private final int retryCount;      // OPTIONAL, default 3

    // PRIVATE CONSTRUCTOR: only Builder can call this
    private HttpRequest(Builder builder) {
        //  ↑ Takes the Builder object as parameter. Copies all Builder fields.
        this.url              = builder.url;
        this.method           = builder.method;
        this.headers          = new HashMap<>(builder.headers);  // Defensive copy
        this.body             = builder.body;
        this.timeoutMs        = builder.timeoutMs;
        this.followRedirects  = builder.followRedirects;
        this.retryCount       = builder.retryCount;
    }

    // Getters only (no setters → immutable after build):
    public String getUrl()    { return url; }
    public String getMethod() { return method; }
    public String getBody()   { return body; }
    public Map<String, String> getHeaders() { return new HashMap<>(headers); } // Defensive copy
    public int getTimeoutMs() { return timeoutMs; }

    // STATIC NESTED BUILDER CLASS:
    public static class Builder {
        //  ↑ static nested class: doesn't need an outer class instance to be created.
        //    Non-static nested class (inner class) would need an instance.
        //    Builder doesn't need HttpRequest — it's creating one.

        // REQUIRED fields:
        private final String url;    // final in Builder = set in Builder constructor, never changed
        private final String method;

        // OPTIONAL fields with defaults:
        private Map<String, String> headers = new HashMap<>();
        //  ↑ Default: empty map. Add headers optionally.
        private String body          = null;      // Default: no body
        private int    timeoutMs     = 30_000;    // Default: 30 seconds (30,000 ms)
        //  ↑ 30_000: Java allows underscores in numeric literals for readability.
        //    30_000 == 30000. Just visual grouping (like comma in 30,000).
        private boolean followRedirects = true;   // Default: follow redirects
        private int     retryCount      = 3;      // Default: retry 3 times

        // Builder constructor — REQUIRED fields go here:
        public Builder(String url, String method) {
            if (url == null || url.isEmpty())
                throw new IllegalArgumentException("URL is required");
            if (!method.matches("GET|POST|PUT|DELETE|PATCH"))
                throw new IllegalArgumentException("Invalid HTTP method: " + method);
            //  ↑ .matches(regex): checks if string matches a regular expression.
            //    "GET|POST|...": | means OR in regex. Matches any of these methods.
            this.url    = url;
            this.method = method;
        }

        // OPTIONAL field setters — return Builder (for method chaining):
        public Builder withHeader(String name, String value) {
            this.headers.put(name, value);
            return this;
            //  ↑ return this: returns the SAME Builder object.
            //    Enables method chaining: builder.withHeader("A","1").withHeader("B","2").build()
            //    Each method returns the builder → next method can be called on it immediately.
        }

        public Builder withBody(String body) {
            this.body = body;
            return this;
        }

        public Builder withTimeoutMs(int ms) {
            if (ms <= 0) throw new IllegalArgumentException("Timeout must be positive");
            this.timeoutMs = ms;
            return this;
        }

        public Builder withFollowRedirects(boolean follow) {
            this.followRedirects = follow;
            return this;
        }

        public Builder withRetryCount(int count) {
            if (count < 0) throw new IllegalArgumentException("Retry count cannot be negative");
            this.retryCount = count;
            return this;
        }

        // BUILD: validate everything, then create the immutable object:
        public HttpRequest build() {
            // Final validation before creating:
            if (method.equals("POST") || method.equals("PUT")) {
                if (body == null || body.isEmpty()) {
                    System.out.println("Warning: POST/PUT request has no body");
                }
            }
            return new HttpRequest(this);
            //  ↑ Call the private HttpRequest constructor with 'this' (the Builder).
            //    Creates an IMMUTABLE HttpRequest. Cannot be modified after this.
        }
    }
}

// USAGE: clean, readable, self-documenting:
// HttpRequest request = new HttpRequest.Builder("https://api.example.com/orders", "POST")
//     .withHeader("Authorization", "Bearer " + token)
//     .withHeader("Content-Type", "application/json")
//     .withBody("{\"amount\": 999.00, \"currency\": \"INR\"}")
//     .withTimeoutMs(5_000)
//     .withRetryCount(2)
//     .build();
```

### C++ — Builder

```cpp
// ── C++ Builder with method chaining ──────────────────────────────────────────
#pragma once
#include <string>
#include <map>
#include <stdexcept>

class HttpRequest {
public:
    struct Builder {
        //  ↑ struct: same as class in C++ but defaults to public access.
        //    Good for builders/configs where everything should be accessible.

        // Required fields:
        std::string url;
        std::string method;

        // Optional fields with defaults:
        std::map<std::string, std::string> headers;
        std::string body;
        int  timeoutMs       = 30'000;   // C++14: digit separator (30'000 == 30000)
        bool followRedirects = true;
        int  retryCount      = 3;

        // Builder constructor:
        Builder(std::string url, std::string method)
            : url(std::move(url)), method(std::move(method)) {}

        // Method chaining: return *this (reference to Builder):
        Builder& withHeader(std::string name, std::string value) {
            headers[std::move(name)] = std::move(value);
            return *this;
            //  ↑ return *this: dereference 'this' pointer → returns reference to Builder.
            //    Enables: builder.withHeader("A","1").withHeader("B","2").build();
        }

        Builder& withBody(std::string b) {
            body = std::move(b);
            return *this;
        }

        Builder& withTimeoutMs(int ms) {
            if (ms <= 0) throw std::invalid_argument("Timeout must be positive");
            timeoutMs = ms;
            return *this;
        }

        // BUILD: create immutable HttpRequest:
        HttpRequest build() {
            if (url.empty()) throw std::invalid_argument("URL required");
            return HttpRequest(std::move(*this));
            //  ↑ std::move(*this): move the Builder's data into HttpRequest.
            //    After this: builder is in valid-but-empty state.
            //    The Builder's strings/maps are transferred to HttpRequest (no copy).
        }
    };

    // Getters:
    const std::string& getUrl()    const { return url_; }
    const std::string& getMethod() const { return method_; }
    const std::string& getBody()   const { return body_; }

private:
    explicit HttpRequest(Builder&& b)   // Takes rvalue reference to Builder
        : url_(std::move(b.url)),       // Move each field from builder
          method_(std::move(b.method)),
          headers_(std::move(b.headers)),
          body_(std::move(b.body)),
          timeoutMs_(b.timeoutMs),
          followRedirects_(b.followRedirects),
          retryCount_(b.retryCount) {}
    //  ↑ &&: rvalue reference. Only accepts temporaries or moved objects.
    //    Ensures Builder is consumed during construction (one-time use).

    std::string url_, method_, body_;
    std::map<std::string, std::string> headers_;
    int  timeoutMs_       = 30'000;
    bool followRedirects_ = true;
    int  retryCount_      = 3;
};

// USAGE:
// HttpRequest req = HttpRequest::Builder("https://api.example.com/orders", "POST")
//     .withHeader("Authorization", "Bearer token123")
//     .withBody("{\"amount\": 999}")
//     .withTimeoutMs(5'000)
//     .build();
```

---

## PATTERN 4: PROTOTYPE

```
PROBLEM: Creating an object is expensive (DB call, file read, complex initialization).
         You need MANY similar objects. Instead of creating each from scratch:
         CLONE an existing "prototype" object and customize it.

EXAMPLE:
  Game: NPC (non-player character). Creating an Orc: load 3D model, load textures, set stats. Slow.
  If you need 1000 Orcs: clone the prototype Orc, change only position/name.
  
  Document editor: "Paste" = clone clipboard object.
  
  Config template: clone a base configuration, override specific fields.
```

### Java — Prototype

```java
// ── Prototype: Game Enemy ────────────────────────────────────────────────────

// STEP 1: Cloneable interface (Java built-in marker interface):
public abstract class Enemy implements Cloneable {
    //  ↑ Cloneable: Java marker interface. Has no methods.
    //    Marks the class as "OK to clone with Object.clone()".
    //    Without Cloneable: clone() throws CloneNotSupportedException.

    protected String name;
    protected int hp;          // Health points
    protected int damage;      // Attack damage
    protected String faction;  // Which team/side this enemy is on
    protected int x, y;        // Position in game world

    public Enemy(String name, int hp, int damage, String faction) {
        this.name    = name;
        this.hp      = hp;
        this.damage  = damage;
        this.faction = faction;
    }

    // CLONE method: shallow copy of this object:
    @Override
    public Enemy clone() {
        //  ↑ @Override: overriding Object.clone() which is inherited by all Java objects.
        try {
            return (Enemy) super.clone();
            //  ↑ super.clone(): Java's built-in bitwise copy of this object.
            //    Creates a new object with same field values as this one.
            //  ↑ (Enemy): cast the returned Object to Enemy.
            //    super.clone() returns Object (generic type) — cast needed.
            //
            //    SHALLOW COPY: primitive fields (int, boolean) are copied by value.
            //    Reference fields (String, List): the REFERENCE is copied (points to same object).
            //    For String: OK (Strings are immutable in Java).
            //    For mutable collections (List): DEEP COPY needed if you modify the clone's list.
        } catch (CloneNotSupportedException e) {
            throw new RuntimeException("Clone failed", e);
            //  ↑ Should never happen since we implement Cloneable.
            //    Wrap in RuntimeException to avoid checked exception propagation.
        }
    }

    // Spawn at a specific position:
    public Enemy spawnAt(int x, int y) {
        Enemy copy = this.clone();   // Clone the prototype
        copy.x = x;                  // Override position
        copy.y = y;
        copy.hp = this.hp;           // Full health (fresh spawn)
        System.out.printf("Spawned %s at (%d, %d)%n", copy.name, x, y);
        return copy;
    }

    public abstract void attack();   // Each enemy attacks differently
}

class Orc extends Enemy {
    private String weapon;  // Orcs use specific weapons

    public Orc(String name, int hp, int damage, String weapon) {
        super(name, hp, damage, "HordeFaction");
        //  ↑ super(...): calls Enemy's constructor with the given faction.
        this.weapon = weapon;
    }

    @Override
    public void attack() {
        System.out.printf("%s attacks with %s for %d damage!%n", name, weapon, damage);
    }
}

// PROTOTYPE REGISTRY: store prototypes by name:
class EnemyRegistry {
    private final Map<String, Enemy> prototypes = new HashMap<>();
    //  ↑ HashMap: stores prototypes. Key = enemy type name, Value = prototype instance.

    public void register(String name, Enemy prototype) {
        prototypes.put(name, prototype);
        System.out.println("Registered prototype: " + name);
    }

    public Enemy spawn(String name, int x, int y) {
        Enemy prototype = prototypes.get(name);
        //  ↑ Get the prototype by name.
        if (prototype == null) throw new IllegalArgumentException("Unknown enemy: " + name);
        return prototype.spawnAt(x, y);   // Clone and position
    }
}

// USAGE:
// EnemyRegistry registry = new EnemyRegistry();
//
// // Create prototype ONCE (expensive):
// Orc orcPrototype = new Orc("Orc Warrior", 200, 35, "Axe");
// registry.register("orc", orcPrototype);
//
// // Clone many times (cheap):
// Enemy orc1 = registry.spawn("orc", 100, 200);
// Enemy orc2 = registry.spawn("orc", 150, 300);
// Enemy orc3 = registry.spawn("orc", 200, 100);
// // All three are independent Orc objects at different positions.
// // Created by cloning the prototype — no expensive re-initialization.
```

---

## Pattern Summary

```
SINGLETON: One instance globally. 
  Java: private constructor + static volatile instance + synchronized DCL.
  C++:  Meyers Singleton (static local variable, thread-safe in C++11).
  When: DB pool, logger, config, sequence generator.

FACTORY METHOD: Decouple object creation from usage.
  Java: static factory method or Factory class.
  C++:  Registration map (extensible without changing factory code).
  When: DB drivers, UI components, payment processors, notification channels.

BUILDER: Readable construction of complex objects.
  Java: static nested Builder class, withX() returns Builder for chaining.
  C++:  struct Builder with method chaining (return *this).
  When: HTTP requests, DB queries, user profiles, configurations with many optional fields.

PROTOTYPE: Clone expensive objects.
  Java: implements Cloneable, override clone().
  C++:  virtual clone() method returning raw/unique_ptr copy.
  When: Game objects, document templates, configuration templates.

MAANG INTERVIEW TIP:
  If interviewer says "Create N similar objects efficiently" → PROTOTYPE.
  If they say "How do you handle new types without changing existing code?" → FACTORY + OCP.
  If they say "How do you create objects with many optional fields?" → BUILDER.
  If they say "One global configuration/pool" → SINGLETON.
```

---

## HOW CREATIONAL PATTERNS APPEAR IN THE LLD CASE STUDIES

### SINGLETON — Where it appears

```
CS01 URL Shortener:
  SequenceGenerator (the global counter for generating short codes).
  ONE counter globally. Multiple instances = duplicate short codes = broken system.
  Java: private static volatile + synchronized DCL.
  C++: Meyers Singleton (static local variable).

CS06 YouTube:
  VideoIndexService (global search index). One shared inverted index.
  Creating multiple instances = inconsistent search results.

CS07 Google Search:
  PageRankEngine (one instance computes scores for all docs).
  InvertedIndex (one global index — cannot have two different indexes).

CS09 Payment Gateway:
  IdempotencyStore (one global store to prevent duplicate payments).
  FraudDetectionEngine (one ML model instance, shared across requests).

JAVA WARNING: Even with Singleton, if the "single" instance holds mutable state
  (like a counter or map), all mutations must be synchronized or atomic.
  Singleton + thread-safety go together in production.
```

### FACTORY METHOD — Where it appears

```
CS04 Uber:
  FareStrategyFactory.create(pricing_type) → returns SurgePricingStrategy, NormalPricingStrategy, etc.
  UberService calls factory.create(request.type). Doesn't know which concrete class is returned.
  Adding new pricing type: update factory. UberService code unchanged.

CS05 Netflix:
  ContentFactory.create(content_type) → Episode or Series.
  Catalog builder calls factory. Doesn't need to know about Episode vs Series construction.

CS09 Payment Gateway:
  PaymentProcessorFactory.create("card") → CardProcessor.
  PaymentProcessorFactory.create("upi")  → UPIProcessor.
  PaymentGatewayService calls factory. Doesn't know concrete processor classes.

CS11 AI Systems:
  LLMAdapterFactory.create("gpt-4") → OpenAIAdapter.
  LLMAdapterFactory.create("claude") → AnthropicAdapter.
  Single registration map. New model: register one entry. Zero other changes.

C++ specific: registration map (std::unordered_map<string, Creator>) allows
  plugins to register themselves without changing the factory class.
  Open for extension, closed for modification.
```

### BUILDER — Where it appears

```
CS01 URL Shortener:
  UrlEntry.Builder: .withCustomCode("mylink").withExpiry(30_days).withMaxClicks(1000).build()
  Many optional fields. Builder prevents telescoping constructor mess.

CS04 Uber:
  TripRequest.Builder: .from(pickup).to(dropoff).vehicleType("auto").scheduledFor(time).build()
  Complex trip request object with many optional fields.

CS09 Payment Gateway:
  PaymentRequest.Builder:
    .amount(BigDecimal("999.00"))
    .currency("INR")
    .cardNumber("4111...")
    .idempotencyKey(UUID)
    .withMetadata("order_id", "ORD123")
    .build()
  Required: amount, currency, idempotencyKey.
  Optional: metadata, 3DS preferences, merchant category.

CS10 MakeMyTrip:
  FlightSearchQuery.Builder:
    .from("DEL").to("BOM").date(LocalDate.now().plusDays(7))
    .passengers(2).cabinClass("ECONOMY").flexDates(true).build()
  Many optional search parameters. Builder ensures readable construction.

JAVA: static nested Builder class with withX() methods returning Builder for chaining.
C++: struct Builder with method chaining (return *this). Use std::move in build().
```

### PROTOTYPE — Where it appears

```
CS04 Uber:
  Driver profiles are cloned when creating surge zones.
  DriverPrototype cloned and position/zone overridden → faster than re-fetching from DB.

CS05 Netflix:
  Default streaming configuration is a prototype.
  Cloned per user session, then overridden with user preferences (resolution, subtitle lang).

CS10 MakeMyTrip:
  "Search result template" is a prototype.
  Cloned per flight result, then specific price/seats/timing filled in.
  Avoids re-constructing complex FlightResult objects from scratch for each search hit.

CS11 AI Systems:
  PromptTemplate is a prototype.
  Cloned per request, then user message + context injected into placeholders.
  System prompt (expensive to construct) reused across requests via cloning.
```

# LLD Topic 02: SOLID Principles
## Java + C++ Primary | Every Keyword Explained | Line by Line

---

> **WHY SOLID?**
> SOLID = 5 design principles that make code easy to extend, test, and maintain.
> MAANG interviewers directly ask: "Does your design follow SOLID?"
> Even if they don't ask directly, they CHECK by asking:
> "What if the requirements change?" — SOLID code handles change gracefully.
>
> **Coined by:** Robert C. Martin (Uncle Bob). Used in every serious software team.

---

## S — Single Responsibility Principle (SRP)

```
RULE: A class should have ONE and ONLY ONE reason to change.

VIOLATION EXAMPLE:
  class Invoice {
    void calculateTotal() { ... }   // Reason 1: business logic changes
    void printInvoice()   { ... }   // Reason 2: output format changes
    void saveToDatabase() { ... }   // Reason 3: DB schema changes
  }
  → 3 reasons to change = 3 responsibilities → violates SRP.

FIX: Split into 3 classes, each with one reason to change.
```

### Java — SRP

```java
// ── VIOLATION: One class doing too much ───────────────────────────────────────
class BadInvoice {
    private double amount;

    void calculateTotal() { /* business logic */ }    // Responsibility 1
    void printToConsole()  { /* formatting */   }     // Responsibility 2
    void saveToMySQL()     { /* DB operation */ }     // Responsibility 3
    // Problem: change MySQL to MongoDB → must modify BadInvoice → violates SRP
}

// ── FIX: Three separate classes, one responsibility each ─────────────────────

// Class 1: ONLY handles invoice business logic
class Invoice {
    private final String customerId;
    //  ↑ final: this ID never changes after construction (immutable field).

    private final List<LineItem> lineItems;
    //  ↑ List<LineItem>: ordered list of items in this invoice.

    public Invoice(String customerId) {
        this.customerId = customerId;
        this.lineItems  = new ArrayList<>();
    }

    public void addItem(LineItem item) {
        lineItems.add(item);
    }

    public double calculateTotal() {
        return lineItems.stream()          // Create a stream from the list
                        .mapToDouble(LineItem::getSubtotal)   // Each item → its subtotal
                        .sum();            // Add them all up
        //  ↑ This is the ONLY business logic responsibility.
    }

    // Getters:
    public String getCustomerId() { return customerId; }
    public List<LineItem> getLineItems() { return Collections.unmodifiableList(lineItems); }
    //  ↑ unmodifiableList: returns a view of the list that cannot be modified.
    //    Caller can READ items but cannot add/remove. Defensive programming.
}

// Class 2: ONLY handles display/printing
class InvoicePrinter {
    //  ↑ Single Responsibility: only knows HOW to display invoices.
    //    If output format changes (HTML, PDF, CSV) → modify only this class.
    //    Invoice class is UNTOUCHED.

    public void print(Invoice invoice) {
        System.out.println("=== INVOICE ===");
        System.out.println("Customer: " + invoice.getCustomerId());
        for (LineItem item : invoice.getLineItems()) {
            System.out.printf("  %-20s ₹%8.2f%n", item.getName(), item.getSubtotal());
            //  ↑ %-20s: left-aligned string in 20-char wide field.
            //  ↑ %8.2f: right-aligned float, 8 chars wide, 2 decimal places.
        }
        System.out.printf("TOTAL: ₹%.2f%n", invoice.calculateTotal());
    }
}

// Class 3: ONLY handles persistence (saving)
class InvoiceRepository {
    //  ↑ "Repository" pattern: class dedicated to DB operations for ONE entity type.
    //    Reason to change: if DB changes (MySQL → MongoDB → Cassandra).
    //    Invoice class is UNTOUCHED.

    public void save(Invoice invoice) {
        // In real code: SQL INSERT or Hibernate/JPA save
        System.out.println("Saving invoice for " + invoice.getCustomerId() + " to DB");
    }

    public Invoice findById(String invoiceId) {
        // In real code: SQL SELECT
        return null; // Placeholder
    }
}

// HOW TO USE:
class InvoiceService {
    private final InvoicePrinter printer;
    private final InvoiceRepository repository;
    //  ↑ Inject dependencies (Dependency Injection). Not created internally.
    //    Makes this class testable: inject mock objects in unit tests.

    public InvoiceService(InvoicePrinter printer, InvoiceRepository repository) {
        this.printer    = printer;
        this.repository = repository;
    }

    public void processInvoice(Invoice invoice) {
        printer.print(invoice);        // Display responsibility → InvoicePrinter
        repository.save(invoice);     // Persistence responsibility → InvoiceRepository
        // InvoiceService: orchestrates the flow. Its own responsibility.
    }
}
```

### C++ — SRP

```cpp
// ── C++ SRP: same idea, different syntax ──────────────────────────────────────
#pragma once
#include <string>
#include <vector>
#include <numeric>   // std::accumulate
#include <iostream>
#include <iomanip>   // std::setw, std::left, std::fixed

struct LineItem {
    std::string name;
    double quantity;
    double unitPrice;

    double subtotal() const { return quantity * unitPrice; }
    //  ↑ const method: only reads data, doesn't modify.
};

// Class 1: Business logic only
class Invoice {
public:
    explicit Invoice(std::string customerId)
        : customerId_(std::move(customerId)) {}
        //  ↑ std::move: transfer ownership of string → avoids copy.

    void addItem(LineItem item) {
        items_.push_back(std::move(item));
        //  ↑ push_back: append to end of vector.
        //  ↑ std::move(item): move item into vector → item's data transferred, not copied.
        //    After move: item is in a "valid but unspecified" state (don't use it).
    }

    double calculateTotal() const {
        return std::accumulate(items_.begin(), items_.end(), 0.0,
            [](double sum, const LineItem& li) { return sum + li.subtotal(); });
        //  ↑ std::accumulate: from <numeric>. Folds list into single value.
        //  ↑ Lambda []: closure. Captures nothing, takes (sum_so_far, next_item).
    }

    const std::string& customerId()         const { return customerId_; }
    const std::vector<LineItem>& lineItems() const { return items_; }
    //  ↑ const&: return read-only reference (no copy, no modification allowed).

private:
    std::string customerId_;
    std::vector<LineItem> items_;
};

// Class 2: Display only
class InvoicePrinter {
public:
    void print(const Invoice& invoice) const {
        //  ↑ const Invoice&: receive invoice as const reference.
        //    Won't copy (large objects → expensive). Won't modify (read-only).
        std::cout << "=== INVOICE ===\n";
        std::cout << "Customer: " << invoice.customerId() << "\n";
        for (const auto& item : invoice.lineItems()) {
            //  ↑ const auto&: const reference to each item. No copy. auto infers LineItem.
            std::cout << std::left << std::setw(20) << item.name
                      << " ₹" << std::fixed << std::setprecision(2) << item.subtotal() << "\n";
            //  ↑ std::left: left-align output.
            //  ↑ std::setw(20): next output field is 20 chars wide.
            //  ↑ std::fixed: show floats in fixed notation (not scientific).
            //  ↑ std::setprecision(2): 2 decimal places.
        }
        std::cout << "TOTAL: ₹" << std::fixed << std::setprecision(2)
                  << invoice.calculateTotal() << "\n";
    }
};

// Class 3: Storage only
class InvoiceRepository {
public:
    void save(const Invoice& invoice) {
        std::cout << "Saving invoice for " << invoice.customerId() << " to DB\n";
        // Real code: SQL INSERT or ORM call
    }
};
```

---

## O — Open/Closed Principle (OCP)

```
RULE: Classes should be OPEN for extension, CLOSED for modification.

MEANING:
  OPEN for extension:    you can add new behaviour (new classes, new strategy).
  CLOSED for modification: you don't change existing, working code to add new behaviour.

VIOLATION EXAMPLE:
  void processPayment(String type) {
    if (type.equals("card"))   { /* card logic */ }
    if (type.equals("upi"))    { /* UPI logic  */ }
    if (type.equals("wallet")) { /* wallet logic */}
    // Add new payment method → MUST modify this method (violates OCP).
  }

FIX: Use Strategy/Interface pattern. Add new class without touching existing code.
```

### Java — OCP

```java
// ── VIOLATION: Must modify existing method every time ─────────────────────────
class BadNotificationService {
    void send(String type, String message) {
        if (type.equals("email")) {
            System.out.println("Email: " + message);          // Hardcoded
        } else if (type.equals("sms")) {
            System.out.println("SMS: " + message);            // Hardcoded
        }
        // Add "push notification" → MUST modify this method → violates OCP.
    }
}

// ── FIX: Open for extension, closed for modification ──────────────────────────

// STEP 1: Define an interface (contract). This will NOT change.
interface NotificationChannel {
    void send(String recipient, String message);
    //  ↑ This interface is CLOSED for modification.
    //    Adding new channel: implement this interface. Don't touch it.
}

// STEP 2: Implement for each channel. Adding new channel = new class only.
class EmailChannel implements NotificationChannel {
    private final String smtpServer;

    EmailChannel(String smtpServer) { this.smtpServer = smtpServer; }

    @Override
    public void send(String recipient, String message) {
        System.out.printf("EMAIL via %s → %s: %s%n", smtpServer, recipient, message);
        // Real: JavaMail API call
    }
}

class SmsChannel implements NotificationChannel {
    private final String twilioSid;

    SmsChannel(String twilioSid) { this.twilioSid = twilioSid; }

    @Override
    public void send(String recipient, String message) {
        System.out.printf("SMS via Twilio → %s: %s%n", recipient, message);
    }
}

// Adding push notifications: NEW CLASS, ZERO changes to existing code!
class PushNotificationChannel implements NotificationChannel {
    @Override
    public void send(String recipient, String message) {
        System.out.printf("PUSH → %s: %s%n", recipient, message);
    }
}

// STEP 3: Service uses the interface. Does NOT change when new channel is added.
class NotificationService {
    private final List<NotificationChannel> channels;
    //  ↑ List of channels. Can hold Email, SMS, Push — anything implementing NotificationChannel.

    NotificationService(List<NotificationChannel> channels) {
        this.channels = new ArrayList<>(channels);
        //  ↑ new ArrayList<>(channels): creates a copy of the provided list.
        //    Defensive copy: our internal list is separate from caller's list.
    }

    void notify(String recipient, String message) {
        for (NotificationChannel channel : channels) {
            channel.send(recipient, message);
            //  ↑ POLYMORPHISM: correct send() called for each channel type.
            //    NotificationService.notify() NEVER changes, even as we add channels.
            //    Open for extension (add channel class). Closed for modification (this method unchanged).
        }
    }
}

// USAGE: Zero changes to NotificationService when adding new channel:
// List<NotificationChannel> channels = List.of(
//     new EmailChannel("smtp.gmail.com"),
//     new SmsChannel("twilio_sid"),
//     new PushNotificationChannel()    ← Added new channel. No existing code changed.
// );
// NotificationService svc = new NotificationService(channels);
// svc.notify("sachin@gmail.com", "Your order has shipped!");
```

---

## L — Liskov Substitution Principle (LSP)

```
RULE: A subclass MUST be substitutable for its parent class without breaking the program.

NAMED AFTER: Barbara Liskov (1987 Turing Award winner).

FORMAL: If S is a subtype of T, then objects of type T may be replaced with
        objects of type S without altering any desirable properties of the program.

SIMPLE VERSION:
  If your code works with a Vehicle, it should work with a Car (subclass of Vehicle)
  without knowing it's a Car. No surprises. No extra checks. No broken behaviour.

CLASSIC VIOLATION: Square extends Rectangle.
  Rectangle: setWidth(w) and setHeight(h) work independently.
  Square: width must always equal height. setWidth(5) must also set height to 5.
  If code does: rect.setWidth(4); rect.setHeight(6); area should be 24.
  But Square: setHeight(6) also sets width=6 → area=36. Surprise! Breaks LSP.
```

### Java — LSP

```java
// ── LSP VIOLATION: Square extends Rectangle ────────────────────────────────────

class Rectangle {
    protected int width;
    protected int height;

    public void setWidth(int w)  { this.width  = w; }
    public void setHeight(int h) { this.height = h; }
    public int area() { return width * height; }
}

class BadSquare extends Rectangle {
    @Override
    public void setWidth(int w) {
        this.width  = w;
        this.height = w;    // Side effect: also changes height!
        //  ↑ Rectangle.setWidth() only changes width. This changes BOTH.
        //    Violates the contract of Rectangle.setWidth(). → LSP VIOLATION.
    }

    @Override
    public void setHeight(int h) {
        this.width  = h;    // Side effect: also changes width!
        this.height = h;
    }
}

// This test FAILS with BadSquare even though BadSquare extends Rectangle:
static void testRectangle(Rectangle rect) {
    rect.setWidth(4);
    rect.setHeight(6);
    assert rect.area() == 24 : "Expected 24 but got " + rect.area();
    //  ↑ If we pass a BadSquare: setHeight(6) also sets width=6 → area=36 ≠ 24.
    //    Code that works for Rectangle BREAKS for Square → LSP violated.
}

// ── LSP FIX: Don't make Square extend Rectangle. Use a common interface. ───────

interface Shape {
    double area();
    double perimeter();
}

class FixedRectangle implements Shape {
    private final double width;    // final: immutable after construction
    private final double height;   // Immutable = no setter = no LSP problem!

    FixedRectangle(double w, double h) { width = w; height = h; }

    @Override public double area()      { return width * height; }
    @Override public double perimeter() { return 2 * (width + height); }
}

class FixedSquare implements Shape {
    private final double side;     // Square has one dimension: side length.

    FixedSquare(double side) { this.side = side; }

    @Override public double area()      { return side * side; }
    @Override public double perimeter() { return 4 * side; }
}

// Now both are substitutable for Shape. No surprises. LSP satisfied.
static void processShape(Shape s) {
    System.out.printf("Area=%.2f, Perimeter=%.2f%n", s.area(), s.perimeter());
    //  ↑ Works correctly for both FixedRectangle and FixedSquare.
    //    No unexpected side effects. Subtype is truly substitutable.
}
```

---

## I — Interface Segregation Principle (ISP)

```
RULE: Don't force a class to implement methods it doesn't need.
      Prefer many small, specific interfaces over one large, fat interface.

VIOLATION EXAMPLE:
  interface Worker {
    void work();
    void eat();
    void sleep();
  }
  
  class Robot implements Worker {
    void work()  { /* OK */ }
    void eat()   { throw new UnsupportedOperationException(); }  // Robots don't eat!
    void sleep() { throw new UnsupportedOperationException(); }  // Robots don't sleep!
  }
  → Robot forced to implement methods that make no sense for it. Violates ISP.
```

### Java — ISP

```java
// ── VIOLATION: Fat interface ────────────────────────────────────────────────────
interface BadWorker {
    void work();
    void eat();    // Not all workers eat (robots)
    void sleep();  // Not all workers sleep (robots)
    void code();   // Not all workers code (factory worker)
    void manage(); // Not all workers manage (intern)
}

// Robot forced to throw exceptions for methods that don't apply:
class Robot implements BadWorker {
    public void work()  { System.out.println("Working..."); }
    public void eat()   { throw new UnsupportedOperationException("Robots don't eat!"); }
    public void sleep() { throw new UnsupportedOperationException("Robots don't sleep!"); }
    public void code()  { throw new UnsupportedOperationException("Robots don't code!"); }
    public void manage(){ throw new UnsupportedOperationException("Robots don't manage!"); }
    // 4 out of 5 methods: useless. ISP violated.
}

// ── FIX: Segregate into small, focused interfaces ──────────────────────────────

interface Workable {
    void work();   // Only the work behaviour
}

interface Feedable {
    void eat();    // Only eating. Applies to humans, not robots.
}

interface Sleepable {
    void sleep();  // Only sleeping. Applies to humans, not robots.
}

interface Codeable {
    void code();   // Only coding. Applies to engineers.
}

// Now each class implements ONLY the interfaces relevant to it:

class HumanEngineer implements Workable, Feedable, Sleepable, Codeable {
    //  ↑ Implements FOUR interfaces. Java allows implementing multiple interfaces.
    //    (Unlike extends: can only extend one class.)
    @Override public void work()  { System.out.println("Engineer working"); }
    @Override public void eat()   { System.out.println("Engineer eating lunch"); }
    @Override public void sleep() { System.out.println("Engineer sleeping"); }
    @Override public void code()  { System.out.println("Engineer coding"); }
}

class Robot implements Workable {
    //  ↑ Robot ONLY implements Workable. No forced methods. Clean.
    @Override public void work() { System.out.println("Robot working"); }
}

class FactoryWorker implements Workable, Feedable, Sleepable {
    //  ↑ Factory worker: works, eats, sleeps but doesn't code.
    @Override public void work()  { System.out.println("Factory worker working"); }
    @Override public void eat()   { System.out.println("Factory worker eating"); }
    @Override public void sleep() { System.out.println("Factory worker sleeping"); }
}

// BENEFIT: If Codeable interface changes (add compileCode()):
// Only HumanEngineer is affected. Robot and FactoryWorker: untouched.
```

---

## D — Dependency Inversion Principle (DIP)

```
RULE: 
  1. High-level modules should NOT depend on low-level modules.
     Both should depend on ABSTRACTIONS (interfaces).
  2. Abstractions should NOT depend on details.
     Details (implementations) should depend on abstractions.

ANALOGY: Wall socket and devices.
  Your laptop doesn't depend on "this specific power plant."
  It depends on the ABSTRACTION: "230V AC socket."
  Any power source that provides 230V AC works. The socket is the abstraction.
  
  DIP: Write code that depends on "socket interface," not "specific power plant."

VIOLATION:
  class OrderService {
    private MySQLDatabase db = new MySQLDatabase();   // Tightly coupled to MySQL!
    // If you switch to PostgreSQL: must modify OrderService. Bad.
  }

FIX: Depend on an interface (IDatabase), inject the implementation.
```

### Java — DIP

```java
// ── VIOLATION: High-level depends on low-level ────────────────────────────────
class BadOrderService {
    private MySQLDatabase db = new MySQLDatabase();
    //  ↑ BadOrderService CREATES its own dependency (MySQLDatabase).
    //    Tightly coupled: cannot test without a real MySQL connection.
    //    Cannot switch to PostgreSQL without modifying BadOrderService.
    //    Both problems: violates DIP.

    void placeOrder(Order order) {
        db.save(order);
    }
}

// ── FIX: Both depend on abstraction (interface) ───────────────────────────────

// ABSTRACTION (interface): what we depend on
interface OrderRepository {
    void save(Order order);
    Order findById(String id);
    List<Order> findByCustomer(String customerId);
    //  ↑ Interface defines the CONTRACT. No implementation details.
    //    OrderService uses this. MySQLOrderRepository implements this.
    //    Neither knows about the other directly.
}

// LOW-LEVEL detail: one implementation
class MySQLOrderRepository implements OrderRepository {
    private final String connectionString;

    MySQLOrderRepository(String connectionString) {
        this.connectionString = connectionString;
    }

    @Override
    public void save(Order order) {
        System.out.println("MySQL: INSERT INTO orders VALUES (...)");
        // Real: JDBC connection, PreparedStatement, executeUpdate()
    }

    @Override
    public Order findById(String id) {
        System.out.println("MySQL: SELECT * FROM orders WHERE id = " + id);
        return null; // Placeholder
    }

    @Override
    public List<Order> findByCustomer(String customerId) {
        return new ArrayList<>(); // Placeholder
    }
}

// ANOTHER low-level detail: another implementation
class InMemoryOrderRepository implements OrderRepository {
    //  ↑ In-memory implementation: used in UNIT TESTS.
    //    No real DB needed → tests run fast (milliseconds vs seconds for DB tests).
    private final Map<String, Order> store = new HashMap<>();
    //  ↑ HashMap: key-value store. Key = order id, Value = Order object.

    @Override
    public void save(Order order) {
        store.put(order.getId(), order);
        //  ↑ put(key, value): insert or update in HashMap.
    }

    @Override
    public Order findById(String id) {
        return store.get(id);
        //  ↑ get(key): returns value or null if key not present.
    }

    @Override
    public List<Order> findByCustomer(String customerId) {
        return store.values().stream()
                             .filter(o -> o.getCustomerId().equals(customerId))
                             .collect(Collectors.toList());
        //  ↑ .values(): all values in the map.
        //  ↑ .filter(predicate): keep only elements where predicate is true.
        //  ↑ Collectors.toList(): collect stream elements into a new List.
    }
}

// HIGH-LEVEL module: depends on ABSTRACTION (interface), not concrete class
class GoodOrderService {
    private final OrderRepository repository;
    //  ↑ Depends on interface. Not MySQL, not InMemory. Just the contract.

    GoodOrderService(OrderRepository repository) {
        //  ↑ DEPENDENCY INJECTION: caller provides the implementation.
        //    In tests: inject InMemoryOrderRepository (fast, no DB needed).
        //    In production: inject MySQLOrderRepository.
        //    GoodOrderService code NEVER CHANGES regardless of which is injected.
        this.repository = repository;
    }

    void placeOrder(Order order) {
        // ... business logic (validate, check inventory, etc.)
        repository.save(order);
        //  ↑ Uses the INTERFACE. Doesn't know or care which implementation runs.
    }
}

// TESTING (no real DB needed):
// OrderRepository repo = new InMemoryOrderRepository();   ← Test double
// GoodOrderService svc = new GoodOrderService(repo);
// svc.placeOrder(new Order(...));
// // Assert: repo.findById(...) returns expected order

// PRODUCTION:
// OrderRepository repo = new MySQLOrderRepository("jdbc:mysql://localhost/orders");
// GoodOrderService svc = new GoodOrderService(repo);      ← Same class, different impl
```

### C++ — DIP

```cpp
// ── C++ DIP: same concept, pure virtual interface ─────────────────────────────
#pragma once
#include <string>
#include <vector>
#include <memory>
#include <unordered_map>

struct Order {
    std::string id;
    std::string customerId;
    double amount;
};

// ABSTRACTION: pure virtual base class = interface in C++
class IOrderRepository {
public:
    virtual ~IOrderRepository() = default;
    virtual void save(const Order& order) = 0;
    //  ↑ = 0: pure virtual. No implementation. Derived class MUST implement.
    virtual Order findById(const std::string& id) const = 0;
};

// LOW-LEVEL: concrete implementation
class MySQLOrderRepository : public IOrderRepository {
public:
    void save(const Order& order) override {
        printf("MySQL: INSERT order %s\n", order.id.c_str());
        //  ↑ .c_str(): convert std::string to C-style const char* (needed for printf).
    }

    Order findById(const std::string& id) const override {
        printf("MySQL: SELECT * FROM orders WHERE id = %s\n", id.c_str());
        return Order{}; // Placeholder
        //  ↑ Order{}: value-initialize all fields to defaults (empty strings, 0 for double).
    }
};

// IN-MEMORY: for testing
class InMemoryOrderRepository : public IOrderRepository {
public:
    void save(const Order& order) override {
        store_[order.id] = order;
        //  ↑ operator[]: insert or update. Key=id, Value=order.
        //    Like Java's HashMap.put().
    }

    Order findById(const std::string& id) const override {
        auto it = store_.find(id);
        //  ↑ find(): O(1) average. Returns iterator to found element.
        //    If not found: returns store_.end() (a sentinel iterator).
        if (it == store_.end()) return Order{}; // Not found → return empty
        return it->second;
        //  ↑ it is an iterator to pair<string, Order>.
        //  ↑ it->second: the VALUE in the pair (the Order object).
        //    it->first would be the KEY (the string id).
    }

private:
    std::unordered_map<std::string, Order> store_;
    //  ↑ unordered_map: hash map. O(1) average for find/insert.
    //    Like Java's HashMap.
};

// HIGH-LEVEL: depends on abstraction
class OrderService {
public:
    explicit OrderService(std::unique_ptr<IOrderRepository> repository)
        : repository_(std::move(repository)) {}
    //  ↑ unique_ptr: exactly one owner. Moved into this class.
    //    When OrderService is destroyed: repository_ is automatically destroyed too.
    //    No manual delete. RAII.

    void placeOrder(const Order& order) {
        repository_->save(order);
        //  ↑ -> : access through smart pointer. Same as (*repository_).save(order).
    }

private:
    std::unique_ptr<IOrderRepository> repository_;
    //  ↑ Points to IOrderRepository interface. Actual type: MySQL or InMemory.
    //    OrderService doesn't know which. Doesn't need to.
};

// USAGE:
// PRODUCTION:
// auto svc = OrderService(std::make_unique<MySQLOrderRepository>());
// TESTING:
// auto svc = OrderService(std::make_unique<InMemoryOrderRepository>());
// Same OrderService class, different behaviour injected.
```

---

## SOLID Quick Reference

```
S — Single Responsibility:
  One class = one reason to change.
  Signal: "If I need to change X, which classes do I touch?" → should be ONE.

O — Open/Closed:
  Add features by ADDING classes/methods, not MODIFYING existing ones.
  Signal: "Adding new payment type → do I modify existing code?" → should be NO.

L — Liskov Substitution:
  Subclass must be a valid replacement for its parent. No surprises.
  Signal: "Can I pass a subclass wherever parent is expected without bugs?" → should be YES.

I — Interface Segregation:
  Small focused interfaces over one big fat interface.
  Signal: "Does any class implement a method with throw UnsupportedOperationException?" → ISP violated.

D — Dependency Inversion:
  Depend on interfaces, not concrete classes. Inject dependencies.
  Signal: "Does high-level class create its own low-level dependencies with 'new'?" → DIP violated.

MAANG INTERVIEW TIP:
  When asked "design a payment system":
  - S: PaymentService (logic) ≠ PaymentRepository (DB) ≠ PaymentNotifier (alerts)
  - O: Adding UPI doesn't modify CardProcessor. New class UPIProcessor.
  - L: UPIProcessor can substitute IPaymentProcessor anywhere CardProcessor was used.
  - I: Don't have one IPaymentProcessor with methods both card and UPI must implement.
  - D: PaymentService depends on IPaymentProcessor, not on StripeProcessor directly.
```

---

## HOW SOLID APPEARS IN THE LLD CASE STUDIES

### S — Single Responsibility

```
CS04 Uber:
  UberService (orchestration only — request, match, trip lifecycle)
  FareCalculator (pricing only — distance + duration + surge → Decimal)
  LocationTracker (GPS tracking only — driver positions)
  TripRepository (DB reads/writes for Trip only)
  Each class changes for exactly ONE reason. Change pricing formula? Only FareCalculator.

CS07 Google Search:
  Tokenizer → text to tokens only.
  InvertedIndex → store and lookup posting lists only.
  PageRankEngine → compute scores only.
  QueryParser → parse raw query string only.
  Ranker → combine TF-IDF + PageRank scores only.
  SearchEngine (Facade) → orchestrate all these single-responsibility classes.
  NONE of these know about each other's internals. Each has one reason to change.

CS09 Payment Gateway:
  PaymentGatewayService → orchestration, routing, idempotency.
  CardProcessor → card charge/refund via Stripe API only.
  FraudDetector → risk scoring only (ML model or rule-based).
  WebhookNotifier → send HTTP callbacks to merchant only.
  Each has a single, clear responsibility.

CS06 YouTube:
  TranscodeJob → manages transcoding lifecycle only.
  VideoSearchService → indexing + search only.
  LikeService → like/unlike counting only.
  Channel → subscription management only.
```

### O — Open / Closed

```
CS04 Uber:
  Adding "flat rate pricing" → new FlatRatePricingStrategy class.
  UberService.calculate_fare(): UNCHANGED. Just injects new strategy. OCP satisfied.

CS09 Payment Gateway:
  Adding UPI → new UPIProcessor implementing IPaymentProcessor.
  PaymentGatewayService._route_to_processor(): add one entry to routing dict.
  CardProcessor, WalletProcessor: COMPLETELY UNTOUCHED.

CS10 MakeMyTrip:
  Adding "new cancellation policy tier" → new PolicyClass(ICancellationPolicy).
  Booking service: assign new policy to new booking types. Existing code unchanged.

CS11 AI Systems:
  Adding Gemini support → new GeminiAdapter(ILLMAdapter).
  LLMService: unchanged. Factory registers "gemini" → GeminiAdapter. Done.

PATTERN: Every Strategy pattern in the case studies = OCP in action.
  Strategy pattern + Factory pattern together = the gold standard for OCP.
```

### L — Liskov Substitution

```
CS04 Uber:
  SurgePricingStrategy substitutes NormalPricingStrategy wherever IFareStrategy is expected.
  No extra null checks. No "if isinstance(strategy, SurgePricingStrategy): do something special."
  The loop: fare = strategy.calculate(distance, duration, surge) works for ALL strategies.

CS05 Netflix:
  Episode substitutes ContentItem anywhere. Series substitutes ContentItem anywhere.
  is_available(), get_content_info() work correctly for BOTH.
  No surprises. No broken behavior.

CS09 Payment Gateway:
  The for-loop: for processor in processors: processor.charge(amount, card)
  Correct behavior for CardProcessor, UPIProcessor, WalletProcessor. No type-checking.

ANTI-PATTERN (what NOT to do in case studies):
  class TrialUserProcessor(CardProcessor):
      def charge(amount, card):
          raise Exception("Trial users can't pay")  ← LSP VIOLATION!
  Fix: Implement IPaymentProcessor directly. Don't inherit from CardProcessor.
```

### I — Interface Segregation

```
CS04 Uber:
  IFareStrategy: ONLY calculate(). Not calculate() + logFare() + displayFare().
  Logging is a separate concern (decorator/observer pattern).

CS06 YouTube:
  IAdaptiveBitrateStrategy: just select(variants, bandwidth) → VideoVariant.
  Separate from ISearchStrategy, separate from INotificationStrategy.
  Each strategy interface is laser-focused.

CS09 Payment Gateway:
  IPaymentProcessor: charge() and refund() ONLY.
  NOT: charge() + refund() + generateReport() + sendSMS() + notify().
  Report generation and notifications are separate classes/interfaces.

CS11 AI Systems:
  ILLMAdapter: generate(prompt, params) → str.
  NOT: generate() + embed() + classify() + moderate() all in one interface.
  Embedding is a separate IEmbeddingAdapter interface.
```

### D — Dependency Inversion

```
CS04 Uber:
  UberService depends on IFareStrategy (interface), not NormalPricingStrategy (concrete).
  Injected via constructor: UberService(fare_strategy=SurgePricingStrategy()).
  In tests: UberService(fare_strategy=MockFareStrategy()).

CS09 Payment Gateway:
  PaymentGatewayService depends on IPaymentProcessor (interface).
  Processors injected/registered from outside.
  Tests: inject MockProcessor → no real network calls.
  Production: inject StripeCardProcessor → real API.

CS11 AI Systems:
  LLMService depends on ILLMAdapter (interface).
  Injected: LLMService(adapter=OpenAIAdapter(api_key="...")).
  To switch: LLMService(adapter=AnthropicAdapter(api_key="...")).
  LLMService code: ZERO changes.

JAVA/C++ PATTERN:
  Java: Constructor receives interface type. Never does: new ConcreteClass() inside.
  C++: Constructor receives unique_ptr<IInterface>. Takes ownership via move.
  Both: The "injected" object can be a mock in tests and real in production.
```

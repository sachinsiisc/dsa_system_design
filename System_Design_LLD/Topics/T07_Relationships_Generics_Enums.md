# LLD Topic 07: Relationships — Association, Aggregation, Composition
## Plus: Generics, Enums, Exceptions | Java + C++ | Every Keyword

---

## CONCEPT 1: CLASS RELATIONSHIPS

```
FOUR MAIN RELATIONSHIPS (how classes connect to each other):

1. ASSOCIATION (uses-a / knows-a):
   Class A has a reference to Class B. They interact but neither owns the other.
   Both can exist independently.
   Example: Student is associated with Library. Student uses Library.
            If Student leaves, Library still exists. If Library closes, Student still exists.
   Code: Library reference stored in Student field.

2. AGGREGATION (has-a, WEAK ownership):
   Class A "has" B, but B can exist without A.
   If A is destroyed, B still lives.
   Example: Team has Players. Player can exist independently (not tied to one team).
   Code: Team stores references/pointers to Players.

3. COMPOSITION (has-a, STRONG ownership):
   Class A OWNS B. B cannot exist without A.
   If A is destroyed, B is also destroyed.
   Example: House has Rooms. Rooms make no sense without the House.
            If House is demolished, all Rooms are gone.
   Code: Room objects created INSIDE House constructor. Live and die with House.

4. INHERITANCE (is-a):
   Already covered in T01. Car IS-A Vehicle.

MEMORY AID:
  "Whole-part" relationship? → Composition (both die together) or Aggregation (part survives).
  "Uses/Knows" relationship? → Association.
  "Is a type of" relationship? → Inheritance.
```

### Java — Association vs Aggregation vs Composition

```java
// ── ASSOCIATION: Student ↔ Library ────────────────────────────────────────────
class Library {
    private final String name;
    private final List<Book> books;

    public Library(String name) {
        this.name  = name;
        this.books = new ArrayList<>();
    }

    public boolean borrowBook(String title) {
        return books.stream()
                    .filter(b -> b.getTitle().equals(title) && b.isAvailable())
                    .findFirst()
                    //  ↑ findFirst(): returns Optional<Book>. First match, or empty Optional.
                    .map(b -> { b.setBorrowed(true); return true; })
                    //  ↑ .map(fn): if Optional has value, apply fn to it.
                    //    b.setBorrowed(true): mark book as borrowed. Returns true.
                    .orElse(false);
                    //  ↑ .orElse(default): return the Optional's value, or default if empty.
                    //    If no book found: return false.
    }

    public String getName() { return name; }
}

class Student {
    private final String name;
    private Library library;
    //  ↑ ASSOCIATION: Student has a reference to Library.
    //    Student doesn't OWN Library. Library exists independently.
    //    Student can change which library they use (library = anotherLibrary).
    //    If Student object is garbage collected: Library still exists.

    public Student(String name) {
        this.name    = name;
        this.library = null;   // Starts with no library association
    }

    public void registerAtLibrary(Library library) {
        this.library = library;
        //  ↑ ASSOCIATION established. Student now "knows about" this library.
        System.out.println(name + " registered at " + library.getName());
    }

    public boolean borrowBook(String title) {
        if (library == null) {
            System.out.println(name + " is not registered at any library.");
            return false;
        }
        return library.borrowBook(title);
        //  ↑ Delegates to Library. Student uses Library's service.
        //    Student → Library interaction is the ASSOCIATION in action.
    }
}

// ── AGGREGATION: Team → Players ───────────────────────────────────────────────
class Player {
    private final String name;
    private int skillLevel;

    public Player(String name, int skillLevel) {
        this.name       = name;
        this.skillLevel = skillLevel;
    }
    public String getName() { return name; }
    public int getSkillLevel() { return skillLevel; }
}

class Team {
    private final String teamName;
    private final List<Player> players;
    //  ↑ AGGREGATION: Team has Players.
    //    Players are NOT created by Team. They exist independently.
    //    Players passed in from outside (not created in constructor).
    //    If Team is dissolved: Player objects still exist (can join another team).

    public Team(String teamName) {
        this.teamName = teamName;
        this.players  = new ArrayList<>();
    }

    public void addPlayer(Player player) {
        //  ↑ Player exists BEFORE being added to team.
        //    Team just holds a REFERENCE to the player (aggregation).
        players.add(player);
        System.out.println(player.getName() + " joined " + teamName);
    }

    public void removePlayer(Player player) {
        players.remove(player);
        System.out.println(player.getName() + " left " + teamName);
        // Player object still exists! Just removed from this team's list.
        // Player can join another team: anotherTeam.addPlayer(player)
    }

    public int getAverageSkill() {
        return (int) players.stream()
                            .mapToInt(Player::getSkillLevel)
                            //  ↑ mapToInt: extract int value from each Player.
                            //  ↑ Player::getSkillLevel: method reference. Same as p -> p.getSkillLevel().
                            .average()
                            //  ↑ average(): returns OptionalDouble. Stream average.
                            .orElse(0);
                            //  ↑ orElse(0): if no players → average is 0.
    }
}

// ── COMPOSITION: House → Room ──────────────────────────────────────────────────
class Room {
    private final String name;      // "Living Room", "Kitchen", etc.
    private final double areaSqFt;

    Room(String name, double areaSqFt) {
        //  ↑ Package-private constructor: only classes in same package can create Room.
        //    External code can't do: new Room("Kitchen", 200).
        //    Only House creates Rooms → enforces composition.
        this.name      = name;
        this.areaSqFt  = areaSqFt;
    }

    public String getName()      { return name; }
    public double getArea()      { return areaSqFt; }
    public String toString() {
        return String.format("Room{%s, %.1f sqft}", name, areaSqFt);
    }
}

class House {
    private final String address;
    private final List<Room> rooms;
    //  ↑ COMPOSITION: House OWNS Rooms.
    //    Rooms created BY House. Rooms live and die with House.
    //    No one can create a Room externally (package-private constructor).

    public House(String address) {
        this.address = address;
        this.rooms   = new ArrayList<>();
        // ROOMS CREATED INSIDE HOUSE (composition — house creates its parts):
        rooms.add(new Room("Living Room", 400));
        rooms.add(new Room("Kitchen",     200));
        rooms.add(new Room("Bedroom",     300));
        rooms.add(new Room("Bathroom",    100));
        System.out.println("House at " + address + " built with " + rooms.size() + " rooms");
    }

    public List<Room> getRooms() {
        return Collections.unmodifiableList(rooms);
        //  ↑ unmodifiableList: caller can read rooms but NOT add/remove.
        //    Prevents: house.getRooms().add(new Room(...)) — which would break encapsulation.
        //    Room list is managed ONLY by House.
    }

    public double getTotalArea() {
        return rooms.stream()
                    .mapToDouble(Room::getArea)
                    .sum();
    }

    // When House object is GC'd: rooms list and all Room objects are also GC'd.
    // No one else has references to these Room objects. Composition: parts die with whole.
}
```

### C++ — Composition vs Aggregation

```cpp
// ── C++ Composition: OWNS (created internally, dies with parent) ───────────────
#pragma once
#include <vector>
#include <memory>
#include <string>

// Composition: Engine is OWNED by Car. Car creates and destroys Engine.
class Engine {
public:
    Engine(int horsePower, std::string fuelType)
        : hp_(horsePower), fuelType_(std::move(fuelType)) {}

    void start() { printf("Engine (%dHP, %s): vroom!\n", hp_, fuelType_.c_str()); }

private:
    int hp_;
    std::string fuelType_;
};

class Car {
public:
    Car(std::string model, int hp, std::string fuel)
        : model_(std::move(model)),
          engine_(std::make_unique<Engine>(hp, std::move(fuel)))
          //  ↑ COMPOSITION: Car creates its Engine using make_unique.
          //    Engine doesn't exist before Car creates it.
          //    unique_ptr: Car OWNS the Engine. No sharing.
          //    When Car is destroyed: ~Car() is called → engine_ unique_ptr destructs → Engine destroyed.
    {}

    void start() {
        printf("Car %s: starting...\n", model_.c_str());
        engine_->start();   // Delegate to owned engine
    }

private:
    std::string model_;
    std::unique_ptr<Engine> engine_;   // COMPOSITION: owns the engine
};

// ── C++ Aggregation: REFERENCES (doesn't own, doesn't destroy) ────────────────

class PlayerObj {
public:
    PlayerObj(std::string name, int skill) : name_(std::move(name)), skill_(skill) {}
    const std::string& name()  const { return name_; }
    int                skill() const { return skill_; }
private:
    std::string name_;
    int skill_;
};

class TeamObj {
public:
    void addPlayer(PlayerObj* player) {
        //  ↑ RAW POINTER: TeamObj does NOT own Player.
        //    Raw pointer = "I know about this object but I don't own it."
        //    When TeamObj is destroyed: Players are NOT deleted.
        //    Player's lifetime is managed externally (by whoever created them).
        players_.push_back(player);
        printf("Player %s joined team\n", player->name().c_str());
    }

    void removePlayer(PlayerObj* player) {
        players_.erase(
            std::remove(players_.begin(), players_.end(), player),
            players_.end()
        );
        //  ↑ Erase-remove idiom:
        //    std::remove: moves all non-matching elements to front, returns iterator to new end.
        //    players_.erase(new_end, end): erase the "removed" elements at the back.
        //    Why two steps? std::remove doesn't change size (just reorders).
    }

    double averageSkill() const {
        if (players_.empty()) return 0.0;
        double total = 0;
        for (const auto* p : players_) total += p->skill();
        //  ↑ const auto*: const pointer to PlayerObj. We don't modify players through this.
        return total / players_.size();
    }

private:
    std::vector<PlayerObj*> players_;
    //  ↑ Vector of RAW POINTERS = aggregation.
    //    Vector of unique_ptr = composition (would own the players).
    //    Vector of shared_ptr = shared ownership (both own).
};

// ── C++ OWNERSHIP SUMMARY:
// T obj;                    → COMPOSITION (by value). obj lives with its parent.
// std::unique_ptr<T> ptr;   → COMPOSITION (by unique ownership). ptr OWNS T.
// std::shared_ptr<T> ptr;   → SHARED OWNERSHIP. Multiple owners.
// T* ptr;                   → AGGREGATION (raw pointer). Doesn't own. Be careful!
// T& ref;                   → ASSOCIATION (reference). Doesn't own. Cannot be null.
```

---

## CONCEPT 2: GENERICS / TEMPLATES

```
WHAT: Write code ONCE that works with ANY type.
      Instead of writing IntStack, StringStack, DoubleStack separately:
      Write Stack<T> once. Works for any T.

JAVA: Generics (compile-time type safety + erasure at runtime)
C++:  Templates (code generation at compile time. No erasure. Full type info at runtime.)
```

### Java — Generics

```java
// ── Generic Stack ──────────────────────────────────────────────────────────────

import java.util.ArrayList;
import java.util.EmptyStackException;

public class Stack<T> {
    //  ↑ <T>: TYPE PARAMETER. T is a placeholder for a real type.
    //    User specifies T when using: Stack<Integer>, Stack<String>, Stack<User>.
    //    Compile-time check: Stack<Integer>.push("hello") → COMPILE ERROR.
    //    Without generics: Stack would hold Object → no type check → runtime ClassCastException.

    private final ArrayList<T> items = new ArrayList<>();
    //  ↑ ArrayList<T>: parameterized by T. Can only hold items of type T.

    public void push(T item) {
        //  ↑ T item: accepts any T. If T=Integer: push(int_value). If T=String: push(string).
        items.add(item);
    }

    public T pop() {
        //  ↑ Returns T. Caller gets back the correct type — no casting needed.
        if (isEmpty()) throw new EmptyStackException();
        return items.remove(items.size() - 1);
        //  ↑ Remove and return last element (top of stack).
    }

    public T peek() {
        if (isEmpty()) throw new EmptyStackException();
        return items.get(items.size() - 1);
        //  ↑ Return last element WITHOUT removing it.
    }

    public boolean isEmpty() { return items.isEmpty(); }
    public int size()        { return items.size(); }
}

// ── Generic method with bounded type parameter ─────────────────────────────────

class MathUtils {
    public static <T extends Comparable<T>> T max(T a, T b) {
        //  ↑ <T extends Comparable<T>>: bounded type parameter.
        //    T must implement Comparable<T> (have a compareTo method).
        //    Without bound: can't call compareTo on T (compiler doesn't know T has it).
        //    With bound: Integer, Double, String all work (they all implement Comparable).
        //  ↑ static <T>: generic static method. T declared on the method, not the class.
        return a.compareTo(b) >= 0 ? a : b;
        //  ↑ compareTo: returns negative if a<b, 0 if equal, positive if a>b.
        //    >= 0: a >= b → return a. Otherwise return b.
    }

    public static <T extends Number & Comparable<T>> double sum(List<T> list) {
        //  ↑ T extends Number & Comparable<T>: multiple bounds.
        //    & syntax: T must implement BOTH Number and Comparable<T>.
        //    Number provides: intValue(), doubleValue(), etc.
        //    Comparable provides: compareTo().
        return list.stream()
                   .mapToDouble(Number::doubleValue)
                   //  ↑ Number::doubleValue: method reference. N → n.doubleValue()
                   //    Works because T extends Number → has doubleValue().
                   .sum();
    }
}

// ── Wildcard: unknown type ─────────────────────────────────────────────────────

class PrintUtils {
    public static void printList(List<?> list) {
        //  ↑ List<?>: "list of unknown type." ? = wildcard.
        //    Can accept: List<Integer>, List<String>, List<User> — anything.
        //    Trade-off: can only READ from the list. Cannot ADD (type unknown).
        for (Object item : list) {
            System.out.println(item);
        }
    }

    public static double sumNumbers(List<? extends Number> list) {
        //  ↑ List<? extends Number>: "list of some type that IS a Number."
        //    Accepts: List<Integer>, List<Double>, List<Long> — any Number subtype.
        //    UPPER BOUNDED wildcard. Can READ (as Number). Cannot ADD.
        return list.stream().mapToDouble(Number::doubleValue).sum();
    }

    public static void addNumbers(List<? super Integer> list) {
        //  ↑ List<? super Integer>: "list of Integer or any SUPERTYPE of Integer."
        //    Accepts: List<Integer>, List<Number>, List<Object>.
        //    LOWER BOUNDED wildcard. Can ADD Integer (or subtype). READ as Object.
        list.add(1);
        list.add(2);
        list.add(3);
    }
}

// PECS rule: Producer Extends, Consumer Super.
// If you READ from a collection → use ? extends T (T is the producer of values).
// If you WRITE to a collection → use ? super T (T is consumed by the collection).
```

### C++ — Templates

```cpp
// ── C++ Template Stack ────────────────────────────────────────────────────────
#pragma once
#include <vector>
#include <stdexcept>

template<typename T>
//  ↑ template<typename T>: defines T as a type parameter.
//    Each use of Stack<int>, Stack<std::string> generates SEPARATE code.
//    C++ templates: code generation at compile time. Full type info. No erasure.
//    Java generics: erasure at runtime. Generic info lost. One compiled version.
class Stack {
public:
    void push(T item) {
        items_.push_back(std::move(item));
        //  ↑ std::move: transfer ownership (avoid copy if T is move-only or large).
    }

    T pop() {
        if (isEmpty()) throw std::underflow_error("Stack is empty");
        T top = std::move(items_.back());
        //  ↑ std::move: move the top element out (before removing it).
        //    items_.back(): reference to last element.
        items_.pop_back();
        //  ↑ Remove last element. O(1).
        return top;   // Move (not copy) the popped value to caller.
    }

    const T& peek() const {
        //  ↑ const T&: return read-only reference (no copy, no modification).
        if (isEmpty()) throw std::underflow_error("Stack is empty");
        return items_.back();
    }

    bool isEmpty() const { return items_.empty(); }
    size_t size()  const { return items_.size(); }
    //  ↑ size_t: unsigned integer type for sizes. Never negative.
    //    Returns same type as vector::size(). Avoids signed/unsigned comparison warnings.

private:
    std::vector<T> items_;
};

// ── Template function with constraint (C++20 Concept) ────────────────────────
#include <concepts>
//  ↑ C++20: <concepts> header. Compile-time constraints on template parameters.

template<std::totally_ordered T>
//  ↑ std::totally_ordered: concept requiring T supports <, >, <=, >=, ==, !=.
//    Like Java's T extends Comparable<T> but at compile time.
//    Error if T doesn't satisfy the concept: clear error message.
T maxValue(T a, T b) {
    return a > b ? a : b;
}

// ── Template specialization: custom behavior for specific type ────────────────
template<>
//  ↑ Full template specialization: empty angle brackets.
const char* maxValue<const char*>(const char* a, const char* b) {
    //  ↑ Specialized version for const char* (C strings).
    //    Generic version uses >: pointer comparison (WRONG for C strings!).
    //    This specialization uses strcmp (CORRECT for C strings).
    return strcmp(a, b) >= 0 ? a : b;
    //  ↑ strcmp: compares two C strings lexicographically.
    //    strcmp("b", "a") > 0 → "b" > "a" → true.
}
```

---

## CONCEPT 3: ENUMS

```
WHAT: A type with a fixed set of named constants.
      Stronger than plain int constants or String constants:
      - Type-safe: no invalid values
      - Methods can be added to each enum value
      - Switch statements are exhaustive (compiler warns on missing cases)

REAL USE IN LLD:
  VideoStatus.UPLOADING, PROCESSING, PUBLISHED (YouTube CS06)
  PaymentStatus.PENDING, AUTHORIZED, CAPTURED (Payment CS09)
  JobStatus.QUEUED, PROCESSING, COMPLETED, FAILED
  TweetType.ORIGINAL, REPLY, RETWEET, QUOTE_TWEET (Twitter CS08)
```

### Java — Enums (powerful)

```java
// ── Java Enum: HttpStatus ─────────────────────────────────────────────────────

public enum HttpStatus {
    //  ↑ enum: special class with fixed instances defined in the enum body.
    //    Each name (OK, NOT_FOUND, etc.) is a public static final instance of HttpStatus.
    //    Cannot create: new HttpStatus("whatever") → compile error. Fixed set only.

    // ENUM CONSTANTS with constructor arguments:
    OK(200, "OK"),
    //  ↑ OK: a constant of type HttpStatus. Constructor called with (200, "OK").
    CREATED(201, "Created"),
    BAD_REQUEST(400, "Bad Request"),
    UNAUTHORIZED(401, "Unauthorized"),
    FORBIDDEN(403, "Forbidden"),
    NOT_FOUND(404, "Not Found"),
    INTERNAL_ERROR(500, "Internal Server Error");

    // FIELDS (each enum value has these):
    private final int code;
    private final String message;
    //  ↑ final: set in constructor, cannot change.
    //    Each enum constant has its own code and message.

    // CONSTRUCTOR (private — called only for each constant definition above):
    HttpStatus(int code, String message) {
        //  ↑ Enum constructors are ALWAYS private (even without 'private' keyword).
        //    You can't call: new HttpStatus(999, "whatever"). Only the constants are created.
        this.code    = code;
        this.message = message;
    }

    // METHODS on enum:
    public int getCode()       { return code; }
    public String getMessage() { return message; }

    public boolean isSuccess() {
        return code >= 200 && code < 300;
        //  ↑ Convenience method. No need for external if/else.
        //    status.isSuccess() is more readable than status.getCode() >= 200 && ...
    }

    public boolean isClientError() { return code >= 400 && code < 500; }
    public boolean isServerError() { return code >= 500; }

    // STATIC FACTORY METHOD on enum:
    public static HttpStatus fromCode(int code) {
        for (HttpStatus status : values()) {
            //  ↑ values(): built-in enum method. Returns array of all constants.
            //    [OK, CREATED, BAD_REQUEST, ...]. Iterate to find by code.
            if (status.code == code) return status;
        }
        throw new IllegalArgumentException("Unknown HTTP code: " + code);
    }

    @Override
    public String toString() {
        return code + " " + message;
        //  ↑ "200 OK", "404 Not Found", etc.
        //    Without @Override: toString() returns "OK", "NOT_FOUND" (enum name).
    }
}

// Enum with ABSTRACT method (each constant has different implementation):
public enum Operation {
    PLUS("+") {
        @Override public double apply(double x, double y) { return x + y; }
        //  ↑ Enum constant-specific body: overrides apply() for PLUS.
    },
    MINUS("-") {
        @Override public double apply(double x, double y) { return x - y; }
    },
    TIMES("*") {
        @Override public double apply(double x, double y) { return x * y; }
    },
    DIVIDE("/") {
        @Override public double apply(double x, double y) {
            if (y == 0) throw new ArithmeticException("Division by zero");
            return x / y;
        }
    };

    private final String symbol;
    Operation(String symbol) { this.symbol = symbol; }

    public abstract double apply(double x, double y);
    //  ↑ Abstract in enum: each constant MUST override it (they do above).
    //    Enum with abstract method = Strategy Pattern built into enum!

    @Override public String toString() { return symbol; }
}

// USAGE:
// HttpStatus status = HttpStatus.NOT_FOUND;
// System.out.println(status);             // "404 Not Found"
// System.out.println(status.isClientError()); // true
//
// HttpStatus found = HttpStatus.fromCode(200);  // OK
// System.out.println(found.isSuccess());  // true
//
// double result = Operation.PLUS.apply(3, 4);   // 7.0
// for (Operation op : Operation.values()) {
//     System.out.printf("3 %s 4 = %.1f%n", op, op.apply(3, 4));
// }
```

### C++ — Enum Class

```cpp
// ── C++: enum class (strongly typed, scoped) ──────────────────────────────────

enum class VideoStatus {
    //  ↑ enum class: strongly typed, scoped enum (C++11).
    //    vs old-style 'enum': old-style leaks names into enclosing scope.
    //    enum Status { UPLOADING, DONE };  → UPLOADING pollutes the namespace!
    //    enum class Status { UPLOADING, DONE }; → must use Status::UPLOADING (scoped).
    //    Also: no implicit conversion to int (type safe).

    Uploading,
    Processing,
    Published,
    Unlisted,
    Private,
    Removed
};

// USAGE:
// VideoStatus s = VideoStatus::Processing;  // Must use scope qualifier
// if (s == VideoStatus::Published) { ... }  // Comparison requires same type
// int code = s;  // COMPILE ERROR: no implicit int conversion (unlike old enum)
// int code = static_cast<int>(s);  // Explicit cast: OK

// ENUM with values (C++ doesn't have built-in methods like Java enum):
enum class HttpStatusCode : int {
    //  ↑ : int: underlying type. Specifies int as storage type.
    //    Default underlying type: int. Can use short, long, uint8_t, etc.
    //    Useful for: serialization (serialize exact type), memory control.
    OK                = 200,
    Created           = 201,
    BadRequest        = 400,
    Unauthorized      = 401,
    NotFound          = 404,
    InternalError     = 500
};

// Helper functions (since C++ enum can't have methods):
bool isSuccess(HttpStatusCode code) {
    int c = static_cast<int>(code);
    return c >= 200 && c < 300;
    //  ↑ static_cast<int>: explicit conversion from enum to int.
    //    Required for enum class (no implicit conversion).
}

const char* httpStatusMessage(HttpStatusCode code) {
    switch (code) {
        case HttpStatusCode::OK:            return "OK";
        case HttpStatusCode::Created:       return "Created";
        case HttpStatusCode::NotFound:      return "Not Found";
        case HttpStatusCode::InternalError: return "Internal Server Error";
        default:                            return "Unknown";
    }
    //  ↑ switch on enum class: compiler warns if a case is missing (with -Wswitch flag).
    //    This is one advantage of enum class over int constants.
}
```

---

## CONCEPT 4: EXCEPTION HANDLING

```
WHAT: Handle runtime errors gracefully. Don't let the program crash.
      Propagate errors UP the call stack to the right handler.

JAVA EXCEPTION HIERARCHY:
  Throwable
  ├── Error (don't catch: OutOfMemoryError, StackOverflowError)
  └── Exception
      ├── RuntimeException (UNCHECKED: don't need to declare or catch)
      │   ├── NullPointerException
      │   ├── IllegalArgumentException
      │   ├── IllegalStateException
      │   └── IndexOutOfBoundsException
      └── CheckedException (MUST catch or declare: IOException, SQLException)

CHECKED vs UNCHECKED:
  Checked: compiler FORCES you to handle or declare.
    IOException: file operations can fail. Must handle.
  Unchecked (Runtime): programmer errors. Should FIX, not catch.
    NullPointerException: don't catch NPE. Fix the code that causes null.
```

### Java — Exception Handling

```java
// ── Custom Exceptions ──────────────────────────────────────────────────────────

// Custom unchecked exception:
public class InsufficientFundsException extends RuntimeException {
    //  ↑ extends RuntimeException: UNCHECKED. Callers don't need to catch it.
    //    Good for domain/business logic errors.

    private final double requested;
    private final double available;

    public InsufficientFundsException(double requested, double available) {
        super(String.format("Requested ₹%.2f but only ₹%.2f available",
                            requested, available));
        //  ↑ super(message): calls RuntimeException constructor with our message.
        //    getMessage() will return this message.
        this.requested = requested;
        this.available = available;
    }

    public double getRequested()  { return requested; }
    public double getAvailable()  { return available; }
    public double getShortfall()  { return requested - available; }
}

// Custom checked exception:
public class PaymentGatewayException extends Exception {
    //  ↑ extends Exception (not RuntimeException): CHECKED exception.
    //    Any method that throws this MUST declare it: void pay() throws PaymentGatewayException
    //    Callers MUST catch it or propagate it.

    private final String gatewayCode;    // Gateway's error code

    public PaymentGatewayException(String message, String gatewayCode) {
        super(message);
        this.gatewayCode = gatewayCode;
    }

    public PaymentGatewayException(String message, String gatewayCode, Throwable cause) {
        super(message, cause);
        //  ↑ super(message, cause): exception CHAINING.
        //    Wraps a lower-level exception with a higher-level one.
        //    Original exception preserved as 'cause'. Caller can inspect full chain.
        //    getCause(): returns the wrapped exception.
        //    Preserves stack trace of original error.
        this.gatewayCode = gatewayCode;
    }

    public String getGatewayCode() { return gatewayCode; }
}

// ── Exception handling patterns ────────────────────────────────────────────────

class PaymentService {
    public void processPayment(double amount, String cardNumber)
            throws PaymentGatewayException {
        //  ↑ throws: declares this method can throw PaymentGatewayException.
        //    REQUIRED for checked exceptions. Callers must handle.

        try {
            validateAmount(amount);         // Can throw IllegalArgumentException (unchecked)
            chargeCard(cardNumber, amount); // Can throw PaymentGatewayException (checked)
            sendConfirmation();             // Might throw EmailException (checked)
        } catch (IllegalArgumentException e) {
            //  ↑ catch: handles specific exception type.
            //    Executed if validateAmount throws IllegalArgumentException.
            System.out.println("Invalid input: " + e.getMessage());
            throw e;   // Re-throw after logging
        } catch (PaymentGatewayException e) {
            System.out.println("Gateway error [" + e.getGatewayCode() + "]: " + e.getMessage());
            throw e;   // Re-throw to caller
        } catch (Exception e) {
            //  ↑ Catch-all: catches any exception not caught above.
            //    Use sparingly — might hide bugs.
            //    Wrap in a more specific exception:
            throw new PaymentGatewayException("Unexpected payment error", "UNKNOWN", e);
            //  ↑ Exception chaining: wraps original 'e' as cause.
        } finally {
            //  ↑ finally: ALWAYS executes, even if exception was thrown.
            //    Use for cleanup: close connections, release locks, etc.
            releaseResources();
        }
    }

    private void validateAmount(double amount) {
        if (amount <= 0)
            throw new IllegalArgumentException("Amount must be positive: " + amount);
        if (amount > 100_000)
            throw new IllegalArgumentException("Amount exceeds limit: " + amount);
    }

    private void chargeCard(String cardNumber, double amount)
            throws PaymentGatewayException {
        if (cardNumber == null || cardNumber.length() < 16)
            throw new PaymentGatewayException("Invalid card", "CARD_INVALID");
        System.out.printf("Charging ₹%.2f to card *%s%n", amount, cardNumber.substring(12));
    }

    private void sendConfirmation() {
        System.out.println("Confirmation sent.");
    }

    private void releaseResources() {
        System.out.println("Resources released.");
    }
}

// TRY-WITH-RESOURCES: auto-close resources (Java 7+):
class FileProcessor {
    void process(String filename) throws Exception {
        try (var reader = new java.io.FileReader(filename);
             var buffered = new java.io.BufferedReader(reader)) {
            //  ↑ try-with-resources: resources declared in () are AUTO-CLOSED when block exits.
            //    Even if exception is thrown: reader.close() and buffered.close() are called.
            //    Resources must implement AutoCloseable (or Closeable).
            //    Order of closing: reverse of declaration. buffered.close() first, then reader.close().
            String line;
            while ((line = buffered.readLine()) != null) {
                //  ↑ readLine(): returns next line or null at end of file.
                //    (line = buffered.readLine()): assignment inside condition (valid in Java).
                //    != null: loop until end of file.
                System.out.println(line);
            }
        }
        //  ↑ No finally needed! Resources auto-closed. Cleaner than pre-Java-7.
    }
}
```

### C++ — Exception Handling

```cpp
// ── C++ Custom Exceptions ─────────────────────────────────────────────────────
#pragma once
#include <stdexcept>
#include <string>

// Custom exception hierarchy:
class DomainException : public std::runtime_error {
    //  ↑ Inherit from std::runtime_error. Provides what() method with our message.
    //    std::runtime_error: C++ standard base for runtime errors.
    //    Could also inherit from std::exception (base for all C++ exceptions).
public:
    explicit DomainException(const std::string& message)
        : std::runtime_error(message) {}
        //  ↑ Pass message to parent constructor. what() returns this message.
};

class InsufficientFundsException : public DomainException {
public:
    InsufficientFundsException(double requested, double available)
        : DomainException("Requested " + std::to_string(requested)
                          + " but only " + std::to_string(available) + " available"),
          requested_(requested), available_(available) {}

    double requested() const { return requested_; }
    double available() const { return available_; }

private:
    double requested_, available_;
};

// Usage:
void withdraw(double balance, double amount) {
    if (amount > balance)
        throw InsufficientFundsException(amount, balance);
        //  ↑ throw: creates exception and sends it up the call stack.
        //    C++ doesn't require declaring thrown exceptions (unlike Java checked exceptions).
}

void main_example() {
    try {
        withdraw(100.0, 200.0);   // Will throw
    } catch (const InsufficientFundsException& e) {
        //  ↑ catch by CONST REFERENCE: no copy made. No slicing. Polymorphism preserved.
        //    Always catch by const reference in C++.
        printf("Error: %s\n", e.what());   // what(): returns error message string
        printf("Shortfall: %.2f\n", e.requested() - e.available());
    } catch (const DomainException& e) {
        printf("Domain error: %s\n", e.what());
    } catch (const std::exception& e) {
        //  ↑ Catch-all for standard exceptions.
        printf("Standard error: %s\n", e.what());
    } catch (...) {
        //  ↑ Catch ANYTHING (including non-exception throws). Rare. Dangerous. Last resort.
        printf("Unknown error\n");
    }
    //  ↑ C++ has NO finally block! Use RAII instead.
    //    RAII: resources held in objects → automatically released in destructor.
    //    std::fstream file("data.txt"); → closed in ~fstream() even if exception thrown.
    //    std::lock_guard<std::mutex> lock(mtx_); → unlocked in ~lock_guard() even on exception.
}
```

---

## Summary

```
RELATIONSHIPS:
  Association: uses-a. Teacher uses Classroom. Independent lifetimes.
  Aggregation: has-a (weak). Team has Players. Players survive Team dissolution.
  Composition: has-a (strong). House has Rooms. Rooms die with House.
  
  Java code signal:
    Association:  field = externally provided reference. Can be null. Can change.
    Aggregation:  field = externally provided reference. Injected via constructor.
    Composition:  field = created INSIDE constructor (new X()). Or: final field.
    
  C++ code signal:
    T obj;              → composition (by value, lives with parent)
    unique_ptr<T>       → composition (exclusive ownership)
    T* or T& or shared_ptr<T> (externally provided) → aggregation/association

GENERICS/TEMPLATES:
  Java: Stack<T> → one compiled class. Type info erased at runtime. Reflection needed to recover.
  C++:  Stack<T> → SEPARATE compiled class for each T. Full type info. Faster. Larger binary.
  
  Java gotchas:
    new T() → compile error (can't instantiate generic type directly).
    T[] arr → compile error (no generic arrays).
    Use factory or Class<T> token to work around.

ENUMS:
  Java: powerful. Can have fields, methods, abstract methods.
        Use: when constants need associated data or behaviour.
  C++:  enum class: scoped, type-safe, no methods.
        For methods: use helper functions or a companion class.

EXCEPTIONS:
  Java: checked (must handle/declare) vs unchecked (RuntimeException).
       Use checked for: recoverable conditions the caller should handle.
       Use unchecked for: programmer errors, invalid input (should fix code, not catch).
       try-with-resources for auto-cleanup of Closeable resources.
  C++:  all exceptions are unchecked. No compiler enforcement.
        Use RAII instead of finally. Destructors clean up automatically.
        Catch by const reference. Use std::exception hierarchy.
```

---

## HOW THESE CONCEPTS APPEAR IN THE LLD CASE STUDIES

### Class Relationships in Case Studies

```
COMPOSITION (owns — part dies with whole):
  CS04 Uber:
    Trip COMPOSES TripRoute (route only makes sense in the context of a trip).
    If Trip is deleted: TripRoute is deleted. Makes no sense standalone.
    Java: Trip constructor creates TripRoute internally.
    C++: unique_ptr<TripRoute> route_ inside Trip.
  
  CS06 YouTube:
    Video COMPOSES VideoVariants (360p, 720p, 1080p, 4K copies).
    If Video is deleted: all variants deleted. No orphan variants allowed.
    Java: List<VideoVariant> created inside Video's processing pipeline.
    C++: vector<VideoVariant> variants_ (by value — composition).

  CS09 Payment Gateway:
    PaymentAttempt COMPOSES CardDetails (card details exist only for one payment attempt).
    Store only tokenized version after processing (PCI compliance).

AGGREGATION (has — part survives whole):
  CS04 Uber:
    DriverPool AGGREGATES Drivers.
    If DriverPool is shutdown: Drivers (user accounts) still exist in DB.
    Driver can be assigned to a different pool in another city.
  
  CS08 Twitter:
    Timeline AGGREGATES Tweets.
    If a user's Timeline is cleared: Tweets still exist (other users' timelines have them).
    Twitter OWNS the Tweets globally. Each timeline holds references.

  CS05 Netflix:
    UserProfile AGGREGATES WatchHistory entries.
    WatchHistory entries exist independently in analytics DB.
    User profile deletion ≠ analytics data deletion (compliance reasons).

ASSOCIATION (uses — independent):
  CS04 Uber:
    UberService uses FareCalculator (knows about it, calls it, but doesn't own it).
    FareCalculator exists independently. Can be used by multiple services.
  
  CS11 AI Systems:
    LLMService uses VectorStore (queries it but doesn't own it).
    VectorStore is shared across multiple services (RAGService, SearchService).
    Neither creates nor destroys the other.
```

### Generics/Templates in Case Studies

```
CS01 URL Shortener:
  Result<T> generic wrapper: Result<UrlEntry>, Result<List<UrlEntry>>.
  Encapsulates: value (T), error code, error message.
  Service methods return Result<T> instead of throwing exceptions.
  Java: class Result<T> { T value; String error; boolean isSuccess(); }
  C++: template<typename T> class Result { T value; std::string error; bool ok; };

CS05 Netflix:
  ContentRepository<T extends ContentItem>:
  Typed repository. findAll() returns List<T>.
  EpisodeRepository extends ContentRepository<Episode>.
  SeriesRepository extends ContentRepository<Series>.
  Type safety: EpisodeRepository.findAll() returns List<Episode>, not List<ContentItem>.

CS11 AI Systems:
  Cache<K, V>:
  SemanticCache<String, LLMResponse> for prompt caching.
  ResponseCache<RequestHash, EmbeddingVector> for embedding caching.
  Java: class Cache<K, V> { Map<K, V> store; V get(K key); void put(K key, V val); }
  C++: template<typename K, typename V> class Cache { unordered_map<K,V> store_; };
```

### Enums in Case Studies

```
CS04 Uber:
  TripStatus enum: REQUESTED, DRIVER_ASSIGNED, IN_PROGRESS, COMPLETED, CANCELLED.
  VehicleType enum: BIKE, AUTO, MINI, SEDAN, XL, PREMIER.
  Used in Trip class and TripStateManager for State pattern transitions.
  Java enum with methods: CANCELLED.canRefund() → true. COMPLETED.canRefund() → false.

CS06 YouTube:
  VideoStatus: UPLOADING, PROCESSING, PUBLISHED, UNLISTED, PRIVATE, REMOVED.
  VideoQuality: P360, P480, P720, P1080, P1440, P2160 (4K).
  VideoQuality enum with bitrate: P1080.getTargetBitrate() → 5_000_000.

CS09 Payment Gateway:
  PaymentStatus: PENDING, AUTHORIZED, CAPTURED, REFUNDED, FAILED, DISPUTED.
  PaymentMethod: CARD, UPI, WALLET, NET_BANKING, BNPL.
  RefundStatus: PENDING, PROCESSING, COMPLETED, FAILED.
  Each enum used in State pattern to determine allowed transitions.

CS10 MakeMyTrip:
  BookingStatus: HOLD, CONFIRMED, TICKETED, CANCELLED, REFUND_PENDING, REFUNDED.
  CabinClass: ECONOMY, PREMIUM_ECONOMY, BUSINESS, FIRST.
  FlightStatus: ON_TIME, DELAYED, CANCELLED, DIVERTED, LANDED.
  
JAVA ENUM PATTERN in Case Studies:
  Payment gateway status enum has methods:
  PaymentStatus.CAPTURED.isTerminal() → true (no further transitions).
  PaymentStatus.PENDING.isTerminal() → false.
  PaymentStatus.AUTHORIZED.allowedTransitions() → [CAPTURED, FAILED].
  This replaces if/else chains in state transition logic.

C++ ENUM CLASS:
  enum class VideoStatus { Uploading, Processing, Published, Removed };
  switch (status) { case VideoStatus::Published: ... break; }
  Compiler warns if switch doesn't cover all cases → catches bugs.
```

### Exceptions in Case Studies

```
CS01 URL Shortener:
  UrlNotFoundException (unchecked): thrown when short code doesn't exist in lookup.
  UrlExpiredException (unchecked): thrown when short URL has expired.
  DuplicateCustomCodeException (unchecked): custom short code already taken.
  All are domain exceptions: extend RuntimeException in Java.

CS04 Uber:
  NoDriverAvailableException: thrown when no drivers in radius.
  TripStateException: thrown when invalid transition (e.g., cancel already-completed trip).
  FareCalculationException: arithmetic issue in fare computation.

CS09 Payment Gateway:
  PaymentDeclinedException (carries: error_code, decline_reason, can_retry).
  InsufficientFundsException: extends PaymentDeclinedException.
  FraudDetectedException: with risk_score field.
  IdempotencyConflictException: same key, different request body.
  
  EXCEPTION CHAINING in CS09:
    try {
        stripeClient.charge(token, amountInCents);
    } catch (StripeException e) {
        throw new PaymentDeclinedException("Card declined", "CARD_DECLINED", e);
        // Wraps Stripe's exception → preserves original stack trace.
        // Caller gets domain exception (not Stripe-specific → Adapter pattern).
    }

CS11 AI Systems:
  LLMRateLimitException (with: retry_after_seconds, provider_name).
  ContextWindowExceededException (with: token_count, max_allowed).
  EmbeddingDimensionMismatchException: vector dimensions don't match index.
  
  TRY-WITH-RESOURCES in CS11 (Java):
    try (var session = llmClient.openSession(model)) {
        return session.generate(prompt);
    } // session auto-closed: API connection released even if exception thrown.

GENERAL PATTERN across all case studies:
  - Domain exceptions (business errors): unchecked (RuntimeException subclass).
  - Infrastructure exceptions (DB, network): caught at boundary, wrapped in domain exceptions.
  - Caller sees ONLY domain exceptions. Never sees "JdbcException" or "HttpException".
  - This is DIP applied to exceptions: high-level code depends on domain exception interface,
    not low-level infrastructure exceptions.
```

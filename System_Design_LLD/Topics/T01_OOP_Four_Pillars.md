# LLD Topic 01: OOP — The 4 Pillars
## Java + C++ Primary | Every Keyword Explained | MAANG Depth

---

> **WHY THIS MATTERS:**
> Every single LLD interview — URL shortener, Uber, PaymentGateway — is built on these 4 pillars.
> You cannot design classes without knowing Encapsulation, Abstraction, Inheritance, Polymorphism cold.
> Interviewers CHECK if you use `private` fields, `abstract` interfaces, proper inheritance.

---

## PILLAR 1: ENCAPSULATION

```
WHAT: Bundle data + behaviour into one unit. HIDE the data. Expose only safe operations.

ANALOGY: ATM machine.
  You don't see the cash storage mechanism inside.
  You only see buttons: deposit, withdraw, check balance.
  The internals are HIDDEN (encapsulated).

WHY HIDE DATA?
  Without encapsulation: any code can do account.balance = 999999 → BUG.
  With encapsulation: must go through deposit()/withdraw() → rules enforced.
```

### Java — Encapsulation

```java
// ── BankAccount.java ──────────────────────────────────────────────────────────

public class BankAccount {
    //  ↑ public  = this class is visible to ALL other classes
    //             (accessible from anywhere in the project)

    // FIELDS (data):
    private String owner;
    //  ↑ private = ONLY this class can access this field directly.
    //              No other class can do: account.owner (compile error)
    //              Enforces access through methods (getOwner())

    private double balance;
    //  ↑ private: same. No direct access from outside.
    //  ↑ double:  64-bit floating point number. Used for money here (simplification).
    //             Production: use BigDecimal instead (see CS09_Payment_Gateway.md).

    // CONSTRUCTOR:
    public BankAccount(String owner, double initialBalance) {
        //  ↑ Constructor: special method called when object is created.
        //    Same name as class. No return type.
        //    Called by: BankAccount acc = new BankAccount("Alice", 1000);

        if (initialBalance < 0) {
            throw new IllegalArgumentException("Balance cannot be negative");
            //  ↑ throw: creates and sends an exception object up the call stack.
            //  ↑ IllegalArgumentException: Java built-in exception for invalid arguments.
            //    Caller must handle it (try-catch) or it crashes the program.
        }
        this.owner   = owner;
        //  ↑ this.owner = the OBJECT's field (field named 'owner')
        //  ↑ owner (right side) = the CONSTRUCTOR PARAMETER named 'owner'
        //  ↑ this.: distinguishes "field" from "parameter" when they have the same name.
        this.balance = initialBalance;
    }

    // METHODS (behaviour):
    public void deposit(double amount) {
        //  ↑ public: accessible from outside.
        //  ↑ void: returns NOTHING. The method changes state but gives nothing back.
        //  ↑ double amount: parameter — the caller passes in the deposit amount.

        if (amount <= 0) {
            throw new IllegalArgumentException("Deposit must be positive. Got: " + amount);
        }
        this.balance += amount;
        //  ↑ += : shorthand for this.balance = this.balance + amount;
    }

    public void withdraw(double amount) {
        if (amount <= 0) throw new IllegalArgumentException("Must be positive");
        if (amount > this.balance) {
            throw new IllegalStateException("Insufficient funds: have " + balance + ", need " + amount);
            //  ↑ IllegalStateException: object is in wrong state for this operation.
            //    Different from IllegalArgument: the argument is valid, but the state is wrong.
        }
        this.balance -= amount;
        //  ↑ -= : shorthand for this.balance = this.balance - amount;
    }

    // GETTER: read-only access to private field
    public double getBalance() {
        return this.balance;
        //  ↑ return: gives a value back to the caller.
        //    Caller: double b = account.getBalance();
    }

    // NO SETTER FOR BALANCE: you can't do account.setBalance(99999).
    // Must go through deposit()/withdraw() → business rules enforced.

    public String getOwner() {
        return this.owner;
    }

    @Override
    //  ↑ @Override: annotation telling compiler "this method overrides a parent class method".
    //    Parent: Object (every Java class extends Object by default).
    //    toString() in Object returns "BankAccount@7a81197d" (ugly).
    //    We override it to return something readable.
    public String toString() {
        return "BankAccount{owner='" + owner + "', balance=" + balance + "}";
        //  ↑ String concatenation: "text" + variable → creates new String.
    }
}

// USAGE:
// BankAccount acc = new BankAccount("Alice", 1000.0);
// acc.deposit(500);           // OK: goes through method
// acc.withdraw(200);          // OK: checks rules
// double b = acc.getBalance(); // OK: 1300.0
// acc.balance = 99999;        // COMPILE ERROR: field is private
```

### C++ — Encapsulation

```cpp
// ── BankAccount.h ─────────────────────────────────────────────────────────────
#pragma once
//  ↑ #pragma once: "include this header file only once per compilation unit".
//    Prevents double-inclusion errors. Alternative: #ifndef / #define guards.

#include <string>
//  ↑ #include: paste the contents of that file here at compile time.
//    <string>: C++ standard library's string class.
//    Angle brackets <>: system/standard library headers.
//    Quotes "": your own project headers.

#include <stdexcept>
//  ↑ <stdexcept>: standard exceptions: std::invalid_argument, std::logic_error, etc.

class BankAccount {
//  ↑ class: defines a new type with data (members) and behaviour (methods).
//    By default in C++: everything is PRIVATE (unlike Java where default is package-private).

public:
//  ↑ public: everything below this label until next access specifier is public.
//    Three access specifiers: public, protected, private.
//    Must be explicit (unlike Java where each member has its own modifier).

    // CONSTRUCTOR: same name as class, no return type
    BankAccount(std::string owner, double initialBalance)
        : owner_(owner), balance_(initialBalance)
        //  ↑ Member Initializer List: initializes fields BEFORE constructor body runs.
        //    Syntax: : field1(value1), field2(value2)
        //    More efficient than assigning inside constructor body.
        //    REQUIRED for: const members, reference members, members with no default constructor.
    {
        if (initialBalance < 0) {
            throw std::invalid_argument("Balance cannot be negative");
            //  ↑ throw: same concept as Java. Sends exception up the call stack.
            //  ↑ std::invalid_argument: C++ standard exception for invalid arguments.
            //    Defined in <stdexcept>.
        }
    }

    void deposit(double amount) {
        //  ↑ void: returns nothing (C++ same as Java).
        if (amount <= 0)
            throw std::invalid_argument("Deposit must be positive");
        balance_ += amount;
        //  ↑ += : same as Java. balance_ = balance_ + amount;
    }

    void withdraw(double amount) {
        if (amount <= 0)
            throw std::invalid_argument("Must be positive");
        if (amount > balance_)
            throw std::logic_error("Insufficient funds");
            //  ↑ std::logic_error: for violations of logical preconditions.
        balance_ -= amount;
    }

    double getBalance() const {
        //  ↑ const (after parameter list): this method does NOT modify the object.
        //    "const method" = read-only. Can be called on const BankAccount objects.
        //    Good practice: mark ALL getter methods as const.
        return balance_;
    }

    std::string getOwner() const {
        return owner_;
    }

private:
//  ↑ private: everything below is accessible ONLY by this class's methods.
//    No other class, not even derived classes, can access private members directly.

    std::string owner_;
    //  ↑ Convention: trailing underscore (_) marks private member variables.
    //    This distinguishes field 'owner_' from parameter 'owner'.
    //    (Python uses self._owner, Java uses this.owner — different conventions)

    double balance_;
    //  ↑ double: 64-bit IEEE 754 floating point.
    //    For real money: use integer (paisa/cents) or a Decimal library.
};
//  ↑ Semicolon after class closing brace: REQUIRED in C++! Common mistake to forget.

// USAGE:
// BankAccount acc("Alice", 1000.0);    // Stack allocation (no 'new')
// BankAccount* acc = new BankAccount("Alice", 1000.0);  // Heap allocation
// acc.deposit(500);                    // OK
// acc.withdraw(200);                   // OK
// double b = acc.getBalance();         // OK: 1300.0
// acc.balance_ = 99999;               // COMPILE ERROR: private
```

---

## PILLAR 2: ABSTRACTION

```
WHAT: Hide HOW something works. Show only WHAT it does.
      Define an interface (contract) — caller doesn't care about implementation details.

ANALOGY: TV remote.
  You press "Volume Up" — you don't know how IR signals travel, how the TV decodes them.
  The HOW is hidden. You only see the WHAT (increase volume).

IN CODE:
  Abstract class / Interface = the "remote" (defines what operations exist).
  Concrete class = the actual implementation (the HOW inside the TV).
```

### Java — Abstraction

```java
// ── PaymentProcessor.java ─────────────────────────────────────────────────────

// INTERFACE (pure abstraction — no implementation at all):
public interface PaymentProcessor {
    //  ↑ interface: defines a CONTRACT. Only method signatures, no method bodies.
    //    ALL methods are implicitly: public abstract (no keyword needed in Java 8+).
    //    Classes that "implement" this interface MUST provide method bodies.

    boolean processPayment(double amount, String cardNumber);
    //  ↑ Method signature only. No body (no {}), just semicolon.
    //    boolean: return type — true=success, false=failure.
    //    String cardNumber: parameter for the card number.

    void refund(String transactionId);
    //  ↑ Another contract method. Any implementor must define this too.
}

// CONCRETE IMPLEMENTATION 1:
public class StripeProcessor implements PaymentProcessor {
    //  ↑ implements: "I will fulfill all methods defined in PaymentProcessor interface."
    //    Java compiler checks: if any interface method is missing → compile error.
    //    A class can implement MULTIPLE interfaces (unlike extends, which is one class only).

    private String apiKey;
    //  ↑ Stripe needs an API key to call their API. Encapsulated inside this class.

    public StripeProcessor(String apiKey) {
        this.apiKey = apiKey;
    }

    @Override
    public boolean processPayment(double amount, String cardNumber) {
        //  ↑ @Override: tells compiler this implements an interface method.
        //    Compiler checks: if method signature doesn't match interface → error.
        //    Good practice: always use @Override when implementing interface methods.
        System.out.println("Stripe: charging ₹" + amount + " to card " + cardNumber.substring(cardNumber.length() - 4));
        //  ↑ substring(n-4): show only last 4 digits of card (security practice).
        //  ↑ length() - 4: Java String method. length() returns total chars.
        // In real code: call Stripe's REST API here.
        return true; // Simulated success
    }

    @Override
    public void refund(String transactionId) {
        System.out.println("Stripe: refunding transaction " + transactionId);
    }
}

// CONCRETE IMPLEMENTATION 2:
public class RazorpayProcessor implements PaymentProcessor {
    @Override
    public boolean processPayment(double amount, String cardNumber) {
        System.out.println("Razorpay: processing ₹" + amount);
        return true;
    }

    @Override
    public void refund(String transactionId) {
        System.out.println("Razorpay: refunding " + transactionId);
    }
}

// CALLER — uses the INTERFACE, not the concrete class:
public class Checkout {
    private PaymentProcessor processor;
    //  ↑ Type is the INTERFACE, not Stripe or Razorpay.
    //    This class doesn't care WHICH processor — just that it follows the contract.
    //    This is called "programming to an interface" — a core OOP principle.

    public Checkout(PaymentProcessor processor) {
        //  ↑ Dependency Injection: caller passes in the implementation.
        //    Checkout doesn't create the processor itself.
        //    Makes testing easy: inject MockProcessor in tests.
        this.processor = processor;
    }

    public void pay(double amount, String cardNumber) {
        boolean success = processor.processPayment(amount, cardNumber);
        //  ↑ Polymorphism in action: which processPayment() runs depends on
        //    what object was injected (Stripe or Razorpay). Decided at runtime.
        if (success) System.out.println("Payment successful!");
        else         System.out.println("Payment failed.");
    }
}

// USAGE:
// Checkout checkout = new Checkout(new StripeProcessor("sk_test_abc123"));
// checkout.pay(999.0, "4111111111111111");
//
// To switch to Razorpay: just change constructor argument. Checkout code unchanged.
// checkout = new Checkout(new RazorpayProcessor());  // Zero changes to Checkout class!
```

### C++ — Abstraction (Pure Virtual Functions)

```cpp
// ── PaymentProcessor.h ────────────────────────────────────────────────────────

#pragma once
#include <string>
#include <memory>
//  ↑ <memory>: std::unique_ptr, std::shared_ptr (smart pointers).

// ABSTRACT BASE CLASS (C++'s equivalent of Java interface):
class PaymentProcessor {
//  ↑ C++ has no 'interface' keyword. Use abstract class with ONLY pure virtual methods.

public:
    virtual ~PaymentProcessor() = default;
    //  ↑ virtual destructor: REQUIRED for polymorphic base classes.
    //    Why? If you have: PaymentProcessor* p = new StripeProcessor();
    //    delete p; → without virtual destructor: only PaymentProcessor's destructor called.
    //    StripeProcessor's resources (apiKey etc.) are NOT freed → memory leak!
    //    With virtual destructor: correct derived destructor is called.
    //    Rule: "If a class has ANY virtual method, make destructor virtual."
    //  ↑ = default: compiler generates the default destructor body.

    virtual bool processPayment(double amount, const std::string& cardNumber) = 0;
    //  ↑ virtual: this method CAN be overridden in derived classes.
    //  ↑ = 0: "pure virtual" — this class provides NO implementation.
    //    Any class with even ONE pure virtual method is ABSTRACT.
    //    Abstract class CANNOT be instantiated: PaymentProcessor p; → compile error.
    //  ↑ const std::string&: pass string by const reference.
    //    Reference (&): no copy made → efficient for large strings.
    //    const: this function won't modify the string → safe for caller.

    virtual void refund(const std::string& transactionId) = 0;
    //  ↑ Another pure virtual method. Derived class MUST implement this.
};

// CONCRETE IMPLEMENTATION:
class StripeProcessor : public PaymentProcessor {
    //  ↑ : public PaymentProcessor: "StripeProcessor extends PaymentProcessor publicly".
    //    public inheritance: public members of base remain public in derived.
    //    (private inheritance: all base members become private in derived — rarely used)

public:
    explicit StripeProcessor(std::string apiKey) : apiKey_(std::move(apiKey)) {}
    //  ↑ explicit: prevents implicit conversion. Without it:
    //    void foo(StripeProcessor p); foo("sk_abc"); would silently compile!
    //    With explicit: must write foo(StripeProcessor("sk_abc")); — intentional.
    //  ↑ std::move: transfers ownership of the string (avoids copying).
    //    Move semantics: C++11 feature. Efficient for large objects.

    bool processPayment(double amount, const std::string& cardNumber) override {
        //  ↑ override: C++11 keyword. Same purpose as Java's @Override.
        //    Tells compiler: "This IS overriding a virtual method."
        //    Compiler error if you misspell the method name → prevents subtle bugs.
        std::cout << "Stripe: charging " << amount << " to card ending "
                  << cardNumber.substr(cardNumber.size() - 4) << std::endl;
        //  ↑ std::cout: standard output stream (like System.out.println).
        //  ↑ <<: stream insertion operator. Chains output.
        //  ↑ substr(n): returns substring starting at position n.
        //  ↑ size() - 4: last 4 chars of card number.
        //  ↑ std::endl: newline + flush. "\n" is faster (no flush) but endl is safer.
        return true;
    }

    void refund(const std::string& transactionId) override {
        std::cout << "Stripe: refunding " << transactionId << std::endl;
    }

private:
    std::string apiKey_;
};

// USAGE WITH SMART POINTERS (modern C++ — no raw new/delete):
// std::unique_ptr<PaymentProcessor> proc = std::make_unique<StripeProcessor>("sk_abc");
// proc->processPayment(999.0, "4111111111111111");
//  ↑ -> : dereference pointer + access member. ptr->method() = (*ptr).method()
//  ↑ unique_ptr: RAII — automatically calls destructor when goes out of scope. No memory leak.
//  ↑ make_unique: factory function for unique_ptr. Safer than "new" (exception-safe).
```

---

## PILLAR 3: INHERITANCE

```
WHAT: A class can INHERIT (reuse) fields and methods from a parent class.
      Child class (subclass) extends parent class (superclass).

ANALOGY: Vehicle → Car, Truck, Motorcycle.
  All vehicles have: speed, fuel, move(), stop().
  Car additionally has: doors, air_conditioning.
  Truck additionally has: payload_capacity, tow().
  
  Instead of copying speed/fuel/move()/stop() into every class: INHERIT from Vehicle.

IS-A RELATIONSHIP: Car IS-A Vehicle. Truck IS-A Vehicle.
  Before inheriting, ask: "Is a [Child] a type of [Parent]?" If yes → inheritance is valid.
  "A Car is a Vehicle" → ✓. "A Garage is a Vehicle" → ✗ (use composition instead).
```

### Java — Inheritance

```java
// ── Vehicle.java ──────────────────────────────────────────────────────────────

public abstract class Vehicle {
    //  ↑ abstract class: can have both abstract AND concrete methods.
    //    Cannot be instantiated directly: new Vehicle() → compile error.
    //    Subclasses must implement all abstract methods.
    //    Use when: you want to provide some default implementation + force some abstract methods.

    protected String brand;
    //  ↑ protected: accessible in this class AND in all subclasses.
    //    More permissive than private (subclasses can access).
    //    Less permissive than public (outside code cannot access directly).

    protected int speedKmh;    // Current speed in km/h
    protected int maxSpeedKmh; // Maximum allowed speed

    // CONSTRUCTOR:
    public Vehicle(String brand, int maxSpeedKmh) {
        this.brand       = brand;
        this.maxSpeedKmh = maxSpeedKmh;
        this.speedKmh    = 0;    // All vehicles start at rest (speed = 0)
    }

    // CONCRETE METHOD (has implementation, subclass inherits it):
    public void accelerate(int deltaKmh) {
        //  ↑ Not abstract: has a body. Every subclass gets this for free.
        speedKmh = Math.min(speedKmh + deltaKmh, maxSpeedKmh);
        //  ↑ Math.min(a, b): Java built-in. Returns smaller of a and b.
        //    Prevents speed from exceeding maxSpeed.
    }

    public void brake(int deltaKmh) {
        speedKmh = Math.max(0, speedKmh - deltaKmh);
        //  ↑ Math.max(a, b): returns larger of a and b.
        //    Prevents speed from going below 0 (negative speed meaningless).
    }

    // ABSTRACT METHOD (no body — subclass MUST implement):
    public abstract String getFuelType();
    //  ↑ abstract: no body, no {}. Just the signature + semicolon.
    //    Each vehicle subtype has different fuel: Car→petrol, ElectricCar→electric, Truck→diesel.
    //    Makes no sense to define at Vehicle level → abstract (force subclass to define).

    public abstract int getPassengerCapacity();

    // TEMPLATE METHOD PATTERN (uses abstract method internally):
    public String describe() {
        //  ↑ Concrete method that calls abstract methods.
        //    At runtime: the correct subclass version of abstract methods is called.
        return brand + " | Fuel: " + getFuelType()
               + " | Speed: " + speedKmh + "/" + maxSpeedKmh + " km/h"
               + " | Passengers: " + getPassengerCapacity();
    }
}

// ── Car.java ──────────────────────────────────────────────────────────────────

public class Car extends Vehicle {
    //  ↑ extends: "Car is a subclass of Vehicle". Inherits all non-private members.
    //    Java: single inheritance only (one class can extend only ONE class).
    //    But can implement MULTIPLE interfaces.

    private int doors;     // Cars have a specific number of doors (2, 4, 5)
    private boolean hasAC; // Does this car have air conditioning?

    public Car(String brand, int maxSpeedKmh, int doors, boolean hasAC) {
        super(brand, maxSpeedKmh);
        //  ↑ super(...): calls the PARENT class constructor.
        //    MUST be the FIRST statement in child constructor.
        //    Parent constructor runs first → sets brand and maxSpeedKmh.
        //    Then our constructor body runs → sets doors and hasAC.
        this.doors = doors;
        this.hasAC = hasAC;
    }

    @Override
    public String getFuelType() {
        return "Petrol";   // Car uses petrol (hardcoded for simplicity)
    }

    @Override
    public int getPassengerCapacity() {
        return doors == 2 ? 2 : 5;
        //  ↑ Ternary operator: condition ? value_if_true : value_if_false
        //    2-door car → 2 passengers. 4/5-door car → 5 passengers.
    }

    // CAR-SPECIFIC method (not in Vehicle):
    public void toggleAC() {
        hasAC = !hasAC;
        //  ↑ ! (NOT operator): flips boolean. true → false, false → true.
        System.out.println("AC is now: " + (hasAC ? "ON" : "OFF"));
    }
}

// ── ElectricCar.java ──────────────────────────────────────────────────────────

public class ElectricCar extends Car {
    //  ↑ Multi-level inheritance: ElectricCar → Car → Vehicle.
    //    ElectricCar inherits from Car, which inherits from Vehicle.
    //    Avoid going deeper than 3 levels (gets confusing).

    private int batteryPercent;

    public ElectricCar(String brand, int maxSpeedKmh, int doors) {
        super(brand, maxSpeedKmh, doors, true);
        //  ↑ super(...): calls Car's constructor (immediate parent).
        //    Electric cars always have AC (true for hasAC).
        batteryPercent = 100;
    }

    @Override
    public String getFuelType() {
        return "Electric";   // Overrides Car's "Petrol" → correct!
    }

    public void charge(int percent) {
        batteryPercent = Math.min(100, batteryPercent + percent);
        System.out.println("Charged to: " + batteryPercent + "%");
    }
}

// USAGE:
// Vehicle v1 = new Car("Toyota", 180, 4, true);
// Vehicle v2 = new ElectricCar("Tesla", 250, 4);
//  ↑ Both stored as Vehicle type (polymorphism) but ARE different objects.
//
// v1.accelerate(50);          // Inherited from Vehicle
// v1.describe();              // Calls getFuelType() → "Petrol" (Car's version)
// v2.describe();              // Calls getFuelType() → "Electric" (ElectricCar's version)
// System.out.println(v1.getFuelType()); // "Petrol"
// System.out.println(v2.getFuelType()); // "Electric"
```

### C++ — Inheritance

```cpp
// ── Vehicle.h ─────────────────────────────────────────────────────────────────
#pragma once
#include <string>
#include <algorithm>   // std::min, std::max
#include <iostream>

class Vehicle {
public:
    Vehicle(std::string brand, int maxSpeedKmh)
        : brand_(std::move(brand)), maxSpeedKmh_(maxSpeedKmh), speedKmh_(0) {}
    //  ↑ Initializer list: order matches declaration order in class body.
    //    std::move(brand): take ownership of string parameter → avoids copying.

    virtual ~Vehicle() = default;
    //  ↑ virtual destructor: mandatory for base classes in C++.
    //    If omitted and you delete derived through base pointer → undefined behavior.

    void accelerate(int delta) {
        speedKmh_ = std::min(speedKmh_ + delta, maxSpeedKmh_);
        //  ↑ std::min: from <algorithm>. Returns smaller of two values.
    }

    void brake(int delta) {
        speedKmh_ = std::max(0, speedKmh_ - delta);
        //  ↑ std::max: returns larger of two values.
    }

    // Pure virtual methods (C++ equivalent of Java abstract):
    virtual std::string getFuelType() const = 0;
    virtual int getPassengerCapacity() const = 0;

    // Concrete method using pure virtual (Template Method):
    std::string describe() const {
        return brand_ + " | Fuel: " + getFuelType()
               + " | Speed: " + std::to_string(speedKmh_)
               + "/" + std::to_string(maxSpeedKmh_);
        //  ↑ std::to_string(int): converts integer to string for concatenation.
        //    Unlike Java where "text" + 42 works, C++ requires explicit conversion.
    }

protected:
    //  ↑ protected: accessible in this class AND derived classes. Same as Java.
    std::string brand_;
    int speedKmh_;
    int maxSpeedKmh_;
};

// ── Car.h ─────────────────────────────────────────────────────────────────────
#pragma once
#include "Vehicle.h"

class Car : public Vehicle {
    //  ↑ : public Vehicle: public inheritance.
    //    public members of Vehicle remain public in Car.
    //    protected members of Vehicle remain protected in Car.
    //    C++ allows: public, protected, private inheritance (Java only has public).
    //    Always use 'public' for IS-A relationships.

public:
    Car(std::string brand, int maxSpeed, int doors, bool hasAC)
        : Vehicle(std::move(brand), maxSpeed), doors_(doors), hasAC_(hasAC) {}
        //  ↑ Vehicle(std::move(brand), maxSpeed): calls BASE class constructor.
        //    C++ equivalent of Java's super(brand, maxSpeed).
        //    Must be in initializer list (before constructor body).

    std::string getFuelType() const override { return "Petrol"; }
    //  ↑ override: C++11 keyword. Same as Java's @Override.
    //    Compile error if this doesn't actually override anything.
    //  ↑ const after (): this method doesn't modify the object.
    //    Both override AND const must match the base class declaration.

    int getPassengerCapacity() const override {
        return doors_ == 2 ? 2 : 5;
        //  ↑ Ternary: condition ? true_value : false_value. Same as Java.
    }

private:
    int  doors_;
    bool hasAC_;
};
```

---

## PILLAR 4: POLYMORPHISM

```
WHAT: "Many forms." One interface, many implementations.
      The SAME method call produces DIFFERENT results based on the actual object type.

TWO TYPES:
  1. COMPILE-TIME (static) polymorphism: method overloading, templates (C++)
  2. RUNTIME (dynamic) polymorphism: method overriding via virtual functions / interfaces

RUNTIME POLYMORPHISM is what we mean in LLD interviews.

ANALOGY: Shape.draw()
  Shape* s1 = new Circle();     s1.draw() → draws circle
  Shape* s2 = new Rectangle();  s2.draw() → draws rectangle
  Shape* s3 = new Triangle();   s3.draw() → draws triangle
  All called as shape.draw(), but different result each time.
```

### Java — Polymorphism

```java
// ── Polymorphism example ──────────────────────────────────────────────────────

import java.util.List;
import java.util.ArrayList;

abstract class Shape {
    abstract double area();           // Must be implemented by each shape
    abstract double perimeter();

    // Concrete method using abstract methods (Template Method):
    void printInfo() {
        System.out.printf("Area: %.2f | Perimeter: %.2f%n", area(), perimeter());
        //  ↑ printf: formatted print. %.2f = float with 2 decimal places.
        //  ↑ %n: platform-independent newline (use %n not \n in printf).
    }
}

class Circle extends Shape {
    private final double radius;
    //  ↑ final: field can NEVER be changed after construction.
    //    Circle's radius doesn't change → make it final (immutable).
    //    Good practice: make fields final whenever possible.

    Circle(double radius) { this.radius = radius; }

    @Override
    double area() {
        return Math.PI * radius * radius;
        //  ↑ Math.PI: Java constant = 3.14159... (double precision).
    }

    @Override
    double perimeter() { return 2 * Math.PI * radius; }
}

class Rectangle extends Shape {
    private final double width, height;

    Rectangle(double w, double h) { width = w; height = h; }

    @Override double area()      { return width * height; }
    @Override double perimeter() { return 2 * (width + height); }
}

// POLYMORPHISM IN ACTION:
public class PolymorphismDemo {
    public static void main(String[] args) {
        List<Shape> shapes = new ArrayList<>();
        //  ↑ List<Shape>: a list that holds Shape objects.
        //    Can hold Circle, Rectangle, Triangle — anything that extends Shape.
        //  ↑ ArrayList: dynamic array (grows as needed). Implements List interface.
        //  ↑ new ArrayList<>(): the <> (diamond operator) infers the type parameter.
        //    Full form: new ArrayList<Shape>() — same meaning.

        shapes.add(new Circle(5.0));
        shapes.add(new Rectangle(4.0, 6.0));
        shapes.add(new Circle(3.0));

        // POLYMORPHIC LOOP:
        for (Shape shape : shapes) {
            //  ↑ for-each loop: iterates over every element in the list.
            //    shape: current element (type Shape, but actual object varies).
            shape.printInfo();
            //  ↑ POLYMORPHISM: Java looks at the ACTUAL object type at runtime.
            //    If actual type is Circle: calls Circle.area() and Circle.perimeter()
            //    If actual type is Rectangle: calls Rectangle.area() and Rectangle.perimeter()
            //    This decision happens at RUNTIME (called "dynamic dispatch").
        }

        // Calculate total area:
        double totalArea = shapes.stream()
            //  ↑ .stream(): creates a Stream (pipeline for processing collections).
            //    Stream API: Java 8+. Functional programming style.
            .mapToDouble(Shape::area)
            //  ↑ mapToDouble: convert each Shape → double by calling area().
            //  ↑ Shape::area: METHOD REFERENCE. Same as: shape -> shape.area()
            //    Two ways to write same thing: lambda or method reference.
            .sum();
            //  ↑ .sum(): terminal operation. Adds all doubles together.

        System.out.printf("Total area: %.2f%n", totalArea);
    }
}
```

### C++ — Polymorphism (virtual dispatch)

```cpp
// ── Polymorphism in C++ ────────────────────────────────────────────────────────
#pragma once
#include <vector>
#include <memory>
#include <cmath>    // M_PI (or use std::numbers::pi in C++20)
#include <numeric>  // std::accumulate

class Shape {
public:
    virtual ~Shape() = default;
    virtual double area() const = 0;
    virtual double perimeter() const = 0;

    void printInfo() const {
        printf("Area: %.2f | Perimeter: %.2f\n", area(), perimeter());
        //  ↑ area() and perimeter() are virtual → correct derived version called.
        //    This is C++ DYNAMIC DISPATCH (same as Java's polymorphism).
        //    Mechanism: vtable (virtual table).
        //    Each class with virtual methods has a vtable (array of function pointers).
        //    Object has a vptr (pointer to its class's vtable).
        //    shape->area() → follow vptr → look up area entry in vtable → call it.
    }
};

class Circle final : public Shape {
    //  ↑ final: C++11 keyword. This class CANNOT be further subclassed.
    //    Circle is a "leaf" class — no one should extend it.
    //    Also allows compiler optimization: knows no further overrides exist.

public:
    explicit Circle(double radius) : radius_(radius) {}

    double area()      const override { return M_PI * radius_ * radius_; }
    double perimeter() const override { return 2.0 * M_PI * radius_; }

private:
    double radius_;
};

class Rectangle final : public Shape {
public:
    Rectangle(double w, double h) : width_(w), height_(h) {}

    double area()      const override { return width_ * height_; }
    double perimeter() const override { return 2.0 * (width_ + height_); }

private:
    double width_, height_;
};

// POLYMORPHISM IN ACTION:
void demo() {
    // MUST use pointers or references for polymorphism in C++!
    // WHY? C++ copies by value if you use Shape shape = Circle(5) → "object slicing"
    // (only Shape part is copied, Circle-specific data lost).
    // Pointer/reference: preserves the full derived object.
    std::vector<std::unique_ptr<Shape>> shapes;
    //  ↑ vector: C++ dynamic array (like Java's ArrayList).
    //  ↑ unique_ptr<Shape>: smart pointer. Owns the Shape object.
    //    Automatically deleted when removed from vector or vector is destroyed.
    //    No manual delete needed → no memory leaks.

    shapes.push_back(std::make_unique<Circle>(5.0));
    //  ↑ push_back: add to end of vector (like Java's list.add()).
    //  ↑ make_unique<Circle>(5.0): create a Circle with radius=5.0, wrap in unique_ptr.
    shapes.push_back(std::make_unique<Rectangle>(4.0, 6.0));
    shapes.push_back(std::make_unique<Circle>(3.0));

    // POLYMORPHIC LOOP:
    for (const auto& shape : shapes) {
        //  ↑ for (const auto& shape : shapes): range-based for loop (C++11).
        //  ↑ const: we won't modify the shape.
        //  ↑ auto: type inferred by compiler = unique_ptr<Shape>.
        //  ↑ &: reference to the element in the vector (no copy).
        shape->printInfo();
        //  ↑ shape is unique_ptr<Shape>. -> dereferences and calls method.
        //    DYNAMIC DISPATCH: actual type (Circle or Rectangle) determines which area() runs.
    }

    // Total area with std::accumulate:
    double total = std::accumulate(shapes.begin(), shapes.end(), 0.0,
        [](double sum, const std::unique_ptr<Shape>& s) {
            return sum + s->area();
        }
    );
    //  ↑ std::accumulate: sum all elements. From <numeric>.
    //    accumulate(begin, end, initial_value, binary_function)
    //    binary_function: takes (accumulated_so_far, next_element) → new accumulated value.
    //  ↑ Lambda: [](double sum, const unique_ptr<Shape>& s) { return sum + s->area(); }
    //    []: capture list. Empty = captures nothing from surrounding scope.
    //    (double sum, ...): parameters of the lambda (function body).
    //    { return sum + s->area(); }: body.
    printf("Total area: %.2f\n", total);
}
```

---

## KEY DIFFERENCES: Java vs C++

```
INHERITANCE:
  Java:  class Car extends Vehicle { ... }   (extends keyword, always public)
  C++:   class Car : public Vehicle { ... }  (colon + access specifier)

ABSTRACT METHOD:
  Java:  abstract double area();             (abstract keyword in class)
         Also: interface with all abstract methods
  C++:   virtual double area() const = 0;   (pure virtual = 0)

CONSTRUCTOR CHAINING:
  Java:  super(brand, maxSpeed);             (first line of constructor)
  C++:   : Vehicle(brand, maxSpeed) { }     (in initializer list before body)

OVERRIDE MARKER:
  Java:  @Override annotation               (checked by compiler)
  C++:   override keyword                   (C++11+, checked by compiler)

DESTRUCTOR:
  Java:  No destructors (GC handles memory)
  C++:   virtual ~ClassName() = default;    (MANDATORY for base classes)

POLYMORPHISM REQUIREMENT:
  Java:  Works through any reference (Vehicle v = new Car())
  C++:   MUST use pointer or reference. Value type → object slicing bug!
         Vehicle* v = new Car();  ← pointer works
         Vehicle v = Car();       ← OBJECT SLICING (Car-specific data lost!)

FINAL CLASS:
  Java:  public final class MyClass { }     (cannot be extended)
  C++:   class MyClass final { }            (C++11, cannot be extended)
```

---

## HOW THESE CONCEPTS APPEAR IN THE LLD CASE STUDIES

> Read this section AFTER reading each case study. It maps which pillar you see WHERE.

### ENCAPSULATION — Where it appears

```
CS01 URL Shortener:
  UrlEntry has private fields: original_url, short_code, click_count.
  click_count cannot be set directly from outside.
  Must call entry.record_click() which validates and increments.
  Without encapsulation: entry.click_count = 9999 (fake viral count) is trivially possible.

CS04 Uber (CS04_Uber.md):
  Trip._status is private. Cannot be changed by external code.
  Must call trip.start_trip() → trip.end_trip() → each validates the transition.
  FareCalculator._strategies is private. Only accessible via calculate().
  
CS06 YouTube (CS06_YouTube.md):
  Video._like_count and ._view_count are private.
  External code must call video.like() or video.record_view().
  record_view() enforces: only counts if watched > 30 seconds (anti-fraud).
  If public: anyone can set _view_count = 10_000_000 to fake viral videos.

CS09 Payment Gateway (CS09_Payment_Gateway.md):
  PaymentGatewayService._transactions is private dict.
  Enforces idempotency: if transaction already processed, return same result.
  External code cannot bypass idempotency by directly writing to _transactions.

CS11 AI Systems (CS11_AI_Systems.md):
  LLMService._conversation_history is private.
  Enforces rolling window: old messages auto-dropped to fit context window.
  Caller cannot manually push stale messages that would overflow the model.

PATTERN TO REMEMBER: Every field that represents a counter, status, or history
  should be private. Only expose through methods that enforce business rules.
```

### ABSTRACTION — Where it appears

```
CS04 Uber:
  IFareStrategy (abstract interface): calculate(distance, duration, surge) → Decimal.
  UberService only calls strategy.calculate(). 
  Does NOT know if it's SurgePricingStrategy or NormalPricingStrategy.
  Adding CorporatePricingStrategy: zero changes to UberService.

CS05 Netflix (CS05_Netflix.md):
  IStreamingSession abstract class hides: CDN selection, DRM, codec negotiation.
  Caller calls session.start_streaming(). Doesn't know complexity inside.

CS09 Payment Gateway:
  IPaymentProcessor interface: charge(), refund().
  PaymentGatewayService calls processor.charge().
  Doesn't know if it's StripeCardProcessor, RazorpayUPIProcessor, or WalletProcessor.

CS11 AI Systems:
  ILLMAdapter abstract interface: generate(prompt, params) → str.
  LLMService calls adapter.generate(). Same call works for GPT-4, Claude, Gemini.
  Switching provider = swap the adapter. LLMService unchanged.

PATTERN TO REMEMBER: "What might we swap?" → define an abstract interface.
  Payment provider, pricing strategy, LLM model, streaming protocol = all swappable.
```

### INHERITANCE — Where it appears

```
CS04 Uber:
  NormalPricingStrategy, SurgePricingStrategy, FlatRatePricingStrategy
  all inherit from IFareStrategy. Share: the contract. Differ: the algorithm.

CS05 Netflix:
  ContentItem is abstract base. Episode and Series inherit from it.
  Episode.get_stream_url() → returns a direct stream URL.
  Series.get_stream_url() → aggregates episodes → returns playlist.
  Common inherited: title, description, is_available(), get_content_info().
  
CS06 YouTube:
  VideoVariant objects share the same structure (resolution, bitrate, codec, url).
  Strategies inherit from IAdaptiveBitrateStrategy.

CS10 MakeMyTrip (CS10_MakeMyTrip.md):
  FlexiblePolicy, ModeratePolicy, StrictPolicy all inherit from ICancellationPolicy.
  Shared: the policy contract (calculate_refund).
  Differ: the refund percentage per time window (24h, 48h cutoffs).

JAVA/C++ SPECIFIC:
  In Java: abstract class Vehicle → Car, Truck, ElectricCar.
  In C++: class Vehicle with pure virtual methods (= 0) → Car : public Vehicle.
  Always use 'override' keyword in C++ to catch typos at compile time.
```

### POLYMORPHISM — Where it appears

```
CS04 Uber:
  fare_calculator.calculate(distance, duration, surge_multiplier):
  Called identically for normal and surge pricing.
  At runtime: correct subclass's calculate() is invoked (dynamic dispatch).

CS05 Netflix:
  for content in library: content.is_available()
  Works for both Episode (checks content rights) and Series (checks if any episode available).
  Same method call, different result. Classic runtime polymorphism.

CS07 Google Search (CS07_Google_Search.md):
  Ranker calls entry.doc_id, entry.term_frequency on PostingEntry objects.
  Works for title entries, body entries, anchor text entries — all PostingEntry subtypes.
  No if/else type-checking. Polymorphism handles the variation.

CS09 Payment Gateway:
  for processor in _processors: result = processor.charge(amount, card)
  Works for CardProcessor, UPIProcessor, WalletProcessor.
  Same loop, different execute. This IS runtime polymorphism.

CS11 AI Systems:
  llm_service.generate(prompt) → internally calls adapter.generate()
  adapter could be OpenAIAdapter or AnthropicAdapter.
  Same call at the LLMService level, different HTTP API called underneath.

JAVA/C++ SPECIFIC:
  Java: polymorphism through any reference (Vehicle v = new Car() works).
  C++: MUST use pointer or reference! (Vehicle* v = new Car() or Vehicle& v = car).
  Value type in C++: Vehicle v = Car() → OBJECT SLICING → Car-specific data LOST!
```

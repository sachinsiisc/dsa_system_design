# LLD Prerequisites — Object-Oriented Design & SOLID Principles
## Beginner-Friendly with Real Examples → MAANG Depth

---

## WHAT IS LLD?

```
HLD: What components exist and how they communicate.
     (Load balancer, DB, cache, message queue — the big boxes)

LLD: What code exists INSIDE each component.
     (Classes, methods, relationships, design patterns — the internal code structure)

MAANG LLD interviews last 45-60 minutes.
You must:
1. Gather requirements
2. Identify entities (nouns → classes)
3. Identify behaviours (verbs → methods)
4. Draw class diagram (relationships)
5. Write clean, runnable code
6. Handle edge cases
```

---

## TOPIC 1: Object-Oriented Programming — The Full Picture

### 1.1 The 4 Pillars

```python
# ── ENCAPSULATION ─────────────────────────────────────────────────────────────
# Bundle data (attributes) and behaviour (methods) together.
# Hide internal state → only expose what's needed.

class BankAccount:
    def __init__(self, owner, initial_balance):
        self._owner   = owner              # "protected" by convention
        self.__balance = initial_balance   # "private" (name-mangled to _BankAccount__balance)
    
    def deposit(self, amount):
        if amount <= 0:
            raise ValueError("Deposit must be positive")
        self.__balance += amount
    
    def withdraw(self, amount):
        if amount <= 0:
            raise ValueError("Withdrawal must be positive")
        if amount > self.__balance:
            raise ValueError("Insufficient funds")
        self.__balance -= amount
    
    @property
    def balance(self):           # read-only access
        return self.__balance
    
    # WHY: External code can't do account.__balance = 999999.
    # Must go through withdraw/deposit → business rules enforced.

acc = BankAccount("Alice", 1000)
acc.deposit(500)
acc.withdraw(200)
print(acc.balance)   # 1300
# acc.__balance = 999999  → AttributeError (name mangling protects it)
```

```python
# ── ABSTRACTION ───────────────────────────────────────────────────────────────
# Hide implementation details. Show only what user needs to know.
# "What" it does, not "How" it does it.

from abc import ABC, abstractmethod

class PaymentProcessor(ABC):
    """Abstract interface. Caller just calls process_payment(). Doesn't care HOW."""
    
    @abstractmethod
    def process_payment(self, amount: float, card_number: str) -> bool:
        """Returns True if successful."""
        pass
    
    @abstractmethod
    def refund(self, transaction_id: str, amount: float) -> bool:
        pass

class StripeProcessor(PaymentProcessor):
    def process_payment(self, amount, card_number):
        # Stripe-specific API calls
        print(f"Processing ${amount} via Stripe API...")
        return True   # simplified
    
    def refund(self, transaction_id, amount):
        print(f"Refunding ${amount} via Stripe for txn {transaction_id}")
        return True

class PayPalProcessor(PaymentProcessor):
    def process_payment(self, amount, card_number):
        print(f"Processing ${amount} via PayPal...")
        return True
    
    def refund(self, transaction_id, amount):
        print(f"Refunding ${amount} via PayPal")
        return True

# Caller code doesn't change if we swap Stripe → PayPal:
def checkout(processor: PaymentProcessor, amount, card):
    return processor.process_payment(amount, card)

# Works with any processor:
checkout(StripeProcessor(), 99.99, "4111...")
checkout(PayPalProcessor(), 99.99, "4111...")
```

```python
# ── INHERITANCE ───────────────────────────────────────────────────────────────
# Child class inherits properties and methods from parent.
# Represents "IS-A" relationship.

class Vehicle:
    def __init__(self, make, model, year):
        self.make  = make
        self.model = model
        self.year  = year
    
    def start(self):
        print(f"{self.make} {self.model} started")
    
    def __str__(self):
        return f"{self.year} {self.make} {self.model}"

class Car(Vehicle):
    def __init__(self, make, model, year, num_doors):
        super().__init__(make, model, year)  # call parent constructor
        self.num_doors = num_doors
    
    def open_trunk(self):
        print("Trunk opened")

class ElectricCar(Car):
    def __init__(self, make, model, year, num_doors, battery_kwh):
        super().__init__(make, model, year, num_doors)
        self.battery_kwh = battery_kwh
    
    def start(self):  # OVERRIDE parent method
        print(f"{self.make} {self.model} silently started (electric)")
    
    def charge(self):
        print(f"Charging {self.battery_kwh} kWh battery...")

tesla = ElectricCar("Tesla", "Model 3", 2024, 4, 75)
tesla.start()       # Calls ElectricCar.start() (overridden)
tesla.open_trunk()  # Inherited from Car
print(tesla)        # Inherited from Vehicle.__str__

# IS-A relationships:
# ElectricCar IS-A Car. Car IS-A Vehicle. ElectricCar IS-A Vehicle.
isinstance(tesla, ElectricCar)  # True
isinstance(tesla, Car)          # True
isinstance(tesla, Vehicle)      # True
```

```python
# ── POLYMORPHISM ──────────────────────────────────────────────────────────────
# Same interface, different behaviour.
# "Poly" = many, "Morphism" = forms.

class Shape(ABC):
    @abstractmethod
    def area(self) -> float: pass
    
    @abstractmethod
    def perimeter(self) -> float: pass

class Circle(Shape):
    def __init__(self, radius):
        self.radius = radius
    
    def area(self): return 3.14159 * self.radius ** 2
    def perimeter(self): return 2 * 3.14159 * self.radius

class Rectangle(Shape):
    def __init__(self, width, height):
        self.width = width
        self.height = height
    
    def area(self): return self.width * self.height
    def perimeter(self): return 2 * (self.width + self.height)

class Triangle(Shape):
    def __init__(self, a, b, c):
        self.a, self.b, self.c = a, b, c
    
    def area(self):
        s = (self.a + self.b + self.c) / 2  # Heron's formula
        return (s * (s-self.a) * (s-self.b) * (s-self.c)) ** 0.5
    
    def perimeter(self): return self.a + self.b + self.c

# Polymorphism: same interface (area, perimeter), different shapes
def print_shape_info(shapes: list):
    for shape in shapes:
        print(f"{type(shape).__name__}: area={shape.area():.2f}, perimeter={shape.perimeter():.2f}")

shapes = [Circle(5), Rectangle(4, 6), Triangle(3, 4, 5)]
print_shape_info(shapes)
# → Circle: area=78.54, perimeter=31.42
# → Rectangle: area=24.00, perimeter=20.00
# → Triangle: area=6.00, perimeter=12.00
```

---

## TOPIC 2: SOLID Principles — The Rules for Good Code

### S — Single Responsibility Principle

```python
# WRONG: One class doing too many things
class UserService_WRONG:
    def create_user(self, name, email, password): ...
    def send_welcome_email(self, user): ...          # Email concern
    def generate_pdf_report(self, users): ...        # Reporting concern
    def save_to_database(self, user): ...            # Persistence concern
    def validate_email_format(self, email): ...      # Validation concern

# If email library changes → UserService must change.
# If PDF library changes → UserService must change.
# UserService changes for MANY different reasons → brittle.

# CORRECT: Each class has ONE reason to change
class UserService:
    def __init__(self, repository, email_service):
        self._repo  = repository
        self._email = email_service
    
    def create_user(self, name, email, password):
        if not self._validate_email(email):
            raise ValueError(f"Invalid email: {email}")
        user = User(name, email, password)
        self._repo.save(user)
        self._email.send_welcome(user)
        return user
    
    def _validate_email(self, email):
        return '@' in email and '.' in email.split('@')[-1]

class UserRepository:
    def save(self, user): ...        # Only knows about DB storage
    def find_by_id(self, id): ...

class EmailService:
    def send_welcome(self, user): ...  # Only knows about emails
    def send_reset(self, user): ...
```

### O — Open/Closed Principle

```python
# Open for extension, Closed for modification.
# Add new behaviour WITHOUT modifying existing code.

# WRONG: Every new payment type requires modifying this function
def process_payment_WRONG(type, amount):
    if type == 'credit_card':
        # credit card logic
        pass
    elif type == 'paypal':
        # paypal logic
        pass
    elif type == 'crypto':    # NEW TYPE: must modify function
        pass
    # Add bitcoin? Modify again. Risky.

# CORRECT: Each payment type is its own class. No modification needed for new types.
class PaymentStrategy(ABC):
    @abstractmethod
    def pay(self, amount: float) -> bool: pass

class CreditCardPayment(PaymentStrategy):
    def __init__(self, card_number, cvv):
        self.card_number = card_number
        self.cvv = cvv
    def pay(self, amount):
        print(f"Charging ${amount} to card {self.card_number[-4:]}")
        return True

class PayPalPayment(PaymentStrategy):
    def __init__(self, email):
        self.email = email
    def pay(self, amount):
        print(f"Sending ${amount} via PayPal to {self.email}")
        return True

class CryptoPayment(PaymentStrategy):   # NEW type: just add a class, modify nothing
    def __init__(self, wallet_address):
        self.wallet = wallet_address
    def pay(self, amount):
        print(f"Transferring ${amount} crypto to {self.wallet}")
        return True

class ShoppingCart:
    def checkout(self, amount, payment: PaymentStrategy):
        return payment.pay(amount)

cart = ShoppingCart()
cart.checkout(99.99, CreditCardPayment("4111111111111234", "123"))
cart.checkout(50.00, CryptoPayment("0x1234..."))  # No changes to ShoppingCart!
```

### L — Liskov Substitution Principle

```python
# Subclass must be substitutable for its parent without breaking the program.
# Behavioural contract of parent must be honoured by child.

# VIOLATION:
class Bird:
    def fly(self): print("Flying!")

class Penguin(Bird):
    def fly(self):
        raise NotImplementedError("Penguins can't fly!")  # VIOLATION!
        # Code that calls bird.fly() breaks when given a Penguin.

# FIX: Correct the hierarchy
class Bird:
    def move(self): pass  # General movement
    def eat(self): pass

class FlyingBird(Bird):
    def move(self): print("Flying!")
    def fly(self): print("Flying!")

class FlightlessBird(Bird):
    def move(self): print("Walking!")

class Eagle(FlyingBird): pass
class Penguin(FlightlessBird): pass

# Now any Bird subtype works for move():
def make_bird_move(bird: Bird):
    bird.move()  # Works for Eagle and Penguin ✓

# Real-world example that MATTERS in interviews:
class Rectangle:
    def __init__(self, width, height):
        self._width  = width
        self._height = height
    
    @property
    def width(self): return self._width
    @width.setter
    def width(self, w): self._width = w
    
    @property
    def height(self): return self._height
    @height.setter
    def height(self, h): self._height = h
    
    def area(self): return self._width * self._height

class Square(Rectangle):  # Square IS-A Rectangle? Mathematically yes. In code: VIOLATION!
    @Rectangle.width.setter
    def width(self, w):
        self._width = w
        self._height = w   # Force equal sides — BREAKS LSP!
    
    @Rectangle.height.setter
    def height(self, h):
        self._width = h
        self._height = h

def test_rectangle(rect: Rectangle):
    rect.width = 5
    rect.height = 10
    assert rect.area() == 50, f"Expected 50, got {rect.area()}"  # FAILS for Square!

r = Rectangle(4, 6)
test_rectangle(r)   # ✓

s = Square(4, 4)
test_rectangle(s)   # ✗ area = 10×10=100, not 50. Square violates LSP!

# Fix: Don't inherit. Use composition or separate hierarchy.
```

### I — Interface Segregation Principle

```python
# Don't force classes to implement methods they don't need.
# Many small interfaces > one large interface.

# WRONG: Fat interface
class Worker_WRONG(ABC):
    @abstractmethod
    def work(self): pass
    
    @abstractmethod
    def eat(self): pass
    
    @abstractmethod
    def sleep(self): pass

class Robot(Worker_WRONG):
    def work(self): print("Working...")
    def eat(self): raise NotImplementedError("Robots don't eat!")  # FORCED to implement!
    def sleep(self): raise NotImplementedError("Robots don't sleep!")

# CORRECT: Segregated interfaces
class Workable(ABC):
    @abstractmethod
    def work(self): pass

class Eatable(ABC):
    @abstractmethod
    def eat(self): pass

class Sleepable(ABC):
    @abstractmethod
    def sleep(self): pass

class HumanWorker(Workable, Eatable, Sleepable):
    def work(self):  print("Human working")
    def eat(self):   print("Human eating")
    def sleep(self): print("Human sleeping")

class RobotWorker(Workable):   # Only implements what it needs
    def work(self): print("Robot working")

# Practical example in ML systems:
class ModelPredictor(ABC):
    @abstractmethod
    def predict(self, input): pass

class ModelTrainable(ABC):
    @abstractmethod
    def train(self, data, labels): pass

class ModelSaveable(ABC):
    @abstractmethod
    def save(self, path): pass

class FullModel(ModelPredictor, ModelTrainable, ModelSaveable):
    def predict(self, input): ...
    def train(self, data, labels): ...
    def save(self, path): ...

class InferenceOnlyModel(ModelPredictor):  # Read-only replica, can't train
    def predict(self, input): ...
```

### D — Dependency Inversion Principle

```python
# High-level modules should NOT depend on low-level modules.
# Both should depend on ABSTRACTIONS (interfaces).

# WRONG: High-level OrderService directly depends on low-level MySQLDatabase
class MySQLDatabase_WRONG:
    def save_order(self, order): print(f"Saving to MySQL: {order}")

class OrderService_WRONG:
    def __init__(self):
        self.db = MySQLDatabase_WRONG()   # ← HARDCODED dependency!
    
    def place_order(self, order):
        # business logic...
        self.db.save_order(order)

# Want to switch to PostgreSQL? Must rewrite OrderService. 
# Want to test? Must use real MySQL. No mocking possible.

# CORRECT: Both depend on abstraction
class Database(ABC):
    @abstractmethod
    def save_order(self, order): pass
    
    @abstractmethod
    def get_order(self, order_id): pass

class MySQLDatabase(Database):
    def save_order(self, order): print(f"MySQL: saving {order}")
    def get_order(self, order_id): return f"order_{order_id}"

class PostgreSQLDatabase(Database):
    def save_order(self, order): print(f"PostgreSQL: saving {order}")
    def get_order(self, order_id): return f"order_{order_id}"

class InMemoryDatabase(Database):   # For testing!
    def __init__(self):
        self._store = {}
    def save_order(self, order):
        self._store[order['id']] = order
    def get_order(self, order_id):
        return self._store.get(order_id)

class OrderService:
    def __init__(self, db: Database):   # ← Inject abstraction
        self.db = db
    
    def place_order(self, order):
        # business logic (validate, calculate total, etc.)
        self.db.save_order(order)

# Production:
service = OrderService(MySQLDatabase())
# Testing:
service = OrderService(InMemoryDatabase())
# Migration to Postgres:
service = OrderService(PostgreSQLDatabase())   # zero changes to OrderService!
```

---

## TOPIC 3: UML Class Diagrams — Reading and Writing

```
CLASS DIAGRAM NOTATION:

ClassName
─────────
- private_attr: type
# protected_attr: type
+ public_attr: type
─────────
- _private_method(): return_type
+ public_method(param: type): return_type

RELATIONSHIPS:

──────►  Association: "uses"  (A has a reference to B)
─────◆   Aggregation: "has-a" (weak, B can exist without A)
─────◆   Composition: "part-of" (strong, B dies with A)
─────▷   Inheritance: "is-a"
- - - ▷  Implements: "implements interface"

EXAMPLE — Order Management System:

KEY RULE: A class defines BEHAVIOUR (methods), not just attributes.
          Attributes = what it HAS.  Methods = what it CAN DO.

[Customer]                   [Order]                      [OrderItem]
──────────                   ───────                      ──────────
- id: int                    - id: int                    - id: int
- name: str                  - customer: Customer         - product: Product
- email: str                 - items: List[OrderItem]     - quantity: int
- address: str               - status: OrderStatus        - unit_price: float
──────────                   - created_at: datetime       ──────────────────
+ place_order(): Order        ───────────────────────      + subtotal(): float
+ cancel_order(id): bool      + add_item(item): void       + apply_discount(pct): float
+ get_order_history(): list   + remove_item(id): void      + to_dict(): dict
+ update_address(a): void     + calculate_total(): float
+ is_premium(): bool          + cancel(): bool
                              + ship(): bool
                              + get_status(): OrderStatus

[Product]
─────────
- id: int
- name: str
- price: float
- stock: int
─────────
+ is_available(qty): bool
+ reserve(qty): bool
+ restock(qty): void
+ apply_discount(pct): float

Customer 1 ──────► * Order      (one customer has many orders)
Order 1 ──────◆ * OrderItem     (composition: items deleted with order)
OrderItem * ──────► 1 Product   (association: product exists independently)

[OrderStatus]  ← Enum: PENDING, CONFIRMED, SHIPPED, DELIVERED, CANCELLED

WHY BEHAVIOUR MATTERS:
  Customer.place_order()    → encapsulates order creation logic
  Customer.is_premium()     → business rule lives IN Customer, not in the caller
  Order.calculate_total()   → knows its own items, can sum them
  Order.cancel()            → enforces rules (can't cancel a SHIPPED order)
  Product.is_available()    → stock check logic belongs to Product
  OrderItem.subtotal()      → unit_price × quantity; caller doesn't care HOW
```

---

## TOPIC 4: Design Patterns — The 23 GoF Patterns

### 4.1 When to Use Which Pattern

```
CREATIONAL (How to create objects):
  Singleton    → Need exactly ONE instance (logger, config, thread pool)
  Factory      → Create object without knowing exact class (PaymentProcessor for card type)
  Abstract Factory → Create families of related objects (UI theme: light/dark)
  Builder      → Complex object with many optional parameters (QueryBuilder, Pizza)
  Prototype    → Clone expensive object (game level, document template)

STRUCTURAL (How to compose objects):
  Adapter      → Wrap incompatible interface (old API → new interface)
  Decorator    → Add behaviour dynamically without subclassing (Coffee + milk + sugar)
  Facade       → Simplify complex subsystem with one interface (HomeTheaterFacade)
  Proxy        → Control access (lazy loading, caching, logging, auth check)
  Composite    → Tree structures (file system, UI components)
  Flyweight    → Share common state across many objects (game characters)
  Bridge       → Decouple abstraction from implementation

BEHAVIORAL (How objects communicate):
  Strategy     → Interchangeable algorithms (sort strategy, payment strategy)
  Observer     → Event notification (EventEmitter, pub/sub)
  Command      → Encapsulate request as object (undo/redo, macros)
  Iterator     → Sequential access without exposing structure
  State        → Behaviour changes with state (order: pending→shipped→delivered)
  Template Method → Define skeleton, subclasses fill details
  Chain of Responsibility → Pass request along chain (middleware)
```

---

## TOPIC 5: Key Design Patterns with Full Code

See `00_Design_Patterns/` for all 10 most-used patterns with:
- When to use
- Real-world example
- Full runnable code
- Pros and cons
- MAANG interview hooks

---

## TOPIC 6: LLD Keywords — Complete Categorized Reference

```
CATEGORY MAP:
  A. Class Definition Keywords   → class, ABC, @abstractmethod, Enum, @dataclass
  B. Access Modifiers            → public, _protected, __private, @property
  C. Decorators                  → @staticmethod, @classmethod, @property, @abstractmethod, @override
  D. Dunder / Magic Methods      → __init__, __str__, __repr__, __eq__, __hash__, __len__, __contains__
  E. Inheritance Keywords        → super(), isinstance(), issubclass(), MRO
  F. Relationship Keywords       → IS-A, HAS-A (aggregation/composition), USES-A (dependency)
  G. Type Hints                  → -> type, Optional, List, Dict, Union, Protocol
```

---

### A. CLASS DEFINITION KEYWORDS

```python
# ── 1. class ──────────────────────────────────────────────────────────────────
# Creates a blueprint. Bundles state (attributes) + behaviour (methods).

class Dog:
    species = "Canis lupus"   # class attribute (shared across ALL instances)

    def __init__(self, name, breed):
        self.name  = name     # instance attribute (unique per object)
        self.breed = breed

    def bark(self):
        return f"{self.name} says Woof!"

d = Dog("Rex", "Labrador")
print(d.bark())          # Rex says Woof!
print(Dog.species)       # Canis lupus  (accessed on the class itself)

# ── 2. ABC  (Abstract Base Class) ─────────────────────────────────────────────
# ABC = a contract. You CANNOT instantiate it. Forces subclasses to implement methods.
# Use ABC when you want a shared interface with NO default logic.

from abc import ABC, abstractmethod

class Notification(ABC):         # Abstract Base Class
    @abstractmethod
    def send(self, message: str) -> bool:
        """All subclasses MUST implement this."""
        pass

    def log(self, msg):          # Concrete method — subclasses INHERIT this free
        print(f"[LOG] {msg}")

class EmailNotification(Notification):
    def send(self, message):
        print(f"Email: {message}")
        return True

class SMSNotification(Notification):
    def send(self, message):
        print(f"SMS: {message}")
        return True

# n = Notification()  ← TypeError: Can't instantiate abstract class
e = EmailNotification()
e.send("Order confirmed!")   # Email: Order confirmed!
e.log("sent via email")      # [LOG] sent via email  (inherited free)

# ── 3. Enum ───────────────────────────────────────────────────────────────────
# Named constants. Used for fixed sets of values (status, types, roles).
# Prevent magic strings like "pending", "PENDING", "Pending" — use Enum instead.

from enum import Enum, auto

class OrderStatus(Enum):
    PENDING   = auto()   # auto() assigns 1, 2, 3 ... automatically
    CONFIRMED = auto()
    SHIPPED   = auto()
    DELIVERED = auto()
    CANCELLED = auto()

class UserRole(Enum):
    ADMIN    = "admin"
    CUSTOMER = "customer"
    SELLER   = "seller"

status = OrderStatus.PENDING
print(status)           # OrderStatus.PENDING
print(status.name)      # PENDING
print(status.value)     # 1
print(status == OrderStatus.PENDING)  # True

# Usage in business logic:
def can_cancel(status: OrderStatus) -> bool:
    return status in (OrderStatus.PENDING, OrderStatus.CONFIRMED)
    # NOT: status == "pending" — that's error-prone

# ── 4. @dataclass ─────────────────────────────────────────────────────────────
# Auto-generates __init__, __repr__, __eq__ from field declarations.
# Use for simple data containers (DTOs, Value Objects).

from dataclasses import dataclass, field
from typing import List

@dataclass
class Address:
    street: str
    city:   str
    pin:    str

@dataclass
class Product:
    id:    int
    name:  str
    price: float
    tags:  List[str] = field(default_factory=list)  # mutable default needs field()

    def discounted_price(self, pct: float) -> float:
        return self.price * (1 - pct / 100)

p = Product(1, "Laptop", 999.99, ["electronics", "sale"])
print(p)                 # Product(id=1, name='Laptop', price=999.99, tags=[...])
print(p == Product(1, "Laptop", 999.99, ["electronics", "sale"]))  # True (auto __eq__)
```

---

### B. ACCESS MODIFIERS

```python
# Python doesn't have true keywords for access control.
# Convention-based: naming prefix signals intent.

class BankAccount:
    MAX_WITHDRAWAL = 50_000   # UPPER_CASE = constant (don't change this)

    def __init__(self, owner, balance):
        self.owner    = owner        # PUBLIC  — anyone can read/write
        self._balance = balance      # PROTECTED — "please don't touch from outside"
                                     #   (convention only; still accessible)
        self.__pin    = "0000"       # PRIVATE — name-mangled to _BankAccount__pin
                                     #   Accessing externally is very hard (by design)

    # ── @property — controlled read access to private state ───────────────────
    @property
    def balance(self):               # Getter — called like attribute: acc.balance
        return self._balance

    @balance.setter
    def balance(self, amount):       # Setter — called like: acc.balance = 500
        if amount < 0:
            raise ValueError("Balance cannot be negative")
        self._balance = amount

    @balance.deleter
    def balance(self):               # Deleter — called like: del acc.balance
        raise AttributeError("Cannot delete balance")

acc = BankAccount("Alice", 1000)
print(acc.owner)          # Alice    (public — fine)
print(acc._balance)       # 1000     (protected — works but bad practice)
# print(acc.__pin)        # AttributeError — name-mangled
print(acc._BankAccount__pin)  # "0000" — accessible if you REALLY need to (testing)

acc.balance = 1500        # calls setter → validated
print(acc.balance)        # 1500     (calls getter)
```

---

### C. DECORATORS

```python
# Decorators modify or wrap a function/method without changing its source code.

from abc import ABC, abstractmethod

class MathUtils:

    # ── @staticmethod ─────────────────────────────────────────────────────────
    # No access to class (cls) or instance (self).
    # Pure utility. Logically belongs to the class but doesn't need its state.

    @staticmethod
    def add(a: int, b: int) -> int:
        return a + b

    @staticmethod
    def is_prime(n: int) -> bool:
        if n < 2: return False
        for i in range(2, int(n**0.5) + 1):
            if n % i == 0: return False
        return True

print(MathUtils.add(3, 4))       # 7  (called on class, no instance needed)
print(MathUtils.is_prime(17))    # True

# ── @classmethod ──────────────────────────────────────────────────────────────
# Receives the CLASS (cls) as first argument, not the instance.
# Used as alternative constructors (named constructors / factory methods).

class User:
    def __init__(self, name, email, role="customer"):
        self.name  = name
        self.email = email
        self.role  = role

    @classmethod
    def from_dict(cls, data: dict) -> "User":        # Alternative constructor
        return cls(data["name"], data["email"], data.get("role", "customer"))

    @classmethod
    def create_admin(cls, name, email) -> "User":    # Named constructor
        return cls(name, email, role="admin")

    def __repr__(self):
        return f"User({self.name}, {self.role})"

u1 = User.from_dict({"name": "Alice", "email": "a@b.com"})
u2 = User.create_admin("Bob", "bob@admin.com")
print(u1)   # User(Alice, customer)
print(u2)   # User(Bob, admin)

# ── @abstractmethod ───────────────────────────────────────────────────────────
# Marks a method as "must be overridden". Shown in Section A above.
# Combine with @property for abstract properties:

class Shape(ABC):
    @property
    @abstractmethod
    def area(self) -> float: pass   # Subclass MUST provide a property named area

class Circle(Shape):
    def __init__(self, r): self.r = r

    @property
    def area(self) -> float:        # Must use @property here too
        return 3.14159 * self.r ** 2

c = Circle(5)
print(c.area)   # 78.53975 (accessed as attribute, not c.area())

# ── @override (Python 3.12+) ──────────────────────────────────────────────────
# Documents intent: "I am intentionally overriding a parent method."
# Catches typos at static analysis time (mypy, pyright will warn if no parent method).

from typing import override

class Animal:
    def speak(self) -> str:
        return "..."

class Cat(Animal):
    @override
    def speak(self) -> str:      # @override signals: this MUST exist in parent
        return "Meow"

    # @override
    # def speek(self): ...       ← mypy/pyright ERROR: no parent method 'speek'
```

---

### D. DUNDER / MAGIC METHODS

```python
# Dunder = Double UNDERscore. Python calls these automatically in specific situations.
# They let your classes integrate with Python syntax (==, len(), str(), in, [], etc.)

class Cart:
    def __init__(self):
        self._items = []

    # ── __repr__ ──────────────────────────────────────────────────────────────
    # Unambiguous string for DEVELOPERS (shown in REPL, logs, debugger).
    # Rule: repr(obj) should ideally be eval()-able back to the object.
    def __repr__(self):
        return f"Cart(items={self._items!r})"

    # ── __str__ ───────────────────────────────────────────────────────────────
    # Human-readable string for USERS (print(), str()).
    # Falls back to __repr__ if __str__ not defined.
    def __str__(self):
        return f"Shopping Cart with {len(self._items)} items"

    # ── __len__ ───────────────────────────────────────────────────────────────
    # Called by len(obj). Makes your class work with len().
    def __len__(self):
        return len(self._items)

    # ── __contains__ ──────────────────────────────────────────────────────────
    # Called by `x in obj`. Makes `"Laptop" in cart` work.
    def __contains__(self, item_name: str):
        return any(i["name"] == item_name for i in self._items)

    # ── __iter__ / __next__ ───────────────────────────────────────────────────
    # Makes your object iterable with `for item in cart`.
    def __iter__(self):
        return iter(self._items)

    def add(self, item):
        self._items.append(item)

    # ── __eq__ ────────────────────────────────────────────────────────────────
    # Called by == operator. Default compares memory address (id).
    # Override to compare by value/ID.
    def __eq__(self, other):
        if not isinstance(other, Cart):
            return NotImplemented
        return self._items == other._items

    # ── __hash__ ──────────────────────────────────────────────────────────────
    # Required if you override __eq__ and want the object usable in sets/dict keys.
    # If __eq__ is defined but NOT __hash__, Python sets __hash__ = None (unhashable).
    def __hash__(self):
        return id(self)   # Identity-based hash (safe default)

# ── Demonstrate all dundgers ──────────────────────────────────────────────────
cart = Cart()
cart.add({"name": "Laptop", "price": 999})
cart.add({"name": "Mouse",  "price": 29})

print(repr(cart))              # Cart(items=[{'name': 'Laptop',...}, ...])
print(str(cart))               # Shopping Cart with 2 items
print(len(cart))               # 2
print("Laptop" in cart)        # True
print("Keyboard" in cart)      # False
for item in cart: print(item)  # iterates both items

# ── __enter__ / __exit__ (Context Manager) ────────────────────────────────────
# Makes your object work with `with` statement.

class DatabaseConnection:
    def __init__(self, url):
        self.url = url
        self.conn = None

    def __enter__(self):            # Called when entering `with` block
        print(f"Connecting to {self.url}")
        self.conn = {"connected": True}   # simulate connection
        return self                       # bound to `as` variable

    def __exit__(self, exc_type, exc_val, exc_tb):   # Called on exit (even on error)
        print("Closing connection")
        self.conn = None
        return False   # False = don't suppress exceptions

with DatabaseConnection("postgresql://localhost/mydb") as db:
    print(f"Using connection: {db.conn}")
# Connecting to postgresql://localhost/mydb
# Using connection: {'connected': True}
# Closing connection   ← always runs, even if exception occurs inside `with`
```

---

### E. INHERITANCE KEYWORDS

```python
# ── super() ───────────────────────────────────────────────────────────────────
# Calls the PARENT class's method. Essential in __init__ to avoid re-writing parent setup.

class Animal:
    def __init__(self, name: str, sound: str):
        self.name  = name
        self.sound = sound

    def speak(self) -> str:
        return f"{self.name} says {self.sound}"

class Dog(Animal):
    def __init__(self, name: str, breed: str):
        super().__init__(name, sound="Woof")   # delegates to Animal.__init__
        self.breed = breed                     # adds Dog-specific attribute

    def fetch(self, item: str) -> str:
        parent_speak = super().speak()         # can call parent method anywhere
        return f"{parent_speak} | fetching {item}"

d = Dog("Rex", "Labrador")
print(d.speak())            # Rex says Woof      (inherited, not overridden)
print(d.fetch("ball"))      # Rex says Woof | fetching ball

# ── isinstance(obj, Class) ────────────────────────────────────────────────────
# Checks if obj IS an instance of Class OR any subclass.
# Use for runtime type checking in polymorphic code.

print(isinstance(d, Dog))     # True
print(isinstance(d, Animal))  # True  (Dog IS-A Animal)
print(isinstance(d, str))     # False

# ── issubclass(Child, Parent) ─────────────────────────────────────────────────
# Checks if a CLASS (not object) is a subclass of another.
# Use to validate class hierarchies at startup or in factory functions.

print(issubclass(Dog, Animal))   # True
print(issubclass(Animal, Dog))   # False
print(issubclass(Dog, Dog))      # True (every class is subclass of itself)

# ── MRO — Method Resolution Order ─────────────────────────────────────────────
# Python resolves which method to call in multiple inheritance using C3 linearization.
# Rule: left-to-right, depth-first.

class A:
    def greet(self): return "A"

class B(A):
    def greet(self): return "B"

class C(A):
    def greet(self): return "C"

class D(B, C):   # Multiple inheritance
    pass

d_obj = D()
print(d_obj.greet())   # "B"  ← B is checked before C (left-to-right)
print(D.__mro__)
# (<class 'D'>, <class 'B'>, <class 'C'>, <class 'A'>, <class 'object'>)
# Python searches in EXACTLY this order for any method call on D.
```

---

### F. RELATIONSHIP KEYWORDS

```python
# Three fundamental relationships in OOP design:
#
#  IS-A   → Inheritance      (class Dog(Animal))
#  HAS-A  → Composition or Aggregation (object holds another object)
#  USES-A → Dependency (method parameter or local variable)

# ── IS-A: Inheritance ─────────────────────────────────────────────────────────
class Vehicle:
    def start(self): print("Vehicle started")

class Car(Vehicle):          # Car IS-A Vehicle
    def open_trunk(self): print("Trunk open")

# ── HAS-A: Composition (strong, lifetime tied) ───────────────────────────────
# The contained object CANNOT exist without the container.
# If the Order is deleted, its OrderItems are deleted too.

class OrderItem:
    def __init__(self, product_name, qty, price):
        self.product_name = product_name
        self.qty   = qty
        self.price = price
    def subtotal(self): return self.qty * self.price

class Order:                 # Order HAS-A list of OrderItems (COMPOSITION)
    def __init__(self, order_id):
        self.order_id = order_id
        self._items   = []    # Order OWNS these items — they live and die with Order

    def add_item(self, name, qty, price):
        self._items.append(OrderItem(name, qty, price))   # Order creates items

    def total(self):
        return sum(i.subtotal() for i in self._items)

o = Order(101)
o.add_item("Laptop", 1, 999.0)
o.add_item("Mouse",  2, 29.0)
print(o.total())   # 1057.0
# When `o` is garbage-collected, ALL its OrderItems are too. → COMPOSITION

# ── HAS-A: Aggregation (weak, independent lifetime) ──────────────────────────
# The contained object CAN exist without the container.
# A Department HAS Employees. If Department is deleted, Employees still exist.

class Employee:
    def __init__(self, name): self.name = name

class Department:            # Department HAS-A list of Employees (AGGREGATION)
    def __init__(self, name):
        self.name      = name
        self.employees = []   # Department does NOT own Employees

    def add_employee(self, emp: Employee):  # Employees are passed IN (not created here)
        self.employees.append(emp)

emp1 = Employee("Alice")
emp2 = Employee("Bob")
dept = Department("Engineering")
dept.add_employee(emp1)
dept.add_employee(emp2)
# dept can be deleted; emp1 and emp2 still exist → AGGREGATION

# ── USES-A: Dependency (method-level, loosest coupling) ──────────────────────
# An object uses another only for the duration of a method call.
# No long-term reference stored.

class Printer:
    def print_document(self, doc: str): print(f"Printing: {doc}")

class ReportService:
    def generate_report(self, data: list, printer: Printer):  # USES-A Printer
        report = "\n".join(str(d) for d in data)
        printer.print_document(report)   # Printer is used here, then forgotten
        # self._printer is NOT stored → loosest coupling

rs = ReportService()
rs.generate_report([1, 2, 3], Printer())   # Dependency injected per call

# ── SUMMARY TABLE ─────────────────────────────────────────────────────────────
# Relationship   | Keyword/Pattern         | Lifetime       | Coupling
# ───────────────┼─────────────────────────┼────────────────┼──────────
# IS-A           | class Child(Parent)     | Same           | Tight
# HAS-A (Comp.)  | self._x = X() inside   | Container owns | Medium
# HAS-A (Aggr.)  | self._x = x (injected) | Independent    | Medium
# USES-A (Dep.)  | method param: X         | Method scope   | Loose
```

---

### G. TYPE HINTS

```python
# Type hints are NOT enforced at runtime but:
# 1. Make code self-documenting
# 2. Enable IDE autocompletion and error highlighting
# 3. Used by mypy/pyright for static analysis
# 4. Expected in MAANG interviews for clean, professional code

from typing import Optional, List, Dict, Tuple, Union, Set
from typing import Callable, Any, TypeVar, Generic, Protocol
from abc import abstractmethod

# ── Basic hints ───────────────────────────────────────────────────────────────
def greet(name: str) -> str:
    return f"Hello, {name}"

def add(a: int, b: int) -> int:
    return a + b

# ── Optional[X] = X | None ────────────────────────────────────────────────────
# Use when a value may or may not be present.
def find_user(user_id: int) -> Optional["User"]:  # returns User or None
    return None   # simplified

# ── Collection hints ──────────────────────────────────────────────────────────
def process_orders(orders: List[str]) -> Dict[str, int]:
    return {o: len(o) for o in orders}

def get_top_users(users: List[str], n: int = 5) -> Tuple[str, ...]:
    return tuple(users[:n])

# ── Union[X, Y] = X or Y ──────────────────────────────────────────────────────
# Use when a value can be one of several types.
def parse_id(raw: Union[str, int]) -> int:
    return int(raw)

# Python 3.10+ shorthand: str | int instead of Union[str, int]
def parse_id_new(raw: str | int) -> int:
    return int(raw)

# ── Callable[[arg_types], return_type] ────────────────────────────────────────
# For functions passed as arguments (callbacks, strategies).
def apply(func: Callable[[int, int], int], a: int, b: int) -> int:
    return func(a, b)

print(apply(lambda x, y: x + y, 3, 4))   # 7

# ── TypeVar + Generic ─────────────────────────────────────────────────────────
# For writing classes/functions that work with ANY type (like List[T]).
T = TypeVar("T")

class Stack(Generic[T]):         # Stack[int], Stack[str], Stack[User], etc.
    def __init__(self): self._data: List[T] = []
    def push(self, item: T) -> None: self._data.append(item)
    def pop(self)         -> T:      return self._data.pop()
    def peek(self)        -> T:      return self._data[-1]
    def is_empty(self)    -> bool:   return len(self._data) == 0

s: Stack[int] = Stack()
s.push(1); s.push(2)
print(s.pop())   # 2

# ── Protocol (Structural Typing / Duck Typing) ────────────────────────────────
# Protocol lets you define an interface WITHOUT requiring inheritance.
# Any class that has the required methods automatically satisfies the protocol.
# ("If it quacks like a duck, it IS a duck.")

class Drawable(Protocol):        # NOT ABC. No need to inherit.
    def draw(self) -> None: ...
    def resize(self, factor: float) -> None: ...

class Circle:                    # Does NOT inherit Drawable
    def draw(self) -> None: print("Drawing circle")
    def resize(self, factor) -> None: print(f"Resizing circle by {factor}")

class Square:                    # Does NOT inherit Drawable
    def draw(self) -> None: print("Drawing square")
    def resize(self, factor) -> None: print(f"Resizing square by {factor}")

def render(shape: Drawable) -> None:   # Accepts ANYTHING with draw() + resize()
    shape.draw()
    shape.resize(1.5)

render(Circle())   # Works — Circle has draw() and resize()
render(Square())   # Works — Square has draw() and resize()
# Advantage over ABC: you can make THIRD-PARTY classes satisfy your protocol
# without touching their source code.

# ── QUICK REFERENCE ───────────────────────────────────────────────────────────
# Hint              | Means
# ──────────────────┼──────────────────────────────────────────────
# int / str / float | primitive types
# Optional[X]       | X or None
# List[X]           | list of X
# Dict[K, V]        | dict with key K and value V
# Tuple[X, Y]       | fixed-length tuple
# Set[X]            | set of X
# Union[X, Y]       | X or Y  (Python 3.10+: X | Y)
# Callable[[X],Y]   | function taking X returning Y
# TypeVar("T")      | generic placeholder type
# Generic[T]        | class parameterized by T
# Protocol          | structural interface (duck-typing friendly)
# Any               | opt out of type checking (use sparingly)
```

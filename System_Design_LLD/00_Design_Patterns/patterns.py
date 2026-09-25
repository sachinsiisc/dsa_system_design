"""
Design Patterns — Complete Implementation
10 Most-Used Patterns for MAANG LLD Interviews
Each pattern: When to use · Real example · Full code · Interview hook
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Callable
from copy import deepcopy
import threading


# ══════════════════════════════════════════════════════════════════════════════
# PATTERN 1: SINGLETON
# ══════════════════════════════════════════════════════════════════════════════
"""
Use when: Need exactly ONE shared instance.
Examples: Logger, Config manager, Thread pool, DB connection pool.

Interview hook: "How do you make Singleton thread-safe?"
→ Double-checked locking OR module-level instance (Python idiom).
"""

class Logger:
    """Thread-safe Singleton Logger."""
    _instance: Optional['Logger'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:                      # double-checked locking
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._logs = []
        return cls._instance
    
    def log(self, level: str, message: str):
        entry = f"[{level}] {message}"
        self._logs.append(entry)
        print(entry)
    
    def get_logs(self) -> list:
        return self._logs.copy()

# Test: same instance
l1 = Logger()
l2 = Logger()
assert l1 is l2, "Should be same instance!"
l1.log("INFO", "Application started")
l2.log("ERROR", "Something failed")
assert len(l1.get_logs()) == 2   # both share same log list


# ══════════════════════════════════════════════════════════════════════════════
# PATTERN 2: FACTORY METHOD
# ══════════════════════════════════════════════════════════════════════════════
"""
Use when: You know WHAT type to create but delegate the HOW to subclasses.
Examples: Document parser (CSV/JSON/XML), Notification sender (Email/SMS/Push).

Factory Method: Superclass has create() method, subclasses override it.
Simple Factory: Static method that picks implementation based on parameter.

Interview hook: "How is Factory different from Abstract Factory?"
→ Factory = creates ONE product family. Abstract Factory = creates MULTIPLE related products.
"""

class Notification(ABC):
    @abstractmethod
    def send(self, recipient: str, message: str) -> bool:
        pass

class EmailNotification(Notification):
    def send(self, recipient, message):
        print(f"📧 Email to {recipient}: {message}")
        return True

class SMSNotification(Notification):
    def send(self, recipient, message):
        print(f"📱 SMS to {recipient}: {message[:160]}")   # SMS limit 160 chars
        return True

class PushNotification(Notification):
    def send(self, recipient, message):
        print(f"🔔 Push to device {recipient}: {message[:100]}")
        return True

class NotificationFactory:
    """Simple Factory — choose implementation based on type string."""
    
    _creators: Dict[str, type] = {
        'email': EmailNotification,
        'sms':   SMSNotification,
        'push':  PushNotification,
    }
    
    @classmethod
    def create(cls, notification_type: str) -> Notification:
        creator = cls._creators.get(notification_type.lower())
        if not creator:
            raise ValueError(f"Unknown notification type: {notification_type}. "
                           f"Supported: {list(cls._creators.keys())}")
        return creator()
    
    @classmethod
    def register(cls, type_name: str, creator: type):
        """Extension point — register new notification types without modifying factory."""
        cls._creators[type_name] = creator

# Usage:
for ntype in ['email', 'sms', 'push']:
    notif = NotificationFactory.create(ntype)
    notif.send("user@example.com", "Your order has shipped!")

# Extend without modifying factory (Open/Closed Principle):
class SlackNotification(Notification):
    def send(self, recipient, message):
        print(f"💬 Slack to #{recipient}: {message}")
        return True

NotificationFactory.register('slack', SlackNotification)
NotificationFactory.create('slack').send('engineering', 'Deployment complete')


# ══════════════════════════════════════════════════════════════════════════════
# PATTERN 3: BUILDER
# ══════════════════════════════════════════════════════════════════════════════
"""
Use when: Object has many parameters, many are optional, order matters.
Examples: Query builder, HTTP request builder, Pizza order, Resume.

Without Builder: Pizza(size, sauce, cheese, pepperoni, mushrooms, onions, ...15 params)
→ Called: Pizza("large", True, True, False, True, ...)  → unreadable!
With Builder: Pizza.Builder().size("large").sauce("tomato").cheese().pepperoni().build()
"""

from dataclasses import dataclass, field

@dataclass
class Pizza:
    size: str
    crust: str
    sauce: str
    cheese: bool
    toppings: List[str]
    
    def __str__(self):
        toppings = ', '.join(self.toppings) if self.toppings else 'none'
        return (f"{self.size} pizza | {self.crust} crust | {self.sauce} sauce | "
                f"{'cheese' if self.cheese else 'no cheese'} | toppings: {toppings}")

class PizzaBuilder:
    def __init__(self):
        self._size     = "medium"     # defaults
        self._crust    = "regular"
        self._sauce    = "tomato"
        self._cheese   = True
        self._toppings = []
    
    def size(self, size: str) -> 'PizzaBuilder':
        valid = ['small', 'medium', 'large', 'xl']
        if size not in valid:
            raise ValueError(f"Size must be one of {valid}")
        self._size = size
        return self   # return self for method chaining
    
    def thin_crust(self) -> 'PizzaBuilder':
        self._crust = "thin"
        return self
    
    def thick_crust(self) -> 'PizzaBuilder':
        self._crust = "thick"
        return self
    
    def sauce(self, sauce: str) -> 'PizzaBuilder':
        self._sauce = sauce
        return self
    
    def no_cheese(self) -> 'PizzaBuilder':
        self._cheese = False
        return self
    
    def add_topping(self, topping: str) -> 'PizzaBuilder':
        self._toppings.append(topping)
        return self
    
    def build(self) -> Pizza:
        return Pizza(self._size, self._crust, self._sauce, self._cheese, self._toppings)

# Fluent interface — reads like English!
pizza1 = (PizzaBuilder()
          .size("large")
          .thin_crust()
          .sauce("bbq")
          .add_topping("chicken")
          .add_topping("onions")
          .build())

pizza2 = (PizzaBuilder()
          .size("medium")
          .no_cheese()
          .sauce("marinara")
          .add_topping("mushrooms")
          .build())

print(pizza1)
print(pizza2)


# ══════════════════════════════════════════════════════════════════════════════
# PATTERN 4: OBSERVER (EVENT SYSTEM)
# ══════════════════════════════════════════════════════════════════════════════
"""
Use when: One-to-many dependency. When one object changes, all dependents notified.
Examples: Event listeners, Stock price alerts, E-commerce order events, GUI events.

Interview hook: "How does Observer relate to Pub/Sub?"
→ Observer: observers know about subject (coupled).
→ Pub/Sub: publishers and subscribers don't know each other (message broker decouples).
"""

class EventEmitter:
    """Simple Observer/EventEmitter base class."""
    
    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = {}
    
    def on(self, event: str, callback: Callable) -> None:
        """Subscribe to an event."""
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)
    
    def off(self, event: str, callback: Callable) -> None:
        """Unsubscribe from an event."""
        if event in self._listeners:
            self._listeners[event] = [
                cb for cb in self._listeners[event] if cb != callback
            ]
    
    def emit(self, event: str, *args, **kwargs) -> None:
        """Notify all subscribers of event."""
        for callback in self._listeners.get(event, []):
            callback(*args, **kwargs)

class Order(EventEmitter):
    def __init__(self, order_id: str, user_id: str, items: list):
        super().__init__()
        self.order_id = order_id
        self.user_id  = user_id
        self.items    = items
        self.status   = "pending"
    
    def confirm(self):
        self.status = "confirmed"
        self.emit('order_confirmed', self)   # notify all listeners
    
    def ship(self, tracking_number: str):
        self.status = "shipped"
        self.tracking = tracking_number
        self.emit('order_shipped', self, tracking_number)
    
    def deliver(self):
        self.status = "delivered"
        self.emit('order_delivered', self)

# Subscribers:
def send_confirmation_email(order):
    print(f"📧 Email to user {order.user_id}: Order {order.order_id} confirmed!")

def update_inventory(order):
    print(f"📦 Inventory: deducting stock for {len(order.items)} items from order {order.order_id}")

def send_shipping_notification(order, tracking):
    print(f"🚚 SMS to user {order.user_id}: Your order ships! Tracking: {tracking}")

def update_analytics(order):
    print(f"📊 Analytics: order {order.order_id} status changed to {order.status}")

# Wire up:
order = Order("ORD-001", "USER-123", ["laptop", "mouse"])
order.on('order_confirmed', send_confirmation_email)
order.on('order_confirmed', update_inventory)
order.on('order_confirmed', update_analytics)
order.on('order_shipped',   send_shipping_notification)
order.on('order_shipped',   update_analytics)
order.on('order_delivered', update_analytics)

order.confirm()     # triggers 3 callbacks
order.ship("TRK-ABC-123")   # triggers 2 callbacks


# ══════════════════════════════════════════════════════════════════════════════
# PATTERN 5: STRATEGY
# ══════════════════════════════════════════════════════════════════════════════
"""
Use when: You have a family of algorithms and want to swap them at runtime.
Examples: Sorting strategy, Payment strategy, Compression strategy, Route planning.

Difference from Factory: Strategy switches algorithm at runtime.
Factory creates objects at creation time.
"""

class SortStrategy(ABC):
    @abstractmethod
    def sort(self, data: list) -> list: pass

class BubbleSortStrategy(SortStrategy):
    def sort(self, data):
        arr = data[:]
        n = len(arr)
        for i in range(n):
            for j in range(n - i - 1):
                if arr[j] > arr[j+1]:
                    arr[j], arr[j+1] = arr[j+1], arr[j]
        return arr

class QuickSortStrategy(SortStrategy):
    def sort(self, data):
        if len(data) <= 1:
            return data
        pivot = data[len(data) // 2]
        left   = [x for x in data if x < pivot]
        middle = [x for x in data if x == pivot]
        right  = [x for x in data if x > pivot]
        return self.sort(left) + middle + self.sort(right)

class MergeSortStrategy(SortStrategy):
    def sort(self, data):
        if len(data) <= 1: return data
        mid   = len(data) // 2
        left  = self.sort(data[:mid])
        right = self.sort(data[mid:])
        return self._merge(left, right)
    
    def _merge(self, left, right):
        result = []
        i = j = 0
        while i < len(left) and j < len(right):
            if left[i] <= right[j]: result.append(left[i]); i += 1
            else: result.append(right[j]); j += 1
        return result + left[i:] + right[j:]

class Sorter:
    def __init__(self, strategy: SortStrategy):
        self._strategy = strategy
    
    def set_strategy(self, strategy: SortStrategy):
        """Change algorithm at runtime!"""
        self._strategy = strategy
    
    def sort(self, data: list) -> list:
        return self._strategy.sort(data)

data = [64, 34, 25, 12, 22, 11, 90]
sorter = Sorter(BubbleSortStrategy())
print(sorter.sort(data))

sorter.set_strategy(QuickSortStrategy())  # swap at runtime
print(sorter.sort(data))


# ══════════════════════════════════════════════════════════════════════════════
# PATTERN 6: DECORATOR
# ══════════════════════════════════════════════════════════════════════════════
"""
Use when: Add behaviour to objects dynamically without modifying their class.
  Better than inheritance when: combinations would create class explosion.
  Coffee example: Coffee, Milk, Sugar, Whip = 2^4 = 16 subclasses via inheritance
                  Decorator: 4 classes, infinite combinations.

Examples: HTTP middleware, Logging wrapper, Auth wrapper, Caching wrapper.

Interview hook: "Is Python's @decorator the same as Decorator pattern?"
→ Similar idea (wrap behaviour), but Python @decorator is syntactic sugar for
function wrapping. GoF Decorator is class-based structural pattern.
"""

class Coffee(ABC):
    @abstractmethod
    def cost(self) -> float: pass
    
    @abstractmethod
    def description(self) -> str: pass

class SimpleCoffee(Coffee):
    def cost(self): return 1.00
    def description(self): return "Simple coffee"

class CoffeeDecorator(Coffee):
    """Base decorator — wraps a coffee object."""
    def __init__(self, coffee: Coffee):
        self._coffee = coffee
    
    def cost(self): return self._coffee.cost()
    def description(self): return self._coffee.description()

class MilkDecorator(CoffeeDecorator):
    def cost(self): return self._coffee.cost() + 0.25
    def description(self): return self._coffee.description() + ", milk"

class SugarDecorator(CoffeeDecorator):
    def cost(self): return self._coffee.cost() + 0.10
    def description(self): return self._coffee.description() + ", sugar"

class WhipDecorator(CoffeeDecorator):
    def cost(self): return self._coffee.cost() + 0.50
    def description(self): return self._coffee.description() + ", whip cream"

class VanillaDecorator(CoffeeDecorator):
    def cost(self): return self._coffee.cost() + 0.75
    def description(self): return self._coffee.description() + ", vanilla"

# Build a complex drink by wrapping:
fancy_coffee = VanillaDecorator(
    WhipDecorator(
        MilkDecorator(
            MilkDecorator(        # double milk!
                SimpleCoffee()
            )
        )
    )
)
print(fancy_coffee.description())   # "Simple coffee, milk, milk, whip cream, vanilla"
print(f"${fancy_coffee.cost():.2f}")  # $1.00 + 0.25 + 0.25 + 0.50 + 0.75 = $2.75

# Real-world: HTTP middleware as Decorators
class HTTPHandler(ABC):
    @abstractmethod
    def handle(self, request: dict) -> dict: pass

class BaseHandler(HTTPHandler):
    def handle(self, request):
        return {"status": 200, "body": f"Hello, {request.get('user', 'guest')}!"}

class AuthMiddleware(HTTPHandler):
    def __init__(self, handler: HTTPHandler, valid_tokens: set):
        self._handler = handler
        self._valid_tokens = valid_tokens
    
    def handle(self, request):
        token = request.get('token')
        if token not in self._valid_tokens:
            return {"status": 401, "body": "Unauthorized"}
        return self._handler.handle(request)

class LoggingMiddleware(HTTPHandler):
    def __init__(self, handler: HTTPHandler):
        self._handler = handler
    
    def handle(self, request):
        print(f"→ Request: {request}")
        response = self._handler.handle(request)
        print(f"← Response: {response}")
        return response

class RateLimitMiddleware(HTTPHandler):
    def __init__(self, handler: HTTPHandler, max_per_minute: int = 60):
        self._handler = handler
        self._requests = {}
        self._max = max_per_minute
    
    def handle(self, request):
        import time
        client = request.get('client_ip', 'unknown')
        now = int(time.time() / 60)   # current minute bucket
        if self._requests.get((client, now), 0) >= self._max:
            return {"status": 429, "body": "Rate limit exceeded"}
        self._requests[(client, now)] = self._requests.get((client, now), 0) + 1
        return self._handler.handle(request)

# Stack middleware (inner → outer):
handler = LoggingMiddleware(
    RateLimitMiddleware(
        AuthMiddleware(
            BaseHandler(),
            valid_tokens={"token123", "secretkey"}
        ),
        max_per_minute=5
    )
)

print("\n--- Valid request ---")
handler.handle({"token": "token123", "user": "Alice", "client_ip": "1.2.3.4"})
print("\n--- Invalid token ---")
handler.handle({"token": "wrong", "client_ip": "1.2.3.4"})


# ══════════════════════════════════════════════════════════════════════════════
# PATTERN 7: STATE
# ══════════════════════════════════════════════════════════════════════════════
"""
Use when: Object behaviour changes dramatically based on internal state.
Examples: Order status, Traffic light, Vending machine, TCP connection states.

Without State pattern: Giant if/elif chain on status string.
→ Adding new state requires modifying existing code.
With State pattern: Each state is a class. Adding new state = new class.
"""

class OrderState(ABC):
    """Abstract state base class."""
    @abstractmethod
    def confirm(self, order): pass
    
    @abstractmethod
    def ship(self, order): pass
    
    @abstractmethod
    def deliver(self, order): pass
    
    @abstractmethod
    def cancel(self, order): pass

class PendingState(OrderState):
    def confirm(self, order):
        print("✓ Order confirmed!")
        order.state = ConfirmedState()
    def ship(self, order):
        print("✗ Cannot ship: order not confirmed yet")
    def deliver(self, order):
        print("✗ Cannot deliver: order not shipped yet")
    def cancel(self, order):
        print("✓ Order cancelled (was pending)")
        order.state = CancelledState()

class ConfirmedState(OrderState):
    def confirm(self, order):
        print("✗ Already confirmed")
    def ship(self, order):
        print("✓ Order shipped!")
        order.state = ShippedState()
    def deliver(self, order):
        print("✗ Cannot deliver: not shipped yet")
    def cancel(self, order):
        print("✓ Order cancelled (was confirmed). Refund processed.")
        order.state = CancelledState()

class ShippedState(OrderState):
    def confirm(self, order):
        print("✗ Already past confirmation")
    def ship(self, order):
        print("✗ Already shipped")
    def deliver(self, order):
        print("✓ Order delivered!")
        order.state = DeliveredState()
    def cancel(self, order):
        print("✗ Cannot cancel: already shipped. Initiate return instead.")

class DeliveredState(OrderState):
    def confirm(self, order): print("✗ Already delivered")
    def ship(self, order):    print("✗ Already delivered")
    def deliver(self, order): print("✗ Already delivered")
    def cancel(self, order):  print("✓ Return/refund initiated.")

class CancelledState(OrderState):
    def confirm(self, order): print("✗ Order was cancelled")
    def ship(self, order):    print("✗ Order was cancelled")
    def deliver(self, order): print("✗ Order was cancelled")
    def cancel(self, order):  print("✗ Already cancelled")

class StatefulOrder:
    def __init__(self, order_id):
        self.order_id = order_id
        self.state = PendingState()   # starts pending
    
    def confirm(self): self.state.confirm(self)
    def ship(self):    self.state.ship(self)
    def deliver(self): self.state.deliver(self)
    def cancel(self):  self.state.cancel(self)
    
    def get_state(self): return type(self.state).__name__

print("\n--- Order lifecycle ---")
order = StatefulOrder("ORD-001")
order.ship()     # Can't ship yet
order.confirm()  # Confirm
order.ship()     # Ship
order.cancel()   # Can't cancel shipped
order.deliver()  # Deliver


# ══════════════════════════════════════════════════════════════════════════════
# PATTERN 8: PROXY
# ══════════════════════════════════════════════════════════════════════════════
"""
Use when: Control access to an object (lazy loading, caching, auth, logging).
Examples: ORM lazy loading, Virtual proxy for large objects, Protection proxy.

Types:
  Virtual Proxy: delay expensive object creation until needed
  Protection Proxy: access control
  Caching Proxy: cache results
  Logging Proxy: log all method calls
"""

class ImageLoader(ABC):
    @abstractmethod
    def display(self) -> None: pass

class RealImage(ImageLoader):
    """Expensive to load — reads from disk."""
    def __init__(self, filename: str):
        self.filename = filename
        self._load()   # expensive!
    
    def _load(self):
        print(f"🖼️  Loading image from disk: {self.filename}")   # simulates disk I/O
    
    def display(self):
        print(f"Displaying: {self.filename}")

class LazyImageProxy(ImageLoader):
    """Virtual Proxy: delay loading until display() is called."""
    def __init__(self, filename: str):
        self.filename = filename
        self._real_image: Optional[RealImage] = None
    
    def display(self):
        if self._real_image is None:
            self._real_image = RealImage(self.filename)   # load on first use
        self._real_image.display()

class CachingImageProxy(ImageLoader):
    """Caching Proxy: don't reload already-loaded images."""
    _cache: Dict[str, RealImage] = {}
    
    def __init__(self, filename: str):
        self.filename = filename
    
    def display(self):
        if self.filename not in CachingImageProxy._cache:
            CachingImageProxy._cache[self.filename] = RealImage(self.filename)
        CachingImageProxy._cache[self.filename].display()

print("\n--- Virtual Proxy (lazy load) ---")
img = LazyImageProxy("photo.jpg")
print("Image created (not loaded yet)")
img.display()   # loads here
img.display()   # doesn't reload


# ══════════════════════════════════════════════════════════════════════════════
# PATTERN 9: COMMAND
# ══════════════════════════════════════════════════════════════════════════════
"""
Use when: Encapsulate requests as objects. Enables: undo/redo, queuing, logging.
Examples: Text editor (undo), Restaurant order system, Task scheduler, Transaction log.
"""

class Command(ABC):
    @abstractmethod
    def execute(self) -> None: pass
    
    @abstractmethod
    def undo(self) -> None: pass

class TextDocument:
    def __init__(self):
        self.text = ""
    
    def __str__(self): return self.text

class InsertCommand(Command):
    def __init__(self, doc: TextDocument, position: int, text: str):
        self.doc = doc
        self.position = position
        self.text = text
    
    def execute(self):
        self.doc.text = (
            self.doc.text[:self.position] + 
            self.text + 
            self.doc.text[self.position:]
        )
    
    def undo(self):
        self.doc.text = (
            self.doc.text[:self.position] + 
            self.doc.text[self.position + len(self.text):]
        )

class DeleteCommand(Command):
    def __init__(self, doc: TextDocument, position: int, length: int):
        self.doc = doc
        self.position = position
        self.length = length
        self._deleted_text = ""
    
    def execute(self):
        self._deleted_text = self.doc.text[self.position:self.position + self.length]
        self.doc.text = self.doc.text[:self.position] + self.doc.text[self.position + self.length:]
    
    def undo(self):
        self.doc.text = (
            self.doc.text[:self.position] + 
            self._deleted_text + 
            self.doc.text[self.position:]
        )

class TextEditor:
    def __init__(self, doc: TextDocument):
        self.doc = doc
        self._history: List[Command] = []
        self._redo_stack: List[Command] = []
    
    def execute(self, command: Command):
        command.execute()
        self._history.append(command)
        self._redo_stack.clear()   # new action clears redo stack
    
    def undo(self):
        if not self._history: return
        command = self._history.pop()
        command.undo()
        self._redo_stack.append(command)
        print(f"Undone. Document: '{self.doc.text}'")
    
    def redo(self):
        if not self._redo_stack: return
        command = self._redo_stack.pop()
        command.execute()
        self._history.append(command)
        print(f"Redone. Document: '{self.doc.text}'")

print("\n--- Command Pattern (Text Editor) ---")
doc = TextDocument()
editor = TextEditor(doc)

editor.execute(InsertCommand(doc, 0, "Hello"))
print(doc)   # Hello
editor.execute(InsertCommand(doc, 5, " World"))
print(doc)   # Hello World
editor.execute(DeleteCommand(doc, 5, 6))
print(doc)   # Hello
editor.undo()    # Undo delete
editor.undo()    # Undo " World" insert
editor.redo()    # Redo insert


# ══════════════════════════════════════════════════════════════════════════════
# PATTERN 10: TEMPLATE METHOD
# ══════════════════════════════════════════════════════════════════════════════
"""
Use when: Skeleton of algorithm fixed, specific steps vary.
Examples: Data processing pipeline, Game turn logic, Report generation.

Difference from Strategy:
  Template: subclasses override STEPS of algorithm. Structure is in parent.
  Strategy: entire algorithm swapped. Structure is in strategy class.
"""

class DataMigrationJob(ABC):
    """Template Method: defines the migration sequence. Subclasses fill in details."""
    
    def run(self):
        """Template method — defines algorithm skeleton. Don't override this."""
        print(f"\n=== Starting {self.__class__.__name__} ===")
        self._connect()
        data = self._extract()
        transformed = self._transform(data)
        self._load(transformed)
        self._validate()
        self._disconnect()
        print(f"=== {self.__class__.__name__} Complete ===")
    
    def _connect(self):
        print("Connecting to source and destination...")
    
    @abstractmethod
    def _extract(self) -> list:
        """Extract data from source."""
        pass
    
    def _transform(self, data: list) -> list:
        """Default: no transformation. Subclasses can override."""
        return data
    
    @abstractmethod
    def _load(self, data: list) -> None:
        """Load data into destination."""
        pass
    
    def _validate(self):
        print("Validation: basic checks passed.")
    
    def _disconnect(self):
        print("Disconnecting...")

class CSVToDBMigration(DataMigrationJob):
    def _extract(self):
        print("Reading CSV file...")
        return [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
    
    def _transform(self, data):
        print("Transforming: normalising names, validating ages...")
        return [{"name": row["name"].upper(), "age": row["age"]} for row in data]
    
    def _load(self, data):
        print(f"Inserting {len(data)} records into database...")

class JSONToKafkaMigration(DataMigrationJob):
    def _extract(self):
        print("Reading JSON API...")
        return [{"event": "purchase", "amount": 99.99}]
    
    def _load(self, data):
        print(f"Publishing {len(data)} events to Kafka topic...")
    
    def _validate(self):
        super()._validate()
        print("Validation: checking Kafka consumer offset...")

CSVToDBMigration().run()
JSONToKafkaMigration().run()


# ══════════════════════════════════════════════════════════════════════════════
# TESTS
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    # Singleton
    assert Logger() is Logger()
    print("✓ Singleton")

    # Factory
    for t in ['email', 'sms', 'push']:
        assert isinstance(NotificationFactory.create(t), Notification)
    print("✓ Factory")

    # Builder
    p = PizzaBuilder().size("large").thin_crust().add_topping("pepperoni").build()
    assert p.size == "large" and p.crust == "thin" and "pepperoni" in p.toppings
    print("✓ Builder")

    # Observer
    o = Order("TEST-001", "U1", ["item1"])
    events = []
    o.on('order_confirmed', lambda ord: events.append('confirmed'))
    o.confirm()
    assert 'confirmed' in events
    print("✓ Observer")

    # Strategy
    data = [3, 1, 4, 1, 5, 9, 2, 6]
    s = Sorter(MergeSortStrategy())
    assert s.sort(data) == sorted(data)
    print("✓ Strategy")

    # State
    order = StatefulOrder("TEST")
    order.ship()   # should fail silently
    assert isinstance(order.state, PendingState)
    order.confirm()
    assert isinstance(order.state, ConfirmedState)
    print("✓ State")

    # Command
    doc2 = TextDocument()
    ed2  = TextEditor(doc2)
    ed2.execute(InsertCommand(doc2, 0, "Hello"))
    assert str(doc2) == "Hello"
    ed2.undo()
    assert str(doc2) == ""
    print("✓ Command")

    print("\n🎉 All design pattern tests passed!")

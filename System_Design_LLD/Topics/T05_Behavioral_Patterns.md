# LLD Topic 05: Design Patterns — Behavioral
## Strategy, Observer, Template Method, Command, State | Java + C++ | Every Keyword

---

> **BEHAVIORAL PATTERNS** deal with how objects COMMUNICATE and DISTRIBUTE responsibility.
> Key question: "Who is responsible for doing X, and how do the objects talk to each other?"

---

## PATTERN 1: STRATEGY

```
PROBLEM: An algorithm (behaviour) needs to vary at RUNTIME.
         Multiple versions of the same operation exist (sorting, pricing, routing).
         
WITHOUT STRATEGY (bad):
  void calculateFare(String type) {
    if (type == "normal") { ... }
    if (type == "surge")  { ... }
    if (type == "flat")   { ... }   // Add new type → modify this method → OCP violated.
  }

WITH STRATEGY:
  FareCalculator.setStrategy(new SurgePricingStrategy());
  FareCalculator.calculate() → calls strategy's calculate() internally.
  Change algorithm at runtime by swapping the strategy object.

REAL EXAMPLES IN OUR CASE STUDIES:
  Uber: SurgePricingStrategy, NormalPricingStrategy, FlatRatePricingStrategy
  Netflix: AdaptiveBitrateStrategy, QualityFirstStrategy, DataSaverStrategy
  MakeMyTrip: FlexibleCancellationPolicy, StrictCancellationPolicy
  Payment: CardProcessor, UPIProcessor, WalletProcessor
  AI: OpenAIAdapter, AnthropicAdapter, GoogleAdapter
```

### Java — Strategy

```java
// ── Strategy: Sorting Algorithm selection ─────────────────────────────────────

import java.util.List;
import java.util.ArrayList;
import java.util.Comparator;

// STEP 1: Strategy INTERFACE (the contract for all algorithms):
interface SortStrategy<T> {
    //  ↑ <T>: Generic type parameter. T can be any type: Integer, String, Employee, etc.
    //    This makes SortStrategy work for any Comparable type. Reusable.

    List<T> sort(List<T> data, Comparator<T> comparator);
    //  ↑ Comparator<T>: a function that compares two T objects.
    //    Defines the ORDERING (ascending, descending, by name, by salary, etc.).
    //    Passed in so the strategy can be applied to any ordering.
}

// STEP 2: Concrete strategy implementations:

class BubbleSortStrategy<T> implements SortStrategy<T> {
    //  ↑ <T>: This class is also generic (uses same T as the interface).

    @Override
    public List<T> sort(List<T> data, Comparator<T> comparator) {
        List<T> result = new ArrayList<>(data);
        //  ↑ new ArrayList<>(data): create a COPY of the input list.
        //    Sorting is destructive. We sort the copy, not the original.
        //    Defensive programming: caller's original list is unchanged.

        int n = result.size();
        for (int i = 0; i < n - 1; i++) {
            //  ↑ Outer loop: n-1 passes (each pass bubbles the max to the end).
            for (int j = 0; j < n - i - 1; j++) {
                //  ↑ Inner loop: compare adjacent elements.
                //    n-i-1: after i passes, last i elements are already sorted.
                if (comparator.compare(result.get(j), result.get(j + 1)) > 0) {
                    //  ↑ comparator.compare(a, b): returns negative if a<b, 0 if equal, positive if a>b.
                    //    > 0: a > b → swap them (to sort ascending).
                    T temp = result.get(j);
                    result.set(j, result.get(j + 1));
                    result.set(j + 1, temp);
                    //  ↑ Swap using temp variable. Three-step swap: standard algorithm.
                }
            }
        }
        System.out.println("BubbleSort: O(n²) — sorted " + n + " elements");
        return result;
    }
}

class QuickSortStrategy<T> implements SortStrategy<T> {
    @Override
    public List<T> sort(List<T> data, Comparator<T> comparator) {
        List<T> result = new ArrayList<>(data);
        quickSort(result, 0, result.size() - 1, comparator);
        System.out.println("QuickSort: O(n log n) average — sorted " + result.size() + " elements");
        return result;
    }

    private void quickSort(List<T> list, int low, int high, Comparator<T> cmp) {
        if (low < high) {
            int pivotIdx = partition(list, low, high, cmp);
            quickSort(list, low, pivotIdx - 1, cmp);
            //  ↑ Recursion: sort left subarray (elements < pivot).
            quickSort(list, pivotIdx + 1, high, cmp);
            //  ↑ Recursion: sort right subarray (elements > pivot).
        }
    }

    private int partition(List<T> list, int low, int high, Comparator<T> cmp) {
        T pivot = list.get(high);   // Use last element as pivot
        int i = low - 1;            // Index of smaller element

        for (int j = low; j < high; j++) {
            if (cmp.compare(list.get(j), pivot) <= 0) {
                //  ↑ If current element <= pivot: move to left partition.
                i++;
                T temp = list.get(i); list.set(i, list.get(j)); list.set(j, temp); // Swap
            }
        }
        // Place pivot in correct position:
        T temp = list.get(i + 1); list.set(i + 1, list.get(high)); list.set(high, temp);
        return i + 1;
    }
}

// CONTEXT: Uses a strategy, can switch at runtime:
class DataSorter<T> {
    private SortStrategy<T> strategy;
    //  ↑ Holds reference to the current strategy.
    //    Not hardcoded to any specific algorithm.

    public DataSorter(SortStrategy<T> strategy) {
        this.strategy = strategy;
    }

    public void setStrategy(SortStrategy<T> strategy) {
        this.strategy = strategy;
        //  ↑ RUNTIME SWAP: change sorting algorithm without changing DataSorter.
        //    Small data: use BubbleSort (simple). Large data: use QuickSort (fast).
    }

    public List<T> sort(List<T> data, Comparator<T> comparator) {
        return strategy.sort(data, comparator);
        //  ↑ DELEGATION: DataSorter doesn't know HOW to sort.
        //    It delegates to whichever strategy is currently set.
        //    The strategy object does the actual work.
    }
}

// USAGE:
// DataSorter<Integer> sorter = new DataSorter<>(new BubbleSortStrategy<>());
// List<Integer> data = List.of(5, 2, 8, 1, 9, 3);
//
// sorter.sort(data, Comparator.naturalOrder());    // Ascending: [1,2,3,5,8,9]
// sorter.sort(data, Comparator.reverseOrder());    // Descending: [9,8,5,3,2,1]
//
// // Switch to QuickSort for large dataset:
// sorter.setStrategy(new QuickSortStrategy<>());
// sorter.sort(largeData, Comparator.naturalOrder());  // Same call, different algorithm.

// CUSTOM COMPARATOR:
// List<Employee> employees = ...;
// sorter.sort(employees, Comparator.comparing(Employee::getSalary));    // By salary
// sorter.sort(employees, Comparator.comparing(Employee::getName));      // By name
//  ↑ Comparator.comparing(keyExtractor): creates Comparator that extracts a key and compares it.
//  ↑ Employee::getSalary: method reference (Employee → double). Used as key extractor.
```

### C++ — Strategy

```cpp
// ── C++ Strategy using std::function or virtual interface ─────────────────────
#pragma once
#include <vector>
#include <functional>
#include <algorithm>
#include <iostream>

// LIGHTWEIGHT STRATEGY using std::function (no virtual dispatch needed):
template<typename T>
//  ↑ template<typename T>: makes this a class template. Works for any type T.
class DataSorter {
public:
    // Strategy type: a function that takes vector by reference and comparator:
    using Strategy = std::function<void(std::vector<T>&, std::function<bool(const T&, const T&)>)>;
    //  ↑ using: type alias.
    //  ↑ std::function<void(...)>: wrapper for any callable with this signature.
    //    Takes: vector by reference + comparator function. Returns nothing (sorts in-place).

    explicit DataSorter(Strategy strategy) : strategy_(std::move(strategy)) {}

    void setStrategy(Strategy s) { strategy_ = std::move(s); }
    //  ↑ std::move: transfer ownership of the function object (no copy).

    std::vector<T> sort(std::vector<T> data,
                        std::function<bool(const T&, const T&)> comparator) {
        //  ↑ Takes data by VALUE (copy made). Sort the copy. Return sorted copy.
        //    Original 'data' unchanged (defensive — caller keeps original).
        strategy_(data, comparator);
        //  ↑ Call whatever function is stored in strategy_. Could be lambda, function pointer, etc.
        return data;
    }

private:
    Strategy strategy_;
};

// PREDEFINED STRATEGIES (as lambdas or functions):

// Quick sort strategy (using STL):
auto quickSortStrategy = [](auto& vec, auto comparator) {
    std::sort(vec.begin(), vec.end(), comparator);
    //  ↑ std::sort: STL introsort (quicksort + heapsort + insertionsort hybrid). O(n log n).
    //    In-place: modifies vec. O(n log n) worst case guaranteed.
    //  ↑ vec.begin(), vec.end(): iterators to start and one-past-end of vector.
    //  ↑ comparator: called to compare elements (a < b → true to sort ascending).
    std::cout << "STL QuickSort applied\n";
};

// Stable sort strategy (preserves original order of equal elements):
auto stableSortStrategy = [](auto& vec, auto comparator) {
    std::stable_sort(vec.begin(), vec.end(), comparator);
    //  ↑ std::stable_sort: like sort but STABLE. Equal elements maintain original relative order.
    //    Use when sorting by one key while preserving order from previous sort.
    std::cout << "Stable sort applied\n";
};

// USAGE:
// DataSorter<int> sorter(quickSortStrategy);
// auto result = sorter.sort({5,2,8,1,9,3}, [](int a, int b){ return a < b; });
//  ↑ Lambda comparator: [](int a, int b){ return a < b; } → sort ascending.
// sorter.setStrategy(stableSortStrategy);  // Switch algorithm at runtime.
```

---

## PATTERN 2: OBSERVER

```
PROBLEM: When one object changes state, other objects need to be notified.
         The publisher doesn't know WHO is listening. Decoupled notification.

TERMS:
  Subject / Observable / Publisher: the object whose state changes.
  Observer / Listener / Subscriber: objects that want to be notified.

REAL EXAMPLES:
  - Twitter: Tweet posted (subject) → all followers notified (observers)
  - YouTube: Video published → subscribers notified
  - Stock price changes → all price alert watchers notified
  - MVC: Model changes → View(s) update automatically
  - Kafka: producer publishes → all consumer groups receive the message

ANALOGY: Magazine subscription.
  Publisher (magazine company) doesn't know who the subscribers are.
  It just sends the magazine to a list. Subscribers receive it.
```

### Java — Observer

```java
// ── Observer: Stock Price Alert System ────────────────────────────────────────

import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

// OBSERVER INTERFACE:
interface StockObserver {
    void onPriceChange(String symbol, double oldPrice, double newPrice);
    //  ↑ Called when stock price changes.
    //    All observers implement this method.
    //    Subject calls this on each observer in its list.
}

// SUBJECT (Observable):
class StockTicker {
    //  ↑ The "publisher." Knows about its observers. Notifies them when price changes.

    private final String symbol;    // e.g., "INFOSYS", "TCS"
    private double currentPrice;
    private final List<StockObserver> observers = new ArrayList<>();
    //  ↑ List of observers (the subscriber list).
    //    ArrayList: allows duplicates and is ordered. Thread safety not addressed here
    //    (production: use CopyOnWriteArrayList for concurrent modifications during iteration).

    public StockTicker(String symbol, double initialPrice) {
        this.symbol       = symbol;
        this.currentPrice = initialPrice;
    }

    // SUBSCRIBE:
    public void addObserver(StockObserver observer) {
        observers.add(observer);
        System.out.println("Observer added for " + symbol + ". Total: " + observers.size());
    }

    // UNSUBSCRIBE:
    public void removeObserver(StockObserver observer) {
        observers.remove(observer);
        //  ↑ removes by OBJECT EQUALITY (uses observer.equals()).
        //    If observer doesn't implement equals(): uses reference equality (memory address).
    }

    // NOTIFY all observers:
    private void notifyObservers(double oldPrice, double newPrice) {
        //  ↑ private: only called internally when price changes.
        for (StockObserver observer : observers) {
            observer.onPriceChange(symbol, oldPrice, newPrice);
            //  ↑ POLYMORPHISM: correct onPriceChange() called for each observer type.
            //    If observer is PriceAlertObserver → its version runs.
            //    If observer is PortfolioObserver → its version runs.
            //    Subject doesn't know or care about observer types.
        }
    }

    // UPDATE PRICE (triggers notification):
    public void updatePrice(double newPrice) {
        if (newPrice == currentPrice) return;   // No change → no notification
        double oldPrice   = currentPrice;
        currentPrice = newPrice;
        //  ↑ Update state FIRST, then notify. Observers see the new state.
        notifyObservers(oldPrice, newPrice);
        //  ↑ PUSH model: we PUSH the change data to observers.
        //    Alternative PULL model: just notify "something changed", observers pull current state.
    }

    public double getCurrentPrice() { return currentPrice; }
    public String getSymbol()       { return symbol; }
}

// CONCRETE OBSERVER 1: Email alert when price drops below threshold
class PriceAlertObserver implements StockObserver {
    private final String email;
    private final double alertBelowPrice;
    //  ↑ Send alert when price drops below this value.

    public PriceAlertObserver(String email, double alertBelowPrice) {
        this.email           = email;
        this.alertBelowPrice = alertBelowPrice;
    }

    @Override
    public void onPriceChange(String symbol, double oldPrice, double newPrice) {
        if (newPrice < alertBelowPrice && oldPrice >= alertBelowPrice) {
            //  ↑ Trigger: price crossed the threshold (was above, now below).
            //    Not triggered on every price change. Only when threshold is crossed.
            System.out.printf("🔔 EMAIL ALERT to %s: %s dropped below ₹%.2f (current: ₹%.2f)%n",
                              email, symbol, alertBelowPrice, newPrice);
        }
    }
}

// CONCRETE OBSERVER 2: Portfolio tracker
class PortfolioObserver implements StockObserver {
    private final String ownerName;
    private final int sharesOwned;
    private double portfolioValue;

    public PortfolioObserver(String ownerName, int sharesOwned, double purchasePrice) {
        this.ownerName = ownerName;
        this.sharesOwned  = sharesOwned;
        this.portfolioValue = sharesOwned * purchasePrice;
    }

    @Override
    public void onPriceChange(String symbol, double oldPrice, double newPrice) {
        double newValue = sharesOwned * newPrice;
        double pnl      = newValue - portfolioValue;
        //  ↑ PnL = Profit and Loss.
        System.out.printf("📊 %s's portfolio: %s × %d = ₹%.2f (PnL: %+.2f)%n",
                          ownerName, symbol, sharesOwned, newValue, pnl);
        //  ↑ %+.2f: always show sign (+ or -). 500.00 → "+500.00", -200.00 → "-200.00".
        portfolioValue = newValue;
    }
}

// LAMBDA OBSERVER (Java 8+ functional style):
// No need to create a class for simple observers:
// StockObserver logger = (symbol, old, newP) -> {
//     System.out.printf("LOG: %s: ₹%.2f → ₹%.2f%n", symbol, old, newP);
// };
//  ↑ Lambda implements the single-method interface (functional interface).
//    Java 8+: any interface with ONE abstract method = functional interface.
//    Can be implemented by a lambda. No class needed.

// USAGE:
// StockTicker infosys = new StockTicker("INFOSYS", 1500.0);
// infosys.addObserver(new PriceAlertObserver("sachin@gmail.com", 1450.0));
// infosys.addObserver(new PortfolioObserver("Sachin", 100, 1500.0));
// infosys.addObserver((s, o, n) -> System.out.printf("LOG: %s ₹%.2f→₹%.2f%n", s, o, n));
//
// infosys.updatePrice(1460.0);  // Notifies all 3 observers
// infosys.updatePrice(1440.0);  // Alert triggers (crossed 1450 threshold)
```

---

## PATTERN 3: TEMPLATE METHOD

```
PROBLEM: Multiple classes follow the SAME algorithm skeleton but differ in specific steps.

WITHOUT TEMPLATE METHOD:
  class CoffeeBarista { void prepare() { boilWater(); brewCoffee(); pourInCup(); } }
  class TeaBarista    { void prepare() { boilWater(); steepTea();   pourInCup(); } }
  boilWater() and pourInCup() are DUPLICATED. DRY (Don't Repeat Yourself) violated.

WITH TEMPLATE METHOD:
  abstract class Beverage {
    final void prepare() { boilWater(); brew(); pourInCup(); }   // FIXED SKELETON
    void boilWater()     { ... }                                  // CONCRETE (shared)
    abstract void brew();                                          // ABSTRACT (customized)
    void pourInCup()     { ... }                                  // CONCRETE (shared)
  }
  class Coffee extends Beverage { void brew() { brewCoffee(); } }
  class Tea    extends Beverage { void brew() { steepTea();   } }

REAL EXAMPLES:
  - TranscodeJob.process() (YouTube CS06): validate → extract metadata → transcode → publish
  - PaymentProcessor.process() (CS09): validate → authorize → capture
  - JUnit test lifecycle: @BeforeEach → @Test → @AfterEach
  - Spring's JdbcTemplate: getConnection → execute → releaseConnection (fixed), your SQL varies.
```

### Java — Template Method

```java
// ── Template Method: Data Export Pipeline ─────────────────────────────────────

abstract class DataExporter {
    //  ↑ Abstract: defines the skeleton. Subclasses fill in specific steps.

    // TEMPLATE METHOD — defines the algorithm skeleton:
    public final void export(String source, String destination) {
        //  ↑ final: CANNOT be overridden by subclasses.
        //    The SKELETON is fixed. Only the STEPS can vary.
        //    This is the key to Template Method: the algorithm order is guaranteed.

        System.out.println("=== Export started ===");
        List<Map<String, Object>> data = extractData(source);
        //  ↑ Step 1: Extract data. (varies by subclass)

        List<Map<String, Object>> validated = validateData(data);
        //  ↑ Step 2: Validate. Default behavior (can be overridden).

        List<Map<String, Object>> transformed = transformData(validated);
        //  ↑ Step 3: Transform. (varies by subclass: CSV vs JSON vs Excel formatting)

        writeOutput(transformed, destination);
        //  ↑ Step 4: Write. (varies by subclass: file format)

        cleanup();
        //  ↑ Step 5: Cleanup. (hook — subclass may or may not override)
        System.out.println("=== Export completed ===");
    }

    // ABSTRACT STEPS: subclasses MUST implement these:
    protected abstract List<Map<String, Object>> extractData(String source);
    //  ↑ abstract: no body. Each subclass implements it differently.
    //  ↑ protected: accessible in subclasses but not from outside.

    protected abstract List<Map<String, Object>> transformData(List<Map<String, Object>> data);

    protected abstract void writeOutput(List<Map<String, Object>> data, String dest);

    // CONCRETE STEP with default behavior (subclass CAN override if needed):
    protected List<Map<String, Object>> validateData(List<Map<String, Object>> data) {
        //  ↑ Not abstract: has a default implementation.
        //    Subclass can override if they need special validation.
        //    Or leave as-is to use this default.
        System.out.println("Validating " + data.size() + " records...");
        return data.stream()
                   .filter(row -> !row.isEmpty())
                   //  ↑ filter: keep only non-empty rows.
                   .collect(java.util.stream.Collectors.toList());
    }

    // HOOK METHOD: empty by default. Subclass can override to add cleanup behaviour.
    protected void cleanup() {
        //  ↑ "Hook": template method calls it, but default is no-op (do nothing).
        //    Subclass that opened a DB connection: override this to close it.
        //    Subclass that created temp files: override this to delete them.
    }
}

// CONCRETE EXPORTER 1: CSV
class CsvExporter extends DataExporter {
    @Override
    protected List<Map<String, Object>> extractData(String source) {
        System.out.println("Extracting from source: " + source);
        return List.of(
            Map.of("name", "Alice", "age", 30, "city", "Mumbai"),
            Map.of("name", "Bob",   "age", 25, "city", "Delhi")
        );
        //  ↑ Map.of(...): immutable map with given key-value pairs. Java 9+.
        //  ↑ List.of(...): immutable list. Java 9+.
    }

    @Override
    protected List<Map<String, Object>> transformData(List<Map<String, Object>> data) {
        System.out.println("Transforming to CSV format...");
        return data;   // No transformation needed for CSV (raw data is fine)
    }

    @Override
    protected void writeOutput(List<Map<String, Object>> data, String dest) {
        System.out.println("Writing CSV to: " + dest);
        // Write header:
        System.out.println("name,age,city");
        // Write rows:
        for (var row : data) {
            //  ↑ var: Java 10+ type inference. Compiler infers: Map<String, Object>.
            //    Equivalent to: for (Map<String, Object> row : data)
            System.out.printf("%s,%s,%s%n", row.get("name"), row.get("age"), row.get("city"));
        }
    }
}

// CONCRETE EXPORTER 2: JSON
class JsonExporter extends DataExporter {
    @Override
    protected List<Map<String, Object>> extractData(String source) {
        return List.of(Map.of("product", "Laptop", "price", 75000));
    }

    @Override
    protected List<Map<String, Object>> transformData(List<Map<String, Object>> data) {
        System.out.println("Transforming to JSON format...");
        return data;
    }

    @Override
    protected void writeOutput(List<Map<String, Object>> data, String dest) {
        System.out.println("Writing JSON to: " + dest);
        System.out.println("[");
        for (int i = 0; i < data.size(); i++) {
            System.out.println("  " + data.get(i));
            if (i < data.size() - 1) System.out.println(",");
        }
        System.out.println("]");
    }

    @Override
    protected void cleanup() {
        //  ↑ Override the hook: this exporter needs to close a file handle.
        System.out.println("JSON: closing output stream.");
    }
}

// USAGE:
// DataExporter csv = new CsvExporter();
// csv.export("orders_db", "exports/orders.csv");
//
// DataExporter json = new JsonExporter();
// json.export("products_db", "exports/products.json");
//
// Both call export() → same algorithm skeleton → different step implementations.
```

---

## PATTERN 4: COMMAND

```
PROBLEM: Encapsulate an operation as an object.
         Benefits:
         - Queue operations (execute later)
         - Undo/Redo (store history of commands)
         - Log/Replay operations (for disaster recovery)
         - Remote execution (send command object over network)

ANALOGY: Restaurant order.
  Waiter (Invoker) takes your order (Command object) to kitchen (Receiver).
  Order slip is a Command: contains: what to do + who to do it + what ingredients.
  
REAL EXAMPLES:
  - Text editor: each keystroke = Command. Ctrl+Z = undo last command.
  - Database transactions: BEGIN, INSERT, UPDATE, COMMIT = commands (can rollback).
  - Job queue: Kafka message = command executed by consumer.
  - Git commits: each commit = a command on the repo state.
```

### Java — Command

```java
// ── Command: Text Editor with Undo ────────────────────────────────────────────

import java.util.Deque;
import java.util.ArrayDeque;

// COMMAND INTERFACE:
interface Command {
    void execute();       // Do the operation
    void undo();          // Reverse the operation
    String getDescription();   // For logging/display
}

// RECEIVER: the object that actually does the work
class TextDocument {
    private final StringBuilder content = new StringBuilder();
    //  ↑ StringBuilder: mutable string. More efficient than String for repeated appending.
    //    String is immutable: every + creates a new String object.
    //    StringBuilder: modifies in-place. No new objects created for each append.

    public void insertText(int position, String text) {
        content.insert(position, text);
        //  ↑ insert(index, text): inserts text at the given position.
        //    Everything after position is shifted right.
    }

    public void deleteText(int start, int length) {
        content.delete(start, start + length);
        //  ↑ delete(start, end): removes characters from start (inclusive) to end (exclusive).
        //    end = start + length → deletes 'length' characters starting at 'start'.
    }

    public String getText() { return content.toString(); }
    //  ↑ toString(): converts StringBuilder to immutable String.

    public int length()     { return content.length(); }
}

// CONCRETE COMMAND 1: Insert
class InsertCommand implements Command {
    private final TextDocument document;
    private final int position;
    private final String text;

    public InsertCommand(TextDocument doc, int position, String text) {
        this.document = doc;
        this.position = position;
        this.text     = text;
    }

    @Override
    public void execute() {
        document.insertText(position, text);
        //  ↑ Delegate to the receiver (TextDocument).
        //    Command doesn't contain the logic — it just invokes the receiver.
    }

    @Override
    public void undo() {
        document.deleteText(position, text.length());
        //  ↑ UNDO insert = delete the same text at the same position.
        //    This is why Command has both execute() and undo().
    }

    @Override
    public String getDescription() {
        return "Insert '" + text + "' at position " + position;
    }
}

// CONCRETE COMMAND 2: Delete
class DeleteCommand implements Command {
    private final TextDocument document;
    private final int start;
    private final int length;
    private String deletedText;   // NOT final: set when execute() runs
    //  ↑ Store deleted text so undo() can re-insert it.
    //    Captured at execute() time (not at construction time — position might change).

    public DeleteCommand(TextDocument doc, int start, int length) {
        this.document = doc;
        this.start    = start;
        this.length   = length;
    }

    @Override
    public void execute() {
        // Capture what we're about to delete (needed for undo):
        deletedText = document.getText().substring(start, start + length);
        //  ↑ .substring(start, end): returns chars from start (inclusive) to end (exclusive).
        document.deleteText(start, length);
    }

    @Override
    public void undo() {
        document.insertText(start, deletedText);
        //  ↑ Re-insert the deleted text at the same position.
    }

    @Override
    public String getDescription() { return "Delete " + length + " chars at " + start; }
}

// INVOKER: manages command history, executes commands, supports undo:
class TextEditor {
    private final TextDocument document = new TextDocument();
    private final Deque<Command> history = new ArrayDeque<>();
    //  ↑ Deque: double-ended queue. Can add/remove from both ends.
    //  ↑ ArrayDeque: efficient Deque implementation (array-backed, no nulls).
    //    Using as a STACK here: push to top (addFirst), pop from top (removeFirst).
    //  ↑ Command history: most recent command at the top (front).

    private static final int MAX_HISTORY = 100;
    //  ↑ static final: constant. Cannot change. Shared across all instances.
    //    Limits undo history (prevents unbounded memory usage).

    public void executeCommand(Command command) {
        command.execute();
        //  ↑ Execute the command (do the actual operation).
        history.addFirst(command);
        //  ↑ addFirst: add to FRONT of deque (like stack push).
        //    Most recent command is now at the front.
        if (history.size() > MAX_HISTORY) {
            history.removeLast();
            //  ↑ removeLast: remove oldest command when history is full.
        }
        System.out.println("Executed: " + command.getDescription());
    }

    public void undo() {
        if (history.isEmpty()) {
            System.out.println("Nothing to undo.");
            return;
        }
        Command last = history.removeFirst();
        //  ↑ removeFirst: remove and return from FRONT (like stack pop).
        //    The MOST RECENT command is undone.
        last.undo();
        System.out.println("Undone: " + last.getDescription());
    }

    public String getContent() { return document.getText(); }
    public TextDocument getDocument() { return document; }
}

// USAGE:
// TextEditor editor = new TextEditor();
// editor.executeCommand(new InsertCommand(editor.getDocument(), 0, "Hello, World!"));
// System.out.println(editor.getContent());  // "Hello, World!"
//
// editor.executeCommand(new InsertCommand(editor.getDocument(), 7, "Beautiful "));
// System.out.println(editor.getContent());  // "Hello, Beautiful World!"
//
// editor.undo();
// System.out.println(editor.getContent());  // "Hello, World!" (beautiful removed)
//
// editor.undo();
// System.out.println(editor.getContent());  // "" (all undone)
```

---

## PATTERN 5: STATE

```
PROBLEM: An object's behaviour changes drastically depending on its internal STATE.
         Using if/else or switch for state-dependent behaviour leads to complex, unmaintainable code.
         
WITH STATE: Each state is a separate class. Object delegates to its current state object.

REAL EXAMPLES:
  - Traffic light: RED → YELLOW → GREEN → RED ...
  - ATM: IdleState → PinEnteredState → AccountSelectedState → ...
  - Order: PENDING → PROCESSING → SHIPPED → DELIVERED / CANCELLED
  - Video: UPLOADING → PROCESSING → PUBLISHED / PRIVATE (CS06 YouTube)
  - Payment: PENDING → AUTHORIZED → CAPTURED / FAILED / REFUNDED (CS09)
```

### Java — State

```java
// ── State: ATM Machine ────────────────────────────────────────────────────────

// STATE INTERFACE:
interface ATMState {
    void insertCard(ATMMachine atm);
    void enterPin(ATMMachine atm, String pin);
    void selectAmount(ATMMachine atm, double amount);
    void ejectCard(ATMMachine atm);
}

// CONTEXT: ATMMachine holds current state and delegates to it:
class ATMMachine {
    private ATMState currentState;
    private double balance;
    private String correctPin = "1234";

    public ATMMachine(double initialBalance) {
        balance = initialBalance;
        currentState = new IdleState();
        //  ↑ Start in IdleState. Card not inserted.
    }

    // DELEGATE all operations to the current state:
    public void insertCard()            { currentState.insertCard(this); }
    public void enterPin(String pin)    { currentState.enterPin(this, pin); }
    public void selectAmount(double a)  { currentState.selectAmount(this, a); }
    public void ejectCard()             { currentState.ejectCard(this); }

    // STATE TRANSITION: change current state:
    public void setState(ATMState state) {
        System.out.println("State: " + state.getClass().getSimpleName());
        //  ↑ getClass().getSimpleName(): gets class name without package prefix.
        //    "IdleState", "AuthenticatedState", etc. Useful for debugging.
        currentState = state;
    }

    public double getBalance()           { return balance; }
    public void setBalance(double b)     { balance = b; }
    public boolean verifyPin(String pin) { return correctPin.equals(pin); }
    //  ↑ .equals(): String comparison. NEVER use == for String content comparison.
    //    == checks REFERENCE equality (same object in memory).
    //    .equals() checks VALUE equality (same characters).
    //    "1234" == "1234" might be false! "1234".equals("1234") is always true.
}

// CONCRETE STATES:
class IdleState implements ATMState {
    //  ↑ ATM is idle. Waiting for card to be inserted.

    @Override public void insertCard(ATMMachine atm) {
        System.out.println("Card inserted. Please enter PIN.");
        atm.setState(new CardInsertedState());
        //  ↑ Transition to next state.
    }
    @Override public void enterPin(ATMMachine atm, String pin) {
        System.out.println("Please insert your card first.");
    }
    @Override public void selectAmount(ATMMachine atm, double amount) {
        System.out.println("Please insert card and enter PIN first.");
    }
    @Override public void ejectCard(ATMMachine atm) {
        System.out.println("No card to eject.");
    }
}

class CardInsertedState implements ATMState {
    @Override public void insertCard(ATMMachine atm) {
        System.out.println("Card already inserted.");
    }
    @Override public void enterPin(ATMMachine atm, String pin) {
        if (atm.verifyPin(pin)) {
            System.out.println("PIN correct. Select amount.");
            atm.setState(new AuthenticatedState());
        } else {
            System.out.println("Wrong PIN. Try again.");
            // Stay in CardInsertedState. Could add: eject after 3 wrong attempts.
        }
    }
    @Override public void selectAmount(ATMMachine atm, double amount) {
        System.out.println("Enter PIN first.");
    }
    @Override public void ejectCard(ATMMachine atm) {
        System.out.println("Card ejected.");
        atm.setState(new IdleState());   // Back to idle.
    }
}

class AuthenticatedState implements ATMState {
    @Override public void insertCard(ATMMachine atm) { System.out.println("Card already in."); }
    @Override public void enterPin(ATMMachine atm, String pin) { System.out.println("PIN already verified."); }

    @Override
    public void selectAmount(ATMMachine atm, double amount) {
        if (amount > atm.getBalance()) {
            System.out.printf("Insufficient funds. Balance: ₹%.2f%n", atm.getBalance());
        } else {
            atm.setBalance(atm.getBalance() - amount);
            System.out.printf("Dispensing ₹%.2f. New balance: ₹%.2f%n", amount, atm.getBalance());
            atm.setState(new IdleState());   // Transaction complete → idle.
        }
    }

    @Override
    public void ejectCard(ATMMachine atm) {
        System.out.println("Card ejected.");
        atm.setState(new IdleState());
    }
}

// USAGE:
// ATMMachine atm = new ATMMachine(10000.0);
// atm.insertCard();          // IdleState → CardInsertedState
// atm.enterPin("9999");      // Wrong PIN — stays in CardInsertedState
// atm.enterPin("1234");      // Correct → CardInsertedState → AuthenticatedState
// atm.selectAmount(3000);    // Dispenses ₹3000 → AuthenticatedState → IdleState
// atm.selectAmount(5000);    // Error: no card. IdleState handles it gracefully.
```

---

## Pattern Summary

```
STRATEGY:
  When: same operation, multiple algorithms. Switch at runtime.
  Signal: "How do we add a new pricing/sorting/routing algorithm without breaking existing?"
  Java: interface Strategy + concrete classes. Context holds Strategy field.
  C++:  std::function or virtual interface.

OBSERVER:
  When: event-driven. Many listeners for one event.
  Signal: "When X happens, notify Y, Z, W."
  Java: Subject.notifyObservers() calls each Observer.onEvent().
  C++:  std::vector<std::function> or virtual Observer interface.

TEMPLATE METHOD:
  When: algorithm skeleton shared, specific steps vary.
  Signal: "All exporters follow: extract → validate → transform → write."
  Java: abstract class with final template method + abstract/concrete step methods.
  C++:  Base class with virtual/pure virtual steps called from non-virtual template method.

COMMAND:
  When: encapsulate operation as object. Need undo, queue, log, retry.
  Signal: "Need undo/redo?" or "Need to queue operations?"
  Java: interface Command { execute(); undo(); }. Stack for history.
  C++:  Same pattern. Can use std::function for execute + separate undo function.

STATE:
  When: object behaviour changes drastically based on internal state.
  Signal: Status enum with if/else or switch everywhere → State Pattern.
  Java: interface State. Context delegates to currentState object.
  C++:  Same. Use std::unique_ptr<State> in context. Replace to transition.

QUICK COMPARISON:
  Strategy vs State:
    Strategy: algorithm chosen by CALLER (external). State changes internally.
    Strategy: context doesn't know which strategy. State: context DOES know current state.
    Strategy: strategy doesn't reference context usually. State: state often references context.
  
  Observer vs Command:
    Observer: passive. Observes events. No undo.
    Command: active. Encapsulates action. Supports undo.
    
  Template Method vs Strategy:
    Template Method: algorithm skeleton in BASE CLASS. Steps overridden via inheritance.
    Strategy: algorithm entirely in SEPARATE CLASS. Injected via composition.
    Template Method: use inheritance. Strategy: use composition (prefer composition over inheritance).
```

---

## HOW BEHAVIORAL PATTERNS APPEAR IN THE LLD CASE STUDIES

### STRATEGY — Where it appears

```
CS04 Uber (CS04_Uber.md):
  IFareStrategy → SurgePricingStrategy, NormalPricingStrategy, FlatRatePricingStrategy.
  UberService holds a reference to the current strategy.
  Peak hours: swap to SurgePricingStrategy. Off-peak: swap to NormalPricingStrategy.
  RUNTIME swap without changing UberService code.
  
  This is the most classic Strategy use case: same algorithm slot, different algorithm.

CS05 Netflix (CS05_Netflix.md):
  IAdaptiveBitrateStrategy → BandwidthAwareStrategy, QualityFirstStrategy, DataSaverStrategy.
  StreamingSession holds current ABR strategy.
  Good connection: QualityFirstStrategy. Poor: DataSaverStrategy.
  Swap at runtime based on network conditions. Player code unchanged.

CS10 MakeMyTrip (CS10_MakeMyTrip.md):
  ICancellationPolicy → FlexiblePolicy, ModeratePolicy, StrictPolicy.
  Booking holds a policy reference. Different fare classes get different policies.
  Economy: StrictPolicy. Business flex: FlexiblePolicy.
  cancellation_service.calculate_refund(booking) → delegates to booking.policy.calculate_refund().

CS09 Payment Gateway (CS09_Payment_Gateway.md):
  IPaymentProcessor → CardProcessor, UPIProcessor, WalletProcessor.
  PaymentGatewayService._route_to_processor(type) → returns the right strategy.
  Actual charging: processor.charge(amount, card) — same call for all.

CS11 AI Systems (CS11_AI_Systems.md):
  IChunkingStrategy → FixedSizeChunker, SentenceBoundaryChunker, SemanticChunker.
  RAGService holds current chunking strategy.
  Different document types need different chunking:
  Legal docs: SentenceBoundaryChunker. Code: FixedSizeChunker.
```

### OBSERVER — Where it appears

```
CS08 Twitter (CS08_Twitter.md):
  Tweet posted → FanoutService notifies all followers.
  The "notification" mechanism is Observer at scale.
  TweetPublisher (subject) → pushes tweet ID to all follower timelines.
  
  Production: Kafka is the Observer infrastructure.
  Producer (subject) publishes to topic. Consumer groups (observers) subscribe.

CS05 Netflix:
  VideoUploadEvent → multiple observers:
    TranscodeObserver (start transcoding to all qualities)
    CatalogObserver (add to content catalog)
    CDNObserver (push to CDN edge nodes)
    NotificationObserver (alert subscribers of new content)
  All registered on the upload event. Fire independently.

CS06 YouTube:
  SubscriptionService: when Channel publishes, notify all subscribers.
  Channel (subject) → calls notify() → emails/push notifications to all subscriber accounts.
  Subscriber (observer): receives onNewVideo(channel, video) callback.

CS09 Payment Gateway:
  PaymentCompletedEvent → multiple observers:
    InventoryObserver (decrement stock)
    LedgerObserver (record transaction)
    NotificationObserver (send receipt)
    FraudObserver (update risk profile)
  All registered on the payment completion event. Decoupled. Independent.

CS10 MakeMyTrip:
  BookingStatusChangeObserver: when flight status changes (delayed, cancelled):
    AlertObserver (notify passenger)
    RebookingObserver (auto-suggest alternatives)
    RefundObserver (trigger refund if cancelled)

JAVA/C++:
  Java: List<Observer> observers. notifyAll() calls observer.onEvent() for each.
       Java 8+: Lambda observers (no class needed for simple cases).
  C++: vector<function<void(Event)>> handlers. notify() calls each in loop.
```

### TEMPLATE METHOD — Where it appears

```
CS06 YouTube (CS06_YouTube.md):
  VideoProcessingPipeline (abstract base):
    final void process(video):    ← TEMPLATE METHOD (fixed skeleton)
      1. validateVideo()           ← abstract (subclass overrides)
      2. extractMetadata()         ← concrete (shared)
      3. transcodeAllQualities()   ← abstract (subclass overrides)
      4. generateThumbnail()       ← concrete (shared)
      5. publishToIndex()          ← abstract (subclass overrides)
      6. notifySubscribers()       ← hook (optional override)
  
  ShortVideoProcessor overrides: validateVideo (shorts ≤ 60s), transcodeAllQualities (fewer resolutions).
  LongVideoProcessor overrides: validateVideo (up to 12h), transcodeAllQualities (4K included).
  The PIPELINE STEPS are fixed. The STEP IMPLEMENTATIONS vary.

CS09 Payment Gateway:
  PaymentProcessor (abstract):
    final void process(request):
      1. validateRequest()    ← concrete (shared validation)
      2. checkFraud()         ← hook (default: skip)
      3. authorize()          ← abstract (card vs UPI differ)
      4. capture()            ← abstract (card vs UPI differ)
      5. logTransaction()     ← concrete (shared logging)
      6. sendWebhook()        ← hook (optional override)
  
  CardProcessor overrides: authorize() (CVV check + bank call), capture() (Stripe capture API).
  UPIProcessor overrides: authorize() (VPA lookup), capture() (UPI collect).

CS10 MakeMyTrip:
  SearchPipeline (abstract):
    final List<Result> search(query):
      1. parseQuery()          ← concrete (shared parsing)
      2. fetchInventory()      ← abstract (flights vs hotels differ)
      3. applyFilters()        ← concrete (shared filter logic)
      4. rankResults()         ← abstract (flight rank vs hotel rank differ)
      5. formatResponse()      ← hook (default JSON format)
  
  FlightSearchPipeline: fetchInventory() calls airline GDS API, rankResults() by price+duration.
  HotelSearchPipeline: fetchInventory() calls hotel inventory, rankResults() by price+rating.

JAVA: abstract class with final template method + abstract/protected step methods.
C++: Base class with non-virtual template method calling pure virtual steps.
     Override keyword ensures correct method is overridden, not accidentally shadowed.
```

### COMMAND — Where it appears

```
CS01 URL Shortener:
  CreateShortUrlCommand: encapsulates the create operation.
  DeleteShortUrlCommand: encapsulates the delete.
  Stored in an audit log. Can be replayed for disaster recovery.
  Pattern: every admin action = a Command object stored in DB.

CS08 Twitter:
  PostTweetCommand: encapsulates posting (tweet content, author, timestamp, idempotency_key).
  DeleteTweetCommand: encapsulates deletion.
  Both go to a Kafka queue (command queue). Workers execute them.
  Retry: if worker fails, re-process the command (idempotent commands are safe to retry).

CS10 MakeMyTrip:
  BookingCommand: encapsulates the full booking (flights + hotels + activities + passengers).
  CancellationCommand: encapsulates cancellation (booking_id, reason, refund_amount).
  These commands are stored in DB before execution.
  If payment fails midway: rollback all commands in the sequence (distributed saga).

CS11 AI Systems:
  Tool calls in agents are Commands.
  WebSearchCommand(query="Python asyncio tutorial"): encapsulates the web search action.
  CodeExecutionCommand(code="import numpy..."): encapsulates code run.
  Agent decides which Command to execute. Commands are logged. Can be replayed.

JAVA: interface Command { execute(); undo(); }. Deque<Command> history for undo stack.
C++: Similar. std::function<void()> for execute + separate undo function.
```

### STATE — Where it appears

```
CS04 Uber:
  TripState machine:
  REQUESTED → (driver_accepted) → DRIVER_ASSIGNED → (driver_arrived) → IN_PROGRESS
  → (trip_ended) → COMPLETED | CANCELLED
  
  Each state has different behavior for:
  cancel(): REQUESTED → full refund. IN_PROGRESS → partial charge.
  on_timeout(): REQUESTED → try next driver. IN_PROGRESS → do nothing.

CS06 YouTube:
  VideoState machine:
  UPLOADING → PROCESSING → PUBLISHED | PRIVATE | UNLISTED | REMOVED
  
  Each state affects: is_searchable(), is_playable(), can_edit(), can_delete().
  PROCESSING: not searchable, not playable.
  PUBLISHED: searchable, playable.
  REMOVED: not searchable, not playable, cannot edit.

CS09 Payment Gateway:
  PaymentState machine:
  PENDING → AUTHORIZED → CAPTURED → REFUNDED
                       → FAILED
  
  Each state determines: can_refund(), can_capture(), can_cancel().
  CAPTURED: can_refund() = true. FAILED: can_refund() = false.
  REFUNDED: can_refund() = false (can't refund twice).

CS10 MakeMyTrip:
  BookingState machine:
  HOLD → CONFIRMED → TICKETED → CANCELLED / REFUNDED
  
  HOLD: payment not done. Can cancel for free.
  CONFIRMED: payment done. Cancellation has charge.
  TICKETED: airline issued ticket. Cancellation requires airline API call.

JAVA: interface BookingState. Context delegates to currentState object.
C++: Same. unique_ptr<IState> in context. setState() replaces the pointer.
```

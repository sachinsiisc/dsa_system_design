# LLD Topic 06: Concurrency & Thread Safety
## Locks, Atomic, Deadlock, Thread Pool | Java + C++ | Every Keyword

---

> **WHY CONCURRENCY IN LLD INTERVIEWS?**
> Real systems are multi-threaded. "How do you handle concurrent requests?"
> Interviewers directly test: shared state, race conditions, deadlocks.
> Every case study we wrote (Uber, Twitter, YouTube, Payment) uses locking.
> You MUST understand synchronized, Lock, volatile, atomic in Java
> and mutex, shared_mutex, atomic, lock_guard in C++.

---

## CONCEPT 1: RACE CONDITION

```
WHAT: Two threads modify shared data simultaneously → unpredictable result.

EXAMPLE:
  count = 0
  Thread A: read count (0), Thread B: read count (0)
  Thread A: add 1, write 1. Thread B: add 1, write 1.
  RESULT: count = 1. WRONG! Should be 2.
  
  This is a race condition. Result depends on thread scheduling (non-deterministic).
  
WHY IT HAPPENS:
  count++ is NOT atomic. It's actually 3 steps:
  1. READ count into register
  2. ADD 1 to register
  3. WRITE register back to count
  Between step 1 and 3, another thread can interfere.
```

### Java — Race Condition Demo + Fixes

```java
// ── BAD: Race condition ────────────────────────────────────────────────────────

class BadCounter {
    private int count = 0;
    //  ↑ Shared mutable state. Accessed by multiple threads. NOT thread-safe.

    public void increment() {
        count++;
        //  ↑ count++ LOOKS like one operation. Compiled to: read, add, write.
        //    Multiple threads doing this simultaneously = lost updates.
    }

    public int get() { return count; }
}

// Try this: 1000 threads each increment 1000 times.
// Expected: count = 1,000,000.
// Actual: 800,000 to 999,999 (non-deterministic). WRONG.

// ── FIX 1: synchronized method ────────────────────────────────────────────────

class SynchronizedCounter {
    private int count = 0;

    public synchronized void increment() {
        //  ↑ synchronized: acquires the INTRINSIC LOCK (monitor) of 'this' object.
        //    Only ONE thread can execute a synchronized method at a time.
        //    Other threads: BLOCKED (wait in the queue).
        //    Lock released automatically when method exits (even if exception thrown).
        count++;
        //  ↑ Now thread-safe: only one thread executes this at a time.
    }

    public synchronized int get() {
        //  ↑ Getter also synchronized: ensures consistent read (visibility).
        //    Without synchronized on getter: thread might read stale cached value.
        return count;
    }
}

// ── FIX 2: AtomicInteger — best for simple counters ──────────────────────────

import java.util.concurrent.atomic.AtomicInteger;

class AtomicCounter {
    private final AtomicInteger count = new AtomicInteger(0);
    //  ↑ AtomicInteger: wrapper around int. All operations are ATOMIC (indivisible).
    //    Uses CPU-level atomic instructions (LOCK prefix on x86-64).
    //    FASTER than synchronized for simple counters (no mutex overhead).
    //    No context switch needed for atomic operations.

    public void increment() {
        count.incrementAndGet();
        //  ↑ incrementAndGet(): atomically increments by 1 and returns new value.
        //    Equivalent to: count++ but thread-safe.
        //    Internal: CAS loop (Compare-And-Swap).
        //    CAS(expected, newValue): if count == expected, set to newValue. Retry if not.
    }

    public int get() {
        return count.get();
        //  ↑ Atomic read. Always returns the latest value (no caching).
    }

    public int incrementAndGet() { return count.incrementAndGet(); }

    public boolean compareAndSet(int expected, int newValue) {
        return count.compareAndSet(expected, newValue);
        //  ↑ CAS: if current value == expected → set to newValue, return true.
        //          else → don't change, return false.
        //    Used for lock-free algorithms (Singleton, optimistic locking).
    }
}

// ── FIX 3: ReentrantLock — more control than synchronized ─────────────────────

import java.util.concurrent.locks.ReentrantLock;
import java.util.concurrent.locks.Condition;

class LockBasedCounter {
    private int count = 0;
    private final ReentrantLock lock = new ReentrantLock();
    //  ↑ ReentrantLock: explicit lock. Same thread can acquire it multiple times (reentrant).
    //    More powerful than synchronized:
    //    - tryLock(): non-blocking. Returns false instead of blocking.
    //    - lockInterruptibly(): can be interrupted while waiting.
    //    - Condition variables: fine-grained wait/notify.
    //    - fairness: new ReentrantLock(true) → FIFO ordering of waiting threads.

    public void increment() {
        lock.lock();
        //  ↑ Acquire the lock. Blocks if another thread holds it.
        try {
            count++;
            //  ↑ Critical section: only one thread here at a time.
        } finally {
            lock.unlock();
            //  ↑ ALWAYS release in finally block!
            //    Without finally: if increment throws → lock NEVER released → deadlock!
            //    finally: executes even if exception is thrown in try block.
        }
    }

    public boolean tryIncrement() {
        if (lock.tryLock()) {
            //  ↑ tryLock(): try to acquire. Returns true if successful, false if not.
            //    NON-BLOCKING: doesn't wait if lock is held. Returns immediately.
            //    Use when: "increment if possible, otherwise skip."
            try {
                count++;
                return true;
            } finally {
                lock.unlock();
            }
        }
        return false;   // Lock was held by another thread → didn't increment.
    }

    public int get() {
        lock.lock();
        try { return count; }
        finally { lock.unlock(); }
    }
}
```

---

## CONCEPT 2: VOLATILE

```
WHAT: Ensures VISIBILITY of variable changes across threads.
      Without volatile: each CPU core caches variables in its L1/L2 cache.
      Thread A writes to 'flag'. Thread B may read STALE cached value.
      volatile: forces every read/write to go to MAIN MEMORY (no caching).

WHEN TO USE volatile:
  - Simple flag that one thread writes and others read.
  - Singleton instance (in DCLP: volatile instance field).
  
WHEN NOT SUFFICIENT:
  - count++ (read-modify-write → not atomic even with volatile).
  - volatile: visibility only. Not atomicity.
  - For compound operations: use synchronized or AtomicInteger.
```

### Java — volatile

```java
// ── volatile: Shutdown flag ────────────────────────────────────────────────────

class BackgroundWorker implements Runnable {
    //  ↑ Runnable: functional interface with one method: run().
    //    Passed to Thread. Thread calls run() when started.

    private volatile boolean running = true;
    //  ↑ volatile: every thread sees the CURRENT value.
    //    Without volatile: main thread sets running=false.
    //    Worker thread reads its cached copy: still true. Runs forever!
    //    With volatile: worker reads from main memory → sees false → stops.

    @Override
    public void run() {
        //  ↑ run(): called by Thread.start(). Runs in a new thread.
        System.out.println("Worker started on: " + Thread.currentThread().getName());
        //  ↑ Thread.currentThread(): reference to the thread executing this code.
        //  ↑ .getName(): "Thread-0", "Thread-1", etc.

        while (running) {
            //  ↑ Runs as long as running is true. volatile ensures fresh read each iteration.
            try {
                Thread.sleep(100);
                //  ↑ Sleep 100ms between iterations. Simulates work.
                System.out.println("Worker: processing...");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                //  ↑ Restore interrupted status. Best practice.
                break;
            }
        }
        System.out.println("Worker: stopped.");
    }

    public void stop() {
        running = false;
        //  ↑ Called from MAIN thread. volatile guarantees worker thread sees this immediately.
        //    Without volatile: uncertain when (or if) worker sees this change.
    }
}

// USAGE:
// BackgroundWorker worker = new BackgroundWorker();
// Thread t = new Thread(worker);
// t.start();                    // Calls worker.run() in new thread
// Thread.sleep(500);            // Main thread: wait 500ms
// worker.stop();                // Set running = false (visible to worker immediately)
// t.join();                     // Main thread: wait for worker thread to finish
//  ↑ .join(): blocks calling thread until 'this' thread completes.
//    Without join: main might exit before worker finishes.
```

---

## CONCEPT 3: READ-WRITE LOCK

```
PROBLEM: Many reads, few writes.
  Simple synchronized: only ONE thread at a time (reader blocks readers too!).
  
READ-WRITE LOCK:
  Multiple readers: CAN run concurrently (reads don't conflict with each other).
  Writer: EXCLUSIVE. No readers or other writers allowed simultaneously.
  
  Real benefit: 1000 read threads + 1 write thread → 999 readers proceed simultaneously.
  With plain synchronized: only 1 reader at a time. 999x slower!
  
  USE WHEN: reads >> writes. Example: configuration, cache, shared data store.
```

### Java — ReadWriteLock

```java
// ── ReadWriteLock: Configuration Cache ────────────────────────────────────────

import java.util.concurrent.locks.ReadWriteLock;
import java.util.concurrent.locks.ReentrantReadWriteLock;
import java.util.HashMap;
import java.util.Map;

class ConfigurationCache {
    private final Map<String, String> config = new HashMap<>();
    private final ReadWriteLock rwLock = new ReentrantReadWriteLock();
    //  ↑ ReentrantReadWriteLock: gives two lock views:
    //    rwLock.readLock():  acquire for reading. Multiple threads can hold simultaneously.
    //    rwLock.writeLock(): acquire for writing. Exclusive. No readers or other writers.
    //    Reentrant: same thread can re-acquire.

    public String get(String key) {
        rwLock.readLock().lock();
        //  ↑ Acquire READ lock. Multiple threads can hold readLock at the same time.
        //    All blocked only if a WRITE lock is currently held.
        try {
            return config.get(key);
            //  ↑ Safe concurrent read. Many threads here simultaneously = OK.
        } finally {
            rwLock.readLock().unlock();
        }
    }

    public void set(String key, String value) {
        rwLock.writeLock().lock();
        //  ↑ Acquire WRITE lock. EXCLUSIVE. Blocks all other readers AND writers.
        //    Only ONE thread can hold writeLock. Waits for all readers to finish.
        try {
            config.put(key, value);
            //  ↑ Safe write. No other threads in get() or set() simultaneously.
        } finally {
            rwLock.writeLock().unlock();
        }
    }

    public int size() {
        rwLock.readLock().lock();
        try { return config.size(); }
        finally { rwLock.readLock().unlock(); }
    }
}
```

### C++ — shared_mutex (ReadWriteLock equivalent)

```cpp
// ── C++: shared_mutex for ReadWrite lock ──────────────────────────────────────
#include <shared_mutex>
#include <unordered_map>
#include <string>
#include <optional>

class ConfigurationCache {
public:
    std::optional<std::string> get(const std::string& key) const {
        std::shared_lock lock(mtx_);
        //  ↑ shared_lock: SHARED (read) lock. Multiple threads can hold simultaneously.
        //    std::shared_lock is the read-lock. std::unique_lock is the write-lock.
        //  ↑ RAII: lock acquired in constructor. Released when 'lock' goes out of scope.
        //    Even if exception occurs: lock released. No manual unlock needed.
        auto it = config_.find(key);
        if (it == config_.end()) return std::nullopt;
        //  ↑ std::optional<string>: represents "possibly has a value".
        //    std::nullopt: "has no value" (like null in Java, but safer).
        //    Caller must CHECK if value is present before using it.
        return it->second;
    }

    void set(const std::string& key, const std::string& value) {
        std::unique_lock lock(mtx_);
        //  ↑ unique_lock: EXCLUSIVE (write) lock. Only ONE thread can hold this.
        //    Blocks all shared_lock holders AND other unique_lock holders.
        config_[key] = value;
    }

private:
    std::unordered_map<std::string, std::string> config_;
    mutable std::shared_mutex mtx_;
    //  ↑ mutable: allows locking in CONST methods (get() is const, but needs to lock).
    //    Normal member variables can't be modified in const methods.
    //    mutable: exception to this rule (for synchronization primitives).
    //  ↑ shared_mutex: C++17. Supports both shared (read) and exclusive (write) locking.
};
```

---

## CONCEPT 4: DEADLOCK

```
WHAT: Thread A holds lock X, waits for lock Y.
      Thread B holds lock Y, waits for lock X.
      Both wait forever. DEADLOCK.

CONDITIONS FOR DEADLOCK (all 4 must hold):
  1. Mutual exclusion: locks are non-shareable.
  2. Hold and wait: thread holds one lock while waiting for another.
  3. No preemption: locks cannot be forcibly taken.
  4. Circular wait: A waits for B, B waits for A.

PREVENTION: Break any one condition.
  Consistent lock ordering: always acquire locks in the same order.
  Lock timeout: tryLock(timeout) → give up if can't acquire within time.
  Lock leveling: lock with lower ID first.
```

### Java — Deadlock Prevention

```java
// ── DEADLOCK EXAMPLE (DON'T DO THIS) ──────────────────────────────────────────

class BadTransfer {
    static void transfer(Account from, Account to, double amount) {
        synchronized (from) {
            //  ↑ Thread A: lock 'from' (Account A). Thread B: lock 'from' (Account B).
            synchronized (to) {
                //  ↑ Thread A: try to lock 'to' (Account B) — but Thread B holds it!
                //    Thread B: try to lock 'to' (Account A) — but Thread A holds it!
                //    DEADLOCK: both wait forever.
                from.balance -= amount;
                to.balance   += amount;
            }
        }
    }
}

// ── DEADLOCK FIX 1: Consistent lock ordering by ID ────────────────────────────

class SafeTransfer {
    static void transfer(Account from, Account to, double amount) {
        // Always lock the account with smaller ID first:
        Account first  = from.id < to.id ? from : to;
        Account second = from.id < to.id ? to : from;
        //  ↑ Consistent ordering: regardless of which direction transfer() is called,
        //    the account with smaller ID is ALWAYS locked first.
        //    No circular wait possible → no deadlock.

        synchronized (first) {
            synchronized (second) {
                from.balance -= amount;
                to.balance   += amount;
            }
        }
    }
}

// ── DEADLOCK FIX 2: tryLock with timeout ──────────────────────────────────────

import java.util.concurrent.TimeUnit;

class TryLockTransfer {
    static boolean transfer(Account from, Account to, double amount)
            throws InterruptedException {

        while (true) {
            if (from.lock.tryLock(100, TimeUnit.MILLISECONDS)) {
                //  ↑ tryLock(time, unit): try to acquire. Wait at most 100ms.
                //    Returns true if acquired, false if timeout.
                //    TimeUnit.MILLISECONDS: unit of the timeout.
                try {
                    if (to.lock.tryLock(100, TimeUnit.MILLISECONDS)) {
                        try {
                            from.balance -= amount;
                            to.balance   += amount;
                            return true;   // Success!
                        } finally {
                            to.lock.unlock();
                        }
                    }
                } finally {
                    from.lock.unlock();
                }
            }
            // If either tryLock timed out: release what we have, try again.
            Thread.sleep(10);   // Small delay before retry (backoff)
        }
    }
}
```

---

## CONCEPT 5: THREAD POOL

```
PROBLEM: Creating a thread for every task is expensive.
  Thread creation: 2-5ms (stack allocation, OS scheduling overhead).
  For 1000 short tasks: 1000 thread creates = seconds wasted.
  
THREAD POOL: Pre-create N threads. Reuse them for multiple tasks.
  Task arrives → assign to idle thread → execute → thread becomes idle again.
  No thread creation overhead. Bounded number of threads (prevents OOM).
  
JAVA: ExecutorService, ThreadPoolExecutor.
C++:  Build manually or use std::async / BS::thread_pool (third-party).

REAL USE:
  Web server: 100-worker thread pool. Each HTTP request → one worker.
  Database: 10-connection thread pool. Each query → one connection.
  Kafka consumer: N worker threads consuming partitions.
```

### Java — ThreadPool + CompletableFuture

```java
// ── Thread Pool: Async Task Executor ──────────────────────────────────────────

import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class VideoTranscodeService {
    private final ExecutorService pool;
    //  ↑ ExecutorService: manages a pool of threads. Accepts Callable/Runnable tasks.
    //    Decouples TASK SUBMISSION from TASK EXECUTION.
    //    You submit tasks; the pool decides when and which thread executes them.

    public VideoTranscodeService(int workerCount) {
        this.pool = Executors.newFixedThreadPool(workerCount);
        //  ↑ newFixedThreadPool(N): create pool with exactly N threads.
        //    N threads: always alive, waiting for tasks.
        //    Tasks queue up if all N threads are busy.
        //    Bounded: won't create more than N threads → won't OOM.

        // Other pool types:
        // Executors.newCachedThreadPool()   → creates threads as needed, reuses idle ones.
        //                                     Unbounded. Good for many short-lived tasks.
        // Executors.newSingleThreadExecutor() → exactly 1 thread. Tasks run sequentially.
        //                                       Good for ordered background work.
        // Executors.newScheduledThreadPool(N) → supports delayed and periodic tasks.
        //                                       Like Timer but better.
    }

    public Future<String> submitTranscodeJob(String videoId, String resolution) {
        //  ↑ Future<String>: a handle to a result that will be available in the future.
        //    Like a "receipt" for the submitted task.
        //    Future.get(): BLOCKS until result is ready.
        //    Future.isDone(): non-blocking check.
        //    Future.cancel(): attempt to cancel.

        return pool.submit(() -> {
            //  ↑ pool.submit(Callable): add task to queue. Returns Future.
            //  ↑ Lambda = Callable<String>: returns String (the transcode result).
            //    Callable vs Runnable: Callable returns a value. Runnable returns void.

            String threadName = Thread.currentThread().getName();
            System.out.printf("[%s] Transcoding %s to %s...%n", threadName, videoId, resolution);

            Thread.sleep(1000);   // Simulate 1-second transcode
            return videoId + "_" + resolution + ".mp4";
            //  ↑ Returned value becomes available via future.get().
        });
    }

    public CompletableFuture<String> transcodeAsync(String videoId, String resolution) {
        //  ↑ CompletableFuture: Java 8+. More powerful than Future.
        //    Supports: chaining (thenApply, thenCompose), combining futures, exception handling.
        //    vs Future: Future.get() always BLOCKS. CompletableFuture can be non-blocking.

        return CompletableFuture.supplyAsync(() -> {
            //  ↑ supplyAsync(supplier, executor): run in thread pool, return result.
            try { Thread.sleep(1000); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
            return videoId + "_" + resolution + ".mp4";
        }, pool)
        .thenApply(result -> {
            //  ↑ thenApply: transform result when ready (like map in streams).
            //    Runs in same thread as supplier (or pool thread).
            System.out.println("Transcode complete: " + result);
            return result.toUpperCase();
            //  ↑ .toUpperCase(): convert to uppercase. Returns new String.
        })
        .exceptionally(ex -> {
            //  ↑ exceptionally: handle exception. Like catch block for CompletableFuture.
            System.out.println("Transcode failed: " + ex.getMessage());
            return "FAILED_" + videoId;
        });
    }

    public void shutdown() {
        pool.shutdown();
        //  ↑ shutdown(): stop accepting new tasks. Complete in-progress tasks. Then terminate.
        //    Graceful shutdown.
        //    pool.shutdownNow(): forcefully interrupt all threads. Not graceful.
        try {
            if (!pool.awaitTermination(30, TimeUnit.SECONDS)) {
                //  ↑ awaitTermination(timeout, unit): wait for pool to fully terminate.
                //    Returns true if terminated within timeout, false if timeout exceeded.
                pool.shutdownNow();   // Force if not done within 30 seconds.
            }
        } catch (InterruptedException e) {
            pool.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}

// USAGE:
// VideoTranscodeService svc = new VideoTranscodeService(4);  // 4 worker threads
//
// // Submit 10 jobs. Only 4 run at a time. Rest wait in queue.
// List<Future<String>> futures = new ArrayList<>();
// for (int i = 0; i < 10; i++) {
//     futures.add(svc.submitTranscodeJob("video_" + i, "1080p"));
// }
//
// // Collect results:
// for (Future<String> f : futures) {
//     System.out.println("Result: " + f.get());   // Blocks until this job's result is ready.
// }
// svc.shutdown();
```

### C++ — Thread Safety

```cpp
// ── C++ Atomic + mutex + lock_guard ───────────────────────────────────────────
#pragma once
#include <atomic>
#include <mutex>
#include <thread>
#include <vector>
#include <functional>
#include <queue>
#include <condition_variable>

// ATOMIC COUNTER (no lock needed):
class AtomicCounter {
    std::atomic<int> count_{0};
    //  ↑ std::atomic<int>: all operations are lock-free and thread-safe.
    //    On x86-64: uses LOCK XADD instruction (single CPU instruction = atomic).

public:
    void increment() {
        count_.fetch_add(1, std::memory_order_relaxed);
        //  ↑ fetch_add: atomically adds 1. Returns old value (ignored here).
        //  ↑ memory_order_relaxed: no ordering constraints.
        //    For counters: relaxed is fine (we just need atomicity, not ordering).
        //    memory_order_seq_cst (default): strongest. Full memory barrier. Slower.
        //    memory_order_acquire/release: for producer-consumer patterns.
    }

    int get() const {
        return count_.load(std::memory_order_acquire);
        //  ↑ acquire: see all writes that were released before this load.
    }
};

// THREAD POOL (simplified):
class ThreadPool {
public:
    explicit ThreadPool(size_t threadCount) {
        for (size_t i = 0; i < threadCount; ++i) {
            workers_.emplace_back([this] {
                //  ↑ emplace_back: construct thread in-place. Lambda is the thread function.
                //  ↑ [this]: capture 'this' pointer. Lambda can access member variables.
                while (true) {
                    std::function<void()> task;
                    {
                        std::unique_lock<std::mutex> lock(queueMutex_);
                        //  ↑ Acquire mutex to check/pop from queue.

                        condition_.wait(lock, [this] {
                            return !running_ || !tasks_.empty();
                            //  ↑ wait(lock, predicate): atomically: release lock, sleep.
                            //    Wake up when: predicate() returns true OR spurious wakeup.
                            //    Re-acquires lock before returning.
                            //    Predicate re-checked after each wakeup (guards spurious wakeups).
                        });
                        if (!running_ && tasks_.empty()) return;
                        //  ↑ Pool is stopping AND no tasks left → thread exits.

                        task = std::move(tasks_.front());
                        //  ↑ Move task out of queue (no copy).
                        tasks_.pop();
                        //  ↑ Remove from queue. O(1).
                    }
                    //  ↑ Lock released here (end of block). Execute task WITHOUT holding lock.
                    task();
                    //  ↑ Execute the task. Other threads can pick tasks concurrently.
                }
            });
        }
    }

    template<typename F>
    void enqueue(F&& task) {
        //  ↑ template<typename F>: accept any callable type (lambda, function, etc.)
        //  ↑ F&&: universal reference (rvalue or lvalue reference).
        {
            std::unique_lock<std::mutex> lock(queueMutex_);
            tasks_.push(std::forward<F>(task));
            //  ↑ std::forward: perfect forwarding. Preserves rvalue/lvalue category.
            //    If task is rvalue (temporary): moves it. If lvalue: copies it.
        }
        condition_.notify_one();
        //  ↑ Wake up ONE waiting thread to pick up the new task.
        //    notify_all(): wake ALL waiting threads. Overkill for one new task.
    }

    ~ThreadPool() {
        {
            std::unique_lock<std::mutex> lock(queueMutex_);
            running_ = false;
        }
        condition_.notify_all();
        //  ↑ Wake all threads. They'll see running_=false and exit.
        for (auto& t : workers_) {
            if (t.joinable()) t.join();
            //  ↑ joinable(): true if thread is running (started but not joined/detached).
            //  ↑ join(): wait for thread to finish. Blocks until thread exits.
            //    MUST join (or detach) every thread before program exits.
            //    Not joining = undefined behavior (crash or resource leak).
        }
    }

private:
    std::vector<std::thread> workers_;
    std::queue<std::function<void()>> tasks_;
    std::mutex queueMutex_;
    std::condition_variable condition_;
    //  ↑ condition_variable: threads can WAIT on it and be notified.
    //    wait(): releases mutex + sleeps. notify_one(): wakes one waiter.
    bool running_ = true;
};

// USAGE:
// ThreadPool pool(4);  // 4 worker threads
// for (int i = 0; i < 10; ++i) {
//     pool.enqueue([i] {
//         printf("Task %d on thread %lu\n", i, std::hash<std::thread::id>{}(std::this_thread::get_id()));
//         std::this_thread::sleep_for(std::chrono::milliseconds(100));
//     });
// }
// // Destructor: waits for all tasks to complete.
```

---

## Summary: Java vs C++ Concurrency

```
MUTEX / LOCK:
  Java: synchronized keyword, ReentrantLock
        synchronized(obj) { ... } → releases on exit/exception automatically
        ReentrantLock: lock(), unlock() (must be in try-finally!)
  C++:  std::mutex, std::lock_guard, std::unique_lock
        lock_guard: RAII, auto-release (like Java's synchronized).
        unique_lock: RAII + can be manually unlocked/relocked.

READ-WRITE LOCK:
  Java: ReentrantReadWriteLock → .readLock() and .writeLock()
  C++:  std::shared_mutex → shared_lock (read) and unique_lock (write)

ATOMIC OPERATIONS:
  Java: AtomicInteger, AtomicLong, AtomicReference
        .incrementAndGet(), .compareAndSet()
  C++:  std::atomic<int>, std::atomic<bool>, std::atomic<T*>
        .fetch_add(), .compare_exchange_strong()

VOLATILE:
  Java: volatile field → visibility across threads. NOT atomicity.
        Use for: single-write flags (running = false to stop a thread).
  C++:  volatile: different meaning! Tells compiler "don't optimize reads/writes."
        For thread safety in C++: use std::atomic, NOT volatile!
        (C++ volatile ≠ Java volatile)

THREAD CREATION:
  Java: new Thread(runnable).start()
        ExecutorService pool = Executors.newFixedThreadPool(N)
  C++:  std::thread t(function, args); t.join();
        No standard thread pool (C++11/14/17). Use third-party or roll your own.
        C++23: std::jthread (auto-joins on destruction. No need to call join()).

CONDITION VARIABLES (wait/notify):
  Java: object.wait() / object.notify() (inside synchronized block)
        Or: Condition.await() / Condition.signal() (with ReentrantLock)
  C++:  std::condition_variable.wait(lock, predicate)
        std::condition_variable.notify_one() / notify_all()

DEADLOCK PREVENTION:
  Java: consistent lock ordering, tryLock with timeout.
  C++:  std::scoped_lock(mutex1, mutex2): acquires BOTH in deadlock-safe order.
        (Uses std::lock() internally which is deadlock-safe.)
        Or: consistent manual ordering (same as Java approach).

COMMON MISTAKES:
  Java: Using == instead of .equals() for String comparison in synchronized code.
        Forgetting to unlock() in finally block.
        Synchronized on wrong object (not the shared state).
        
  C++:  Using volatile for thread safety (wrong! Use atomic or mutex).
        Not calling join() → undefined behavior.
        Forgetting virtual destructor in polymorphic base → memory leak under polymorphism.
        Copying unique_ptr (compile error) → use move semantics.
        Data race: accessing shared data without synchronization → undefined behavior.
```

---

## HOW CONCURRENCY APPEARS IN THE LLD CASE STUDIES

### Race Conditions & AtomicInteger

```
CS01 URL Shortener (CS01_URL_Shortener.md):
  SequenceGenerator has a global counter. Multiple threads call next_id() simultaneously.
  WITHOUT AtomicLong: two threads read counter=1000, both increment to 1001.
  Both generate short code "abc". COLLISION. URL is lost.
  
  FIX (Java): private final AtomicLong counter = new AtomicLong(0);
              public long nextId() { return counter.incrementAndGet(); }
  FIX (C++):  std::atomic<uint64_t> counter_{0};
              uint64_t nextId() { return counter_.fetch_add(1, memory_order_relaxed); }

CS06 YouTube:
  Video.like_count: thousands of concurrent like/unlike calls.
  FIX: AtomicInteger(Java) / atomic<int>(C++) for like_count.
       Or: Increment via Redis INCR (atomic at DB level, avoids Java-level race).

CS08 Twitter:
  TweetService.tweet_count per user. Concurrent posting.
  FIX: AtomicLong for tweet counters, or let DB handle (UPDATE SET count = count + 1).
```

### synchronized / mutex — Shared State Protection

```
CS01 URL Shortener:
  UrlStore._url_map (HashMap): read by many threads, written by create_url().
  Java: ConcurrentHashMap (lock-striped, better than synchronizing the whole map).
  C++: unordered_map + shared_mutex (shared_lock for reads, unique_lock for writes).

CS04 Uber:
  DriverLocationService._driver_locations: many GPS updates + ride requests reading concurrently.
  Java: ConcurrentHashMap<DriverId, Location>.
  C++: unordered_map + shared_mutex.
  
  DriverPool._available_drivers: drivers get marked busy on assignment. Concurrent writes.
  Java: synchronized block on the pool.
  C++: unique_lock<mutex> on assignment.

CS09 Payment Gateway:
  IdempotencyStore._processed: check-then-set must be ATOMIC.
  Without synchronization: two concurrent requests for same idempotency_key
  both pass the check → both process → DOUBLE CHARGE. 
  FIX: synchronized block wrapping the check-and-store operation.
  Or better: DB-level UNIQUE constraint on idempotency_key (atomic at storage level).
```

### volatile — Visibility Flags

```
CS06 YouTube:
  TranscodeJob._is_cancelled: main thread sets it, worker thread reads it.
  Java: private volatile boolean isCancelled = false;
  Without volatile: worker's CPU cache holds stale false. Never sees the cancel.
  C++: Use atomic<bool> (volatile in C++ doesn't provide memory visibility guarantee).

CS04 Uber:
  LocationTracker._is_tracking: background GPS thread checks this flag to know if it should stop.
  Java: volatile boolean isTracking.
  C++: std::atomic<bool> isTracking.
```

### ReadWriteLock — Read-Heavy Data

```
CS01 URL Shortener:
  URL lookup (reads) >> URL creation (writes). 1000 reads per write typical.
  Java: ReentrantReadWriteLock. readLock() for lookup. writeLock() for create/delete.
  C++: shared_mutex. shared_lock for lookup. unique_lock for create.
  Result: 1000 read threads proceed simultaneously. Only writes are exclusive.

CS07 Google Search:
  InvertedIndex: very read-heavy. Crawl updates (writes) happen periodically.
  Thousands of search queries hit the index per second (reads).
  Java: StampedLock (optimistic reads, even better than ReadWriteLock).
  C++: shared_mutex. reads via shared_lock.

CS05 Netflix:
  ContentCatalog: reads (users browsing) >> writes (new content added).
  shared_mutex pattern. Multiple users browse simultaneously.
```

### ThreadPool — Task Execution

```
CS06 YouTube:
  VideoTranscodeService: Executors.newFixedThreadPool(8) (8 transcode workers).
  Each uploaded video → submitted as task. Pool prevents unbounded thread creation.
  Without pool: 10,000 uploads = 10,000 threads → OutOfMemoryError.

CS11 AI Systems:
  LLMBatchService: ThreadPool for parallel prompt processing.
  Submit 100 prompts → pool of 10 workers processes them concurrently.
  CompletableFuture.supplyAsync() per prompt, combine with allOf().

CS04 Uber:
  DriverMatchingService: ThreadPool to run matching algorithm for many simultaneous requests.
  Each ride request → submitted to pool → matching runs in parallel.
  ScheduledExecutorService for periodic location broadcast to nearby drivers.

CS09 Payment Gateway:
  WebhookNotifier: ThreadPool for sending HTTP callbacks.
  Payment completes → webhook submitted to pool → sent asynchronously.
  Main payment flow doesn't wait for webhook delivery.
```

### Deadlock Prevention in Case Studies

```
CS09 Payment Gateway:
  When processing a payment involving: user account lock + merchant account lock.
  DEADLOCK SCENARIO: 
    Thread A: lock user_A → wait for merchant_B.
    Thread B: lock merchant_B → wait for user_A.
  
  FIX: Consistent ordering by account ID.
    Always lock lower ID first:
    lock(min(user_id, merchant_id))
    lock(max(user_id, merchant_id))
  
  OR: Use database transactions with row-level locking (DB handles deadlock detection).

CS04 Uber:
  Two drivers accepting the same ride simultaneously.
  FIX: DB-level optimistic locking. SELECT + UPDATE SET driver_id = ? WHERE driver_id IS NULL.
  Only one UPDATE succeeds. Other fails → retry with next available ride.
  No Java-level locks needed. DB handles it.
```

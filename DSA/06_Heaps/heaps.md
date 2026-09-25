# Heaps & Priority Queues — Google Level

## Mental Model
```
Heap = complete binary tree where parent is always ≤ children (min-heap)
Top of heap = always minimum (min-heap) or maximum (max-heap)
Push/pop: O(log n)   Peek: O(1)   Build heap: O(n)

Use heap when: "find K largest/smallest", "always need current min/max",
               "merge K sorted lists", "streaming median"
```

---

## Python `heapq` — Always a min-heap

```python
import heapq

# Min-heap
heap = []
heapq.heappush(heap, 5)
heapq.heappush(heap, 2)
heapq.heappush(heap, 8)
print(heapq.heappop(heap))   # 2 — smallest

# Max-heap: negate values
heap = []
heapq.heappush(heap, -5)
heapq.heappush(heap, -2)
print(-heapq.heappop(heap))  # 5 — largest

# Build from list: O(n)
data = [3, 1, 4, 1, 5]
heapq.heapify(data)

# Peek (no pop)
print(heap[0])

# Heap with tuples (sorted by first element)
heapq.heappush(heap, (priority, item))
```

---

## Pattern 1: K Largest / K Smallest

```python
# K largest elements — use min-heap of size K
def k_largest(nums, k):
    heap = []
    for num in nums:
        heapq.heappush(heap, num)
        if len(heap) > k:
            heapq.heappop(heap)  # remove smallest
    return list(heap)  # K largest remain

# K smallest elements — use max-heap of size K
def k_smallest(nums, k):
    heap = []
    for num in nums:
        heapq.heappush(heap, -num)
        if len(heap) > k:
            heapq.heappop(heap)
    return [-x for x in heap]

# K-th largest — O(n log k)
def kth_largest(nums, k):
    heap = []
    for num in nums:
        heapq.heappush(heap, num)
        if len(heap) > k:
            heapq.heappop(heap)
    return heap[0]
```

---

## Pattern 2: Merge K Sorted Lists

```python
from heapq import heappush, heappop

def merge_k_sorted(lists):
    """lists: list of sorted arrays"""
    result = []
    heap = []  # (value, list_index, element_index)

    # Initialize with first element of each list
    for i, lst in enumerate(lists):
        if lst:
            heappush(heap, (lst[0], i, 0))

    while heap:
        val, i, j = heappop(heap)
        result.append(val)
        if j + 1 < len(lists[i]):
            heappush(heap, (lists[i][j+1], i, j+1))

    return result
```

---

## Pattern 3: Streaming Median (Two Heaps)

```python
class MedianFinder:
    """
    Lower half: max-heap (negate values)
    Upper half: min-heap
    Invariant: len(lower) == len(upper) or len(lower) == len(upper) + 1
    """
    def __init__(self):
        self.lower = []  # max-heap (store negated)
        self.upper = []  # min-heap

    def addNum(self, num):
        # Push to lower, balance to upper
        heapq.heappush(self.lower, -num)

        # Ensure lower's max <= upper's min
        if self.upper and -self.lower[0] > self.upper[0]:
            heapq.heappush(self.upper, -heapq.heappop(self.lower))

        # Balance sizes
        if len(self.lower) > len(self.upper) + 1:
            heapq.heappush(self.upper, -heapq.heappop(self.lower))
        elif len(self.upper) > len(self.lower):
            heapq.heappush(self.lower, -heapq.heappop(self.upper))

    def findMedian(self):
        if len(self.lower) > len(self.upper):
            return -self.lower[0]
        return (-self.lower[0] + self.upper[0]) / 2
```

---

## Pattern 4: Task Scheduler / Frequency-based

```python
def least_interval(tasks, n):
    """Min intervals to complete all tasks with cooldown n."""
    freq = Counter(tasks)
    heap = [-f for f in freq.values()]
    heapq.heapify(heap)

    time = 0
    cooldown = []  # (available_time, freq)

    while heap or cooldown:
        time += 1
        if heap:
            freq = heapq.heappop(heap) + 1  # decrement (stored negative)
            if freq < 0:
                cooldown.append((time + n, freq))

        if cooldown and cooldown[0][0] == time:
            _, f = cooldown.pop(0)
            heapq.heappush(heap, f)

    return time
```

---

## Pattern 5: Dijkstra (heap-based shortest path)

See Graphs.md — Dijkstra uses min-heap to always process closest node.

---

## Pattern 6: Meeting Rooms / Interval Scheduling

```python
def min_meeting_rooms(intervals):
    """Minimum rooms needed for all meetings."""
    intervals.sort(key=lambda x: x[0])  # sort by start

    heap = []  # end times of active meetings
    for start, end in intervals:
        if heap and heap[0] <= start:
            heapq.heapreplace(heap, end)  # reuse this room
        else:
            heapq.heappush(heap, end)     # need new room

    return len(heap)
```

---

## Google Problem Table

| Problem | Pattern | Difficulty |
|---------|---------|------------|
| Kth Largest Element | Min-heap size K | Medium |
| K Closest Points to Origin | Min-heap | Medium |
| Top K Frequent Elements | Max-heap / bucket sort | Medium |
| Merge K Sorted Lists | Multi-way heap merge | Hard |
| Find Median from Stream | Two heaps | Hard |
| Task Scheduler | Max-heap + cooldown | Medium |
| Meeting Rooms II | Min-heap of end times | Medium |
| Ugly Number II | 3 heaps | Medium |
| Sliding Window Maximum | Monotonic deque | Hard |
| Reorganize String | Max-heap | Medium |
| IPO (maximize capital) | Two heaps | Hard |

---

## Key Rules
- "K largest" → min-heap of size K (pop when > K)
- "K smallest" → max-heap of size K (pop when > K)
- "Always need current min/max" → heap
- "Streaming median" → two heaps (lower max-heap + upper min-heap)
- "Merge K sorted" → heap with (value, list_idx, elem_idx)

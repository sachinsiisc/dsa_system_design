# Arrays & Strings — Theory
## Memory Model · Operations · Tricks · Complexity Proofs · MAANG Examples

---

## 1. Memory Model — How Arrays Actually Work

```
An array is a CONTIGUOUS block of memory.

int arr[5] = {10, 20, 30, 40, 50};

Memory addresses (assuming int = 4 bytes, base addr = 1000):
  arr[0] → address 1000  → value 10
  arr[1] → address 1004  → value 20
  arr[2] → address 1008  → value 30
  arr[3] → address 1012  → value 40
  arr[4] → address 1016  → value 50

Formula: address(arr[i]) = base_address + i × element_size

This is why arr[i] is O(1) — one multiplication + one addition. No traversal needed.
```

**Python list** — stores pointers (8 bytes each), not values directly:
```
lst = [10, 20, 30]

Memory:
  lst → [ptr_to_10, ptr_to_20, ptr_to_30]  ← array of 8-byte pointers
            ↓           ↓           ↓
           [10]        [20]        [30]     ← actual int objects on heap

This is why Python lists are O(1) access but use more memory than C arrays.
```

---

## 2. Dynamic Array (Python list / Java ArrayList) — Amortised O(1) Append

**How resize works:**
```
Initial capacity: 4
Push elements: [1] → [1,2] → [1,2,3] → [1,2,3,4] → FULL → RESIZE

Resize strategy: double capacity (capacity 4 → 8)
Steps:
  1. Allocate new array of size 8
  2. Copy 4 elements from old to new: O(4)
  3. Free old array

After resize: capacity = 8, 5th element appended → no copy

Cost of copying:  1 + 2 + 4 + 8 + 16 + ... + n = 2n (geometric series)
Total cost for n appends = n (appends) + 2n (copies) = 3n = O(n)
Amortised cost per append = O(n)/n = O(1)

This is called "amortised analysis" — average cost over all operations.
```

---

## 3. Key Array Techniques

### 3.1 Prefix Sum
Pre-compute cumulative sums to answer range queries in O(1).

```
Array: [3, 1, 4, 1, 5, 9, 2, 6]
Index:  0  1  2  3  4  5  6  7

Prefix: [0, 3, 4, 8, 9, 14, 23, 25, 31]
         ^  prefix[i] = sum(arr[0..i-1])

Range sum query [l, r]:  prefix[r+1] - prefix[l]

Example: sum(arr[2..5]) = prefix[6] - prefix[2] = 23 - 4 = 19
Verify:  4+1+5+9 = 19 ✓

Build: O(n). Query: O(1).
```

**Code:**
```python
def build_prefix(arr):
    prefix = [0] * (len(arr) + 1)
    for i, v in enumerate(arr):
        prefix[i+1] = prefix[i] + v
    return prefix

def range_sum(prefix, l, r):   # inclusive [l, r]
    return prefix[r+1] - prefix[l]
```

**2D Prefix Sum:**
```
Matrix:
  1  2  3
  4  5  6
  7  8  9

2D prefix[i][j] = sum of rectangle (0,0) to (i-1,j-1)

prefix[i][j] = matrix[i-1][j-1]
             + prefix[i-1][j]    (row above)
             + prefix[i][j-1]    (column left)
             - prefix[i-1][j-1]  (subtract double-counted top-left)

Query rectangle (r1,c1) to (r2,c2):
  prefix[r2+1][c2+1] - prefix[r1][c2+1] - prefix[r2+1][c1] + prefix[r1][c1]
```

---

### 3.2 Kadane's Algorithm — Maximum Subarray (Fundamental DP)

**Problem:** Find contiguous subarray with maximum sum.

**Brute force:** O(n²) — try all (i, j) pairs.

**Kadane's — O(n):**
```
Intuition: At each position, decide: extend previous subarray, or start fresh?
If the running sum goes negative, starting fresh is always better.

Array: [-2, 1, -3, 4, -1, 2, 1, -5, 4]

i=0: current = max(-2, -2) = -2,  best = -2
i=1: current = max(1, -2+1=-1) = 1,  best = 1
i=2: current = max(-3, 1-3=-2) = -2,  best = 1
i=3: current = max(4, -2+4=2) = 4,  best = 4
i=4: current = max(-1, 4-1=3) = 3,  best = 4
i=5: current = max(2, 3+2=5) = 5,  best = 5
i=6: current = max(1, 5+1=6) = 6,  best = 6
i=7: current = max(-5, 6-5=1) = 1,  best = 6
i=8: current = max(4, 1+4=5) = 5,  best = 6

Answer: 6 (subarray [4,-1,2,1])
```

**Code:**
```python
def max_subarray(nums):
    best = current = nums[0]
    for n in nums[1:]:
        current = max(n, current + n)
        best = max(best, current)
    return best
```

**Follow-up — return actual subarray:**
```python
def max_subarray_with_indices(nums):
    best = current = nums[0]
    start = end = temp_start = 0
    for i in range(1, len(nums)):
        if nums[i] > current + nums[i]:
            current = nums[i]
            temp_start = i
        else:
            current += nums[i]
        if current > best:
            best = current
            start = temp_start
            end = i
    return best, nums[start:end+1]
```

---

### 3.3 Dutch National Flag (3-Way Partition)

**Problem:** Sort array of 0s, 1s, 2s in-place in O(n) with O(1) space.

```
Invariant at any moment:
  [0...lo-1] = all 0s
  [lo...mid-1] = all 1s
  [mid...hi] = unknown
  [hi+1...n-1] = all 2s

Start: lo=0, mid=0, hi=n-1

Array: [2, 0, 2, 1, 1, 0]

Step 1: arr[mid]=2 → swap(mid, hi), hi-- → [0, 0, 2, 1, 1, 2], hi=4
Step 2: arr[mid]=0 → swap(lo, mid), lo++, mid++ → [0, 0, 2, 1, 1, 2], lo=1,mid=1
Step 3: arr[mid]=0 → swap(lo, mid), lo++, mid++ → [0, 0, 2, 1, 1, 2], lo=2,mid=2
Step 4: arr[mid]=2 → swap(mid, hi), hi-- → [0, 0, 1, 1, 2, 2], hi=3
Step 5: arr[mid]=1 → mid++ → mid=3
Step 6: arr[mid]=1 → mid++ → mid=4 > hi=3 → DONE

Result: [0, 0, 1, 1, 2, 2] ✓
```

---

### 3.4 String Techniques

**Sliding window for substring problems:**
```
Longest substring without repeating characters:
s = "abcabcbb"

[a]       → seen={a:0},  len=1
[a,b]     → seen={a:0,b:1}, len=2
[a,b,c]   → seen={a:0,b:1,c:2}, len=3
[a,b,c,a] → a seen at 0! → move left to 1 → [b,c,a], seen={b:1,c:2,a:3}, len=3
[b,c,a,b] → b seen at 1! → move left to 2 → [c,a,b], seen={c:2,a:3,b:4}, len=3
[c,a,b,c] → c seen at 2! → move left to 3 → [a,b,c], seen={a:3,b:4,c:5}, len=3
[a,b,c,b] → b seen at 4! → move left to 5 → [c,b], seen={c:5,b:6}, len=2
[b,b]     → b seen at 6! → move left to 7 → [b], len=1

Answer: 3
```

**Z-Algorithm — O(n) pattern search:**
```
Z[i] = length of longest string starting at s[i] that matches a prefix of s.

s = "aabxaab"
    0123456

Z[0] = undefined (or n by convention)
Z[1] = 1 (s[1]='a' matches s[0]='a', but s[2]='b' ≠ s[1]='a')
Z[2] = 0 (s[2]='b' ≠ s[0]='a')
Z[3] = 0 (s[3]='x' ≠ s[0]='a')
Z[4] = 3 (s[4..6]="aab" matches s[0..2]="aab")
Z[5] = 1 (s[5]='a' matches s[0], s[6]='b' ≠ s[1])
Z[6] = 0

Pattern matching: P + "#" + T. If Z[i] == len(P) → match found.
```

---

## 4. Complexity Reference for Arrays

| Operation | Array | Dynamic Array | Notes |
|-----------|-------|---------------|-------|
| Access arr[i] | O(1) | O(1) | Direct address calculation |
| Search (unsorted) | O(n) | O(n) | Linear scan |
| Search (sorted) | O(log n) | O(log n) | Binary search |
| Insert at end | O(1) | O(1) amortised | Dynamic: may resize |
| Insert at index i | O(n) | O(n) | Shift elements right |
| Delete at end | O(1) | O(1) | |
| Delete at index i | O(n) | O(n) | Shift elements left |
| Build prefix sum | O(n) | O(n) | One pass |
| Range sum query | O(1) | O(1) | With prefix sum |

---

## 5. Common Traps and Edge Cases

```
Edge case                        | Example             | How to handle
─────────────────────────────────┼─────────────────────┼──────────────────────
Empty array                      | []                  | if not arr: return ...
Single element                   | [5]                 | check n==1 separately
All same elements                | [3,3,3,3]           | test duplicate logic
Sorted ascending/descending      | [1,2,3] / [3,2,1]   | test both
Array with negatives             | [-5, 3, -1, 4]      | Kadane's handles this
Integer overflow (not Python)    | sum of 10^18 values  | use long in Java/C++
Off-by-one in indices            | range(n) vs range(n+1) | test manually
Modifying array while iterating  | rm during for loop  | iterate backward or copy
```

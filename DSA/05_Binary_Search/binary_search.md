# Binary Search — Google Level

## Mental Model
```
Binary search works on ANY monotonic function — not just sorted arrays.
Ask: "Can I binary search on the ANSWER?" (search space reduction)
Template: shrink search space [lo, hi] until lo == hi
```

---

## Universal Template (no off-by-one bugs)

```python
def binary_search(arr, target):
    lo, hi = 0, len(arr) - 1

    while lo <= hi:
        mid = lo + (hi - lo) // 2   # avoid overflow

        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1

    return -1   # not found
```

## Left-most position (first occurrence / lower_bound)

```python
def left_bound(arr, target):
    lo, hi = 0, len(arr)  # hi = len (not len-1)

    while lo < hi:
        mid = lo + (hi - lo) // 2
        if arr[mid] < target:
            lo = mid + 1
        else:
            hi = mid   # keep moving left

    return lo   # lo = first index where arr[lo] >= target
```

## Right-most position (last occurrence / upper_bound)

```python
def right_bound(arr, target):
    lo, hi = 0, len(arr)

    while lo < hi:
        mid = lo + (hi - lo) // 2
        if arr[mid] <= target:
            lo = mid + 1
        else:
            hi = mid

    return lo - 1   # last index where arr[i] <= target
```

---

## Binary Search on Answer (most important Google pattern)

**Template:**
```python
def is_feasible(value, *args):
    """Return True if value satisfies condition."""
    pass

def solve():
    lo, hi = MIN_ANSWER, MAX_ANSWER

    while lo < hi:
        mid = lo + (hi - lo) // 2
        if is_feasible(mid):
            hi = mid         # try smaller (minimize)
        else:
            lo = mid + 1

    return lo
```

---

## Classic Problems

### 1. Search in Rotated Sorted Array
```python
def search_rotated(nums, target):
    lo, hi = 0, len(nums) - 1

    while lo <= hi:
        mid = lo + (hi - lo) // 2
        if nums[mid] == target:
            return mid

        # Left half is sorted
        if nums[lo] <= nums[mid]:
            if nums[lo] <= target < nums[mid]:
                hi = mid - 1
            else:
                lo = mid + 1
        # Right half is sorted
        else:
            if nums[mid] < target <= nums[hi]:
                lo = mid + 1
            else:
                hi = mid - 1

    return -1
```

### 2. Find Minimum in Rotated Sorted Array
```python
def find_min(nums):
    lo, hi = 0, len(nums) - 1

    while lo < hi:
        mid = lo + (hi - lo) // 2
        if nums[mid] > nums[hi]:
            lo = mid + 1    # min is in right half
        else:
            hi = mid        # mid could be the min

    return nums[lo]
```

### 3. Koko Eating Bananas (Binary search on answer)
```python
def min_eating_speed(piles, h):
    """Minimum speed k so Koko finishes all piles in h hours."""
    import math

    def can_finish(k):
        return sum(math.ceil(p / k) for p in piles) <= h

    lo, hi = 1, max(piles)
    while lo < hi:
        mid = lo + (hi - lo) // 2
        if can_finish(mid):
            hi = mid
        else:
            lo = mid + 1

    return lo
```

### 4. Capacity to Ship Packages (Binary search on answer)
```python
def ship_within_days(weights, days):
    """Min capacity to ship all weights within days."""
    def can_ship(capacity):
        d, cur = 1, 0
        for w in weights:
            if cur + w > capacity:
                d += 1
                cur = 0
            cur += w
        return d <= days

    lo, hi = max(weights), sum(weights)
    while lo < hi:
        mid = lo + (hi - lo) // 2
        if can_ship(mid):
            hi = mid
        else:
            lo = mid + 1

    return lo
```

### 5. Median of Two Sorted Arrays (Hard — O(log(min(m,n))))
```python
def find_median_sorted_arrays(nums1, nums2):
    # Binary search on the smaller array
    if len(nums1) > len(nums2):
        nums1, nums2 = nums2, nums1

    m, n = len(nums1), len(nums2)
    lo, hi = 0, m

    while lo <= hi:
        cut1 = (lo + hi) // 2           # cut in nums1
        cut2 = (m + n + 1) // 2 - cut1  # cut in nums2

        l1 = float('-inf') if cut1 == 0 else nums1[cut1 - 1]
        l2 = float('-inf') if cut2 == 0 else nums2[cut2 - 1]
        r1 = float('inf') if cut1 == m else nums1[cut1]
        r2 = float('inf') if cut2 == n else nums2[cut2]

        if l1 <= r2 and l2 <= r1:
            if (m + n) % 2 == 0:
                return (max(l1, l2) + min(r1, r2)) / 2
            else:
                return max(l1, l2)
        elif l1 > r2:
            hi = cut1 - 1
        else:
            lo = cut1 + 1
```

### 6. Find Peak Element
```python
def find_peak(nums):
    lo, hi = 0, len(nums) - 1
    while lo < hi:
        mid = lo + (hi - lo) // 2
        if nums[mid] > nums[mid + 1]:
            hi = mid          # peak is on left (including mid)
        else:
            lo = mid + 1      # peak is on right
    return lo
```

---

## Google-Level Problem Table

| Problem | Key Insight | Difficulty |
|---------|------------|------------|
| Binary Search | Baseline | Easy |
| Search 2D Matrix | Treat as 1D array | Medium |
| Search Rotated Array | One half always sorted | Medium |
| Find Min in Rotated | Compare mid with right | Medium |
| Peak Element | Binary search on slope | Medium |
| Koko Eating Bananas | BS on speed | Medium |
| Capacity to Ship | BS on capacity | Medium |
| Split Array Largest Sum | BS on answer | Hard |
| Median of Two Sorted Arrays | BS on smaller array | Hard |
| K-th Smallest in Sorted Matrix | BS on value range | Hard |
| Minimise Max Distance | BS on distance | Hard |

---

## Key Patterns

1. **Sorted array + target** → standard BS
2. **First/last occurrence** → left_bound / right_bound
3. **"Minimum/maximum that satisfies X"** → BS on answer with feasibility check
4. **Rotated array** → determine which half is sorted, search accordingly
5. **Matrix** → row*cols + col indexing to treat as 1D

"""
Arrays & Strings — SOLUTIONS
Each solution includes: approach, complexity proof, edge cases, follow-ups.
"""
from collections import deque


# ══════════════════════════════════════════════════════════════════════════════
# P1: TWO SUM
# ══════════════════════════════════════════════════════════════════════════════
def two_sum(nums, target):
    """
    Approach: HashMap {value: index}. For each num, check if (target - num) exists.

    Walk-through for [2, 7, 11, 15], target=9:
      i=0: num=2, complement=7 → 7 not in seen → seen={2:0}
      i=1: num=7, complement=2 → 2 IS in seen at index 0 → return [0, 1] ✓

    Why no brute force (O(n²))?
      Brute: nested loops try all pairs. HashMap: one pass, O(1) lookup.

    Time: O(n) — one pass through array
    Space: O(n) — HashMap stores up to n entries

    Edge cases:
      - Duplicate values: [3, 3], target=6 → we check complement before inserting
        i=0: 3 not in seen → seen={3:0}
        i=1: complement=3, 3 IS in seen → [0, 1] ✓
    """
    seen = {}
    for i, num in enumerate(nums):
        complement = target - num
        if complement in seen:
            return [seen[complement], i]
        seen[num] = i
    return []


# ══════════════════════════════════════════════════════════════════════════════
# P2: MAXIMUM SUBARRAY (KADANE'S)
# ══════════════════════════════════════════════════════════════════════════════
def max_subarray(nums):
    """
    Approach: Kadane's Algorithm.
    At each position: is it better to extend the current subarray or start fresh?
    If current sum + nums[i] < nums[i] → current sum is negative → start fresh.

    Recurrence: current[i] = max(nums[i], current[i-1] + nums[i])
                best = max of all current[i]

    Walk-through for [-2,1,-3,4,-1,2,1,-5,4]:
      i=0: current=max(-2,-2)=-2,   best=-2
      i=1: current=max(1,-2+1)=1,   best=1
      i=2: current=max(-3,1-3)=-2,  best=1
      i=3: current=max(4,-2+4)=4,   best=4
      i=4: current=max(-1,4-1)=3,   best=4
      i=5: current=max(2,3+2)=5,    best=5
      i=6: current=max(1,5+1)=6,    best=6  ← answer
      i=7: current=max(-5,6-5)=1,   best=6
      i=8: current=max(4,1+4)=5,    best=6
    Answer: 6

    Time: O(n)
    Space: O(1)

    Edge: all negative → return max single element.
    Follow-up: print actual subarray → track start/end pointers.
    """
    best = current = nums[0]
    for n in nums[1:]:
        current = max(n, current + n)
        best = max(best, current)
    return best


# ══════════════════════════════════════════════════════════════════════════════
# P3: CONTAINS DUPLICATE
# ══════════════════════════════════════════════════════════════════════════════
def contains_duplicate(nums):
    """
    Approach: HashSet. If element already in set → duplicate.

    Walk-through for [1,2,3,1]:
      1 → add to seen
      2 → add to seen
      3 → add to seen
      1 → 1 is IN seen → return True ✓

    Time: O(n)
    Space: O(n)

    Alternative O(n log n): sort, then check adjacent pairs. But O(n) is better.
    """
    seen = set()
    for n in nums:
        if n in seen:
            return True
        seen.add(n)
    return False


# ══════════════════════════════════════════════════════════════════════════════
# P4: BEST TIME TO BUY AND SELL STOCK
# ══════════════════════════════════════════════════════════════════════════════
def best_time_to_buy_sell(prices):
    """
    Approach: Track min_price seen so far. At each day: profit = price - min_price.

    Walk-through for [7,1,5,3,6,4]:
      day 0: price=7, min=7, profit=0,  best=0
      day 1: price=1, min=1, profit=0,  best=0
      day 2: price=5, min=1, profit=4,  best=4
      day 3: price=3, min=1, profit=2,  best=4
      day 4: price=6, min=1, profit=5,  best=5  ← answer
      day 5: price=4, min=1, profit=3,  best=5
    Answer: 5

    Time: O(n)
    Space: O(1)

    Edge: descending prices [7,6,4,3,1] → min always decreases, profit always negative → return 0.
    """
    if not prices:
        return 0
    min_price = float('inf')
    best = 0
    for price in prices:
        min_price = min(min_price, price)
        best = max(best, price - min_price)
    return best


# ══════════════════════════════════════════════════════════════════════════════
# P5: PRODUCT OF ARRAY EXCEPT SELF
# ══════════════════════════════════════════════════════════════════════════════
def product_except_self(nums):
    """
    Approach: Two passes — left products then right products.

    For [1,2,3,4]:
    Pass 1 (left products): output[i] = product of all nums[j] for j < i
      output = [1, 1, 2, 6]
               ^  ^  ^^  ^^^
               1  1  1×2  1×2×3

    Pass 2 (right products): multiply by product of all nums[j] for j > i
      right=1
      i=3: output[3]=6×1=6,   right=1×4=4
      i=2: output[2]=2×4=8,   right=4×3=12
      i=1: output[1]=1×12=12, right=12×2=24
      i=0: output[0]=1×24=24, right=24×1=24

    Final: [24, 12, 8, 6] ✓

    Time: O(n)
    Space: O(1) extra (output array doesn't count per problem constraints)

    Edge: [0, 0] → output [0, 0]. Both zeros.
    Edge: [0, 4, 5] → output [20, 0, 0]. Zero in array.
    """
    n = len(nums)
    output = [1] * n
    # Left pass
    prefix = 1
    for i in range(n):
        output[i] = prefix
        prefix *= nums[i]
    # Right pass
    suffix = 1
    for i in range(n - 1, -1, -1):
        output[i] *= suffix
        suffix *= nums[i]
    return output


# ══════════════════════════════════════════════════════════════════════════════
# P6: MAXIMUM PRODUCT SUBARRAY
# ══════════════════════════════════════════════════════════════════════════════
def max_product_subarray(nums):
    """
    Approach: Track both max AND min product at each position.
    Why min? A negative × negative = positive → the min can flip to become the new max.

    Walk-through for [-2,3,-4]:
      i=0: n=-2, max_p=-2, min_p=-2, best=-2
      i=1: n=3,
            candidates: 3×(-2)=-6, 3×(-2)=-6, 3
            max_p = max(3, -2×3, -2×3) = max(3,-6,-6) = 3
            min_p = min(3, -6, -6) = -6
            best = max(-2, 3) = 3
      i=2: n=-4,
            candidates: -4, 3×(-4)=-12, (-6)×(-4)=24
            new_max = max(-4, -12, 24) = 24
            new_min = min(-4, -12, 24) = -12
            best = max(3, 24) = 24
    Answer: 24 ✓

    IMPORTANT: Always compute new_max and new_min from OLD max_p and min_p.
    Don't update in-place or you'll use the updated value!

    Time: O(n)
    Space: O(1)

    Edge: [0,2] → 0 acts as reset. max resets to 0 or 2 → answer 2.
    """
    if not nums:
        return 0
    max_p = min_p = best = nums[0]
    for n in nums[1:]:
        candidates = (n, max_p * n, min_p * n)
        max_p = max(candidates)
        min_p = min(candidates)
        best = max(best, max_p)
    return best


# ══════════════════════════════════════════════════════════════════════════════
# P7: FIND MINIMUM IN ROTATED SORTED ARRAY
# ══════════════════════════════════════════════════════════════════════════════
def find_min_rotated_sorted(nums):
    """
    Approach: Binary search. Key observation:
      If arr[mid] > arr[hi]: the rotation point (minimum) is in RIGHT half.
      If arr[mid] < arr[hi]: minimum is at mid or in LEFT half.

    Walk-through for [3,4,5,1,2]:
      lo=0, hi=4, mid=2, nums[mid]=5, nums[hi]=2
      5 > 2 → minimum in right half → lo = mid+1 = 3
      lo=3, hi=4, mid=3, nums[mid]=1, nums[hi]=2
      1 < 2 → minimum at mid or left → hi = mid = 3
      lo=3 == hi=3 → return nums[3] = 1 ✓

    Walk-through for [4,5,6,7,0,1,2]:
      lo=0, hi=6, mid=3, nums[mid]=7, nums[hi]=2
      7 > 2 → lo = 4
      lo=4, hi=6, mid=5, nums[mid]=1, nums[hi]=2
      1 < 2 → hi = 5
      lo=4, hi=5, mid=4, nums[mid]=0, nums[hi]=1
      0 < 1 → hi = 4
      lo=4 == hi=4 → return nums[4] = 0 ✓

    Time: O(log n)
    Space: O(1)

    Edge: not rotated [1,2,3,4] → nums[mid] < nums[hi] always → hi shrinks to 0 → return nums[0].
    """
    lo, hi = 0, len(nums) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if nums[mid] > nums[hi]:
            lo = mid + 1
        else:
            hi = mid
    return nums[lo]


# ══════════════════════════════════════════════════════════════════════════════
# P8: SEARCH IN ROTATED SORTED ARRAY
# ══════════════════════════════════════════════════════════════════════════════
def search_rotated_sorted(nums, target):
    """
    Approach: Binary search — at each step, one half is ALWAYS sorted.
    Determine which half is sorted, then check if target lies in it.

    Walk-through for [4,5,6,7,0,1,2], target=0:
      lo=0, hi=6, mid=3, nums[mid]=7
      Left half [4,5,6,7]: nums[lo]=4 ≤ nums[mid]=7 → LEFT is sorted
      Is target=0 in [4,7]? No (0<4) → search RIGHT → lo=4
      lo=4, hi=6, mid=5, nums[mid]=1
      Left half [0,1]: nums[lo]=0 ≤ nums[mid]=1 → LEFT is sorted
      Is target=0 in [0,1]? Yes (0≤0≤1) → search LEFT → hi=5
      lo=4, hi=5, mid=4, nums[mid]=0 == target → return 4 ✓

    Walk-through for [4,5,6,7,0,1,2], target=3:
      (similar — target never found in sorted half) → return -1

    Time: O(log n)
    Space: O(1)

    Edge: single element [1], target=0 → lo==hi, nums[lo]≠target → return -1.
    """
    lo, hi = 0, len(nums) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
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


# ══════════════════════════════════════════════════════════════════════════════
# P9: THREE SUM
# ══════════════════════════════════════════════════════════════════════════════
def three_sum(nums):
    """
    Approach: Sort + fix first element + two pointers.

    For sorted [-4,-1,-1,0,1,2]:
      Fix i=0 (-4): two pointers [lo=1, hi=5]
        -4 + (-1) + 2 = -3 < 0 → lo++
        -4 + (-1) + 2 = -3 < 0 → lo++
        -4 + 0 + 2 = -2 < 0 → lo++
        -4 + 1 + 2 = -1 < 0 → lo++
        lo >= hi → no triplet for i=0
      Fix i=1 (-1): two pointers [lo=2, hi=5]
        -1 + (-1) + 2 = 0 → found! add [-1,-1,2]
        Skip duplicates: lo++ until nums[lo]≠-1 → lo=3
        -1 + 0 + 2 = 1 > 0 → hi--
        -1 + 0 + 1 = 0 → found! add [-1,0,1]
        Skip: lo=4, hi=4 → done
      Fix i=2 (-1): nums[i] == nums[i-1] → SKIP (avoid duplicate triplet)
      Fix i=3 (0): two pointers [lo=4, hi=5]
        0 + 1 + 2 = 3 > 0 → hi--
        lo >= hi → done
    Final: [[-1,-1,2],[-1,0,1]] ✓

    Time: O(n²) — O(n log n) sort + O(n) for each of n pivot values
    Space: O(1) extra (not counting output)

    Edge: [0,0,0] → finds [0,0,0].
    Edge: fewer than 3 elements → return [].
    """
    nums.sort()
    result = []
    for i in range(len(nums) - 2):
        if nums[i] > 0:
            break   # sorted; if first element > 0, no zero sum possible
        if i > 0 and nums[i] == nums[i-1]:
            continue    # skip duplicate pivot
        lo, hi = i + 1, len(nums) - 1
        while lo < hi:
            s = nums[i] + nums[lo] + nums[hi]
            if s == 0:
                result.append([nums[i], nums[lo], nums[hi]])
                while lo < hi and nums[lo] == nums[lo+1]: lo += 1
                while lo < hi and nums[hi] == nums[hi-1]: hi -= 1
                lo += 1; hi -= 1
            elif s < 0:
                lo += 1
            else:
                hi -= 1
    return result


# ══════════════════════════════════════════════════════════════════════════════
# P10: CONTAINER WITH MOST WATER
# ══════════════════════════════════════════════════════════════════════════════
def container_with_most_water(height):
    """
    Approach: Two pointers from both ends.
    Proof of correctness: Move the SHORTER line inward.
    Why? The current area is limited by the SHORTER line.
    Moving the TALLER line inward: width decreases, height can only decrease or stay (bounded by the shorter).
    → current area can only decrease or stay: provably suboptimal.
    Moving the SHORTER line: width decreases, but height MIGHT increase → possibly better.
    Therefore: always move the shorter line.

    Walk-through for [1,8,6,2,5,4,8,3,7]:
      l=0(h=1), r=8(h=7): area=min(1,7)*8=8. Move l (shorter). best=8
      l=1(h=8), r=8(h=7): area=min(8,7)*7=49. Move r (shorter). best=49
      l=1(h=8), r=7(h=3): area=min(8,3)*6=18. Move r. best=49
      l=1(h=8), r=6(h=8): area=min(8,8)*5=40. Move either. best=49
      l=2(h=6), r=6(h=8): area=min(6,8)*4=24. Move l. best=49
      ...
    Answer: 49 ✓

    Time: O(n) — pointers meet in middle
    Space: O(1)
    """
    lo, hi = 0, len(height) - 1
    best = 0
    while lo < hi:
        water = min(height[lo], height[hi]) * (hi - lo)
        best = max(best, water)
        if height[lo] < height[hi]:
            lo += 1
        else:
            hi -= 1
    return best


# ══════════════════════════════════════════════════════════════════════════════
# P11: TRAPPING RAIN WATER
# ══════════════════════════════════════════════════════════════════════════════
def trapping_rain_water(height):
    """
    Approach: Two pointers. O(n) time, O(1) space.

    Key insight: Water at position i = min(max_height_to_left, max_height_to_right) - height[i]
    Two-pointer logic:
      If max_left < max_right: LEFT boundary is bottleneck.
        Water at left = max_left - height[left] (right side is taller, won't limit)
        Process left, move left++
      Else: RIGHT boundary is bottleneck.
        Water at right = max_right - height[right]
        Process right, move right--

    Walk-through for [4,2,0,3,2,5]:
      l=0(h=4), r=5(h=5): max_l=4, max_r=5
      max_l(4) < max_r(5): water at l=max(0,4-4)=0, l→1, max_l=max(4,2)=4
      max_l(4) < max_r(5): water at l=max(0,4-2)=2, l→2, max_l=max(4,0)=4
      max_l(4) < max_r(5): water at l=max(0,4-0)=4→wait, 4-0=4, l→3
      max_l=max(4,3)=4
      max_l(4) < max_r(5): water at l=max(0,4-3)=1, l→4, max_l=max(4,2)=4
      max_l(4) < max_r(5): water at l=max(0,4-2)=2, l→5 == r→done
      Total = 0+2+4+1+2 = 9 ✓

    Time: O(n)
    Space: O(1)

    Edge: empty [] → return 0. Monotone → no water trapped.
    """
    if not height:
        return 0
    lo, hi = 0, len(height) - 1
    max_left = max_right = 0
    water = 0
    while lo < hi:
        if height[lo] < height[hi]:
            if height[lo] >= max_left:
                max_left = height[lo]
            else:
                water += max_left - height[lo]
            lo += 1
        else:
            if height[hi] >= max_right:
                max_right = height[hi]
            else:
                water += max_right - height[hi]
            hi -= 1
    return water


# ══════════════════════════════════════════════════════════════════════════════
# P12: SLIDING WINDOW MAXIMUM (MONOTONIC DEQUE)
# ══════════════════════════════════════════════════════════════════════════════
def sliding_window_maximum(nums, k):
    """
    Approach: Monotonic DECREASING deque of indices.
    Invariant: deque stores indices with decreasing nums[i] values.
    Front of deque = maximum of current window.

    Why it works: If nums[j] >= nums[i] and j > i, then when i is in the window,
    j is also in the window AND is larger → i can never be the max → safely removed.

    Walk-through for [1,3,-1,-3,5,3,6,7], k=3:
      i=0: deque=[0]
      i=1: 3>1 → pop 0, push 1. deque=[1]
      i=2: -1<3 → push 2. deque=[1,2]. Window complete! Max=nums[1]=3
      i=3: -3<-1 → push 3. deque=[1,2,3]. Front(1)=1, 1≤i-k=0? No. Max=nums[1]=3
      i=4: 5>-3→pop3, 5>-1→pop2, 5>3→pop1. deque=[4]. i-k=1, front=4>1 ✓. Max=nums[4]=5
      i=5: 3<5 → push 5. deque=[4,5]. i-k=2, front=4>2 ✓. Max=nums[4]=5
      i=6: 6>3→pop5, 6>5→pop4. deque=[6]. i-k=3, front=6>3 ✓. Max=nums[6]=6
      i=7: 7>6→pop6. deque=[7]. i-k=4. Max=nums[7]=7
    Result: [3,3,5,5,6,7] ✓

    Time: O(n) — each element pushed and popped at most once
    Space: O(k) — deque size bounded by window
    """
    if not nums or k == 0:
        return []
    dq = deque()   # stores indices
    result = []
    for i, val in enumerate(nums):
        # Remove indices out of window
        while dq and dq[0] < i - k + 1:
            dq.popleft()
        # Remove indices whose values are smaller than current (they'll never be max)
        while dq and nums[dq[-1]] < val:
            dq.pop()
        dq.append(i)
        # Window is complete
        if i >= k - 1:
            result.append(nums[dq[0]])
    return result


# ══════════════════════════════════════════════════════════════════════════════
# TESTS
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("Running all tests...")

    # P1
    assert two_sum([2,7,11,15], 9) == [0,1]
    assert two_sum([3,2,4], 6) == [1,2]
    assert two_sum([3,3], 6) == [0,1]
    print("✓ two_sum")

    # P2
    assert max_subarray([-2,1,-3,4,-1,2,1,-5,4]) == 6
    assert max_subarray([1]) == 1
    assert max_subarray([-1]) == -1
    assert max_subarray([-5,-3,-1,-2]) == -1
    print("✓ max_subarray")

    # P3
    assert contains_duplicate([1,2,3,1]) == True
    assert contains_duplicate([1,2,3,4]) == False
    assert contains_duplicate([]) == False
    print("✓ contains_duplicate")

    # P4
    assert best_time_to_buy_sell([7,1,5,3,6,4]) == 5
    assert best_time_to_buy_sell([7,6,4,3,1]) == 0
    assert best_time_to_buy_sell([1,2]) == 1
    print("✓ best_time_to_buy_sell")

    # P5
    assert product_except_self([1,2,3,4]) == [24,12,8,6]
    assert product_except_self([0,0]) == [0,0]
    print("✓ product_except_self")

    # P6
    assert max_product_subarray([2,3,-2,4]) == 6
    assert max_product_subarray([-2,0,-1]) == 0
    assert max_product_subarray([-2,3,-4]) == 24
    print("✓ max_product_subarray")

    # P7
    assert find_min_rotated_sorted([3,4,5,1,2]) == 1
    assert find_min_rotated_sorted([4,5,6,7,0,1,2]) == 0
    assert find_min_rotated_sorted([11,13,15,17]) == 11
    print("✓ find_min_rotated_sorted")

    # P8
    assert search_rotated_sorted([4,5,6,7,0,1,2], 0) == 4
    assert search_rotated_sorted([4,5,6,7,0,1,2], 3) == -1
    assert search_rotated_sorted([1], 0) == -1
    assert search_rotated_sorted([3,1], 1) == 1
    print("✓ search_rotated_sorted")

    # P9
    assert three_sum([-1,0,1,2,-1,-4]) == [[-1,-1,2],[-1,0,1]]
    assert three_sum([0,1,1]) == []
    assert three_sum([0,0,0]) == [[0,0,0]]
    print("✓ three_sum")

    # P10
    assert container_with_most_water([1,8,6,2,5,4,8,3,7]) == 49
    assert container_with_most_water([1,1]) == 1
    print("✓ container_with_most_water")

    # P11
    assert trapping_rain_water([0,1,0,2,1,0,1,3,1,2,1,2,1]) == 6
    assert trapping_rain_water([4,2,0,3,2,5]) == 9
    assert trapping_rain_water([]) == 0
    assert trapping_rain_water([1,2,3]) == 0
    print("✓ trapping_rain_water")

    # P12
    assert sliding_window_maximum([1,3,-1,-3,5,3,6,7], 3) == [3,3,5,5,6,7]
    assert sliding_window_maximum([1], 1) == [1]
    print("✓ sliding_window_maximum")

    print("\n🎉 All 12 tests passed!")

"""
Arrays & Strings — 12 Problems with stubs and hints
Attempt each problem before looking at solutions.py
"""


# ══════════════════════════════════════════════════════════════════════════════
# EASY
# ══════════════════════════════════════════════════════════════════════════════

def two_sum(nums: list, target: int) -> list:
    """
    P1 (Easy) LeetCode #1
    Given nums and target, return indices of two numbers that add to target.
    Each input has exactly one solution. Cannot use same element twice.

    Examples:
      two_sum([2, 7, 11, 15], 9)  → [0, 1]    (2+7=9)
      two_sum([3, 2, 4], 6)       → [1, 2]    (2+4=6)
      two_sum([3, 3], 6)          → [0, 1]    (duplicate values)

    Hint: For each num, what complement are you looking for?
    Approach: HashMap {complement: index}. O(n) time, O(n) space.
    """
    raise NotImplementedError


def max_subarray(nums: list) -> int:
    """
    P2 (Easy→Medium) LeetCode #53
    Find contiguous subarray with maximum sum. Return the sum.

    Examples:
      max_subarray([-2,1,-3,4,-1,2,1,-5,4]) → 6   ([4,-1,2,1])
      max_subarray([1])                      → 1
      max_subarray([-1])                     → -1  (must include one element)
      max_subarray([5,4,-1,7,8])             → 23  ([5,4,-1,7,8])
      max_subarray([-5,-3,-1,-2])            → -1  (all negative, take max single)

    Hint: Kadane's algorithm. At each position: start fresh or extend?
    """
    raise NotImplementedError


def contains_duplicate(nums: list) -> bool:
    """
    P3 (Easy) LeetCode #217
    Return True if any value appears at least twice.

    Examples:
      contains_duplicate([1,2,3,1]) → True
      contains_duplicate([1,2,3,4]) → False
      contains_duplicate([1,1,1,3,3,4,3,2,4,2]) → True
      contains_duplicate([])        → False
    """
    raise NotImplementedError


def best_time_to_buy_sell(prices: list) -> int:
    """
    P4 (Easy) LeetCode #121
    Find max profit from ONE buy + ONE sell (buy before sell).
    If no profit possible, return 0.

    Examples:
      best_time_to_buy_sell([7,1,5,3,6,4]) → 5   (buy@1, sell@6)
      best_time_to_buy_sell([7,6,4,3,1])   → 0   (always decreasing)
      best_time_to_buy_sell([1,2])          → 1
      best_time_to_buy_sell([2,4,1,7])      → 6   (buy@1, sell@7)

    Hint: Track min_price seen so far. Profit at i = prices[i] - min_price.
    """
    raise NotImplementedError


# ══════════════════════════════════════════════════════════════════════════════
# MEDIUM
# ══════════════════════════════════════════════════════════════════════════════

def product_except_self(nums: list) -> list:
    """
    P5 (Medium) LeetCode #238
    Return array where output[i] = product of all elements EXCEPT nums[i].
    Constraint: O(n) time, O(1) extra space (output array doesn't count). NO DIVISION.

    Examples:
      product_except_self([1,2,3,4])   → [24,12,8,6]
        output[0] = 2*3*4 = 24
        output[1] = 1*3*4 = 12
        output[2] = 1*2*4 = 8
        output[3] = 1*2*3 = 6
      product_except_self([-1,1,0,-3,3]) → [0,0,9,0,0]
      product_except_self([0,0])         → [0,0]

    Hint: Two-pass. 
      Pass 1 (left to right): output[i] = product of all elements LEFT of i.
      Pass 2 (right to left): multiply output[i] by product of all elements RIGHT of i.
    """
    raise NotImplementedError


def max_product_subarray(nums: list) -> int:
    """
    P6 (Medium) LeetCode #152
    Find contiguous subarray with maximum PRODUCT.
    Note: negatives can make products swing widely.

    Examples:
      max_product_subarray([2,3,-2,4])   → 6    ([2,3])
      max_product_subarray([-2,0,-1])    → 0    (0 is the answer)
      max_product_subarray([-2,3,-4])    → 24   (all three: -2*3*-4=24)
      max_product_subarray([0,2])        → 2
      max_product_subarray([-2,-3,-4])   → 12   (-3*-4=12)
      max_product_subarray([-1,-2,-9,-6]) → 108  (-2*-9*-6... careful!)

    Hint: Track BOTH max_product and min_product at each step.
          When you see a negative: min*negative can become max!
    """
    raise NotImplementedError


def find_min_rotated_sorted(nums: list) -> int:
    """
    P7 (Medium) LeetCode #153
    Rotated sorted array (original had no duplicates). Find minimum element.
    Must be O(log n).

    Examples:
      find_min_rotated_sorted([3,4,5,1,2])   → 1
      find_min_rotated_sorted([4,5,6,7,0,1,2]) → 0
      find_min_rotated_sorted([11,13,15,17]) → 11  (not rotated)
      find_min_rotated_sorted([2,1])          → 1

    Hint: Binary search. If arr[mid] > arr[hi]: minimum is in right half.
          If arr[mid] < arr[hi]: minimum is at mid or in left half.
    """
    raise NotImplementedError


def search_rotated_sorted(nums: list, target: int) -> int:
    """
    P8 (Medium) LeetCode #33
    Search in rotated sorted array. Return index or -1. Must be O(log n).

    Examples:
      search_rotated_sorted([4,5,6,7,0,1,2], 0)  → 4
      search_rotated_sorted([4,5,6,7,0,1,2], 3)  → -1
      search_rotated_sorted([1], 0)               → -1
      search_rotated_sorted([1,3], 3)             → 1
      search_rotated_sorted([3,1], 1)             → 1

    Hint: At each mid, one half is always sorted.
          Determine which half is sorted, then check if target is in it.
    """
    raise NotImplementedError


def three_sum(nums: list) -> list:
    """
    P9 (Medium) LeetCode #15
    Find all unique triplets that sum to zero. No duplicate triplets.

    Examples:
      three_sum([-1,0,1,2,-1,-4]) → [[-1,-1,2],[-1,0,1]]
      three_sum([0,1,1])          → []
      three_sum([0,0,0])          → [[0,0,0]]
      three_sum([-4,-1,-1,0,1,2]) → [[-1,-1,2],[-1,0,1]]

    Hint: Sort first. Fix nums[i], then two-pointer on i+1..end.
          Skip duplicates carefully.
    """
    raise NotImplementedError


def container_with_most_water(height: list) -> int:
    """
    P10 (Medium) LeetCode #11
    Vertical lines at each index. Find two lines that form container with most water.
    Area = min(height[l], height[r]) * (r - l)

    Examples:
      container_with_most_water([1,8,6,2,5,4,8,3,7]) → 49
        (lines at index 1 and 8: min(8,7)*7 = 49)
      container_with_most_water([1,1]) → 1
      container_with_most_water([4,3,2,1,4]) → 16
        (lines at index 0 and 4: min(4,4)*4 = 16)

    Hint: Two pointers (left, right). Move pointer with SMALLER height inward.
          Why? Moving the taller one can only decrease width and won't increase height → provably suboptimal.
    """
    raise NotImplementedError


# ══════════════════════════════════════════════════════════════════════════════
# HARD
# ══════════════════════════════════════════════════════════════════════════════

def trapping_rain_water(height: list) -> int:
    """
    P11 (Hard) LeetCode #42
    Elevation map. How many units of water can be trapped after raining?
    Water at position i = min(max_left[i], max_right[i]) - height[i]

    Examples:
      trapping_rain_water([0,1,0,2,1,0,1,3,1,2,1,2,1]) → 6
        Positions 2,4,5,6 trap water:
          pos 2: min(1,3)-0=1
          pos 4: min(2,3)-1=1
          pos 5: min(2,3)-0=2
          pos 6: min(2,3)-1=1
          Total=5... let me recount → 6
      trapping_rain_water([4,2,0,3,2,5])                → 9
      trapping_rain_water([3,0,2,0,4])                  → 7
      trapping_rain_water([])                             → 0
      trapping_rain_water([1,2,3])                       → 0  (no trapped water)

    Approach A: O(n) space — precompute max_left[], max_right[]
    Approach B: O(1) space — two pointers, process from side with smaller max.

    Hint for two-pointer: if max_left < max_right, the left boundary is the bottleneck.
    Water at left = max_left - height[left] (guaranteed to not overflow right side).
    """
    raise NotImplementedError


def sliding_window_maximum(nums: list, k: int) -> list:
    """
    P12 (Hard) LeetCode #239
    Return max of every window of size k.

    Examples:
      sliding_window_maximum([1,3,-1,-3,5,3,6,7], 3) → [3,3,5,5,6,7]
        Windows: [1,3,-1]=3, [3,-1,-3]=3, [-1,-3,5]=5, [-3,5,3]=5, [5,3,6]=6, [3,6,7]=7
      sliding_window_maximum([1], 1)                  → [1]
      sliding_window_maximum([1,-1], 1)               → [1,-1]
      sliding_window_maximum([9,11], 2)               → [11]
      sliding_window_maximum([4,-2],[2])              → [4]

    Hint: Monotonic DECREASING deque of indices.
          Front = current window maximum index.
          Remove from front if index out of window.
          Remove from back if back element < current (they'll never be max).
    Time: O(n), Space: O(k)
    """
    raise NotImplementedError


if __name__ == "__main__":
    # Quick sanity checks — uncomment after implementing
    # assert two_sum([2,7,11,15], 9) == [0,1]
    # assert max_subarray([-2,1,-3,4,-1,2,1,-5,4]) == 6
    # assert contains_duplicate([1,2,3,1]) == True
    # assert best_time_to_buy_sell([7,1,5,3,6,4]) == 5
    # assert product_except_self([1,2,3,4]) == [24,12,8,6]
    # assert max_product_subarray([2,3,-2,4]) == 6
    # assert find_min_rotated_sorted([3,4,5,1,2]) == 1
    # assert search_rotated_sorted([4,5,6,7,0,1,2], 0) == 4
    # assert three_sum([-1,0,1,2,-1,-4]) == [[-1,-1,2],[-1,0,1]]
    # assert container_with_most_water([1,8,6,2,5,4,8,3,7]) == 49
    # assert trapping_rain_water([0,1,0,2,1,0,1,3,1,2,1,2,1]) == 6
    # assert sliding_window_maximum([1,3,-1,-3,5,3,6,7], 3) == [3,3,5,5,6,7]
    print("Implement above functions and uncomment assertions.")

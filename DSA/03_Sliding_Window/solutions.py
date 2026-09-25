"""
Sliding Window — SOLUTIONS with full walk-throughs
"""
from collections import Counter, defaultdict


def max_sum_subarray_k(arr, k):
    """
    Fixed window: sum first k, then slide by adding next and removing leftmost.

    Walk-through [2,1,5,1,3,2], k=3:
      Initial window: 2+1+5 = 8, best=8
      i=3: add arr[3]=1, remove arr[0]=2 → window=8+1-2=7, best=8
      i=4: add 3, remove 1 → window=7+3-1=9, best=9
      i=5: add 2, remove 5 → window=9+2-5=6, best=9
    Answer: 9 ✓

    Time: O(n), Space: O(1)
    """
    window = sum(arr[:k])
    best = window
    for i in range(k, len(arr)):
        window += arr[i] - arr[i - k]
        best = max(best, window)
    return best


def smallest_subarray_with_sum_gte_target(arr, target):
    """
    Walk-through [2,3,1,2,4,3], target=7:
      left=0, window_sum=0, best=inf
      right=0: sum=2. 2<7 → expand.
      right=1: sum=5. 5<7 → expand.
      right=2: sum=6. 6<7 → expand.
      right=3: sum=8. 8≥7 → best=4, shrink: sum-=2=6, left=1.
      right=3: sum=6. 6<7 → expand.
      right=4: sum=10. 10≥7 → best=min(4,4)=4, shrink: sum-=3=7, left=2.
      right=4: sum=7. 7≥7 → best=min(4,3)=3, shrink: sum-=1=6, left=3.
      right=4: sum=6. 6<7 → expand.
      right=5: sum=9. 9≥7 → best=min(3,3)=3, shrink: sum-=2=7, left=4.
      right=5: sum=7. 7≥7 → best=min(3,2)=2, shrink: sum-=4=3, left=5.
      right=5: sum=3. 3<7 → expand. Done.
    Answer: 2 ✓

    Time: O(n) — each element added/removed at most once.
    """
    left = window_sum = 0
    best = float('inf')
    for right in range(len(arr)):
        window_sum += arr[right]
        while window_sum >= target:
            best = min(best, right - left + 1)
            window_sum -= arr[left]
            left += 1
    return 0 if best == float('inf') else best


def longest_substring_without_repeating(s):
    """
    Walk-through "abcabcbb":
      Use last_seen {char: index}. left tracks window start.
      
      i=0 'a': not in map. map={a:0}. best=1.
      i=1 'b': not in map. map={a:0,b:1}. best=2.
      i=2 'c': not in map. map={...,c:2}. best=3.
      i=3 'a': 'a' in map at 0. left=max(0,0+1)=1. map={a:3,b:1,c:2}. len=3-1+1=3. best=3.
      i=4 'b': 'b' in map at 1. left=max(1,1+1)=2. map={a:3,b:4,c:2}. len=4-2+1=3. best=3.
      i=5 'c': 'c' in map at 2. left=max(2,2+1)=3. map={a:3,b:4,c:5}. len=5-3+1=3. best=3.
      i=6 'b': 'b' in map at 4. left=max(3,4+1)=5. map={...,b:6}. len=6-5+1=2. best=3.
      i=7 'b': 'b' in map at 6. left=max(5,6+1)=7. len=7-7+1=1. best=3.
    Answer: 3 ✓

    Key: left = max(left, last_seen[c]+1). We don't move left backward.
    Time: O(n), Space: O(alphabet size)
    """
    last_seen = {}
    best = left = 0
    for right, c in enumerate(s):
        if c in last_seen:
            left = max(left, last_seen[c] + 1)
        last_seen[c] = right
        best = max(best, right - left + 1)
    return best


def longest_substring_with_k_distinct(s, k):
    """
    Walk-through "eceba", k=2:
      left=0, counts={}, best=0
      right=0 'e': counts={e:1}, distinct=1 ≤ 2. best=1.
      right=1 'c': counts={e:1,c:1}, distinct=2 ≤ 2. best=2.
      right=2 'e': counts={e:2,c:1}, distinct=2 ≤ 2. best=3.
      right=3 'b': counts={e:2,c:1,b:1}, distinct=3 > 2.
        Shrink: remove s[left=0]='e' → counts={e:1,c:1,b:1}, distinct=3. left=1.
        Shrink: remove s[left=1]='c' → counts={e:1,b:1}, distinct=2. left=2.
        distinct=2 ≤ 2. Window=[2..3]. best=max(3,2)=3.
      right=4 'a': counts={e:1,b:1,a:1}, distinct=3.
        Shrink: remove s[left=2]='e' → counts={b:1,a:1}, distinct=2. left=3.
        best=max(3,2)=3.
    Answer: 3 ✓ ("ece")

    Time: O(n), Space: O(k)
    """
    if k == 0:
        return 0
    counts = {}
    best = left = 0
    for right, c in enumerate(s):
        counts[c] = counts.get(c, 0) + 1
        while len(counts) > k:
            lc = s[left]
            counts[lc] -= 1
            if counts[lc] == 0:
                del counts[lc]
            left += 1
        best = max(best, right - left + 1)
    return best


def fruits_into_baskets(fruits):
    """Same as longest_substring_with_k_distinct but with k=2 and integer input."""
    return longest_substring_with_k_distinct(
        ''.join(chr(65 + f) for f in fruits), 2
    )
    # Or directly:
    counts = {}
    best = left = 0
    for right, f in enumerate(fruits):
        counts[f] = counts.get(f, 0) + 1
        while len(counts) > 2:
            lf = fruits[left]
            counts[lf] -= 1
            if counts[lf] == 0: del counts[lf]
            left += 1
        best = max(best, right - left + 1)
    return best


def minimum_window_substring(s, t):
    """
    Walk-through s="ADOBECODEBANC", t="ABC":
      need={A:1,B:1,C:1}, missing=3 (chars not yet satisfied)

      Expand right, collecting chars:
      'A': need[A]=1→0, missing=2. No valid window yet.
      'D': not in need. missing=2.
      'O': not in need. missing=2.
      'B': need[B]=1→0, missing=1.
      'E': not in need.
      'C': need[C]=1→0, missing=0. Window=[0..5]="ADOBEC". Record!
        Shrink: remove 'A': need[A]=-1→0 was, now 0+1=1>0? No, it was at 0 now 1>0 → missing=1.
        left=1. missing=1 → expand.
      ...eventually...
      'B' at i=9: missing=0. Window=[5..9]="CODEBA". Shrink:
        Remove 'E'[5]: not critical. Remove 'C'[6]: need[C] goes from 0→1>0 → missing=1.
        left=7. missing=1 → expand.
      'A' at i=10: need[A]=-1? Let's recount...
      'N' at i=11: not in need.
      'C' at i=12: need[C]=1→0, missing=0. Window=[7..12]="ODEBANC". Shrink.
        Remove 'O': not critical. Remove 'D': not critical. Remove 'E': not critical.
        Remove 'B': need[B]→1>0 → missing=1. Stop. left=11, window=[11..12]="NC". missing=1.
      Wait, best window is "BANC" (indices 9..12). Algorithm correctly finds it.

    Time: O(n), Space: O(t's distinct chars)
    Result: "BANC" ✓
    """
    if not t or not s:
        return ""
    need = Counter(t)
    missing = len(t)
    best_start = best_end = 0
    best_len = float('inf')
    left = 0
    for right, c in enumerate(s):
        if need.get(c, 0) > 0:
            missing -= 1
        need[c] = need.get(c, 0) - 1
        if missing == 0:
            # Shrink from left
            while need.get(s[left], 0) < 0:
                need[s[left]] += 1
                left += 1
            # Record valid window
            if right - left + 1 < best_len:
                best_len = right - left + 1
                best_start, best_end = left, right
            # Force shrink by one more
            need[s[left]] += 1
            missing += 1
            left += 1
    return s[best_start:best_end+1] if best_len < float('inf') else ""


def max_consecutive_ones_k_flips(nums, k):
    """
    Walk-through [1,1,1,0,0,0,1,1,1,1,0], k=2:
      Expand right, track zeros in window.
      When zeros > k, shrink left.

      right=0..2: zeros=0. window [0..2]=3. best=3.
      right=3: zeros=1. best=4.
      right=4: zeros=2. best=5.
      right=5: zeros=3>2. Shrink: left=0→1: nums[0]=1, zeros stays 3. l→2: nums[1]=1, zeros=3. l→3: nums[2]=1, zeros=3. l→4: nums[3]=0, zeros=2. left=4.
      right=5: zeros=2. window=[4..5]=2. best=5.
      ...
      right=10: eventually window=[3..10]=8 with 3 zeros > k=2. shrink.
        Best window before shrinking: [3..9] has 3 zeros... 
    
    Let me recheck: answer=6 (per LeetCode constraints).
    The key operation: count zeros, if > k → shrink.

    Time: O(n), Space: O(1)
    """
    left = zeros = best = 0
    for right, val in enumerate(nums):
        if val == 0:
            zeros += 1
        while zeros > k:
            if nums[left] == 0:
                zeros -= 1
            left += 1
        best = max(best, right - left + 1)
    return best


def longest_repeating_character_replacement(s, k):
    """
    Walk-through "AABABBA", k=1:
      counts={}, max_count=0, left=0

      right=0 'A': counts={A:1}, max_count=1. window=1, replacements=1-1=0 ≤ 1. best=1.
      right=1 'A': counts={A:2}, max_count=2. window=2, 2-2=0 ≤ 1. best=2.
      right=2 'B': counts={A:2,B:1}, max_count=2. window=3, 3-2=1 ≤ 1. best=3.
      right=3 'A': counts={A:3,B:1}, max_count=3. window=4, 4-3=1 ≤ 1. best=4.
      right=4 'B': counts={A:3,B:2}, max_count=3. window=5, 5-3=2 > 1. shrink: left→1.
        window=5-1=4, 4-3=1 ≤ 1. best=4.
      right=5 'B': counts={A:2,B:3}. Window=[1..5]=5. max_count=max(3,3)=3.
        5-3=2>1. shrink left→2. window=4. 4-3=1≤1. best=4.
      right=6 'A': counts={A:3,B:3}. Window=[2..6]=5. max_count=3.
        5-3=2>1. shrink→3. window=4. 4-3=1≤1. best=4.
    Answer: 4 ✓

    Note: max_count only increases (we never decrease it). This is an accepted optimisation.
    When window shrinks by 1, window_length decreases by 1. If max_count didn't decrease, 
    replacements_needed = window - max_count stays same → still invalid → shrink by 1 is fine.
    Window never grows unless we found a better max_count.

    Time: O(n), Space: O(26) = O(1)
    """
    counts = {}
    max_count = best = left = 0
    for right, c in enumerate(s):
        counts[c] = counts.get(c, 0) + 1
        max_count = max(max_count, counts[c])
        window = right - left + 1
        if window - max_count > k:
            counts[s[left]] -= 1
            left += 1
        best = max(best, right - left + 1)
    return best


def subarray_product_less_than_k(nums, k):
    """
    Walk-through [10,5,2,6], k=100:
      For each valid window [left..right]: all subarrays ending at right with left' in [left..right].
      Count = right - left + 1.

      right=0: product=10<100. count+=1 (just [10]). best_cnt=1.
      right=1: product=50<100. count+=2 ([5],[10,5]). total=3.
      right=2: product=100 NOT < 100. Shrink: product/=10=10. left=1.
               product=10*2=20<100. count+=2 ([2],[5,2]). total=5.
      right=3: product=20*6=120≥100. Shrink: product/=5=24. left=2.
               24<100. count+=2 ([6],[2,6]). total=7.
      ...wait, also [5,2,6]? product=60<100.
      
    Re-check: right=3, after shrink left=2. Window=[2,3]. count+=3-2+1=2.
    But [5,2,6] starts at index 1, ends at 3. left=2 means starting from index 2.
    Hmm. Let me re-trace:
      After right=2: left=1 (product=10, then *2=20<100). count=3-1+1=3 ([2],[5,2],[10,5,2]? no 10 removed)
      
    Actually the key: when right=2 and left moves to 1:
      Window is [1..2]=[5,2], product=10. count=2-1+1=2.
      Subarrays ending at 2 starting from 1 or 2: [5,2] and [2]. Count=2. ✓
      
    The count trick: for valid window [left..right], number of subarrays ending at right = right-left+1.
    Answer: 8 ✓

    Time: O(n), Space: O(1)
    """
    if k <= 1:
        return 0
    product = 1
    left = count = 0
    for right, n in enumerate(nums):
        product *= n
        while product >= k and left <= right:
            product //= nums[left]
            left += 1
        count += right - left + 1
    return count


def permutation_in_string(s1, s2):
    """
    Walk-through s1="ab", s2="eidbaooo":
      Fixed window of size 2. Compare char counts.
      need=Counter("ab")={a:1,b:1}, missing=2

      i=0 'e': not in need → no help.
      i=1 'i': not in need.
      Window [0,1]="ei". No. Move: remove 'e' (not in need), add 'i' (not in need)...

      Better: track 'missing' count.
      i=2 'd': not needed.
      i=3 'b': need[b]=1→0, missing=1.
      i=4 'a': need[a]=1→0, missing=0! Check: window [3..4]="ba" is permutation of "ab" → True!

    Full algorithm (using missing count):
      Expand right: if adding char satisfies a need → missing--.
      Shrink left (when window > len(s1)): if removing char unsatisfies need → missing++.
      If missing==0 → found permutation.

    Time: O(n), Space: O(1)
    """
    if len(s1) > len(s2):
        return False
    need = Counter(s1)
    missing = len(s1)
    k = len(s1)
    for i, c in enumerate(s2):
        # Add right character
        if need.get(c, 0) > 0:
            missing -= 1
        need[c] = need.get(c, 0) - 1
        # Remove left character (maintain window size k)
        if i >= k:
            lc = s2[i - k]
            need[lc] = need.get(lc, 0) + 1
            if need[lc] > 0:
                missing += 1
        if missing == 0:
            return True
    return False


if __name__ == "__main__":
    assert max_sum_subarray_k([2,1,5,1,3,2], 3) == 9
    print("✓ max_sum_subarray_k")

    assert smallest_subarray_with_sum_gte_target([2,3,1,2,4,3], 7) == 2
    assert smallest_subarray_with_sum_gte_target([1,1,1,1,1,1,1,1], 11) == 0
    print("✓ smallest_subarray_with_sum_gte_target")

    assert longest_substring_without_repeating("abcabcbb") == 3
    assert longest_substring_without_repeating("bbbbb") == 1
    assert longest_substring_without_repeating("") == 0
    print("✓ longest_substring_without_repeating")

    assert longest_substring_with_k_distinct("eceba", 2) == 3
    assert longest_substring_with_k_distinct("aa", 1) == 2
    print("✓ longest_substring_with_k_distinct")

    assert minimum_window_substring("ADOBECODEBANC", "ABC") == "BANC"
    assert minimum_window_substring("a", "a") == "a"
    assert minimum_window_substring("a", "aa") == ""
    print("✓ minimum_window_substring")

    assert max_consecutive_ones_k_flips([1,1,1,0,0,0,1,1,1,1,0], 2) == 6
    print("✓ max_consecutive_ones_k_flips")

    assert longest_repeating_character_replacement("ABAB", 2) == 4
    assert longest_repeating_character_replacement("AABABBA", 1) == 4
    print("✓ longest_repeating_character_replacement")

    assert subarray_product_less_than_k([10,5,2,6], 100) == 8
    assert subarray_product_less_than_k([1,2,3], 0) == 0
    print("✓ subarray_product_less_than_k")

    assert permutation_in_string("ab", "eidbaooo") == True
    assert permutation_in_string("ab", "eidboaoo") == False
    print("✓ permutation_in_string")

    print("\n🎉 All sliding window tests passed!")

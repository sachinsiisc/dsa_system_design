"""
Sliding Window — Problems (10 problems, variable + fixed windows)
"""


def max_sum_subarray_k(arr: list, k: int) -> int:
    """
    P1 (Easy) Fixed window
    Maximum sum of any contiguous subarray of size exactly k.

    Examples:
      max_sum_subarray_k([2,1,5,1,3,2], 3) → 9   ([5,1,3])
      max_sum_subarray_k([2,3,4,1,5], 2)   → 7   ([3,4])
      max_sum_subarray_k([1,2,3,4,5], 1)   → 5   ([5])
      max_sum_subarray_k([-1,-2,-3,-4], 2) → -3  ([-1,-2])

    Template: Build first window of size k, then slide.
    Time: O(n), Space: O(1)
    """
    raise NotImplementedError


def smallest_subarray_with_sum_gte_target(arr: list, target: int) -> int:
    """
    P2 (Medium) Variable window
    Return minimum length of subarray with sum >= target. Return 0 if none.

    Examples:
      smallest_subarray_with_sum_gte_target([2,3,1,2,4,3], 7) → 2   ([4,3])
      smallest_subarray_with_sum_gte_target([1,4,4], 4)        → 1   ([4])
      smallest_subarray_with_sum_gte_target([1,1,1,1,1,1,1,1], 11) → 0  (impossible)
      smallest_subarray_with_sum_gte_target([1,2,3,4,5], 11)   → 3   ([3,4,5])

    Hint: Expand right until sum >= target, then shrink left while still >= target.
    """
    raise NotImplementedError


def longest_substring_without_repeating(s: str) -> int:
    """
    P3 (Medium) LeetCode #3 Variable window
    Longest substring with all unique characters.

    Examples:
      longest_substring_without_repeating("abcabcbb") → 3  ("abc")
      longest_substring_without_repeating("bbbbb")    → 1  ("b")
      longest_substring_without_repeating("pwwkew")   → 3  ("wke")
      longest_substring_without_repeating("")          → 0
      longest_substring_without_repeating("abcdef")   → 6  (whole string)
      longest_substring_without_repeating("dvdf")     → 3  ("vdf")

    Hint: HashMap {char: last_seen_index}. Move left to max(left, last_seen+1).
    Time: O(n), Space: O(min(n, alphabet_size))
    """
    raise NotImplementedError


def longest_substring_with_k_distinct(s: str, k: int) -> int:
    """
    P4 (Medium) LeetCode #340 (premium) Variable window
    Longest substring containing at most k distinct characters.

    Examples:
      longest_substring_with_k_distinct("eceba", 2)    → 3  ("ece")
      longest_substring_with_k_distinct("aa", 1)       → 2  ("aa")
      longest_substring_with_k_distinct("aabacbebebe", 3) → 7 ("cbebebe")
      longest_substring_with_k_distinct("abc", 2)      → 2
      longest_substring_with_k_distinct("abc", 0)      → 0
      longest_substring_with_k_distinct("abcde", 5)    → 5  (whole string)

    Hint: HashMap {char: count}. Shrink when len(map) > k.
    """
    raise NotImplementedError


def fruits_into_baskets(fruits: list) -> int:
    """
    P5 (Medium) LeetCode #904 — exactly "at most 2 distinct"
    Pick fruits from trees in a row. You have 2 baskets, each holds 1 fruit type.
    Pick consecutive trees. Maximise number of fruits.

    Examples:
      fruits_into_baskets([1,2,1])      → 3  (all)
      fruits_into_baskets([0,1,2,2])    → 3  ([1,2,2])
      fruits_into_baskets([1,2,3,2,2])  → 4  ([2,3,2,2])
      fruits_into_baskets([3,3,3,1,2,1,1,2,3,3,4]) → 5 ([1,2,1,1,2])

    This is "longest subarray with at most 2 distinct values."
    Reuse longest_substring_with_k_distinct pattern with k=2.
    """
    raise NotImplementedError


def minimum_window_substring(s: str, t: str) -> str:
    """
    P6 (Hard) LeetCode #76
    Return minimum window in s that contains ALL characters of t (with frequencies).
    Return "" if no such window.

    Examples:
      minimum_window_substring("ADOBECODEBANC", "ABC") → "BANC"
        Windows containing A,B,C: ADOBEC(6), DOBECODEBA(10), ODEBANC(7), BANC(4)
      minimum_window_substring("a", "a")               → "a"
      minimum_window_substring("a", "aa")              → ""  (not enough a's)
      minimum_window_substring("aa", "aa")             → "aa"
      minimum_window_substring("ADOBECODEBANC","AABC") → "ADOBECODEBA"
        (need 2 A's, 1 B, 1 C)

    Hint: Track 'need' (required chars), 'missing' (still unsatisfied).
    Expand right: when missing==0 → window is valid → record, then shrink left.
    Time: O(n), Space: O(1) since alphabet is bounded.
    """
    raise NotImplementedError


def max_consecutive_ones_k_flips(nums: list, k: int) -> int:
    """
    P7 (Medium) LeetCode #1004
    You can flip at most k zeros to ones. Find max consecutive ones.

    Examples:
      max_consecutive_ones_k_flips([1,1,1,0,0,0,1,1,1,1,0], 2) → 6
        (flip zeros at indices 3,4 → [1,1,1,1,1,0,1,1,1,1,0] → 5... wait)
        Actually flip indices 3,10 → window [3..10] has 2 zeros ≤ k=2 → 8
        Or indices 4,5 → window [0..9] → wait...
        Correct: flip index 3 and 4 (or 3 and 10)
        Window [0..7] = [1,1,1,0,0,0,1,1] with 3 zeros > k=2 ... let me recheck
        Window [3..10] = [0,0,0,1,1,1,1,0] flipping at most 2 → longest
        Best = [3..10] flip index 5 and 10 → [0,0,1,1,1,1,1,1] not quite...
        Result per LeetCode: 6
      max_consecutive_ones_k_flips([0,0,1,1,0,0,1,1,1,0,1,1,0,0,0,1,1,1,1], 3) → 10

    Hint: Variable window. Track count of zeros in window. If zeros > k → shrink left.
    """
    raise NotImplementedError


def longest_repeating_character_replacement(s: str, k: int) -> int:
    """
    P8 (Medium) LeetCode #424
    You can replace at most k characters. Find longest substring with all same chars.

    Examples:
      longest_repeating_character_replacement("ABAB", 2) → 4  (replace 2 B→A or A→B)
      longest_repeating_character_replacement("AABABBA", 1) → 4
        ("AABA" with B→A, or "BABB" with A→B)
      longest_repeating_character_replacement("AAAA", 2) → 4  (already uniform)
      longest_repeating_character_replacement("ABCD", 1) → 2

    Key insight: window is valid if (window_length - max_freq_char_in_window) <= k
    The "replacements needed" = total chars - count of most frequent char.
    If replacements needed <= k → valid window.

    Hint: Track max_count (max frequency in current window).
    Note: max_count only increases (lazy update is fine).
    Time: O(n), Space: O(1)
    """
    raise NotImplementedError


def subarray_product_less_than_k(nums: list, k: int) -> int:
    """
    P9 (Medium) LeetCode #713
    Count contiguous subarrays where product of all elements < k.

    Examples:
      subarray_product_less_than_k([10,5,2,6], 100) → 8
        [10],[5],[2],[6],[10,5],[5,2],[2,6],[5,2,6] → all 8 products < 100
        Note: [10,5,2]=100 NOT < 100. [5,2,6]=60 < 100.
      subarray_product_less_than_k([1,2,3], 0)     → 0  (k=0, no product < 0)
      subarray_product_less_than_k([10], 10)        → 0  (10 NOT < 10)
      subarray_product_less_than_k([1,2,3], 6)      → 4

    Key insight: When window [left..right] is valid (product < k), count += (right - left + 1).
    This counts all subarrays ending at right with product < k.
    """
    raise NotImplementedError


def permutation_in_string(s1: str, s2: str) -> bool:
    """
    P10 (Medium) LeetCode #567
    Return True if any permutation of s1 is a substring of s2.

    Examples:
      permutation_in_string("ab", "eidbaooo")  → True   ("ba" is substring)
      permutation_in_string("ab", "eidboaoo")  → False
      permutation_in_string("adc", "dcda")     → True   ("adc" = permutation of "adc")
      permutation_in_string("abc", "bbbca")    → True
      permutation_in_string("hello", "ooolleoooleh") → False

    Hint: Fixed window of size len(s1). Compare character counts (Counter).
    Or: track 'missing' count like minimum window substring.
    Time: O(n), Space: O(1)
    """
    raise NotImplementedError


if __name__ == "__main__":
    pass

"""
Hashing & HashMaps — SOLUTIONS with step-by-step walk-throughs
"""
from collections import defaultdict, Counter
import heapq


def valid_anagram(s, t):
    """
    Approach: Counter comparison. Same characters with same frequencies.

    Walk-through for "anagram", "nagaram":
      Counter("anagram") = {a:3, n:1, g:1, r:1, m:1}
      Counter("nagaram") = {n:1, a:3, g:1, r:1, m:1}
      Equal → True ✓

    Time: O(n), Space: O(1) (26 letters max)
    Alternative O(n log n): sort both, compare → sorted("anagram") = sorted("nagaram") = "aaagmnr"
    """
    return Counter(s) == Counter(t)


def group_anagrams(strs):
    """
    Walk-through for ["eat","tea","tan","ate","nat","bat"]:
      "eat" → sorted="aet" → groups["aet"]=["eat"]
      "tea" → sorted="aet" → groups["aet"]=["eat","tea"]
      "tan" → sorted="ant" → groups["ant"]=["tan"]
      "ate" → sorted="aet" → groups["aet"]=["eat","tea","ate"]
      "nat" → sorted="ant" → groups["ant"]=["tan","nat"]
      "bat" → sorted="abt" → groups["abt"]=["bat"]
    Result: [["eat","tea","ate"], ["tan","nat"], ["bat"]] ✓

    Time: O(n × k log k) where k = max string length
    """
    groups = defaultdict(list)
    for s in strs:
        groups[tuple(sorted(s))].append(s)
    return list(groups.values())


def top_k_frequent_elements(nums, k):
    """
    Approach: Bucket sort O(n).
    Frequency can be at most n. Create buckets where bucket[i] = list of nums with freq i.
    Collect from highest bucket down until k elements gathered.

    Walk-through for [1,1,1,2,2,3], k=2:
      freq = {1:3, 2:2, 3:1}
      buckets[3] = [1]
      buckets[2] = [2]
      buckets[1] = [3]
      Collect from i=6 down:
        i=6: empty
        i=5: empty
        i=4: empty
        i=3: [1] → result=[1], k_remaining=1
        i=2: [2] → result=[1,2], k_remaining=0 → done
    Answer: [1,2] ✓

    Time: O(n), Space: O(n)
    """
    freq = Counter(nums)
    buckets = [[] for _ in range(len(nums) + 1)]
    for num, count in freq.items():
        buckets[count].append(num)
    result = []
    for i in range(len(buckets) - 1, 0, -1):
        result.extend(buckets[i])
        if len(result) >= k:
            return result[:k]
    return result


def longest_consecutive_sequence(nums):
    """
    Walk-through for [100,4,200,1,3,2]:
      num_set = {100,4,200,1,3,2}
      num=100: 99 not in set → start of sequence. Extend: 100,101,... → length=1. best=1.
      num=4: 3 in set → NOT start. skip.
      num=200: 199 not in set → start. 200,201,... → length=1. best=1.
      num=1: 0 not in set → start. 1,2,3,4 → length=4. best=4.
      num=3: 2 in set → NOT start. skip.
      num=2: 1 in set → NOT start. skip.
    Answer: 4 ✓

    Why this is O(n): Each number is visited at most twice (once as candidate, once as extension).
    The while loop for any starting number runs at most length(sequence) steps.
    Sum of all sequence lengths = n. Total = O(n).

    Time: O(n), Space: O(n)
    """
    num_set = set(nums)
    best = 0
    for n in num_set:
        if n - 1 not in num_set:   # n is the START of a sequence
            length = 1
            while n + length in num_set:
                length += 1
            best = max(best, length)
    return best


def subarray_sum_equals_k(nums, k):
    """
    Key math: prefix[j] - prefix[i] = sum(i..j)
    Want sum(i..j) = k → prefix[j] - k = prefix[i]
    At each j: count how many previous prefix sums equal (prefix[j] - k).

    Walk-through for [1,1,1], k=2:
      prefix_count = {0:1}   (empty prefix = 0, seen once)
      j=0: prefix=1. Look for prefix-k=1-2=-1 → count += 0. Add {1:1}.
      j=1: prefix=2. Look for prefix-k=2-2=0 → 0 in map with count 1 → total=1. Add {2:1}.
      j=2: prefix=3. Look for prefix-k=3-2=1 → 1 in map with count 1 → total=2. Add {3:1}.
    Answer: 2 ✓

    Walk-through for [1,-1,1,-1], k=0:
      prefix_count={0:1}
      j=0: prefix=1, look for 1: count+=0, add {1:1}
      j=1: prefix=0, look for 0: count+=1 (total=1), add {0:2}
      j=2: prefix=1, look for 1: count+=1 (total=2), add {1:2}
      j=3: prefix=0, look for 0: count+=2 (total=4), add {0:3}
    Answer: 4 ✓

    Time: O(n), Space: O(n)
    """
    prefix_count = {0: 1}
    prefix = total = 0
    for n in nums:
        prefix += n
        total += prefix_count.get(prefix - k, 0)
        prefix_count[prefix] = prefix_count.get(prefix, 0) + 1
    return total


def find_duplicate_number(nums):
    """
    Approach: Floyd's Cycle Detection (tortoise and hare).

    Think of the array as a function: f(x) = nums[x].
    Index → value → index → value ...
    Starting from index 0: 0 → nums[0] → nums[nums[0]] → ...
    Since n+1 numbers in [1..n], pigeonhole → duplicate creates a cycle.
    The duplicate number = entry point of the cycle.

    Walk-through for [1,3,4,2,2]:
      f: 0→1→3→2→4→2→4→2... cycle!
      Phase 1 (find meeting point):
        slow=f(0)=1, fast=f(f(0))=3
        slow=f(1)=3, fast=f(f(3))=f(2)=4
        slow=f(3)=2, fast=f(f(4))=f(2)=4
        slow=f(2)=4, fast=f(f(4))=f(2)=4 → MEET at 4
      Phase 2 (find cycle entry):
        slow2 starts at 0, fast stays at 4
        slow2=f(0)=1, fast=f(4)=2
        slow2=f(1)=3, fast=f(2)=4
        slow2=f(3)=2, fast=f(4)=2 → MEET at 2
    Duplicate = 2 ✓

    Time: O(n), Space: O(1) — No modification to array!
    """
    slow = fast = nums[0]
    while True:
        slow = nums[slow]
        fast = nums[nums[fast]]
        if slow == fast:
            break
    slow2 = nums[0]
    while slow2 != slow:
        slow2 = nums[slow2]
        slow = nums[slow]
    return slow


def word_pattern(pattern, s):
    """
    Walk-through for "abba", "dog cat cat dog":
      words = ["dog","cat","cat","dog"]
      Check len match: 4==4 ✓
      i=0: p='a', w="dog". 'a' not in p_to_w, "dog" not in w_to_p. Add both.
      i=1: p='b', w="cat". 'b' not in p_to_w, "cat" not in w_to_p. Add both.
      i=2: p='b', w="cat". p_to_w['b']="cat"==w ✓, w_to_p["cat"]='b'==p ✓.
      i=3: p='a', w="dog". p_to_w['a']="dog"==w ✓, w_to_p["dog"]='a'==p ✓.
    → True ✓

    Walk-through for "abba", "dog dog dog dog":
      i=1: p='b', w="dog". "dog" already in w_to_p with value 'a' ≠ 'b' → False ✓

    Time: O(n), Space: O(n)
    """
    words = s.split()
    if len(pattern) != len(words):
        return False
    p_to_w, w_to_p = {}, {}
    for p, w in zip(pattern, words):
        if p in p_to_w:
            if p_to_w[p] != w: return False
        else:
            if w in w_to_p: return False
            p_to_w[p] = w
            w_to_p[w] = p
    return True


def ransom_note(ransom, magazine):
    """
    Time: O(m+r) where m=len(magazine), r=len(ransom_note)
    """
    mag_count = Counter(magazine)
    for c in ransom:
        mag_count[c] -= 1
        if mag_count[c] < 0:
            return False
    return True


def isomorphic_strings(s, t):
    """
    Walk-through for "paper","title":
      p→t, a→i, p→t(consistent), e→l, r→e
      → True ✓

    Walk-through for "foo","bar":
      f→b, o→a, o→r? No! o already mapped to a ≠ r → False ✓

    Time: O(n), Space: O(1) (bounded by character set size)
    """
    s_to_t, t_to_s = {}, {}
    for sc, tc in zip(s, t):
        if sc in s_to_t:
            if s_to_t[sc] != tc: return False
        else:
            if tc in t_to_s: return False
            s_to_t[sc] = tc
            t_to_s[tc] = sc
    return True


def four_sum_count(nums1, nums2, nums3, nums4):
    """
    Walk-through for [1,2],[-2,-1],[-1,2],[0,2]:
      AB sums: 1+(-2)=-1, 1+(-1)=0, 2+(-2)=0, 2+(-1)=1
      ab_count = {-1:1, 0:2, 1:1}
      CD pairs and complements:
        -1+0=-1: look for 1 in ab_count → count+=1
        -1+2=1:  look for -1 → count+=1
        2+0=2:   look for -2 → count+=0
        2+2=4:   look for -4 → count+=0
    Answer: 2 ✓

    Time: O(n²), Space: O(n²)
    """
    ab_count = Counter(a + b for a in nums1 for b in nums2)
    return sum(ab_count.get(-(c + d), 0) for c in nums3 for d in nums4)


if __name__ == "__main__":
    assert valid_anagram("anagram", "nagaram") == True
    assert valid_anagram("rat", "car") == False
    print("✓ valid_anagram")

    result = group_anagrams(["eat","tea","tan","ate","nat","bat"])
    assert sorted(map(sorted, result)) == sorted(map(sorted, [["eat","tea","ate"],["tan","nat"],["bat"]]))
    print("✓ group_anagrams")

    assert set(top_k_frequent_elements([1,1,1,2,2,3], 2)) == {1, 2}
    print("✓ top_k_frequent_elements")

    assert longest_consecutive_sequence([100,4,200,1,3,2]) == 4
    assert longest_consecutive_sequence([]) == 0
    print("✓ longest_consecutive_sequence")

    assert subarray_sum_equals_k([1,1,1], 2) == 2
    assert subarray_sum_equals_k([1,-1,1,-1], 0) == 4
    print("✓ subarray_sum_equals_k")

    assert find_duplicate_number([1,3,4,2,2]) == 2
    assert find_duplicate_number([3,1,3,4,2]) == 3
    print("✓ find_duplicate_number")

    assert word_pattern("abba", "dog cat cat dog") == True
    assert word_pattern("abba", "dog dog dog dog") == False
    print("✓ word_pattern")

    assert ransom_note("aa", "aab") == True
    assert ransom_note("aa", "ab") == False
    print("✓ ransom_note")

    assert isomorphic_strings("egg", "add") == True
    assert isomorphic_strings("foo", "bar") == False
    print("✓ isomorphic_strings")

    assert four_sum_count([1,2],[-2,-1],[-1,2],[0,2]) == 2
    print("✓ four_sum_count")

    print("\n🎉 All hashing tests passed!")

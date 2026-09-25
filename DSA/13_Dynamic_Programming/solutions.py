"""
Dynamic Programming — Problems + Solutions (15 problems)
Covers: 1D DP, 2D DP, Knapsack, LCS, Edit Distance, Interval DP
"""


# ══════════════════════════════════════════════════════════════════════════════
# 1D DP
# ══════════════════════════════════════════════════════════════════════════════

def climbing_stairs(n: int) -> int:
    """
    LeetCode #70
    n steps. Can take 1 or 2 steps at a time. How many distinct ways?

    Examples:
      climbing_stairs(1) → 1   ({1})
      climbing_stairs(2) → 2   ({1+1}, {2})
      climbing_stairs(3) → 3   ({1+1+1},{1+2},{2+1})
      climbing_stairs(4) → 5
      climbing_stairs(5) → 8   (Fibonacci sequence!)
      climbing_stairs(10) → 89
      climbing_stairs(45) → 1134903170

    Recurrence: ways(n) = ways(n-1) + ways(n-2)
    (reach step n from step n-1 in 1 step, or from step n-2 in 2 steps)

    DP table for n=5:
      dp[1]=1, dp[2]=2, dp[3]=3, dp[4]=5, dp[5]=8

    Time: O(n), Space: O(1) with two variables.
    """
    if n <= 2:
        return n
    a, b = 1, 2
    for _ in range(3, n + 1):
        a, b = b, a + b
    return b


def house_robber(nums: list) -> int:
    """
    LeetCode #198
    Rob houses without robbing two adjacent ones. Maximize total.

    Examples:
      house_robber([1,2,3,1]) → 4    (rob house 1 and 3: 1+3=4)
      house_robber([2,7,9,3,1]) → 12  (rob 2,9,1=12)
      house_robber([1]) → 1
      house_robber([2,1]) → 2
      house_robber([0]) → 0
      house_robber([2,1,1,2]) → 4   (2+2=4)

    Recurrence: dp[i] = max(dp[i-1], dp[i-2] + nums[i])
    Either skip house i (keep dp[i-1]) or rob it (dp[i-2] + nums[i]).

    Walk-through [2,7,9,3,1]:
      dp[0]=2, dp[1]=max(2,7)=7
      dp[2]=max(7, 2+9)=11
      dp[3]=max(11, 7+3)=11
      dp[4]=max(11, 11+1)=12
    Answer: 12 ✓

    Time: O(n), Space: O(1) — rolling two variables.
    """
    if not nums: return 0
    if len(nums) == 1: return nums[0]
    prev2, prev1 = nums[0], max(nums[0], nums[1])
    for i in range(2, len(nums)):
        prev2, prev1 = prev1, max(prev1, prev2 + nums[i])
    return prev1


def house_robber_ii(nums: list) -> int:
    """
    LeetCode #213
    Houses arranged in a circle. First and last are adjacent.

    Examples:
      house_robber_ii([2,3,2]) → 3   (can't rob 2+2=4 because adjacent via circle; rob just 3)
      house_robber_ii([1,2,3,1]) → 4  (rob 1,3 — not adjacent in circle? 1 and 3: adjacent? No! 1-2-3-1(circle))
        Wait: [1,2,3,1]: indices 0,1,2,3. In circle: 3 is adjacent to 0.
        Rob 0 and 2: 1+3=4. Indices 0 and 2 not adjacent. ✓ → 4.
      house_robber_ii([1,2,3]) → 3
      house_robber_ii([1]) → 1

    Key insight: Either rob house 0 (must skip house n-1) OR skip house 0 (can rob house n-1).
    Run house_robber I on [0..n-2] and on [1..n-1], take max.
    """
    def rob_linear(houses):
        if not houses: return 0
        if len(houses) == 1: return houses[0]
        prev2, prev1 = houses[0], max(houses[0], houses[1])
        for i in range(2, len(houses)):
            prev2, prev1 = prev1, max(prev1, prev2 + houses[i])
        return prev1

    if len(nums) == 1:
        return nums[0]
    return max(rob_linear(nums[:-1]), rob_linear(nums[1:]))


def longest_increasing_subsequence(nums: list) -> int:
    """
    LeetCode #300
    Length of longest strictly increasing subsequence (not necessarily contiguous).

    Examples:
      longest_increasing_subsequence([10,9,2,5,3,7,101,18]) → 4  ([2,3,7,101] or [2,5,7,101])
      longest_increasing_subsequence([0,1,0,3,2,3]) → 4  ([0,1,2,3])
      longest_increasing_subsequence([7,7,7,7,7]) → 1  (all same, need STRICTLY increasing)
      longest_increasing_subsequence([1]) → 1
      longest_increasing_subsequence([1,2,3,4,5]) → 5  (whole array)
      longest_increasing_subsequence([5,4,3,2,1]) → 1  (strictly decreasing)

    Approach A: O(n²) DP.
      dp[i] = length of LIS ending at index i.
      dp[i] = max(dp[j]+1) for all j<i where nums[j]<nums[i].

    Walk-through [10,9,2,5,3,7,101,18]:
      dp=[1,1,1,1,1,1,1,1]
      i=1: 9<10? No. dp[1]=1.
      i=2: 2<10? No(2<10 but we need nums[j]<nums[i]). 2<9? No. dp[2]=1.
      Wait: dp[j]+1 when nums[j]<nums[i].
      i=3: nums[3]=5. j=0:10<5?No. j=1:9<5?No. j=2:2<5?Yes→dp[3]=max(1,1+1)=2. dp[3]=2.
      i=4: nums[4]=3. j=2:2<3?Yes→dp[4]=2. dp[4]=2.
      i=5: nums[5]=7. j=2:2<7→2, j=3:5<7→3, j=4:3<7→3. dp[5]=3.
      i=6: nums[6]=101. All smaller. dp[6]=dp[5]+1=4.
      i=7: nums[7]=18. 2<18,5<18,3<18,7<18. Max dp among those +1 = 3+1=4. dp[7]=4.
    Answer: 4 ✓

    Approach B: O(n log n) with patience sorting (binary search on tails array).
    """
    if not nums: return 0
    n = len(nums)
    dp = [1] * n
    for i in range(1, n):
        for j in range(i):
            if nums[j] < nums[i]:
                dp[i] = max(dp[i], dp[j] + 1)
    return max(dp)


def coin_change(coins: list, amount: int) -> int:
    """
    LeetCode #322
    Fewest number of coins to make amount. Return -1 if impossible.

    Examples:
      coin_change([1,2,5], 11) → 3  (5+5+1)
      coin_change([2], 3)      → -1 (impossible)
      coin_change([1], 0)      → 0  (zero coins for amount 0)
      coin_change([1], 1)      → 1
      coin_change([1,2,5], 0)  → 0
      coin_change([186,419,83,408], 6249) → 20

    Recurrence: dp[i] = min coins to make amount i.
      dp[0] = 0 (base case: 0 coins for amount 0)
      dp[i] = 1 + min(dp[i-c]) for each coin c where i >= c

    Walk-through coins=[1,2,5], amount=11:
      dp = [0, inf, inf, ..., inf]  (size 12)
      dp[1] = 1 + min(dp[0]) = 1+0 = 1
      dp[2] = 1 + min(dp[1], dp[0]) = 1+0 = 1   (use coin 2)
      dp[3] = 1 + min(dp[2], dp[1]) = 1+1 = 2   (coins 2+1)
      dp[4] = 1 + min(dp[3], dp[2]) = 1+1 = 2   (2+2)
      dp[5] = 1 + min(dp[4], dp[3], dp[0]) = 1+0 = 1  (use coin 5)
      dp[6] = 1 + min(dp[5]) = 2
      ...
      dp[10] = 1 + min(dp[9], dp[8], dp[5]) = 1 + min(2,2,1) = 2
      dp[11] = 1 + min(dp[10], dp[9], dp[6]) = 1 + min(2,2,2) = 3? Wait...
        dp[10]=2, dp[9]=2, dp[6]=2. min=2 → dp[11]=3 ✓

    Time: O(amount × n_coins), Space: O(amount)
    """
    dp = [float('inf')] * (amount + 1)
    dp[0] = 0
    for i in range(1, amount + 1):
        for c in coins:
            if c <= i:
                dp[i] = min(dp[i], 1 + dp[i - c])
    return dp[amount] if dp[amount] != float('inf') else -1


# ══════════════════════════════════════════════════════════════════════════════
# 2D DP
# ══════════════════════════════════════════════════════════════════════════════

def unique_paths(m: int, n: int) -> int:
    """
    LeetCode #62
    Robot on m×n grid. Start top-left, reach bottom-right. Only move right or down.
    How many unique paths?

    Examples:
      unique_paths(3,7) → 28
      unique_paths(3,2) → 3
        Right,Down,Down
        Down,Right,Down
        Down,Down,Right
      unique_paths(1,1) → 1  (already there)
      unique_paths(3,3) → 6

    Recurrence: dp[i][j] = dp[i-1][j] + dp[i][j-1]
    (came from above or from left)

    DP table for 3×3:
      Row 0: [1, 1, 1]  (only one way to reach any cell in top row: go right)
      Row 1: [1, 2, 3]  (dp[1][1]=dp[0][1]+dp[1][0]=1+1=2)
      Row 2: [1, 3, 6]  (dp[2][2]=dp[1][2]+dp[2][1]=3+3=6)
    Answer: 6 ✓

    Mathematical: C(m+n-2, m-1) combinations.

    Time: O(m×n), Space: O(n) with 1D rolling array.
    """
    dp = [1] * n
    for i in range(1, m):
        for j in range(1, n):
            dp[j] += dp[j - 1]
    return dp[-1]


def longest_common_subsequence(text1: str, text2: str) -> int:
    """
    LeetCode #1143
    LCS: longest subsequence present in both strings (chars don't need to be contiguous).

    Examples:
      longest_common_subsequence("abcde", "ace") → 3  ("ace")
      longest_common_subsequence("abc", "abc")   → 3  ("abc")
      longest_common_subsequence("abc", "def")   → 0  (nothing in common)
      longest_common_subsequence("bsbininm", "jmjkbkjkv") → 1  ("b" or "j"?)
        Actually: "b" ∈ both → LCS="b" → 1
      longest_common_subsequence("oxcpqrsvwf", "shmtulqrypy") → 2  ("qr" or "ry")

    Recurrence:
      dp[i][j] = LCS length of text1[:i] and text2[:j]
      If text1[i-1] == text2[j-1]: dp[i][j] = dp[i-1][j-1] + 1
      Else: dp[i][j] = max(dp[i-1][j], dp[i][j-1])

    DP table for "abcde", "ace":
          ""  a  c  e
      ""  [0, 0, 0, 0]
      a   [0, 1, 1, 1]
      b   [0, 1, 1, 1]
      c   [0, 1, 2, 2]
      d   [0, 1, 2, 2]
      e   [0, 1, 2, 3]  ← answer

    Time: O(m×n), Space: O(min(m,n)) with rolling row.
    """
    m, n = len(text1), len(text2)
    if m < n:
        text1, text2 = text2, text1
        m, n = n, m
    prev = [0] * (n + 1)
    for i in range(1, m + 1):
        curr = [0] * (n + 1)
        for j in range(1, n + 1):
            if text1[i-1] == text2[j-1]:
                curr[j] = prev[j-1] + 1
            else:
                curr[j] = max(prev[j], curr[j-1])
        prev = curr
    return prev[n]


def edit_distance(word1: str, word2: str) -> int:
    """
    LeetCode #72
    Minimum operations (insert, delete, replace) to transform word1 to word2.

    Examples:
      edit_distance("horse", "ros") → 3
        horse → rorse (replace h→r)
        rorse → rose  (delete r)
        rose  → ros   (delete e)
      edit_distance("intention", "execution") → 5
      edit_distance("", "abc") → 3  (3 insertions)
      edit_distance("abc", "") → 3  (3 deletions)
      edit_distance("abc", "abc") → 0

    Recurrence: dp[i][j] = edit distance of word1[:i] and word2[:j]
      If word1[i-1] == word2[j-1]: dp[i][j] = dp[i-1][j-1]  (no op needed)
      Else: dp[i][j] = 1 + min(
          dp[i-1][j],    # delete from word1
          dp[i][j-1],    # insert into word1 (= delete from word2)
          dp[i-1][j-1]   # replace
      )

    DP table for "horse", "ros":
            ""  r  o  s
      ""  [0,  1, 2, 3]
      h   [1,  1, 2, 3]
      o   [2,  2, 1, 2]
      r   [3,  2, 2, 2]
      s   [4,  3, 3, 2]
      e   [5,  4, 4, 3]  ← answer

    Time: O(m×n), Space: O(min(m,n)) rolling row.
    """
    m, n = len(word1), len(word2)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp = dp[j]
            if word1[i-1] == word2[j-1]:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j-1])
            prev = temp
    return dp[n]


def zero_one_knapsack(weights: list, values: list, capacity: int) -> int:
    """
    Classic 0/1 Knapsack
    Each item can be taken at most once. Maximize value within capacity.

    Examples:
      zero_one_knapsack([1,3,4,5], [1,4,5,7], 7) → 9  (items 2+3: weight=3+4=7, value=4+5=9)
      zero_one_knapsack([2,3,4,5], [3,4,5,6], 5) → 7  (items 1+2: weight=2+3=5, value=3+4=7)
      zero_one_knapsack([1,2,3], [6,10,12], 5)   → 22  (items 2+3: weight=2+3=5, value=10+12=22)
      zero_one_knapsack([], [], 10) → 0

    Recurrence:
      dp[j] = max value with capacity j
      For each item i (in order), for j from capacity down to weight[i]:
        dp[j] = max(dp[j], dp[j - weight[i]] + value[i])

    Walk-through weights=[1,3,4,5], values=[1,4,5,7], capacity=7:
      dp = [0,0,0,0,0,0,0,0]  (size 8)

      Item 0 (w=1, v=1): j from 7 down to 1:
        dp[7]=max(0,dp[6]+1)=1, dp[6]=1,...dp[1]=1
        dp = [0,1,1,1,1,1,1,1]

      Item 1 (w=3, v=4): j from 7 down to 3:
        dp[7]=max(1,dp[4]+4)=max(1,5)=5
        dp[6]=max(1,dp[3]+4)=max(1,5)=5
        dp[5]=max(1,dp[2]+4)=max(1,5)=5
        dp[4]=max(1,dp[1]+4)=5
        dp[3]=max(1,dp[0]+4)=4
        dp = [0,1,1,4,5,5,5,5]

      Item 2 (w=4, v=5): j from 7 down to 4:
        dp[7]=max(5,dp[3]+5)=max(5,9)=9
        dp[6]=max(5,dp[2]+5)=max(5,6)=6
        dp[5]=max(5,dp[1]+5)=max(5,6)=6
        dp[4]=max(5,dp[0]+5)=5
        dp = [0,1,1,4,5,6,6,9]

      Item 3 (w=5, v=7): j from 7 down to 5:
        dp[7]=max(9,dp[2]+7)=max(9,8)=9
        dp[6]=max(6,dp[1]+7)=max(6,8)=8
        dp[5]=max(6,dp[0]+7)=7
        dp = [0,1,1,4,5,7,8,9]

    Answer: dp[7] = 9 ✓

    Time: O(n × capacity), Space: O(capacity)
    """
    n = len(weights)
    dp = [0] * (capacity + 1)
    for i in range(n):
        for j in range(capacity, weights[i] - 1, -1):   # iterate backward to prevent reuse
            dp[j] = max(dp[j], dp[j - weights[i]] + values[i])
    return dp[capacity]


def word_break(s: str, word_dict: list) -> bool:
    """
    LeetCode #139
    Can s be segmented into words from word_dict?

    Examples:
      word_break("leetcode", ["leet","code"]) → True  ("leet"+"code")
      word_break("applepenapple", ["apple","pen"]) → True
      word_break("catsandog", ["cats","dog","sand","and","cat"]) → False
      word_break("a", ["b"]) → False
      word_break("", ["leet"]) → True  (empty string trivially segmented)
      word_break("aaaaaaa", ["aaaa","aa","a"]) → True

    Recurrence: dp[i] = True if s[:i] can be segmented.
      dp[0] = True (empty prefix)
      dp[i] = OR over all j < i: dp[j] AND s[j:i] in word_set

    Walk-through "leetcode", ["leet","code"]:
      word_set={"leet","code"}, dp=[T,F,F,F,F,F,F,F,F]
      i=1: j=0: dp[0]=T, s[0:1]="l" not in set. dp[1]=F.
      i=2: j=0: "le"?No. j=1: dp[1]=F. dp[2]=F.
      i=3: similarly F.
      i=4: j=0: dp[0]=T, s[0:4]="leet" ✓ → dp[4]=T!
      i=5: j=0:"leetc"?No. j=4:dp[4]=T,"c"?No. dp[5]=F.
      i=6: j=4: dp[4]=T, "co"?No. dp[6]=F.
      i=7: j=4: dp[4]=T, "cod"?No. dp[7]=F.
      i=8: j=4: dp[4]=T, "code" ✓ → dp[8]=T!
    Answer: dp[8]=True ✓

    Time: O(n²), Space: O(n)
    """
    word_set = set(word_dict)
    n = len(s)
    dp = [False] * (n + 1)
    dp[0] = True
    for i in range(1, n + 1):
        for j in range(i):
            if dp[j] and s[j:i] in word_set:
                dp[i] = True
                break
    return dp[n]


def partition_equal_subset_sum(nums: list) -> bool:
    """
    LeetCode #416
    Can array be partitioned into two subsets with equal sum?

    Examples:
      partition_equal_subset_sum([1,5,11,5]) → True  ([1,5,5] and [11])
      partition_equal_subset_sum([1,2,3,5])  → False
      partition_equal_subset_sum([1,1])       → True  ([1] and [1])
      partition_equal_subset_sum([2,2,1,1])  → True
      partition_equal_subset_sum([1,2])       → False

    Key insight: total sum must be even (else impossible).
    Find subset with sum = total/2. This is 0/1 knapsack subset problem.

    dp[j] = True if subset with sum j is achievable.
    For each num, update dp backward (to avoid reuse).
    """
    total = sum(nums)
    if total % 2 != 0:
        return False
    target = total // 2
    dp = [False] * (target + 1)
    dp[0] = True
    for num in nums:
        for j in range(target, num - 1, -1):
            dp[j] = dp[j] or dp[j - num]
    return dp[target]


# ══════════════════════════════════════════════════════════════════════════════
# TESTS
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    assert climbing_stairs(1) == 1
    assert climbing_stairs(2) == 2
    assert climbing_stairs(3) == 3
    assert climbing_stairs(10) == 89
    print("✓ climbing_stairs")

    assert house_robber([1,2,3,1]) == 4
    assert house_robber([2,7,9,3,1]) == 12
    assert house_robber([1]) == 1
    print("✓ house_robber")

    assert house_robber_ii([2,3,2]) == 3
    assert house_robber_ii([1,2,3,1]) == 4
    print("✓ house_robber_ii")

    assert longest_increasing_subsequence([10,9,2,5,3,7,101,18]) == 4
    assert longest_increasing_subsequence([7,7,7,7,7]) == 1
    assert longest_increasing_subsequence([1,2,3,4,5]) == 5
    print("✓ longest_increasing_subsequence")

    assert coin_change([1,2,5], 11) == 3
    assert coin_change([2], 3) == -1
    assert coin_change([1], 0) == 0
    print("✓ coin_change")

    assert unique_paths(3, 7) == 28
    assert unique_paths(3, 2) == 3
    assert unique_paths(1, 1) == 1
    print("✓ unique_paths")

    assert longest_common_subsequence("abcde", "ace") == 3
    assert longest_common_subsequence("abc", "abc") == 3
    assert longest_common_subsequence("abc", "def") == 0
    print("✓ longest_common_subsequence")

    assert edit_distance("horse", "ros") == 3
    assert edit_distance("", "abc") == 3
    assert edit_distance("abc", "abc") == 0
    print("✓ edit_distance")

    assert zero_one_knapsack([1,3,4,5], [1,4,5,7], 7) == 9
    assert zero_one_knapsack([1,2,3], [6,10,12], 5) == 22
    print("✓ zero_one_knapsack")

    assert word_break("leetcode", ["leet","code"]) == True
    assert word_break("catsandog", ["cats","dog","sand","and","cat"]) == False
    print("✓ word_break")

    assert partition_equal_subset_sum([1,5,11,5]) == True
    assert partition_equal_subset_sum([1,2,3,5]) == False
    print("✓ partition_equal_subset_sum")

    print("\n🎉 All DP tests passed!")

# Advanced DP — Google Level

## Patterns Covered
1. Interval DP
2. Bitmask DP
3. Digit DP
4. DP on Trees
5. 2D DP (advanced)
6. DP + Binary Search (patience sorting, LIS)

---

## 1. Interval DP

**Pattern:** Problem on subarrays/substrings where you split into two parts.
`dp[i][j]` = answer for range [i, j]
Fill by increasing interval length.

```python
# Matrix Chain Multiplication
def matrix_chain(dims):
    """dims[i] = rows of matrix i, dims[i+1] = cols"""
    n = len(dims) - 1
    dp = [[0]*n for _ in range(n)]

    for length in range(2, n+1):         # interval length
        for i in range(n - length + 1):
            j = i + length - 1
            dp[i][j] = float('inf')
            for k in range(i, j):
                cost = dp[i][k] + dp[k+1][j] + dims[i]*dims[k+1]*dims[j+1]
                dp[i][j] = min(dp[i][j], cost)

    return dp[0][n-1]

# Burst Balloons (Google classic)
def max_coins(nums):
    nums = [1] + nums + [1]
    n = len(nums)
    dp = [[0]*n for _ in range(n)]

    for length in range(2, n):
        for left in range(n - length):
            right = left + length
            for k in range(left+1, right):
                coins = nums[left]*nums[k]*nums[right]
                dp[left][right] = max(dp[left][right],
                                      dp[left][k] + coins + dp[k][right])
    return dp[0][n-1]

# Palindrome Partitioning II — min cuts
def min_cut(s):
    n = len(s)
    # is_pal[i][j] = True if s[i..j] is palindrome
    is_pal = [[False]*n for _ in range(n)]
    for i in range(n-1, -1, -1):
        for j in range(i, n):
            if s[i] == s[j] and (j-i <= 2 or is_pal[i+1][j-1]):
                is_pal[i][j] = True

    dp = list(range(n))  # dp[i] = min cuts for s[0..i]
    for i in range(1, n):
        if is_pal[0][i]:
            dp[i] = 0
            continue
        for j in range(1, i+1):
            if is_pal[j][i]:
                dp[i] = min(dp[i], dp[j-1] + 1)
    return dp[n-1]
```

---

## 2. Bitmask DP

**Pattern:** State includes a set of items represented as a bitmask.
Use when: n ≤ 20, "cover all elements", "travelling salesman", "assignment problems"

```python
# Travelling Salesman Problem (TSP)
def tsp(dist):
    n = len(dist)
    # dp[mask][i] = min cost to visit all nodes in mask, ending at i
    dp = [[float('inf')]*n for _ in range(1 << n)]
    dp[1][0] = 0  # start at node 0, visited = {0}

    for mask in range(1 << n):
        for u in range(n):
            if dp[mask][u] == float('inf'):
                continue
            if not (mask >> u & 1):  # u not in mask
                continue
            for v in range(n):
                if mask >> v & 1:    # v already visited
                    continue
                new_mask = mask | (1 << v)
                dp[new_mask][v] = min(dp[new_mask][v], dp[mask][u] + dist[u][v])

    # Return to start
    full = (1 << n) - 1
    return min(dp[full][i] + dist[i][0] for i in range(n))

# Minimum number of people to cover all skills
def smallest_sufficient_team(req_skills, people):
    skill_idx = {s: i for i, s in enumerate(req_skills)}
    m = len(req_skills)
    full = (1 << m) - 1
    dp = [None] * (1 << m)
    dp[0] = []

    for i, skills in enumerate(people):
        mask = 0
        for s in skills:
            if s in skill_idx:
                mask |= (1 << skill_idx[s])

        for prev_mask in range(len(dp)):
            if dp[prev_mask] is None:
                continue
            new_mask = prev_mask | mask
            if dp[new_mask] is None or len(dp[new_mask]) > len(dp[prev_mask]) + 1:
                dp[new_mask] = dp[prev_mask] + [i]

    return dp[full]
```

---

## 3. LIS (Longest Increasing Subsequence) — O(n log n)

```python
import bisect

def length_of_LIS(nums):
    # tails[i] = smallest tail element of IS of length i+1
    tails = []

    for num in nums:
        pos = bisect.bisect_left(tails, num)
        if pos == len(tails):
            tails.append(num)
        else:
            tails[pos] = num

    return len(tails)

# Patience sorting insight:
# tails is always sorted; binary search finds insertion point
# Time: O(n log n)  Space: O(n)

# Reconstruct actual LIS
def find_LIS(nums):
    n = len(nums)
    dp = [1]*n
    parent = [-1]*n

    for i in range(1, n):
        for j in range(i):
            if nums[j] < nums[i] and dp[j]+1 > dp[i]:
                dp[i] = dp[j]+1
                parent[i] = j

    max_len = max(dp)
    idx = dp.index(max_len)
    path = []
    while idx != -1:
        path.append(nums[idx])
        idx = parent[idx]
    return path[::-1]
```

---

## 4. DP on Trees

```python
# Diameter of Binary Tree
def diameter(root):
    result = [0]

    def dfs(node):
        if not node:
            return 0
        left = dfs(node.left)
        right = dfs(node.right)
        result[0] = max(result[0], left + right)
        return 1 + max(left, right)

    dfs(root)
    return result[0]

# House Robber III (rob tree nodes, no adjacent)
def rob_tree(root):
    def dfs(node):
        if not node:
            return (0, 0)  # (rob this node, skip this node)

        left_rob, left_skip = dfs(node.left)
        right_rob, right_skip = dfs(node.right)

        rob = node.val + left_skip + right_skip
        skip = max(left_rob, left_skip) + max(right_rob, right_skip)
        return (rob, skip)

    return max(dfs(root))

# Binary Tree Max Path Sum
def max_path_sum(root):
    result = [float('-inf')]

    def dfs(node):
        if not node:
            return 0
        left = max(dfs(node.left), 0)   # ignore negative branches
        right = max(dfs(node.right), 0)
        result[0] = max(result[0], node.val + left + right)
        return node.val + max(left, right)   # can only go one direction up

    dfs(root)
    return result[0]
```

---

## 5. Edit Distance (Classic 2D DP)

```python
def edit_distance(word1, word2):
    m, n = len(word1), len(word2)
    dp = [[0]*(n+1) for _ in range(m+1)]

    for i in range(m+1): dp[i][0] = i
    for j in range(n+1): dp[0][j] = j

    for i in range(1, m+1):
        for j in range(1, n+1):
            if word1[i-1] == word2[j-1]:
                dp[i][j] = dp[i-1][j-1]
            else:
                dp[i][j] = 1 + min(dp[i-1][j],    # delete
                                    dp[i][j-1],    # insert
                                    dp[i-1][j-1])  # replace
    return dp[m][n]
```

---

## Google Problem Table

| Problem | DP Type | Difficulty |
|---------|---------|------------|
| Burst Balloons | Interval DP | Hard |
| Strange Printer | Interval DP | Hard |
| Travelling Salesman | Bitmask DP | Hard |
| Partition to K Equal Subsets | Bitmask DP | Medium |
| Smallest Sufficient Team | Bitmask DP | Hard |
| LIS O(n log n) | DP + binary search | Medium |
| Russian Doll Envelopes | 2D LIS | Hard |
| Edit Distance | 2D DP | Medium |
| Palindrome Partition II | Interval DP | Hard |
| Binary Tree Max Path Sum | Tree DP | Hard |
| House Robber III | Tree DP | Medium |
| Regular Expression Matching | 2D DP | Hard |

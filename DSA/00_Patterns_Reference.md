# DSA Patterns Reference — When to Use What
## The #1 Skill in MAANG Interviews: Pattern Recognition

Read this before every practice session. The goal is: hear a problem → pattern fires in 30 seconds.

---

## Pattern 1: Sliding Window

**Signal words:** "contiguous subarray/substring", "maximum/minimum sum of size k", "longest substring with", "at most k distinct"

**Template — Fixed window (size k):**
```python
def fixed_window(arr, k):
    window_sum = sum(arr[:k])
    best = window_sum
    for i in range(k, len(arr)):
        window_sum += arr[i] - arr[i - k]   # slide: add right, remove left
        best = max(best, window_sum)
    return best
```

**Template — Variable window (expand right, shrink left on condition):**
```python
def variable_window(s):
    left = 0
    state = {}   # window state (counts, sums, etc.)
    best = 0
    for right in range(len(s)):
        # ADD s[right] to window state
        state[s[right]] = state.get(s[right], 0) + 1

        while WINDOW_INVALID(state):    # shrink until valid
            state[s[left]] -= 1
            if state[s[left]] == 0: del state[s[left]]
            left += 1

        best = max(best, right - left + 1)
    return best
```

**Problems:** Max sum subarray of size k, Longest substring without repeating chars, Minimum window substring, Fruits into baskets, Longest substring with at most k distinct, Max consecutive 1s after flipping k zeros.

---

## Pattern 2: Two Pointers

**Signal words:** Sorted array, pair sum, palindrome, Dutch flag, remove duplicates, "sorted" + O(n).

**Template — Opposite ends:**
```python
def two_sum_sorted(arr, target):
    lo, hi = 0, len(arr) - 1
    while lo < hi:
        s = arr[lo] + arr[hi]
        if s == target: return [lo, hi]
        elif s < target: lo += 1    # need bigger sum
        else: hi -= 1               # need smaller sum
    return []
```

**Template — Same direction (fast/slow):**
```python
def remove_duplicates(arr):
    if not arr: return 0
    slow = 0
    for fast in range(1, len(arr)):
        if arr[fast] != arr[slow]:
            slow += 1
            arr[slow] = arr[fast]
    return slow + 1
```

**Problems:** Two Sum II (sorted), 3Sum, 4Sum, Container with most water, Trapping rain water, Remove duplicates, Remove nth node from end (linked list), Valid palindrome.

---

## Pattern 3: Binary Search

**Signal words:** Sorted array, "find minimum/maximum such that condition holds", "search in rotated", O(log n) required.

**Template — Classic:**
```python
def binary_search(arr, target):
    lo, hi = 0, len(arr) - 1
    while lo <= hi:
        mid = lo + (hi - lo) // 2   # avoid overflow (Python doesn't overflow but good habit)
        if arr[mid] == target: return mid
        elif arr[mid] < target: lo = mid + 1
        else: hi = mid - 1
    return -1
```

**Template — Find leftmost position (lower bound):**
```python
def lower_bound(arr, target):
    lo, hi = 0, len(arr)
    while lo < hi:
        mid = (lo + hi) // 2
        if arr[mid] < target: lo = mid + 1
        else: hi = mid              # keep hi at mid (could be answer)
    return lo   # first position where arr[lo] >= target
```

**Template — Minimize/Maximize on answer space:**
```python
def min_capacity(weights, days):
    def can_ship(capacity):
        current, d = 0, 1
        for w in weights:
            if current + w > capacity: d += 1; current = 0
            current += w
        return d <= days

    lo, hi = max(weights), sum(weights)
    while lo < hi:
        mid = (lo + hi) // 2
        if can_ship(mid): hi = mid      # mid works, try smaller
        else: lo = mid + 1              # too small, go bigger
    return lo
```

**Problems:** Binary search, Search in rotated sorted array, Find minimum in rotated sorted array, Search 2D matrix, Find peak element, Koko eating bananas, Minimum capacity to ship packages, Split array largest sum.

---

## Pattern 4: HashMap / HashSet

**Signal words:** "two sum", "frequency count", "seen before", "anagram", "group by", O(1) lookup.

**Template — Count frequencies:**
```python
from collections import Counter, defaultdict

freq = Counter(arr)                     # {element: count}
groups = defaultdict(list)              # {key: [items]}
seen = set()                            # O(1) existence check
```

**Template — Prefix sum + HashMap:**
```python
def subarray_sum_k(nums, k):
    prefix_count = {0: 1}   # prefix_sum → count of times seen
    total, prefix = 0, 0
    for n in nums:
        prefix += n
        total += prefix_count.get(prefix - k, 0)
        prefix_count[prefix] = prefix_count.get(prefix, 0) + 1
    return total
```

**Problems:** Two Sum, Group Anagrams, Top K frequent elements, Longest consecutive sequence, Subarray sum equals k, Longest subarray with sum k, Valid anagram, Contains duplicate.

---

## Pattern 5: Stack (LIFO / Monotonic)

**Signal words:** "nearest greater/smaller", "valid parentheses", "next greater element", "largest rectangle", "daily temperatures".

**Template — Monotonic decreasing (find next greater element):**
```python
def next_greater(arr):
    result = [-1] * len(arr)
    stack = []   # indices, maintaining arr[stack] in decreasing order
    for i, val in enumerate(arr):
        while stack and arr[stack[-1]] < val:
            idx = stack.pop()
            result[idx] = val   # val is the next greater for idx
        stack.append(i)
    return result
```

**Template — Parentheses validation:**
```python
def is_valid(s):
    stack = []
    pairs = {')': '(', '}': '{', ']': '['}
    for c in s:
        if c in '({[': stack.append(c)
        elif not stack or stack[-1] != pairs[c]: return False
        else: stack.pop()
    return not stack
```

**Problems:** Valid parentheses, Min stack, Daily temperatures, Next greater element I/II, Largest rectangle in histogram, Trapping rain water (stack approach), Remove k digits, Car fleet.

---

## Pattern 6: Heap / Priority Queue

**Signal words:** "K largest", "K smallest", "K-th", "merge K sorted", "top K frequent", continuous stream.

**Template — K largest elements:**
```python
import heapq

def k_largest(nums, k):
    heap = []   # min-heap of size k
    for n in nums:
        heapq.heappush(heap, n)
        if len(heap) > k:
            heapq.heappop(heap)   # evict smallest
    return list(heap)   # k largest remain
```

**Template — K-way merge:**
```python
def merge_k_sorted(lists):
    heap = []   # (value, list_index, element_index)
    for i, lst in enumerate(lists):
        if lst:
            heapq.heappush(heap, (lst[0], i, 0))
    result = []
    while heap:
        val, i, j = heapq.heappop(heap)
        result.append(val)
        if j + 1 < len(lists[i]):
            heapq.heappush(heap, (lists[i][j+1], i, j+1))
    return result
```

**Problems:** Kth largest element, Top K frequent, K closest points, Merge K sorted lists, Find median from data stream, Task scheduler, Meeting rooms II, Reorganise string.

---

## Pattern 7: Tree DFS / BFS

**Template — DFS (recursive):**
```python
def dfs(node):
    if not node: return BASE_CASE
    left  = dfs(node.left)
    right = dfs(node.right)
    return COMBINE(left, right, node.val)
```

**Template — BFS (level order):**
```python
from collections import deque

def bfs(root):
    if not root: return []
    queue = deque([root])
    result = []
    while queue:
        level_size = len(queue)
        level = []
        for _ in range(level_size):
            node = queue.popleft()
            level.append(node.val)
            if node.left:  queue.append(node.left)
            if node.right: queue.append(node.right)
        result.append(level)
    return result
```

**Template — Iterative DFS (avoids recursion stack overflow):**
```python
def dfs_iterative(root):
    stack = [root]
    while stack:
        node = stack.pop()
        if not node: continue
        # process node
        stack.append(node.right)
        stack.append(node.left)   # left on top → processed first
```

**Problems:** Max depth, Min depth, Diameter, Same tree, Symmetric tree, Path sum, Max path sum, LCA, Serialize/deserialize, Invert binary tree, Count good nodes, Level order traversal, Zigzag traversal, Right side view.

---

## Pattern 8: Graph BFS / DFS

**Template — BFS for shortest path:**
```python
from collections import deque

def bfs_shortest(graph, start, end):
    queue = deque([(start, 0)])   # (node, distance)
    visited = {start}
    while queue:
        node, dist = queue.popleft()
        if node == end: return dist
        for nb in graph[node]:
            if nb not in visited:
                visited.add(nb)
                queue.append((nb, dist + 1))
    return -1
```

**Template — DFS with cycle detection:**
```python
def has_cycle(graph, n):
    color = [0] * n   # 0=unvisited, 1=in-progress, 2=done
    def dfs(node):
        color[node] = 1
        for nb in graph[node]:
            if color[nb] == 1: return True    # back edge = cycle
            if color[nb] == 0 and dfs(nb): return True
        color[node] = 2
        return False
    return any(dfs(i) for i in range(n) if color[i] == 0)
```

**Template — Union-Find (Disjoint Set):**
```python
class UnionFind:
    def __init__(self, n):
        self.parent = list(range(n))
        self.rank   = [0] * n

    def find(self, x):
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])   # path compression
        return self.parent[x]

    def union(self, x, y):
        px, py = self.find(x), self.find(y)
        if px == py: return False
        if self.rank[px] < self.rank[py]: px, py = py, px
        self.parent[py] = px
        if self.rank[px] == self.rank[py]: self.rank[px] += 1
        return True
```

**Problems:** Number of islands, Clone graph, Rotting oranges, Pacific Atlantic water flow, Course schedule I/II, Word ladder, Walls and gates, Alien dictionary, Redundant connection, Number of provinces.

---

## Pattern 9: Dynamic Programming

**Signal words:** "maximum / minimum", "number of ways", "can you reach", "optimal substructure".

**Recognition checklist:**
1. Can the problem be broken into subproblems?
2. Do subproblems overlap (same subproblem computed multiple times)?
3. Is there an optimal substructure? (optimal solution uses optimal subproblems)
If all 3: DP.

**Template — 1D DP:**
```python
def climb_stairs(n):
    if n <= 2: return n
    dp = [0] * (n + 1)
    dp[1], dp[2] = 1, 2
    for i in range(3, n + 1):
        dp[i] = dp[i-1] + dp[i-2]
    return dp[n]
```

**Template — 2D DP:**
```python
def longest_common_subsequence(s1, s2):
    m, n = len(s1), len(s2)
    dp = [[0] * (n+1) for _ in range(m+1)]
    for i in range(1, m+1):
        for j in range(1, n+1):
            if s1[i-1] == s2[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])
    return dp[m][n]
```

**Template — Space optimised (rolling row):**
```python
def lcs_space_opt(s1, s2):
    m, n = len(s1), len(s2)
    prev = [0] * (n + 1)
    for i in range(1, m+1):
        curr = [0] * (n + 1)
        for j in range(1, n+1):
            curr[j] = prev[j-1]+1 if s1[i-1]==s2[j-1] else max(prev[j], curr[j-1])
        prev = curr
    return prev[n]
```

**Problems:** Climbing stairs, House robber I/II, Longest increasing subsequence, Coin change, Unique paths, Edit distance, LCS, 0/1 Knapsack, Partition equal subset sum, Word break, Decode ways, Jump game.

---

## Pattern 10: Backtracking

**Signal words:** "all combinations", "all permutations", "all subsets", "generate all", decision tree.

**Template:**
```python
def backtrack(result, path, choices, start=0):
    if GOAL_MET(path):
        result.append(path[:])   # snapshot of current path
        return
    for i in range(start, len(choices)):
        if SKIP(choices, i): continue           # pruning
        path.append(choices[i])                 # choose
        backtrack(result, path, choices, i+1)   # explore
        path.pop()                              # un-choose

result = []
backtrack(result, [], candidates)
```

**Problems:** Subsets, Subsets II (duplicates), Combinations, Combination sum I/II, Permutations I/II, Palindrome partitioning, Word search, N-Queens, Sudoku solver, Letter combinations of phone number.

---

## Pattern 11: Topological Sort

**Template — Kahn's BFS:**
```python
from collections import deque

def topo_sort(n, prerequisites):
    graph    = [[] for _ in range(n)]
    in_degree = [0] * n
    for u, v in prerequisites:
        graph[v].append(u)
        in_degree[u] += 1
    queue = deque([i for i in range(n) if in_degree[i] == 0])
    order = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for nb in graph[node]:
            in_degree[nb] -= 1
            if in_degree[nb] == 0:
                queue.append(nb)
    return order if len(order) == n else []   # [] = cycle exists
```

**Problems:** Course schedule I/II, Alien dictionary, Sequence reconstruction, Minimum height trees.

---

## Pattern 12: Trie

**Template:**
```python
class TrieNode:
    def __init__(self):
        self.children = {}
        self.is_end   = False

class Trie:
    def __init__(self): self.root = TrieNode()

    def insert(self, word):
        node = self.root
        for c in word:
            if c not in node.children:
                node.children[c] = TrieNode()
            node = node.children[c]
        node.is_end = True

    def search(self, word):
        node = self.root
        for c in word:
            if c not in node.children: return False
            node = node.children[c]
        return node.is_end

    def starts_with(self, prefix):
        node = self.root
        for c in prefix:
            if c not in node.children: return False
            node = node.children[c]
        return True
```

**Problems:** Implement Trie, Word search II, Add and search words (wildcard), Replace words, Design search autocomplete, Word square.

---

## Complexity Reference Table

| Data Structure | Access | Search | Insert | Delete | Space |
|---------------|--------|--------|--------|--------|-------|
| Array | O(1) | O(n) | O(n) | O(n) | O(n) |
| Dynamic Array | O(1) | O(n) | O(1) amort | O(n) | O(n) |
| Linked List | O(n) | O(n) | O(1) | O(1)* | O(n) |
| Hash Map | — | O(1) avg | O(1) avg | O(1) avg | O(n) |
| Binary Search Tree | O(log n) | O(log n) | O(log n) | O(log n) | O(n) |
| Balanced BST (AVL/RB) | O(log n) | O(log n) | O(log n) | O(log n) | O(n) |
| Heap | O(1) top | O(n) | O(log n) | O(log n) | O(n) |
| Trie | O(k)* | O(k)* | O(k)* | O(k)* | O(n×k) |
| Graph (adjacency list) | — | O(V+E) | O(1) | O(E) | O(V+E) |

*k = key length, *with known pointer

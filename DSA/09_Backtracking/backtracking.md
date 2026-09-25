# Backtracking — Google Level

## Mental Model
```
Backtracking = DFS on decision tree
At each step: make a choice → recurse → UNDO the choice
Use when: "all combinations/permutations/subsets", "find one valid solution"
Key: prune early — if current state already invalid, don't recurse deeper
```

## Universal Template

```python
def backtrack(state, choices, result):
    if is_solution(state):
        result.append(list(state))  # collect answer
        return

    for choice in choices:
        if is_valid(choice, state):
            state.append(choice)        # make choice
            backtrack(state, choices, result)
            state.pop()                 # UNDO choice
```

---

## Subsets

```python
def subsets(nums):
    result = []

    def backtrack(start, path):
        result.append(list(path))   # every state is a valid subset
        for i in range(start, len(nums)):
            path.append(nums[i])
            backtrack(i + 1, path)
            path.pop()

    backtrack(0, [])
    return result
# [[], [1], [1,2], [1,2,3], [1,3], [2], [2,3], [3]]

# With duplicates — Subsets II
def subsets_with_dup(nums):
    nums.sort()
    result = []

    def backtrack(start, path):
        result.append(list(path))
        for i in range(start, len(nums)):
            if i > start and nums[i] == nums[i-1]:  # skip duplicate
                continue
            path.append(nums[i])
            backtrack(i + 1, path)
            path.pop()

    backtrack(0, [])
    return result
```

---

## Permutations

```python
def permutations(nums):
    result = []

    def backtrack(path, used):
        if len(path) == len(nums):
            result.append(list(path))
            return
        for i, num in enumerate(nums):
            if not used[i]:
                used[i] = True
                path.append(num)
                backtrack(path, used)
                path.pop()
                used[i] = False

    backtrack([], [False] * len(nums))
    return result

# With duplicates — Permutations II
def permutations_unique(nums):
    nums.sort()
    result = []

    def backtrack(path, used):
        if len(path) == len(nums):
            result.append(list(path))
            return
        for i in range(len(nums)):
            if used[i]:
                continue
            # skip if same value as previous and previous was NOT used
            if i > 0 and nums[i] == nums[i-1] and not used[i-1]:
                continue
            used[i] = True
            path.append(nums[i])
            backtrack(path, used)
            path.pop()
            used[i] = False

    backtrack([], [False] * len(nums))
    return result
```

---

## Combinations

```python
def combination_sum(candidates, target):
    """Unlimited use of each candidate."""
    result = []

    def backtrack(start, path, remaining):
        if remaining == 0:
            result.append(list(path))
            return
        if remaining < 0:
            return  # prune

        for i in range(start, len(candidates)):
            path.append(candidates[i])
            backtrack(i, path, remaining - candidates[i])  # i (not i+1) = reuse
            path.pop()

    backtrack(0, [], target)
    return result

def combine(n, k):
    """All k-size combinations from 1..n."""
    result = []

    def backtrack(start, path):
        if len(path) == k:
            result.append(list(path))
            return
        # Pruning: enough elements remaining?
        for i in range(start, n - (k - len(path)) + 2):
            path.append(i)
            backtrack(i + 1, path)
            path.pop()

    backtrack(1, [])
    return result
```

---

## N-Queens (Google Classic)

```python
def solve_n_queens(n):
    result = []
    cols = set()
    diag1 = set()   # row - col
    diag2 = set()   # row + col

    def backtrack(row, board):
        if row == n:
            result.append([''.join(r) for r in board])
            return

        for col in range(n):
            if col in cols or (row - col) in diag1 or (row + col) in diag2:
                continue  # under attack — prune

            cols.add(col)
            diag1.add(row - col)
            diag2.add(row + col)
            board[row][col] = 'Q'

            backtrack(row + 1, board)

            cols.remove(col)
            diag1.remove(row - col)
            diag2.remove(row + col)
            board[row][col] = '.'

    board = [['.' for _ in range(n)] for _ in range(n)]
    backtrack(0, board)
    return result
```

---

## Sudoku Solver

```python
def solve_sudoku(board):
    def is_valid(board, row, col, num):
        box_r, box_c = 3*(row//3), 3*(col//3)
        for i in range(9):
            if board[row][i] == num: return False
            if board[i][col] == num: return False
            if board[box_r + i//3][box_c + i%3] == num: return False
        return True

    def solve(board):
        for i in range(9):
            for j in range(9):
                if board[i][j] == '.':
                    for num in '123456789':
                        if is_valid(board, i, j, num):
                            board[i][j] = num
                            if solve(board):
                                return True
                            board[i][j] = '.'   # backtrack
                    return False   # no valid num — dead end
        return True   # all cells filled

    solve(board)
```

---

## Word Search in Grid

```python
def word_search(board, word):
    rows, cols = len(board), len(board[0])

    def dfs(r, c, idx):
        if idx == len(word):
            return True
        if not (0 <= r < rows and 0 <= c < cols):
            return False
        if board[r][c] != word[idx]:
            return False

        temp = board[r][c]
        board[r][c] = '#'   # mark visited

        found = any(dfs(r+dr, c+dc, idx+1)
                    for dr, dc in [(0,1),(0,-1),(1,0),(-1,0)])

        board[r][c] = temp  # restore (backtrack)
        return found

    return any(dfs(r, c, 0)
               for r in range(rows)
               for c in range(cols))
```

---

## Google Problem Table

| Problem | Key Insight | Difficulty |
|---------|------------|------------|
| Subsets | Backtrack from index | Medium |
| Subsets II | Sort + skip duplicates | Medium |
| Permutations | Use `used[]` array | Medium |
| Combination Sum | Reuse same element (i not i+1) | Medium |
| N-Queens | Track cols + 2 diagonals | Hard |
| Sudoku Solver | Try 1-9, backtrack on fail | Hard |
| Word Search | DFS on grid, mark visited | Medium |
| Palindrome Partitioning | Check substring before recurse | Medium |
| Generate Parentheses | open < n and close < open | Medium |
| Letter Phone Combinations | Map digit → letters | Medium |

---

## Pruning — The Google Differentiator

```python
# Sort candidates first → prune when candidate > remaining
candidates.sort()
for i in range(start, len(candidates)):
    if candidates[i] > remaining:
        break   # all subsequent are larger too

# Count-based pruning (combine)
for i in range(start, n - (k - len(path)) + 2):
    # ensures enough elements remain to fill path to size k
```

# Graphs — Google Level

## Mental Model
```
Graph = Nodes (vertices) + Edges (connections)
BFS  = level-by-level (queue) → shortest path in unweighted graph
DFS  = go deep first (stack/recursion) → cycle detection, path existence, connected components
```

---

## Representations

```python
# Adjacency List (standard — O(V+E) space)
graph = defaultdict(list)
graph[0].append(1)
graph[1].append(0)  # undirected

# Adjacency Matrix (dense graphs, O(1) edge check, O(V²) space)
matrix = [[0]*n for _ in range(n)]
matrix[0][1] = 1

# Edge list
edges = [(0,1), (1,2), (2,3)]
```

---

## BFS — Template

```python
from collections import deque

def bfs(graph, start):
    visited = set([start])
    queue = deque([start])
    result = []

    while queue:
        node = queue.popleft()
        result.append(node)

        for neighbor in graph[node]:
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)

    return result

# Shortest path BFS (unweighted)
def shortest_path(graph, start, end):
    visited = {start}
    queue = deque([(start, [start])])   # (node, path)

    while queue:
        node, path = queue.popleft()
        if node == end:
            return path
        for nbr in graph[node]:
            if nbr not in visited:
                visited.add(nbr)
                queue.append((nbr, path + [nbr]))
    return []
```

## DFS — Template

```python
# Recursive
def dfs(graph, node, visited=None):
    if visited is None:
        visited = set()
    visited.add(node)
    for neighbor in graph[node]:
        if neighbor not in visited:
            dfs(graph, neighbor, visited)
    return visited

# Iterative (for very deep graphs — avoids recursion limit)
def dfs_iterative(graph, start):
    visited = set()
    stack = [start]
    result = []

    while stack:
        node = stack.pop()
        if node not in visited:
            visited.add(node)
            result.append(node)
            for nbr in graph[node]:   # reversed for same order as recursive
                if nbr not in visited:
                    stack.append(nbr)
    return result
```

---

## Topological Sort (DAG — directed, no cycles)

Used for: build order, course scheduling, dependency resolution.

```python
# Kahn's Algorithm (BFS-based)
def topo_sort_bfs(n, edges):
    """n nodes, edges = [(from, to)]"""
    graph = defaultdict(list)
    indegree = [0] * n

    for u, v in edges:
        graph[u].append(v)
        indegree[v] += 1

    queue = deque([i for i in range(n) if indegree[i] == 0])
    order = []

    while queue:
        node = queue.popleft()
        order.append(node)
        for nbr in graph[node]:
            indegree[nbr] -= 1
            if indegree[nbr] == 0:
                queue.append(nbr)

    return order if len(order) == n else []  # [] means cycle exists

# DFS-based topo sort
def topo_sort_dfs(n, edges):
    graph = defaultdict(list)
    for u, v in edges:
        graph[u].append(v)

    visited = [0] * n  # 0=unvisited, 1=in-stack, 2=done
    result = []
    has_cycle = [False]

    def dfs(node):
        if has_cycle[0]: return
        visited[node] = 1
        for nbr in graph[node]:
            if visited[nbr] == 1:
                has_cycle[0] = True
                return
            if visited[nbr] == 0:
                dfs(nbr)
        visited[node] = 2
        result.append(node)

    for i in range(n):
        if visited[i] == 0:
            dfs(i)

    return [] if has_cycle[0] else result[::-1]
```

---

## Dijkstra — Shortest Path (weighted, no negative edges)

```python
import heapq

def dijkstra(graph, start, n):
    """
    graph: {node: [(neighbor, weight)]}
    Returns: dist[] from start to all nodes
    """
    dist = [float('inf')] * n
    dist[start] = 0
    heap = [(0, start)]   # (cost, node)

    while heap:
        d, node = heapq.heappop(heap)

        if d > dist[node]:   # stale entry — skip
            continue

        for nbr, weight in graph[node]:
            new_dist = dist[node] + weight
            if new_dist < dist[nbr]:
                dist[nbr] = new_dist
                heapq.heappush(heap, (new_dist, nbr))

    return dist

# Time: O((V+E) log V)   Space: O(V)
```

---

## Bellman-Ford — Negative Edges

```python
def bellman_ford(n, edges, start):
    """edges = [(from, to, weight)]"""
    dist = [float('inf')] * n
    dist[start] = 0

    # Relax all edges V-1 times
    for _ in range(n - 1):
        for u, v, w in edges:
            if dist[u] != float('inf') and dist[u] + w < dist[v]:
                dist[v] = dist[u] + w

    # Check for negative cycle
    for u, v, w in edges:
        if dist[u] != float('inf') and dist[u] + w < dist[v]:
            return None  # negative cycle exists

    return dist

# Time: O(VE)   Use when: negative edges present
```

---

## Union-Find (Disjoint Set Union — DSU)

Used for: connected components, cycle detection in undirected graph, Kruskal's MST.

```python
class UnionFind:
    def __init__(self, n):
        self.parent = list(range(n))
        self.rank = [0] * n
        self.components = n

    def find(self, x):
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])  # path compression
        return self.parent[x]

    def union(self, x, y):
        px, py = self.find(x), self.find(y)
        if px == py:
            return False  # already connected — cycle!
        # union by rank
        if self.rank[px] < self.rank[py]:
            px, py = py, px
        self.parent[py] = px
        if self.rank[px] == self.rank[py]:
            self.rank[px] += 1
        self.components -= 1
        return True

    def connected(self, x, y):
        return self.find(x) == self.find(y)
```

---

## Cycle Detection

```python
# Undirected — via DFS with parent tracking
def has_cycle_undirected(graph, n):
    visited = [False] * n

    def dfs(node, parent):
        visited[node] = True
        for nbr in graph[node]:
            if not visited[nbr]:
                if dfs(nbr, node):
                    return True
            elif nbr != parent:
                return True  # back edge = cycle
        return False

    for i in range(n):
        if not visited[i]:
            if dfs(i, -1):
                return True
    return False

# Directed — via DFS with color marking (0=white, 1=grey/in-stack, 2=black/done)
def has_cycle_directed(graph, n):
    color = [0] * n

    def dfs(node):
        color[node] = 1
        for nbr in graph[node]:
            if color[nbr] == 1:
                return True  # back edge = cycle
            if color[nbr] == 0 and dfs(nbr):
                return True
        color[node] = 2
        return False

    return any(color[i] == 0 and dfs(i) for i in range(n))
```

---

## Bipartite Check

```python
def is_bipartite(graph, n):
    color = [-1] * n

    def bfs(start):
        color[start] = 0
        queue = deque([start])
        while queue:
            node = queue.popleft()
            for nbr in graph[node]:
                if color[nbr] == -1:
                    color[nbr] = 1 - color[node]
                    queue.append(nbr)
                elif color[nbr] == color[node]:
                    return False
        return True

    return all(color[i] != -1 or bfs(i) for i in range(n))
```

---

## Flood Fill / Grid BFS (very common at Google)

```python
def num_islands(grid):
    if not grid:
        return 0
    rows, cols = len(grid), len(grid[0])
    count = 0

    def bfs(r, c):
        queue = deque([(r, c)])
        grid[r][c] = '0'  # mark visited
        while queue:
            row, col = queue.popleft()
            for dr, dc in [(0,1),(0,-1),(1,0),(-1,0)]:
                nr, nc = row+dr, col+dc
                if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] == '1':
                    grid[nr][nc] = '0'
                    queue.append((nr, nc))

    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == '1':
                bfs(r, c)
                count += 1
    return count
```

---

## Key Google Problems

| Problem | Algorithm | Difficulty |
|---------|-----------|------------|
| Number of Islands | BFS/DFS | Easy |
| Course Schedule (cycle?) | Topo sort / DFS | Medium |
| Course Schedule II (order) | Kahn's BFS | Medium |
| Shortest Path in Binary Matrix | BFS | Medium |
| Network Delay Time | Dijkstra | Medium |
| Find the Town Judge | In/out degree | Easy |
| Cheapest Flights K Stops | Bellman-Ford / Dijkstra | Medium |
| Word Ladder | BFS (word as node) | Hard |
| Redundant Connection | Union-Find | Medium |
| Accounts Merge | Union-Find | Medium |
| Clone Graph | BFS/DFS | Medium |
| Alien Dictionary | Topo sort | Hard |
| Critical Connections | Tarjan's bridges | Hard |

---

## Tips for Google

- **Grid problems**: treat each cell as a node — BFS for shortest path, DFS for components
- **Word problems**: treat each word as a node — build adjacency from transitions
- **Always check**: disconnected graph (multiple components) — loop over all nodes
- **Cycle in directed graph**: use 3-color DFS (0/1/2) or Kahn's (if leftover nodes after topo sort)
- **Shortest path**: BFS for unweighted, Dijkstra for weighted non-negative, Bellman-Ford for negative

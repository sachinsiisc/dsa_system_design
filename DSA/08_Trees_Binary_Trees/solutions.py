"""
Binary Trees — Problems + Solutions (12 problems)
Full solutions included with step-by-step walk-throughs.
"""
from collections import deque
from typing import Optional, List


class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right

    @staticmethod
    def from_list(values):
        """Build tree from level-order list (None = missing node)."""
        if not values:
            return None
        root = TreeNode(values[0])
        queue = deque([root])
        i = 1
        while queue and i < len(values):
            node = queue.popleft()
            if i < len(values) and values[i] is not None:
                node.left = TreeNode(values[i])
                queue.append(node.left)
            i += 1
            if i < len(values) and values[i] is not None:
                node.right = TreeNode(values[i])
                queue.append(node.right)
            i += 1
        return root

    def to_list(self):
        """Level-order list representation."""
        result, queue = [], deque([self])
        while queue:
            node = queue.popleft()
            if node:
                result.append(node.val)
                queue.append(node.left)
                queue.append(node.right)
            else:
                result.append(None)
        while result and result[-1] is None:
            result.pop()
        return result


# ══════════════════════════════════════════════════════════════════════════════
# P1: MAXIMUM DEPTH
# ══════════════════════════════════════════════════════════════════════════════
def max_depth(root: Optional[TreeNode]) -> int:
    """
    LeetCode #104

    Examples:
      [3,9,20,null,null,15,7] → 3
           3
          / \\
         9   20
            /  \\
           15    7
      Depth: max(depth(9), depth(20)) + 1 = max(1, 2) + 1 = 3

      [1,null,2] → 2
      [] → 0

    Approach: DFS. depth(node) = 1 + max(depth(left), depth(right)).
    Base case: None → 0.

    Time: O(n), Space: O(h) where h = tree height (recursion stack)
    Worst case (skewed tree): O(n) space.
    """
    if not root:
        return 0
    return 1 + max(max_depth(root.left), max_depth(root.right))


# ══════════════════════════════════════════════════════════════════════════════
# P2: INVERT BINARY TREE
# ══════════════════════════════════════════════════════════════════════════════
def invert_tree(root: Optional[TreeNode]) -> Optional[TreeNode]:
    """
    LeetCode #226

    Example:
         4              4
        / \\    →       / \\
       2   7          7   2
      /\\ /\\          /\\ /\\
     1 3 6 9        9 6 3 1

    Approach: Post-order DFS. Invert children first, then swap.
    Or pre-order: swap first, then invert children (both work).

    Walk-through for [4,2,7,1,3,6,9]:
      invert(4):
        left = invert(2):
          left = invert(1): returns leaf 1
          right = invert(3): returns leaf 3
          swap: node.left=3, node.right=1 → return 2-node with children 3,1
        right = invert(7):
          left = invert(6): returns leaf 6
          right = invert(9): returns leaf 9
          swap: node.left=9, node.right=6
        swap: node.left=7-subtree, node.right=2-subtree
    """
    if not root:
        return None
    root.left, root.right = invert_tree(root.right), invert_tree(root.left)
    return root


# ══════════════════════════════════════════════════════════════════════════════
# P3: DIAMETER OF BINARY TREE
# ══════════════════════════════════════════════════════════════════════════════
def diameter_of_binary_tree(root: Optional[TreeNode]) -> int:
    """
    LeetCode #543
    Diameter = longest path between any two nodes (may not pass through root).
    Path length = number of EDGES.

    Example:
            1
           / \\
          2   3
         / \\
        4   5
    Diameter = 3 (4→2→1→3 or 5→2→1→3, 3 edges)
    But also: 4→2→5 = 2 edges < 3.

    [1,2,3,4,5] → 3
    [1,2] → 1
    [1] → 0

    Approach: For each node, diameter THROUGH that node = left_height + right_height.
    Track global max. DFS returns height (for use by parent).

    Walk-through for [1,2,3,4,5]:
      dfs(4): height=1, diameter_through_4=0+0=0. Update best=0.
      dfs(5): height=1, diameter_through_5=0. best=0.
      dfs(2): left_h=1, right_h=1. diameter_through_2=1+1=2. best=2. Return height=2.
      dfs(3): height=1. diameter_through_3=0. best=2.
      dfs(1): left_h=2, right_h=1. diameter_through_1=2+1=3. best=3. Return 3.
    Answer: 3 ✓
    """
    best = [0]
    def dfs(node):
        if not node:
            return 0
        left_h  = dfs(node.left)
        right_h = dfs(node.right)
        best[0] = max(best[0], left_h + right_h)
        return 1 + max(left_h, right_h)
    dfs(root)
    return best[0]


# ══════════════════════════════════════════════════════════════════════════════
# P4: SAME TREE
# ══════════════════════════════════════════════════════════════════════════════
def is_same_tree(p: Optional[TreeNode], q: Optional[TreeNode]) -> bool:
    """
    LeetCode #100

    Examples:
      [1,2,3] vs [1,2,3] → True
      [1,2]   vs [1,null,2] → False  (structure differs)
      [1,2,1] vs [1,1,2]   → False  (values differ)

    Base cases:
      Both None → True (matching leaves)
      One None → False (structure mismatch)
      Values differ → False
    Recursive: check left subtrees AND right subtrees.
    """
    if not p and not q:
        return True
    if not p or not q or p.val != q.val:
        return False
    return is_same_tree(p.left, q.left) and is_same_tree(p.right, q.right)


# ══════════════════════════════════════════════════════════════════════════════
# P5: SYMMETRIC TREE
# ══════════════════════════════════════════════════════════════════════════════
def is_symmetric(root: Optional[TreeNode]) -> bool:
    """
    LeetCode #101
    Is tree a mirror of itself?

    Examples:
          1               1
         / \\             / \\
        2   2           2   2
       /\\ /\\           \\    \\
      3 4 4 3          3    3
    True                False (left has node on right, right has node on right)

    [1,2,2,3,4,4,3] → True
    [1,2,2,null,3,null,3] → False

    Key insight: symmetric if left subtree is a mirror of right subtree.
    Mirror check: is_mirror(a, b) = a.val == b.val AND is_mirror(a.left, b.right) AND is_mirror(a.right, b.left)
    """
    def is_mirror(a, b):
        if not a and not b: return True
        if not a or not b: return False
        return a.val == b.val and is_mirror(a.left, b.right) and is_mirror(a.right, b.left)
    return is_mirror(root.left, root.right) if root else True


# ══════════════════════════════════════════════════════════════════════════════
# P6: BINARY TREE LEVEL ORDER TRAVERSAL
# ══════════════════════════════════════════════════════════════════════════════
def level_order(root: Optional[TreeNode]) -> List[List[int]]:
    """
    LeetCode #102

    Example:
          3
         / \\
        9   20
           /  \\
          15    7
    → [[3],[9,20],[15,7]]

    [1] → [[1]]
    [] → []

    Approach: BFS. Process level-by-level using queue.
    Key: record queue size at start of each level → process exactly that many nodes.

    Time: O(n), Space: O(n) (queue holds widest level at once)
    """
    if not root:
        return []
    result = []
    queue = deque([root])
    while queue:
        level = []
        for _ in range(len(queue)):     # process exactly this level's nodes
            node = queue.popleft()
            level.append(node.val)
            if node.left:  queue.append(node.left)
            if node.right: queue.append(node.right)
        result.append(level)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# P7: BINARY TREE RIGHT SIDE VIEW
# ══════════════════════════════════════════════════════════════════════════════
def right_side_view(root: Optional[TreeNode]) -> List[int]:
    """
    LeetCode #199
    Return values visible from the right side (rightmost node of each level).

    Examples:
          1            [1]
         / \\
        2   3          [1,3]
         \\   \\
          5   4        [1,3,4]
    → [1,3,4]

    [1,2,3,null,5,null,4] → [1,3,4]
    [1,null,3] → [1,3]
    [] → []

    Approach: Level-order BFS. Take last node of each level.
    """
    if not root:
        return []
    result = []
    queue = deque([root])
    while queue:
        level_size = len(queue)
        for i in range(level_size):
            node = queue.popleft()
            if i == level_size - 1:   # last node in level
                result.append(node.val)
            if node.left:  queue.append(node.left)
            if node.right: queue.append(node.right)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# P8: PATH SUM II (ALL PATHS)
# ══════════════════════════════════════════════════════════════════════════════
def path_sum(root: Optional[TreeNode], target_sum: int) -> List[List[int]]:
    """
    LeetCode #113
    Find all root-to-leaf paths where sum equals target_sum.

    Example:
              5
             / \\
            4   8
           /   / \\
          11  13   4
         / \\      / \\
        7   2    5   1
    target=22
    → [[5,4,11,2], [5,8,4,5]]
    5+4+11+2=22 ✓, 5+8+4+5=22 ✓

    [1,2,3], target=5 → []
    [1,2], target=1 → [] (1 is not a leaf, path must reach leaf)

    Approach: DFS with backtracking. At leaf: if remaining==0, record path.
    """
    result = []
    def dfs(node, remaining, path):
        if not node:
            return
        path.append(node.val)
        if not node.left and not node.right and remaining == node.val:
            result.append(path[:])   # snapshot
        dfs(node.left,  remaining - node.val, path)
        dfs(node.right, remaining - node.val, path)
        path.pop()   # backtrack
    dfs(root, target_sum, [])
    return result


# ══════════════════════════════════════════════════════════════════════════════
# P9: MAXIMUM PATH SUM
# ══════════════════════════════════════════════════════════════════════════════
def max_path_sum(root: Optional[TreeNode]) -> int:
    """
    LeetCode #124
    Find maximum sum path. Path can start/end at any node.
    At least one node must be included.

    Examples:
      [1,2,3] → 6   (2+1+3)
      [-10,9,20,null,null,15,7] → 42  (15+20+7=42)
            -10
            / \\
           9   20
              / \\
             15   7
      [-3] → -3  (single node)
      [2,-1] → 2
      [-1,-2,-3] → -1  (must include at least one node)

    Approach: For each node, max "gain" it contributes to parent =
      max(0, max(gain_left, gain_right)) + node.val
      (take the better child, or no child if both negative)

    Max path THROUGH this node = node.val + max(0, left_gain) + max(0, right_gain)
    Update global best. Return single-branch gain to parent.

    Walk-through for [-10,9,20,null,null,15,7]:
      gain(9) = 9. path_through_9=9. best=9.
      gain(15) = 15. best=15.
      gain(7)  = 7. best=15.
      gain(20): left_gain=15, right_gain=7.
        path_through_20 = 20+15+7 = 42. best=42.
        return 20+15=35 (single branch to parent)
      gain(-10): left_gain=9, right_gain=35.
        path_through_-10 = -10+9+35 = 34 < 42. best=42.
    Answer: 42 ✓
    """
    best = [float('-inf')]
    def gain(node):
        if not node:
            return 0
        left_gain  = max(0, gain(node.left))
        right_gain = max(0, gain(node.right))
        best[0] = max(best[0], node.val + left_gain + right_gain)
        return node.val + max(left_gain, right_gain)   # single branch to parent
    gain(root)
    return best[0]


# ══════════════════════════════════════════════════════════════════════════════
# P10: LOWEST COMMON ANCESTOR
# ══════════════════════════════════════════════════════════════════════════════
def lowest_common_ancestor(root: Optional[TreeNode], p: TreeNode, q: TreeNode) -> Optional[TreeNode]:
    """
    LeetCode #236
    Find LCA of nodes p and q in binary tree (not BST).

    Examples:
            3
           / \\
          5   1
         / \\ / \\
        6  2 0  8
          / \\
         7   4
    LCA(5,1) = 3   (3 is lowest common ancestor)
    LCA(5,4) = 5   (5 is ancestor of 4, and 5 itself counts)
    LCA(6,4) = 5

    Approach: Post-order DFS.
    If current node is p or q → return it.
    If left subtree returned non-null AND right returned non-null → current is LCA.
    Otherwise return whichever subtree returned non-null.

    Walk-through LCA(5,4):
      dfs(3):
        left = dfs(5):
          left = dfs(6): 6 ≠ p(5), 6 ≠ q(4). return None.
          right = dfs(2):
            left = dfs(7): not p/q → None.
            right = dfs(4): 4 == q → return node(4).
            left=None, right=node(4) → return node(4).
          left=None (6), right=node(4) from dfs(2). Both non-null? No, left=None.
          But current node(5) == p! → return node(5).
        right = dfs(1): 1≠p, 1≠q. Its subtrees don't have p or q → return None.
        left=node(5) (non-null), right=None → return node(5).
    LCA = node(5) ✓
    """
    if not root or root is p or root is q:
        return root
    left  = lowest_common_ancestor(root.left,  p, q)
    right = lowest_common_ancestor(root.right, p, q)
    if left and right:
        return root   # p in one subtree, q in other → root is LCA
    return left or right


# ══════════════════════════════════════════════════════════════════════════════
# P11: SERIALIZE AND DESERIALIZE BINARY TREE
# ══════════════════════════════════════════════════════════════════════════════
class Codec:
    """
    LeetCode #297 (Hard)

    Example:
      Tree:    1
              / \\
             2   3
                / \\
               4   5
    serialize → "1,2,#,#,3,4,#,#,5,#,#"  (pre-order, # = null)
    deserialize → reconstruct same tree

    Approach: Pre-order DFS.
    serialize: visit node → left → right. Nulls as "#".
    deserialize: reconstruct using iterator over tokens.

    Pre-order ensures we see root before children → can rebuild left-to-right.
    """
    def serialize(self, root):
        parts = []
        def dfs(node):
            if not node:
                parts.append('#')
                return
            parts.append(str(node.val))
            dfs(node.left)
            dfs(node.right)
        dfs(root)
        return ','.join(parts)

    def deserialize(self, data):
        tokens = iter(data.split(','))
        def dfs():
            val = next(tokens)
            if val == '#':
                return None
            node = TreeNode(int(val))
            node.left  = dfs()
            node.right = dfs()
            return node
        return dfs()


# ══════════════════════════════════════════════════════════════════════════════
# P12: COUNT GOOD NODES IN BINARY TREE
# ══════════════════════════════════════════════════════════════════════════════
def good_nodes(root: TreeNode) -> int:
    """
    LeetCode #1448
    A node X is "good" if no node on the path from root to X has value > X.val.
    Return count of good nodes.

    Examples:
            3
           / \\
          1   4
         /   / \\
        3   1   5
    Good nodes: 3(root), 3(leaf, path=[3,1,3] max=3 ≤3), 4, 5
    Not good: 1(left, path=[3,1] max=3 > 1), 1(right of 4, path=[3,4,1] max=4 > 1)
    → 4

    [3,3,null,4,2]: 3 nodes.

    Approach: DFS tracking max_so_far.
    Node is good if node.val >= max_so_far.
    """
    def dfs(node, max_so_far):
        if not node:
            return 0
        good = 1 if node.val >= max_so_far else 0
        max_so_far = max(max_so_far, node.val)
        return good + dfs(node.left, max_so_far) + dfs(node.right, max_so_far)
    return dfs(root, float('-inf'))


# ══════════════════════════════════════════════════════════════════════════════
# TESTS
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    def make(vals): return TreeNode.from_list(vals)

    # P1
    assert max_depth(make([3,9,20,None,None,15,7])) == 3
    assert max_depth(make([1,None,2])) == 2
    assert max_depth(None) == 0
    print("✓ max_depth")

    # P2
    t = make([4,2,7,1,3,6,9])
    invert_tree(t)
    assert t.to_list() == [4,7,2,9,6,3,1]
    print("✓ invert_tree")

    # P3
    assert diameter_of_binary_tree(make([1,2,3,4,5])) == 3
    assert diameter_of_binary_tree(make([1,2])) == 1
    print("✓ diameter_of_binary_tree")

    # P4
    assert is_same_tree(make([1,2,3]), make([1,2,3])) == True
    assert is_same_tree(make([1,2]), make([1,None,2])) == False
    print("✓ is_same_tree")

    # P5
    assert is_symmetric(make([1,2,2,3,4,4,3])) == True
    assert is_symmetric(make([1,2,2,None,3,None,3])) == False
    print("✓ is_symmetric")

    # P6
    assert level_order(make([3,9,20,None,None,15,7])) == [[3],[9,20],[15,7]]
    assert level_order(None) == []
    print("✓ level_order")

    # P7
    assert right_side_view(make([1,2,3,None,5,None,4])) == [1,3,4]
    assert right_side_view(None) == []
    print("✓ right_side_view")

    # P8
    paths = path_sum(make([5,4,8,11,None,13,4,7,2,None,None,None,None,5,1]), 22)
    assert sorted(paths) == sorted([[5,4,11,2],[5,8,4,5]])
    print("✓ path_sum")

    # P9
    assert max_path_sum(make([1,2,3])) == 6
    assert max_path_sum(make([-10,9,20,None,None,15,7])) == 42
    assert max_path_sum(make([-3])) == -3
    print("✓ max_path_sum")

    # P10
    t = make([3,5,1,6,2,0,8,None,None,7,4])
    nodes = {}
    def collect(node):
        if node:
            nodes[node.val] = node
            collect(node.left)
            collect(node.right)
    collect(t)
    lca = lowest_common_ancestor(t, nodes[5], nodes[1])
    assert lca.val == 3
    lca = lowest_common_ancestor(t, nodes[5], nodes[4])
    assert lca.val == 5
    print("✓ lowest_common_ancestor")

    # P11
    codec = Codec()
    t = make([1,2,3,None,None,4,5])
    serialized = codec.serialize(t)
    restored = codec.deserialize(serialized)
    assert codec.serialize(restored) == serialized
    print("✓ serialize/deserialize")

    # P12
    assert good_nodes(make([3,1,4,3,None,1,5])) == 4
    assert good_nodes(make([3,3,None,4,2])) == 3
    print("✓ good_nodes")

    print("\n🎉 All binary tree tests passed!")

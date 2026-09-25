# Tries — Google Level

## Mental Model
```
Trie = prefix tree — each node is a character, path from root = prefix
Operations: insert O(L), search O(L), startsWith O(L)   L = word length
Use for: autocomplete, spell check, prefix matching, word search in grid
```

---

## Trie Implementation

```python
class TrieNode:
    def __init__(self):
        self.children = {}   # char → TrieNode
        self.is_end = False  # marks complete word

class Trie:
    def __init__(self):
        self.root = TrieNode()

    def insert(self, word):
        node = self.root
        for ch in word:
            if ch not in node.children:
                node.children[ch] = TrieNode()
            node = node.children[ch]
        node.is_end = True

    def search(self, word):
        node = self.root
        for ch in word:
            if ch not in node.children:
                return False
            node = node.children[ch]
        return node.is_end

    def starts_with(self, prefix):
        node = self.root
        for ch in prefix:
            if ch not in node.children:
                return False
            node = node.children[ch]
        return True

    def delete(self, word):
        """Delete word if it exists."""
        def _delete(node, word, depth):
            if depth == len(word):
                if not node.is_end:
                    return False
                node.is_end = False
                return len(node.children) == 0  # delete if no children

            ch = word[depth]
            if ch not in node.children:
                return False
            should_delete = _delete(node.children[ch], word, depth + 1)
            if should_delete:
                del node.children[ch]
                return not node.is_end and len(node.children) == 0
            return False

        _delete(self.root, word, 0)
```

---

## Pattern 1: Word Search II (Trie + Backtracking)

Find all words from a dictionary that exist in a grid.

```python
def find_words(board, words):
    trie = Trie()
    for word in words:
        trie.insert(word)

    rows, cols = len(board), len(board[0])
    result = set()

    def dfs(node, r, c, path):
        ch = board[r][c]
        if ch not in node.children:
            return
        next_node = node.children[ch]
        path += ch

        if next_node.is_end:
            result.add(path)
            next_node.is_end = False  # avoid duplicates

        board[r][c] = '#'  # mark visited
        for dr, dc in [(0,1),(0,-1),(1,0),(-1,0)]:
            nr, nc = r+dr, c+dc
            if 0 <= nr < rows and 0 <= nc < cols and board[nr][nc] != '#':
                dfs(next_node, nr, nc, path)
        board[r][c] = ch  # restore

    for r in range(rows):
        for c in range(cols):
            dfs(trie.root, r, c, "")

    return list(result)
```

---

## Pattern 2: Replace Words (Prefix replacement)

```python
def replace_words(dictionary, sentence):
    trie = Trie()
    for root in dictionary:
        trie.insert(root)

    def find_prefix(word):
        node = trie.root
        for i, ch in enumerate(word):
            if ch not in node.children:
                return word   # no prefix found
            node = node.children[ch]
            if node.is_end:
                return word[:i+1]   # found prefix
        return word

    return ' '.join(find_prefix(word) for word in sentence.split())
```

---

## Pattern 3: Design Search Autocomplete (Top K suggestions)

```python
import heapq

class AutocompleteSystem:
    def __init__(self, sentences, times):
        self.root = TrieNode()
        self.cur_input = ""

        for sentence, time in zip(sentences, times):
            self._insert(sentence, time)

    def _insert(self, sentence, time):
        node = self.root
        for ch in sentence:
            if ch not in node.children:
                node.children[ch] = TrieNode()
            node = node.children[ch]
        if hasattr(node, 'count'):
            node.count = getattr(node, 'count', 0) + time
        else:
            node.count = time

    def input(self, c):
        if c == '#':
            self._insert(self.cur_input, 1)
            self.cur_input = ""
            return []

        self.cur_input += c
        node = self.root
        for ch in self.cur_input:
            if ch not in node.children:
                return []
            node = node.children[ch]

        # BFS/DFS to collect all sentences with this prefix
        results = []
        self._collect(node, self.cur_input, results)
        results.sort(key=lambda x: (-x[1], x[0]))
        return [s for s, _ in results[:3]]

    def _collect(self, node, prefix, results):
        if hasattr(node, 'count'):
            results.append((prefix, node.count))
        for ch, child in node.children.items():
            self._collect(child, prefix + ch, results)
```

---

## Pattern 4: Wildcard / Regex with Trie

```python
class WordDictionary:
    """Supports '.' wildcard."""
    def __init__(self):
        self.root = TrieNode()

    def addWord(self, word):
        node = self.root
        for ch in word:
            if ch not in node.children:
                node.children[ch] = TrieNode()
            node = node.children[ch]
        node.is_end = True

    def search(self, word):
        def dfs(node, i):
            if i == len(word):
                return node.is_end
            ch = word[i]
            if ch == '.':
                return any(dfs(child, i+1) for child in node.children.values())
            if ch not in node.children:
                return False
            return dfs(node.children[ch], i+1)

        return dfs(self.root, 0)
```

---

## Google Problem Table

| Problem | Approach | Difficulty |
|---------|---------|------------|
| Implement Trie | Standard | Medium |
| Search Suggestions | Trie + sort children | Medium |
| Word Search II | Trie + DFS backtracking | Hard |
| Replace Words | Trie prefix lookup | Medium |
| Design Add and Search Words | Trie + DFS for '.' | Medium |
| Longest Word in Dictionary | Trie BFS level-by-level | Medium |
| Palindrome Pairs | Trie + reverse | Hard |
| Stream of Characters | Aho-Corasick / Trie | Hard |

---

## Key Optimizations

```python
# Use array instead of dict for lowercase letters (faster)
class TrieNode:
    def __init__(self):
        self.children = [None] * 26   # index = ord(ch) - ord('a')
        self.is_end = False

# Prune Trie branches with no words (in Word Search II)
# After finding a word, set is_end = False and remove empty branches
# → avoids revisiting dead branches
```

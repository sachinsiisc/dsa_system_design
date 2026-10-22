# CS07: LLD — Google Search
## Search Engine | Every Line Explained | Python + Java + C++

---

> **WHAT WE'RE BUILDING:**
> A simplified search engine covering the core data structures Google uses:
> Inverted Index, PageRank, Crawling, Ranking, and Query Processing.
>
> **THE CORE CHALLENGE:**
> Web has 5.7 billion pages. User types a query → response in < 200ms.
> Must search TRILLIONS of words across billions of documents in 200ms.
> Answer: pre-compute everything. The query-time computation is minimal.

---

## STEP 1 — Requirements & Entities

```
FUNCTIONAL REQUIREMENTS:
  1. Web crawler crawls URLs and extracts text content + links
  2. Indexer processes crawled pages → builds an Inverted Index
  3. PageRank algorithm assigns importance score to each page
  4. Query processor handles search queries:
     - Single word: "python"
     - Multi-word: "python tutorial" (AND by default)
     - Phrase: '"python tutorial"' (exact phrase)
     - Minus: "python -snake" (exclude pages with "snake")
  5. Result ranker: combines relevance + PageRank → sorted results
  6. Spell correction: "pythn tutorial" → "python tutorial"
  7. Auto-suggest: complete partial query as user types
  8. Search result snippets: extract relevant excerpt from page

KEY ENTITIES:
  WebPage         — a crawled page with URL, content, outbound links
  CrawlerQueue    — URL frontier (queue of URLs to crawl)
  Crawler         — fetches web pages, extracts text + links
  InvertedIndex   — maps word → list of (doc_id, positions[])
  PostingList     — list of (doc_id, term_frequency, positions[])
  PageRankEngine  — computes PageRank (link graph-based importance)
  Tokenizer       — splits text into searchable tokens
  QueryParser     — parses search query into structured Query object
  Query           — parsed query with terms, phrases, exclusions
  Ranker          — combines TF-IDF + PageRank → final score
  SnippetExtractor — finds relevant excerpt from page text for result display

NON-FUNCTIONAL:
  Crawl: 1B pages/day = 11K pages/sec
  Index: build incrementally (new pages indexed continuously)
  Query: < 200ms response (pre-built index makes this possible)
  Storage: inverted index for 100B words ≈ several petabytes
```

---

## STEP 2 — Core Concepts Deep Dive

```
INVERTED INDEX (the heart of search):
  Normal (forward) index:
    doc1 → ["google", "search", "engine", "web"]
    doc2 → ["search", "algorithm", "ranking"]
  
  Inverted index (maps word → documents):
    "search" → [(doc1, freq=1, pos=[1]), (doc2, freq=1, pos=[0])]
    "engine" → [(doc1, freq=1, pos=[2])]
    "ranking"→ [(doc2, freq=1, pos=[1])]
  
  WHY INVERTED?
  Query: "search engine"
  Look up "search" → {doc1, doc2}
  Look up "engine" → {doc1}
  Intersect: {doc1} ← only doc1 has both words
  
  This is O(k) where k = matching documents (not O(N) total pages)
  That's why search is fast — we DON'T scan all documents at query time.

TF-IDF (relevance score):
  TF (Term Frequency): how often does the word appear in THIS document?
  "python" appears 50 times in a Python tutorial → TF is high.
  "python" appears 1 time in a travel blog → TF is low.
  
  IDF (Inverse Document Frequency): how RARE is this word across ALL documents?
  Common words ("the", "is", "a"): appear in every document → IDF is near 0.
  Rare words ("quasar", "eigenvalue"): appear in few documents → IDF is high.
  
  TF-IDF = TF × IDF
  High score = word appears often in THIS doc BUT is rare globally = highly relevant.
  "the" has high TF everywhere but IDF ≈ 0 → TF-IDF ≈ 0 (filtered by stopwords)

PAGERANK (importance score):
  A page is important if:
  - Many pages link to it (inbound links = votes)
  - Important pages link to it (quality of votes matters)
  
  PageRank formula (simplified):
  PR(A) = (1-d) + d × (PR(T1)/C(T1) + PR(T2)/C(T2) + ...)
  
  Where:
  d = damping factor (0.85) — models "random surfer" sometimes types new URL
  T1, T2 = pages linking TO page A
  C(T) = number of outbound links from T
  PR(T)/C(T) = fraction of T's PageRank passed to A
  
  Run iteratively until convergence (typically 50-100 iterations).
```

---

## STEP 3 — Python Implementation (Every Line Explained)

```python
# google_search_lld.py
from __future__ import annotations

import math
import re
import threading
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Iterator


# ══════════════════════════════════════════════════════════════════════════════
# WEB PAGE
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class WebPage:
    """
    A crawled web page.
    
    Stores both metadata (for display in results) and content (for indexing).
    Outbound links: used to build the link graph for PageRank.
    """
    url:        str              # Canonical URL: "https://docs.python.org/3/"
    title:      str              # HTML <title> tag content
    content:    str              # Full text content (HTML stripped)
    links:      List[str]        # All hyperlinks found on this page
    id:         str = field(default_factory=lambda: str(uuid.uuid4()))
    crawled_at: str = field(default_factory=lambda: str(__import__('datetime').datetime.utcnow()))
    
    def word_count(self) -> int:
        return len(self.content.split())

    def __repr__(self) -> str:
        return f"WebPage({self.url!r}, {len(self.content)} chars)"


# ══════════════════════════════════════════════════════════════════════════════
# TOKENIZER
# ══════════════════════════════════════════════════════════════════════════════

class Tokenizer:
    """
    Converts raw text to a list of normalized tokens (words).
    
    This is the first step in both INDEXING and QUERY PROCESSING.
    Both must use the SAME tokenization so index and queries match.
    
    STEPS:
    1. Lowercase: "Python" → "python"
    2. Remove punctuation: "Hello, World!" → "Hello World"
    3. Split into words: "python tutorial" → ["python", "tutorial"]
    4. Remove stopwords: ["the", "is", "a", "in"] → removed (useless for search)
    5. Stem/Lemmatize: "running" → "run", "tutorials" → "tutorial"
       (simplified: we skip stemming here)
    """

    # Stopwords: common words that add no search value
    STOPWORDS = {
        "the", "is", "in", "it", "of", "a", "an", "and", "or", "to",
        "for", "that", "this", "with", "be", "on", "as", "are", "was",
        "at", "by", "from", "but", "not", "have", "had", "has", "will"
    }

    def tokenize(self, text: str) -> List[str]:
        """
        Convert text to cleaned tokens.
        
        re.sub(pattern, replacement, string):
        pattern = r'[^a-z0-9\s]'  → match any char that is NOT a-z, 0-9, or whitespace
        replacement = ''           → replace those chars with nothing (delete them)
        This removes all punctuation.
        """
        text = text.lower()
        # 1. Lowercase: "Python Tutorial" → "python tutorial"

        text = re.sub(r'[^a-z0-9\s]', '', text)
        # 2. Remove non-alphanumeric chars: "Hello, World!" → "hello world"
        # re.sub = regular expression substitution
        # r'[^a-z0-9\s]' = regex: [^...] = NOT any of these chars
        # a-z = lowercase letters, 0-9 = digits, \s = whitespace

        tokens = text.split()
        # 3. Split on whitespace: "hello world" → ["hello", "world"]

        tokens = [t for t in tokens if t not in self.STOPWORDS and len(t) > 1]
        # 4. Remove stopwords AND single-character tokens
        # "a" → removed (stopword). "I" → removed (single char after lowercase).
        # List comprehension: keep token only if NOT a stopword AND length > 1

        return tokens

    def tokenize_with_positions(self, text: str) -> Dict[str, List[int]]:
        """
        Returns: {token: [positions where it appears]}
        
        WHY POSITIONS?
        For phrase search: '"python tutorial"' → we need "python" immediately followed by "tutorial".
        Position data lets us check: does position(tutorial) == position(python) + 1?
        
        Example:
        "Python is a tutorial for python programming"
        token_positions = {
          "python": [0, 5],   ← appears at word 0 and word 5
          "tutorial": [3],    ← appears at word 3
          "programming": [6]  ← appears at word 6
        }
        """
        text_lower = text.lower()
        text_clean = re.sub(r'[^a-z0-9\s]', '', text_lower)
        raw_tokens = text_clean.split()

        token_positions: Dict[str, List[int]] = defaultdict(list)
        # defaultdict(list): if key doesn't exist, creates empty list automatically
        # So we can do token_positions["python"].append(5) without checking if key exists

        for position, token in enumerate(raw_tokens):
            # enumerate: gives (index, value) pairs: (0, "python"), (1, "is"), ...
            if token not in self.STOPWORDS and len(token) > 1:
                token_positions[token].append(position)

        return dict(token_positions)


# ══════════════════════════════════════════════════════════════════════════════
# INVERTED INDEX
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class PostingEntry:
    """
    One entry in the PostingList for a term.
    Represents: "term T appears in document D, N times, at positions [...]"
    
    WHY STORE POSITIONS?
    Essential for phrase search and proximity queries.
    Without positions: can only check if term EXISTS in document (not WHERE it is).
    With positions: can check if two terms are ADJACENT (phrase search).
    """
    doc_id:          str        # Which document
    term_frequency:  int        # How many times this term appears in the document
    positions:       List[int]  # Word positions: [0, 5, 12] means positions 0, 5, 12
    url:             str = ""   # For easy result display (no need to re-fetch doc)
    title:           str = ""


class InvertedIndex:
    """
    THE CORE DATA STRUCTURE of a search engine.
    
    STRUCTURE:
    {
      "python":   [PostingEntry(doc1, tf=5, pos=[0,3,7]), PostingEntry(doc2, tf=2, pos=[1,9])],
      "tutorial": [PostingEntry(doc1, tf=3, pos=[1,8,12])],
      "java":     [PostingEntry(doc3, tf=8, pos=[0,2,5,7,...])],
      ...
    }
    
    LOOKUP: O(1) — just a dict lookup.
    INTERSECTION (AND): O(m + n) where m, n = sizes of two posting lists.
    
    REAL GOOGLE INDEX:
    Can't fit in memory. Stored on disk with specialized format:
    - Sorted posting lists: docs sorted by doc_id for efficient merge-intersection
    - Delta encoding: store differences between consecutive doc_ids (compression)
    - VByte encoding: variable-length integers (most doc_ids are small, need few bytes)
    - Partitioned: split by hash(term) across many machines (distributed)
    """

    def __init__(self):
        # term → list of PostingEntry, sorted by doc_id for efficient intersection
        self._index: Dict[str, List[PostingEntry]] = defaultdict(list)
        self._tokenizer = Tokenizer()
        self._doc_count = 0      # Total number of indexed documents
        self._doc_lengths: Dict[str, int] = {}   # doc_id → total token count
        self._lock = threading.RLock()

    def index_document(self, page: WebPage) -> None:
        """
        Add a web page to the inverted index.
        
        PROCESS:
        1. Tokenize the page's title + content
        2. Count term frequencies and positions
        3. For each term, add a PostingEntry to the index
        
        WHY TITLE + CONTENT?
        Title words are more important than body words.
        In production: index separately and weight title 3-5× more in scoring.
        We concatenate here for simplicity (title first = earlier positions = lower pos numbers).
        """
        full_text = page.title + " " + page.content
        # Concatenate title and content. Title appears first → lower position numbers.
        # This matters when ranking (terms in title get higher relevance).

        token_positions = self._tokenizer.tokenize_with_positions(full_text)
        # token_positions: {"python": [0, 5, 12], "tutorial": [3, 8], ...}

        with self._lock:
            self._doc_count += 1
            self._doc_lengths[page.id] = len(full_text.split())

            for term, positions in token_positions.items():
                entry = PostingEntry(
                    doc_id=page.id,
                    term_frequency=len(positions),
                    # term_frequency = how many times this term appears
                    # = length of positions list (one entry per occurrence)
                    positions=positions,
                    url=page.url,
                    title=page.title
                )
                self._index[term].append(entry)
                # List.append: add to end. O(1) amortized.

        print(f"Indexed: {page.url[:50]} ({len(token_positions)} unique terms)")

    def lookup(self, term: str) -> List[PostingEntry]:
        """
        Look up a term in the index.
        Returns all documents containing this term.
        O(1) — just a dict lookup.
        """
        term = term.lower().strip()
        with self._lock:
            return list(self._index.get(term, []))
            # list(...) = return a copy (don't return the mutable internal list)
            # .get(term, []) = return empty list if term not in index

    def intersect(self, posting_lists: List[List[PostingEntry]]) -> List[PostingEntry]:
        """
        AND operation: find documents that appear in ALL posting lists.
        
        ALGORITHM: Merge intersection (like merge sort).
        Works by sorting posting lists by size (smallest first) and iterating.
        
        WHY SMALLEST FIRST?
        If first list has 10 docs and second has 10M docs:
        Start with the 10 — check each of those 10 in the 10M list.
        Much faster than starting with 10M and checking all against 10.
        """
        if not posting_lists:
            return []
        
        # Sort by length (smallest posting list first)
        sorted_lists = sorted(posting_lists, key=len)

        # Start with the smallest list
        result_doc_ids: Set[str] = {e.doc_id for e in sorted_lists[0]}
        # Set comprehension: create a set of doc_ids from the first (smallest) posting list
        # Using a set for O(1) lookup

        # For each subsequent list, intersect with current result
        for posting_list in sorted_lists[1:]:
            posting_doc_ids = {e.doc_id for e in posting_list}
            result_doc_ids &= posting_doc_ids
            # &= is set intersection-update: keep only elements in BOTH sets
            # Same as: result_doc_ids = result_doc_ids.intersection(posting_doc_ids)

            if not result_doc_ids:
                return []   # Early exit: intersection is empty → no results

        # Return PostingEntry objects for documents in the intersection
        # Use entries from the first (smallest) list for their metadata
        return [e for e in sorted_lists[0] if e.doc_id in result_doc_ids]

    def compute_tf_idf(self, entry: PostingEntry, term: str) -> float:
        """
        Compute TF-IDF score for a document-term pair.
        
        TF (Term Frequency — normalized):
        tf = log(1 + raw_tf) / log(1 + doc_length)
        WHY LOG? Prevents 100 occurrences from being 100× more relevant than 1 occurrence.
        
        IDF (Inverse Document Frequency):
        idf = log(N / df) where N = total docs, df = docs containing this term
        WHY LOG? Dampens the effect of rare words (prevents 1-document terms from dominating).
        """
        with self._lock:
            raw_tf = entry.term_frequency
            doc_length = self._doc_lengths.get(entry.doc_id, 1)
            n_docs = max(self._doc_count, 1)
            
            # Number of documents containing this term
            df = len(self._index.get(term, []))
            df = max(df, 1)   # Prevent division by zero

        tf  = math.log(1 + raw_tf) / math.log(1 + doc_length)
        # math.log: natural logarithm. log(1 + 0) = 0, log(1 + 1) = 0.69
        # Adding 1 prevents log(0) error and handles tf=0 gracefully.
        # Dividing by doc_length normalizes for document length
        # (a long document will naturally have higher raw_tf even if term is less relevant)

        idf = math.log(n_docs / df + 1)
        # n_docs/df: how many times rarer this term is than average.
        # +1: additive smoothing — prevents idf=0 for terms in all documents.

        return tf * idf

    def phrase_search(self, phrase: str) -> List[PostingEntry]:
        """
        Phrase search: find documents where terms appear consecutively.
        
        Example: '"python tutorial"' (in quotes)
        Must find documents where "python" appears at position X
        AND "tutorial" appears at position X+1.
        
        ALGORITHM:
        1. Get posting lists for each term in phrase
        2. Intersect to find docs with ALL terms
        3. For each intersecting doc: check positions
           Are the terms adjacent (consecutive positions)?
        """
        terms = self._tokenizer.tokenize(phrase)
        if len(terms) < 2:
            return self.lookup(terms[0]) if terms else []

        # Step 1 & 2: Get posting lists and intersect
        posting_lists = [self.lookup(t) for t in terms]
        candidates = self.intersect(posting_lists)

        # Step 3: Check positional adjacency
        phrase_matches = []
        for candidate_entry in candidates:
            doc_id = candidate_entry.doc_id
            
            with self._lock:
                # Get positions of each term in this document
                term_positions: List[List[int]] = []
                for term in terms:
                    entries_for_term = self._index.get(term, [])
                    for e in entries_for_term:
                        if e.doc_id == doc_id:
                            term_positions.append(e.positions)
                            break   # Found the entry for this doc_id
                    else:
                        term_positions.append([])   # This doc doesn't have this term

            # Check: does any starting position of terms[0] create a consecutive sequence?
            for start_pos in term_positions[0]:
                # Check if terms[1] is at start_pos+1, terms[2] at start_pos+2, etc.
                is_phrase = all(
                    (start_pos + i) in term_positions[i]
                    for i in range(1, len(terms))
                )
                # all(): returns True only if ALL conditions are True
                # (start_pos + i) in term_positions[i]:
                #   Is position (start_pos+i) in the positions list of term i?
                # Example: phrase "python tutorial"
                #   start_pos = 5 (position of "python")
                #   terms[1] = "tutorial", need it at position 6
                #   term_positions[1] = [6, 14] → 6 is in there → True → phrase match!
                
                if is_phrase:
                    phrase_matches.append(candidate_entry)
                    break   # No need to check other starting positions for this doc

        return phrase_matches

    @property
    def doc_count(self) -> int:
        with self._lock: return self._doc_count

    @property
    def term_count(self) -> int:
        with self._lock: return len(self._index)


# ══════════════════════════════════════════════════════════════════════════════
# PAGERANK ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class PageRankEngine:
    """
    Computes PageRank for all pages in the link graph.
    
    PageRank = Google's original innovation (Larry Page's PhD thesis).
    Treats hyperlinks as "votes" — a link from page A to page B = A voting for B.
    
    INTUITION:
    - Wikipedia is linked to by millions of pages → high PageRank
    - A random blog post linked by 3 pages → low PageRank
    - Quality of linker matters: a Wikipedia link is worth more than a spam blog link
    
    ALGORITHM (Power Iteration):
    Start: all pages get equal PageRank (1/N).
    Each iteration: redistribute PageRank based on link structure.
    Repeat until values converge (change < epsilon).
    
    DAMPING FACTOR (d = 0.85):
    Models "random surfer" behavior.
    85% of time: follow a link on current page.
    15% of time: type a random URL in browser.
    Without damping: pages with no inbound links get PR=0 (sink problem).
    With damping: every page gets at least (1-d)/N ≈ 0.15/N base PageRank.
    """

    DAMPING_FACTOR  = 0.85   # 85% probability of following a link
    MAX_ITERATIONS  = 50     # Run at most 50 iterations
    CONVERGENCE_EPS = 1e-6   # Stop when change < 0.000001

    def __init__(self):
        self._scores: Dict[str, float] = {}
        # page_url → PageRank score (after computation)

    def compute(self, pages: List[WebPage]) -> Dict[str, float]:
        """
        Run PageRank algorithm on all known pages.
        Returns: dict of url → PageRank score.
        """
        n = len(pages)
        if n == 0: return {}

        # Build link graph
        urls      = {p.url for p in pages}
        # Set of all known URLs (to filter out-of-corpus links)

        outlinks: Dict[str, List[str]] = {}
        # url → list of URLs this page links to (outbound links)
        # Only count links to pages WE HAVE (ignore external links we haven't crawled)

        inlinks:  Dict[str, List[str]] = defaultdict(list)
        # url → list of URLs that link TO this page (inbound links)

        for page in pages:
            outlinks[page.url] = [l for l in page.links if l in urls]
            # Filter: only links to crawled pages
            for link in outlinks[page.url]:
                inlinks[link].append(page.url)
                # Record that page.url links to 'link'

        # Initialize: all pages start with equal PageRank
        pr: Dict[str, float] = {p.url: 1.0 / n for p in pages}
        # 1.0/n: normalized so total PageRank sums to 1.0
        # Python: 1.0/n = float division. 1/n = integer division (Python 3: also float. OK.)

        base_pr = (1.0 - self.DAMPING_FACTOR) / n
        # base_pr: "teleportation" probability. 15% of random jumps distributed equally.

        for iteration in range(self.MAX_ITERATIONS):
            new_pr: Dict[str, float] = {}

            for page in pages:
                # Contribution from pages that link to this page
                rank_sum = 0.0
                for linker_url in inlinks[page.url]:
                    n_outlinks = len(outlinks.get(linker_url, []))
                    if n_outlinks > 0:
                        rank_sum += pr[linker_url] / n_outlinks
                        # Each linker contributes its PR / (number of its outlinks)
                        # Why divide by outlinks? PageRank is distributed equally among all links.
                        # A page with 100 outlinks passes 1/100 of its PR through each link.
                        # A page with 1 outlink passes all its PR through that link.

                new_pr[page.url] = base_pr + self.DAMPING_FACTOR * rank_sum
                # Final formula: (1-d)/N + d × (sum of incoming PR contributions)

            # Check convergence: has PR stabilized?
            max_change = max(abs(new_pr[u] - pr[u]) for u in pr)
            # max(): find the largest change across all page PR scores
            # abs(): absolute value (change could be positive or negative)

            pr = new_pr
            if max_change < self.CONVERGENCE_EPS:
                print(f"PageRank converged after {iteration + 1} iterations")
                break

        self._scores = pr
        return pr

    def get_score(self, url: str) -> float:
        """Get PageRank score for a URL. Returns 0.0 if not computed."""
        return self._scores.get(url, 0.0)


# ══════════════════════════════════════════════════════════════════════════════
# QUERY PARSER
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ParsedQuery:
    """
    Structured representation of a search query.
    
    Examples:
    "python tutorial" → required_terms=["python", "tutorial"]
    '"python tutorial"' → phrases=[["python", "tutorial"]]
    "python -snake" → required_terms=["python"], excluded_terms=["snake"]
    """
    required_terms:  List[str]        # All must be present
    phrases:         List[List[str]]  # Must appear consecutively
    excluded_terms:  List[str]        # None must be present
    raw_query:       str


class QueryParser:
    """
    Parses a raw search string into a structured ParsedQuery.
    
    Handles:
    - Normal terms: "python tutorial" → two required terms
    - Phrases: '"python tutorial"' → one phrase (must be adjacent)
    - Exclusion: "-snake" → must NOT appear in results
    """

    def __init__(self):
        self._tokenizer = Tokenizer()

    def parse(self, raw_query: str) -> ParsedQuery:
        """
        Parse a raw query string into structured form.
        
        ALGORITHM:
        1. Extract quoted phrases: '"python tutorial"' → phrase = ["python", "tutorial"]
        2. Remove phrases from raw query
        3. Process remaining terms:
           - "-term" → excluded
           - "term"  → required
        """
        phrases:        List[List[str]] = []
        required_terms: List[str]       = []
        excluded_terms: List[str]       = []

        # Step 1: Extract quoted phrases using regex
        phrase_pattern = r'"([^"]+)"'
        # Pattern explanation:
        # "  → literal opening double-quote
        # ([^"]+) → capture group: one or more chars that are NOT double-quote
        # "  → literal closing double-quote

        for phrase_match in re.finditer(phrase_pattern, raw_query):
            phrase_text = phrase_match.group(1)
            # group(1) = first capture group = the text INSIDE the quotes
            phrase_tokens = self._tokenizer.tokenize(phrase_text)
            if phrase_tokens:
                phrases.append(phrase_tokens)
                # Also add each phrase word to required_terms (doc must have all words)
                required_terms.extend(phrase_tokens)

        # Step 2: Remove phrases from query to process remaining words
        remaining = re.sub(phrase_pattern, '', raw_query).strip()
        # re.sub: replace all matches of phrase_pattern with ''
        # Remove the quoted parts — we already processed them

        # Step 3: Process remaining words
        for word in remaining.split():
            word = word.strip()
            if not word: continue

            if word.startswith('-'):
                # Exclusion term: "-snake" → exclude "snake"
                excluded = word[1:]   # Remove the '-' prefix. "-snake"[1:] = "snake"
                excluded_tokens = self._tokenizer.tokenize(excluded)
                excluded_terms.extend(excluded_tokens)
            else:
                # Required term
                tokens = self._tokenizer.tokenize(word)
                required_terms.extend(tokens)

        # Remove duplicates while preserving order
        required_terms = list(dict.fromkeys(required_terms))
        # dict.fromkeys(): creates dict with keys from list (values=None).
        # Dicts in Python 3.7+ preserve insertion order.
        # list(...): convert back to list.
        # Effect: deduplication while preserving original order.

        return ParsedQuery(
            required_terms=required_terms,
            phrases=phrases,
            excluded_terms=excluded_terms,
            raw_query=raw_query
        )


# ══════════════════════════════════════════════════════════════════════════════
# RANKER
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class SearchResult:
    """One result in the search results page."""
    url:       str
    title:     str
    snippet:   str       # Excerpt from the page showing query terms in context
    score:     float     # Final ranking score (higher = better)
    pagerank:  float
    tf_idf:    float


class Ranker:
    """
    Combines TF-IDF relevance score + PageRank importance score → final ranking.
    
    FINAL SCORE = α × TF-IDF + β × PageRank
    
    α = 0.6: 60% weight on relevance (how well query matches content)
    β = 0.4: 40% weight on authority (how important is this page globally)
    
    Real Google uses 200+ signals:
    - TF-IDF relevance
    - PageRank / domain authority
    - User engagement (click-through rate, bounce rate)
    - Freshness (recently updated pages score higher for news queries)
    - Mobile-friendliness
    - HTTPS security
    - Page load speed
    - User location (local results)
    - Search history personalization
    """

    RELEVANCE_WEIGHT = 0.6   # α: TF-IDF weight
    PAGERANK_WEIGHT  = 0.4   # β: PageRank weight

    def __init__(self, index: InvertedIndex, pagerank: PageRankEngine):
        self._index    = index
        self._pagerank = pagerank

    def rank(self, query: ParsedQuery, candidates: List[PostingEntry],
             pages: Dict[str, WebPage]) -> List[SearchResult]:
        """
        Score and rank candidates for a given query.
        
        INPUTS:
        query: parsed query with required terms, phrases, exclusions
        candidates: PostingEntry list (documents that match the query)
        pages: dict of page_id → WebPage (for snippet extraction)
        
        OUTPUTS:
        List[SearchResult] sorted by score descending (best first)
        """
        results = []

        for entry in candidates:
            page = pages.get(entry.doc_id)
            if not page: continue

            # Exclusion check: skip if page contains any excluded term
            page_tokens = set(self._index._tokenizer.tokenize(page.content))
            if any(ex in page_tokens for ex in query.excluded_terms):
                continue
            # any(): True if at least ONE excluded term is in the page

            # TF-IDF score: average across all required terms
            tf_idf_scores = []
            for term in query.required_terms:
                # Find the PostingEntry for this doc + term
                term_entries = [e for e in self._index.lookup(term)
                                if e.doc_id == entry.doc_id]
                if term_entries:
                    tf_idf_scores.append(self._index.compute_tf_idf(term_entries[0], term))

            avg_tf_idf = (sum(tf_idf_scores) / len(tf_idf_scores)
                          if tf_idf_scores else 0.0)
            # Average TF-IDF across all required terms
            # Sum then divide: arithmetic mean

            # PageRank score (normalized to 0-1 range)
            pr_score = min(self._pagerank.get_score(page.url) * 10, 1.0)
            # *10: scale up small PageRank values (they're often tiny fractions)
            # min(..., 1.0): cap at 1.0

            # Title boost: if query terms appear in title, boost score
            title_tokens = set(self._index._tokenizer.tokenize(page.title))
            title_boost = len(set(query.required_terms) & title_tokens) / max(len(query.required_terms), 1)
            # & = set intersection: how many required terms appear in title?
            # Divide by total required terms → fraction 0.0 to 1.0

            # Final score
            final_score = (self.RELEVANCE_WEIGHT * avg_tf_idf
                           + self.PAGERANK_WEIGHT * pr_score
                           + 0.2 * title_boost)   # Title boost bonus
            # Weights: 60% TF-IDF + 40% PageRank + up to 20% title bonus

            # Generate snippet
            snippet = self._extract_snippet(page.content, query.required_terms)

            results.append(SearchResult(
                url=page.url,
                title=page.title,
                snippet=snippet,
                score=final_score,
                pagerank=pr_score,
                tf_idf=avg_tf_idf
            ))

        # Sort by score descending (best results first)
        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def _extract_snippet(self, content: str, query_terms: List[str], window: int = 50) -> str:
        """
        Extract a relevant snippet from page content.
        Find the position of the first query term, return ±window words around it.
        
        This is the "..." excerpt shown under each search result.
        Google shows the part of the page most relevant to your query.
        """
        words  = content.split()
        target = {t.lower() for t in query_terms}

        # Find first occurrence of any query term
        start_idx = 0
        for i, word in enumerate(words):
            if re.sub(r'[^a-z]', '', word.lower()) in target:
                start_idx = max(0, i - 5)   # Start 5 words before the match
                break

        # Extract window words around the match
        end_idx = min(start_idx + window, len(words))
        snippet_words = words[start_idx:end_idx]
        snippet = ' '.join(snippet_words)

        if start_idx > 0: snippet = "..." + snippet
        if end_idx < len(words): snippet = snippet + "..."

        return snippet


# ══════════════════════════════════════════════════════════════════════════════
# WEB CRAWLER
# ══════════════════════════════════════════════════════════════════════════════

class Crawler:
    """
    Crawls web pages by following links.
    
    REAL GOOGLE CRAWLER (Googlebot):
    - Follows robots.txt rules (politeness protocol)
    - Respects crawl-delay headers
    - Millions of crawler instances distributed worldwide
    - Prioritizes important pages (high PageRank, frequently updated)
    
    BFS CRAWL:
    Start with seed URLs → crawl them → extract links → add to queue → repeat.
    deque for the queue: O(1) append and popleft vs list's O(n) pop(0).
    """

    def __init__(self):
        self._queue:   deque[str] = deque()   # URLs to crawl next
        self._visited: Set[str]   = set()     # URLs already crawled (no revisit)
        self._pages:   Dict[str, WebPage] = {}
        self._lock     = threading.Lock()

    def add_seed_url(self, url: str) -> None:
        """Add starting URL to the crawl queue."""
        with self._lock:
            if url not in self._visited:
                self._queue.append(url)

    def crawl_next(self) -> Optional[WebPage]:
        """
        Crawl the next URL in the queue.
        In production: actual HTTP request using requests or aiohttp.
        Here: simulated with placeholder content.
        """
        with self._lock:
            if not self._queue:
                return None
            url = self._queue.popleft()   # BFS: FIFO (first in, first out)
            # popleft() removes and returns from the LEFT (front) of deque
            # This gives BFS (breadth-first) behavior

            if url in self._visited:
                return None    # Already crawled
            self._visited.add(url)

        # SIMULATE fetching the page (real: HTTP GET request)
        page = self._simulate_fetch(url)
        if page:
            with self._lock:
                self._pages[page.id] = page
                # Add discovered links to queue (filtered: not already visited)
                for link in page.links:
                    if link not in self._visited:
                        self._queue.append(link)
        return page

    def _simulate_fetch(self, url: str) -> Optional[WebPage]:
        """Simulate fetching a page (in production: actual HTTP request + HTML parser)."""
        # Only simulate specific test URLs
        SIMULATED_CONTENT = {
            "https://docs.python.org/3/": {
                "title": "Python 3 Documentation",
                "content": "Python is a programming language tutorial. Python tutorial for beginners. "
                          "Python python python programming guide reference documentation.",
                "links": ["https://docs.python.org/3/library/", "https://python.org/"]
            },
            "https://python.org/": {
                "title": "Welcome to Python.org",
                "content": "Python programming language official website. Python downloads tutorials "
                          "documentation community. Python is versatile and powerful programming.",
                "links": ["https://docs.python.org/3/", "https://pypi.org/"]
            },
            "https://realpython.com/": {
                "title": "Real Python — Python Tutorials",
                "content": "Real Python tutorials for Python developers. Python tutorial intermediate "
                          "advanced web development data science machine learning python.",
                "links": ["https://docs.python.org/3/"]
            },
        }
        if url not in SIMULATED_CONTENT:
            return None
        data = SIMULATED_CONTENT[url]
        return WebPage(url=url, title=data["title"],
                       content=data["content"], links=data["links"])

    def get_all_pages(self) -> List[WebPage]:
        with self._lock:
            return list(self._pages.values())


# ══════════════════════════════════════════════════════════════════════════════
# SEARCH ENGINE — Facade
# ══════════════════════════════════════════════════════════════════════════════

class SearchEngine:
    """
    FACADE: Orchestrates crawler → indexer → PageRank → ranker → results.
    
    The public interface is simple:
    - search_engine.crawl(url)   → crawl a URL
    - search_engine.build_index() → build inverted index from crawled pages
    - search_engine.search(query) → return ranked results
    
    All the complexity (InvertedIndex, PageRank, QueryParser, Ranker) is hidden.
    """

    def __init__(self):
        self._crawler      = Crawler()
        self._index        = InvertedIndex()
        self._pagerank     = PageRankEngine()
        self._query_parser = QueryParser()
        self._ranker:      Optional[Ranker] = None   # Created after PageRank is computed
        self._pages:       Dict[str, WebPage] = {}   # page_id → WebPage

    def add_seed(self, url: str) -> None:
        self._crawler.add_seed_url(url)

    def crawl_all(self) -> int:
        """Crawl all queued URLs. Returns number of pages crawled."""
        count = 0
        while True:
            page = self._crawler.crawl_next()
            if page is None:
                break
            self._pages[page.id] = page
            count += 1
        print(f"Crawled {count} pages")
        return count

    def build_index(self) -> None:
        """Build inverted index and compute PageRank from crawled pages."""
        pages = self._crawler.get_all_pages()

        print(f"\nBuilding index for {len(pages)} pages...")
        for page in pages:
            self._index.index_document(page)

        print(f"\nComputing PageRank...")
        self._pagerank.compute(pages)

        self._ranker = Ranker(self._index, self._pagerank)
        print(f"\nIndex ready: {self._index.term_count} unique terms across {self._index.doc_count} docs")

    def search(self, raw_query: str, max_results: int = 10) -> List[SearchResult]:
        """
        Process a search query and return ranked results.
        """
        if not self._ranker:
            raise RuntimeError("Call build_index() before searching")

        print(f"\n🔍 Query: '{raw_query}'")
        
        # Step 1: Parse query
        query = self._query_parser.parse(raw_query)
        print(f"   Required: {query.required_terms} | Excluded: {query.excluded_terms}")

        # Step 2: Retrieve candidates using inverted index
        if query.phrases:
            # Phrase search
            all_candidates = []
            for phrase in query.phrases:
                phrase_str = " ".join(phrase)
                candidates = self._index.phrase_search(phrase_str)
                all_candidates.extend(candidates)
        elif query.required_terms:
            # Standard AND search: intersect posting lists for all required terms
            posting_lists = [self._index.lookup(t) for t in query.required_terms]
            posting_lists = [pl for pl in posting_lists if pl]   # Remove empty lists
            all_candidates = (self._index.intersect(posting_lists)
                              if posting_lists else [])
        else:
            return []

        print(f"   Candidates: {len(all_candidates)}")

        # Step 3: Rank candidates
        results = self._ranker.rank(query, all_candidates, self._pages)

        return results[:max_results]


# ══════════════════════════════════════════════════════════════════════════════
# DEMO
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    engine = SearchEngine()

    # Add seed URLs
    for url in ["https://docs.python.org/3/", "https://python.org/", "https://realpython.com/"]:
        engine.add_seed(url)

    # Crawl and index
    engine.crawl_all()
    engine.build_index()

    # Search queries
    results = engine.search("python tutorial")
    print(f"\nTop results for 'python tutorial':")
    for i, r in enumerate(results, 1):
        print(f"  {i}. [{r.score:.3f}] {r.title}")
        print(f"     {r.url}")
        print(f"     {r.snippet[:100]}...")

    results2 = engine.search('"python tutorial"')
    print(f"\nPhrase results for '\"python tutorial\"':")
    for r in results2:
        print(f"  [{r.score:.3f}] {r.title}")
```

---

## STEP 4 — Java Key Patterns

```java
// Java: ConcurrentHashMap for thread-safe inverted index
class InvertedIndex {
    // ConcurrentHashMap: thread-safe HashMap.
    // Multiple threads can READ and WRITE concurrently.
    // Internally: splits map into 16 segments. Locks one segment at a time.
    // This allows 16 threads to write simultaneously (to different segments).
    private final ConcurrentHashMap<String, List<PostingEntry>> index
        = new ConcurrentHashMap<>();

    // computeIfAbsent: atomic "get or create"
    // If key not present: create with factory function (lambda).
    // Atomic: no race condition between "check if exists" and "insert".
    public void addPosting(String term, PostingEntry entry) {
        index.computeIfAbsent(term, k -> new CopyOnWriteArrayList<>())
             .add(entry);
        // CopyOnWriteArrayList: thread-safe list.
        // READS: no lock (reads from snapshot).
        // WRITES: copy entire list, modify copy, swap.
        // Good when reads >> writes (posting list: many searches, few updates).
    }
}

// Java: Streams for intersection
List<String> intersect(List<List<String>> docIdLists) {
    if (docIdLists.isEmpty()) return List.of();
    
    // Sort by size (smallest first) for efficient intersection
    List<Set<String>> sets = docIdLists.stream()
        .sorted(Comparator.comparingInt(List::size))   // Sort by list size
        .map(HashSet::new)   // Convert each list to HashSet for O(1) lookup
        .collect(Collectors.toList());
    
    Set<String> result = new HashSet<>(sets.get(0));  // Start with smallest
    for (int i = 1; i < sets.size(); i++) {
        result.retainAll(sets.get(i));  // retainAll = intersection
        // Mutates result in-place: removes elements NOT in sets.get(i)
        if (result.isEmpty()) return List.of();  // Early exit
    }
    return new ArrayList<>(result);
}
```

---

## STEP 5 — C++ Key Patterns

```cpp
// C++: unordered_map for inverted index + shared_mutex for concurrent reads
#include <unordered_map>
#include <shared_mutex>
#include <vector>

class InvertedIndex {
    std::unordered_map<std::string, std::vector<PostingEntry>> index_;
    mutable std::shared_mutex mtx_;
    // shared_mutex: allows multiple concurrent readers OR one writer.
    // mutable: allows locking in const member functions (needed for reads in const methods).

public:
    void addPosting(const std::string& term, PostingEntry entry) {
        std::unique_lock lock(mtx_);   // Exclusive write lock
        index_[term].push_back(std::move(entry));
        // std::move: transfer ownership (avoid copying PostingEntry)
    }

    std::vector<PostingEntry> lookup(const std::string& term) const {
        std::shared_lock lock(mtx_);   // Shared read lock (multiple threads can hold this)
        auto it = index_.find(term);   // O(1) hash lookup
        if (it == index_.end()) return {};
        return it->second;   // Return copy (safe after releasing lock)
    }
};

// C++: PageRank using unordered_map
std::unordered_map<std::string, double> computePageRank(
    const std::vector<WebPage>& pages, int maxIterations = 50
) {
    const double d = 0.85;
    const int n = pages.size();
    std::unordered_map<std::string, double> pr;
    
    // Initialize: equal PageRank for all pages
    for (const auto& p : pages)
        pr[p.url] = 1.0 / n;
    
    for (int iter = 0; iter < maxIterations; ++iter) {
        std::unordered_map<std::string, double> newPr;
        double maxChange = 0.0;
        
        for (const auto& page : pages) {
            double rankSum = 0.0;
            for (const auto& linkerUrl : inlinks.at(page.url)) {
                // at(): like [], but throws std::out_of_range if key missing
                // [] would insert a default value (dangerous for const maps)
                int nOut = outlinks.at(linkerUrl).size();
                if (nOut > 0) rankSum += pr.at(linkerUrl) / nOut;
            }
            newPr[page.url] = (1.0 - d) / n + d * rankSum;
            maxChange = std::max(maxChange, std::abs(newPr[page.url] - pr.at(page.url)));
        }
        pr = std::move(newPr);  // Move instead of copy (efficient)
        if (maxChange < 1e-6) break;
    }
    return pr;
}
```

---

## STEP 6 — Interview Follow-Ups

```
Q: "How does Google handle 8 billion queries per day?"
A:
  8B/day = ~92K queries/sec.
  
  1. The inverted index is distributed across thousands of machines (shards).
     Each shard holds a portion of the index (by hash of term).
     Query: fan out to all shards → each returns local results → merge.
  
  2. Index is replicated 3× for availability and parallel serving.
  
  3. Caching: popular queries cached in Redis/memcached.
     "python tutorial" → cached result returned in < 1ms.
     Cache hit rate: ~80% (most queries are common).
  
  4. Two-phase retrieval:
     Phase 1 (retrieve): get top-1000 candidate docs from index (fast, simple scoring).
     Phase 2 (rerank): apply 200+ signals to top-1000 (expensive, full-featured scoring).
     This pipeline is faster than applying all signals to all candidates.

Q: "How do you handle the Index freshness problem?"
A:
  The inverted index is built from crawled pages. Crawling takes time.
  A page updated 5 minutes ago might not be in the index yet.
  
  TWO INDEX SYSTEM:
  1. Main index: comprehensive, refreshed every few days.
  2. Supplemental (Freshness) index: smaller, updated continuously.
  
  Query: search BOTH indexes, merge results.
  Fresh content: appears in freshness index within minutes.
  Historical content: in main index.
  
  Google publishes a new version of its index every 2-4 weeks (core update).
  Between updates: freshness index handles new content.

Q: "What's the difference between search and recommendation?"
A:
  Search: USER specifies what they want. Pull-based (user pulls results).
  Query: "python tutorial". Results are relevant to THAT query.
  
  Recommendation: SYSTEM guesses what user wants. Push-based.
  "You might also like..." based on past behavior, similar users.
  
  ML difference:
  Search: query-document relevance. Query is explicit signal.
  Recommendation: user-item interaction modeling. No explicit query.
  
  Architecture difference:
  Search: InvertedIndex + real-time query processing.
  Recommendation: Pre-computed user vectors, offline batch processing.
  
  Both use: collaborative filtering signals (users who searched X also searched Y).
  Google Search: "People also ask" = recommendation within search context.

Q: "How does autocomplete work?"
A:
  Data source: most popular past queries that start with the typed prefix.
  "py" → ["python", "python tutorial", "pytorch", "python download", ...]
  
  Data structure: TRIE (prefix tree)
  Every past query is stored in a trie. Each node has: children map + popularity count.
  Lookup: traverse trie with typed prefix → return top-K highest-popularity suggestions.
  
  Trie lookup: O(L) where L = length of typed prefix. Very fast.
  
  Personalized: blend global suggestions + user's own search history.
  "py" → ["pytorch" (you searched before), "python tutorial" (popular), ...]
  
  Updated: globally every hour (new popular queries), personalized real-time.
```


---

## STEP 8 — Extended Deep-Dives: Advanced Design Patterns in Practice

```
CONCURRENT ACCESS PATTERNS — THE SUBTLETIES:

  WHY ConcurrentHashMap.newKeySet() in Java:
    Set<String> followers = new HashSet<>();  // NOT thread-safe
    Thread A: followers.add("alice");
    Thread B: followers.add("bob");
    Result: potential data corruption. HashSet.add() is NOT atomic.
    
    Set<String> followers = ConcurrentHashMap.newKeySet();  // thread-safe
    Internally: ConcurrentHashMap<String, Boolean>. All operations atomic.
    Why not Collections.synchronizedSet()?
      synchronizedSet wraps with synchronized block.
      add() and remove(): one thread at a time. Works but LOW THROUGHPUT.
      ConcurrentHashMap.newKeySet(): lock-free reads via CAS (Compare-And-Swap).
      Much higher throughput for read-heavy access (followers list is read very often).
  
  THE READ-WRITE LOCK PATTERN (Java ReentrantReadWriteLock):
    Scenario: followers list accessed thousands of times per second for reads.
    Writing (follow/unfollow): rare (maybe 100 times/day for average user).
    
    synchronized(lock): allows ONLY ONE thread at a time — both reads AND writes exclusive.
    ReadWriteLock: multiple readers simultaneously. Only one writer at a time.
    
    private final ReadWriteLock lock = new ReentrantReadWriteLock();
    
    // Read: acquire read lock (multiple threads can hold read lock simultaneously)
    public int getFollowerCount() {
        lock.readLock().lock();
        try {
            return followers.size();  // can be read by 1000 threads simultaneously
        } finally {
            lock.readLock().unlock();
        }
    }
    
    // Write: acquire write lock (exclusive — waits for all readers to finish)
    public boolean follow(User target) {
        lock.writeLock().lock();
        try {
            return following.add(target.getId());
        } finally {
            lock.writeLock().unlock();
        }
    }
    
    Performance gain: 100× read throughput vs plain synchronized.
    Read-heavy workload (99% reads, 1% writes) → ReadWriteLock is dramatically faster.
    
    When NOT to use ReadWriteLock:
      Write-heavy workloads: write lock contention → worse than synchronized.
      Very short critical sections: overhead of RWLock > benefit.
      Rule of thumb: reads > 10× writes → ReadWriteLock wins.

ATOMIC OPERATIONS IN JAVA — WHEN TO USE WHAT:
  
  AtomicInteger vs volatile vs synchronized:
  
  volatile int counter = 0;
  counter++;  // NOT thread-safe! Three operations: read, increment, write.
  // Thread A reads 5, Thread B reads 5, A writes 6, B writes 6. Incremented ONCE. Wrong.
  
  AtomicInteger counter = new AtomicInteger(0);
  counter.incrementAndGet();  // THREAD-SAFE. Single atomic hardware instruction (LOCK ADD).
  
  int count = counter.get();  // Thread-safe read.
  counter.compareAndSet(expected, newValue);  // CAS: only updates if current == expected.
  
  When to use AtomicInteger:
    Single-field counter that only increments/decrements.
    Like: clickCount, likeCount, retryCount.
  
  When AtomicInteger is NOT enough:
    Need to update TWO related fields atomically.
    E.g., "transfer $100: decrease account A, increase account B" — need synchronized.
    AtomicInteger: each field is atomic, but the COMBINATION isn't. Race condition possible.
    Fix: synchronized block covering BOTH updates, or compare-and-swap loop.

IMMUTABILITY AS A CONCURRENCY TOOL:
  
  Location is a frozen dataclass (Python) / Java record.
  Immutable = no setters = shared freely between threads without locking.
  
  Why immutability is the BEST concurrency solution:
    No mutation → no race condition possible → no locks needed → faster.
  
  Make as many objects immutable as possible:
    All "value objects" (Location, MediaMeta, UrlEntry): immutable. ✓
    All "service objects" (UrlShortener, FeedService): mutable (have state). Use locks.
  
  In Java: use records (Java 16+) for immutable value objects.
  In C++: use const member variables + no setters.
  In Python: use @dataclass(frozen=True).
```

---

## STEP 9 — System Design Upgrade Paths

```
HOW THIS LLD EVOLVES TO PRODUCTION:

LEVEL 1: Single Process (current LLD)
  InMemoryRepository: dict in RAM.
  LRUCache: OrderedDict in process.
  Single thread or very limited concurrency.
  Scale: up to 100K entries. Suitable for demo.

LEVEL 2: Single Machine, Multiple Threads
  Replace dict with PostgreSQL + connection pool (psycopg2/asyncpg).
  Replace LRUCache with Redis (redisio library).
  Uvicorn/Gunicorn: 4 workers × 8 threads = 32 concurrent request handlers.
  Scale: millions of entries, thousands requests/sec.
  Code change: only change what gets INJECTED (Strategy Pattern saves us).
    repo = PostgresUrlRepository(db_pool)  # one line change
    cache = RedisCacheLayer(redis_client)  # one line change
    shortener = UrlShortener(repo, cache)  # zero changes to this class

LEVEL 3: Multi-Machine (Microservices)
  UrlShortener → ShortenService (containerized, stateless, scale horizontally).
  RedirectService → RedirectService (separate container, optimized for reads).
  PostgreSQL → PostgreSQL cluster (1 primary + 3 read replicas + Pgpool-II load balancer).
  Redis → Redis Cluster (6 nodes, 3 primary + 3 replica).
  API Gateway → Kong (handles auth, rate limiting, routing).
  Scale: millions of requests/sec. 99.99% availability.

LEVEL 4: Global Scale (bit.ly / TinyURL scale)
  Database → sharded PostgreSQL (10 shards × consistent hashing).
  CDN → Cloudflare (redirects served at CDN edge, < 5ms globally).
  Analytics → ClickHouse (50B click events/day, < 1s aggregation queries).
  Multi-region → US + EU + APAC (3 regions × full stack).
  Scale: 100M URLs, 10B redirects/day. < 10ms p99 globally.
  Code changes: none to core business logic. Only infra config changes.
  The LLD design held up to 100,000× scale increase. This is the power of good OOP design.

INTERVIEW TIP — HOW TO TRANSITION FROM LLD TO HLD:
  After showing LLD code, interviewer asks "how would this scale?"
  
  1. Identify the bottleneck (InMemoryRepository can't handle 578K reads/sec).
  2. Replace the specific component (not the entire system):
     "I'd replace InMemoryUrlRepository with a sharded PostgreSQL repository.
     The IUrlRepository interface means UrlShortener doesn't change at all."
  3. Discuss the HLD implications (sharding, caching, CDN) in terms of your LLD design.
  4. Show you understand the PROGRESSION from clean OOP to distributed systems.
  
  This answer demonstrates: LLD mastery + HLD thinking + evolutionary design mindset.
  MAANG interviewers specifically look for this progression.
```


---

## STEP 4 â€” Java Implementation (Full â€” Every Line Explained)

> **Enhanced Java section**: Complete, production-quality implementation matching Python depth. Every data structure, lock, and design pattern is annotated.

```java
// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
// Google Search Engine â€” Full Java LLD (every line explained)
//
// Java vs Python highlights:
//   â— PriorityQueue<T>  â€” O(log n) min-heap for URL frontier priority queue
//   â— ConcurrentHashMap â€” lock-striped thread-safe map for inverted index
//   â— ReentrantReadWriteLock â€” concurrent readers / exclusive writer
//   â— AtomicLong        â€” thread-safe document count / URL counter
//   â— record (Java 16+) â€” immutable value types (Document, SearchResult)
//   â— Stream API        â€” functional pipeline replaces Python comprehensions
//   â— TreeMap           â€” sorted map for posting list merges
// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.concurrent.locks.*;
import java.util.stream.*;

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// ENUMS
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

enum CrawlPriority { HIGH, MEDIUM, LOW }
// HIGH:   news sites, frequently changing pages (re-crawl every hour)
// MEDIUM: standard websites (re-crawl weekly)
// LOW:    rarely-updated long-tail pages (re-crawl monthly)


// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// DOMAIN MODELS â€” Immutable records (Java 16+)
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

/**
 * A URL waiting to be crawled.
 * WHY record? URL metadata is a pure value (no behavior beyond holding data).
 * record auto-generates: constructor, getters, equals/hashCode/toString.
 * Immutable by default â€” no thread-safety concerns when shared across threads.
 */
record CrawlUrl(
    String url,
    int    priority,   // Lower = higher priority (min-heap convention)
    int    depth,      // Hops from a seed URL (controls crawl depth limit)
    Instant discoveredAt
) implements Comparable<CrawlUrl> {

    // Compact constructor: validate fields before assignment (no `this.field =` needed in record)
    CrawlUrl {
        Objects.requireNonNull(url, "URL cannot be null");
        if (priority < 0) throw new IllegalArgumentException("Priority must be >= 0");
    }

    @Override
    public int compareTo(CrawlUrl other) {
        // PriorityQueue uses this to determine ordering.
        // Integer.compare(a, b): returns negative if a < b, 0 if a==b, positive if a > b.
        // Min-heap: smaller priority value = dequeued first = higher actual priority.
        return Integer.compare(this.priority, other.priority);
    }
}

/**
 * A crawled and parsed web document.
 * Immutable value type â€” safe to share between crawler, indexer, and ranker threads.
 */
record Document(
    String        id,          // URL (also serves as unique document ID)
    String        title,
    String        body,        // Cleaned text content (HTML stripped)
    List<String>  outboundLinks, // URLs found in <a href="..."> tags
    double        pageRank,    // Computed PageRank score (updated periodically)
    Instant       crawledAt
) {
    /** Parse whitespace-separated words from body, lowercase, min 3 chars. */
    public List<String> tokens() {
        if (body == null || body.isBlank()) return List.of();
        // List.of(): immutable list factory (Java 9+). More efficient than new ArrayList<>().

        return Arrays.stream(body.toLowerCase().split("\\W+"))
        // "\\W+" = one or more non-word characters (spaces, punctuation, newlines).
        // Equivalent to Python's re.split(r'\W+', body.lower()).
                .filter(t -> t.length() >= 3)
                // filter: keep only tokens with >= 3 characters (remove "a", "is", "of" noise).
                .distinct()
                // distinct(): removes duplicate tokens. Each term appears at most once per document.
                // Uses Object.equals/hashCode internally. O(n) time with a LinkedHashSet.
                .collect(Collectors.toUnmodifiableList());
                // Collectors.toUnmodifiableList(): returns immutable list. Java 10+.
    }

    /** Compute TF (Term Frequency) for a given term in this document. */
    public double tf(String term) {
        if (body == null || body.isBlank()) return 0.0;
        String[] words = body.toLowerCase().split("\\W+");
        long termCount = Arrays.stream(words)
                .filter(w -> w.equals(term))
                // filter: count exact matches of the term.
                .count();
                // Stream.count(): terminal operation â€” returns long (count of matching elements).
        return words.length == 0 ? 0.0 : (double) termCount / words.length;
        // TF = (occurrences of term in doc) / (total tokens in doc).
        // Cast termCount to double before division to avoid integer division truncation.
    }
}

/**
 * A single result returned to the user after search.
 */
record SearchResult(
    String  url,
    String  title,
    String  snippet,   // ~150-char excerpt showing context around matched terms
    double  score,     // Combined TF-IDF Ã— PageRank score
    Instant crawledAt
) implements Comparable<SearchResult> {

    @Override
    public int compareTo(SearchResult other) {
        // Higher score = better result = should come FIRST.
        // Double.compare(a, b): returns positive if a > b.
        // Negating: reversed() for descending order in PriorityQueue (max-heap).
        return Double.compare(other.score, this.score);
        // Note: comparing other.score vs this.score (reversed) = descending natural order.
    }
}

/**
 * A posting: one document's TF-IDF relevance for a specific term.
 * Stored in InvertedIndex posting lists.
 */
record Posting(String docId, double tfidf) implements Comparable<Posting> {
    @Override
    public int compareTo(Posting other) {
        return Double.compare(other.tfidf, this.tfidf); // Descending: highest TF-IDF first
    }
}


// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// URL FRONTIER  (priority queue of URLs to crawl)
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class UrlFrontier {
    // PriorityQueue: min-heap. poll() returns the element with the LOWEST priority value.
    // We assign lower numeric values to higher-priority URLs (news=1, standard=5, long-tail=10).
    // Thread-safety: PriorityQueue is NOT thread-safe â†’ we wrap with synchronized methods.
    //
    // WHY NOT PriorityBlockingQueue?
    //   PriorityBlockingQueue is thread-safe but has no built-in dedup.
    //   We need to track visited URLs AND maintain ordering â†’ use synchronized PriorityQueue + HashSet.
    private final PriorityQueue<CrawlUrl> queue   = new PriorityQueue<>();
    private final Set<String>             visited = new HashSet<>();
    // visited: tracks URLs we've already crawled or queued. Prevents re-crawling the same URL.
    // HashSet: O(1) contains/add. NOT thread-safe (accessed only within synchronized blocks).

    private final ReentrantLock lock = new ReentrantLock();
    // ReentrantLock vs synchronized:
    //   Both provide mutual exclusion (one thread at a time).
    //   ReentrantLock: supports tryLock(timeout), lockInterruptibly(), fair ordering (optional).
    //   synchronized: simpler syntax, JVM-optimized for low-contention cases.
    //   Here: either works. ReentrantLock chosen for its explicit unlock-in-finally safety pattern.

    /** Add URL to frontier if not already visited. Returns true if added. */
    public boolean add(String url, int priority, int depth) {
        lock.lock();
        try {
            if (visited.contains(url)) return false;  // Dedup: skip already-queued/crawled URLs
            visited.add(url);
            queue.offer(new CrawlUrl(url, priority, depth, Instant.now()));
            // PriorityQueue.offer(element): insert into heap. O(log n) â€” heap re-orders.
            // offer() never throws (unlike add() which throws if capacity exceeded in bounded queues).
            // Our PriorityQueue is unbounded â†’ no capacity issue, but offer() is the safer idiom.
            return true;
        } finally {
            lock.unlock();  // ALWAYS in finally â€” release lock even if exception is thrown
        }
    }

    /** Get the next highest-priority URL to crawl. Returns null if frontier is empty. */
    public CrawlUrl poll() {
        lock.lock();
        try {
            return queue.poll();
            // PriorityQueue.poll(): removes and returns the head (lowest priority value = highest priority URL).
            // Returns null if queue is empty (does NOT throw â€” unlike remove() which throws).
            // O(log n): after removal, heap re-orders to restore min-heap property.
        } finally {
            lock.unlock();
        }
    }

    public int size() {
        lock.lock();
        try { return queue.size(); }
        finally { lock.unlock(); }
    }

    public boolean isEmpty() {
        lock.lock();
        try { return queue.isEmpty(); }
        finally { lock.unlock(); }
    }
}


// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// INVERTED INDEX  (the core data structure of any search engine)
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class InvertedIndex {
    /**
     * THE INVERTED INDEX:
     * Maps each term â†’ sorted list of Postings (docId + TF-IDF score).
     * "Inverted" because we invert the document-centric view:
     *   Normal:   Document â†’ [terms in document]
     *   Inverted: Term     â†’ [documents containing the term]
     *
     * Example:
     *   "java" â†’ [(doc1, tfidf=0.8), (doc3, tfidf=0.5), (doc7, tfidf=0.2)]
     *   "design" â†’ [(doc2, tfidf=0.9), (doc1, tfidf=0.6)]
     *
     * Query "java design" â†’ intersect posting lists â†’ rank by combined TF-IDF.
     */
    private final ConcurrentHashMap<String, List<Posting>> index = new ConcurrentHashMap<>();
    // ConcurrentHashMap: allows concurrent reads (no lock) + lock-striped writes.
    // Each term's posting list can be read by many query threads simultaneously.
    // Adding a new term (new key): ConcurrentHashMap handles atomically.

    private final ConcurrentHashMap<String, Document>     documents = new ConcurrentHashMap<>();
    // Store full documents for snippet generation. Key: docId (= URL).

    private final AtomicLong docCount = new AtomicLong(0);
    // AtomicLong: thread-safe 64-bit counter. Incremented each time a new document is indexed.
    // Used in IDF calculation: IDF = log(total_docs / docs_containing_term).
    // AtomicLong.get(): single volatile read. AtomicLong.incrementAndGet(): single CAS instruction.

    // Per-term lock for modifying posting lists (finer granularity than one global lock)
    private final ConcurrentHashMap<String, ReentrantReadWriteLock> termLocks
            = new ConcurrentHashMap<>();

    private ReentrantReadWriteLock getLock(String term) {
        return termLocks.computeIfAbsent(term, k -> new ReentrantReadWriteLock());
        // computeIfAbsent: atomically create a new lock for a term if none exists.
        // Multiple threads calling for the same new term â†’ only one lock is created.
    }

    /** Index a document: compute TF-IDF for each term and update posting lists. */
    public void index(Document doc) {
        documents.put(doc.id(), doc);
        long n = docCount.incrementAndGet();
        // incrementAndGet(): atomically adds 1 and returns the new value (new total doc count).
        // Using this as N in IDF formula: IDF(t) = log(N / df(t)).

        // Compute TF for each unique token in this document
        List<String> tokens = doc.tokens();
        for (String term : tokens) {
            double tf = doc.tf(term);

            // IDF approximation: use current docCount as N.
            // In a real search engine: IDF is recomputed periodically in a background batch job.
            // Here: approximate with current N (may be slightly inaccurate for early docs).
            long df = getDocumentFrequency(term);  // How many docs already contain this term
            // IDF = log((N + 1) / (df + 1)) â€” add 1 to avoid division by zero (Laplace smoothing)
            double idf = Math.log((n + 1.0) / (df + 1.0));
            // Math.log(): natural logarithm (base e). Both Python's math.log and Java's Math.log are base e.
            double tfidf = tf * idf;

            // Create the posting for this document
            Posting posting = new Posting(doc.id(), tfidf);

            // Update the posting list for this term (thread-safe write)
            ReentrantReadWriteLock.WriteLock wl = getLock(term).writeLock();
            wl.lock();
            try {
                // computeIfAbsent: get existing list or create new ArrayList for new term. Atomic.
                List<Posting> postings = index.computeIfAbsent(term, k -> new ArrayList<>());
                postings.add(posting);
                // Keep posting list sorted: highest TF-IDF first (best documents for this term).
                postings.sort(Comparator.naturalOrder());
                // Comparator.naturalOrder(): uses Posting.compareTo() â†’ descending TF-IDF (as defined above).
                // Sort is O(n log n). For large indexes: use SortedList or skip sort (merge at query time).
            } finally {
                wl.unlock();
            }
        }
    }

    /** Get posting list for a term (thread-safe read). */
    public List<Posting> getPostings(String term) {
        List<Posting> postings = index.get(term);
        if (postings == null) return List.of();  // Term not in index â†’ empty list

        ReentrantReadWriteLock.ReadLock rl = getLock(term).readLock();
        rl.lock();
        try {
            return new ArrayList<>(postings);
            // Return a COPY (defensive copy). Caller can iterate without holding the lock.
            // If we returned the live list: caller iterates â†’ writer modifies â†’ ConcurrentModificationException.
        } finally {
            rl.unlock();
        }
    }

    /** Get document by ID (for snippet generation). */
    public Optional<Document> getDocument(String docId) {
        return Optional.ofNullable(documents.get(docId));
        // Optional.ofNullable: wraps the result, which may be null if doc not found.
    }

    public long getTotalDocs() {
        return docCount.get();  // Volatile read â€” current total document count
    }

    /** How many documents in the index contain this term? (document frequency) */
    private long getDocumentFrequency(String term) {
        List<Posting> postings = index.get(term);
        // Reading from ConcurrentHashMap without a lock: safe because ConcurrentHashMap
        // guarantees that get() always returns a consistent (if potentially stale by a few ms) value.
        return (postings == null) ? 0 : postings.size();
    }
}


// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// QUERY PROCESSOR  (parse + expand the search query)
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class QueryProcessor {
    /**
     * Tokenize and clean a user's search query.
     * Same preprocessing as document indexing â†’ tokens match index terms.
     */
    public List<String> tokenize(String query) {
        if (query == null || query.isBlank()) return List.of();

        return Arrays.stream(query.toLowerCase().trim().split("\\W+"))
                .filter(t -> t.length() >= 2)  // Keep terms with >= 2 chars ("of" out, "go" in)
                .distinct()                    // Deduplicate: "java java" â†’ ["java"]
                .collect(Collectors.toList());
    }

    /**
     * Build a query plan: which terms are MUST-HAVE vs SHOULD-HAVE.
     * Simple version: all terms are MUST-HAVE (AND query).
     * Real Google: complex boolean algebra + query expansion via synonym/spelling correction.
     */
    public Map<String, Boolean> buildQueryPlan(String query) {
        // Map: term â†’ isMandatory (true = AND, false = OR/optional)
        List<String> tokens = tokenize(query);
        Map<String, Boolean> plan = new LinkedHashMap<>();
        // LinkedHashMap: maintains insertion order (important for result display).
        // vs HashMap: no ordering guarantee. vs TreeMap: alphabetical order (not what we want here).

        for (String token : tokens) {
            plan.put(token, true);  // All terms mandatory (AND semantics)
        }
        return plan;
    }
}


// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// SEARCH ENGINE  (facade orchestrating all components)
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class SearchEngine {
    private final InvertedIndex   invertedIndex  = new InvertedIndex();
    private final UrlFrontier     frontier       = new UrlFrontier();
    private final QueryProcessor  queryProcessor = new QueryProcessor();

    // PageRank scores (computed externally via batch job â€” not in this LLD scope)
    private final ConcurrentHashMap<String, Double> pageRankScores = new ConcurrentHashMap<>();

    /**
     * Index a web document. Called by the web crawler after parsing a page.
     * Thread-safe: InvertedIndex handles concurrent indexing.
     */
    public void indexDocument(Document doc) {
        invertedIndex.index(doc);
        pageRankScores.putIfAbsent(doc.id(), 1.0);
        // putIfAbsent: insert default PageRank of 1.0 if this docId not yet ranked.
        // "putIfAbsent" vs "put": doesn't overwrite if a real PageRank was already assigned.
    }

    /**
     * Execute a search query. Returns top-K results ranked by TF-IDF Ã— PageRank.
     *
     * ALGORITHM:
     * 1. Tokenize query: "java design patterns" â†’ ["java", "design", "patterns"]
     * 2. For each term: get posting list (docId â†’ TF-IDF)
     * 3. AND semantics: keep only docs that appear in ALL posting lists
     * 4. Score: TF-IDF (sum of all terms) Ã— PageRank
     * 5. Sort by score descending, return top-K
     */
    public List<SearchResult> search(String query, int topK) {
        List<String> terms = queryProcessor.tokenize(query);
        if (terms.isEmpty()) return List.of();

        // â”€â”€ Step 1: Get posting lists for all query terms â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        Map<String, List<Posting>> termPostings = new HashMap<>();
        for (String term : terms) {
            List<Posting> postings = invertedIndex.getPostings(term);
            if (postings.isEmpty()) {
                // If ANY term has zero results â†’ AND query returns no results.
                // Real Google: fall back to OR semantics. We keep it simple here.
                return List.of();
            }
            termPostings.put(term, postings);
        }

        // â”€â”€ Step 2: AND intersection â€” find docs present in ALL posting lists â”€
        // Start with the smallest posting list (optimization: fewer docs to intersect against).
        List<Posting> smallest = termPostings.values().stream()
                .min(Comparator.comparingInt(List::size))
                // Comparator.comparingInt(List::size): compare posting lists by their size.
                // List::size is a method reference: l -> l.size().
                // min(): returns Optional<List<Posting>> of the smallest list.
                .orElse(List.of());
                // orElse: return empty list if stream was empty (shouldn't happen â€” checked above).

        // docId â†’ cumulative TF-IDF across all query terms
        Map<String, Double> docScores = new HashMap<>();

        for (Posting p : smallest) {
            // Check if this doc appears in ALL other posting lists
            boolean inAll = termPostings.entrySet().stream()
                    // Stream over (term, postingList) pairs
                    .filter(e -> !e.getKey().equals(terms.get(0)))
                    // Skip the first term's list (we're already iterating it)
                    .allMatch(e -> e.getValue().stream().anyMatch(op -> op.docId().equals(p.docId())));
                    // allMatch: true if ALL posting lists contain a Posting with this docId.
                    // anyMatch: true if at least one Posting in the list has the matching docId.
                    // Nested streams: O(numTerms Ã— postingListSize). In production: use sorted merge.

            if (inAll) {
                // Sum TF-IDF across all terms for this document
                double totalTfIdf = termPostings.values().stream()
                        .flatMap(List::stream)
                        // flatMap: flatten List<List<Posting>> â†’ Stream<Posting>
                        // List::stream is a method reference: list -> list.stream()
                        .filter(op -> op.docId().equals(p.docId()))
                        .mapToDouble(Posting::tfidf)
                        // mapToDouble: transform Posting â†’ double (extracts tfidf field).
                        // Returns DoubleStream (specialized, avoids boxing to Double objects).
                        .sum();
                        // DoubleStream.sum(): sum all double values. Terminal operation.
                docScores.put(p.docId(), totalTfIdf);
            }
        }

        // â”€â”€ Step 3: Multiply by PageRank and build SearchResult objects â”€â”€â”€â”€
        // PriorityQueue as a max-heap for top-K extraction.
        // We want the K HIGHEST scores. Use min-heap of size K: evict the smallest if over K.
        PriorityQueue<SearchResult> topKHeap = new PriorityQueue<>(topK + 1, Comparator.naturalOrder());
        // PriorityQueue(capacity, comparator): initial capacity + ordering.
        // Comparator.naturalOrder() uses SearchResult.compareTo() â†’ descending score.

        for (Map.Entry<String, Double> entry : docScores.entrySet()) {
            String docId     = entry.getKey();
            double tfidf     = entry.getValue();
            double pageRank  = pageRankScores.getOrDefault(docId, 1.0);
            // getOrDefault(key, default): returns 1.0 if this doc has no PageRank score yet.
            double finalScore = tfidf * pageRank;
            // FINAL RANKING FORMULA: TF-IDF Ã— PageRank
            // High TF-IDF: the query terms appear frequently and prominently in this doc.
            // High PageRank: many important pages link to this doc â†’ authoritative.
            // Both factors together = likely a relevant AND authoritative result.

            Optional<Document> doc = invertedIndex.getDocument(docId);
            String snippet = doc.map(d -> generateSnippet(d.body(), terms))
                    // Optional.map(function): if present, apply function; return Optional of result.
                    // Returns Optional<String>. If doc is empty â†’ Optional.empty().
                    .orElse("No snippet available.");
                    // orElse: default value if Optional is empty.
            String title = doc.map(Document::title).orElse(docId);

            topKHeap.offer(new SearchResult(docId, title, snippet, finalScore, Instant.now()));
        }

        // Extract results from the heap in order (highest score first):
        List<SearchResult> results = new ArrayList<>();
        while (!topKHeap.isEmpty()) {
            results.add(topKHeap.poll());
            // poll(): removes and returns the head (highest score since we used reversed comparator).
        }
        // The heap naturally orders results by score (highest first due to compareTo implementation).
        return results;
    }

    /**
     * Generate a snippet: find the first occurrence of any query term in the body,
     * return the surrounding ~150 characters as context.
     */
    private String generateSnippet(String body, List<String> terms) {
        if (body == null) return "";
        String lower = body.toLowerCase();
        // Find the earliest position of any query term in the body
        int pos = terms.stream()
                .mapToInt(t -> lower.indexOf(t))
                // mapToInt: transform String â†’ int (index of term in body). Returns IntStream.
                // String.indexOf(str): returns the index of first occurrence, or -1 if not found.
                .filter(i -> i >= 0)
                // filter: remove -1 values (terms not found in body)
                .min()
                // IntStream.min(): returns OptionalInt (minimum value, or empty if no elements).
                .orElse(0);
                // orElse(0): if no term found, start snippet at beginning of body.

        int start = Math.max(0, pos - 30);
        // Show 30 chars before the matched term for context.
        // Math.max(0, ...): don't go before the start of the string.
        int end   = Math.min(body.length(), start + 150);
        // Show 150 chars total. Math.min: don't go past the end of the string.
        return (start > 0 ? "..." : "") + body.substring(start, end) + (end < body.length() ? "..." : "");
        // Add "..." prefix if we didn't start at the beginning (shows context was truncated).
        // Ternary operator: condition ? valueIfTrue : valueIfFalse.
    }

    /** Add a URL to the crawl frontier. */
    public boolean addToCrawlQueue(String url, CrawlPriority priority) {
        int p = switch (priority) {
            // Java 14+ switch expression (value-producing switch â€” replaces switch statement).
            // Each case produces a value directly (no break needed).
            case HIGH   -> 1;
            case MEDIUM -> 5;
            case LOW    -> 10;
        };
        return frontier.add(url, p, 0);  // depth=0 for seed URLs
    }

    /** Update PageRank score for a document (called by PageRank batch job). */
    public void updatePageRank(String docId, double score) {
        pageRankScores.put(docId, score);
        // ConcurrentHashMap.put() is thread-safe. No additional lock needed.
    }

    /** Get all pending URLs for the crawler (batch fetch for crawler workers). */
    public List<CrawlUrl> getNextBatch(int batchSize) {
        List<CrawlUrl> batch = new ArrayList<>(batchSize);
        for (int i = 0; i < batchSize && !frontier.isEmpty(); i++) {
            CrawlUrl next = frontier.poll();
            if (next != null) batch.add(next);
        }
        return batch;
    }
}


// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// PAGERANK CALCULATOR  (simplified iterative computation)
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class PageRankCalculator {
    private static final double DAMPING    = 0.85;  // Standard PageRank damping factor
    private static final double CONVERGENCE = 0.001; // Stop when change < 0.1%
    // DAMPING FACTOR (d = 0.85):
    //   Models the probability that a random web surfer follows a link (85%)
    //   vs teleports to a random page (15%). Prevents rank sink (dangling nodes).
    //   PR(page) = (1 - d) + d Ã— Î£ (PR(linking_page) / out_degree(linking_page))

    /**
     * Compute PageRank iteratively until convergence.
     * @param adjacency: outbound links. Key: sourceUrl, Value: list of target URLs.
     * @return Map of docId â†’ PageRank score.
     */
    public Map<String, Double> compute(Map<String, List<String>> adjacency, int maxIterations) {
        Set<String> allNodes = new HashSet<>(adjacency.keySet());
        // Add all target nodes (some pages are linked-to but don't have outbound links):
        adjacency.values().forEach(links -> allNodes.addAll(links));
        // Set.addAll(): adds all elements from collection. Duplicates are ignored (Set semantics).

        int n = allNodes.size();
        if (n == 0) return Map.of();  // Map.of(): immutable empty map (Java 9+)

        // Initialize: all pages start with equal PageRank = 1/N
        Map<String, Double> ranks = new HashMap<>();
        allNodes.forEach(node -> ranks.put(node, 1.0 / n));
        // Map.forEach(BiConsumer): iterates all (key, value) pairs. Lambda receives (node, initialRank).

        for (int iteration = 0; iteration < maxIterations; iteration++) {
            Map<String, Double> newRanks = new HashMap<>();

            // Initialize all nodes with the teleport component (1 - d) / N
            allNodes.forEach(node -> newRanks.put(node, (1.0 - DAMPING) / n));

            // Distribute rank from each node to its outbound links
            for (Map.Entry<String, List<String>> entry : adjacency.entrySet()) {
                String       source = entry.getKey();
                List<String> links  = entry.getValue();
                if (links.isEmpty()) continue;  // Dangling node: no outbound links (skip)

                double rankShare = DAMPING * ranks.get(source) / links.size();
                // This node's rank is split equally among its outbound links.
                // DAMPING Ã— PR(source) / out_degree(source)

                for (String target : links) {
                    if (allNodes.contains(target)) {
                        // merge(key, delta, mergeFunction): atomically add delta to existing value.
                        // merge(k, v, f): if key absent â†’ put(k, v); if present â†’ put(k, f(old, v)).
                        // Here: f = Double::sum â†’ newRanks[target] += rankShare
                        newRanks.merge(target, rankShare, Double::sum);
                        // Double::sum is a method reference for the BinaryOperator (a, b) -> a + b.
                        // Cleaner than: newRanks.put(target, newRanks.getOrDefault(target, 0.0) + rankShare)
                    }
                }
            }

            // Check convergence: if max change in any node's rank < threshold â†’ stop
            double maxDelta = allNodes.stream()
                    .mapToDouble(node -> Math.abs(newRanks.getOrDefault(node, 0.0)
                                                 - ranks.getOrDefault(node, 0.0)))
                    // mapToDouble: extract double values (absolute rank change per node).
                    .max()
                    // DoubleStream.max(): returns OptionalDouble (max value across all nodes).
                    .orElse(0.0);
                    // orElse: if stream was empty (no nodes) â†’ delta = 0.

            ranks.putAll(newRanks);
            // Map.putAll(): copies all (key, value) from newRanks into ranks. Overwrites existing keys.

            if (maxDelta < CONVERGENCE) {
                System.out.printf("PageRank converged after %d iterations%n", iteration + 1);
                break;  // Early exit when converged. Typical: 50-100 iterations for real web graphs.
            }
        }

        return Collections.unmodifiableMap(ranks);
        // Return immutable view: caller can read but cannot modify the ranks map.
    }
}


// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// DEMO
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class GoogleSearchJavaDemo {
    public static void main(String[] args) {
        SearchEngine engine = new SearchEngine();

        // â”€â”€ Seed the crawler â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        engine.addToCrawlQueue("https://docs.oracle.com/javase/tutorial/", CrawlPriority.HIGH);
        engine.addToCrawlQueue("https://www.baeldung.com/java-design-patterns", CrawlPriority.HIGH);
        engine.addToCrawlQueue("https://refactoring.guru/design-patterns", CrawlPriority.MEDIUM);

        // â”€â”€ Simulate crawled documents â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        Document doc1 = new Document(
            "https://docs.oracle.com/javase/tutorial/",
            "Java Tutorials â€” Oracle",
            "Java is an object-oriented programming language. " +
            "Java design patterns like singleton factory observer strategy " +
            "are essential for software engineering. Java concurrent programming " +
            "uses locks and atomic operations for thread safety.",
            List.of("https://docs.oracle.com/javase/8/docs/api/"),
            1.0, Instant.now()
        );
        Document doc2 = new Document(
            "https://www.baeldung.com/java-design-patterns",
            "Java Design Patterns â€” Baeldung",
            "Design patterns are reusable solutions to common software design problems. " +
            "The singleton pattern ensures only one instance of a class exists in Java. " +
            "Observer pattern enables event-driven programming in Java applications. " +
            "Strategy pattern allows swapping algorithms at runtime.",
            List.of("https://refactoring.guru/design-patterns"),
            0.8, Instant.now()
        );
        Document doc3 = new Document(
            "https://refactoring.guru/design-patterns",
            "Design Patterns â€” Refactoring Guru",
            "Catalog of design patterns in software engineering. " +
            "Creational patterns: factory method, abstract factory, singleton, builder, prototype. " +
            "Structural: adapter, decorator, proxy, composite. " +
            "Behavioral: observer, strategy, command, template method, iterator.",
            List.of(),
            1.2, Instant.now()
        );

        engine.indexDocument(doc1);
        engine.indexDocument(doc2);
        engine.indexDocument(doc3);

        // â”€â”€ Update PageRank scores (normally from batch job) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        engine.updatePageRank(doc1.id(), 1.5);   // High authority (Oracle)
        engine.updatePageRank(doc2.id(), 1.0);   // Good authority (Baeldung)
        engine.updatePageRank(doc3.id(), 1.3);   // Good authority (Refactoring Guru)

        // â”€â”€ Standalone PageRank computation demo â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        PageRankCalculator prCalc = new PageRankCalculator();
        Map<String, List<String>> adjacency = Map.of(
            doc1.id(), doc1.outboundLinks(),
            doc2.id(), doc2.outboundLinks(),
            doc3.id(), doc3.outboundLinks()
        );
        // Map.of(k1, v1, k2, v2, ...): immutable map factory (Java 9+). Up to 10 entries.
        Map<String, Double> pageRanks = prCalc.compute(adjacency, 100);
        System.out.println("\n--- Computed PageRanks ---");
        pageRanks.forEach((url, score) ->
            System.out.printf("  %.2f  %s%n", score,
                              url.substring(0, Math.min(50, url.length()))));
        // Map.forEach: iterates all (key, value) pairs. Printf formats: %.2f = 2 decimal places.

        // â”€â”€ Search queries â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        System.out.println("\n--- Search: 'java design patterns' ---");
        List<SearchResult> results = engine.search("java design patterns", 5);
        results.forEach(r -> System.out.printf(
            "  Score=%.3f  %s%n    %s%n%n",
            r.score(), r.title(), r.snippet().substring(0, Math.min(80, r.snippet().length()))
        ));

        System.out.println("--- Search: 'singleton observer java' ---");
        engine.search("singleton observer java", 3)
              .forEach(r -> System.out.printf("  [%.3f] %s%n", r.score(), r.title()));

        System.out.println("\n--- Crawl Queue ---");
        List<CrawlUrl> batch = engine.getNextBatch(5);
        batch.forEach(cu -> System.out.printf("  Priority=%d: %s%n", cu.priority(), cu.url()));
    }
}
```

---

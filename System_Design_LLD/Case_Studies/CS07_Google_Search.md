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

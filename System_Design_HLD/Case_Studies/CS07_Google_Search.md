# CS07 — Google Search at Scale

## Core Requirements

**Functional:**
- Crawl the web (billions of pages)
- Index content (full-text search)
- Rank results by relevance
- Return results in < 200ms
- Handle 8.5 billion queries/day

**Non-functional:**
- Freshness: new pages indexed in hours, popular pages in minutes
- Quality: rank spam below legitimate content
- Scale: index 100+ billion pages, petabytes of data
- Global: serve from closest region, all languages

---

## High-Level Architecture

```
┌─────────────────────────────────────────────┐
│                Web                          │
└────────────────┬────────────────────────────┘
                 │  URLs to crawl
                 ▼
         ┌──────────────┐
         │  URL Frontier │  Priority queue of URLs to fetch
         └──────┬───────┘
                │
                ▼
         ┌──────────────┐
         │   Crawlers   │  Fetch web pages (distributed)
         └──────┬───────┘
                │  raw HTML
                ▼
         ┌──────────────┐
         │    Parser    │  Extract text, links, metadata
         └──────┬───────┘
         ┌──────┴───────┐
         │              │
         ▼              ▼
   ┌─────────┐   ┌──────────────┐
   │ Link    │   │  Content     │
   │ Extractor│   │  Store (raw) │
   └────┬────┘   └──────────────┘
        │
        ▼
   ┌──────────┐
   │ Indexer  │  Build inverted index
   └────┬─────┘
        │
        ▼
   ┌──────────┐
   │ Index    │  Serving index (sharded)
   └────┬─────┘
        │
        ▼
   ┌──────────────┐
   │  Query       │  Parse query, lookup index, rank
   │  Processor   │
   └──────────────┘
```

---

## Web Crawler

### URL Frontier (Priority Queue)
```
URLs ranked by:
- Priority (PageRank / importance of linking page)
- Freshness (last crawl time → recrawl popular pages more)
- Politeness (robots.txt, crawl delay per domain)

Implementation:
- Multiple priority queues (high/medium/low)
- Per-domain queues (politeness — don't hammer one server)
- Bloom filter for "already visited" deduplication (billion URLs)
```

```python
class URLFrontier:
    def __init__(self):
        self.bloom = BloomFilter(capacity=10**9, error_rate=0.001)
        self.priority_queues = {
            'high': deque(),
            'medium': deque(),
            'low': deque()
        }

    def add_url(self, url, priority):
        if url in self.bloom:
            return  # already seen
        self.bloom.add(url)
        self.priority_queues[priority].append(url)
```

### Distributed Crawlers
- Thousands of crawler machines
- Each fetches, parses, and extracts links
- Respect robots.txt, crawl-delay
- Handle redirects, canonical URLs
- Download timeout: 5 seconds
- User-Agent: Googlebot

### URL Deduplication
- Bloom filter (probabilistic) — O(1) check, ~10 bits/URL
- Fingerprint/SimHash for near-duplicate content detection

---

## Inverted Index

**The core of search:**

```
Normal: Document → Words
Inverted: Word → Documents (with positions)

Index entry:
"python" → [(doc_id=5, pos=[12,45,102]), (doc_id=19, pos=[3,88]), ...]
```

```python
# Building inverted index
def build_index(documents):
    index = defaultdict(list)  # word → [(doc_id, positions)]

    for doc_id, text in enumerate(documents):
        words = tokenize(text)          # lowercase, remove stopwords
        stems = [stem(w) for w in words]  # "running" → "run"

        word_positions = defaultdict(list)
        for pos, word in enumerate(stems):
            word_positions[word].append(pos)

        for word, positions in word_positions.items():
            index[word].append((doc_id, positions))

    return index

# Serving: merge posting lists
def search(query, index):
    terms = [stem(t) for t in query.lower().split()]
    posting_lists = [set(doc_id for doc_id, _ in index.get(t, []))
                     for t in terms]
    # AND: intersection of all posting lists
    return set.intersection(*posting_lists) if posting_lists else set()
```

### Index Sharding (at Google scale)

**Document-based sharding:**
- Shard 1: doc_ids 0-100M
- Shard 2: doc_ids 100M-200M
- Query hits ALL shards in parallel → merge results

**Term-based sharding:**
- Shard 1: terms A-M
- Shard 2: terms N-Z
- Complex for multi-term queries (need to talk to multiple shards)

**Google uses:** Hybrid — document-based with term-based optimizations.

---

## PageRank

```
PR(A) = (1-d) + d * sum(PR(B)/out_links(B) for B in pages_linking_to_A)
d = damping factor = 0.85
```

- Iterative algorithm — run until convergence
- At scale: Pregel (Google's graph processing) or MapReduce
- Modern Google: PageRank is one of 200+ ranking signals

---

## Query Processing

```
User query: "python interview questions"
    ↓
Query Understanding:
  - Spell correction: "questins" → "questions"
  - Synonym expansion: "python" → "python3, CPython"
  - Intent: informational (list format expected)
    ↓
Query Rewriting: boolean → efficient form
    ↓
Index Lookup: fetch posting lists for each term
    ↓
Ranking (SERP):
  - TF-IDF: term frequency × inverse doc frequency
  - PageRank: link authority
  - Freshness: newer pages ranked higher for news queries
  - User signals: click-through rate, dwell time
  - ML model (RankBrain/BERT): semantic understanding
    ↓
Results served < 200ms
```

### TF-IDF
```
TF(t, d) = count of term t in doc d / total terms in d
IDF(t) = log(total docs / docs containing t)
TF-IDF = TF × IDF
```

---

## Freshness — Crawl Scheduling

```
Popular pages (Google.com): crawl every few minutes
News articles: crawl every hour
Long-tail pages: crawl every few weeks

Signals for recrawl priority:
- Link velocity (how many new pages link to it)
- Historical change frequency
- Sitemap change dates
- Ping/Fetch-as-Googlebot requests
```

---

## Anti-Spam

- Link farm detection (sudden spike in backlinks)
- Content fingerprinting (near-duplicate detection via SimHash)
- Manual quality raters
- Penguin (links), Panda (content quality) algorithms

---

## Key Numbers

| Metric | Value |
|--------|-------|
| Pages in index | 100B+ |
| Daily queries | 8.5B |
| Query latency | < 200ms |
| New pages indexed | hours to days |
| Crawler machines | thousands |
| Index size | hundreds of PB |

---

## Interview Focus Points

1. **Bloom filter for URL dedup** — why probabilistic is fine (false positive → skip a URL, acceptable)
2. **Inverted index** — draw it on whiteboard, explain posting list merge
3. **Sharding the index** — document-based vs term-based, why document-based at scale
4. **PageRank** — iterative convergence, how links = votes
5. **Freshness vs crawl budget** — tradeoff between crawling more and server politeness
6. **MapReduce / Pregel** — how PageRank is computed at web scale

# CS07: Design Google Search (Web Search Engine)
## Full HLD Case Study | MAANG Interview Ready

---

## STEP 1 — Requirements Clarification

```
"This is a massive system. Let me first nail requirements and scope."

FUNCTIONAL:
  1. Web Crawler: discover and crawl billions of web pages continuously
  2. Indexing: build a searchable full-text index of crawled pages
  3. Ranking: given a query, rank results by relevance (PageRank + ML signals)
  4. Query serving: return top results for user query in < 200ms
  5. Autocomplete / typeahead: suggest queries as user types
  6. Special features: Knowledge Graph cards, image search, news, maps (out of scope)
  7. Spell correction: "googel" → "google"
  8. Personalization: user's search history influences ranking (minor scope here)

NON-FUNCTIONAL:
  - Scale: 8.5 billion queries/day → ~100,000 queries/sec avg, 400K/sec peak
  - Index: 100+ billion pages
  - Crawl freshness: popular pages re-crawled within minutes; long-tail within weeks
  - Query latency: < 200ms p99 end-to-end (including network)
  - Availability: 99.999% (5 nines — Google is the internet's front door)
  - Global: 190+ countries, all languages
  - Storage: hundreds of petabytes of index data

OUT OF SCOPE:
  - Ads auction (separate multi-billion system)
  - Image/Video/News/Maps search (separate pipelines)
  - Chrome browser integration
```

---

## STEP 2 — Back-of-Envelope Estimation

```
CRAWLING:
  Target: 100B pages. Re-crawl popular pages daily, long-tail monthly.
  Average page size: 500 KB HTML.
  Daily crawl volume (assume 5B pages/day recrawled):
    5B × 500 KB = 2.5 PB/day of raw HTML fetched.
    Crawler bandwidth: 2.5 PB / 86,400 = 29 GB/sec sustained.
    → Thousands of crawler machines needed.
  
  Crawl rate per domain (politeness):
    Max 1 request/domain every 30 seconds.
    But Google has 100B pages across billions of domains.
    Most domains: 1-10 pages each. Can crawl fast per domain.
    Popular domains (Wikipedia, NYT): 1M+ pages each → crawl queue needed.

INDEX SIZE:
  100B pages × avg 1,000 unique words/page = 100T word occurrences.
  After deduplication and stopword removal: ~10T index entries.
  Each entry: (term_id:4B, doc_id:8B, position:4B, freq:4B) = 20B.
  Raw index: 10T × 20B = 200 TB.
  Compressed (delta encoding, varint): ~40-80 TB.
  Google's actual index: hundreds of TB (many replicas + additional features).

QUERY SERVING:
  100,000 queries/sec avg. Peak 400K/sec.
  Per query: lookup posting lists for 3-4 terms → intersect → rank top-1000 → return top-10.
  
  Each term lookup: O(log N) in B-tree index. ~5-10ms per lookup.
  4 lookups × 10ms parallel = 10ms for lookups.
  Ranking top-1000 results: 5ms.
  Total: ~15-20ms internal → < 200ms with network/rendering overhead.

AUTOCOMPLETE:
  8.5B queries/day. Users type avg 4 characters before selecting suggestion.
  8.5B × 4 keystrokes = 34B autocomplete requests/day.
  34B ÷ 86,400 = 393K autocomplete requests/sec.
  Must be < 50ms (inline typing suggestions).
```

---

## STEP 3 — High-Level Architecture

```
THE FOUR SUBSYSTEMS:

  1. Crawler (offline, continuous): discovers and downloads web pages
  2. Indexer (offline, batch + streaming): builds inverted index from crawled pages
  3. Query Processor (online, real-time): handles user queries
  4. Ranking Engine (online): scores and sorts results for a query

FULL ARCHITECTURE:

  ┌──────────────────────────────────────────────────────────────────────────────┐
  │                              THE WEB (100B+ pages)                           │
  └───────────────────────────────────┬──────────────────────────────────────────┘
                                      │ HTTP/HTTPS
  ┌───────────────────────────────────▼──────────────────────────────────────────┐
  │                     CRAWLER SYSTEM                                            │
  │  ┌───────────────┐   ┌───────────────┐   ┌───────────────────────────────┐  │
  │  │  URL Frontier │ → │ Crawler Fleet │ → │  Content Store (raw HTML/GCS) │  │
  │  │  (Priority Q) │   │  (10K+ nodes) │   │  + Link Graph Store           │  │
  │  └───────────────┘   └───────────────┘   └───────────────────────────────┘  │
  └──────────────────────────────────────────────────────────────────────────────┘
                                      │ raw pages
  ┌───────────────────────────────────▼──────────────────────────────────────────┐
  │                     INDEXING PIPELINE                                         │
  │  ┌───────────┐  ┌──────────────┐  ┌────────────┐  ┌──────────────────────┐  │
  │  │  Parser   │→ │  Deduper     │→ │  Anchor    │→ │  Inverted Index      │  │
  │  │ (HTML→text│  │ (SimHash dup │  │  Text      │  │  Builder (MapReduce) │  │
  │  │  extract) │  │  detection)  │  │  Extractor │  │                      │  │
  │  └───────────┘  └──────────────┘  └────────────┘  └──────────────────────┘  │
  └──────────────────────────────────────────────────────────────────────────────┘
                                      │ serving index shards
  ┌───────────────────────────────────▼──────────────────────────────────────────┐
  │                     QUERY SERVING LAYER                                       │
  │  ┌─────────────┐  ┌───────────────────┐  ┌──────────────────────────────┐   │
  │  │  Query      │  │  Index Shards     │  │  Ranking Engine              │   │
  │  │  Processor  │→ │  (leaf servers)   │→ │  (TF-IDF + PageRank + ML)   │   │
  │  │  (spell/NLU)│  │  parallel lookup  │  │                              │   │
  │  └─────────────┘  └───────────────────┘  └──────────────────────────────┘   │
  │                                │                                              │
  │  ┌─────────────────────────────▼────────────────────────────────────────┐   │
  │  │  SERP (Search Engine Results Page) — assembled and returned          │   │
  │  └──────────────────────────────────────────────────────────────────────┘   │
  └──────────────────────────────────────────────────────────────────────────────┘
```

---

## STEP 4 — Deep-Dive: Web Crawler

```
THE CHALLENGES:
  1. Scale: 100B pages. Can't crawl sequentially.
  2. Politeness: don't hammer any one server.
  3. Freshness: popular pages must be re-crawled frequently.
  4. Deduplication: same content at multiple URLs → only store once.
  5. Robots.txt: respect webmaster exclusions.
  6. Traps: infinite URL spaces (session IDs, filters, calendars → infinite pages).

URL FRONTIER (Priority Queue):

  Three-tier priority system:
  
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │  PRIORITY ASSIGNMENT:                                                        │
  │    High priority (crawl every few minutes):                                  │
  │      - Pages with high PageRank (linked from many pages)                    │
  │      - News sites, Wikipedia, major domains                                  │
  │      - Pages that change frequently (detected by HTTP Last-Modified)         │
  │    Medium priority (crawl every few hours):                                  │
  │      - Pages with moderate inbound links                                     │
  │    Low priority (crawl every week/month):                                    │
  │      - Long-tail pages, rarely linked                                        │
  └─────────────────────────────────────────────────────────────────────────────┘
  
  POLITENESS: per-domain queue + crawl delay.
    Domain "nytimes.com" has own queue.
    Pop one URL from nytimes.com queue → wait 30s → pop next.
    Don't mix nytimes.com URLs with other domains → rate limiting per domain.
  
  BLOOM FILTER for visited URLs:
    100B URLs. Can't store all in hash table (too much memory).
    Bloom filter: probabilistic set membership. 10 bits per URL.
    100B × 10 bits = 125 GB RAM. Acceptable for distributed cluster.
    False positive rate 0.1%: occasionally skip a URL we haven't visited → acceptable.
    False negative rate 0%: never wrongly report "visited" for unvisited URL.
  
  class URLFrontier:
      def __init__(self):
          self.bloom = BloomFilter(capacity=100_000_000_000, error_rate=0.001)
          self.domain_queues: dict[str, deque] = {}  # per-domain queue
          self.priority_heap = []  # (next_crawl_time, domain)
      
      def add_url(self, url: str, priority: float, estimated_change_freq: int):
          # Normalize URL: lowercase scheme/host, sort query params, remove session IDs
          url = normalize(url)
          
          if url in self.bloom:
              return  # already queued/visited
          
          self.bloom.add(url)
          
          domain = extract_domain(url)
          if domain not in self.domain_queues:
              self.domain_queues[domain] = deque()
          
          self.domain_queues[domain].append({
              "url": url,
              "priority": priority,
              "next_crawl": now() + (1/priority) * 3600  # sooner = higher priority
          })
      
      def get_next_crawlable_url(self) -> str | None:
          # Return URL where enough time has elapsed since last domain crawl
          ready_domains = [d for d, t in self.last_crawl_time.items()
                           if now() - t > self.crawl_delay[d]]
          if not ready_domains:
              return None
          domain = max(ready_domains, key=lambda d: self.domain_queues[d][0]["priority"])
          return self.domain_queues[domain].popleft()["url"]

CRAWLER WORKERS:
  10,000+ crawler machines. Each:
    1. Pop URL from frontier.
    2. DNS resolve (cached: many pages share same server IP).
    3. Fetch page (HTTP GET, timeout 5s, max size 5 MB, respect robots.txt).
    4. Parse HTML → extract: text, outbound links, metadata.
    5. Store raw HTML in GCS (content addressable: hash of content = filename → dedup).
    6. Extract links → normalize → add to URL frontier queue.
    7. Compute page signature (SimHash) → detect near-duplicate content.

DUPLICATE CONTENT DETECTION:
  Two URLs with different paths but same content (e.g., www. vs non-www, session IDs).
  
  SimHash algorithm:
    1. Extract tokens from page text.
    2. For each token: compute 64-bit hash.
    3. If bit_i of hash is 1: add weight to dimension i.
       If bit_i of hash is 0: subtract weight.
    4. Final 64-bit simhash: bit_i = 1 if sum_i > 0 else 0.
    
    Similar pages (>90% same content): Hamming distance < 3 bits.
    Store all simhashes. Query: find simhashes within Hamming distance 3.
    Locality Sensitive Hashing (LSH): groups similar hashes → O(1) lookup.
  
  Canonical URL handling: <link rel="canonical" href="..." /> → use canonical as primary.
```

---

## STEP 5 — Deep-Dive: Inverted Index

```
THE CORE DATA STRUCTURE OF SEARCH:

  Forward index (not useful for search):
    doc_1 → ["python", "tutorial", "beginner", "programming"]
    doc_2 → ["python", "interview", "questions", "MAANG"]
  
  Inverted index (what you need for "find docs containing python"):
    "python"      → [(doc_1, freq:3, pos:[5,12,47]), (doc_2, freq:5, pos:[1,8,22,35,41])]
    "tutorial"    → [(doc_1, freq:1, pos:[6])]
    "interview"   → [(doc_2, freq:2, pos:[9,50])]
    "programming" → [(doc_1, freq:2, pos:[13,48])]
  
  Each entry (doc_id, freq, positions) is called a "posting".
  The list of postings for a term is the "posting list" or "inverted list".

BUILDING THE INDEX (at scale — MapReduce / Dataflow):
  
  Input: 100B documents with extracted text.
  
  MAP phase (per document):
    mapper(doc_id, text):
      for pos, word in enumerate(tokenize(text)):
          word = stem(lowercase(word))  # "Running" → "run"
          if word not in STOPWORDS:     # skip "the", "and", "is"
              emit((word, doc_id), pos)
  
  REDUCE phase (per term):
    reducer(word, [(doc_id_1, pos_1), (doc_id_2, pos_2), ...]):
        # Sort by doc_id, then by position within doc
        grouped = group_by(lambda x: x[0], sort_by(lambda x: x[0]))
        posting_list = []
        for doc_id, positions in grouped:
            tf = len(positions)  # term frequency
            posting_list.append((doc_id, tf, sorted(positions)))
        emit(word, sorted(posting_list, key=lambda x: rank_score(x[0])))
  
  Output: posting lists for all 100B terms (after dedup: ~50B unique terms).
  Storage: 50B terms × avg 100 postings × 20B = 100 TB compressed.

TOKENIZATION AND TEXT PROCESSING:
  Raw text: "Python is GREAT for System-Design! See: https://link.com"
  
  Step 1 — Tokenize: ["Python", "is", "GREAT", "for", "System", "Design", "See", "https://link.com"]
  Step 2 — Lowercase: ["python", "is", "great", "for", "system", "design", "see", "https://link.com"]
  Step 3 — Remove stopwords: ["python", "great", "system", "design"]
  Step 4 — Stem: ["python", "great", "system", "design"] (these don't change much)
              or lemmatize: "running" → "run", "better" → "good"
  Step 5 — Handle synonyms: "automobile" → also index as "car"
  
  N-grams: also index bigrams "system design", "machine learning" → phrase search.
  Anchor text: text of links pointing TO a page is indexed WITH the target page.
    → "click here to see Google" → "google" in anchor text for google.com. Very valuable signal.

INDEX SHARDING (how to split 100 TB across machines):
  
  Option A: Document-Based Sharding
    Shard 1: doc_ids 0–1B
    Shard 2: doc_ids 1B–2B
    ...
    For query "python tutorial":
      Send query to ALL shards in parallel.
      Each shard: lookup "python" AND "tutorial" in its own slice → return top-K local results.
      Merger: merge all shards' results → global top-10.
    
    PROS: simple, balanced load (each shard has equal # docs).
    CONS: every query hits ALL shards (fan-out cost).
    
    GOOGLE USES THIS (with optimizations).
  
  Option B: Term-Based Sharding
    Shard A: terms starting with A-M
    Shard B: terms starting with N-Z
    For query "python tutorial":
      "python" → go to P shard
      "tutorial" → go to T shard
      Must coordinate between 2 shards to intersect → complex.
    
    PROS: reduces fan-out for single-term queries.
    CONS: multi-term queries need cross-shard joins → slow.
  
  GOOGLE'S ACTUAL APPROACH:
    Document-based sharding at leaf level.
    Multiple replicas of each shard (for availability + read load).
    Query fan-out: query → distributed to all shard groups in parallel → merge.
    
    Hierarchical: multiple datacenters per region.
    Each query served entirely within one datacenter (data locality).

SERVING INDEX STRUCTURE (on each shard):
  In-memory index (hot): compressed posting lists in RAM.
  On-disk index (cold): older/less popular terms in SSDs.
  
  Compression techniques:
    - Variable-length integers (varint): small numbers take fewer bytes.
    - Delta encoding: store deltas between sorted doc_ids (much smaller than raw IDs).
      Example: [100, 105, 112, 120] → [100, 5, 7, 8] → 4 varints instead of 4 ints.
    - Gap compression: first posting = full doc_id, rest = gap since previous.
  
  Result: 100 TB raw → ~10-20 TB compressed serving index.
```

---

## STEP 6 — Deep-Dive: PageRank

```
CORE INSIGHT:
  Not all links are equal. A link from NYT is worth more than a link from a spam blog.
  A page is important if important pages link to it.
  Circular definition → solved by iterative algorithm.

FORMULA:
  PR(A) = (1 - d) / N + d × Σ(PR(B) / OutLinks(B)) for all B that link to A
  
  Where:
    d = 0.85 (damping factor: probability user continues clicking vs stops)
    N = total pages
    PR(B) = PageRank of linking page B
    OutLinks(B) = number of outbound links from B (each outbound link gets equal share)

INTUITION:
  "Random Surfer Model":
    User randomly clicks links on any page.
    With 15% probability (1-d): jumps to a completely random page.
    With 85% probability (d): clicks a link on current page.
    PageRank of a page = probability that random surfer is on that page at any time.
  
  Pages with many inbound links from popular pages → surfer visits them often → high PR.
  Pages with no inbound links → surfer never reaches them → PR approaches (1-d)/N.

COMPUTATION AT SCALE (MapReduce):
  Graph: 100B nodes, 10T edges.
  
  Representation:
    Each page → (page_id, outbound_links[], current_pagerank)
  
  One iteration:
    MAP:
      mapper(page_id, (outlinks, pr)):
          contribution = pr / len(outlinks)
          for link in outlinks:
              emit(link, contribution)  # this link gets this much PR
    
    REDUCE:
      reducer(page_id, contributions):
          new_pr = (1 - 0.85) / N + 0.85 * sum(contributions)
          emit(page_id, new_pr)
  
  Convergence: ~50 iterations until values stabilize (< 0.0001 change).
  
  At scale: Google uses Pregel (graph processing framework) or Dataflow.
  10T edges × 50 iterations × data transfer = enormous computation.
  Pregel: keeps graph in memory, message-passing between vertex workers.
  Much faster than MapReduce for iterative graph algorithms.

PAGERANK IN 2024:
  PageRank is now ONE of 200+ ranking signals.
  Modern Google weights:
    - PageRank (authority signal) ~10% weight
    - Content relevance (TF-IDF + BERT embeddings) ~30%
    - User engagement signals (CTR, dwell time) ~20%
    - Freshness ~10%
    - User personalization ~10%
    - Other signals: HTTPS, page speed, mobile-friendliness, Core Web Vitals ~20%
```

---

## STEP 7 — Deep-Dive: Query Processing

```
USER TYPES: "best python interview questions 2024"

STEP 1 — Query Understanding:
  
  Spell Correction:
    "questoins" → "questions" (Noisy Channel model: P(typo|word) × P(word))
    Training data: billions of query pairs where user corrected themselves.
    "Did you mean: ...?" shown if confidence > 0.8.
  
  Query Classification (intent):
    Navigational: "youtube" → user wants youtube.com directly.
    Informational: "how to learn python" → user wants articles/tutorials.
    Transactional: "buy python book" → user wants to buy something.
    Local: "python classes near me" → user wants local results.
    
    BERT model classifies query into one of these intents.
    Intent affects result types shown (Knowledge Panel, shopping results, local pack).
  
  Named Entity Recognition:
    "Python" → programming language or snake? Context disambiguates.
    "Jordan" → Michael Jordan? Country? River? 
    Entity linking: map query terms to Knowledge Graph entities.
  
  Query Expansion:
    Synonyms: "python tutorial" → also search for "python course", "learn python"
    Abbreviations: "SDE" → "Software Design Engineer"
    Historical clickthrough data: queries that led to same documents get related ranking.

STEP 2 — Index Lookup:
  
  Terms extracted: ["python", "interview", "question", "2024"]
  
  For each term: fetch posting list from inverted index (all shards in parallel).
  
  Posting list for "python" → 50M documents
  Posting list for "interview" → 30M documents
  Posting list for "question" → 80M documents
  Posting list for "2024" → 200M documents (lots of pages have "2024")
  
  Intersection (AND): documents in ALL four posting lists.
  Algorithm: merge sorted posting lists using DAAT (Document-At-A-Time) merge.
  
  def intersect_posting_lists(lists: list[list[int]]) -> list[int]:
      # Sort lists by length (shortest first = faster pruning)
      lists = sorted(lists, key=len)
      result = set(lists[0])
      for lst in lists[1:]:
          result = result.intersection(lst)
          if not result:
              break  # early termination
      return sorted(result)
  
  Result set: ~1M documents contain all 4 terms.
  
  Approximate results: can't score 1M docs in < 200ms.
  Optimization: take top-1000 by pre-computed ranking score → score these fully.
  Pre-computed score: at index build time → store PageRank + base TF score per doc.
  This filters 1M → 1000 quickly → score 1000 fully with all signals.

STEP 3 — Scoring and Ranking:
  
  TF-IDF base score:
    TF(t, d) = log(1 + count of term t in doc d)  [log dampens high freq]
    IDF(t) = log(total_docs / docs_containing_t)   [rare terms score higher]
    TF-IDF(t, d) = TF × IDF
    
    Doc score = Σ(TF-IDF(term, doc)) for all query terms
    
    Phrase bonus: "python interview" as exact phrase → 2× bonus.
    Position bonus: term in <title> = 5×, in <h1> = 3×, in URL = 2×.
    Anchor text bonus: inbound links' anchor text → major ranking signal.
  
  Learning to Rank (RankBrain → BERT → MUM):
    Input: 200 signals for each candidate document.
    Output: final ranking score.
    Model: deep neural network (Google's proprietary).
    Training: human quality raters label query-result pairs (2000+ raters globally).
    Evaluation: NDCG (Normalized Discounted Cumulative Gain).
  
  BERT for relevance (2019+):
    Traditional: exact word matching. "buy vs purchase" treated as different.
    BERT: understands semantics. "buy" and "purchase" are similar.
    Query embedding: BERT encodes query → 768-dim vector.
    Doc embedding: BERT encodes doc title+snippet → 768-dim vector.
    Semantic score: cosine similarity of embeddings.
    Much better for: long queries, questions, typos, synonyms.
  
  User signals (from clickstream):
    CTR (click-through rate): higher = more relevant.
    Dwell time: user clicked and stayed 5 min = good result.
    Pogo-sticking: user clicked, immediately returned = bad result.
    These are "implicit feedback" — powerful signals but gameable (click farms).
    Google uses them carefully to avoid gaming.

STEP 4 — Result Assembly:
  
  Top-10 results selected. Snippet generated:
    Extract 2-3 sentences containing query terms.
    Highlight matching terms.
    Show most relevant passage (not necessarily beginning of doc).
  
  Featured Snippet / Knowledge Panel:
    Structured data markup → parsed → shown as rich snippet.
    "Population of India" → "1.43 billion" shown directly.
    No need to click through.
  
  Deduplication: don't show 5 results from same domain.
    Max 2 results per domain (with exceptions for navigational queries).
```

---

## STEP 8 — Deep-Dive: Autocomplete

```
PROBLEM:
  User types "py" → suggest ["python", "python tutorial", "python interview questions"].
  Must respond in < 50ms at 400K queries/sec.

APPROACH: Prefix Trie + Redis

  OFFLINE: build trie from historical queries.
    Key insight: query suggestions = popular past queries with this prefix.
    Data: billions of historical queries with frequency counts.
    
    Build prefix → [sorted list of top-10 suggestions by frequency].
    Storage: not a real trie (too much RAM). Instead: hash table.
    Key: "py" → ["python", "python tutorial", "python interview", ...]
    Key: "pyt" → ["python", "python tutorial", "python download", ...]
    
    After pruning: ~1M unique prefixes (1-5 chars) × 10 suggestions × 50B each = ~500 GB.
    Too large for single Redis → Redis Cluster + data sharded by prefix.
  
  ONLINE: prefix lookup.
    User types "pyt" → GET from Redis: "suggestions:pyt"
    Return: top-10 suggestions in < 5ms.
    Full latency with network: < 50ms.
  
  PERSONALIZATION:
    Prefix "pyt" → global top-10 is generic.
    If user previously searched "python interview" → boost "python interview" in their suggestions.
    Stored: "user_top:{user_id}:{prefix}" → personalized suggestions.
    Blend: 50% global + 50% personalized. Avoids "filter bubble" while still personalizing.
  
  TRENDING QUERIES:
    New trend: "python 3.13 release" — not in historical trie yet.
    Real-time: Kafka stream of current queries → sliding window count per query per prefix.
    Redis sorted set: "trending:prefix:py" → {query: count}.
    Merge with static trie suggestions → trending queries appear quickly.

IMPLEMENTATION:

  class Autocomplete:
      def get_suggestions(self, prefix: str, user_id: str) -> list[str]:
          prefix = prefix.lower().strip()[:20]  # limit prefix length
          
          # 1. Check cache (very hot — same prefix typed millions of times)
          cache_key = f"ac:global:{prefix}"
          cached = redis.get(cache_key)
          if cached:
              global_suggestions = json.loads(cached)
          else:
              global_suggestions = self._trie_lookup(prefix)
              redis.setex(cache_key, 300, json.dumps(global_suggestions))
          
          # 2. Personal suggestions
          personal_key = f"ac:user:{user_id}:{prefix}"
          personal = redis.lrange(personal_key, 0, 4)  # user's last typed matching this prefix
          
          # 3. Trending
          trending = redis.zrevrange(f"ac:trending:{prefix}", 0, 2, withscores=False)
          
          # 4. Merge: personal first, then trending, then global
          seen = set()
          result = []
          for s in personal + trending + global_suggestions:
              if s not in seen:
                  seen.add(s)
                  result.append(s)
              if len(result) == 10:
                  break
          return result
```

---

## STEP 9 — Deep-Dive: Freshness

```
CHALLENGE:
  News: "earthquake in Tokyo" must appear in results within minutes.
  Product pages: rarely change — crawl monthly is fine.
  
  Wrong freshness = wrong results. News from 2020 shown for "today's news" = terrible.

CRAWL SCHEDULING:
  Each URL has a predicted change frequency (ΔF):
    ΔF = pages that changed between consecutive crawls / total pages examined
  
  Historical data: crawled 1000 times → changed 200 times → ΔF = 0.2.
  Crawl interval = 1 / ΔF = 5 crawl cycles.
  
  Real-time signals to increase priority:
    Sitemap with <lastmod>: webmaster says "this page changed"
    RSS/Atom feeds: news sites publish new articles
    External link velocity: many new pages linking here = something happened here
    PubSubHubbub (WebSub): publisher proactively pings Google "I have new content"
  
  News-specific fresh crawl: dedicated "Freshbot" for news domains.
    Every 5 minutes: crawl sitemap of news sites.
    New URLs → immediate crawl → within 30s: parsed, indexed, available.
  
  Freshness ranking boost:
    Query "python 3.13 release" → freshness signal weighted heavily.
    For "python tutorial" → freshness less important, authority more important.
    Query understanding classifies query as "fresh-sensitive" or "authority-sensitive".

TIERED INDEX:
  Fresh tier: last 72 hours (small, updates every few minutes)
  Recent tier: 72 hours – 30 days (medium, updates daily)
  Main index: all time (large, updates weekly)
  
  Query hits ALL tiers simultaneously:
    Fresh tier: most recent relevant content
    Main index: authoritative, well-established content
    Merge results: fresh deduped against main, then ranked together.
  
  This is why you see both new articles AND timeless pages in results.
```

---

## STEP 10 — Bottlenecks and Solutions

```
BOTTLENECK 1: Crawling 100B pages (2.5 PB/day of HTML fetched)
  Can't fit in one machine. Can't go through central router.
  Fix: distributed crawler fleet (10K+ machines). Each machine is independent.
  Coordinate only for: URL frontier access (distributed queue), bloom filter (distributed).
  DNS caching: each crawler caches DNS lookups (many pages share IPs).
  HTTP/2 multiplexing: open persistent connections to popular domains.

BOTTLENECK 2: Index too large for single machine (10-20 TB)
  Fix: shard by document ID. Each shard = 100K machines with a slice of the index.
  Query fan-out: one query → hits all shards simultaneously → merge top-K results.
  Each shard returns top-K (say top-1000). Merger takes global top-10.
  Merge overhead: 1000 results × N shards → still just top-10.

BOTTLENECK 3: 400K queries/sec, each hitting all index shards
  Each shard must handle 400K queries/sec.
  At 100 shards: each shard handles 400K queries/sec. Still too many for one machine.
  Fix: N replicas of each shard. Load balance across replicas.
  3 replicas: each handles 133K queries/sec. Feasible for fast SSD + in-memory index.

BOTTLENECK 4: PageRank computation on 100B page graph
  Naive MapReduce: 50 iterations × 100B nodes × 10T edges = years.
  Fix: Pregel graph computation. Graph stays in memory across iterations.
  Incremental PageRank: only recompute affected subgraph when new pages added.
  Approximate PageRank: Monte Carlo random walk estimation. Much faster, close enough.

BOTTLENECK 5: Hot queries (same query asked millions of times per second)
  "weather today" → asked 1M times/hour.
  Same result for same query (except personalized ordering).
  Fix: query-level caching in Redis.
  Key: "serp_cache:{hash(query)}" → JSON of top-10 results. TTL: 5 minutes.
  For news queries: TTL = 30 seconds (results change fast).
  Cache hit rate: top 1000 queries cover ~40% of all traffic.
```

---

## STEP 11 — Trade-offs

```
TRADE-OFF 1: Document-based vs term-based sharding
  Document-based: every query hits every shard (fan-out). Simple, balanced.
  Term-based: single-term queries → one shard. Multi-term → cross-shard join (complex).
  Decision: document-based with replicas. Fan-out is fine — each shard responds < 10ms.

TRADE-OFF 2: PageRank freshness vs computation cost
  Recompute daily: always fresh. Expensive: 100B nodes × 10T edges × 50 iterations.
  Recompute weekly: stale by a week. Much cheaper.
  Incremental update: only update PageRank for pages that changed. Best of both.
  Decision: incremental updates daily. Full recompute weekly.

TRADE-OFF 3: Full inverted index vs approximate matching
  Full AND matching: only return docs with ALL query terms. Can be zero results.
  Approximate: OR matching + penalize missing terms. More results, some less relevant.
  Decision: attempt AND first. If < 10 results: fall back to OR with missing-term penalty.

TRADE-OFF 4: Freshness vs quality
  Brand new page indexed immediately: no PageRank (no inbound links yet).
  Quality = 0 but freshness = high.
  Decision: freshness trumps quality only for time-sensitive queries ("breaking news").
  For other queries: established pages with PageRank rank higher even if slightly older.

TRADE-OFF 5: Crawler aggressiveness vs web server politeness
  Crawl faster: more current index. But: hammering servers → get IP-blocked.
  Crawl slower: miss updates. But: good citizen.
  Decision: adaptive crawl rate. Slow down if server returns 429 Too Many Requests.
  robots.txt: absolute upper limit on crawl rate per domain.
```

---

## STEP 12 — Follow-Up Questions

```
Q: "How do you detect and filter spam/SEO manipulation?"
A: Multi-layer spam detection:
   Link spam: sudden spike in inbound links (link farms). Detect via velocity.
   Content spam: keyword stuffing, thin content, auto-generated text.
     → Panda algorithm: ML model trained on quality rater data.
   Cloaking: show Googlebot different content than users. 
     → Compare crawled HTML with Chrome-rendered HTML.
   Manual penalties: reported spam → human review → manual penalty.
   
   SpamBrain (Google's AI spam fighter): 
     Neural network trained to identify spammy content patterns.
     Analyzes 200+ signals per page.

Q: "How would you design autocomplete to avoid showing harmful/offensive queries?"
A: Blocklist of terms: never suggest these.
   Country-specific blocklists: what's legal varies by jurisdiction.
   Sensitive query dampening: reduce weight of queries related to self-harm,
   illegal content, harassment (even if frequently searched).
   Real-time detection: ML classifier on candidate suggestions → filter score.
   
   Challenge: "bomb" is legitimate ("cherry bomb recipe" or "Atomic bomb history").
   Context from prefix helps. "how to make a b" → different from "cherry b".

Q: "How do you implement search within a private enterprise (internal Google search)?"
A: Same crawling but only behind-firewall URLs.
   Crawler needs VPN or internal network access.
   Index: private cluster, not shared with web index.
   Access control: search results filtered by document ACL.
     User only sees docs they have permission to read.
   Hybrid: search both internal and external web simultaneously.

Q: "How do you handle multi-language search? (Japanese query for Chinese content)"
A: Cross-lingual search via multilingual embeddings.
   mBERT (multilingual BERT): trained on 100+ languages.
   Query "机器学习" (machine learning in Chinese): encode with mBERT → same embedding space.
   English docs about "machine learning": similar embedding → cross-lingual match.
   Translation: translate query + docs to English for uniform indexing (alternative approach).

Q: "How would you design Personalized Search?"
A: User's search history: "what did user search last 30 days?"
   Implicit feedback: what results did user click? How long did they stay?
   Personalization signals: if user clicked "ML tutorials" repeatedly → boost ML content.
   Privacy: Google stores this in user profile (tied to logged-in account).
   Incognito mode: no personalization, no history stored.
   Implementation: personalization offset added to ranking score per doc per user.
   Not a separate index — just per-user score adjustment at ranking time.
```


---

## DEEP-DIVE IMPROVEMENT: BERT Integration for Semantic Search

```
THE PROBLEM WITH KEYWORD MATCHING:
  Query: "how to cure a headache"
  Page contains: "remedies for migraine relief"
  
  TF-IDF / BM25: ZERO overlap. These words don't match. Document not returned. BAD.
  BERT: understands semantics. "headache" ≈ "migraine". "cure" ≈ "remedy". MATCH. GOOD.
  
  This semantic understanding is why Google's results feel "smart" compared to older search engines.

BERT OVERVIEW:
  BERT = Bidirectional Encoder Representations from Transformers.
  Training: masked language model on 3.3B words (Wikipedia + BooksCorpus).
  Architecture: 12 Transformer layers, 768-dimensional embeddings.
  Key property: bidirectional context. "bank" in "river bank" vs "bank account" → different embeddings.
  
  Why bidirectional matters for search:
    "Apple stock" vs "Apple pie"
    Unidirectional: "Apple" gets same representation in both. Context to the RIGHT is ignored.
    Bidirectional: BERT reads both left AND right context → different "Apple" embeddings.
    Query understanding dramatically improved.

HOW BERT IS DEPLOYED IN GOOGLE SEARCH:

STAGE 1: Offline — Pre-compute Document Embeddings
  
  For each webpage in the index:
    Input: concatenate title + first 512 tokens of content.
    BERT forward pass: produces [CLS] token embedding (768-dimensional vector).
    Store: {doc_id → 768-dim embedding vector} in dense vector index (FAISS or similar).
  
  Storage: 100B docs × 768 dim × 4 bytes = 308 TB. Enormous.
  Compression: quantize to 8-bit integers → 77 TB.
  Sharding: distribute across thousands of servers.
  
  Update frequency: re-embed pages when content changes significantly.
  New page indexed: encode immediately (batch embedding inference on TPUs).

STAGE 2: Runtime — Query Embedding + Semantic Retrieval
  
  User query: "how to cure a headache"
  
  a) Query encoding (< 5ms on TPU):
     BERT forward pass on query tokens → 768-dim query vector.
  
  b) Approximate nearest neighbor (ANN) search:
     Find documents whose embeddings are closest to query embedding.
     FAISS (Facebook): IVF-PQ index.
       IVF: Inverted File — partitions vector space into 1000 clusters. 
       PQ: Product Quantization — compresses 768-dim → 64-byte code. 
       Search: find nearest cluster center → search only that cluster (1% of docs).
       Speed: < 5ms for top-1000 similar documents from 100B docs. ✓
     
     Result: top-1000 semantically similar documents, even with zero keyword overlap.
  
  c) Combine with keyword results:
     BM25 candidates: top-1000 by keyword matching.
     BERT candidates: top-1000 by semantic similarity.
     Union: up to 2000 candidates.
     Deduplication: remove docs appearing in both (keep once).
     Carry forward: up to 2000 unique candidates to re-ranking stage.

STAGE 3: Neural Re-ranking (cross-encoder)
  
  The above used "bi-encoder" (query and doc encoded separately → dot product).
  Faster but less accurate (query and doc don't attend to each other).
  
  Cross-encoder (BERT applied to query + doc TOGETHER):
    Input: "[CLS] query [SEP] document_snippet [SEP]"
    Output: relevance score 0.0 to 1.0 (single number).
    BERT's attention layers: query tokens attend to document tokens → rich interaction.
    Much more accurate. But: O(N) BERT passes for N candidates.
    
    At 2000 candidates × 10ms BERT inference = 20 seconds. TOO SLOW.
    
    Optimization: use cross-encoder only on top-100 bi-encoder results.
    2000 → (bi-encoder ranking) → top-100 → (cross-encoder reranking) → top-10.
    100 × 10ms = 1 second. Still too slow for p99 goal of 200ms.
    
    Solution: DistilBERT (smaller BERT, 2× faster, 97% accuracy).
    Or: BERT quantized to INT8 (4× faster inference via hardware acceleration).
    Or: BERT served on TPUs (10× faster than CPU).
    Google's TPUs: designed specifically for BERT inference at scale.
    Result: cross-encoder reranking in < 50ms on Google's TPU fleet.

MUM (Multitask Unified Model) — Google's next generation:
  BERT limitation: processes text only. Images and other modalities separate.
  MUM: understands 75+ languages simultaneously. Processes text + images.
  
  "Best hike near Mount Fuji" query:
    BERT: returns English text results. Misses Japanese hiking forums.
    MUM: understands Japanese hiking forums + English mountaineering guides → combined results.
    Also: "Show me trails" → MUM can analyze trail images to understand terrain difficulty.
  
  Deployed for: complex queries, COVID-19 information synthesis, vaccine search.
  Not replacing BERT for all queries (too slow). Augments BERT for complex cases.
  
  This is the distinction between Google (MUM + BERT + 200+ signals) and 
  basic search engines (just TF-IDF). The NLP stack is the moat.
```

---

## DEEP-DIVE IMPROVEMENT: Link Graph and PageRank at Scale

```
LINK GRAPH PROPERTIES:
  100B pages, 10T+ links.
  Approximate: average 100 outbound links per page.
  
  This graph is:
    Directed (A links to B doesn't mean B links to A).
    Sparse (10T edges vs 10^22 possible edges = extremely sparse).
    Power-law distribution: most pages have few links. Few pages (Wikipedia, Google.com) have millions.

CHALLENGES IN COMPUTING PAGERANK AT SCALE:

CHALLENGE 1: Graph doesn't fit in single machine memory.
  100B nodes × 8B each = 800 GB just for node IDs.
  10T edges × 8B each = 80 TB just for edges.
  
  Solution: graph partitioning.
    Partition nodes across machines. Each machine owns a "slice" of the graph.
    Edges: some edges are within same partition (local), some cross partitions (remote).
    Algorithm: processes local edges. For remote edges: message-passing between machines.

CHALLENGE 2: Iterative convergence is slow with message passing.
  50 iterations × 10T edges × message send = enormous network traffic.
  
  Solution: Pregel framework.
    Each node = a vertex. Computation runs in "supersteps."
    Superstep i: each vertex reads messages from last superstep, computes new PR, sends messages.
    All vertices compute simultaneously (BSP: Bulk Synchronous Parallel).
    Messages are BATCHED per superstep, not sent individually.
    Network traffic: 50 supersteps × batched messages. 100× more efficient than naive MR.

PREGEL PAGERANK IN PSEUDOCODE:
  
  class PageRankVertex:
      def compute(self, messages):
          if self.superstep == 0:
              # Initialize: all pages start with PR = 1/N
              self.value = 1.0 / total_pages
              # Send initial contribution to all neighbors
              for neighbor in self.out_edges:
                  self.send_message(neighbor, self.value / len(self.out_edges))
          else:
              # Receive contributions from all pages that link to me
              received_pr_sum = sum(messages)
              
              # PageRank formula:
              self.value = (1 - DAMPING) / total_pages + DAMPING * received_pr_sum
              
              # Propagate my PR contribution to neighbors
              if self.superstep < MAX_ITERATIONS:
                  contribution = self.value / len(self.out_edges)
                  for neighbor in self.out_edges:
                      self.send_message(neighbor, contribution)
              else:
                  self.vote_to_halt()  # signal convergence check
  
  DAMPING = 0.85  # probability of following a link
  MAX_ITERATIONS = 50  # or until convergence (delta < 0.0001)

DANGLING NODES (pages with no outbound links):
  Problem: pages with no outbound links absorb PageRank but don't distribute it.
  PR leaks out of the system over iterations.
  
  Fix: "dangling node correction."
    At each iteration: sum PR of all dangling nodes.
    Distribute this sum evenly to ALL nodes (as if dangling nodes link to everywhere).
    
    dangling_sum = sum(pr for node in dangling_nodes)
    correction = (1 - DAMPING) / N + DAMPING * dangling_sum / N
    # Add correction to every node's PR at each iteration.
  
  Mathematical significance: ensures PR values sum to 1.0 across all pages.
  Without this fix: PR values gradually decrease (leak) → incorrect rankings.

TRUST RANK (anti-spam PageRank extension):
  Problem: spammers create link farms (thousands of pages linking to each other).
  Normal PageRank: link farm pages accumulate high PR → rank well. Spam wins.
  
  TrustRank: start from TRUSTED SEED PAGES (hand-selected by Google quality reviewers).
  Apply reverse PageRank from seeds: pages linked from seeds get high trust.
  Pages only linked from spam: low trust → penalized in rankings.
  
  Algorithm:
    TRUST_SEEDS = {Wikipedia, NYT, BBC, major academic institutions, ...}
    TrustRank(page) = how likely a random surfer starting from seeds reaches this page.
    Same formula as PageRank but seeded differently.
    
    Score: hybrid = PageRank_score × TrustRank_score
    High PR but low trust (link farm) → high rank × low trust → medium overall.
    High PR and high trust (Wikipedia) → high × high = very high.
  
  This is why Google fights link farms effectively.
  Buying thousands of links helps less than getting one link from Wikipedia.
```

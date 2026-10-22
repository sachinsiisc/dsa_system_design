# CS05: Design Netflix (Video Streaming)
## Full HLD Case Study | MAANG Interview Ready

---

## STEP 1 — Requirements

```
FUNCTIONAL:
  1. Browse catalog: search by title, genre, cast; recommendations
  2. Stream videos: 1080p HD, 4K HDR, mobile quality (240p-480p)
  3. Resume watching from last position (watch progress)
  4. Download for offline viewing (mobile)
  5. Continue watching list, watchlist (My List)
  6. User profiles: up to 5 profiles per account (different recommendations)
  7. Content restrictions by region (not all titles available everywhere)

NON-FUNCTIONAL:
  - 220M subscribers globally, 100M+ daily active users
  - 1 billion hours of video watched per day
  - Video start time: < 2 seconds (player opens and starts fast)
  - Zero rebuffering: once playing, no pauses for loading
  - Global: 190+ countries. Low latency worldwide.
  - 99.99% availability for streaming
  - Content duplication: same content in many regions (CDN)
  - Recommendations personalized per user per profile
```

---

## STEP 2 — Scale Estimation

```
VIEWING:
  1 billion hours/day watched.
  100M DAU. Average: 10 hours/DAU/day (heavy streaming).
  
  Concurrent streams at peak (8-10 PM):
    Assume 20% of DAU watching simultaneously = 20M concurrent streams.
  
  Average bitrate: 5 Mbps for 1080p, 15 Mbps for 4K.
  Assume avg 5 Mbps (mix of SD/HD/4K):
  Bandwidth: 20M streams × 5 Mbps = 100 Tbps (!) at peak.
  
  This is why Netflix needs ISP-embedded CDN. 100 Tbps cannot come from AWS.

STORAGE:
  Content library: 15,000 titles.
  Each title encoded in 10+ profiles (240p, 360p, 480p, 720p, 1080p, 4K, HDR10, Dolby Vision, 
                                      SDR/HDR variants, audio-only).
  Average movie (2 hours, 1080p h265): ~1.5 GB.
  Per title (all profiles): 10 profiles × avg 1.5 GB = 15 GB per title.
  Total: 15,000 × 15 GB = 225 TB (just content, all titles).
  With 3× replication: 675 TB ≈ 1 PB for video content.
  
  Netflix actual: ~9 PB (larger catalog + multiple bitrate profiles + redundancy).

VIDEO STARTS:
  100M DAU × 2 video starts/day = 200M starts/day.
  200M ÷ 86,400 = 2,315 starts/sec avg.
  Peak: 11,574 starts/sec.
  Each start: fetch manifest → fetch first segment → begin playback.

RECOMMENDATIONS:
  220M users × avg 200 ratings/user = 44B user-item interactions.
  Model retrained weekly (batch). Real-time updates: within session.
```

---

## STEP 3 — High-Level Architecture

```
BROWSE/CATALOG FLOW:
  ┌──────────┐   GET /home        ┌────────────────────┐    ┌──────────────────┐
  │  App     │ ─────────────────► │  API Gateway (Zuul)│ →  │  Catalog Service │
  └──────────┘                    └────────────────────┘    └──────┬───────────┘
                                                                   │
                                                          ┌────────▼────────┐
                                                          │  Redis (top rows)│
                                                          └────────┬────────┘
                                                                   │ (miss)
                                                          ┌────────▼────────┐
                                                          │  DynamoDB        │
                                                          │  (metadata)      │
                                                          └─────────────────┘

PLAY FLOW:
  ┌──────────┐   POST /play/{id}  ┌────────────────────┐    ┌──────────────────┐
  │  App     │ ─────────────────► │  Playback Service  │ →  │  License Service │
  └──────────┘ ◄────────────────── └──────────┬─────────┘    │  (DRM check)     │
               manifest URL                   │              └──────────────────┘
                                    ┌──────────▼─────────┐
                                    │  Steering Service   │ ← which CDN server?
                                    └──────────┬──────────┘
                                               │
                                    ┌──────────▼──────────┐
                                    │  Open Connect CDN   │  ← nearest ISP
                                    │  (video segments)   │  embedded appliance
                                    └─────────────────────┘

FULL ARCHITECTURE:
  ┌────────────────────────────────────────────────────────────────────┐
  │                   AWS EDGE / Route 53                               │
  └─────┬──────────────────────────────────────────────────┬───────────┘
        │ API traffic                                       │ Video traffic
  ┌─────▼───────────────────────────────────────┐    ┌─────▼───────────────┐
  │  Zuul API Gateway                            │    │  Open Connect CDN   │
  │  - Auth / rate limit                         │    │  (ISP co-located)   │
  │  - Route to microservices                    │    │  200TB+ per PoP     │
  └─────┬─────────────┬─────────────────┬────────┘    └─────────────────────┘
        │             │                 │
  ┌─────▼──────┐┌─────▼──────┐ ┌────────▼────────┐
  │  Catalog   ││  Playback  │ │  Recommendation │
  │  Service   ││  Service   │ │  Service (ML)   │
  └─────┬──────┘└─────┬──────┘ └────────┬────────┘
        │             │                 │
  ┌─────▼─────────────▼─────────────────▼───────┐
  │                 Data Tier                     │
  │  DynamoDB (catalog) │ Cassandra (progress)   │
  │  ElasticSearch (search) │ S3 (video master)  │
  │  Kafka (events) │ Spark (recommendations)    │
  └───────────────────────────────────────────────┘
```

---

## STEP 4 — Deep-Dive: Open Connect CDN

```
THE PROBLEM:
  Netflix serves 100 Tbps at peak.
  Standard CDN (Akamai): would cost ~$1B+/month in bandwidth.
  Even AWS has limits at this scale.

OPEN CONNECT (Netflix's proprietary CDN):
  Netflix manufactures custom CDN appliances.
  Deploys them INSIDE ISP data centres (co-location, free of charge).
  
  WHY ISPs ACCEPT THIS:
    ISP normally pays transit bandwidth: money for moving Netflix traffic to users.
    With OC appliance inside their network: traffic never crosses ISP's transit links.
    ISP saves ~40-60% of their bandwidth cost.
    Win-win: Netflix gets cheap CDN, ISP saves bandwidth cost.
  
  APPLIANCE HARDWARE:
    ~17,000 OC appliances globally.
    Each: 100-200 TB NVMe SSD + HDD, 100 Gbps NIC.
    Total OC storage: hundreds of petabytes.

CONTENT DELIVERY STRATEGY:

  FILL (overnight push):
    Each night (low-traffic hours): Netflix analyzes what's trending per region.
    Proactively pushes popular content to nearby OC appliances.
    India: push Bollywood movies, regional shows for next day's viewers.
    US: push top 200 shows + latest releases.
    
    fill_score(title, appliance) = 
        popularity_in_region × recency_weight × space_available_on_appliance
    
    Titles with highest fill_score → pushed to OC during night fill window.

  SERVE (daytime):
    User requests video: Steering Service checks which OC appliance has this title.
    Nearest OC with content → serve from there.
    Cache HIT: 95-99% for popular content.
    
    Cache MISS (rare, new content not yet pushed): fetch from S3 origin → cache → serve.
    CDN origin: S3 buckets in us-east-1 (primary) + us-west-2 (failover).

  STEERING SERVICE:
    For each video request: which OC appliance to use?
    Factors:
      1. Does appliance have this content? (inventory DB)
      2. How close is appliance to user? (BGP distance, latency measurement)
      3. Is appliance healthy? (load, error rates)
      4. Available bandwidth on appliance?
    
    Returns: ordered list of appliance URLs.
    Client tries first. If fails: try second (failover).
    
    URL format: "https://ipv4_ipv6.oc-manifest.netflix.net/segment.ts?token=..."
    Token: time-limited access token signed by playback service. Prevents hotlinking.
```

---

## STEP 5 — Deep-Dive: Video Encoding

```
ENCODING PIPELINE:

  Source file → Multiple encoding profiles → HLS/DASH segments → S3 → OC CDN

SOURCE FILE:
  Movie studio uploads original: 4K ProRes, 200 GB+ file.
  Uploaded to Netflix S3 via secure transfer.

ENCODING (AWS MediaConvert or custom):
  Netflix re-encodes every title in 10+ quality profiles.
  
  Profile table:
    Resolution │ Bitrate (Mbps) │ Codec  │ Use
    ───────────┼────────────────┼────────┼────────────────
    240p       │ 0.3            │ H.264  │ Mobile 2G
    360p       │ 0.7            │ H.264  │ Mobile 3G
    480p       │ 1.5            │ H.265  │ Mobile 4G
    720p       │ 3.0            │ H.265  │ WiFi, Smart TV
    1080p      │ 5.0            │ H.265  │ HD
    1080p HDR  │ 7.0            │ H.265  │ HDR displays
    4K SDR     │ 15.0           │ H.265  │ 4K TV
    4K HDR10   │ 20.0           │ H.265  │ 4K HDR TV
    4K DV      │ 20.0           │ H.265  │ Dolby Vision TV
    Audio only │ 0.064          │ AAC    │ Background play

  Per-title encoding: 200 GB source → 100 worker instances → parallel encode.
  Time: ~1-4 hours for a 2-hour movie (parallelized).

HLS SEGMENTING:
  Each encoded video → split into 10-second segments.
  2-hour movie × 10 profiles × 6 segments/min × 120 minutes = 7,200 segments total.
  
  HLS Manifest (m3u8 file):
    #EXTM3U
    #EXT-X-VERSION:7
    
    #EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=640x360,CODECS="hvc1"
    /v1/movie_123/hls/360p/playlist.m3u8
    
    #EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080,CODECS="hvc1"
    /v1/movie_123/hls/1080p/playlist.m3u8
    
    #EXT-X-STREAM-INF:BANDWIDTH=20000000,RESOLUTION=3840x2160,CODECS="hvc1"
    /v1/movie_123/hls/4k/playlist.m3u8

PER-TITLE ENCODING OPTIMIZATION:
  Traditional: all content encoded at same bitrate for same resolution.
  Netflix innovation: Per-Title Encode (2015).
  
  Animated shows: very compressible. Can be 1080p at 2 Mbps (normally 5 Mbps).
  Action movies: lots of motion. Need 5 Mbps for same quality.
  
  Process: analyze "complexity" of each shot → allocate bits where needed.
  Result: 20% smaller files at same visual quality. Huge bandwidth + storage savings.
```

---

## STEP 6 — Deep-Dive: Adaptive Bitrate Streaming (ABR)

```
PROBLEM:
  User's network varies: wifi (50 Mbps) → 4G (10 Mbps) → spotty (1 Mbps).
  Fixed quality → either: high quality (buffering on slow) or low quality (bad on fast).
  
ADAPTIVE BITRATE STREAMING:
  Player dynamically switches quality based on measured bandwidth.
  
  ABR ALGORITHM (simplified):
  
  buffer_size = 60 seconds of video pre-loaded (fills on fast network)
  
  def choose_quality(measured_bandwidth, buffer_level):
      # Buffer safety: if below 10s, choose conservatively
      if buffer_level < 10:
          safety_margin = 0.5  # use only 50% of bandwidth
      else:
          safety_margin = 0.9  # aggressive, maximize quality
      
      available_bandwidth = measured_bandwidth * safety_margin
      
      # Choose highest quality fitting in available bandwidth
      for profile in sorted(PROFILES, key='bitrate', reverse=True):
          if profile.bitrate <= available_bandwidth:
              return profile
      return PROFILES['240p']  # fallback to lowest

  SEGMENT DOWNLOAD:
    Player fetches one segment at a time (10 seconds).
    Downloads: 10s of video data. Measures how long it took.
    Throughput = segment_size / download_time.
    Use throughput to choose next segment's quality.
    
    Example:
      Current: 1080p (5 Mbps). Next segment takes 8 seconds to download (should be ~2s).
      Measured: 5 Mbps × 2s / 8s = 1.25 Mbps available.
      Switch to: 480p (1.5 Mbps). Segment fits in 2.4s. Back to normal.
  
  BUFFER-BASED SELECTION:
    If buffer > 60s: aggressively increase quality.
    If buffer 20-60s: maintain current quality.
    If buffer 5-20s: slight quality decrease.
    If buffer < 5s: emergency drop to lowest quality.
    
  RESULT:
    User: "Movie played without buffering." ← what they care about.
    Reality: quality dropped from 4K → 720p for 30 seconds. User didn't notice.
    Seamless quality switches happen at segment boundaries (invisible).

CLIENT-SIDE PLAYER BUFFER:
  Pre-load: download 60 seconds ahead of playback position.
  60 seconds at 5 Mbps = 300 Mb = 37.5 MB buffered.
  Network blip lasting < 60 seconds: invisible (playing from buffer).
  
  Memory cost on device: 37.5 MB (acceptable on modern devices).
  Trade-off: 60s buffer vs smaller (5s) → 60s chosen for reliability over memory.
```

---

## STEP 7 — Deep-Dive: Recommendations

```
THE SCALE:
  220M users × 15,000 titles × 200+ signals = massive ML problem.
  
  WHAT NETFLIX PERSONALIZES:
    1. Which shows/movies appear in your home feed rows.
    2. The ORDER of rows (which genre row appears first for you).
    3. The ARTWORK for each title (action vs romantic poster for same movie).
       A/B tested: action fans see action scene, romance fans see romance scene.
       Increased click-through rate significantly.
    4. SEARCH RANKING: same query returns different ranked results per user.

COLLABORATIVE FILTERING (Matrix Factorization):
  Matrix: Users (rows) × Titles (columns). Value: implicit feedback.
  Implicit feedback: watched? How much? Rated?
  
  Decompose: M (220M × 15K) ≈ U (220M × k) × V^T (k × 15K)
  k = 100 latent factors. Each user/title = 100-dimensional vector.
  
  User vector: [0.9, -0.2, 0.5, ...] (encodes preferences: likes action, dislikes romance, ...)
  Title vector: [0.8, -0.1, 0.3, ...] (encodes characteristics: action film, not romantic, ...)
  
  Recommendation score = dot product of user vector × title vector.
  High dot product = high predicted affinity.
  
  For user U: compute dot product with ALL 15K titles → sort → top 50.
  
  COMPUTATION:
    At inference: 220M users × 15K titles = 3.3T dot products.
    Batch offline: once per day → store top-100 per user → serve from Redis.
    Not real-time: user logs in → sees pre-computed recommendations.
    
    Real-time update: last 10 actions in session → update user vector slightly → re-rank.

CONTEXTUAL SIGNALS:
  Time of day: 8 AM → suggest news/documentaries (commute mindset).
               8 PM → suggest movies (relax mindset).
  Device: mobile → suggest shorter content (episodes vs movies).
  Who's watching: Profile A (kids) vs Profile B (adults) → very different signals.
  Recent watch: just finished Stranger Things → suggest horror/sci-fi similar shows.

HOMEPAGE PERSONALIZATION:
  Each user sees different row ordering:
    Row 1: "Continue Watching" (universal)
    Row 2: Could be "Action" or "Comedies" or "Trending" — personalized by ML.
    ...
    Row 20+: Long tail content you might like.
  
  Netflix shows ~200 rows/cards. You see ~30 in a session.
  ML decides which 30 and in what order. 1,000 possible permutations.
  A/B tested over billions of impressions.
```

---

## STEP 8 — Watch Progress and Continue Watching

```
WATCH PROGRESS:
  Every 30 seconds while watching: update progress.
  
  Data: {user_id, profile_id, content_id, progress_seconds, total_seconds, updated_at}
  
  Write rate: 20M concurrent users × 1 write/30s = 666K writes/sec.
  
  STORAGE: Cassandra (high write throughput, simple key-value access).
  
  CREATE TABLE watch_progress (
      user_id     UUID,
      profile_id  UUID,
      content_id  UUID,
      progress    INT,     -- seconds watched
      total       INT,     -- total content seconds
      updated_at  TIMESTAMP,
      PRIMARY KEY ((user_id, profile_id), content_id)
  );
  
  WRITE: UPSERT on every 30-second heartbeat.
  READ: on app open → GET progress for all content in "Continue Watching" list.

CONTINUE WATCHING LIST:
  "Continue Watching" shows content watched but not completed.
  
  Query: SELECT * FROM watch_progress 
         WHERE user_id = ? AND profile_id = ?
         AND progress < total * 0.95  -- not fully watched (< 95% = incomplete)
         ORDER BY updated_at DESC
         LIMIT 10;
  
  Pre-compute: cache this list in Redis (invalidate on new progress update).
  Key: "continue_watching:{user_id}:{profile_id}"
  TTL: 1 hour (progress updates frequently → short TTL).

RESUME PLAYBACK:
  User clicks on content → fetch progress → start video at that second.
  progress = 4320  → video.currentTime = 4320 → play.
```

---

## STEP 9 — DRM (Digital Rights Management)

```
WHY DRM:
  Content studios require encryption. Without DRM: content freely downloadable and redistributable.
  Netflix must protect studio content or lose licensing deals.

HOW DRM WORKS:
  Each video segment encrypted with a unique content key.
  Content key stored in Netflix License Server (KMS).
  
  PLAY FLOW:
    1. User clicks play.
    2. Netflix client requests license: {content_id, device_id, user_id, token}
    3. License Server validates: is this user's subscription active? 
                                  Is this device registered?
                                  Is this content available in user's country?
    4. License granted: returns encrypted content key.
    5. Client decrypts content key (using device-bound secret key in TEE).
    6. Client decrypts video segments with content key → plays.
  
  DRM SYSTEMS:
    Android/Web (Chrome): Widevine (Google)
    Apple (iOS/macOS/tvOS): FairPlay (Apple)
    Windows (Edge): PlayReady (Microsoft)
  
  OFFLINE DOWNLOAD:
    License includes "offline_expiry" (e.g., 30 days or until subscription ends).
    Content key stored in device Trusted Execution Environment (TEE).
    Can play offline until license expires.

CONCURRENT STREAM LIMITS:
  Netflix plan: "2 screens simultaneously."
  License Server tracks: how many active streaming licenses per account?
  If > 2: deny license → "Too many screens."
  Redis tracks: "active_streams:{account_id}" → set of {device_id, started_at}
  TTL: segment duration (10s). Client refreshes every 10s.
  If session dies: TTL expires → slot freed.
```

---

## STEP 10 — Trade-offs and Follow-ups

```
TRADE-OFF 1: Own CDN (Open Connect) vs third-party
  Third-party: pay per GB. Zero infrastructure management.
  At 100 Tbps: ~$3M/hour at standard Akamai pricing. Unviable.
  Own CDN: hardware cost (~$500M capex), but $0 bandwidth cost.
  Decision: own CDN saves billions/year. At Netflix scale, it's a no-brainer.

TRADE-OFF 2: Push content proactively vs on-demand CDN
  On-demand: CDN fetches from origin on first request. Flexible.
  Proactive fill: predict usage → push overnight. Needs accurate prediction.
  Decision: proactive. Netflix's recommendation model accurately predicts regional demand.
  Waste rate: <5% of pushed content is never watched. 95% efficiency.

TRADE-OFF 3: Batch recommendations vs real-time
  Batch: recompute weekly (accurate model, slow to reflect new preferences).
  Real-time: stream processing (expensive infra, complex models).
  Decision: Batch for main model. Real-time for within-session adjustments.
  Within-session: simple contextual model (last 10 actions) using Redis, fast enough.

Q: "How would you handle live streaming (Netflix live events)?"
A: Very different from VOD. No pre-computed CDN fill.
   Ingestion: OBS → RTMP → Netflix ingest server → transcode in real-time → HLS.
   Ultra-low latency: LL-HLS (Low Latency HLS) with 2-5s segments instead of 10s.
   CDN: push-based broadcast to all OC appliances simultaneously.
   Buffer: reduced to 10s (not 60s) for live → some rebuffering risk acceptable.

Q: "How do you A/B test new features for 220M users?"
A: User in experiment cohort? Determined at login by feature flag service.
   Feature flags stored in Redis: "flag:new_homepage:user_123" → true/false.
   Cohort: 1% of users. Run for 2 weeks. Measure: engagement, watch time, cancellations.
   If uplift: gradually roll out to 5%, 10%, 50%, 100%.
   Tool: Netflix uses their own experimentation platform.

Q: "How do you handle subtitles and multiple audio tracks?"
A: Subtitles: separate .vtt files per language, served from CDN.
   Multiple audio: HLS alternate renditions.
   Manifest includes: multiple audio tracks (English 5.1, Spanish, Hindi...)
                     multiple subtitle tracks (English CC, Spanish, Hindi...)
   Client selects desired tracks. Downloads audio + video separately. Player mixes.
```


---

## STEP 11 — Extended Deep-Dive: Chaos Engineering and Resilience

```
NETFLIX IS THE INVENTOR OF CHAOS ENGINEERING:
  "Chaos Monkey" (2011): randomly kills production servers to ensure system tolerates it.
  If you never test failure, you don't know if your fallbacks work.
  
  Netflix's Simian Army (chaos tools):
    Chaos Monkey: kills random EC2 instances during business hours.
    Chaos Gorilla: takes down an entire AWS availability zone.
    Chaos Kong: simulates an entire AWS region failure.
    Latency Monkey: injects artificial network delays.
    Doctor Monkey: detects unhealthy instances via health checks, removes from LB.
    Janitor Monkey: cleans up unused cloud resources (cost optimization).

WHAT HAPPENS WHEN A MICROSERVICE DIES:
  Netflix has 700+ microservices. Any can fail at any time.
  
  Fallback strategy for Recommendation Service failure:
    Primary: personalized recommendations (ML model).
    Fallback 1: cached recommendations from last successful computation (Redis, TTL 24h).
    Fallback 2: trending top-50 globally (always available, pre-computed).
    Fallback 3: genre-based recommendations (deterministic, no ML needed).
    User sees slightly less personalized content. Streaming still works.
  
  Fallback for Playback Service failure:
    Playback Service down -> user can't get video manifest -> streaming fails.
    This is CRITICAL path. No graceful degradation possible.
    Fix: deploy Playback Service in 3 AZs. N+2 redundancy (lose 2 AZs, still up).
    Circuit breaker: if Playback fails 3x in 10s -> route to backup region.

HYSTRIX (Netflix's Circuit Breaker Library, now open-source):
  Wraps every inter-service call.
  
  Example: Catalog Service calls DRM License Service.
  Without Hystrix: DRM down -> Catalog hangs waiting -> Catalog threads exhausted -> Catalog down.
  Cascade failure: one service failure brings down entire call chain.
  
  With Hystrix:
    HystrixCommand wraps DRM call.
    Timeout: 500ms max wait.
    Failure threshold: open circuit after 5 failures in 10s.
    Fallback: return "license pending" status -> client retries after 2s.
    Bulkhead: DRM calls use separate thread pool (isolation).
      DRM thread pool: 10 threads. Even if all hang, Catalog's other pools unaffected.
    
  @HystrixCommand(
      fallbackMethod = "getLicenseFallback",
      commandProperties = {
          @HystrixProperty(name="execution.isolation.thread.timeoutInMilliseconds", value="500"),
          @HystrixProperty(name="circuitBreaker.requestVolumeThreshold", value="5"),
          @HystrixProperty(name="circuitBreaker.errorThresholdPercentage", value="50"),
          @HystrixProperty(name="circuitBreaker.sleepWindowInMilliseconds", value="10000")
      }
  )
  public License getDrmLicense(String contentId, String deviceId) {
      return drmClient.getLicense(contentId, deviceId);
  }
  
  public License getLicenseFallback(String contentId, String deviceId) {
      return License.pending();  // client will retry
  }
```

---

## STEP 12 — Extended Deep-Dive: Netflix Architecture Decisions (Microservices + AWS)

```
NETFLIX'S FULL MIGRATION TO AWS (2008-2016):
  Netflix migrated ENTIRELY to AWS after a 3-day datacenter outage in 2008.
  All services now run on AWS. Netflix is the largest AWS customer.
  Regions: us-east-1 (primary), us-west-2, eu-west-1, ap-northeast-1.
  Goal: if us-east-1 goes down -> entire Netflix runs from us-west-2 within minutes.

ACTIVE-ACTIVE MULTI-REGION:
  Normal operation: users route to nearest region via Route53 latency routing.
  us-east-1 down: Route53 health check fails -> removes from DNS -> traffic to us-west-2.
  
  But: data must be replicated to all regions BEFORE failover.
  
  DynamoDB Global Tables: synchronous replication across regions.
    Catalog data in all regions. Eventual consistency (~1s lag). Acceptable.
  
  Cassandra (watch progress): Netflix uses a multi-region Cassandra cluster.
    Two datacenters: us-east-1 DC and us-west-2 DC.
    Write: QUORUM across DCs (both must acknowledge = strong consistency).
    Read: LOCAL_QUORUM (read from local DC only = low latency).
    Trade-off: writes are slower (cross-DC) but progress is never lost.

ZUUL (API GATEWAY):
  Netflix open-sourced Zuul (API gateway).
  Every API request: Client -> Zuul -> target microservice.
  
  Zuul responsibilities:
    Authentication: validate JWT token -> extract user_id, account_id.
    Rate limiting: global + per-user rate limits.
    Request routing: route /api/catalog to Catalog Service, /api/play to Playback Service.
    Request transformation: add auth headers, set request ID for distributed tracing.
    Response transformation: add CORS headers, compress response.
    A/B testing: route 5% of traffic to new service version (canary release).
    
  Zuul filters (chain of responsibility pattern):
    PreFilters: auth, rate limit, routing decision.
    RouteFilters: proxy to target service.
    PostFilters: add headers, log, metric collection.
    ErrorFilters: handle errors, return friendly error response.

EUREKA (SERVICE DISCOVERY):
  Netflix open-sourced Eureka (service registry).
  700 microservices. How does Zuul know where Catalog Service is?
  
  Service registration:
    On startup: each instance registers with Eureka: {service: "catalog", ip: "10.0.1.42", port: 8080}.
    Heartbeat every 30s: instance renews registration.
    Eureka: if no heartbeat for 90s -> remove instance from registry.
  
  Service discovery:
    Zuul: GET /eureka/apps/catalog -> list of healthy instances.
    Load balance: client-side load balancing (Ribbon library) picks one instance.
    Client cache: Eureka registry cached locally -> no Eureka call per request.
    Cache refresh: every 30s. At most 30s stale.
  
  Without service discovery: hardcoded IPs in config. Instance IP changes on restart.
  With Eureka: services are ephemeral. New instances register. Dead ones deregister. Zuul adapts.

DISTRIBUTED TRACING (Zipkin / Sleuth):
  Request spans 5 microservices. Something is slow. Which one?
  
  Each request: generate unique trace_id.
  Each service: record {trace_id, service_name, start_time, end_time, status}.
  Aggregated in Zipkin: shows full call graph with latency at each hop.
  
  Netflix's Zipkin setup:
    Microservices: publish trace spans to Kafka.
    Zipkin collector: consumes Kafka -> stores in Cassandra.
    Zipkin UI: visualize traces, find slow spans.
    
  Example trace for GET /home:
    Zuul: 2ms
    -> Catalog Service: 45ms
       -> DynamoDB: 12ms
       -> Redis: 2ms
       -> Recommendation Service: 28ms (SLOW!)
          -> Spark model: 25ms
    -> User Service: 5ms
    Total: 50ms
    
  Bottleneck identified: Recommendation Service (28ms). Investigate Spark model latency.
```

---

## STEP 13 — Extended Deep-Dive: Content Licensing and Regional Strategy

```
CONTENT LICENSING COMPLEXITY:
  Netflix doesn't OWN most content. They LICENSE it from studios.
  License = "you can show Movie X in Country Y for Z years."
  
  This creates massive content catalog management requirements:
    15,000 titles × 190 countries = 2.85M title-country combinations.
    Each with its own license terms, start/end dates, audio/subtitle requirements.

CONTENT RIGHTS DATABASE:
  CREATE TABLE content_rights (
      content_id      UUID,
      country_code    CHAR(2),
      available_from  TIMESTAMP,
      available_until TIMESTAMP,  -- null = perpetual
      audio_langs     TEXT[],     -- required audio tracks for this country
      subtitle_langs  TEXT[],     -- required subtitles for this country
      age_rating      TEXT,       -- 'PG', 'R', '18+' etc (country-specific)
      is_exclusive    BOOLEAN,    -- Netflix Original = exclusive globally
      PRIMARY KEY (content_id, country_code)
  );
  
  Geo-blocking:
    Playback Service: user in Germany requests Movie X.
    Check: SELECT * FROM content_rights WHERE content_id = X AND country_code = 'DE'.
    available_from <= now <= available_until? -> allow.
    No record? -> block. Return 403 with "Not available in your region."
  
  VPN detection:
    Users in Germany use VPN to appear in US -> access US-only content.
    Netflix detects VPN: compare user's IP with IP geolocation DB.
    Known VPN/proxy IP ranges: block or downgrade.
    CDN IP blocks: if user's IP is a known datacenter IP -> likely VPN.

LOCALIZATION PIPELINE:
  Each title needs: dubbed audio + subtitles for each supported language.
  Netflix: 30+ languages. 15,000 titles × 30 = 450,000 audio tracks.
  
  Dubbing workflow:
    Netflix contracts dubbing studios per language.
    Dialogue replacement: original audio swapped with dubbed audio.
    Lip sync: timing adjusted to match mouth movements.
    Quality control: Netflix QC team reviews each dubbed version.
    Upload: dubbed audio stored as separate HLS audio rendition.
    
  Subtitle workflow (faster than dubbing):
    Translation: subtitles translated (human or AI for simpler shows).
    Timing: synchronized to original audio.
    Format: .vtt (WebVTT) files served from CDN separately.
    Player: selects subtitle track based on user's language preference.

NETFLIX ORIGINALS STRATEGY:
  Problem: licensing costs growing. Studios raising prices. Exclusivity shrinking.
  Solution: produce own content. Netflix Originals.
  
  Advantages:
    No geo-restrictions: Netflix owns rights globally.
    No expiry: license is perpetual.
    Cost long-term: production cost < 10 years of licensing fees for hit shows.
    Data advantage: Netflix knows exactly what resonates with each market.
    "House of Cards" decision: data showed: users who liked Kevin Spacey + David Fincher +
    UK political dramas -> significant overlap. Greenlit show before filming.
  
  Storage: Netflix Originals masters stored in Netflix's own archive (not licensed).
  Multiple formats: 4K RAW + multiple codec variants kept forever.
  Original master kept for potential future re-encoding (when better codecs exist).
```

---

## STEP 14 — Extended Deep-Dive: Data Pipeline and Analytics

```
NETFLIX'S DATA SCALE:
  100M DAU × avg 10 hours watched = 1B hours/day.
  Data collected: every play/pause/seek/skip/rating/search action.
  ~500 events per user per session × 100M users = 50B events/day.
  
  This data powers: recommendations, content decisions, UI A/B tests, encoding optimization.

KAFKA PIPELINE:
  Every user action -> Kafka event -> multiple consumers:
  
  Topic: "playback.events"
    Producer: Netflix client app (iOS/Android/Smart TV/Web)
    Consumer 1: Real-time analytics (Flink streaming)
    Consumer 2: Recommendation model feature store
    Consumer 3: Data warehouse (S3 Parquet via Kafka Connect)
    Consumer 4: Anomaly detection (fraud, account sharing)
  
  Event schema (Avro):
  {
    "event_id": "uuid",
    "user_id": "user_xyz",
    "profile_id": "profile_abc",
    "content_id": "movie_123",
    "event_type": "PLAY | PAUSE | SEEK | STOP | SKIP_INTRO | RATE",
    "timestamp": 1726458600,
    "position_sec": 4320,       // where in the video
    "bitrate_kbps": 5000,       // what quality they were watching
    "device_type": "SMART_TV",
    "country": "US",
    "session_id": "sess_abc"
  }

APACHE SPARK FOR BATCH ANALYTICS:
  Daily batch jobs (Spark on AWS EMR):
    Job 1: Compute weekly recommendations for all 220M users.
    Job 2: Calculate per-title retention rate (% who finish watching).
    Job 3: Generate "Top 10 in [Country]" rankings per region.
    Job 4: Fill score computation for Open Connect CDN (what to push where).
    Job 5: A/B test result analysis (did new feature improve engagement?).
  
  Scale:
    Recommendation job: 44B user-item interactions -> Matrix Factorization -> 220M user vectors.
    Cluster: 2000 Spark workers × 16 cores each = 32,000 cores.
    Duration: ~3-4 hours for weekly recommendations. Runs Sunday night (low traffic).

APACHE FLINK FOR REAL-TIME STREAMING:
  Real-time use cases:
    "Top 10 in [Country] TODAY" — updated every 15 minutes.
    "Trending now" — updated every minute.
    Live error rate monitoring — catch CDN/playback issues immediately.
    Real-time personalization — update user model within session.
  
  Flink job for "Top 10 in US":
    Consume "playback.events" Kafka topic.
    Filter: country = "US" AND event_type = "PLAY".
    Window: sliding 24-hour window, updated every 15 minutes.
    Count plays per content_id within window.
    Rank by count -> emit top-10 list to Redis.
    
    Redis: "top10:US" -> [movie_123, show_456, ...] (JSON array). TTL 20 min.
    Catalog Service: "Top 10 in US" row reads from Redis. Always fresh.

A/B TESTING AT SCALE:
  Netflix runs 300+ A/B tests simultaneously.
  Each user: assigned to multiple test cohorts.
  
  Assignment:
    User logs in -> A/B service consulted: "which tests is this user in?"
    Stored in Redis: "ab_assignments:{user_id}" -> {"test_thumbnail_v2": "B", "test_autoplay": "A", ...}
    Assignment is deterministic: hash(user_id + test_name) % 100 -> group A (0-49) or B (50-99).
    Consistent: same user always in same group for same test.
    No coordination needed: assignment computed locally from hash.
  
  Metric collection:
    Test B users: measure engagement, watch time, cancellations.
    Minimum duration: 2 weeks (avoid day-of-week effect).
    Statistical significance: p < 0.05 (standard academic threshold).
    Netflix uses sequential testing (can stop early if effect is large).
  
  Feature flags (fast rollout):
    New feature ready. Want to roll out to 1% -> 5% -> 25% -> 100% gradually.
    Feature flag: "new_home_ui" -> percentage_enabled = 1.
    Deployment: flag changed via admin UI, no code deploy needed.
    Monitoring: if error rate spikes -> set percentage = 0 (instant rollback).
```


---

## DEEP-DIVE IMPROVEMENT: DRM — Digital Rights Management

```
DRM GOAL: prevent users from downloading and distributing content they don't own.
  Netflix pays billions for content licenses.
  Without DRM: one user downloads, shares — Netflix loses subscribers.
  With DRM: video is encrypted. You can only watch if you have a valid license key.
  License key = "this user has Netflix subscription + they are allowed to watch this title."

DRM SYSTEMS:
  Widevine (Google): used by Chrome, Android, smart TVs, Chromecast.
  PlayReady (Microsoft): used by Edge, Windows, Xbox.
  FairPlay (Apple): used by Safari, iOS, Apple TV.
  Netflix must support all three. Different browsers/devices = different DRM.

CONTENT KEY INFRASTRUCTURE:
  
  Step 1: Encoding (offline, one time per title):
    Content Key K: random 128-bit AES key generated for this title.
    Each encrypted HLS/DASH segment: AES-128-CBC(K, video_bytes).
    Content Key K stored in: Netflix's Key Management System (KMS). NEVER on CDN.
    CDN: serves only encrypted ciphertext. Cannot decrypt without K.
    
    Key Rotation: some titles use different K per segment (more secure).
    Attacker captures K for segment 100: can only decrypt that one segment.
  
  Step 2: License Acquisition (runtime, every play session):
    User presses Play on "Interstellar."
    
    Client → Netflix License Service:
    POST /drm/license
    {
        "content_id": "interstellar",
        "drm_type": "widevine",
        "challenge": base64(widevine_challenge_bytes)  // device-specific DRM challenge
    }
    Authorization: Bearer {jwt_token}
    
    License Service:
    1. Validate JWT: is user authenticated? Is subscription active?
    2. Check content rights: can this user watch "Interstellar" in their country?
    3. Fetch Content Key K from KMS: GET /kms/keys/{content_id}
    4. Encrypt K using Widevine server: Widevine server wraps K with device's public key.
       Result: encrypted key blob that ONLY this device's secure hardware can decrypt.
    5. Return license (encrypted key blob + playback restrictions).
    
    Playback restrictions in license:
      max_resolution: "1080p" (4K requires separate tier + HDCP-capable TV)
      allow_hdcp_bypass: false (must have HDCP-2.2 connection for 4K)
      license_duration: 86400 (offline license valid 24 hours for downloads)
      rental_expiry: null (owned content, no expiry)
  
  Step 3: Secure Playback:
    Device's secure hardware (TEE — Trusted Execution Environment) receives license.
    TEE decrypts: K = decrypt(encrypted_key_blob, device_private_key).
    TEE decrypts video segments: AES-128-CBC(K, segment_ciphertext).
    Decrypted video: goes directly to decoder chip. NEVER touches app memory as plaintext.
    Screen recording: TEE enforces HDCP. Screen capture APIs: video shows as black rectangle.
    Memory dump: no useful plaintext video in RAM. 
    This is why screen recording Netflix shows a black screen.

OFFLINE DOWNLOADS:
  Netflix allows download for offline viewing (mobile app).
  
  Download flow:
    1. User taps Download. Client: POST /download/initiate?content_id=X
    2. Server: create offline license (valid 30 days).
       License includes: content key K + expiry timestamp.
    3. Client: download encrypted video segments to local storage.
    4. Client: store license in secure enclave on device.
    
  Offline playback:
    1. Check: is license still valid? now < license.expiry? ✓
    2. Check: has user connected to Netflix in last 30 days? ✓
       (Anti-sharing: must be online periodically to refresh download license.)
    3. TEE decrypts segments using stored K.
    4. Play.
  
  Download expires after 30 days:
    License expiry hits. K wiped from secure enclave. Video segments remain on disk.
    But without K: encrypted bytes are useless. Effectively deleted.
    User must re-download (requires active subscription).

ANTI-PIRACY FORENSIC WATERMARKING:
  Problem: screen-capture rigs can still record (camera pointed at screen).
  Screen recording catches decoded video before HDCP, for example a camera pointed at the TV.
  Solution: forensic watermarking. Invisible watermark embedded in the video.
  
  Per-user watermarking:
    At CDN: video stream slightly modified per user (specific pixel patterns in certain frames).
    Pattern is imperceptible to human eye.
    Each user gets a unique pattern (based on user_id + timestamp).
    
    If pirated video found online:
      Netflix extracts watermark → identifies user who recorded it.
      Account terminated + potential legal action.
  
  Why "per-user watermarking" at CDN scale is hard:
    Cannot pre-encode unique video per user (too much storage).
    Solution: A/B versions. Encode TWO versions of each segment (version A and B).
    User's watermark: a binary string. Bit 0 = segment from version A. Bit 1 = version B.
    CDN serves: segment_1_A + segment_2_B + segment_3_A + ... for each user.
    Watermark: bit pattern of A/B choices across N segments.
    N segments: 128 segments → 2^128 unique watermarks. Enough for all users.
    
    CDN implementation: edge logic reads user watermark from JWT → selects A or B per segment.
    Storage: 2× per title (A + B versions for each segment). 2× storage overhead.
    Worth it: prevents mass piracy of premium content.
```

---

## DEEP-DIVE IMPROVEMENT: Video Encoding — Codec Selection and Efficiency

```
CODEC CHOICES AND WHY THEY MATTER:

H.264 (AVC — Advanced Video Coding):
  Released: 2003. Most universally supported (every device made since 2007).
  Compression: good (baseline 5 Mbps for 1080p30).
  Patent: MPEG-LA holds patents. Netflix pays licensing fees.
  Netflix use: main codec for low-end devices, live streams, older smart TVs.

H.265 (HEVC — High Efficiency Video Coding):
  Released: 2013. ~50% better compression than H.264.
  Compression: 1080p30 at 2.5 Mbps vs H.264's 5 Mbps. Same quality, half the bandwidth!
  Patent: complex patent pool. Higher licensing fees than H.264.
  Netflix use: 4K HDR content, high-end smart TVs, Apple devices.

VP9 (Google):
  Released: 2013. Similar to HEVC. Royalty-FREE.
  Compression: ~40-50% better than H.264.
  Support: Chrome, Firefox, Android, YouTube. Not Safari (until recent versions).
  Netflix use: streaming to Chrome/Firefox browsers. Significant cost savings (no patent fees).

AV1 (Alliance for Open Media):
  Released: 2018. ~30% better than HEVC. Also royalty-FREE.
  Support: Chrome, Firefox, Android 10+. Growing rapidly.
  Encoding speed: 10× slower to encode than H.264 (more CPU-intensive).
  Netflix use: gradually rolling out. Target: AV1 as primary codec by 2026.
  Benefit: same quality at 30-40% lower bitrate → less CDN bandwidth → millions in savings.

ENCODING PROFILES NETFLIX GENERATES PER TITLE:
  
  Codec × Resolution × Frame Rate × HDR variants:
  
  H.264  360p  23.976fps  SDR
  H.264  480p  23.976fps  SDR
  H.264  720p  23.976fps  SDR
  H.264  720p  23.976fps  SDR   (mobile-optimized, lower bitrate)
  H.265  1080p 23.976fps  SDR
  H.265  1080p 23.976fps  HDR10
  H.265  2160p 23.976fps  SDR
  H.265  2160p 23.976fps  HDR10
  H.265  2160p 23.976fps  Dolby Vision
  VP9    360p  23.976fps  SDR
  VP9    1080p 23.976fps  SDR
  AV1    1080p 23.976fps  SDR
  ...and more for different frame rates (30fps, 60fps for sports content)
  
  Total: 30-40 encoding profiles per title.
  For a 2-hour movie: 120 chunks × 35 profiles = 4,200 encoding jobs.
  Each job: 30 seconds - 5 minutes on a GPU.
  Estimated total encoding compute: 4,200 × 3 min avg = 210 GPU-hours per movie.
  
  Cost: at $3/GPU-hour (AWS): $630 to encode one movie.
  Netflix releases 500+ titles/year: $315,000/year just for encoding. Small vs content cost.

BITRATE LADDER OPTIMIZATION (per-title, not fixed):
  
  OLD approach (fixed bitrate ladder):
    Same bitrate ladder for ALL titles:
    360p: 500 Kbps
    720p: 2,000 Kbps
    1080p: 5,000 Kbps
    4K: 15,000 Kbps
    
    Problem: animation (simple colors) and sports (high motion) need very different bitrates.
    Animation: 1080p looks perfect at 1,000 Kbps. Giving it 5,000 Kbps = wasted 4 Mbps.
    Sports: fast motion, lots of texture. 1080p needs 8,000 Kbps to avoid artifacts.
    Fixed ladder: wastes bandwidth on simple content, insufficient for complex content.
  
  NETFLIX's PER-TITLE ENCODING:
    Analyze each title: compute complexity score per scene.
    Complexity metrics:
      Spatial information (SI): how much detail is in each frame?
      Temporal information (TI): how much does the image change between frames?
    
    Low-complexity title (animated movie): encode 1080p at 1,500 Kbps (vs 5,000 fixed).
    High-complexity title (action movie): encode 1080p at 7,000 Kbps.
    
    Result: 20% average bandwidth reduction across all titles.
    Netflix streams 100M+ hours/day × 5 Mbps avg = 500 Gbps × 20% savings = 100 Gbps saved.
    100 Gbps × $0.01/GB CDN cost = $86,400/day savings. $31.5M/year from one optimization!

CHUNKED ENCODING PIPELINE (parallel):
  Goal: encode a 2-hour movie in 30 minutes, not 2 hours.
  
  Splitting strategy:
    Split at Scene Cuts (not arbitrary time boundaries):
    Frame detector: compare adjacent frames. Large difference = scene cut.
    Split ONLY at scene cuts → each chunk is a complete "scene."
    Why? Encoding across a scene cut is slightly less efficient. Splitting at cuts = better quality.
    Each chunk: 30s to 5 min of video (depending on scene length).
    2-hour movie: ~200 chunks.
  
  Parallel encoding farm:
    200 chunks × 35 profiles = 7,000 encoding jobs.
    Each job dispatched to Kubernetes pod with GPU.
    With 500 GPU workers: 7,000/500 = 14 jobs per worker = 14 × avg 2 min = 28 min.
    Total: 2-hour movie encoded in ~30 minutes from raw to CDN-ready. ✓
  
  Assembly:
    After all chunks encoded: stitch into DASH/HLS manifests.
    No actual video stitching (segments play seamlessly at chunk boundaries).
    Manifest: a text file listing all segment URLs with timestamps.
    Manifest upload: < 1 second.
```

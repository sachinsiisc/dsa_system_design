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

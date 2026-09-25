# Topic 3: Load Balancing
## HLD Deep Dive | MAANG Interview Ready

---

## 1. What Is a Load Balancer?

```
A load balancer distributes incoming traffic across multiple backend servers.

Without LB:
  All 100,000 req/sec → Server A → overloaded → 5xx errors.
  Servers B and C: idle.

With LB:
  100,000 req/sec → LB → ~33K to Server A, ~33K to B, ~33K to C.
  All servers at ~33% utilization. Fast responses.

Benefits:
  1. Horizontal scalability: add servers, LB distributes more traffic.
  2. High availability: server fails → LB stops sending traffic to it.
  3. Graceful deploys: take servers out of rotation one-by-one, deploy, add back.
  4. SSL termination: decrypt HTTPS once at LB, HTTP to backends.
```

---

## 2. Layer 4 vs Layer 7 Load Balancing

```
OSI MODEL CONTEXT:
  Layer 4 = Transport Layer (TCP/UDP) → sees IP + port only
  Layer 7 = Application Layer (HTTP) → sees URL, headers, cookies, body

LAYER 4 LOAD BALANCER:
  Routes based on IP address and port.
  Does NOT read HTTP content.
  Very fast (just IP/TCP header inspection).
  
  What it CAN do:
    - Route TCP connections
    - NAT (Network Address Translation)
    - Basic health checks (can TCP connect to port 80?)
  
  What it CANNOT do:
    - Route based on URL path
    - Route based on HTTP headers
    - Session affinity via cookies (can only do IP-based sticky)
  
  Examples: AWS NLB, HAProxy (TCP mode), Nginx (stream module)
  
  Use when: raw TCP routing, very high throughput (millions of connections/sec),
             WebSocket (persistent TCP connections), game servers.

LAYER 7 LOAD BALANCER:
  Reads HTTP request. Understands URLs, headers, cookies, body.
  Slightly more expensive (HTTP parsing overhead).
  
  What it CAN do:
    - Route /api/* → API servers, /static/* → file servers
    - A/B testing: route 10% of users to new version
    - SSL termination
    - HTTP compression (gzip)
    - Rate limiting per user/IP
    - Request/response modification (add headers, rewrite URLs)
    - Cookie-based sticky sessions
    - WebSocket upgrade handling
    - Health checks at HTTP level (GET /health → 200 OK)
  
  Examples: AWS ALB, Nginx (HTTP mode), HAProxy (HTTP mode), Cloudflare, Envoy, Traefik
  
  Use when: web applications, APIs, microservices routing.

NGINX CONFIGURATION EXAMPLE:
  upstream api_servers {
      least_conn;                    # algorithm: least connections
      server api-1:8080 weight=2;    # gets 2× traffic of others
      server api-2:8080;
      server api-3:8080;
      keepalive 32;                  # keep 32 persistent connections to backends
  }

  server {
      listen 443 ssl http2;          # L7: HTTP/2 SSL termination
      
      location /api/ {
          proxy_pass http://api_servers;
          proxy_set_header Host $host;
          proxy_set_header X-Real-IP $remote_addr;
          proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      }
      
      location /static/ {
          proxy_pass http://static_file_servers;
          expires 1d;
          add_header Cache-Control "public";
      }
  }
```

---

## 3. Load Balancing Algorithms

```
1. ROUND ROBIN:
   Requests go: A → B → C → A → B → C → ...
   
   Best for: identical servers, identical request costs.
   Problem: "elephant requests" — Server A gets a 30-second DB query,
            B and C get fast queries → A is stuck, C is underloaded.

2. WEIGHTED ROUND ROBIN:
   Server A: weight=3, B: weight=2, C: weight=1.
   Pattern: A,A,A,B,B,C,A,A,A,B,B,C,...
   
   Best for: heterogeneous servers (different hardware specs).
   Use when: one server has 16 cores, another has 4 cores.

3. LEAST CONNECTIONS:
   Route to server with FEWEST active connections right now.
   
   State: A=45 active, B=12 active, C=38 active → route to B.
   
   Best for: long-lived connections (file uploads, WebSocket, streaming).
   Because: round robin would send to A even if A has 100 slow connections.
   
   Variant: Weighted Least Connections (factor in server capacity).

4. IP HASH (Sticky Sessions):
   hash(client_IP) % num_servers → always same server.
   
   Best for: stateful servers that store session locally (legacy apps).
   Problem: if server dies, that IP hash's users lose session.
   Problem: Nat/proxy → all users appear as same IP → uneven distribution.
   Fix: Better to use Redis sessions (truly stateless) instead.

5. LEAST RESPONSE TIME:
   Route to server with lowest combination of: response time + connections.
   Nginx Plus, Envoy: actively track p99 response time per backend.
   
   Best for: heterogeneous workloads where some requests are much slower.

6. RANDOM:
   Randomly select a server.
   Surprisingly good: mathematically close to round robin for large N.
   Used by: AWS ALB internally.

7. CONSISTENT HASHING (for cache routing):
   hash(request) → deterministic server.
   Same request always goes to same server → maximize cache hit rate.
   Adding/removing servers: only re-routes ~1/N of requests (vs hash % N which re-routes all).
   
   Used by: Nginx for proxy_cache, Memcached client libraries.

ALGORITHM SELECTION GUIDE:
  Same servers, simple API → Round Robin
  Different server capacities → Weighted Round Robin
  Long-lived connections → Least Connections
  Maximize cache hits → Consistent Hashing
  Legacy stateful app → IP Hash (or fix app to use Redis sessions)
  Best general → Least Response Time (if supported by your LB)
```

---

## 4. Health Checks

```
ACTIVE HEALTH CHECKS (LB polls backends):
  
  HTTP health check:
    LB sends: GET /health HTTP/1.1 every 10 seconds
    Healthy: 200 OK within 2 seconds
    Unhealthy: non-200 or timeout
    
    After 2 consecutive failures → mark server unhealthy → stop routing.
    After 3 consecutive successes → mark healthy → resume routing.
  
  TCP health check:
    LB attempts TCP connect to port 8080.
    Connection established → healthy.
    Connection refused or timeout → unhealthy.
    Use when: app doesn't have /health endpoint, or for non-HTTP.

  Graded health checks (advanced):
    /health/live  → is the process alive? (for Kubernetes liveness probe)
    /health/ready → is it ready to serve traffic? 
                    (checks DB connection, cache connection)
    /health/full  → detailed status (DB, cache, external APIs)
    
    LB uses /health/ready → doesn't send traffic until DB is connected.
    Kubernetes: if /health/live fails → restart pod.
                if /health/ready fails → remove from Service endpoints (no traffic).

HEALTH CHECK ENDPOINT:
  # Python FastAPI health check
  from fastapi import FastAPI
  from databases import Database
  import redis

  app = FastAPI()
  db = Database("postgresql://...")
  cache = redis.Redis(host="redis")

  @app.get("/health/ready")
  async def health_check():
      try:
          await db.execute("SELECT 1")    # DB reachable?
          cache.ping()                    # Redis reachable?
          return {"status": "healthy", "db": "ok", "redis": "ok"}
      except Exception as e:
          raise HTTPException(503, detail=f"Unhealthy: {e}")

PASSIVE HEALTH CHECKS (circuit breaker):
  Monitor real traffic for errors.
  If Server A returns 5xx for 5 consecutive requests → mark unhealthy.
  Advantage: catches subtle issues (right responses but wrong data).
  Used by: Envoy, Nginx Plus.
```

---

## 5. SSL Termination

```
SSL/TLS TERMINATION AT LOAD BALANCER:

Client → HTTPS → [Load Balancer] → HTTP → [Backend Servers]
               (terminate TLS here)    (plain HTTP internally)

Advantages:
  - Backend servers don't do expensive TLS crypto (CPU savings)
  - One place to manage certificates (not on every server)
  - LB can inspect HTTP content (for routing, headers, logging)
  - Centralized certificate renewal (Let's Encrypt with Certbot)

Backend communication options:
  1. Plain HTTP (most common inside VPC — trusted network)
  2. HTTPS (for compliance — PCI DSS, HIPAA may require end-to-end encryption)
  3. mTLS (mutual TLS — both LB and backend authenticate each other)

CERTIFICATE MANAGEMENT:
  Let's Encrypt: free, auto-renewal every 90 days.
  AWS Certificate Manager: free with ALB, auto-renewal.
  Certificates in Kubernetes: cert-manager (automated Let's Encrypt).

WILDCARD CERTIFICATES:
  *.example.com covers: api.example.com, app.example.com, admin.example.com.
  One cert for all subdomains.
```

---

## 6. Global Load Balancing

```
PROBLEM: You have servers in us-east-1 and ap-south-1.
How do you route users to the nearest region?

APPROACH 1: GeoDNS
  DNS returns different IP based on user's geographic location.
  User in India → DNS resolves to ap-south-1 LB IP.
  User in US → DNS resolves to us-east-1 LB IP.
  
  Providers: AWS Route 53 (Geolocation Routing), Cloudflare.
  Failover: if ap-south-1 health check fails → Route 53 routes India users to us-east-1.

APPROACH 2: Anycast
  Both regions advertise same IP via BGP.
  Internet routing sends user to nearest BGP peer (closest region).
  
  Used by: Cloudflare, Google, Fastly.
  Advantage: no DNS TTL delay for failover. BGP reconverges in seconds.

APPROACH 3: Traffic Manager (AWS Global Accelerator)
  Entry points in 100+ cities worldwide (AWS edge locations).
  User connects to nearest edge → private AWS backbone to origin.
  Reduces number of internet hops (slower, variable) vs private backbone (fast, consistent).
  
  Result: 50-75% lower latency + higher reliability vs routing entirely over public internet.

ACTIVE-ACTIVE vs ACTIVE-PASSIVE:
  Active-Active: both regions serve traffic simultaneously.
    Pro: use full capacity, lower latency globally.
    Challenge: data sync between regions (write conflicts).
  
  Active-Passive: one region serves all, other is standby.
    Pro: no sync complexity.
    Con: standby region is wasted capacity until failover.
    Con: failover time = DNS TTL + connection drain time (30-120 seconds).
```

---

## 7. Rate Limiting at the Load Balancer

```
WHY AT LB:
  Rate limit before requests reach your app servers.
  Prevents one client from overwhelming your system.

NGINX RATE LIMITING:
  # Limit per IP: 10 requests/second
  limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
  
  server {
      location /api/ {
          limit_req zone=api_limit burst=20 nodelay;
          # burst=20: allow 20 extra requests, then 429
          # nodelay: don't delay burst requests, serve immediately
          
          limit_req_status 429;
          proxy_pass http://api_servers;
      }
  }

AWS WAF (Web Application Firewall):
  Rate limit by IP: block if > 2000 requests in 5 minutes.
  Country blocking: block all traffic from specific countries.
  SQL injection / XSS protection.
  Bot detection.

CLOUDFLARE RATE LIMITING:
  Rules: "If URI path matches /api/* AND request rate > 100/min per IP → block for 1 hour."
  Bot Fight Mode: challenge suspicious traffic patterns.
```

---

## 8. Load Balancer High Availability

```
PROBLEM: The load balancer itself is a single point of failure!

SOLUTION 1: Active-Passive LB pair
  Two LBs: one primary, one standby.
  Virtual IP (VIP) floats between them.
  If primary fails → standby takes VIP via VRRP/Keepalived → takes over in <1 second.
  
  Implementation:
    LB-1 (primary): 10.0.0.1, VIP: 10.0.0.100
    LB-2 (standby): 10.0.0.2, also claims VIP 10.0.0.100
    Keepalived: monitors LB-1. If LB-1 down → LB-2 claims VIP.
    Clients connect to 10.0.0.100 → always works.

SOLUTION 2: DNS-based failover
  LB-1 fails health check → Route 53 removes its IP from DNS.
  Clients get LB-2 IP instead.
  Failover time: DNS TTL (typically 60 seconds).

SOLUTION 3: Managed LB (AWS ALB, GCP Load Balancer)
  AWS ALB is a managed service with built-in HA.
  Distributed across multiple AZs. No SPOF by design.
  SLA: 99.99% availability.
  You don't manage the LB infrastructure at all.
  
  Best for: most production systems. Don't manage your own LB if managed is available.
```

---

## 9. Connection Draining (Graceful Shutdown)

```
PROBLEM: You remove Server A from LB during deployment.
         Active requests to Server A are abruptly terminated.
         Users get connection errors mid-request.

SOLUTION: Connection draining (a.k.a. deregistration delay)

Process:
  1. Remove Server A from LB rotation (stop sending NEW requests).
  2. Wait for existing connections to complete (drain period: 30-300 seconds).
  3. Force-close any remaining connections after drain period.
  4. Server A is now safe to shut down/deploy.

AWS ALB: "Deregistration Delay" setting (default: 300 seconds).
Kubernetes: Pod graceful termination period (terminationGracePeriodSeconds: 30).

KUBERNETES GRACEFUL SHUTDOWN:
  # 1. Kubernetes sends SIGTERM to pod
  # 2. Pod stops accepting new requests (closes listener)
  # 3. Pod drains existing connections (max 30 seconds by default)
  # 4. Kubernetes sends SIGKILL if not done in time
  
  # Python FastAPI graceful shutdown:
  import signal
  import asyncio
  
  shutting_down = False
  
  @app.middleware("http")
  async def reject_when_shutting_down(request, call_next):
      if shutting_down:
          return JSONResponse({"error": "service unavailable"}, status_code=503)
      return await call_next(request)
  
  def handle_sigterm(*args):
      global shutting_down
      shutting_down = True
      # Wait for in-flight requests to complete, then exit
  
  signal.signal(signal.SIGTERM, handle_sigterm)
```

---

## 10. Interview Questions

```
Q1: "What's the difference between L4 and L7 load balancing?"
A: L4 routes by IP/port (fast, no HTTP parsing). L7 reads HTTP headers/URL (smart routing).
   L4 use: TCP routing, game servers, WebSocket at massive scale.
   L7 use: web apps, API routing, A/B testing.

Q2: "How do you handle sticky sessions if sessions are in memory?"
A: Don't use in-memory sessions — use Redis.
   Redis sessions: any server can serve any user. True horizontal scaling.
   If you must use memory sessions: IP hash LB algorithm (but loses on server failure).

Q3: "What happens when a load-balanced server crashes?"
A: Health check detects failure (within 2 failed checks × interval).
   LB stops routing to failed server.
   Existing connections: depends on TCP layer — connection reset, client retries.
   In-flight requests lost: design clients to retry idempotent requests.

Q4: "How do you do zero-downtime deployments?"
A: Rolling deploy: take servers out of LB one-by-one. Deploy. Health check passes. Add back.
   Blue-green: entire new fleet ready. Switch LB from blue to green atomically.
   Canary: route 1% to new version. Watch errors. Gradually increase %.
   All three require: stateless servers, connection draining.

Q5: "Can the load balancer become a bottleneck?"
A: Yes. A single LB can handle ~1M req/sec (software LB like Nginx).
   Fix: DNS round robin across multiple LBs. Or managed LB (AWS ALB) with built-in scaling.
   AWS ALB: scales automatically. You can't even see the individual LB instances.
```


---

## HOW THESE HLD CONCEPTS APPEAR IN THE CASE STUDIES

### Scalability (this file) — Case Study Connections

**CS04 Uber:** Horizontal scaling of ride-service. Stateless pods. Geo-shard drivers.
Adding India capacity: deploy more pods. No code change. Just config.

**CS06 YouTube:** CDN scales video delivery without scaling origin servers.
Async transcode queue: upload completes in 2s. Transcode takes 10 min in background.

**CS09 Payment Gateway:** Idempotency makes any node retry-safe. Horizontal scale-friendly.
Stateless: transaction state in PostgreSQL. Any instance handles any request.

### Load Balancing (HLD 03) — Case Study Connections

**CS04 Uber:** L4 LB at TCP level (fast). L7 routes by URL path to microservices.
/api/rides/* → ride-service. /api/payments/* → payment-service.

**CS01 URL Shortener:** L4 round-robin. All nodes identical (same Redis data). Millions of redirects/s.

**CS08 Twitter:** Fanout workers use consistent hashing LB on user_id. Same user → same worker.

### Caching (HLD 04) — Case Study Connections

**CS04 Uber:** Redis for driver locations (TTL 30s). Fare estimate cache 60s.
LLD link: CachingDecorator (T04) wraps DriverLocationService.

**CS06 YouTube:** CDN edge caches video segments (Cache-Control: max-age=86400).
Redis caches: metadata, search results (TTL 300s). LLD: CachingSearchDecorator.

**CS07 Google Search:** Top 1000 query results in in-memory cache. PageRank cached weekly.

**CS09 Payment Gateway:** Fraud scores cached per session. Exchange rates cached 60s.

### Databases (HLD 05) — Case Study Connections

**CS04 Uber:** PostgreSQL (trips, ACID). Redis (locations, TTL). Cassandra (analytics, high writes).

**CS06 YouTube:** MySQL (metadata, joins). Bigtable (counts, high write throughput). GCS (binary blobs).

**CS09 Payment Gateway:** PostgreSQL (payments, ACID — money never loses consistency).
Redis (idempotency keys, fast check). Elasticsearch (search transaction history).

### Message Queues (HLD 06) — Case Study Connections

**CS06 YouTube:** Kafka — upload event → transcode + notification + analytics workers.
Dead-letter queue for failed transcode jobs.
LLD link: Command pattern (TranscodeCommand object published to queue).

**CS08 Twitter:** Kafka — tweet published → fanout workers. Partitioned by user_id.
Consumer group pattern. One partition per worker. In-order delivery per user.

**CS09 Payment Gateway:** Kafka — PaymentCompleted event consumed by inventory, ledger, fraud.
Outbox pattern: DB write + Kafka publish in same transaction (no lost events).

### CAP Theorem (HLD 07) — Case Study Connections

**CS04 Uber (AP):** Driver location: show stale GPS during partition. Don't block ride requests.
Availability > perfect consistency for location data.

**CS09 Payment Gateway (CP):** During partition: REFUSE payment. No double-charge risk.
Consistency > availability for money. User retries later after partition heals.

**CS01 URL Shortener (AP):** New URL: replication lag ok (1-2s). User waits 2s then shares link.
Read-your-write: route creator's first redirect to primary DB.

### Consistency Models (HLD 08) — Case Study Connections

**CS08 Twitter:** Eventual consistency for follower timelines (fanout takes 100ms-5s).
Strong consistency for your own tweets: you see them immediately (read-your-write).

**CS05 Netflix:** Strong consistency for "continue watching" (your progress, read-your-write).
Eventual consistency for global trending content lists (updated every few minutes).

**CS09 Payment:** Strong (ACID) for account balance. Cannot ever be eventually consistent for money.

### API Design (HLD 09) — Case Study Connections

**CS04 Uber:** POST /api/v1/rides → create. WebSocket for real-time driver location push.
REST for commands. WebSocket for streaming state updates.

**CS09 Payment:** POST /v1/payments with Idempotency-Key header. Webhook on completion.
Async pattern: respond PENDING immediately, webhook when CAPTURED/FAILED.

**CS11 AI Systems:** POST /v1/chat/completions. SSE for streaming tokens to client.
Compatible with OpenAI API format (LLD: Adapter pattern for multiple providers).

### Rate Limiting (HLD 12) — Case Study Connections

**CS09 Payment Gateway:** Per-merchant 1000 req/s (token bucket). Per-card 10/hour (sliding window).
LLD link: RateLimitDecorator (T04) wraps PaymentProcessor.

**CS11 AI Systems:** Per-user 60 req/min. Redis ZADD + ZCOUNT sliding window.
LLD link: RateLimitDecorator wraps LLMAdapter.

**CS04 Uber:** 5 ride requests/min per user. Gateway enforces before service sees it.

### Consistent Hashing (HLD 11) — Case Study Connections

**CS04 Uber:** Driver geo-sharding. Adding new city shard: only that geo-hash remaps.
Simple modulo would remap ALL drivers on scale event (bad for production).

**CS01 URL Shortener:** Redis cluster. Consistent hashing: adding node remaps only 1/N keys.
Simple modulo: adding node remaps ALL keys → cache miss storm.

**CS08 Twitter:** Kafka partition by user_id = consistent hashing at infra level.
Same user's fanout always goes to same worker. Ordering guaranteed.

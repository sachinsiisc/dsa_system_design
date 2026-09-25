# Topic 1: Networking Basics — How the Internet Works
## HLD Deep Dive | Every Point Explained in Plain English | MAANG Interview Ready

---

> **HOW TO READ THIS FILE**
> Every concept has two parts:
> 1. The technical fact (in code blocks)
> 2. A plain English explanation immediately below it — labelled **WHAT THIS MEANS**
> Read both. Never skip the explanation.

---

## 1. What Is Networking in System Design?

```
Networking = how data moves between machines.
Every system design starts with a request traveling from client to server.
Understanding this journey lets you:
  - Identify latency sources
  - Choose the right protocol (HTTP vs WebSocket vs gRPC)
  - Design for reliability (retries, timeouts, circuit breakers)
  - Optimize with CDN, connection pooling, keep-alive
```

**WHAT THIS MEANS:**
- When you open Instagram on your phone, your phone sends a message across the internet to Instagram's servers in California. The servers send back your photos. This back-and-forth is "networking."
- As a system designer, you need to understand *every step* of that journey because **each step has a cost** (time, money, failure risk).
- If you don't understand networking, you'll design systems that are slow, fragile, or wasteful.

---

## 2. The Full Journey: Browser → Server

### 2.1 Step-by-Step: What happens when you type `amazon.com`

---

### STEP 1: DNS RESOLUTION

```
DNS = Domain Name System = the internet's phone book.

Browser cache → OS hosts file → OS DNS cache → Router cache
→ ISP Recursive Resolver → Root Nameserver → TLD (.com) Nameserver
→ Authoritative Nameserver for amazon.com
→ Returns: 205.251.242.103 (an IP address)
```

**WHAT THIS MEANS — Plain English:**
- Your browser knows how to reach IP addresses like `205.251.242.103` (a number). But you typed `amazon.com` (a name). DNS translates the name into a number.
- Think of it like a contacts app: you search for "Amazon" and it gives you their phone number.
- Your computer checks several places in order, fastest first:
  1. **Browser cache** — "Did I look this up recently?" If yes, use that saved answer.
  2. **OS hosts file** — A local file on your computer (`C:\Windows\System32\drivers\etc\hosts`). Developers use this to redirect `amazon.com` to `localhost` for testing.
  3. **OS DNS cache** — The operating system's recent memory of DNS lookups.
  4. **Router cache** — Your WiFi router also caches DNS answers.
  5. **ISP Recursive Resolver** — Your internet provider's DNS server (like Jio's DNS). This is the main workhorse that does the full lookup.
  6. **Root Nameserver** — Knows which server handles `.com` domains.
  7. **TLD (.com) Nameserver** — Knows which server handles `amazon.com` specifically.
  8. **Authoritative Nameserver** — The final authority. Amazon controls this. It says "amazon.com = 205.251.242.103."

```
TTL (Time-To-Live): How long DNS result is cached.
  amazon.com TTL: 60 seconds (short → fast failover if IP changes)
  cdn.example.com TTL: 3600 seconds (long → CDN IPs change rarely)
```

**WHAT THIS MEANS — TTL:**
- TTL = how many seconds other people are allowed to cache (remember) your DNS answer.
- If TTL = 60, every 60 seconds the world re-checks what IP `amazon.com` points to.
- **Why short TTL?** If Amazon's server in `205.251.242.103` crashes and they switch to a new IP, everyone discovers the new IP within 60 seconds. If TTL was 1 day, users would keep hitting the dead server for 24 hours.
- **Why long TTL?** CDN servers rarely change IPs. No need to re-lookup every minute. Long TTL = less DNS traffic = cheaper.

```
WHY THIS MATTERS IN INTERVIEW:
  DNS TTL limits how fast you can failover. If your server IP changes,
  all clients with cached DNS keep hitting the old IP for up to TTL seconds.
  Netflix, Amazon: short TTLs (~60s) for fast disaster recovery.
```

**WHAT THIS MEANS — Interview Hook:**
- In a MAANG interview: if you say "if our server fails, we'll change the DNS to a backup server," the interviewer WILL ask: "how long will it take for the change to take effect?" Answer: up to TTL seconds. That's why production systems use short TTLs (60 seconds).

---

### STEP 2: TCP 3-WAY HANDSHAKE

```
TCP = Transmission Control Protocol = reliable delivery guarantee.
Before any data is sent, client and server must "shake hands" to agree they're both ready.

Client → Server:  SYN   (seq=100, "I want to talk, my sequence starts at 100")
Server → Client:  SYN-ACK (seq=200, ack=101, "OK, I'm ready, my sequence starts at 200")
Client → Server:  ACK   (ack=201, "Got it, let's go")

Cost: 1 round trip BEFORE any data is sent.
  If client is in India, server in US: 1 RTT ≈ 200ms just for handshake.
  This is why CDN edge servers are geographically close.
```

**WHAT THIS MEANS — Plain English:**
- Imagine calling someone on the phone:
  - You call them: "Hello, can you hear me?" (SYN)
  - They answer: "Yes I can hear you, can you hear me?" (SYN-ACK)
  - You say: "Yes!" (ACK)
  - NOW you start talking (actual data)
- **seq numbers:** Every byte sent gets a sequence number so the receiver knows if anything is missing. seq=100 means "my first byte is number 100."
- **ack:** Acknowledgment. ack=101 means "I received everything up to byte 100, now send me byte 101."
- **The cost:** This entire handshake must complete before one byte of your actual request is sent. If you're in India and the server is in the US, light takes ~200ms to travel there and back. So just the handshake costs 200ms — before you even see any data!

```
This is why CDN edge servers are geographically close.
```

**WHAT THIS MEANS:**
- A CDN (Content Delivery Network) places servers near you. If there's a server in Mumbai, your handshake is 5ms instead of 200ms. That's 40× faster, from just the handshake alone.

---

### STEP 3: TLS HANDSHAKE (for HTTPS)

```
TLS = Transport Layer Security = encryption so nobody can read your data in transit.
HTTPS = HTTP + TLS.

TLS 1.2: 2 RTTs after TCP. Total: 3 RTTs before first byte of data.
TLS 1.3: 1 RTT (or even 0-RTT for resumed sessions). Major improvement.

TLS 1.3 Handshake:
  Client → Server: ClientHello + key_share (DH public key)
  Server → Client: ServerHello + key_share + Certificate + Finished
  Client → Server: Finished + First HTTP request (all in one!)
  
  0-RTT (session resumption):
    Client already has a "session ticket" from previous connection.
    Client → Server: 0-RTT data (first request immediately, no wait)
    Downside: 0-RTT is NOT replay-safe. Only use for safe GET requests.
```

**WHAT THIS MEANS — Plain English:**
- When you visit `https://amazon.com`, all your data (credit card, password) is encrypted so even if someone intercepts it, they can't read it.
- TLS is the encryption layer. Before encryption starts, the client and server must agree on HOW to encrypt (which cipher, which key).

**TLS 1.2 (Old, slower):**
- Round trip 1: "Hello, here's what encryption methods I support"
- Round trip 2: "OK, here's my certificate (proof of identity), here's the chosen method"
- Round trip 3: THEN your actual request goes
- That's 3 round trips = 600ms from India to US before you see any response!

**TLS 1.3 (New, faster):**
- Round trip 1: Client sends "Hello" + already includes a public key guess (starts key exchange immediately)
- Server replies with certificate + encrypted response + key
- The FIRST HTTP request piggybacks on the same round trip as the TLS Finished message
- That's 2 round trips total, not 3

**0-RTT (Zero round trip):**
- If you visited the same site recently, your browser saved a "session ticket" (like a temporary VIP pass)
- Next time: your FIRST request goes out immediately, no handshake needed at all
- **But why is it unsafe for POST?** If someone intercepts and replays the 0-RTT packet (sends it again), the server would execute the same request twice. A GET (just reading data) repeated is fine. A POST (placing an order) repeated means buying twice. So 0-RTT is only for GET requests.

---

### STEP 4 & 5: HTTP Request/Response

```
GET / HTTP/1.1
Host: amazon.com
Accept: text/html,application/xhtml+xml
Accept-Encoding: gzip, br
Cookie: session=abc123
Connection: keep-alive
```

**WHAT EACH HEADER MEANS:**
- `GET /` — "I want the homepage. Method=GET means read-only, no body, don't change anything"
- `Host: amazon.com` — Since multiple sites can live on the same IP, this tells the server which site you want
- `Accept: text/html` — "I can understand HTML. Send me HTML please."
- `Accept-Encoding: gzip, br` — "I know how to decompress gzip and brotli formats. Compress the response to save bandwidth."
- `Cookie: session=abc123` — "I logged in earlier and got this session ID. Use it to know who I am."
- `Connection: keep-alive` — "After responding, DON'T close the connection. I'll send more requests."

```
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
Content-Encoding: gzip
Cache-Control: no-store
Transfer-Encoding: chunked
```

**WHAT EACH RESPONSE HEADER MEANS:**
- `200 OK` — Success. (Other codes: 404=not found, 500=server error, 301=moved permanently, 429=too many requests)
- `Content-Type: text/html` — "The body is HTML, not JSON or an image"
- `Content-Encoding: gzip` — "The body is compressed with gzip. Decompress it before showing."
- `Cache-Control: no-store` — "Do not cache this. It's your homepage with personalized content."
- `Transfer-Encoding: chunked` — "I'm sending the response in pieces (chunks) as I generate it, not all at once"

---

## 3. HTTP Versions — Why It Matters

```
HTTP/1.0 (1996):
  NEW connection per request. 
  6 images → 6 TCP handshakes. Wasteful.
```

**WHAT THIS MEANS:**
- In 1996, every single HTTP request opened a brand new TCP connection (3-way handshake), then immediately closed it. Loading a page with 6 images meant 7 TCP handshakes (1 for HTML + 6 for images). Each handshake = wasted time.

```
HTTP/1.1 (1997 — still common):
  Persistent connections (keep-alive): reuse TCP connection.
  BUT: Head-of-line blocking. Request 2 must wait for Request 1 to finish.
  Workaround: browsers open 6 parallel connections per domain.
```

**WHAT THIS MEANS:**
- HTTP/1.1 kept the TCP connection open (`keep-alive`) so you don't redo the handshake for every request.
- **Head-of-line blocking:** Imagine a single-lane road. If Car 1 (Request 1) is slow, Car 2 (Request 2) is stuck behind it even if Car 2 is going to a different destination. HTTP/1.1 is like that — one slow response blocks the next one on the same connection.
- **The workaround:** Browsers cheat by opening 6 simultaneous connections to the same domain. Now 6 requests run in parallel. But this means 6× handshake overhead and 6× more server burden.

```
HTTP/2 (2015):
  Multiplexing: many requests/responses over ONE TCP connection simultaneously.
  Header compression (HPACK): repeated headers compressed.
  Server Push: server sends resources before client asks.
  Binary protocol (vs text in HTTP/1): faster to parse.
  
  Downside: TCP-level head-of-line blocking still exists.
  (If one TCP packet lost → all streams stall while it's retransmitted)
```

**WHAT THIS MEANS:**
- **Multiplexing:** Like a multi-lane highway on ONE connection. Requests 1, 2, 3, 4, 5 all travel simultaneously on the same connection. No waiting.
- **HPACK header compression:** In HTTP/1.1, every request sends the same headers again and again (`Cookie: session=abc123`, `Accept-Encoding: gzip`, etc). HTTP/2 builds a shared dictionary — after the first request, it says "send me the same headers as last time" using just a tiny reference number.
- **Server Push:** Server can say "I know you'll need this CSS file and this JS file, let me send them before you even ask." Eliminates the round trip of the browser asking for them.
- **The remaining problem:** HTTP/2 runs over TCP. TCP itself has head-of-line blocking at the *packet* level. If one TCP packet is lost, ALL HTTP/2 streams must wait for that one packet to be retransmitted. This is the fundamental limit of TCP.

```
HTTP/3 (2022, QUIC):
  Uses UDP, not TCP. Implements reliability in application layer.
  Per-stream reliability: lost packet only blocks THAT stream, not all.
  0-RTT connection establishment.
  Better on mobile: handles IP address changes (wifi → 4G) without reconnect.
  
  Used by: YouTube, Google, Cloudflare, Meta.
```

**WHAT THIS MEANS:**
- HTTP/3 ditches TCP entirely and uses UDP instead.
- But UDP doesn't guarantee delivery — doesn't HTTP/3 need reliability? Yes. So HTTP/3 implements its own reliability ON TOP of UDP, in a smarter way.
- **Per-stream reliability:** If a UDP packet for Stream 1 is lost, only Stream 1 pauses and retransmits. Streams 2, 3, 4 keep flowing uninterrupted. This completely solves HTTP/2's remaining problem.
- **IP change (mobile):** With TCP, if you switch from WiFi to 4G, your IP address changes → your TCP connection breaks → everything must reconnect. QUIC uses a "connection ID" that's independent of your IP address. When your IP changes, the connection continues seamlessly.
- **Who uses it:** YouTube, Google Search, Gmail, Facebook. It's production-proven.

```
INTERVIEW ANSWER: "For real-time systems, I'd use HTTP/2 for multiplexing.
For mobile-heavy apps with flaky networks, HTTP/3 / QUIC is better."
```

---

## 4. HTTP vs WebSocket vs gRPC vs SSE

### 4.1 HTTP (Request-Response)

```
Client initiates. Server responds. Connection may close.
Use: REST APIs, page loads, CRUD operations.
```

**WHAT THIS MEANS:**
- Classic "question and answer" model. You ask, server answers.
- Like sending a letter. You send it, they reply.
- Stateless: the server doesn't remember you between requests (that's what cookies/sessions solve).

---

### 4.2 WebSocket (Persistent Bidirectional)

```
ONE connection, both sides can send anytime.
Overhead after handshake: just 2-byte framing per message.

Handshake:
  GET /ws HTTP/1.1
  Upgrade: websocket
  Connection: Upgrade
  Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
  
  Server: 101 Switching Protocols (connection upgraded)

Use: Chat, live notifications, online gaming, collaborative editing (Google Docs),
     trading platforms (real-time price feed).
```

**WHAT THIS MEANS:**
- WebSocket is like a phone call vs HTTP's letter.
- A phone call is connected and either party can speak anytime. Once the call is connected, talking is very cheap (just audio, no "hello my name is..." again).
- The **handshake** starts as a regular HTTP request but includes `Upgrade: websocket`. The server responds `101 Switching Protocols` meaning "OK, we're switching from HTTP mode to WebSocket mode on this connection."
- After that, both sides can send messages at any time with just **2 bytes of overhead** per message (vs HTTP headers that are 200-800 bytes every time).
- **2-byte overhead example:** Sending "hello" (5 bytes) via HTTP: 5 bytes + 400 bytes of headers = 405 bytes. Via WebSocket: 5 bytes + 2 bytes framing = 7 bytes. **57× more efficient per message.**

```
Challenges:
  - Load balancing stateful connections (sticky sessions or shared state in Redis)
  - What if server restarts? Client must reconnect.
  - Firewall/proxy issues (some proxies don't support WebSocket)
```

**WHAT EACH CHALLENGE MEANS:**
- **Load balancing:** WebSocket maintains a long-lived connection to ONE server. If you have 10 servers, how does Server 2 know about a message sent to a connection on Server 1? Solution: all servers share state in Redis ("which user is connected to which server"). Or use "sticky sessions" (load balancer always sends the same user to the same server).
- **Server restart:** If Server 1 crashes, the WebSocket connection dies. The client must reconnect (usually done automatically with exponential backoff). The client needs reconnection logic.
- **Firewall issues:** Old corporate firewalls block anything that's not standard HTTP. They don't understand WebSocket's `101 Switching Protocols`. Solution: use port 443 (HTTPS) which most firewalls allow. Or fall back to HTTP long-polling.

---

### 4.3 SSE — Server-Sent Events

```
Server pushes to client over plain HTTP. Client cannot send back.
Simpler than WebSocket. Auto-reconnects on disconnect.

Server sends:
  Content-Type: text/event-stream
  
  data: {"price": 150.23}\n\n
  data: {"price": 150.50}\n\n

Use: Dashboards, notification feeds, progress updates.
Use when: server needs to push, client rarely needs to send back.
```

**WHAT THIS MEANS:**
- Like a newspaper delivery. The newspaper company (server) pushes new editions to your door (client). You don't push anything back to them.
- The server opens a regular HTTP connection but keeps it open forever, dripping data down it continuously.
- `\n\n` (double newline) separates individual events.
- **Why simpler than WebSocket?** No special protocol needed. Standard HTTP. Works through all firewalls. Automatically reconnects if the connection drops (browsers handle this natively).
- **When NOT to use:** If you need the client to also push data (like a chat app), SSE doesn't work. Use WebSocket instead.

---

### 4.4 gRPC

```
Uses Protocol Buffers (binary, strongly typed) over HTTP/2.
Faster serialization than JSON (2-10×). Smaller payload.
Streaming modes: unary, server streaming, client streaming, bidirectional.

Use: Internal microservice communication (service A calling service B).
Not for browsers (no native browser gRPC support without grpc-web).
```

**WHAT THIS MEANS:**
- gRPC is designed for microservices talking to each other — NOT for browsers talking to servers.
- **Protocol Buffers (Protobuf):** Instead of JSON (`{"name": "Alice", "age": 30}` = 25 bytes as text), Protobuf encodes this as binary. Approximately `\x01\x05Alice\x02\x1E` = 9 bytes. Smaller + faster to encode/decode.
- **Strongly typed:** You define your API in a `.proto` file. The code generator creates stubs (boilerplate code) in any language. No accidental typos in field names. Type errors caught at compile time, not runtime.
- **Streaming modes:**
  - Unary: one request, one response (like HTTP)
  - Server streaming: one request, server sends many responses (like SSE)
  - Client streaming: client sends many messages, server sends one response
  - Bidirectional: both sides stream simultaneously (like WebSocket)

---

### 4.5 Decision Matrix

```
DECISION MATRIX:
┌─────────────────────┬────────────┬───────────┬──────┬───────────┐
│ Requirement         │ HTTP REST  │ WebSocket │ SSE  │ gRPC      │
├─────────────────────┼────────────┼───────────┼──────┼───────────┤
│ Request-response    │ ✓ Best     │ OK        │ ✗    │ ✓         │
│ Server push         │ Polling    │ ✓ Best    │ ✓    │ ✓         │
│ Client push         │ ✓          │ ✓         │ ✗    │ ✓         │
│ Bidirectional       │ ✗          │ ✓ Best    │ ✗    │ ✓         │
│ Browser compatible  │ ✓          │ ✓         │ ✓    │ ✗         │
│ Microservices       │ OK         │ ✗         │ ✗    │ ✓ Best    │
│ Low overhead/fast   │ Medium     │ High      │ High │ ✓ Best    │
└─────────────────────┴────────────┴───────────┴──────┴───────────┘
```

**HOW TO READ THIS IN AN INTERVIEW:**
- If interviewer says **"real-time chat"** → WebSocket (bidirectional, both sides push)
- If interviewer says **"live stock price dashboard"** → SSE (server pushes, client only reads)
- If interviewer says **"microservice A calls microservice B"** → gRPC (fast, typed, internal)
- If interviewer says **"mobile app fetching user profile"** → HTTP REST (simple request-response)

---

## 5. CDN — Content Delivery Network

```
WHAT:
  Global network of edge servers that cache content close to users.
  Providers: Cloudflare, Akamai, AWS CloudFront, Fastly, Netflix Open Connect.
```

**WHAT THIS MEANS:**
- CDN = a network of warehouses placed near customers instead of having one central factory.
- Without CDN: every user worldwide connects to Amazon's servers in Virginia, USA → slow for users in India, Japan, Brazil.
- With CDN: Amazon stores copies of images and videos in 300 cities worldwide. A user in Mumbai gets content from a server 10km away.

```
HOW IT WORKS:
  Origin Server (e.g., S3 in us-east-1)  ← The actual source of truth
       │
       │ CDN pulls content on first request (or origin pushes proactively)
       │
  ┌────▼────────────────────────────────────────┐
  │ CDN Edge PoP (Point of Presence)             │
  │  Mumbai, London, São Paulo, Tokyo, ...       │
  │  Each PoP: SSDs + fast NICs + BGP routing    │
  └─────────────────────────────────────────────┘
       │
  User in Mumbai requests image:
    1st request: Mumbai PoP → miss → fetch from US origin → cache in Mumbai
    2nd request: Mumbai PoP → HIT → serve from local SSD (5ms vs 200ms)
```

**WHAT EACH PART MEANS:**
- **Origin Server:** The master copy. Amazon's actual server in Virginia where the real image lives.
- **PoP (Point of Presence):** A CDN data center in a city. Contains SSDs (fast storage) and powerful network equipment.
- **Cache Miss (1st request):** Mumbai CDN doesn't have the image yet. It fetches it from Virginia, stores a copy, then serves it to the user. Slow this time, but the copy is now saved locally.
- **Cache Hit (2nd request onward):** Mumbai CDN has the cached copy. Serves it directly. 5ms instead of 200ms — 40× faster!
- **BGP routing:** The internet's routing protocol. CDN PoPs use BGP to announce "I have this content, route users to me."

---

### 5.1 Cache-Control Headers

```
Cache-Control: public, max-age=86400        → CDN caches for 24 hours
Cache-Control: no-store                     → CDN must not cache (private data)
Cache-Control: s-maxage=3600, max-age=300   → CDN caches 1h, browser 5min
Vary: Accept-Encoding                       → Different cache per encoding
ETag: "abc123"                              → CDN validates with origin if content changed
```

**WHAT EACH HEADER MEANS:**
- `Cache-Control: public, max-age=86400` → "This content is the same for everyone. Cache it. Valid for 86400 seconds (24 hours)."
- `Cache-Control: no-store` → "Never cache this. It's sensitive (e.g., bank statement, personal data)." CDN immediately discards it.
- `s-maxage=3600, max-age=300` → `s-maxage` is for shared caches (CDN). `max-age` is for the browser. So CDN holds for 1 hour; browser holds for 5 min. Why different? CDN can be invalidated via API; browsers can't. So keep browser cache short.
- `Vary: Accept-Encoding` → CDN stores SEPARATE copies based on encoding. One copy compressed with gzip, another with brotli. Each user gets the right version for what their browser supports.
- `ETag: "abc123"` → A fingerprint of the content. Browser sends `If-None-Match: "abc123"` → if content hasn't changed, server says `304 Not Modified` (no body = faster). If changed, sends new content with new ETag.

---

### 5.2 What to Put on CDN

```
✓ Static assets: images, videos, CSS, JS, fonts, HTML (if cacheable)
✓ Software downloads (GitHub releases, APKs)
✓ API responses that are same for all users (public exchange rates, weather)
✗ Personalized data (user profile, cart, recommendations)
✗ Real-time data (stock prices, live scores — need SSE/WebSocket)
✗ Private data (medical records, financial data)
```

**WHY EACH RULE EXISTS:**
- ✓ **Static assets:** An image `logo.png` is identical for every user. Cache it. Everyone benefits.
- ✓ **Software downloads:** Same APK file for all users. Cache aggressively (1 year).
- ✓ **Public API responses:** `/api/exchange-rates` returns the same JSON for everyone. Cache it. Saves server load.
- ✗ **Personalized data:** `/api/my-cart` is different for each user. CDN caches by URL — if User A's cart gets cached, User B would see User A's cart. **This is a serious privacy bug.** Never cache personalized endpoints.
- ✗ **Real-time data:** CDN cache means stale data. Stock prices change every millisecond — CDN would serve 5-minute-old prices as if current.
- ✗ **Private data:** Medical records on CDN = data leak. Always served directly from origin with no-store header.

---

### 5.3 CDN Cache Invalidation

```
Problem: You deploy new JS file but CDN serves old cached version.

Solution 1: Content-addressed URLs
  bundle.abc123.js  → bundle.xyz789.js (filename includes content hash)
  Old URL: never changes → stays cached (safe).
  New URL: cache miss → fetches from origin. Browser gets new JS.
  Max-age can be 1 year. No invalidation ever needed.

Solution 2: CDN Purge API
  POST /zones/{zone_id}/purge_cache
  { "files": ["https://cdn.example.com/image.png"] }
  → CDN removes that URL from all edge caches immediately.
  Cost: Cloudflare purge API rate limit = 1000 files/minute.
```

**WHAT THIS MEANS:**
- **The problem:** You set `max-age=31536000` (1 year) on your `bundle.js`. CDN caches it. 2 weeks later you push a bug fix. CDN still serves the year-old broken version to everyone!
- **Solution 1 (Best):** Include a hash of the file content in the filename. `bundle.abc123.js` where `abc123` = a fingerprint of the file's contents. If you change one byte of JS, the hash changes → new filename → new URL → CDN has never seen this URL → fetches from origin. The old URL with the old file still exists in cache, but nobody uses it (no links to it). **This is what Webpack/Vite do automatically.**
- **Solution 2 (Emergency):** Call Cloudflare's API and say "delete this specific URL from all your caches now." Takes effect in seconds. But rate-limited — you can't purge millions of files this way.

---

### 5.4 Real Numbers

```
Without CDN (user in India, server in US):
  Latency: 200-300ms (physics of light + routing)

With Cloudflare CDN (edge in Mumbai):
  Latency: 5-15ms (data center 10km away)
  Speedup: 20-60× for cached content

Netflix Open Connect (co-located at ISP):
  Latency: 1-5ms (literally inside ISP's building)
  99% of Netflix traffic served from OC appliances — never hits AWS.
```

**WHAT THIS MEANS:**
- **200-300ms:** Light travels at ~200,000 km/s through fiber (slower than vacuum due to refraction). India to US is ~13,000 km. Round trip = 130ms just for light + routing overhead = 200-300ms total.
- **5-15ms:** Mumbai CDN data center is maybe 10km away. Light takes ~0.05ms. Add network hops = 5-15ms.
- **Netflix Open Connect:** Netflix went even further. They placed their own servers *inside* ISP (Jio, Airtel) data centers. Your Netflix stream literally never leaves your ISP's network. This is why Netflix rarely buffers even in India.

---

## 6. DNS Load Balancing and Failover

```
DNS can itself be a load balancer:

Round-Robin DNS:
  amazon.com → [1.2.3.4, 5.6.7.8, 9.10.11.12]
  Each DNS query returns one IP (rotated).
  Problem: Client caches IP for TTL. If that server dies, client is stuck until TTL expires.
```

**WHAT THIS MEANS:**
- DNS can return different IPs to different users in round-robin. User 1 gets IP1, User 2 gets IP2, User 3 gets IP3 → traffic spread across 3 servers.
- **Problem:** Once a client gets IP1, it caches it. If Server 1 dies, that client keeps trying the dead IP for up to TTL seconds. No automatic failover at the client level.

```
Geo DNS:
  User in India → India server IP
  User in US → US server IP
  Used by: Netflix, Google, Cloudflare.
  Implementation: Route 53 Geolocation Routing, Cloudflare Load Balancing.
```

**WHAT THIS MEANS:**
- DNS server checks the user's IP address, figures out which country they're in (GeoIP lookup), and returns the IP of the closest server.
- **How to implement:** AWS Route 53 lets you set rules: "If request comes from India, return `ap-south-1` IP. If from US East, return `us-east-1` IP."

```
Health-Check-Based DNS:
  Route 53 / Cloudflare monitor /health endpoints.
  If primary DC fails health check → update DNS to backup DC.
  Failover time: TTL of the DNS record (usually 60 seconds for production).
```

**WHAT THIS MEANS:**
- Route 53 pings `https://yourserver.com/health` every 10 seconds.
- If `/health` returns an error → Route 53 automatically updates DNS to point to the backup server.
- Failover time = TTL (60 seconds typically). That's 60 seconds of users hitting the dead server.

```
ANYCAST:
  Multiple servers worldwide share the SAME IP address.
  BGP routing automatically sends traffic to the geographically nearest server.
  Used by: Cloudflare (all 300 PoPs share IPs), Google DNS (8.8.8.8).
  Advantage: user is always routed to nearest server automatically, no DNS lookup needed.
```

**WHAT THIS MEANS:**
- This sounds impossible — how can multiple servers have the same IP?
- **BGP (Border Gateway Protocol):** The internet's routing system. Every router in the world decides packet routes using BGP. Cloudflare tells every major router: "If you see a packet for IP 1.1.1.1, send it to whichever of my 300 servers is nearest to you."
- Result: The same IP address `1.1.1.1` resolves to a server in Mumbai for Indian users and a server in London for UK users — automatically, at the routing layer, without DNS lookups.
- **Google's 8.8.8.8** works this way. Every user who uses Google DNS hits the geographically nearest Google DNS server automatically.

---

## 7. Connection Pooling

```
PROBLEM:
  Every TCP + TLS handshake costs 1-3 RTTs + CPU for crypto.
  If your app server opens a new DB connection per request:
  10,000 req/sec → 10,000 new connections/sec → DB exhausted.
```

**WHAT THIS MEANS:**
- Every time your app talks to PostgreSQL, it needs to:
  1. TCP handshake (1 RTT)
  2. Authenticate (send username/password, verify) (1 RTT)
  3. THEN send your SQL query
- For high-traffic apps doing 10,000 requests/second, opening 10,000 new DB connections per second is catastrophically expensive. PostgreSQL crashes (it has a hard limit on connections, typically 100-300).

```
SOLUTION: Connection Pool
  Maintain a pool of pre-established connections.
  App server borrows a connection → uses it → returns to pool.

# Python SQLAlchemy connection pool:
engine = create_engine(
    "postgresql://user:pass@db:5432/mydb",
    pool_size=20,          # keep 20 connections open always
    max_overflow=30,       # allow up to 30 extra temporary connections
    pool_timeout=30,       # wait up to 30s for available connection
    pool_recycle=3600,     # recycle connections older than 1h
)
```

**WHAT EACH PARAMETER MEANS:**
- `pool_size=20` → Always keep 20 TCP connections to PostgreSQL open, even when idle. Like keeping 20 phone lines open.
- `max_overflow=30` → During a spike, allow up to 30 MORE connections (total 50). These extra ones are closed when demand drops.
- `pool_timeout=30` → If all 50 connections are busy and a new request comes in, wait up to 30 seconds for one to free up. If still waiting after 30s → throw an error.
- `pool_recycle=3600` → A connection open for 1 hour may have silently died (network timeout, DB restart). Proactively close and re-open it every hour to avoid stale connection errors.

```
PGBOUNCER (PostgreSQL connection pooler):
  Sits between app servers and PostgreSQL.
  PostgreSQL: handles ~100 connections max efficiently.
  1000 app server threads all connect to PgBouncer.
  PgBouncer: multiplexes onto 20-30 real DB connections.
  
  Modes:
    session:     connection held for entire client session
    transaction: connection returned after each TRANSACTION (most common)
    statement:   connection returned after each STATEMENT (most aggressive)
```

**WHAT THIS MEANS:**
- Think of PgBouncer as a receptionist. 1000 app threads think they each have their own DB connection (they talk to PgBouncer). PgBouncer actually has only 20 real connections to PostgreSQL and smartly routes queries.
- **Session mode:** App gets a connection, uses it for everything, connection freed only when app disconnects. Safest but least efficient.
- **Transaction mode (most common):** App gets a connection, uses it for ONE transaction (BEGIN...COMMIT), connection freed immediately. If app runs 10 transactions, it might use 10 different pooled connections. Very efficient.
- **Statement mode:** Connection freed after EVERY single SQL statement. Extremely efficient. BUT: if you use temporary tables or transactions that span multiple statements, this breaks things.

```
REAL EXAMPLE:
  Without pooling: 500 app server threads → 500 PostgreSQL connections → OOM crash.
  With PgBouncer (transaction mode): 500 threads → 20 DB connections → stable.
```

**WHAT THIS MEANS:**
- 500 direct connections = PostgreSQL crashes (out of memory, too many connections).
- 20 connections through PgBouncer = PostgreSQL is happy. 500 app threads are all served because no single thread holds a connection while it's thinking/waiting. The connection is only held during the actual SQL execution (milliseconds), then returned.

---

## 8. TCP vs UDP — When to Use Which

```
TCP (Transmission Control Protocol):
  Reliable delivery: retransmits lost packets.
  Ordered delivery: packets arrive in order.
  Flow control: doesn't overwhelm receiver.
  Congestion control: slows down on network congestion.
  Use: HTTP, HTTPS, databases, file transfers, email.
```

**WHAT EACH PROPERTY MEANS:**
- **Reliable delivery:** If a packet is lost (network hiccup, router dropped it), TCP automatically detects the loss (via missing acknowledgment) and resends it. You never lose data.
- **Ordered delivery:** Packets might arrive in wrong order (took different routes). TCP numbers them and reorders before handing to your app. Your app always sees data in the right sequence.
- **Flow control:** If the receiver's buffer is full (it can't process data fast enough), TCP tells the sender to slow down. Prevents overwhelming slow receivers.
- **Congestion control:** If the network between sender and receiver is congested (packets getting dropped by routers), TCP slows its sending rate. Like slowing down on a busy highway.

```
UDP (User Datagram Protocol):
  No connection, no reliability guarantees.
  Fire-and-forget. No retransmit. May arrive out-of-order.
  Use: DNS queries, video streaming, VoIP, online gaming, QUIC.
```

**WHAT THIS MEANS:**
- UDP is like sending a postcard. You write it, drop it in the mailbox, and forget about it. Maybe it arrives, maybe it doesn't. No receipt, no guarantee.
- **Why use something unreliable?** Because reliability is *expensive* — it takes extra round trips to confirm delivery. If you don't NEED reliability, dropping it makes you much faster.

```
WHY UDP FOR STREAMING:
  Video streaming: if one frame arrives late, don't wait — just skip it.
  Retransmitting a late frame would cause more delay than skipping.
  UDP + application-level error correction (FEC) = resilient streaming.
```

**WHAT THIS MEANS:**
- A video plays at 30 frames per second. Frame 15 arrives late or is lost. If you wait for retransmission, you've paused for maybe 200ms to get one frame → video stutters badly.
- Better to just skip frame 15 and show frame 16. The viewer might see a tiny glitch but the video keeps playing smoothly.
- **FEC (Forward Error Correction):** Send extra redundant data. "Every 10 video packets, I'll also send 2 parity packets that can reconstruct any 1 of the 10 if lost." Like RAID for network packets. Protects against occasional loss without needing retransmission.

```
WHY UDP FOR DNS:
  DNS query/response fits in one packet (< 512 bytes originally).
  No need for connection setup overhead.
  If no response in 100ms: client retries. Simple and fast.
```

**WHAT THIS MEANS:**
- A DNS query is tiny — "what's the IP for amazon.com?" fits in one UDP packet.
- The reply also fits in one packet.
- No need for the 3-way handshake overhead of TCP.
- If the DNS server doesn't reply within 100ms, the client just retries (sends the query again). Simple retry logic is fine for DNS.

```
QUIC (HTTP/3):
  UDP underneath, but adds:
    - Reliable, ordered delivery per stream
    - Encryption built-in (TLS 1.3 integrated)
    - 0-RTT connection setup
    - Connection migration (change IP without disconnect)
  Best of both worlds: reliability + no head-of-line blocking.
```

**WHAT THIS MEANS:**
- QUIC is "smart UDP." It builds all the reliability of TCP back on top of UDP, but in a smarter way that avoids TCP's head-of-line blocking problem.
- **Why not just fix TCP?** TCP is implemented in operating system kernels. Updating all kernels worldwide takes decades. QUIC runs in userspace (in the application), so it can be updated by deploying new software — much faster.
- **Encryption built-in:** TCP relies on TLS added on top. QUIC integrates TLS 1.3 directly — you can't use QUIC without encryption. Security by default.

---

## 9. Network Protocols Reference

```
PROTOCOL  | PORT | USE CASE                        | WHY THIS PORT?
──────────┼──────┼─────────────────────────────────┼──────────────────────
HTTP      │ 80   │ Web, APIs (unencrypted)          │ Historical standard
HTTPS     │ 443  │ Web, APIs (TLS encrypted)        │ Historical standard
WebSocket │ 80/443│ Real-time bidirectional          │ Reuses HTTP ports
gRPC      │ 443  │ Microservices (HTTP/2+Protobuf)  │ Runs over HTTPS
SSH       │ 22   │ Remote server access             │ Historical standard
FTP       │ 21   │ File transfer (legacy)           │ Avoid — use SFTP/S3
SMTP      │ 25   │ Email sending (server→server)    │ Historical standard
IMAP      │ 993  │ Email receiving (TLS)            │ 993 = IMAP over SSL
DNS       │ 53   │ Name resolution (UDP + TCP)      │ UDP for queries, TCP for zone transfers
Redis     │ 6379 │ Cache (TCP, binary protocol)     │ Default, configurable
PostgreSQL│ 5432 │ Database (TCP)                   │ Default, configurable
Kafka     │ 9092 │ Message broker (TCP)             │ Default, configurable
```

**WHAT THIS MEANS:**
- Ports are like apartment numbers in a building. An IP address is the building (server). The port says which specific service inside to talk to.
- Port 80 = walk in the main door (HTTP). Port 443 = walk in the secure door (HTTPS). Port 22 = maintenance entrance (SSH).
- Firewalls control which ports are open. Most corporate firewalls only allow ports 80 and 443 → this is why WebSocket uses port 443, and gRPC runs over HTTPS port 443.

---

## 10. Common Interview Questions — With Deep Answers

```
Q1: "What's the difference between TCP and UDP? When would you use UDP?"
```

**DEEP ANSWER:**
- TCP: connection-based (3-way handshake), reliable (retransmits lost packets), ordered (packets arrive in sequence), has flow and congestion control. Overhead: more bytes per packet, more round trips.
- UDP: connectionless, unreliable, unordered, no flow control. Overhead: minimal.
- Use UDP when: latency matters more than reliability. Examples:
  - **DNS:** Query + response are tiny. Retry if no answer. No need for connection overhead.
  - **Video streaming:** Better to skip a frame than buffer. App-level FEC handles occasional loss.
  - **VoIP (phone calls):** Better to hear a glitch than have a 500ms pause waiting for retransmit.
  - **Online gaming:** Game state is sent 60 times/second. An old packet that arrives late is useless — the game has moved on. Discard old packets, use latest state.
  - **QUIC:** UDP underneath with application-level reliability, solving TCP's head-of-line blocking.

```
Q2: "How does HTTPS work?"
```

**DEEP ANSWER:**
1. Browser connects via TCP (3-way handshake).
2. TLS handshake begins. Browser sends supported cipher suites (encryption algorithms) and its TLS version.
3. Server picks a cipher, sends its **certificate** (digital document proving "I am really amazon.com, signed by a Certificate Authority like DigiCert").
4. Browser verifies the certificate against trusted CA list (built into browser/OS).
5. **Key exchange:** Client and server run Diffie-Hellman math to independently arrive at the same secret key without ever sending it over the network. (Even if someone recorded all traffic, they can't compute the key.)
6. All subsequent communication encrypted with symmetric key (AES typically). Fast.

```
Q3: "A user in India is experiencing slow load times. How do you fix it?"
```

**DEEP ANSWER:**
- Step 1: **Profile** — is it DNS (100ms+)? TCP handshake (200ms RTT)? TLS (2 RTTs)? Slow content (10MB images)? Use Chrome DevTools Network tab to see timing breakdown.
- Step 2: **CDN for static assets** (images, CSS, JS) → 5-15ms instead of 200ms for Mumbai users.
- Step 3: **Geographic API servers** → Deploy in `ap-south-1` (Mumbai). Use Route 53 geolocation routing so Indian users hit the Mumbai API server.
- Step 4: **HTTP/2 or HTTP/3** → Multiplexing reduces round trips. gRPC between microservices.
- Step 5: **Compress** → Enable gzip/brotli compression on text assets. 70-80% smaller payloads.
- Step 6: **Connection pooling** at app layer → don't open new DB connection per request.

```
Q4: "What is HTTP/2 and why is it better than HTTP/1.1?"
```

**DEEP ANSWER:**
HTTP/1.1 problems: head-of-line blocking (slow request blocks fast one), no header compression (same headers sent repeatedly), no server push, text protocol (slower to parse).

HTTP/2 solutions:
- **Multiplexing:** Multiple requests in parallel over ONE connection. No blocking.
- **HPACK header compression:** First request sends full headers. Subsequent requests say "same as request 1 except field X." Saves 60-80% header bytes.
- **Server push:** Server sends `style.css` and `app.js` proactively when it sends `index.html`. Saves 1 round trip.
- **Binary framing:** Packets are binary structs, not text. No parsing of "GET / HTTP/1.1\r\nHost:..." strings. 2-3× faster to parse.
- Remaining issue: TCP head-of-line blocking (solved by HTTP/3/QUIC).

```
Q5: "How would you design a real-time notification system?"
```

**DEEP ANSWER:**
Architecture choices:
1. **WebSocket** for each client connecting to a notification server. Long-lived persistent connection. O(2 bytes) per notification.
2. **Load balancing challenge:** User A connected to Server 1. Notification targeted at User A triggered on Server 2. Server 2 must tell Server 1 to push to User A. Solution: **Redis Pub/Sub**. Server 2 publishes to Redis channel `user:A:notifications`. Server 1 (subscribed to that channel) receives it and pushes to the WebSocket.
3. **Scale:** 1M concurrent WebSocket connections → 5 servers × 200K connections each. Each WebSocket is ~2KB RAM → 200K × 2KB = 400MB per server. Feasible.
4. **Reconnection:** Client disconnects (phone sleeps) → reconnects → fetch missed notifications from Kafka/DB.
5. **Fanout:** Celebrity has 10M followers. New post notification → 10M WebSocket pushes. Use Kafka fanout: notification service produces to Kafka, 100 consumer workers each push to 100K connections.

---

## 11. Common Mistakes — Deeply Explained

```
MISTAKE 1: Ignoring DNS TTL in failover design
  Plan: "If server fails, update DNS to point to backup."
  Problem: Old IP cached by clients for up to TTL seconds.
  Fix: Use short TTL (60s) for production DNS records.
```

**WHY THIS BITES YOU:**
- You set TTL=3600 (1 hour) to reduce DNS lookup load.
- Server crashes at 2:00 PM.
- You update DNS to backup server at 2:01 PM.
- But 100,000 users have the old IP cached until 3:00 PM.
- For an entire hour, those users hit the dead server → errors.
- Fix: TTL=60 for production. Cost: slightly more DNS lookup traffic. Worth it.

```
MISTAKE 2: Using HTTP polling instead of WebSocket for real-time
  Polling: client asks "any updates?" every 5 seconds.
  99% of responses: "no". Wasted bandwidth and server load.
  Fix: WebSocket or SSE for push-based delivery.
```

**NUMBERS:**
- 1M users polling every 5 seconds = 200,000 HTTP requests/second.
- 99% empty responses = 198,000 wasted requests/second.
- Each request: ~500 bytes headers = 99 MB/sec wasted bandwidth.
- Same 1M users with WebSocket: 0 requests until something actually happens. Then 1M pushes. Infinitely more efficient.

```
MISTAKE 3: Putting user data on CDN
  CDN caches by URL. All users hitting the same URL get same cached response.
  Fix: CDN for public/static only. User-specific data: never cache or use Vary header.
```

**THE BUG THIS CAUSES:**
- User A visits `/api/user/profile`. CDN caches the response (Alice's profile data).
- User B visits `/api/user/profile`. CDN serves the CACHED response — Alice's data!
- User B sees Alice's name, email, address. GDPR violation. Security incident.
- Fix: `Cache-Control: no-store` on any user-specific API response. Always.

```
MISTAKE 4: Not accounting for TLS overhead in latency estimates
  "Database is 5ms away, so response is 5ms"
  Reality: TCP handshake (1 RTT) + TLS handshake (1-2 RTTs) + request = 3 RTTs.
  Fix: Keep connections alive (HTTP keep-alive, connection pooling).
```

**THE MATH:**
- Round trip to database = 5ms.
- TCP handshake = 1 RTT = 5ms.
- TLS 1.2 handshake = 2 RTTs = 10ms.
- First query = 1 RTT = 5ms.
- Total for FIRST request = 20ms, not 5ms.
- **With connection pooling/keep-alive:** TLS done once. Every subsequent request = 5ms. This is why connection pools matter so much.

```
MISTAKE 5: Forgetting connection limits
  PostgreSQL default: 100 max connections.
  100 app servers × 10 threads each = 1000 concurrent connections → crash.
  Fix: PgBouncer / connection pooling at every DB-facing service.
```

**WHY POSTGRES HAS A LIMIT:**
- Each PostgreSQL connection is a forked OS process (legacy architecture). Each process uses ~5-10 MB RAM.
- 1000 connections = 5-10 GB RAM just for connection overhead. Database crashes.
- Modern databases (PgBouncer, ProxySQL for MySQL) multiplex thousands of app connections onto dozens of real DB connections. Essential for any production system.

---

## HOW NETWORKING CONCEPTS APPEAR IN THE CASE STUDIES

### TCP vs UDP in Real Systems

```
CS04 Uber (Driver location updates):
  Driver GPS → server: UDP preferred.
  Why: losing one GPS packet is acceptable (next update arrives in 2-5s).
  UDP: no ACK, no retransmit → lower latency → better for real-time location.
  
  Ride booking request: TCP (HTTP/2).
  Why: MUST reliably reach server. Cannot lose a booking request.

CS06 YouTube (Video streaming):
  Control plane (play, pause, seek): TCP (HTTP).
  Data plane (video segments): DASH over HTTP/TCP.
  Why TCP for streaming? Reliable. Retransmission of lost segments = stutter.
  Modern: QUIC (UDP-based but reliable via QUIC's own congestion control).
  QUIC: used by YouTube/Netflix to reduce head-of-line blocking vs TCP.

CS03 WhatsApp (Real-time messaging):
  WebSocket: persistent TCP connection.
  Why: bi-directional. Server can PUSH messages to client without client polling.
  HTTP: client must poll (GET /new-messages every 5s) → battery drain, latency.
  WebSocket: server pushes → instant delivery.
```

### HTTP/HTTPS in Case Studies

```
CS09 Payment Gateway:
  ALL payment communication: HTTPS (TLS 1.3).
  TLS: encrypts card numbers, CVV, bank tokens in transit.
  Without HTTPS: man-in-the-middle captures card data.
  Certificate pinning on mobile apps: prevent fake certificates.

CS01 URL Shortener:
  Redirect: HTTP 301 (permanent) vs 302 (temporary).
  302: browser doesn't cache. Every visit goes to shortener. Click analytics work.
  301: browser caches. Subsequent visits skip shortener. Analytics miss repeat visits.
  Design choice: use 302 for analytics, 301 for performance (no analytics needed).
  
  HTTPS: short link → redirect → HTTPS destination. Mixed content issues if destination is HTTP.

CS11 AI Systems:
  LLM API calls: HTTPS REST.
  Streaming responses: Server-Sent Events (SSE) over HTTPS.
  SSE: server keeps connection open, streams tokens as they're generated.
  User sees "typewriter effect" — each token appears as generated.
```

### DNS in Case Studies

```
CS04 Uber:
  rider.uber.com → Uber's load balancer IP.
  DNS TTL set low (60s): allows rapid failover if a data center goes down.
  GeoDNS: riders in India get IP of India data center. Reduces latency.

CS01 URL Shortener:
  short.ly A record → load balancer IP.
  CNAME for custom domains: company.short.ly → short.ly → load balancer.
  CDN: short.ly CNAME → Cloudflare → origin server.
```

### Load Balancing at Network Layer

```
CS04 Uber:
  L4 (TCP): first layer. Route by IP. Stateless. Ultra-fast.
  L7 (HTTP): second layer. Route by URL path.
    /api/rides/* → ride service.
    /api/drivers/* → driver service.
    /api/payments/* → payment service.

CS06 YouTube:
  Anycast: CDN edge servers. User's DNS resolves to nearest CDN edge IP.
  CDN edge handles: video segment requests (static content).
  Origin handles: upload, API calls, non-cached content.
```

# CS03: Design WhatsApp (Messaging System)
## Full HLD Case Study | MAANG Interview Ready

---

## STEP 1 — Requirements

```
FUNCTIONAL:
  1. One-to-one messaging (text, images, voice notes, video)
  2. Group messaging (up to 512 members)
  3. Delivery receipts: sent ✓, delivered ✓✓, read ✓✓ (blue ticks)
  4. Online/Last seen status
  5. Push notifications for offline users
  6. End-to-end encryption (E2EE) — server cannot read content
  7. Message delivery when recipient is offline (store up to 30 days)

NON-FUNCTIONAL:
  - 2 billion users, 1 billion DAU
  - 100 billion messages/day (~1.16M messages/second)
  - Message delivery latency: < 1 second for online recipient
  - 99.99% availability (messaging is critical communication)
  - E2EE: server stores only ciphertext (cannot read)
  - Message ordering: within a conversation, messages always in sent order
  - Storage: messages stored until delivered, or 30 days for offline users
```

---

## STEP 2 — Scale Estimation

```
MESSAGES:
  100B messages/day ÷ 86,400 = 1,157,407 msg/sec avg
  Peak (assume 3× avg): ~3.5M msg/sec

CONCURRENT CONNECTIONS:
  1B DAU. Not all active simultaneously.
  Peak concurrent WebSocket connections: ~500M
  
  Each WebSocket connection: ~50KB server memory
  500M × 50KB = 25 TB RAM for connections alone!
  → Must shard connection servers across thousands of machines.
  → With 64 GB RAM per server: 64GB / 50KB = ~1.28M connections/server
  → 500M / 1.28M = ~390 connection servers (call it 500 with headroom)

MESSAGE STORAGE:
  100B messages/day. But most messages delivered quickly and deleted from server.
  Persistent: only undelivered messages (offline users).
  Assume 10% messages to offline users = 10B messages awaiting delivery.
  Avg message size: ~100 bytes (text).
  Pending storage: 10B × 100B = 1 TB (manageable, temporary)
  
  Long-term (for compliance/backup): Compressed archive.

MEDIA:
  20% of messages include media.
  20B media messages/day × avg 200KB = 4 PB/day (media needs CDN + object store).
  Media stored in S3, URL in message. Not in message queue.

GROUPS:
  Assume avg group = 50 members.
  Group message = 1 send → 50 deliveries.
  If 10% messages are group: 10B × 50 = 500B delivery events/day.
  → Group messaging amplifies writes by 50×.
```

---

## STEP 3 — High-Level Architecture

```
CONNECTION TIER (WebSocket servers):
  Each user maintains ONE persistent WebSocket connection to a Connection Server.
  Connection Servers are stateful (hold open TCP connections).
  Multiple Connection Servers: each holds subset of users.
  
FLOW: Alice → Bob (online)
  ┌──────┐   WebSocket    ┌─────────────────┐   Internal route   ┌─────────────────┐
  │Alice │ ─────────────► │ Connection Srv A│ ─────────────────► │ Connection Srv B│ ─── WebSocket ──► Bob
  └──────┘                └─────────────────┘                     └─────────────────┘
                                   │
                          [Message Service]
                                   │
                           [Cassandra DB]
                         (store for durability)
                                   │
                          [Delivery Service]
                         (Is Bob online? Which server?)
                                   │
                          [Presence Service (Redis)]
                          "bob_id" → "connection_server_B:port"

FLOW: Alice → Charlie (offline)
  Alice → Connection Srv A → Message Service → Cassandra (store pending)
  Charlie comes online → Connection Srv → "you have pending" → fetch → deliver → ACK → delete

FULL ARCHITECTURE:
  ┌───────────────────────────────────────────────────────────┐
  │  Load Balancer (sticky sessions — must route to same CS)  │
  └──────────┬─────────────────────────────────────┬──────────┘
             │                                     │
  ┌──────────▼──────────┐             ┌────────────▼────────────┐
  │  Connection Server A│             │  Connection Server B     │
  │  (WebSocket farm)   │             │  (WebSocket farm)        │
  │  Alice's connection │             │  Bob's connection        │
  └──────────┬──────────┘             └────────────┬────────────┘
             │                                     │
  ┌──────────▼─────────────────────────────────────▼──────────┐
  │              Message Router / Delivery Service              │
  └──────────┬─────────────────────────────────────┬──────────┘
             │                                     │
  ┌──────────▼──────────┐             ┌────────────▼────────────┐
  │  Presence Service   │             │  Message Store           │
  │  (Redis Cluster)    │             │  (Cassandra Cluster)     │
  │  user_id → srv_id   │             │  pending messages        │
  └─────────────────────┘             └─────────────────────────┘
```

---

## STEP 4 — Deep-Dive: Message Protocol and States

```
MESSAGE OBJECT:
  {
    "message_id": "msg_550e8400-e29b-41d4-a716",   // UUID (unique globally)
    "conversation_id": "conv_alice_bob",             // for retrieval
    "sender_id": "alice_id",
    "recipient_id": "bob_id",
    "content": "<ENCRYPTED_BYTES>",                  // E2EE: server sees only this
    "type": "text",                                  // text, image, voice, video
    "sent_at": 1726458600,                           // client-side timestamp
    "server_at": 1726458600001                       // server receipt timestamp
  }

MESSAGE STATES:
  QUEUED     → Message accepted by server (buffered in memory)
  SENT       → Stored in Cassandra (✓ shown to sender)
  DELIVERED  → Recipient's device received it (✓✓ shown to sender)
  READ       → Recipient opened the conversation (✓✓ blue to sender)

DELIVERY PROTOCOL:

1. Alice sends message via WebSocket:
   {type: "send", message_id: "msg_abc", to: "bob_id", content: "..."}

2. Connection Server A receives message:
   → Write to Cassandra: {message_id, conversation_id, sender, content, status: "SENT"}
   → Send ACK to Alice: {type: "ack", message_id: "msg_abc", status: "SENT"}  [✓ shown]

3. Delivery Service queries Presence Service:
   Is bob_id online? → Redis: "bob" → "connection_server_B:8080:conn_id_456"
   
   YES (Bob online):
   → Push to Connection Server B internal API: deliver_to_conn("conn_id_456", message)
   → Connection Server B → Bob's WebSocket: message received
   → Bob's device sends ACK: {type: "ack", message_id: "msg_abc", status: "DELIVERED"}
   → Update Cassandra status → Notify Alice: {type: "receipt", message_id: "msg_abc", status: "DELIVERED"}  [✓✓ shown]
   
   NO (Bob offline):
   → Message stays in Cassandra with status: "SENT"
   → Send push notification to Bob (APNs / Firebase FCM)
   → Bob comes online → Connection Server sends "you have pending messages"
   → Bob's client fetches pending → delivers → ACK

4. Bob opens conversation:
   Bob's client: {type: "read_receipt", message_ids: ["msg_abc", ...]}
   → Update status → notify Alice → ✓✓ blue

CASSANDRA SCHEMA FOR MESSAGES:
  CREATE TABLE messages (
      conversation_id  UUID,
      message_id       TIMEUUID,     -- time-ordered UUID (natural sort by time)
      sender_id        UUID,
      recipient_id     UUID,
      content          BLOB,          -- encrypted bytes (E2EE)
      message_type     TEXT,          -- text, image, voice, video
      status           TEXT,          -- SENT, DELIVERED, READ
      server_timestamp TIMESTAMP,
      PRIMARY KEY ((conversation_id), message_id)
  ) WITH CLUSTERING ORDER BY (message_id DESC);
  
  -- Pending messages (for offline delivery):
  CREATE TABLE pending_messages (
      recipient_id  UUID,
      message_id    TIMEUUID,
      conversation_id UUID,
      payload       BLOB,             -- full message, compressed
      PRIMARY KEY ((recipient_id), message_id)
  ) WITH default_time_to_live = 2592000;  -- 30-day TTL

WHY CASSANDRA:
  100B messages/day = 1.16M writes/sec.
  Cassandra: optimized for high write throughput.
  Messages: always written by time → time-ordered partition key makes reads fast.
  TTL support: auto-delete delivered messages (saves storage).
```

---

## STEP 5 — Deep-Dive: Presence Service

```
THE PROBLEM: User sends message. Is recipient online? Which server holds their connection?

SOLUTION: Redis-based presence store.

  ON CONNECT:
    def user_connected(user_id, server_id, connection_id):
        redis.hset("presence", user_id, json.dumps({
            "server_id": server_id,
            "conn_id": connection_id,
            "status": "online",
            "connected_at": time.now()
        }))
        redis.expire(f"heartbeat:{user_id}", 30)  # expire if no heartbeat in 30s
  
  HEARTBEAT (client sends every 15 seconds):
    def heartbeat(user_id):
        redis.setex(f"heartbeat:{user_id}", 30, 1)  # refresh 30s TTL
        # If this expires: Redis auto-deletes → we know user disconnected
  
  ON DISCONNECT:
    def user_disconnected(user_id):
        redis.hdel("presence", user_id)
  
  LOOKUP:
    def get_user_location(user_id) -> dict | None:
        data = redis.hget("presence", user_id)
        if data and redis.exists(f"heartbeat:{user_id}"):
            return json.loads(data)
        return None  # offline

HANDLING DISCONNECTIONS:
  Problem: server crashes without clean disconnect. User appears "online" forever.
  Fix: heartbeat TTL. If no heartbeat for 30s → treat as offline.
  
  When user reconnects after crash:
    New connection → new heartbeat → presence updated with new server location.
    Any messages delivered via new connection.

LAST SEEN:
  On disconnect: record disconnect time.
  redis.hset("last_seen", user_id, int(time.now()))
  
  Show: "Last seen today at 3:42 PM"
  Privacy setting: allow user to disable "Last seen" (set "privacy:last_seen:{user_id}" = "off")
```

---

## STEP 6 — Deep-Dive: End-to-End Encryption

```
PROTOCOL: Signal Protocol (what WhatsApp actually uses).
KEY EXCHANGE: X3DH (Extended Triple Diffie-Hellman).
MESSAGE ENCRYPTION: Double Ratchet Algorithm.

KEYS PER USER (stored on device, never sent to server):
  Identity Key Pair:           IK = (IKpub, IKpriv) — permanent, long-term identity
  Signed Pre-Key Pair:         SPK = (SPKpub, SPKpriv) — rotated monthly
  One-Time Pre-Keys:           OPK1..OPKn = (OPK_ipub, OPK_ipriv) — single use
  
  Public keys UPLOADED to WhatsApp Key Server on registration:
  PUT /keys/{user_id} {IKpub, SPKpub, [OPK1pub, OPK2pub, ..., OPK100pub]}

ALICE SENDS FIRST MESSAGE TO BOB:
  Step 1: Alice fetches Bob's public keys from WhatsApp Key Server.
          GET /keys/bob_id → {IKpub, SPKpub, OPK1pub}  (OPK consumed — one-time use)
  
  Step 2: Alice computes shared secret (X3DH) using:
          DH1 = DH(Alice.IKpriv, Bob.SPKpub)
          DH2 = DH(Alice.EKpriv, Bob.IKpub)     // EK = ephemeral key, generated now
          DH3 = DH(Alice.EKpriv, Bob.SPKpub)
          DH4 = DH(Alice.EKpriv, Bob.OPK1pub)   // uses one-time pre-key
          SK = KDF(DH1 || DH2 || DH3 || DH4)   // shared secret
  
  Step 3: Alice encrypts message with SK.
          ciphertext = AES-GCM(SK, "Hello Bob!")
  
  Step 4: Alice sends to WhatsApp server:
          {to: "bob", content: ciphertext, session_init: {Alice.IKpub, Alice.EKpub, OPK1_id}}
  
  Step 5: WhatsApp server routes to Bob. CANNOT DECRYPT (no SK).
  
  Step 6: Bob reconstructs SK using same DH with HIS private keys.
          Decrypts ciphertext → "Hello Bob!"

DOUBLE RATCHET (forward secrecy):
  After X3DH: use Double Ratchet for each subsequent message.
  Each message uses a NEW derived key.
  Compromising one message key → cannot decrypt past/future messages.
  This is "forward secrecy" — past messages safe even if key compromised later.

METADATA WHITEPAPER (what WhatsApp CAN see):
  ✓ Who messages whom (social graph)
  ✓ When messages sent
  ✓ Message frequency, patterns
  ✗ Message content (encrypted)
  ✗ Group membership (metadata encrypted in newer versions)

INTERVIEW: "The server stores only ciphertext. Private keys never leave user devices.
WhatsApp uses Signal Protocol: X3DH for key exchange, Double Ratchet for messages.
Forward secrecy means past messages safe even if current keys compromised."
```

---

## STEP 7 — Group Messaging

```
GROUP METADATA:
  CREATE TABLE groups (
      group_id    UUID PRIMARY KEY,
      name        TEXT,
      creator_id  UUID,
      created_at  TIMESTAMP,
      max_members INT DEFAULT 512
  );
  
  CREATE TABLE group_members (
      group_id   UUID,
      user_id    UUID,
      joined_at  TIMESTAMP,
      role       TEXT,  -- admin, member
      PRIMARY KEY ((group_id), user_id)
  );

GROUP MESSAGE DELIVERY:
  def deliver_group_message(msg, group_id):
      members = db.get_group_members(group_id)  # up to 512 members
      
      # Fan-out: one message → N deliveries
      for member_id in members:
          if member_id == msg.sender_id:
              continue  # don't send back to sender
          
          location = presence.get_user_location(member_id)
          if location:
              # Online: push via WebSocket
              connection_servers.deliver(location['server_id'], member_id, msg)
          else:
              # Offline: store in Cassandra pending_messages
              cassandra.insert_pending(member_id, msg)
              push_notification.send(member_id, "New message in {group_name}")

E2EE FOR GROUPS (Sender Key Protocol):
  One sender key per group per user.
  Alice distributes her "sender key" to all group members (encrypted to each member's IK).
  Alice encrypts group messages with her sender key.
  Each member decrypts with the sender key (already distributed).
  
  Advantage: 1 encryption per message (not N).
  Server: routes one ciphertext to all members. Much more efficient than 1:1.

DELIVERY RECEIPTS FOR GROUPS:
  ✓✓ shows when ALL members have DELIVERED.
  ✓✓ blue only when you open the conversation to see individual read receipts.
  
  Storage: group_delivery_receipts(message_id, user_id, status, timestamp)
  When: all members deliver → sender sees ✓✓.
```

---

## STEP 8 — Trade-offs

```
TRADE-OFF 1: Store-and-forward vs peer-to-peer
  P2P: messages go device-to-device directly. True privacy. No server storage.
  Problem: both parties must be online simultaneously. Bad for mobile users.
  Store-and-forward: server buffers. Works offline.
  Decision: Store-and-forward with E2EE. Best of both.

TRADE-OFF 2: WebSocket vs HTTP long-polling
  WebSocket: persistent, low-latency push. Requires sticky sessions.
  Long-polling: client polls every 30s. Simple. Works anywhere. High latency.
  Decision: WebSocket. 1B users need real-time delivery. Long-polling is 2005.

TRADE-OFF 3: Cassandra vs PostgreSQL for messages
  PostgreSQL: ACID. Better for complex queries. Lower write throughput.
  Cassandra: 1M+ writes/sec. No JOINs. Time-series optimal.
  Decision: Cassandra. 1.16M messages/sec is beyond single PostgreSQL capacity.
  Access pattern is: "get all messages in conversation X" → perfect partition key.

TRADE-OFF 4: Read receipts privacy
  Some users don't want others to know when they read messages.
  Decision: opt-out setting. If you disable read receipts: you also can't see others'.
  Symmetric: fair. WhatsApp's actual approach.

TRADE-OFF 5: Group size limit 512
  Larger groups need fan-out to more users per message.
  512 × 1.16M group msg/sec = 594M deliveries/sec at extreme scale.
  500+ members: WhatsApp uses pub/sub channels (Broadcast Lists) instead.
  Decision: 512 for interactive groups. No real-time E2EE fan-out above this.
```

---

## STEP 9 — Follow-Up Questions

```
Q: "How do you handle a 100M-member broadcast (like a country-wide alert)?"
A: Different product: Broadcast Lists or Channels (WhatsApp's newer feature).
   Publisher pushes one message. Server fans out via push notification infrastructure.
   Not E2EE (or different E2EE model). More like email broadcast.

Q: "How do you implement message search?"
A: E2EE means server can't index content.
   Search must happen on-device (client-side).
   Each client maintains local encrypted index of their messages.
   Search: client decrypts local index, searches, returns results.
   Server-side search: only metadata (sender, time) — not content.

Q: "What if the connection server crashes?"
A: Client notices WebSocket disconnect → reconnects to any available server.
   Presence Service: old server removed from Redis (heartbeat expires).
   New server: client reconnects, sends "connect" event, gets new presence entry.
   Pending messages: client fetches all pending from Cassandra on reconnect.

Q: "How do you handle message ordering?"
A: Within a conversation: messages have server_timestamp + message_id (TIMEUUID).
   Display: sort by server_timestamp.
   Edge case: Alice sends 2 rapid messages. Server assigns timestamps in order.
   But: if two clients send simultaneously → server serializes → order deterministic.
   TIMEUUID ensures total ordering even if same millisecond timestamp.

Q: "How would you handle location sharing (WhatsApp Live Location)?"
A: Sender's device publishes GPS coordinates every 5 seconds to a "location" topic.
   Recipients subscribe to that topic via WebSocket.
   Server: relays coordinates (encrypted). Recipient decrypts and displays on map.
   Expiry: location sharing ends after N minutes → stop publishing.
   Storage: ephemeral (no need to store location history on server).
```


---

## STEP 10 — Deep-Dive: Connection Server Architecture

```
CHALLENGE: 500M concurrent WebSocket connections.
  Each connection = persistent TCP socket = ~50KB server memory.
  500M x 50KB = 25 TB RAM total.
  Single server: max ~64 GB RAM -> 64GB/50KB = 1.28M connections/server.
  Servers needed: 500M / 1.28M = ~390 servers (call it 500 with headroom).

WHY STICKY SESSIONS MATTER:
  Alice is connected to Connection Server A (CS-A).
  If Bob's message goes to CS-B, CS-B must internally route to CS-A to reach Alice.
  
  Alternative: no sticky sessions -> any server can handle any request.
  Problem: stateful WebSocket (Alice's open TCP socket IS on CS-A).
  You can't "move" a WebSocket connection between servers mid-session.
  
  Solution: sticky routing for DELIVERY, not for initial connection.
    Presence Service knows: Alice -> CS-A.
    CS-B receives message for Alice -> looks up Presence -> forwards to CS-A via internal RPC.
    CS-A delivers to Alice's open WebSocket.

CONNECTION SERVER INTERNAL ROUTING:
  CS-A needs to forward message to CS-B for delivery to Bob.
  
  Method 1: Direct RPC (gRPC)
    CS-A -> gRPC call -> CS-B.deliver_message(conn_id=Bob's conn, message)
    Fast (< 1ms). But: CS-A must know CS-B's address.
    Discovery: Consul/ZooKeeper service registry.
    CS-B registers on startup: "I am CS-B at 10.0.1.42:8080".
    CS-A looks up CS-B address from registry.
  
  Method 2: Redis Pub/Sub
    CS-A publishes to Redis channel: "ws:CS-B" -> message.
    CS-B subscribes to its own channel.
    CS-B receives -> delivers to Bob.
    Pro: decoupled. Con: extra Redis hop.
  
  WhatsApp uses Method 1 (direct RPC). Lowest latency.

CONNECTION SERVER FAILOVER:
  CS-A crashes. Alice's WebSocket is lost.
  Alice's client: detects disconnect (TCP RST or timeout).
  Client: automatically reconnects (exponential backoff: 1s, 2s, 4s, max 30s).
  New connection: goes to any available CS (load balancer round-robin).
  Presence Service: old entry for Alice expires (heartbeat TTL = 30s).
  New entry: Alice -> new CS.
  Pending messages: when Alice reconnects, CS fetches pending from Cassandra.
  
  User experience: "WhatsApp reconnecting..." spinner for < 30 seconds. Seamless.

LOAD BALANCER FOR WEBSOCKETS:
  Problem: standard HTTP load balancer (round-robin) sends each HTTP request to different server.
  WebSocket: initial HTTP upgrade -> then persistent TCP. LB must route ALL traffic for this connection to same CS.
  
  Solution: TCP-layer load balancer (Layer 4, not Layer 7).
    AWS NLB (Network Load Balancer): Layer 4, sticky by connection (TCP 5-tuple).
    Once TCP connection established, all packets go to same CS.
    No HTTP inspection needed.
  
  Alternative: DNS-based sticky routing (user's IP -> CS assignment).
    Less flexible but simpler.
```

---

## STEP 11 — Deep-Dive: Message Ordering and Deduplication

```
MESSAGE ORDERING GUARANTEE:
  Within a conversation: Alice sends msg_1 then msg_2.
  Must arrive to Bob as: msg_1, msg_2 (not reversed).
  
  HOW WE ENSURE IT:
  
  Option A: Server assigns timestamps.
    Server receives msg_1 at t=100ms, msg_2 at t=101ms.
    server_timestamp: msg_1=100, msg_2=101.
    Bob sorts by server_timestamp. Order guaranteed.
    
    Problem: Clock drift. CS-A and CS-B might have different clocks.
    Fix: NTP (Network Time Protocol) keeps servers within 1ms.
    TIMEUUID: timestamp + node ID + random -> unique AND time-ordered even across servers.
  
  Option B: Client-side sequence numbers.
    Alice includes: {seq: 1} for msg_1, {seq: 2} for msg_2.
    Server respects client sequence numbers for ordering.
    Problem: Alice uses multiple devices (phone + web). Both send seq=1. Conflict.
    Fix: per-device sequence number. {device_id, seq} tuple.
    Server merges: order by server_timestamp, use client seq only for tie-breaking.
  
  WhatsApp's approach: server-assigned TIMEUUID + client seq for display ordering.
  Display: sorted by server_timestamp ascending.

MESSAGE DEDUPLICATION:
  Alice sends msg. Network hiccup. Client retries. Server receives TWICE.
  Two identical messages appear in conversation. BAD.
  
  Idempotency key: client generates UUID per message (random, per attempt).
  {message_id: "client-uuid-abc123", content: "Hello"}
  
  Server: before inserting, check: "have I seen this message_id before?"
  Redis: SET "msg_dedup:{message_id}" with TTL 30 minutes.
  If key exists: reject duplicate. Return same ACK as original.
  If not: process normally, set dedup key.
  
  30-minute TTL: client will stop retrying after a few seconds.
  After 30 min: dedup key expires (free memory). Old message_ids won't be retried.

MULTI-DEVICE SUPPORT:
  Alice has phone + laptop both running WhatsApp Web.
  Message to Alice must be delivered to ALL her devices.
  
  Presence Service: one entry per device, not per user.
  "alice:phone" -> CS-A:conn_123
  "alice:laptop" -> CS-B:conn_456
  
  On message to Alice:
    Lookup all of Alice's active devices.
    Deliver to each device independently.
    Each device sends its own ACK.
    DELIVERED status: set when ALL devices have ACKed.
    Or: set DELIVERED when any one device receives (WhatsApp's actual behavior).
    
  If phone is offline but laptop is online:
    Deliver to laptop immediately.
    Store in pending for phone.
    When phone comes online: deliver pending to phone too.
```

---

## STEP 12 — Deep-Dive: Media Handling

```
MEDIA TYPES: images, voice notes, video, documents, stickers, GIFs.

UPLOAD FLOW (E2EE preserved):
  Alice wants to send a photo to Bob.
  
  Step 1: Alice encrypts photo on her device.
    media_key = random 32-byte symmetric key.
    encrypted_photo = AES-CBC(media_key, photo_bytes).
    hmac = HMAC-SHA256(media_key, encrypted_photo).  // integrity check
  
  Step 2: Alice uploads encrypted_photo to WhatsApp Media Server.
    POST /media/upload
    Body: encrypted_photo bytes
    Server returns: {media_url: "https://mmg.whatsapp.net/d/abc123"}
    Server sees ONLY encrypted bytes. Cannot decrypt.
  
  Step 3: Alice sends message to Bob via normal message channel.
    Content: {
        "type": "image",
        "media_url": "https://mmg.whatsapp.net/d/abc123",
        "media_key": encrypt(media_key, bob_signal_key),  // key encrypted for Bob
        "file_size": 2048000,
        "thumbnail": base64_encoded_low_res_thumbnail
    }
    The thumbnail is sent directly in the message (small, < 5KB).
    Allows Bob to see preview without downloading full image.
  
  Step 4: Bob downloads and decrypts.
    Download: GET https://mmg.whatsapp.net/d/abc123
    Decrypt media_key (using Signal protocol key from Alice).
    Decrypt photo: AES-CBC(media_key, encrypted_photo).
    Verify HMAC (integrity check).
    Display to Bob.

MEDIA STORAGE:
  WhatsApp Media Server: stores encrypted blobs only.
  Storage: distributed object store (similar to S3).
  Retention: 30 days (after that, download link expires).
  Why 30 days? If Bob's phone is offline for 30 days, we delete undownloaded media.
  
  TTL handling:
    Redis: "media_expiry:{media_id}" -> timestamp. TTL = 30 days.
    Background job: expired media -> delete from object store.
    Message remains in conversation with "Media expired" placeholder.

MEDIA CDN:
  Photos/videos served from CDN (PoPs near users).
  CDN key: media_url is random opaque ID. Not guessable.
  Access token: media_url includes signed token (proves Bob is authorized recipient).
  Token expires: 24 hours (fresh token provided if message is old).
  
  WHY CDN?
    1B DAU sending media -> huge bandwidth.
    CDN PoP near each user -> fast download (< 100ms vs 500ms from central server).
    CDN serves encrypted blob: even CDN cannot read content. E2EE preserved.

VOICE NOTE PROCESSING:
  Voice notes: OGG/Opus codec (good quality at low bitrate).
  Duration encoded in message metadata (so waveform shown before download).
  WhatsApp generates waveform: FFT of audio -> amplitude per 100ms chunk -> 64 values.
  Waveform stored in message metadata -> displayed immediately (no need to download full audio).
```

---

## STEP 13 — Deep-Dive: Scaling to 1 Billion Messages/Day

```
BOTTLENECK ANALYSIS AT PRODUCTION SCALE:

MESSAGE INGESTION:
  100B messages/day = 1.16M messages/sec avg; peak 3.5M/sec.
  Each message: receive (WebSocket) -> validate -> write Cassandra -> route -> deliver.
  
  Cassandra write throughput:
    Single node: ~50K writes/sec.
    Cluster: 100 nodes x 50K = 5M writes/sec. Handles 3.5M peak. OK.
    RF=3 (replication factor 3): each write goes to 3 nodes -> 10.5M actual writes/sec.
    LWTs (Lightweight Transactions) for DELIVERED status: AVOID. Too slow.
    Use eventual consistency (QUORUM write: 2 of 3 nodes must ACK).

DELIVERY ROUTING:
  3.5M messages/sec. Each needs: Presence lookup + route to connection server.
  
  Redis Presence lookup: O(1) HGET.
  3.5M HGET/sec across Redis Cluster.
  Redis Cluster: 16 nodes x 200K ops/sec = 3.2M ops/sec. TIGHT at peak.
  Fix: Presence data also cached in-process (LRU cache, 5-second TTL) on each CS.
    Most users send messages frequently -> their presence stays in CS memory.
    Only cache misses hit Redis.
    Cache hit rate: ~85% -> Redis load = 3.5M x 15% = 525K/sec. Comfortable.

CONNECTION SERVER CAPACITY:
  500M concurrent WebSockets. 500 servers x 1M connections each.
  Each server: 32 vCPU, 64 GB RAM. Network: 25 Gbps NIC.
  
  Network bandwidth per CS:
    Inbound: 1M connections x avg 5 messages/sec x 100 bytes = 500 MB/sec = 4 Gbps.
    At 25 Gbps NIC: headroom exists. But kernel TCP overhead can be bottleneck.
    Fix: io_uring (Linux) for zero-copy I/O. Massive throughput improvement.
    WhatsApp used FreeBSD (zero-copy sockets in kernel) historically.

GROUP MESSAGE FAN-OUT AT SCALE:
  512-member group. 1 message -> 512 deliveries.
  If 10% of messages are group: 350K group msg/sec x 512 = 179M deliveries/sec.
  
  This is the TRUE throughput challenge.
  
  Optimization 1: batch delivery per connection server.
    CS-A hosts many group members.
    Instead of 512 individual RPCs (one per CS), batch: send once per destination CS.
    If CS-A hosts 50 members of this group: 1 RPC to CS-A with 50 member deliveries.
    Reduces fan-out RPCs dramatically (from 512 to ~20 unique CS calls per group).
  
  Optimization 2: Sender Key protocol (E2EE for groups).
    ONE ciphertext per message (not 512).
    Server routes same ciphertext to all 512 members.
    Each member has the sender's key -> decrypts locally.
    Server bandwidth: 1 message size, not 512x. Massive savings.

DATABASE HOTSPOTS:
  Popular group (512 members, very active): all messages partition by group_id.
  Same partition -> same Cassandra node -> HOT PARTITION.
  
  Fix: bucket within partition.
    PRIMARY KEY ((group_id, bucket), message_id)
    bucket = floor(message_timestamp / 3600)  // hour bucket
    Each hour's messages are in a separate sub-partition.
    Queries: current hour = current bucket. Very active groups spread across time buckets.
```


---

## DEEP-DIVE IMPROVEMENT: Signal Protocol — E2EE Explained Step by Step

```
WHY E2EE MATTERS:
  WhatsApp server handles 100B messages/day.
  Without E2EE: WhatsApp can read any message. Government can subpoena messages.
  With E2EE: even WhatsApp's own servers cannot decrypt your messages. Period.
  The server stores only ciphertext. The keys exist only on user devices.

THE SIGNAL PROTOCOL — BUILDING BLOCKS:

A) ASYMMETRIC KEY PAIRS (each user has these):
  
  Identity Key Pair (IK):
    Long-term. Generated once when user installs WhatsApp.
    Private key: NEVER leaves device. Stored in device secure enclave.
    Public key: uploaded to WhatsApp's Key Distribution Server (KDS).
  
  Signed Pre-Key (SPK):
    Medium-term (rotated every few weeks).
    One signed pre-key per user on KDS at any time.
    "Signed" by identity key (proves it's authentic).
  
  One-Time Pre-Keys (OPKs):
    Ephemeral. One key per future conversation initiation.
    WhatsApp uploads a batch of 100 OPKs to KDS on registration.
    When you start a conversation with someone: one OPK is consumed.
    KDS informs WhatsApp app to generate and upload more when running low.

B) X3DH — EXTENDED TRIPLE DIFFIE-HELLMAN (session establishment):
  
  SCENARIO: Alice wants to send first message to Bob.
  Alice doesn't need Bob to be online. This is the magic of X3DH.
  
  Alice fetches from KDS:
    Bob's Identity Key (IK_B)
    Bob's Signed Pre-Key (SPK_B)
    Bob's One-Time Pre-Key (OPK_B) — consumed now, deleted from KDS
  
  Alice generates ephemeral key pair (EK_A) for this session only.
  
  Alice computes 4 Diffie-Hellman operations:
    DH1 = DH(IK_A.private, SPK_B)        ← Alice's identity ↔ Bob's signed pre-key
    DH2 = DH(EK_A.private, IK_B)         ← Alice's ephemeral ↔ Bob's identity
    DH3 = DH(EK_A.private, SPK_B)        ← Alice's ephemeral ↔ Bob's signed pre-key
    DH4 = DH(EK_A.private, OPK_B)        ← Alice's ephemeral ↔ Bob's one-time key
  
  Master Secret = HKDF(DH1 || DH2 || DH3 || DH4)
  → Derives a shared symmetric key (256-bit AES key).
  
  CRITICAL: Bob can compute the SAME master secret WITHOUT talking to Alice first.
  When Bob receives the first message:
    He has his private keys (IK_B, SPK_B, OPK_B).
    He sees Alice's IK_A and EK_A (sent in the message header, unencrypted).
    He computes the same 4 DH operations → same master secret. ✓
  
  Neither Alice nor Bob directly sent the key.
  The key was DERIVED from the combination. Even if KDS is compromised: doesn't help.
  Attacker on KDS only sees public keys. Cannot derive the shared secret without private keys.

C) DOUBLE RATCHET ALGORITHM (message-by-message encryption):
  
  Problem with simple symmetric key: if attacker captures key, they can decrypt ALL past messages.
  
  Double Ratchet solution: new encryption key for EACH message. Forward secrecy + break-in recovery.
  
  TWO RATCHETS:
  
  Ratchet 1 — Diffie-Hellman Ratchet:
    Each message includes a new ephemeral DH public key.
    Receiver uses it to generate new chain key.
    Purpose: break-in recovery. If attacker cracks current key → only decrypts CURRENT message.
    Next message: new DH ratchet step → new key. Attacker can't follow.
  
  Ratchet 2 — Symmetric Ratchet (KDF Chain):
    Chain Key → HKDF → Message Key (for this message) + New Chain Key (for next message).
    Chain Key: never transmitted. Only derived locally.
    Forward secrecy: message key derived, message sent, message key DELETED.
    Even if device is compromised LATER: past message keys are gone. Past messages unreadable.
  
  RESULT:
    Each message encrypted with unique key.
    Past keys deleted → forward secrecy.
    Future keys derived from DH ratchet → break-in recovery.
    Server only sees ciphertext. Keys never touch server.

GROUP MESSAGES — SENDER KEY PROTOCOL:
  
  Problem with 1:1 Double Ratchet for groups:
    Alice sends message to 100-person group.
    Double Ratchet: send 100 different ciphertexts (one per member). 100× bandwidth.
  
  Sender Key Protocol:
    Alice generates a single Sender Key for the group.
    She encrypts the Sender Key individually for each member (using their Signal keys). One-time setup.
    From then on: ONE ciphertext per message. All members decrypt with Alice's Sender Key.
    Bandwidth: 1 message, not 100. ✓
  
  What if a member leaves the group?
    Alice (and all members) generate new Sender Keys.
    New keys sent to remaining members only.
    Evicted member can't decrypt future messages.
    This is called "Key Rotation" — happens on membership change.

VERIFICATION — SAFETY NUMBERS:
  How do you know Bob's key on the KDS is actually Bob's (not a man-in-the-middle)?
  WhatsApp Safety Numbers: 60-digit code derived from both users' identity public keys.
  Alice and Bob: show each other their Safety Numbers in-person (or video call).
  If they match → keys are authentic → no MITM. ✓
  If mismatch → someone (WhatsApp? government?) substituted a different key. Alert!
  Most users never check. But the option exists. Security researchers do verify.
```

---

## DEEP-DIVE IMPROVEMENT: Presence Service — Online/Offline/Last Seen

```
PRESENCE AT SCALE:
  500M concurrent users. Each user: connected via WebSocket to a Connection Server.
  Presence = who is online right now, and when were offline users last seen?

PRESENCE DATA MODEL:
  Redis Hash (one per user):
    Key: "presence:{user_id}"
    Fields:
      status: "online" | "away" | "offline"
      last_seen: Unix timestamp (float, seconds since epoch)
      conn_server: "cs-12" (which connection server holds the WebSocket)
      conn_id: "conn_89234" (specific connection on that server)
    TTL: 60 seconds (auto-expires if not refreshed = disconnected)
  
  Example:
    HSET presence:alice status online last_seen 1726458600 conn_server cs-12 conn_id conn_89
    EXPIRE presence:alice 60

HEARTBEAT MECHANISM:
  Problem: WebSocket doesn't have built-in "user is still connected" ping.
  Solution: periodic heartbeat from client.
  
  Client (every 30 seconds):
    Send: {"type": "heartbeat", "timestamp": 1726458600}
    Waits for: {"type": "heartbeat_ack"}
  
  Server (Connection Server, on heartbeat receive):
    redis.hset(f"presence:{user_id}", "status", "online", "last_seen", time.time())
    redis.expire(f"presence:{user_id}", 60)  # Reset TTL to 60s
    Send heartbeat_ack back to client.
  
  If Connection Server doesn't receive heartbeat for 35 seconds:
    User's TTL starts counting down (not refreshed).
    At 60s: Redis auto-evicts presence key → user "offline".
    Background task: record last_seen timestamp in persistent store.
  
  If client doesn't receive heartbeat_ack in 5 seconds:
    Assume connection broken. Reconnect (with exponential backoff).

LAST SEEN (privacy-aware):
  WhatsApp: 3 privacy levels:
    "Everyone": any WhatsApp user can see your last seen.
    "My Contacts": only your contacts can see it.
    "Nobody": no one sees it.
  
  Storage: last_seen stored in Redis (while online) + PostgreSQL (persistent, after offline).
  
  GET last_seen for Alice when Bob queries:
    1. Check Bob's permission to see Alice's last_seen (privacy setting).
    2. If allowed: check Redis first (online user → last_seen is very recent).
       If not in Redis (offline): read from PostgreSQL users table.
    3. Return: "last seen today at 3:45 PM" (formatted by client).
  
  Read receipt tie-in:
    WhatsApp: blue double tick (✓✓) = message read.
    Read receipt only sent if: receiver's privacy allows "read receipts".
    If user turns off read receipts: no blue tick shown to senders.
    But: if user turns off read receipts → they also can't see others' read receipts.
    This is by WhatsApp design (fairness).

PRESENCE PROPAGATION (who to notify when user goes online/offline):
  Alice goes online. Who cares? All her contacts who have open WhatsApp.
  
  Problem: Alice has 500 contacts. 500M users total. Push to 500 devices when Alice connects.
  
  SUBSCRIPTION-BASED APPROACH:
    When Bob opens a chat with Alice:
      Bob's client subscribes: "notify me when Alice's presence changes."
      Subscribe event: Connection Server records: "Bob is watching Alice."
      Redis: SADD "watchers:alice" "bob_id"
    
    When Bob closes the chat / goes to a different chat:
      Unsubscribe: remove Bob from Alice's watchers.
      SREM "watchers:alice" "bob_id"
    
    When Alice's presence changes (online → offline):
      Notify all watchers:
        watchers = redis.smembers("watchers:alice")
        for watcher_id in watchers:
            cs = redis.hget(f"presence:{watcher_id}", "conn_server")
            grpc.call(cs, "deliver_presence", {user_id: "alice", status: "offline"})
      
      This is O(watchers) not O(all_alice_contacts).
      If Alice is in an active chat with 5 people: notify 5 watchers.
      Not 500 contacts (most of whom aren't watching her right now).
  
  RATE LIMITING PRESENCE UPDATES:
    If Alice's network is flaky: online/offline many times per minute.
    1000 status changes/minute × 5 watchers = 5000 presence pushes/minute. For one user. Wasteful.
    
    Solution: debounce presence changes.
      Online → immediate notify (eager, users want to know when friend is online).
      Offline → wait 30 seconds before notifying (maybe connection is temporary).
      If reconnects within 30s: no offline notification sent.
      After 30s offline confirmed: then notify watchers.
      
      Implemented with Redis:
        On disconnect: SET "pending_offline:alice" 1 EX 30 (expire in 30s)
        On reconnect: DEL "pending_offline:alice" (cancel pending notification)
        Background task: scan "pending_offline:*" keys expired → send offline notifications.
```

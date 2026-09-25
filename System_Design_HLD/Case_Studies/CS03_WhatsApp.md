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

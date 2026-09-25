# Topic 6: Message Queues
## HLD Deep Dive | MAANG Interview Ready

---

## 1. Why Message Queues?

```
SYNCHRONOUS PROBLEM:
  User uploads photo.
  App needs to: store photo, resize 5 thumbnails, run ML moderation, update feed, notify followers.
  
  Synchronous: all done before response.
  User waits 15 seconds. If moderation ML is down: entire upload fails.
  Tightly coupled: upload service depends on notification service.

ASYNC WITH QUEUE:
  App stores photo → puts ONE message in queue → responds "uploaded!" immediately.
  Workers consume message asynchronously:
    Thumbnail Worker:    resize 5 versions (3 seconds)
    Moderation Worker:  run ML model (2 seconds)
    Feed Worker:        update feed (0.5 seconds)
    Notification Worker: notify followers (1 second)
  
  All parallel. Total user-visible latency: ~100ms.
  If ML model crashes: message goes back to queue → retry when model recovers.
  Upload service knows NOTHING about notification service → decoupled.

BENEFITS:
  1. Decoupling: producer and consumer evolve independently.
  2. Resilience: if consumer is down, messages wait in queue (not lost).
  3. Scalability: add more workers to consume faster.
  4. Rate limiting: workers consume at their own pace (backpressure).
  5. Async: user gets fast response, processing happens in background.
```

---

## 2. Queue vs Pub/Sub

```
QUEUE (Point-to-Point):
  Producer sends message → Queue → ONE consumer receives it.
  Message deleted after consumption.
  
  Multiple workers: competing consumers → each message processed ONCE.
  Use: task distribution (job queue), email sending, order processing.
  
  [Producer] → [Queue] → Consumer A processes message 1
                        → Consumer B processes message 2
                        → Consumer A processes message 3
  
  Examples: SQS, RabbitMQ, Celery task queue.

PUB/SUB (Publish-Subscribe):
  Publisher sends message to TOPIC.
  ALL subscribers to that topic receive a COPY.
  
  Photo upload event → 4 services ALL receive it:
    Thumbnail service (1 copy)
    Moderation service (1 copy)
    Analytics service (1 copy)
    Notification service (1 copy)
  
  Use: event broadcasting, one-to-many communication.
  Examples: Kafka, Google Pub/Sub, AWS SNS (+ SQS for each subscriber).

RULE: Use Queue for TASKS (one worker does the job).
      Use Pub/Sub for EVENTS (many services react to the same event).

KAFKA IS BOTH:
  Topic with partitions = ordered log.
  Each consumer GROUP reads entire topic (like queue: one worker per group).
  Multiple consumer groups: each group reads full topic (like pub/sub).
  
  Consumer group "thumbnail-workers" reads all events (thumbnail jobs).
  Consumer group "analytics-workers" ALSO reads all events (analytics jobs).
  Both operate independently. Neither knows about the other.
```

---

## 3. Kafka Deep Dive

```
KAFKA CONCEPTS:

BROKER: A Kafka server. Stores and serves messages.
CLUSTER: Multiple brokers. Typically 3-5 for HA.

TOPIC: Named stream of messages. Logical category.
  Examples: "user-registrations", "payment-events", "photo-uploads", "order-placed"

PARTITION: Topic split into ordered, immutable logs.
  "payment-events" → Partition 0, Partition 1, Partition 2 (on different brokers)
  Each partition: ordered sequence of messages, each with an offset.
  Parallelism: N partitions → up to N consumers in a group can consume in parallel.

OFFSET: Position of a message in a partition.
  Consumer tracks its own offset. Can replay from any offset.
  Unlike traditional queues: messages not deleted after consumption (retention-based).

REPLICATION:
  Each partition has 1 leader + N-1 followers.
  replication.factor=3: partition on 3 brokers.
  If leader fails → a follower becomes leader (automatic via Zookeeper/KRaft).

PRODUCER:
  from confluent_kafka import Producer
  
  p = Producer({'bootstrap.servers': 'kafka:9092'})
  
  def delivery_callback(err, msg):
      if err:
          print(f'Message delivery failed: {err}')
      else:
          print(f'Message delivered to {msg.topic()} [{msg.partition()}] at offset {msg.offset()}')
  
  p.produce(
      topic='payment-events',
      key=str(user_id).encode(),      # same key → same partition (ordering per user)
      value=json.dumps(event).encode(),
      callback=delivery_callback
  )
  p.flush()  # wait for all messages to be delivered

CONSUMER GROUP:
  from confluent_kafka import Consumer
  
  c = Consumer({
      'bootstrap.servers': 'kafka:9092',
      'group.id': 'payment-processor-group',
      'auto.offset.reset': 'earliest',         # start from beginning if no committed offset
      'enable.auto.commit': False              # manual commit for at-least-once
  })
  c.subscribe(['payment-events'])
  
  while True:
      msg = c.poll(1.0)
      if msg is None: continue
      if msg.error():
          print(f"Error: {msg.error()}")
          continue
      
      # Process message
      event = json.loads(msg.value())
      process_payment(event)
      
      # Manually commit offset AFTER successful processing
      c.commit(asynchronous=False)  # at-least-once: process then commit

DELIVERY SEMANTICS:
  At-most-once:   Commit offset before processing. Fast. Message may be lost on crash.
  At-least-once:  Commit offset after processing. Message processed ≥1 times.
                  Consumer must be idempotent (safe to process same message twice).
  Exactly-once:   Kafka transactions + idempotent producers. Complex. 
                  Use when: financial events where double-processing is catastrophic.

KAFKA RETENTION:
  Messages NOT deleted after consumption. Retained for N days (default 7).
  Multiple consumer groups: all read independently.
  New service added: can replay from day 0 (backfill historical data).
  This is the KEY advantage over RabbitMQ/SQS (which delete on consume).
```

---

## 4. RabbitMQ Deep Dive

```
RABBITMQ CONCEPTS:

Exchange: receives messages from producers, routes to queues.
Queue: stores messages until consumed.
Binding: rule connecting exchange to queue.

EXCHANGE TYPES:
  Direct: route by routing key exactly.
    "payment.created" → "payment-queue"
    
  Topic: route by wildcard matching.
    "payment.*"    → matches "payment.created", "payment.failed"
    "*.created"    → matches "payment.created", "order.created"
    "#"            → matches everything (fan-out)
  
  Fanout: route to ALL bound queues (broadcast).
    One message → thumbnail-queue, moderation-queue, notification-queue simultaneously.
  
  Headers: route by message headers (not topic name).

RELIABLE DELIVERY:
  Publisher confirms: broker acknowledges each message.
  Consumer acks: consumer confirms processing before message deleted.
  Persistent messages: stored to disk (not lost on broker restart).
  Dead letter exchange (DLX): failed messages routed to a separate "dead letter queue."

USE CASES FOR RABBITMQ (vs Kafka):
  ✓ Complex routing (different message types → different queues based on attributes)
  ✓ Task queues with priority (higher-priority messages processed first)
  ✓ Request-reply patterns (RPC-style over queue)
  ✓ When message must be deleted after consumption (no replay needed)
  ✓ Short message lifetime (not 7-day retention)
  ✗ High throughput (Kafka: 1M/sec vs RabbitMQ: ~50K/sec)
  ✗ Replay/reprocessing historical messages (use Kafka)
  ✗ Multiple consumer groups reading same stream (use Kafka)

PYTHON EXAMPLE:
  import pika
  
  connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
  channel = connection.channel()
  channel.queue_declare(queue='email-tasks', durable=True)
  
  # Producer
  channel.basic_publish(
      exchange='',
      routing_key='email-tasks',
      body=json.dumps({"to": "alice@example.com", "subject": "Welcome!"}),
      properties=pika.BasicProperties(delivery_mode=2)  # persistent
  )
  
  # Consumer
  def callback(ch, method, properties, body):
      task = json.loads(body)
      send_email(task['to'], task['subject'])
      ch.basic_ack(delivery_tag=method.delivery_tag)  # ack after processing
  
  channel.basic_qos(prefetch_count=1)  # one message at a time per worker
  channel.basic_consume(queue='email-tasks', on_message_callback=callback)
  channel.start_consuming()
```

---

## 5. AWS SQS and SNS

```
SQS (Simple Queue Service):
  Managed queue. No brokers to manage.
  Standard: at-least-once delivery. Messages may arrive out-of-order.
  FIFO: exactly-once, ordered. Lower throughput (3,000 msg/sec vs unlimited for Standard).
  
  Visibility timeout: message invisible to other consumers while being processed.
  If worker crashes: visibility timeout expires → message re-appears → another worker picks it up.
  
  DLQ (Dead Letter Queue): 
    After N failed processing attempts (maxReceiveCount): 
    Message moved to DLQ for manual inspection.
  
  Boto3 example:
    import boto3
    sqs = boto3.client('sqs', region_name='us-east-1')
    
    # Send
    sqs.send_message(QueueUrl='...', MessageBody=json.dumps(task))
    
    # Receive (long polling: wait up to 20s for messages)
    messages = sqs.receive_message(QueueUrl='...', MaxNumberOfMessages=10, WaitTimeSeconds=20)
    
    for msg in messages.get('Messages', []):
        process(json.loads(msg['Body']))
        sqs.delete_message(QueueUrl='...', ReceiptHandle=msg['ReceiptHandle'])

SNS (Simple Notification Service) + SQS fan-out:
  Pattern: one event → multiple SQS queues.
  
  SNS topic: "order-placed"
  Subscribers:
    - Inventory SQS queue (deduct stock)
    - Email SQS queue (send confirmation)
    - Analytics SQS queue (record event)
    - Recommendation SQS queue (update model)
  
  Each SQS queue: separate consumer group. Independent retry, independent scaling.
  Advantage: decoupled. Add new consumer: just subscribe new SQS to SNS topic.
```

---

## 6. Backpressure and Queue Depth Management

```
PROBLEM: Producer publishes 100K messages/sec. Consumer processes 10K/sec.
Queue grows 90K messages/sec → memory exhaustion.

BACKPRESSURE: Signal to producer to slow down.

Approaches:

1. Block producer (strongest backpressure):
   Producer's publish() call blocks until queue has space.
   Kafka: max.block.ms (default: 60000ms). If buffer full, block for up to 60s.
   
   Downside: can cascade failure back to user request if producer is on critical path.

2. Drop messages (weakest backpressure):
   If queue full: discard new messages.
   OK for: metrics, logs, analytics (losing a few events is acceptable).
   NOT OK for: financial events, order placements.

3. Reject with error:
   API returns 503 to producer if queue full.
   Producer returns error to user ("System busy, try again").
   User sees error but data is not lost.

4. Rate limiting upstream:
   Measure consumer throughput. Rate limit producers to that speed.
   Token bucket at producer: max N messages/sec regardless of queue depth.

QUEUE DEPTH MONITORING:
  Kafka: consumer lag = last produced offset - last consumed offset.
  Alert: consumer lag > 100,000 → consumers falling behind → scale up.
  Auto-scaling: Kafka consumer lag → trigger HPA to add consumer pods.

DEAD LETTER QUEUES:
  Message fails processing after N retries (e.g., malformed payload).
  Move to DLQ for manual inspection.
  Never silently drop failed messages in production.
  
  SQS: configure maxReceiveCount=3 → after 3 failures → DLQ.
  Kafka: implement in consumer code: retry 3× → write to "dead-letters" topic.
```

---

## 7. Exactly-Once Processing

```
WHY HARD:
  Consumer receives message → processes → crashes before committing offset.
  Queue resends message → consumer processes AGAIN → duplicate.
  
  At-least-once: message processed ≥1 times. Duplicates possible.
  Exactly-once: processed exactly 1 time. Requires special handling.

APPROACH 1: Idempotent Consumer
  Design consumer so processing the same message twice has same result as once.
  
  Example: "Charge user $10 for order #456"
  Idempotent: before charging → check if "order_456_charged" exists in DB.
    YES → already charged → skip.
    NO → charge → insert "order_456_charged" marker.
  
  Key: message_id → deduplication_id stored in DB/Redis.

APPROACH 2: Kafka Transactions + Idempotent Producer
  Kafka producer can be made idempotent (retries don't duplicate messages).
  Kafka consumer: atomic read + process + write (all in one transaction).
  
  with producer.begin_transaction():
      result = process(message)
      producer.send("output-topic", result)
      consumer.commit()          # commit offset atomically with produce
  producer.commit_transaction()
  
  Either ALL happen (process + output + offset commit) or NONE.

APPROACH 3: Outbox Pattern
  Instead of publishing to queue directly from service:
  1. Write business data + event to DB in ONE ACID transaction.
  2. Background job reads "outbox" table → publishes to Kafka → marks as published.
  
  orders table: {id, status, ...}
  outbox table: {id, event_type, event_data, published_at}
  
  BEGIN TRANSACTION;
    INSERT INTO orders VALUES (...);
    INSERT INTO outbox (event_type, event_data) VALUES ('order_placed', {...});
  COMMIT;
  -- Both committed atomically.
  
  Outbox publisher: reads unpublished outbox rows → publishes to Kafka → marks published.
  If Kafka publish fails: retry. Safe (outbox publisher is idempotent).
```

---

## 8. Comparison: Kafka vs RabbitMQ vs SQS

```
Feature               │ Kafka          │ RabbitMQ         │ AWS SQS
──────────────────────┼────────────────┼──────────────────┼──────────────────
Throughput            │ 1M+ msg/sec    │ ~50K msg/sec     │ Unlimited (managed)
Message replay        │ ✓ (retention)  │ ✗ (deleted)      │ ✗ (deleted)
Consumer groups       │ ✓ Multiple     │ Competing only   │ Competing only
Ordering              │ Per-partition  │ Per-queue        │ FIFO mode only
Routing               │ Topic/partition│ Exchange types   │ Simple
Delivery              │ At-least-once* │ At-least-once    │ At-least-once
Complex routing       │ ✗              │ ✓                │ ✗
Managed service       │ Confluent/MSK  │ Amazon MQ        │ ✓ Native
Operational burden    │ High (self-host)│ Medium          │ Zero
Retention             │ Days (configurable) │ Until consumed│ 4 days (max 14)
Best for              │ Event streaming│ Complex routing  │ Simple task queue

*Kafka has exactly-once with transactions.

WHEN TO USE WHAT:
  Kafka:     High throughput. Replay needed. Multiple independent consumer groups.
             Event sourcing. Real-time stream processing.
  RabbitMQ:  Complex message routing. Priority queues. Request-reply RPC.
             Lower throughput. Want delete-on-consume.
  SQS:       AWS-native stack. Simple task queue. Zero ops burden.
             Don't need replay. FIFO for ordering.
```

---

## 9. Interview Questions

```
Q1: "How does Kafka differ from RabbitMQ?"
A: Kafka: high throughput (1M/sec), message replay (retention-based), multiple consumer groups.
   RabbitMQ: complex routing, lower throughput, delete-on-consume.
   Choose Kafka for event streaming and replay. RabbitMQ for complex routing or simple tasks.

Q2: "What is consumer lag in Kafka and why does it matter?"
A: Difference between latest offset and consumer's committed offset.
   High lag: consumers falling behind producers. May lead to data loss if retention expires.
   Monitor: Kafka consumer group lag metric. Alert > threshold. Auto-scale consumers.

Q3: "How do you achieve exactly-once message processing?"
A: Option 1: Idempotent consumer (deduplication using message ID in DB).
   Option 2: Kafka transactions (atomic process + offset commit).
   Option 3: Outbox pattern (write event to DB atomically, then publish from outbox).

Q4: "What is the outbox pattern?"
A: Write business data + event to same DB transaction atomically.
   Background job reads outbox table, publishes to Kafka, marks as published.
   Solves: "I wrote to DB but Kafka publish failed (or vice versa)."

Q5: "How would you handle a failing consumer that keeps crashing on the same message?"
A: Retry N times with exponential backoff.
   After N failures: move message to Dead Letter Queue (DLQ) for investigation.
   Never silently discard. Alert on DLQ activity.
   Kafka: implement in consumer code. SQS: configure maxReceiveCount + DLQ setting.
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

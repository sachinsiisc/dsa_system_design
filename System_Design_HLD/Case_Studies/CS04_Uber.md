# CS04: Design Uber (Ride-Sharing Platform)
## Full HLD Case Study | MAANG Interview Ready

---

## STEP 1 — Requirements

```
FUNCTIONAL:
  1. Rider requests a ride: pickup + dropoff location
  2. System finds nearest available driver
  3. Driver accepts or declines
  4. Real-time tracking: rider sees driver moving on map (update every 5s)
  5. ETA calculation and route display
  6. Dynamic pricing (surge pricing based on supply/demand)
  7. Trip completion and payment processing
  8. Ratings: rider rates driver, driver rates rider after trip

NON-FUNCTIONAL:
  - Scale: 5M active drivers, 5M rides/day
  - Driver location updates: every 5 seconds from ALL active drivers
  - Matching latency: < 1 second from request to "driver found"
  - Tracking update latency: < 5 seconds (live map)
  - High availability: 99.99% (unavailability during rush hour = major revenue loss)
  - Surge pricing: update every minute per geographic zone
  - Global: multiple countries, currencies, regulations
```

---

## STEP 2 — Scale Estimation

```
RIDES:
  5M rides/day ÷ 86,400 = 57.9 rides/sec avg
  Peak (6-9 PM): 5× = ~290 rides/sec

DRIVER LOCATION UPDATES:
  5M active drivers × 1 update/5 seconds = 1M location updates/sec
  Per update: {driver_id(8B), lat(8B), lng(8B), timestamp(8B), heading(4B), speed(4B)} = 40B
  Throughput: 1M × 40B = 40 MB/sec of location data
  
  This is the HOTTEST write path. Cannot use SQL DB for this!
  Solution: Redis Geo / In-memory data structure.

MATCHING:
  290 ride requests/sec at peak.
  Each request: find all drivers within 5km radius from 5M driver locations.
  Must complete in < 500ms.
  → Geospatial indexing is CRITICAL.

TRIPS STORAGE:
  5M trips/day × 365 × 5 years = 9.125B trips
  Per trip: driver_id + rider_id + route_polyline + fare + timestamps + rating ≈ 5KB avg
  Total: 9.125B × 5KB = 45.6 TB over 5 years → sharding needed.

SURGE PRICING READS:
  Every ride request reads surge price for pickup zone.
  290 req/sec × 1 Redis read = 290 reads/sec → trivially handled by Redis.

NOTIFICATIONS:
  290 rides/sec → 290 push notifications to matched driver.
  Each declined match → another notification. Assume 2 avg → 580 notifications/sec.
```

---

## STEP 3 — High-Level Architecture

```
DRIVER APP:
  ┌──────────────┐    location updates (every 5s)     ┌─────────────────────┐
  │  Driver App  │ ──────────────────────────────────► │  Location Service   │
  └──────────────┘                                     │  → Redis H3 Grid    │
         ▲                                             └─────────────────────┘
         │ ride offer push (WebSocket/FCM)
         │
  ┌──────┴───────┐    ride request                    ┌─────────────────────┐
  │  Rider App   │ ──────────────────────────────────► │  Dispatch Service   │
  └──────────────┘                                     │  (find + match)     │
         │ real-time tracking                          └──────────┬──────────┘
         ▼                                                        │
  ┌──────────────┐    trip updates (WebSocket)         ┌──────────▼──────────┐
  │ Trip Service │ ◄─────────────────────────────────── │  Trip State Machine │
  └──────────────┘                                     └──────────────────────┘

FULL DIAGRAM:
  ┌────────────────────────────────────────────────────────────────┐
  │                     API GATEWAY / LB                           │
  └─────┬──────────────┬────────────────┬───────────────┬──────────┘
        │              │                │               │
  ┌─────▼──────┐ ┌─────▼──────┐ ┌──────▼──────┐ ┌─────▼──────┐
  │  Location  │ │  Dispatch  │ │   Trip      │ │  Payment   │
  │  Service   │ │  Service   │ │   Service   │ │  Service   │
  └─────┬──────┘ └─────┬──────┘ └──────┬──────┘ └─────┬──────┘
        │              │                │               │
  ┌─────▼──────────────▼────────────────▼───────────────▼──────┐
  │            REDIS CLUSTER                                      │
  │  driver locations (H3) │ presence │ surge prices │ sessions  │
  └──────────────────────────────────────────────────────────────┘
        │              │                │
  ┌─────▼──────┐ ┌─────▼──────┐ ┌──────▼──────┐
  │ PostgreSQL │ │ Cassandra  │ │   Kafka     │
  │  (trips,   │ │  (trip     │ │  (events,   │
  │  users,    │ │  tracking  │ │  analytics, │
  │  drivers)  │ │  history)  │ │  surge calc)│
  └────────────┘ └────────────┘ └─────────────┘
```

---

## STEP 4 — Deep-Dive: Driver Location Storage

```
THE PROBLEM:
  5M active drivers. Each updates every 5 seconds.
  1M updates/sec.
  Need to query: "all drivers within 5km of (lat, lng)" in < 100ms.

APPROACH 1: PostgreSQL with PostGIS
  Spatially indexed geometry column.
  Query: SELECT driver_id FROM drivers WHERE ST_DWithin(location, rider_point, 5000)
  
  Problem: 1M writes/sec is WAY beyond single PostgreSQL capacity (10K writes/sec).
  Even with sharding: location data changes CONSTANTLY → massive index thrashing.
  NOT suitable.

APPROACH 2: Redis GEOADD
  redis.geoadd("drivers:active", longitude, latitude, driver_id)
  redis.georadius("drivers:active", rider_lng, rider_lat, 5, "km", count=20, sort="ASC")
  
  Pros: O(N+log M) query. Fast. Built-in.
  Cons: All 5M drivers in ONE Redis key.
        Can't shard by geography within one Redis key.
        5M × 25 bytes ≈ 125MB per key → manageable on one Redis node.
        But: all radius queries go to SAME Redis shard → hotspot.

APPROACH 3: H3 Hexagonal Grid (UBER'S ACTUAL APPROACH)
  H3: library developed by Uber (open-sourced).
  Divides Earth into hexagonal cells at multiple resolution levels.
  
  RESOLUTION 7: each cell ≈ 1.2 km², ~98K cells to cover continental US.
  RESOLUTION 5: each cell ≈ 252 km², cover an entire city in one cell.
  
  DATA STRUCTURE:
    For each H3 cell at resolution 7:
      Redis SET: "drivers:cell:{h3_index}" → {driver_id_1, driver_id_2, ...}
    
    For each driver:
      Redis HASH: "driver:{driver_id}" → {lat, lng, status, heading, speed}
  
  LOCATION UPDATE:
  def update_driver_location(driver_id: str, lat: float, lng: float):
      # Compute new H3 cell
      new_cell = h3.geo_to_h3(lat, lng, resolution=7)
      
      # Get old cell (stored in driver hash)
      old_cell = redis.hget(f"driver:{driver_id}", "h3_cell")
      
      # If moved to different cell: update set memberships
      if old_cell != new_cell:
          if old_cell:
              redis.srem(f"drivers:cell:{old_cell}", driver_id)
          redis.sadd(f"drivers:cell:{new_cell}", driver_id)
      
      # Always update driver details
      redis.hset(f"driver:{driver_id}", mapping={
          "lat": lat, "lng": lng,
          "h3_cell": new_cell,
          "heading": heading,
          "speed": speed,
          "updated_at": time.now()
      })
  
  NEARBY DRIVER QUERY:
  def find_nearby_drivers(rider_lat: float, rider_lng: float, radius_km: float) -> list:
      rider_cell = h3.geo_to_h3(rider_lat, rider_lng, resolution=7)
      
      # Get all cells within N rings (ring size ≈ 1.2km at res 7)
      rings = math.ceil(radius_km / 1.2)  # 5km radius → 4 rings
      nearby_cells = h3.k_ring(rider_cell, rings)  # hexagonal rings
      
      # Union of all driver IDs in these cells
      driver_ids = redis.sunion([f"drivers:cell:{cell}" for cell in nearby_cells])
      
      # Filter and rank by actual distance
      candidates = []
      for driver_id in driver_ids:
          driver = redis.hgetall(f"driver:{driver_id}")
          if driver.get("status") == "available":
              actual_dist = haversine(rider_lat, rider_lng, float(driver["lat"]), float(driver["lng"]))
              candidates.append((actual_dist, driver_id, driver))
      
      # Return nearest N
      return sorted(candidates, key=lambda x: x[0])[:10]
  
  WHY H3 IS BETTER THAN SIMPLE REDIS GEO:
    Geographic sharding: each cell is a separate Redis key → distribute across Redis nodes.
    No single hot key for all drivers.
    Natural partitioning: India cells on one Redis cluster, US cells on another.
    Adding new cells: just add new Redis keys. No resharding.
```

---

## STEP 5 — Deep-Dive: Matching Algorithm

```
RIDE REQUEST FLOW:
  def request_ride(rider_id, pickup_lat, pickup_lng, dropoff_lat, dropoff_lng):
      # Step 1: Find available drivers nearby
      candidates = find_nearby_drivers(pickup_lat, pickup_lng, radius_km=5)
      
      if not candidates:
          return {"status": "no_drivers_available"}
      
      # Step 2: Rank candidates
      ranked = rank_drivers(candidates, rider_id)
      
      # Step 3: Offer to best candidate
      trip_id = create_pending_trip(rider_id, pickup, dropoff)
      return offer_ride(ranked[0], trip_id)
  
  def rank_drivers(candidates, rider_id):
      scored = []
      for dist, driver_id, driver in candidates:
          score = (
              -dist * 0.4 +                              # closer = better
              driver["rating"] * 0.3 +                   # higher rating = better
              (1 if driver["car_type"] == rider_pref else 0) * 0.3  # car preference
          )
          scored.append((score, driver_id, driver))
      return sorted(scored, key=lambda x: -x[0])  # highest score first

OFFER AND ACCEPT:
  def offer_ride(driver_id, trip_id):
      # Push offer to driver app via WebSocket or FCM
      websocket.push(driver_id, {
          "type": "ride_offer",
          "trip_id": trip_id,
          "pickup": {...},
          "dropoff": {...},
          "fare_estimate": calculate_fare(...)
      })
      
      # Store offer with 15-second acceptance window
      redis.setex(f"offer:{trip_id}:{driver_id}", 15, "pending")
      
      # Wait for acceptance or timeout
      return wait_for_response(driver_id, trip_id, timeout=15)
  
  def driver_response(driver_id, trip_id, accepted: bool):
      if accepted:
          redis.set(f"trip:{trip_id}:driver", driver_id)
          notify_rider(trip_id, driver_id, "driver_found")
          start_tracking(trip_id, driver_id)
      else:
          # Move to next ranked driver
          next_driver = get_next_candidate(trip_id)
          if next_driver:
              offer_ride(next_driver, trip_id)
          else:
              expand_radius_and_retry(trip_id)

TRIP STATE MACHINE:
  PENDING → (driver offered) → OFFERED → (driver accepts) → DRIVER_ASSIGNED
  → (driver arrives) → DRIVER_ARRIVED → (trip starts) → IN_PROGRESS
  → (trip ends) → COMPLETED → (payment) → PAID
  
  Each state transition: update PostgreSQL trips table + publish Kafka event.
  Event: "trip-state-changed" → {trip_id, old_state, new_state, timestamp}
  Consumers: payment service, notification service, analytics.
```

---

## STEP 6 — Deep-Dive: Surge Pricing

```
GOAL: Increase price when demand > supply in a zone to attract more drivers.

CALCULATION (per geographic zone, every 60 seconds):
  For each H3 cell at resolution 5 (≈city-district size, 252 km²):
    available_drivers = count_available_drivers_in_zone(cell)
    pending_requests  = count_pending_requests_in_zone(cell)
    
    ratio = pending_requests / max(available_drivers, 1)
    
    if ratio >= 3.0:   surge_multiplier = 3.0   # 3× price
    elif ratio >= 2.0: surge_multiplier = 2.0
    elif ratio >= 1.5: surge_multiplier = 1.5
    else:              surge_multiplier = 1.0   # no surge
    
    # Cap at Uber's max surge (varies by region)
    surge_multiplier = min(surge_multiplier, 5.0)
    
    # Store in Redis with 61-second TTL (recalculated every 60s)
    redis.setex(f"surge:{cell}", 61, surge_multiplier)

PRICE CALCULATION:
  def calculate_fare(pickup, dropoff, surge_multiplier):
      distance_km = calculate_distance(pickup, dropoff)
      duration_min = estimate_duration(pickup, dropoff)
      
      base_fare = 2.00
      distance_rate = distance_km * 1.20   # $1.20/km
      time_rate = duration_min * 0.25      # $0.25/min
      
      estimated_fare = (base_fare + distance_rate + time_rate) * surge_multiplier
      return max(estimated_fare, minimum_fare=5.00)

USER NOTIFICATION:
  If surge_multiplier >= 2.0: show warning before confirming ride.
  "Prices are currently 2.3× higher than normal due to high demand. Confirm?"
  User must acknowledge surge before ride is booked.

SURGE ANALYTICS (Kafka):
  Every minute: publish surge data to Kafka.
  Analytics pipeline: correlate surge with events (concerts, rain, rush hour).
  Used to train predictive surge model (pre-surge 15 minutes before event ends).
```

---

## STEP 7 — Real-Time Tracking

```
RIDER SEES DRIVER ON MAP:
  After driver assigned: rider gets driver's location every 5 seconds.

APPROACH: WebSocket streaming.
  Driver app: sends GPS update every 5 seconds.
  Location Service: receives update → publishes to Redis Pub/Sub channel.
  
  Redis Pub/Sub:
    Channel: "trip:tracking:{trip_id}"
    Publisher: Location Service (on each driver update)
    Subscriber: Rider's connection server
    
  Rider's connection server:
    Subscribed to "trip:tracking:{trip_id}" for their active trip.
    Receives driver location → pushes to rider's WebSocket → rider's map updates.
  
  def on_driver_location_update(driver_id, lat, lng):
      trip_id = redis.get(f"driver:{driver_id}:active_trip")
      if trip_id:
          # Update H3 grid (for matching other rides)
          update_h3_grid(driver_id, lat, lng)
          
          # Notify rider via pub/sub
          redis.publish(f"trip:tracking:{trip_id}", json.dumps({
              "driver_lat": lat,
              "driver_lng": lng,
              "heading": heading,
              "eta_minutes": calculate_eta(lat, lng, pickup_lat, pickup_lng)
          }))

ETA CALCULATION:
  Not straight-line distance (as the crow flies).
  Must use road network.
  Google Maps API / Mapbox API → driving duration considering traffic.
  Cache ETA: Redis. Key: "eta:{origin_geohash}:{dest_geohash}" TTL: 2 minutes.
  Same origin/dest cell: reuse cached ETA. Saves API calls.

MAP MATCHING:
  GPS has ±10m accuracy. Driver appears "in buildings" or "off road."
  Map matching: snap GPS point to nearest road segment.
  Algorithm: Hidden Markov Model (HMM) on road network graph.
  Uber open-sourced their map matching library (h3 + routing engine).
```

---

## STEP 8 — Database Schema

```sql
-- Users/Drivers (PostgreSQL)
CREATE TABLE users (
    user_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone        VARCHAR(20) UNIQUE NOT NULL,
    name         TEXT NOT NULL,
    rating       DECIMAL(3,2) DEFAULT 5.00,
    is_driver    BOOLEAN DEFAULT FALSE,
    created_at   TIMESTAMP DEFAULT NOW()
);

-- Trips (Cassandra — high write volume, time-series)
CREATE TABLE trips (
    trip_id       UUID,
    rider_id      UUID,
    driver_id     UUID,
    pickup_lat    DECIMAL,
    pickup_lng    DECIMAL,
    dropoff_lat   DECIMAL,
    dropoff_lng   DECIMAL,
    status        TEXT,    -- PENDING, OFFERED, IN_PROGRESS, COMPLETED, CANCELLED
    fare          DECIMAL,
    surge_multiplier DECIMAL,
    started_at    TIMESTAMP,
    ended_at      TIMESTAMP,
    PRIMARY KEY ((rider_id), trip_id)  -- partition by rider for "my trips" query
) WITH CLUSTERING ORDER BY (trip_id DESC);

-- Also need: index by driver_id for driver's trip history
CREATE INDEX idx_trips_driver ON trips(driver_id);

-- Trip tracking (Cassandra — high write, time-series)
CREATE TABLE trip_tracking (
    trip_id     UUID,
    recorded_at TIMESTAMP,
    lat         DECIMAL,
    lng         DECIMAL,
    speed       DECIMAL,
    PRIMARY KEY ((trip_id), recorded_at)
) WITH CLUSTERING ORDER BY (recorded_at ASC)
  AND default_time_to_live = 2592000;  -- 30 days
```

---

## STEP 9 — Trade-offs

```
TRADE-OFF 1: H3 grid vs Redis GEO
  Redis GEO: simpler, built-in. All drivers in one key → scaling bottleneck.
  H3: separate Redis key per cell → geographic sharding → scales infinitely.
  Decision: H3. At 5M drivers, geographic sharding is necessary.

TRADE-OFF 2: Driver location update frequency (5s vs 1s)
  1s updates: smoother tracking, 5× write load (5M/sec instead of 1M/sec).
  5s updates: slight tracking lag, manageable load.
  Decision: 5 seconds. Users don't notice 5s lag on a map.
  Advanced: on trip start, driver sends every 1s (more frequent for navigation).

TRADE-OFF 3: Sync vs async offer-decline flow
  Sync: wait for driver response before doing anything else.
  Async: send offer, rider sees "finding driver" spinner, system tries others.
  Decision: Async. Sync blocks rider app. Async feels faster even if same duration.

TRADE-OFF 4: Centralized vs decentralized matching
  Centralized Dispatch: global view of all drivers → optimal matching.
  Decentralized: regional matching servers → lower latency locally.
  Decision: Regional (city-level) dispatch servers. Global view within a city.
  Cross-city rides: routed to destination city's dispatch for driver matching there.

TRADE-OFF 5: Real-time surge vs pre-computed surge
  Real-time: accurate, updated every 60 seconds.
  Pre-computed: predict surge using ML (historical data + events calendar).
  Decision: Both. Real-time for current surge. Predictive for "pre-positioning" drivers.
  Uber sends notifications to drivers: "Surge expected near stadium at 10 PM."
```

---

## STEP 10 — Follow-Up Questions

```
Q: "How would you design for multiple vehicle types (UberX, UberBlack, Pool)?"
A: Separate H3 grids per vehicle type: "drivers:cell:{cell}:uberx", "drivers:cell:{cell}:uberblack"
   Matching: filter candidates by vehicle type before ranking.
   UberPool: complex — find riders going same direction. N-SAT problem. Use simplified heuristics.

Q: "How would you add scheduled rides (book for tomorrow)?"
A: Scheduled rides: store in PostgreSQL with future pickup_time.
   Cron job: N minutes before pickup → trigger matching as if real-time request.
   Driver matching: prefer drivers who opted into "scheduled rides" (they know the area).

Q: "How would you handle international expansion?"
A: Multi-region deployment. Each city cluster is mostly self-contained.
   Regional dispatch: Mumbai cluster handles Mumbai rides (no cross-region calls).
   Global: user auth, payments, analytics. These are global services.
   Regulatory: different surge caps, different pricing models, different payment methods.
   Each region can have different maximum surge multiplier.

Q: "How do you detect fraudulent rides?"
A: ML model consuming Kafka events: trip patterns, GPS trajectory, payment data.
   Red flags: GPS zigzag (not following road), no movement (fake trip), 
              driver and rider GPS far apart but trip marked complete.
   Real-time scoring: if fraud_score > threshold → hold payout → manual review.

Q: "How do you handle GPS-denied areas (tunnels, buildings)?"
A: Dead reckoning: use last known GPS + speed + heading to predict position.
   WiFi/cell tower triangulation as backup (less accurate, ~50-200m).
   Map knowledge: "this route goes through a tunnel, expect GPS loss for 2 minutes."
   Smooth the tracking line (Kalman filter) to avoid erratic display.
```


---

## STEP 11 — Deep-Dive: Payment Processing

```
PAYMENT FLOW:
  Trip completes -> calculate final fare -> charge rider -> pay driver.
  This is a financial transaction: must be ACID, idempotent, auditable.

ARCHITECTURE:
  Trip Service (state: COMPLETED) -> publishes Kafka event "trip.completed"
  -> Payment Service consumes -> charges rider -> records payout to driver.

FARE CALCULATION (final):
  def calculate_final_fare(trip):
      # Use ACTUAL distance + duration (from GPS tracking, not estimate)
      actual_distance_km = calculate_from_gps_track(trip.tracking_points)
      actual_duration_min = (trip.ended_at - trip.started_at).seconds / 60
      
      base = 2.00
      distance_cost = actual_distance_km * 1.20
      time_cost = actual_duration_min * 0.25
      surge = trip.surge_multiplier  # locked at trip start (not recalculated)
      
      subtotal = (base + distance_cost + time_cost) * surge
      platform_fee = subtotal * 0.10  # Uber's 10-30% commission
      
      return {
          "rider_charge": max(subtotal, MINIMUM_FARE),
          "driver_payout": subtotal - platform_fee,
          "platform_fee": platform_fee,
          "surge_multiplier": surge
      }

PAYMENT IDEMPOTENCY:
  Network failure: Payment Service crashes after charging rider but before recording.
  On restart: re-processes Kafka event -> charges rider AGAIN. DISASTER.
  
  Solution: idempotency key.
    Idempotency key = trip_id + "_payment_v1" (unique per payment attempt).
    Before charging: check DB: "have I processed this trip's payment?"
    CREATE TABLE payment_idempotency (
        idempotency_key TEXT PRIMARY KEY,
        status TEXT,
        charge_id TEXT,
        processed_at TIMESTAMP
    );
    
    If key exists AND status=COMPLETED: return stored result. Skip charge.
    If key not exists: charge -> store result atomically.
    
    Implementation:
      tx = db.begin()
      result = tx.execute("INSERT INTO payment_idempotency (key, status) VALUES (?, 'PROCESSING')", key)
      if result.rows_affected == 0:
          tx.rollback()
          return get_existing_result(key)  # already processed
      
      charge = stripe.charge(amount, rider_card)  # external call
      tx.execute("UPDATE payment_idempotency SET status='COMPLETED', charge_id=? WHERE key=?", charge.id, key)
      tx.commit()

PAYMENT METHODS:
  Credit/debit card: Stripe/Braintree (handles PCI DSS compliance).
    Uber stores tokenized card (never raw card numbers -> PCI scope reduced).
    Token: "tok_abc123" stored in Uber DB. Actual card: Stripe's vault.
    Charge: Stripe.charge({amount, currency, customer: "cus_xyz"}).
  
  Wallets: Paytm (India), GoPay (SE Asia), etc.
    Direct API integration per country.
    Uber maintains a payment method abstraction layer.
    PaymentMethod.charge(amount) -> routes to correct provider.
  
  Cash: driver collects cash. Uber deducts platform fee from driver's next payout.

DRIVER PAYOUT:
  Drivers paid weekly (batch) or on-demand (Uber Instant Pay).
  Instant Pay: Stripe Treasury or Visa Direct (real-time bank transfer).
  Weekly: standard ACH bank transfer.
  
  Driver earnings tracked in:
    CREATE TABLE driver_earnings (
        driver_id UUID,
        week_start DATE,
        gross_earnings DECIMAL,  -- before Uber commission
        commission DECIMAL,      -- Uber's cut
        net_payout DECIMAL,      -- what driver receives
        status TEXT,             -- PENDING, PROCESSING, PAID
        PRIMARY KEY (driver_id, week_start)
    );
```

---

## STEP 12 — Deep-Dive: Driver and Rider Safety Features

```
SAFETY IS A PRODUCT REQUIREMENT (not just a nice-to-have):
  Emergency button, trip sharing, anonymized phone numbers, driver background checks.
  These require specific system design considerations.

PHONE NUMBER ANONYMIZATION:
  Problem: rider can see driver's phone number -> calls driver directly -> bypasses Uber platform.
  Privacy: driver's personal number exposed to strangers.
  
  Solution: virtual phone number proxy (Twilio Proxy / similar).
    For each trip: allocate a temporary virtual number.
    Rider sees: "+1-415-555-0142" (Twilio proxy, not driver's real number).
    When rider calls this number: Twilio routes to driver's real number.
    Driver sees: rider's virtual number (not their real number either).
    After trip completes: proxy number released. Connection severed.
    
    Implementation:
      On trip start: POST /twilio/proxy/session {participant_1: rider_phone, participant_2: driver_phone}
      Returns: {rider_proxy: "+14155550142", driver_proxy: "+14155550143"}
      Both parties call their respective proxy numbers -> Twilio connects them.
      On trip end: DELETE /twilio/proxy/session/{session_id}

EMERGENCY SOS:
  User presses SOS button in app.
  
  1. Immediately call 911 (or local emergency number) via Twilio.
  2. Send rider's GPS coordinates to emergency services.
  3. Share trip details (driver name, car, license plate) with emergency services.
  4. Notify Uber safety team (on-call PagerDuty alert).
  5. Continuously stream GPS location to Uber safety dashboard.
  
  Safety dashboard: real-time map of all active SOS trips.
  Safety agents: call rider/driver to assess situation.
  
  GPS streaming during SOS:
    Instead of every 5s: update every 1s.
    Location published to Redis Pub/Sub: "safety:trip:{trip_id}".
    Safety dashboard subscribes and shows real-time marker on map.

TRIP SHARING (share your ride):
  User shares trip link with a contact.
  Link: https://r.uber.com/trip/abc123 (short URL to trip share).
  
  Recipient opens link in browser -> sees live map with:
    Driver's car icon moving in real-time.
    Rider's pickup and dropoff locations.
    ETA to destination.
    Driver details: name, photo, car, license plate.
  
  Implementation:
    Trip share page: subscribes to Redis Pub/Sub "trip:tracking:{trip_id}".
    Real-time driver location updates pushed via SSE (Server-Sent Events) to browser.
    SSE (not WebSocket): one-way server-to-browser. Simpler for read-only tracking.
    No auth required for share link (recipient doesn't need Uber account).
    Link expires: 1 hour after trip completes.
    
    Security: trip_id in URL is random UUID (unguessable). Not sequential.
    Additionally: trip share token = HMAC-signed. Tamper-proof.

DRIVER BACKGROUND CHECK INTEGRATION:
  On driver signup: trigger background check with Checkr (background check SaaS).
  Webhook: Checkr calls back when check completes (passes/fails).
  Driver account: status = "BACKGROUND_CHECK_PENDING" until webhook received.
  
  Periodic re-checks: drivers re-checked annually.
  Instant background check trigger: if rider reports safety concern -> immediate Checkr re-check.
```

---

## STEP 13 — Deep-Dive: System Reliability and Fault Tolerance

```
CIRCUIT BREAKER PATTERN:
  Dispatch Service calls Google Maps API for ETA calculation.
  Google Maps goes down -> all Dispatch calls hang -> timeout cascade -> Dispatch down.
  
  Circuit Breaker: wraps external calls.
  States:
    CLOSED (normal): calls go through. Track failures.
    OPEN (degraded): too many failures -> stop calling external. Return fallback.
    HALF-OPEN (recovery): try 1 call -> if success -> CLOSED. If fail -> OPEN.
  
  Configuration:
    Open when: 50% of last 20 calls failed.
    Stay open: 30 seconds.
    Fallback for ETA: use straight-line distance / average speed estimate.
    User sees slightly less accurate ETA (5 min vs 3 min Google Maps ETA). Acceptable.
  
  Libraries: Netflix Hystrix, resilience4j (Java), tenacity (Python).

KAFKA CONSUMER LAG MONITORING:
  Fan-out workers consume from Kafka.
  If workers fall behind (consumer lag grows): fan-out delay grows.
  Rider's tweet visible to followers after minutes instead of seconds.
  (Same problem at Uber: trip state change events delayed.)
  
  Monitoring: Kafka consumer group lag = messages_in_queue - messages_processed.
  Alert: if lag > 10K messages -> PagerDuty alert.
  Fix: autoscale consumers (Kubernetes HPA based on lag metric via KEDA).
  KEDA: Kubernetes Event-Driven Autoscaling. Scales pods based on Kafka lag metric.

GRACEFUL DEGRADATION PLAN:
  If Redis Cluster goes down:
    Location data lost -> can't find nearby drivers.
    Fallback: read driver locations from PostgreSQL (slower but possible).
    Surge prices: use last known surge from local in-memory cache.
    Degraded mode: matching is slower (5-10s instead of < 1s). Uber still functions.
  
  If Cassandra goes down:
    Trip history unavailable.
    In-progress trips: state kept in Redis (ephemeral but fast).
    New trips: accepted and tracked via Redis only.
    After recovery: sync Redis trip state to Cassandra.
    Never lose trip data: Redis AOF persistence + Redis backup to S3 every minute.
  
  If Dispatch Service goes down:
    Riders see "No drivers available" (conservative degradation).
    Driver app: shows map but can't accept new trips.
    Fix: deploy Dispatch in 3 replicas across 3 AZs. Any 1 can handle full load.
    AZ failure: 2 remaining replicas handle load (each sized for 60% of peak).

EXACTLY-ONCE PAYMENT PROCESSING:
  Trip.completed event in Kafka. Payment Service crashes mid-processing.
  Kafka: offset not committed -> event re-delivered -> payment charged twice.
  
  Fix: transactional outbox pattern.
    Payment Service: charge Stripe -> write to payments table AND update offset
    atomically in a DB transaction.
    If crash after Stripe charge but before DB write: Stripe charge is orphaned.
    Recovery: scheduled job scans for orphaned Stripe charges -> reconcile.
    
    Industry standard: two-phase commit (2PC) is too slow across services.
    Preferred: idempotency keys (described in payment deep-dive above) +
              Saga pattern for distributed transaction.

LOAD TESTING STRATEGY:
  Simulate 5M drivers updating location at 1 update/5sec.
  Tool: Locust (Python), k6, or AWS Load Testing.
  Shadow traffic: replay production traffic to staging (same volume, real patterns).
  Chaos Engineering (Netflix Chaos Monkey equivalent):
    Randomly kill Redis nodes in staging -> verify fallback works.
    Randomly delay Kafka messages -> verify fan-out still completes in < 10s.
    Simulate Google Maps API returning 503 -> verify circuit breaker opens.
```


---

## DEEP-DIVE IMPROVEMENT: H3 Geospatial Indexing — The Heart of Uber

```
WHY GEOSPATIAL INDEXING IS THE CORE PROBLEM:
  "Find all drivers within 3km of rider at (28.6139, 77.2090)."
  Naive approach: scan ALL drivers in DB → check each distance. O(N) = too slow for 5M drivers.
  We need spatial indexing: like a B-tree but for 2D space.

H3 HEXAGONAL GRID (what Uber actually uses):
  H3: open-source geospatial indexing system by Uber (MIT license).
  Earth divided into a hierarchy of hexagonal cells at 16 resolution levels.
  
  KEY INSIGHT: Hexagons are better than squares for geospatial search.
    Square grid: corner-to-corner distance (1.41×) > edge-to-edge distance (1×). Uneven.
    Hexagon grid: all neighbors are exactly the same distance from center. Uniform.
    "Find all cells within 1 ring of center" = 6 hexagons (always, regardless of direction).
    Square equivalent: 4 orthogonal + 4 diagonal = neighbors at different distances. Messy.
  
  RESOLUTION LEVELS:
    Level 9 (Uber's main level): each cell ≈ 0.1 km² (100m × 100m roughly).
    Level 9 cell count globally: 98 million hexagons cover entire Earth.
    A single city (Mumbai): ~15,000 level-9 cells.
  
  H3 CELL ID ENCODING:
    Each cell: unique 64-bit integer. Example: 617700169958293503 (decimal) or 0x8928308280fffff (hex).
    This integer encodes: resolution level + longitude + latitude → one number.
    Distance between cells: can compute purely from cell IDs (no coordinate arithmetic needed).
    Finding neighbors: h3.grid_disk(cell_id, k=1) → 6 neighbors in O(1).
    
  DRIVER LOCATION → H3 CELL:
    def get_h3_cell(lat: float, lng: float, resolution: int = 9) -> str:
        return h3.latlng_to_cell(lat, lng, resolution)
    
    driver_lat, driver_lng = 28.6139, 77.2090
    cell = get_h3_cell(driver_lat, driver_lng)
    # cell = "8928308280fffff"
    
    # When driver moves: recompute cell every 5s. If cell changed: update Redis.
    
  FINDING NEARBY DRIVERS — STEP BY STEP:
  
    # Step 1: Get rider's cell
    rider_cell = h3.latlng_to_cell(28.6139, 77.2090, resolution=9)
    
    # Step 2: Get all cells within k rings (k=2 = 2 rings = ~1km radius at level 9)
    nearby_cells = h3.grid_disk(rider_cell, k=2)
    # This returns: 1 + 6 + 12 = 19 hexagons (k=0,1,2 rings)
    # Covering roughly 1km radius. O(1) computation.
    
    # Step 3: Batch Redis query — get all drivers in these cells
    pipeline = redis.pipeline()
    for cell in nearby_cells:
        pipeline.smembers(f"drivers:{cell}")  # Set of driver IDs in this cell
    driver_sets = pipeline.execute()
    
    # Step 4: Union all sets → list of candidate driver IDs
    all_driver_ids = set.union(*[set(s) for s in driver_sets if s])
    
    # Step 5: Get each driver's exact location from Redis Hash
    pipeline = redis.pipeline()
    for driver_id in all_driver_ids:
        pipeline.hgetall(f"driver:{driver_id}")
    driver_locations = pipeline.execute()
    
    # Step 6: Filter by actual distance (precise, within 1km)
    nearby_drivers = []
    for driver_data in driver_locations:
        if not driver_data:
            continue
        driver_lat = float(driver_data[b'lat'])
        driver_lng = float(driver_data[b'lng'])
        distance = haversine(rider_lat, rider_lng, driver_lat, driver_lng)
        if distance <= 1.0:  # within 1km
            nearby_drivers.append({
                **driver_data,
                'distance_km': distance,
                'eta_min': estimate_eta(distance, driver_lat, driver_lng, rider_lat, rider_lng)
            })
    
    # Step 7: Sort by ETA (not just distance — traffic matters)
    nearby_drivers.sort(key=lambda d: d['eta_min'])
    return nearby_drivers

HAVERSINE DISTANCE FORMULA:
  Earth is a sphere. Straight-line distance ignores curvature.
  Haversine: accurate spherical distance.
  
  def haversine(lat1, lon1, lat2, lon2):
      R = 6371  # Earth's radius in km
      phi1, phi2 = math.radians(lat1), math.radians(lat2)
      dphi = math.radians(lat2 - lat1)
      dlam = math.radians(lon2 - lon1)
      
      a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
      return 2*R*math.asin(math.sqrt(a))
  
  Performance: 0.1ms per call. At 150K ride requests/sec: 15M haversine calls/sec.
  Optimization: vectorize with NumPy (batch compute distances for all candidates at once).
    numpy.sqrt, numpy.sin, numpy.arcsin — all vectorized operations on arrays.
    Process 100 driver distances simultaneously: same time as 1. 100× speedup.

DYNAMIC SEARCH RADIUS:
  Problem: at 3am, fewer drivers active. 1km search finds 0 drivers. Fail.
  Solution: expand search radius dynamically.
  
  def find_drivers_with_fallback(rider_lat, rider_lng):
      for radius_rings in [1, 2, 3, 5]:  # 0.5km, 1km, 1.5km, 2.5km at level 9
          cells = h3.grid_disk(rider_cell, k=radius_rings)
          drivers = query_redis_cells(cells)
          if drivers:
              return drivers
      
      return []  # No drivers available in entire city
  
  Radius expansion is fast because it's just more cell lookups.
  Response: "Closest driver is 8 min away" (not "No cars available" if within reasonable distance).
  "No cars available": returned only if all expansions find nothing.

H3 GRANULARITY CHOICE:
  Coarser (level 7, ~5km²): fewer cells → fewer Redis keys → simpler.
    But: "find nearby drivers" includes too large an area → more irrelevant candidates.
  Finer (level 11, ~0.001km²): very precise.
    But: millions of cells in one city → too many Redis keys to query.
  Level 9 (0.1km²): Goldilocks. Used by Uber's production system.
    City of Mumbai: 15,000 cells. Query 37 cells (k=3 rings) = 25% of city. Focused.
```

---

## DEEP-DIVE IMPROVEMENT: Dynamic Surge Pricing Algorithm

```
SURGE PRICING GOAL:
  - Balance supply (drivers) and demand (riders) in real time.
  - High demand, low supply → increase price → some riders postpone → demand reduces.
  - High surge → drivers in adjacent areas move to high-surge zone → supply increases.
  - Equilibrium restored. Surge drops. Market cleared.
  - Result: riders who NEED a ride get one. Drivers earn more. Uber takes commission.

SURGE CALCULATION — REAL ALGORITHM:
  
  Input metrics per H3 cell (computed every 60 seconds):
    active_requests  = rider requests in last 5 minutes in this cell
    available_drivers = drivers in this cell + adjacent cells, not on a trip
    in_progress_trips = trips currently being served from this cell
    
    demand_metric = active_requests / (available_drivers + 1)  # +1 to avoid division by zero
    
    # Historical baseline for comparison:
    baseline_demand = avg demand for this cell, same day of week, same hour, last 4 weeks
    demand_ratio = demand_metric / baseline_demand
  
  Surge multiplier mapping:
    demand_ratio < 0.5: multiplier = 1.0 (no surge — plenty of supply)
    demand_ratio 0.5-1.0: multiplier = 1.0-1.2 (mild surge)
    demand_ratio 1.0-1.5: multiplier = 1.2-1.5 (moderate surge)
    demand_ratio 1.5-2.0: multiplier = 1.5-2.0 (high surge — peak event)
    demand_ratio > 2.0:   multiplier = 2.0-3.0 (extreme surge — concert ending, NYE)
    
    Cap: max multiplier = 3.0 (Uber caps to prevent extreme pricing + regulatory compliance)
    Exception: some markets have regulatory caps (Mumbai: max 2.0× allowed by law)

SURGE MAP ARCHITECTURE:
  
  Every 60 seconds (Surge Service cron job):
    For each city's active H3 cells:
      1. Compute demand metrics from Redis (driver locations + active requests).
      2. Compare to historical baseline (stored in ClickHouse or PostgreSQL).
      3. Calculate surge multiplier (clamp between 1.0 and 3.0).
      4. Update Redis: HSET "surge:{cell_id}" multiplier 1.8 updated_at {now} EX 120
         (expires in 120s — ensures stale surge doesn't persist if job fails)
    
  Rider fare estimation flow:
    GET /estimate?pickup_lat=28.6&pickup_lng=77.2&dropoff_lat=28.7&dropoff_lng=77.3
    1. Compute pickup H3 cell.
    2. Lookup: HGET "surge:{pickup_cell}" multiplier → 1.8
    3. Estimate base fare (distance + time estimate from Google Maps API).
    4. final_fare = base_fare × surge_multiplier × service_fees.
    5. Lock surge multiplier: store in session "trip_estimate:{estimate_id}" for 5 minutes.
       If rider confirms within 5 minutes: guaranteed this surge price.
       After 5 minutes: re-compute (surge may have changed).

SURGE NOTIFICATION TO DRIVERS:
  Goal: inform drivers in low-demand areas about high-demand zones nearby.
  Uber driver app: shows a "heat map" overlay. Brighter = higher surge.
  
  Implementation:
    Surge map data sent to driver app periodically (every 2 minutes, or push on significant change).
    Driver app: renders heat map using H3 cell boundaries + surge multiplier = color intensity.
    H3 provides: h3.cell_to_boundary(cell_id) → list of lat/lng polygon vertices for rendering.
    
    Push strategy: only send heat map to drivers within 10km of high-surge zone.
      Efficiently: query Redis for active drivers in cells adjacent to surge zone.
      Send push notification to these drivers (via FCM) with surge zone details.
    
  Driver behavior:
    Drivers reposition toward surge zones to earn more.
    This increases supply in the surge zone → surge decreases.
    This is the self-healing mechanism of surge pricing.

SURGE PREDICTION (proactive, not reactive):
  Reactive: compute surge when demand spikes. Already 1 minute late.
  Proactive: predict where surge will happen and pre-notify drivers.
  
  Predictive signals:
    Events: concerts, sports games (from Eventbrite, Ticketmaster APIs).
    Weather: heavy rain → demand spikes (from weather APIs).
    Time patterns: Friday 11pm → historically high demand.
    Historical data: same cell, last 20 Fridays at 11pm → demand will be 2.3× baseline.
  
  Pre-surge: 30 minutes before predicted spike, show "Surge expected soon" to nearby drivers.
  This encourages preemptive repositioning → surge is shorter and lower when it actually starts.
  
  Implementation: ClickHouse query.
    SELECT AVG(demand_ratio), STDDEV(demand_ratio)
    FROM cell_demand_history
    WHERE h3_cell = ? AND day_of_week = ? AND hour_bucket = ?
    ORDER BY date DESC LIMIT 20;
    
    If AVG > 1.5 AND next_event IN this cell: trigger pre-surge notification.
```

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

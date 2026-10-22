# CS04: LLD — Uber / Ola (Ride Sharing)
## Every Line Explained | Python + Java + C++ | MAANG Interview Ready

---

> **WHAT WE'RE BUILDING:**
> The core Uber backend — a rider requests a ride, a nearby driver accepts,
> the system matches them, tracks location, and computes the fare.
> This is one of the most common MAANG LLD interviews.

---

## STEP 1 — Requirements & Entities

```
FUNCTIONAL REQUIREMENTS:
  1. Rider registers, requests a ride (from location A to location B)
  2. Driver registers, marks themselves AVAILABLE/BUSY/OFFLINE
  3. System finds nearby available drivers
  4. Match rider ↔ driver (driver accepts/declines)
  5. Track driver location in real-time (GPS updates every 3 seconds)
  6. Calculate ETA and fare estimate before booking
  7. Trip starts → ends → fare calculated
  8. Rider rates driver (1-5 stars), driver rates rider

KEY ENTITIES (every noun = a class):
  Rider          — person requesting a ride
  Driver         — person providing a ride
  Location       — (latitude, longitude) value object
  Vehicle        — car info linked to a driver
  TripRequest    — rider's request with pickup + drop locations
  Trip           — active/completed ride (Driver + Rider + route + fare)
  FareCalculator — computes fare based on distance, time, surge
  MatchingService — finds nearest available drivers for a request
  LocationTracker — real-time driver location store (in-memory grid)
  RatingService   — stores and computes average ratings
```

```
NON-FUNCTIONAL (scale for context):
  Uber: 5M trips/day = 58 trips/sec
  Driver GPS updates: every 3 sec × 2M active drivers = 667K location updates/sec
  Matching latency: < 2 seconds to find and notify driver
```

---

## STEP 2 — Class Diagram

```
[Location] (Value Object)          [Vehicle]
───────────────────────            ─────────
- lat: float                       - id: UUID
- lng: float                       - make: str   (Honda, Toyota)
- timestamp: datetime              - model: str  (City, Innova)
──────────────────────             - plate: str  (MH-01-AB-1234)
+ distance_to(loc): float          - capacity: int
+ to_geohash(): str                - type: VehicleType (SEDAN, SUV, AUTO)

[Rider]                            [Driver]
───────                            ────────
- id: UUID                         - id: UUID
- name: str                        - name: str
- phone: str                       - phone: str
- rating: float (avg)              - rating: float (avg)
- payment_method: PaymentMethod    - vehicle: Vehicle
──────                             - status: DriverStatus (AVAILABLE/BUSY/OFFLINE)
+ request_ride(): TripRequest      - current_location: Location
+ rate_driver(): void              ──────
                                   + update_location(Location): void
[TripRequest]                      + accept_trip(TripRequest): Trip
──────────────                     + decline_trip(): void
- id: UUID                         + complete_trip(): void
- rider: Rider                     + rate_rider(): void
- pickup: Location
- dropoff: Location                [Trip]
- vehicle_type: VehicleType        ──────
- requested_at: datetime           - id: UUID
- status: RequestStatus            - rider: Rider
                                   - driver: Driver
[FareCalculator]                   - pickup: Location
────────────────                   - dropoff: Location
- base_fare: float                 - started_at: datetime
- per_km_rate: float               - ended_at: datetime?
- per_min_rate: float              - fare: float
- surge_multiplier: float          - status: TripStatus
────────────────                   ──────
+ estimate(from, to): FareEstimate + start(): void
+ calculate_final(trip): float     + end(): void
+ get_surge(): float               + get_duration_secs(): int

[MatchingService]                  [LocationTracker]
─────────────────                  ─────────────────
- tracker: LocationTracker         - grid: Dict[geohash → Set[driver_id]]
- drivers: Dict[id→Driver]         - locations: Dict[driver_id → Location]
─────────────────                  ─────────────────
+ find_nearby(loc, n): [Driver]    + update(driver_id, loc): void
+ match(request): Driver?          + get_nearby(loc, radius): [str]

PATTERNS USED:
  Strategy   → FareCalculator (different pricing: standard, premium, surge)
  Observer   → LocationTracker notifies MatchingService when driver enters/exits area
  State      → Driver.status (AVAILABLE → BUSY → AVAILABLE state machine)
  State      → Trip.status (REQUESTED → MATCHED → IN_PROGRESS → COMPLETED)
  Factory    → TripFactory.create_trip() builds a Trip from TripRequest + Driver
  Facade     → UberService wraps all sub-services
  Value Obj  → Location (immutable, computed distance)
```

---

## STEP 3 — Python Implementation (Every Line Explained)

```python
# uber_lld.py
from __future__ import annotations

import uuid          # for generating unique IDs
import math          # for math.sqrt, math.radians, math.sin, math.cos, math.asin (Haversine formula)
import threading     # for thread-safe locks
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional, List, Dict, Tuple, Set


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1: ENUMS — All possible states
# ══════════════════════════════════════════════════════════════════════════════

class DriverStatus(Enum):
    """
    STATE MACHINE for a driver:
    OFFLINE → AVAILABLE → BUSY → AVAILABLE → ...
    
    OFFLINE:    Driver is not working (app closed)
    AVAILABLE:  Driver is looking for rides (can be matched)
    BUSY:       Driver is on a trip (cannot be matched)
    
    WHY ENUM and not a string?
    - Strings allow typos: "avaiable" (misspelled) would silently fail.
    - Enum makes invalid states impossible: DriverStatus.AVAIABLE → AttributeError at code time.
    """
    OFFLINE   = auto()   # auto() = assigns increasing integers automatically (1, 2, 3...)
    AVAILABLE = auto()
    BUSY      = auto()

class TripStatus(Enum):
    """
    STATE MACHINE for a trip:
    REQUESTED → MATCHED → IN_PROGRESS → COMPLETED
                        ↘ CANCELLED
    """
    REQUESTED   = auto()   # Rider sent request, no driver yet
    MATCHED     = auto()   # Driver accepted, on the way to pickup
    IN_PROGRESS = auto()   # Driver picked up rider, en route to destination
    COMPLETED   = auto()   # Rider dropped off, fare charged
    CANCELLED   = auto()   # Either party cancelled

class VehicleType(Enum):
    """What kind of vehicle the rider wants."""
    AUTO  = auto()   # 3-wheeler (like Ola Auto)
    SEDAN = auto()   # Standard car (like Uber Go)
    SUV   = auto()   # Larger car (like Uber XL)

class RequestStatus(Enum):
    PENDING  = auto()   # Waiting for a driver to accept
    ACCEPTED = auto()   # A driver accepted this request
    EXPIRED  = auto()   # No driver found in time


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2: VALUE OBJECTS — Immutable data containers
# ══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Location:
    """
    Immutable GPS coordinate.
    
    frozen=True means: once created, cannot be modified.
    WHY IMMUTABLE?
    - A location is a VALUE, not an entity. "28.6°N, 77.2°E" is just a fact.
    - Like a number: you don't "change" the number 5; you create a new number.
    - Immutability = safe to share across threads (no lock needed — no mutation possible).
    - Can be used as dict key (hashable) because it never changes.
    """
    lat: float   # Latitude: -90 to +90. Positive = North. (Delhi ≈ 28.6)
    lng: float   # Longitude: -180 to +180. Positive = East. (Delhi ≈ 77.2)

    def distance_to(self, other: Location) -> float:
        """
        Haversine formula: calculate distance between two GPS points in km.
        
        WHY HAVERSINE and not simple Euclidean (sqrt(Δlat² + Δlng²))?
        Earth is a sphere, not a flat plane. Near the equator, 1° latitude ≈ 111km
        but 1° longitude ≈ 111km × cos(latitude). At poles, longitude lines converge.
        Haversine accounts for Earth's curvature. Error: < 0.3% vs reality.
        """
        R = 6371  # Earth's radius in km (6371 km is the standard accepted value)
        
        dlat = math.radians(other.lat - self.lat)
        # math.radians() converts degrees to radians (trigonometry functions need radians)
        # Δlat = difference in latitude
        
        dlng = math.radians(other.lng - self.lng)
        # Δlng = difference in longitude
        
        a = (math.sin(dlat/2)**2                      # sin²(Δlat/2)
             + math.cos(math.radians(self.lat))        # cos(lat1)
               * math.cos(math.radians(other.lat))     # × cos(lat2)
               * math.sin(dlng/2)**2)                  # × sin²(Δlng/2)
        # This is the Haversine formula's 'a' component
        
        c = 2 * math.asin(math.sqrt(a))
        # asin = arc sine (inverse of sine). This gives angle in radians.
        # 2 × asin(√a) = central angle between the two points on Earth's surface
        
        return R * c
        # Distance = Earth's radius × central angle
        # Units: km (because R is in km)

    def to_geohash(self, precision: int = 6) -> str:
        """
        Convert location to a Geohash string.
        
        WHAT IS A GEOHASH?
        Geohash encodes latitude + longitude into a short string like "ttnfv2".
        Points near each other have similar geohash prefixes.
        
        WHY GEOHASH FOR UBER?
        Uber needs: "find all available drivers within 5km of this location."
        Geohash divides the world into a grid. Searching nearby = lookup nearby grid cells.
        Without geohash: compare every driver's lat/lng to the rider's → O(N) scan.
        With geohash: find grid cells → O(1) lookup → get all drivers in those cells → filter.
        
        SIMPLIFIED IMPLEMENTATION (real geohash is binary encoded):
        Real geohash uses base32 encoding. We use a simplified version here.
        """
        # Quantize lat/lng to a grid cell
        # precision=6 → cell size ≈ 1.2km × 0.6km (appropriate for Uber matching)
        lat_quantized = round(self.lat, precision - 3)   # Round to N-3 decimal places
        lng_quantized = round(self.lng, precision - 3)
        return f"{lat_quantized:.3f}_{lng_quantized:.3f}"
        # f-string: f"{value:.3f}" formats float with exactly 3 decimal places
        # Result: "28.600_77.200" — identifies a grid cell


@dataclass
class FareEstimate:
    """Result of fare estimation (before trip starts)."""
    base_fare:  float          # Fixed amount charged per trip (e.g., ₹50)
    distance_km: float         # Estimated distance
    estimated_fare: float      # Total estimate
    surge_multiplier: float    # 1.0 = no surge, 2.5 = 2.5× peak pricing
    eta_minutes: int           # How many minutes until driver arrives


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3: DOMAIN ENTITIES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Vehicle:
    """The car a driver uses."""
    id:       str = field(default_factory=lambda: str(uuid.uuid4()))
    make:     str = "Honda"      # Brand: Honda, Toyota, Hyundai
    model:    str = "City"       # Model: City, Innova, i20
    plate:    str = "MH-01-AB-1234"   # License plate
    capacity: int = 4            # Max passengers
    type:     VehicleType = VehicleType.SEDAN


class Driver:
    """
    A driver who provides rides.
    
    STATE MACHINE for status:
    OFFLINE → AVAILABLE (driver goes online)
    AVAILABLE → BUSY (driver accepts a trip)
    BUSY → AVAILABLE (trip completed)
    AVAILABLE → OFFLINE (driver goes offline)
    """

    def __init__(self, name: str, phone: str, vehicle: Vehicle):
        self.id       = str(uuid.uuid4())
        self.name     = name
        self.phone    = phone
        self.vehicle  = vehicle
        self._status  = DriverStatus.OFFLINE     # _ prefix = private by convention
        self._location: Optional[Location] = None
        
        # Ratings: stored as list of individual ratings
        # Average computed on demand (not stored separately to avoid inconsistency)
        self._ratings: List[float] = []
        
        self._lock    = threading.RLock()   # RLock = Reentrant Lock (same thread can re-acquire)

    def go_online(self) -> None:
        """Driver opens the app and becomes available."""
        with self._lock:
            if self._status == DriverStatus.OFFLINE:
                self._status = DriverStatus.AVAILABLE
            # If already AVAILABLE or BUSY, this call is ignored silently

    def go_offline(self) -> None:
        """Driver closes the app."""
        with self._lock:
            if self._status == DriverStatus.BUSY:
                raise ValueError("Cannot go offline during an active trip")
                # Business rule: must complete the trip first
            self._status = DriverStatus.OFFLINE

    def set_busy(self) -> None:
        """Called when driver accepts a trip."""
        with self._lock:
            if self._status != DriverStatus.AVAILABLE:
                raise ValueError(f"Driver not available (status: {self._status.name})")
            self._status = DriverStatus.BUSY

    def set_available(self) -> None:
        """Called when driver completes a trip."""
        with self._lock:
            self._status = DriverStatus.AVAILABLE

    def update_location(self, location: Location) -> None:
        """GPS update from driver's phone (every 3 seconds)."""
        with self._lock:
            self._location = location

    def add_rating(self, stars: float) -> None:
        """Rider rated this driver 1-5 stars."""
        if not (1 <= stars <= 5):
            raise ValueError(f"Rating must be 1-5, got {stars}")
        with self._lock:
            self._ratings.append(stars)

    @property
    def status(self) -> DriverStatus:
        """
        @property: allows calling driver.status instead of driver.status()
        The property makes it look like a field but runs code behind the scenes.
        WHY: Reading status with lock (thread-safe read).
        """
        with self._lock: return self._status

    @property
    def location(self) -> Optional[Location]:
        with self._lock: return self._location

    @property
    def rating(self) -> float:
        """Average of all ratings. Returns 0 if no ratings yet."""
        with self._lock:
            return sum(self._ratings) / len(self._ratings) if self._ratings else 0.0

    def __repr__(self) -> str:
        return f"Driver({self.name}, {self.status.name}, ⭐{self.rating:.1f})"


class Rider:
    """A person requesting a ride."""

    def __init__(self, name: str, phone: str):
        self.id     = str(uuid.uuid4())
        self.name   = name
        self.phone  = phone
        self._ratings: List[float] = []
        self._lock  = threading.Lock()

    def add_rating(self, stars: float) -> None:
        if not (1 <= stars <= 5): raise ValueError("Rating must be 1-5")
        with self._lock:
            self._ratings.append(stars)

    @property
    def rating(self) -> float:
        with self._lock:
            return sum(self._ratings) / len(self._ratings) if self._ratings else 5.0

    def __repr__(self) -> str:
        return f"Rider({self.name})"


class TripRequest:
    """
    A rider's request for a ride.
    Exists from when rider requests until driver is matched.
    Then becomes a Trip.
    """

    def __init__(self, rider: Rider, pickup: Location, dropoff: Location,
                 vehicle_type: VehicleType = VehicleType.SEDAN):
        self.id           = str(uuid.uuid4())
        self.rider        = rider
        self.pickup       = pickup
        self.dropoff      = dropoff
        self.vehicle_type = vehicle_type
        self.requested_at = datetime.utcnow()
        self.status       = RequestStatus.PENDING


class Trip:
    """
    An active or completed ride.
    Created when a driver accepts a TripRequest.
    
    STATE MACHINE:
    (MATCHED) → start() → IN_PROGRESS → end() → COMPLETED
                                              ↘ cancel() → CANCELLED
    """

    def __init__(self, rider: Rider, driver: Driver,
                 pickup: Location, dropoff: Location):
        self.id         = str(uuid.uuid4())
        self.rider      = rider
        self.driver     = driver
        self.pickup     = pickup
        self.dropoff    = dropoff
        self._status    = TripStatus.MATCHED    # Driver accepted → starts as MATCHED
        self.started_at: Optional[datetime] = None
        self.ended_at:   Optional[datetime] = None
        self.fare:       Optional[float]    = None
        self._lock      = threading.Lock()

    def start(self) -> None:
        """Called when driver arrives at pickup and rider gets in."""
        with self._lock:
            if self._status != TripStatus.MATCHED:
                raise ValueError(f"Cannot start trip in status {self._status.name}")
            self._status    = TripStatus.IN_PROGRESS
            self.started_at = datetime.utcnow()

    def end(self, fare: float) -> None:
        """Called when rider reaches destination."""
        with self._lock:
            if self._status != TripStatus.IN_PROGRESS:
                raise ValueError(f"Cannot end trip in status {self._status.name}")
            self._status  = TripStatus.COMPLETED
            self.ended_at = datetime.utcnow()
            self.fare     = fare

    def cancel(self) -> None:
        """Either rider or driver cancels."""
        with self._lock:
            if self._status in (TripStatus.COMPLETED, TripStatus.CANCELLED):
                raise ValueError("Trip already finished")
            self._status = TripStatus.CANCELLED

    def get_duration_seconds(self) -> int:
        """How long the trip took (after ended)."""
        if not self.started_at or not self.ended_at: return 0
        return int((self.ended_at - self.started_at).total_seconds())
        # timedelta.total_seconds() = duration as float of seconds
        # int() = truncate to integer (no fractional seconds)

    @property
    def status(self) -> TripStatus:
        with self._lock: return self._status

    def __repr__(self) -> str:
        return f"Trip({self.rider.name}→{self.driver.name}, {self.status.name})"


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4: FARE CALCULATOR — Strategy Pattern
# ══════════════════════════════════════════════════════════════════════════════

class IFarePricingStrategy(ABC):
    """
    STRATEGY INTERFACE for fare pricing.
    
    WHY STRATEGY?
    Uber has multiple pricing models:
    - StandardPricing: normal weekday pricing
    - SurgePricing: 2-3× during rain, evening rush, New Year's Eve
    - PremiumPricing: Uber Premier / Ola Select (higher base fare, no surge)
    
    Without Strategy: FareCalculator has if/elif/else for each type → messy, hard to extend.
    With Strategy: each pricing model is its own class. FareCalculator just calls calculate().
    Adding a new pricing type = adding a new class, not touching FareCalculator.
    This follows the Open/Closed Principle: open for extension, closed for modification.
    """

    @abstractmethod
    def get_base_fare(self) -> float:
        """Fixed amount charged regardless of distance (covers driver's approach cost)."""
        ...

    @abstractmethod
    def get_per_km_rate(self) -> float:
        """How much is charged per kilometer of the trip."""
        ...

    @abstractmethod
    def get_per_min_rate(self) -> float:
        """How much is charged per minute of the trip (covers traffic jams)."""
        ...

    @abstractmethod
    def get_surge_multiplier(self) -> float:
        """
        How much to multiply the total by.
        1.0 = no surge (normal times).
        2.5 = 2.5× surge (high demand like New Year's Eve).
        """
        ...


class StandardPricing(IFarePricingStrategy):
    """Normal pricing (most trips)."""
    def get_base_fare(self)        -> float: return 50.0    # ₹50 base
    def get_per_km_rate(self)      -> float: return 12.0    # ₹12 per km
    def get_per_min_rate(self)     -> float: return 2.0     # ₹2 per minute
    def get_surge_multiplier(self) -> float: return 1.0     # No surge

class SurgePricing(IFarePricingStrategy):
    """Peak demand pricing (rain, rush hour, events)."""
    def __init__(self, surge_multiplier: float = 2.0):
        self._surge = surge_multiplier

    def get_base_fare(self)        -> float: return 50.0
    def get_per_km_rate(self)      -> float: return 12.0
    def get_per_min_rate(self)     -> float: return 2.0
    def get_surge_multiplier(self) -> float: return self._surge

class PremiumPricing(IFarePricingStrategy):
    """Uber Premier / Ola Select — higher rates, no surge cap."""
    def get_base_fare(self)        -> float: return 100.0   # Higher base
    def get_per_km_rate(self)      -> float: return 20.0    # More per km
    def get_per_min_rate(self)     -> float: return 3.0
    def get_surge_multiplier(self) -> float: return 1.0     # Premium never surges


class FareCalculator:
    """
    Computes fare using the injected pricing strategy.
    
    Note: This class just does math. It doesn't decide WHICH strategy to use.
    The UberService decides that (based on time of day, demand, vehicle type).
    """

    def __init__(self, strategy: IFarePricingStrategy):
        self._strategy = strategy  # Which pricing model to apply

    def set_strategy(self, strategy: IFarePricingStrategy) -> None:
        """Switch pricing model at runtime (e.g., surge kicks in at 6 PM)."""
        self._strategy = strategy

    def estimate(self, pickup: Location, dropoff: Location,
                 avg_speed_kmph: float = 30.0) -> FareEstimate:
        """
        Estimate fare BEFORE the trip starts.
        Uses straight-line distance (faster to compute).
        Actual fare uses GPS-tracked route distance.
        """
        dist_km = pickup.distance_to(dropoff)
        # Direct distance between pickup and dropoff (Haversine formula)
        
        travel_minutes = (dist_km / avg_speed_kmph) * 60
        # Time = Distance / Speed.
        # dist_km / avg_speed_kmph = time in HOURS.
        # × 60 converts hours to MINUTES.
        
        raw_fare = (self._strategy.get_base_fare()
                  + dist_km * self._strategy.get_per_km_rate()
                  + travel_minutes * self._strategy.get_per_min_rate())
        # Total = base + (distance × per_km_rate) + (time × per_min_rate)
        
        total = raw_fare * self._strategy.get_surge_multiplier()
        # Apply surge multiplier at the end (multiplies the TOTAL, not just one component)
        
        return FareEstimate(
            base_fare=self._strategy.get_base_fare(),
            distance_km=round(dist_km, 2),    # Round to 2 decimal places
            estimated_fare=round(total, 2),
            surge_multiplier=self._strategy.get_surge_multiplier(),
            eta_minutes=int(travel_minutes) + 5  # +5 min for driver to arrive at pickup
        )

    def calculate_final(self, trip: Trip, actual_distance_km: float) -> float:
        """
        Calculate ACTUAL fare after trip ends.
        Uses GPS-tracked route (may be longer than straight line due to traffic).
        """
        duration_min = trip.get_duration_seconds() / 60.0
        # Convert seconds to minutes for per_min_rate calculation
        
        raw = (self._strategy.get_base_fare()
             + actual_distance_km * self._strategy.get_per_km_rate()
             + duration_min * self._strategy.get_per_min_rate())
        
        return round(raw * self._strategy.get_surge_multiplier(), 2)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5: LOCATION TRACKER — Geohash-Based Grid
# ══════════════════════════════════════════════════════════════════════════════

class LocationTracker:
    """
    Tracks real-time driver locations using a Geohash grid.
    
    PROBLEM: Finding nearest drivers naively requires checking ALL drivers.
    For 2M drivers: O(2M) comparisons per rider request = way too slow.
    
    SOLUTION: Geohash grid.
    - Divide the world into grid cells (each cell ≈ 1.2km × 0.6km)
    - Store drivers by their grid cell: { geohash: {driver_id_1, driver_id_2, ...} }
    - When a rider requests a ride near "28.600_77.200":
      → Look up that cell AND the 8 surrounding cells
      → Get the small set of driver IDs in those cells
      → Compute exact distance only for those drivers (O(small_number) instead of O(2M))
    
    This is a simplified version of S2 Geometry (what Google Maps and Uber actually use).
    """

    def __init__(self):
        # Grid: geohash string → set of driver IDs in that cell
        # Dict[str, Set[str]]: key is geohash, value is set of driver IDs
        self._grid: Dict[str, Set[str]] = {}
        
        # Direct location store: driver_id → current Location
        # This is the source of truth for exact coordinates
        self._locations: Dict[str, Location] = {}
        
        self._lock = threading.RLock()

    def update(self, driver_id: str, new_location: Location) -> None:
        """
        Called every 3 seconds per driver with their latest GPS coordinate.
        
        WHAT THIS DOES:
        1. Remove driver from their OLD grid cell
        2. Add driver to their NEW grid cell
        3. Update the exact location
        """
        with self._lock:
            old_loc = self._locations.get(driver_id)
            
            if old_loc:
                old_hash = old_loc.to_geohash()       # Which cell was driver in before?
                if old_hash in self._grid:
                    self._grid[old_hash].discard(driver_id)
                    # discard() removes if present, does nothing if not (safe version of remove())
                    if not self._grid[old_hash]:       # Cell is now empty
                        del self._grid[old_hash]       # Remove empty cell to save memory
            
            new_hash = new_location.to_geohash()      # Which cell is driver in now?
            if new_hash not in self._grid:
                self._grid[new_hash] = set()          # Create new cell if it doesn't exist
            self._grid[new_hash].add(driver_id)       # Add driver to new cell
            
            self._locations[driver_id] = new_location # Update exact location

    def get_nearby_driver_ids(self, center: Location, radius_km: float) -> List[str]:
        """
        Find driver IDs in grid cells near the given center location.
        
        SIMPLIFIED APPROACH (real Uber uses S2 library):
        We search the center cell + 8 surrounding cells (3×3 grid).
        Then filter by actual distance.
        
        REAL APPROACH: S2 geometry — spherical geometry library that handles
        the wrap-around at ±180° longitude and the distortion near poles.
        """
        with self._lock:
            nearby_ids = []
            
            # Generate geohashes for center + 8 neighbors
            # In real geohash, neighbors are computed mathematically.
            # Here: we sample nearby lat/lng points to generate their hashes.
            offsets = [-0.01, 0, 0.01]   # ±0.01 degrees ≈ ±1.1 km
            cells_to_check = set()
            
            for dlat in offsets:
                for dlng in offsets:
                    neighbor = Location(center.lat + dlat, center.lng + dlng)
                    cells_to_check.add(neighbor.to_geohash())
            # This generates up to 9 unique geohash cells (3×3 grid around center)
            
            for cell in cells_to_check:
                for driver_id in self._grid.get(cell, set()):
                    # For each driver in this grid cell, check exact distance
                    driver_loc = self._locations.get(driver_id)
                    if driver_loc and driver_loc.distance_to(center) <= radius_km:
                        nearby_ids.append(driver_id)
                        # Only include if within the requested radius
            
            return nearby_ids


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6: MATCHING SERVICE
# ══════════════════════════════════════════════════════════════════════════════

class MatchingService:
    """
    Finds the best available driver for a ride request.
    
    ALGORITHM: Nearest available driver (simplified).
    Real Uber uses a more complex global optimization (minimizes total driver idle time).
    """

    def __init__(self, tracker: LocationTracker, drivers: Dict[str, Driver]):
        self._tracker = tracker     # Location grid to find nearby drivers
        self._drivers = drivers     # All registered drivers (id → Driver)

    def find_best_driver(self, request: TripRequest, search_radius_km: float = 5.0) -> Optional[Driver]:
        """
        Find the nearest AVAILABLE driver who has the right vehicle type.
        
        RETURNS: The best Driver, or None if no one is available.
        """
        nearby_ids = self._tracker.get_nearby_driver_ids(
            request.pickup, search_radius_km
        )
        # Get all driver IDs within radius km of the pickup point

        best_driver: Optional[Driver] = None
        best_distance: float = float('inf')    # Start with infinite distance
        # float('inf') = positive infinity. Any real distance will be smaller.

        for driver_id in nearby_ids:
            driver = self._drivers.get(driver_id)
            if not driver: continue                    # Driver ID not in registry (shouldn't happen)
            if driver.status != DriverStatus.AVAILABLE: continue  # Skip busy/offline drivers
            if driver.vehicle.type != request.vehicle_type: continue  # Wrong vehicle type
            
            driver_loc = driver.location
            if not driver_loc: continue               # Driver has no location yet
            
            distance = driver_loc.distance_to(request.pickup)
            # How far is this driver from the rider's pickup location?
            
            if distance < best_distance:
                best_distance = distance
                best_driver = driver
                # Update best if this driver is closer than the current best

        return best_driver
        # Returns None if no suitable driver found within radius


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7: RATING SERVICE
# ══════════════════════════════════════════════════════════════════════════════

class RatingService:
    """
    Handles ratings between riders and drivers after trip completion.
    Both rider rates driver AND driver rates rider.
    """

    def rate_driver(self, rider: Rider, driver: Driver, trip: Trip,
                    stars: float, comment: str = "") -> None:
        """Rider rates the driver after a completed trip."""
        if trip.status != TripStatus.COMPLETED:
            raise ValueError("Can only rate after trip is completed")
        if trip.rider.id != rider.id:
            raise ValueError("Only the trip's rider can rate")
        driver.add_rating(stars)
        # In production: store (trip_id, rater_id, ratee_id, stars, comment, timestamp)
        # in a Ratings DB table for audit and anti-abuse purposes.

    def rate_rider(self, driver: Driver, rider: Rider, trip: Trip,
                   stars: float) -> None:
        """Driver rates the rider after a completed trip."""
        if trip.status != TripStatus.COMPLETED:
            raise ValueError("Can only rate after trip is completed")
        if trip.driver.id != driver.id:
            raise ValueError("Only the trip's driver can rate")
        rider.add_rating(stars)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8: UBER SERVICE — Facade Pattern
# ══════════════════════════════════════════════════════════════════════════════

class UberService:
    """
    FACADE: Single entry point for the entire Uber backend.
    Hides LocationTracker, MatchingService, FareCalculator, RatingService.
    
    Caller does: uber.request_ride(rider, pickup, dropoff) → TripRequest
    Not: manually create TripRequest, call MatchingService, call LocationTracker...
    """

    def __init__(self):
        self._riders:   Dict[str, Rider]  = {}   # All registered riders
        self._drivers:  Dict[str, Driver] = {}   # All registered drivers
        self._trips:    Dict[str, Trip]   = {}   # All trips (active + completed)
        self._requests: Dict[str, TripRequest] = {}   # Pending requests

        self._tracker  = LocationTracker()       # The GPS grid
        self._matcher  = MatchingService(self._tracker, self._drivers)
        self._fare_calc = FareCalculator(StandardPricing())  # Default: standard pricing
        self._rater    = RatingService()
        
        self._lock = threading.RLock()

    # ── Registration ────────────────────────────────────────────────────────────

    def register_rider(self, name: str, phone: str) -> Rider:
        rider = Rider(name, phone)
        with self._lock:
            self._riders[rider.id] = rider
        return rider

    def register_driver(self, name: str, phone: str, vehicle: Vehicle) -> Driver:
        driver = Driver(name, phone, vehicle)
        with self._lock:
            self._drivers[driver.id] = driver
        return driver

    # ── Driver operations ────────────────────────────────────────────────────────

    def driver_go_online(self, driver: Driver) -> None:
        driver.go_online()
        print(f"✓ {driver.name} is now AVAILABLE")

    def update_driver_location(self, driver: Driver, location: Location) -> None:
        """
        Called every 3 seconds by driver's app.
        Updates GPS grid AND the driver object.
        
        WHY TWO UPDATES?
        - driver.update_location(location): driver object holds current location
        - self._tracker.update(): the grid for fast spatial queries
        Both must be kept in sync.
        """
        driver.update_location(location)
        self._tracker.update(driver.id, location)

    # ── Ride request flow ────────────────────────────────────────────────────────

    def request_ride(self, rider: Rider, pickup: Location, dropoff: Location,
                     vehicle_type: VehicleType = VehicleType.SEDAN) -> Optional[Trip]:
        """
        Main flow: rider asks for a ride.
        Returns Trip if a driver was found, None if no driver available.
        
        FULL FLOW:
        1. Create TripRequest
        2. MatchingService finds nearest available driver
        3. Driver state → BUSY
        4. TripRequest status → ACCEPTED
        5. Create Trip (replaces TripRequest)
        6. Return Trip to caller
        """
        request = TripRequest(rider, pickup, dropoff, vehicle_type)
        with self._lock:
            self._requests[request.id] = request

        # Get fare estimate (shown to rider before confirming)
        estimate = self._fare_calc.estimate(pickup, dropoff)
        print(f"Fare estimate: ₹{estimate.estimated_fare}, ETA: {estimate.eta_minutes} min"
              f", Surge: {estimate.surge_multiplier}×")

        # Find a driver
        driver = self._matcher.find_best_driver(request)
        if not driver:
            print(f"No drivers available near {pickup.lat:.2f},{pickup.lng:.2f}")
            return None

        # Book the driver
        driver.set_busy()                          # Driver is now BUSY (can't be matched)
        request.status = RequestStatus.ACCEPTED    # This request has a driver

        # Create the Trip
        trip = Trip(rider, driver, pickup, dropoff)
        with self._lock:
            self._trips[trip.id] = trip

        print(f"✓ Matched: {rider.name} → {driver.name} ({driver.vehicle.plate})")
        return trip

    def start_trip(self, trip: Trip) -> None:
        """Rider got into the car. Trip begins."""
        trip.start()
        print(f"Trip started: {trip}")

    def end_trip(self, trip: Trip, actual_distance_km: float) -> float:
        """
        Rider reached destination. Trip ends, fare charged.
        
        WHY 'actual_distance_km' is passed in?
        The route GPS tracked during the trip may be longer than the straight-line estimate.
        (Traffic, detours). The actual fare uses GPS-measured route distance.
        """
        fare = self._fare_calc.calculate_final(trip, actual_distance_km)
        trip.end(fare)
        trip.driver.set_available()   # Driver is free for next ride
        print(f"Trip ended: ₹{fare:.2f} charged. Duration: {trip.get_duration_seconds()}s")
        return fare

    def rate(self, rider: Rider, driver: Driver, trip: Trip,
             rider_gives: float, driver_gives: float) -> None:
        """Both parties rate each other."""
        self._rater.rate_driver(rider, driver, trip, rider_gives)
        self._rater.rate_rider(driver, rider, trip, driver_gives)
        print(f"Ratings: {driver.name} ⭐{driver.rating:.1f}, "
              f"{rider.name} ⭐{rider.rating:.1f}")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 9: DEMO
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import time

    uber = UberService()

    # Register users
    alice  = uber.register_rider("Alice", "+91-9000000001")
    raju   = uber.register_driver("Raju", "+91-9800000001",
                                  Vehicle(make="Honda", model="City",
                                          plate="DL-01-AB-1234"))

    # Driver goes online and sends GPS location
    uber.driver_go_online(raju)
    connaught_place = Location(28.6315, 77.2167)   # Connaught Place, New Delhi
    uber.update_driver_location(raju, connaught_place)

    # Rider requests a ride
    india_gate    = Location(28.6129, 77.2295)    # India Gate (pickup)
    airport       = Location(28.5665, 77.1031)    # IGI Airport (dropoff)
    trip = uber.request_ride(alice, india_gate, airport)

    if trip:
        time.sleep(0.1)   # Simulate driver arriving at pickup
        uber.start_trip(trip)

        time.sleep(0.1)   # Simulate driving to destination
        fare = uber.end_trip(trip, actual_distance_km=22.5)   # Actual GPS distance

        uber.rate(alice, raju, trip, rider_gives=4.8, driver_gives=5.0)

    print(f"\nFinal driver rating: {raju.rating:.1f}")
    print(f"Final rider rating:  {alice.rating:.1f}")
```

---

## STEP 4 — Java Implementation (Key Parts with Explanations)

```java
// uber_lld.java — Key Java-specific patterns and concurrency

import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.concurrent.locks.*;

// ── Enums ─────────────────────────────────────────────────────────────────────
enum DriverStatus  { OFFLINE, AVAILABLE, BUSY }
enum TripStatus    { REQUESTED, MATCHED, IN_PROGRESS, COMPLETED, CANCELLED }
enum VehicleType   { AUTO, SEDAN, SUV }
enum RequestStatus { PENDING, ACCEPTED, EXPIRED }

// ── Location (Value Object) ────────────────────────────────────────────────────
record Location(double lat, double lng) {
    // Java 'record': immutable, auto-generates constructor, getters, equals, hashCode.
    // Like Python @dataclass(frozen=True).
    // 'lat' and 'lng' are implicitly final (cannot be changed after construction).

    double distanceTo(Location other) {
        // Haversine formula — same math as Python, just Java syntax
        double R = 6371.0;
        double dlat = Math.toRadians(other.lat() - this.lat());
        double dlng = Math.toRadians(other.lng() - this.lng());
        // Math.toRadians() = same as Python's math.radians()
        double a = Math.sin(dlat/2) * Math.sin(dlat/2)
                 + Math.cos(Math.toRadians(this.lat())) * Math.cos(Math.toRadians(other.lat()))
                 * Math.sin(dlng/2) * Math.sin(dlng/2);
        return R * 2 * Math.asin(Math.sqrt(a));
    }

    String toGeohash() {
        // Simplified geohash: round lat/lng to 3 decimal places
        return String.format("%.3f_%.3f", lat(), lng());
        // String.format("%.3f", x) = format float with 3 decimal places (like Python's f"{x:.3f}")
    }
}

// ── Driver ────────────────────────────────────────────────────────────────────
class Driver {
    private final String id = UUID.randomUUID().toString();
    private final String name, phone;
    private final Vehicle vehicle;

    // volatile: ensures write visibility across threads.
    // Without volatile, one thread's write to status might not be seen by another thread
    // due to CPU cache vs main memory visibility (memory model).
    private volatile DriverStatus status = DriverStatus.OFFLINE;

    // volatile for location because GPS updates come from a background thread
    // and are read by the matching thread
    private volatile Location location = null;

    // AtomicReference<double[]>: atomic update to {sum, count} for ratings
    // Why not just two volatile doubles? Two separate volatiles can be read inconsistently
    // (sum updated, count not yet). AtomicReference updates BOTH atomically.
    private final AtomicReference<double[]> ratingData = new AtomicReference<>(new double[]{0.0, 0.0});
    // ratingData[0] = sum of all ratings, ratingData[1] = count of ratings

    Driver(String name, String phone, Vehicle vehicle) {
        this.name = name; this.phone = phone; this.vehicle = vehicle;
    }

    synchronized void goOnline() {
        // 'synchronized' on an instance method: acquires 'this' object's monitor lock.
        // Only one thread can execute this at a time.
        // Equivalent to Python's: with self._lock:
        if (status == DriverStatus.OFFLINE) status = DriverStatus.AVAILABLE;
    }

    synchronized void setBusy() {
        if (status != DriverStatus.AVAILABLE)
            throw new IllegalStateException("Driver not available: " + status);
        status = DriverStatus.BUSY;
    }

    synchronized void setAvailable() { status = DriverStatus.AVAILABLE; }

    void updateLocation(Location loc) {
        // volatile write: no synchronized needed for single-field update
        location = loc;
        // volatile guarantees: after this write, any thread that subsequently reads
        // 'location' will see this new value (not a stale cached value).
    }

    void addRating(double stars) {
        // Compare-And-Swap (CAS) loop for lock-free rating update:
        // Read current value → compute new value → try to set → if another thread
        // changed it in between, retry. No lock needed!
        double[] current, next;
        do {
            current = ratingData.get();
            // current[0] = sum of ratings, current[1] = count of ratings
            next = new double[]{current[0] + stars, current[1] + 1};
            // Compute what the new array should be
        } while (!ratingData.compareAndSet(current, next));
        // compareAndSet(expected, newValue): if current value == expected, set it to newValue.
        // Returns true if successful, false if another thread changed it.
        // The do-while retries until OUR update succeeds.
        // This is lock-free! No mutex, no blocking.
    }

    double getRating() {
        double[] data = ratingData.get();
        return data[1] == 0 ? 0.0 : data[0] / data[1];
        // If no ratings (count=0), return 0. Otherwise return average.
    }

    DriverStatus getStatus()   { return status; }    // volatile read: always current
    Location     getLocation() { return location; }  // volatile read: always current
    String       getId()       { return id; }
    String       getName()     { return name; }
    Vehicle      getVehicle()  { return vehicle; }
}

// ── Trip ──────────────────────────────────────────────────────────────────────
class Trip {
    private final String id = UUID.randomUUID().toString();
    private final Rider   rider;
    private final Driver  driver;
    private final Location pickup, dropoff;
    private volatile TripStatus status = TripStatus.MATCHED;
    private volatile java.time.Instant startedAt, endedAt;
    private volatile double fare = 0.0;

    Trip(Rider rider, Driver driver, Location pickup, Location dropoff) {
        this.rider = rider; this.driver = driver;
        this.pickup = pickup; this.dropoff = dropoff;
    }

    synchronized void start() {
        if (status != TripStatus.MATCHED)
            throw new IllegalStateException("Cannot start: " + status);
        status = TripStatus.IN_PROGRESS;
        startedAt = java.time.Instant.now();
    }

    synchronized void end(double calculatedFare) {
        if (status != TripStatus.IN_PROGRESS)
            throw new IllegalStateException("Cannot end: " + status);
        status = TripStatus.COMPLETED;
        endedAt = java.time.Instant.now();
        fare = calculatedFare;
    }

    synchronized void cancel() {
        if (status == TripStatus.COMPLETED || status == TripStatus.CANCELLED)
            throw new IllegalStateException("Trip already finished");
        status = TripStatus.CANCELLED;
    }

    long getDurationSeconds() {
        if (startedAt == null || endedAt == null) return 0;
        return endedAt.getEpochSecond() - startedAt.getEpochSecond();
        // getEpochSecond() = Unix timestamp in seconds
    }

    TripStatus getStatus() { return status; }
    Rider    getRider()    { return rider; }
    Driver   getDriver()   { return driver; }
    double   getFare()     { return fare; }
    @Override public String toString() {
        return "Trip(" + rider.getName() + "→" + driver.getName() + ", " + status + ")";
    }
}

// ── Vehicle, Rider, FareEstimate ──────────────────────────────────────────────
record Vehicle(String id, String make, String model, String plate,
               int capacity, VehicleType type) {
    Vehicle(String make, String model, String plate) {
        this(UUID.randomUUID().toString(), make, model, plate, 4, VehicleType.SEDAN);
    }
}

class Rider {
    final String id = UUID.randomUUID().toString();
    final String name;
    private final java.util.concurrent.atomic.AtomicReference<double[]> ratingData
        = new java.util.concurrent.atomic.AtomicReference<>(new double[]{0.0, 0.0});

    Rider(String name) { this.name = name; }
    void addRating(double stars) {
        double[] cur, next;
        do { cur = ratingData.get(); next = new double[]{cur[0]+stars, cur[1]+1}; }
        while (!ratingData.compareAndSet(cur, next));
    }
    double getRating() { double[] d = ratingData.get(); return d[1]==0 ? 5.0 : d[0]/d[1]; }
    String getName() { return name; }
}

record FareEstimate(double baseFare, double distanceKm, double estimatedFare,
                    double surgeMultiplier, int etaMinutes) {}

// ── Pricing Strategy (Strategy Pattern) ───────────────────────────────────────
interface FarePricingStrategy {
    double getBaseFare();
    double getPerKmRate();
    double getPerMinRate();
    double getSurgeMultiplier();
}

record StandardPricing() implements FarePricingStrategy {
    public double getBaseFare()        { return 50.0; }
    public double getPerKmRate()       { return 12.0; }
    public double getPerMinRate()      { return 2.0; }
    public double getSurgeMultiplier() { return 1.0; }
}

class SurgePricing implements FarePricingStrategy {
    private final double surge;
    SurgePricing(double surge) { this.surge = surge; }
    public double getBaseFare()        { return 50.0; }
    public double getPerKmRate()       { return 12.0; }
    public double getPerMinRate()      { return 2.0; }
    public double getSurgeMultiplier() { return surge; }
}

// ── FareCalculator ────────────────────────────────────────────────────────────
class FareCalculator {
    private volatile FarePricingStrategy strategy;
    // volatile: strategy can be swapped by one thread (surge kicks in)
    // while another thread is calculating fares

    FareCalculator(FarePricingStrategy s) { this.strategy = s; }
    void setStrategy(FarePricingStrategy s) { this.strategy = s; }

    FareEstimate estimate(Location pickup, Location dropoff) {
        double distKm = pickup.distanceTo(dropoff);
        double travelMin = (distKm / 30.0) * 60;
        double raw = strategy.getBaseFare()
                   + distKm * strategy.getPerKmRate()
                   + travelMin * strategy.getPerMinRate();
        double total = raw * strategy.getSurgeMultiplier();
        return new FareEstimate(strategy.getBaseFare(),
            Math.round(distKm * 100.0) / 100.0,
            Math.round(total * 100.0) / 100.0,
            strategy.getSurgeMultiplier(),
            (int) travelMin + 5);
    }

    double calculateFinal(Trip trip, double actualDistKm) {
        double durationMin = trip.getDurationSeconds() / 60.0;
        double raw = strategy.getBaseFare()
                   + actualDistKm * strategy.getPerKmRate()
                   + durationMin * strategy.getPerMinRate();
        return Math.round(raw * strategy.getSurgeMultiplier() * 100.0) / 100.0;
    }
}

// ── LocationTracker ────────────────────────────────────────────────────────────
class LocationTracker {
    // ConcurrentHashMap: thread-safe, allows concurrent reads (no lock), fine-grained writes
    private final ConcurrentHashMap<String, Set<String>> grid  = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, Location>   locs   = new ConcurrentHashMap<>();

    void update(String driverId, Location newLoc) {
        Location old = locs.get(driverId);
        if (old != null) {
            // Remove from old geohash cell
            Set<String> oldCell = grid.get(old.toGeohash());
            if (oldCell != null) oldCell.remove(driverId);
        }
        // Add to new geohash cell
        grid.computeIfAbsent(newLoc.toGeohash(),
            k -> ConcurrentHashMap.newKeySet())   // Thread-safe Set
            .add(driverId);
        locs.put(driverId, newLoc);
    }

    List<String> getNearbyDriverIds(Location center, double radiusKm) {
        List<String> result = new ArrayList<>();
        double[] offsets = {-0.01, 0, 0.01};
        Set<String> checkedCells = new HashSet<>();

        for (double dlat : offsets) {
            for (double dlng : offsets) {
                Location neighbor = new Location(center.lat() + dlat, center.lng() + dlng);
                String cellHash = neighbor.toGeohash();
                if (!checkedCells.add(cellHash)) continue;
                // Set.add() returns false if element already present → skip duplicates

                Set<String> cell = grid.get(cellHash);
                if (cell == null) continue;

                for (String driverId : cell) {
                    Location driverLoc = locs.get(driverId);
                    if (driverLoc != null && driverLoc.distanceTo(center) <= radiusKm)
                        result.add(driverId);
                }
            }
        }
        return result;
    }
}

// ── UberService (Facade) ──────────────────────────────────────────────────────
class UberService {
    private final ConcurrentHashMap<String, Rider>  riders  = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, Driver> drivers = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, Trip>   trips   = new ConcurrentHashMap<>();
    private final LocationTracker tracker = new LocationTracker();
    private volatile FarePricingStrategy pricing = new StandardPricing();
    private final FareCalculator fareCalc = new FareCalculator(pricing);

    Rider registerRider(String name)     { var r = new Rider(name); riders.put(r.id, r); return r; }
    Driver registerDriver(String name, Vehicle v) {
        var d = new Driver(name, "+91-9800000001", v); drivers.put(d.getId(), d); return d;
    }

    void updateDriverLocation(Driver d, Location loc) {
        d.updateLocation(loc); tracker.update(d.getId(), loc);
    }

    Optional<Trip> requestRide(Rider rider, Location pickup, Location dropoff) {
        var estimate = fareCalc.estimate(pickup, dropoff);
        System.out.printf("Estimate: ₹%.2f, ETA: %d min%n",
            estimate.estimatedFare(), estimate.etaMinutes());

        // Find nearest available SEDAN driver
        var nearbyIds = tracker.getNearbyDriverIds(pickup, 5.0);
        Driver best = null;
        double bestDist = Double.MAX_VALUE;
        for (String id : nearbyIds) {
            Driver d = drivers.get(id);
            if (d == null || d.getStatus() != DriverStatus.AVAILABLE) continue;
            if (d.getVehicle().type() != VehicleType.SEDAN) continue;
            double dist = d.getLocation().distanceTo(pickup);
            if (dist < bestDist) { bestDist = dist; best = d; }
        }

        if (best == null) { System.out.println("No drivers available"); return Optional.empty(); }

        best.setBusy();
        var trip = new Trip(rider, best, pickup, dropoff);
        trips.put(trip.id, trip);
        System.out.println("Matched: " + rider.getName() + " → " + best.getName());
        return Optional.of(trip);
    }

    double endTrip(Trip trip, double actualKm) {
        double fare = fareCalc.calculateFinal(trip, actualKm);
        trip.end(fare);
        trip.getDriver().setAvailable();
        System.out.printf("Trip ended: ₹%.2f%n", fare);
        return fare;
    }
}
```

---

## STEP 5 — C++ Key Patterns

```cpp
// uber_lld.cpp — C++ specific patterns
#include <iostream>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#include <memory>
#include <mutex>
#include <shared_mutex>
#include <atomic>
#include <optional>
#include <cmath>
#include <limits>

// ── Location (Value Object) ───────────────────────────────────────────────────
struct Location {
    double lat, lng;

    double distanceTo(const Location& other) const {
        // const method: doesn't modify the Location object
        // const reference parameter: doesn't copy, doesn't modify
        constexpr double R = 6371.0;
        // constexpr = compile-time constant (like Java's 'static final')
        double dlat = (other.lat - lat) * M_PI / 180.0;
        double dlng = (other.lng - lng) * M_PI / 180.0;
        // M_PI = π (pi) from <cmath>
        double a = std::sin(dlat/2)*std::sin(dlat/2)
                 + std::cos(lat*M_PI/180)*std::cos(other.lat*M_PI/180)
                 * std::sin(dlng/2)*std::sin(dlng/2);
        return R * 2 * std::asin(std::sqrt(a));
    }

    std::string toGeohash() const {
        char buf[32];
        std::snprintf(buf, sizeof(buf), "%.3f_%.3f", lat, lng);
        // snprintf: safe printf to buffer. sizeof(buf) = max bytes to write.
        // %.3f = float with 3 decimal places.
        return std::string(buf);
    }

    bool operator==(const Location& o) const { return lat == o.lat && lng == o.lng; }
};

// ── DriverStatus State Machine ────────────────────────────────────────────────
enum class DriverStatus { OFFLINE, AVAILABLE, BUSY };
enum class TripStatus   { MATCHED, IN_PROGRESS, COMPLETED, CANCELLED };
enum class VehicleType  { AUTO, SEDAN, SUV };

// ── Driver ────────────────────────────────────────────────────────────────────
class Driver {
    std::string id_, name_;
    std::atomic<DriverStatus> status_{DriverStatus::OFFLINE};
    // std::atomic<DriverStatus>: atomic enum.
    // C++20: atomic can work with enums and other trivially copyable types.
    // Allows lock-free reads/writes of status.

    std::atomic<Location*> location_{nullptr};
    // WHY pointer? Atomic needs fixed-size type. Location is a struct.
    // Alternative: shared_mutex + volatile Location. But atomic<Location*> is simpler.
    // NOTE: in production use atomic<shared_ptr<Location>> (C++20) or a mutex.

    double ratingSum_{0}; double ratingCount_{0};
    mutable std::shared_mutex ratingMtx_;
    // shared_mutex: allows multiple concurrent readers (getRating()) OR one writer (addRating())
    // 'mutable': can be locked even in const methods

    mutable std::mutex statusMtx_;
    // For state transition validation (read-check-write must be atomic)

public:
    explicit Driver(std::string name) : name_(std::move(name)) {
        static std::atomic<int> c{0};
        id_ = "driver_" + std::to_string(++c);
    }

    void goOnline() {
        std::lock_guard lk(statusMtx_);
        // std::lock_guard: RAII lock. Constructor acquires, destructor releases.
        // Equivalent to Java's synchronized block.
        if (status_.load() == DriverStatus::OFFLINE)
            status_.store(DriverStatus::AVAILABLE);
        // .load() = atomic read. .store() = atomic write.
        // Use load/store explicitly with std::memory_order for fine control.
    }

    bool setBusy() {
        std::lock_guard lk(statusMtx_);
        if (status_.load() != DriverStatus::AVAILABLE) return false;
        status_.store(DriverStatus::BUSY);
        return true;
    }

    void setAvailable() { status_.store(DriverStatus::AVAILABLE); }
    // No lock needed here: single atomic write is always safe.

    void updateLocation(Location* loc) {
        // Store new location pointer atomically
        Location* old = location_.exchange(loc);
        // exchange(new_val) = atomically set to new_val, return old value.
        // If old is not null and we own it: delete old; (not shown — use shared_ptr in prod)
    }

    void addRating(double stars) {
        std::unique_lock lk(ratingMtx_);  // Exclusive write lock
        ratingSum_ += stars;
        ratingCount_ += 1;
    }

    double getRating() const {
        std::shared_lock lk(ratingMtx_);  // Shared read lock (concurrent reads OK)
        return ratingCount_ == 0 ? 0.0 : ratingSum_ / ratingCount_;
    }

    DriverStatus getStatus() const { return status_.load(std::memory_order_acquire); }
    // memory_order_acquire: see all writes that happened before the corresponding store/release.
    // Prevents compiler/CPU from reordering reads to before this load.

    Location* getLocation() const { return location_.load(std::memory_order_acquire); }
    const std::string& getId()   const { return id_; }
    const std::string& getName() const { return name_; }
};

// ── LocationTracker ────────────────────────────────────────────────────────────
class LocationTracker {
    // Grid: geohash → set of driver IDs
    std::unordered_map<std::string, std::unordered_set<std::string>> grid_;
    // Location store: driver_id → Location
    std::unordered_map<std::string, Location> locations_;
    mutable std::shared_mutex mtx_;
    // shared_mutex: multiple readers (getNearbyDriverIds) OR one writer (update)

public:
    void update(const std::string& driverId, const Location& newLoc) {
        std::unique_lock lk(mtx_);  // Exclusive write lock
        auto it = locations_.find(driverId);
        if (it != locations_.end()) {
            // Remove from old cell
            std::string oldHash = it->second.toGeohash();
            auto cellIt = grid_.find(oldHash);
            if (cellIt != grid_.end()) {
                cellIt->second.erase(driverId);
                if (cellIt->second.empty()) grid_.erase(cellIt);
            }
        }
        std::string newHash = newLoc.toGeohash();
        grid_[newHash].insert(driverId);    // operator[] creates cell if not exists
        locations_[driverId] = newLoc;
    }

    std::vector<std::string> getNearbyDriverIds(const Location& center, double radiusKm) const {
        std::shared_lock lk(mtx_);  // Shared read lock: concurrent calls OK
        std::vector<std::string> result;
        double offsets[] = {-0.01, 0.0, 0.01};

        std::unordered_set<std::string> checked;
        for (double dlat : offsets) {
            for (double dlng : offsets) {
                Location neighbor{center.lat + dlat, center.lng + dlng};
                std::string cell = neighbor.toGeohash();
                if (!checked.insert(cell).second) continue;
                // set::insert returns {iterator, bool}. bool=false if already existed → skip

                auto it = grid_.find(cell);
                if (it == grid_.end()) continue;

                for (const auto& id : it->second) {
                    auto locIt = locations_.find(id);
                    if (locIt != locations_.end()
                        && locIt->second.distanceTo(center) <= radiusKm)
                        result.push_back(id);
                }
            }
        }
        return result;
    }
};

// ── FarePricingStrategy (Strategy Pattern) ─────────────────────────────────────
class IFarePricingStrategy {
public:
    virtual ~IFarePricingStrategy() = default;
    virtual double getBaseFare()        const = 0;
    virtual double getPerKmRate()       const = 0;
    virtual double getPerMinRate()      const = 0;
    virtual double getSurgeMultiplier() const = 0;
};

class StandardPricing : public IFarePricingStrategy {
public:
    double getBaseFare()        const override { return 50.0; }
    double getPerKmRate()       const override { return 12.0; }
    double getPerMinRate()      const override { return 2.0; }
    double getSurgeMultiplier() const override { return 1.0; }
};

class SurgePricing : public IFarePricingStrategy {
    double surge_;
public:
    explicit SurgePricing(double s) : surge_(s) {}
    double getBaseFare()        const override { return 50.0; }
    double getPerKmRate()       const override { return 12.0; }
    double getPerMinRate()      const override { return 2.0; }
    double getSurgeMultiplier() const override { return surge_; }
};

// ── FareCalculator ────────────────────────────────────────────────────────────
class FareCalculator {
    // shared_ptr: multiple owners (UberService and possibly others)
    std::shared_ptr<IFarePricingStrategy> strategy_;
    mutable std::shared_mutex mtx_;

public:
    explicit FareCalculator(std::shared_ptr<IFarePricingStrategy> s)
        : strategy_(std::move(s)) {}

    void setStrategy(std::shared_ptr<IFarePricingStrategy> s) {
        std::unique_lock lk(mtx_);    // Exclusive write: swapping strategy
        strategy_ = std::move(s);
    }

    double estimate(const Location& pickup, const Location& dropoff) const {
        std::shared_lock lk(mtx_);    // Shared read: many threads can estimate simultaneously
        double distKm = pickup.distanceTo(dropoff);
        double travelMin = (distKm / 30.0) * 60;
        double raw = strategy_->getBaseFare()
                   + distKm * strategy_->getPerKmRate()
                   + travelMin * strategy_->getPerMinRate();
        return raw * strategy_->getSurgeMultiplier();
    }
};
```

---

## STEP 6 — Trade-offs (Explained)

```
TRADE-OFF 1: Geohash grid vs K-D Tree for spatial search
  Geohash: O(1) lookup per cell. Simple to implement. Works well for uniform distribution.
           Problem: Cell boundaries can separate two nearby points into different cells.
           Solution: Always check 3×3 grid (9 cells) around the target point.
  
  K-D Tree: Binary search tree in 2D space. O(log N) nearest-neighbor search.
            Better for non-uniform distributions (e.g., more drivers in cities).
            More complex to implement with concurrent updates.
  
  Uber actually uses: S2 Geometry (Google's library) — spherical geometry cells
  that don't have the edge-problem of flat-grid geohashes.
  
  For interview: Geohash with 3×3 search is the right answer. Show you know S2 exists.

TRADE-OFF 2: Atomic<DriverStatus> vs synchronized status block
  Java:
    volatile DriverStatus: single reads/writes are atomic. But read-check-write is NOT.
    Problem: thread A reads AVAILABLE → thread B reads AVAILABLE → both try setBusy().
    Solution: synchronized(this) on setBusy() ensures read-check-write is atomic.
  
  C++:
    atomic<DriverStatus>: atomic reads/writes. But goOnline() is still read-check-write.
    Add std::mutex for the state TRANSITION check (goOnline, setBusy).
    Single atomic reads (getStatus) need no lock.

TRADE-OFF 3: AtomicReference CAS for ratings (Java)
  Problem: ratingSum++ and ratingCount++ together are not atomic.
  If two threads call addRating simultaneously: both read same old values → one update lost.
  
  Solution 1: synchronized — simple but blocks all concurrent rating calls.
  Solution 2: AtomicReference<double[]> with CAS loop — lock-free, no blocking.
  
  CAS: If the value hasn't changed since we read it, set the new value. If it has, retry.
  In practice: ratings are infrequent. CAS loops rarely retry. Both solutions are fine.

TRADE-OFF 4: Pull model (find driver on request) vs Push model (pre-assign drivers)
  Pull (what we built): On request, scan nearby drivers → find best → assign.
  Pro: No wasted pre-assignments. Simple.
  Con: Latency: scanning can take 100ms under load.
  
  Push (Uber's actual system): Pre-compute "supply zones" with idle drivers.
  Demand prediction → pre-position drivers near busy areas.
  When request comes: already know which driver to offer → faster matching.
  Con: Complex demand prediction model. Wrong prediction = driver in wrong area.

TRADE-OFF 5: Real-time fare vs upfront fare
  Real-time fare: calculated at trip end using actual GPS distance + duration.
  Fair but rider doesn't know how much they'll pay before booking.
  
  Upfront fare (Uber's actual): estimated at request time, locked in.
  Rider knows exactly what they'll pay. Better UX. Driver paid separately (may differ).
  Implementation: same FareCalculator.estimate() result is locked as the billing fare.
```

---

## STEP 7 — Interview Follow-Ups

```
Q: "How does Uber handle surge pricing?"
A: Demand vs supply ratio per geohash zone.
   demand = open TripRequests in zone in last 5 minutes
   supply = AVAILABLE drivers in same zone
   surge = f(demand / supply). Threshold: ratio > 2.0 → 1.5×, > 3.0 → 2.0×, etc.
   FareCalculator.setStrategy(new SurgePricing(multiplier)) — Strategy Pattern!
   Surge is recalculated every 30 seconds per zone.

Q: "How do you handle 667K GPS location updates per second?"
A: GPS updates: batch-write to Redis (driver_id → location as sorted set by geohash).
   Write throughput: Redis can handle ~500K writes/sec per node.
   Horizontal: shard by driver_id % N_shards. 4 shards → 167K/sec each. Feasible.
   MatchingService reads from Redis (not in-memory map): consistent cross-server.
   In LLD: our LocationTracker is in-memory (single-server model). OK for interview.

Q: "How do you handle a driver and rider being matched but driver cancels?"
A: Trip.cancel() → driver.setAvailable() (so driver can be matched again).
   MatchingService re-runs for the same TripRequest (with updated request.status = PENDING).
   Limit: rider can receive max 3 consecutive cancellations before showing "no driver" error.
   Anti-cancellation: driver gets penalty for > 10% cancellation rate (monitored).

Q: "How does payment integration fit in?"
A: PaymentService (separate microservice / class).
   After trip.end(): PaymentService.charge(rider.paymentMethod, fare).
   Retry logic: if charge fails, retry 3× with exponential backoff. 
   Rider gets notification of charge. Driver gets commission (fare × 0.8).
   PaymentService is a separate concern → doesn't belong in UberService (SRP).

Q: "How would you add UberPool (shared rides)?"
A: UberPool is a new VehicleType = VehicleType.POOL.
   PoolTripRequest has a route: pickup → waypoint1 → waypoint2 → destination.
   PoolMatchingService matches multiple riders to one driver going the same direction.
   New class: PoolTrip extends Trip (adds waypoints list, multiple riders).
   FareCalculator: PoolPricing implements IFarePricingStrategy (lower per-km, no surge cap).
   No changes to Driver, Location, LocationTracker — Open/Closed Principle preserved.
```


---

## STEP 8 — Extended Deep-Dives: Advanced Design Patterns in Practice

```
CONCURRENT ACCESS PATTERNS — THE SUBTLETIES:

  WHY ConcurrentHashMap.newKeySet() in Java:
    Set<String> followers = new HashSet<>();  // NOT thread-safe
    Thread A: followers.add("alice");
    Thread B: followers.add("bob");
    Result: potential data corruption. HashSet.add() is NOT atomic.
    
    Set<String> followers = ConcurrentHashMap.newKeySet();  // thread-safe
    Internally: ConcurrentHashMap<String, Boolean>. All operations atomic.
    Why not Collections.synchronizedSet()?
      synchronizedSet wraps with synchronized block.
      add() and remove(): one thread at a time. Works but LOW THROUGHPUT.
      ConcurrentHashMap.newKeySet(): lock-free reads via CAS (Compare-And-Swap).
      Much higher throughput for read-heavy access (followers list is read very often).
  
  THE READ-WRITE LOCK PATTERN (Java ReentrantReadWriteLock):
    Scenario: followers list accessed thousands of times per second for reads.
    Writing (follow/unfollow): rare (maybe 100 times/day for average user).
    
    synchronized(lock): allows ONLY ONE thread at a time — both reads AND writes exclusive.
    ReadWriteLock: multiple readers simultaneously. Only one writer at a time.
    
    private final ReadWriteLock lock = new ReentrantReadWriteLock();
    
    // Read: acquire read lock (multiple threads can hold read lock simultaneously)
    public int getFollowerCount() {
        lock.readLock().lock();
        try {
            return followers.size();  // can be read by 1000 threads simultaneously
        } finally {
            lock.readLock().unlock();
        }
    }
    
    // Write: acquire write lock (exclusive — waits for all readers to finish)
    public boolean follow(User target) {
        lock.writeLock().lock();
        try {
            return following.add(target.getId());
        } finally {
            lock.writeLock().unlock();
        }
    }
    
    Performance gain: 100× read throughput vs plain synchronized.
    Read-heavy workload (99% reads, 1% writes) → ReadWriteLock is dramatically faster.
    
    When NOT to use ReadWriteLock:
      Write-heavy workloads: write lock contention → worse than synchronized.
      Very short critical sections: overhead of RWLock > benefit.
      Rule of thumb: reads > 10× writes → ReadWriteLock wins.

ATOMIC OPERATIONS IN JAVA — WHEN TO USE WHAT:
  
  AtomicInteger vs volatile vs synchronized:
  
  volatile int counter = 0;
  counter++;  // NOT thread-safe! Three operations: read, increment, write.
  // Thread A reads 5, Thread B reads 5, A writes 6, B writes 6. Incremented ONCE. Wrong.
  
  AtomicInteger counter = new AtomicInteger(0);
  counter.incrementAndGet();  // THREAD-SAFE. Single atomic hardware instruction (LOCK ADD).
  
  int count = counter.get();  // Thread-safe read.
  counter.compareAndSet(expected, newValue);  // CAS: only updates if current == expected.
  
  When to use AtomicInteger:
    Single-field counter that only increments/decrements.
    Like: clickCount, likeCount, retryCount.
  
  When AtomicInteger is NOT enough:
    Need to update TWO related fields atomically.
    E.g., "transfer $100: decrease account A, increase account B" — need synchronized.
    AtomicInteger: each field is atomic, but the COMBINATION isn't. Race condition possible.
    Fix: synchronized block covering BOTH updates, or compare-and-swap loop.

IMMUTABILITY AS A CONCURRENCY TOOL:
  
  Location is a frozen dataclass (Python) / Java record.
  Immutable = no setters = shared freely between threads without locking.
  
  Why immutability is the BEST concurrency solution:
    No mutation → no race condition possible → no locks needed → faster.
  
  Make as many objects immutable as possible:
    All "value objects" (Location, MediaMeta, UrlEntry): immutable. ✓
    All "service objects" (UrlShortener, FeedService): mutable (have state). Use locks.
  
  In Java: use records (Java 16+) for immutable value objects.
  In C++: use const member variables + no setters.
  In Python: use @dataclass(frozen=True).
```

---

## STEP 9 — System Design Upgrade Paths

```
HOW THIS LLD EVOLVES TO PRODUCTION:

LEVEL 1: Single Process (current LLD)
  InMemoryRepository: dict in RAM.
  LRUCache: OrderedDict in process.
  Single thread or very limited concurrency.
  Scale: up to 100K entries. Suitable for demo.

LEVEL 2: Single Machine, Multiple Threads
  Replace dict with PostgreSQL + connection pool (psycopg2/asyncpg).
  Replace LRUCache with Redis (redisio library).
  Uvicorn/Gunicorn: 4 workers × 8 threads = 32 concurrent request handlers.
  Scale: millions of entries, thousands requests/sec.
  Code change: only change what gets INJECTED (Strategy Pattern saves us).
    repo = PostgresUrlRepository(db_pool)  # one line change
    cache = RedisCacheLayer(redis_client)  # one line change
    shortener = UrlShortener(repo, cache)  # zero changes to this class

LEVEL 3: Multi-Machine (Microservices)
  UrlShortener → ShortenService (containerized, stateless, scale horizontally).
  RedirectService → RedirectService (separate container, optimized for reads).
  PostgreSQL → PostgreSQL cluster (1 primary + 3 read replicas + Pgpool-II load balancer).
  Redis → Redis Cluster (6 nodes, 3 primary + 3 replica).
  API Gateway → Kong (handles auth, rate limiting, routing).
  Scale: millions of requests/sec. 99.99% availability.

LEVEL 4: Global Scale (bit.ly / TinyURL scale)
  Database → sharded PostgreSQL (10 shards × consistent hashing).
  CDN → Cloudflare (redirects served at CDN edge, < 5ms globally).
  Analytics → ClickHouse (50B click events/day, < 1s aggregation queries).
  Multi-region → US + EU + APAC (3 regions × full stack).
  Scale: 100M URLs, 10B redirects/day. < 10ms p99 globally.
  Code changes: none to core business logic. Only infra config changes.
  The LLD design held up to 100,000× scale increase. This is the power of good OOP design.

INTERVIEW TIP — HOW TO TRANSITION FROM LLD TO HLD:
  After showing LLD code, interviewer asks "how would this scale?"
  
  1. Identify the bottleneck (InMemoryRepository can't handle 578K reads/sec).
  2. Replace the specific component (not the entire system):
     "I'd replace InMemoryUrlRepository with a sharded PostgreSQL repository.
     The IUrlRepository interface means UrlShortener doesn't change at all."
  3. Discuss the HLD implications (sharding, caching, CDN) in terms of your LLD design.
  4. Show you understand the PROGRESSION from clean OOP to distributed systems.
  
  This answer demonstrates: LLD mastery + HLD thinking + evolutionary design mindset.
  MAANG interviewers specifically look for this progression.
```

# CS10: LLD — MakeMyTrip / Booking.com
## Travel Booking Platform | Every Line Explained | Python + Java + C++

---

> **WHAT WE'RE BUILDING:**
> A travel booking platform like MakeMyTrip or Booking.com.
> Users search for flights/hotels, book them, manage reservations.
> This is a classic inventory + booking + payment problem.
>
> **THE CORE CHALLENGE:**
> Inventory is limited (Seat 12A on IndiGo 6E-123 exists exactly ONCE).
> Two users searching simultaneously → both see the seat → only one can book.
> This requires distributed locking or atomic DB transactions.

---

## STEP 1 — Requirements & Entities

```
FUNCTIONAL REQUIREMENTS:
  FLIGHTS:
  1. Search flights by origin, destination, date, passengers, class
  2. Filter/sort: price, duration, stops, airline
  3. Book flight: select seats, provide passenger details
  4. Payment: redirect to payment gateway
  5. E-ticket: email confirmation with PNR
  6. Cancellation: full/partial refund based on timing
  7. Seat selection and upgrade
  
  HOTELS:
  1. Search hotels by city/location, check-in/out dates, guests, room type
  2. Filter: price, rating, amenities, distance
  3. Book room: guest details, special requests
  4. Cancellation policy (free until N days before check-in, penalty after)
  
  COMMON:
  1. User registration and login
  2. Saved travelers (family member profiles)
  3. Price alerts (notify when price drops)
  4. Booking history
  5. Reviews and ratings for hotels

KEY ENTITIES:
  User            — registered traveler
  SavedTraveler   — family member profile (child, spouse)
  Airport         — location with IATA code (DEL, BOM, LHR)
  Airline         — IndiGo, Air India, Emirates
  Flight          — a scheduled flight with inventory
  FlightClass     — ECONOMY, BUSINESS, FIRST_CLASS
  Seat            — individual seat on a flight (12A, 15F)
  FlightInventory — available seats per class (cached count for search speed)
  FlightBooking   — a confirmed flight reservation
  Passenger       — traveler on a specific booking (from User or SavedTraveler)
  
  Hotel           — property listing
  Room            — a specific room type at a hotel
  RoomInventory   — available rooms per type per date range
  HotelBooking    — a confirmed hotel reservation
  
  SearchService   — finds available flights / hotels
  BookingService  — creates and manages bookings
  PricingService  — calculates prices with dynamic pricing
  InventoryService — manages seat/room availability (prevents double booking)
  NotificationService — email/SMS confirmations
  
NON-FUNCTIONAL:
  Search: < 2 seconds for flight search results
  Booking: idempotent (retry-safe), < 5 seconds to confirm
  Overbooking: ZERO tolerance — never sell seat that doesn't exist
  Scale: 10M searches/day, 100K bookings/day
```

---

## STEP 2 — Class Diagram

```
[Airport]                     [Airline]                  [FlightClass]
─────────                     ────────                   ────────────
- code: str ("DEL")           - code: str ("6E")         ECONOMY
- name: str                   - name: str ("IndiGo")     BUSINESS
- city: str                   - logo_url: str            FIRST_CLASS
- country: str
- timezone: str               [Seat]                     [SeatStatus]
                              ──────                     ────────────
[Flight]                      - seat_number: str ("12A") AVAILABLE
────────                      - row: int (12)            BOOKED
- id: UUID                    - col: str ("A")           BLOCKED (held for 10min)
- flight_number: str          - type: SeatType           UNAVAILABLE
- airline: Airline            - class: FlightClass
- origin: Airport             - flight: Flight           [SeatType]
- destination: Airport                                   WINDOW / MIDDLE / AISLE
- departure: datetime         [FlightInventory]
- arrival: datetime           ────────────────
- aircraft_type: str          - flight: Flight
- status: FlightStatus        - class: FlightClass
────────                      - total_seats: int
+ get_duration(): timedelta   - available_seats: int
+ get_fare(class): Money      - blocked_seats: int
+ is_full(class): bool        ────────────────
                              + block(n): bool    ← atomic!
[FlightBooking]               + confirm(n): void
───────────────               + release(n): void
- id: UUID
- pnr: str (6-char alphanum)  [Hotel]
- user: User                  ───────
- flight: Flight              - id: UUID
- passengers: List[Passenger] - name: str
- seats: List[Seat]           - city: str
- class: FlightClass          - address: str
- status: BookingStatus       - star_rating: int (1-5)
- total_fare: Money           - amenities: List[str]
- booked_at: datetime         - check_in_time: time
- hold_expires_at: datetime   - check_out_time: time
───────────────               - rating: float (avg guest)
+ generate_pnr(): str
+ cancel(): RefundDetails     [Room]
                              ──────
[HotelBooking]                - id: UUID
──────────────                - hotel: Hotel
- id: UUID                    - room_type: RoomType (SINGLE/DOUBLE/SUITE)
- user: User                  - max_guests: int
- hotel: Hotel                - base_price_per_night: Money
- room: Room                  - amenities: List[str]
- guests: List[Guest]         - floor: int
- check_in: date              - view: str (sea view, city view)
- check_out: date
- status: BookingStatus       [RoomInventory]
- total_price: Money          ─────────────
- cancellation_policy: CancellationPolicy  - room: Room
                              - date: date
                              - is_available: bool
                              - is_blocked: bool

PATTERNS:
  Strategy  → CancellationPolicy (flexible, moderate, strict)
  Strategy  → PricingStrategy (baseFare, dynamic surge, corporate discount)
  Template  → BookingService.book() skeleton, flight/hotel subtypes differ
  Observer  → PriceAlert (notifies user when price drops below threshold)
  State     → FlightBooking.status (HELD→CONFIRMED→CANCELLED/COMPLETED)
  Factory   → BookingFactory.create(type, data) → FlightBooking or HotelBooking
  Repository → FlightRepository, HotelRepository (decoupled from storage)
```

---

## STEP 3 — Python Implementation (Every Line Explained)

```python
# makemytrip_lld.py
from __future__ import annotations

import uuid
import random
import string
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, time
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum, auto
from typing import Optional, List, Dict, Set, Tuple


# ══════════════════════════════════════════════════════════════════════════════
# ENUMS
# ══════════════════════════════════════════════════════════════════════════════

class FlightClass(Enum):
    ECONOMY      = "economy"
    BUSINESS     = "business"
    FIRST_CLASS  = "first_class"

class SeatType(Enum):
    WINDOW = "window"   # A or F column
    MIDDLE = "middle"   # B, E column
    AISLE  = "aisle"    # C or D column (easy to get out)

class SeatStatus(Enum):
    AVAILABLE   = "available"
    BLOCKED     = "blocked"    # Temporarily held (10 min hold during booking)
    BOOKED      = "booked"     # Confirmed booking
    UNAVAILABLE = "unavailable" # Broken seat, emergency exit no-book, etc.

class FlightStatus(Enum):
    SCHEDULED   = "scheduled"    # Future flight, normal
    DELAYED     = "delayed"      # Departure pushed back
    CANCELLED   = "cancelled"    # Flight cancelled
    BOARDING    = "boarding"      # Now boarding at gate
    IN_FLIGHT   = "in_flight"    # Currently airborne
    LANDED      = "landed"       # Arrived at destination
    DIVERTED    = "diverted"     # Redirected to different airport

class BookingStatus(Enum):
    HELD        = "held"         # Inventory blocked, payment pending
    CONFIRMED   = "confirmed"    # Payment done, booking confirmed
    CANCELLED   = "cancelled"    # User or airline cancelled
    COMPLETED   = "completed"    # Trip finished, customer has flown

class RoomType(Enum):
    SINGLE    = "single"     # 1 person
    DOUBLE    = "double"     # 2 persons, 1 bed
    TWIN      = "twin"       # 2 persons, 2 beds
    SUITE     = "suite"      # Large luxury room
    DELUXE    = "deluxe"     # Premium room

class CancellationPolicyType(Enum):
    FLEXIBLE   = "flexible"    # Full refund until 24 hours before
    MODERATE   = "moderate"    # Full refund until 5 days before
    STRICT     = "strict"      # 50% refund 7 days before, none after
    NON_REFUNDABLE = "non_refundable"   # No refund at all


# ══════════════════════════════════════════════════════════════════════════════
# VALUE OBJECTS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Airport:
    """
    Immutable airport data.
    IATA code uniquely identifies each airport worldwide.
    e.g., DEL = Indira Gandhi International, BOM = Chhatrapati Shivaji
    """
    code: str      # 3-letter IATA code: "DEL", "BOM", "LHR"
    name: str      # Full name: "Indira Gandhi International Airport"
    city: str      # City it serves: "New Delhi"
    country: str   # Country code: "IN", "GB"
    timezone: str  # IANA timezone: "Asia/Kolkata", "Europe/London"

    def __eq__(self, other) -> bool:
        """Two airports are the same if they have the same IATA code."""
        return isinstance(other, Airport) and self.code == other.code

    def __hash__(self) -> int:
        """Allow Airport to be used as dict key or in sets."""
        return hash(self.code)   # Hash is based on IATA code only


@dataclass(frozen=True)
class Airline:
    code: str   # ICAO code: "6E" (IndiGo), "AI" (Air India), "EK" (Emirates)
    name: str
    logo_url: str = ""


@dataclass
class RefundDetails:
    """Result of a cancellation request."""
    booking_id:    str
    refund_amount: Decimal
    refund_percent: float   # 0-100%
    refund_reason: str
    processed_at:  datetime = field(default_factory=datetime.utcnow)


# ══════════════════════════════════════════════════════════════════════════════
# CANCELLATION POLICY — Strategy Pattern
# ══════════════════════════════════════════════════════════════════════════════

class ICancellationPolicy(ABC):
    """
    STRATEGY PATTERN for cancellation refund rules.
    
    WHY STRATEGY?
    Hotels have different cancellation policies for different rate plans:
    - Book flexible rate (more expensive): free cancellation
    - Book non-refundable rate (cheaper): no refund
    - Book moderate rate: partial refund
    
    Without Strategy: giant if/elif in HotelBooking.cancel(). Hard to add new policy types.
    With Strategy: each policy is its own class. HotelBooking just calls policy.calculate_refund().
    """

    @abstractmethod
    def calculate_refund(self, total_paid: Decimal,
                         check_in: date, cancelled_at: datetime) -> Tuple[Decimal, str]:
        """
        Returns: (refund_amount, explanation)
        refund_amount: how much money to return to customer (₹)
        explanation: "Full refund - cancelled 8 days before check-in"
        """
        ...


class FlexiblePolicy(ICancellationPolicy):
    """
    Full refund if cancelled at least 24 hours before check-in.
    No refund within 24 hours.
    """

    def calculate_refund(self, total_paid: Decimal,
                         check_in: date, cancelled_at: datetime) -> Tuple[Decimal, str]:
        check_in_dt  = datetime.combine(check_in, time(14, 0))
        # datetime.combine: create a datetime from a date + time.
        # check_in = date(2025, 12, 25). time(14, 0) = 2:00 PM.
        # Result: "2025-12-25 14:00:00" (standard hotel check-in time)

        hours_before = (check_in_dt - cancelled_at).total_seconds() / 3600
        # timedelta.total_seconds() = duration as float seconds. / 3600 = hours.
        
        if hours_before >= 24:
            return total_paid, f"Full refund — cancelled {hours_before:.0f} hours before check-in"
        else:
            return Decimal("0.00"), f"No refund — cancelled within 24 hours of check-in"


class ModeratePolicy(ICancellationPolicy):
    """
    Full refund if cancelled 5+ days before check-in.
    50% refund if cancelled 1-5 days before.
    No refund within 24 hours.
    """

    def calculate_refund(self, total_paid: Decimal,
                         check_in: date, cancelled_at: datetime) -> Tuple[Decimal, str]:
        check_in_dt  = datetime.combine(check_in, time(14, 0))
        days_before  = (check_in_dt - cancelled_at).days
        # timedelta.days: the integer number of days in the timedelta.

        if days_before >= 5:
            return total_paid, f"Full refund — cancelled {days_before} days before"
        elif days_before >= 1:
            refund = (total_paid * Decimal("0.5")).quantize(Decimal("0.01"), ROUND_HALF_UP)
            return refund, "50% refund — cancelled 1-5 days before check-in"
        else:
            return Decimal("0.00"), "No refund — cancelled within 24 hours"


class StrictPolicy(ICancellationPolicy):
    """
    50% refund 7+ days before. No refund within 7 days."""

    def calculate_refund(self, total_paid: Decimal,
                         check_in: date, cancelled_at: datetime) -> Tuple[Decimal, str]:
        check_in_dt  = datetime.combine(check_in, time(14, 0))
        days_before  = (check_in_dt - cancelled_at).days
        if days_before >= 7:
            refund = (total_paid * Decimal("0.5")).quantize(Decimal("0.01"), ROUND_HALF_UP)
            return refund, f"50% refund — strict policy, {days_before} days before"
        return Decimal("0.00"), "No refund — strict policy within 7 days"


class NonRefundablePolicy(ICancellationPolicy):
    """No refund under any circumstance."""

    def calculate_refund(self, total_paid: Decimal,
                         check_in: date, cancelled_at: datetime) -> Tuple[Decimal, str]:
        return Decimal("0.00"), "Non-refundable rate — no refund"


# ══════════════════════════════════════════════════════════════════════════════
# FLIGHT ENTITIES
# ══════════════════════════════════════════════════════════════════════════════

class Seat:
    """A specific physical seat on a specific flight."""

    def __init__(self, flight: Flight, seat_number: str, seat_class: FlightClass):
        self.id          = str(uuid.uuid4())
        self.flight      = flight
        self.seat_number = seat_number   # "12A", "15F", "3C"
        self.seat_class  = seat_class

        # Determine row (number) and column (letter) from seat number
        self.row = int(seat_number[:-1])   # "12A" → 12
        self.col = seat_number[-1]          # "12A" → "A"
        # seat_number[:-1] = all but last character. "12A"[:-1] = "12"
        # seat_number[-1]  = last character. "12A"[-1] = "A"

        self.seat_type   = self._determine_seat_type()
        self._status     = SeatStatus.AVAILABLE
        self._hold_until: Optional[datetime] = None  # When the hold expires
        self._lock       = threading.RLock()

    def _determine_seat_type(self) -> SeatType:
        """
        Airlines use standard column letters.
        Narrow body (A320): A-B-C (window-middle-aisle) | D-E-F (aisle-middle-window)
        Wide body (B777): A-B-C | D-E-F | G-H-K
        
        Simplified 6-column layout: A,F=window; B,E=middle; C,D=aisle
        """
        window_cols = {'A', 'F'}
        aisle_cols  = {'C', 'D'}
        if self.col in window_cols:  return SeatType.WINDOW
        if self.col in aisle_cols:   return SeatType.AISLE
        return SeatType.MIDDLE

    def hold(self, hold_duration_minutes: int = 10) -> bool:
        """
        Temporarily block this seat during checkout (10-minute hold).
        
        WHY A HOLD?
        User is filling in passenger details and payment info.
        We can't permanently book yet (payment not done).
        But we can't leave seat available (another user might take it).
        Solution: HOLD for 10 minutes. If payment completes → confirm.
        If payment fails or user abandons → release back to available.
        
        CONCURRENCY:
        Two users might try to hold the same seat simultaneously.
        The lock ensures only ONE succeeds.
        """
        with self._lock:
            if self._status != SeatStatus.AVAILABLE:
                # Check if a previous hold has expired
                if (self._status == SeatStatus.BLOCKED
                        and self._hold_until
                        and datetime.utcnow() > self._hold_until):
                    self._status = SeatStatus.AVAILABLE
                    self._hold_until = None
                    # Hold expired — seat is now available again
                else:
                    return False   # Seat is genuinely taken

            # Seat is available — place hold
            self._status     = SeatStatus.BLOCKED
            self._hold_until = datetime.utcnow() + timedelta(minutes=hold_duration_minutes)
            return True   # Hold successful

    def confirm_booking(self) -> bool:
        """
        Convert hold to permanent booking (after payment succeeds).
        Only works if seat was BLOCKED (held).
        """
        with self._lock:
            if self._status != SeatStatus.BLOCKED:
                return False   # Seat wasn't held (shouldn't happen in normal flow)
            self._status     = SeatStatus.BOOKED
            self._hold_until = None   # Hold converted to permanent booking
            return True

    def release(self) -> None:
        """Release held seat (payment failed or user abandoned checkout)."""
        with self._lock:
            if self._status in (SeatStatus.BLOCKED, SeatStatus.BOOKED):
                self._status     = SeatStatus.AVAILABLE
                self._hold_until = None

    @property
    def status(self) -> SeatStatus:
        with self._lock:
            # Auto-expire holds
            if (self._status == SeatStatus.BLOCKED
                    and self._hold_until
                    and datetime.utcnow() > self._hold_until):
                self._status     = SeatStatus.AVAILABLE
                self._hold_until = None
            return self._status


class Flight:
    """
    A scheduled flight from A to B at a specific time.
    Has a fixed number of seats in each class.
    """

    def __init__(self, flight_number: str, airline: Airline,
                 origin: Airport, destination: Airport,
                 departure: datetime, arrival: datetime,
                 aircraft_type: str = "A320"):
        self.id             = str(uuid.uuid4())
        self.flight_number  = flight_number   # "6E-123", "AI-302"
        self.airline        = airline
        self.origin         = origin
        self.destination    = destination
        self.departure      = departure
        self.arrival        = arrival
        self.aircraft_type  = aircraft_type
        self._status        = FlightStatus.SCHEDULED
        
        # Fare by class (base fares, dynamic pricing applied on top)
        self._base_fares: Dict[FlightClass, Decimal] = {
            FlightClass.ECONOMY:     Decimal("3500.00"),
            FlightClass.BUSINESS:    Decimal("15000.00"),
            FlightClass.FIRST_CLASS: Decimal("35000.00"),
        }
        
        # Seat inventory
        self._seats: List[Seat] = []
        self._lock = threading.RLock()

    def add_seat(self, seat: Seat) -> None:
        with self._lock:
            self._seats.append(seat)

    def get_available_seats(self, seat_class: FlightClass) -> List[Seat]:
        """Return all available (not held or booked) seats in the given class."""
        with self._lock:
            return [s for s in self._seats
                    if s.seat_class == seat_class
                    and s.status == SeatStatus.AVAILABLE]

    def get_available_count(self, seat_class: FlightClass) -> int:
        return len(self.get_available_seats(seat_class))

    def get_duration(self) -> timedelta:
        return self.arrival - self.departure

    def get_base_fare(self, seat_class: FlightClass) -> Decimal:
        return self._base_fares.get(seat_class, Decimal("0.00"))

    def cancel_flight(self) -> None:
        """Airline cancels flight — release all held/booked seats."""
        with self._lock:
            self._status = FlightStatus.CANCELLED
            for seat in self._seats:
                seat.release()   # Release all held/booked seats

    @property
    def status(self) -> FlightStatus:
        return self._status

    def __repr__(self) -> str:
        return (f"Flight({self.flight_number}: "
                f"{self.origin.code}→{self.destination.code} "
                f"{self.departure.strftime('%Y-%m-%d %H:%M')})")


# ══════════════════════════════════════════════════════════════════════════════
# PASSENGER
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Passenger:
    """
    A traveler on a specific flight booking.
    Can be the booking user themselves or a saved traveler (family member).
    """
    first_name:    str
    last_name:     str
    date_of_birth: date
    gender:        str            # "M", "F", "OTHER"
    passport_no:   Optional[str] = None   # Required for international flights
    nationality:   str = "IN"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def age(self) -> int:
        """Current age of this passenger."""
        today = date.today()
        born  = self.date_of_birth
        # Calculate age considering if birthday has passed this year
        return today.year - born.year - (
            (today.month, today.day) < (born.month, born.day)
        )
        # (today.month, today.day) < (born.month, born.day):
        # Tuple comparison: True if birthday hasn't occurred yet this year.
        # If True (birthday not yet): subtract 1 more year from age.

    def is_child(self) -> bool:
        return 2 <= self.age < 12

    def is_infant(self) -> bool:
        return self.age < 2


# ══════════════════════════════════════════════════════════════════════════════
# FLIGHT BOOKING
# ══════════════════════════════════════════════════════════════════════════════

class FlightBooking:
    """
    A flight reservation for one or more passengers.
    
    LIFECYCLE:
    1. HELD: Seats blocked, awaiting payment (10-minute window)
    2. CONFIRMED: Payment done, e-ticket generated
    3. COMPLETED: Flight has taken off, booking is historical
    4. CANCELLED: User cancelled or airline cancelled
    """

    HOLD_MINUTES = 10   # Seats held for this long before being released

    def __init__(self, user: User, flight: Flight, passengers: List[Passenger],
                 seats: List[Seat], seat_class: FlightClass, total_fare: Decimal):
        self.id           = str(uuid.uuid4())
        self.pnr          = self._generate_pnr()    # 6-char booking reference
        self.user         = user
        self.flight       = flight
        self.passengers   = passengers
        self.seats        = seats
        self.seat_class   = seat_class
        self.total_fare   = total_fare
        self._status      = BookingStatus.HELD
        self.booked_at    = datetime.utcnow()
        self.hold_expires  = datetime.utcnow() + timedelta(minutes=self.HOLD_MINUTES)
        self._lock        = threading.Lock()

    def _generate_pnr(self) -> str:
        """
        Generate a 6-character alphanumeric PNR (Passenger Name Record).
        PNR is the airline booking reference: "T3XK9P"
        
        random.choices: pick N random items from a population (with replacement).
        string.ascii_uppercase + string.digits = 26 letters + 10 digits = 36 chars.
        ''.join(...) = combine list of chars into a single string.
        """
        chars = string.ascii_uppercase + string.digits
        return ''.join(random.choices(chars, k=6))
        # k=6 means pick 6 characters. With replacement (same char can appear twice).

    def confirm(self) -> bool:
        """
        Confirm booking after payment succeeds.
        Converts seat holds to permanent bookings.
        """
        with self._lock:
            if self._status != BookingStatus.HELD:
                return False   # Already confirmed or cancelled
            if datetime.utcnow() > self.hold_expires:
                # Hold expired — someone else may have taken the seats
                self.cancel()
                return False
            
            # Convert all held seats to confirmed bookings
            for seat in self.seats:
                if not seat.confirm_booking():
                    # If any seat fails to confirm, cancel everything
                    for confirmed_seat in self.seats:
                        confirmed_seat.release()
                    self._status = BookingStatus.CANCELLED
                    return False
            
            self._status = BookingStatus.CONFIRMED
            return True

    def cancel(self) -> RefundDetails:
        """Cancel booking. Release seats. Calculate refund."""
        with self._lock:
            if self._status == BookingStatus.CANCELLED:
                # Already cancelled — return ₹0 refund (don't refund twice)
                return RefundDetails(self.id, Decimal("0.00"), 0, "Already cancelled")
            
            # Release all seats back to available
            for seat in self.seats:
                seat.release()
            
            prev_status   = self._status
            self._status  = BookingStatus.CANCELLED
            
            # Calculate refund based on when cancelled
            return self._calculate_flight_refund(prev_status)

    def _calculate_flight_refund(self, prev_status: BookingStatus) -> RefundDetails:
        """
        Flight refund policy (simplified):
        - HELD (never paid): 100% refund (nothing was charged)
        - CONFIRMED + more than 24 hours before departure: 75% refund (25% airline fee)
        - CONFIRMED + within 24 hours: 0% refund (non-refundable within 24h)
        """
        if prev_status == BookingStatus.HELD:
            return RefundDetails(self.id, Decimal("0.00"), 0,
                                 "Booking was not confirmed — no charge applied")

        hours_to_departure = (self.flight.departure - datetime.utcnow()).total_seconds() / 3600
        if hours_to_departure > 24:
            refund = (self.total_fare * Decimal("0.75")).quantize(
                Decimal("0.01"), ROUND_HALF_UP
            )
            return RefundDetails(self.id, refund, 75,
                                 f"75% refund — cancelled {hours_to_departure:.0f}h before departure")
        else:
            return RefundDetails(self.id, Decimal("0.00"), 0,
                                 "No refund — cancelled within 24 hours of departure")

    @property
    def status(self) -> BookingStatus:
        with self._lock:
            if (self._status == BookingStatus.HELD
                    and datetime.utcnow() > self.hold_expires):
                # Auto-expire: if hold expired and not confirmed, cancel
                self._status = BookingStatus.CANCELLED
                for seat in self.seats:
                    seat.release()
            return self._status

    def __repr__(self) -> str:
        return f"FlightBooking(PNR:{self.pnr}, {self.flight}, {self.status.value})"


# ══════════════════════════════════════════════════════════════════════════════
# HOTEL ENTITIES
# ══════════════════════════════════════════════════════════════════════════════

class Room:
    """A room TYPE at a hotel (not a specific physical room)."""

    def __init__(self, hotel: Hotel, room_type: RoomType, max_guests: int,
                 price_per_night: Decimal, total_count: int):
        self.id              = str(uuid.uuid4())
        self.hotel           = hotel
        self.room_type       = room_type
        self.max_guests      = max_guests
        self.price_per_night = price_per_night
        self._total          = total_count    # How many rooms of this type exist
        self._available      = total_count    # How many are currently bookable
        self._lock           = threading.Lock()

    def check_availability(self, check_in: date, check_out: date,
                           guests_count: int) -> bool:
        """
        Can we book this room type for the given dates?
        
        SIMPLIFIED: We check if rooms are available in general.
        REAL SYSTEM: Check room availability per date
        (a room booked Dec 25-27 is unavailable on those specific dates,
        but available on Dec 28+).
        """
        if guests_count > self.max_guests:
            return False   # Room too small for the party

        with self._lock:
            return self._available > 0

    def block(self) -> bool:
        """Block one room (during checkout)."""
        with self._lock:
            if self._available <= 0:
                return False
            self._available -= 1
            return True

    def release(self) -> None:
        """Release one room back to available."""
        with self._lock:
            if self._available < self._total:
                self._available += 1

    def confirm(self) -> None:
        """Booking confirmed — room remains blocked (already was)."""
        pass   # Room stays blocked until checkout date passes

    @property
    def available_count(self) -> int:
        with self._lock:
            return self._available


class Hotel:
    """
    A hotel property listing.
    Has multiple room types with different prices.
    """

    def __init__(self, name: str, city: str, address: str,
                 star_rating: int, amenities: List[str]):
        self.id          = str(uuid.uuid4())
        self.name        = name
        self.city        = city
        self.address     = address
        self.star_rating = star_rating   # 1-5 stars
        self.amenities   = amenities     # ["WiFi", "Pool", "Gym", "Breakfast"]
        self._rooms:     List[Room]  = []
        self._reviews:   List[float] = []   # List of star ratings (1-5)
        self._lock       = threading.Lock()

    def add_room(self, room: Room) -> None:
        with self._lock:
            self._rooms.append(room)

    def get_rooms(self, room_type: RoomType = None) -> List[Room]:
        with self._lock:
            if room_type is None:
                return list(self._rooms)   # All room types
            return [r for r in self._rooms if r.room_type == room_type]

    def add_review(self, stars: float) -> None:
        if not (1 <= stars <= 5): raise ValueError("Rating must be 1-5")
        with self._lock:
            self._reviews.append(stars)

    @property
    def rating(self) -> float:
        with self._lock:
            return sum(self._reviews) / len(self._reviews) if self._reviews else 0.0

    @property
    def review_count(self) -> int:
        with self._lock:
            return len(self._reviews)

    def __repr__(self) -> str:
        return f"Hotel({self.name}, {self.city}, ⭐{self.star_rating})"


class HotelBooking:
    """
    A hotel reservation for one or more guests.
    
    NOTE: Hotels allow rooms to be pre-blocked and confirmed.
    Unlike flights (exact seat), hotels are typically room-type bookings
    (you book "1 Double Room", hotel assigns specific room at check-in).
    """

    def __init__(self, user: User, hotel: Hotel, room: Room,
                 check_in: date, check_out: date, guests: int,
                 total_price: Decimal, policy: ICancellationPolicy):
        self.id                  = str(uuid.uuid4())
        self.booking_ref         = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        self.user                = user
        self.hotel               = hotel
        self.room                = room
        self.check_in            = check_in
        self.check_out           = check_out
        self.guests              = guests
        self.total_price         = total_price
        self._cancellation_policy = policy    # Strategy object
        self._status             = BookingStatus.HELD
        self._lock               = threading.Lock()

    @property
    def nights(self) -> int:
        """Number of nights in the booking."""
        return (self.check_out - self.check_in).days
        # date subtraction gives timedelta. .days = integer number of days.

    def confirm(self) -> bool:
        with self._lock:
            if self._status != BookingStatus.HELD:
                return False
            self.room.confirm()
            self._status = BookingStatus.CONFIRMED
            return True

    def cancel(self) -> RefundDetails:
        """
        Cancel with refund calculated by the cancellation POLICY (Strategy Pattern).
        
        The HotelBooking doesn't know the refund rules — it delegates to the policy.
        Different bookings can have different policies even in the same hotel.
        """
        with self._lock:
            if self._status == BookingStatus.CANCELLED:
                return RefundDetails(self.id, Decimal("0.00"), 0, "Already cancelled")
            
            self.room.release()
            self._status = BookingStatus.CANCELLED
        
        # STRATEGY PATTERN: delegate to the injected policy
        refund_amount, reason = self._cancellation_policy.calculate_refund(
            self.total_price, self.check_in, datetime.utcnow()
        )
        return RefundDetails(self.id, refund_amount,
                             float(refund_amount / self.total_price * 100) if self.total_price else 0,
                             reason)

    @property
    def status(self) -> BookingStatus:
        with self._lock:
            return self._status


# ══════════════════════════════════════════════════════════════════════════════
# USER
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class SavedTraveler:
    """
    A family member profile saved by the user.
    "Add to my travelers" for quick booking.
    """
    first_name:    str
    last_name:     str
    date_of_birth: date
    gender:        str
    passport_no:   Optional[str] = None
    nationality:   str = "IN"
    id:            str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_passenger(self) -> Passenger:
        """Convert saved traveler to a Passenger object for a booking."""
        return Passenger(
            first_name=self.first_name,
            last_name=self.last_name,
            date_of_birth=self.date_of_birth,
            gender=self.gender,
            passport_no=self.passport_no,
            nationality=self.nationality
        )


class User:
    """A registered user of the travel platform."""

    def __init__(self, email: str, name: str, phone: str):
        self.id               = str(uuid.uuid4())
        self.email            = email
        self.name             = name
        self.phone            = phone
        self._saved_travelers: List[SavedTraveler] = []
        self._bookings:       List[str]            = []   # Booking IDs
        self._lock            = threading.Lock()

    def add_traveler(self, traveler: SavedTraveler) -> None:
        with self._lock:
            self._saved_travelers.append(traveler)

    def get_travelers(self) -> List[SavedTraveler]:
        with self._lock:
            return list(self._saved_travelers)

    def add_booking_ref(self, booking_id: str) -> None:
        with self._lock:
            self._bookings.append(booking_id)


# ══════════════════════════════════════════════════════════════════════════════
# PRICING SERVICE — Strategy Pattern
# ══════════════════════════════════════════════════════════════════════════════

class IPricingStrategy(ABC):
    """
    STRATEGY for price calculation.
    Dynamic pricing: price goes up as seats fill up (like airline pricing).
    """

    @abstractmethod
    def calculate_fare(self, base_fare: Decimal, available_seats: int,
                       total_seats: int, days_to_departure: int) -> Decimal:
        """
        Calculate the final fare based on current conditions.
        
        base_fare: airline's published base price
        available_seats: how many seats still available in this class
        total_seats: total seats in this class on this flight
        days_to_departure: how many days until the flight
        """
        ...


class DynamicPricingStrategy(IPricingStrategy):
    """
    Airlines use dynamic pricing — price increases as:
    1. More seats fill up (scarcity)
    2. Departure gets closer (urgency)
    
    ALGORITHM (simplified):
    - Occupancy > 80%: 1.3× multiplier
    - Occupancy > 90%: 1.5× multiplier
    - Days to departure < 3: 1.4× multiplier
    - Both factors compound
    """

    def calculate_fare(self, base_fare: Decimal, available_seats: int,
                       total_seats: int, days_to_departure: int) -> Decimal:
        occupancy_rate = 1.0 - (available_seats / total_seats) if total_seats > 0 else 0.0
        # occupancy_rate: 0.0 = empty plane, 1.0 = fully booked

        multiplier = Decimal("1.0")

        # Scarcity pricing
        if occupancy_rate > 0.9:
            multiplier *= Decimal("1.5")    # 50% markup for near-full flights
        elif occupancy_rate > 0.8:
            multiplier *= Decimal("1.3")    # 30% markup for 80%+ full
        elif occupancy_rate > 0.6:
            multiplier *= Decimal("1.1")    # 10% markup for 60%+ full

        # Urgency pricing (last-minute)
        if days_to_departure <= 3:
            multiplier *= Decimal("1.4")    # 40% markup for last 3 days
        elif days_to_departure <= 7:
            multiplier *= Decimal("1.2")    # 20% markup for last week

        fare = (base_fare * multiplier).quantize(Decimal("0.01"), ROUND_HALF_UP)
        return fare


class FixedPricingStrategy(IPricingStrategy):
    """Fixed fare — no dynamic changes. Used for corporate accounts."""

    def calculate_fare(self, base_fare: Decimal, available_seats: int,
                       total_seats: int, days_to_departure: int) -> Decimal:
        return base_fare   # No adjustment


# ══════════════════════════════════════════════════════════════════════════════
# SEARCH SERVICE
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class FlightSearchResult:
    """A flight search result shown to the user."""
    flight:          Flight
    available_class: FlightClass
    available_seats: int
    price:           Decimal
    duration:        timedelta
    stops:           int = 0    # 0 = direct, 1 = one stop, etc.

    def __repr__(self) -> str:
        hrs  = int(self.duration.total_seconds() // 3600)
        mins = int((self.duration.total_seconds() % 3600) // 60)
        return (f"{self.flight} | {self.available_class.value} | "
                f"₹{self.price} | {hrs}h {mins}m | {self.available_seats} seats left")


@dataclass
class HotelSearchResult:
    """A hotel search result shown to the user."""
    hotel:        Hotel
    room:         Room
    available:    int
    price_per_night: Decimal
    total_price:  Decimal
    nights:       int

    def __repr__(self) -> str:
        return (f"{self.hotel.name} ({self.hotel.star_rating}★) | "
                f"{self.room.room_type.value} | "
                f"₹{self.price_per_night}/night × {self.nights} = ₹{self.total_price}")


class SearchService:
    """
    Searches available flights and hotels.
    In production: backed by Elasticsearch or Solr for full-text search.
    Inventory counts cached in Redis for fast availability checks.
    """

    def __init__(self, pricing: IPricingStrategy = None):
        self._flights: List[Flight] = []
        self._hotels:  List[Hotel]  = []
        self._pricing  = pricing or DynamicPricingStrategy()

    def add_flight(self, flight: Flight) -> None:
        self._flights.append(flight)

    def add_hotel(self, hotel: Hotel) -> None:
        self._hotels.append(hotel)

    def search_flights(self, origin_code: str, dest_code: str,
                       departure_date: date, passengers: int = 1,
                       preferred_class: FlightClass = FlightClass.ECONOMY) -> List[FlightSearchResult]:
        """
        Search for available flights between two airports on a given date.
        
        FILTERING:
        1. Origin and destination match
        2. Departure date matches
        3. Enough available seats for all passengers
        4. Flight not cancelled
        """
        results = []
        for flight in self._flights:
            # Filter: origin/destination match
            if flight.origin.code != origin_code.upper():    continue
            if flight.destination.code != dest_code.upper(): continue
            
            # Filter: departure date matches
            if flight.departure.date() != departure_date:    continue
            
            # Filter: flight is not cancelled
            if flight.status == FlightStatus.CANCELLED:      continue
            
            # Filter: enough seats for all passengers
            available = flight.get_available_count(preferred_class)
            if available < passengers:                       continue
            
            # Calculate price with dynamic pricing
            base_fare = flight.get_base_fare(preferred_class)
            total_seats = len([s for s in flight._seats if s.seat_class == preferred_class])
            days_to_dep = (flight.departure.date() - date.today()).days
            
            price = self._pricing.calculate_fare(
                base_fare * passengers,   # Total for all passengers
                available, total_seats, days_to_dep
            )

            results.append(FlightSearchResult(
                flight=flight,
                available_class=preferred_class,
                available_seats=available,
                price=price,
                duration=flight.get_duration()
            ))

        # Sort by price (cheapest first) by default
        results.sort(key=lambda r: r.price)
        return results

    def search_hotels(self, city: str, check_in: date, check_out: date,
                      guests: int = 2, room_type: RoomType = None,
                      max_price_per_night: Decimal = None) -> List[HotelSearchResult]:
        """Search available hotels in a city for given dates."""
        nights = (check_out - check_in).days
        if nights <= 0:
            raise ValueError("Check-out must be after check-in")

        results = []
        for hotel in self._hotels:
            if hotel.city.lower() != city.lower(): continue   # City match

            for room in hotel.get_rooms(room_type):
                if not room.check_availability(check_in, check_out, guests): continue
                if max_price_per_night and room.price_per_night > max_price_per_night: continue

                total = (room.price_per_night * nights).quantize(Decimal("0.01"), ROUND_HALF_UP)
                results.append(HotelSearchResult(
                    hotel=hotel, room=room,
                    available=room.available_count,
                    price_per_night=room.price_per_night,
                    total_price=total,
                    nights=nights
                ))

        results.sort(key=lambda r: r.price_per_night)
        return results


# ══════════════════════════════════════════════════════════════════════════════
# BOOKING SERVICE — Facade
# ══════════════════════════════════════════════════════════════════════════════

class BookingService:
    """
    FACADE for the booking flow.
    
    FLIGHT BOOKING FLOW:
    1. Hold seats (block for 10 minutes)
    2. Collect passenger details
    3. Process payment (via payment gateway)
    4. Confirm booking (convert hold → permanent)
    5. Generate e-ticket, send email
    
    HOTEL BOOKING FLOW:
    1. Hold room (block)
    2. Collect guest details
    3. Process payment
    4. Confirm booking
    5. Send voucher
    """

    def __init__(self):
        self._bookings: Dict[str, object] = {}   # id → FlightBooking or HotelBooking
        self._lock = threading.RLock()

    def hold_flight(self, user: User, search_result: FlightSearchResult,
                    passengers: List[Passenger]) -> Optional[FlightBooking]:
        """
        Step 1: Hold seats for selected flight.
        Attempts to block the required number of seats.
        Returns FlightBooking in HELD state, or None if seats unavailable.
        
        CRITICAL SECTION:
        If two users book simultaneously, the lock ensures only one
        successfully holds the seats. The other user gets None and must retry.
        """
        flight    = search_result.flight
        cls       = search_result.available_class
        n_pax     = len(passengers)

        # Get available seats and try to hold them
        available_seats = flight.get_available_seats(cls)
        if len(available_seats) < n_pax:
            print(f"❌ Not enough seats available (need {n_pax}, have {len(available_seats)})")
            return None

        # Hold exactly n_pax seats
        held_seats = []
        for seat in available_seats[:n_pax]:
            if seat.hold():
                held_seats.append(seat)
            else:
                # Seat.hold() failed (someone else took it between our availability check and hold)
                # Release any seats we already held
                for s in held_seats: s.release()
                print(f"❌ Seat {seat.seat_number} taken during hold. Try again.")
                return None

        booking = FlightBooking(
            user=user, flight=flight, passengers=passengers,
            seats=held_seats, seat_class=cls, total_fare=search_result.price
        )
        with self._lock:
            self._bookings[booking.id] = booking
        user.add_booking_ref(booking.id)

        print(f"✅ Seats held: {[s.seat_number for s in held_seats]} | "
              f"PNR: {booking.pnr} | Hold expires in {FlightBooking.HOLD_MINUTES} min")
        return booking

    def confirm_flight_booking(self, booking: FlightBooking) -> bool:
        """
        Step 2: Confirm after payment succeeds.
        Converts seat holds to permanent bookings.
        """
        success = booking.confirm()
        if success:
            print(f"✅ Flight booking CONFIRMED! PNR: {booking.pnr}")
            print(f"   {booking.flight}")
            print(f"   Passengers: {[p.full_name for p in booking.passengers]}")
            print(f"   Seats: {[s.seat_number for s in booking.seats]}")
            print(f"   Total: ₹{booking.total_fare}")
        else:
            print(f"❌ Booking confirmation failed — seats may have been released")
        return success

    def hold_hotel(self, user: User, search_result: HotelSearchResult,
                   guests: int, cancellation_type: CancellationPolicyType,
                   check_in: date, check_out: date) -> Optional[HotelBooking]:
        """Hold a hotel room during checkout."""
        room = search_result.room
        if not room.block():
            print(f"❌ Room not available at {search_result.hotel.name}")
            return None

        # Select cancellation policy based on type (Strategy injection)
        policy_map = {
            CancellationPolicyType.FLEXIBLE:       FlexiblePolicy(),
            CancellationPolicyType.MODERATE:       ModeratePolicy(),
            CancellationPolicyType.STRICT:         StrictPolicy(),
            CancellationPolicyType.NON_REFUNDABLE: NonRefundablePolicy(),
        }
        policy = policy_map[cancellation_type]

        booking = HotelBooking(
            user=user, hotel=search_result.hotel, room=room,
            check_in=check_in, check_out=check_out, guests=guests,
            total_price=search_result.total_price, policy=policy
        )
        with self._lock:
            self._bookings[booking.id] = booking
        user.add_booking_ref(booking.id)

        print(f"✅ Room held: {room.room_type.value} at {search_result.hotel.name}")
        print(f"   Booking ref: {booking.booking_ref} | {booking.nights} nights | ₹{booking.total_price}")
        return booking

    def confirm_hotel_booking(self, booking: HotelBooking) -> bool:
        """Confirm hotel booking after payment."""
        success = booking.confirm()
        if success:
            print(f"✅ Hotel CONFIRMED! Ref: {booking.booking_ref}")
        return success

    def cancel_booking(self, booking_id: str) -> RefundDetails:
        """Cancel any booking and get refund details."""
        with self._lock:
            booking = self._bookings.get(booking_id)
        if not booking:
            raise ValueError(f"Booking {booking_id} not found")
        return booking.cancel()


# ══════════════════════════════════════════════════════════════════════════════
# MAKEMYTRIP SERVICE — Main Facade
# ══════════════════════════════════════════════════════════════════════════════

class MakeMyTripService:
    """Main entry point for the travel booking platform."""

    def __init__(self):
        self._users:   Dict[str, User] = {}
        self._search   = SearchService(DynamicPricingStrategy())
        self._bookings = BookingService()

    def register_user(self, email: str, name: str, phone: str) -> User:
        user = User(email, name, phone)
        self._users[user.id] = user
        return user

    def add_flight(self, flight: Flight) -> None:
        self._search.add_flight(flight)

    def add_hotel(self, hotel: Hotel) -> None:
        self._search.add_hotel(hotel)

    def search_flights(self, origin: str, dest: str, travel_date: date,
                       passengers: int = 1,
                       cls: FlightClass = FlightClass.ECONOMY) -> List[FlightSearchResult]:
        results = self._search.search_flights(origin, dest, travel_date, passengers, cls)
        print(f"\nFlights {origin}→{dest} on {travel_date} | {passengers} pax | {cls.value}")
        for i, r in enumerate(results, 1):
            print(f"  {i}. {r}")
        return results

    def search_hotels(self, city: str, check_in: date, check_out: date,
                      guests: int = 2) -> List[HotelSearchResult]:
        results = self._search.search_hotels(city, check_in, check_out, guests)
        print(f"\nHotels in {city} | {check_in} to {check_out} | {guests} guests")
        for i, r in enumerate(results, 1):
            print(f"  {i}. {r}")
        return results

    def book_flight(self, user: User, search_result: FlightSearchResult,
                    passengers: List[Passenger]) -> Optional[FlightBooking]:
        booking = self._bookings.hold_flight(user, search_result, passengers)
        if booking:
            # In real flow: redirect to payment gateway
            # Simulate payment success:
            confirmed = self._bookings.confirm_flight_booking(booking)
        return booking

    def book_hotel(self, user: User, search_result: HotelSearchResult,
                   guests: int, check_in: date, check_out: date,
                   policy: CancellationPolicyType = CancellationPolicyType.FLEXIBLE) -> Optional[HotelBooking]:
        booking = self._bookings.hold_hotel(user, search_result, guests, policy, check_in, check_out)
        if booking:
            confirmed = self._bookings.confirm_hotel_booking(booking)
        return booking

    def cancel(self, booking_id: str) -> RefundDetails:
        return self._bookings.cancel_booking(booking_id)


# ══════════════════════════════════════════════════════════════════════════════
# DEMO
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    mmt = MakeMyTripService()

    # Setup airports
    DEL = Airport("DEL", "Indira Gandhi International", "New Delhi", "IN", "Asia/Kolkata")
    BOM = Airport("BOM", "Chhatrapati Shivaji International", "Mumbai", "IN", "Asia/Kolkata")

    # Setup airline
    indigo = Airline("6E", "IndiGo", "cdn/indigo_logo.png")

    # Create a flight
    dep = datetime(2025, 12, 25, 8, 0)   # Dec 25, 2025 at 8:00 AM
    arr = datetime(2025, 12, 25, 10, 15) # Arrives at 10:15 AM (2h 15m flight)
    flight = Flight("6E-123", indigo, DEL, BOM, dep, arr, "A320")

    # Add seats to the flight
    for row in range(1, 31):       # 30 rows
        for col in ["A", "B", "C", "D", "E", "F"]:
            cls = (FlightClass.BUSINESS if row <= 5
                   else FlightClass.ECONOMY)
            seat = Seat(flight, f"{row}{col}", cls)
            flight.add_seat(seat)

    mmt.add_flight(flight)

    # Add hotel
    taj = Hotel("Taj Mahal Palace", "Mumbai", "Apollo Bunder, Colaba",
                star_rating=5, amenities=["WiFi", "Pool", "Spa", "Restaurant"])
    deluxe_room = Room(taj, RoomType.DELUXE, max_guests=2,
                       price_per_night=Decimal("12000.00"), total_count=10)
    taj.add_room(deluxe_room)
    mmt.add_hotel(taj)

    # Register user
    sachin = mmt.register_user("sachin@gmail.com", "Sachin Kumar", "+91-9876543210")

    # Search flights
    flight_results = mmt.search_flights("DEL", "BOM", date(2025, 12, 25), passengers=2)

    # Book flight
    if flight_results:
        p1 = Passenger("Sachin", "Kumar", date(1995, 6, 15), "M")
        p2 = Passenger("Priya", "Kumar", date(1997, 3, 22), "F")
        flight_booking = mmt.book_flight(sachin, flight_results[0], [p1, p2])

    # Search hotels
    hotel_results = mmt.search_hotels("Mumbai", date(2025, 12, 25), date(2025, 12, 28), guests=2)

    # Book hotel with flexible cancellation
    if hotel_results:
        hotel_booking = mmt.book_hotel(sachin, hotel_results[0], 2,
                                       date(2025, 12, 25), date(2025, 12, 28),
                                       CancellationPolicyType.FLEXIBLE)

        # Cancel hotel 8 days before check-in (should get full refund)
        if hotel_booking:
            refund = mmt.cancel(hotel_booking.id)
            print(f"\nRefund: ₹{refund.refund_amount} | {refund.refund_reason}")
```

---

## STEP 5 — Trade-offs & Key Concepts

```
TRADE-OFF 1: Seat hold vs direct booking
  Direct (no hold): User clicks "Book" → immediately charge → confirm.
  Con: Payment may fail. How long do we hold the seat while payment processes?
  
  10-minute hold (what we built): block seat → collect details → process payment.
  Industry standard for airline booking.
  Con: Seat is unavailable for 10 minutes even if user abandons checkout.
  
  Overbooking mitigation: airlines sometimes sell more seats than capacity.
  If all passengers show up: "bumping" a passenger (with compensation).
  In our LLD: no overbooking. available_count never goes below 0.

TRADE-OFF 2: Room-type booking (hotel) vs seat booking (flight)
  Flights: exact seat (12A is yours and ONLY yours). Blocking one specific object.
  Hotels: room type ("1 Deluxe Room"). Hotel assigns actual room at check-in.
  
  Why different? Hotels don't need exact room assignment months in advance.
  Flexibility helps hotels (can upgrade customer to better available room).
  
  Implementation impact:
  - Flight: hold/confirm specific Seat objects
  - Hotel: hold/confirm a count in Room (abstract, not specific physical room)

TRADE-OFF 3: Dynamic pricing — when to recalculate?
  Option A: Recalculate on every search request.
  Con: price might change between search and booking.
  
  Option B: Lock price when seats are held.
  Price shown = price charged. User gets what they were quoted.
  This is what airlines do (fare guarantee during checkout window).
  
  We lock the price in FlightSearchResult.price and pass that to FlightBooking.total_fare.
  Price doesn't recalculate during the 10-minute hold.

TRADE-OFF 4: Cancellation policy as Strategy vs if/elif
  Without Strategy: HotelBooking.cancel() has:
    if policy == "flexible": full_refund()
    elif policy == "moderate": partial_refund()
    elif policy == "strict": ...
  Adding new policy = modify HotelBooking (violates Open/Closed Principle).
  
  With Strategy: HotelBooking.cancel() calls: self._policy.calculate_refund()
  Adding new policy = new class only. HotelBooking unchanged. Clean.
  Also: different policies can be A/B tested independently.

TRADE-OFF 5: Search backed by DB vs Elasticsearch
  DB: SELECT * FROM flights WHERE origin = 'DEL' AND destination = 'BOM' AND date = '2025-12-25'
  Works for simple queries. Gets slow with many filters (price range, stops, airline).
  
  Elasticsearch: Index all flights. Full-text + faceted search. < 100ms response.
  Supports: "Show me flights under ₹5000, direct, IndiGo or Air India, 8-10am"
  In production: MakeMyTrip uses Elasticsearch for flight/hotel search.
  
  Our SearchService can be reimplemented as an ElasticsearchSearchService
  (Strategy Pattern) — caller (MakeMyTripService) doesn't change.
```

---

## STEP 6 — Interview Follow-Ups

```
Q: "How do you prevent two users from booking the same seat?"
A:
  Our solution: Seat.hold() uses a threading.RLock.
  Only one thread can execute hold() at a time.
  Second thread finds status = BLOCKED → returns False → user sees "seat taken."
  
  In distributed system (multiple servers):
  DB-level: SELECT FOR UPDATE or optimistic locking (version column).
  Redis-level: SETNX (SET if Not eXists) for distributed lock.
  SETNX key = "seat_lock_6E123_12A", value = user_session_id, expiry = 10 min
  Only one server succeeds (Redis is single-threaded → SETNX is atomic).

Q: "How does price drop alert work?"
A:
  PriceAlert entity: user_id, flight/hotel_id, target_price, is_active.
  Stored in DB.
  
  Scheduled job (every 15 minutes):
  1. Get all active price alerts.
  2. For each alert: calculate current price (same pricing engine).
  3. If current_price <= target_price: send email/SMS notification.
  4. Mark alert as triggered (one-time notification).
  
  At scale: Kafka topic "price_changes". When pricing engine recalculates,
  publish to topic. PriceAlert consumer checks if any alert matches.
  More real-time than scheduled job.

Q: "How do you handle partial flight booking (only 2 seats left, user wants 3)?"
A:
  Search layer: search_flights() filters: available >= passengers.
  So user never sees a flight that can't accommodate all passengers.
  
  At booking time: if between search and hold attempt, one more seat is taken,
  hold_flight() returns None (failed to hold all seats).
  UX: "Oops, seats no longer available. Please search again."
  
  Can offer alternatives: "3 seats available on the next flight at 10:30 AM."

Q: "How does multi-city booking work (Delhi → Mumbai → Goa)?"
A:
  MultiCityBooking: contains a list of FlightBookings.
  Each leg is independently searched and booked.
  
  Challenge: if leg 2 (Mumbai → Goa) is unavailable, should we cancel leg 1 (Delhi → Mumbai)?
  Yes: book all legs atomically. If any fails: release all held seats.
  
  Implementation:
  BookingService.hold_multi_city(user, [result1, result2], passengers):
    holdings = []
    for result in results:
      holding = hold_flight(user, result, passengers)
      if not holding: # failed
        for h in holdings: h.cancel()  # rollback
        return None
      holdings.append(holding)
    return MultiCityBooking(holdings)
  This is a SAGA pattern: compensating transactions on failure.
```


---

## STEP 7 — Deep-Dive: GDS Integration and Real-Time Inventory

```
WHAT IS A GDS?
  GDS = Global Distribution System.
  Three major players: Amadeus (EU), Sabre (US), Travelport (UK).
  
  Airlines publish their flight inventory to GDS.
  OTAs (MakeMyTrip, Expedia, Booking.com) query GDS to get real-time availability and prices.
  
  WHY GDS EXISTS:
    Without GDS: Expedia must integrate directly with 500+ airlines individually.
    500 different APIs, different formats, different auth systems.
    With GDS: one API → access to all 500+ airlines. Expedia integrates once.
    GDS acts as a broker between airlines and OTAs.
  
  GDS REVENUE MODEL:
    Airlines pay GDS per booking (booking fee, typically $3-10 per segment).
    OTAs pay GDS for API access (subscription + per-search fees).
    GDS revenue: billions per year.

LLD — GDS ADAPTER PATTERN:

  class IGDS(ABC):
      """Interface for any GDS provider."""
      
      @abstractmethod
      def search_flights(self, origin: str, destination: str, date: str, 
                         passengers: int) -> List[GDSFlightResult]:
          ...
      
      @abstractmethod
      def create_pnr(self, flight_id: str, passengers: List[PassengerData]) -> str:
          """Create Passenger Name Record (PNR) = the booking record."""
          ...
      
      @abstractmethod
      def issue_ticket(self, pnr: str, payment: PaymentData) -> str:
          """Issue the actual e-ticket. Returns ticket number."""
          ...
      
      @abstractmethod
      def cancel_pnr(self, pnr: str) -> RefundDetails:
          ...
  
  class AmadeusGDS(IGDS):
      """Adapter for Amadeus GDS API."""
      BASE_URL = "https://api.amadeus.com/v2"
      
      def __init__(self, client_id: str, client_secret: str):
          self._client_id = client_id
          self._client_secret = client_secret
          self._access_token = None
          self._token_expiry = None
      
      def _ensure_token(self):
          """OAuth2 client credentials flow. Token expires every 30 minutes."""
          if self._access_token and datetime.utcnow() < self._token_expiry:
              return  # Token still valid
          
          # POST to token endpoint
          response = requests.post(
              f"{self.BASE_URL}/security/oauth2/token",
              data={
                  "grant_type": "client_credentials",
                  "client_id": self._client_id,
                  "client_secret": self._client_secret
              }
          )
          token_data = response.json()
          self._access_token = token_data["access_token"]
          self._token_expiry = datetime.utcnow() + timedelta(
              seconds=token_data["expires_in"] - 60  # Refresh 1 min before expiry
          )
      
      def search_flights(self, origin, destination, date, passengers) -> List[GDSFlightResult]:
          self._ensure_token()
          
          response = requests.get(
              f"{self.BASE_URL}/shopping/flight-offers",
              headers={"Authorization": f"Bearer {self._access_token}"},
              params={
                  "originLocationCode": origin,
                  "destinationLocationCode": destination,
                  "departureDate": date,  # "2025-12-25" format
                  "adults": passengers,
                  "max": 50  # limit results
              }
          )
          
          # Parse Amadeus-specific response format → our GDSFlightResult format
          return [self._parse_offer(offer) for offer in response.json().get("data", [])]
      
      def _parse_offer(self, offer: dict) -> GDSFlightResult:
          """Convert Amadeus API response format to our internal format."""
          itinerary = offer["itineraries"][0]
          segment = itinerary["segments"][0]
          price = offer["price"]
          
          return GDSFlightResult(
              gds_offer_id=offer["id"],
              origin=segment["departure"]["iataCode"],
              destination=segment["arrival"]["iataCode"],
              departure_time=segment["departure"]["at"],
              arrival_time=segment["arrival"]["at"],
              airline_code=segment["carrierCode"],
              flight_number=segment["number"],
              total_price=Decimal(price["total"]),
              currency=price["currency"],
              seats_available=offer.get("numberOfBookableSeats", 9),
              cabin_class=offer["travelerPricings"][0]["fareDetailsBySegment"][0]["cabin"]
          )
  
  class SabreGDS(IGDS):
      """Adapter for Sabre GDS API (different format, same interface)."""
      # Different Sabre-specific implementation
      # But same IGDS interface → SearchService.search_flights() doesn't need to change
      pass
  
  # ADAPTER PATTERN IN ACTION:
  class SearchService:
      def __init__(self, gds: IGDS):  # Inject the GDS
          self._gds = gds
      
      def search_flights(self, origin, destination, date, passengers) -> List[FlightSearchResult]:
          # Works with Amadeus, Sabre, or Travelport — same interface
          gds_results = self._gds.search_flights(origin, destination, date, passengers)
          return [self._convert(r) for r in gds_results]
  
  # At startup: choose which GDS to use
  service = SearchService(gds=AmadeusGDS(CLIENT_ID, CLIENT_SECRET))
  # To switch to Sabre: SearchService(gds=SabreGDS(...)) — zero other changes.

PRICE CACHING STRATEGY:
  Problem: GDS search is expensive (takes 500ms-2s, costs money per search).
  At scale: millions of searches per hour × $0.01/search = thousands of dollars/hour.
  
  Solution: cache search results.
    Cache key: (origin, destination, date, passengers, cabin_class) → results
    TTL: 5 minutes (prices change rapidly, but not every second)
    
    Redis caching:
    def search_flights_cached(self, origin, dest, date, passengers):
        cache_key = f"search:{origin}:{dest}:{date}:{passengers}"
        cached = redis.get(cache_key)
        if cached:
            return json.loads(cached)  # Return cached results
        
        # Cache miss: call GDS
        results = self._gds.search_flights(origin, dest, date, passengers)
        redis.setex(cache_key, 300, json.dumps(results))  # Cache 5 minutes
        return results
    
    Cache hit rate: 60-70% (many users search same routes, prices are valid for a few minutes).
    Cost reduction: 60% fewer GDS API calls = significant savings.
    
    When to NOT cache:
      Booking time: always call GDS for fresh inventory (never book on stale cache).
      Price guarantee: at hold time, re-fetch from GDS to ensure current price.
```

---

## STEP 8 — Deep-Dive: SOLID and Pattern Summary

```
COMPLETE PATTERN CATALOG FOR TRAVEL BOOKING LLD:

STRATEGY PATTERN — THREE USES:
  
  1. Pricing Strategy (IPricingStrategy):
     DynamicPricingStrategy (most flights) vs FixedPricingStrategy (corporate contracts).
     Swap at runtime: corporate user → fixed pricing, retail user → dynamic.
     
  2. Cancellation Policy (ICancellationPolicy):
     Flexible / Moderate / Strict / NonRefundable.
     Different policies for different booking tiers.
     Adding "SuperFlexible" policy: new class only. Zero change to HotelBooking.
     
  3. GDS Provider (IGDS):
     Amadeus / Sabre / Travelport.
     Swap provider: one config change. All business logic unchanged.
  
  STRATEGY PATTERN TELLS THE INTERVIEWER:
    You understand Open/Closed Principle.
    You can design for extensibility without modification.
    You think in terms of behavior as an object, not hardcoded logic.

OBSERVER PATTERN — Booking Notifications:
  Subject: BookingService (emits booking events).
  Observers: EmailService, SMSService, PushNotificationService.
  
  When booking is confirmed:
    booking_service.notify_observers(BookingEvent.CONFIRMED, booking)
    
    → EmailService.on_event(): send confirmation email with e-ticket PDF.
    → SMSService.on_event(): send SMS "Booking confirmed! PNR: ABC123".
    → PushNotificationService.on_event(): push to user's mobile app.
  
  Adding WhatsApp notification: new WhatsAppService(IBookingObserver). Zero code change to BookingService.

COMPOSITE PATTERN — Itinerary:
  A trip = list of segments (flights, hotels, transfers).
  Each segment can be:
    Leaf: FlightBooking (atomic, indivisible)
    Composite: MultiCityItinerary (contains multiple FlightBookings + HotelBookings)
  
  Both implement IBooking:
    cancel() → leaf cancels one; composite cancels all with rollback.
    get_total_price() → leaf returns its own; composite sums children.
  
  Client code: treats individual bookings and multi-city itineraries identically.
  MakeMyTripService.cancel(booking_id) → doesn't know if it's a leaf or composite.

TEMPLATE METHOD — Payment Processing:
  Abstract flow: validate → hold inventory → process payment → confirm → notify.
  FlightBookingProcessor and HotelBookingProcessor:
    Both follow same template.
    "hold inventory" step differs (seats for flights, room count for hotels).
  
  Base class defines order of steps. Subclasses override the step-specific logic.

INTERVIEW TIP — How to narrate patterns to interviewers:
  
  Don't just say "I used Strategy Pattern."
  Say:
    "For cancellation policies, I used the Strategy Pattern.
    HotelBooking has a reference to ICancellationPolicy (an interface).
    The concrete policy (Flexible, Moderate, Strict) is injected at booking creation time.
    When the user cancels, HotelBooking calls policy.calculate_refund() — it doesn't need
    to know which specific policy it is.
    If the business adds a new 'Platinum' policy, I just write a new class.
    HotelBooking doesn't change. That's the Open/Closed Principle."
  
  This level of articulation = MAANG-level LLD interview performance.
```

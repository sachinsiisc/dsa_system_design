# CS09: LLD — Payment Gateway & Processor
## Razorpay / Stripe / PayU | Every Line Explained | Python + Java + C++

---

> **WHAT WE'RE BUILDING:**
> A payment gateway like Razorpay or Stripe.
> This sits between a merchant (e.g., Amazon) and the bank networks.
> It processes credit/debit cards, UPI, net banking, and wallets.
>
> **WHY THIS IS IMPORTANT:**
> Payment systems appear in EVERY real-world system design.
> Even Netflix, Uber, MakeMyTrip all use Razorpay/Stripe internally.
> MAANG loves asking: "How would you design a payment system?"

---

## STEP 1 — Requirements & Entities

```
FUNCTIONAL REQUIREMENTS:
  1. Merchant integrates our gateway (API key based)
  2. Customer initiates payment on merchant's site
  3. We collect payment method (card, UPI, wallet)
  4. We route to the appropriate bank / payment processor
  5. Bank approves or declines
  6. We notify merchant of success/failure (webhook)
  7. Merchant refunds (partial or full)
  8. Merchant sees transaction history and settlements
  9. We handle retries (if bank times out)
  10. Fraud detection (flag suspicious transactions)

KEY ENTITIES:
  Merchant          — business using our payment gateway (Amazon, Flipkart)
  Customer          — end user paying for something
  PaymentOrder      — created BEFORE payment (amount, currency, merchant)
  Payment           — the actual payment attempt (order + payment method + result)
  PaymentMethod     — card / UPI / wallet / net banking
  Card              — credit or debit card details (PAN, expiry, CVV)
  UPIPayment        — UPI ID or QR code payment
  Transaction       — final ledger entry after payment
  Refund            — partial or full reversal of a transaction
  PaymentProcessor  — routes to appropriate bank (Visa/Mastercard/NPCI)
  FraudDetector     — flags suspicious transactions
  WebhookService    — notifies merchant of payment events
  Settlement        — batch transfer of funds to merchant account

NON-FUNCTIONAL:
  99.99% uptime (4 nines = 52 min downtime/year)
  < 3 second payment confirmation
  PCI-DSS compliant (card data handling standards)
  Idempotent APIs (retry safe — double-click shouldn't charge twice)
```

---

## STEP 2 — Class Diagram

```
[Merchant]                    [Customer]                  [PaymentOrder]
──────────                    ──────────                  ──────────────
- id: UUID                    - id: UUID                  - id: UUID (= order_id in API)
- name: str                   - email: str                - merchant: Merchant
- api_key: str (hashed)       - phone: str                - customer: Customer
- webhook_url: str            - kyc_verified: bool        - amount: Decimal
- balance: Decimal            ──────────                  - currency: str ("INR","USD")
- is_active: bool             + create_payment_order()    - description: str
──────────                                                - status: OrderStatus
+ verify_api_key(): bool      [PaymentMethod] (Abstract)  - created_at: datetime
+ receive_webhook(): void     ──────────────────────────  - expires_at: datetime
                              - id: UUID                  ──────────────
[Payment]                     - customer: Customer        + is_valid(): bool
─────────                     - type: PaymentType         + mark_paid(): void
- id: UUID                    - is_default: bool
- order: PaymentOrder         ──────────────────────────  [Card] extends PaymentMethod
- method: PaymentMethod       + get_display_name(): str   - pan_last4: str
- amount: Decimal             + tokenize(): str           - pan_hash: str (NOT full PAN!)
- status: PaymentStatus                                   - expiry_month: int
- gateway_ref: str            [UPIPayment] extends PaymentMethod   - expiry_year: int
- failure_reason: str?        - vpa: str  ("sachin@paytm")         - cardholder_name: str
- created_at: datetime        + generate_collect_request(): str     - card_type: CardType
- attempts: int                                           - network: CardNetwork
─────────                     [Wallet] extends PaymentMethod        (VISA/MASTERCARD/RUPAY)
+ process(): PaymentResult    - wallet_type: WalletType
+ refund(amt): Refund         - balance: Decimal          [Transaction]
+ get_receipt(): Receipt      + debit(amount): bool       ─────────────
                                                          - id: UUID
[FraudSignal]                 [Refund]                    - payment: Payment
────────────                  ───────                     - type: TxType (CREDIT/DEBIT)
- risk_score: float (0-1)     - id: UUID                  - amount: Decimal
- signals: List[str]          - payment: Payment           - status: TxStatus
- is_blocked: bool            - amount: Decimal            - processed_at: datetime
                              - reason: str
                              - status: RefundStatus       [Settlement]
                              - processed_at: datetime?    ─────────────
                                                          - merchant: Merchant
                                                          - amount: Decimal
                                                          - transactions: List[Transaction]
                                                          - settled_at: datetime

PATTERNS:
  Strategy   → PaymentProcessor (CardProcessor/UPIProcessor/WalletProcessor)
  State      → Payment.status (PENDING→PROCESSING→COMPLETED/FAILED/REFUNDED)
  State      → PaymentOrder.status (CREATED→PAID/EXPIRED/CANCELLED)
  Observer   → WebhookService watches Payment state changes
  Template   → PaymentProcessor.process() skeleton, subtypes fill in bank communication
  Idempotency Key → Payment deduplication by idempotency_key field
  Builder    → PaymentOrderBuilder for complex order construction
```

---

## STEP 3 — Python Implementation (Every Line Explained)

```python
# payment_gateway_lld.py
from __future__ import annotations

import uuid
import hashlib
import hmac         # hmac = Hash-based Message Authentication Code
                    # Used for webhook signature verification (prove the webhook is from us)
import json
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
# Decimal: Python's fixed-precision decimal arithmetic.
# WHY NOT float? float is binary floating point. 0.1 + 0.2 = 0.30000000000000004 (bug!)
# In payments, $0.01 + $0.02 MUST equal $0.03, not $0.030000000000000004.
# Decimal uses decimal floating point — no rounding errors for money.
# ROUND_HALF_UP: 2.5 → 3 (standard rounding, not banker's rounding)

from enum import Enum, auto
from typing import Optional, List, Dict, Callable
from collections import defaultdict


# ══════════════════════════════════════════════════════════════════════════════
# ENUMS — All possible states
# ══════════════════════════════════════════════════════════════════════════════

class PaymentStatus(Enum):
    """
    STATE MACHINE for a Payment:
    
    PENDING → PROCESSING → COMPLETED (success)
                        → FAILED (bank declined)
                        → TIMED_OUT (no bank response in 30s)
    COMPLETED → REFUNDED (merchant issued refund)
    COMPLETED → PARTIALLY_REFUNDED
    
    WHY THESE STATES?
    Financial systems need EXACTLY these states to reconcile.
    A payment in PROCESSING state means: money may or may not have been taken.
    Bank must be queried (via "check payment status" API) to determine outcome.
    """
    PENDING             = "pending"        # Created, not yet attempted
    PROCESSING          = "processing"     # Sent to bank, waiting for response
    COMPLETED           = "completed"      # Bank confirmed payment
    FAILED              = "failed"         # Bank declined
    TIMED_OUT           = "timed_out"      # No bank response (indeterminate!)
    REFUNDED            = "refunded"       # Full refund issued
    PARTIALLY_REFUNDED  = "partially_refunded"  # Partial refund issued
    CANCELLED           = "cancelled"      # Cancelled before processing

class OrderStatus(Enum):
    CREATED  = "created"   # Order exists, awaiting payment
    PAID     = "paid"      # Payment completed
    EXPIRED  = "expired"   # Payment window expired (usually 15 minutes)
    CANCELLED = "cancelled"

class RefundStatus(Enum):
    PENDING    = "pending"     # Refund requested
    PROCESSING = "processing"  # Sent to bank
    COMPLETED  = "completed"   # Money returned to customer
    FAILED     = "failed"      # Refund failed (rare, but happens)

class PaymentType(Enum):
    CARD      = "card"         # Credit or debit card
    UPI       = "upi"          # Unified Payments Interface (India)
    WALLET    = "wallet"       # Paytm, PhonePe, etc.
    NET_BANKING = "net_banking" # Direct bank account transfer

class CardNetwork(Enum):
    VISA       = "visa"
    MASTERCARD = "mastercard"
    RUPAY      = "rupay"       # India's domestic card network
    AMEX       = "amex"

class CardType(Enum):
    CREDIT = "credit"
    DEBIT  = "debit"

class WalletType(Enum):
    PAYTM   = "paytm"
    PHONEPE = "phonepe"
    GPAY    = "gpay"


# ══════════════════════════════════════════════════════════════════════════════
# DOMAIN ENTITIES
# ══════════════════════════════════════════════════════════════════════════════

class Merchant:
    """
    A business that uses our payment gateway.
    Like Amazon, Flipkart, MakeMyTrip using Razorpay.
    """

    def __init__(self, name: str, webhook_url: str):
        self.id          = str(uuid.uuid4())
        self.name        = name
        self.webhook_url = webhook_url    # URL we call when payment completes
        self.is_active   = True
        self.balance     = Decimal("0.00")   # Decimal, not float (money!)
        
        # API key is what the merchant includes in every API call to authenticate.
        # We store the HASH of the key, not the key itself.
        # (If our DB is breached, attacker gets hashes — useless without the original)
        raw_key         = str(uuid.uuid4()).replace("-", "")  # 32-char random key
        self.api_key_prefix = raw_key[:8]   # "rzp_live" prefix shown to merchant
        self._api_key_hash  = self._hash_key(raw_key)
        self._raw_key       = raw_key       # Shown ONCE at creation, never again

    @staticmethod
    def _hash_key(key: str) -> str:
        """One-way hash of API key for storage."""
        return hashlib.sha256(key.encode()).hexdigest()
        # hashlib.sha256: SHA-256 hash algorithm.
        # .encode(): convert str to bytes (sha256 requires bytes).
        # .hexdigest(): return hash as 64-char hex string.

    def verify_api_key(self, provided_key: str) -> bool:
        """
        Verify an API key without ever comparing plain text keys.
        Uses constant-time comparison to prevent timing attacks.
        
        TIMING ATTACK: A naive '==' comparison short-circuits on first mismatched char.
        Attacker can measure response time to guess the key character by character.
        hmac.compare_digest() always takes the same time regardless of where strings differ.
        """
        provided_hash = self._hash_key(provided_key)
        return hmac.compare_digest(self._api_key_hash, provided_hash)
        # hmac.compare_digest: constant-time string comparison.
        # Prevents timing side-channel attacks.

    def get_raw_key(self) -> str:
        """Return the raw API key (only for initial display to merchant)."""
        return self._raw_key


class Customer:
    """End user making a payment."""

    def __init__(self, email: str, phone: str):
        self.id           = str(uuid.uuid4())
        self.email        = email
        self.phone        = phone
        self.kyc_verified = False
        self._payment_methods: List[PaymentMethod] = []
        self._lock        = threading.Lock()

    def add_payment_method(self, method: PaymentMethod) -> None:
        with self._lock:
            self._payment_methods.append(method)

    def get_payment_methods(self) -> List[PaymentMethod]:
        with self._lock:
            return list(self._payment_methods)   # Return a copy (defensive copy)


class PaymentMethod(ABC):
    """
    ABSTRACT BASE CLASS for all payment methods.
    Card, UPI, Wallet, NetBanking all extend this.
    
    TOKENIZATION:
    We NEVER store actual card numbers (PCI-DSS compliance).
    Card numbers are tokenized: actual PAN → a token.
    Token is stored; actual PAN is sent to payment network and discarded.
    """

    def __init__(self, customer: Customer, payment_type: PaymentType):
        self.id           = str(uuid.uuid4())
        self.customer     = customer
        self.type         = payment_type
        self.is_default   = False
        self.created_at   = datetime.utcnow()

    @abstractmethod
    def get_display_name(self) -> str:
        """Human-readable name shown to customer (e.g., "VISA ending in 4242")."""
        ...

    @abstractmethod
    def tokenize(self) -> str:
        """
        Tokenize sensitive payment data.
        Returns a token (safe to store) instead of sensitive data.
        
        WHY TOKENIZE?
        PCI-DSS requirement: card numbers cannot be stored in plain text.
        Token: opaque string that represents the payment method.
        Only the payment network (Visa/Mastercard) can map token → real card.
        """
        ...


class Card(PaymentMethod):
    """
    Credit or debit card payment method.
    
    PAN = Primary Account Number (the 16-digit card number).
    We NEVER store the full PAN. Only last 4 digits (for display) and a hash.
    
    The CVV is NEVER stored at all (Visa/Mastercard prohibit it).
    CVV is used once during authorization, then discarded.
    """

    def __init__(self, customer: Customer, pan: str, expiry_month: int,
                 expiry_year: int, cardholder_name: str,
                 card_type: CardType, network: CardNetwork):
        super().__init__(customer, PaymentType.CARD)
        
        # SECURITY: Don't store full PAN!
        self.pan_last4 = pan[-4:]     # Last 4 digits only (for display)
        # pan[-4:] = Python slice: take last 4 characters
        
        self.pan_hash = hashlib.sha256(pan.encode()).hexdigest()
        # Hash of full PAN: used to detect duplicate card additions.
        # Can't reverse the hash to get the PAN (one-way).
        
        # CVV is NOT stored at all. Only passed to bank during authorization.
        # We hold it only in memory during the request, never write to disk.
        
        self.expiry_month     = expiry_month
        self.expiry_year      = expiry_year
        self.cardholder_name  = cardholder_name
        self.card_type        = card_type
        self.network          = network
        
        # Token from payment network (Visa Token Service / Mastercard MDES)
        self._token: Optional[str] = None

    def is_expired(self) -> bool:
        """Has this card's validity period passed?"""
        now = datetime.utcnow()
        # Card expires at END of expiry_month in expiry_year
        # If expiry is "12/2025", card is valid through December 31, 2025
        if now.year > self.expiry_year:
            return True
        if now.year == self.expiry_year and now.month > self.expiry_month:
            return True
        return False

    def get_display_name(self) -> str:
        return f"{self.network.value.capitalize()} {self.card_type.value} ••••{self.pan_last4}"
        # Example: "Visa debit ••••4242"
        # .capitalize() → "Visa" (not "VISA")
        # "••••" = masked representation of first 12 digits

    def tokenize(self) -> str:
        """
        Generate a token for this card.
        
        REAL IMPLEMENTATION:
        Send card to Visa Token Service (VTS) or Mastercard MDES.
        They store the real PAN and return a token.
        We store the token and use it for future payments.
        
        HERE: simplified simulation.
        """
        if not self._token:
            self._token = f"tok_{hashlib.md5(self.pan_hash.encode()).hexdigest()[:16]}"
            # In production: API call to Visa/Mastercard tokenization service
        return self._token


class UPIPayment(PaymentMethod):
    """
    UPI (Unified Payments Interface) — India's real-time payment system.
    Works via VPA (Virtual Payment Address): "sachin@paytm", "9876543210@ybl"
    """

    def __init__(self, customer: Customer, vpa: str):
        super().__init__(customer, PaymentType.UPI)
        self.vpa = vpa.lower()   # VPAs are case-insensitive; normalize to lowercase
        # Example VPAs: sachin@paytm, 9876543210@ybl, merchant@okaxis

    def get_display_name(self) -> str:
        return f"UPI: {self.vpa}"

    def tokenize(self) -> str:
        # VPAs don't need real tokenization (not sensitive like card numbers)
        return f"upi_{hashlib.md5(self.vpa.encode()).hexdigest()[:16]}"

    def generate_collect_request(self, amount: Decimal) -> str:
        """
        Generate a UPI collect request URL.
        Customer's UPI app receives a notification to approve this amount.
        
        UPI Deep Link format:
        upi://pay?pa={vpa}&am={amount}&cu=INR&tn={note}
        """
        return f"upi://pay?pa={self.vpa}&am={amount}&cu=INR&tn=Payment"


class Wallet(PaymentMethod):
    """Digital wallet (Paytm, PhonePe, GPay)."""

    def __init__(self, customer: Customer, wallet_type: WalletType, balance: Decimal):
        super().__init__(customer, PaymentType.WALLET)
        self.wallet_type = wallet_type
        self._balance    = balance          # Current wallet balance
        self._lock       = threading.Lock()

    def get_display_name(self) -> str:
        return f"{self.wallet_type.value.capitalize()} Wallet (₹{self._balance:.2f})"

    def tokenize(self) -> str:
        return f"wallet_{self.wallet_type.value}_{self.customer.id[:8]}"

    def debit(self, amount: Decimal) -> bool:
        """
        Debit amount from wallet.
        Returns True if successful (sufficient balance), False if insufficient.
        
        Decimal comparison: Decimal("100.00") > Decimal("50.00") works correctly.
        Would NOT work with float: 0.1 + 0.2 != 0.3 (floating point error).
        """
        with self._lock:
            if self._balance < amount:
                return False   # Insufficient balance
            self._balance -= amount
            return True

    def credit(self, amount: Decimal) -> None:
        """Credit (add) to wallet (e.g., refund)."""
        with self._lock:
            self._balance += amount

    @property
    def balance(self) -> Decimal:
        with self._lock:
            return self._balance


# ══════════════════════════════════════════════════════════════════════════════
# PAYMENT ORDER
# ══════════════════════════════════════════════════════════════════════════════

class PaymentOrder:
    """
    Created BEFORE actual payment.
    Merchant creates an order → customer pays against this order.
    
    WHY HAVE BOTH ORDER AND PAYMENT?
    Order = merchant's intent ("I want ₹500 for booking #123")
    Payment = customer's attempt to pay for that order.
    One order can have MULTIPLE payment attempts (retry after failure).
    The order tracks whether ANYTHING was paid; Payment tracks each attempt.
    
    IDEMPOTENCY:
    If merchant calls create_order() twice for the same booking, they get the SAME order.
    This prevents double-charging on network timeouts.
    """

    ORDER_TTL_MINUTES = 15   # Order expires in 15 minutes if not paid

    def __init__(self, merchant: Merchant, customer: Customer,
                 amount: Decimal, currency: str, description: str,
                 idempotency_key: str = None):
        self.id              = str(uuid.uuid4())
        self.merchant        = merchant
        self.customer        = customer
        self.amount          = amount
        self.currency        = currency.upper()   # "INR", "USD" — always uppercase
        self.description     = description
        self.idempotency_key = idempotency_key    # Merchant-provided dedup key
        self.status          = OrderStatus.CREATED
        self.created_at      = datetime.utcnow()
        self.expires_at      = self.created_at + timedelta(minutes=self.ORDER_TTL_MINUTES)
        self._payments:  List[str] = []   # List of payment IDs (attempts)
        self._lock       = threading.Lock()

    def is_valid(self) -> bool:
        """Can a payment be attempted against this order?"""
        if self.status == OrderStatus.PAID:       return False   # Already paid
        if self.status == OrderStatus.CANCELLED:  return False   # Cancelled
        if self.status == OrderStatus.EXPIRED:    return False   # Expired
        if datetime.utcnow() > self.expires_at:
            # Order time window has passed — mark as expired
            with self._lock: self.status = OrderStatus.EXPIRED
            return False
        return True

    def mark_paid(self) -> None:
        with self._lock:
            self.status = OrderStatus.PAID

    def add_payment_attempt(self, payment_id: str) -> None:
        with self._lock:
            self._payments.append(payment_id)


# ══════════════════════════════════════════════════════════════════════════════
# PAYMENT
# ══════════════════════════════════════════════════════════════════════════════

class Payment:
    """
    An actual payment attempt.
    Linked to a PaymentOrder (which it's paying for).
    
    One PaymentOrder can have multiple Payments (retries after failure).
    But only ONE Payment per order can COMPLETE successfully.
    """

    MAX_RETRY_ATTEMPTS = 3   # Max times customer can retry

    def __init__(self, order: PaymentOrder, method: PaymentMethod,
                 amount: Decimal):
        self.id              = str(uuid.uuid4())
        self.order           = order
        self.method          = method
        self.amount          = amount
        self._status         = PaymentStatus.PENDING
        self.gateway_ref     = None   # Reference from bank/payment network
        self.failure_reason  = None   # Why it failed (if failed)
        self.created_at      = datetime.utcnow()
        self.attempts        = 0
        self._refunds:       List[Refund] = []
        self._lock           = threading.RLock()

    def transition_to(self, new_status: PaymentStatus,
                      gateway_ref: str = None, failure_reason: str = None) -> None:
        """
        STATE TRANSITION: validates and applies status change.
        
        VALID TRANSITIONS:
        PENDING     → PROCESSING (payment initiated)
        PROCESSING  → COMPLETED  (bank approved)
        PROCESSING  → FAILED     (bank declined)
        PROCESSING  → TIMED_OUT  (no bank response)
        COMPLETED   → REFUNDED   (full refund)
        COMPLETED   → PARTIALLY_REFUNDED (partial refund)
        """
        VALID_TRANSITIONS = {
            PaymentStatus.PENDING:     {PaymentStatus.PROCESSING, PaymentStatus.CANCELLED},
            PaymentStatus.PROCESSING:  {PaymentStatus.COMPLETED, PaymentStatus.FAILED, PaymentStatus.TIMED_OUT},
            PaymentStatus.COMPLETED:   {PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED},
            PaymentStatus.PARTIALLY_REFUNDED: {PaymentStatus.REFUNDED},
        }

        with self._lock:
            allowed = VALID_TRANSITIONS.get(self._status, set())
            if new_status not in allowed:
                raise ValueError(
                    f"Invalid transition: {self._status.value} → {new_status.value}"
                )
            self._status     = new_status
            if gateway_ref:
                self.gateway_ref = gateway_ref
            if failure_reason:
                self.failure_reason = failure_reason

    def create_refund(self, amount: Decimal, reason: str) -> Refund:
        """
        Initiate a refund for this payment.
        
        RULES:
        - Can only refund COMPLETED payments.
        - Total refunded ≤ original payment amount.
        - Multiple partial refunds allowed.
        """
        with self._lock:
            if self._status not in (PaymentStatus.COMPLETED, PaymentStatus.PARTIALLY_REFUNDED):
                raise ValueError(f"Cannot refund a payment in status {self._status.value}")
            
            total_refunded = sum(r.amount for r in self._refunds
                                 if r.status != RefundStatus.FAILED)
            # sum() with a generator: calculates total of all non-failed refunds
            
            remaining = self.amount - total_refunded
            if amount > remaining:
                raise ValueError(
                    f"Refund amount ₹{amount} exceeds remaining refundable ₹{remaining}"
                )
            
            refund = Refund(self, amount, reason)
            self._refunds.append(refund)
            
            new_refunded = total_refunded + amount
            if new_refunded >= self.amount:
                self._status = PaymentStatus.REFUNDED
            else:
                self._status = PaymentStatus.PARTIALLY_REFUNDED
            
            return refund

    @property
    def status(self) -> PaymentStatus:
        with self._lock: return self._status

    def total_refunded(self) -> Decimal:
        with self._lock:
            return sum((r.amount for r in self._refunds if r.status != RefundStatus.FAILED),
                       Decimal("0.00"))
            # sum() with start value: second argument is start value.
            # Prevents TypeError if list is empty (sum of empty = start value = 0.00).


@dataclass
class Refund:
    """A refund request for a payment."""
    payment:      Payment
    amount:       Decimal
    reason:       str
    id:           str = field(default_factory=lambda: str(uuid.uuid4()))
    status:       RefundStatus = RefundStatus.PENDING
    processed_at: Optional[datetime] = None

    def process(self, success: bool) -> None:
        """Mark refund as completed or failed."""
        self.status       = RefundStatus.COMPLETED if success else RefundStatus.FAILED
        self.processed_at = datetime.utcnow()


# ══════════════════════════════════════════════════════════════════════════════
# PAYMENT PROCESSOR — Strategy + Template Method
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class PaymentResult:
    """Result from bank/payment network."""
    success:     bool
    gateway_ref: str          # Bank's transaction reference ID
    status:      PaymentStatus
    failure_reason: Optional[str] = None


class IPaymentProcessor(ABC):
    """
    STRATEGY INTERFACE for payment processors.
    
    Different payment methods need different processors:
    - CardProcessor → Visa/Mastercard network
    - UPIProcessor  → NPCI (National Payments Corporation of India)
    - WalletProcessor → Paytm/PhonePe APIs
    
    TEMPLATE METHOD:
    process() defines the skeleton:
      1. validate()
      2. _authorize() — abstract (each processor implements differently)
      3. _capture()   — abstract
      4. return result
    """

    @abstractmethod
    def _validate(self, payment: Payment) -> None:
        """Validate payment method is usable (not expired, sufficient balance, etc.)."""
        ...

    @abstractmethod
    def _authorize(self, payment: Payment) -> PaymentResult:
        """
        Step 1: Ask bank "Can this payment method pay ₹X?"
        Bank checks: available credit/balance, fraud score, card validity.
        Returns: authorized or declined (no money moves yet).
        """
        ...

    @abstractmethod
    def _capture(self, payment: Payment, auth_result: PaymentResult) -> PaymentResult:
        """
        Step 2: Tell bank "Yes, capture the authorized amount."
        Money actually moves from customer to merchant's escrow.
        
        TWO-STEP AUTH + CAPTURE vs ONE-STEP:
        Auth-then-Capture: hotel holds ₹5000, captures actual bill ₹4200.
        Direct charge: most e-commerce (capture immediately after auth).
        """
        ...

    def process(self, payment: Payment) -> PaymentResult:
        """
        TEMPLATE METHOD: defines the algorithm. Subclasses fill in steps.
        This method is NOT abstract — it calls abstract sub-steps.
        """
        try:
            payment.attempts += 1
            payment.transition_to(PaymentStatus.PROCESSING)
            
            # Step 1: Validate (is card expired? is UPI VPA valid?)
            self._validate(payment)
            
            # Step 2: Authorize (check with bank if payment can go through)
            auth_result = self._authorize(payment)
            
            if not auth_result.success:
                # Authorization failed — payment rejected by bank
                payment.transition_to(PaymentStatus.FAILED,
                                      failure_reason=auth_result.failure_reason)
                return auth_result
            
            # Step 3: Capture (money moves)
            final_result = self._capture(payment, auth_result)
            
            if final_result.success:
                payment.transition_to(PaymentStatus.COMPLETED,
                                      gateway_ref=final_result.gateway_ref)
                payment.order.mark_paid()
            else:
                payment.transition_to(PaymentStatus.FAILED,
                                      failure_reason=final_result.failure_reason)
            
            return final_result

        except TimeoutError:
            # No response from bank within timeout period
            payment.transition_to(PaymentStatus.TIMED_OUT)
            return PaymentResult(False, "", PaymentStatus.TIMED_OUT,
                                 "Payment timed out — please check payment status")


class CardProcessor(IPaymentProcessor):
    """
    Processes credit/debit card payments via Visa/Mastercard network.
    
    REAL FLOW:
    1. We send card token + amount to payment network (Visa/MC)
    2. Network checks with issuing bank (customer's bank)
    3. Issuing bank checks: available balance, fraud score, 3D Secure
    4. Returns: approved/declined
    5. On approval: we capture (money moves to acquiring bank escrow)
    6. After settlement period (T+2): money arrives in merchant's account
    """

    def _validate(self, payment: Payment) -> None:
        card = payment.method
        if not isinstance(card, Card):
            raise ValueError("CardProcessor requires a Card payment method")
        if card.is_expired():
            raise ValueError(f"Card expired ({card.expiry_month}/{card.expiry_year})")

    def _authorize(self, payment: Payment) -> PaymentResult:
        """
        Simulate authorization (in production: API call to Visa/Mastercard).
        In real system: this is a synchronous HTTP call to payment network.
        Timeout: 30 seconds max.
        """
        card = payment.method
        
        # SIMULATION: In real system, this is an API call.
        # We simulate 90% success rate.
        import random
        success = random.random() > 0.1   # 90% approval rate

        if success:
            auth_ref = f"AUTH_{uuid.uuid4().hex[:8].upper()}"
            return PaymentResult(True, auth_ref, PaymentStatus.PROCESSING)
        else:
            return PaymentResult(False, "", PaymentStatus.FAILED,
                                 "Insufficient funds")

    def _capture(self, payment: Payment, auth_result: PaymentResult) -> PaymentResult:
        """
        Simulate capture (in production: another API call to payment network).
        In real Stripe: auth + capture can be combined into one call (charge).
        """
        capture_ref = f"CAP_{uuid.uuid4().hex[:8].upper()}"
        return PaymentResult(True, capture_ref, PaymentStatus.COMPLETED)


class UPIProcessor(IPaymentProcessor):
    """
    Processes UPI payments via NPCI (National Payments Corporation of India).
    
    REAL UPI FLOW:
    1. Customer initiates UPI payment (scans QR or enters VPA)
    2. Customer's UPI app sends collect request to their bank (PSP)
    3. Customer approves in their UPI app
    4. NPCI debits customer's bank, credits merchant's bank
    5. Response: success/failure/pending (if customer doesn't approve)
    
    CHALLENGE: UPI is asynchronous.
    Customer must manually approve in their app. This can take 10-60 seconds.
    We poll NPCI for status (or receive callback).
    """

    def _validate(self, payment: Payment) -> None:
        upi = payment.method
        if not isinstance(upi, UPIPayment):
            raise ValueError("UPIProcessor requires a UPI payment method")
        if "@" not in upi.vpa:
            raise ValueError(f"Invalid VPA format: {upi.vpa}")

    def _authorize(self, payment: Payment) -> PaymentResult:
        """
        In real UPI: send collect request to NPCI.
        Customer approves in their UPI app.
        We poll NPCI every 3 seconds for up to 60 seconds.
        """
        upi = payment.method
        print(f"UPI collect request sent to {upi.vpa}. Awaiting approval...")
        
        # SIMULATION: Immediate approval (in reality: wait for customer)
        import random
        if random.random() > 0.05:   # 95% approval (UPI approval rate is high)
            return PaymentResult(True, f"UPI_{uuid.uuid4().hex[:12].upper()}",
                                 PaymentStatus.PROCESSING)
        return PaymentResult(False, "", PaymentStatus.FAILED, "Payment declined by customer")

    def _capture(self, payment: Payment, auth_result: PaymentResult) -> PaymentResult:
        # UPI is a "pull" payment — authorization already moves money (no separate capture)
        return PaymentResult(True, auth_result.gateway_ref, PaymentStatus.COMPLETED)


class WalletProcessor(IPaymentProcessor):
    """Processes wallet payments (Paytm, PhonePe)."""

    def _validate(self, payment: Payment) -> None:
        wallet = payment.method
        if not isinstance(wallet, Wallet):
            raise ValueError("WalletProcessor requires a Wallet payment method")
        if wallet.balance < payment.amount:
            raise ValueError(
                f"Insufficient wallet balance. Have: ₹{wallet.balance}, "
                f"Need: ₹{payment.amount}"
            )

    def _authorize(self, payment: Payment) -> PaymentResult:
        wallet = payment.method
        success = wallet.debit(payment.amount)
        # Immediately debit the wallet (wallets are real-time, no bank involved)
        if success:
            return PaymentResult(True, f"WLT_{uuid.uuid4().hex[:8].upper()}",
                                 PaymentStatus.PROCESSING)
        return PaymentResult(False, "", PaymentStatus.FAILED, "Wallet debit failed")

    def _capture(self, payment: Payment, auth_result: PaymentResult) -> PaymentResult:
        # Already debited in authorize step
        return PaymentResult(True, auth_result.gateway_ref, PaymentStatus.COMPLETED)


# ══════════════════════════════════════════════════════════════════════════════
# FRAUD DETECTOR
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class FraudSignal:
    """Result of fraud analysis."""
    risk_score:  float       # 0.0 (safe) to 1.0 (certain fraud)
    signals:     List[str]   # List of triggered fraud rules
    is_blocked:  bool        # Should this payment be blocked?


class FraudDetector:
    """
    Simple rule-based fraud detection.
    
    REAL SYSTEMS use ML models (Random Forest, Neural Networks).
    Rules here demonstrate the concept.
    
    FRAUD SIGNALS:
    - High amount for new customer
    - Many attempts in short time (velocity check)
    - Card used from unusual location
    - Multiple cards from same IP
    - Night-time transactions in unusual patterns
    """

    def __init__(self):
        self._attempt_counts: Dict[str, List[float]] = defaultdict(list)
        # customer_id → list of timestamps of recent payment attempts
        # Used for velocity check (too many attempts in short time = suspicious)
        self._lock = threading.Lock()

    def analyze(self, payment: Payment) -> FraudSignal:
        """
        Analyze a payment for fraud signals.
        Returns FraudSignal with risk score and whether to block.
        """
        signals = []
        risk_score = 0.0

        # RULE 1: High velocity — too many attempts in 5 minutes
        velocity_risk = self._check_velocity(payment.order.customer.id)
        if velocity_risk > 0.5:
            signals.append(f"High velocity: {velocity_risk:.0%} risk")
            risk_score += velocity_risk * 0.4   # Weight this signal at 40%

        # RULE 2: Large amount for customer with no history
        if payment.amount > Decimal("50000"):   # > ₹50,000
            signals.append("Large transaction amount")
            risk_score += 0.2   # Add 20% risk

        # RULE 3: Card payment with unusual amount (round numbers are suspicious)
        if (isinstance(payment.method, Card)
                and payment.amount % Decimal("1000") == 0
                and payment.amount > Decimal("10000")):
            signals.append("Suspicious round amount (possible test fraud)")
            risk_score += 0.1

        risk_score = min(risk_score, 1.0)   # Cap at 1.0
        is_blocked = risk_score > 0.8        # Block if risk > 80%

        return FraudSignal(
            risk_score=risk_score,
            signals=signals,
            is_blocked=is_blocked
        )

    def _check_velocity(self, customer_id: str) -> float:
        """
        Velocity check: how many payment attempts in last 5 minutes?
        Returns risk score 0.0–1.0.
        """
        now = time.time()
        five_min_ago = now - 300   # 300 seconds = 5 minutes
        
        with self._lock:
            # Record this attempt
            self._attempt_counts[customer_id].append(now)
            # Keep only last 5 minutes of attempts
            self._attempt_counts[customer_id] = [
                t for t in self._attempt_counts[customer_id]
                if t > five_min_ago
            ]
            count = len(self._attempt_counts[customer_id])
        
        # Score: 0 = 1 attempt, 1.0 = 10+ attempts in 5 min
        return min(count / 10.0, 1.0)
        # count=1 → 0.1, count=5 → 0.5, count=10+ → 1.0


# ══════════════════════════════════════════════════════════════════════════════
# WEBHOOK SERVICE — Observer Pattern
# ══════════════════════════════════════════════════════════════════════════════

class WebhookService:
    """
    OBSERVER PATTERN:
    When Payment status changes → notify merchant via webhook.
    
    WEBHOOKS:
    A webhook is an HTTP POST request WE make to the merchant's server.
    Contains event data: payment_id, status, amount, etc.
    
    WHY WEBHOOKS vs polling?
    Polling: merchant's server asks us "did payment complete?" every 5 seconds. Wasteful.
    Webhook: we push notification immediately when something happens. Efficient.
    
    WEBHOOK SECURITY:
    We sign the webhook payload with HMAC-SHA256 using merchant's webhook secret.
    Merchant verifies signature before trusting the data.
    Prevents: fake webhooks from malicious actors claiming payment succeeded.
    """

    def __init__(self):
        self._pending: List[dict] = []          # Webhooks not yet delivered
        self._delivered: List[dict] = []        # Successful deliveries
        self._lock = threading.Lock()

    def send(self, merchant: Merchant, event_type: str, payment: Payment) -> bool:
        """
        Send a webhook notification to the merchant.
        
        PAYLOAD: JSON with payment details.
        SIGNATURE: HMAC-SHA256 of payload using merchant's secret.
        """
        payload = {
            "event":      event_type,           # "payment.completed", "payment.failed"
            "payment_id": payment.id,
            "order_id":   payment.order.id,
            "amount":     str(payment.amount),  # Decimal → str for JSON serialization
            "currency":   payment.order.currency,
            "status":     payment.status.value,
            "timestamp":  datetime.utcnow().isoformat()
        }

        payload_json = json.dumps(payload, sort_keys=True)
        # json.dumps: convert dict to JSON string.
        # sort_keys=True: sort keys alphabetically — ensures same key order every time.
        # WHY? Signature is computed on the JSON string. Key order must be consistent.

        # Sign the payload:
        signature = hmac.new(
            key=merchant._api_key_hash.encode(),   # Secret key (merchant-specific)
            msg=payload_json.encode(),              # Message to sign
            digestmod=hashlib.sha256               # Hash algorithm
        ).hexdigest()
        # hmac.new creates an HMAC object.
        # .hexdigest() returns the 64-char hex signature.
        # Merchant verifies: hmac.compare_digest(our_sig, their_computed_sig) == True

        webhook_data = {
            "url":       merchant.webhook_url,
            "payload":   payload,
            "signature": signature,
            "sent_at":   datetime.utcnow().isoformat()
        }

        # SIMULATE sending (in production: HTTP POST with retry logic)
        print(f"→ Webhook to {merchant.webhook_url}: {event_type} "
              f"| Payment: {payment.id[:8]}... | Status: {payment.status.value}")
        
        with self._lock:
            self._delivered.append(webhook_data)
        
        return True   # Simulate success

    def get_webhook_history(self) -> List[dict]:
        with self._lock:
            return list(self._delivered)


# ══════════════════════════════════════════════════════════════════════════════
# PAYMENT GATEWAY SERVICE — Facade
# ══════════════════════════════════════════════════════════════════════════════

class PaymentGatewayService:
    """
    FACADE: The main entry point for the entire payment gateway.
    
    WHAT IT DOES:
    1. Merchant creates an order
    2. Customer makes a payment against that order
    3. Fraud detection runs
    4. Appropriate processor handles the payment
    5. Webhook sent to merchant
    6. Refunds handled
    
    IDEMPOTENCY:
    Merchants include an idempotency_key with each request.
    If same key is seen twice (retry due to timeout), return same response.
    Prevents double charges.
    """

    def __init__(self):
        self._merchants:    Dict[str, Merchant]     = {}
        self._customers:    Dict[str, Customer]     = {}
        self._orders:       Dict[str, PaymentOrder] = {}
        self._payments:     Dict[str, Payment]      = {}
        self._idempotency:  Dict[str, str]          = {}   # key → payment_id
        self._processors:   Dict[PaymentType, IPaymentProcessor] = {
            PaymentType.CARD:   CardProcessor(),
            PaymentType.UPI:    UPIProcessor(),
            PaymentType.WALLET: WalletProcessor(),
        }
        self._fraud     = FraudDetector()
        self._webhooks  = WebhookService()
        self._lock      = threading.RLock()

    def register_merchant(self, name: str, webhook_url: str) -> Merchant:
        merchant = Merchant(name, webhook_url)
        with self._lock:
            self._merchants[merchant.id] = merchant
        print(f"Merchant registered: {name}")
        print(f"API Key (save this, shown only once): {merchant.get_raw_key()}")
        return merchant

    def create_order(self, merchant: Merchant, customer: Customer,
                     amount: Decimal, currency: str, description: str,
                     idempotency_key: str = None) -> PaymentOrder:
        """
        Create a payment order.
        Idempotent: same key → same order returned (no duplicate).
        """
        # IDEMPOTENCY CHECK:
        if idempotency_key:
            with self._lock:
                if idempotency_key in self._idempotency:
                    existing_order_id = self._idempotency[idempotency_key]
                    print(f"Idempotency hit! Returning existing order: {existing_order_id[:8]}...")
                    return self._orders[existing_order_id]

        # Amount validation:
        if amount <= Decimal("0"):
            raise ValueError("Amount must be positive")
        
        # Round to 2 decimal places (paisa for INR):
        amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        # Decimal.quantize: round to specified precision.
        # ROUND_HALF_UP: 2.545 → 2.55 (standard rounding, not banker's rounding).

        order = PaymentOrder(merchant, customer, amount, currency,
                             description, idempotency_key)
        with self._lock:
            self._orders[order.id] = order
            if idempotency_key:
                self._idempotency[idempotency_key] = order.id

        print(f"Order created: {order.id[:8]}... | ₹{amount} | {description}")
        return order

    def process_payment(self, order: PaymentOrder,
                        payment_method: PaymentMethod) -> Payment:
        """
        The main payment processing flow.
        
        FLOW:
        1. Validate order is still valid (not expired, not already paid)
        2. Fraud detection
        3. Route to correct processor
        4. Update payment status
        5. Send webhook to merchant
        """
        if not order.is_valid():
            raise ValueError(f"Order {order.id[:8]}... is not valid "
                             f"(status: {order.status.value})")

        payment = Payment(order, payment_method, order.amount)
        with self._lock:
            self._payments[payment.id] = payment
        order.add_payment_attempt(payment.id)

        # FRAUD DETECTION:
        fraud_signal = self._fraud.analyze(payment)
        if fraud_signal.is_blocked:
            payment.transition_to(PaymentStatus.FAILED,
                                  failure_reason=f"Blocked by fraud detection: "
                                                 f"{', '.join(fraud_signal.signals)}")
            print(f"❌ Payment BLOCKED (fraud score: {fraud_signal.risk_score:.2f})")
            return payment
        
        if fraud_signal.risk_score > 0.3:
            print(f"⚠ Fraud warning (score: {fraud_signal.risk_score:.2f}): "
                  f"{fraud_signal.signals}")

        # ROUTE TO PROCESSOR:
        processor = self._processors.get(payment_method.type)
        if not processor:
            raise ValueError(f"No processor for payment type: {payment_method.type.value}")

        result = processor.process(payment)

        # SEND WEBHOOK:
        event = ("payment.completed" if result.success
                 else "payment.failed")
        self._webhooks.send(order.merchant, event, payment)

        status_icon = "✅" if result.success else "❌"
        print(f"{status_icon} Payment {payment.id[:8]}... | "
              f"Status: {payment.status.value} | "
              f"Ref: {result.gateway_ref or 'N/A'}")
        return payment

    def refund(self, payment: Payment, amount: Decimal,
               reason: str = "Customer request") -> Refund:
        """Issue a refund for a completed payment."""
        refund = payment.create_refund(amount, reason)
        # In production: API call to bank to reverse the charge
        # Here: simulate immediate success
        refund.process(success=True)
        
        # Send refund webhook
        self._webhooks.send(payment.order.merchant, "refund.processed", payment)
        print(f"↩ Refund: ₹{amount} for payment {payment.id[:8]}...")
        return refund


# ══════════════════════════════════════════════════════════════════════════════
# DEMO
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    gateway = PaymentGatewayService()

    # Merchant setup
    amazon = gateway.register_merchant("Amazon India",
                                       "https://amazon.in/payments/webhook")

    # Customer setup
    sachin = Customer("sachin@gmail.com", "+91-9876543210")
    visa_card = Card(sachin, pan="4111111111111111",
                     expiry_month=12, expiry_year=2027,
                     cardholder_name="Sachin Kumar",
                     card_type=CardType.DEBIT,
                     network=CardNetwork.VISA)
    upi = UPIPayment(sachin, "sachin@paytm")
    paytm_wallet = Wallet(sachin, WalletType.PAYTM, Decimal("2000.00"))
    sachin.add_payment_method(visa_card)
    sachin.add_payment_method(upi)
    sachin.add_payment_method(paytm_wallet)

    print("\n" + "="*60)
    print("TEST 1: Card Payment")
    print("="*60)
    order1 = gateway.create_order(
        amazon, sachin,
        amount=Decimal("999.00"),
        currency="INR",
        description="iPhone 15 case",
        idempotency_key="booking_001"    # Same key → same order if retried
    )
    payment1 = gateway.process_payment(order1, visa_card)

    print("\n" + "="*60)
    print("TEST 2: Idempotency (retry same order)")
    print("="*60)
    order1_retry = gateway.create_order(
        amazon, sachin,
        amount=Decimal("999.00"),
        currency="INR",
        description="iPhone 15 case",
        idempotency_key="booking_001"    # Same key → should return same order
    )
    print(f"Same order? {order1.id == order1_retry.id}")   # True

    print("\n" + "="*60)
    print("TEST 3: UPI Payment")
    print("="*60)
    order2 = gateway.create_order(
        amazon, sachin, Decimal("2499.00"), "INR", "Wireless earphones"
    )
    payment2 = gateway.process_payment(order2, upi)

    print("\n" + "="*60)
    print("TEST 4: Wallet Payment")
    print("="*60)
    order3 = gateway.create_order(
        amazon, sachin, Decimal("500.00"), "INR", "Book: Clean Code"
    )
    payment3 = gateway.process_payment(order3, paytm_wallet)

    print("\n" + "="*60)
    print("TEST 5: Refund")
    print("="*60)
    if payment3.status == PaymentStatus.COMPLETED:
        refund = gateway.refund(payment3, Decimal("500.00"), "Item out of stock")
        print(f"Refund status: {refund.status.value}")
        print(f"Payment status after refund: {payment3.status.value}")
```

---

## STEP 4 — Java Key Patterns

```java
// ── Key Java-specific patterns for Payment Gateway ────────────────────────────

// BigDecimal for money (NEVER use double/float for money in Java)
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal amount = new BigDecimal("999.00");
// WHY BigDecimal? Same reason as Python Decimal: no floating point errors.
// new BigDecimal("999.00") — always use String constructor (not double)!
// new BigDecimal(999.00) is wrong: 999.00 might not be exactly representable in binary.

amount = amount.setScale(2, RoundingMode.HALF_UP);
// setScale(2) = 2 decimal places. HALF_UP = standard rounding (0.5 → 1).

// ── AtomicReference for Payment Status ────────────────────────────────────────
class Payment {
    private final AtomicReference<PaymentStatus> status
        = new AtomicReference<>(PaymentStatus.PENDING);

    boolean transitionTo(PaymentStatus expected, PaymentStatus next) {
        return status.compareAndSet(expected, next);
        // CAS: if current == expected → set to next (returns true).
        // If another thread already changed status → returns false (retry).
        // This guarantees only ONE thread can perform each status transition.
    }

    void process() {
        if (!transitionTo(PaymentStatus.PENDING, PaymentStatus.PROCESSING))
            throw new IllegalStateException("Payment not in PENDING state");
        // Atomic: only succeeds if we're PENDING. Prevents double-processing.
    }
}

// ── Idempotency with ConcurrentHashMap.computeIfAbsent ────────────────────────
class PaymentGateway {
    private final ConcurrentHashMap<String, String> idempotencyMap = new ConcurrentHashMap<>();

    PaymentOrder createOrder(String idempotencyKey, BigDecimal amount, String desc) {
        String orderId = idempotencyMap.computeIfAbsent(idempotencyKey, k -> {
            // This lambda runs ONLY if key not present (and only once, atomically)
            PaymentOrder newOrder = new PaymentOrder(amount, desc);
            orders.put(newOrder.getId(), newOrder);
            return newOrder.getId();
        });
        // If key already existed: returns existing orderId (no new order created)
        // If key is new: creates order inside lambda, stores id, returns id
        // computeIfAbsent is atomic in ConcurrentHashMap → no duplicate orders even with concurrent requests
        return orders.get(orderId);
    }
}

// ── Webhook Signature Verification (HMAC) ──────────────────────────────────────
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

class WebhookVerifier {
    static boolean verify(String payload, String receivedSignature, String secret) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        // Mac = Message Authentication Code. getInstance("HmacSHA256") = HMAC with SHA-256.
        
        mac.init(new SecretKeySpec(secret.getBytes(), "HmacSHA256"));
        // SecretKeySpec wraps the secret bytes as a cryptographic key.
        // mac.init() sets the key.
        
        byte[] hash = mac.doFinal(payload.getBytes());
        // doFinal(message): compute HMAC of payload using the secret key.
        
        String computedSig = HexFormat.of().formatHex(hash);
        // Convert bytes to hex string (like Python's .hexdigest()).
        
        return MessageDigest.isEqual(
            receivedSignature.getBytes(),
            computedSig.getBytes()
        );
        // MessageDigest.isEqual = constant-time comparison (prevents timing attacks).
        // Like Python's hmac.compare_digest().
    }
}
```

---

## STEP 5 — C++ Key Patterns

```cpp
// ── C++ Payment Key Patterns ──────────────────────────────────────────────────
#include <atomic>
#include <shared_mutex>
#include <string>
#include <stdexcept>

// ── Money representation in C++ ───────────────────────────────────────────────
// C++ has no built-in Decimal type. Use cents/paisa (integer) to avoid float issues.
using Paisa = long long;   // 1 rupee = 100 paisa. ₹999.00 = 99900 paisa.

// WHY INTEGER FOR MONEY IN C++?
// Integer arithmetic has NO floating point errors.
// 99900 + 24900 = 124800 (exact). No rounding needed.
// Display: paise / 100.0 for showing to user.

struct Money {
    Paisa amount_paisa;
    std::string currency;

    Money(Paisa paisa, std::string curr) : amount_paisa(paisa), currency(curr) {}

    // Construct from rupee decimal string: "999.50" → 99950 paisa
    static Money fromString(const std::string& rupees, std::string curr) {
        // Parse "999.50": find decimal point, split into rupees and paisa parts
        size_t dot = rupees.find('.');
        Paisa whole = std::stoll(dot == std::string::npos ? rupees : rupees.substr(0, dot));
        Paisa frac  = 0;
        if (dot != std::string::npos && dot + 1 < rupees.size())
            frac = std::stoll(rupees.substr(dot + 1, 2));  // Take only 2 decimal digits
        return Money(whole * 100 + frac, curr);
    }

    std::string toString() const {
        return std::to_string(amount_paisa / 100) + "." +
               (amount_paisa % 100 < 10 ? "0" : "") +
               std::to_string(amount_paisa % 100);
        // If paisa part is < 10, add leading zero: 5 paisa → "05"
    }

    bool operator>=(const Money& other) const {
        return amount_paisa >= other.amount_paisa;
    }
    Money operator-(const Money& other) const {
        if (amount_paisa < other.amount_paisa)
            throw std::runtime_error("Negative money not allowed");
        return Money(amount_paisa - other.amount_paisa, currency);
    }
};

// ── Payment Status with Atomic CAS ────────────────────────────────────────────
enum class PaymentStatus { PENDING, PROCESSING, COMPLETED, FAILED, TIMED_OUT };

class Payment {
    std::atomic<PaymentStatus> status_{PaymentStatus::PENDING};
    // atomic<PaymentStatus>: enum is trivially copyable → atomic supports it in C++20.

public:
    bool transitionTo(PaymentStatus expected, PaymentStatus next) {
        return status_.compare_exchange_strong(expected, next);
        // compare_exchange_strong(expected, desired):
        //   If status_ == expected → set to desired → return true.
        //   If status_ != expected → load actual value into expected → return false.
        // "strong" vs "weak": strong never spuriously fails (weak can fail even if match).
        // Use "strong" when false negative is unacceptable (state transitions).
    }

    PaymentStatus getStatus() const {
        return status_.load(std::memory_order_acquire);
        // acquire: see all writes that happened before the corresponding release store.
    }
};

// ── Idempotency with shared_mutex ─────────────────────────────────────────────
class PaymentGateway {
    std::unordered_map<std::string, std::string> idempotencyMap_;  // key → order_id
    std::unordered_map<std::string, std::shared_ptr<PaymentOrder>> orders_;
    mutable std::shared_mutex idempotencyMtx_;

    std::shared_ptr<PaymentOrder> createOrder(const std::string& key, Money amount) {
        // First check with read lock (fast path for existing orders):
        {
            std::shared_lock lk(idempotencyMtx_);
            auto it = idempotencyMap_.find(key);
            if (it != idempotencyMap_.end())
                return orders_.at(it->second);   // Return existing order
        }

        // Not found: create new order with write lock:
        std::unique_lock lk(idempotencyMtx_);
        // Double-check after acquiring write lock (another thread might have created it):
        auto it = idempotencyMap_.find(key);
        if (it != idempotencyMap_.end())
            return orders_.at(it->second);

        auto order = std::make_shared<PaymentOrder>(amount);
        orders_[order->id] = order;
        idempotencyMap_[key] = order->id;
        return order;
        // Pattern: read with shared_lock → miss → write with unique_lock → double-check
        // This avoids holding write lock for the common case (existing orders).
    }
};
```

---

## STEP 6 — Trade-offs

```
TRADE-OFF 1: Decimal/BigDecimal vs float for money
  float: ₹0.10 + ₹0.20 = ₹0.30000000000000004 — WRONG for financial system!
  Decimal (Python): exact decimal arithmetic. Correct always.
  BigDecimal (Java): same. Must use setScale(2, ROUND_HALF_UP).
  Integer (Paisa in C++): integer arithmetic is always exact. 99 + 201 = 300 exactly.
  
  RULE: NEVER use float/double for money in any language.

TRADE-OFF 2: Two-step (Auth + Capture) vs One-step (Charge)
  Auth-only: hotel blocks ₹5000 on check-in, captures actual bill on check-out.
  Charge: Amazon captures immediately (they know the exact amount).
  
  When to use auth-only?
  - Amount is not known upfront (car rental: you don't know if there'll be damage)
  - Hotel (stay might be extended)
  
  Implementation: PaymentProcessor has separate _authorize() and _capture() methods.
  For e-commerce: call both in sequence. For hotels: call _authorize() only, _capture() later.

TRADE-OFF 3: Synchronous vs Asynchronous payment processing
  Synchronous (what we built): customer waits for bank response (up to 30 sec).
  Simple. Customer sees result immediately.
  
  Asynchronous (UPI actual): customer approved in UPI app → NPCI callback to us → webhook to merchant.
  3 parties: customer, NPCI, merchant. All async.
  Implementation: 
    PaymentService publishes to Kafka: "payment_initiated" event.
    BankIntegration consumer processes it, calls bank API.
    Bank calls our callback URL on completion.
    We publish "payment_completed" to Kafka.
    WebhookService consumer sends webhook to merchant.
  
  Fully decoupled. Resilient to bank timeouts. Industry standard.

TRADE-OFF 4: Database isolation level for payment transactions
  Postgres READ_COMMITTED (default): two concurrent reads can see different data.
  Not safe for "check balance → debit" sequence (race condition: balance checked twice, both proceed).
  
  Solution: SELECT FOR UPDATE (pessimistic lock): locks the row during check.
    BEGIN;
    SELECT balance FROM wallets WHERE id = ? FOR UPDATE;  -- lock this row
    UPDATE wallets SET balance = balance - ? WHERE id = ?;
    COMMIT;
  
  Or: Optimistic locking with version number:
    UPDATE wallets SET balance = balance - ?, version = version + 1
    WHERE id = ? AND version = ?  -- fails if version changed (concurrent update)
  
  Retry if optimistic lock fails. Better for low-contention scenarios.

TRADE-OFF 5: Idempotency key — client-generated vs server-generated
  Client-generated (Stripe approach): merchant provides their own key.
  Merchant uses their internal order_id as the idempotency key.
  No coordination needed — merchant already has unique IDs.
  Risk: merchant might reuse keys incorrectly.
  
  Server-generated: we generate the key, return to merchant.
  Merchant must store it and include in retries.
  More controlled but requires extra round trip before payment.
  
  Stripe uses client-generated. Razorpay uses order_id as natural idempotency key.
```

---

## STEP 7 — Interview Follow-Ups

```
Q: "How do you prevent double charging on network timeout?"
A: 
  Idempotency keys: merchant includes their order_id (or a UUID) in every request.
  If same key seen twice: return the same payment response (no new charge).
  Implementation: ConcurrentHashMap<idempotency_key, payment_id>.
  computeIfAbsent() (Java) / setdefault() (Python) are atomic — only one payment created.
  
  Database: UNIQUE constraint on (order_id, idempotency_key) in payments table.
  Database-level enforcement is the last line of defense.

Q: "How does Razorpay handle 10,000 payments per second?"
A:
  - Horizontal scaling: 50 stateless payment API servers behind a load balancer.
  - Idempotency store in Redis (fast, in-memory, clustered).
  - Payment status in PostgreSQL with write-through cache.
  - Bank communication via async message queues (Kafka).
  - Circuit breaker: if bank API is slow, fail fast instead of queuing up timeouts.
  - Read replicas for payment history queries (read-heavy, stale ok).

Q: "What is PCI-DSS and how does it affect our LLD?"
A:
  PCI-DSS = Payment Card Industry Data Security Standard.
  Rules for anyone who handles card data:
  - Never store CVV (we showed this: CVV only in memory, never written)
  - Store full PAN only if encrypted (we showed tokenization instead)
  - Card data transmitted only over TLS 1.2+
  - Access logs for all card data access
  - Regular security audits
  
  LLD impact:
  - Card class stores pan_last4 and pan_hash, never full PAN
  - CVV not stored at all (not even as a field in Card class)
  - Card.tokenize() sends PAN to Visa Token Service once, never stores locally
  - All API calls to bank over HTTPS (TLS)

Q: "How do you handle settlement (merchant getting paid)?"
A:
  Settlements = batch transfers of collected payments to merchant bank account.
  
  Flow:
  1. Payments collected (money sits in gateway's escrow account).
  2. Deduct: processing fees (e.g., 2% Razorpay fee), refunds, chargebacks.
  3. Remaining amount: settled to merchant's bank account.
  4. Schedule: T+2 (2 business days after payment) is standard.
  
  LLD:
  SettlementService runs daily batch job:
    - Query all COMPLETED payments since last settlement for each merchant
    - Deduct fees and refunds
    - Create bank transfer (NEFT/RTGS/IMPS to merchant's account)
    - Create Settlement record
    - Send settlement report to merchant
```

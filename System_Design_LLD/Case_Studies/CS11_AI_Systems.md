# CS11: LLD — AI System Designs
## ChatGPT | Recommendation Engine | RAG System | Every Line Explained

---

> **WHAT WE'RE BUILDING:**
> Three modern AI systems that every senior engineer must know:
> 1. **ChatGPT-like LLM Service** — API wrapper around an LLM with conversation history
> 2. **Recommendation Engine** — Content/Product recommendation (Netflix, Amazon, YouTube)
> 3. **RAG System** — Retrieval-Augmented Generation (like Perplexity, Google Gemini with Search)
>
> **WHY AI LLD IN 2025?**
> Every MAANG interview now includes: "How would you design an AI-powered feature?"
> Even if you're not an ML engineer, you must know the SYSTEM DESIGN around AI.

---

## PART 1: ChatGPT-like LLM Service

### STEP 1 — Requirements & Entities

```
WHAT WE'RE BUILDING:
  An API service like OpenAI's API.
  Applications (Copilot, Claude.ai) call us to generate AI responses.

FUNCTIONAL REQUIREMENTS:
  1. User sends a message → LLM returns a response
  2. Multi-turn conversations (remember context from previous messages)
  3. Streaming responses (text appears word by word, not all at once)
  4. Multiple models (GPT-4o, GPT-4 mini — different speed/cost tradeoffs)
  5. Rate limiting per API key (prevent abuse)
  6. Token counting (billing by token usage)
  7. Conversation history management (rolling window — forget old messages)
  8. System prompts (customize LLM behavior per application)
  9. Content moderation (filter harmful outputs)

KEY ENTITIES:
  ApiKey           — authentication token for each application
  Conversation     — a multi-turn chat session (persisted)
  Message          — a single turn (role: user/assistant/system + content)
  LLMRequest       — formatted request to the LLM (model + messages + params)
  LLMResponse      — LLM's output (text + token counts + finish_reason)
  Model            — which AI model to use (gpt-4o, gemini-pro, claude-3)
  TokenCounter     — count tokens for billing (expensive = charged by token)
  RateLimiter      — limit requests per minute per API key
  ModerationService — check if content is safe
  StreamingSession — manage streaming (partial response chunks)
```

### STEP 2 — Python Implementation (Every Line Explained)

```python
# llm_service_lld.py
from __future__ import annotations

import uuid
import hashlib
import time
import threading
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Optional, List, Dict, Generator, Iterator


# ══════════════════════════════════════════════════════════════════════════════
# ENUMS
# ══════════════════════════════════════════════════════════════════════════════

class MessageRole(Enum):
    """
    WHAT ARE THESE ROLES?
    
    SYSTEM: Instructions to the LLM about how to behave.
    Like a "job description" for the AI.
    Example: "You are a helpful coding assistant. Be concise. Use Python examples."
    
    USER: The human's message in a conversation.
    
    ASSISTANT: The AI's previous response (included so LLM knows what it said before).
    This is how "memory" works — we re-send the history every time.
    
    WHY DOES THIS MATTER?
    LLMs are STATELESS — each API call is independent.
    They have no memory of previous calls.
    "Memory" is faked by including previous messages in each new request.
    """
    SYSTEM    = "system"
    USER      = "user"
    ASSISTANT = "assistant"

class FinishReason(Enum):
    """
    Why did the LLM stop generating?
    
    STOP:        Natural end — LLM decided it was done.
    LENGTH:      Hit max_tokens limit — output was truncated.
    CONTENT_FILTER: Safety system blocked the output.
    TOOL_CALL:   LLM wants to call a function/tool (function calling feature).
    """
    STOP           = "stop"
    LENGTH         = "length"
    CONTENT_FILTER = "content_filter"
    TOOL_CALL      = "tool_calls"

class ModelTier(Enum):
    """
    Different LLM models with different speed/quality/cost tradeoffs.
    
    FAST:  Smallest model. Cheap. Good for simple tasks.
           Examples: GPT-4o-mini, Gemini Flash, Claude Haiku.
    STANDARD: Balanced. Most use cases.
              Examples: GPT-4o, Gemini Pro, Claude Sonnet.
    POWERFUL: Largest, slowest, most expensive. Complex reasoning.
              Examples: GPT-o1, Gemini Ultra, Claude Opus.
    """
    FAST     = "fast"
    STANDARD = "standard"
    POWERFUL = "powerful"


# ══════════════════════════════════════════════════════════════════════════════
# CORE DATA TYPES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Message:
    """
    A single message in a conversation.
    
    In OpenAI format:
    {"role": "user", "content": "What is LLD?"}
    {"role": "assistant", "content": "LLD stands for Low-Level Design..."}
    
    The LLM receives the ENTIRE history as a list of these messages.
    This is why context window (max tokens) matters — long conversations hit the limit.
    """
    role:    MessageRole
    content: str
    id:      str  = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)
    token_count: int = 0    # How many tokens this message uses (set after creation)

    def to_api_format(self) -> dict:
        """Convert to the format LLM APIs expect."""
        return {"role": self.role.value, "content": self.content}
        # Example: {"role": "user", "content": "Hello, how are you?"}

    def __len__(self) -> int:
        return len(self.content)


@dataclass
class LLMResponse:
    """
    Complete response from the LLM.
    
    WHAT IS A "TOKEN"?
    LLMs don't process characters or words — they process TOKENS.
    A token ≈ 4 characters ≈ 0.75 words (for English).
    "Hello" = 1 token. "ChatGPT" = 2 tokens. "antidisestablishmentarianism" = 7 tokens.
    
    WHY TOKEN COUNT MATTERS:
    1. Billing: OpenAI charges per token ($0.0015 per 1K input tokens for GPT-4 mini)
    2. Context window: LLMs have max token limits (GPT-4o = 128K tokens)
       If conversation history > 128K tokens → must trim old messages.
    """
    content:          str
    model:            str
    finish_reason:    FinishReason
    input_tokens:     int     # Tokens in the request (history + new message)
    output_tokens:    int     # Tokens in the response
    processing_ms:    int     # How long the LLM took to generate

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def cost_usd(self) -> float:
        """
        Estimate cost in USD.
        Simplified pricing (actual varies by model and tier).
        """
        INPUT_COST_PER_1K  = 0.0015   # $0.0015 per 1K input tokens
        OUTPUT_COST_PER_1K = 0.002    # $0.002 per 1K output tokens
        return (self.input_tokens  * INPUT_COST_PER_1K / 1000
              + self.output_tokens * OUTPUT_COST_PER_1K / 1000)


@dataclass
class ModelConfig:
    """Configuration for a specific AI model."""
    name:             str    # "gpt-4o", "gemini-pro", "claude-3-sonnet"
    tier:             ModelTier
    max_context_tokens: int  # How many tokens fit in the context window
    max_output_tokens:  int  # Max tokens the model can generate per response
    requests_per_min:   int  # Rate limit for this model
    cost_per_1k_input:  float
    cost_per_1k_output: float


# ══════════════════════════════════════════════════════════════════════════════
# TOKEN COUNTER
# ══════════════════════════════════════════════════════════════════════════════

class TokenCounter:
    """
    Estimate token count for messages.
    
    REAL IMPLEMENTATION uses tiktoken (OpenAI's tokenizer):
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")  # GPT-4's tokenizer
    tokens = enc.encode("Hello world")           # Returns [9906, 1917]
    len(tokens) = 2  ← this is the token count
    
    SIMPLIFIED HERE: approximate as len(text) / 4
    (Average English token ≈ 4 characters)
    """

    CHARS_PER_TOKEN = 4   # Approximation

    @staticmethod
    def count_text(text: str) -> int:
        """Estimate token count for a string."""
        return max(1, len(text) // TokenCounter.CHARS_PER_TOKEN)
        # max(1, ...) ensures at least 1 token even for very short strings
        # // = integer division (floor): "Hello" = 5 chars // 4 = 1 token

    @staticmethod
    def count_messages(messages: List[Message]) -> int:
        """
        Count tokens for a list of messages.
        
        OVERHEAD: Each message has some overhead beyond just the content:
        - role field: ~1 token
        - Formatting tokens: ~4 tokens per message
        Total overhead per message: ~4 tokens
        
        This is why a 1000-message conversation uses more tokens than
        the sum of all individual message tokens.
        """
        total = 0
        for msg in messages:
            total += TokenCounter.count_text(msg.content)
            total += 4   # Per-message formatting overhead
        total += 2   # Conversation start/end tokens
        return total


# ══════════════════════════════════════════════════════════════════════════════
# CONVERSATION HISTORY — Rolling Window
# ══════════════════════════════════════════════════════════════════════════════

class ConversationHistory:
    """
    Manages the chat history for a conversation.
    
    THE CORE CHALLENGE:
    LLMs have a context window limit (e.g., 128,000 tokens for GPT-4o).
    Long conversations exceed this limit.
    
    SOLUTION: Rolling window — drop the oldest messages when limit is exceeded.
    
    BUT: Must ALWAYS keep the system message (it defines the bot's behavior).
    So: system_message (always kept) + most recent N user/assistant messages.
    
    MEMORY TYPES:
    1. Short-term memory (this class): recent conversation turns in context.
    2. Long-term memory: summarize old messages and inject summary as context.
       "Earlier in our conversation, you mentioned you're a Python developer..."
    3. External memory: vector database search (RAG) — covered in Part 3.
    """

    def __init__(self, system_prompt: str, max_tokens: int = 4000):
        self.id = str(uuid.uuid4())

        # System message: always included, never dropped
        self._system_message = Message(
            role=MessageRole.SYSTEM,
            content=system_prompt
        )
        self._system_message.token_count = TokenCounter.count_text(system_prompt)

        # Recent messages in a deque (double-ended queue)
        # deque allows efficient O(1) pop from the left (oldest messages)
        self._messages: deque[Message] = deque()
        # deque vs list:
        # list.pop(0) = O(n) — must shift all elements
        # deque.popleft() = O(1) — no shifting needed
        # For rolling window: we frequently pop the oldest → deque is better

        self._max_tokens  = max_tokens
        self._total_tokens = self._system_message.token_count
        self._lock = threading.RLock()

    def add_message(self, role: MessageRole, content: str) -> Message:
        """
        Add a new message to the conversation.
        Automatically drops oldest messages if context window is exceeded.
        """
        msg = Message(role=role, content=content)
        msg.token_count = TokenCounter.count_text(content) + 4   # +4 for overhead

        with self._lock:
            self._messages.append(msg)
            self._total_tokens += msg.token_count

            # ROLLING WINDOW: drop oldest non-system messages if over limit
            # Note: drop in pairs (user + assistant) to maintain conversation structure
            while (self._total_tokens > self._max_tokens
                   and len(self._messages) >= 2):
                # Pop the oldest message (from the front of the deque)
                oldest = self._messages.popleft()
                self._total_tokens -= oldest.token_count
                # If oldest was a "user" message, also drop the next "assistant" response
                # to keep the conversation structure (user-assistant pairs)

        return msg

    def get_messages_for_api(self) -> List[dict]:
        """
        Return ALL messages in the format the LLM API expects.
        
        Always includes:
        1. The system message (first)
        2. All recent messages in chronological order
        
        This is sent to the LLM API on EVERY request.
        This is how the LLM "remembers" the conversation.
        """
        with self._lock:
            result = [self._system_message.to_api_format()]
            result.extend(msg.to_api_format() for msg in self._messages)
            return result

    def get_recent_messages(self, n: int = 10) -> List[Message]:
        """Get last N messages (for display purposes)."""
        with self._lock:
            return list(self._messages)[-n:]    # Last N elements

    @property
    def token_usage(self) -> int:
        with self._lock:
            return self._total_tokens

    @property
    def message_count(self) -> int:
        with self._lock:
            return len(self._messages)


# ══════════════════════════════════════════════════════════════════════════════
# RATE LIMITER — Token Bucket Algorithm
# ══════════════════════════════════════════════════════════════════════════════

class RateLimiter:
    """
    Token Bucket Rate Limiter.
    
    WHAT IS TOKEN BUCKET?
    Imagine a bucket that:
    - Holds max N "tokens" (not LLM tokens — rate limiter tokens, just units)
    - Fills at a rate of R tokens per second
    - Each request consumes 1 token
    
    If bucket is empty: request is DENIED (rate limit exceeded).
    If bucket has tokens: request is ALLOWED, consume 1 token.
    
    WHY TOKEN BUCKET vs simple counter?
    Simple counter: "10 requests per second" — all 10 can happen in first 100ms.
    Token bucket: requests are more evenly spread. Burst is allowed (up to bucket capacity)
    but sustained over-use is prevented.
    
    REAL USAGE:
    - API services: 60 requests/minute per API key
    - GPT-4: 500 requests/minute per tier
    - We implement per-API-key rate limiting
    """

    def __init__(self, requests_per_minute: int):
        self._rpm      = requests_per_minute
        self._rate     = requests_per_minute / 60.0   # Requests per SECOND
        # Divide by 60: "100 requests/min" → "1.67 requests/sec" fill rate

        self._tokens   = float(requests_per_minute)   # Start with a full bucket
        self._capacity = float(requests_per_minute)   # Max bucket size
        self._last_refill = time.monotonic()
        # time.monotonic() = monotonically increasing time (never goes backwards)
        # Unlike time.time() which can be adjusted by NTP sync
        # Use monotonic for timing/rate calculations

        self._lock = threading.Lock()

    def _refill(self) -> None:
        """
        Add tokens to the bucket based on elapsed time.
        Called before every request.
        """
        now     = time.monotonic()
        elapsed = now - self._last_refill           # Seconds since last refill
        new_tokens = elapsed * self._rate           # How many tokens to add
        self._tokens = min(self._capacity,
                          self._tokens + new_tokens)  # Don't exceed capacity
        self._last_refill = now

    def allow_request(self) -> bool:
        """
        Check if a request is allowed (non-blocking).
        Returns True if allowed and consumes 1 token.
        Returns False if rate limit exceeded.
        """
        with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0    # Consume one token
                return True
        return False   # Bucket is empty

    def remaining_tokens(self) -> float:
        """How many requests are still allowed right now?"""
        with self._lock:
            self._refill()
            return self._tokens


# ══════════════════════════════════════════════════════════════════════════════
# API KEY MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

class ApiKey:
    """
    Authentication token for applications using the LLM service.
    Each application (like Copilot, a chatbot) has its own API key.
    Tracks usage and has its own rate limit.
    """

    def __init__(self, name: str, model_config: ModelConfig,
                 monthly_token_limit: int = 10_000_000):
        self.id          = str(uuid.uuid4())
        self.name        = name   # Human-readable: "Sachin's Chatbot", "Copilot"
        
        raw_key          = f"sk-{uuid.uuid4().hex}"   # "sk-" prefix like OpenAI
        self._key_hash   = hashlib.sha256(raw_key.encode()).hexdigest()
        self._raw_key    = raw_key   # Shown only once
        
        self.model_config = model_config
        self.is_active    = True
        self.created_at   = datetime.utcnow()
        
        # Rate limiter: configured per the model's limits
        self._rate_limiter = RateLimiter(model_config.requests_per_min)
        
        # Usage tracking
        self._total_tokens_used  = 0     # All-time token usage
        self._monthly_token_limit = monthly_token_limit
        self._monthly_tokens_used = 0
        self._current_month       = datetime.utcnow().month
        self._lock = threading.Lock()

    def verify(self, provided_key: str) -> bool:
        """Constant-time comparison to prevent timing attacks."""
        import hmac
        provided_hash = hashlib.sha256(provided_key.encode()).hexdigest()
        return hmac.compare_digest(self._key_hash, provided_hash)

    def check_rate_limit(self) -> bool:
        """Is this API key allowed to make a request right now?"""
        if not self.is_active:
            return False
        return self._rate_limiter.allow_request()

    def check_monthly_limit(self) -> bool:
        """Has this key exceeded its monthly token budget?"""
        with self._lock:
            # Reset counter if we're in a new month
            current_month = datetime.utcnow().month
            if current_month != self._current_month:
                self._monthly_tokens_used = 0
                self._current_month       = current_month
            return self._monthly_tokens_used < self._monthly_token_limit

    def record_usage(self, tokens: int) -> None:
        """Record token usage (called after each successful request)."""
        with self._lock:
            self._total_tokens_used  += tokens
            self._monthly_tokens_used += tokens

    def get_raw_key(self) -> str:
        return self._raw_key   # Only for display at creation


# ══════════════════════════════════════════════════════════════════════════════
# LLM ADAPTER — Strategy Pattern for multiple LLM providers
# ══════════════════════════════════════════════════════════════════════════════

class ILLMAdapter(ABC):
    """
    STRATEGY INTERFACE for different LLM providers.
    
    WHY ADAPTER/STRATEGY?
    We might use: OpenAI, Anthropic, Google, local Ollama — same interface.
    
    Real engineering: if OpenAI is down, switch to Anthropic (fallback).
    This is called: LLM routing / model gateway.
    Used by: LiteLLM, Portkey, OpenRouter — they're LLM gateways.
    """

    @abstractmethod
    def generate(self, messages: List[dict], model: str,
                 max_tokens: int, temperature: float) -> LLMResponse:
        """
        Call the LLM and return the response.
        
        messages: List of {role, content} dicts
        model: Which model to use ("gpt-4o", "claude-3-sonnet", etc.)
        max_tokens: Max tokens to generate (controls response length)
        temperature: 0.0 = deterministic, 1.0 = creative/random
                     Coding: use 0.1 (precise). Creative writing: use 0.9.
        """
        ...

    @abstractmethod
    def stream_generate(self, messages: List[dict], model: str,
                        max_tokens: int, temperature: float) -> Iterator[str]:
        """
        Same as generate() but yields response CHUNKS as they're generated.
        This is how ChatGPT's "typewriter" effect works.
        Each chunk is a few words: "The " → "answer " → "is " → "42."
        """
        ...


class OpenAIAdapter(ILLMAdapter):
    """
    Adapter for OpenAI's API (GPT-4o, GPT-4 mini, etc.)
    
    REAL IMPLEMENTATION:
    import openai
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello!"}],
        max_tokens=1000,
        temperature=0.7,
        stream=False
    )
    return response.choices[0].message.content
    
    WE SIMULATE IT HERE (no actual API call).
    """

    def __init__(self, api_key: str = None):
        self._api_key = api_key   # OpenAI API key (sk-...)

    def generate(self, messages: List[dict], model: str,
                 max_tokens: int, temperature: float) -> LLMResponse:
        """Simulated LLM response for demo purposes."""
        start = time.time()
        
        # SIMULATION: In production, this is an HTTP call to api.openai.com
        # response = openai_client.chat.completions.create(model=model, messages=messages, ...)
        
        # Count input tokens (approximation)
        input_text = " ".join(m["content"] for m in messages)
        input_tokens = TokenCounter.count_text(input_text)
        
        # Simulate response
        last_user_msg = next((m["content"] for m in reversed(messages)
                              if m["role"] == "user"), "")
        simulated_response = (
            f"[Simulated {model} response to: '{last_user_msg[:50]}...']\n"
            f"This is where the actual LLM response would appear.\n"
            f"In production, this calls openai.chat.completions.create()."
        )
        
        output_tokens = TokenCounter.count_text(simulated_response)
        processing_ms = int((time.time() - start) * 1000)

        return LLMResponse(
            content=simulated_response,
            model=model,
            finish_reason=FinishReason.STOP,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            processing_ms=processing_ms
        )

    def stream_generate(self, messages: List[dict], model: str,
                        max_tokens: int, temperature: float) -> Iterator[str]:
        """
        Simulated streaming: yield one word at a time.
        
        REAL STREAMING:
        for chunk in openai_client.chat.completions.create(
            model=model, messages=messages, stream=True
        ):
            delta = chunk.choices[0].delta.content
            if delta: yield delta
        
        Each 'delta' is a partial response (usually 1-5 words).
        The client receives and displays these incrementally → "typewriter" effect.
        """
        response_text = (
            f"[Streaming {model} response]\n"
            f"Here is the generated content, word by word, "
            f"just like ChatGPT's typewriter effect."
        )
        for word in response_text.split():
            yield word + " "
            time.sleep(0.05)   # Simulate generation speed


class ModerationService:
    """
    Content moderation: check if input/output is safe.
    
    REAL IMPLEMENTATION:
    OpenAI Moderation API: POST https://api.openai.com/v1/moderations
    Returns: is_flagged + categories (hate, violence, sexual, etc.)
    
    Other approaches:
    - Custom classifier: fine-tuned BERT for content safety
    - Rules-based: keyword blocklist for quick filtering
    """

    BLOCKED_PATTERNS = ["violent content", "explicit", "harmful instructions"]
    # In production: these would be much more sophisticated

    def check_input(self, text: str) -> tuple[bool, str]:
        """
        Returns: (is_safe, reason_if_not_safe)
        """
        text_lower = text.lower()
        for pattern in self.BLOCKED_PATTERNS:
            if pattern in text_lower:
                return False, f"Content blocked: detected '{pattern}'"
        return True, ""   # Safe

    def check_output(self, text: str) -> tuple[bool, str]:
        return self.check_input(text)   # Same rules for output


# ══════════════════════════════════════════════════════════════════════════════
# LLM SERVICE — Facade
# ══════════════════════════════════════════════════════════════════════════════

class LLMService:
    """
    FACADE: Main service for the LLM API.
    
    This is the class that:
    - Validates API keys
    - Enforces rate limits
    - Manages conversations
    - Calls the LLM adapter
    - Records usage for billing
    - Moderates content
    """

    def __init__(self, adapter: ILLMAdapter):
        self._adapter       = adapter         # Which LLM to use
        self._api_keys:     Dict[str, ApiKey] = {}
        self._conversations: Dict[str, ConversationHistory] = {}
        self._moderation    = ModerationService()
        self._lock          = threading.RLock()

    def create_api_key(self, name: str, model_config: ModelConfig) -> ApiKey:
        """Create and register a new API key."""
        key = ApiKey(name, model_config)
        with self._lock:
            self._api_keys[key.id] = key
        print(f"API Key created for {name}")
        print(f"Key (save this!): {key.get_raw_key()}")
        return key

    def create_conversation(self, api_key: ApiKey,
                            system_prompt: str = "You are a helpful assistant.") -> ConversationHistory:
        """Start a new conversation (chat session)."""
        history = ConversationHistory(
            system_prompt=system_prompt,
            max_tokens=api_key.model_config.max_context_tokens // 2
            # Use half the context window for history (leave room for new responses)
        )
        with self._lock:
            self._conversations[history.id] = history
        return history

    def chat(self, api_key: ApiKey, conversation: ConversationHistory,
             user_message: str, max_tokens: int = 1000,
             temperature: float = 0.7) -> LLMResponse:
        """
        Main method: send a message and get a response.
        
        FLOW:
        1. Validate API key
        2. Check rate limit
        3. Check monthly token budget
        4. Moderate user input
        5. Add user message to history
        6. Call LLM with full history
        7. Moderate LLM output
        8. Add LLM response to history
        9. Record token usage
        10. Return response
        """
        # Step 1: Validate API key is active
        if not api_key.is_active:
            raise ValueError("API key is not active")

        # Step 2: Rate limit check
        if not api_key.check_rate_limit():
            raise ValueError(
                f"Rate limit exceeded. Limit: {api_key.model_config.requests_per_min} req/min"
            )

        # Step 3: Monthly budget check
        if not api_key.check_monthly_limit():
            raise ValueError("Monthly token limit exceeded. Upgrade your plan.")

        # Step 4: Content moderation on user input
        is_safe, reason = self._moderation.check_input(user_message)
        if not is_safe:
            raise ValueError(f"Message blocked by content filter: {reason}")

        # Step 5: Add user message to conversation history
        conversation.add_message(MessageRole.USER, user_message)

        # Step 6: Get all messages formatted for the LLM API
        api_messages = conversation.get_messages_for_api()
        # This returns: [system_msg, older_msg1, older_msg2, ..., new_user_msg]
        # The LLM sees the ENTIRE conversation and responds in context.

        # Step 7: Call the LLM
        response = self._adapter.generate(
            messages=api_messages,
            model=api_key.model_config.name,
            max_tokens=max_tokens,
            temperature=temperature
        )

        # Step 8: Moderate LLM output
        is_safe, reason = self._moderation.check_output(response.content)
        if not is_safe:
            # Replace blocked output with a safe message
            response = LLMResponse(
                content="I can't help with that request.",
                model=response.model,
                finish_reason=FinishReason.CONTENT_FILTER,
                input_tokens=response.input_tokens,
                output_tokens=5,   # Short response
                processing_ms=response.processing_ms
            )

        # Step 9: Add assistant response to conversation history
        conversation.add_message(MessageRole.ASSISTANT, response.content)

        # Step 10: Record token usage for billing
        api_key.record_usage(response.total_tokens)

        return response

    def stream_chat(self, api_key: ApiKey, conversation: ConversationHistory,
                    user_message: str) -> Generator[str, None, None]:
        """
        Streaming version: yields response chunks as they're generated.
        
        USAGE:
        for chunk in service.stream_chat(key, conv, "Tell me a story"):
            print(chunk, end="", flush=True)   # Print without newline, flush immediately
        
        WHY STREAMING?
        LLM generation is slow (1-5 seconds for long responses).
        Without streaming: user stares at blank screen for 5 seconds.
        With streaming: text appears word by word (much better UX).
        """
        if not api_key.check_rate_limit():
            raise ValueError("Rate limit exceeded")

        # Moderate input
        is_safe, reason = self._moderation.check_input(user_message)
        if not is_safe: raise ValueError(f"Blocked: {reason}")

        conversation.add_message(MessageRole.USER, user_message)
        api_messages = conversation.get_messages_for_api()

        full_response = []
        for chunk in self._adapter.stream_generate(
            messages=api_messages,
            model=api_key.model_config.name,
            max_tokens=1000,
            temperature=0.7
        ):
            full_response.append(chunk)
            yield chunk
            # yield: this turns stream_chat() into a GENERATOR
            # Generator = function that produces values one at a time (lazily)
            # The for loop in the caller receives one chunk at a time
            # No waiting for entire response to complete

        # After streaming is done: save complete response to history
        full_text = "".join(full_response)
        conversation.add_message(MessageRole.ASSISTANT, full_text)
        api_key.record_usage(TokenCounter.count_text(full_text))


# ══════════════════════════════════════════════════════════════════════════════
# DEMO
# ══════════════════════════════════════════════════════════════════════════════

def demo_llm_service():
    """Demonstrates the LLM service with a multi-turn conversation."""

    # Model configuration
    gpt4o_config = ModelConfig(
        name="gpt-4o",
        tier=ModelTier.STANDARD,
        max_context_tokens=128_000,   # 128K context window
        max_output_tokens=4096,
        requests_per_min=100,
        cost_per_1k_input=0.005,
        cost_per_1k_output=0.015
    )

    # Setup service
    adapter = OpenAIAdapter(api_key="sk-your-key-here")
    service = LLMService(adapter)

    # Create API key
    my_key = service.create_api_key("My Coding Assistant", gpt4o_config)

    # Create a conversation
    conv = service.create_conversation(
        my_key,
        system_prompt="You are a senior software engineer. Help with system design."
    )

    print("\n" + "="*60)
    print("MULTI-TURN CONVERSATION DEMO")
    print("="*60)

    # Turn 1
    r1 = service.chat(my_key, conv, "What is the difference between LLD and HLD?")
    print(f"\nUser: What is LLD vs HLD?")
    print(f"AI: {r1.content}")
    print(f"Tokens: {r1.total_tokens} | Cost: ${r1.cost_usd:.4f}")
    print(f"Context: {conv.token_usage} tokens used / {gpt4o_config.max_context_tokens} max")

    # Turn 2 — LLM remembers the previous message context
    r2 = service.chat(my_key, conv, "Can you give me an example of LLD?")
    print(f"\nUser: Can you give an example?")
    print(f"AI: {r2.content}")

    # Streaming demo
    print("\n" + "="*60)
    print("STREAMING DEMO")
    print("="*60)
    print("\nUser: Explain the Strategy pattern in one sentence.")
    print("AI: ", end="")
    conv2 = service.create_conversation(my_key, "You are a helpful assistant.")
    for chunk in service.stream_chat(my_key, conv2, "Explain Strategy pattern briefly."):
        print(chunk, end="", flush=True)
    print()  # Newline after streaming
```

---

## PART 2: Recommendation Engine

```python
# recommendation_engine_lld.py
"""
WHAT IS A RECOMMENDATION ENGINE?
Used by: Netflix (shows), Amazon (products), YouTube (videos), Spotify (songs).
Goal: predict what a user wants BEFORE they know they want it.

THREE MAIN APPROACHES:
1. Collaborative Filtering: "Users like you also liked..."
   Find similar users → recommend what they liked but you haven't.
   
2. Content-Based Filtering: "Because you liked X (which has properties A, B, C)..."
   Find items with similar properties to what you've already liked.
   
3. Hybrid (what big companies actually use):
   Combine both. Netflix's recommendation uses 800+ models.

WE BUILD: A hybrid engine with both approaches + Embedding similarity.
"""
from __future__ import annotations
import math
import threading
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass, field
from abc import ABC, abstractmethod


@dataclass
class Item:
    """
    An item to recommend: product, movie, song, article.
    Tags represent the item's attributes.
    """
    id:         str
    title:      str
    tags:       List[str]   # Attributes: ["sci-fi", "action", "christopher nolan"]
    popularity: float = 0.0  # Global popularity score (like YouTube view count)

    def tag_set(self) -> Set[str]:
        return set(tag.lower() for tag in self.tags)


@dataclass
class UserInteraction:
    """
    A user's interaction with an item.
    
    IMPLICIT FEEDBACK (most common):
    User doesn't explicitly rate things. We infer preference from behavior.
    - Clicked = some interest
    - Watched 80% = strong positive signal
    - Skipped after 5 seconds = negative signal
    """
    user_id:     str
    item_id:     str
    score:       float      # 0.0 (strong dislike) to 1.0 (strong like)
    # Derived from: watch time, clicks, skips, explicit ratings
    # 1.0 = watched 100% + rated 5 stars
    # 0.7 = watched 80% (implied like)
    # 0.3 = watched 30% (mild interest)
    # 0.0 = immediately skipped (dislike)


class UserItemMatrix:
    """
    Stores user × item interactions.
    
    MATRIX FORM:
         Item1  Item2  Item3
    User1  0.9    0.0    0.7
    User2  0.0    0.8    0.6
    User3  0.7    0.9    0.0
    
    Most entries are 0.0 (user hasn't interacted with most items).
    This is a "sparse matrix" — most values are missing.
    
    WHY THIS MATTERS:
    Collaborative filtering uses this matrix to find similar users.
    "User1 and User3 both liked Item1 and Item3 → they're similar → recommend Item2 to User3"
    """

    def __init__(self):
        # user_id → {item_id → score}
        self._data: Dict[str, Dict[str, float]] = {}
        self._lock = threading.RLock()

    def record(self, interaction: UserInteraction) -> None:
        """Record a user's interaction with an item."""
        with self._lock:
            if interaction.user_id not in self._data:
                self._data[interaction.user_id] = {}
            self._data[interaction.user_id][interaction.item_id] = interaction.score
            # This overwrites previous score (latest interaction wins)

    def get_user_scores(self, user_id: str) -> Dict[str, float]:
        """Get all items a user has interacted with and their scores."""
        with self._lock:
            return dict(self._data.get(user_id, {}))   # Return a copy

    def get_item_scores(self, item_id: str) -> Dict[str, float]:
        """Get all users who interacted with an item and their scores."""
        with self._lock:
            return {
                user_id: scores[item_id]
                for user_id, scores in self._data.items()
                if item_id in scores
            }

    def get_all_users(self) -> List[str]:
        with self._lock:
            return list(self._data.keys())


class CosineSimilarity:
    """
    Computes cosine similarity between two vectors.
    
    WHAT IS COSINE SIMILARITY?
    A measure of similarity between two vectors (0.0 = no similarity, 1.0 = identical).
    
    MATH:
    cosine_sim(A, B) = (A · B) / (|A| × |B|)
    
    Where:
    A · B = dot product (sum of element-wise products)
    |A| = magnitude (length) of vector A = sqrt(sum of squares)
    
    INTUITION:
    - Two users who rated the same items similarly have high cosine similarity.
    - The "angle" between their preference vectors is small.
    - cosine = 1.0: identical preference. cosine = 0.0: completely different.
    
    WHY COSINE NOT EUCLIDEAN DISTANCE?
    User A rated everything 5/5 (generous rater). User B rated same items 3/3 (strict rater).
    Same relative preference, but Euclidean distance would be high.
    Cosine ignores magnitude — only direction matters. Perfect for preferences.
    """

    @staticmethod
    def compute(vec_a: Dict[str, float], vec_b: Dict[str, float]) -> float:
        """
        Compute cosine similarity between two sparse vectors (as dicts).
        
        EXAMPLE:
        vec_a = {"item1": 0.9, "item3": 0.7}  (User A's ratings)
        vec_b = {"item1": 0.7, "item2": 0.8, "item3": 0.0}  (User B's ratings)
        
        Common keys: item1, item3
        dot_product = 0.9 × 0.7 + 0.7 × 0.0 = 0.63
        |vec_a| = sqrt(0.9² + 0.7²) = sqrt(0.81 + 0.49) = sqrt(1.30) ≈ 1.14
        |vec_b| = sqrt(0.7² + 0.8² + 0.0²) = sqrt(0.49 + 0.64) ≈ 1.06
        cosine_sim = 0.63 / (1.14 × 1.06) ≈ 0.52
        """
        # Find common keys (items both users rated)
        common_keys = set(vec_a.keys()) & set(vec_b.keys())
        # & operator on sets = intersection (elements in BOTH sets)

        if not common_keys:
            return 0.0   # No common items → no similarity can be computed

        # Dot product: sum of a[key] × b[key] for all common keys
        dot_product = sum(vec_a[k] * vec_b[k] for k in common_keys)

        # Magnitudes (lengths)
        mag_a = math.sqrt(sum(v**2 for v in vec_a.values()))
        mag_b = math.sqrt(sum(v**2 for v in vec_b.values()))

        if mag_a == 0 or mag_b == 0:
            return 0.0   # Zero vector → undefined similarity

        return dot_product / (mag_a * mag_b)
        # Result is between 0.0 and 1.0 (assuming all scores are positive)


class IRecommendationStrategy(ABC):
    """Strategy interface for recommendation algorithms."""

    @abstractmethod
    def recommend(self, user_id: str, items: List[Item],
                  matrix: UserItemMatrix, limit: int) -> List[Tuple[Item, float]]:
        """
        Returns: list of (item, predicted_score) sorted by score descending.
        predicted_score: how likely the user is to like this item (0.0 to 1.0).
        """
        ...


class CollaborativeFilteringStrategy(IRecommendationStrategy):
    """
    USER-BASED COLLABORATIVE FILTERING:
    Find N users most similar to target user → recommend what they liked.
    
    STEPS:
    1. Get target user's ratings vector
    2. For every other user: compute cosine similarity
    3. Pick top-K most similar users (K-nearest neighbors)
    4. Aggregate their ratings → predict target user's score for unseen items
    5. Return top-N predicted items
    """

    def __init__(self, k_neighbors: int = 5):
        self._k = k_neighbors   # How many similar users to consider

    def recommend(self, user_id: str, items: List[Item],
                  matrix: UserItemMatrix, limit: int) -> List[Tuple[Item, float]]:
        user_scores   = matrix.get_user_scores(user_id)
        # user_scores = {"movie_1": 0.9, "movie_3": 0.7, ...}
        # Items this user has already rated/watched

        all_users     = matrix.get_all_users()
        item_map      = {item.id: item for item in items}
        # Build a dict for O(1) item lookup by ID

        # Step 1: Find similar users
        similarities: List[Tuple[str, float]] = []
        for other_user_id in all_users:
            if other_user_id == user_id: continue   # Don't compare with self
            other_scores = matrix.get_user_scores(other_user_id)
            sim = CosineSimilarity.compute(user_scores, other_scores)
            if sim > 0:   # Only include users with some similarity
                similarities.append((other_user_id, sim))

        # Sort by similarity descending: highest similar users first
        similarities.sort(key=lambda x: x[1], reverse=True)
        top_k = similarities[:self._k]   # Take K nearest neighbors

        # Step 2: Aggregate predictions from top-K neighbors
        predicted: Dict[str, Tuple[float, float]] = {}
        # item_id → (weighted_sum, similarity_sum)
        # weighted_sum: sum of (similarity × rating) for each neighbor
        # similarity_sum: sum of similarities (for normalization)

        for neighbor_id, similarity in top_k:
            neighbor_scores = matrix.get_user_scores(neighbor_id)
            for item_id, rating in neighbor_scores.items():
                if item_id in user_scores: continue   # Already seen — don't recommend
                if item_id not in item_map: continue  # Item not in our catalog

                if item_id not in predicted:
                    predicted[item_id] = (0.0, 0.0)
                ws, ss = predicted[item_id]
                predicted[item_id] = (
                    ws + similarity * rating,   # Weight by similarity
                    ss + similarity             # Accumulate similarities
                )

        # Step 3: Compute final predicted scores
        results: List[Tuple[Item, float]] = []
        for item_id, (weighted_sum, sim_sum) in predicted.items():
            if sim_sum == 0: continue
            score = weighted_sum / sim_sum   # Weighted average
            # This is the PREDICTED score: if user had rated this item, what would they give?
            results.append((item_map[item_id], score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]


class ContentBasedStrategy(IRecommendationStrategy):
    """
    CONTENT-BASED FILTERING:
    Find items with similar tags to what the user has liked.
    
    EXAMPLE:
    User liked: "Inception" (tags: sci-fi, mind-bending, Christopher Nolan)
    Content-based finds: "Interstellar" (same tags) → recommend it.
    
    Uses tag overlap (Jaccard similarity) to measure item similarity.
    """

    def recommend(self, user_id: str, items: List[Item],
                  matrix: UserItemMatrix, limit: int) -> List[Tuple[Item, float]]:
        user_scores = matrix.get_user_scores(user_id)
        if not user_scores:
            # New user: return most popular items (cold-start problem)
            sorted_by_popularity = sorted(items, key=lambda i: -i.popularity)
            return [(item, item.popularity) for item in sorted_by_popularity[:limit]]

        item_map = {item.id: item for item in items}

        # Build "user taste profile": union of tags from positively-rated items
        liked_tags: Dict[str, float] = {}   # tag → weighted preference score
        for item_id, score in user_scores.items():
            if score < 0.5: continue   # Neutral or disliked — ignore
            item = item_map.get(item_id)
            if not item: continue
            for tag in item.tags:
                tag = tag.lower()
                liked_tags[tag] = liked_tags.get(tag, 0.0) + score
                # Tags from highly-liked items get higher weights

        if not liked_tags:
            return []

        # Score each unseen item by tag overlap with user's taste profile
        seen_ids = set(user_scores.keys())
        results:  List[Tuple[Item, float]] = []

        for item in items:
            if item.id in seen_ids: continue   # Already seen

            # Jaccard-weighted similarity: overlap of item tags with user taste profile
            item_tags = item.tag_set()
            overlap_score = sum(liked_tags.get(t, 0.0) for t in item_tags)
            # Sum of user preference weights for each tag the item has

            if overlap_score > 0:
                # Normalize by number of tags to avoid longer-tag-list bias
                score = overlap_score / max(len(item_tags), 1)
                results.append((item, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]


class HybridRecommendationEngine:
    """
    HYBRID APPROACH: Combine collaborative + content-based.
    
    WHY HYBRID?
    Collaborative filtering: great when user has history. Fails for new users.
    Content-based: works for new users. Fails to discover surprising new genres.
    
    Hybrid: alpha × collaborative + (1-alpha) × content-based
    alpha = 0.7 → 70% collaborative, 30% content-based.
    
    In practice: Netflix uses hundreds of models with learned weights.
    Our alpha is a simple starting point.
    """

    def __init__(self, collaborative: CollaborativeFilteringStrategy,
                 content_based: ContentBasedStrategy, alpha: float = 0.7):
        self._collab  = collaborative   # Collaborative filtering strategy
        self._content = content_based   # Content-based strategy
        self._alpha   = alpha           # Weight for collaborative (0.0 to 1.0)
        # alpha=1.0: pure collaborative. alpha=0.0: pure content-based.

    def recommend(self, user_id: str, items: List[Item],
                  matrix: UserItemMatrix, limit: int = 10) -> List[Tuple[Item, float]]:
        """
        Merge collaborative and content-based recommendations.
        
        APPROACH:
        1. Get top-N×2 from each strategy (more candidates before merging)
        2. Combine scores: score = alpha × collab_score + (1-alpha) × content_score
        3. Sort by combined score
        4. Return top-N
        """
        collab_recs  = self._collab.recommend(user_id, items, matrix, limit * 2)
        content_recs = self._content.recommend(user_id, items, matrix, limit * 2)

        # Build score maps for merging
        collab_map  = {item.id: score for item, score in collab_recs}
        content_map = {item.id: score for item, score in content_recs}

        # Get all candidate items from either strategy
        all_item_ids = set(collab_map.keys()) | set(content_map.keys())
        # | on sets = union (elements in EITHER set)

        item_lookup = {item.id: item for item in items}
        combined: List[Tuple[Item, float]] = []

        for item_id in all_item_ids:
            item = item_lookup.get(item_id)
            if not item: continue

            c_score = collab_map.get(item_id, 0.0)    # Collaborative score (0 if not in collab results)
            b_score = content_map.get(item_id, 0.0)   # Content score

            # Weighted combination
            combined_score = self._alpha * c_score + (1 - self._alpha) * b_score
            combined.append((item, combined_score))

        combined.sort(key=lambda x: x[1], reverse=True)
        return combined[:limit]


def demo_recommendation():
    """Demonstrates the hybrid recommendation engine."""
    # Create items
    items = [
        Item("i1", "Inception",        ["sci-fi", "mind-bending", "nolan"], popularity=0.95),
        Item("i2", "Interstellar",     ["sci-fi", "space", "nolan"],        popularity=0.92),
        Item("i3", "The Dark Knight",  ["action", "superhero", "nolan"],    popularity=0.98),
        Item("i4", "Avengers",         ["action", "superhero", "marvel"],   popularity=0.90),
        Item("i5", "La La Land",       ["romance", "music", "drama"],       popularity=0.85),
        Item("i6", "Tenet",            ["sci-fi", "mind-bending", "nolan"], popularity=0.80),
        Item("i7", "Oppenheimer",      ["history", "drama", "nolan"],       popularity=0.91),
    ]

    # Create interaction matrix
    matrix = UserItemMatrix()

    # User A: loves Nolan films
    for item_id, score in [("i1",0.95), ("i3",0.90), ("i7",0.85)]:
        matrix.record(UserInteraction("user_A", item_id, score))

    # User B: also loves Nolan (similar to A)
    for item_id, score in [("i1",0.90), ("i2",0.95), ("i3",0.85), ("i6",0.88)]:
        matrix.record(UserInteraction("user_B", item_id, score))

    # User C: loves Marvel/action
    for item_id, score in [("i4",0.95), ("i3",0.80)]:
        matrix.record(UserInteraction("user_C", item_id, score))

    # Build engine
    engine = HybridRecommendationEngine(
        collaborative=CollaborativeFilteringStrategy(k_neighbors=2),
        content_based=ContentBasedStrategy(),
        alpha=0.6   # 60% collaborative, 40% content-based
    )

    print("\n" + "="*60)
    print("RECOMMENDATIONS FOR User A (loves Nolan):")
    print("="*60)
    recs = engine.recommend("user_A", items, matrix, limit=3)
    for item, score in recs:
        print(f"  {item.title:20s} | Score: {score:.3f} | Tags: {item.tags}")
    # Expected: Interstellar, Tenet (similar to what User A liked, and User B (similar) liked them)
```

---

## PART 3: RAG System (Retrieval-Augmented Generation)

```python
# rag_system_lld.py
"""
WHAT IS RAG?
RAG = Retrieval-Augmented Generation.
Used by: Perplexity.ai, ChatGPT with browsing, Gemini with Search, Claude.ai.

THE PROBLEM WITH LLMs ALONE:
1. Training data cutoff: LLM knows nothing after its training date.
2. Hallucination: LLM invents facts it doesn't know.
3. Private data: LLM wasn't trained on YOUR company's documents.

THE RAG SOLUTION:
Before asking the LLM, RETRIEVE relevant documents from your knowledge base.
Inject those documents into the LLM's context as REFERENCE.
LLM generates response GROUNDED in the retrieved facts.

REAL-WORLD EXAMPLES:
- "What is our Q3 revenue?" → RAG fetches financial reports → LLM answers from those reports.
- "How do I fix this error?" → RAG fetches relevant docs/Stack Overflow → LLM answers.
- Perplexity: "What happened yesterday?" → RAG searches the web → LLM summarizes.

KEY CONCEPTS:
Embedding: converting text to a vector of numbers that captures semantic meaning.
Vector Database: stores and searches embeddings by similarity.
Chunking: splitting documents into small pieces before embedding.
"""

from __future__ import annotations
import math
import uuid
import threading
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from abc import ABC, abstractmethod


# ══════════════════════════════════════════════════════════════════════════════
# EMBEDDING — Text to Vector
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Embedding:
    """
    A vector representation of text.
    
    WHAT IS AN EMBEDDING?
    An embedding converts text to a list of numbers (a vector).
    Similar texts → similar vectors (close in "embedding space").
    
    Example (simplified):
    "I love Python" → [0.2, 0.8, 0.1, -0.3, ...]  (1536-dimensional vector for OpenAI ada-002)
    "Python is great" → [0.19, 0.79, 0.11, -0.31, ...]  (very similar!)
    "I love pizza" → [0.7, 0.1, 0.9, 0.2, ...]  (different — different meaning)
    
    Similarity = cosine similarity between vectors.
    
    WHY DOES THIS MATTER FOR RAG?
    User asks: "How to fix memory leak in Python?"
    We embed the question → search for chunks with similar embeddings.
    "Python garbage collector" chunk matches because semantically similar.
    """
    vector: List[float]    # The actual embedding vector (1536 floats for OpenAI ada-002)
    text:   str            # The original text this was embedded from
    model:  str = "text-embedding-ada-002"   # Which embedding model was used

    @property
    def dimension(self) -> int:
        return len(self.vector)


class IEmbeddingModel(ABC):
    """
    STRATEGY INTERFACE for embedding models.
    
    Real options:
    - OpenAI text-embedding-ada-002: 1536 dimensions, $0.0001/1K tokens
    - Google text-embedding-004: 768 dimensions, free tier
    - Cohere embed-english-v3: 1024 dimensions
    - Local: SentenceTransformers (free, runs on your machine)
    """

    @abstractmethod
    def embed(self, text: str) -> Embedding: ...

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[Embedding]: ...


class MockEmbeddingModel(IEmbeddingModel):
    """
    Simulated embedding model for demo purposes.
    
    REAL IMPLEMENTATION:
    import openai
    response = openai.embeddings.create(
        input=text,
        model="text-embedding-ada-002"
    )
    vector = response.data[0].embedding  # List of 1536 floats
    """

    DIMENSION = 128   # Simplified (real is 1536 or more)

    def embed(self, text: str) -> Embedding:
        """
        Create a deterministic fake embedding.
        In real system: HTTP call to embedding API.
        
        DETERMINISTIC: same text always gives same vector.
        We use hash to simulate this.
        """
        import hashlib
        hash_bytes = hashlib.sha256(text.encode()).digest()
        # digest() = 32 bytes. We use these bytes to create a vector.

        # Create 128-dimensional vector from hash
        vector = []
        for i in range(0, min(32, len(hash_bytes))):
            vector.append((hash_bytes[i] - 128) / 128.0)
            # Normalize to [-1, 1] range (typical for embeddings)

        # Pad to DIMENSION with zeros if needed
        while len(vector) < self.DIMENSION:
            vector.append(0.0)

        return Embedding(vector=vector[:self.DIMENSION], text=text)

    def embed_batch(self, texts: List[str]) -> List[Embedding]:
        return [self.embed(t) for t in texts]


# ══════════════════════════════════════════════════════════════════════════════
# VECTOR DATABASE — Similarity Search
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class VectorDocument:
    """
    A document chunk stored in the vector database.
    
    CHUNKING STRATEGY:
    Why chunk documents instead of storing whole documents?
    1. LLM context window limits: can't fit a 100-page PDF in context.
    2. Better retrieval: smaller, focused chunks match queries more precisely.
    3. Cost: only retrieve relevant parts, not entire documents.
    
    CHUNK SIZE RECOMMENDATIONS:
    - 200-500 tokens per chunk (sweet spot)
    - Overlap: each chunk overlaps with next by 20% (avoids missing info at boundaries)
    """
    id:        str
    text:      str        # The actual text content of this chunk
    embedding: Embedding  # Vector representation for similarity search
    source:    str        # Which document this came from ("handbook.pdf", "api_docs.md")
    page_num:  int = 0    # Page number in source document
    metadata:  dict = field(default_factory=dict)   # Any extra info


class VectorDatabase(ABC):
    """
    INTERFACE for vector similarity search.
    
    Production options:
    - Pinecone: managed vector DB, fastest
    - Weaviate: open source, self-hosted
    - pgvector: PostgreSQL extension (easiest to add to existing PostgreSQL)
    - Chroma: lightweight, good for prototypes
    - FAISS: Facebook's library, excellent for large scale
    
    All implement the same interface: upsert + similarity_search
    """

    @abstractmethod
    def upsert(self, doc: VectorDocument) -> None: ...

    @abstractmethod
    def similarity_search(self, query_embedding: Embedding,
                          k: int = 5,
                          min_similarity: float = 0.0) -> List[Tuple[VectorDocument, float]]:
        """
        Find the K most similar documents to the query embedding.
        Returns: list of (document, similarity_score) sorted by similarity descending.
        similarity_score: 0.0 to 1.0 (higher = more similar = more relevant)
        """
        ...


class InMemoryVectorDB(VectorDatabase):
    """
    In-memory vector database using brute-force cosine similarity.
    
    BRUTE FORCE:
    For each query: compare against ALL stored vectors.
    O(N × D): N documents, D dimensions.
    
    WORKS FOR: up to ~100K documents (fast enough).
    
    PRODUCTION (millions of documents): Use FAISS with ANN (Approximate Nearest Neighbor).
    ANN sacrifices some accuracy for massive speed improvement (100× faster than brute force).
    Algorithms: HNSW (hierarchical navigable small world), IVF (inverted file index).
    """

    def __init__(self):
        self._docs: Dict[str, VectorDocument] = {}   # id → document
        self._lock = threading.RLock()

    def upsert(self, doc: VectorDocument) -> None:
        """Add or update a document in the vector DB."""
        with self._lock:
            self._docs[doc.id] = doc

    def similarity_search(self, query_embedding: Embedding,
                          k: int = 5,
                          min_similarity: float = 0.0) -> List[Tuple[VectorDocument, float]]:
        """
        Find K most similar documents using cosine similarity.
        
        COSINE SIMILARITY BETWEEN VECTORS:
        cosine_sim(A, B) = (A · B) / (|A| × |B|)
        (Same as before but for raw float lists, not dicts)
        """
        with self._lock:
            scores: List[Tuple[VectorDocument, float]] = []

            for doc in self._docs.values():
                sim = self._cosine_similarity(
                    query_embedding.vector,
                    doc.embedding.vector
                )
                if sim >= min_similarity:
                    scores.append((doc, sim))

            scores.sort(key=lambda x: x[1], reverse=True)
            return scores[:k]

    @staticmethod
    def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        """Cosine similarity between two float vectors."""
        if len(vec_a) != len(vec_b):
            min_len = min(len(vec_a), len(vec_b))
            vec_a, vec_b = vec_a[:min_len], vec_b[:min_len]

        dot    = sum(a * b for a, b in zip(vec_a, vec_b))
        # zip(A, B): pairs elements: [(a1,b1), (a2,b2), ...]
        # sum(a*b for a,b in ...): compute dot product

        mag_a  = math.sqrt(sum(a**2 for a in vec_a))
        mag_b  = math.sqrt(sum(b**2 for b in vec_b))

        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)


# ══════════════════════════════════════════════════════════════════════════════
# DOCUMENT PROCESSOR — Chunking
# ══════════════════════════════════════════════════════════════════════════════

class DocumentProcessor:
    """
    Processes raw documents into chunks and stores them in the vector DB.
    
    PIPELINE:
    Raw text → Chunks → Embeddings → Vector DB
    
    This is the "indexing" phase of RAG.
    Done once when adding new documents.
    Querying is done at runtime.
    """

    def __init__(self, embedding_model: IEmbeddingModel, vector_db: VectorDatabase):
        self._embedder = embedding_model
        self._vector_db = vector_db

    def process(self, text: str, source: str,
                chunk_size: int = 500, overlap: int = 100) -> int:
        """
        Process a document: chunk it and store in vector DB.
        Returns: number of chunks created.
        
        CHUNKING WITH OVERLAP:
        Without overlap: "...end of chunk 1. Start of chunk 2..."
        If a sentence spans the chunk boundary → split and context is lost.
        
        With overlap (100 chars): chunk 1 ends at char 500, chunk 2 starts at char 400.
        The 100-char overlap ensures boundary sentences appear in both chunks.
        """
        chunks = self._chunk_text(text, chunk_size, overlap)
        
        # Embed all chunks (batch for efficiency)
        embeddings = self._embedder.embed_batch(chunks)
        
        # Store in vector DB
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            # zip pairs each chunk with its corresponding embedding
            doc = VectorDocument(
                id=str(uuid.uuid4()),
                text=chunk,
                embedding=emb,
                source=source,
                page_num=i,   # Approximate page/chunk number
                metadata={"chunk_index": i, "total_chunks": len(chunks)}
            )
            self._vector_db.upsert(doc)
        
        return len(chunks)

    def _chunk_text(self, text: str, chunk_size: int, overlap: int) -> List[str]:
        """
        Split text into overlapping chunks.
        
        STEP BY STEP for text "abcdefghij" with chunk_size=5, overlap=2:
        Chunk 0: chars 0-4 = "abcde"
        Chunk 1: chars 3-7 = "defgh" (starts at 5-2=3 due to overlap)
        Chunk 2: chars 6-9 = "ghij"  (starts at 8-2=6 due to overlap)
        
        Each chunk starts (chunk_size - overlap) chars after previous start.
        """
        chunks = []
        step = chunk_size - overlap
        # step = how many characters to advance between chunk starts

        for start in range(0, len(text), step):
            # range(start, stop, step): generates 0, step, 2*step, ...
            end   = start + chunk_size
            chunk = text[start:end]   # Python slice: characters from start to end-1
            if chunk.strip():         # Skip empty/whitespace chunks
                chunks.append(chunk)
            if end >= len(text):
                break   # We've reached the end of the text

        return chunks if chunks else [text]
        # If text is shorter than chunk_size: return entire text as one chunk


# ══════════════════════════════════════════════════════════════════════════════
# RAG SERVICE — Orchestrates Retrieval + Generation
# ══════════════════════════════════════════════════════════════════════════════

class RAGService:
    """
    RAG = Retrieval-Augmented Generation.
    
    QUERY PIPELINE (happens on every user question):
    1. Embed the user's query (convert question to vector)
    2. Search vector DB for similar chunks (retrieve relevant context)
    3. Build a prompt: [System] + [Retrieved Context] + [User Question]
    4. Call LLM with the augmented prompt
    5. LLM generates answer GROUNDED in the retrieved context
    6. Return answer
    
    WHY THIS IS POWERFUL:
    - LLM generates answer only from retrieved documents → less hallucination
    - Fresh documents (updated daily) → no training cutoff problem
    - Source attribution: you know WHICH document the answer came from
    """

    SYSTEM_PROMPT_TEMPLATE = """You are a helpful assistant. Answer the user's question 
based ONLY on the following retrieved context. If the context doesn't contain 
enough information, say so honestly. Do NOT make up facts.

RETRIEVED CONTEXT:
{context}

---
Answer based only on the above context."""

    def __init__(self, embedding_model: IEmbeddingModel,
                 vector_db: VectorDatabase,
                 llm_adapter: ILLMAdapter):
        self._embedder  = embedding_model
        self._vector_db = vector_db
        self._llm       = llm_adapter

    def query(self, question: str, k: int = 5,
              min_similarity: float = 0.3) -> dict:
        """
        Answer a question using RAG.
        
        Returns:
        {
            "answer": str,           # LLM's response
            "sources": List[str],    # Which documents were cited
            "context_used": str      # What was retrieved and sent to LLM
        }
        """
        # Step 1: Embed the question
        query_embedding = self._embedder.embed(question)
        # question → vector (same embedding space as our stored documents)

        # Step 2: Retrieve relevant chunks
        retrieved = self._vector_db.similarity_search(
            query_embedding, k=k, min_similarity=min_similarity
        )
        # Retrieved: [(VectorDocument, similarity_score), ...]
        # Sorted by similarity: most relevant first

        if not retrieved:
            return {
                "answer": "I couldn't find relevant information to answer your question.",
                "sources": [],
                "context_used": ""
            }

        # Step 3: Build context string from retrieved chunks
        context_parts = []
        sources = []
        for doc, score in retrieved:
            context_parts.append(
                f"[Source: {doc.source} | Relevance: {score:.2f}]\n{doc.text}"
            )
            if doc.source not in sources:
                sources.append(doc.source)

        context = "\n\n---\n\n".join(context_parts)
        # Join chunks with separator for readability

        # Step 4: Build the augmented prompt
        system_prompt = self.SYSTEM_PROMPT_TEMPLATE.format(context=context)
        # .format() fills in the {context} placeholder with our retrieved text

        # Step 5: Call LLM with augmented context
        messages = [
            {"role": "system",  "content": system_prompt},
            {"role": "user",    "content": question}
        ]
        response = self._llm.generate(
            messages=messages,
            model="gpt-4o",
            max_tokens=1000,
            temperature=0.1    # Low temperature: factual answers need precision
        )

        return {
            "answer":       response.content,
            "sources":      sources,
            "context_used": context,
            "tokens_used":  response.total_tokens,
            "chunks_found": len(retrieved)
        }

    def index_document(self, text: str, source: str) -> int:
        """Add a new document to the knowledge base."""
        processor = DocumentProcessor(self._embedder, self._vector_db)
        n_chunks = processor.process(text, source)
        print(f"Indexed '{source}': {n_chunks} chunks created")
        return n_chunks


def demo_rag():
    """Demonstrate the RAG system."""
    # Setup
    embedder    = MockEmbeddingModel()
    vector_db   = InMemoryVectorDB()
    llm_adapter = OpenAIAdapter()   # From Part 1
    rag         = RAGService(embedder, vector_db, llm_adapter)

    # Index some documents
    company_doc = """
    Our company, TechCorp, was founded in 2018 by Sachin Kumar and Priya Sharma.
    We specialize in AI-powered SaaS products for enterprise customers.
    Our flagship product, DataSense, uses machine learning to analyze business data.
    As of Q3 2025, we have 500 enterprise customers and 200 employees.
    Revenue in 2024 was ₹150 crore, up 40% from 2023.
    """
    rag.index_document(company_doc, "company_overview.pdf")

    product_doc = """
    DataSense features:
    - Real-time dashboard with 50+ pre-built charts
    - AI-powered anomaly detection (finds unusual patterns in your data)
    - Integration with 100+ data sources (Excel, Google Sheets, MySQL, etc.)
    - Natural language queries: ask questions in plain English
    - Pricing: ₹50,000/month for up to 10 users, ₹10,000 per additional user
    """
    rag.index_document(product_doc, "product_specs.pdf")

    print("\n" + "="*60)
    print("RAG QUERY DEMO")
    print("="*60)

    # Query the RAG system
    result = rag.query("What was TechCorp's revenue in 2024?")
    print(f"\nQ: What was TechCorp's revenue in 2024?")
    print(f"A: {result['answer']}")
    print(f"Sources: {result['sources']}")
    print(f"Chunks used: {result['chunks_found']}")

    result2 = rag.query("How much does DataSense cost for 15 users?")
    print(f"\nQ: How much does DataSense cost for 15 users?")
    print(f"A: {result2['answer']}")


if __name__ == "__main__":
    print("=" * 70)
    print("PART 1: LLM SERVICE")
    print("=" * 70)
    demo_llm_service()

    print("\n" + "=" * 70)
    print("PART 2: RECOMMENDATION ENGINE")
    print("=" * 70)
    demo_recommendation()

    print("\n" + "=" * 70)
    print("PART 3: RAG SYSTEM")
    print("=" * 70)
    demo_rag()
```

---

## STEP 4 — AI System Trade-offs

```
TRADE-OFF 1: RAG vs Fine-tuning
  Fine-tuning: Train the LLM on your specific data. LLM "learns" your domain.
  Pro: Can learn writing style, domain concepts.
  Con: Expensive ($1000s to fine-tune GPT-4). Data stays in training → can't update easily.
  
  RAG: Keep base LLM, retrieve relevant context at query time.
  Pro: Cheap. Knowledge base updates daily (no retraining). Citations/sources available.
  Con: Context window limited. Retrieval can miss relevant info.
  
  When to use which?
  - Update knowledge frequently (news, company docs, pricing): RAG
  - Domain-specific style/behavior (medical, legal): Fine-tuning
  - Large knowledge base with precise facts: RAG (hallucination-resistant)
  - MAANG default answer: "Start with RAG, fine-tune if needed"

TRADE-OFF 2: Collaborative vs Content-based for cold start
  COLD START PROBLEM: new user has no history. What do you recommend?
  
  Collaborative filtering: fails completely (no ratings to compare).
  Content-based: also fails (no liked items to find similar ones from).
  
  Solutions:
  1. Onboarding quiz: "Pick 5 genres you like" → seed content-based.
  2. Demographics-based: recommend popular items for similar age/location.
  3. Popular items: simplest — recommend trending content.
  4. Progressive personalization: start generic, get more personalized over time.
  
  In our HybridEngine: ContentBasedStrategy returns popular items for new users.

TRADE-OFF 3: Vector DB choice — pgvector vs Pinecone
  pgvector: Extension to PostgreSQL. Store vectors in your existing DB.
  Pro: No new infrastructure. Transactional consistency with other data. Free.
  Con: Not as fast for very large scale (>1M vectors).
  
  Pinecone: Purpose-built vector DB (managed cloud service).
  Pro: Extremely fast. Scales to billions of vectors. Managed (no ops).
  Con: Cost ($70/month minimum). Another service to maintain.
  
  Decision matrix:
  < 100K vectors + PostgreSQL already in use → pgvector
  > 1M vectors OR need < 10ms latency → Pinecone/Weaviate

TRADE-OFF 4: Streaming vs non-streaming for LLM
  Non-streaming: wait for complete response (2-10 seconds). Show all at once.
  Streaming: show partial responses as they're generated (word by word).
  
  User perception: streaming FEELS much faster even if total time is the same.
  Streaming makes a 5-second response feel immediate.
  
  Implementation cost: streaming requires: server-sent events (SSE) or WebSocket.
  Backend: yield chunks (Generator). Frontend: process EventSource stream.
  
  Most production LLM APIs default to streaming. We should too.

TRADE-OFF 5: Context window management strategies
  PROBLEM: GPT-4o has 128K token limit. Long conversations exceed this.
  
  Strategy 1 (what we built): Rolling window — drop oldest messages.
  Simple. Fast. Loses old context. User might need to repeat themselves.
  
  Strategy 2: Summarization — periodically summarize old messages.
  "Earlier, we discussed: you're building a payment system, using Python..."
  Keep the summary (compact) + recent messages (full detail).
  
  Strategy 3: RAG over conversation history.
  Store old messages in vector DB. On each query, retrieve relevant past messages.
  "When did we discuss the database choice?" → semantic search retrieves that exact exchange.
  
  Production systems use Strategy 2 or 3 for very long conversations.
```

---

## STEP 5 — Interview Follow-Ups

```
Q: "How would you design a system like Perplexity.ai?"
A:
  Perplexity = RAG with real-time web search.
  
  Pipeline:
  1. User asks question
  2. Query rewriter: expand query for better search ("What is RAG?" → "retrieval augmented generation LLM")
  3. Web search: call Bing/Google Search API → get top 10 URLs
  4. Scraper: fetch and parse each URL's text content
  5. Chunker + Embedder: chunk and embed fetched content
  6. Retriever: similarity search → top-K relevant chunks
  7. LLM: generate answer with sources cited
  8. Return answer + sources
  
  In LLD: RAGService.query() + WebSearchAdapter (implements IDocumentSource).
  New documents fetched and indexed for each query (unlike our static index).

Q: "How do you prevent LLM hallucination in RAG?"
A:
  1. Temperature=0.1 for factual queries (deterministic output).
  2. Strict prompting: "Answer ONLY from the provided context."
  3. Confidence threshold: if max similarity < 0.6, say "I don't know."
  4. Source grounding: require LLM to cite specific chunks.
  5. Verifier model: second LLM call to check if answer is supported by context.
     "Does this answer contradict the provided sources?" → Yes/No.
  6. Fallback: if RAG retrieval returns nothing useful → "I don't have information on that."

Q: "How do recommendation engines handle seasonality?"
A:
  Seasonality: Diwali → more shopping for ethnic wear. Christmas → gifts.
  Static collaborative/content-based doesn't account for time.
  
  Solutions:
  1. Time-decayed scores: recent interactions weighted more than old ones.
     score = original_score × exp(-decay_rate × days_since_interaction)
     Interaction from 2 years ago matters less than yesterday's.
  
  2. Seasonal features in the model: day_of_week, month, festival as input features.
  
  3. Trending items: blend recommendations with trending items in current period.
     "Trending this Diwali: {items}" → add to recommendations.
  
  In our UserItemMatrix: add decay to UserInteraction.score before computing similarity.

Q: "How would you scale the LLM service to 1M requests/day?"
A:
  1M requests/day = 11.5 requests/sec.
  
  - Stateless API servers: horizontally scale (10 servers × 2 RPS each = 20 RPS).
  - Rate limiting in Redis (shared across all servers, not in-memory per server).
  - Request queue (Kafka): absorb spikes. LLM workers pull from queue.
  - LLM call optimization:
    a) Caching: same prompt → same response. Cache in Redis with 1hr TTL.
       (Exact match only — LLMs are deterministic at temperature=0)
    b) Prompt compression: summarize long system prompts (fewer tokens = cheaper).
  - Cost optimization: route simple queries to fast/cheap model (GPT-4o-mini).
    Complex queries → powerful model (GPT-o1). 
    Classification step: "Is this query simple or complex?"
```

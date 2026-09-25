# CS03: LLD — WhatsApp
## Class Design, Patterns, Full Code | Python + Java + C++

---

## STEP 1 — Requirements & Entities

```
FUNCTIONAL (LLD scope):
  1. Send/receive text, image, video, document messages
  2. One-to-one chats and Group chats (up to 256 members)
  3. Message delivery states: SENT → DELIVERED → READ (double blue tick)
  4. Message reactions (emoji reactions)
  5. Message quoting/reply (reply to specific message)
  6. Online/last seen status
  7. End-to-end encryption metadata (key exchange model)

KEY ENTITIES:
  User          — identity, status, profile
  Message       — content + metadata + delivery state
  Chat          — 1:1 conversation (two participants)
  Group         — multi-party chat with admin roles
  MessageStore  — append-only log per chat
  DeliveryTracker — tracks per-recipient delivery/read receipts
  MediaMessage  — extends Message with media metadata
  Reaction      — emoji response to a message

KEY BEHAVIOURS:
  Chat.sendMessage(sender, content) → Message
  Group.addMember(admin, user) → bool
  Group.sendMessage(sender, content) → Message (fan-out)
  Message.markDelivered(userId) → void
  Message.markRead(userId) → void
  DeliveryTracker.getStatus(message) → MessageStatus
  User.setStatus(StatusType) → void
```

---

## STEP 2 — Class Diagram

```
[User]                    [Message]                    [Chat]
──────                    ─────────                    ──────
- id: UUID                - id: UUID                   - id: UUID
- phone: str              - sender: User               - participants: [User, User]
- displayName: str        - chatId: UUID               - messages: List[Message]
- avatarUrl: str          - content: MessageContent    - createdAt: datetime
- publicKey: bytes        - type: MessageType          ──────
- status: OnlineStatus    - status: MessageStatus      + sendMessage(User,str): Message
- lastSeen: datetime      - sentAt: datetime           + getMessages(limit): List
──────                    - deliveredAt: datetime?     + getUnreadCount(User): int
+ setOnline(): void       - readAt: datetime?
+ setOffline(): void      - replyTo: Message?          [Group]
+ updateStatus(): void    - reactions: List[Reaction]  ──────
                          - isDeleted: bool            - id: UUID
[MessageContent]          ──────                       - name: str
─────────────             + markDelivered(uid): void   - members: Dict[User, Role]
- type: ContentType       + markRead(uid): void        - messages: List[Message]
- text: str?              + addReaction(uid,emoji): void  - admins: Set[UUID]
- mediaUrl: str?          + deleteForMe(uid): void     ──────
- thumbUrl: str?          + deleteForAll(): void       + addMember(admin,User): bool
- sizeBytes: int          + getStatus(): MsgStatus     + removeMember(admin,User): bool
- durationSec: int                                     + sendMessage(User,str): Message
                          [Reaction]                   + promoteAdmin(admin,User): bool
[DeliveryTracker]         ──────────                   + getOnlineCount(): int
─────────────────         - userId: UUID
- receipts: Dict[uid→Receipt]   - emoji: str
─────────────────         - reactedAt: datetime

PATTERNS USED:
  State    → MessageStatus (PENDING→SENT→DELIVERED→READ) state machine
  Strategy → MessageContent (text vs media vs location) polymorphic rendering
  Observer → DeliveryTracker notifies sender on status change
  Template Method → BaseChat.sendMessage(); Chat/Group override fan-out logic
  Memento  → Message.deleteForMe (stores per-user deleted set, original preserved)
  Flyweight → Reaction emoji strings shared across all reactions (intern)
```

---

## STEP 3 — Python Implementation (Deep)

```python
# whatsapp_lld.py
from __future__ import annotations
import uuid
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional, List, Dict, Set, Callable


# ── ENUMS ─────────────────────────────────────────────────────────────────────

class MessageStatus(Enum):
    """
    STATE MACHINE:
      PENDING → SENT → DELIVERED → READ
    Transitions are one-directional (can't go backwards).
    """
    PENDING   = 0
    SENT      = 1
    DELIVERED = 2
    READ      = 3

    def can_transition_to(self, next_status: MessageStatus) -> bool:
        return next_status.value > self.value

class ContentType(Enum):
    TEXT     = auto()
    IMAGE    = auto()
    VIDEO    = auto()
    DOCUMENT = auto()
    AUDIO    = auto()
    LOCATION = auto()

class GroupRole(Enum):
    MEMBER = auto()
    ADMIN  = auto()
    OWNER  = auto()

class OnlineStatus(Enum):
    ONLINE  = auto()
    OFFLINE = auto()


# ── VALUE OBJECTS ─────────────────────────────────────────────────────────────

@dataclass
class MessageContent:
    content_type: ContentType
    text:        Optional[str]   = None
    media_url:   Optional[str]   = None
    thumb_url:   Optional[str]   = None
    size_bytes:  int             = 0
    duration_sec: int            = 0
    latitude:    Optional[float] = None
    longitude:   Optional[float] = None

    def render_preview(self) -> str:
        """Strategy-like: each content type has its own rendering."""
        if self.content_type == ContentType.TEXT:
            return (self.text or "")[:100]
        if self.content_type == ContentType.IMAGE:
            return f"[Photo: {self.size_bytes // 1024} KB]"
        if self.content_type == ContentType.VIDEO:
            return f"[Video: {self.duration_sec}s]"
        if self.content_type == ContentType.DOCUMENT:
            return f"[Document: {self.size_bytes // 1024} KB]"
        if self.content_type == ContentType.LOCATION:
            return f"[Location: {self.latitude:.4f}, {self.longitude:.4f}]"
        return "[Media]"

    @classmethod
    def text(cls, content: str) -> MessageContent:
        return cls(ContentType.TEXT, text=content)

    @classmethod
    def image(cls, url: str, thumb: str, size: int) -> MessageContent:
        return cls(ContentType.IMAGE, media_url=url, thumb_url=thumb, size_bytes=size)


@dataclass
class DeliveryReceipt:
    user_id:      str
    delivered_at: Optional[datetime] = None
    read_at:      Optional[datetime] = None

    def mark_delivered(self) -> None:
        if not self.delivered_at:
            self.delivered_at = datetime.utcnow()

    def mark_read(self) -> None:
        self.mark_delivered()
        if not self.read_at:
            self.read_at = datetime.utcnow()

    @property
    def status(self) -> MessageStatus:
        if self.read_at:       return MessageStatus.READ
        if self.delivered_at:  return MessageStatus.DELIVERED
        return MessageStatus.SENT


@dataclass
class Reaction:
    user_id:    str
    emoji:      str           # FLYWEIGHT: intern common emojis
    reacted_at: datetime = field(default_factory=datetime.utcnow)

    # FLYWEIGHT: pool of emoji strings to avoid duplication
    _emoji_pool: dict = field(default_factory=dict, init=False, repr=False)

    @staticmethod
    def intern_emoji(emoji: str) -> str:
        """Flyweight: return shared emoji string from pool."""
        _pool = Reaction._pool if hasattr(Reaction, '_pool') else {}
        if emoji not in _pool:
            _pool[emoji] = emoji
        Reaction._pool = _pool
        return _pool[emoji]
Reaction._pool: Dict[str, str] = {}


# ── USER ──────────────────────────────────────────────────────────────────────

class User:
    def __init__(self, phone: str, display_name: str):
        self.id           = str(uuid.uuid4())
        self.phone        = phone
        self.display_name = display_name
        self.avatar_url   = ""
        self.status       = OnlineStatus.OFFLINE
        self.last_seen    = datetime.utcnow()
        self._status_observers: List[Callable] = []
        self._lock        = threading.Lock()

    def set_online(self) -> None:
        with self._lock:
            self.status = OnlineStatus.ONLINE
            self._notify_status_observers()

    def set_offline(self) -> None:
        with self._lock:
            self.status    = OnlineStatus.OFFLINE
            self.last_seen = datetime.utcnow()
            self._notify_status_observers()

    def subscribe_status(self, callback: Callable) -> None:
        with self._lock:
            self._status_observers.append(callback)

    def _notify_status_observers(self) -> None:
        for cb in self._status_observers:
            cb(self)

    def __repr__(self) -> str:
        return f"User({self.display_name}, {self.status.name})"


# ── MESSAGE ───────────────────────────────────────────────────────────────────

class Message:
    """
    STATE PATTERN: MessageStatus transitions enforced via State machine.
    MEMENTO PATTERN: per-user deletion stored in _deleted_for set.
    """

    def __init__(self, sender: User, chat_id: str, content: MessageContent,
                 reply_to: Optional[Message] = None):
        self.id         = str(uuid.uuid4())
        self.sender     = sender
        self.chat_id    = chat_id
        self.content    = content
        self.reply_to   = reply_to
        self.sent_at    = datetime.utcnow()
        self._status    = MessageStatus.PENDING
        self._receipts: Dict[str, DeliveryReceipt] = {}
        self._reactions: Dict[str, Reaction] = {}      # userId → Reaction
        self._deleted_for: Set[str] = set()            # userIds for "delete for me"
        self._deleted_for_all = False
        self._lock      = threading.RLock()

    # ── State transitions ─────────────────────────────────────────────────────
    def mark_sent(self) -> None:
        with self._lock:
            if self._status == MessageStatus.PENDING:
                self._status = MessageStatus.SENT

    def mark_delivered(self, user_id: str) -> None:
        """
        Recipient device calls this when message received.
        Status = DELIVERED when ALL recipients delivered.
        """
        with self._lock:
            if user_id not in self._receipts:
                self._receipts[user_id] = DeliveryReceipt(user_id)
            self._receipts[user_id].mark_delivered()
            self._update_aggregate_status()

    def mark_read(self, user_id: str) -> None:
        with self._lock:
            if user_id not in self._receipts:
                self._receipts[user_id] = DeliveryReceipt(user_id)
            self._receipts[user_id].mark_read()
            self._update_aggregate_status()

    def _update_aggregate_status(self) -> None:
        """Aggregate status = minimum across all recipients."""
        if not self._receipts:
            return
        statuses = [r.status for r in self._receipts.values()]
        # Overall status is lowest common denominator
        if all(s == MessageStatus.READ for s in statuses):
            self._status = MessageStatus.READ
        elif all(s.value >= MessageStatus.DELIVERED.value for s in statuses):
            self._status = MessageStatus.DELIVERED
        else:
            self._status = MessageStatus.SENT

    def get_status_for(self, user_id: str) -> MessageStatus:
        with self._lock:
            r = self._receipts.get(user_id)
            return r.status if r else MessageStatus.SENT

    # ── Reactions ─────────────────────────────────────────────────────────────
    def add_reaction(self, user: User, emoji: str) -> None:
        interned = Reaction.intern_emoji(emoji)
        with self._lock:
            self._reactions[user.id] = Reaction(user.id, interned)

    def remove_reaction(self, user: User) -> bool:
        with self._lock:
            return self._reactions.pop(user.id, None) is not None

    def get_reactions(self) -> Dict[str, int]:
        """Returns {emoji: count}."""
        with self._lock:
            counts: Dict[str, int] = {}
            for r in self._reactions.values():
                counts[r.emoji] = counts.get(r.emoji, 0) + 1
            return counts

    # ── Deletion (Memento-like) ───────────────────────────────────────────────
    def delete_for_me(self, user: User) -> None:
        with self._lock:
            self._deleted_for.add(user.id)

    def delete_for_all(self, requestor: User) -> bool:
        """Only sender can delete for all, within 1 hour."""
        if requestor.id != self.sender.id:
            raise PermissionError("Only sender can delete for all")
        age = (datetime.utcnow() - self.sent_at).total_seconds()
        if age > 3600:
            raise ValueError("Cannot delete after 1 hour")
        with self._lock:
            self._deleted_for_all = True
            self.content = MessageContent.text("This message was deleted.")
            return True

    def is_visible_to(self, user: User) -> bool:
        if self._deleted_for_all: return False
        return user.id not in self._deleted_for

    @property
    def status(self) -> MessageStatus:
        with self._lock:
            return self._status

    def __repr__(self) -> str:
        return f"Message({self.sender.display_name}: {self.content.render_preview()[:30]})"


# ── BASE CHAT (Template Method) ───────────────────────────────────────────────

class BaseChat(ABC):
    """
    TEMPLATE METHOD PATTERN:
      send_message() defines the algorithm skeleton.
      _fan_out() is overridden by Chat (1 recipient) and Group (N recipients).
    """
    def __init__(self):
        self.id       = str(uuid.uuid4())
        self._messages: List[Message] = []
        self._lock    = threading.RLock()

    def send_message(self, sender: User, content: MessageContent,
                     reply_to: Optional[Message] = None) -> Message:
        """Template method: validate → create → store → fan-out → return."""
        self._validate_sender(sender)
        msg = Message(sender, self.id, content, reply_to)
        msg.mark_sent()
        with self._lock:
            self._messages.append(msg)
        self._fan_out(msg)    # Subclass fills in fan-out logic
        return msg

    @abstractmethod
    def _validate_sender(self, sender: User) -> None: ...

    @abstractmethod
    def _fan_out(self, message: Message) -> None: ...

    def get_messages(self, limit: int = 50,
                     before_id: Optional[str] = None) -> List[Message]:
        with self._lock:
            msgs = self._messages
            if before_id:
                idx = next((i for i, m in enumerate(msgs) if m.id == before_id), len(msgs))
                msgs = msgs[:idx]
            return msgs[-limit:]

    def get_unread_count(self, user: User) -> int:
        with self._lock:
            return sum(
                1 for m in self._messages
                if m.sender.id != user.id
                and m.get_status_for(user.id).value < MessageStatus.READ.value
                and m.is_visible_to(user)
            )


# ── CHAT (1:1) ────────────────────────────────────────────────────────────────

class Chat(BaseChat):
    def __init__(self, user_a: User, user_b: User):
        super().__init__()
        self.participants = (user_a, user_b)

    def _validate_sender(self, sender: User) -> None:
        if sender.id not in (p.id for p in self.participants):
            raise PermissionError(f"{sender} is not a participant in this chat")

    def _fan_out(self, message: Message) -> None:
        """In 1:1: only one recipient to notify."""
        recipient = next(p for p in self.participants if p.id != message.sender.id)
        # Simulate delivery if online (in prod: WebSocket push)
        if recipient.status == OnlineStatus.ONLINE:
            message.mark_delivered(recipient.id)

    def get_other_participant(self, user: User) -> User:
        return next(p for p in self.participants if p.id != user.id)


# ── GROUP CHAT ────────────────────────────────────────────────────────────────

class Group(BaseChat):
    MAX_MEMBERS = 256

    def __init__(self, name: str, creator: User):
        super().__init__()
        self.name = name
        self._members: Dict[str, GroupRole] = {creator.id: GroupRole.OWNER}
        self._users:   Dict[str, User]      = {creator.id: creator}
        self._member_lock = threading.RLock()

    def add_member(self, admin: User, new_member: User) -> bool:
        with self._member_lock:
            if self._members.get(admin.id) not in (GroupRole.ADMIN, GroupRole.OWNER):
                raise PermissionError("Only admins can add members")
            if len(self._members) >= self.MAX_MEMBERS:
                raise ValueError(f"Group is full ({self.MAX_MEMBERS} members max)")
            if new_member.id in self._members:
                return False
            self._members[new_member.id] = GroupRole.MEMBER
            self._users[new_member.id]   = new_member
            return True

    def remove_member(self, admin: User, member: User) -> bool:
        with self._member_lock:
            if self._members.get(admin.id) not in (GroupRole.ADMIN, GroupRole.OWNER):
                raise PermissionError("Only admins can remove members")
            if self._members.get(member.id) == GroupRole.OWNER:
                raise PermissionError("Cannot remove the owner")
            return bool(self._members.pop(member.id, None))

    def promote_admin(self, owner: User, member: User) -> bool:
        with self._member_lock:
            if self._members.get(owner.id) != GroupRole.OWNER:
                raise PermissionError("Only owner can promote admins")
            if member.id not in self._members:
                return False
            self._members[member.id] = GroupRole.ADMIN
            return True

    def _validate_sender(self, sender: User) -> None:
        with self._member_lock:
            if sender.id not in self._members:
                raise PermissionError(f"{sender} is not a group member")

    def _fan_out(self, message: Message) -> None:
        """Deliver to ALL online members except sender."""
        with self._member_lock:
            recipients = [u for uid, u in self._users.items()
                          if uid != message.sender.id]
        for r in recipients:
            if r.status == OnlineStatus.ONLINE:
                message.mark_delivered(r.id)

    def get_online_count(self) -> int:
        with self._member_lock:
            return sum(1 for u in self._users.values()
                       if u.status == OnlineStatus.ONLINE)

    @property
    def member_count(self) -> int:
        with self._member_lock:
            return len(self._members)


# ── DELIVERY TRACKER (Observer) ───────────────────────────────────────────────

class DeliveryTracker:
    """
    OBSERVER: message.sender subscribes to delivery events.
    In prod: pushed via WebSocket to sender's device.
    """
    def __init__(self):
        self._callbacks: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()

    def subscribe(self, message_id: str, callback: Callable[[MessageStatus], None]) -> None:
        with self._lock:
            self._callbacks.setdefault(message_id, []).append(callback)

    def notify(self, message: Message) -> None:
        with self._lock:
            cbs = self._callbacks.get(message.id, [])
        for cb in cbs:
            cb(message.status)


# ── WHATSAPP SERVICE (Facade) ─────────────────────────────────────────────────

class WhatsAppService:
    def __init__(self):
        self._users:    Dict[str, User]     = {}   # phone → User
        self._chats:    Dict[str, Chat]     = {}   # chatId → Chat
        self._groups:   Dict[str, Group]    = {}   # groupId → Group
        self._tracker   = DeliveryTracker()
        self._lock      = threading.RLock()

    def register(self, phone: str, name: str) -> User:
        with self._lock:
            if phone in self._users:
                raise ValueError(f"{phone} already registered")
            user = User(phone, name)
            self._users[phone] = user
            return user

    def get_or_create_chat(self, user_a: User, user_b: User) -> Chat:
        key = "_".join(sorted([user_a.id, user_b.id]))
        with self._lock:
            if key not in self._chats:
                self._chats[key] = Chat(user_a, user_b)
            return self._chats[key]

    def create_group(self, name: str, creator: User, members: List[User]) -> Group:
        group = Group(name, creator)
        for m in members:
            group.add_member(creator, m)
        with self._lock:
            self._groups[group.id] = group
        return group

    def send_text(self, sender: User, chat: BaseChat, text: str,
                  reply_to: Message = None) -> Message:
        content = MessageContent.text(text)
        msg = chat.send_message(sender, content, reply_to)
        return msg

    def react(self, user: User, message: Message, emoji: str) -> None:
        message.add_reaction(user, emoji)

    def delete_for_me(self, user: User, message: Message) -> None:
        message.delete_for_me(user)

    def delete_for_all(self, sender: User, message: Message) -> bool:
        return message.delete_for_all(sender)


# ── DEMO ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    wa = WhatsAppService()

    alice = wa.register("+91-9000000001", "Alice")
    bob   = wa.register("+91-9000000002", "Bob")
    carol = wa.register("+91-9000000003", "Carol")

    alice.set_online()
    bob.set_online()

    # 1:1 Chat
    chat = wa.get_or_create_chat(alice, bob)
    msg1 = wa.send_text(alice, chat, "Hey Bob! How are you?")
    print(f"Sent: {msg1}, Status: {msg1.status.name}")

    msg1.mark_delivered(bob.id)
    msg1.mark_read(bob.id)
    print(f"After read: {msg1.status.name}")    # READ

    # Reply
    msg2 = wa.send_text(bob, chat, "Hey Alice! Doing great, you?", reply_to=msg1)
    wa.react(alice, msg2, "❤️")
    print(f"Reactions: {msg2.get_reactions()}")

    # Group
    group = wa.create_group("Team Alpha", alice, [bob, carol])
    print(f"Group members: {group.member_count}")

    gmsg = wa.send_text(alice, group, "Meeting at 3pm!")
    print(f"Group message: {gmsg}")
    print(f"Unread for bob: {group.get_unread_count(bob)}")

    # Delete for me
    wa.delete_for_me(bob, gmsg)
    print(f"Visible to bob: {gmsg.is_visible_to(bob)}")     # False
    print(f"Visible to carol: {gmsg.is_visible_to(carol)}") # True
```

---

## STEP 4 — Java Implementation (Deep)

```java
// whatsapp_lld.java

import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.concurrent.locks.*;
import java.time.Instant;
import java.util.stream.*;

enum MessageStatus { PENDING(0), SENT(1), DELIVERED(2), READ(3);
    final int level;
    MessageStatus(int l) { level = l; }
}
enum ContentType  { TEXT, IMAGE, VIDEO, DOCUMENT, AUDIO, LOCATION }
enum GroupRole    { MEMBER, ADMIN, OWNER }
enum OnlineStatus { ONLINE, OFFLINE }

// ── MessageContent (Strategy-like) ───────────────────────────────────────────
record MessageContent(ContentType type, String text, String mediaUrl,
                      String thumbUrl, long sizeBytes, int durationSec) {
    static MessageContent text(String t)    { return new MessageContent(ContentType.TEXT, t, null, null, 0, 0); }
    static MessageContent image(String url, String thumb, long size) {
        return new MessageContent(ContentType.IMAGE, null, url, thumb, size, 0);
    }
    String renderPreview() {
        return switch (type) {
            case TEXT     -> text != null ? text.substring(0, Math.min(100, text.length())) : "";
            case IMAGE    -> "[Photo: " + sizeBytes / 1024 + " KB]";
            case VIDEO    -> "[Video: " + durationSec + "s]";
            case DOCUMENT -> "[Document: " + sizeBytes / 1024 + " KB]";
            default       -> "[Media]";
        };
    }
}

// ── DeliveryReceipt ───────────────────────────────────────────────────────────
class DeliveryReceipt {
    final String userId;
    volatile Instant deliveredAt, readAt;
    DeliveryReceipt(String uid) { userId = uid; }

    void markDelivered() { if (deliveredAt == null) deliveredAt = Instant.now(); }
    void markRead()      { markDelivered(); if (readAt == null) readAt = Instant.now(); }

    MessageStatus getStatus() {
        if (readAt != null)      return MessageStatus.READ;
        if (deliveredAt != null) return MessageStatus.DELIVERED;
        return MessageStatus.SENT;
    }
}

// ── Reaction (Flyweight) ──────────────────────────────────────────────────────
class Reaction {
    private static final Map<String, String> POOL = new ConcurrentHashMap<>();
    final String userId, emoji;
    final Instant reactedAt = Instant.now();

    Reaction(String userId, String emoji) {
        this.userId = userId;
        this.emoji  = POOL.computeIfAbsent(emoji, k -> k);  // Flyweight: intern
    }
}

// ── Message ───────────────────────────────────────────────────────────────────
class Message {
    private final String id = UUID.randomUUID().toString();
    private final User author;
    private final String chatId;
    private volatile MessageContent content;
    private final Message replyTo;
    private final Instant sentAt = Instant.now();
    private final Map<String, DeliveryReceipt> receipts = new ConcurrentHashMap<>();
    private final Map<String, Reaction>        reactions = new ConcurrentHashMap<>();
    private final Set<String> deletedFor = ConcurrentHashMap.newKeySet();
    private volatile boolean deletedForAll = false;
    private volatile MessageStatus aggregateStatus = MessageStatus.SENT;
    private final Object statusLock = new Object();

    Message(User author, String chatId, MessageContent content, Message replyTo) {
        this.author  = author;
        this.chatId  = chatId;
        this.content = content;
        this.replyTo = replyTo;
    }

    void markDelivered(String userId) {
        receipts.computeIfAbsent(userId, DeliveryReceipt::new).markDelivered();
        updateAggregateStatus();
    }

    void markRead(String userId) {
        receipts.computeIfAbsent(userId, DeliveryReceipt::new).markRead();
        updateAggregateStatus();
    }

    private void updateAggregateStatus() {
        synchronized (statusLock) {
            if (receipts.isEmpty()) return;
            boolean allRead      = receipts.values().stream().allMatch(r -> r.getStatus() == MessageStatus.READ);
            boolean allDelivered = receipts.values().stream().allMatch(r -> r.getStatus().level >= MessageStatus.DELIVERED.level);
            if      (allRead)      aggregateStatus = MessageStatus.READ;
            else if (allDelivered) aggregateStatus = MessageStatus.DELIVERED;
            else                   aggregateStatus = MessageStatus.SENT;
        }
    }

    MessageStatus getStatusFor(String userId) {
        DeliveryReceipt r = receipts.get(userId);
        return r != null ? r.getStatus() : MessageStatus.SENT;
    }

    void addReaction(String userId, String emoji) { reactions.put(userId, new Reaction(userId, emoji)); }
    boolean removeReaction(String userId)         { return reactions.remove(userId) != null; }

    Map<String, Long> getReactions() {
        return reactions.values().stream()
            .collect(Collectors.groupingBy(r -> r.emoji, Collectors.counting()));
    }

    void deleteForMe(String userId)     { deletedFor.add(userId); }
    boolean isVisibleTo(String userId)  { return !deletedForAll && !deletedFor.contains(userId); }

    boolean deleteForAll(User requestor) {
        if (!requestor.getId().equals(author.getId()))
            throw new SecurityException("Only sender can delete for all");
        long ageSeconds = Instant.now().getEpochSecond() - sentAt.getEpochSecond();
        if (ageSeconds > 3600) throw new IllegalStateException("Cannot delete after 1 hour");
        deletedForAll = true;
        content = MessageContent.text("This message was deleted.");
        return true;
    }

    MessageStatus getStatus() { return aggregateStatus; }
    String getId()            { return id; }
    User getAuthor()          { return author; }
    MessageContent getContent() { return content; }
    @Override public String toString() {
        return "Message(" + author + ": " + content.renderPreview() + ")";
    }
}

// ── User ──────────────────────────────────────────────────────────────────────
class User {
    private final String id       = UUID.randomUUID().toString();
    private final String phone, displayName;
    private volatile OnlineStatus status = OnlineStatus.OFFLINE;
    private volatile Instant lastSeen    = Instant.now();
    private final List<java.util.function.Consumer<User>> observers = new CopyOnWriteArrayList<>();

    User(String phone, String name) { this.phone = phone; this.displayName = name; }

    void setOnline()  { status = OnlineStatus.ONLINE; observers.forEach(cb -> cb.accept(this)); }
    void setOffline() { status = OnlineStatus.OFFLINE; lastSeen = Instant.now(); observers.forEach(cb -> cb.accept(this)); }
    void subscribeStatus(java.util.function.Consumer<User> cb) { observers.add(cb); }

    String getId()          { return id; }
    String getPhone()       { return phone; }
    String getDisplayName() { return displayName; }
    OnlineStatus getStatus(){ return status; }
    @Override public String toString() { return displayName; }
}

// ── BaseChat (Template Method) ────────────────────────────────────────────────
abstract class BaseChat {
    protected final String id = UUID.randomUUID().toString();
    protected final List<Message> messages = new CopyOnWriteArrayList<>();

    final Message sendMessage(User sender, MessageContent content, Message replyTo) {
        validateSender(sender);
        Message msg = new Message(sender, id, content, replyTo);
        messages.add(msg);
        fanOut(msg);
        return msg;
    }

    protected abstract void validateSender(User sender);
    protected abstract void fanOut(Message msg);

    List<Message> getMessages(int limit) {
        var all = messages;
        return all.subList(Math.max(0, all.size() - limit), all.size());
    }

    long getUnreadCount(User user) {
        return messages.stream()
            .filter(m -> !m.getAuthor().getId().equals(user.getId()))
            .filter(m -> m.isVisibleTo(user.getId()))
            .filter(m -> m.getStatusFor(user.getId()).level < MessageStatus.READ.level)
            .count();
    }
}

// ── Chat (1:1) ────────────────────────────────────────────────────────────────
class Chat extends BaseChat {
    private final User[] participants;
    Chat(User a, User b) { participants = new User[]{a, b}; }

    @Override protected void validateSender(User sender) {
        boolean valid = Arrays.stream(participants).anyMatch(p -> p.getId().equals(sender.getId()));
        if (!valid) throw new SecurityException(sender + " is not a participant");
    }

    @Override protected void fanOut(Message msg) {
        Arrays.stream(participants)
            .filter(p -> !p.getId().equals(msg.getAuthor().getId()))
            .filter(p -> p.getStatus() == OnlineStatus.ONLINE)
            .forEach(p -> msg.markDelivered(p.getId()));
    }
}

// ── Group ─────────────────────────────────────────────────────────────────────
class Group extends BaseChat {
    private static final int MAX_MEMBERS = 256;
    private final String name;
    private final Map<String, GroupRole> memberRoles = new ConcurrentHashMap<>();
    private final Map<String, User>      members     = new ConcurrentHashMap<>();

    Group(String name, User creator) {
        this.name = name;
        memberRoles.put(creator.getId(), GroupRole.OWNER);
        members.put(creator.getId(), creator);
    }

    boolean addMember(User admin, User newMember) {
        GroupRole role = memberRoles.get(admin.getId());
        if (role != GroupRole.ADMIN && role != GroupRole.OWNER)
            throw new SecurityException("Only admins can add members");
        if (memberRoles.size() >= MAX_MEMBERS)
            throw new IllegalStateException("Group is full");
        return memberRoles.putIfAbsent(newMember.getId(), GroupRole.MEMBER) == null
            && members.putIfAbsent(newMember.getId(), newMember) == null;
    }

    @Override protected void validateSender(User sender) {
        if (!memberRoles.containsKey(sender.getId()))
            throw new SecurityException(sender + " is not a group member");
    }

    @Override protected void fanOut(Message msg) {
        members.values().stream()
            .filter(u -> !u.getId().equals(msg.getAuthor().getId()))
            .filter(u -> u.getStatus() == OnlineStatus.ONLINE)
            .forEach(u -> msg.markDelivered(u.getId()));
    }

    int getMemberCount()   { return memberRoles.size(); }
    long getOnlineCount()  { return members.values().stream().filter(u -> u.getStatus() == OnlineStatus.ONLINE).count(); }
}

// ── WhatsApp Facade ───────────────────────────────────────────────────────────
class WhatsAppService {
    private final Map<String, User>  users  = new ConcurrentHashMap<>();  // phone→User
    private final Map<String, Chat>  chats  = new ConcurrentHashMap<>();
    private final Map<String, Group> groups = new ConcurrentHashMap<>();

    User register(String phone, String name) {
        if (users.containsKey(phone)) throw new IllegalArgumentException("Already registered: " + phone);
        User u = new User(phone, name);
        users.put(phone, u);
        return u;
    }

    Chat getOrCreateChat(User a, User b) {
        String key = Stream.of(a.getId(), b.getId()).sorted().collect(Collectors.joining("_"));
        return chats.computeIfAbsent(key, k -> new Chat(a, b));
    }

    Group createGroup(String name, User creator, List<User> members) {
        Group g = new Group(name, creator);
        members.forEach(m -> g.addMember(creator, m));
        groups.put(g.id, g);
        return g;
    }

    Message sendText(User sender, BaseChat chat, String text, Message replyTo) {
        return chat.sendMessage(sender, MessageContent.text(text), replyTo);
    }
}

// ── Demo ──────────────────────────────────────────────────────────────────────
class WhatsAppMain {
    public static void main(String[] args) {
        var wa    = new WhatsAppService();
        var alice = wa.register("+91-9000000001", "Alice");
        var bob   = wa.register("+91-9000000002", "Bob");
        var carol = wa.register("+91-9000000003", "Carol");

        alice.setOnline(); bob.setOnline();

        var chat = wa.getOrCreateChat(alice, bob);
        var msg1 = wa.sendText(alice, chat, "Hey Bob!", null);
        System.out.println("Sent: " + msg1 + ", Status: " + msg1.getStatus());

        msg1.markDelivered(bob.getId());
        msg1.markRead(bob.getId());
        System.out.println("After read: " + msg1.getStatus()); // READ

        var msg2 = wa.sendText(bob, chat, "Hey Alice! Doing great!", msg1);
        msg2.addReaction(alice.getId(), "❤️");
        System.out.println("Reactions: " + msg2.getReactions());

        var group = wa.createGroup("Team Alpha", alice, List.of(bob, carol));
        var gmsg  = wa.sendText(alice, group, "Meeting at 3pm!", null);
        System.out.println("Group unread (Bob): " + group.getUnreadCount(bob));

        gmsg.deleteForMe(bob.getId());
        System.out.println("Visible to Bob: "   + gmsg.isVisibleTo(bob.getId()));   // false
        System.out.println("Visible to Carol: " + gmsg.isVisibleTo(carol.getId())); // true
    }
}
```

---

## STEP 5 — C++ Implementation (Key Parts)

```cpp
// whatsapp_lld.cpp — key C++ specifics
// Full concurrency patterns for Message status tracking

#include <iostream>
#include <string>
#include <vector>
#include <unordered_map>
#include <unordered_set>
#include <memory>
#include <mutex>
#include <shared_mutex>
#include <atomic>
#include <chrono>
#include <optional>
#include <functional>
#include <stdexcept>

using Clock = std::chrono::system_clock;
using TP    = std::chrono::time_point<Clock>;

// ── Enums ─────────────────────────────────────────────────────────────────────
enum class MessageStatus { PENDING=0, SENT=1, DELIVERED=2, READ=3 };
enum class ContentType   { TEXT, IMAGE, VIDEO, DOCUMENT };
enum class GroupRole     { MEMBER, ADMIN, OWNER };
enum class OnlineStatus  { ONLINE, OFFLINE };

// ── MessageContent ────────────────────────────────────────────────────────────
struct MessageContent {
    ContentType type;
    std::string text;
    std::string mediaUrl;
    long        sizeBytes{0};
    int         durationSec{0};

    static MessageContent makeText(std::string t) {
        return {ContentType::TEXT, std::move(t), "", 0, 0};
    }

    std::string renderPreview() const {
        switch (type) {
            case ContentType::TEXT:  return text.substr(0, std::min((size_t)100, text.size()));
            case ContentType::IMAGE: return "[Photo: " + std::to_string(sizeBytes/1024) + " KB]";
            case ContentType::VIDEO: return "[Video: " + std::to_string(durationSec) + "s]";
            default:                 return "[Media]";
        }
    }
};

// ── DeliveryReceipt ───────────────────────────────────────────────────────────
struct DeliveryReceipt {
    std::string uid;
    std::optional<TP> deliveredAt;
    std::optional<TP> readAt;

    void markDelivered() { if (!deliveredAt) deliveredAt = Clock::now(); }
    void markRead()      { markDelivered(); if (!readAt) readAt = Clock::now(); }

    MessageStatus status() const {
        if (readAt)      return MessageStatus::READ;
        if (deliveredAt) return MessageStatus::DELIVERED;
        return MessageStatus::SENT;
    }
};

// ── Reaction (Flyweight) ──────────────────────────────────────────────────────
class EmojiPool {
    std::unordered_map<std::string, std::string> pool_;
    std::mutex mtx_;
public:
    const std::string& intern(const std::string& emoji) {
        std::lock_guard lk(mtx_);
        return pool_.emplace(emoji, emoji).first->second;
    }
    static EmojiPool& get() { static EmojiPool p; return p; }
};

struct Reaction {
    std::string userId;
    const std::string& emoji;  // reference to interned string
    TP reactedAt;
    Reaction(std::string uid, const std::string& e)
        : userId(std::move(uid))
        , emoji(EmojiPool::get().intern(e))
        , reactedAt(Clock::now()) {}
};

// ── User ──────────────────────────────────────────────────────────────────────
class User {
    static std::atomic<int> counter_;
    std::string id_, phone_, name_;
    std::atomic<OnlineStatus> status_{OnlineStatus::OFFLINE};
    std::vector<std::function<void(User*)>> observers_;
    mutable std::mutex obsMtx_;

public:
    User(std::string phone, std::string name)
        : id_("u" + std::to_string(++counter_))
        , phone_(std::move(phone)), name_(std::move(name)) {}

    void setOnline()  {
        status_.store(OnlineStatus::ONLINE, std::memory_order_release);
        std::lock_guard lk(obsMtx_);
        for (auto& cb : observers_) cb(this);
    }
    void setOffline() {
        status_.store(OnlineStatus::OFFLINE, std::memory_order_release);
        std::lock_guard lk(obsMtx_);
        for (auto& cb : observers_) cb(this);
    }

    OnlineStatus getStatus() const {
        return status_.load(std::memory_order_acquire);
    }

    void subscribeStatus(std::function<void(User*)> cb) {
        std::lock_guard lk(obsMtx_);
        observers_.push_back(std::move(cb));
    }

    const std::string& getId()   const { return id_; }
    const std::string& getName() const { return name_; }
};
std::atomic<int> User::counter_{0};

// ── Message ───────────────────────────────────────────────────────────────────
class Message {
    static std::atomic<int> counter_;
    std::string id_;
    std::shared_ptr<User> author_;
    std::string chatId_;
    MessageContent content_;
    TP sentAt_;

    // Delivery tracking — shared_mutex for concurrent reads
    std::unordered_map<std::string, DeliveryReceipt> receipts_;
    mutable std::shared_mutex receiptMtx_;

    // Reactions
    std::unordered_map<std::string, Reaction> reactions_;
    mutable std::shared_mutex reactionMtx_;

    // Deletion
    std::unordered_set<std::string> deletedFor_;
    std::atomic<bool> deletedForAll_{false};
    mutable std::mutex deletionMtx_;

    std::atomic<int> aggregateLevel_{(int)MessageStatus::SENT};

public:
    Message(std::shared_ptr<User> author, std::string chatId, MessageContent content)
        : id_("msg" + std::to_string(++counter_))
        , author_(author), chatId_(std::move(chatId))
        , content_(std::move(content)), sentAt_(Clock::now()) {}

    void markDelivered(const std::string& uid) {
        {
            std::unique_lock lk(receiptMtx_);
            receipts_.emplace(uid, DeliveryReceipt{uid}).first->second.markDelivered();
        }
        recomputeStatus();
    }

    void markRead(const std::string& uid) {
        {
            std::unique_lock lk(receiptMtx_);
            receipts_.emplace(uid, DeliveryReceipt{uid}).first->second.markRead();
        }
        recomputeStatus();
    }

    void recomputeStatus() {
        std::shared_lock lk(receiptMtx_);
        if (receipts_.empty()) return;
        bool allRead      = true;
        bool allDelivered = true;
        for (auto& [uid, r] : receipts_) {
            auto s = r.status();
            if (s != MessageStatus::READ)      allRead      = false;
            if ((int)s < (int)MessageStatus::DELIVERED) allDelivered = false;
        }
        int level = allRead ? (int)MessageStatus::READ
                  : allDelivered ? (int)MessageStatus::DELIVERED
                  : (int)MessageStatus::SENT;
        aggregateLevel_.store(level, std::memory_order_release);
    }

    MessageStatus getStatus() const {
        return (MessageStatus)aggregateLevel_.load(std::memory_order_acquire);
    }

    void addReaction(const std::string& uid, const std::string& emoji) {
        std::unique_lock lk(reactionMtx_);
        reactions_.emplace(uid, Reaction{uid, emoji});
    }

    std::unordered_map<std::string, int> getReactions() const {
        std::shared_lock lk(reactionMtx_);
        std::unordered_map<std::string, int> counts;
        for (auto& [uid, r] : reactions_) counts[r.emoji]++;
        return counts;
    }

    void deleteForMe(const std::string& uid) {
        std::lock_guard lk(deletionMtx_);
        deletedFor_.insert(uid);
    }

    bool isVisibleTo(const std::string& uid) const {
        if (deletedForAll_.load()) return false;
        std::lock_guard lk(deletionMtx_);
        return deletedFor_.find(uid) == deletedFor_.end();
    }

    const std::string& getId() const { return id_; }
    std::shared_ptr<User> getAuthor() const { return author_; }
    const MessageContent& getContent() const { return content_; }

    std::string str() const {
        return "Message(" + author_->getName() + ": " + content_.renderPreview() + ")";
    }
};
std::atomic<int> Message::counter_{0};

// ── BaseChat (Template Method) ────────────────────────────────────────────────
class BaseChat {
protected:
    static std::atomic<int> chatCounter_;
    std::string id_;
    std::vector<std::shared_ptr<Message>> messages_;
    mutable std::shared_mutex msgMtx_;

public:
    BaseChat() : id_("chat" + std::to_string(++chatCounter_)) {}
    virtual ~BaseChat() = default;

    std::shared_ptr<Message> sendMessage(
        std::shared_ptr<User> sender,
        MessageContent content,
        std::shared_ptr<Message> replyTo = nullptr) {

        validateSender(sender);
        auto msg = std::make_shared<Message>(sender, id_, std::move(content));
        {
            std::unique_lock lk(msgMtx_);
            messages_.push_back(msg);
        }
        fanOut(msg);
        return msg;
    }

    std::vector<std::shared_ptr<Message>> getMessages(int limit) const {
        std::shared_lock lk(msgMtx_);
        int start = std::max(0, (int)messages_.size() - limit);
        return {messages_.begin() + start, messages_.end()};
    }

protected:
    virtual void validateSender(std::shared_ptr<User> sender) = 0;
    virtual void fanOut(std::shared_ptr<Message> msg) = 0;

    const std::string& getId() const { return id_; }
};
std::atomic<int> BaseChat::chatCounter_{0};

// ── 1:1 Chat ──────────────────────────────────────────────────────────────────
class Chat : public BaseChat {
    std::array<std::shared_ptr<User>, 2> participants_;
public:
    Chat(std::shared_ptr<User> a, std::shared_ptr<User> b)
        : participants_{a, b} {}

    void validateSender(std::shared_ptr<User> sender) override {
        bool ok = std::any_of(participants_.begin(), participants_.end(),
            [&](auto& p){ return p->getId() == sender->getId(); });
        if (!ok) throw std::runtime_error(sender->getName() + " is not a participant");
    }

    void fanOut(std::shared_ptr<Message> msg) override {
        for (auto& p : participants_) {
            if (p->getId() != msg->getAuthor()->getId()
                && p->getStatus() == OnlineStatus::ONLINE) {
                msg->markDelivered(p->getId());
            }
        }
    }
};

// ── Group ─────────────────────────────────────────────────────────────────────
class Group : public BaseChat {
    static constexpr int MAX = 256;
    std::string name_;
    std::unordered_map<std::string, GroupRole>           memberRoles_;
    std::unordered_map<std::string, std::shared_ptr<User>> members_;
    mutable std::shared_mutex memberMtx_;

public:
    Group(std::string name, std::shared_ptr<User> creator) : name_(std::move(name)) {
        memberRoles_[creator->getId()] = GroupRole::OWNER;
        members_[creator->getId()]     = creator;
    }

    bool addMember(std::shared_ptr<User> admin, std::shared_ptr<User> newMember) {
        std::unique_lock lk(memberMtx_);
        auto r = memberRoles_.find(admin->getId());
        if (r == memberRoles_.end() || (r->second != GroupRole::ADMIN && r->second != GroupRole::OWNER))
            throw std::runtime_error("Only admins can add members");
        if ((int)memberRoles_.size() >= MAX)
            throw std::runtime_error("Group is full");
        return memberRoles_.emplace(newMember->getId(), GroupRole::MEMBER).second
            && members_.emplace(newMember->getId(), newMember).second;
    }

    void validateSender(std::shared_ptr<User> sender) override {
        std::shared_lock lk(memberMtx_);
        if (!memberRoles_.count(sender->getId()))
            throw std::runtime_error(sender->getName() + " is not a member");
    }

    void fanOut(std::shared_ptr<Message> msg) override {
        std::vector<std::shared_ptr<User>> recipients;
        {
            std::shared_lock lk(memberMtx_);
            for (auto& [uid, u] : members_)
                if (uid != msg->getAuthor()->getId()) recipients.push_back(u);
        }
        for (auto& r : recipients)
            if (r->getStatus() == OnlineStatus::ONLINE)
                msg->markDelivered(r->getId());
    }

    int getMemberCount() const {
        std::shared_lock lk(memberMtx_);
        return (int)memberRoles_.size();
    }
};

// ── Demo ──────────────────────────────────────────────────────────────────────
int main() {
    auto alice = std::make_shared<User>("+91-9000000001", "Alice");
    auto bob   = std::make_shared<User>("+91-9000000002", "Bob");
    auto carol = std::make_shared<User>("+91-9000000003", "Carol");

    alice->setOnline(); bob->setOnline();

    Chat chat(alice, bob);
    auto msg1 = chat.sendMessage(alice, MessageContent::makeText("Hey Bob!"));
    std::cout << msg1->str() << " Status: " << (int)msg1->getStatus() << "\n";

    msg1->markDelivered(bob->getId());
    msg1->markRead(bob->getId());
    std::cout << "After read: " << (int)msg1->getStatus() << "\n";  // 3=READ

    msg1->addReaction(alice->getId(), "❤️");
    auto reactions = msg1->getReactions();
    for (auto& [emoji, cnt] : reactions)
        std::cout << emoji << " x" << cnt << "\n";

    Group group("Team Alpha", alice);
    group.addMember(alice, bob);
    group.addMember(alice, carol);
    auto gmsg = group.sendMessage(alice, MessageContent::makeText("Meeting at 3pm!"));
    std::cout << "Group members: " << group.getMemberCount() << "\n";

    gmsg->deleteForMe(bob->getId());
    std::cout << "Visible to Bob: "   << gmsg->isVisibleTo(bob->getId())   << "\n";  // 0
    std::cout << "Visible to Carol: " << gmsg->isVisibleTo(carol->getId()) << "\n";  // 1
    return 0;
}
```

---

## STEP 6 — Deep Concurrency Analysis

```
MESSAGE STATUS — The hardest part:

Python approach:
  RLock on Message for all state changes.
  Aggregate status computed inside the lock → consistent view.
  Reentrant lock needed because markRead calls markDelivered internally.

Java approach:
  ConcurrentHashMap for receipts → no lock on reads.
  synchronized(statusLock) only for aggregate recomputation.
  volatile on aggregateStatus → visibility without lock on reads.
  AtomicInteger for aggregate level (lock-free status reads).

C++ approach:
  shared_mutex on receiptMtx_ → many readers (getStatus), exclusive writers (markDelivered).
  atomic<int> for aggregateLevel_ → lock-free reads by all threads.
  std::memory_order_release on writes → guarantees visibility to other CPUs.
  std::memory_order_acquire on reads → sees latest written value.

DEADLOCK PREVENTION in Group.addMember + Group.fanOut:
  addMember: unique_lock (write)
  fanOut: calls markDelivered on Message (different lock) AFTER releasing group lock.
  → Never hold two locks at same time → no deadlock possible.

C++ RAII pattern:
  All std::lock_guard, std::unique_lock, std::shared_lock are RAII.
  Lock released automatically on scope exit — even on exception.
  No finally{} needed unlike Java.
```

---

## STEP 7 — Trade-offs

```
TRADE-OFF 1: CopyOnWriteArrayList for messages (Java)
  Group has 256 members all sending simultaneously.
  COW: each write copies the full list → expensive but reads are lock-free.
  Alternative: ConcurrentLinkedQueue (lock-free queue). Better for high-volume writes.
  Decision: COW for < 10K messages/chat. Queue for > 10K.

TRADE-OFF 2: Aggregate status = minimum vs per-recipient status
  Min status: one tick = SENT, one blue tick = DELIVERED, two blue ticks = READ.
  Shows lowest common denominator across all recipients.
  Group with 256 members: READ only after all 256 read it → undesirable.
  WhatsApp actual: two blue ticks when at least one person reads.
  Fix: aggregate = MAX(recipient statuses) for group, MIN for 1:1.

TRADE-OFF 3: Reaction as Flyweight
  Each emoji string stored once in EmojiPool.
  Reaction holds reference (C++) or interned String (Java).
  Saves memory when millions of users react with same emoji.
  Trade-off: EmojiPool is a Singleton → shared mutable state → needs lock.

TRADE-OFF 4: Soft delete via deletedFor set
  Memory: each "delete for me" adds a userId to a Set.
  Active messages with millions of "delete for me": set grows large.
  Alternative: store in separate DB table. Delete set from memory.
  Decision: in-memory for LLD; DB table for prod.

TRADE-OFF 5: Template Method (BaseChat) vs Strategy
  Template Method: algorithm fixed, subclasses fill steps.
  Strategy: swap entire algorithm at runtime.
  WhatsApp: Chat vs Group semantics are FIXED at construction.
  Template Method is correct; Strategy would add unnecessary flexibility.
```

---

## STEP 8 — Interview Follow-Ups

```
Q: "How do you implement end-to-end encryption?"
A: Signal Protocol (used by WhatsApp).
  Key components in LLD:
    User.publicKey (X25519 Diffie-Hellman key)
    EncryptedMessage wraps ciphertext + mac + ephemeralKey
    KeyExchangeService: on first message → exchange keys via server
    Server: never stores plaintext. Only routes encrypted bytes.
  LLD class: EncryptionService with encrypt(plaintext, recipientPublicKey) → ciphertext

Q: "How do you handle offline message delivery?"
A: MessageQueue per user (in-memory or DB-backed).
   When user comes online: flush all queued messages → deliver.
   Use push notifications (FCM/APNs) to wake up offline device.
   In LLD: User.offline_queue: List[Message]. Server.on_connect(user) drains queue.

Q: "How would you implement message search?"
A: Inverted index on message text (simplified: Map<word, List<MessageId>>).
   In prod: Elasticsearch with per-user shard (privacy: no cross-user search).
   SearchService.search(userId, query) → messages where userId is participant.

Q: "How does Group.sendMessage scale to 256 members?"
A: fanOut() is O(N) — fine for N=256 in-process.
   In prod: Kafka topic per group. Message written once.
   256 consumers (one per member's device server) read from topic.
   Decouples sender throughput from delivery fan-out.

Q: "Concurrent likes from 1M users on a broadcast message?"
A: Message.reactions uses ConcurrentHashMap (Java) / shared_mutex (C++).
   Lock-free reads (getReactions) — most users only view reactions.
   Writes contend on individual user's bucket in ConcurrentHashMap → low contention.
   For exact counts: Redis HINCRBY emoji_counts:<msg_id> "❤️" 1 (atomic).
```

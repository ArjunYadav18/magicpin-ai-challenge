from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class StoredContext:
    scope: str
    context_id: str
    version: int
    payload: dict[str, Any]
    delivered_at: str


@dataclass
class ConversationState:
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    trigger_id: Optional[str] = None
    send_as: str = "vera"
    pending_action: Optional[str] = None
    last_bot_body: Optional[str] = None
    last_bodies: list[str] = field(default_factory=list)
    turns: list[dict[str, Any]] = field(default_factory=list)
    auto_reply_streak: int = 0
    ended: bool = False
    opted_out: bool = False


class ContextStore:
    """In-memory store for the four context layers plus conversation/suppression state."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._contexts: dict[tuple[str, str], StoredContext] = {}
        self._conversations: dict[str, ConversationState] = {}
        self._suppression: set[str] = set()
        self._merchant_opt_out: set[str] = set()
        self._customer_opt_out: set[str] = set()
        self._merchant_auto_replies: dict[str, dict[str, Any]] = {}
        self._merchant_open_convs: dict[str, str] = {}

    def reset(self) -> None:
        with self._lock:
            self._contexts.clear()
            self._conversations.clear()
            self._suppression.clear()
            self._merchant_opt_out.clear()
            self._customer_opt_out.clear()
            self._merchant_auto_replies.clear()
            self._merchant_open_convs.clear()

    def put(
        self,
        scope: str,
        context_id: str,
        version: int,
        payload: dict[str, Any],
        delivered_at: str,
    ) -> tuple[bool, str, Optional[int], Optional[str]]:
        valid_scopes = {"category", "merchant", "customer", "trigger"}
        if scope not in valid_scopes:
            return False, "invalid_scope", None, f"scope must be one of {sorted(valid_scopes)}"
        if not context_id:
            return False, "malformed", None, "context_id is required"
        if version < 0:
            return False, "malformed", None, "version must be >= 0"

        key = (scope, context_id)
        with self._lock:
            current = self._contexts.get(key)
            if current is not None and version <= current.version:
                return False, "stale_version", current.version, None
            self._contexts[key] = StoredContext(
                scope=scope,
                context_id=context_id,
                version=version,
                payload=payload if isinstance(payload, dict) else {},
                delivered_at=delivered_at or utc_now_iso(),
            )
            return True, f"ack_{context_id}_v{version}", None, None

    def get(self, scope: str, context_id: Optional[str]) -> Optional[dict[str, Any]]:
        if not context_id:
            return None
        with self._lock:
            stored = self._contexts.get((scope, context_id))
            return None if stored is None else stored.payload

    def version_of(self, scope: str, context_id: str) -> Optional[int]:
        with self._lock:
            stored = self._contexts.get((scope, context_id))
            return None if stored is None else stored.version

    def counts(self) -> dict[str, int]:
        counts = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
        with self._lock:
            for scope, _ in self._contexts:
                if scope in counts:
                    counts[scope] += 1
        return counts

    def get_trigger(self, trigger_id: str) -> Optional[dict[str, Any]]:
        payload = self.get("trigger", trigger_id)
        if payload:
            return payload
        return None

    def find_customer(self, customer_id: Optional[str]) -> Optional[dict[str, Any]]:
        return self.get("customer", customer_id)

    def find_merchant(self, merchant_id: Optional[str]) -> Optional[dict[str, Any]]:
        return self.get("merchant", merchant_id)

    def find_category(self, slug: Optional[str]) -> Optional[dict[str, Any]]:
        return self.get("category", slug)

    def is_suppressed(self, key: Optional[str]) -> bool:
        if not key:
            return False
        with self._lock:
            return key in self._suppression

    def mark_suppressed(self, key: Optional[str]) -> None:
        if not key:
            return
        with self._lock:
            self._suppression.add(key)

    def merchant_opted_out(self, merchant_id: Optional[str]) -> bool:
        if not merchant_id:
            return False
        with self._lock:
            return merchant_id in self._merchant_opt_out

    def opt_out_merchant(self, merchant_id: Optional[str]) -> None:
        if not merchant_id:
            return
        with self._lock:
            self._merchant_opt_out.add(merchant_id)

    def customer_opted_out(self, customer_id: Optional[str]) -> bool:
        if not customer_id:
            return False
        with self._lock:
            return customer_id in self._customer_opt_out

    def opt_out_customer(self, customer_id: Optional[str]) -> None:
        if not customer_id:
            return
        with self._lock:
            self._customer_opt_out.add(customer_id)

    def get_conversation(self, conversation_id: str) -> Optional[ConversationState]:
        with self._lock:
            return self._conversations.get(conversation_id)

    def upsert_conversation(self, state: ConversationState) -> ConversationState:
        with self._lock:
            self._conversations[state.conversation_id] = state
            if state.merchant_id and not state.ended:
                self._merchant_open_convs[state.merchant_id] = state.conversation_id
            return state

    def note_auto_reply(self, merchant_id: Optional[str], message: str) -> int:
        if not merchant_id:
            return 1
        normalized = " ".join(message.lower().split())
        with self._lock:
            rec = self._merchant_auto_replies.get(merchant_id)
            if rec and rec.get("text") == normalized:
                rec["count"] = int(rec["count"]) + 1
            else:
                rec = {"text": normalized, "count": 1}
            self._merchant_auto_replies[merchant_id] = rec
            return int(rec["count"])

    def clear_auto_reply(self, merchant_id: Optional[str]) -> None:
        if not merchant_id:
            return
        with self._lock:
            self._merchant_auto_replies.pop(merchant_id, None)


store = ContextStore()

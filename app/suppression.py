from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.facts import parse_dt
from app.store import ContextStore


class SuppressionGuard:
    def __init__(self, store: ContextStore) -> None:
        self.store = store

    def blocked(self, trigger: dict[str, Any], now: Optional[datetime]) -> Optional[str]:
        key = trigger.get("suppression_key")
        if key and self.store.is_suppressed(str(key)):
            return "suppression_key_already_sent"
        expires = parse_dt(trigger.get("expires_at"))
        if now and expires:
            now_naive = now.replace(tzinfo=None) if now.tzinfo else now
            exp_naive = expires.replace(tzinfo=None) if expires.tzinfo else expires
            if now_naive > exp_naive:
                return "trigger_expired"
        merchant_id = trigger.get("merchant_id")
        if self.store.merchant_opted_out(merchant_id):
            return "merchant_opted_out"
        customer_id = trigger.get("customer_id")
        if customer_id and self.store.customer_opted_out(customer_id):
            return "customer_opted_out"
        return None

    def remember_send(self, trigger: dict[str, Any]) -> None:
        key = trigger.get("suppression_key")
        if key:
            self.store.mark_suppressed(str(key))

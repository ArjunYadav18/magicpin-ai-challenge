from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from app.facts import active_offers, parse_dt
from app.store import ContextStore

# Families are matched on trigger.kind substrings, never on trigger ids.
FAMILY_TOKENS: list[tuple[str, tuple[str, ...]]] = [
    ("customer", ("recall_due", "customer_lapsed", "appointment", "wedding_package", "trial_followup", "chronic_refill", "bridal")),
    ("compliance", ("regulation", "supply_alert", "compliance")),
    ("research", ("research_digest", "cde", "digest")),
    ("performance", ("perf_dip", "perf_spike", "seasonal_perf")),
    ("seasonal", ("festival", "ipl_match", "category_seasonal", "weather", "heatwave")),
    ("planning", ("active_planning", "curious_ask")),
    ("renewal", ("renewal_due",)),
    ("growth", ("competitor", "milestone", "gbp_unverified", "winback", "dormant")),
]


def classify_family(kind: str) -> str:
    k = (kind or "").lower()
    for family, tokens in FAMILY_TOKENS:
        if any(tok in k for tok in tokens):
            return family
    return "general"


def required_consent_scopes(kind: str) -> list[str]:
    k = (kind or "").lower()
    if "recall" in k:
        return ["recall_reminders", "appointment_reminders"]
    if "appointment" in k:
        return ["appointment_reminders"]
    if "wedding" in k or "bridal" in k:
        return ["bridal_package_followup", "appointment_reminders"]
    if "lapsed" in k or "winback" in k:
        return ["winback_offers", "promotional_offers", "renewal_reminders"]
    if "trial" in k:
        return ["kids_program_updates", "program_updates", "appointment_reminders"]
    if "refill" in k or "chronic" in k:
        return ["refill_reminders", "delivery_notifications", "recall_alerts"]
    return ["promotional_offers", "appointment_reminders", "program_updates"]


def customer_may_be_contacted(
    trigger: dict[str, Any],
    customer: Optional[dict[str, Any]],
) -> tuple[bool, str]:
    if str(trigger.get("scope") or "merchant") != "customer":
        return True, "merchant_scope"
    if not customer:
        return False, "missing_customer"
    consent = customer.get("consent") or {}
    prefs = customer.get("preferences") or {}
    identity = customer.get("identity") or {}
    if not consent.get("opted_in_at"):
        return False, "no_opt_in"
    if prefs.get("reminder_opt_in") is False:
        return False, "reminder_opt_out"
    channel = str(prefs.get("channel") or "").lower()
    if channel in {"none", "none_recorded"}:
        return False, "no_channel"
    if identity.get("phone_redacted") in (None, "") and "no profile" in str(identity.get("name") or "").lower():
        return False, "anonymous_customer"
    scopes = {str(s) for s in (consent.get("scope") or [])}
    if not scopes:
        return False, "empty_consent_scope"
    needed = required_consent_scopes(str(trigger.get("kind") or ""))
    if scopes.isdisjoint(set(needed)):
        return False, "consent_scope_mismatch"
    return True, "ok"


@dataclass
class Candidate:
    trigger_id: str
    trigger: dict[str, Any]
    merchant: dict[str, Any]
    category: Optional[dict[str, Any]]
    customer: Optional[dict[str, Any]]
    family: str
    score: float
    reasons: list[str] = field(default_factory=list)
    skip_reason: Optional[str] = None


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _urgency(trigger: dict[str, Any]) -> float:
    try:
        return _clamp(int(trigger.get("urgency") or 1) / 5.0)
    except (TypeError, ValueError):
        return 0.2


def _recency(trigger: dict[str, Any], now: Optional[datetime]) -> float:
    payload = trigger.get("payload") or {}
    days_until = payload.get("days_until")
    if isinstance(days_until, (int, float)):
        if days_until > 45:
            return 0.15
        if days_until > 21:
            return 0.4
        return 0.9
    expires = parse_dt(trigger.get("expires_at"))
    if now and expires:
        now_n = now.replace(tzinfo=None) if now.tzinfo else now
        exp_n = expires.replace(tzinfo=None) if expires.tzinfo else expires
        hours = (exp_n - now_n).total_seconds() / 3600.0
        if hours <= 0:
            return 0.0
        if hours < 24:
            return 1.0
        if hours < 24 * 7:
            return 0.8
        if hours < 24 * 30:
            return 0.6
        return 0.35
    return 0.55


def _actionability(trigger: dict[str, Any], merchant: dict[str, Any], category: Optional[dict[str, Any]]) -> float:
    payload = trigger.get("payload") or {}
    score = 0.35
    if payload and not payload.get("placeholder"):
        score += 0.35
    if payload.get("placeholder"):
        score -= 0.15
    if active_offers(merchant):
        score += 0.1
    if category and (category.get("digest") or category.get("offer_catalog")):
        score += 0.1
    if payload.get("available_slots") or payload.get("next_session_options"):
        score += 0.15
    return _clamp(score)


def _merchant_relevance(trigger: dict[str, Any], merchant: dict[str, Any]) -> float:
    payload = trigger.get("payload") or {}
    signals = " ".join(str(s) for s in (merchant.get("signals") or [])).lower()
    kind = str(trigger.get("kind") or "").lower()
    score = 0.45
    if kind in signals or kind.replace("_", " ") in signals:
        score += 0.2
    if "perf" in kind and ("perf" in signals or "dip" in signals or "spike" in signals or "seasonal" in signals):
        score += 0.2
    if "unverified" in kind and "unverified" in signals:
        score += 0.25
    if "renewal" in kind and "renewal" in signals:
        score += 0.25
    if "winback" in kind and "winback" in signals:
        score += 0.25
    if "dormant" in kind and "dormant" in signals:
        score += 0.2
    if payload.get("metric") and merchant.get("performance"):
        score += 0.1
    return _clamp(score)


def _category_relevance(trigger: dict[str, Any], merchant: dict[str, Any], category: Optional[dict[str, Any]]) -> float:
    payload = trigger.get("payload") or {}
    slug = (merchant.get("category_slug") or (category or {}).get("slug") or "").lower()
    allowed = payload.get("category_relevance")
    if isinstance(allowed, list) and allowed:
        if slug not in {str(x).lower() for x in allowed}:
            return 0.0
        return 1.0
    payload_cat = str(payload.get("category") or "").lower()
    if payload_cat and slug and payload_cat != slug:
        return 0.2
    return 0.85 if category else 0.4


def _conversation_fit(merchant: dict[str, Any], family: str) -> float:
    history = merchant.get("conversation_history") or []
    if not history:
        return 0.55
    last = history[-1] if history else {}
    engagement = str(last.get("engagement") or "").lower()
    if engagement in {"intent_action", "intent_planning", "intent_question", "merchant_replied"}:
        if family in {"planning", "compliance", "customer"}:
            return 0.95
        return 0.7
    if engagement in {"merchant_no_reply"} and family == "renewal":
        return 0.4
    return 0.6


class DecisionEngine:
    def __init__(self, store: ContextStore) -> None:
        self.store = store

    def evaluate(
        self,
        trigger_id: str,
        trigger: dict[str, Any],
        merchant: dict[str, Any],
        category: Optional[dict[str, Any]],
        customer: Optional[dict[str, Any]],
        now: Optional[datetime],
    ) -> Candidate:
        family = classify_family(str(trigger.get("kind") or ""))
        reasons: list[str] = []
        allowed, why = customer_may_be_contacted(trigger, customer)
        if not allowed:
            return Candidate(trigger_id, trigger, merchant, category, customer, family, 0.0, [why], why)

        trigger_rel = _category_relevance(trigger, merchant, category)
        if trigger_rel <= 0.0:
            return Candidate(trigger_id, trigger, merchant, category, customer, family, 0.0, ["category_mismatch"], "category_mismatch")

        merchant_rel = _merchant_relevance(trigger, merchant)
        urgency = _urgency(trigger)
        recency = _recency(trigger, now)
        action = _actionability(trigger, merchant, category)
        conv = _conversation_fit(merchant, family)
        customer_rel = 1.0 if str(trigger.get("scope")) == "customer" and customer else 0.7

        # Festival far in the future is a weak "why now".
        payload = trigger.get("payload") or {}
        if family == "seasonal" and isinstance(payload.get("days_until"), (int, float)) and payload["days_until"] > 60:
            return Candidate(trigger_id, trigger, merchant, category, customer, family, 0.2, ["too_far_out"], "too_far_out")

        score = (
            0.22 * trigger_rel
            + 0.18 * merchant_rel
            + 0.18 * urgency
            + 0.10 * recency
            + 0.18 * action
            + 0.07 * customer_rel
            + 0.07 * conv
        )

        if family in {"compliance", "planning", "customer"}:
            score += 0.08

        if family in {"research", "growth", "performance"}:
            score += 0.04

        score = _clamp(score)
        reasons.append(f"family={family}")
        reasons.append(f"urgency={urgency:.2f}")
        reasons.append(f"actionability={action:.2f}")

        skip = None
        return Candidate(trigger_id, trigger, merchant, category, customer, family, score, reasons, skip)

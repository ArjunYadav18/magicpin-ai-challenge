from __future__ import annotations

from typing import Any, Optional

from app.facts import digest_by_id, first_digest
from app.store import ContextStore


def resolve_bundle(
    store: ContextStore,
    trigger: dict[str, Any],
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    merchant_id = trigger.get("merchant_id")
    customer_id = trigger.get("customer_id")
    merchant = store.find_merchant(merchant_id)
    customer = store.find_customer(customer_id) if customer_id else None
    slug = None
    if merchant:
        slug = merchant.get("category_slug")
    payload = trigger.get("payload") or {}
    slug = slug or payload.get("category")
    category = store.find_category(slug)
    return category, merchant, customer


def relevant_digest(
    category: Optional[dict[str, Any]],
    trigger: dict[str, Any]
) -> Optional[dict[str, Any]]:
    if not category:
        return None

    payload = trigger.get("payload") or {}

    item_id = (
        payload.get("top_item_id")
        or payload.get("digest_item_id")
        or payload.get("alert_id")
    )

    if item_id:
        found = digest_by_id(category, item_id)
        if found:
            return found

    kind = str(trigger.get("kind") or "").lower()

    kind_map = {
        "research_digest": "research",
        "research_digest_release": "research",
        "category_research_digest_release": "research",
        "regulation_change": "compliance",
        "cde_opportunity": "cde",
        "supply_alert": "alert",
        "category_seasonal": "seasonal",
        "festival_upcoming": "seasonal",
        "ipl_match_today": "seasonal",
    }

    mapped = kind_map.get(kind)

    if mapped:
        return first_digest(category, mapped)

    # IMPORTANT:
    # Do not attach an arbitrary digest item to an unrelated trigger.
    return None

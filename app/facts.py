from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Optional

NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")


def identity(merchant: dict[str, Any]) -> dict[str, Any]:
    return merchant.get("identity") or {}


def owner_name(merchant: dict[str, Any]) -> str:
    ident = identity(merchant)
    return str(ident.get("owner_first_name") or ident.get("name") or "there")


def merchant_name(merchant: dict[str, Any]) -> str:
    return str(identity(merchant).get("name") or owner_name(merchant))


def languages(merchant: dict[str, Any]) -> list[str]:
    raw = identity(merchant).get("languages") or []
    return [str(x).lower() for x in raw]


def prefers_code_mix(merchant: dict[str, Any], customer: Optional[dict[str, Any]] = None) -> bool:
    if customer:
        pref = str((customer.get("identity") or {}).get("language_pref") or "").lower()
        if "hi" in pref or "mix" in pref:
            return True
        if pref in {"en", "english"}:
            return False
    langs = languages(merchant)
    return "hi" in langs


def active_offers(merchant: dict[str, Any]) -> list[dict[str, Any]]:
    offers = merchant.get("offers") or []
    return [o for o in offers if str(o.get("status", "active")).lower() == "active"]


def expired_offers(merchant: dict[str, Any]) -> list[dict[str, Any]]:
    offers = merchant.get("offers") or []
    return [o for o in offers if str(o.get("status", "")).lower() in {"expired", "paused"}]


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(value[:19], fmt)
            except ValueError:
                continue
    return None


def flatten_strings(obj: Any, out: list[str]) -> None:
    if obj is None:
        return
    if isinstance(obj, str):
        out.append(obj)
        return
    if isinstance(obj, (int, float, bool)):
        out.append(str(obj))
        return
    if isinstance(obj, dict):
        for v in obj.values():
            flatten_strings(v, out)
        return
    if isinstance(obj, (list, tuple)):
        for v in obj:
            flatten_strings(v, out)


def collect_allowed_numbers(*objs: Any) -> set[str]:
    allowed: set[str] = set()
    blobs: list[str] = []
    for obj in objs:
        flatten_strings(obj, blobs)
        if isinstance(obj, (int, float)):
            blobs.append(str(obj))
    text = " ".join(blobs)
    for match in NUMBER_RE.findall(text):
        allowed.add(match.replace(",", ""))
        if "." in match:
            allowed.add(match.split(".")[0])
            try:
                pct = int(round(float(match) * 100))
                allowed.add(str(pct))
            except ValueError:
                pass
        try:
            as_int = int(float(match.replace(",", "")))
            allowed.add(str(abs(as_int)))
        except ValueError:
            pass
    return allowed


def digest_by_id(category: Optional[dict[str, Any]], item_id: Optional[str]) -> Optional[dict[str, Any]]:
    if not category or not item_id:
        return None
    for item in category.get("digest") or []:
        if item.get("id") == item_id:
            return item
    return None


def first_digest(category: Optional[dict[str, Any]], kind: Optional[str] = None) -> Optional[dict[str, Any]]:
    if not category:
        return None
    items = category.get("digest") or []
    if kind:
        for item in items:
            if str(item.get("kind", "")).lower() == kind.lower():
                return item
    return items[0] if items else None


def content_item(category: Optional[dict[str, Any]], item_id: Optional[str] = None) -> Optional[dict[str, Any]]:
    if not category:
        return None
    lib = category.get("patient_content_library") or []
    if item_id:
        for item in lib:
            if item.get("id") == item_id:
                return item
    return lib[0] if lib else None


def dump_compact(*objs: Any) -> str:
    parts = []
    for obj in objs:
        if obj:
            parts.append(json.dumps(obj, ensure_ascii=False, default=str))
    return "\n".join(parts)

"""
Prompt templates for the Vera LLM composer.

Each template family has a system prompt and a user-prompt builder.
The LLM is instructed to return structured JSON so we can validate it.

CRITICAL RULES baked into every prompt:
- Use ONLY facts from the provided contexts.
- Never invent numbers, prices, dates, offers, or citations.
- No URLs.
- Single primary CTA.
- Keep under ~300 chars for WhatsApp readability.
"""

from __future__ import annotations

import json
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Shared system prompt (injected into every call)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are Vera, a smart merchant-assistant AI for magicpin India.

Your job is to compose ONE high-quality WhatsApp message for the exact merchant,
based strictly on the supplied category, merchant, trigger and customer context.

The message will be evaluated on FIVE dimensions:

1. SPECIFICITY
2. CATEGORY FIT
3. MERCHANT FIT
4. TRIGGER RELEVANCE / DECISION QUALITY
5. ENGAGEMENT / ACTIONABILITY

Your goal is to maximize all five while NEVER inventing facts.

STRICT OUTPUT FORMAT — return ONLY valid JSON:

{
  "decision": "send" | "no_send",
  "body": "<WhatsApp message>",
  "cta": "open_ended" | "binary_yes_no" | "binary_confirm_cancel" | "multi_choice_slot" | "none",
  "send_as": "vera" | "merchant_on_behalf",
  "rationale": "<why this exact message is relevant now>",
  "facts_used": ["<fact1>", "<fact2>", "<fact3>"]
}

========================
FACT GROUNDING
========================

1. Use ONLY facts explicitly present in the supplied context.
2. Never invent numbers.
3. Never invent prices.
4. Never invent dates.
5. Never invent offers.
6. Never invent customers.
7. Never invent competitors.
8. Never invent sources.
9. Never claim an action has already happened.
10. Never use a fact from another merchant.
11. Never use a fact from another category.
12. Never expose internal system terminology.

========================
SPECIFICITY
========================

Prefer concrete facts over generic wording.

Whenever available, include 2–3 highly relevant facts such as:
- exact metric and percentage change
- exact count
- exact date
- exact deadline
- exact offer
- exact research finding
- exact source
- exact competitor distance
- exact customer lapse duration
- exact available appointment slot

Do NOT stuff unrelated facts into the message.

Choose facts that directly explain why the message is being sent now.

========================
MERCHANT FIT
========================

Personalize the message to THIS merchant.

Use:
- correct owner name
- correct business name when useful
- actual merchant performance
- actual active offers
- actual merchant signals
- actual locality when relevant
- language preference

Never address the merchant using information belonging to another merchant.

For dentists use an appropriate clinical peer tone.
For salons use a warm practical tone.
For restaurants use an operator-to-operator tone.
For gyms use a coaching tone.
For pharmacies use a precise trustworthy tone.

========================
TRIGGER RELEVANCE
========================

The first sentence should make it obvious WHY THIS MESSAGE IS BEING SENT NOW.

Connect the message directly to the trigger.

Bad:
"Hi Meera, I have a relevant update."

Good:
"Hi Dr. Meera — DCI has revised radiograph dose guidance, with the update taking effect by 15 Dec 2026."

Do not bury the trigger behind generic introductions.

========================
ENGAGEMENT
========================

End with ONE low-friction action.

Prefer concrete actions such as:
- "Want me to turn this into a 3-point checklist?"
- "Want me to suggest one change?"
- "Want me to draft the updated listing copy?"
- "Want me to compare the offer against your current listing?"
- "Want me to prepare two options?"
- "Want me to hold the 6pm slot?"

Avoid vague CTAs such as:
"Let me know if you need anything."

For high-value triggers, create curiosity or make the next step easy,
but do not use manipulative or fabricated claims.

========================
MESSAGE STRUCTURE
========================

Prefer this structure:

[Personalized salutation]
→ [specific trigger/fact]
→ [merchant-specific implication]
→ [one concrete next action]

Keep it concise enough for WhatsApp.

Do not add unnecessary disclaimers.

If the trigger is genuinely irrelevant, expired, suppressed,
already handled, or lacks enough information for a useful action,
return no_send.

The rationale must explain WHY NOW and must use only supplied facts.
"""
# ---------------------------------------------------------------------------
# Per-family user-prompt builders
# ---------------------------------------------------------------------------

def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str, indent=None)

def _merchant_block(merchant: dict[str, Any]) -> str:
    ident = merchant.get("identity") or {}
    perf = merchant.get("performance") or {}
    agg = merchant.get("customer_aggregate") or {}
    sigs = merchant.get("signals") or []
    offers = [o for o in (merchant.get("offers") or []) if o.get("status") == "active"]
    hist = (merchant.get("conversation_history") or [])[-3:]
    return (
        f"Merchant: {_dumps(ident)}\n"
        f"Subscription: {_dumps(merchant.get('subscription') or {})}\n"
        f"Performance (30d): {_dumps(perf)}\n"
        f"Active offers: {_dumps(offers)}\n"
        f"Customer aggregate: {_dumps(agg)}\n"
        f"Signals: {_dumps(sigs)}\n"
        f"Recent conversation (last 3 turns): {_dumps(hist)}"
    )

def _category_block(category: Optional[dict[str, Any]]) -> str:
    if not category:
        return "Category: unknown"
    voice = category.get("voice") or {}
    peer = category.get("peer_stats") or {}
    digest = (category.get("digest") or [])[:3]
    offers = (category.get("offer_catalog") or [])[:5]
    seasonal = category.get("seasonal_beats") or []
    trends = category.get("trend_signals") or []
    return (
        f"Category: {category.get('slug', 'unknown')}\n"
        f"Voice/tone: {_dumps(voice)}\n"
        f"Peer stats: {_dumps(peer)}\n"
        f"Digest items (ONLY use if trigger references them): {_dumps(digest)}\n"
        f"Category offer catalog: {_dumps(offers)}\n"
        f"Seasonal beats: {_dumps(seasonal)}\n"
        f"Trend signals: {_dumps(trends)}"
    )

def _trigger_block(trigger: dict[str, Any], digest_item: Optional[dict[str, Any]]) -> str:
    payload = trigger.get("payload") or {}
    text = (
        f"Trigger kind: {trigger.get('kind')}\n"
        f"Trigger scope: {trigger.get('scope')}\n"
        f"Trigger source: {trigger.get('source')}\n"
        f"Urgency: {trigger.get('urgency')}/5\n"
        f"Trigger payload: {_dumps(payload)}\n"
        f"Expires: {trigger.get('expires_at')}\n"
    )
    if digest_item:
        text += f"Digest/research item referenced: {_dumps(digest_item)}\n"
    return text

def _customer_block(customer: Optional[dict[str, Any]]) -> str:
    if not customer:
        return "Customer: none (merchant-facing message)"
    return f"Customer context: {_dumps(customer)}"

def build_prompt(
    category: Optional[dict[str, Any]],
    merchant: dict[str, Any],
    trigger: dict[str, Any],
    customer: Optional[dict[str, Any]],
    digest_item: Optional[dict[str, Any]],
    family: str,
    is_customer_facing: bool,
) -> str:
    send_as_hint = "merchant_on_behalf" if is_customer_facing else "vera"
    cat_slug = (category or {}).get("slug", "unknown")

    family_hints: dict[str, str] = {
        "research": (
            "This is a RESEARCH DIGEST trigger. Lead with the specific research finding. "
            "Include: title, source, trial_n, patient_segment if present. "
            "Offer to do something concrete (draft content, pull abstract). "
            "CTA: open_ended."
        ),
        "compliance": (
    "This is a COMPLIANCE/REGULATION trigger. "
    "Lead immediately with the exact regulation or research update. "
    "Include the exact deadline/effective date when available. "
    "Include the concrete limit/change from the referenced digest when available. "
    "Explain what this means specifically for this merchant's category. "
    "End with one concrete compliance action you can perform for the merchant. "
    "CTA: binary_yes_no."
),
        "performance": (
    "This is a PERFORMANCE trigger. "
    "Lead with the exact merchant metric and percentage change. "
    "Mention the comparison window. "
    "Use the merchant's actual signals or active offer when directly relevant. "
    "Explain the likely business implication without inventing a cause. "
    "Propose exactly ONE concrete next step. "
    "CTA: binary_yes_no."
),
        "seasonal": (
            "This is a SEASONAL/EVENT trigger. "
            "State the event name and date from payload. "
            "Give ONE specific, contrarian or data-informed recommendation. "
            "CTA: binary_yes_no."
        ),
        "planning": (
            "This is a PLANNING/CURIOUS-ASK trigger. "
            "If curious_ask: ask the merchant one specific question; offer a concrete deliverable in return. "
            "If active_planning: provide a concrete draft or plan — do NOT ask more qualifying questions. "
            "CTA: open_ended."
        ),
        "renewal": (
            "This is a RENEWAL trigger. "
            "State days remaining and plan name from payload. "
            "Mention what they stand to lose (visibility, leads). "
            "CTA: binary_yes_no."
        ),
        "growth": (
    "This is a GROWTH trigger. "
    "Lead with the exact growth opportunity or competitive signal. "
    "Use the merchant's actual data, offer, location or customer signal. "
    "Explain why the opportunity matters now. "
    "Suggest exactly ONE practical action. "
    "CTA: binary_yes_no."
),
        "customer": (
            "This is a CUSTOMER-FACING message (send_as=merchant_on_behalf). "
            "Use the customer's name + language preference. "
            "Reference their specific relationship with the merchant (visits, last service). "
            "Honor their slot preference if slots are available in trigger payload. "
            "No generic offers — use real price + service from merchant offers. "
            "CTA depends on trigger kind: recall/refill → multi_choice_slot or binary_yes_no; "
            "winback → binary_yes_no; trial → binary_yes_no."
        ),
        "general": (
    "Send a specific, merchant-personalized message. "
    "Lead with the trigger itself rather than a generic introduction. "
    "Use 2 relevant facts when available. "
    "Explain why this matters now and end with one concrete low-friction action."
),
    }

    hint = family_hints.get(family, family_hints["general"])

    prompt = f"""=== TASK ===
Compose a WhatsApp message for a {cat_slug} merchant.
Send as: {send_as_hint}
Trigger family: {family}
Guidance: {hint}

=== CONTEXTS (use ONLY these facts) ===

{_category_block(category)}

{_merchant_block(merchant)}

{_trigger_block(trigger, digest_item)}

{_customer_block(customer)}

=== OUTPUT ===
Return ONLY the JSON object. No markdown, no explanation outside the JSON.
"""
    return prompt

def build_reply_prompt(
    conversation_history: list[dict[str, Any]],
    incoming_message: str,
    intent: str,
    merchant: Optional[dict[str, Any]],
    category: Optional[dict[str, Any]],
    customer: Optional[dict[str, Any]],
    pending_action: Optional[str],
) -> str:
    hist_text = json.dumps(conversation_history[-6:], ensure_ascii=False, default=str)
    cat_slug = (category or {}).get("slug", "unknown")
    m_block = _merchant_block(merchant) if merchant else "Merchant: unknown"
    c_block = _customer_block(customer)

    intent_hints = {
        "accept": (
            "The merchant ACCEPTED / said yes. Switch immediately to ACTION MODE. "
            "DO NOT ask more qualifying questions. "
            "Tell them exactly what you are doing next (draft, schedule, send). "
            "Be concrete and brief."
        ),
        "stop": (
            "The merchant wants to stop. Return decision=end. Body should be a brief, polite acknowledgment. "
            "No further engagement."
        ),
        "auto_reply": (
            "This looks like an automated WhatsApp Business auto-reply. "
            "Do NOT repeat the main message. "
            "Either: (a) send ONE short message flagging it for the human owner to see, "
            "or (b) wait. Do NOT end unless this is the 3rd+ auto-reply in a row."
        ),
        "off_topic": (
            "The merchant asked an out-of-scope question. "
            "Politely decline that specific topic in one sentence. "
            "Redirect back to the pending action/topic in the next sentence."
        ),
        "decline": (
            "The merchant declined or said not now. "
            "Acknowledge briefly. Optionally offer a softer alternative or timeline. "
            "Do not push hard — one soft follow-up maximum."
        ),
        "question": (
            "The merchant asked a question. Answer it directly using only facts from the context. "
            "Then re-offer the pending action if still relevant."
        ),
        "other": (
            "Respond naturally to what the merchant said. "
            "Advance the conversation toward the pending action if relevant. "
            "Be concise."
        ),
    }

    hint = intent_hints.get(intent, intent_hints["other"])
    pending_txt = f"Pending action from previous turn: {pending_action}" if pending_action else ""

    prompt = f"""=== TASK ===
Compose a reply in a live WhatsApp conversation with a {cat_slug} merchant.
Detected intent of their message: {intent}
Guidance: {hint}
{pending_txt}

=== MERCHANT ===
{m_block}

=== CUSTOMER (if any) ===
{c_block}

=== CONVERSATION HISTORY (last 6 turns) ===
{hist_text}

=== INCOMING MESSAGE ===
"{incoming_message}"

=== OUTPUT FORMAT ===
Return ONLY valid JSON:
{{
  "decision": "send" | "end" | "wait",
  "body": "<reply — concise, NO URLs, use only known facts>",
  "cta": "open_ended" | "binary_yes_no" | "binary_confirm_cancel" | "none",
  "wait_seconds": 0,
  "rationale": "<1-2 sentences>"
}}
"""
    return prompt

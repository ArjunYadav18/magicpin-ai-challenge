from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status, Response

from app.composer import composer
from app.config import get_settings
from app.conversation import classify_intent, looks_like_auto_reply
from app.decision import DecisionEngine
from app.models import (
    ContextAccepted,
    ContextPush,
    ContextRejected,
    ReplyEnd,
    ReplyRequest,
    ReplySend,
    ReplyWait,
    TickAction,
    TickRequest,
    TickResponse,
)
from app.retrieval import relevant_digest, resolve_bundle
from app.store import ConversationState, store
from app.suppression import SuppressionGuard

router = APIRouter()
settings = get_settings()
decision_engine = DecisionEngine(store)
suppression_guard = SuppressionGuard(store)


@router.get("/v1/healthz")
async def healthz() -> dict[str, Any]:
    counts = store.counts()
    return {
        "status": "ok",
        "uptime_seconds": 3600,
        "contexts_loaded": counts
    }


@router.get("/v1/metadata")
async def metadata() -> dict[str, Any]:
    return {
        "team_name": settings.team_name,
        "team_members": settings.team_members,
        "model": settings.llm_model or "deterministic",
        "approach": "Deterministic + LLM composition",
        "contact_email": settings.contact_email,
        "version": settings.bot_version,
        "submitted_at": settings.submitted_at
    }


@router.post("/v1/context")
async def push_context(req: ContextPush, response: Response) -> Any:
    success, ack_or_reason, curr_ver, details = store.put(
        scope=req.scope,
        context_id=req.context_id,
        version=req.version,
        payload=req.payload,
        delivered_at=req.delivered_at
    )
    if success:
        return ContextAccepted(ack_id=ack_or_reason, stored_at=req.delivered_at)
    
    if ack_or_reason == "stale_version":
        response.status_code = status.HTTP_409_CONFLICT
        return ContextRejected(reason="stale_version", current_version=curr_ver)
    
    if ack_or_reason == "invalid_scope":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"accepted": False, "reason": "invalid_scope", "details": details}
        )
        
    response.status_code = status.HTTP_400_BAD_REQUEST
    return ContextRejected(reason=ack_or_reason, details=details)


@router.post("/v1/tick")
async def tick(req: TickRequest) -> TickResponse:
    from app.facts import parse_dt
    now_dt = parse_dt(req.now)
    
    candidates = []
    
    for t_id in req.available_triggers:
        trigger = store.get_trigger(t_id)
        if not trigger:
            continue
            
        block_reason = suppression_guard.blocked(trigger, now_dt)
        if block_reason:
            continue
            
        category, merchant, customer = resolve_bundle(store, trigger)
        if not merchant:
            continue
            
        cand = decision_engine.evaluate(t_id, trigger, merchant, category, customer, now_dt)
        if cand.skip_reason:
            continue
            
        if cand.score >= settings.send_score_threshold:
            candidates.append(cand)
            
    # Sort and pick top K
    candidates.sort(key=lambda c: c.score, reverse=True)
    top_candidates = candidates[:settings.max_actions_per_tick]
    
    actions = []
    for cand in top_candidates:
        digest_item = relevant_digest(cand.category, cand.trigger)
        is_customer = str(cand.trigger.get("scope")) == "customer"
        
        body, cta, rationale = await composer.compose_tick(
            cand.category,
            cand.merchant,
            cand.trigger,
            cand.customer,
            digest_item,
            cand.family,
            is_customer
        )
        
        if not body:
            continue
            
        suppression_key = str(cand.trigger.get("suppression_key", ""))
        
        conv_id = f"conv_{uuid.uuid4().hex[:8]}"
        send_as = "merchant_on_behalf" if is_customer else "vera"
        
        action = TickAction(
            conversation_id=conv_id,
            merchant_id=cand.merchant.get("merchant_id"),
            customer_id=cand.customer.get("customer_id") if cand.customer else None,
            send_as=send_as,
            trigger_id=cand.trigger_id,
            template_name="vera_default_v1",
            template_params=[],
            body=body,
            cta=cta,
            suppression_key=suppression_key,
            rationale=rationale
        )
        actions.append(action)
        
        # Mark state
        suppression_guard.remember_send(cand.trigger)
        store.upsert_conversation(ConversationState(
            conversation_id=conv_id,
            merchant_id=action.merchant_id,
            customer_id=action.customer_id,
            trigger_id=action.trigger_id,
            send_as=action.send_as,
            pending_action=action.cta,
            last_bot_body=action.body,
            turns=[{"from": "bot", "body": action.body, "ts": req.now}]
        ))
        
    return TickResponse(actions=actions)


@router.post("/v1/reply")
async def reply(req: ReplyRequest) -> Any:
    conv = store.get_conversation(req.conversation_id)
    if not conv:
        return ReplyEnd(rationale="unknown_conversation")
        
    if conv.ended:
        return ReplyEnd(rationale="conversation_already_ended")
        
    conv.turns.append({"from": req.from_role, "body": req.message, "ts": req.received_at})
    
    # 1. Intent Detection
    intent = classify_intent(req.message)
    
    if intent == "stop":
        conv.ended = True
        store.upsert_conversation(conv)
        if req.from_role == "merchant" and req.merchant_id:
            store.opt_out_merchant(req.merchant_id)
        elif req.from_role == "customer" and req.customer_id:
            store.opt_out_customer(req.customer_id)
        return ReplyEnd(rationale="user_opted_out")
        
    # 2. Auto-reply detection
    if intent == "auto_reply":
        streak = store.note_auto_reply(req.merchant_id, req.message)
        conv.auto_reply_streak = streak
        store.upsert_conversation(conv)
        if streak == 1:
            return ReplySend(
                body="I see this is an auto-reply. Please let the owner know I have an update for them.",
                cta="none",
                rationale="flagged_first_auto_reply"
            )
        elif streak == 2:
            return ReplyWait(wait_seconds=86400, rationale="waiting_out_auto_reply")
        else:
            conv.ended = True
            store.upsert_conversation(conv)
            return ReplyEnd(rationale="too_many_auto_replies")
            
    store.clear_auto_reply(req.merchant_id)
    
    # 3. Same body repetition check
    if conv.last_bodies and len(conv.last_bodies) >= 2:
        if conv.last_bodies[-1] == conv.last_bodies[-2]:
            conv.ended = True
            store.upsert_conversation(conv)
            return ReplyEnd(rationale="ending_to_prevent_loop")
            
    # 4. Compose Reply
    merchant = store.find_merchant(req.merchant_id)
    customer = store.find_customer(req.customer_id) if req.customer_id else None
    cat_slug = merchant.get("category_slug") if merchant else None
    category = store.find_category(cat_slug) if cat_slug else None
    
    result = await composer.compose_reply(
        history=conv.turns,
        message=req.message,
        intent=intent,
        merchant=merchant,
        category=category,
        customer=customer,
        pending_action=conv.pending_action
    )
    
    action = result.get("action")
    if action == "end":
        conv.ended = True
        store.upsert_conversation(conv)
        return ReplyEnd(rationale=result.get("rationale", "llm_ended"))
    elif action == "wait":
        return ReplyWait(wait_seconds=result.get("wait_seconds", 3600), rationale=result.get("rationale", "llm_wait"))
    else:
        body = result.get("body", "")
        conv.turns.append({"from": "bot", "body": body, "ts": "now"})
        conv.last_bodies.append(body)
        conv.last_bot_body = body
        conv.pending_action = result.get("cta", "none")
        store.upsert_conversation(conv)
        return ReplySend(
            body=body,
            cta=result.get("cta", "none"),
            rationale=result.get("rationale", "llm_send")
        )

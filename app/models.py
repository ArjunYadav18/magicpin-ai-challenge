from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ContextPush(BaseModel):
    model_config = ConfigDict(extra="allow")

    scope: str
    context_id: str
    version: int
    payload: dict[str, Any]
    delivered_at: str = ""


class ContextAccepted(BaseModel):
    accepted: bool = True
    ack_id: str
    stored_at: str


class ContextRejected(BaseModel):
    accepted: bool = False
    reason: str
    current_version: Optional[int] = None
    details: Optional[str] = None


class TickRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    now: str = ""
    available_triggers: list[str] = Field(default_factory=list)


class TickAction(BaseModel):
    conversation_id: str
    merchant_id: str
    customer_id: Optional[str] = None
    send_as: Literal["vera", "merchant_on_behalf"]
    trigger_id: str
    template_name: str
    template_params: list[str]
    body: str
    cta: str
    suppression_key: str
    rationale: str


class TickResponse(BaseModel):
    actions: list[TickAction]


class ReplyRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str = "merchant"
    message: str = ""
    received_at: str = ""
    turn_number: int = 1


class ReplySend(BaseModel):
    action: Literal["send"] = "send"
    body: str
    cta: str
    rationale: str


class ReplyWait(BaseModel):
    action: Literal["wait"] = "wait"
    wait_seconds: int
    rationale: str


class ReplyEnd(BaseModel):
    action: Literal["end"] = "end"
    rationale: str

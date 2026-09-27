from __future__ import annotations

import re
from typing import Literal

Intent = Literal["stop", "auto_reply", "accept", "decline", "off_topic", "question", "other"]

STOP_PATTERNS = [
    r"\bstop\b",
    r"unsubscribe",
    r"don't message",
    r"dont message",
    r"do not (message|text|contact)",
    r"not interested",
    r"\bspam\b",
    r"leave me",
    r"bother",
    r"useless",
    r"nahi chahiye",
    r"mat bhejo",
    r"band karo",
]

AUTO_REPLY_PATTERNS = [
    r"thank you for contacting",
    r"thanks for (contacting|reaching)",
    r"our team will (respond|get back|reply)",
    r"we will (get back|respond) shortly",
    r"automated assistant",
    r"this is an auto",
    r"auto[- ]?reply",
    r"currently unavailable",
    r"aapki jaankari ke liye",
    r"team tak pahuncha",
    r"office hours",
    r"we are closed",
]

ACCEPT_PATTERNS = [
    r"\byes\b",
    r"\byeah\b",
    r"\byep\b",
    r"\bok\b",
    r"\bokay\b",
    r"go ahead",
    r"do it",
    r"\bproceed\b",
    r"make it",
    r"send it",
    r"let'?s do it",
    r"lets do it",
    r"\bconfirm\b",
    r"sure",
    r"please send",
    r"please do",
    r"haan",
    r"ha ji",
    r"kar do",
    r"bhej do",
    r"what's next",
    r"whats next",
]

DECLINE_PATTERNS = [
    r"\bno\b",
    r"\bnope\b",
    r"not now",
    r"later",
    r"skip",
    r"nahi",
    r"maybe later",
]

OFF_TOPIC_PATTERNS = [
    r"\bgst\b",
    r"income tax",
    r"file my",
    r"payroll",
    r"loan",
    r"unrelated",
]


def _matches(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text, flags=re.IGNORECASE) for p in patterns)


def classify_intent(message: str) -> Intent:
    text = (message or "").strip()
    if not text:
        return "other"
    if _matches(text, STOP_PATTERNS):
        return "stop"
    if _matches(text, AUTO_REPLY_PATTERNS):
        return "auto_reply"
    if _matches(text, OFF_TOPIC_PATTERNS) and not _matches(text, ACCEPT_PATTERNS):
        return "off_topic"
    if _matches(text, ACCEPT_PATTERNS):
        return "accept"
    if _matches(text, DECLINE_PATTERNS):
        return "decline"
    if text.endswith("?") or _matches(text, [r"\bhow\b", r"\bwhat\b", r"\bcan you\b", r"kya "]):
        return "question"
    return "other"


def looks_like_auto_reply(message: str) -> bool:
    return classify_intent(message) == "auto_reply"

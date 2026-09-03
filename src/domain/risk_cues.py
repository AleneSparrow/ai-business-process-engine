"""Deterministic risk language shared by the AI calibrator and the fallback extractor.

These patterns are a backstop, not a classifier: they only fire on explicit
safety, advice/commitment, or hostility cues. Everyday sales language must
not match. Kept in `src.domain` so `src.engine` and `src.ai` can share them
without a circular import.
"""

import re

SAFETY_CUE = re.compile(
    r"\b(?:emergency|cannot breathe|can't breathe|trouble breathing|chest pain|"
    r"hurt myself|kill myself|suicid\w*|unconscious|severe bleeding|gas leak|"
    r"on fire|electrical sparks?|sparks?|smok(?:ing|es)|in danger|unsafe)\b",
    re.IGNORECASE,
)
HIGH_URGENCY_CUE = re.compile(
    r"\b(?:urgent(?:ly)?|asap|right away|immediately|today|tonight|now|"
    r"cannot wait|can't wait|time[- ]sensitive)\b",
    re.IGNORECASE,
)
ADVICE_OR_COMMITMENT_CUE = re.compile(
    r"\b(?:tell me exactly|what should i|should i|advise me|legal advice|"
    r"medical advice|diagnose me|decide for me|guarantee|promise|invest it)\b",
    re.IGNORECASE,
)
HOSTILE_CUE = re.compile(
    r"\b(?:fuck(?:ing)?|bullshit|idiot|moron|stupid|scam(?:mer)?|fraud)\b",
    re.IGNORECASE,
)
HUMAN_REQUEST_CUE = re.compile(
    r"\b(?:human|real person|live person|someone|representative|operator|agent|manager|supervisor)\b",
    re.IGNORECASE,
)

"""Transcript-level structural signal extraction."""

from __future__ import annotations

import re

from .models import Stage3Signal, Transcript


THEME_PATTERNS = {
    "backlog_expansion": (
        "record backlog",
        "backlog grew",
        "backlog growth",
        "bookings exceeded",
        "book-to-bill",
        "orders accelerated",
        "demand visibility",
        "order backlog",
        "new orders",
        "accelerating customer demand",
        "demand needed to support",
        "demand exceeds",
    ),
    "capacity_pre_sold": (
        "sold out",
        "pre-sold",
        "capacity committed",
        "reserved capacity",
        "take-or-pay",
        "long-term supply agreement",
        "customer commitments",
        "supply agreement",
        "purchase agreement",
    ),
    "pricing_power": (
        "pricing power",
        "price increases",
        "favorable pricing",
        "mix shift",
        "higher asp",
        "asp expansion",
        "premium pricing",
        "raised prices",
    ),
    "operating_leverage": (
        "operating leverage",
        "margin expansion",
        "scale benefits",
        "utilization improved",
        "yield improvement",
        "cost absorption",
    ),
    "new_cycle": (
        "new platform",
        "ramp",
        "inflection",
        "qualification",
        "design win",
        "production ramp",
        "commercial deployment",
        "contract award",
        "customer win",
        "strategic partnership",
        "larger ramp expected",
        "ramp expected",
    ),
}


def score_transcript(transcript: Transcript) -> Stage3Signal:
    normalized = _normalize(transcript.content)
    detected: list[str] = []
    evidence: list[str] = []

    for theme, phrases in THEME_PATTERNS.items():
        matched_phrase = next((phrase for phrase in phrases if phrase in normalized), None)
        if matched_phrase:
            detected.append(theme)
            excerpt = _excerpt_for_phrase(transcript.content, matched_phrase)
            if excerpt:
                evidence.append(excerpt)

    pricing_power_score = _pricing_score(detected, normalized)
    confidence = _confidence_score(detected, pricing_power_score)
    evidence_excerpt = " | ".join(dict.fromkeys(evidence))[:700]

    return Stage3Signal(
        ticker=transcript.symbol,
        backlog_expansion_detected="backlog_expansion" in detected,
        capacity_pre_sold="capacity_pre_sold" in detected,
        pricing_power_indicator=pricing_power_score,
        textual_evidence_excerpt=evidence_excerpt,
        pipeline_confidence_score=confidence,
        detected_themes=detected,
    )


def _normalize(content: str) -> str:
    return re.sub(r"\s+", " ", content).lower()


def _pricing_score(detected: list[str], normalized: str) -> int:
    score = 0
    if "pricing_power" in detected:
        score += 55
    if "operating_leverage" in detected:
        score += 20
    if "new_cycle" in detected:
        score += 15
    if any(phrase in normalized for phrase in ("discounting", "pricing pressure", "price decline", "lower asp")):
        score -= 25
    return max(0, min(100, score))


def _confidence_score(detected: list[str], pricing_power_score: int) -> int:
    weights = {
        "backlog_expansion": 24,
        "capacity_pre_sold": 24,
        "pricing_power": 18,
        "operating_leverage": 14,
        "new_cycle": 14,
    }
    score = sum(weights[theme] for theme in detected)
    if len(detected) >= 3:
        score += 12
    if pricing_power_score >= 70:
        score += 8
    return max(0, min(100, score))


def _excerpt_for_phrase(content: str, phrase: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", content)
    for sentence in sentences:
        if re.search(re.escape(phrase), sentence, re.IGNORECASE):
            return re.sub(r"\s+", " ", sentence).strip()
    return ""

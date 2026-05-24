"""News catalyst scoring."""

from __future__ import annotations

import re

from .models import NewsArticle, NewsSignal, Stage3Signal


CATALYST_PATTERNS = {
    "customer_win": ("customer win", "selected by", "awarded", "contract award", "new contract", "supply agreement"),
    "guidance_raise": ("raises guidance", "raised guidance", "boosts outlook", "increases forecast", "above consensus"),
    "analyst_upgrade": ("upgrades", "price target raised", "raises price target", "initiates buy", "reiterates buy"),
    "ai_infrastructure": ("ai infrastructure", "artificial intelligence", "data center", "800g", "1.6t", "gpu", "accelerator"),
    "capacity_expansion": ("capacity expansion", "expands capacity", "new facility", "production ramp", "ramp up", "comes online"),
    "earnings_beat": ("beats estimates", "earnings beat", "revenue beat", "better-than-expected", "record revenue"),
    "strategic_deal": ("partnership", "strategic partnership", "collaboration", "joint venture", "investment from"),
    "regulatory_approval": ("fda approval", "regulatory approval", "approved by", "clearance", "authorization"),
    "short_squeeze": ("short squeeze", "short interest", "days to cover", "borrow fee", "squeeze"),
}

RISK_PATTERNS = {
    "dilution": ("stock offering", "secondary offering", "atm offering", "shelf registration", "convertible notes", "warrants"),
    "downgrade": ("downgrades", "price target cut", "cuts price target", "initiates sell"),
    "legal": ("lawsuit", "investigation", "sec probe", "subpoena", "class action"),
    "accounting": ("restatement", "material weakness", "going concern", "delayed filing"),
    "guidance_cut": ("cuts guidance", "lowers outlook", "misses estimates", "below consensus"),
}


def score_news(symbol: str, articles: list[NewsArticle]) -> NewsSignal:
    themes: list[str] = []
    risk_flags: list[str] = []
    evidence: list[str] = []
    catalyst_score = 0
    risk_score = 0

    for article in articles[:12]:
        text = _normalize(" ".join(part for part in (article.title, article.description or "") if part))
        article_themes = [theme for theme, patterns in CATALYST_PATTERNS.items() if any(pattern in text for pattern in patterns)]
        article_risks = [theme for theme, patterns in RISK_PATTERNS.items() if any(pattern in text for pattern in patterns)]

        if article_themes:
            catalyst_score += 14 + min(12, len(article_themes) * 4)
            themes.extend(article_themes)
            evidence.append(article.title)
        if article_risks:
            risk_score += 18 + min(16, len(article_risks) * 6)
            risk_flags.extend(article_risks)
            evidence.append(article.title)

    themes = list(dict.fromkeys(themes))
    risk_flags = list(dict.fromkeys(risk_flags))
    evidence = list(dict.fromkeys(evidence))[:6]
    catalyst_score = max(0, min(100, catalyst_score))
    risk_score = max(0, min(100, risk_score))
    sentiment_score = max(0, min(100, 50 + catalyst_score // 2 - risk_score // 2))

    return NewsSignal(
        ticker=symbol,
        catalyst_score=catalyst_score,
        sentiment_score=sentiment_score,
        risk_score=risk_score,
        detected_themes=themes,
        risk_flags=risk_flags,
        evidence_headlines=evidence,
    )


def news_to_stage3_signal(news: NewsSignal) -> Stage3Signal:
    score = max(0, min(95, news.catalyst_score + (news.sentiment_score - 50) - news.risk_score // 2))
    return Stage3Signal(
        ticker=news.ticker,
        backlog_expansion_detected=any(theme in news.detected_themes for theme in ("customer_win", "capacity_expansion", "ai_infrastructure")),
        capacity_pre_sold="customer_win" in news.detected_themes or "strategic_deal" in news.detected_themes,
        pricing_power_indicator=news.sentiment_score,
        textual_evidence_excerpt=" | ".join(news.evidence_headlines),
        pipeline_confidence_score=score,
        detected_themes=[f"news_{theme}" for theme in news.detected_themes],
    )


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower()

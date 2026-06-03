"""Typed records moving through the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Ticker:
    symbol: str
    name: str | None = None
    exchange: str | None = None
    type: str | None = None
    sector: str | None = None
    industry: str | None = None


@dataclass(frozen=True)
class PriceStats:
    symbol: str
    close_price: float
    avg_volume_20d: float
    volatility_6m: float | None = None
    as_of: date | None = None
    return_6m: float | None = None
    return_ytd: float | None = None
    return_3m: float | None = None
    return_1m: float | None = None
    return_2w: float | None = None
    return_1w: float | None = None
    return_1d: float | None = None


@dataclass(frozen=True)
class FundamentalSnapshot:
    symbol: str
    capex_growth_yoy: float | None = None
    gross_margin_delta: float | None = None
    revenue_growth: float | None = None
    ev_to_tangible_book: float | None = None
    industry: str | None = None
    debt_to_equity: float | None = None
    revenue_growth_acceleration: float | None = None
    free_cash_flow_margin_delta: float | None = None


@dataclass(frozen=True)
class Stage1Candidate:
    ticker: Ticker
    price_stats: PriceStats


@dataclass(frozen=True)
class SieveHit:
    name: str
    score: float
    reason: str


@dataclass(frozen=True)
class Stage2Candidate:
    symbol: str
    score: float
    hits: list[SieveHit] = field(default_factory=list)
    snapshot: FundamentalSnapshot | None = None
    sector: str | None = None
    industry: str | None = None
    current_price: float | None = None
    volatility_6m: float | None = None
    return_6m: float | None = None
    return_ytd: float | None = None
    return_3m: float | None = None
    return_1m: float | None = None
    return_2w: float | None = None
    return_1w: float | None = None
    return_1d: float | None = None


@dataclass(frozen=True)
class Transcript:
    symbol: str
    quarter: str | None
    year: int | None
    content: str


@dataclass(frozen=True)
class Stage3Signal:
    ticker: str
    backlog_expansion_detected: bool
    capacity_pre_sold: bool
    pricing_power_indicator: int
    textual_evidence_excerpt: str
    pipeline_confidence_score: int
    detected_themes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Stage4Report:
    symbol: str
    archetype: str
    confidence_score: int
    markdown: str


@dataclass(frozen=True)
class NewsArticle:
    symbol: str
    title: str
    description: str | None = None
    published_utc: str | None = None
    url: str | None = None
    publisher: str | None = None


@dataclass(frozen=True)
class NewsSignal:
    ticker: str
    catalyst_score: int
    sentiment_score: int
    risk_score: int
    detected_themes: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    evidence_headlines: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SentimentSignal:
    ticker: str
    news_sentiment_score: int
    social_sentiment_score: int
    hype_score: int
    controversy_score: int
    catalyst_believability_score: int
    retail_attention_score: int
    summary: str
    bullish_points: list[str] = field(default_factory=list)
    bearish_points: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AnalystConsensus:
    symbol: str
    target_low: float | None = None
    target_median: float | None = None
    target_consensus: float | None = None
    target_high: float | None = None
    recent_target_avg: float | None = None
    recent_target_count: int | None = None
    last_year_target_avg: float | None = None
    last_year_target_count: int | None = None
    estimated_revenue: float | None = None
    estimated_eps: float | None = None
    num_analysts_revenue: int | None = None
    num_analysts_eps: int | None = None
    estimate_period: str | None = None
    estimate_year: int | None = None

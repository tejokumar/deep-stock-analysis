"""Stage 4 catalyst-linked report generation."""

from __future__ import annotations

from dataclasses import dataclass

from .models import AnalystConsensus, NewsSignal, SentimentSignal, Stage2Candidate, Stage3Signal, Stage4Report


@dataclass(frozen=True)
class ScenarioTargetValues:
    near_bear: float
    near_base: float
    near_bull: float
    long_bear: float
    long_base: float
    long_bull: float


def build_report(
    stage2: Stage2Candidate,
    stage3: Stage3Signal,
    analyst_consensus: AnalystConsensus | None = None,
    news_signal: NewsSignal | None = None,
    sentiment_signal: SentimentSignal | None = None,
) -> Stage4Report:
    archetype = classify_archetype(stage2, stage3)
    catalysts = catalyst_timeline(archetype, stage3)
    target_values = calculate_scenario_targets(stage2, stage3)
    targets = scenario_targets(stage2, stage3, target_values)
    analyst_section = analyst_estimates_section(analyst_consensus, stage2.current_price)
    news_section = news_catalyst_section(news_signal)
    sentiment_section = sentiment_section_markdown(sentiment_signal)
    decision = automated_decision_section(stage2, stage3, analyst_consensus, target_values, news_signal, sentiment_signal)
    quantitative_signals = "\n".join(f"- {hit.name}: {hit.reason}" for hit in stage2.hits if hit.name != "multi_signal_bonus")
    themes = ", ".join(stage3.detected_themes) if stage3.detected_themes else "none"
    current_price = f"${stage2.current_price:,.2f}" if stage2.current_price is not None else "Unavailable"

    markdown = f"""# {stage2.symbol} Deep Discovery Report

## Classification

- Archetype: {archetype}
- Current price: {current_price}
- Quant score: {stage2.score:.1f}
- Transcript confidence: {stage3.pipeline_confidence_score}
- Transcript themes: {themes}

## Why It Passed

{quantitative_signals}

## Transcript Evidence

{stage3.textual_evidence_excerpt or "No transcript excerpt captured."}

## Catalyst-Linked Timeline

{catalysts}

## Scenario Price Targets

{targets}

## Analyst Estimates

{analyst_section}

## News Catalyst

{news_section}

## Sentiment Analysis

{sentiment_section}

## Automated Action

{decision}
"""
    return Stage4Report(
        symbol=stage2.symbol,
        archetype=archetype,
        confidence_score=stage3.pipeline_confidence_score,
        markdown=markdown,
    )


def analyst_estimates_section(analyst: AnalystConsensus | None, current_price: float | None) -> str:
    if not analyst:
        return "Analyst consensus data unavailable from configured providers."

    lines = []
    if any(value is not None for value in (analyst.target_low, analyst.target_median, analyst.target_consensus, analyst.target_high)):
        lines.append(
            "- Price target low/median/consensus/high: "
            f"{_money(analyst.target_low)} / {_money(analyst.target_median)} / "
            f"{_money(analyst.target_consensus)} / {_money(analyst.target_high)}"
        )
        if current_price and analyst.target_consensus:
            upside = (analyst.target_consensus / current_price) - 1
            lines.append(f"- Consensus target upside/downside vs current price: {upside:.1%}")
    if analyst.recent_target_avg is not None:
        count = f" from {analyst.recent_target_count} target(s)" if analyst.recent_target_count is not None else ""
        lines.append(f"- Recent average target, last quarter: {_money(analyst.recent_target_avg)}{count}")
    if analyst.last_year_target_avg is not None:
        count = f" from {analyst.last_year_target_count} target(s)" if analyst.last_year_target_count is not None else ""
        lines.append(f"- Average target, last year: {_money(analyst.last_year_target_avg)}{count}")
    if analyst.estimated_revenue is not None or analyst.estimated_eps is not None:
        period = " ".join(str(part) for part in (analyst.estimate_period, analyst.estimate_year) if part)
        label = f" for {period}" if period else ""
        revenue_count = f" ({analyst.num_analysts_revenue} analyst(s))" if analyst.num_analysts_revenue is not None else ""
        eps_count = f" ({analyst.num_analysts_eps} analyst(s))" if analyst.num_analysts_eps is not None else ""
        lines.append(f"- Analyst estimated revenue{label}: {_money(analyst.estimated_revenue)}{revenue_count}")
        lines.append(f"- Analyst estimated EPS{label}: {_number(analyst.estimated_eps)}{eps_count}")
    if not lines:
        return "Analyst consensus endpoint returned no usable target or estimate fields."
    return "\n".join(lines)


def news_catalyst_section(news: NewsSignal | None) -> str:
    if not news:
        return "No high-scoring recent Polygon news catalyst detected for this candidate."
    themes = ", ".join(news.detected_themes) if news.detected_themes else "none"
    risks = ", ".join(news.risk_flags) if news.risk_flags else "none"
    headlines = "\n".join(f"- {headline}" for headline in news.evidence_headlines) or "- No evidence headlines captured."
    return (
        f"- Catalyst score: {news.catalyst_score}/100\n"
        f"- News sentiment score: {news.sentiment_score}/100\n"
        f"- News risk score: {news.risk_score}/100\n"
        f"- Catalyst themes: {themes}\n"
        f"- News risk flags: {risks}\n"
        f"- Evidence headlines:\n{headlines}"
    )


def sentiment_section_markdown(sentiment: SentimentSignal | None) -> str:
    if not sentiment:
        return "xAI sentiment analysis unavailable or not run for this candidate."
    bullish = "\n".join(f"- {point}" for point in sentiment.bullish_points) or "- None captured."
    bearish = "\n".join(f"- {point}" for point in sentiment.bearish_points) or "- None captured."
    return (
        f"- News sentiment score: {sentiment.news_sentiment_score}/100\n"
        f"- Social sentiment score: {sentiment.social_sentiment_score}/100\n"
        f"- Retail attention score: {sentiment.retail_attention_score}/100\n"
        f"- Hype score: {sentiment.hype_score}/100\n"
        f"- Controversy score: {sentiment.controversy_score}/100\n"
        f"- Catalyst believability score: {sentiment.catalyst_believability_score}/100\n"
        f"- Summary: {sentiment.summary}\n"
        f"- Bullish sentiment points:\n{bullish}\n"
        f"- Bearish sentiment points:\n{bearish}"
    )


def automated_decision_section(
    stage2: Stage2Candidate,
    stage3: Stage3Signal,
    analyst: AnalystConsensus | None,
    targets: ScenarioTargetValues | None,
    news: NewsSignal | None = None,
    sentiment: SentimentSignal | None = None,
) -> str:
    if stage2.current_price is None or targets is None:
        return (
            "- Bot action: Watch\n"
            "- Reason: current price or scenario targets are unavailable, so the bot cannot size the risk/reward."
        )

    current = stage2.current_price
    quant_score = min(stage2.score, 100)
    transcript_score = stage3.pipeline_confidence_score
    news_boost = 0
    news_risk = 0
    if news:
        news_boost = max(0, news.catalyst_score - 60) * 0.35
        news_risk = news.risk_score * 0.20
    sentiment_boost = 0
    sentiment_risk = 0
    if sentiment:
        sentiment_boost = max(0, sentiment.catalyst_believability_score - 60) * 0.25
        sentiment_risk = max(0, sentiment.hype_score - sentiment.catalyst_believability_score) * 0.20
        sentiment_risk += sentiment.controversy_score * 0.10
    thesis_score = max(
        0,
        min(100, (transcript_score * 0.55) + (quant_score * 0.45) + news_boost + sentiment_boost - news_risk - sentiment_risk),
    )
    volatility = stage2.volatility_6m or 0
    analyst_reference = _best_analyst_target(analyst)
    analyst_gap = (analyst_reference / current - 1) if analyst_reference else None
    price_ahead_of_street = analyst_gap is not None and analyst_gap < -0.10
    extended = volatility >= 0.09 or current > targets.near_base

    if thesis_score >= 72 and not extended and not price_ahead_of_street:
        action = "Early Accumulation Candidate"
        posture = "Start or add gradually while the price remains below the 3-6 month base scenario."
    elif thesis_score >= 72 and extended and not price_ahead_of_street:
        action = "Confirmed Breakout - Buy Pullbacks"
        posture = "Do not chase strength; prefer entries on pullbacks toward the risk-adjusted entry zone."
    elif thesis_score >= 72 and price_ahead_of_street:
        action = "Watchlist - Price Ahead of Street"
        posture = "Wait for either analyst revisions to catch up or a pullback that restores upside to recent Street targets."
    elif thesis_score >= 58:
        action = "Watch"
        posture = "Keep on the active watchlist until the next catalyst confirms margin, revenue, or backlog conversion."
    else:
        action = "Avoid"
        posture = "Insufficient evidence for a parabolic setup."

    entry_low, entry_high = _entry_zone(current, targets, extended, price_ahead_of_street)
    invalidation = _invalidation_rules(stage2, stage3, analyst_reference)
    upside_to_base = targets.near_base / current - 1
    downside_to_bear = targets.near_bear / current - 1

    lines = [
        f"- Bot action: {action}",
        f"- Thesis score: {thesis_score:.1f}/100 ({quant_score:.1f} quant, {transcript_score} transcript)",
        f"- Suggested posture: {posture}",
        f"- Preferred entry zone: ${entry_low:,.2f} to ${entry_high:,.2f}",
        f"- 3-6 month base upside: {upside_to_base:.1%}",
        f"- 3-6 month bear downside: {downside_to_bear:.1%}",
    ]
    if analyst_reference:
        lines.append(f"- Best recent analyst reference target: ${analyst_reference:,.2f} ({analyst_gap:.1%} vs current)")
    if news:
        lines.append(f"- News impact: catalyst {news.catalyst_score}/100, risk {news.risk_score}/100")
    if sentiment:
        lines.append(
            "- xAI sentiment impact: "
            f"believability {sentiment.catalyst_believability_score}/100, "
            f"hype {sentiment.hype_score}/100, controversy {sentiment.controversy_score}/100"
        )
    lines.extend(
        [
            f"- Invalidation triggers: {invalidation}",
            "- Execution note: these are automated research outputs based on configured data feeds, not personalized financial advice.",
        ]
    )
    return "\n".join(lines)


def _money(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"${value:,.2f}"


def _number(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:,.2f}"


def classify_archetype(stage2: Stage2Candidate, stage3: Stage3Signal) -> str:
    hit_names = {hit.name for hit in stage2.hits}
    industry = (stage2.snapshot.industry if stage2.snapshot else "") or ""
    industry = industry.lower()

    if stage3.capacity_pre_sold and ("capex_divergence" in hit_names or "new_cycle" in stage3.detected_themes):
        return "Capacity Ramp / Pre-Sold Demand"
    if "asset_replacement_discount" in hit_names:
        return "Asset Replacement Discount"
    if "margin_acceleration" in hit_names and "semiconductor" in industry:
        return "Cyclical Hardware Runner"
    if "pricing_power" in stage3.detected_themes and "revenue_acceleration" in hit_names:
        return "Pricing Power Re-Rating"
    return "Multi-Signal Structural Inflection"


def catalyst_timeline(archetype: str, stage3: Stage3Signal) -> str:
    if archetype == "Capacity Ramp / Pre-Sold Demand":
        return (
            "- 0-2 quarters: confirm customer commitments, backlog conversion, and capacity reservation details.\n"
            "- 2-4 quarters: track production ramp milestones and whether reserved capacity converts into revenue.\n"
            "- 4-8 quarters: watch for operating leverage as utilization improves and unit economics become visible."
        )
    if archetype == "Asset Replacement Discount":
        return (
            "- 0-2 quarters: confirm balance-sheet asset values and replacement-cost assumptions.\n"
            "- 2-4 quarters: track utilization, pricing stabilization, and inventory normalization.\n"
            "- 4-8 quarters: watch for valuation re-rating as asset earnings power becomes measurable."
        )
    if archetype == "Cyclical Hardware Runner":
        return (
            "- 0-2 quarters: confirm gross margin inflection and supply-demand tightening.\n"
            "- 2-4 quarters: track revenue recognition from platform ramps, design wins, or product-cycle transitions.\n"
            "- 4-8 quarters: watch for peak-cycle multiple expansion tied to normalized operating margin."
        )
    if archetype == "Pricing Power Re-Rating":
        return (
            "- 0-2 quarters: confirm ASP expansion and absence of offsetting discount pressure.\n"
            "- 2-4 quarters: track whether pricing flows into gross margin and estimate revisions.\n"
            "- 4-8 quarters: watch for multiple expansion as durable pricing power becomes consensus."
        )
    return (
        "- 0-2 quarters: confirm the first measurable catalyst behind the anomaly.\n"
        "- 2-4 quarters: track whether transcript claims become reported financial acceleration.\n"
        "- 4-8 quarters: watch for re-rating once the market can underwrite durability."
    )


def scenario_targets(stage2: Stage2Candidate, stage3: Stage3Signal, targets: ScenarioTargetValues | None = None) -> str:
    target_values = targets or calculate_scenario_targets(stage2, stage3)
    if target_values is None:
        return "Current price unavailable, so scenario targets were not generated."

    return (
        f"- 3-6 month bear/base/bull: ${target_values.near_bear:,.2f} / ${target_values.near_base:,.2f} / ${target_values.near_bull:,.2f}\n"
        f"- 12-24 month bear/base/bull: ${target_values.long_bear:,.2f} / ${target_values.long_base:,.2f} / ${target_values.long_bull:,.2f}\n"
        "- Method: current price multiplied by a scenario factor derived from quant score, transcript confidence, and recent volatility. "
        "Use this as a prioritization range; the automated action below combines the scenario range with analyst context and extension risk."
    )


def calculate_scenario_targets(stage2: Stage2Candidate, stage3: Stage3Signal) -> ScenarioTargetValues | None:
    if stage2.current_price is None:
        return None

    current = stage2.current_price
    confidence = stage3.pipeline_confidence_score / 100
    quant = min(stage2.score, 100) / 100
    signal_strength = (confidence * 0.65) + (quant * 0.35)
    volatility = stage2.volatility_6m or 0.06
    volatility_haircut = min(0.25, max(0.0, volatility - 0.05))

    near_base = current * (1 + 0.12 + signal_strength * 0.22 - volatility_haircut)
    near_bull = current * (1 + 0.28 + signal_strength * 0.38)
    near_bear = current * max(0.55, 0.82 - volatility_haircut)

    long_base = current * (1 + 0.35 + signal_strength * 0.55 - volatility_haircut)
    long_bull = current * (1 + 0.75 + signal_strength * 0.90)
    long_bear = current * max(0.40, 0.68 - volatility_haircut)

    return ScenarioTargetValues(
        near_bear=near_bear,
        near_base=near_base,
        near_bull=near_bull,
        long_bear=long_bear,
        long_base=long_base,
        long_bull=long_bull,
    )


def _best_analyst_target(analyst: AnalystConsensus | None) -> float | None:
    if not analyst:
        return None
    if analyst.recent_target_avg is not None and (analyst.recent_target_count or 0) > 0:
        return analyst.recent_target_avg
    return analyst.target_consensus


def _entry_zone(
    current: float,
    targets: ScenarioTargetValues,
    extended: bool,
    price_ahead_of_street: bool,
) -> tuple[float, float]:
    if price_ahead_of_street:
        return (max(targets.near_bear, current * 0.70), current * 0.88)
    if extended:
        return (max(targets.near_bear, current * 0.78), current * 0.93)
    return (current * 0.97, min(targets.near_base, current * 1.05))


def _invalidation_rules(stage2: Stage2Candidate, stage3: Stage3Signal, analyst_reference: float | None) -> str:
    rules = []
    snapshot = stage2.snapshot
    if snapshot and snapshot.revenue_growth_acceleration is not None:
        rules.append("revenue acceleration turns negative")
    if snapshot and snapshot.gross_margin_delta is not None and snapshot.gross_margin_delta < 0:
        rules.append("promised margin recovery fails to appear next quarter")
    if "new_cycle" in stage3.detected_themes:
        rules.append("ramp timing slips or customer demand language weakens")
    if analyst_reference and stage2.current_price and analyst_reference < stage2.current_price:
        rules.append("recent analyst targets do not revise upward after the next report")
    if not rules:
        rules.append("next quarter fails to confirm the stated catalyst")
    return "; ".join(rules)

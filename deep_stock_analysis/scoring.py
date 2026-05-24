"""Broad anomaly scoring for parabolic-move candidates."""

from __future__ import annotations

from .models import FundamentalSnapshot, PriceStats, SieveHit, Stage2Candidate


HARDWARE_INDUSTRY_TERMS = (
    "semiconductor",
    "computer hardware",
    "electronic components",
    "communication equipment",
    "solar",
)


def score_candidate(snapshot: FundamentalSnapshot, price_stats: PriceStats | None = None) -> Stage2Candidate:
    hits: list[SieveHit] = []

    if snapshot.capex_growth_yoy is not None and snapshot.capex_growth_yoy >= 0.30:
        compressed = price_stats and price_stats.volatility_6m is not None and price_stats.volatility_6m <= 0.05
        score = 24.0 if compressed else 16.0
        reason = f"CapEx growth YoY {snapshot.capex_growth_yoy:.1%}"
        if compressed:
            reason += f" with compressed 6m volatility {price_stats.volatility_6m:.1%}"
        hits.append(SieveHit("capex_divergence", score, reason))

    if snapshot.gross_margin_delta is not None and snapshot.gross_margin_delta >= 0.02:
        if snapshot.revenue_growth is None or snapshot.revenue_growth <= 0.05:
            hits.append(
                SieveHit(
                    "margin_acceleration",
                    22.0,
                    f"Gross margin expanded {snapshot.gross_margin_delta:.1%} while revenue growth stayed muted",
                )
            )
        else:
            hits.append(SieveHit("margin_acceleration", 14.0, f"Gross margin expanded {snapshot.gross_margin_delta:.1%}"))

    if snapshot.ev_to_tangible_book is not None and snapshot.ev_to_tangible_book <= 1.2:
        industry = (snapshot.industry or "").lower()
        hardware_match = any(term in industry for term in HARDWARE_INDUSTRY_TERMS)
        score = 22.0 if hardware_match else 13.0
        hits.append(SieveHit("asset_replacement_discount", score, f"EV/Tangible Book {snapshot.ev_to_tangible_book:.2f}x"))

    if snapshot.revenue_growth_acceleration is not None and snapshot.revenue_growth_acceleration >= 0.08:
        hits.append(
            SieveHit(
                "revenue_acceleration",
                16.0,
                f"Revenue growth acceleration improved {snapshot.revenue_growth_acceleration:.1%}",
            )
        )

    if snapshot.free_cash_flow_margin_delta is not None and snapshot.free_cash_flow_margin_delta >= 0.03:
        hits.append(
            SieveHit(
                "cash_flow_inflection",
                14.0,
                f"Free cash flow yield improved {snapshot.free_cash_flow_margin_delta:.1%}",
            )
        )

    if snapshot.debt_to_equity is not None and snapshot.debt_to_equity <= 0.35:
        hits.append(SieveHit("balance_sheet_optionality", 8.0, f"Debt/equity {snapshot.debt_to_equity:.2f}"))

    diversity_bonus = min(14.0, max(0, len(hits) - 1) * 4.0)
    total_score = sum(hit.score for hit in hits) + diversity_bonus
    if diversity_bonus:
        hits.append(SieveHit("multi_signal_bonus", diversity_bonus, f"{len(hits)} independent anomaly signals"))

    return Stage2Candidate(symbol=snapshot.symbol, score=round(total_score, 2), hits=hits, snapshot=snapshot)

"""Command line entry point for the discovery bot."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import re
import sys

from .config import PipelineConfig
from .news import news_to_stage3_signal
from .pipeline import DiscoveryPipeline
from .providers import FmpClient, PolygonClient, RoicClient, SampleProvider
from .sentiment import XaiSentimentClient, fallback_sentiment
from .models import Stage4Report
from .state import PipelineState


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the deep stock discovery bot.")
    parser.add_argument(
        "--stage",
        choices=["stage1", "stage2", "stage3", "stage4", "stage1-stage2", "stage1-stage3", "stage1-stage4", "index"],
        default="stage1-stage2",
    )
    parser.add_argument("--limit", type=int, default=1000, help="Maximum number of tickers to scan.")
    parser.add_argument("--all-tickers", action="store_true", help="Follow Polygon pagination and scan the full active ticker universe.")
    parser.add_argument("--shortlist-min-score", type=float, default=None, help="Override Stage 2 shortlist threshold.")
    parser.add_argument("--stage3-min-confidence", type=int, default=85, help="Minimum Stage 3 transcript confidence.")
    parser.add_argument("--reports-dir", default="reports", help="Directory for Stage 4 markdown reports.")
    parser.add_argument("--state-path", default=None, help="SQLite state path.")
    parser.add_argument("--sample-data", default=None, help="Run against a local sample JSON file.")
    parser.add_argument("--use-cached-stage1", action="store_true", help="Reuse cached Stage 1 candidates from the state DB.")
    parser.add_argument("--use-cached-stage2", action="store_true", help="Reuse cached Stage 2 candidates from the state DB.")
    parser.add_argument("--cache-max-age-hours", type=float, default=None, help="Maximum cache age for cached stage reuse.")
    parser.add_argument("--progress-every", type=int, default=100, help="Print progress every N completed ticker calls.")
    parser.add_argument("--max-sentiment-candidates", type=int, default=50, help="Maximum promoted candidates to send to xAI sentiment.")
    parser.add_argument("--refresh-index-prices", action="store_true", help="Refresh Polygon price performance for report symbols before writing index.")
    parser.add_argument("--refresh-index-details", action="store_true", help="Refresh Polygon company name, sector, and industry for report symbols before writing index.")
    parser.add_argument("--max-index", type=int, default=None, help="Maximum ranked rows to show in index.md.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = PipelineConfig.from_env(args.state_path)
    if args.shortlist_min_score is not None:
        config = replace(config, shortlist_min_score=args.shortlist_min_score)
    state = PipelineState(config.state_path)

    try:
        if args.stage == "index":
            reports_dir = Path(args.reports_dir)
            reports = load_reports_from_dir(reports_dir)
            if args.refresh_index_prices:
                if not config.polygon_api_key:
                    print("POLYGON_API_KEY is required for --refresh-index-prices.", file=sys.stderr, flush=True)
                    return 2
                refresh_index_prices(state, PolygonClient(config.polygon_api_key), reports, args.progress_every)
            if args.refresh_index_details:
                if not config.polygon_api_key:
                    print("POLYGON_API_KEY is required for --refresh-index-details.", file=sys.stderr, flush=True)
                    return 2
                refresh_index_details(state, PolygonClient(config.polygon_api_key), reports, args.progress_every)
            write_report_index(reports_dir, reports, state, max_rows=args.max_index)
            print(f"Regenerated ranked index for {len(reports)} reports in {reports_dir}.", flush=True)
            return 0

        if args.sample_data:
            provider = SampleProvider(Path(args.sample_data))
            universe_provider = provider
            fundamental_provider = provider
            transcript_provider = provider
            analyst_provider = None
            news_provider = provider
            sentiment_provider = None
        else:
            if not config.polygon_api_key:
                print("POLYGON_API_KEY is required unless --sample-data is provided.", file=sys.stderr)
                return 2
            if not (config.roic_api_key or config.fmp_api_key) and args.stage in {
                "stage2",
                "stage3",
                "stage4",
                "stage1-stage2",
                "stage1-stage3",
                "stage1-stage4",
            }:
                print("ROIC_API_KEY or FMP_API_KEY is required for Stage 2/3 unless --sample-data is provided.", file=sys.stderr)
                return 2
            universe_provider = PolygonClient(config.polygon_api_key)
            if config.roic_api_key:
                fundamental_provider = RoicClient(config.roic_api_key)
            else:
                fundamental_provider = FmpClient(config.fmp_api_key or "", fundamental_period=config.fmp_fundamental_period)
            transcript_provider = fundamental_provider
            analyst_provider = FmpClient(config.fmp_api_key, fundamental_period=config.fmp_fundamental_period) if config.fmp_api_key else None
            news_provider = universe_provider
            sentiment_provider = XaiSentimentClient(config.xai_api_key, config.xai_sentiment_model) if config.xai_api_key else None

        stage1_candidates = []
        pipeline = DiscoveryPipeline(
            config,
            state,
            universe_provider,
            fundamental_provider,
            transcript_provider,
            analyst_provider,
            news_provider,
            sentiment_provider,
        )
        if args.stage in {"stage1", "stage1-stage2", "stage1-stage3", "stage1-stage4"}:
            if args.use_cached_stage1:
                stage1_candidates = state.load_stage1(max_age_hours=args.cache_max_age_hours)
                print(f"Stage 1 loaded {len(stage1_candidates)} cached liquid equities.", flush=True)
            else:
                stage1_limit = None if args.all_tickers else args.limit
                stage1_candidates = pipeline.run_stage1(limit=stage1_limit, progress_every=args.progress_every)
            print(f"Stage 1 retained {len(stage1_candidates)} liquid equities.", flush=True)
            _print_error_summary("Stage 1", pipeline.stage1_errors)

        stage2_candidates = []
        if args.stage in {"stage2", "stage3", "stage4", "stage1-stage2", "stage1-stage3", "stage1-stage4"}:
            if args.use_cached_stage2:
                stage2_candidates = state.load_stage2(max_age_hours=args.cache_max_age_hours)
                print(f"Stage 2 loaded {len(stage2_candidates)} cached anomaly candidates.", flush=True)
            else:
                if not stage1_candidates:
                    if args.use_cached_stage1:
                        stage1_candidates = state.load_stage1(max_age_hours=args.cache_max_age_hours)
                        print(f"Stage 1 loaded {len(stage1_candidates)} cached liquid equities.", flush=True)
                    else:
                        stage1_limit = None if args.all_tickers else args.limit
                        stage1_candidates = pipeline.run_stage1(limit=stage1_limit, progress_every=args.progress_every)
                stage2_candidates = pipeline.run_stage2(stage1_candidates, progress_every=max(1, args.progress_every // 2))
            print(f"Stage 2 shortlisted {len(stage2_candidates)} anomaly candidates.", flush=True)
            _print_error_summary("Stage 2", pipeline.stage2_errors)
            for candidate in stage2_candidates[:25]:
                hit_names = ", ".join(hit.name for hit in candidate.hits)
                print(f"{candidate.symbol}: {candidate.score:.1f} ({hit_names})", flush=True)

        stage3_signals = []
        news_signals = []
        sentiment_signals = []
        if args.stage in {"stage3", "stage4", "stage1-stage3", "stage1-stage4"}:
            stage3_signals = pipeline.run_stage3(
                stage2_candidates,
                min_confidence=args.stage3_min_confidence,
                progress_every=max(1, args.progress_every // 4),
            )
            print(f"Stage 3 promoted {len(stage3_signals)} transcript-confirmed candidates.", flush=True)
            _print_error_summary("Stage 3", pipeline.stage3_errors)
            for signal in stage3_signals[:25]:
                themes = ", ".join(signal.detected_themes)
                print(f"{signal.ticker}: {signal.pipeline_confidence_score} confidence ({themes})", flush=True)

            news_signals = pipeline.run_news(stage2_candidates, progress_every=max(1, args.progress_every // 4))
            print(f"News analysis found {len(news_signals)} high-signal news catalysts.", flush=True)
            _print_error_summary("News", pipeline.news_errors)
            existing_symbols = {signal.ticker for signal in stage3_signals}
            for news_signal in news_signals:
                if news_signal.ticker not in existing_symbols and news_signal.catalyst_score >= 75 and news_signal.risk_score < 60:
                    stage3_signals.append(news_to_stage3_signal(news_signal))
                    existing_symbols.add(news_signal.ticker)
            stage3_signals.sort(key=lambda item: item.pipeline_confidence_score, reverse=True)
            for signal in stage3_signals[:25]:
                if any(theme.startswith("news_") for theme in signal.detected_themes):
                    themes = ", ".join(signal.detected_themes)
                    print(f"{signal.ticker}: {signal.pipeline_confidence_score} news-promoted confidence ({themes})", flush=True)

            sentiment_signals = pipeline.run_sentiment(stage3_signals, news_signals, max_candidates=args.max_sentiment_candidates)
            if not sentiment_signals and stage3_signals:
                news_by_symbol = {signal.ticker: signal for signal in news_signals}
                sentiment_signals = [
                    fallback_sentiment(signal.ticker, signal, news_by_symbol.get(signal.ticker))
                    for signal in stage3_signals
                ]
                state.save_sentiment(sentiment_signals)
            print(f"Sentiment analysis generated {len(sentiment_signals)} candidate sentiment profiles.", flush=True)
            _print_error_summary("Sentiment", pipeline.sentiment_errors)
            for sentiment in sentiment_signals[:25]:
                print(
                    f"{sentiment.ticker}: sentiment {sentiment.news_sentiment_score}, "
                    f"believability {sentiment.catalyst_believability_score}, hype {sentiment.hype_score}"
                    ,
                    flush=True,
                )

        if args.stage in {"stage4", "stage1-stage4"}:
            reports = pipeline.run_stage4(stage2_candidates, stage3_signals, news_signals, sentiment_signals)
            _print_error_summary("Stage 4", pipeline.stage4_errors)
            reports_dir = Path(args.reports_dir)
            reports_dir.mkdir(parents=True, exist_ok=True)
            for report in reports:
                report_path = reports_dir / f"{report.symbol}.md"
                report_path.write_text(report.markdown)
            write_report_index(reports_dir, reports, state, max_rows=args.max_index)
            print(f"Stage 4 generated {len(reports)} catalyst-linked reports in {reports_dir}.", flush=True)
    finally:
        state.close()

    return 0


def _print_error_summary(stage_name: str, errors: dict[str, str]) -> None:
    if not errors:
        return
    print(f"{stage_name} skipped {len(errors)} symbols because provider calls failed.", flush=True)
    for symbol, reason in list(errors.items())[:5]:
        print(f"{stage_name} skip {symbol}: {reason}", flush=True)


def write_report_index(reports_dir: Path, reports, state: PipelineState, max_rows: int | None = None) -> None:
    stage2_by_symbol = {candidate.symbol: candidate for candidate in state.load_stage2()}
    ranked = sorted(reports, key=lambda report: _final_score(report.markdown, stage2_by_symbol.get(report.symbol)), reverse=True)
    if max_rows is not None:
        ranked = ranked[:max_rows]
    headers = [
        "Rank",
        "Symbol",
        "Name",
        "Sub Sector",
        "Score",
        "Action",
        "Thesis",
        "Current",
        "Entry Zone",
        "Analyst Targets L/M/C/H",
        "Recent Target",
        "2026E Rev",
        "2026E EPS",
        "6M",
        "YTD",
        "3M",
        "1M",
        "1W",
        "Today",
        "Believability",
        "Hype",
        "Report",
    ]
    alignment = [
        "---:",
        "---",
        "---",
        "---",
        "---:",
        "---",
        "---:",
        "---:",
        "---",
        "---",
        "---",
        "---:",
        "---:",
        "---:",
        "---:",
        "---:",
        "---:",
        "---:",
        "---:",
        "---:",
        "---:",
        "---",
    ]
    rows = [
        "# Ranked Bot Summary",
        "",
        _markdown_row(headers),
        _markdown_row(alignment, escape=False),
    ]
    for rank, report in enumerate(ranked, start=1):
        metrics = _extract_report_metrics(report.markdown)
        stage2 = stage2_by_symbol.get(report.symbol)
        name = _company_name_for_symbol(state, report.symbol)
        final_score = _final_score(report.markdown, stage2)
        rows.append(
            _markdown_row(
                [
                    str(rank),
                    report.symbol,
                    name,
                    _sub_sector_for_symbol(state, report.symbol, stage2),
                    f"{final_score:.1f}",
                    metrics.get("action", ""),
                    metrics.get("thesis", ""),
                    _money(stage2.current_price if stage2 else None),
                    metrics.get("entry", ""),
                    metrics.get("analyst_targets", ""),
                    metrics.get("recent_target", ""),
                    metrics.get("estimated_revenue", ""),
                    metrics.get("estimated_eps", ""),
                    _pct(stage2.return_6m if stage2 else None),
                    _pct(stage2.return_ytd if stage2 else None),
                    _pct(stage2.return_3m if stage2 else None),
                    _pct(stage2.return_1m if stage2 else None),
                    _pct(stage2.return_1w if stage2 else None),
                    _pct(stage2.return_1d if stage2 else None),
                    metrics.get("believability", ""),
                    metrics.get("hype", ""),
                    f"[{report.symbol}.md]({report.symbol}.md)",
                ]
            )
        )
    (reports_dir / "index.md").write_text("\n".join(rows) + "\n")


def _markdown_row(values: list[str], escape: bool = True) -> str:
    cells = [_markdown_cell(value) if escape else value for value in values]
    return "| " + " | ".join(cells) + " |"


def _markdown_cell(value: str) -> str:
    return str(value).replace("\n", " ").replace("|", "\\|")


def _extract_report_metrics(markdown: str) -> dict[str, str]:
    patterns = {
        "action": r"- Bot action: (.+)",
        "thesis": r"- Thesis score: ([0-9.]+/100)",
        "entry": r"- Preferred entry zone: (.+)",
        "believability": r"believability ([0-9]+/100)",
        "hype": r"hype ([0-9]+/100)",
        "analyst_targets": r"- Price target low/median/consensus/high: (.+)",
        "recent_target": r"- Recent average target, last quarter: (.+)",
        "estimated_revenue": r"- Analyst estimated revenue(?:[^:]*): (.+)",
        "estimated_eps": r"- Analyst estimated EPS(?:[^:]*): (.+)",
    }
    return {
        key: (match.group(1).strip() if (match := re.search(pattern, markdown)) else "")
        for key, pattern in patterns.items()
    }


def _final_score(markdown: str, stage2) -> float:
    metrics = _extract_report_metrics(markdown)
    action = metrics.get("action", "")
    action_weight = {
        "Early Accumulation Candidate": 18,
        "Confirmed Breakout - Buy Pullbacks": 12,
        "Watchlist - Price Ahead of Street": 3,
        "Watch": -8,
        "Avoid": -30,
    }.get(action, 0)
    thesis_match = re.search(r"- Thesis score: ([0-9.]+)/100", markdown)
    believability_match = re.search(r"believability ([0-9]+)/100", markdown)
    hype_match = re.search(r"hype ([0-9]+)/100", markdown)
    recent_target_match = re.search(r"- Best recent analyst reference target: \$([0-9,.]+) \(([+-]?[0-9.]+)% vs current\)", markdown)
    base_upside_match = re.search(r"- 3-6 month base upside: ([+-]?[0-9.]+)%", markdown)
    thesis = float(thesis_match.group(1)) if thesis_match else 0
    believability = int(believability_match.group(1)) if believability_match else 0
    hype = int(hype_match.group(1)) if hype_match else 50
    analyst_upside = float(recent_target_match.group(2)) if recent_target_match else 0
    base_upside = float(base_upside_match.group(1)) if base_upside_match else 0

    score = 0.0
    score += action_weight
    score += thesis * 0.45
    score += believability * 0.35
    score += min(30, max(-20, analyst_upside)) * 0.45
    score += min(35, max(-20, base_upside)) * 0.35
    score -= max(0, hype - 65) * 0.35

    if believability < 60:
        score -= 20
    if "Price Ahead of Street" in action:
        score -= 12
    if stage2:
        if stage2.return_1m is not None and stage2.return_1m > 0.80:
            score -= 14
        if stage2.return_1w is not None and stage2.return_1w > 0.35:
            score -= 8
        if stage2.return_6m is not None and stage2.return_6m < -0.25 and stage2.return_1w is not None and stage2.return_1w > 0.05:
            score += 6
    return score


def _pct(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.1%}"


def _money(value: float | None) -> str:
    if value is None:
        return ""
    return f"${value:,.2f}"


def _company_name_for_symbol(state: PipelineState, symbol: str) -> str:
    row = state.connection.execute("select name from stage1_candidates where symbol = ?", (symbol,)).fetchone()
    if not row or not row["name"]:
        return ""
    return str(row["name"]).replace("|", "/")


def _sub_sector_for_symbol(state: PipelineState, symbol: str, stage2=None) -> str:
    if stage2 and stage2.industry:
        return _clean_sub_sector(stage2.industry)
    if stage2 and stage2.sector:
        return _clean_sub_sector(stage2.sector)
    row = state.connection.execute(
        """
        select coalesce(s2.industry, s1.industry, s2.sector, s1.sector) as sub_sector
        from stage2_candidates s2
        left join stage1_candidates s1 on s1.symbol = s2.symbol
        where s2.symbol = ?
        union all
        select coalesce(industry, sector) as sub_sector
        from stage1_candidates
        where symbol = ?
        limit 1
        """,
        (symbol, symbol),
    ).fetchone()
    if not row or not row["sub_sector"]:
        return ""
    return _clean_sub_sector(row["sub_sector"])


def _clean_sub_sector(value: str) -> str:
    text = str(value).strip()
    normalized = text.lower()
    labels = [
        ("Semiconductors", ("semiconductor",)),
        ("Memory/Storage", ("magnetic and optical recording media", "storage", "memory")),
        ("Software", ("prepackaged software", "software services", "software")),
        ("Networking Infrastructure", ("computer communications equipment", "networking")),
        ("Optical/Comms Equipment", ("communications equipment", "optical")),
        ("Electronic Components", ("electronic components",)),
        ("Power/Electrical Equipment", ("electronic & other electrical equipment", "electrical equipment")),
        ("Aerospace/Defense", ("aircraft", "aeronautical", "guided missiles", "defense")),
        ("Industrial Construction", ("heavy construction", "engineering services")),
        ("Utilities - Power", ("electric services",)),
        ("Pharma", ("pharmaceutical preparations",)),
        ("Biotech", ("biological products",)),
        ("Retail/E-Commerce", ("catalog & mail-order", "retail")),
        ("Business Services", ("business services",)),
    ]
    for label, keywords in labels:
        if any(keyword in normalized for keyword in keywords):
            return label
    return text.replace("|", "/").title()


def load_reports_from_dir(reports_dir: Path) -> list[Stage4Report]:
    reports = []
    for path in sorted(reports_dir.glob("*.md")):
        if path.name == "index.md":
            continue
        markdown = path.read_text()
        symbol = path.stem
        archetype_match = re.search(r"- Archetype: (.+)", markdown)
        confidence_match = re.search(r"- Transcript confidence: ([0-9]+)", markdown)
        reports.append(
            Stage4Report(
                symbol=symbol,
                archetype=archetype_match.group(1).strip() if archetype_match else "",
                confidence_score=int(confidence_match.group(1)) if confidence_match else 0,
                markdown=markdown,
            )
        )
    return reports


def refresh_index_prices(state: PipelineState, polygon: PolygonClient, reports: list[Stage4Report], progress_every: int) -> None:
    for index, report in enumerate(reports, start=1):
        try:
            stats = polygon.price_stats(report.symbol)
        except Exception as exc:
            print(f"Price refresh skipped {report.symbol}: {exc}", flush=True)
            continue
        if stats:
            state.update_stage2_price_stats(report.symbol, stats)
        if progress_every and index % progress_every == 0:
            print(f"Index price refresh progress: {index}/{len(reports)} symbols.", flush=True)


def refresh_index_details(state: PipelineState, polygon: PolygonClient, reports: list[Stage4Report], progress_every: int) -> None:
    for index, report in enumerate(reports, start=1):
        try:
            ticker = polygon.ticker_details(report.symbol)
        except Exception as exc:
            print(f"Details refresh skipped {report.symbol}: {exc}", flush=True)
            continue
        if ticker:
            state.update_ticker_details(ticker)
        if progress_every and index % progress_every == 0:
            print(f"Index details refresh progress: {index}/{len(reports)} symbols.", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())

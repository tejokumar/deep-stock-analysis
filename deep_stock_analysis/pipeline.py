"""Pipeline orchestration."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
import json
import time
from typing import Protocol

from .config import PipelineConfig
from .models import AnalystConsensus, FundamentalSnapshot, NewsArticle, NewsSignal, PriceStats, SentimentSignal, Stage1Candidate, Stage2Candidate, Stage3Signal, Stage4Report, Ticker, Transcript
from .news import score_news
from .providers import ProviderError
from .reports import build_report
from .scoring import score_candidate
from .state import PipelineState
from .transcripts import score_transcript


class UniverseProvider(Protocol):
    def active_us_equities(self, limit: int | None = 1000, progress_every_pages: int = 0) -> list[Ticker]:
        ...

    def price_stats(self, symbol: str) -> PriceStats | None:
        ...


class FundamentalProvider(Protocol):
    def fundamentals(self, symbol: str) -> FundamentalSnapshot:
        ...


class TranscriptProvider(Protocol):
    def latest_transcript(self, symbol: str) -> Transcript | None:
        ...


class AnalystProvider(Protocol):
    def analyst_consensus(self, symbol: str) -> AnalystConsensus | None:
        ...


class NewsProvider(Protocol):
    def latest_news(self, symbol: str, limit: int = 10) -> list[NewsArticle]:
        ...


class SentimentProvider(Protocol):
    def analyze(self, symbol: str, stage3: Stage3Signal | None, news: NewsSignal | None) -> SentimentSignal:
        ...


class DiscoveryPipeline:
    def __init__(
        self,
        config: PipelineConfig,
        state: PipelineState,
        universe_provider: UniverseProvider,
        fundamental_provider: FundamentalProvider,
        transcript_provider: TranscriptProvider | None = None,
        analyst_provider: AnalystProvider | None = None,
        news_provider: NewsProvider | None = None,
        sentiment_provider: SentimentProvider | None = None,
    ):
        self.config = config
        self.state = state
        self.universe_provider = universe_provider
        self.fundamental_provider = fundamental_provider
        self.transcript_provider = transcript_provider
        self.analyst_provider = analyst_provider
        self.news_provider = news_provider
        self.sentiment_provider = sentiment_provider
        self.stage1_errors: dict[str, str] = {}
        self.stage2_errors: dict[str, str] = {}
        self.stage3_errors: dict[str, str] = {}
        self.stage4_errors: dict[str, str] = {}
        self.news_errors: dict[str, str] = {}
        self.sentiment_errors: dict[str, str] = {}

    def run_stage1(self, limit: int | None = 1000, progress_every: int = 100) -> list[Stage1Candidate]:
        started = time.monotonic()
        tickers = [
            ticker
            for ticker in self.universe_provider.active_us_equities(limit=limit, progress_every_pages=1 if limit is None and progress_every else 0)
            if not ticker.type or ticker.type.upper() in {"CS", "ADRC", "ADRP"}
        ]
        if progress_every:
            print(f"Stage 1 fetched {len(tickers)} active common/ADR tickers.", flush=True)
        candidates: list[Stage1Candidate] = []
        processed = 0

        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            future_to_ticker = {executor.submit(self.universe_provider.price_stats, ticker.symbol): ticker for ticker in tickers}
            for future in as_completed(future_to_ticker):
                processed += 1
                ticker = future_to_ticker[future]
                try:
                    stats = future.result()
                except ProviderError as exc:
                    self.stage1_errors[ticker.symbol] = str(exc)
                    continue
                if not stats:
                    continue
                if stats.close_price >= self.config.min_close_price and stats.avg_volume_20d >= self.config.min_avg_volume:
                    candidates.append(Stage1Candidate(ticker=ticker, price_stats=stats))
                if progress_every and processed % progress_every == 0:
                    elapsed = time.monotonic() - started
                    print(f"Stage 1 progress: {processed}/{len(tickers)} scanned, {len(candidates)} retained, {elapsed:.1f}s elapsed.", flush=True)

        candidates.sort(key=lambda item: item.ticker.symbol)
        self.state.save_stage1(candidates)
        return candidates

    def run_stage2(self, stage1_candidates: list[Stage1Candidate], progress_every: int = 50) -> list[Stage2Candidate]:
        started = time.monotonic()
        price_by_symbol = {candidate.ticker.symbol: candidate.price_stats for candidate in stage1_candidates}
        ticker_by_symbol = {candidate.ticker.symbol: candidate.ticker for candidate in stage1_candidates}
        scored: list[Stage2Candidate] = []
        processed = 0

        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            future_to_symbol = {
                executor.submit(self.fundamental_provider.fundamentals, candidate.ticker.symbol): candidate.ticker.symbol
                for candidate in stage1_candidates
            }
            for future in as_completed(future_to_symbol):
                processed += 1
                symbol = future_to_symbol[future]
                try:
                    snapshot = future.result()
                except ProviderError as exc:
                    self.stage2_errors[symbol] = str(exc)
                    continue
                candidate = score_candidate(snapshot, price_by_symbol.get(symbol))
                price_stats = price_by_symbol.get(symbol)
                ticker = ticker_by_symbol.get(symbol)
                if price_stats:
                    candidate = replace(
                        candidate,
                        sector=ticker.sector if ticker and ticker.sector else None,
                        industry=(ticker.industry if ticker and ticker.industry else snapshot.industry),
                        current_price=price_stats.close_price,
                        volatility_6m=price_stats.volatility_6m,
                        return_6m=price_stats.return_6m,
                        return_ytd=price_stats.return_ytd,
                        return_3m=price_stats.return_3m,
                        return_1m=price_stats.return_1m,
                        return_1w=price_stats.return_1w,
                        return_1d=price_stats.return_1d,
                    )
                if candidate.score >= self.config.shortlist_min_score:
                    scored.append(candidate)
                if progress_every and processed % progress_every == 0:
                    elapsed = time.monotonic() - started
                    self.state.save_stage2(scored)
                    print(f"Stage 2 progress: {processed}/{len(stage1_candidates)} analyzed, {len(scored)} shortlisted, {elapsed:.1f}s elapsed.", flush=True)

        scored.sort(key=lambda item: item.score, reverse=True)
        self.state.save_stage2(scored)
        return scored

    def run_stage3(self, stage2_candidates: list[Stage2Candidate], min_confidence: int = 85, progress_every: int = 25) -> list[Stage3Signal]:
        if not self.transcript_provider:
            raise ValueError("Transcript provider is required for Stage 3")

        signals: list[Stage3Signal] = []
        processed = 0
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            future_to_symbol = {
                executor.submit(self.transcript_provider.latest_transcript, candidate.symbol): candidate.symbol
                for candidate in stage2_candidates
            }
            for future in as_completed(future_to_symbol):
                processed += 1
                symbol = future_to_symbol[future]
                try:
                    transcript = future.result()
                except ProviderError as exc:
                    self.stage3_errors[symbol] = str(exc)
                    continue
                if not transcript:
                    continue
                signal = score_transcript(transcript)
                if signal.pipeline_confidence_score >= min_confidence:
                    signals.append(signal)
                if progress_every and processed % progress_every == 0:
                    self.state.save_stage3(signals)
                    print(f"Stage 3 progress: {processed}/{len(stage2_candidates)} transcripts checked, {len(signals)} promoted.", flush=True)

        signals.sort(key=lambda item: item.pipeline_confidence_score, reverse=True)
        self.state.save_stage3(signals)
        return signals

    def run_news(self, stage2_candidates: list[Stage2Candidate], min_catalyst_score: int = 60, progress_every: int = 25) -> list[NewsSignal]:
        if not self.news_provider:
            return []

        signals: list[NewsSignal] = []
        processed = 0
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            future_to_symbol = {
                executor.submit(self.news_provider.latest_news, candidate.symbol): candidate.symbol
                for candidate in stage2_candidates
            }
            for future in as_completed(future_to_symbol):
                processed += 1
                symbol = future_to_symbol[future]
                try:
                    articles = future.result()
                except ProviderError as exc:
                    self.news_errors[symbol] = str(exc)
                    continue
                signal = score_news(symbol, articles)
                if signal.catalyst_score >= min_catalyst_score or signal.risk_score >= 50:
                    signals.append(signal)
                if progress_every and processed % progress_every == 0:
                    self.state.save_news(signals)
                    print(f"News progress: {processed}/{len(stage2_candidates)} tickers checked, {len(signals)} high-signal.", flush=True)

        signals.sort(key=lambda item: (item.catalyst_score - item.risk_score), reverse=True)
        self.state.save_news(signals)
        return signals

    def run_sentiment(
        self,
        stage3_signals: list[Stage3Signal],
        news_signals: list[NewsSignal] | None = None,
        max_candidates: int | None = None,
    ) -> list[SentimentSignal]:
        if not self.sentiment_provider:
            return []

        candidate_signals = stage3_signals[:max_candidates] if max_candidates is not None else stage3_signals
        news_by_symbol = {signal.ticker: signal for signal in news_signals or []}
        sentiment_signals: list[SentimentSignal] = []
        with ThreadPoolExecutor(max_workers=min(self.config.max_workers, 3)) as executor:
            future_to_symbol = {
                executor.submit(self.sentiment_provider.analyze, signal.ticker, signal, news_by_symbol.get(signal.ticker)): signal.ticker
                for signal in candidate_signals
            }
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    sentiment_signals.append(future.result())
                except (ProviderError, ValueError, KeyError, json.JSONDecodeError) as exc:
                    self.sentiment_errors[symbol] = str(exc)

        sentiment_signals.sort(key=lambda item: item.catalyst_believability_score, reverse=True)
        self.state.save_sentiment(sentiment_signals)
        return sentiment_signals

    def run_stage4(
        self,
        stage2_candidates: list[Stage2Candidate],
        stage3_signals: list[Stage3Signal],
        news_signals: list[NewsSignal] | None = None,
        sentiment_signals: list[SentimentSignal] | None = None,
    ) -> list[Stage4Report]:
        stage2_by_symbol = {candidate.symbol: candidate for candidate in stage2_candidates}
        news_by_symbol = {signal.ticker: signal for signal in news_signals or []}
        sentiment_by_symbol = {signal.ticker: signal for signal in sentiment_signals or []}
        reports: list[Stage4Report] = []
        for signal in stage3_signals:
            if signal.ticker not in stage2_by_symbol:
                continue
            analyst_consensus = None
            if self.analyst_provider:
                try:
                    analyst_consensus = self.analyst_provider.analyst_consensus(signal.ticker)
                except ProviderError as exc:
                    self.stage4_errors[signal.ticker] = str(exc)
            reports.append(
                build_report(
                    stage2_by_symbol[signal.ticker],
                    signal,
                    analyst_consensus,
                    news_by_symbol.get(signal.ticker),
                    sentiment_by_symbol.get(signal.ticker),
                )
            )
        reports.sort(key=lambda item: item.confidence_score, reverse=True)
        self.state.save_stage4(reports)
        return reports

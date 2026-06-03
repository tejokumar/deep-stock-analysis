"""SQLite state cache for resumable pipeline runs."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .models import FundamentalSnapshot, NewsSignal, PriceStats, SentimentSignal, SieveHit, Stage1Candidate, Stage2Candidate, Stage3Signal, Stage4Report, Ticker


class PipelineState:
    def __init__(self, path: Path):
        self.path = path
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self.connection.close()

    def save_stage1(self, candidates: Iterable[Stage1Candidate]) -> None:
        rows = [
            (
                candidate.ticker.symbol,
                candidate.ticker.name,
                candidate.ticker.exchange,
                candidate.ticker.sector,
                candidate.ticker.industry,
                candidate.price_stats.close_price,
                candidate.price_stats.avg_volume_20d,
                candidate.price_stats.volatility_6m,
                candidate.price_stats.return_6m,
                candidate.price_stats.return_ytd,
                candidate.price_stats.return_3m,
                candidate.price_stats.return_1m,
                candidate.price_stats.return_2w,
                candidate.price_stats.return_1w,
                candidate.price_stats.return_1d,
            )
            for candidate in candidates
        ]
        self.connection.executemany(
            """
            insert into stage1_candidates(
                symbol, name, exchange, sector, industry, close_price, avg_volume_20d, volatility_6m,
                return_6m, return_ytd, return_3m, return_1m, return_2w, return_1w, return_1d
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(symbol) do update set
                name=excluded.name,
                exchange=excluded.exchange,
                sector=coalesce(excluded.sector, stage1_candidates.sector),
                industry=coalesce(excluded.industry, stage1_candidates.industry),
                close_price=excluded.close_price,
                avg_volume_20d=excluded.avg_volume_20d,
                volatility_6m=excluded.volatility_6m,
                return_6m=excluded.return_6m,
                return_ytd=excluded.return_ytd,
                return_3m=excluded.return_3m,
                return_1m=excluded.return_1m,
                return_2w=excluded.return_2w,
                return_1w=excluded.return_1w,
                return_1d=excluded.return_1d,
                updated_at=current_timestamp
            """,
            rows,
        )
        self.connection.commit()

    def save_stage2(self, candidates: Iterable[Stage2Candidate]) -> None:
        rows = [
            (
                candidate.symbol,
                candidate.score,
                json.dumps([hit.__dict__ for hit in candidate.hits]),
                json.dumps(candidate.snapshot.__dict__ if candidate.snapshot else {}),
                candidate.sector,
                candidate.industry,
                candidate.current_price,
                candidate.volatility_6m,
                candidate.return_6m,
                candidate.return_ytd,
                candidate.return_3m,
                candidate.return_1m,
                candidate.return_2w,
                candidate.return_1w,
                candidate.return_1d,
            )
            for candidate in candidates
        ]
        self.connection.executemany(
            """
            insert into stage2_candidates(
                symbol, score, hits_json, snapshot_json, sector, industry, current_price, volatility_6m,
                return_6m, return_ytd, return_3m, return_1m, return_2w, return_1w, return_1d
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(symbol) do update set
                score=excluded.score,
                hits_json=excluded.hits_json,
                snapshot_json=excluded.snapshot_json,
                sector=coalesce(excluded.sector, stage2_candidates.sector),
                industry=coalesce(excluded.industry, stage2_candidates.industry),
                current_price=excluded.current_price,
                volatility_6m=excluded.volatility_6m,
                return_6m=excluded.return_6m,
                return_ytd=excluded.return_ytd,
                return_3m=excluded.return_3m,
                return_1m=excluded.return_1m,
                return_2w=excluded.return_2w,
                return_1w=excluded.return_1w,
                return_1d=excluded.return_1d,
                updated_at=current_timestamp
            """,
            rows,
        )
        self.connection.commit()

    def load_stage1(self, max_age_hours: float | None = None) -> list[Stage1Candidate]:
        age_filter = ""
        params: tuple[float, ...] = ()
        if max_age_hours is not None:
            age_filter = "where (julianday('now') - julianday(updated_at)) * 24 <= ?"
            params = (max_age_hours,)
        rows = self.connection.execute(
            f"""
            select symbol, name, exchange, sector, industry, close_price, avg_volume_20d, volatility_6m,
                   return_6m, return_ytd, return_3m, return_1m, return_2w, return_1w, return_1d
            from stage1_candidates
            {age_filter}
            order by symbol
            """,
            params,
        ).fetchall()
        return [
            Stage1Candidate(
                ticker=Ticker(
                    symbol=row["symbol"],
                    name=row["name"],
                    exchange=row["exchange"],
                    sector=row["sector"],
                    industry=row["industry"],
                ),
                price_stats=PriceStats(
                    symbol=row["symbol"],
                    close_price=row["close_price"],
                    avg_volume_20d=row["avg_volume_20d"],
                    volatility_6m=row["volatility_6m"],
                    return_6m=row["return_6m"],
                    return_ytd=row["return_ytd"],
                    return_3m=row["return_3m"],
                    return_1m=row["return_1m"],
                    return_2w=row["return_2w"],
                    return_1w=row["return_1w"],
                    return_1d=row["return_1d"],
                ),
            )
            for row in rows
        ]

    def load_stage2(self, max_age_hours: float | None = None) -> list[Stage2Candidate]:
        age_filter = ""
        params: tuple[float, ...] = ()
        if max_age_hours is not None:
            age_filter = "where (julianday('now') - julianday(updated_at)) * 24 <= ?"
            params = (max_age_hours,)
        rows = self.connection.execute(
            f"""
            select symbol, score, hits_json, snapshot_json, sector, industry, current_price, volatility_6m,
                   return_6m, return_ytd, return_3m, return_1m, return_2w, return_1w, return_1d
            from stage2_candidates
            {age_filter}
            order by score desc
            """,
            params,
        ).fetchall()
        candidates = []
        for row in rows:
            snapshot_data = json.loads(row["snapshot_json"] or "{}")
            hits_data = json.loads(row["hits_json"] or "[]")
            candidates.append(
                Stage2Candidate(
                    symbol=row["symbol"],
                    score=row["score"],
                    hits=[SieveHit(**hit) for hit in hits_data],
                    snapshot=FundamentalSnapshot(**snapshot_data) if snapshot_data else None,
                    sector=row["sector"],
                    industry=row["industry"],
                    current_price=row["current_price"],
                    volatility_6m=row["volatility_6m"],
                    return_6m=row["return_6m"],
                    return_ytd=row["return_ytd"],
                    return_3m=row["return_3m"],
                    return_1m=row["return_1m"],
                    return_2w=row["return_2w"],
                    return_1w=row["return_1w"],
                    return_1d=row["return_1d"],
                )
            )
        return candidates

    def update_stage2_price_stats(self, symbol: str, price_stats: PriceStats) -> None:
        self.connection.execute(
            """
            update stage2_candidates
            set current_price=?,
                volatility_6m=?,
                return_6m=?,
                return_ytd=?,
                return_3m=?,
                return_1m=?,
                return_2w=?,
                return_1w=?,
                return_1d=?,
                updated_at=current_timestamp
            where symbol=?
            """,
            (
                price_stats.close_price,
                price_stats.volatility_6m,
                price_stats.return_6m,
                price_stats.return_ytd,
                price_stats.return_3m,
                price_stats.return_1m,
                price_stats.return_2w,
                price_stats.return_1w,
                price_stats.return_1d,
                symbol,
            ),
        )
        self.connection.commit()

    def update_ticker_details(self, ticker: Ticker) -> None:
        self.connection.execute(
            """
            update stage1_candidates
            set name=coalesce(?, name),
                exchange=coalesce(?, exchange),
                sector=coalesce(?, sector),
                industry=coalesce(?, industry),
                updated_at=current_timestamp
            where symbol=?
            """,
            (ticker.name, ticker.exchange, ticker.sector, ticker.industry, ticker.symbol),
        )
        self.connection.execute(
            """
            update stage2_candidates
            set sector=coalesce(?, sector),
                industry=coalesce(?, industry),
                updated_at=current_timestamp
            where symbol=?
            """,
            (ticker.sector, ticker.industry, ticker.symbol),
        )
        self.connection.commit()

    def save_stage3(self, signals: Iterable[Stage3Signal]) -> None:
        rows = [
            (
                signal.ticker,
                int(signal.backlog_expansion_detected),
                int(signal.capacity_pre_sold),
                signal.pricing_power_indicator,
                signal.textual_evidence_excerpt,
                signal.pipeline_confidence_score,
                json.dumps(signal.detected_themes),
            )
            for signal in signals
        ]
        self.connection.executemany(
            """
            insert into stage3_signals(
                symbol,
                backlog_expansion_detected,
                capacity_pre_sold,
                pricing_power_indicator,
                textual_evidence_excerpt,
                pipeline_confidence_score,
                detected_themes_json
            )
            values (?, ?, ?, ?, ?, ?, ?)
            on conflict(symbol) do update set
                backlog_expansion_detected=excluded.backlog_expansion_detected,
                capacity_pre_sold=excluded.capacity_pre_sold,
                pricing_power_indicator=excluded.pricing_power_indicator,
                textual_evidence_excerpt=excluded.textual_evidence_excerpt,
                pipeline_confidence_score=excluded.pipeline_confidence_score,
                detected_themes_json=excluded.detected_themes_json,
                updated_at=current_timestamp
            """,
            rows,
        )
        self.connection.commit()

    def save_stage4(self, reports: Iterable[Stage4Report]) -> None:
        rows = [(report.symbol, report.archetype, report.confidence_score, report.markdown) for report in reports]
        self.connection.executemany(
            """
            insert into stage4_reports(symbol, archetype, confidence_score, markdown)
            values (?, ?, ?, ?)
            on conflict(symbol) do update set
                archetype=excluded.archetype,
                confidence_score=excluded.confidence_score,
                markdown=excluded.markdown,
                updated_at=current_timestamp
            """,
            rows,
        )
        self.connection.commit()

    def save_news(self, signals: Iterable[NewsSignal]) -> None:
        rows = [
            (
                signal.ticker,
                signal.catalyst_score,
                signal.sentiment_score,
                signal.risk_score,
                json.dumps(signal.detected_themes),
                json.dumps(signal.risk_flags),
                json.dumps(signal.evidence_headlines),
            )
            for signal in signals
        ]
        self.connection.executemany(
            """
            insert into news_signals(
                symbol,
                catalyst_score,
                sentiment_score,
                risk_score,
                detected_themes_json,
                risk_flags_json,
                evidence_headlines_json
            )
            values (?, ?, ?, ?, ?, ?, ?)
            on conflict(symbol) do update set
                catalyst_score=excluded.catalyst_score,
                sentiment_score=excluded.sentiment_score,
                risk_score=excluded.risk_score,
                detected_themes_json=excluded.detected_themes_json,
                risk_flags_json=excluded.risk_flags_json,
                evidence_headlines_json=excluded.evidence_headlines_json,
                updated_at=current_timestamp
            """,
            rows,
        )
        self.connection.commit()

    def save_sentiment(self, signals: Iterable[SentimentSignal]) -> None:
        rows = [
            (
                signal.ticker,
                signal.news_sentiment_score,
                signal.social_sentiment_score,
                signal.hype_score,
                signal.controversy_score,
                signal.catalyst_believability_score,
                signal.retail_attention_score,
                signal.summary,
                json.dumps(signal.bullish_points),
                json.dumps(signal.bearish_points),
            )
            for signal in signals
        ]
        self.connection.executemany(
            """
            insert into sentiment_signals(
                symbol,
                news_sentiment_score,
                social_sentiment_score,
                hype_score,
                controversy_score,
                catalyst_believability_score,
                retail_attention_score,
                summary,
                bullish_points_json,
                bearish_points_json
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(symbol) do update set
                news_sentiment_score=excluded.news_sentiment_score,
                social_sentiment_score=excluded.social_sentiment_score,
                hype_score=excluded.hype_score,
                controversy_score=excluded.controversy_score,
                catalyst_believability_score=excluded.catalyst_believability_score,
                retail_attention_score=excluded.retail_attention_score,
                summary=excluded.summary,
                bullish_points_json=excluded.bullish_points_json,
                bearish_points_json=excluded.bearish_points_json,
                updated_at=current_timestamp
            """,
            rows,
        )
        self.connection.commit()

    def _init_schema(self) -> None:
        self.connection.executescript(
            """
            create table if not exists stage1_candidates (
                symbol text primary key,
                name text,
                exchange text,
                sector text,
                industry text,
                close_price real not null,
                avg_volume_20d real not null,
                volatility_6m real,
                return_6m real,
                return_ytd real,
                return_3m real,
                return_1m real,
                return_2w real,
                return_1w real,
                return_1d real,
                updated_at text not null default current_timestamp
            );

            create table if not exists stage2_candidates (
                symbol text primary key,
                score real not null,
                hits_json text not null,
                snapshot_json text not null,
                sector text,
                industry text,
                current_price real,
                volatility_6m real,
                return_6m real,
                return_ytd real,
                return_3m real,
                return_1m real,
                return_2w real,
                return_1w real,
                return_1d real,
                updated_at text not null default current_timestamp
            );

            create table if not exists stage3_signals (
                symbol text primary key,
                backlog_expansion_detected integer not null,
                capacity_pre_sold integer not null,
                pricing_power_indicator integer not null,
                textual_evidence_excerpt text not null,
                pipeline_confidence_score integer not null,
                detected_themes_json text not null,
                updated_at text not null default current_timestamp
            );

            create table if not exists stage4_reports (
                symbol text primary key,
                archetype text not null,
                confidence_score integer not null,
                markdown text not null,
                updated_at text not null default current_timestamp
            );

            create table if not exists news_signals (
                symbol text primary key,
                catalyst_score integer not null,
                sentiment_score integer not null,
                risk_score integer not null,
                detected_themes_json text not null,
                risk_flags_json text not null,
                evidence_headlines_json text not null,
                updated_at text not null default current_timestamp
            );

            create table if not exists sentiment_signals (
                symbol text primary key,
                news_sentiment_score integer not null,
                social_sentiment_score integer not null,
                hype_score integer not null,
                controversy_score integer not null,
                catalyst_believability_score integer not null,
                retail_attention_score integer not null,
                summary text not null,
                bullish_points_json text not null,
                bearish_points_json text not null,
                updated_at text not null default current_timestamp
            );
            """
        )
        self._ensure_column("stage2_candidates", "current_price", "real")
        self._ensure_column("stage2_candidates", "volatility_6m", "real")
        for table in ("stage1_candidates", "stage2_candidates"):
            self._ensure_column(table, "sector", "text")
            self._ensure_column(table, "industry", "text")
        for table in ("stage1_candidates", "stage2_candidates"):
            self._ensure_column(table, "return_6m", "real")
            self._ensure_column(table, "return_ytd", "real")
            self._ensure_column(table, "return_3m", "real")
            self._ensure_column(table, "return_1m", "real")
            self._ensure_column(table, "return_2w", "real")
            self._ensure_column(table, "return_1w", "real")
            self._ensure_column(table, "return_1d", "real")
        self.connection.commit()

    def _ensure_column(self, table: str, column: str, column_type: str) -> None:
        columns = {row["name"] for row in self.connection.execute(f"pragma table_info({table})")}
        if column not in columns:
            self.connection.execute(f"alter table {table} add column {column} {column_type}")

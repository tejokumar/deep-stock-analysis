"""Data provider clients.

The live clients are intentionally thin: they normalize provider responses into
pipeline models while leaving scoring decisions elsewhere.
"""

from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
from statistics import mean, pstdev
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from .models import AnalystConsensus, FundamentalSnapshot, NewsArticle, PriceStats, Ticker, Transcript


class ProviderError(RuntimeError):
    pass


def _bar_date(bar: dict[str, Any]) -> date:
    timestamp = int(bar["t"]) / 1000
    return date.fromtimestamp(timestamp)


def _close_on_or_before(bars_by_date: dict[date, dict[str, Any]], target: date) -> float | None:
    current = target
    for _ in range(10):
        bar = bars_by_date.get(current)
        if bar:
            return float(bar["c"])
        current -= timedelta(days=1)
    return None


def _period_return(latest_close: float, prior_close: float | None) -> float | None:
    if prior_close in (None, 0):
        return None
    return (latest_close / prior_close) - 1


def _broad_sector_from_industry(industry: str | None) -> str | None:
    if not industry:
        return None
    text = industry.lower()
    sector_keywords = [
        ("Technology", ("software", "semiconductor", "computer communications", "computer peripheral", "communications equipment", "electronic components", "data processing")),
        ("Health Care", ("pharmaceutical", "biological", "medical", "health", "hospital", "diagnostic")),
        ("Financials", ("bank", "insurance", "investment", "broker", "credit", "mortgage")),
        ("Consumer Discretionary", ("retail", "catalog", "restaurants", "apparel", "automotive", "hotels")),
        ("Consumer Staples", ("food", "beverages", "grocery", "tobacco", "household")),
        ("Energy", ("oil", "gas", "petroleum", "drilling", "coal")),
        ("Utilities", ("electric services", "natural gas transmission", "water supply", "sanitary services")),
        ("Industrials", ("aircraft", "aeronautical", "construction", "machinery", "aerospace", "defense", "transportation", "electronic & other electrical equipment")),
        ("Materials", ("chemicals", "metals", "mining", "paper", "steel", "building materials")),
        ("Real Estate", ("real estate", "reit")),
        ("Communication Services", ("telecommunications", "cable", "broadcasting", "motion picture", "publishing")),
    ]
    for sector, keywords in sector_keywords:
        if any(keyword in text for keyword in keywords):
            return sector
    return None


class PolygonClient:
    base_url = "https://api.polygon.io"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def active_us_equities(self, limit: int | None = 1000, progress_every_pages: int = 0) -> list[Ticker]:
        params = {
            "market": "stocks",
            "active": "true",
            "locale": "us",
            "limit": min(limit or 1000, 1000),
            "apiKey": self.api_key,
        }
        tickers = []
        next_url: str | None = None
        pages = 0

        while True:
            payload = self._get_json_url(next_url) if next_url else self._get_json("/v3/reference/tickers", params)
            pages += 1
            for row in payload.get("results", []):
                tickers.append(
                    Ticker(
                        symbol=row["ticker"],
                        name=row.get("name"),
                        exchange=row.get("primary_exchange"),
                        type=row.get("type"),
                    )
                )
                if limit is not None and len(tickers) >= limit:
                    return tickers
            if progress_every_pages and pages % progress_every_pages == 0:
                print(f"Polygon ticker pagination: {pages} page(s), {len(tickers)} tickers fetched.", flush=True)
            next_url = payload.get("next_url")
            if not next_url:
                break
        return tickers

    def ticker_details(self, symbol: str) -> Ticker | None:
        payload = self._get_json(f"/v3/reference/tickers/{symbol}", {"apiKey": self.api_key})
        row = payload.get("results") or {}
        if not row:
            return None
        sic_description = row.get("sic_description")
        return Ticker(
            symbol=row.get("ticker") or symbol,
            name=row.get("name"),
            exchange=row.get("primary_exchange"),
            type=row.get("type"),
            sector=row.get("sector") or _broad_sector_from_industry(row.get("industry") or sic_description),
            industry=row.get("industry") or sic_description,
        )

    def price_stats(self, symbol: str, today: date | None = None) -> PriceStats | None:
        today = today or date.today()
        start = today - timedelta(days=210)
        path = f"/v2/aggs/ticker/{symbol}/range/1/day/{start.isoformat()}/{today.isoformat()}"
        payload = self._get_json(path, {"adjusted": "true", "sort": "asc", "limit": 5000, "apiKey": self.api_key})
        bars = payload.get("results") or []
        if not bars:
            return None

        bars_by_date = {_bar_date(bar): bar for bar in bars}
        latest_close = float(bars[-1]["c"])
        recent_20 = bars[-20:]
        recent_126 = bars[-126:]
        closes = [float(bar["c"]) for bar in recent_126 if "c" in bar]
        volatility = None
        if len(closes) >= 2:
            returns = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes)) if closes[i - 1]]
            volatility = pstdev(returns) if len(returns) >= 2 else None

        return PriceStats(
            symbol=symbol,
            close_price=latest_close,
            avg_volume_20d=mean(float(bar.get("v", 0)) for bar in recent_20),
            volatility_6m=volatility,
            as_of=today,
            return_6m=_period_return(latest_close, _close_on_or_before(bars_by_date, today - timedelta(days=182))),
            return_ytd=_period_return(latest_close, _close_on_or_before(bars_by_date, date(today.year, 1, 1))),
            return_3m=_period_return(latest_close, _close_on_or_before(bars_by_date, today - timedelta(days=91))),
            return_1m=_period_return(latest_close, _close_on_or_before(bars_by_date, today - timedelta(days=30))),
            return_1w=_period_return(latest_close, _close_on_or_before(bars_by_date, today - timedelta(days=7))),
            return_1d=_period_return(latest_close, float(bars[-2]["c"]) if len(bars) >= 2 else None),
        )

    def latest_news(self, symbol: str, limit: int = 10) -> list[NewsArticle]:
        payload = self._get_json(
            "/v2/reference/news",
            {
                "ticker": symbol,
                "limit": limit,
                "order": "desc",
                "sort": "published_utc",
                "apiKey": self.api_key,
            },
        )
        articles = []
        for row in payload.get("results", []):
            publisher = row.get("publisher") or {}
            articles.append(
                NewsArticle(
                    symbol=symbol,
                    title=row.get("title") or "",
                    description=row.get("description"),
                    published_utc=row.get("published_utc"),
                    url=row.get("article_url"),
                    publisher=publisher.get("name") if isinstance(publisher, dict) else None,
                )
            )
        return [article for article in articles if article.title]

    def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}?{urlencode(params)}"
        return self._get_json_url(url)

    def _get_json_url(self, url: str) -> dict[str, Any]:
        if "apiKey=" not in url:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}apiKey={self.api_key}"
        try:
            with urlopen(url, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise ProviderError(f"Polygon HTTP {exc.code} for {url.split('?')[0]}") from exc
        except URLError as exc:
            raise ProviderError(f"Polygon network error for {url.split('?')[0]}: {exc.reason}") from exc


class FmpClient:
    base_url = "https://financialmodelingprep.com"

    def __init__(self, api_key: str, fundamental_period: str = "annual"):
        self.api_key = api_key
        self.fundamental_period = fundamental_period

    def fundamentals(self, symbol: str) -> FundamentalSnapshot:
        if self.fundamental_period == "quarter":
            return self._quarterly_fundamentals(symbol)
        return self._annual_fundamentals(symbol)

    def _quarterly_fundamentals(self, symbol: str) -> FundamentalSnapshot:
        growth = self._get_list(f"/api/v3/financial-growth/{symbol}", {"period": "quarter", "limit": 8})
        ratios = self._get_list(f"/api/v3/ratios/{symbol}", {"period": "quarter", "limit": 4})
        metrics = self._optional_list(f"/api/v3/key-metrics/{symbol}", {"period": "quarter", "limit": 4})
        profile = self._optional_list(f"/api/v3/profile/{symbol}", {})

        capex_growth = self._field(growth, 0, "growthCapitalExpenditure")
        gross_margin_delta = None
        if len(ratios) >= 2:
            current = ratios[0].get("grossProfitMargin")
            previous = ratios[1].get("grossProfitMargin")
            if current is not None and previous is not None:
                gross_margin_delta = float(current) - float(previous)

        revenue_growth = self._field(growth, 0, "growthRevenue")
        ev_to_tangible_book = self._first_metric_field(
            metrics,
            0,
            (
                "enterpriseValueOverTangibleBookValue",
                "evToTangibleBookValue",
                "enterpriseValueToTangibleBookValue",
            ),
        )
        debt_to_equity = self._field(ratios, 0, "debtEquityRatio")
        fcf_margin_delta = None
        if len(metrics) >= 2:
            current_fcf = metrics[0].get("freeCashFlowYield")
            previous_fcf = metrics[1].get("freeCashFlowYield")
            if current_fcf is not None and previous_fcf is not None:
                fcf_margin_delta = float(current_fcf) - float(previous_fcf)

        revenue_acceleration = None
        if len(growth) >= 2:
            current_revenue = growth[0].get("growthRevenue")
            previous_revenue = growth[1].get("growthRevenue")
            if current_revenue is not None and previous_revenue is not None:
                revenue_acceleration = float(current_revenue) - float(previous_revenue)

        return FundamentalSnapshot(
            symbol=symbol,
            capex_growth_yoy=capex_growth,
            gross_margin_delta=gross_margin_delta,
            revenue_growth=revenue_growth,
            ev_to_tangible_book=ev_to_tangible_book,
            industry=(profile[0].get("industry") if profile else None),
            debt_to_equity=debt_to_equity,
            revenue_growth_acceleration=revenue_acceleration,
            free_cash_flow_margin_delta=fcf_margin_delta,
        )

    def _annual_fundamentals(self, symbol: str) -> FundamentalSnapshot:
        income = self._stable_list("income-statement", symbol, {"period": "annual", "limit": 5})
        balance = self._stable_list("balance-sheet-statement", symbol, {"period": "annual", "limit": 5})
        cash_flow = self._stable_list("cash-flow-statement", symbol, {"period": "annual", "limit": 5})
        ratios = self._optional_stable_list("ratios", symbol, {"period": "annual", "limit": 5})
        profile = self._optional_stable_list("profile", symbol, {})

        revenue_growth = self._growth(income, "revenue", 0, 1)
        previous_revenue_growth = self._growth(income, "revenue", 1, 2)
        revenue_acceleration = None
        if revenue_growth is not None and previous_revenue_growth is not None:
            revenue_acceleration = revenue_growth - previous_revenue_growth

        capex_growth = self._growth_abs(cash_flow, "capitalExpenditure", 0, 1)
        gross_margin_delta = self._margin_delta(income, "grossProfit", "revenue")
        debt_to_equity = self._debt_to_equity(balance)
        fcf_margin_delta = self._free_cash_flow_margin_delta(cash_flow, income)

        return FundamentalSnapshot(
            symbol=symbol,
            capex_growth_yoy=capex_growth,
            gross_margin_delta=gross_margin_delta,
            revenue_growth=revenue_growth,
            ev_to_tangible_book=None,
            industry=(profile[0].get("industry") if profile else None),
            debt_to_equity=debt_to_equity if debt_to_equity is not None else self._field(ratios, 0, "debtEquityRatio"),
            revenue_growth_acceleration=revenue_acceleration,
            free_cash_flow_margin_delta=fcf_margin_delta,
        )

    def latest_transcript(self, symbol: str) -> Transcript | None:
        try:
            return self._latest_earnings_transcript(symbol)
        except ProviderError:
            return self._latest_news_as_text(symbol)

    def _latest_earnings_transcript(self, symbol: str) -> Transcript | None:
        transcript_dates = self._get_list(f"/api/v4/earning_call_transcript", {"symbol": symbol})
        if not transcript_dates:
            return None
        latest = transcript_dates[0]
        quarter = str(latest.get("quarter")) if latest.get("quarter") is not None else None
        year = int(latest["year"]) if latest.get("year") is not None else None
        if not quarter or not year:
            return None
        rows = self._get_list(f"/api/v3/earning_call_transcript/{symbol}", {"quarter": quarter, "year": year})
        if not rows:
            return None
        content = rows[0].get("content") or rows[0].get("transcript") or ""
        if not content:
            return None
        return Transcript(symbol=symbol, quarter=quarter, year=year, content=content)

    def _latest_news_as_text(self, symbol: str) -> Transcript | None:
        rows = self._get_list("/stable/news/stock", {"symbols": symbol, "limit": 20})
        snippets: list[str] = []
        for row in rows:
            title = row.get("title") or ""
            text = row.get("text") or row.get("content") or row.get("summary") or ""
            snippet = " ".join(part for part in (title, text) if part)
            if snippet:
                snippets.append(snippet)
        if not snippets:
            return None
        return Transcript(symbol=symbol, quarter=None, year=None, content=" ".join(snippets))

    def analyst_consensus(self, symbol: str) -> AnalystConsensus | None:
        price_target = self._optional_stable_list("price-target-consensus", symbol, {})
        price_target_summary = self._optional_stable_list("price-target-summary", symbol, {})
        estimates = self._optional_stable_list("analyst-estimates", symbol, {"period": "annual", "limit": 8})
        if not price_target and not price_target_summary and not estimates:
            return None

        target_row = price_target[0] if price_target else {}
        summary_row = price_target_summary[0] if price_target_summary else {}
        estimate_row = self._nearest_forward_estimate(estimates)
        return AnalystConsensus(
            symbol=symbol,
            target_low=self._first_number(target_row, ("targetLow", "low", "priceTargetLow")),
            target_median=self._first_number(target_row, ("targetMedian", "median", "priceTargetMedian")),
            target_consensus=self._first_number(target_row, ("targetConsensus", "consensus", "priceTargetAverage", "targetMean")),
            target_high=self._first_number(target_row, ("targetHigh", "high", "priceTargetHigh")),
            recent_target_avg=self._first_number(summary_row, ("lastQuarterAvgPriceTarget", "lastMonthAvgPriceTarget")),
            recent_target_count=self._first_int(summary_row, ("lastQuarterCount", "lastMonthCount")),
            last_year_target_avg=self._first_number(summary_row, ("lastYearAvgPriceTarget",)),
            last_year_target_count=self._first_int(summary_row, ("lastYearCount",)),
            estimated_revenue=self._first_number(estimate_row, ("estimatedRevenueAvg", "revenueAvg", "estimatedRevenue")),
            estimated_eps=self._first_number(estimate_row, ("estimatedEpsAvg", "epsAvg", "estimatedEps")),
            num_analysts_revenue=self._first_int(estimate_row, ("numAnalystsRevenue",)),
            num_analysts_eps=self._first_int(estimate_row, ("numAnalystsEps",)),
            estimate_period=estimate_row.get("period"),
            estimate_year=int(estimate_row["date"][:4]) if isinstance(estimate_row.get("date"), str) and estimate_row["date"][:4].isdigit() else None,
        )

    def _get_list(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        payload = self._get_json(path, params | {"apikey": self.api_key})
        if isinstance(payload, list):
            return payload
        raise ProviderError(f"Expected list from FMP path {path}")

    def _optional_list(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            return self._get_list(path, params)
        except ProviderError:
            return []

    def _stable_list(self, endpoint: str, symbol: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        return self._get_list(f"/stable/{endpoint}", {"symbol": symbol} | params)

    def _optional_stable_list(self, endpoint: str, symbol: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            return self._stable_list(endpoint, symbol, params)
        except ProviderError:
            return []

    def _get_json(self, path: str, params: dict[str, Any]) -> Any:
        url = f"{self.base_url}{path}?{urlencode(params)}"
        try:
            with urlopen(url, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise ProviderError(f"FMP HTTP {exc.code} for {path}") from exc
        except URLError as exc:
            raise ProviderError(f"FMP network error for {path}: {exc.reason}") from exc

    @staticmethod
    def _field(rows: list[dict[str, Any]], index: int, name: str) -> float | None:
        if len(rows) <= index or rows[index].get(name) is None:
            return None
        return float(rows[index][name])

    @staticmethod
    def _first_metric_field(rows: list[dict[str, Any]], index: int, names: tuple[str, ...]) -> float | None:
        if len(rows) <= index:
            return None
        for name in names:
            if rows[index].get(name) is not None:
                return float(rows[index][name])
        return None

    @staticmethod
    def _growth(rows: list[dict[str, Any]], field: str, current_index: int, previous_index: int) -> float | None:
        if len(rows) <= previous_index:
            return None
        current = rows[current_index].get(field)
        previous = rows[previous_index].get(field)
        if current is None or previous in (None, 0):
            return None
        return (float(current) - float(previous)) / float(previous)

    @staticmethod
    def _growth_abs(rows: list[dict[str, Any]], field: str, current_index: int, previous_index: int) -> float | None:
        if len(rows) <= previous_index:
            return None
        current = rows[current_index].get(field)
        previous = rows[previous_index].get(field)
        if current is None or previous in (None, 0):
            return None
        current_abs = abs(float(current))
        previous_abs = abs(float(previous))
        if previous_abs == 0:
            return None
        return (current_abs - previous_abs) / previous_abs

    @staticmethod
    def _margin_delta(rows: list[dict[str, Any]], numerator_field: str, denominator_field: str) -> float | None:
        if len(rows) < 2:
            return None
        current = FmpClient._ratio(rows[0].get(numerator_field), rows[0].get(denominator_field))
        previous = FmpClient._ratio(rows[1].get(numerator_field), rows[1].get(denominator_field))
        if current is None or previous is None:
            return None
        return current - previous

    @staticmethod
    def _debt_to_equity(rows: list[dict[str, Any]]) -> float | None:
        if not rows:
            return None
        debt = rows[0].get("totalDebt")
        equity = rows[0].get("totalStockholdersEquity") or rows[0].get("totalEquity")
        return FmpClient._ratio(debt, equity)

    @staticmethod
    def _free_cash_flow_margin_delta(cash_flow: list[dict[str, Any]], income: list[dict[str, Any]]) -> float | None:
        if len(cash_flow) < 2 or len(income) < 2:
            return None
        current_fcf_margin = FmpClient._free_cash_flow_margin(cash_flow[0], income[0])
        previous_fcf_margin = FmpClient._free_cash_flow_margin(cash_flow[1], income[1])
        if current_fcf_margin is None or previous_fcf_margin is None:
            return None
        return current_fcf_margin - previous_fcf_margin

    @staticmethod
    def _free_cash_flow_margin(cash_flow_row: dict[str, Any], income_row: dict[str, Any]) -> float | None:
        operating_cash_flow = cash_flow_row.get("operatingCashFlow") or cash_flow_row.get("netCashProvidedByOperatingActivities")
        capex = cash_flow_row.get("capitalExpenditure")
        revenue = income_row.get("revenue")
        if operating_cash_flow is None or capex is None or revenue in (None, 0):
            return None
        free_cash_flow = float(operating_cash_flow) + float(capex)
        return free_cash_flow / float(revenue)

    @staticmethod
    def _ratio(numerator: Any, denominator: Any) -> float | None:
        if numerator is None or denominator in (None, 0):
            return None
        return float(numerator) / float(denominator)

    @staticmethod
    def _first_number(row: dict[str, Any], names: tuple[str, ...]) -> float | None:
        for name in names:
            value = row.get(name)
            if value is not None:
                return float(value)
        return None

    @staticmethod
    def _first_int(row: dict[str, Any], names: tuple[str, ...]) -> int | None:
        for name in names:
            value = row.get(name)
            if value is not None:
                return int(value)
        return None

    @staticmethod
    def _nearest_forward_estimate(rows: list[dict[str, Any]]) -> dict[str, Any]:
        current_year = date.today().year
        dated_rows = [
            row
            for row in rows
            if isinstance(row.get("date"), str) and row["date"][:4].isdigit() and int(row["date"][:4]) >= current_year
        ]
        if dated_rows:
            return sorted(dated_rows, key=lambda row: row["date"])[0]
        return rows[0] if rows else {}


class SampleProvider:
    """Local deterministic provider used for development and tests."""

    def __init__(self, sample_path: Path):
        self.data = json.loads(sample_path.read_text())

    def active_us_equities(self, limit: int = 1000, progress_every_pages: int = 0) -> list[Ticker]:
        rows = self.data["tickers"][:limit]
        return [Ticker(symbol=row["symbol"], name=row.get("name"), exchange=row.get("exchange"), type=row.get("type")) for row in rows]

    def price_stats(self, symbol: str, today: date | None = None) -> PriceStats | None:
        row = self.data["price_stats"].get(symbol)
        if not row:
            return None
        return PriceStats(
            symbol=symbol,
            close_price=float(row["close_price"]),
            avg_volume_20d=float(row["avg_volume_20d"]),
            volatility_6m=row.get("volatility_6m"),
        )

    def fundamentals(self, symbol: str) -> FundamentalSnapshot:
        row = self.data["fundamentals"][symbol]
        return FundamentalSnapshot(symbol=symbol, **row)

    def latest_transcript(self, symbol: str) -> Transcript | None:
        row = self.data.get("transcripts", {}).get(symbol)
        if not row:
            return None
        return Transcript(symbol=symbol, quarter=row.get("quarter"), year=row.get("year"), content=row["content"])

    def latest_news(self, symbol: str, limit: int = 10) -> list[NewsArticle]:
        rows = self.data.get("news", {}).get(symbol, [])[:limit]
        return [
            NewsArticle(
                symbol=symbol,
                title=row["title"],
                description=row.get("description"),
                published_utc=row.get("published_utc"),
                url=row.get("url"),
                publisher=row.get("publisher"),
            )
            for row in rows
        ]


class RoicClient:
    base_url = "https://api.roic.ai"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def fundamentals(self, symbol: str) -> FundamentalSnapshot:
        income = self._get_list(f"/v2/fundamental/income-statement/{symbol}", {"period": "quarterly", "limit": 8})
        cash_flow = self._get_list(f"/v2/fundamental/cash-flow/{symbol}", {"period": "quarterly", "limit": 8})
        balance = self._optional_list(f"/v2/fundamental/balance-sheet/{symbol}", {"period": "quarterly", "limit": 4})
        enterprise_value = self._optional_list(f"/v2/fundamental/enterprise-value/{symbol}", {"period": "quarterly", "limit": 4})
        profile = self._optional_get(f"/v2/company/profile/{symbol}", {})

        revenue_growth = self._growth(income, ("is_sales_revenue_turnover", "is_sales_and_services_revenues"), 0, 4)
        previous_revenue_growth = self._growth(income, ("is_sales_revenue_turnover", "is_sales_and_services_revenues"), 1, 5)
        revenue_acceleration = None
        if revenue_growth is not None and previous_revenue_growth is not None:
            revenue_acceleration = revenue_growth - previous_revenue_growth

        return FundamentalSnapshot(
            symbol=symbol,
            capex_growth_yoy=self._growth_abs(cash_flow, ("cf_cap_expenditures", "cf_purchase_of_fixed_prod_assets"), 0, 4),
            gross_margin_delta=self._percent_field_delta(income, "gross_margin", 0, 1),
            revenue_growth=revenue_growth,
            ev_to_tangible_book=self._ev_to_tangible_book(enterprise_value, balance),
            industry=profile.get("industry") if isinstance(profile, dict) else None,
            debt_to_equity=self._debt_to_equity(balance),
            revenue_growth_acceleration=revenue_acceleration,
            free_cash_flow_margin_delta=self._free_cash_flow_margin_delta(cash_flow, income),
        )

    def latest_transcript(self, symbol: str) -> Transcript | None:
        payload = self._get_json(f"/v2/company/earnings-calls/latest/{symbol}", {})
        if not isinstance(payload, dict):
            return None
        content = payload.get("content") or payload.get("transcript") or ""
        if not content:
            return None
        quarter = payload.get("quarter")
        year = payload.get("year")
        return Transcript(
            symbol=symbol,
            quarter=str(quarter) if quarter is not None else None,
            year=int(year) if year is not None else None,
            content=content,
        )

    def _get_list(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        payload = self._get_json(path, params)
        if isinstance(payload, list):
            return payload
        raise ProviderError(f"Expected list from ROIC path {path}")

    def _optional_list(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            return self._get_list(path, params)
        except ProviderError:
            return []

    def _optional_get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            payload = self._get_json(path, params)
            return payload if isinstance(payload, dict) else {}
        except ProviderError:
            return {}

    def _get_json(self, path: str, params: dict[str, Any]) -> Any:
        url = f"{self.base_url}{path}?{urlencode(params | {'apikey': self.api_key})}"
        try:
            with urlopen(url, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise ProviderError(f"ROIC HTTP {exc.code} for {path}") from exc
        except URLError as exc:
            raise ProviderError(f"ROIC network error for {path}: {exc.reason}") from exc

    @staticmethod
    def _growth(rows: list[dict[str, Any]], fields: tuple[str, ...], current_index: int, previous_index: int) -> float | None:
        current = RoicClient._row_number(rows, current_index, fields)
        previous = RoicClient._row_number(rows, previous_index, fields)
        if current is None or previous in (None, 0):
            return None
        return (current - previous) / previous

    @staticmethod
    def _growth_abs(rows: list[dict[str, Any]], fields: tuple[str, ...], current_index: int, previous_index: int) -> float | None:
        current = RoicClient._row_number(rows, current_index, fields)
        previous = RoicClient._row_number(rows, previous_index, fields)
        if current is None or previous is None:
            return None
        current_abs = abs(current)
        previous_abs = abs(previous)
        if previous_abs == 0:
            return None
        return (current_abs - previous_abs) / previous_abs

    @staticmethod
    def _percent_field_delta(rows: list[dict[str, Any]], field: str, current_index: int, previous_index: int) -> float | None:
        current = RoicClient._row_number(rows, current_index, (field,))
        previous = RoicClient._row_number(rows, previous_index, (field,))
        if current is None or previous is None:
            return None
        return (current - previous) / 100

    @staticmethod
    def _free_cash_flow_margin_delta(cash_flow: list[dict[str, Any]], income: list[dict[str, Any]]) -> float | None:
        current = RoicClient._free_cash_flow_margin(cash_flow, income, 0)
        previous = RoicClient._free_cash_flow_margin(cash_flow, income, 1)
        if current is None or previous is None:
            return None
        return current - previous

    @staticmethod
    def _free_cash_flow_margin(cash_flow: list[dict[str, Any]], income: list[dict[str, Any]], index: int) -> float | None:
        free_cash_flow = RoicClient._row_number(cash_flow, index, ("cf_free_cash_flow", "cf_free_cash_flow_firm"))
        revenue = RoicClient._row_number(income, index, ("is_sales_revenue_turnover", "is_sales_and_services_revenues"))
        if free_cash_flow is None or revenue in (None, 0):
            return None
        return free_cash_flow / revenue

    @staticmethod
    def _debt_to_equity(balance: list[dict[str, Any]]) -> float | None:
        debt = RoicClient._row_number(
            balance,
            0,
            ("bs_st_borrow", "bs_lt_borrow", "short_and_long_term_debt", "total_debt"),
            sum_fields=True,
        )
        equity = RoicClient._row_number(balance, 0, ("bs_tot_equity", "total_equity", "totalStockholdersEquity"))
        if debt is None or equity in (None, 0):
            return None
        return debt / equity

    @staticmethod
    def _ev_to_tangible_book(enterprise_value: list[dict[str, Any]], balance: list[dict[str, Any]]) -> float | None:
        ev = RoicClient._row_number(enterprise_value, 0, ("enterprise_value", "diluted_ev"))
        equity = RoicClient._row_number(balance, 0, ("bs_tot_equity", "total_equity", "totalStockholdersEquity"))
        goodwill = RoicClient._row_number(balance, 0, ("bs_goodwill", "goodwill"), default=0)
        intangibles = RoicClient._row_number(balance, 0, ("bs_intangibles", "intangibleAssets"), default=0)
        if ev is None or equity in (None, 0):
            return None
        tangible_book = equity - (goodwill or 0) - (intangibles or 0)
        if tangible_book <= 0:
            return None
        return ev / tangible_book

    @staticmethod
    def _row_number(
        rows: list[dict[str, Any]],
        index: int,
        fields: tuple[str, ...],
        default: float | None = None,
        sum_fields: bool = False,
    ) -> float | None:
        if len(rows) <= index:
            return default
        values = []
        for field in fields:
            value = rows[index].get(field)
            if value is not None:
                values.append(float(value))
        if not values:
            return default
        return sum(values) if sum_fields else values[0]

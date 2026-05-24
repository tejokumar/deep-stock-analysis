"""LLM sentiment analysis for promoted candidates."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import NewsSignal, SentimentSignal, Stage3Signal
from .providers import ProviderError


class XaiSentimentClient:
    base_url = "https://api.x.ai/v1/chat/completions"

    def __init__(self, api_key: str, model: str = "grok-4.3"):
        self.api_key = api_key
        self.model = model

    def analyze(self, symbol: str, stage3: Stage3Signal | None, news: NewsSignal | None) -> SentimentSignal:
        payload = {
            "model": self.model,
            "stream": False,
            "temperature": 0,
            "max_tokens": 700,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a market sentiment classifier for a stock discovery bot. "
                        "Return strict JSON only. Score 0-100. Distinguish real catalyst substance from hype."
                    ),
                },
                {
                    "role": "user",
                    "content": _sentiment_prompt(symbol, stage3, news),
                },
            ],
        }
        response = self._post_json(payload)
        content = response["choices"][0]["message"]["content"]
        return _parse_sentiment(symbol, content)

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            self.base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=45) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise ProviderError(f"xAI HTTP {exc.code} for sentiment analysis") from exc
        except URLError as exc:
            raise ProviderError(f"xAI network error for sentiment analysis: {exc.reason}") from exc


def fallback_sentiment(symbol: str, stage3: Stage3Signal | None, news: NewsSignal | None) -> SentimentSignal:
    news_sentiment = news.sentiment_score if news else 50
    hype = 70 if news and news.catalyst_score >= 90 and news.risk_score < 20 else 45
    believability = 50
    if stage3:
        believability += max(0, stage3.pipeline_confidence_score - 70) // 2
    if news:
        believability += max(0, news.catalyst_score - news.risk_score - 60) // 3
    believability = max(0, min(100, believability))
    return SentimentSignal(
        ticker=symbol,
        news_sentiment_score=news_sentiment,
        social_sentiment_score=50,
        hype_score=hype,
        controversy_score=news.risk_score if news else 0,
        catalyst_believability_score=believability,
        retail_attention_score=50 if news else 25,
        summary="Fallback sentiment derived from structured news/transcript scores because xAI sentiment was unavailable.",
    )


def _sentiment_prompt(symbol: str, stage3: Stage3Signal | None, news: NewsSignal | None) -> str:
    stage3_payload = {}
    if stage3:
        stage3_payload = {
            "transcript_confidence": stage3.pipeline_confidence_score,
            "transcript_themes": stage3.detected_themes,
            "transcript_evidence": stage3.textual_evidence_excerpt[:1200],
        }
    news_payload = {}
    if news:
        news_payload = {
            "news_catalyst_score": news.catalyst_score,
            "keyword_news_sentiment_score": news.sentiment_score,
            "news_risk_score": news.risk_score,
            "news_themes": news.detected_themes,
            "news_risk_flags": news.risk_flags,
            "headlines": news.evidence_headlines[:8],
        }
    return json.dumps(
        {
            "task": "Classify sentiment and catalyst quality for a potential parabolic stock move.",
            "symbol": symbol,
            "inputs": {"transcript": stage3_payload, "news": news_payload},
            "output_schema": {
                "news_sentiment_score": "integer 0-100",
                "social_sentiment_score": "integer 0-100; use 50 if no social data is provided",
                "hype_score": "integer 0-100",
                "controversy_score": "integer 0-100",
                "catalyst_believability_score": "integer 0-100",
                "retail_attention_score": "integer 0-100",
                "summary": "one concise sentence",
                "bullish_points": ["short strings"],
                "bearish_points": ["short strings"],
            },
            "rules": [
                "High hype without concrete customer, revenue, backlog, capacity, or margin evidence should lower believability.",
                "Analyst-upgrade headlines alone are weaker than customer orders, guidance raises, or earnings beats.",
                "Do not infer social sentiment unless supplied; use 50 neutral.",
                "Return JSON only, no markdown.",
            ],
        }
    )


def _parse_sentiment(symbol: str, content: str) -> SentimentSignal:
    raw = content.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
    data = json.loads(raw)
    return SentimentSignal(
        ticker=symbol,
        news_sentiment_score=_score(data.get("news_sentiment_score")),
        social_sentiment_score=_score(data.get("social_sentiment_score")),
        hype_score=_score(data.get("hype_score")),
        controversy_score=_score(data.get("controversy_score")),
        catalyst_believability_score=_score(data.get("catalyst_believability_score")),
        retail_attention_score=_score(data.get("retail_attention_score")),
        summary=str(data.get("summary") or ""),
        bullish_points=[str(item) for item in data.get("bullish_points", [])][:5],
        bearish_points=[str(item) for item in data.get("bearish_points", [])][:5],
    )


def _score(value: Any) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return 50

"""Runtime configuration for the discovery pipeline."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class PipelineConfig:
    polygon_api_key: str | None
    fmp_api_key: str | None
    state_path: Path
    roic_api_key: str | None = None
    xai_api_key: str | None = None
    xai_sentiment_model: str = "grok-4.3"
    fmp_fundamental_period: str = "annual"
    max_workers: int = 5
    min_close_price: float = 2.0
    min_avg_volume: int = 250_000
    shortlist_min_score: float = 55.0

    @classmethod
    def from_env(cls, state_path: str | None = None) -> "PipelineConfig":
        load_dotenv()
        return cls(
            polygon_api_key=os.getenv("POLYGON_API_KEY"),
            fmp_api_key=os.getenv("FMP_API_KEY"),
            xai_api_key=os.getenv("XAI_API_KEY"),
            roic_api_key=os.getenv("ROIC_API_KEY"),
            xai_sentiment_model=os.getenv("XAI_SENTIMENT_MODEL", "grok-4.3"),
            fmp_fundamental_period=os.getenv("FMP_FUNDAMENTAL_PERIOD", "annual"),
            state_path=Path(state_path or os.getenv("PIPELINE_STATE_PATH", "pipeline_state.db")),
            max_workers=int(os.getenv("MAX_WORKERS", "5")),
            shortlist_min_score=float(os.getenv("SHORTLIST_MIN_SCORE", "55")),
        )


def load_dotenv(path: str | Path = ".env") -> None:
    """Load KEY=VALUE pairs from a local .env file without overriding the shell."""
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue

        os.environ[key] = _clean_env_value(value.strip())


def _clean_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value

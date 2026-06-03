"""Alpaca paper-trading planner and executor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
import json
from pathlib import Path
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class AlpacaError(RuntimeError):
    pass


@dataclass(frozen=True)
class TradeCandidate:
    symbol: str
    rank: int
    score: float
    current_price: float
    entry_low: float | None
    entry_high: float | None
    action: str
    thesis: float | None
    believability: int | None
    hype: int | None


@dataclass(frozen=True)
class PaperOrderPlan:
    symbol: str
    side: str
    notional: float | None
    qty: float | None
    reason: str


class AlpacaPaperClient:
    def __init__(self, api_key: str, secret_key: str, base_url: str = "https://paper-api.alpaca.markets"):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url.rstrip("/")

    def account(self) -> dict[str, Any]:
        return self._request("GET", "/v2/account")

    def positions(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/v2/positions")
        return payload if isinstance(payload, list) else []

    def submit_order(self, order: PaperOrderPlan) -> dict[str, Any]:
        if order.side == "buy":
            body = {
                "symbol": order.symbol,
                "side": "buy",
                "type": "market",
                "time_in_force": "day",
                "notional": f"{order.notional:.2f}",
            }
        else:
            body = {
                "symbol": order.symbol,
                "side": "sell",
                "type": "market",
                "time_in_force": "day",
                "qty": f"{order.qty:.6f}".rstrip("0").rstrip("."),
            }
        return self._request("POST", "/v2/orders", body)

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={
                "APCA-API-KEY-ID": self.api_key,
                "APCA-API-SECRET-KEY": self.secret_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise AlpacaError(f"Alpaca HTTP {exc.code} for {path}: {detail}") from exc
        except URLError as exc:
            raise AlpacaError(f"Alpaca network error for {path}: {exc.reason}") from exc


def latest_report_dir(reports_root: Path) -> Path | None:
    candidates = [path for path in reports_root.iterdir() if path.is_dir() and re.match(r"^[0-9]+_", path.name)]
    return sorted(candidates)[0] if candidates else None


def load_candidates_from_index(index_path: Path) -> list[TradeCandidate]:
    rows = []
    for line in index_path.read_text().splitlines():
        if not line.startswith("| ") or "---" in line or "Rank" in line:
            continue
        cells = [_clean_cell(cell) for cell in line.strip().strip("|").split("|")]
        if len(cells) < 21:
            continue
        performance_offset = 1 if len(cells) >= 23 else 0
        rows.append(
            TradeCandidate(
                symbol=cells[1],
                rank=int(cells[0]),
                score=_number(cells[4]) or 0.0,
                action=cells[5],
                thesis=_number(cells[6]),
                current_price=_number(cells[7]) or 0.0,
                entry_low=_entry_number(cells[8], 0),
                entry_high=_entry_number(cells[8], 1),
                believability=int(_number(cells[19 + performance_offset]) or 0),
                hype=int(_number(cells[20 + performance_offset]) or 0),
            )
        )
    return rows


def build_order_plan(
    candidates: list[TradeCandidate],
    account: dict[str, Any],
    positions: list[dict[str, Any]],
    ledger: dict[str, Any],
    max_positions: int = 7,
    max_deployed_pct: float = 0.60,
    entry_buffer_pct: float = 0.05,
    stop_loss_pct: float = 0.15,
    min_hold_days: int = 20,
    max_hold_days: int = 180,
    min_order_notional: float = 25.0,
) -> list[PaperOrderPlan]:
    equity = float(account.get("equity") or account.get("portfolio_value") or 0)
    if equity <= 0:
        raise AlpacaError("Alpaca account equity is unavailable or zero.")

    position_by_symbol = {position["symbol"]: position for position in positions}
    today = date.today()
    targets = _target_weights(candidates[:max_positions], max_deployed_pct)
    orders: list[PaperOrderPlan] = []

    for symbol, position in position_by_symbol.items():
        if symbol not in ledger.get("positions", {}):
            continue
        market_value = abs(float(position.get("market_value") or 0))
        avg_entry = float(position.get("avg_entry_price") or 0)
        current_price = float(position.get("current_price") or 0)
        qty = abs(float(position.get("qty") or 0))
        held_days = _held_days(ledger, symbol, today)
        drawdown = (current_price / avg_entry - 1) if avg_entry else 0

        if drawdown <= -stop_loss_pct:
            orders.append(PaperOrderPlan(symbol, "sell", None, qty, f"stop loss hit: {drawdown:.1%}"))
        elif symbol not in targets and held_days >= min_hold_days:
            orders.append(PaperOrderPlan(symbol, "sell", None, qty, f"not in latest high-conviction list after {held_days} days"))
        elif held_days >= max_hold_days:
            orders.append(PaperOrderPlan(symbol, "sell", None, qty, f"max hold reached: {held_days} days"))

    for candidate in candidates[:max_positions]:
        target_value = equity * targets[candidate.symbol]
        max_entry = candidate.entry_high * (1 + entry_buffer_pct) if candidate.entry_high else None
        if max_entry is not None and candidate.current_price > max_entry:
            continue
        existing_value = abs(float(position_by_symbol.get(candidate.symbol, {}).get("market_value") or 0))
        add_notional = target_value - existing_value
        if add_notional >= min_order_notional:
            orders.append(
                PaperOrderPlan(
                    candidate.symbol,
                    "buy",
                    add_notional,
                    None,
                    f"rank {candidate.rank}, score {candidate.score:.1f}, target {targets[candidate.symbol]:.1%}",
                )
            )
    return orders


def execute_order_plan(client: AlpacaPaperClient, orders: list[PaperOrderPlan], execute: bool) -> list[dict[str, Any]]:
    submitted = []
    for order in orders:
        if execute:
            submitted.append(client.submit_order(order))
        else:
            submitted.append({"dry_run": True, "symbol": order.symbol, "side": order.side, "reason": order.reason})
    return submitted


def write_plan_markdown(
    path: Path,
    reports_dir: Path,
    candidates: list[TradeCandidate],
    orders: list[PaperOrderPlan],
    account: dict[str, Any],
    execute: bool,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    equity = account.get("equity") or account.get("portfolio_value") or ""
    rows = [
        "# Paper Trading Plan",
        "",
        f"- Mode: {'execute' if execute else 'dry-run'}",
        f"- Reports: `{reports_dir}`",
        f"- Account equity: {_money(equity)}",
        f"- Candidates: {len(candidates)}",
        f"- Planned orders: {len(orders)}",
        "",
        "## Candidate List",
        "",
        "| Rank | Symbol | Score | Current | Entry High | Believability | Hype |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for candidate in candidates:
        rows.append(
            "| "
            + " | ".join(
                [
                    str(candidate.rank),
                    candidate.symbol,
                    f"{candidate.score:.1f}",
                    _money(candidate.current_price),
                    _money(candidate.entry_high),
                    "" if candidate.believability is None else str(candidate.believability),
                    "" if candidate.hype is None else str(candidate.hype),
                ]
            )
            + " |"
        )
    rows.extend(["", "## Orders", ""])
    if not orders:
        rows.append("No orders needed.")
    else:
        rows.extend(["| Side | Symbol | Amount | Reason |", "|---|---|---:|---|"])
        for order in orders:
            amount = _money(order.notional) if order.notional is not None else f"{order.qty:g} shares"
            rows.append(f"| {order.side} | {order.symbol} | {amount} | {order.reason.replace('|', '/')} |")
    path.write_text("\n".join(rows) + "\n")


def load_ledger(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"positions": {}}
    return json.loads(path.read_text())


def update_ledger(path: Path, orders: list[PaperOrderPlan], execute: bool) -> None:
    if not execute:
        return
    ledger = load_ledger(path)
    positions = ledger.setdefault("positions", {})
    today = datetime.now(UTC).date().isoformat()
    for order in orders:
        if order.side == "buy":
            positions.setdefault(order.symbol, {"opened_at": today})
        elif order.side == "sell":
            positions.pop(order.symbol, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")


def _target_weights(candidates: list[TradeCandidate], max_deployed_pct: float) -> dict[str, float]:
    base = []
    for candidate in candidates:
        if candidate.rank <= 3:
            base.append((candidate.symbol, 0.10))
        elif candidate.rank <= 7:
            base.append((candidate.symbol, 0.06))
        else:
            base.append((candidate.symbol, 0.04))
    total = sum(weight for _, weight in base)
    scale = min(1.0, max_deployed_pct / total) if total else 0
    return {symbol: weight * scale for symbol, weight in base}


def _held_days(ledger: dict[str, Any], symbol: str, today: date) -> int:
    opened_at = ledger.get("positions", {}).get(symbol, {}).get("opened_at")
    if not opened_at:
        return 999
    return (today - date.fromisoformat(opened_at)).days


def _clean_cell(value: str) -> str:
    return value.strip().replace("\\|", "|")


def _number(value: str) -> float | None:
    match = re.search(r"-?[0-9,.]+", value.replace("$", ""))
    return float(match.group(0).replace(",", "")) if match else None


def _entry_number(value: str, index: int) -> float | None:
    matches = re.findall(r"\$?([0-9,.]+)", value)
    if len(matches) <= index:
        return None
    return float(matches[index].replace(",", ""))


def _money(value: Any) -> str:
    if value in (None, ""):
        return ""
    return f"${float(value):,.2f}"

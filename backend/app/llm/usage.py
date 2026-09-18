"""Cost accounting (SPEC 6.8).

Phase 0 records every paid call to a JSONL file. Phase 2 moves this to the
UsageLog table and adds enforcement of MONTHLY_BUDGET_USD; the calculation
itself does not change.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

from app.config import APP_DIR, USAGE_LOG
from app.schemas import Usage

PRICING_PATH = APP_DIR / "llm" / "pricing.yaml"


@dataclass(frozen=True)
class ModelPrice:
    input_per_mtok: float
    output_per_mtok: float
    cache_write_multiplier: float = 1.25
    cache_read_multiplier: float = 0.1


class UnknownModelPriceError(LookupError):
    pass


def load_pricing(path: Path = PRICING_PATH) -> dict[str, ModelPrice]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    defaults = data.get("defaults", {})
    prices: dict[str, ModelPrice] = {}
    for model, entry in (data.get("models") or {}).items():
        prices[model] = ModelPrice(
            input_per_mtok=float(entry["input_per_mtok"]),
            output_per_mtok=float(entry["output_per_mtok"]),
            cache_write_multiplier=float(defaults.get("cache_write_multiplier", 1.25)),
            cache_read_multiplier=float(defaults.get("cache_read_multiplier", 0.1)),
        )
    return prices


def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
    prices: dict[str, ModelPrice] | None = None,
) -> float:
    """Cost of one call in USD.

    Raises rather than silently returning 0 for an unknown model: a budget that
    quietly stops counting is worse than no budget (D4).
    """
    table = prices if prices is not None else load_pricing()
    price = table.get(model)
    if price is None:
        raise UnknownModelPriceError(
            f"No hay precio registrado para el modelo '{model}'. "
            f"Agrégalo en {PRICING_PATH.name} antes de usarlo."
        )

    per_token_in = price.input_per_mtok / 1_000_000
    per_token_out = price.output_per_mtok / 1_000_000

    return (
        input_tokens * per_token_in
        + output_tokens * per_token_out
        + cache_write_tokens * per_token_in * price.cache_write_multiplier
        + cache_read_tokens * per_token_in * price.cache_read_multiplier
    )


def record(usage: Usage, log_path: Path | None = None, **extra: object) -> None:
    """Append one call to the usage log."""
    # Resolved at call time rather than as a default argument, so the path stays
    # overridable in tests and by a future per-environment setting.
    log_path = log_path if log_path is not None else USAGE_LOG
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        **usage.model_dump(mode="json"),
        **extra,
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def month_to_date(log_path: Path | None = None, now: datetime | None = None) -> float:
    """Total spend for the current calendar month."""
    log_path = log_path if log_path is not None else USAGE_LOG
    if not log_path.is_file():
        return 0.0
    now = now or datetime.now(UTC)
    total = 0.0
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            stamp = datetime.fromisoformat(entry["timestamp"])
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
        if (stamp.year, stamp.month) == (now.year, now.month):
            total += float(entry.get("cost_usd", 0.0))
    return total

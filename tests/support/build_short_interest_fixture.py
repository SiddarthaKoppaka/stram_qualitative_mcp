"""Rebuild the short_interest part of `tests/fixtures/news`. Everything here is invented.

Only the two short_interest directories are replaced; the rest of the fixture is left as it is. The
tickers are ones the synthetic lake already uses (plus one made up), the figures are made up, and no
FINRA data is copied. Rows go through stram_data's own publisher, so the layout is the real one.
"""

from __future__ import annotations

import shutil
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from stram_data.news.short_interest_lake import (
    SHORT_INTEREST_DATASET,
    ShortInterestParquetPublisher,
    event_id,
)

PARQUET_ROOT = Path(__file__).parents[1] / "fixtures/news/parquet"
INGESTED = datetime(2026, 10, 30, 9, tzinfo=UTC)
SETTLEMENTS = (date(2026, 9, 15), date(2026, 9, 30), date(2026, 10, 15), date(2026, 10, 30))
# Hidden characters a publisher could put in a name; the tool strips them.
HIDDEN_NAME = "Bolt​ Synthetic\x07 Corp"


def _row(
    symbol: str, settlement: date, position: int, previous: int | None, **changes: Any
) -> dict[str, Any]:
    """One invented row; `changes` overrides issue_name, average_daily_volume or a flag."""
    row: dict[str, Any] = {
        "issue_name": "Synthetic Issuer Inc Common",
        "average_daily_volume": 500_000,
        "split_flag": False,
        "revision_flag": False,
    }
    row.update(changes)
    volume = row["average_daily_volume"]
    return {
        "event_id": event_id(symbol, settlement),
        "symbol": symbol,
        "settlement_date": settlement,
        "short_position": position,
        "previous_short_position": previous,
        "change_percent": None
        if previous is None
        else round((position - previous) / previous * 100, 2),
        "days_to_cover": None if volume is None else round(position / volume, 2),
        "market_class": "NNM",
        "published_estimated": settlement + timedelta(days=8),
        "ingested_at": INGESTED,
        **row,
    }


def rows() -> list[dict[str, Any]]:
    first, second, third, fourth = SETTLEMENTS
    return [
        # AAPL: four figures, the third flagged as a split and the fourth as revised.
        _row("AAPL", first, 1_000_000, None),
        _row("AAPL", second, 1_200_000, 1_000_000),
        _row("AAPL", third, 600_000, 1_200_000, split_flag=True),
        _row("AAPL", fourth, 660_000, 600_000, revision_flag=True),
        # MSFT: two figures, the later one without an average daily volume.
        _row("MSFT", second, 2_500_000, 2_000_000),
        _row("MSFT", fourth, 2_400_000, 2_500_000, average_daily_volume=None),
        # BOLT: one figure with hidden characters in the publisher's name.
        _row("BOLT", fourth, 42, 40, issue_name=HIDDEN_NAME, average_daily_volume=None),
    ]


def main() -> None:
    built = rows()  # build first: a failure must not leave the fixture deleted
    shutil.rmtree(PARQUET_ROOT / SHORT_INTEREST_DATASET, ignore_errors=True)
    shutil.rmtree(PARQUET_ROOT / "_manifests" / SHORT_INTEREST_DATASET, ignore_errors=True)
    ShortInterestParquetPublisher(PARQUET_ROOT).publish(built)


if __name__ == "__main__":
    main()

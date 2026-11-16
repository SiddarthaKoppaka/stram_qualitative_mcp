"""Rebuild the insider_transaction part of `tests/fixtures/news`. Everything here is invented.

Only the two insider directories are replaced; the news fixture is left as it is. Names are
made up, the issuer is a ticker the synthetic lake already uses, and every accession and path is
fictional.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from stram_data.news.insider_lake import INSIDER_DATASET, INSIDER_SCHEMA, InsiderParquetPublisher

PARQUET_ROOT = Path(__file__).parents[1] / "fixtures/news/parquet"
INGESTED = datetime(2026, 10, 30, 9, tzinfo=UTC)
ISSUER = {
    "issuer_cik": "0000000001",
    "issuer_name": "Synthetic Issuer Inc",
    "issuer_ticker": "AAPL",
}


@dataclass(frozen=True)
class Trade:
    """One invented transaction; `_row` fills in the rest of a stored row."""

    accession: str
    filed: date
    owner: str
    code: str
    category: str
    shares: str
    price: str | None
    plan: bool | None = None
    derivative: bool = False
    footnotes: tuple[str, ...] = ()


def _row(trade: Trade) -> dict[str, Any]:
    quantity = Decimal(trade.shares)
    cost = None if trade.price is None else Decimal(trade.price)
    filed = trade.filed
    row: dict[str, Any] = dict.fromkeys(INSIDER_SCHEMA.names)
    row.update(
        ISSUER,
        event_id=f"{trade.accession}:001",
        accession=trade.accession,
        line=1,
        form_type="4",
        filing_date=filed,
        accepted_at=datetime(filed.year, filed.month, filed.day, 21, tzinfo=UTC),
        period_of_report=filed,
        owner_cik=owner_cik(trade.owner),
        owner_name=trade.owner,
        other_owners=[],
        is_director=trade.owner.startswith("Example Director"),
        is_officer=trade.owner.startswith("Example Officer"),
        is_ten_percent_owner=False,
        is_other=False,
        is_derivative=trade.derivative,
        security_title="Synthetic Common Stock",
        transaction_date=filed,
        code=trade.code,
        category=trade.category,
        is_open_market=trade.code in {"P", "S"},
        acquired_disposed="A" if trade.code in {"P", "A", "M"} else "D",
        shares=quantity,
        price=cost,
        notional_usd=quantity * cost if cost else None,
        post_shares=Decimal("100000"),
        ownership="D",
        plan_10b5_1=trade.plan,
        footnotes=list(trade.footnotes),
        raw_path=f"4/synthetic_0000000001/{trade.accession}/doc4.xml",
        source_sha256="0" * 64,
        parser_version="insiders-1",
        ingested_at=INGESTED,
    )
    return row


def owner_cik(owner: str) -> str:
    return {"Example Director A": "0000000011", "Example Officer B": "0000000012"}.get(
        owner, "0000000013"
    )


def rows() -> list[dict[str, Any]]:
    note = "Synthetic footnote: sold under a synthetic trading plan."
    trades = (
        Trade(
            "0000000001-26-000101",
            date(2026, 10, 12),
            "Example Director A",
            "S",
            "open_market_sale",
            "1000",
            "200.00",
            plan=True,
            footnotes=(note,),
        ),
        Trade(
            "0000000001-26-000102",
            date(2026, 10, 13),
            "Example Director C",
            "S",
            "open_market_sale",
            "500",
            "201.00",
        ),
        Trade(
            "0000000001-26-000103",
            date(2026, 10, 14),
            "Example Officer B",
            "P",
            "open_market_purchase",
            "300",
            "195.50",
            plan=False,
        ),
        Trade(
            "0000000001-26-000104",
            date(2026, 10, 15),
            "Example Officer B",
            "A",
            "grant_or_award",
            "5000",
            "0",
        ),
        Trade(
            "0000000001-26-000105",
            date(2026, 10, 16),
            "Example Officer B",
            "F",
            "tax_withholding",
            "800",
            "199.00",
        ),
        Trade(
            "0000000001-26-000106",
            date(2026, 10, 16),
            "Example Officer B",
            "M",
            "option_exercise",
            "2000",
            "150.00",
            derivative=True,
        ),
    )
    return [_row(trade) for trade in trades]


def main() -> None:
    shutil.rmtree(PARQUET_ROOT / INSIDER_DATASET, ignore_errors=True)
    shutil.rmtree(PARQUET_ROOT / "_manifests" / INSIDER_DATASET, ignore_errors=True)
    InsiderParquetPublisher(PARQUET_ROOT).publish(rows())


if __name__ == "__main__":
    main()

"""Rebuild the filing_section part of `tests/fixtures/news`. Everything here is invented.

Only the two filing_section directories are replaced; the rest of the fixture is left as it is. The
issuer is a ticker the synthetic lake already uses, the text is made up, and every accession and
path is fictional.
"""

from __future__ import annotations

import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, NamedTuple

from stram_data.news.filing_section_lake import (
    SECTION_DATASET,
    SECTION_SCHEMA,
    SectionParquetPublisher,
)

PARQUET_ROOT = Path(__file__).parents[1] / "fixtures/news/parquet"
INGESTED = datetime(2026, 10, 30, 9, tzinfo=UTC)
ISSUER = {"cik": "0000000001", "ticker": "AAPL", "company_name": "Synthetic Issuer Inc"}
RISK = "Synthetic risk text: demand may change, suppliers may fail, and rules may shift. " * 120
DISCUSSION = "Synthetic discussion text: revenue moved and costs moved, as they do. " * 30

ANNUAL = "0000000001-26-000201"
QUARTERLY = "0000000001-26-000202"


class Section(NamedTuple):
    """One invented Item; `_row` fills in the rest of a stored row."""

    accession: str
    form: str
    filed: date
    part: str
    item: str
    title: str
    ordinal: int
    text: str
    flags: tuple[str, ...] = ()


def _row(section: Section) -> dict[str, Any]:
    accession, form, filed, part, item, title, ordinal, text, flags = section
    url = f"https://www.sec.gov/Archives/edgar/data/1/{accession.replace('-', '')}/synthetic.htm"
    row: dict[str, Any] = dict.fromkeys(SECTION_SCHEMA.names)
    row.update(
        ISSUER,
        event_id=f"{accession}:{part or '-'}:{item}",
        accession=accession,
        form=form,
        filing_date=filed,
        accepted_at=datetime(filed.year, filed.month, filed.day, 21, tzinfo=UTC),
        part=part,
        item=item,
        title=title,
        ordinal=ordinal,
        text=text,
        char_count=len(text),
        token_estimate=len(text) // 4,
        quality_flags=list(flags),
        source_document="synthetic.htm",
        source_url=url,
        raw_path=f"{form}/synthetic_0000000001/{accession}/synthetic.htm",
        source_sha256="0" * 64,
        parser_version="sections-1",
        ingested_at=INGESTED,
    )
    return row


def rows() -> list[dict[str, Any]]:
    filed, quarter = date(2026, 10, 29), date(2026, 10, 28)
    sections = (
        Section(ANNUAL, "10-K", filed, "", "1", "Business", 1, DISCUSSION),
        Section(ANNUAL, "10-K", filed, "", "1A", "Risk Factors", 2, RISK),
        Section(ANNUAL, "10-K", filed, "", "7", "Management's Discussion", 3, DISCUSSION),
        Section(
            ANNUAL,
            "10-K",
            filed,
            "",
            "8",
            "Financial Statements",
            4,
            "See the statements.",
            ("numbers_in_financial_facts",),
        ),
        Section(
            ANNUAL,
            "10-K",
            filed,
            "",
            "10",
            "Directors",
            5,
            "Incorporated by reference.",
            ("incorporated_by_reference",),
        ),
        Section(ANNUAL, "10-K", filed, "", "7A", "Market Risk", 6, "", ("not_found",)),
        Section(QUARTERLY, "10-Q", quarter, "I", "2", "Management's Discussion", 1, DISCUSSION),
        Section(
            QUARTERLY,
            "10-Q",
            quarter,
            "II",
            "1A",
            "Risk Factors",
            2,
            "There were no material changes to our risk factors.",
        ),
    )
    return [_row(section) for section in sections]


def main() -> None:
    built = rows()  # build first: a failure must not leave the fixture deleted
    shutil.rmtree(PARQUET_ROOT / SECTION_DATASET, ignore_errors=True)
    shutil.rmtree(PARQUET_ROOT / "_manifests" / SECTION_DATASET, ignore_errors=True)
    SectionParquetPublisher(PARQUET_ROOT).publish(built)


if __name__ == "__main__":
    main()

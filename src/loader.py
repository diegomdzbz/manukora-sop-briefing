"""Load and validate the sales dataset.

Validation is deliberately strict. A briefing that silently reports on malformed data is
worse than one that refuses to run: the executive cannot tell the difference, and the wrong
reorder gets placed. Every failure here is loud and names the row.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from . import config


class DataValidationError(ValueError):
    """Raised when the dataset does not match what the engine requires."""


REQUIRED_COLUMNS = (
    "SKU",
    *(f"Shopify_{m}" for m in config.MONTH_COLUMNS),
    *(f"Amazon_{m}" for m in config.MONTH_COLUMNS),
    "Stock_On_Hand",
    "Units_On_Order",
    "Order_Arrival_Months",
    "Target_Months_Cover",
    "Retail_Price_USD",
)


@dataclass(frozen=True)
class SkuRecord:
    """One SKU's raw position, straight from the dataset with nothing derived."""

    sku: str
    shopify: dict[str, int]
    amazon: dict[str, int]
    stock_on_hand: int
    units_on_order: int
    order_arrival_months: int
    target_months_cover: int
    retail_price_usd: float

    @property
    def units(self) -> dict[str, int]:
        """Pooled monthly demand.

        The brief states that Shopify and Amazon draw from one inventory position, so
        demand is the sum of both channels. The split is kept above for channel analysis,
        but every cover and reorder calculation runs on this pooled figure.
        """
        return {m: self.shopify[m] + self.amazon[m] for m in config.MONTH_COLUMNS}

    @property
    def has_order_placed(self) -> bool:
        """Whether a confirmed inbound shipment exists.

        The brief is explicit that `Order_Arrival_Months = 0` means no order is currently
        placed — it does *not* mean the order arrives immediately. Reading it the other way
        would treat SKUs with no coverage plan as if stock were landing today, which is the
        exact inverse of the truth and would hide every genuine reorder.
        """
        return self.units_on_order > 0 and self.order_arrival_months > 0


def load(path: str | Path) -> list[SkuRecord]:
    """Read the dataset, validating structure, types and business expectations."""
    path = Path(path)
    if not path.exists():
        raise DataValidationError(f"Dataset not found: {path}")

    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    if not rows:
        raise DataValidationError(f"Dataset is empty: {path}")

    missing = [c for c in REQUIRED_COLUMNS if c not in rows[0]]
    if missing:
        raise DataValidationError(f"Dataset is missing columns: {', '.join(missing)}")

    records = [_parse_row(row, line_no=i + 2) for i, row in enumerate(rows)]

    duplicates = {r.sku for r in records if [x.sku for x in records].count(r.sku) > 1}
    if duplicates:
        raise DataValidationError(f"Duplicate SKUs in dataset: {', '.join(sorted(duplicates))}")

    _assert_targets_match_brief(records)
    return records


def _parse_row(row: dict[str, str], line_no: int) -> SkuRecord:
    sku = (row["SKU"] or "").strip()
    if not sku:
        raise DataValidationError(f"Line {line_no}: SKU is blank")

    def as_int(column: str) -> int:
        raw = (row[column] or "").strip()
        try:
            value = int(raw)
        except ValueError:
            raise DataValidationError(
                f"Line {line_no} ({sku}): {column} is not a whole number: {raw!r}"
            ) from None
        if value < 0:
            raise DataValidationError(f"Line {line_no} ({sku}): {column} is negative: {value}")
        return value

    def as_float(column: str) -> float:
        raw = (row[column] or "").strip()
        try:
            value = float(raw)
        except ValueError:
            raise DataValidationError(
                f"Line {line_no} ({sku}): {column} is not a number: {raw!r}"
            ) from None
        if value <= 0:
            raise DataValidationError(f"Line {line_no} ({sku}): {column} must be positive: {value}")
        return value

    shopify = {m: as_int(f"Shopify_{m}") for m in config.MONTH_COLUMNS}
    amazon = {m: as_int(f"Amazon_{m}") for m in config.MONTH_COLUMNS}

    pooled_current = shopify[config.CURRENT_MONTH] + amazon[config.CURRENT_MONTH]
    if pooled_current == 0:
        raise DataValidationError(
            f"Line {line_no} ({sku}): no units sold in {config.MONTH_LABELS[config.CURRENT_MONTH]}; "
            "cover and revenue opportunity cannot be derived from a zero baseline"
        )

    target = as_int("Target_Months_Cover")
    if target == 0:
        raise DataValidationError(f"Line {line_no} ({sku}): Target_Months_Cover must be at least 1")

    return SkuRecord(
        sku=sku,
        shopify=shopify,
        amazon=amazon,
        stock_on_hand=as_int("Stock_On_Hand"),
        units_on_order=as_int("Units_On_Order"),
        order_arrival_months=as_int("Order_Arrival_Months"),
        target_months_cover=target,
        retail_price_usd=as_float("Retail_Price_USD"),
    )


def _assert_targets_match_brief(records: list[SkuRecord]) -> None:
    """Cross-check the dataset's cover targets against the rules declared in config.

    The brief states MGO 1700+ 100g carries a three-month target. The CSV happens to agree.
    Checking rather than trusting means that if a future dataset quietly changes that
    column, the run fails instead of producing a plausible wrong answer.
    """
    for record in records:
        expected = config.expected_target_cover(record.sku)
        if record.target_months_cover != expected:
            raise DataValidationError(
                f"{record.sku}: dataset says target cover is {record.target_months_cover} months "
                f"but the brief requires {expected}. Reconcile config.py with the data before "
                "running."
            )

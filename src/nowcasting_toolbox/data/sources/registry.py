"""Dataset registry: maps dataset IDs to metadata.

Provides a single source of truth for:
- Dataset ID (used in OpenDOSM API calls)
- Human-readable name
- Frequency (monthly / quarterly / daily)
- Transformation code (0=level, 1=MoM, 2=diff, 3=QoQ ann, 4=YoY)
- Group / category (for block factors)
- Publication delay (days)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Frequency(str, Enum):
    DAILY = "daily"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"


class TransformCode(int, Enum):
    LEVEL = 0
    MOM = 1   # month-on-month growth (dlog)
    DIFF = 2  # first difference
    QOQ_ANN = 3  # annualised quarter-on-quarter growth (dlog * 4)
    YOY = 4   # year-on-year growth (dlog)


@dataclass
class DatasetMeta:
    """Metadata for a single dataset."""

    id: str
    name: str
    frequency: Frequency
    transform: TransformCode = TransformCode.MOM
    group: str = "other"
    pub_lag_days: int = 30  # typical publication delay after period end
    is_target: bool = False  # True if this is the target (GDP)
    source: str = "opendosm"  # "opendosm" | "bnm"
    description: str = ""

    # For BNM-sourced data
    bnm_path: Optional[str] = None


MALAYSIA_REGISTRY: list[DatasetMeta] = [
    # ---------- Target ----------
    DatasetMeta(
        id="gdp_qtr_real",
        name="GDP (Real, QoQ Annualised)",
        frequency=Frequency.QUARTERLY,
        transform=TransformCode.QOQ_ANN,
        group="national_accounts",
        pub_lag_days=45,
        is_target=True,
        description="Quarterly real GDP at constant 2015 prices (seasonally adjusted available via gdp_qtr_real_sa)",
    ),
    # ---------- Prices ----------
    DatasetMeta(
        id="cpi_headline",
        name="CPI Headline",
        frequency=Frequency.MONTHLY,
        transform=TransformCode.MOM,
        group="prices",
        pub_lag_days=19,
        description="Monthly consumer price index, all divisions",
    ),
    DatasetMeta(
        id="cpi_core",
        name="CPI Core",
        frequency=Frequency.MONTHLY,
        transform=TransformCode.MOM,
        group="prices",
        pub_lag_days=19,
        description="Monthly core CPI (excl. volatile items)",
    ),
    DatasetMeta(
        id="ppi",
        name="Producer Price Index",
        frequency=Frequency.MONTHLY,
        transform=TransformCode.MOM,
        group="prices",
        pub_lag_days=25,
        description="Monthly headline PPI",
    ),
    # ---------- Labour ----------
    DatasetMeta(
        id="lfs_month",
        name="Labour Force (Monthly)",
        frequency=Frequency.MONTHLY,
        transform=TransformCode.DIFF,
        group="labour",
        pub_lag_days=12,
        description="Monthly principal labour force statistics",
    ),
    DatasetMeta(
        id="lfs_month_sa",
        name="Labour Force SA (Monthly)",
        frequency=Frequency.MONTHLY,
        transform=TransformCode.DIFF,
        group="labour",
        pub_lag_days=12,
        description="Seasonally adjusted monthly labour force statistics",
    ),
    # ---------- Trade ----------
    DatasetMeta(
        id="bop_balance",
        name="Balance of Payments",
        frequency=Frequency.QUARTERLY,
        transform=TransformCode.DIFF,
        group="external",
        pub_lag_days=45,
        description="Quarterly balance of payments components",
    ),
    # ---------- Financial (BNM) ----------
    DatasetMeta(
        id="exchange_rate_usd",
        name="MYR/USD Exchange Rate (middle)",
        frequency=Frequency.DAILY,
        transform=TransformCode.MOM,  # dlog for % change
        group="financial",
        pub_lag_days=1,
        source="bnm",
        bnm_path="/public/exchange-rate",
        description="Daily MYR per USD middle exchange rate from BNM",
    ),
    DatasetMeta(
        id="interbank_overnight",
        name="Overnight Interbank Rate",
        frequency=Frequency.DAILY,
        transform=TransformCode.LEVEL,
        group="financial",
        pub_lag_days=0,
        source="bnm",
        bnm_path="/public/interest-rate",
        description="Daily overnight interbank offered rate (overall)",
    ),
    DatasetMeta(
        id="opr",
        name="Overnight Policy Rate (BNM)",
        frequency=Frequency.DAILY,
        transform=TransformCode.LEVEL,
        group="financial",
        pub_lag_days=0,
        source="bnm",
        bnm_path="/public/opr",
        description="BNM Overnight Policy Rate",
    ),
]


def get_registry(source: str = "all") -> list[DatasetMeta]:
    """Return the full dataset registry, optionally filtered by source."""
    if source == "all":
        return MALAYSIA_REGISTRY
    return [m for m in MALAYSIA_REGISTRY if m.source == source]


def get_meta(dataset_id: str) -> Optional[DatasetMeta]:
    """Look up metadata for a dataset by ID."""
    for m in MALAYSIA_REGISTRY:
        if m.id == dataset_id:
            return m
    return None


def get_target() -> DatasetMeta:
    """Return the target variable metadata (GDP)."""
    for m in MALAYSIA_REGISTRY:
        if m.is_target:
            return m
    raise ValueError("No target variable defined in registry")


def get_monthly_ids() -> list[str]:
    """Return IDs of all monthly non-target datasets."""
    return [m.id for m in MALAYSIA_REGISTRY if m.frequency == Frequency.MONTHLY and not m.is_target]


def get_daily_financial_ids() -> list[str]:
    """Return IDs of daily financial datasets (BNM-sourced)."""
    return [m.id for m in MALAYSIA_REGISTRY if m.frequency == Frequency.DAILY]

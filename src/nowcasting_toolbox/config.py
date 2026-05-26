"""Pydantic configuration models for all toolbox parameters.

Mirrors the MATLAB Par, Country, Eval, Loop, MAE structs from Nowcast_Main_vF.m.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

import numpy as np
from pydantic import BaseModel, Field, field_validator, model_validator


class ModelType(str, Enum):
    DFM = "DFM"
    BEQ = "BEQ"
    BVAR = "BVAR"


class CovidCorrection(int, Enum):
    NONE = 0
    DUMMY_JUNE_SEPT = 1
    SET_NAN = 2
    OUTLIER_NAN = 3
    DUMMY_MARCH_JUNE = 4


class InterpolationType(int, Enum):
    BVAR_ALL = 901
    BVAR_SELECTED = 902
    UNIVARIATE_BVAR = 903
    ALL_THREE = 904


# ---------------------------------------------------------------------------
# Per-model parameter blocks
# ---------------------------------------------------------------------------


class DFMParams(BaseModel):
    """DFM-specific parameters (Banbura & Modugno, 2014)."""
    p: int = Field(default=4, ge=1, le=5, description="Number of lags for factor VAR")
    r: int = Field(default=5, ge=1, description="Number of factors")
    idio: int = Field(default=1, ge=0, le=1, description="Idiosyncratic specification: 0=iid, 1=AR(1)")
    thresh: float = Field(default=1e-4, gt=0, description="Convergence threshold for EM")
    max_iter: int = Field(default=100, ge=1, description="Max EM iterations")
    block_factors: int = Field(default=0, ge=0, le=1, description="Include block factors")


class BVARParams(BaseModel):
    """BVAR-specific parameters (Cimadomo et al., 2022)."""
    bvar_lags: int = Field(default=5, ge=1, le=12, description="Number of lags")
    bvar_thresh: float = Field(default=1e-6, gt=0, description="Optimization convergence threshold")
    bvar_max_iter: int = Field(default=200, ge=1, description="Max optimization iterations")


class BEQParams(BaseModel):
    """Bridge Equation parameters (Banbura et al., 2023)."""
    lagM: int = Field(default=1, ge=0, description="Lags for monthly regressors (quarterly terms)")
    lagQ: int = Field(default=1, ge=0, description="Lags for quarterly regressors (quarterly terms)")
    lagY: int = Field(default=1, ge=0, description="Lags for endogenous variable (quarterly terms)")
    type: InterpolationType = Field(default=InterpolationType.ALL_THREE, description="Interpolation method")
    Dum: list[tuple[int, int]] = Field(default_factory=list, description="Dummy dates (year, month)")


# ---------------------------------------------------------------------------
# Evaluation parameters
# ---------------------------------------------------------------------------


class MAEPeriodParams(BaseModel):
    """MAE / FDA values for one forecast horizon period."""
    mae_1st: float = Field(default=0.15, ge=0)
    mae_2nd: float = Field(default=0.15, ge=0)
    mae_3rd: float = Field(default=0.15, ge=0)
    fda_1st: float = Field(default=0.88, ge=0, le=1)
    fda_2nd: float = Field(default=0.88, ge=0, le=1)
    fda_3rd: float = Field(default=0.88, ge=0, le=1)


class MAEParams(BaseModel):
    """User-specified MAE / FDA values (used when do_mae=0)."""
    Bac: MAEPeriodParams = Field(default_factory=MAEPeriodParams)
    Now: MAEPeriodParams = Field(default_factory=MAEPeriodParams)
    For: MAEPeriodParams = Field(default_factory=MAEPeriodParams)


class EvalParams(BaseModel):
    """Out-of-sample evaluation parameters."""
    data_update_lastyear: int = Field(default=2023, ge=2000)
    data_update_lastmonth: int = Field(default=10, ge=1, le=12)
    eval_startyear: int = Field(default=2020, ge=2000)
    eval_startmonth: int = Field(default=10, ge=1, le=12)
    eval_endyear: int = Field(default=2022, ge=2000)
    eval_endmonth: int = Field(default=10, ge=1, le=12)
    gdp_rel: int = Field(default=2, ge=1, le=3, description="Month of quarter GDP is available")

    @model_validator(mode="after")
    def check_dates(self) -> "EvalParams":
        if (self.eval_startyear, self.eval_startmonth) >= (self.eval_endyear, self.eval_endmonth):
            raise ValueError("eval_start must be before eval_end")
        return self


class LoopParams(BaseModel):
    """Automated loop over random models."""
    n_iter: int = Field(default=10, ge=1, description="Number of random models")
    name_loop: str = Field(default="b1")
    min_startyear: int = Field(default=2008, ge=2000)
    max_startyear: int = Field(default=2014, ge=2000)
    startmonth: int = Field(default=1, ge=1, le=12)
    min_var: int = Field(default=5, ge=1)
    max_var: int = Field(default=10, ge=1)
    min_p: int = Field(default=1, ge=1)
    max_p: int = Field(default=4, ge=1)
    min_r: int = Field(default=2, ge=1)
    max_r: int = Field(default=6, ge=1)
    min_lagM: int = Field(default=1, ge=0)
    max_lagM: int = Field(default=4, ge=0)
    min_lagQ: int = Field(default=1, ge=0)
    max_lagQ: int = Field(default=4, ge=0)
    min_lagY: int = Field(default=1, ge=0)
    max_lagY: int = Field(default=2, ge=0)
    min_bvar_lags: int = Field(default=2, ge=1)
    max_bvar_lags: int = Field(default=4, ge=1)
    do_random: int = Field(default=1, ge=0, le=1)
    list_name: str = Field(default="Eval_list_DFM.xlsx")
    name_customloop: str = Field(default="customloop")
    alter_covid: int = Field(default=1, ge=0, le=1)


# ---------------------------------------------------------------------------
# Country / dataset configuration
# ---------------------------------------------------------------------------


class CountryConfig(BaseModel):
    """Country-specific configuration."""
    name: str = Field(default="malaysia", description="Country identifier for data files")
    model: ModelType = Field(default=ModelType.DFM, description="Primary model type")

    @property
    def data_file(self) -> str:
        return f"data_{self.name}"

    @property
    def output_dir(self) -> Path:
        return Path(f"output/{self.name}")

    @property
    def eval_dir(self) -> Path:
        return Path(f"eval/{self.name}")


# ---------------------------------------------------------------------------
# Master configuration
# ---------------------------------------------------------------------------


class ToolboxConfig(BaseModel):
    """Master configuration combining all settings (mirrors Nowcast_Main_vF.m)."""

    # Operating mode
    do_eval: int = Field(default=0, ge=0, le=1, description="0=nowcast, 1=evaluation")
    do_loop: int = Field(default=0, ge=0, le=2, description="0=single, 1=random, 2=custom")
    do_range: int = Field(default=0, ge=0, le=1, description="Compute range of nowcasts")
    do_mae: int = Field(default=0, ge=0, le=1, description="Compute MAE from data (0=user-specified)")
    do_subset: int = Field(default=0, ge=0, le=1, description="Use subset of variables")
    do_covid: CovidCorrection = Field(default=CovidCorrection.NONE)

    # Forecast horizon (months ahead)
    m: int = Field(default=6, ge=1, le=24)

    # Estimation start
    startyear: int = Field(default=2010, ge=2000)
    startmonth: int = Field(default=1, ge=1, le=12)

    # Sub-models
    country: CountryConfig = Field(default_factory=CountryConfig)
    dfm: DFMParams = Field(default_factory=DFMParams)
    bvar: BVARParams = Field(default_factory=BVARParams)
    beq: BEQParams = Field(default_factory=BEQParams)
    mae: MAEParams = Field(default_factory=MAEParams)
    eval: EvalParams = Field(default_factory=EvalParams)
    loop: LoopParams = Field(default_factory=LoopParams)

    # Variable subset (used when do_subset=1)
    var_keep: list[int] = Field(default_factory=list)

    # Data directory
    data_dir: Path = Field(default=Path("data"))
    cache_ttl_hours: int = Field(default=6, ge=0, description="Cache TTL in hours (0=forever)")

    @model_validator(mode="after")
    def enforce_loop_eval(self) -> "ToolboxConfig":
        if self.do_loop > 0:
            self.do_eval = 1
        return self


# ---------------------------------------------------------------------------
# Helper: load config from dict / JSON
# ---------------------------------------------------------------------------


def load_config(data: dict | None = None, **overrides) -> ToolboxConfig:
    """Create a ToolboxConfig from a dict with optional overrides.

    Parameters
    ----------
    data : dict, optional
        Base configuration dictionary.
    **overrides
        Key-value pairs to override.

    Returns
    -------
    ToolboxConfig
    """
    merged = {}
    if data is not None:
        merged.update(data)
    merged.update(overrides)
    return ToolboxConfig(**merged)

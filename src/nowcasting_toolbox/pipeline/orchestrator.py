"""Pipeline orchestrator: fetch → transform → nowcast → evaluate → export."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from nowcasting_toolbox.config import ToolboxConfig, ModelType
from nowcasting_toolbox.data.loader import load_data, LoadedData

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Container for a full pipeline run."""
    config: ToolboxConfig
    data: LoadedData
    dfm_result: Optional[object] = None
    bvar_result: Optional[object] = None
    beq_result: Optional[object] = None
    leaderboard: Optional[pd.DataFrame] = None


class Pipeline:
    """Orchestrates the full nowcasting workflow."""

    def __init__(self, config: ToolboxConfig) -> None:
        self.config = config
        self._data: Optional[LoadedData] = None

    def fetch(self, source: str = "api") -> LoadedData:
        """Fetch data from the configured source."""
        logger.info("Fetching data (source=%s)...", source)
        self._data = load_data(self.config, source=source)
        return self._data

    def nowcast(self) -> PipelineResult:
        """Run all three models and return consolidated results."""
        if self._data is None:
            raise RuntimeError("No data. Call .fetch() first.")

        data = self._data
        result = PipelineResult(config=self.config, data=data)

        # DFM
        from nowcasting_toolbox.dfm import DFM
        from nowcasting_toolbox.config import DFMParams
        logger.info("Running DFM...")
        dfm = DFM(DFMParams(
            r=self.config.dfm.r,
            p=self.config.dfm.p,
            max_iter=self.config.dfm.max_iter,
            thresh=self.config.dfm.thresh,
            idio=self.config.dfm.idio,
            block_factors=self.config.dfm.block_factors,
        ))
        result.dfm_result = dfm.fit(data.xest)

        # BVAR
        from nowcasting_toolbox.bvar import BVAR
        from nowcasting_toolbox.config import BVARParams
        logger.info("Running BVAR...")
        bvar = BVAR(BVARParams(
            bvar_lags=self.config.bvar.bvar_lags,
            bvar_thresh=self.config.bvar.bvar_thresh,
            bvar_max_iter=self.config.bvar.bvar_max_iter,
        ))
        result.bvar_result = bvar.fit(data.xest, data.datet)

        # BEQ
        from nowcasting_toolbox.beq import BEQ
        from nowcasting_toolbox.config import BEQParams
        logger.info("Running BEQ...")
        beq = BEQ(BEQParams(
            lagM=self.config.beq.lagM,
            lagQ=self.config.beq.lagQ,
            lagY=self.config.beq.lagY,
            type=self.config.beq.type,
        ))
        result.beq_result = beq.fit(data.xest, data.datet, data.nameseries)

        logger.info("Pipeline complete.")
        return result

    def evaluate(self) -> pd.DataFrame:
        """Run backtest evaluation and return leaderboard."""
        if self._data is None:
            raise RuntimeError("No data. Call .fetch() first.")

        from nowcasting_toolbox.eval.backtest import run_backtest
        from nowcasting_toolbox.pipeline.leaderboard import build_leaderboard

        logger.info("Running backtest...")
        bt_df = run_backtest(self.config, self._data.xest, self._data.datet)
        leaderboard_df = build_leaderboard(bt_df)
        return leaderboard_df

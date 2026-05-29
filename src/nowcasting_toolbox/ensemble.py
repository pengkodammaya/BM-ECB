"""Ensemble model: combines predictions from multiple nowcasting models.

Supports:
- Simple median
- Inverse MAE² weighting
- User-specified weights
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
from numpy.typing import NDArray

from nowcasting_toolbox.eval.metrics import compute_mae

logger = logging.getLogger(__name__)
FloatArray = NDArray[np.float64]


@dataclass
class EnsembleResult:
    """Container for ensemble prediction results."""
    prediction: float
    weights: dict[str, float]
    model_predictions: dict[str, float]
    method: str


class Ensemble:
    """Ensemble combiner for nowcasting models.

    Parameters
    ----------
    method : str
        Combination method:
        - "median": simple median of predictions
        - "mean": simple mean of predictions
        - "inverse_mae": inverse MAE² weighting (requires history)
    """

    def __init__(self, method: str = "median") -> None:
        if method not in ("median", "mean", "inverse_mae"):
            raise ValueError(f"Unknown method: {method}")
        self.method = method
        self._history: dict[str, list[float]] = {}
        self._actuals: list[float] = []

    def predict(
        self,
        model_predictions: dict[str, Optional[float]],
    ) -> EnsembleResult:
        """Compute ensemble prediction.

        Parameters
        ----------
        model_predictions : dict
            {model_name: prediction} for each model.
            None values are excluded.

        Returns
        -------
        EnsembleResult
        """
        # Filter out None predictions
        valid = {k: v for k, v in model_predictions.items() if v is not None}

        if not valid:
            return EnsembleResult(
                prediction=np.nan,
                weights={},
                model_predictions=model_predictions,
                method=self.method,
            )

        if self.method == "median":
            pred = float(np.median(list(valid.values())))
            weights = {k: 1.0 / len(valid) for k in valid}
        elif self.method == "mean":
            pred = float(np.mean(list(valid.values())))
            weights = {k: 1.0 / len(valid) for k in valid}
        elif self.method == "inverse_mae":
            pred, weights = self._inverse_mae_predict(valid)
        else:
            raise ValueError(f"Unknown method: {self.method}")

        return EnsembleResult(
            prediction=pred,
            weights=weights,
            model_predictions=model_predictions,
            method=self.method,
        )

    def update_history(
        self,
        model_predictions: dict[str, Optional[float]],
        actual: float,
    ) -> None:
        """Update history for inverse-MAE weighting.

        Parameters
        ----------
        model_predictions : dict
            {model_name: prediction} for each model.
        actual : float
            Actual GDP value.
        """
        self._actuals.append(actual)
        for model, pred in model_predictions.items():
            if model not in self._history:
                self._history[model] = []
            self._history[model].append(pred if pred is not None else np.nan)

    def _inverse_mae_predict(
        self,
        valid: dict[str, float],
    ) -> tuple[float, dict[str, float]]:
        """Inverse MAE² weighted prediction."""
        if len(self._actuals) < 3:
            # Not enough history, fall back to median
            pred = float(np.median(list(valid.values())))
            weights = {k: 1.0 / len(valid) for k in valid}
            return pred, weights

        # Compute MAE for each model
        mae_scores = {}
        for model in valid:
            if model in self._history and len(self._history[model]) >= len(self._actuals):
                hist = np.array(self._history[model][-len(self._actuals):])
                actuals = np.array(self._actuals)
                mask = ~np.isnan(hist)
                if np.sum(mask) >= 3:
                    mae_scores[model] = compute_mae(actuals[mask], hist[mask])

        if not mae_scores:
            pred = float(np.median(list(valid.values())))
            weights = {k: 1.0 / len(valid) for k in valid}
            return pred, weights

        # Inverse MAE² weighting
        inv_mae2 = {k: 1.0 / (v ** 2 + 0.01) for k, v in mae_scores.items() if k in valid}
        total = sum(inv_mae2.values())
        weights = {k: v / total for k, v in inv_mae2.items()}

        pred = sum(valid[k] * weights.get(k, 0) for k in valid if k in weights)

        return pred, weights

"""Ensemble model: combines predictions from multiple nowcasting models.

Supports:
- Simple median
- Simple mean
- Inverse MAE² weighting
- Inverse MSE weighting
- Direction vote (majority sign agreement)
- Trimmed mean (remove extremes)
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
        - "inverse_mse": inverse MSE weighting (requires history)
        - "direction_vote": majority direction, then mean of sign-concordant predictions
        - "trimmed_mean": remove min/max predictions, then mean
    """

    def __init__(self, method: str = "median") -> None:
        valid_methods = ("median", "mean", "inverse_mae", "inverse_mse",
                         "direction_vote", "trimmed_mean")
        if method not in valid_methods:
            raise ValueError(f"Unknown method: {method}. Valid: {valid_methods}")
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
            pred, weights = self._median_predict(valid)
        elif self.method == "mean":
            pred, weights = self._mean_predict(valid)
        elif self.method == "inverse_mae":
            pred, weights = self._inverse_mae_predict(valid)
        elif self.method == "inverse_mse":
            pred, weights = self._inverse_mse_predict(valid)
        elif self.method == "direction_vote":
            pred, weights = self._direction_vote_predict(valid)
        elif self.method == "trimmed_mean":
            pred, weights = self._trimmed_mean_predict(valid)
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
        """Update history for weighted ensemble methods.

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

    def _median_predict(self, valid: dict[str, float]) -> tuple[float, dict[str, float]]:
        """Simple median prediction."""
        pred = float(np.median(list(valid.values())))
        weights = {k: 1.0 / len(valid) for k in valid}
        return pred, weights

    def _mean_predict(self, valid: dict[str, float]) -> tuple[float, dict[str, float]]:
        """Simple mean prediction."""
        pred = float(np.mean(list(valid.values())))
        weights = {k: 1.0 / len(valid) for k in valid}
        return pred, weights

    def _inverse_mae_predict(
        self,
        valid: dict[str, float],
    ) -> tuple[float, dict[str, float]]:
        """Inverse MAE² weighted prediction."""
        if len(self._actuals) < 3:
            return self._median_predict(valid)

        mae_scores = {}
        for model in valid:
            if model in self._history and len(self._history[model]) >= len(self._actuals):
                hist = np.array(self._history[model][-len(self._actuals):])
                actuals = np.array(self._actuals)
                mask = ~np.isnan(hist)
                if np.sum(mask) >= 3:
                    mae_scores[model] = compute_mae(actuals[mask], hist[mask])

        if not mae_scores:
            return self._median_predict(valid)

        inv_mae2 = {k: 1.0 / (v ** 2 + 0.01) for k, v in mae_scores.items() if k in valid}
        total = sum(inv_mae2.values())
        weights = {k: v / total for k, v in inv_mae2.items()}
        pred = sum(valid[k] * weights.get(k, 0) for k in valid if k in weights)
        return pred, weights

    def _inverse_mse_predict(
        self,
        valid: dict[str, float],
    ) -> tuple[float, dict[str, float]]:
        """Inverse MSE weighted prediction (penalizes large errors more)."""
        if len(self._actuals) < 3:
            return self._median_predict(valid)

        mse_scores = {}
        for model in valid:
            if model in self._history and len(self._history[model]) >= len(self._actuals):
                hist = np.array(self._history[model][-len(self._actuals):])
                actuals = np.array(self._actuals)
                mask = ~np.isnan(hist)
                if np.sum(mask) >= 3:
                    errors = actuals[mask] - hist[mask]
                    mse_scores[model] = float(np.mean(errors ** 2))

        if not mse_scores:
            return self._median_predict(valid)

        inv_mse = {k: 1.0 / (v + 0.01) for k, v in mse_scores.items() if k in valid}
        total = sum(inv_mse.values())
        weights = {k: v / total for k, v in inv_mse.items()}
        pred = sum(valid[k] * weights.get(k, 0) for k in valid if k in weights)
        return pred, weights

    def _direction_vote_predict(
        self,
        valid: dict[str, float],
    ) -> tuple[float, dict[str, float]]:
        """Majority direction vote.

        Counts which direction (positive/negative) most models predict,
        then averages predictions that agree with the majority.
        """
        if len(valid) < 2:
            return self._median_predict(valid)

        # Count direction votes
        positive_votes = sum(1 for v in valid.values() if v > 0)
        negative_votes = sum(1 for v in valid.values() if v < 0)

        # Filter to majority direction
        if positive_votes >= negative_votes:
            concordant = {k: v for k, v in valid.items() if v > 0}
        else:
            concordant = {k: v for k, v in valid.items() if v < 0}

        # If no concordant predictions, fall back to median
        if not concordant:
            return self._median_predict(valid)

        # Average concordant predictions
        pred = float(np.mean(list(concordant.values())))
        weights = {k: (1.0 / len(concordant) if k in concordant else 0.0) for k in valid}
        return pred, weights

    def _trimmed_mean_predict(
        self,
        valid: dict[str, float],
    ) -> tuple[float, dict[str, float]]:
        """Trimmed mean: remove min and max, then average."""
        if len(valid) < 3:
            return self._mean_predict(valid)

        values = list(valid.values())
        names = list(valid.keys())

        # Find min and max indices
        min_idx = np.argmin(values)
        max_idx = np.argmax(values)

        # Remove min and max (if different)
        keep = [i for i in range(len(values)) if i != min_idx and i != max_idx]
        if not keep:
            return self._mean_predict(valid)

        trimmed_values = [values[i] for i in keep]
        trimmed_names = [names[i] for i in keep]

        pred = float(np.mean(trimmed_values))
        weights = {k: (1.0 / len(keep) if k in trimmed_names else 0.0) for k in valid}
        return pred, weights

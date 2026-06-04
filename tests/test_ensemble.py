"""Tests for Ensemble model."""
import numpy as np
import pytest
from nowcasting_toolbox.ensemble import Ensemble, EnsembleResult


class TestEnsemble:
    """Tests for the Ensemble combiner."""

    def test_median_prediction(self):
        """Median ensemble returns median of predictions."""
        ens = Ensemble(method="median")
        result = ens.predict({"dfm": 5.0, "bvar": 3.0, "beq": 4.0})

        assert isinstance(result, EnsembleResult)
        assert result.prediction == 4.0  # median of 3, 4, 5
        assert result.method == "median"

    def test_mean_prediction(self):
        """Mean ensemble returns mean of predictions."""
        ens = Ensemble(method="mean")
        result = ens.predict({"dfm": 6.0, "bvar": 3.0, "beq": 3.0})

        assert result.prediction == 4.0  # mean of 6, 3, 3
        assert result.method == "mean"

    def test_none_predictions_excluded(self):
        """None predictions are excluded from ensemble."""
        ens = Ensemble(method="median")
        result = ens.predict({"dfm": 5.0, "bvar": None, "beq": 3.0})

        assert result.prediction == 4.0  # median of 3, 5

    def test_all_none_returns_nan(self):
        """All None predictions returns NaN."""
        ens = Ensemble(method="median")
        result = ens.predict({"dfm": None, "bvar": None, "beq": None})

        assert np.isnan(result.prediction)

    def test_single_prediction(self):
        """Single prediction returns that value."""
        ens = Ensemble(method="median")
        result = ens.predict({"dfm": 5.0, "bvar": None, "beq": None})

        assert result.prediction == 5.0

    def test_weights_equal_for_median(self):
        """Median ensemble assigns equal weights."""
        ens = Ensemble(method="median")
        result = ens.predict({"dfm": 5.0, "bvar": 3.0, "beq": 4.0})

        assert result.weights["dfm"] == pytest.approx(1/3)
        assert result.weights["bvar"] == pytest.approx(1/3)
        assert result.weights["beq"] == pytest.approx(1/3)

    def test_invalid_method_raises(self):
        """Invalid method raises ValueError."""
        with pytest.raises(ValueError, match="Unknown method"):
            Ensemble(method="invalid")

    def test_inverse_mae_insufficient_history(self):
        """Inverse MAE falls back to median with insufficient history."""
        ens = Ensemble(method="inverse_mae")
        result = ens.predict({"dfm": 5.0, "bvar": 3.0, "beq": 4.0})

        # With no history, should fall back to median
        assert result.prediction == 4.0

    def test_update_history(self):
        """update_history stores predictions and actuals."""
        ens = Ensemble(method="inverse_mae")
        ens.update_history({"dfm": 5.0, "bvar": 3.0}, actual=4.0)
        ens.update_history({"dfm": 4.5, "bvar": 3.5}, actual=4.0)
        ens.update_history({"dfm": 4.0, "bvar": 4.0}, actual=4.0)

        assert len(ens._actuals) == 3
        assert ens._actuals == [4.0, 4.0, 4.0]

    def test_inverse_mae_with_history(self):
        """Inverse MAE uses history for weighting."""
        ens = Ensemble(method="inverse_mae")

        # Build history: dfm is always accurate, bvar is always off
        for _ in range(5):
            ens.update_history({"dfm": 5.0, "bvar": 10.0}, actual=5.0)

        result = ens.predict({"dfm": 5.0, "bvar": 10.0})

        # dfm should get higher weight (lower MAE)
        assert result.weights["dfm"] > result.weights["bvar"]
        # Prediction should be closer to dfm
        assert abs(result.prediction - 5.0) < abs(result.prediction - 10.0)

    def test_inverse_mse_with_history(self):
        """Inverse MSE uses history for weighting."""
        ens = Ensemble(method="inverse_mse")

        # Build history: dfm is accurate, bvar has large errors
        for _ in range(5):
            ens.update_history({"dfm": 5.1, "bvar": 8.0}, actual=5.0)

        result = ens.predict({"dfm": 5.0, "bvar": 8.0})

        # dfm should get higher weight
        assert result.weights["dfm"] > result.weights["bvar"]

    def test_direction_vote_positive(self):
        """Direction vote picks positive when majority agrees."""
        ens = Ensemble(method="direction_vote")
        result = ens.predict({"dfm": 5.0, "bvar": 3.0, "beq": -1.0})

        # 2 positive, 1 negative -> average positive predictions
        assert result.prediction > 0
        assert result.prediction == 4.0  # mean of 5.0 and 3.0

    def test_direction_vote_negative(self):
        """Direction vote picks negative when majority agrees."""
        ens = Ensemble(method="direction_vote")
        result = ens.predict({"dfm": -5.0, "bvar": -3.0, "beq": 1.0})

        # 2 negative, 1 positive -> average negative predictions
        assert result.prediction < 0
        assert result.prediction == -4.0  # mean of -5.0 and -3.0

    def test_direction_vote_all_positive(self):
        """Direction vote handles all positive."""
        ens = Ensemble(method="direction_vote")
        result = ens.predict({"dfm": 5.0, "bvar": 3.0, "beq": 1.0})

        assert result.prediction == 3.0  # mean of all

    def test_trimmed_mean(self):
        """Trimmed mean removes extremes."""
        ens = Ensemble(method="trimmed_mean")
        result = ens.predict({"dfm": 10.0, "bvar": 5.0, "beq": 1.0})

        # Removes 10.0 (max) and 1.0 (min), keeps 5.0
        assert result.prediction == 5.0

    def test_trimmed_mean_equal_values(self):
        """Trimmed mean handles equal values."""
        ens = Ensemble(method="trimmed_mean")
        result = ens.predict({"dfm": 5.0, "bvar": 5.0, "beq": 5.0})

        # All equal, removing min/max still gives 5.0
        assert result.prediction == 5.0

    def test_trimmed_mean_two_models(self):
        """Trimmed mean falls back to mean with 2 models."""
        ens = Ensemble(method="trimmed_mean")
        result = ens.predict({"dfm": 6.0, "bvar": 4.0})

        # Can't trim with only 2, falls back to mean
        assert result.prediction == 5.0

    def test_invalid_method_raises(self):
        """Invalid method raises ValueError."""
        with pytest.raises(ValueError, match="Unknown method"):
            Ensemble(method="invalid")

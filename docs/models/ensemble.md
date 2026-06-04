# Ensemble

## Overview

The Ensemble module combines predictions from multiple nowcasting models (DFM, BVAR, BEQ) to improve accuracy and directional consistency.

## Usage

```python
from nowcasting_toolbox.ensemble import Ensemble

# Create ensemble with method
ens = Ensemble(method="direction_vote")

# Combine predictions
result = ens.predict({
    "dfm": 5.0,
    "bvar": 3.0,
    "beq": 4.0,
})

print(result.prediction)  # Combined forecast
print(result.weights)     # Model weights
```

## Methods

### Median (default)

Simple median of predictions. Robust to outliers.

```python
Ensemble(method="median")
```

### Mean

Simple mean of predictions.

```python
Ensemble(method="mean")
```

### Inverse MAE

Weights models by inverse squared MAE from historical performance. Requires `update_history()` calls.

```python
ens = Ensemble(method="inverse_mae")
ens.update_history({"dfm": 5.0, "bvar": 3.0}, actual=4.5)
ens.update_history({"dfm": 4.8, "bvar": 3.5}, actual=4.5)
# ... more history
result = ens.predict({"dfm": 5.0, "bvar": 3.0})
```

### Inverse MSE

Similar to inverse MAE but penalizes large errors more.

```python
Ensemble(method="inverse_mse")
```

### Direction Vote

Picks the direction (positive/negative) that most models agree on, then averages predictions with that sign. Best for FDA optimization.

```python
Ensemble(method="direction_vote")
```

### Trimmed Mean

Removes min and max predictions, then averages. Reduces impact of extreme forecasts.

```python
Ensemble(method="trimmed_mean")
```

## Direction-Aware Hybrid

The daily pipeline uses a hybrid approach:
- **Models agree on direction:** Inverse MAE weighted average
- **Models disagree:** Direction vote (majority sign, then average concordant)

This improves FDA when models disagree on the sign of GDP growth.

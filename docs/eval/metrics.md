# Metrics

## Available Metrics

### MAE (Mean Absolute Error)

```python
from nowcasting_toolbox.eval.metrics import compute_mae
mae = compute_mae(actual, predicted)
```

### RMSE (Root Mean Squared Error)

```python
from nowcasting_toolbox.eval.metrics import compute_rmse
rmse = compute_rmse(actual, predicted)
```

### FDA (Forecast Directional Accuracy)

Percentage of correct sign predictions.

```python
from nowcasting_toolbox.eval.metrics import compute_fda
fda = compute_fda(actual, predicted)  # Returns 0.0-1.0
```

### Bias

Mean prediction error (positive = overestimate).

```python
from nowcasting_toolbox.eval.metrics import compute_bias
bias = compute_bias(actual, predicted)
```

### MASE (Mean Absolute Scaled Error)

MAE relative to naive seasonal forecast. <1 = better than naive.

```python
from nowcasting_toolbox.eval.metrics import compute_mase
mase = compute_mae(actual, predicted, seasonal_period=4)
```

### CRPS (Continuous Ranked Probability Score)

For probabilistic forecasts with confidence intervals.

```python
from nowcasting_toolbox.eval.metrics import compute_crps
crps = compute_crps(actual, lower_bound, upper_bound)
```

### Coverage

Percentage of actuals within confidence interval.

```python
from nowcasting_toolbox.eval.metrics import compute_coverage
cov = compute_coverage(actual, lower_bound, upper_bound)
```

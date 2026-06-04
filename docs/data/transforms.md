# Transforms

## Transform Codes

| Code | Name | Description |
|------|------|-------------|
| 0 | LEVEL | No transformation (raw values) |
| 1 | MOM | Month-on-month dlog growth |
| 2 | DIFF | First difference |
| 3 | QOQ_ANN | Annualised quarter-on-quarter growth |
| 4 | YOY | Year-on-year dlog growth |

## Usage

```python
from nowcasting_toolbox.data.transforms import transform_series

# Apply MoM transform to monthly data
y = transform_series(x, code=1, freq="monthly")

# Apply YoY transform to quarterly data
y = transform_series(x, code=4, freq="quarterly")
```

## Transform Details

### Level (code=0)
No transformation. Used for rates (unemployment, interest rates).

### MoM (code=1)
```
y[t] = log(x[t]) - log(x[t-1])
```
Used for prices, trade, indices.

### Diff (code=2)
```
y[t] = x[t] - x[t-1]
```
Used for stationary series.

### QoQ Annualised (code=3)
```
y[t] = (log(x[t]) - log(x[t-1])) * 4  # quarterly
y[t] = (log(x[t]) - log(x[t-1])) * 12 # monthly
```

### YoY (code=4)
```
y[t] = log(x[t]) - log(x[t-12])  # monthly
y[t] = log(x[t]) - log(x[t-4])   # quarterly
```

## NaN Handling

Transforms produce NaN for the initial lag period:
- MoM/Diff: 1 NaN at start
- YoY (monthly): 12 NaN at start
- YoY (quarterly): 4 NaN at start

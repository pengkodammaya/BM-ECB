# Troubleshooting Guide

Common issues and solutions for the Nowcasting Toolbox.

---

## Installation

### `ModuleNotFoundError: No module named 'nowcasting_toolbox'`

**Cause:** Package not installed in development mode.

```bash
uv pip install -e ".[dev]"
```

### `ModuleNotFoundError: No module named 'yfinance'`

**Cause:** yfinance is an optional dependency for global indicators.

```bash
uv pip install yfinance
# or
uv pip install -e ".[global]"
```

### `ModuleNotFoundError: No module named 'yaml'`

**Cause:** PyYAML is optional for YAML config support.

```bash
uv pip install pyyaml
# or
uv pip install -e ".[yaml]"
```

---

## API Errors

### `httpx.HTTPStatusError: 429 Too Many Requests`

**Cause:** OpenDOSM or BNM API rate limit exceeded.

**Solution:** The toolbox now retries automatically (3 attempts with exponential backoff). If it persists:
- Wait a few minutes and try again
- Check if the API is down: https://developer.data.gov.my/status

### `httpx.ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED]`

**Cause:** SSL certificate verification failed (common on Windows).

**Solution:**
```bash
# Option 1: Install certificates (macOS)
/Applications/Python\ 3.x/Install\ Certificates.command

# Option 2: Use certifi
pip install certifi
```

### `httpx.TimeoutException`

**Cause:** API request timed out (default 30s).

**Solution:** The toolbox retries automatically. For slow connections, you can increase timeout:
```python
from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient
client = OpenDOSMClient(timeout=60.0)
```

---

## FRED API

### `FRED API key not found`

**Cause:** No FRED API key configured.

**Solution:**
1. Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html
2. Set as environment variable:
   ```bash
   export FRED_API_KEY="your_key_here"  # Linux/Mac
   set FRED_API_KEY=your_key_here       # Windows CMD
   $env:FRED_API_KEY="your_key_here"    # PowerShell
   ```
3. Or create `.fred_key` file in project root (not recommended for production)

---

## Model Errors

### BVAR hangs or takes 30+ minutes

**Cause:** Ill-conditioned input data (near-constant or perfectly collinear columns).

**Solution:**
1. Check logs for `near_constant` or `collinear` warnings
2. Remove problematic indicators
3. Use fast mode without `datet` parameter:
   ```python
   bvar.fit(X)  # Fast (~30s)
   # vs
   bvar.fit(X, datet)  # Accurate (~10min)
   ```

### DFM: `LinAlgError: Singular matrix`

**Cause:** Too many NaN values or insufficient data.

**Solution:**
- Ensure at least 24 months of data
- Check for all-NaN columns
- Reduce number of factors (`r` parameter)

### BEQ returns NaN forecasts

**Cause:** Target column has insufficient observations.

**Solution:**
- Ensure GDP is observed at quarter-end months (3, 6, 9, 12)
- Check that at least 5 quarterly observations exist

---

## GitHub Actions

### `exit 143` (SIGTERM timeout)

**Cause:** Pipeline exceeded 60-minute timeout.

**Solution:**
- Check logs for the last checkpoint before timeout
- BVAR is usually the bottleneck — reduce `bvar_n_draws` or `bvar_max_iter`
- Use fast mode (no `datet` parameter)

### `No file changes detected`

**Cause:** Data hasn't changed since last run.

**Solution:** Normal behavior — an empty commit is created for tracking.

### Publish dashboard fails with 403

**Cause:** `SITE_DEPLOY_TOKEN` secret missing or expired PAT.

**Solution:**
1. Go to GitHub Settings → Developer Settings → Personal Access Tokens → Fine-grained tokens
2. Create token with `repo` scope (or `contents:write` on `kodam-my/gdp-nowcast`)
3. Copy the token
4. Go to `pengkodammaya/BM-ECB` → Settings → Secrets → Actions
5. Add/update `SITE_DEPLOY_TOKEN` with the token value
6. Re-run the publish workflow

**Note:** PATs expire — when the publish step 403s, regenerate the token and update the secret.

### Published dashboard URL

The dashboard is served at: **https://kodam-my.github.io/gdp-nowcast-ECBport/**

---

## Data Issues

### GDP nowcast is wildly wrong

**Possible causes:**
1. **Stale data cache:** Delete `data/malaysia/*.parquet` and re-fetch
2. **COVID outlier:** Enable COVID correction in config:
   ```json
   {"do_covid": 2}
   ```
3. **Wrong transformation:** Ensure GDP uses `gdp_qtr_real_sa` (seasonally adjusted)

### `KeyError` when fetching data

**Cause:** OpenDOSM API changed column names.

**Solution:** Check the API docs at https://developer.data.gov.my/static-api/opendosm and update the dataset registry.

---

## Configuration

### Config file not found

**Solution:** Use absolute path or ensure correct working directory:
```bash
cd /path/to/nowcast
nowcast --config config.json run
```

### YAML config not working

**Cause:** PyYAML not installed.

```bash
pip install pyyaml
```

---

## Performance

### Backtest takes too long

**Solution:**
1. Reduce vintage date range:
   ```bash
   nowcast backtest --start 2023-01-01 --end 2025-12-31
   ```
2. Use fast BVAR mode (default in daily_update.py)
3. Reduce Gibbs sampler draws in config

---

## Getting Help

1. Check the [GitHub Issues](https://github.com/pengkodammaya/BM-ECB/issues)
2. Review logs with `--verbose` flag:
   ```bash
   nowcast --verbose run
   ```
3. Run tests to verify installation:
   ```bash
   python -m pytest tests/ -v
   ```

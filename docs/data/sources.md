# Data Sources

## OpenDOSM API

Malaysian macroeconomic data from the Department of Statistics Malaysia.

**Base URL:** `https://api.data.gov.my/opendosm/`

### Datasets

| Dataset ID | Description | Frequency |
|------------|-------------|-----------|
| `ipi` | Industrial Production Index | Monthly |
| `cpi_headline` | Consumer Price Index | Monthly |
| `cpi_core` | Core CPI | Monthly |
| `ppi` | Producer Price Index | Monthly |
| `lfs_month` | Labour Force Survey | Monthly |
| `economic_indicators` | Leading/Coincident Index | Monthly |
| `trade_headline` | External Trade | Monthly |
| `iowrt` | Wholesale & Retail Trade | Monthly |
| `gdp_qtr_real` | Real GDP (YoY) | Quarterly |
| `gdp_qtr_real_sa` | Real GDP (SA, QoQ) | Quarterly |

## BNM OpenAPI

Financial data from Bank Negara Malaysia.

**Base URL:** `https://api.bnm.gov.my/public`

### Datasets

| Endpoint | Description | Frequency |
|----------|-------------|-----------|
| `/interest-rate` | Overnight interbank rate | Daily |
| `/exchange-rate/USD` | MYR/USD exchange rate | Daily |

## Yahoo Finance (Global)

Global equity indices and commodities via `yfinance`.

| Ticker | Label | Group |
|--------|-------|-------|
| `^GSPC` | sp500 | global_equity |
| `000001.SS` | shcomp | global_equity |
| `^SOX` | sox | global_equity |
| `^KLSE` | klci | global_equity |
| `^STI` | sti | global_equity |
| `BZ=F` | brent | global_commodity |
| `CPO=F` | cpо | global_commodity |
| `BDRY` | bdry | global_demand |

## FRED (US Economic Data)

| Series ID | Label | Description |
|-----------|-------|-------------|
| `INDPRO` | us_ip | US Industrial Production |
| `UMCSENT` | us_sentiment | US Consumer Sentiment |

## Caching

All API responses are cached locally in `data/malaysia/` as Parquet files with configurable TTL (default: 6 hours).

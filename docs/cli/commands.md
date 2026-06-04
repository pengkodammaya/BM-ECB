# CLI Commands

## Global Options

```bash
nowcast [OPTIONS] COMMAND
```

| Option | Description |
|--------|-------------|
| `--verbose`, `-v` | Enable debug logging |
| `--config`, `-c` | Path to JSON/YAML config file |
| `--help` | Show help |

## Commands

### `fetch`

Fetch latest data from configured sources.

```bash
nowcast fetch [--source api|excel|csv|parquet] [--file PATH]
```

### `run`

Full pipeline: fetch → transform → nowcast → leaderboard.

```bash
nowcast run
```

### `backtest`

Run pseudo-real-time backtest evaluation.

```bash
nowcast backtest [--start YYYY-MM-DD] [--end YYYY-MM-DD]
```

### `leaderboard`

Print latest leaderboard from cached results.

```bash
nowcast leaderboard
```

### `news`

News decomposition: attribute nowcast changes to data releases.

```bash
nowcast news [--old-date YYYY-MM-DD] [--new-date YYYY-MM-DD]
```

### `select-vars`

Rank indicators by predictive power for GDP.

```bash
nowcast select-vars [--method lars|tstat|correlation] [--n 20]
```

### `config-template`

Generate a sample JSON config file.

```bash
nowcast config-template
```

### `schedule`

Install a scheduled task (Windows) or print cron line (Unix).

```bash
nowcast schedule [--interval daily|weekly]
```

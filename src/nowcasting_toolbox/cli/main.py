"""CLI entry point for the Nowcasting Toolbox."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from nowcasting_toolbox.config import ToolboxConfig
from nowcasting_toolbox.pipeline.orchestrator import Pipeline
from nowcasting_toolbox.pipeline.leaderboard import print_leaderboard, export_leaderboard

logger = logging.getLogger(__name__)


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Verbose output.")
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True),
    default=None,
    help="Path to JSON config file.",
)
@click.pass_context
def cli(ctx: click.Context, verbose: bool, config: str | None) -> None:
    """Nowcasting Toolbox — GDP nowcasting with DFM, BVAR, and BEQ models."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if config:
        import json
        with open(config) as f:
            cfg_data = json.load(f)
        ctx.obj = ToolboxConfig(**cfg_data)
    else:
        ctx.obj = ToolboxConfig()


@cli.command()
@click.option("--source", "-s", default="api", type=click.Choice(["api", "excel", "csv", "parquet"]))
@click.option("--file", "-f", default=None, type=click.Path(exists=True))
@click.pass_context
def fetch(ctx: click.Context, source: str, file: str | None) -> None:
    """Fetch latest data from configured sources."""
    config: ToolboxConfig = ctx.obj
    pipeline = Pipeline(config)
    data = pipeline.fetch(source=source, file_path=file)
    click.echo(f"Loaded {data.xest.shape[0]} obs × {data.xest.shape[1]} variables")
    click.echo(f"Dates: {data.datet[0]} to {data.datet[-1]}")
    click.echo(f"Monthly: {data.nM}, Quarterly: {data.nQ}")


@cli.command()
@click.pass_context
def run(ctx: click.Context) -> None:
    """Run full pipeline: fetch -> nowcast -> leaderboard."""
    config: ToolboxConfig = ctx.obj
    pipeline = Pipeline(config)

    click.echo("Fetching data...")
    pipeline.fetch()

    click.echo("Running nowcasts...")
    result = pipeline.nowcast()

    # Extract latest nowcast
    d = result.dfm_result.X_sm[-1, -1] if result.dfm_result else float("nan")
    b = result.bvar_result.X_sm[-1, -1] if result.bvar_result else float("nan")
    e = result.beq_result.X_sm[-1, -1] if result.beq_result else float("nan")

    click.echo(f"\nLatest GDP nowcast (QoQ annualised %):")
    click.echo(f"  DFM:  {d:.2f}")
    click.echo(f"  BVAR: {b:.2f}")
    click.echo(f"  BEQ:  {e:.2f}")

    # Leaderboard
    click.echo("\nEvaluating...")
    lb = pipeline.evaluate()
    print_leaderboard(lb)
    export_leaderboard(lb, Path("output/malaysia/leaderboard"))


@cli.command()
@click.option("--start", default="2020-01-01", help="Backtest start (YYYY-MM).")
@click.option("--end", default="2025-12-31", help="Backtest end (YYYY-MM).")
@click.pass_context
def backtest(ctx: click.Context, start: str, end: str) -> None:
    """Run pseudo-real-time backtest evaluation."""
    config: ToolboxConfig = ctx.obj

    sy, sm = int(start[:4]), int(start[5:7])
    ey, em = int(end[:4]), int(end[5:7])

    config.eval.eval_startyear = sy
    config.eval.eval_startmonth = sm
    config.eval.eval_endyear = ey
    config.eval.eval_endmonth = em
    config.do_eval = 1

    pipeline = Pipeline(config)
    pipeline.fetch()
    lb = pipeline.evaluate()
    print_leaderboard(lb)
    export_leaderboard(lb, Path("output/malaysia/leaderboard"))
    click.echo("Backtest complete.")


@cli.command()
@click.pass_context
def leaderboard(ctx: click.Context) -> None:
    """Print latest leaderboard from cached results."""
    path = Path("output/malaysia/leaderboard.csv")
    if not path.exists():
        click.echo("No leaderboard found. Run 'nowcast run' or 'nowcast backtest' first.")
        return

    import pandas as pd
    df = pd.read_csv(path)
    print_leaderboard(df)


@cli.command("config-template")
def config_template() -> None:
    """Generate a sample JSON config file."""
    import json
    from nowcasting_toolbox.config import ToolboxConfig
    
    cfg = ToolboxConfig()
    # Use model_dump with mode='json' for clean serialization
    cfg_dict = cfg.model_dump(mode="json")
    config_json = json.dumps(cfg_dict, indent=2)
    
    out_path = Path("config_example.json")
    out_path.write_text(config_json)
    click.echo(f"Sample config written to {out_path}")
    click.echo("Edit this file and run: nowcast --config config_example.json run")


@cli.command("select-vars")
@click.option("--method", "-m", default="lars", type=click.Choice(["lars", "tstat", "correlation"]),
              help="Selection method.")
@click.option("--n", "-n", default=20, help="Number of top variables to return.")
@click.pass_context
def select_vars_cmd(ctx: click.Context, method: str, n: int) -> None:
    """Rank indicators by predictive power for GDP."""
    import numpy as np
    import pandas as pd
    from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient
    from nowcasting_toolbox.data.sources.cache import DataCache
    from nowcasting_toolbox.data.calendar import generate_dates
    from nowcasting_toolbox.data.transforms import transform_series
    from nowcasting_toolbox.selection.variable_selection import select_variables

    click.echo(f"Loading data for variable selection (method={method})...")

    DATASETS = {
        "ipi": ("ipi", "index", 0, "industry", {"series": "growth_mom"}, 8, "monthly"),
        "cpi_headline": ("cpi_headline", "index", 1, "prices", {"division": "overall"}, 19, "monthly"),
        "cpi_core": ("cpi_core", "index", 1, "prices", {"division": "overall"}, 19, "monthly"),
        "ppi": ("ppi", "index", 1, "prices", {"series": "abs"}, 25, "monthly"),
        "u_rate": ("lfs_month", "u_rate", 0, "labour", {}, 12, "monthly"),
        "p_rate": ("lfs_month", "p_rate", 0, "labour", {}, 12, "monthly"),
        "u_rate_youth": ("lfs_month_youth", "u_rate_15_30", 0, "labour", {}, 12, "monthly"),
        "leading": ("economic_indicators", "leading", 1, "leading", {}, 55, "monthly"),
        "coincident": ("economic_indicators", "coincident", 1, "coincident", {}, 55, "monthly"),
        "exports": ("trade_headline", "exports", 1, "external", {"series": "abs"}, 30, "monthly"),
        "imports_capital": ("trade_enduse_bec", "imports", 0, "external", {"bec": "000", "end_use": "capital", "series": "growth_mom"}, 30, "monthly"),
        "imports_consumer": ("trade_enduse_bec", "imports", 0, "external", {"bec": "000", "end_use": "consumption", "series": "growth_mom"}, 30, "monthly"),
        "wrt": ("iowrt", "sales", 1, "services", {"series": "abs"}, 30, "monthly"),
        "gdp": ("gdp_qtr_real_sa", "value", 0, "target", {"series": "abs"}, 45, "quarterly"),
    }

    cache = DataCache(ttl_hours=24)
    client = OpenDOSMClient()
    filtered = {}
    # Store metadata for output
    var_meta = {}
    for name, (did, col, tcode, group, filters, lag_days, freq) in DATASETS.items():
        df = cache.get(did)
        if df is None:
            df = client.fetch(did, limit=20000)
            if df is not None and not df.empty:
                cache.put(did, df)
        if df is None or df.empty:
            continue
        df = df.copy()
        for fc, fv in filters.items():
            if fc in df.columns:
                df = df[df[fc] == fv]
        if col not in df.columns:
            continue
        df = df[["date", col]].dropna().rename(columns={col: name})
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").drop_duplicates("date")
        filtered[name] = df
        var_meta[name] = {"group": group, "lag_days": lag_days, "freq": freq}

    # Convert % growth to decimal
    for var in ["ipi", "imports_capital", "imports_consumer"]:
        if var in filtered:
            filtered[var][var] = filtered[var][var] / 100.0

    # GDP QoQ
    gdp_df = filtered["gdp"].copy().sort_values("date")
    gv = gdp_df["gdp"].values
    gq = np.full(len(gv), np.nan)
    for i in range(1, len(gv)):
        if gv[i-1] > 0:
            gq[i] = (gv[i] - gv[i-1]) / gv[i-1]
    gdp_df["gdp"] = gq
    gdp_df = gdp_df.dropna(subset=["gdp"])
    filtered["gdp"] = gdp_df

    # Build grid
    mn = [n for n in DATASETS if n != "gdp" and n in filtered]
    md = [df["date"].min() for df in filtered.values()]
    Mx = [df["date"].max() for df in filtered.values()]
    gd = max(filtered["gdp"]["date"].min(), pd.Timestamp("2018-01-01"))
    ed = max(Mx)
    datet = generate_dates(gd.year, gd.month, ed.year, ed.month)
    T = len(datet)
    X = np.full((T, len(mn) + 1), np.nan)

    for j, name in enumerate(mn):
        df = filtered[name]
        for _, row in df.iterrows():
            y, m = row["date"].year, row["date"].month
            idx = np.where((datet[:, 0] == y) & (datet[:, 1] == m))[0]
            if len(idx) > 0:
                X[idx[0], j] = row[name]

    gdp_df_q = filtered["gdp"]
    for _, row in gdp_df_q.iterrows():
        y, m = row["date"].year, row["date"].month
        qem = ((m - 1) // 3) * 3 + 3
        idx = np.where((datet[:, 0] == y) & (datet[:, 1] == qem))[0]
        if len(idx) > 0:
            X[idx[0], -1] = row["gdp"]

    X_trans = X.copy()
    for j, name in enumerate(mn):
        tcode = DATASETS[name][2]
        X_trans[:, j] = transform_series(X[:, j].copy(), tcode, "monthly")

    # Align: use only rows where GDP is observed (quarterly)
    gdp_col = -1
    gdp_rows = ~np.isnan(X_trans[:, gdp_col])
    X_monthly = X_trans[gdp_rows, :len(mn)]
    y_target = X_trans[gdp_rows, gdp_col]

    client.close()

    # Drop any remaining NaN
    valid = ~np.any(np.isnan(X_monthly), axis=1) & ~np.isnan(y_target)
    X_valid = X_monthly[valid]
    y_valid = y_target[valid]

    if len(y_valid) < 5:
        click.echo("Not enough data for variable selection.")
        return

    # Convert to DataFrame for named output
    X_df = pd.DataFrame(X_valid, columns=mn)
    
    # Run selection
    result = select_variables(
        X_df, y_valid, 
        method=method, 
        n_select=n,
    )

    # Add metadata columns
    result["group"] = result["variable"].map(lambda v: var_meta.get(v, {}).get("group", "unknown"))
    result["lag_days"] = result["variable"].map(lambda v: var_meta.get(v, {}).get("lag_days", 0))
    result["frequency"] = result["variable"].map(lambda v: var_meta.get(v, {}).get("freq", "unknown"))

    click.echo(f"\nTop {n} indicators by {method}:")
    for _, row in result.iterrows():
        click.echo(f"  {int(row['rank']):2d}. {row['variable']:<25s} score={row['score']:.4f}  group={row['group']:<12s} lag={row['lag_days']}d")

    # Save
    out = Path(f"output/malaysia/variable_ranking_{method}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out, index=False)
    click.echo(f"\nSaved to {out}")

@cli.command()
@click.option("--old-date", "-o", default=None, help="Old vintage date (YYYY-MM-DD). Default: 1 month ago.")
@click.option("--new-date", "-n", default=None, help="New vintage date (YYYY-MM-DD). Default: today.")
@click.pass_context
def news(ctx: click.Context, old_date: str | None, new_date: str | None) -> None:
    """News decomposition: attribute nowcast changes to data releases."""
    import numpy as np
    import pandas as pd
    from datetime import date, timedelta
    from pathlib import Path
    from rich.table import Table
    from rich.console import Console
    
    from nowcasting_toolbox.data.sources.opendosm import OpenDOSMClient
    from nowcasting_toolbox.data.sources.cache import DataCache
    from nowcasting_toolbox.data.calendar import generate_dates
    from nowcasting_toolbox.data.transforms import transform_series
    from nowcasting_toolbox.eval.vintage import ARCVintageBuilder
    from nowcasting_toolbox.data.sources.arc_parser import build_publication_schedule
    from nowcasting_toolbox.dfm import DFM
    from nowcasting_toolbox.config import DFMParams
    from nowcasting_toolbox.news.base import compute_news

    # Set vintage dates
    if new_date is None:
        new_vdate = date.today()
    else:
        new_vdate = date.fromisoformat(new_date)
    if old_date is None:
        old_vdate = new_vdate - timedelta(days=30)
    else:
        old_vdate = date.fromisoformat(old_date)

    click.echo(f"News decomposition: {old_vdate} -> {new_vdate}")

    # Load data
    DATASETS = {
        "ipi": ("ipi", "index", 0, "industry", {"series": "growth_mom"}),
        "cpi_headline": ("cpi_headline", "index", 1, "prices", {"division": "overall"}),
        "cpi_core": ("cpi_core", "index", 1, "prices", {"division": "overall"}),
        "ppi": ("ppi", "index", 1, "prices", {"series": "abs"}),
        "u_rate": ("lfs_month", "u_rate", 0, "labour", {}),
        "p_rate": ("lfs_month", "p_rate", 0, "labour", {}),
        "leading": ("economic_indicators", "leading", 1, "leading", {}),
        "coincident": ("economic_indicators", "coincident", 1, "coincident", {}),
        "exports": ("trade_headline", "exports", 1, "external", {"series": "abs"}),
        "wrt": ("iowrt", "sales", 1, "services", {"series": "abs"}),
        "gdp": ("gdp_qtr_real_sa", "value", 0, "target", {"series": "abs"}),
    }
    MN = [n for n in DATASETS if n != "gdp"]
    AN = MN + ["gdp"]
    GROUPS = [DATASETS[n][3] for n in MN] + ["target"]

    cache = DataCache(ttl_hours=6)
    client = OpenDOSMClient()
    filtered = {}
    for name, (did, col, tcode, group, filters) in DATASETS.items():
        df = cache.get(did)
        if df is None:
            df = client.fetch(did, limit=20000)
            if df is not None and not df.empty:
                cache.put(did, df)
        if df is None or df.empty:
            continue
        df = df.copy()
        for fc, fv in filters.items():
            if fc in df.columns:
                df = df[df[fc] == fv]
        if col not in df.columns:
            continue
        df = df[["date", col]].dropna().rename(columns={col: name})
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").drop_duplicates("date")
        filtered[name] = df

    if "ipi" in filtered:
        filtered["ipi"]["ipi"] = filtered["ipi"]["ipi"] / 100.0

    gdp_df = filtered["gdp"].copy().sort_values("date")
    gv = gdp_df["gdp"].values
    gq = np.full(len(gv), np.nan)
    for i in range(1, len(gv)):
        if gv[i-1] > 0:
            gq[i] = (gv[i] - gv[i-1]) / gv[i-1]
    gdp_df["gdp"] = gq
    gdp_df = gdp_df.dropna(subset=["gdp"])
    filtered["gdp"] = gdp_df

    md = [df["date"].min() for df in filtered.values()]
    Mx = [df["date"].max() for df in filtered.values()]
    gd = max(filtered["gdp"]["date"].min(), pd.Timestamp("2018-01-01"))
    ed = max(Mx)
    datet_full = generate_dates(gd.year, gd.month, ed.year, ed.month)
    T = len(datet_full)
    X_full = np.full((T, len(MN) + 1), np.nan)
    for j, name in enumerate(MN):
        df = filtered[name]
        for _, row in df.iterrows():
            y, m = row["date"].year, row["date"].month
            idx = np.where((datet_full[:, 0] == y) & (datet_full[:, 1] == m))[0]
            if len(idx) > 0:
                X_full[idx[0], j] = row[name]
    gdp_df_q = filtered["gdp"]
    for _, row in gdp_df_q.iterrows():
        y, m = row["date"].year, row["date"].month
        qem = ((m - 1) // 3) * 3 + 3
        idx = np.where((datet_full[:, 0] == y) & (datet_full[:, 1] == qem))[0]
        if len(idx) > 0:
            X_full[idx[0], -1] = row["gdp"]
    X_trans = X_full.copy()
    for j, name in enumerate(AN):
        tcode = DATASETS[name][2]
        freq = "quarterly" if name == "gdp" else "monthly"
        X_trans[:, j] = transform_series(X_full[:, j].copy(), tcode, freq)
    mu = np.nanmean(X_trans, axis=0)
    sigma = np.nanstd(X_trans, axis=0)
    sigma[sigma < 1e-10] = 1.0
    X_raw = X_trans.copy()
    ff = np.where(~np.all(np.isnan(X_raw), axis=1))[0][0]
    X_raw = X_raw[ff:]
    datet = datet_full[ff:]
    client.close()

    # Vintage builder
    arc_schedule = build_publication_schedule(years=[2023, 2024, 2025, 2026], cache_dir=Path("data/malaysia"))
    vb = ARCVintageBuilder(schedule=arc_schedule)
    DID_MAP = ["ipi", "cpi_headline", "cpi_core", "ppi", "u_rate", "u_rate", "leading", "coincident", "exports", "wrt", "gdp"]

    # Build vintages
    X_old_raw = vb.build(X_raw.copy(), datet, old_vdate, var_names=AN, dataset_ids=DID_MAP)
    X_new_raw = vb.build(X_raw.copy(), datet, new_vdate, var_names=AN, dataset_ids=DID_MAP)

    # Show what changed
    click.echo("\nNew data since previous vintage:")
    for j, name in enumerate(AN):
        old_last = np.where(~np.isnan(X_old_raw[:, j]))[0]
        new_last = np.where(~np.isnan(X_new_raw[:, j]))[0]
        old_end = old_last[-1] if len(old_last) > 0 else -1
        new_end = new_last[-1] if len(new_last) > 0 else -1
        if old_end != new_end:
            y, m = int(datet[new_end, 0]), int(datet[new_end, 1])
            new_val = X_new_raw[new_end, j]
            click.echo(f"  {name:<20s}: {y}-{m:02d} = {new_val:+.3f}")

    # Standardize
    vint_mu = np.nanmean(X_old_raw, axis=0)
    vint_sigma = np.nanstd(X_old_raw, axis=0)
    vint_sigma[vint_sigma < 1e-10] = 1.0
    X_old_std = (X_old_raw - vint_mu) / vint_sigma
    X_new_std = (X_new_raw - vint_mu) / vint_sigma
    valid_rows = ~np.all(np.isnan(X_old_std), axis=1)
    first = np.where(valid_rows)[0][0]
    X_old_std = X_old_std[first:]
    X_new_std = X_new_std[first:]

    click.echo("\nFitting DFM on old vintage...")
    dfm = DFM(DFMParams(r=2, p=4, max_iter=50, thresh=1e-5, idio=1))
    res_old = dfm.fit(X_old_std)

    # Compute news
    gdp_col = -1
    target_idx = len(X_old_std) - 1
    news_result = compute_news(
        X_old_std, X_new_std,
        res_old.A, res_old.C, res_old.Q, res_old.R,
        var_names=AN, group_names=GROUPS,
        gdp_col=gdp_col, target_quarter_end_idx=target_idx,
    )

    click.echo(f"\n  Old nowcast: {news_result['old_nowcast_pct']:+.2f}%")
    click.echo(f"  New nowcast: {news_result['new_nowcast_pct']:+.2f}%")
    click.echo(f"  Total change: [bold]{news_result['total_change_pp']:+.3f} pp[/bold]")

    # Table
    table = Table(title="News Decomposition — Contribution by Variable")
    table.add_column("Variable", style="bold")
    table.add_column("Group")
    table.add_column("Contribution (pp)", justify="right")

    for row in news_result["news_table"]:
        if abs(row["contribution_pp"]) < 0.001:
            continue
        style = "green" if row["direction"] == "up" else "red"
        table.add_row(row["series"], row["group"], f"{row['contribution_pp']:+.3f}", style=style)

    console = Console()
    console.print(table)

@cli.command()
@click.option("--interval", "-i", default="daily", type=click.Choice(["daily", "weekly"]))
@click.pass_context
def schedule(ctx: click.Context, interval: str) -> None:
    """Install a scheduled task to run the pipeline automatically.

    On Windows this creates a scheduled task; on Unix a cron job.
    """
    import platform
    import subprocess

    python_exe = sys.executable
    script = f'cd "{Path.cwd()}" && "{python_exe}" -m nowcasting_toolbox.cli.main run'

    if platform.system() == "Windows":
        task_name = "NowcastingToolbox"
        cmd = (
            f'schtasks /create /tn "{task_name}" /tr "{script}" '
            f'/sc {"DAILY" if interval == "daily" else "WEEKLY"} /f'
        )
        subprocess.run(cmd, shell=True)
        click.echo(f"Scheduled task '{task_name}' created ({interval}).")
    else:
        cron_line = (
            f"0 8 * * * {script}" if interval == "daily"
            else f"0 8 * * 1 {script}"
        )
        click.echo("Add this line to crontab (crontab -e):")
        click.echo(cron_line)

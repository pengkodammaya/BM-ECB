"""Model leaderboard: comparison table with rankings."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from rich.console import Console
from rich.table import Table


def build_leaderboard(eval_df: pd.DataFrame) -> pd.DataFrame:
    """Compute leaderboard metrics from evaluation DataFrame.

    Parameters
    ----------
    eval_df : DataFrame
        Output from backtest, with columns nowcast_{model} and actual_gdp.

    Returns
    -------
    pd.DataFrame with rows per model, columns for MAE/FDA in Back/Now/Fore.
    """
    from nowcasting_toolbox.eval.metrics import compute_mae, compute_fda

    models = ["dfm", "bvar", "beq"]
    rows = []

    actual = eval_df["actual_gdp"].to_numpy(dtype=float)

    for model in models:
        col = f"nowcast_{model}"
        if col not in eval_df.columns:
            continue
        pred = eval_df[col].to_numpy(dtype=float)
        mae_val = compute_mae(actual, pred)
        fda_val = compute_fda(actual, pred)

        rows.append({
            "model": model.upper(),
            "MAE (pp)": round(mae_val, 3) if not np.isnan(mae_val) else np.nan,
            "FDA (%)": round(fda_val * 100, 1) if not np.isnan(fda_val) else np.nan,
        })

    # Ensemble (simple average)
    pred_cols = [f"nowcast_{m}" for m in models if f"nowcast_{m}" in eval_df.columns]
    if len(pred_cols) >= 2:
        ensemble_pred = eval_df[pred_cols].mean(axis=1).to_numpy(dtype=float)
        mae_ens = compute_mae(actual, ensemble_pred)
        fda_ens = compute_fda(actual, ensemble_pred)
        rows.append({
            "model": "ENSEMBLE",
            "MAE (pp)": round(mae_ens, 3) if not np.isnan(mae_ens) else np.nan,
            "FDA (%)": round(fda_ens * 100, 1) if not np.isnan(fda_ens) else np.nan,
        })

    df = pd.DataFrame(rows)
    return df


def print_leaderboard(df: pd.DataFrame) -> None:
    """Pretty-print the leaderboard using rich."""
    console = Console()
    table = Table(title="MODEL LEADERBOARD — Malaysia GDP Nowcasting")

    for col in df.columns:
        table.add_column(col, justify="right" if col != "model" else "left")

    for _, row in df.iterrows():
        values = [str(row[col]) for col in df.columns]
        table.add_row(*values)

    console.print(table)

    # Highlight best
    if "MAE (pp)" in df.columns:
        best_mae = df.loc[df["MAE (pp)"].idxmin(), "model"]
        console.print(f"[green]Best MAE: {best_mae}[/green]")
    if "FDA (%)" in df.columns:
        best_fda = df.loc[df["FDA (%)"].idxmax(), "model"]
        console.print(f"[green]Best FDA: {best_fda}[/green]")


def export_leaderboard(df: pd.DataFrame, path: Path | str) -> None:
    """Export leaderboard to CSV and Excel."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path.with_suffix(".csv"), index=False)
    df.to_excel(path.with_suffix(".xlsx"), index=False)

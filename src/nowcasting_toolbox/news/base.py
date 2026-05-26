"""News decomposition: attributes nowcast revisions to new data releases.

Algorithm (from Banbura & Modugno, 2014):
1. Fit the DFM on the OLD data vintage → get parameters (C, A, Q, R)
2. Run Kalman smoother on OLD → old_nowcast at target quarter
3. Run Kalman smoother on NEW → new_nowcast
4. For each series with new observations, run KF with just that series
   updated → attribute the nowcast change proportionally
5. Sum of individual contributions ≈ total change (linear approximation)

When no previous vintage exists, compares against "no observations" baseline
(pure factor propagation).
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def compute_news(
    X_old: FloatArray,
    X_new: FloatArray,
    A: FloatArray,
    C: FloatArray,
    Q: FloatArray,
    R: FloatArray,
    var_names: list[str],
    group_names: list[str],
    gdp_col: int = -1,
    target_quarter_end_idx: int | None = None,
) -> dict:
    """Compute news decomposition between two data vintages.

    Parameters
    ----------
    X_old : (T, N) previous data vintage (may be all-NaN for baseline)
    X_new : (T, N) current data vintage
    A, C, Q, R : state-space parameters from model fitted on OLD data
    var_names : list of variable names
    group_names : list of group names per variable
    gdp_col : column index for GDP target
    target_quarter_end_idx : row index of the target quarter in X.
                              If None, uses last row.

    Returns
    -------
    dict with keys:
        old_nowcast_pct, new_nowcast_pct, total_change_pct
        news_table : list of {series, group, contribution_pct, pct_of_total, direction}
        summary_by_group : {group: total_pp}
    """
    from nowcasting_toolbox.dfm.kalman import kalman_filter_smoother

    N, T = X_old.shape[1], X_old.shape[0]
    if target_quarter_end_idx is None:
        target_quarter_end_idx = T - 1

    gdp_c = C[gdp_col, :]  # loading vector for GDP

    # ---------- Old nowcast ----------
    if np.all(np.isnan(X_old)):
        old_nowcast_std = 0.0
        Z_smooth_old = np.zeros((T, A.shape[0]))
    else:
        y_old = X_old.T
        Z_0 = np.zeros(A.shape[0])
        V_0 = np.eye(A.shape[0])
        Z_smooth_old, _ = kalman_filter_smoother(y_old, A, C, Q, R, Z_0, V_0)
        old_nowcast_std = float(Z_smooth_old[target_quarter_end_idx] @ gdp_c)

    # ---------- New nowcast ----------
    y_new = X_new.T
    Z_0 = np.zeros(A.shape[0])
    V_0 = np.eye(A.shape[0])
    Z_smooth_new, _ = kalman_filter_smoother(y_new, A, C, Q, R, Z_0, V_0)
    new_nowcast_std = float(Z_smooth_new[target_quarter_end_idx] @ gdp_c)

    total_change_std = new_nowcast_std - old_nowcast_std

    # ---------- Attribute to individual series ----------
    series_contrib = np.zeros(N)

    for j in range(N):
        # Find rows where series j changed (from NaN → value or value → different value)
        old_col = X_old[:, j]
        new_col = X_new[:, j]
        changed = ~np.isclose(old_col, new_col, rtol=1e-8, equal_nan=True)
        # Only count cases where new data IS available (not NaN in new)
        new_available = ~np.isnan(new_col)
        relevant = changed & new_available

        if not np.any(relevant):
            continue

        # Build partial data: old with just series j updated to new
        X_partial = X_old.copy()
        X_partial[relevant, j] = X_new[relevant, j]
        y_partial = X_partial.T
        Z_0 = np.zeros(A.shape[0])
        V_0 = np.eye(A.shape[0])
        Z_smooth_partial, _ = kalman_filter_smoother(y_partial, A, C, Q, R, Z_0, V_0)
        partial_nowcast_std = float(Z_smooth_partial[target_quarter_end_idx] @ gdp_c)
        series_contrib[j] = partial_nowcast_std - old_nowcast_std

    # Rescale to match total (handles non-linear interaction effects)
    sum_contrib = np.sum(series_contrib)
    if abs(sum_contrib) > 1e-12:
        series_contrib *= total_change_std / sum_contrib

    # ---------- Build output ----------
    news_table = []
    group_sums: dict[str, float] = {}

    for j in range(N):
        name = var_names[j] if j < len(var_names) else f"var_{j}"
        group = group_names[j] if j < len(group_names) else "other"
        contrib = float(series_contrib[j])

        news_table.append({
            "series": name,
            "group": group,
            "contribution_pp": round(contrib * 100, 4),
            "pct_of_total": round(abs(contrib) / (abs(total_change_std) + 1e-12) * 100, 1),
            "direction": "up" if contrib > 1e-6 else "down" if contrib < -1e-6 else "flat",
        })
        group_sums[group] = group_sums.get(group, 0.0) + contrib

    # Sort by absolute contribution
    news_table.sort(key=lambda r: abs(r["contribution_pp"]), reverse=True)

    return {
        "old_nowcast_pct": old_nowcast_std * 100,
        "new_nowcast_pct": new_nowcast_std * 100,
        "total_change_pp": total_change_std * 100,
        "news_table": news_table,
        "summary_by_group": {k: round(v * 100, 4) for k, v in group_sums.items()},
    }

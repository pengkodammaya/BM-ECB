"""Data availability heatmap (replicates common_heatmap.m)."""

from __future__ import annotations

import numpy as np


def plot_heatmap(
    X: np.ndarray,
    groups: list[str] | None = None,
    groups_name: list[str] | None = None,
    names: list[str] | None = None,
    ax=None,
) -> object:
    """Plot a heatmap showing data availability (NaN = missing).

    Returns matplotlib figure.
    """
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors

    if ax is None:
        fig, ax = plt.subplots(figsize=(12, 6))
    else:
        fig = ax.figure

    cmap = mcolors.ListedColormap(["#d3d3d3", "#1f77b4"])
    data_mask = (~np.isnan(X)).astype(int)

    ax.imshow(data_mask.T, aspect="auto", cmap=cmap, interpolation="nearest")

    if names:
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names, fontsize=8)

    ax.set_title("Data Availability Heatmap")
    ax.set_xlabel("Time")
    ax.set_ylabel("Variable")

    return fig

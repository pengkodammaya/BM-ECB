"""Guard test: ensure no np.interp in backtest-critical code paths.

np.interp interpolates between past AND future values, causing data leakage
in pseudo-real-time backtesting. Use forward_fill() instead.

See docs/EXPERIMENTAL_FINDINGS.md section 0 for details.
"""

import pytest


def test_no_interp_in_backtest_scripts():
    """Backtest scripts should not use np.interp for data filling."""
    import os
    from pathlib import Path

    root = Path(__file__).parent.parent
    backtest_files = [
        root / "scripts" / "backtest_all_models.py",
        root / "scripts" / "test_all_models.py",
        root / "scripts" / "component_backtest.py",
    ]

    for fpath in backtest_files:
        if not fpath.exists():
            continue
        content = fpath.read_text()
        # Allow np.interp only in comments
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "np.interp" in line:
                pytest.fail(
                    f"{fpath.name}:{i} uses np.interp — causes data leakage! "
                    f"Use forward_fill() from utils.missing instead. "
                    f"See docs/EXPERIMENTAL_FINDINGS.md section 0."
                )


def test_no_interp_in_bvar_fill():
    """BVAR _fill_data should use forward-fill, not np.interp."""
    from pathlib import Path

    bbvar_path = Path(__file__).parent.parent / "src" / "nowcasting_toolbox" / "bvar" / "bbvar.py"
    content = bbvar_path.read_text()

    # Check that _fill_data doesn't use np.interp
    in_fill_data = False
    for line in content.split("\n"):
        if "def _fill_data" in line:
            in_fill_data = True
        elif in_fill_data and line.strip().startswith("def "):
            in_fill_data = False
        if in_fill_data and "np.interp" in line:
            pytest.fail(
                "bvar/bbvar.py:_fill_data uses np.interp — causes data leakage! "
                "Use forward-fill instead."
            )

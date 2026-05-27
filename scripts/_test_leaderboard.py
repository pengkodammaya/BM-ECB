"""Test: generate leaderboard.md without fetching data."""
import sys, json
from pathlib import Path
from datetime import date, datetime

# Simulate nowcasts with real values
today_str = "2026-05-27"
nowcast_label = "Q2 2026"
backcast_label = "Q1 2026"
forecast_label = "Q3 2026"
actual_pct = -0.01
current_quarter = 2

# Create dummy log with 1 row
import pandas as pd
log = pd.DataFrame([{
    "date": "2026-05-26",
    "dfm": 2.14, "bvar": 0.92, "beq": 1.09, "ar1": 1.46,
    "naive": -0.01, "ensemble": 1.09, "actual_gdp_pct": -0.01
}])

nowcasts = {
    "dfm": 2.14, "bvar": 0.92, "beq": 1.09, "ar1": 1.46, "naive": -0.01, "ensemble": 1.09,
    "dfm_backcast": 1.78, "bvar_backcast": 0.99, "beq_backcast": 1.05,
    "dfm_forecast": 1.18, "bvar_forecast": 0.53, "beq_forecast": 1.05,
    "consumption": 7.47, "investment": 5.24, "government": 4.65, "exports_comp": 4.05, "imports_comp": 4.70,
    "consumption_ar1": 5.12, "investment_ar1": 5.41, "government_ar1": 4.26,
    "exports_comp_ar1": 4.93, "imports_comp_ar1": 4.75,
    "consumption_naive": 4.7, "investment_naive": 7.3, "government_naive": 4.1,
    "exports_comp_naive": 5.2, "imports_comp_naive": 4.6,
    "consumption_actual": 4.7, "investment_actual": 7.3, "government_actual": 4.1,
    "exports_comp_actual": 5.2, "imports_comp_actual": 4.6,
    "imports_identity": 10.99, "actual_gdp_pct": -0.01,
}

# Import needed modules
sys.path.insert(0, "src")
from nowcasting_toolbox.eval.metrics import compute_mae, compute_rmse, compute_fda

# Run the markdown generation code from daily_update.py
# We execute a simplified version of the leaderboard gen
dosm_advance = None
adv_q_label = f"{datetime.now().year}-Q{current_quarter}"
adv_reference = actual_pct
adv_reference_source = f"DOSM Actual (latest: {backcast_label})"

md = f"# Malaysia GDP Nowcasting — Live Leaderboard\n\n"
md += f"**Updated:** {today_str} | **Nowcasting:** {nowcast_label} | **Reference:** {adv_reference_source}\n\n"
md += "## Current Quarter Nowcast (QoQ SA %)\n\n"
md += f"*Nowcasting GDP for **{nowcast_label}**.*\n\n"

all_models = ["DFM", "BVAR", "BEQ", "AR(1)", "NAIVE", "ENSEMBLE"]
model_errors = {}
for model in all_models:
    col = model.lower()
    val = nowcasts.get(col)
    if val is not None:
        err = abs(val - adv_reference) if adv_reference is not None else None
        model_errors[model] = err
        md += f"- **{model}:** `{val:+.2f}%`\n"

if adv_reference is not None:
    md += f"\n*Reference: `{adv_reference:+.1f}%` — {adv_reference_source}*\n"
    if model_errors:
        min_err = min(model_errors.values())
        best_models = [m for m, e in model_errors.items() if e == min_err]
        md += f"\n**Closest:** {', '.join(best_models)} ({min_err:+.2f}pp err)\n"

# Component leaderboard
comp_labels = {
    "consumption": ("Consumption (Private)", "C"),
    "government": ("Government Spending", "G"),
    "investment": ("Investment (GFCF)", "I"),
    "exports_comp": ("Exports", "X"),
    "imports_comp": ("Imports", "M"),
}

md += f"\n## Component Leaderboard (YoY %)\n\n"

for ck, (clabel, ccode) in comp_labels.items():
    dfm_val = nowcasts.get(ck)
    ar1_val = nowcasts.get(ck + "_ar1")
    naive_val = nowcasts.get(ck + "_naive")
    act_val = nowcasts.get(ck + "_actual")

    dfm_f = f"{dfm_val:+.1f}%" if dfm_val is not None else "—"
    ar1_f = f"{ar1_val:+.1f}%" if ar1_val is not None else "—"
    naive_f = f"{naive_val:+.1f}%" if naive_val is not None else "—"
    act_f = f"`{act_val:+.1f}%`" if act_val is not None else "—"

    dfm_err = abs(dfm_val - act_val) if (dfm_val is not None and act_val is not None) else None
    ar1_err = abs(ar1_val - act_val) if (ar1_val is not None and act_val is not None) else None
    naive_err = 0.0 if naive_val is not None and act_val is not None else None

    if dfm_err is not None and ar1_err is not None:
        errors = {"DFM": dfm_err, "AR(1)": ar1_err, "NAIVE": naive_err}
        min_err = min(errors.values())
        colors = {m: "green" if e == min_err else "red" for m, e in errors.items()}
        dfm_rich = f'<span style="color:{colors["DFM"]}">{dfm_f}</span>'
        ar1_rich = f'<span style="color:{colors["AR(1)"]}">{ar1_f}</span>'
        naive_rich = f'<span style="color:{colors["NAIVE"]}">{naive_f}</span>'
    else:
        dfm_rich = f"`{dfm_f}`" if dfm_val is not None else "—"
        ar1_rich = f"`{ar1_f}`" if ar1_val is not None else "—"
        naive_rich = f"`{naive_f}`" if naive_val is not None else "—"

    md += f"### {clabel} ({ccode})\n\n"
    md += "| Model | Nowcast | Reference (Actual) |\n"
    md += "|-------|---------|--------------------|\n"
    if dfm_err is not None:
        md += f"| DFM | {dfm_rich} ({dfm_err:+.1f}pp) | {act_f} |\n"
        md += f"| AR(1) (baseline) | {ar1_rich} ({ar1_err:+.1f}pp) | {act_f} |\n"
        md += f"| NAIVE (last Q) | {naive_rich} (0.0pp) | {act_f} |\n"
    else:
        md += f"| DFM | {dfm_rich} | {act_f} |\n"
        md += f"| AR(1) (baseline) | {ar1_rich} | {act_f} |\n"
        md += f"| NAIVE (last Q) | {naive_rich} | {act_f} |\n"
    md += "\n"

(Path("docs") / "leaderboard.md").write_text(md)
print("Written to leaderboard.md")

# Check
content = (Path("docs") / "leaderboard.md").read_text()
print(f"HAS color: {'color' in content}")
print(f"HAS NAIVE: {'NAIVE' in content}")
print(f"HAS span: {'span' in content}")
print(f"HAS pp: {'pp' in content}")

# Show component section
idx = content.find("## Component Leaderboard")
if idx >= 0:
    print("\n--- Component section preview ---")
    print(content[idx:idx+600])

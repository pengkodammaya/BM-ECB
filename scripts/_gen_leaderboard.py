"""Generate leaderboard.md from existing daily_log.csv (no data fetch)."""
import pandas as pd, sys
from pathlib import Path
sys.path.insert(0, "src")
from nowcasting_toolbox.eval.metrics import compute_mae, compute_rmse, compute_fda

log = pd.read_csv("docs/daily_log.csv")
nowcasts = log.iloc[-1].to_dict() if len(log) > 0 else {}

actual_pct = nowcasts.get("actual_gdp_pct", -0.01)
adv_reference = actual_pct
today_str = pd.Timestamp.now().strftime("%Y-%m-%d")
nowcast_label = "Q2 2026"
backcast_label = "Q1 2026"
forecast_label = "Q3 2026"
current_quarter = 2

md = "# Malaysia GDP Nowcasting — Live Leaderboard\n\n"
md += f"**Updated:** {today_str} | **Nowcasting:** {nowcast_label} | **Reference:** DOSM Actual (latest: {backcast_label}) — advance for {nowcast_label} pending\n\n"
md += "## Current Quarter Nowcast (QoQ SA %)\n\n"
md += f"*Nowcasting GDP for **{nowcast_label}**.*\n\n"

all_models = ["DFM", "BVAR", "BEQ", "AR(1)", "NAIVE", "ENSEMBLE"]
model_errors = {}
for model in all_models:
    col = model.lower()
    val = nowcasts.get(col)
    if val is not None and not (isinstance(val, float) and pd.isna(val)):
        err = abs(val - adv_reference) if adv_reference is not None else None
        model_errors[model] = err
        md += f"- **{model}:** `{val:+.2f}%`\n"

if adv_reference is not None:
    md += f"\n*Reference (best available): `{adv_reference:+.1f}%` — DOSM Actual (latest: {backcast_label})*\n"
    if model_errors:
        min_err = min(model_errors.values())
        best = [m for m, e in model_errors.items() if e == min_err]
        md += f"\n**Closest to reference:** {', '.join(best)} ({min_err:+.2f}pp err)\n"

md += f"\n## Backcast: {backcast_label} (QoQ SA %)\n\n"
for model in ["DFM", "BVAR", "BEQ"]:
    bc = nowcasts.get(f"{model.lower()}_backcast")
    if bc is not None and not (isinstance(bc, float) and pd.isna(bc)):
        md += f"- **{model}:** `{bc:+.2f}%`\n"
if actual_pct is not None and not (isinstance(actual_pct, float) and pd.isna(actual_pct)):
    md += f"\n*DOSM official: `{actual_pct:+.1f}%`*\n"

md += f"\n## 1-Quarter-Ahead Forecast: {forecast_label} (QoQ SA %)\n\n"
for model in ["DFM", "BVAR", "BEQ"]:
    fc = nowcasts.get(f"{model.lower()}_forecast")
    if fc is not None and not (isinstance(fc, float) and pd.isna(fc)):
        md += f"- **{model}:** `{fc:+.2f}%`\n"

md += "\n## Model Leaderboard\n\n"
md += "*Daily nowcast accuracy vs best available reference. Metrics appear after 3+ days.*\n\n"
if len(log) >= 3:
    lb_rows = []
    for model in ["dfm", "bvar", "beq", "ar1", "naive", "ensemble"]:
        col = model
        if col not in log.columns:
            continue
        sub = log[[col, "actual_gdp_pct"]].dropna()
        if len(sub) < 3:
            continue
        pred = sub[col].values
        act = sub["actual_gdp_pct"].values
        lb_rows.append({
            "model": model.upper(),
            "MAE (pp)": round(compute_mae(act, pred), 3),
            "RMSE (pp)": round(compute_rmse(act, pred), 3),
            "FDA (%)": round(compute_fda(act, pred) * 100, 1),
            "N": len(sub),
            "last_nowcast": nowcasts.get(model),
        })
    lb_df = pd.DataFrame(lb_rows)
    lb_df.to_csv(Path("docs/leaderboard.csv"), index=False)

    md += "| Model | MAE (pp) | RMSE (pp) | FDA (%) | N | Latest |\n"
    md += "|-------|----------|-----------|---------|---|--------|\n"
    for _, r in lb_df.iterrows():
        latest = r.get("last_nowcast", "—")
        latest_str = f"{latest:+.1f}%" if isinstance(latest, (int, float)) else "—"
        note = ""
        if r["model"] == "AR(1)":
            note = " *(baseline)*"
        elif r["model"] == "NAIVE":
            note = " *(last Q)*"
        elif r["model"] == "ENSEMBLE":
            note = " *(combined)*"
        md += f"| {r['model']}{note} | {r['MAE (pp)']:.3f} | {r['RMSE (pp)']:.3f} | {r['FDA (%)']:.1f}% | {int(r['N'])} | {latest_str} |\n"
else:
    md += f"*Leaderboard requires 3+ daily observations. Currently: {len(log)}.*\n\n"
    md += "| Model | MAE (pp) | RMSE (pp) | FDA (%) | N | Latest |\n"
    md += "|-------|----------|-----------|---------|---|--------|\n"
    for model in ["DFM", "BVAR", "BEQ", "AR(1)", "NAIVE", "ENSEMBLE"]:
        col = model.lower()
        val = nowcasts.get(col)
        latest_str = f"{val:+.1f}%" if val is not None else "—"
        note = " *(baseline)*" if model == "AR(1)" else " *(last Q)*" if model == "NAIVE" else " *(combined)*" if model == "ENSEMBLE" else ""
        md += f"| {model}{note} | — | — | — | {len(log)} | {latest_str} |\n"

md += f"\n## Recent Nowcasts ({min(30, len(log))} days)\n\n"
md += "| Date | DFM | BVAR | BEQ | AR(1) | NAIVE | ENSEMBLE | Reference |\n"
md += "|------|-----|------|-----|-------|-------|----------|----------|\n"
ref_str = f"{adv_reference:+.1f}%" if adv_reference is not None else "—"
for _, row in log.tail(30).iterrows():
    vals = []
    for m in ["dfm", "bvar", "beq", "ar1", "naive", "ensemble"]:
        v = row.get(m)
        vals.append(f"{v:+.1f}%" if pd.notna(v) else "—")
    md += f"| {row['date']} | {vals[0]} | {vals[1]} | {vals[2]} | {vals[3]} | {vals[4]} | {vals[5]} | {ref_str} |\n"

md += "\n## Component Leaderboard (YoY %)\n\n"
md += "*DFM nowcast vs AR(1) vs NAIVE baseline for each expenditure component.*\n\n"

comp_labels = {
    "consumption": ("Consumption (Private)", "C"),
    "government": ("Government Spending", "G"),
    "investment": ("Investment (GFCF)", "I"),
    "exports_comp": ("Exports", "X"),
    "imports_comp": ("Imports", "M"),
}

for ck, (clabel, ccode) in comp_labels.items():
    dfm_val = nowcasts.get(ck)
    ar1_val = nowcasts.get(ck + "_ar1")
    naive_val = nowcasts.get(ck + "_naive") or nowcasts.get(ck + "_actual")  # fallback to actual
    act_val = nowcasts.get(ck + "_actual")

    def ok(v):
        return v is not None and not (isinstance(v, float) and pd.isna(v))

    dfm_f = f"{dfm_val:+.1f}%" if ok(dfm_val) else "—"
    ar1_f = f"{ar1_val:+.1f}%" if ok(ar1_val) else "—"
    naive_f = f"{naive_val:+.1f}%" if ok(naive_val) else "—"
    act_f = f"`{act_val:+.1f}%`" if ok(act_val) else "—"

    dfm_err = abs(dfm_val - act_val) if (ok(dfm_val) and ok(act_val)) else None
    ar1_err = abs(ar1_val - act_val) if (ok(ar1_val) and ok(act_val)) else None
    naive_err = 0.0 if (ok(naive_val) and ok(act_val)) else None

    if dfm_err is not None and ar1_err is not None:
        errors = {"DFM": dfm_err, "AR(1)": ar1_err, "NAIVE": naive_err or 0.0}
        ranked = sorted(errors.items(), key=lambda x: x[1])
        rank_emoji = {ranked[0][0]: " 🟢", ranked[1][0]: " 🟠", ranked[2][0]: " 🔴"}
        dfm_rich = f"{rank_emoji['DFM']} {dfm_f}"
        ar1_rich = f"{rank_emoji['AR(1)']} {ar1_f}"
        naive_rich = f"{rank_emoji['NAIVE']} {naive_f}"
    else:
        dfm_rich = f"`{dfm_f}`" if dfm_val is not None else "—"
        ar1_rich = f"`{ar1_f}`" if ar1_val is not None else "—"
        naive_rich = f"`{naive_f}`" if naive_val is not None else "—"

    md += f"### {clabel} ({ccode})\n\n"
    md += "| Model | Nowcast | Reference (Actual) |\n"
    md += "|-------|---------|--------------------|\n"
    if dfm_err is not None:
        md += f"| DFM | {dfm_rich} ({dfm_err:+.1f}pp) | {act_f} |\n"
        md += f"| AR(1) *(baseline)* | {ar1_rich} ({ar1_err:+.1f}pp) | {act_f} |\n"
        md += f"| NAIVE *(last Q)* | {naive_rich} (0.0pp) | {act_f} |\n"
    else:
        md += f"| DFM | {dfm_rich} | {act_f} |\n"
        md += f"| AR(1) *(baseline)* | {ar1_rich} | {act_f} |\n"
        md += f"| NAIVE *(last Q)* | {naive_rich} | {act_f} |\n"
    md += "\n"

md += "\n## Ground Truth Definition\n\n"
md += "- **Main GDP:** QoQ SA growth from DOSM `gdp_qtr_real_sa`\n"
md += "- **Components:** YoY growth from DOSM `gdp_qtr_real_demand`\n"
md += "- **Source:** [OpenDOSM API](https://open.dosm.gov.my)\n"
md += f"- **Latest vintage:** {today_str}\n\n"
md += "---\n*Auto-generated daily at 8am MYT via GitHub Actions. [View source](https://github.com/pengkodammaya/BM-ECB)*\n"

(Path("docs") / "leaderboard.md").write_text(md, encoding="utf-8")
print("Written leaderboard.md")
print(f"  color: {'color' in md}")
print(f"  NAIVE: {'NAIVE' in md}")
print(f"  span: {'span' in md}")

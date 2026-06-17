"""Generate self-contained dashboard and report HTML from docs/data.json.

Embeds the JSON data directly into the HTML so it works without a server.
"""
import json
import csv
from pathlib import Path

DATA_PATH = Path("docs/data.json")
BACKTEST_LEADERBOARD = Path("output/malaysia/leaderboard.csv")
LEADERBOARD_PATH = Path("docs/leaderboard_full.csv")
LEADERBOARD_FALLBACK = Path("docs/leaderboard.csv")
DASHBOARD_TEMPLATE = Path("docs/dashboard.html")
REPORT_TEMPLATE = Path("docs/report_template.html")
OUT_DASHBOARD = Path("docs/dashboard_standalone.html")
OUT_REPORT = Path("docs/report.html")


def _num(row, *names, default=0.0):
    """First parseable numeric value found under any of the given column names."""
    for n in names:
        v = row.get(n)
        if v not in (None, ""):
            try:
                return float(v)
            except (ValueError, TypeError):
                pass
    return default


def load_leaderboard_csv():
    """Load the best available leaderboard CSV and normalise to dashboard rows.

    Preference order: the full multi-quarter backtest
    (output/malaysia/leaderboard.csv) → docs/leaderboard_full.csv →
    docs/leaderboard.csv. Handles both column conventions: the backtest writes
    lowercase mae/rmse/fda/n with fda as a 0-1 fraction and a `type` column
    (model/benchmark); the daily pipeline writes MAE (pp)/RMSE (pp)/FDA (%)/N
    with fda as 0-100. Benchmark rows (e.g. DOSM Advance, not comparable to the
    model metrics) are dropped when a type column is present.
    """
    for path in (BACKTEST_LEADERBOARD, LEADERBOARD_PATH, LEADERBOARD_FALLBACK):
        if path.exists():
            break
    else:
        return []
    try:
        rows = []
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("type") and row.get("type") != "model":
                    continue
                fda = _num(row, "FDA (%)", "fda")
                if "fda" in row and fda <= 1.0:
                    fda *= 100.0
                rows.append({
                    "target": row.get("target") or "GDP",
                    "model": row.get("model", ""),
                    "mae": _num(row, "MAE (pp)", "mae"),
                    "rmse": _num(row, "RMSE (pp)", "rmse"),
                    "fda": round(fda, 1),
                    "n": int(_num(row, "N", "n", default=0)),
                    "latest": _num(row, "last_nowcast"),
                })
        return rows
    except Exception:
        return []


def embed_data(template_path, out_path, data):
    """Embed JSON data into HTML template."""
    html = template_path.read_text(encoding="utf-8")
    data_json = json.dumps(data, indent=2)
    
    # Replace fetch-based loadData with embedded data
    old_fetch = """async function loadData() {
  // Try multiple paths for data.json
  const paths = [
    'data.json',
    './data.json',
    '/docs/data.json',
    'https://raw.githubusercontent.com/pengkodammaya/BM-ECB/main/docs/data.json'
  ];
  
  for (const path of paths) {
    try {
      const resp = await fetch(path);
      if (resp.ok) {
        const data = await resp.json();
        renderHero(data);
        renderComponents(data);
        renderSectors(data);
        renderEvolution(data);
        renderLeaderboard(data);
        renderRecent(data);
        return;
      }
    } catch (e) {
      // Try next path
    }
  }
  document.getElementById('hero').innerHTML = `<div class="loading">Could not load data.json. Make sure the daily update has run.</div>`;
}"""

    new_load = f"""async function loadData() {{
  const data = {data_json};
  renderHero(data);
  renderComponents(data);
  renderSectors(data);
  renderEvolution(data);
  renderLeaderboard(data);
  renderRecent(data);
}}"""

    html = html.replace(old_fetch, new_load)
    
    # For report template, replace %%DATA_JSON%% placeholder
    html = html.replace('%%DATA_JSON%%', data_json)
    
    out_path.write_text(html, encoding="utf-8")
    print(f"Written to {out_path} ({len(html)} bytes)")


def main():
    if not DATA_PATH.exists():
        print("No data.json found — run daily_update.py first.")
        return

    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    
    # If leaderboard is empty in data.json, load from leaderboard.csv
    if not data.get("leaderboard"):
        lb = load_leaderboard_csv()
        if lb:
            data["leaderboard"] = lb
            print(f"Loaded {len(lb)} entries from leaderboard.csv")
            # Persist the backfill into data.json so the copy shipped by
            # publish-dashboard.yml (which copies docs/data.json verbatim)
            # stays consistent with the embedded HTML instead of carrying
            # an empty leaderboard.
            tmp = DATA_PATH.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp.replace(DATA_PATH)
            print(f"Backfilled leaderboard written to {DATA_PATH}")

    # Generate standalone dashboard
    if DASHBOARD_TEMPLATE.exists():
        embed_data(DASHBOARD_TEMPLATE, OUT_DASHBOARD, data)

    # Generate report
    if REPORT_TEMPLATE.exists():
        embed_data(REPORT_TEMPLATE, OUT_REPORT, data)


if __name__ == "__main__":
    main()

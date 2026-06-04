"""Generate self-contained dashboard and report HTML from docs/data.json.

Embeds the JSON data directly into the HTML so it works without a server.
"""
import json
import csv
from pathlib import Path

DATA_PATH = Path("docs/data.json")
LEADERBOARD_PATH = Path("docs/leaderboard_full.csv")
LEADERBOARD_FALLBACK = Path("docs/leaderboard.csv")
DASHBOARD_TEMPLATE = Path("docs/dashboard.html")
REPORT_TEMPLATE = Path("docs/report_template.html")
OUT_DASHBOARD = Path("docs/dashboard_standalone.html")
OUT_REPORT = Path("docs/report.html")


def load_leaderboard_csv():
    """Load leaderboard_full.csv (with components) and convert to list of dicts."""
    path = LEADERBOARD_PATH if LEADERBOARD_PATH.exists() else LEADERBOARD_FALLBACK
    if not path.exists():
        return []
    try:
        rows = []
        with open(path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append({
                    "target": row.get("target", "GDP"),
                    "model": row.get("model", ""),
                    "mae": float(row.get("MAE (pp)", 0) or 0),
                    "rmse": float(row.get("RMSE (pp)", 0) or 0),
                    "fda": float(row.get("FDA (%)", 0) or 0),
                    "n": int(row.get("N", 0) or 0),
                    "latest": float(row.get("last_nowcast", 0) or 0),
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

    # Generate standalone dashboard
    if DASHBOARD_TEMPLATE.exists():
        embed_data(DASHBOARD_TEMPLATE, OUT_DASHBOARD, data)

    # Generate report
    if REPORT_TEMPLATE.exists():
        embed_data(REPORT_TEMPLATE, OUT_REPORT, data)


if __name__ == "__main__":
    main()

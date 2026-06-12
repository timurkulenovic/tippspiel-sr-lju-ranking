from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from tippspiel_crawler.extractors import to_int

TABLE_HEADERS = ["RANK", "PLAYER", "TIPS", "POINTS", "WIN PERCENTAGE"]
LJUBLJANA_TZ = ZoneInfo("Europe/Ljubljana")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export filtered ranking rows to a styled HTML report")
    parser.add_argument("--input", default="ranking.json", help="Path to ranking JSON")
    parser.add_argument("--output", default="index.html", help="Path to output HTML file")
    parser.add_argument("--office", default="Ljubljana", help="Office substring filter")
    return parser.parse_args()


def load_ranking(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    ranking = payload.get("ranking", [])
    if not isinstance(ranking, list):
        raise RuntimeError("Invalid ranking JSON: 'ranking' must be a list")
    return ranking


def filter_by_office(rows: list[dict], office_text: str) -> list[dict]:
    needle = office_text.strip().lower()
    return [
        row
        for row in rows
        if needle in str(row.get("office", "")).strip().lower() and str(row.get("player", "")).strip()
    ]


def deduplicate_by_player_keep_highest_points(rows: list[dict]) -> list[dict]:
    best_rows_by_player: dict[str, tuple[int, dict]] = {}

    for row in rows:
        player = str(row.get("player", "")).strip()
        if not player:
            continue

        key = player.casefold()
        points_value = to_int(row.get("points"))
        points_value = points_value if points_value is not None else -1

        existing = best_rows_by_player.get(key)
        if existing is None or points_value > existing[0]:
            best_rows_by_player[key] = (points_value, row)

    return [row for _, row in best_rows_by_player.values()]


def _format_value(value: object) -> str:
    if value is None:
        return "&mdash;"
    if value == "":
        return "&mdash;"
    return html.escape(str(value))


def _initials(name: str) -> str:
    parts = [part for part in name.replace("-", " ").split() if part]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _avatar_color(name: str) -> str:
    palette = ["#e11d48", "#0f766e", "#7c3aed", "#ea580c", "#2563eb", "#059669", "#dc2626", "#0891b2"]
    return palette[sum(ord(ch) for ch in name) % len(palette)]


def _first_name(name: str) -> str:
    return next((part for part in name.split() if part), "")


def _to_ljubljana_timestamp(crawled_at: str | None) -> str:
    if crawled_at:
        normalized = crawled_at.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(LJUBLJANA_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
        except ValueError:
            pass

    return datetime.now(LJUBLJANA_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")


def build_html_report(rows: list[dict], office_text: str, source_url: str | None = None, crawled_at: str | None = None) -> str:
    filtered = filter_by_office(rows, office_text)
    deduplicated = deduplicate_by_player_keep_highest_points(filtered)
    duplicates_removed = max(0, len(filtered) - len(deduplicated))
    generated_at = _to_ljubljana_timestamp(crawled_at)
    source_label = html.escape(source_url or "ranking.json")
    office_label = html.escape(office_text.strip() or "All offices")

    if deduplicated:
        body_rows = []
        for index, row in enumerate(deduplicated):
            player = str(row.get("player", "")).strip()
            player_display = _first_name(player) or player
            tips = _format_value(row.get("tips"))
            points = _format_value(row.get("points"))
            win_percent = _format_value(row.get("winPercent"))
            initials = html.escape(_initials(player))
            avatar_color = _avatar_color(player_display)
            body_rows.append(
                f"""
                <tr class="rank-row {'rank-row-alt' if index % 2 else ''}">
                  <td class="rank-cell px-4 py-4 text-slate-500 tabular-nums font-medium">{index + 1}</td>
                  <td class="px-4 py-4">
                    <div class="player-cell">
                      <span class="avatar" style="background:{avatar_color}">{initials}</span>
                      <span class="font-medium text-slate-800">{html.escape(player_display)}</span>
                    </div>
                  </td>
                  <td class="px-4 py-4 text-slate-600 tabular-nums">{tips}</td>
                  <td class="px-4 py-4 text-slate-800 tabular-nums font-semibold"><span class="metric metric-points">{points}</span></td>
                  <td class="px-4 py-4 text-slate-700 tabular-nums"><span class="metric metric-win">{win_percent}</span></td>
                </tr>
                """.strip()
            )
        table_body = "\n".join(body_rows)
    else:
        table_body = (
            "<tr><td colspan=\"5\" class=\"px-4 py-8 text-center text-slate-500\">"
            "No rows found for the selected office.</td></tr>"
        )

    headers_html = "".join(
        (
            f'<th class="rank-header px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">{html.escape(header)}</th>'
            if index == 0
            else f'<th class="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{html.escape(header)}</th>'
        )
        for index, header in enumerate(TABLE_HEADERS)
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>LAOLA Tippspiel SR LJU Ranking</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f8fafc;
      --panel: #ffffff;
      --panel-soft: #f8fafc;
      --border: #e2e8f0;
      --border-soft: #f1f5f9;
      --text: #0f172a;
      --muted: #64748b;
      --accent: #1d4ed8;
      --accent-2: #0f766e;
      --shadow: 0 10px 35px rgba(15, 23, 42, 0.08);
    }}

    * {{ box-sizing: border-box; }}

    body {{
      margin: 0;
      min-height: 100vh;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: linear-gradient(180deg, #ffffff 0%, var(--bg) 100%);
      color: var(--text);
    }}

    .page {{
      max-width: 1280px;
      margin: 0 auto;
      padding: 48px 20px 72px;
    }}

    .hero {{
      margin-bottom: 28px;
    }}

    .updated-at {{
      margin: 0 0 14px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 600;
    }}

    .eyebrow {{
      margin: 0 0 10px;
      text-transform: uppercase;
      letter-spacing: 0.18em;
      font-size: 12px;
      font-weight: 700;
      color: var(--muted);
    }}

    h1 {{
      margin: 0;
      font-size: clamp(2rem, 4vw, 3.25rem);
      line-height: 1.05;
      letter-spacing: -0.04em;
    }}

    .table-card {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 24px;
      overflow: hidden;
      box-shadow: var(--shadow);
    }}

    .table-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 22px 24px 18px;
      border-bottom: 1px solid var(--border-soft);
    }}

    .table-head h2 {{
      margin: 0;
      font-size: 18px;
      letter-spacing: -0.02em;
    }}

    .table-head span {{
      color: #94a3b8;
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.12em;
    }}

    .table-wrap {{
      overflow-x: auto;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 14px;
    }}

    thead tr {{
      background: #f8fafc;
    }}

    tbody tr {{
      border-top: 1px solid var(--border-soft);
      transition: background-color 0.18s ease;
    }}

    tbody tr:hover {{
      background: #f8fafc;
    }}

    .rank-row-alt {{
      background: rgba(241, 245, 249, 0.45);
    }}

    .rank-cell {{
      text-align: center;
    }}

    .rank-header {{
      text-align: center;
    }}

    .player-cell {{
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 220px;
    }}

    .avatar {{
      width: 34px;
      height: 34px;
      border-radius: 9999px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      color: white;
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 0.04em;
      flex: 0 0 auto;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.15);
    }}

    .metric {{
      display: inline-flex;
      align-items: center;
      min-width: 54px;
      justify-content: center;
      border-radius: 9999px;
      padding: 5px 10px;
      font-weight: 700;
    }}

    .metric-points {{
      background: #fef3c7;
      color: #92400e;
    }}

    .metric-win {{
      background: #dcfce7;
      color: #166534;
    }}

    @media (max-width: 640px) {{
      .page {{ padding: 28px 12px 48px; }}
      .table-head {{ flex-direction: column; align-items: flex-start; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <header class="hero">
      <p class="eyebrow">Tippspiel ranking</p>
      <h1>LAOLA Tippspiel SR LJU Ranking</h1>
    </header>

    <p class="updated-at">Updated: {generated_at} (Europe/Ljubljana)</p>

    <section class="table-card">
      <div class="table-head">
        <h2>Leaderboard</h2>
        <span>{office_label}</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>{headers_html}</tr>
          </thead>
          <tbody>
            {table_body}
          </tbody>
        </table>
       </div>
     </section>

   </main>
 </body>
 </html>
 """


# Backwards-compatible alias for older callers.
render_html = build_html_report


def write_html(rows: list[dict], output: Path, office_text: str) -> None:
    output.write_text(build_html_report(rows, office_text), encoding="utf-8")



def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    rows = load_ranking(input_path)
    write_html(rows, output_path, args.office)
    filtered = filter_by_office(rows, args.office)
    deduplicated = deduplicate_by_player_keep_highest_points(filtered)

    print(f"Saved {len(deduplicated)} rows to {output_path}")


if __name__ == "__main__":
    main()


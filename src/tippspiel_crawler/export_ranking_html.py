from __future__ import annotations

import argparse
import csv
import html
import json
import tomllib
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from tippspiel_crawler.extractors import to_int

TABLE_HEADERS = ["RANK", "PLAYER", "KOCKAR", "TIPS", "POINTS", "WIN PERCENTAGE"]
LJUBLJANA_TZ = ZoneInfo("Europe/Ljubljana")


@dataclass(frozen=True)
class ExportSettings:
    exception_players: set[str]
    bettors: set[str]
    bettor_labels: dict[str, str]
    bettor_count: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export filtered ranking rows to a styled HTML report")
    parser.add_argument("--input", default="ranking.json", help="Path to ranking JSON")
    parser.add_argument("--output", default="index.html", help="Path to output HTML file")
    parser.add_argument("--office", default="Ljubljana", help="Office substring filter")
    parser.add_argument("--config-file", default="config.toml", help="Path to TOML config with optional export.exception_players")
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


def load_export_settings(config_path: Path) -> ExportSettings:
    # Always load bettors from bettors.csv in the same directory as config
    csv_path = config_path.parent / "bettors.csv"
    bettors: set[str] = set()
    bettor_labels: dict[str, str] = {}
    bettor_count = 0

    if csv_path.exists():
        bettors, bettor_labels, bettor_count = _load_bettors_from_csv(csv_path)

    # Load exception_players from config file
    exception_players: set[str] = set()
    if config_path.exists():
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
        export_section = data.get("export") if isinstance(data, dict) else None
        if isinstance(export_section, dict):
            raw_exceptions = export_section.get("exception_players")
            if isinstance(raw_exceptions, list):
                exception_players = {_normalize_person_name(str(name)) for name in raw_exceptions if str(name).strip()}

    return ExportSettings(
        exception_players=exception_players,
        bettors=bettors,
        bettor_labels=bettor_labels,
        bettor_count=bettor_count,
    )


def _normalize_initials(initials: str) -> str:
    return _normalize_person_name(initials).upper()


def _bettor_signature(first_name: str, initials: str) -> str:
    return f"{_normalize_person_name(first_name)}|{_normalize_initials(initials)}"


def _signature_from_full_name(full_name: str) -> str:
    return _bettor_signature(_first_name(full_name), _initials(full_name))


def _coerce_bettors_input(bettors: set[str] | None) -> tuple[set[str], dict[str, str]]:
    signatures: set[str] = set()
    labels: dict[str, str] = {}
    for raw in bettors or set():
        value = str(raw).strip()
        if not value:
            continue

        if "|" in value:
            first, initials = value.split("|", 1)
            signature = _bettor_signature(first, initials)
            label = f"{first.strip()} ({_normalize_initials(initials)})"
        else:
            signature = _signature_from_full_name(value)
            label = f"{_first_name(value)} ({_initials(value)})"

        signatures.add(signature)
        labels[signature] = label

    return signatures, labels


def _load_bettors_from_csv(path: Path) -> tuple[set[str], dict[str, str], int]:
    signatures: set[str] = set()
    labels: dict[str, str] = {}
    row_count = 0

    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))

    if rows and len(rows[0]) >= 2:
        first = rows[0][0].strip().casefold()
        second = rows[0][1].strip().casefold()
        if first == "first_name" and second == "initials":
            rows = rows[1:]

    for row in rows:
        if len(row) < 2:
            continue
        first_name = row[0].strip()
        initials = row[1].strip()
        if not first_name or not initials:
            continue
        signature = _bettor_signature(first_name, initials)
        signatures.add(signature)
        labels[signature] = f"{first_name} ({_normalize_initials(initials)})"
        row_count += 1

    return signatures, labels, row_count


def _normalize_person_name(name: str) -> str:
    collapsed = " ".join(name.strip().split())
    normalized = unicodedata.normalize("NFKD", collapsed)
    without_diacritics = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return without_diacritics.casefold()


def deduplicate_by_player_keep_highest_points(rows: list[dict], exception_players: set[str] | None = None) -> list[dict]:
    exceptions = exception_players or set()
    best_rows_by_player: dict[str, tuple[int, dict, int]] = {}
    exception_rows: list[tuple[int, dict]] = []

    for index, row in enumerate(rows):
        player = str(row.get("player", "")).strip()
        if not player:
            continue

        key = _normalize_person_name(player)
        if key in exceptions:
            exception_rows.append((index, row))
            continue

        points_value = to_int(row.get("points"))
        points_value = points_value if points_value is not None else -1

        existing = best_rows_by_player.get(key)
        if existing is None or points_value > existing[0]:
            first_index = existing[2] if existing is not None else index
            best_rows_by_player[key] = (points_value, row, first_index)

    combined: list[tuple[int, dict]] = [(first_index, row) for _, row, first_index in best_rows_by_player.values()]
    combined.extend(exception_rows)
    combined.sort(key=lambda item: item[0])
    return [row for _, row in combined]


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
    if len(parts) == 3:
        return "".join(part[0] for part in parts).upper()
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


def _is_bettor(name: str, bettors: set[str] | None) -> bool:
    if not bettors:
        return False
    return _signature_from_full_name(name) in bettors


MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def _compute_ranks(rows: list[dict]) -> list[int]:
    """Standard competition ranking (1,2,2,4) based on descending points."""
    ranks: list[int] = []
    rank = 1
    for i, row in enumerate(rows):
        if i == 0:
            ranks.append(1)
        else:
            prev_pts = to_int(rows[i - 1].get("points")) or 0
            curr_pts = to_int(row.get("points")) or 0
            if curr_pts < prev_pts:
                rank = i + 1
            ranks.append(rank)
    return ranks


def build_html_report(
    rows: list[dict],
    office_text: str,
    crawled_at: str | None = None,
    exception_players: set[str] | None = None,
    bettors: set[str] | None = None,
    bettor_labels: dict[str, str] | None = None,
    bettors_count: int | None = None,
) -> str:
    filtered = filter_by_office(rows, office_text)
    deduplicated = deduplicate_by_player_keep_highest_points(filtered, exception_players=exception_players)
    normalized_bettors, normalized_bettor_labels = _coerce_bettors_input(bettors)
    if bettor_labels:
        normalized_bettor_labels = {**normalized_bettor_labels, **bettor_labels}
    effective_bettor_count = bettors_count if bettors_count is not None else len(normalized_bettors)
    generated_at = _to_ljubljana_timestamp(crawled_at)
    office_label = html.escape(office_text.strip() or "All offices")
    matched_bettors: set[str] = set()

    if deduplicated:
        body_rows = []
        ranks = _compute_ranks(deduplicated)
        for index, row in enumerate(deduplicated):
            player = str(row.get("player", "")).strip()
            # IMPORTANT: determine bettor status from the full player name before any display shortening.
            is_bettor = _is_bettor(player, normalized_bettors)
            if is_bettor:
                matched_bettors.add(_signature_from_full_name(player))
            player_display = _first_name(player) or player
            tips = _format_value(row.get("tips"))
            points = _format_value(row.get("points"))
            win_percent = _format_value(row.get("winPercent"))
            gambler_display = "💸" if is_bettor else ""
            initials = html.escape(_initials(player))
            avatar_color = _avatar_color(player_display)
            rank = ranks[index]
            medal = MEDALS.get(rank)
            if medal:
                rank_cell = f'<span class="medal" title="Rank {rank}">{medal}</span>'
            else:
                rank_cell = str(rank)
            points_int = to_int(row.get("points"))
            points_int = points_int if points_int is not None else -1
            body_rows.append(
                f"""
                <tr class="rank-row {'rank-row-alt' if index % 2 else ''}" data-bettor="{'1' if is_bettor else '0'}" data-points="{points_int}">
                  <td class="rank-cell px-4 py-4 text-slate-500 tabular-nums font-medium" data-rank-cell="1">{rank_cell}</td>
                  <td class="px-4 py-4">
                    <div class="player-cell">
                      <span class="avatar" style="background:{avatar_color}">{initials}</span>
                      <span class="font-medium text-slate-800">{html.escape(player_display)}</span>
                    </div>
                  </td>
                  <td class="px-4 py-4 text-slate-700 tabular-nums"><span class="bettor-flag">{gambler_display}</span></td>
                  <td class="px-4 py-4 text-slate-600 tabular-nums">{tips}</td>
                  <td class="px-4 py-4 text-slate-800 tabular-nums font-semibold"><span class="metric metric-points">{points}</span></td>
                  <td class="px-4 py-4 text-slate-700 tabular-nums"><span class="metric metric-win">{win_percent}</span></td>
                </tr>
                """.strip()
            )
        table_body = "\n".join(body_rows)
    else:
        table_body = (
            "<tr><td colspan=\"6\" class=\"px-4 py-8 text-center text-slate-500\">"
            "No rows found for the selected office.</td></tr>"
        )

    missing_bettors = normalized_bettors - matched_bettors if deduplicated else normalized_bettors
    missing_bettors_html = ""
    if missing_bettors:
        missing_items = "".join(
            f'<li class="missing-bettor-item">{html.escape(normalized_bettor_labels.get(signature, signature))}</li>'
            for signature in sorted(missing_bettors)
        )
        missing_bettors_html = f"""
    <div id="missingBettorsSection" class="missing-bettors-section" style="display:none;">
      <h3>Kockarji not found in LAOLA ranking</h3>
      <ul class="missing-bettors-list">
        {missing_items}
      </ul>
    </div>
    """

    bettors_summary_html = f"""
    <div id="bettorsSummary" class="bettors-summary" data-bettors-count="{effective_bettor_count}" style="display:none;">
      <h3>Kockarji Betting Pool and Prizes</h3>
      <p>Total bet amount: <strong id="bettorsTotal">0.00€</strong> (<span id="bettorsCount">0</span> x 15€)</p>
      <p>🥇 1st place (50%): <strong id="prize1">0.00€</strong></p>
      <p>🥈 2nd place (30%): <strong id="prize2">0.00€</strong></p>
      <p>🥉 3rd place (20%): <strong id="prize3">0.00€</strong></p>
    </div>
    """

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

    .table-controls {{
      display: flex;
      justify-content: center;
      align-items: center;
      gap: 12px;
      margin: 0 0 10px;
    }}

    .toggle-label {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      user-select: none;
    }}

    .toggle-label.active {{
      color: var(--text);
    }}

    .ios-toggle {{
      border: 0;
      background: transparent;
      padding: 0;
      cursor: pointer;
    }}

    .ios-track {{
      width: 52px;
      height: 30px;
      border-radius: 9999px;
      background: #cbd5e1;
      display: inline-flex;
      align-items: center;
      padding: 3px;
      transition: background-color 0.2s ease;
      box-shadow: inset 0 0 0 1px rgba(15, 23, 42, 0.08);
    }}

    .ios-thumb {{
      width: 24px;
      height: 24px;
      border-radius: 9999px;
      background: #fff;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25);
      transition: transform 0.2s ease;
    }}

    .ios-toggle.active .ios-track {{
      background: #16a34a;
    }}

    .ios-toggle.active .ios-thumb {{
      transform: translateX(22px);
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

    .bettor-flag {{
      font-size: 12px;
      font-weight: 800;
      letter-spacing: 0.08em;
      color: #b45309;
      display: inline-flex;
      min-width: 42px;
      justify-content: center;
    }}

    .medal {{
      font-size: 20px;
      line-height: 1;
    }}

    .missing-bettors-section {{
      margin-top: 24px;
      padding: 12px;
      background: #fef2f2;
      border: 1px solid #fecaca;
      border-radius: 12px;
    }}

    .missing-bettors-section h3 {{
      margin: 0 0 8px;
      font-size: 12px;
      font-weight: 700;
      color: #991b1b;
    }}

    .missing-bettors-list {{
      margin: 0;
      padding-left: 20px;
      list-style-position: inside;
    }}

    .missing-bettor-item {{
      font-size: 11px;
      color: #7f1d1d;
      line-height: 1.4;
    }}

    .bettors-summary {{
      margin-top: 16px;
      padding: 16px;
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 12px;
    }}

    .bettors-summary h3 {{
      margin: 0 0 8px;
      font-size: 14px;
      font-weight: 700;
      color: #0f172a;
    }}

    .bettors-summary p {{
      margin: 4px 0;
      font-size: 13px;
      color: #1e293b;
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

    <div class="table-controls">
      <span id="toggleLabelAll" class="toggle-label">ALL PLAYERS</span>
      <button id="bettorToggle" class="ios-toggle active" type="button" role="switch" aria-checked="true" aria-label="Filter bettors only">
        <span class="ios-track"><span class="ios-thumb"></span></span>
      </button>
      <span id="toggleLabelBettors" class="toggle-label active">💸 KOCKARJI ONLY</span>
    </div>

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

      {bettors_summary_html}
      {missing_bettors_html}
   </main>
   <script>
     (() => {{
       const toggle = document.getElementById("bettorToggle");
       const labelAll = document.getElementById("toggleLabelAll");
       const labelBettors = document.getElementById("toggleLabelBettors");
       const missingSection = document.getElementById("missingBettorsSection");
       const bettorsSummary = document.getElementById("bettorsSummary");
       const bettorsCount = document.getElementById("bettorsCount");
       const bettorsTotal = document.getElementById("bettorsTotal");
       const prize1 = document.getElementById("prize1");
       const prize2 = document.getElementById("prize2");
       const prize3 = document.getElementById("prize3");
       const rows = Array.from(document.querySelectorAll("tbody tr.rank-row"));
       if (!toggle || !labelAll || !labelBettors || rows.length === 0) return;

       const medalForRank = (rank) => ({{ 1: "🥇", 2: "🥈", 3: "🥉" }})[rank] || null;

       const applyRanks = (visibleRows) => {{
         let prevPoints = null;
         let currentRank = 1;
         visibleRows.forEach((row, idx) => {{
           const points = Number(row.getAttribute("data-points") || "-1");
           if (idx === 0) {{
             currentRank = 1;
           }} else if (prevPoints !== null && points < prevPoints) {{
             currentRank = idx + 1;
           }}

           const medal = medalForRank(currentRank);
           const rankCell = row.querySelector('[data-rank-cell="1"]');
           if (rankCell) {{
             rankCell.innerHTML = medal
               ? `<span class="medal" title="Rank ${{currentRank}}">${{medal}}</span>`
               : String(currentRank);
           }}
           prevPoints = points;
         }});
       }};

       let bettorsOnly = true;

       const render = () => {{
         labelAll.classList.toggle("active", !bettorsOnly);
         labelBettors.classList.toggle("active", bettorsOnly);
         labelBettors.textContent = "💸 KOCKARJI ONLY";
         toggle.classList.toggle("active", bettorsOnly);
         toggle.setAttribute("aria-checked", bettorsOnly ? "true" : "false");
         rows.forEach((row) => {{
           const isBettor = row.getAttribute("data-bettor") === "1";
           row.style.display = !bettorsOnly || isBettor ? "" : "none";
         }});
         const visibleRows = rows.filter((row) => row.style.display !== "none");
         applyRanks(visibleRows);

          if (missingSection) {{
            missingSection.style.display = bettorsOnly ? "" : "none";
          }}

          if (bettorsSummary) {{
            bettorsSummary.style.display = bettorsOnly ? "" : "none";
          }}

          if (bettorsOnly && bettorsCount && bettorsTotal && prize1 && prize2 && prize3) {{
            const count = Number((bettorsSummary && bettorsSummary.getAttribute("data-bettors-count")) || "0");
            const total = count * 15;
            const formatMoney = (value) => `${{value.toFixed(2)}}€`;
            bettorsCount.textContent = String(count);
            bettorsTotal.textContent = formatMoney(total);
            prize1.textContent = formatMoney(total * 0.5);
            prize2.textContent = formatMoney(total * 0.3);
            prize3.textContent = formatMoney(total * 0.2);
          }}
       }};

       toggle.addEventListener("click", () => {{
         bettorsOnly = !bettorsOnly;
         render();
       }});

       render();
     }})();
   </script>
 </body>
 </html>
 """


# Backwards-compatible alias for older callers.
render_html = build_html_report


def write_html(
    rows: list[dict],
    output: Path,
    office_text: str,
    bettors: set[str] | None = None,
    bettor_labels: dict[str, str] | None = None,
    bettors_count: int | None = None,
) -> None:
    output.write_text(
        build_html_report(rows, office_text, bettors=bettors, bettor_labels=bettor_labels, bettors_count=bettors_count),
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    config_path = Path(args.config_file)

    rows = load_ranking(input_path)
    settings = load_export_settings(config_path)
    write_html(
        rows,
        output_path,
        args.office,
        bettors=settings.bettors,
        bettor_labels=settings.bettor_labels,
        bettors_count=settings.bettor_count,
    )
    filtered = filter_by_office(rows, args.office)
    deduplicated = deduplicate_by_player_keep_highest_points(filtered)

    print(f"Saved {len(deduplicated)} rows to {output_path}")


if __name__ == "__main__":
    main()


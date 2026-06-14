from __future__ import annotations

import argparse
import csv
import json
import tomllib
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from tippspiel_crawler.extractors import to_int

LJUBLJANA_TZ = ZoneInfo("Europe/Ljubljana")


@dataclass(frozen=True)
class ExportSettings:
    exception_players: set[str]
    bettors: set[str]
    bettor_labels: dict[str, str]
    bettor_count: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare Ljubljana ranking JSON for frontend rendering")
    parser.add_argument("--input", default="ranking.json", help="Path to raw ranking JSON")
    parser.add_argument("--output", default="ljubljana_ranking.json", help="Path to prepared Ljubljana ranking JSON")
    parser.add_argument("--office", default="Ljubljana", help="Office substring filter")
    parser.add_argument("--config-file", default="config.toml", help="Path to TOML config with optional export.exception_players")
    return parser.parse_args()


def load_json_payload(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Invalid JSON payload: expected an object")
    return payload


def filter_by_office(rows: list[dict], office_text: str) -> list[dict]:
    needle = office_text.strip().lower()
    return [
        row
        for row in rows
        if needle in str(row.get("office", "")).strip().lower() and str(row.get("player", "")).strip()
    ]


def load_export_settings(config_path: Path) -> ExportSettings:
    csv_path = config_path.parent / "bettors.csv"
    bettors: set[str] = set()
    bettor_labels: dict[str, str] = {}
    bettor_count = 0

    if csv_path.exists():
        bettors, bettor_labels, bettor_count = _load_bettors_from_csv(csv_path)

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


def _normalize_person_name(name: str) -> str:
    collapsed = " ".join(name.strip().split())
    normalized = unicodedata.normalize("NFKD", collapsed)
    without_diacritics = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return without_diacritics.casefold()


def _normalize_initials(initials: str) -> str:
    return _normalize_person_name(initials).upper()


def _bettor_signature(first_name: str, initials: str) -> str:
    return f"{_normalize_person_name(first_name)}|{_normalize_initials(initials)}"


def _first_name(name: str) -> str:
    return next((part for part in name.split() if part), "")


def _initials(name: str) -> str:
    parts = [part for part in name.replace("-", " ").split() if part]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    if len(parts) == 3:
        return "".join(part[0] for part in parts).upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _signature_from_full_name(full_name: str) -> str:
    return _bettor_signature(_first_name(full_name), _initials(full_name))


def _is_bettor(name: str, bettors: set[str]) -> bool:
    return _signature_from_full_name(name) in bettors


def _avatar_color(name: str) -> str:
    palette = ["#e11d48", "#0f766e", "#7c3aed", "#ea580c", "#2563eb", "#059669", "#dc2626", "#0891b2"]
    return palette[sum(ord(ch) for ch in name) % len(palette)]


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


def prepare_report_payload(
    rows: list[dict],
    office_text: str,
    crawled_at: str | None,
    settings: ExportSettings,
) -> dict:
    filtered = filter_by_office(rows, office_text)
    deduplicated = deduplicate_by_player_keep_highest_points(filtered, exception_players=settings.exception_players)

    matched_bettors: set[str] = set()
    prepared_rows: list[dict] = []
    for row in deduplicated:
        player = str(row.get("player", "")).strip()
        is_bettor = _is_bettor(player, settings.bettors)
        if is_bettor:
            matched_bettors.add(_signature_from_full_name(player))

        player_display = _first_name(player) or player
        points_int = to_int(row.get("points"))
        points_int = points_int if points_int is not None else -1
        prepared_rows.append(
            {
                "playerDisplay": player_display,
                "tips": row.get("tips"),
                "points": row.get("points"),
                "pointsInt": points_int,
                "winPercent": row.get("winPercent"),
                "isBettor": is_bettor,
                "initials": _initials(player),
                "avatarColor": _avatar_color(player_display),
            }
        )

    missing_signatures = settings.bettors - matched_bettors if prepared_rows else settings.bettors
    missing_bettors = [settings.bettor_labels.get(signature, signature) for signature in sorted(missing_signatures)]
    betting_entry_fee = 15
    betting_total = settings.bettor_count * betting_entry_fee

    return {
        "office": office_text.strip() or "All offices",
        "generatedAt": _to_ljubljana_timestamp(crawled_at),
        "bettorsCount": settings.bettor_count,
        "bettingPool": {
            "entryFee": betting_entry_fee,
            "currency": "EUR",
            "totalAmount": betting_total,
            "prizes": {
                "first": betting_total * 0.5,
                "second": betting_total * 0.3,
                "third": betting_total * 0.2,
            },
        },
        "missingBettors": missing_bettors,
        "rows": prepared_rows,
    }


def write_prepared_report(payload: dict, output_path: Path) -> None:
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_prepared_report(path: Path) -> dict:
    payload = load_json_payload(path)
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise RuntimeError("Invalid prepared ranking JSON: 'rows' must be a list")
    return payload


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    config_path = Path(args.config_file)

    raw_payload = load_json_payload(input_path)
    rows = raw_payload.get("ranking", [])
    if not isinstance(rows, list):
        raise RuntimeError("Invalid ranking JSON: 'ranking' must be a list")

    settings = load_export_settings(config_path)
    prepared_payload = prepare_report_payload(
        rows,
        args.office,
        crawled_at=str(raw_payload.get("crawledAt")) if raw_payload.get("crawledAt") is not None else None,
        settings=settings,
    )
    write_prepared_report(prepared_payload, output_path)
    print(f"Saved {len(prepared_payload.get('rows', []))} rows to {output_path}")


if __name__ == "__main__":
    main()


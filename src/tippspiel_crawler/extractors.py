from __future__ import annotations

from typing import Any


def to_int(value: Any) -> int | None:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit() or ch == "-")
    if not digits or digits == "-":
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def parse_ranking_row(
    cells: list[str],
    *,
    player_id: int | str | None = None,
) -> dict[str, int | str | None]:
    normalized = (cells + [""] * 7)[:7]
    if len(cells) >= 7:
        rank_text, name_text, office_text, tips_text, points_text, _icon, win_text = normalized
    else:
        rank_text, name_text, tips_text, points_text, _icon, win_text, _unused = normalized
        office_text = ""

    parsed: dict[str, int | str | None] = {
        "rank": to_int(rank_text),
        "player": (name_text or "").strip(),
        "office": (office_text or "").strip(),
        "tips": to_int(tips_text),
        "points": to_int(points_text),
        "winPercent": to_int(win_text),
        "bwinBonusPoints": 0,
        "laolaBonusPoints": 0,
    }
    parsed_player_id = to_int(player_id)
    if parsed_player_id is not None:
        parsed["playerId"] = parsed_player_id
    return parsed


def bonus_points_from_tip(tip: dict[str, Any]) -> int:
    for key in ("earned_points", "earnedPoints", "pointsAwarded", "points"):
        points = to_int(tip.get(key))
        if points is not None:
            return points
    return 0


def sum_bonus_points_by_customer(bonus_tip_results: list[dict[str, Any]] | None) -> tuple[int, int]:
    """Return (bwin_bonus_points, laola_bonus_points) from statistics.bonusTipResults."""
    bwin = 0
    laola = 0
    for tip in bonus_tip_results or []:
        if not isinstance(tip, dict):
            continue
        points = bonus_points_from_tip(tip)
        customer = str(tip.get("customer") or "").strip().lower()
        if customer == "bwin":
            bwin += points
        elif customer in {"", "laola", "laola1", "none", "null"}:
            # LAOLA bonus tips use null/empty customer in the API.
            laola += points
    return bwin, laola


def parse_bonus_statistics_payload(body: dict[str, Any] | None) -> tuple[int, int]:
    if not isinstance(body, dict):
        return 0, 0
    return sum_bonus_points_by_customer(body.get("bonusTipResults"))


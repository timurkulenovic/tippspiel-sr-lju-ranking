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


def parse_ranking_row(cells: list[str]) -> dict[str, int | str | None]:
    normalized = (cells + [""] * 7)[:7]
    if len(cells) >= 7:
        rank_text, name_text, office_text, tips_text, points_text, _icon, win_text = normalized
    else:
        rank_text, name_text, tips_text, points_text, _icon, win_text, _unused = normalized
        office_text = ""

    return {
        "rank": to_int(rank_text),
        "player": (name_text or "").strip(),
        "office": (office_text or "").strip(),
        "tips": to_int(tips_text),
        "points": to_int(points_text),
        "winPercent": to_int(win_text),
    }


from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

CHARACTER_SHEETS_DIR = "character_sheets"
ROLLS_FILE = "rolls.jsonl"
ROLL_KINDS = {"attack", "damage", "save", "check", "initiative", "other"}


@dataclass(frozen=True)
class DiceRollInput:
    t_ms: int
    character: str | None
    kind: str
    expression: str | None
    total: int | None
    detail: object | None
    line_number: int


def find_character_sheet_paths(session_dir: Path) -> list[Path]:
    sheets_dir = session_dir / CHARACTER_SHEETS_DIR
    if not sheets_dir.exists():
        return []
    return sorted(p for p in sheets_dir.glob("*.json") if p.is_file())


def load_character_sheet(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def find_rolls_path(session_dir: Path) -> Path | None:
    rolls_path = session_dir / ROLLS_FILE
    return rolls_path if rolls_path.exists() else None


def parse_rolls_jsonl(path: Path) -> tuple[list[DiceRollInput], list[str]]:
    rolls: list[DiceRollInput] = []
    errors: list[str] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_number}: {exc}")
            continue

        t_ms = payload.get("t_ms")
        if not isinstance(t_ms, (int, float)):
            errors.append(f"line {line_number}: missing or invalid t_ms")
            continue
        t_ms = int(t_ms)

        kind = payload.get("kind", "other")
        if not isinstance(kind, str):
            kind = "other"
        kind = kind if kind in ROLL_KINDS else "other"

        total = payload.get("total")
        if total is not None and not isinstance(total, int):
            errors.append(f"line {line_number}: invalid total")
            continue

        rolls.append(
            DiceRollInput(
                t_ms=t_ms,
                character=payload.get("character"),
                kind=kind,
                expression=payload.get("expression"),
                total=total,
                detail=payload.get("detail"),
                line_number=line_number,
            )
        )

    return rolls, errors

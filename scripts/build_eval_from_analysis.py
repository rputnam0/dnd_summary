from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEGACY_SUMMARIES = ROOT / "legacy" / "summaries"
TRANSCRIPTS = ROOT / "transcripts" / "campaigns"
OUTPUT_PATH = ROOT / "evals" / "npc_eval_from_analysis.jsonl"


NPC_SECTION_RE = re.compile(r"non-player character", re.IGNORECASE)
NEXT_SECTION_RE = re.compile(r"^(#{2,}|\*\*)\s*\d+\.", re.IGNORECASE)
NPC_BULLET_RE = re.compile(r"\*\s+\*\*(.+?)\*\*")
NPC_NAME_RE = re.compile(r"\*\s+\*\*Name:\*\*\s*(.+)")
LOCATION_SECTION_RE = re.compile(r"locations", re.IGNORECASE)
FACTION_SECTION_RE = re.compile(r"faction|organization", re.IGNORECASE)

SKIP_TOKENS = {
    "description",
    "detailed description",
    "role",
    "role and objectives",
    "key interaction",
    "key interactions & dialogue",
    "key interactions",
    "significance",
    "immediate impact",
    "campaign connection",
    "foreshadowing",
    "brief description",
    "characters present",
    "event title",
    "note",
    "function and purpose",
    "narrative significance",
    "impact",
}
ITEM_KEYWORDS = (
    "key",
    "lantern",
    "ring",
    "blade",
    "sword",
    "staff",
    "amulet",
    "helm",
    "helmet",
    "armor",
    "gauntlet",
    "shield",
    "bow",
    "spear",
    "whip",
    "potion",
    "scroll",
    "orb",
    "relic",
    "gem",
    "stone",
    "coin",
    "tome",
    "book",
    "mask",
    "crown",
    "orchid",
    "flower",
    "weapon",
    "spear",
    "whip",
    "shield",
)
LOCATION_KEYWORDS = (
    "district",
    "city",
    "dome",
    "hut",
    "forest",
    "mountain",
    "tower",
    "ruins",
    "keep",
    "castle",
    "town",
    "village",
    "isle",
    "island",
    "temple",
    "grove",
    "cavern",
    "pass",
    "road",
    "valley",
    "plains",
    "fields",
    "market",
    "core",
    "arena",
)


def _contains_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    for keyword in keywords:
        if re.search(rf"\b{re.escape(keyword)}\b", text):
            return True
    return False


def _extract_npcs(text: str) -> list[str]:
    section_match = None
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if NPC_SECTION_RE.search(line):
            section_match = idx
            break
    if section_match is None:
        return []
    section_lines = lines[section_match + 1 :]
    next_idx = None
    for idx, line in enumerate(section_lines):
        if NEXT_SECTION_RE.match(line.strip()):
            next_idx = idx
            break
    if next_idx is not None:
        section_lines = section_lines[:next_idx]

    names = []
    skip_tokens = SKIP_TOKENS
    for line in section_lines:
        match = NPC_NAME_RE.search(line)
        if match:
            name = match.group(1).strip()
            if name and name.lower() not in skip_tokens and name not in names:
                names.append(name)
            continue
        match = NPC_BULLET_RE.search(line)
        if match:
            name = match.group(1).strip()
            if name.endswith(":"):
                name = name[:-1].strip()
            if not name:
                continue
            if name.startswith("["):
                continue
            if name.lower() in skip_tokens:
                continue
            if name not in names:
                names.append(name)
    return names


def _session_slug_from_name(path: Path) -> str | None:
    match = re.search(r"session_(\d+)_analysis_output", path.name)
    if match:
        return f"session_{match.group(1)}"
    match = re.search(r"Session\s+(\d+)", str(path.parent))
    if match:
        return f"session_{match.group(1)}"
    return None


def _extract_named_bullets(lines: list[str]) -> list[str]:
    names = []
    for line in lines:
        match = NPC_BULLET_RE.search(line)
        if not match:
            continue
        name = match.group(1).strip().rstrip(":")
        if name.lower() in SKIP_TOKENS:
            continue
        if name.startswith("["):
            continue
        if name and name not in names:
            names.append(name)
    return names


def _extract_section(lines: list[str], section_re: re.Pattern) -> list[str]:
    start = None
    for idx, line in enumerate(lines):
        if section_re.search(line):
            start = idx
            break
    if start is None:
        return []
    section_lines = lines[start + 1 :]
    for idx, line in enumerate(section_lines):
        if NEXT_SECTION_RE.match(line.strip()):
            section_lines = section_lines[:idx]
            break
    return section_lines


def _extract_locations_items(text: str) -> tuple[list[str], list[str]]:
    lines = text.splitlines()
    section_lines = _extract_section(lines, LOCATION_SECTION_RE)
    names = _extract_named_bullets(section_lines)
    locations = []
    items = []
    for name in names:
        lowered = name.lower()
        if lowered in SKIP_TOKENS:
            continue
        if _contains_keyword(lowered, ITEM_KEYWORDS):
            items.append(name)
        elif _contains_keyword(lowered, LOCATION_KEYWORDS):
            locations.append(name)
        else:
            locations.append(name)
    return locations, items


def _extract_factions(text: str) -> list[str]:
    lines = text.splitlines()
    section_lines = _extract_section(lines, FACTION_SECTION_RE)
    names = _extract_named_bullets(section_lines)
    return [name for name in names if name.lower() not in SKIP_TOKENS]


def main() -> None:
    rows = []
    for analysis_path in sorted(LEGACY_SUMMARIES.rglob("*analysis_output.txt")):
        text = analysis_path.read_text(encoding="utf-8", errors="ignore")
        npcs = _extract_npcs(text)
        locations, items = _extract_locations_items(text)
        factions = _extract_factions(text)
        if not any([npcs, locations, items, factions]):
            continue
        session_slug = _session_slug_from_name(analysis_path)
        if not session_slug:
            continue
        transcript_path = (
            TRANSCRIPTS / "avarias" / "sessions" / session_slug / "transcript.txt"
        )
        if not transcript_path.exists():
            continue
        rows.append(
            {
                "transcript_path": str(transcript_path),
                "gold_npcs": npcs,
                "gold_locations": locations,
                "gold_items": items,
                "gold_factions": factions,
            }
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")

    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

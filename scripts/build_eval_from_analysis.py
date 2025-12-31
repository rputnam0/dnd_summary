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
    skip_tokens = {
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
    }
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


def main() -> None:
    rows = []
    for analysis_path in sorted(LEGACY_SUMMARIES.rglob("*analysis_output.txt")):
        text = analysis_path.read_text(encoding="utf-8", errors="ignore")
        npcs = _extract_npcs(text)
        if not npcs:
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
            }
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")

    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

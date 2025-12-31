#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path


def _slugify_session_dirname(name: str) -> str:
    """Normalize various legacy 'Session X' directory names into a stable session_slug."""
    raw = name.strip()
    lowered = raw.lower()
    lowered = re.sub(r"^seasion\b", "session", lowered)  # legacy typo
    lowered = re.sub(r"\s+", "_", lowered)
    lowered = re.sub(r"[^a-z0-9_]+", "_", lowered)
    lowered = re.sub(r"_+", "_", lowered).strip("_")

    # Prefer "session_<digits>[_suffix]" when we can parse it.
    match = re.match(r"session_(\d+)(?:_(.+))?$", lowered)
    if match:
        session_num = match.group(1)
        suffix = match.group(2)
        return f"session_{session_num}" + (f"_{suffix}" if suffix else "")

    return lowered or "session_unknown"


def _files_identical(a: Path, b: Path) -> bool:
    if a.stat().st_size != b.stat().st_size:
        return False
    with a.open("rb") as fa, b.open("rb") as fb:
        while True:
            ca = fa.read(1024 * 1024)
            cb = fb.read(1024 * 1024)
            if ca != cb:
                return False
            if not ca:
                return True


def _move_file(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))

def _canonicalize_transcripts(session_dir: Path, dry_run: bool) -> None:
    """Standardize transcript artifact names inside a session directory.

    - Choose the "best" artifact per format (largest, then newest).
    - Promote it to transcript.<ext> (jsonl/txt/srt).
    - Move other variants into extras/ (or delete if byte-identical to the canonical).
    """
    extras = session_dir / "extras"

    for ext in ("jsonl", "txt", "srt"):
        candidates = [p for p in session_dir.glob(f"*.{ext}") if p.is_file()]
        if not candidates:
            continue

        candidates.sort(key=lambda p: (p.stat().st_size, p.stat().st_mtime), reverse=True)
        canonical_name = f"transcript.{ext}"
        canonical_path = session_dir / canonical_name
        best = candidates[0]

        if canonical_path.exists() and best.resolve() != canonical_path.resolve():
            if _files_identical(best, canonical_path):
                if dry_run:
                    print(f"DRY-RUN delete duplicate {best} (identical to {canonical_path})")
                else:
                    best.unlink()
            else:
                if dry_run:
                    print(f"DRY-RUN move {best} -> {extras / best.name}")
                else:
                    extras.mkdir(parents=True, exist_ok=True)
                    _move_file(best, extras / best.name)

        elif not canonical_path.exists():
            if dry_run:
                print(f"DRY-RUN promote {best} -> {canonical_path}")
            else:
                _move_file(best, canonical_path)

        # Move any remaining variants out of the session root.
        if canonical_path.exists():
            for other in [p for p in session_dir.glob(f"*.{ext}") if p.is_file()]:
                if other.name == canonical_name:
                    continue
                if _files_identical(other, canonical_path):
                    if dry_run:
                        print(f"DRY-RUN delete duplicate {other} (identical to {canonical_path})")
                    else:
                        other.unlink()
                    continue
                if dry_run:
                    print(f"DRY-RUN move {other} -> {extras / other.name}")
                else:
                    extras.mkdir(parents=True, exist_ok=True)
                    _move_file(other, extras / other.name)


def migrate_transcripts(source_root: Path, dest_root: Path, dry_run: bool) -> None:
    if not source_root.exists():
        raise SystemExit(f"Missing source root: {source_root}")
    dest_root.mkdir(parents=True, exist_ok=True)

    for entry in sorted(source_root.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_dir():
            continue
        if entry.name.lower() == "desktop.ini":
            continue

        session_slug = _slugify_session_dirname(entry.name)
        target_dir = dest_root / session_slug
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)

        for src_file in sorted(entry.iterdir(), key=lambda p: p.name.lower()):
            if src_file.is_dir():
                continue
            if src_file.name.lower() == "desktop.ini":
                continue

            dest_file = target_dir / src_file.name
            if dest_file.exists():
                if _files_identical(src_file, dest_file):
                    if not dry_run:
                        src_file.unlink()
                    continue

                stem = dest_file.stem
                suffix = dest_file.suffix
                i = 2
                while True:
                    alt = target_dir / f"{stem}__dup{i}{suffix}"
                    if not alt.exists():
                        dest_file = alt
                        break
                    i += 1

            if dry_run:
                print(f"DRY-RUN move {src_file} -> {dest_file}")
            else:
                _move_file(src_file, dest_file)

        if not dry_run:
            # Remove empty session dirs.
            remaining = [p for p in entry.iterdir() if p.name.lower() != "desktop.ini"]
            if not remaining:
                shutil.rmtree(entry)

    # Canonicalize transcript artifacts after all moves/merges.
    for session_dir in sorted(dest_root.iterdir(), key=lambda p: p.name.lower()):
        if session_dir.is_dir():
            _canonicalize_transcripts(session_dir, dry_run=dry_run)


def main() -> None:
    ap = argparse.ArgumentParser(description="Migrate legacy Transcripts/ into transcripts/ multi-campaign layout.")
    ap.add_argument("--source", default="Transcripts", help="Legacy transcripts root (default: Transcripts)")
    ap.add_argument(
        "--dest",
        default="transcripts/campaigns/avarias/sessions",
        help="Destination sessions root (default: transcripts/campaigns/avarias/sessions)",
    )
    ap.add_argument("--dry-run", action="store_true", help="Print actions without modifying the filesystem.")
    args = ap.parse_args()

    migrate_transcripts(Path(args.source), Path(args.dest), dry_run=args.dry_run)


if __name__ == "__main__":
    main()

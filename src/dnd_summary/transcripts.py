from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator


@dataclass(frozen=True)
class ParsedUtterance:
    speaker: str
    start_ms: int
    end_ms: int
    text: str
    speaker_raw: str | None = None


def _to_ms(seconds: float) -> int:
    return int(round(seconds * 1000))


def _parse_timecode(token: str) -> int:
    match = re.match(r"^(\\d+):(\\d+):(\\d+)$", token.strip())
    if not match:
        raise ValueError(f"Invalid timestamp: {token}")
    hours, minutes, seconds = map(int, match.groups())
    return ((hours * 60 + minutes) * 60 + seconds) * 1000


def _parse_srt_timecode(token: str) -> int:
    match = re.match(r"^(\\d+):(\\d+):(\\d+),(\\d{3})$", token.strip())
    if not match:
        raise ValueError(f"Invalid SRT timestamp: {token}")
    hours, minutes, seconds, millis = map(int, match.groups())
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis


def parse_jsonl(path: Path) -> list[ParsedUtterance]:
    utterances: list[ParsedUtterance] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            speaker = str(payload.get("speaker") or "unknown").strip() or "unknown"
            speaker_raw = payload.get("speaker_raw")
            start = payload.get("start")
            end = payload.get("end")
            text = str(payload.get("text") or "").strip()
            if start is None or end is None:
                raise ValueError(f"Missing start/end in JSONL line: {payload}")
            utterances.append(
                ParsedUtterance(
                    speaker=speaker,
                    start_ms=_to_ms(float(start)),
                    end_ms=_to_ms(float(end)),
                    text=text,
                    speaker_raw=speaker_raw,
                )
            )
    return utterances


def parse_txt(path: Path) -> list[ParsedUtterance]:
    utterances: list[ParsedUtterance] = []
    line_re = re.compile(r"^(?P<speaker>.+?)\\s+(?P<ts>\\d{2}:\\d{2}:\\d{2})\\s+(?P<text>.+)$")
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            match = line_re.match(raw)
            if not match:
                raise ValueError(f"Invalid TXT transcript line: {raw}")
            speaker = match.group("speaker").strip()
            start_ms = _parse_timecode(match.group("ts"))
            text = match.group("text").strip()
            utterances.append(
                ParsedUtterance(
                    speaker=speaker or "unknown",
                    start_ms=start_ms,
                    end_ms=start_ms,
                    text=text,
                )
            )

    # Fill in end_ms using the next utterance start_ms.
    for idx, utt in enumerate(utterances):
        if idx < len(utterances) - 1:
            next_start = utterances[idx + 1].start_ms
            utterances[idx] = ParsedUtterance(
                speaker=utt.speaker,
                start_ms=utt.start_ms,
                end_ms=max(utt.start_ms, next_start),
                text=utt.text,
                speaker_raw=utt.speaker_raw,
            )
        else:
            utterances[idx] = ParsedUtterance(
                speaker=utt.speaker,
                start_ms=utt.start_ms,
                end_ms=utt.start_ms,
                text=utt.text,
                speaker_raw=utt.speaker_raw,
            )

    return utterances


def parse_srt(path: Path) -> list[ParsedUtterance]:
    utterances: list[ParsedUtterance] = []
    time_re = re.compile(r"(?P<start>\\d{2}:\\d{2}:\\d{2},\\d{3})\\s+-->\\s+(?P<end>\\d{2}:\\d{2}:\\d{2},\\d{3})")
    block: list[str] = []

    def flush_block(lines: list[str]) -> None:
        if not lines:
            return
        if len(lines) < 2:
            return
        time_line = lines[1]
        match = time_re.search(time_line)
        if not match:
            return
        start_ms = _parse_srt_timecode(match.group("start"))
        end_ms = _parse_srt_timecode(match.group("end"))
        text_lines = lines[2:]
        text = " ".join(t.strip() for t in text_lines if t.strip())
        utterances.append(
            ParsedUtterance(
                speaker="unknown",
                start_ms=start_ms,
                end_ms=end_ms,
                text=text,
            )
        )

    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            if not line.strip():
                flush_block(block)
                block = []
                continue
            block.append(line)
        flush_block(block)

    return utterances


def parse_transcript(path: Path) -> list[ParsedUtterance]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return parse_jsonl(path)
    if suffix == ".txt":
        return parse_txt(path)
    if suffix == ".srt":
        return parse_srt(path)
    raise ValueError(f"Unsupported transcript format: {path}")

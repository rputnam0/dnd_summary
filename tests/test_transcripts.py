from __future__ import annotations

from pathlib import Path

import pytest

from dnd_summary.transcripts import parse_jsonl, parse_srt, parse_transcript, parse_txt


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_parse_jsonl_reads_utterances(tmp_path):
    path = _write(
        tmp_path / "sample.jsonl",
        '{"speaker": "DM", "start": 0.0, "end": 1.5, "text": "Hello"}\n',
    )

    utterances = parse_jsonl(path)

    assert len(utterances) == 1
    assert utterances[0].speaker == "DM"
    assert utterances[0].start_ms == 0
    assert utterances[0].end_ms == 1500


def test_parse_jsonl_requires_start_end(tmp_path):
    path = _write(tmp_path / "bad.jsonl", '{"speaker": "DM", "text": "Hi"}\n')
    with pytest.raises(ValueError):
        parse_jsonl(path)


def test_parse_txt_parses_speaker_and_timecode(tmp_path):
    path = _write(
        tmp_path / "sample.txt",
        "00:00:01: Alice: Hello there\n00:00:02 Bob: Hi\n",
    )

    utterances = parse_txt(path)

    assert len(utterances) == 2
    assert utterances[0].speaker == "Alice"
    assert utterances[0].start_ms == 1000
    assert utterances[0].end_ms == 2000
    assert utterances[1].speaker == "Bob"


def test_parse_srt_parses_blocks(tmp_path):
    srt = (
        "1\n"
        "00:00:00,000 --> 00:00:01,000\n"
        "Hello\n\n"
        "2\n"
        "00:00:01,500 --> 00:00:02,000\n"
        "World\n"
    )
    path = _write(tmp_path / "sample.srt", srt)

    utterances = parse_srt(path)

    assert len(utterances) == 2
    assert utterances[0].start_ms == 0
    assert utterances[0].end_ms == 1000
    assert utterances[1].start_ms == 1500


def test_parse_transcript_routes_by_suffix(tmp_path):
    txt = _write(tmp_path / "sample.txt", "00:00:01: Hello\n")

    utterances = parse_transcript(txt)

    assert len(utterances) == 1
    assert utterances[0].text == "Hello"

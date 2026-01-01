from __future__ import annotations

from dataclasses import dataclass

import pytest

from dnd_summary.activities.summary import (
    _quote_bank,
    _strip_unapproved_quotes,
    _validate_summary_quotes,
)


@dataclass
class DummyUtterance:
    id: str
    text: str


@dataclass
class DummyQuote:
    utterance_id: str
    char_start: int | None = None
    char_end: int | None = None
    clean_text: str | None = None


def test_quote_bank_selects_best_quote():
    utterances = [DummyUtterance(id="u1", text="Hello there"), DummyUtterance(id="u2", text="Bye")]
    quotes = [
        DummyQuote(utterance_id="u1", char_start=0, char_end=5),
        DummyQuote(utterance_id="u1", char_start=0, char_end=11),
        DummyQuote(utterance_id="u2", clean_text="Bye"),
    ]

    bank = _quote_bank(utterances, quotes)

    assert "u1 ::: Hello there" in bank
    assert "u2 ::: Bye" in bank


def test_validate_summary_quotes_rejects_ids():
    with pytest.raises(ValueError):
        _validate_summary_quotes("[00:00:01] text", [])


def test_validate_summary_quotes_rejects_unapproved_quote():
    with pytest.raises(ValueError):
        _validate_summary_quotes('He said "bad quote"', ["good quote"])


def test_strip_unapproved_quotes_removes_unapproved():
    result = _strip_unapproved_quotes('He said "bad quote" and "good quote"', ["good quote"])
    assert '"good quote"' in result
    assert '"bad quote"' not in result
    assert "bad quote" in result

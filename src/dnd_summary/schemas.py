from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EvidenceSpan(BaseModel):
    utterance_id: str
    char_start: int | None = None
    char_end: int | None = None
    kind: Literal["quote", "support", "mention", "other"] = "support"
    confidence: float | None = None


class Mention(BaseModel):
    text: str
    entity_type: Literal[
        "character",
        "location",
        "item",
        "faction",
        "monster",
        "deity",
        "organization",
        "other",
    ]
    description: str | None = None
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    confidence: float | None = None


class Scene(BaseModel):
    title: str | None = None
    start_ms: int
    end_ms: int
    summary: str
    location: str | None = None
    participants: list[str] = Field(default_factory=list)
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class AtomicEvent(BaseModel):
    event_type: Literal[
        "combat",
        "social",
        "travel",
        "discovery",
        "loot",
        "economy",
        "relationship",
        "thread_update",
        "rules",
        "generic",
    ]
    start_ms: int
    end_ms: int
    summary: str
    entities: list[str] = Field(default_factory=list)
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    confidence: float | None = None


class QuoteCandidate(BaseModel):
    utterance_id: str
    char_start: int | None = None
    char_end: int | None = None
    speaker: str | None = None
    note: str | None = None


class ThreadUpdate(BaseModel):
    update_type: str
    note: str
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class ThreadCandidate(BaseModel):
    title: str
    kind: Literal["quest", "mystery", "personal_arc", "faction_arc", "other"] = "other"
    status: Literal["proposed", "active", "blocked", "completed", "failed", "abandoned"] = "proposed"
    summary: str | None = None
    updates: list[ThreadUpdate] = Field(default_factory=list)
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    confidence: float | None = None


class SessionFacts(BaseModel):
    mentions: list[Mention] = Field(default_factory=list)
    scenes: list[Scene] = Field(default_factory=list)
    events: list[AtomicEvent] = Field(default_factory=list)
    threads: list[ThreadCandidate] = Field(default_factory=list)
    quotes: list[QuoteCandidate] = Field(default_factory=list)


class SummaryBeat(BaseModel):
    title: str
    summary: str
    quote_utterance_ids: list[str] = Field(default_factory=list)


class SummaryPlan(BaseModel):
    beats: list[SummaryBeat] = Field(default_factory=list)

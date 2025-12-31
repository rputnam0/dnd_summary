from __future__ import annotations

from google.genai import types


def _evidence_schema() -> types.Schema:
    return types.Schema(
        type=types.Type.OBJECT,
        required=["utterance_id"],
        properties={
            "utterance_id": types.Schema(type=types.Type.STRING),
            "char_start": types.Schema(type=types.Type.INTEGER),
            "char_end": types.Schema(type=types.Type.INTEGER),
            "kind": types.Schema(
                type=types.Type.STRING,
                enum=["quote", "support", "mention", "other"],
            ),
            "confidence": types.Schema(type=types.Type.NUMBER),
        },
    )


def session_facts_schema() -> types.Schema:
    evidence_schema = _evidence_schema()
    return types.Schema(
        type=types.Type.OBJECT,
        required=["mentions", "scenes", "events", "threads", "quotes"],
        properties={
            "mentions": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(
                    type=types.Type.OBJECT,
                    required=["text", "entity_type", "evidence"],
                    properties={
                        "text": types.Schema(type=types.Type.STRING),
                        "entity_type": types.Schema(
                            type=types.Type.STRING,
                            enum=[
                                "character",
                                "location",
                                "item",
                                "faction",
                                "monster",
                                "deity",
                                "organization",
                                "other",
                            ],
                        ),
                        "description": types.Schema(type=types.Type.STRING),
                        "evidence": types.Schema(type=types.Type.ARRAY, items=evidence_schema),
                        "confidence": types.Schema(type=types.Type.NUMBER),
                    },
                ),
            ),
            "scenes": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(
                    type=types.Type.OBJECT,
                    required=["start_ms", "end_ms", "summary", "evidence"],
                    properties={
                        "title": types.Schema(type=types.Type.STRING),
                        "start_ms": types.Schema(type=types.Type.INTEGER),
                        "end_ms": types.Schema(type=types.Type.INTEGER),
                        "summary": types.Schema(type=types.Type.STRING),
                        "location": types.Schema(type=types.Type.STRING),
                        "participants": types.Schema(
                            type=types.Type.ARRAY,
                            items=types.Schema(type=types.Type.STRING),
                        ),
                        "evidence": types.Schema(type=types.Type.ARRAY, items=evidence_schema),
                    },
                ),
            ),
            "events": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(
                    type=types.Type.OBJECT,
                    required=["event_type", "start_ms", "end_ms", "summary", "evidence"],
                    properties={
                        "event_type": types.Schema(
                            type=types.Type.STRING,
                            enum=[
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
                            ],
                        ),
                        "start_ms": types.Schema(type=types.Type.INTEGER),
                        "end_ms": types.Schema(type=types.Type.INTEGER),
                        "summary": types.Schema(type=types.Type.STRING),
                        "entities": types.Schema(
                            type=types.Type.ARRAY,
                            items=types.Schema(type=types.Type.STRING),
                        ),
                        "evidence": types.Schema(type=types.Type.ARRAY, items=evidence_schema),
                        "confidence": types.Schema(type=types.Type.NUMBER),
                    },
                ),
            ),
            "threads": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(
                    type=types.Type.OBJECT,
                    required=["title", "kind", "status", "evidence", "updates"],
                    properties={
                        "title": types.Schema(type=types.Type.STRING),
                        "kind": types.Schema(
                            type=types.Type.STRING,
                            enum=["quest", "mystery", "personal_arc", "faction_arc", "other"],
                        ),
                        "status": types.Schema(
                            type=types.Type.STRING,
                            enum=["proposed", "active", "blocked", "completed", "failed", "abandoned"],
                        ),
                        "summary": types.Schema(type=types.Type.STRING),
                        "updates": types.Schema(
                            type=types.Type.ARRAY,
                            items=types.Schema(
                                type=types.Type.OBJECT,
                                required=["update_type", "note", "evidence", "related_event_indexes"],
                                properties={
                                    "update_type": types.Schema(type=types.Type.STRING),
                                    "note": types.Schema(type=types.Type.STRING),
                                    "related_event_indexes": types.Schema(
                                        type=types.Type.ARRAY,
                                        items=types.Schema(type=types.Type.INTEGER),
                                    ),
                                    "evidence": types.Schema(
                                        type=types.Type.ARRAY, items=evidence_schema
                                    ),
                                },
                            ),
                        ),
                        "evidence": types.Schema(type=types.Type.ARRAY, items=evidence_schema),
                        "confidence": types.Schema(type=types.Type.NUMBER),
                    },
                ),
            ),
            "quotes": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(
                    type=types.Type.OBJECT,
                    required=["utterance_id"],
                    properties={
                        "utterance_id": types.Schema(type=types.Type.STRING),
                        "char_start": types.Schema(type=types.Type.INTEGER),
                        "char_end": types.Schema(type=types.Type.INTEGER),
                        "speaker": types.Schema(type=types.Type.STRING),
                        "note": types.Schema(type=types.Type.STRING),
                        "clean_text": types.Schema(type=types.Type.STRING),
                    },
                ),
            ),
        },
    )


def summary_plan_schema() -> types.Schema:
    return types.Schema(
        type=types.Type.OBJECT,
        required=["beats"],
        properties={
            "beats": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(
                    type=types.Type.OBJECT,
                    required=["title", "summary", "quote_utterance_ids"],
                    properties={
                        "title": types.Schema(type=types.Type.STRING),
                        "summary": types.Schema(type=types.Type.STRING),
                        "quote_utterance_ids": types.Schema(
                            type=types.Type.ARRAY,
                            items=types.Schema(type=types.Type.STRING),
                        ),
                    },
                ),
            ),
        },
    )


def quotes_schema() -> types.Schema:
    return types.Schema(
        type=types.Type.OBJECT,
        required=["quotes"],
        properties={
            "quotes": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(
                    type=types.Type.OBJECT,
                    required=["utterance_id"],
                    properties={
                        "utterance_id": types.Schema(type=types.Type.STRING),
                        "char_start": types.Schema(type=types.Type.INTEGER),
                        "char_end": types.Schema(type=types.Type.INTEGER),
                        "speaker": types.Schema(type=types.Type.STRING),
                        "note": types.Schema(type=types.Type.STRING),
                        "clean_text": types.Schema(type=types.Type.STRING),
                    },
                ),
            )
        },
    )


def events_schema() -> types.Schema:
    evidence_schema = _evidence_schema()
    return types.Schema(
        type=types.Type.OBJECT,
        required=["events"],
        properties={
            "events": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(
                    type=types.Type.OBJECT,
                    required=["event_type", "start_ms", "end_ms", "summary", "evidence"],
                    properties={
                        "event_type": types.Schema(
                            type=types.Type.STRING,
                            enum=[
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
                            ],
                        ),
                        "start_ms": types.Schema(type=types.Type.INTEGER),
                        "end_ms": types.Schema(type=types.Type.INTEGER),
                        "summary": types.Schema(type=types.Type.STRING),
                        "entities": types.Schema(
                            type=types.Type.ARRAY,
                            items=types.Schema(type=types.Type.STRING),
                        ),
                        "evidence": types.Schema(type=types.Type.ARRAY, items=evidence_schema),
                        "confidence": types.Schema(type=types.Type.NUMBER),
                    },
                ),
            )
        },
    )


def semantic_search_schema() -> types.Schema:
    return types.Schema(
        type=types.Type.OBJECT,
        required=["keywords", "entities"],
        properties={
            "keywords": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.STRING),
            ),
            "entities": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.STRING),
            ),
            "notes": types.Schema(type=types.Type.STRING),
        },
    )

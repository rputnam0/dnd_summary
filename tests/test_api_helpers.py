from __future__ import annotations

from dnd_summary.api import (
    _entity_alias_changes,
    _entity_correction_maps,
    _thread_correction_maps,
)
from dnd_summary.models import Correction


def test_entity_correction_maps_collects_changes():
    corrections = [
        Correction(campaign_id="c", target_type="entity", target_id="e1", action="entity_hide"),
        Correction(
            campaign_id="c",
            target_type="entity",
            target_id="e2",
            action="entity_merge",
            payload={"into_id": "e3"},
        ),
        Correction(
            campaign_id="c",
            target_type="entity",
            target_id="e4",
            action="entity_rename",
            payload={"name": "New"},
        ),
    ]

    hidden, merge_map, rename_map = _entity_correction_maps(corrections)

    assert hidden == {"e1", "e2"}
    assert merge_map == {"e2": "e3"}
    assert rename_map == {"e4": "New"}


def test_entity_alias_changes_tracks_add_remove():
    corrections = [
        Correction(
            campaign_id="c",
            target_type="entity",
            target_id="e1",
            action="entity_alias_add",
            payload={"alias": "Bob"},
        ),
        Correction(
            campaign_id="c",
            target_type="entity",
            target_id="e1",
            action="entity_alias_remove",
            payload={"alias": "Bobby"},
        ),
    ]

    adds, removes = _entity_alias_changes(corrections, "e1")

    assert adds == {"Bob"}
    assert removes == {"Bobby"}


def test_thread_correction_maps_handles_rename_and_status():
    corrections = [
        Correction(campaign_id="c", target_type="thread", target_id="t1", action="thread_hide"),
        Correction(
            campaign_id="c",
            target_type="thread",
            target_id="t2",
            action="thread_merge",
            payload={"into_id": "t3"},
        ),
        Correction(
            campaign_id="c",
            target_type="thread",
            target_id="t4",
            action="thread_title",
            payload={"title": "New Title"},
        ),
        Correction(
            campaign_id="c",
            target_type="thread",
            target_id="t5",
            action="thread_status",
            payload={"status": "completed"},
        ),
        Correction(
            campaign_id="c",
            target_type="thread",
            target_id="t6",
            action="thread_summary",
            payload={"summary": "Done"},
        ),
    ]

    hidden, merge_map, title_map, status_map, summary_map = _thread_correction_maps(corrections)

    assert hidden == {"t1", "t2"}
    assert merge_map == {"t2": "t3"}
    assert title_map == {"t4": "New Title"}
    assert status_map == {"t5": "completed"}
    assert summary_map == {"t6": "Done"}

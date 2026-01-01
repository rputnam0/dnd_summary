from __future__ import annotations

import json
from pathlib import Path

from fastapi import status

from tests.factories import (
    create_campaign,
    create_event,
    create_participant,
    create_run,
    create_session,
    create_utterance,
)


def test_retrieval_goldens(api_client, db_session, settings_overrides):
    settings_overrides(embedding_dimensions=8, rerank_enabled=True, rerank_provider="hash")
    campaign = create_campaign(db_session, slug="alpha")
    session_obj = create_session(db_session, campaign=campaign)
    run = create_run(db_session, campaign=campaign, session_obj=session_obj)
    participant = create_participant(db_session, campaign=campaign)
    utt1 = create_utterance(
        db_session,
        session_obj=session_obj,
        participant=participant,
        utterance_id="utt-1",
        text="A goblin ambush erupts in the canyon.",
    )
    utt2 = create_utterance(
        db_session,
        session_obj=session_obj,
        participant=participant,
        utterance_id="utt-2",
        text="They recover the lost relic from the shrine.",
    )
    create_event(
        db_session,
        run=run,
        session_obj=session_obj,
        summary="Goblin ambush",
        evidence=[{"utterance_id": utt1.id, "char_start": 2, "char_end": 16}],
        entities=["Goblin"],
    )
    create_event(
        db_session,
        run=run,
        session_obj=session_obj,
        summary="Relic recovered",
        evidence=[{"utterance_id": utt2.id, "char_start": 5, "char_end": 20}],
        entities=["Relic"],
    )
    db_session.commit()

    from dnd_summary.embedding_index import build_embeddings_for_campaign

    build_embeddings_for_campaign(db_session, campaign.id, include_all_runs=True)
    db_session.commit()

    goldens_path = Path("tests/data/retrieval_goldens.jsonl")
    for line in goldens_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        query = payload["query"]
        expected = set(payload["expected_utterance_ids"])

        response = api_client.get(
            f"/campaigns/{campaign.slug}/semantic_retrieve",
            params={"q": query},
        )
        assert response.status_code == status.HTTP_200_OK
        results = response.json()["results"]
        found = False
        for item in results:
            for span in item.get("evidence", []):
                if span.get("utterance_id") in expected:
                    found = True
                    break
            if found:
                break
        assert found, f"Missing expected evidence for query: {query}"

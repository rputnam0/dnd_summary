from __future__ import annotations

import json

from fastapi import status

from tests.factories import (
    create_campaign,
    create_event,
    create_participant,
    create_run,
    create_session,
    create_utterance,
)


def test_semantic_retrieve_returns_evidence(api_client, db_session, settings_overrides):
    settings_overrides(embedding_dimensions=8)
    campaign = create_campaign(db_session, slug="alpha")
    session_obj = create_session(db_session, campaign=campaign)
    run = create_run(db_session, campaign=campaign, session_obj=session_obj)
    participant = create_participant(db_session, campaign=campaign)
    utterance = create_utterance(db_session, session_obj=session_obj, participant=participant)
    create_event(
        db_session,
        run=run,
        session_obj=session_obj,
        summary="Goblin ambush",
        evidence=[{"utterance_id": utterance.id, "char_start": 0, "char_end": 5}],
        entities=["Goblin"],
    )
    db_session.commit()

    # Build embeddings via API dependency (use hash provider).
    from dnd_summary.embedding_index import build_embeddings_for_campaign

    build_embeddings_for_campaign(db_session, campaign.id, include_all_runs=True)
    db_session.commit()

    response = api_client.get(
        f"/campaigns/{campaign.slug}/semantic_retrieve",
        params={"q": "goblin"},
    )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["results"]
    assert payload["results"][0]["evidence"]
    assert payload["evidence_utterances"]


def test_ask_campaign_returns_llm_answer(
    api_client, db_session, settings_overrides, monkeypatch
):
    settings_overrides(embedding_dimensions=8)
    campaign = create_campaign(db_session, slug="alpha")
    session_obj = create_session(db_session, campaign=campaign)
    run = create_run(db_session, campaign=campaign, session_obj=session_obj)
    participant = create_participant(db_session, campaign=campaign)
    utterance = create_utterance(db_session, session_obj=session_obj, participant=participant)
    create_event(
        db_session,
        run=run,
        session_obj=session_obj,
        summary="Goblin ambush",
        evidence=[{"utterance_id": utterance.id, "char_start": 0, "char_end": 5}],
        entities=["Goblin"],
    )
    db_session.commit()

    from dnd_summary.embedding_index import build_embeddings_for_campaign

    build_embeddings_for_campaign(db_session, campaign.id, include_all_runs=True)
    db_session.commit()

    class DummyLLM:
        def generate_json_schema(self, _prompt, schema=None):
            return json.dumps(
                {
                    "answer": "A goblin ambush happened.",
                    "citations": [{"utterance_id": utterance.id, "quote": "Hi"}],
                }
            )

    monkeypatch.setattr("dnd_summary.api.LLMClient", lambda: DummyLLM())

    response = api_client.post(
        f"/campaigns/{campaign.slug}/ask",
        json={"question": "What happened?"},
    )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["answer"]
    assert payload["citations"]

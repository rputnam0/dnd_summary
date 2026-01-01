from __future__ import annotations

from fastapi import status

from tests.factories import create_campaign, create_run, create_session, create_session_extraction


def test_summary_endpoint_includes_variants(api_client, db_session):
    campaign = create_campaign(db_session, slug="alpha")
    session_obj = create_session(db_session, campaign=campaign)
    run = create_run(db_session, campaign=campaign, session_obj=session_obj)
    create_session_extraction(
        db_session,
        run=run,
        session_obj=session_obj,
        kind="summary_text",
        payload={"text": "Main summary"},
    )
    create_session_extraction(
        db_session,
        run=run,
        session_obj=session_obj,
        kind="summary_player",
        payload={"text": "Player recap"},
    )
    db_session.commit()

    response = api_client.get(f"/sessions/{session_obj.id}/summary")

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["text"] == "Main summary"
    assert payload["variants"]["summary_player"] == "Player recap"

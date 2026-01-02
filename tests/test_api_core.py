from __future__ import annotations

from fastapi import status

from tests.factories import (
    create_campaign,
    create_entity,
    create_membership,
    create_run,
    create_session,
    create_user,
)


def _auth_headers(user_id: str) -> dict[str, str]:
    return {"X-User-Id": user_id}


def test_health(api_client):
    response = api_client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ok"}


def test_list_campaigns_scoped_to_user(api_client, db_session, settings_overrides):
    settings_overrides(auth_enabled=True)
    user = create_user(db_session, display_name="User")
    other_user = create_user(db_session, display_name="Other")
    campaign_a = create_campaign(db_session, slug="alpha")
    campaign_b = create_campaign(db_session, slug="beta")
    create_membership(db_session, campaign=campaign_a, user=user, role="player")
    create_membership(db_session, campaign=campaign_b, user=other_user, role="player")
    db_session.commit()

    response = api_client.get("/campaigns", headers=_auth_headers(user.id))

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["slug"] == "alpha"


def test_campaign_membership_endpoint(api_client, db_session, settings_overrides):
    settings_overrides(auth_enabled=True)
    campaign = create_campaign(db_session, slug="alpha")
    user = create_user(db_session, display_name="User")
    create_membership(db_session, campaign=campaign, user=user, role="player")
    db_session.commit()

    response = api_client.get(
        f"/campaigns/{campaign.slug}/me",
        headers=_auth_headers(user.id),
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["role"] == "player"


def test_spoilers_require_dm(api_client, db_session, settings_overrides):
    settings_overrides(auth_enabled=True)
    campaign = create_campaign(db_session, slug="alpha")
    dm_user = create_user(db_session, display_name="DM")
    player = create_user(db_session, display_name="Player")
    create_membership(db_session, campaign=campaign, user=dm_user, role="dm")
    create_membership(db_session, campaign=campaign, user=player, role="player")
    db_session.commit()

    payload = {
        "campaign_slug": "alpha",
        "target_type": "entity",
        "target_id": "e1",
        "reveal_session_number": 2,
    }
    response = api_client.post("/spoilers", json=payload, headers=_auth_headers(player.id))
    assert response.status_code == status.HTTP_403_FORBIDDEN

    response = api_client.post("/spoilers", json=payload, headers=_auth_headers(dm_user.id))
    assert response.status_code == status.HTTP_200_OK


def test_upload_transcript_requires_dm(api_client, db_session, settings_overrides, tmp_path):
    settings_overrides(auth_enabled=True, transcripts_root=str(tmp_path))
    campaign = create_campaign(db_session, slug="alpha")
    dm_user = create_user(db_session, display_name="DM")
    player = create_user(db_session, display_name="Player")
    create_membership(db_session, campaign=campaign, user=dm_user, role="dm")
    create_membership(db_session, campaign=campaign, user=player, role="player")
    create_session(db_session, campaign=campaign, slug="session_1")
    db_session.commit()

    files = {"file": ("transcript.txt", b"00:00:01: Hello")}
    response = api_client.post(
        f"/campaigns/{campaign.slug}/sessions/session_1/transcript",
        files=files,
        headers=_auth_headers(player.id),
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN

    response = api_client.post(
        f"/campaigns/{campaign.slug}/sessions/session_1/transcript",
        files=files,
        headers=_auth_headers(dm_user.id),
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["bytes"] > 0


def test_create_session_requires_dm(api_client, db_session, settings_overrides):
    settings_overrides(auth_enabled=True)
    campaign = create_campaign(db_session, slug="alpha")
    dm_user = create_user(db_session, display_name="DM")
    player = create_user(db_session, display_name="Player")
    create_membership(db_session, campaign=campaign, user=dm_user, role="dm")
    create_membership(db_session, campaign=campaign, user=player, role="player")
    db_session.commit()

    payload = {
        "slug": "session_9",
        "title": "The Crossing",
        "occurred_at": "2024-01-05",
    }
    response = api_client.post(
        f"/campaigns/{campaign.slug}/sessions",
        json=payload,
        headers=_auth_headers(player.id),
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN

    response = api_client.post(
        f"/campaigns/{campaign.slug}/sessions",
        json=payload,
        headers=_auth_headers(dm_user.id),
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["slug"] == "session_9"
    assert data["title"] == "The Crossing"
    assert data["occurred_at"].startswith("2024-01-05")


def test_create_session_validates_required_fields(api_client, db_session, settings_overrides):
    settings_overrides(auth_enabled=True)
    campaign = create_campaign(db_session, slug="alpha")
    dm_user = create_user(db_session, display_name="DM")
    create_membership(db_session, campaign=campaign, user=dm_user, role="dm")
    db_session.commit()

    payload = {
        "slug": "session_10",
        "title": "",
        "occurred_at": "",
    }
    response = api_client.post(
        f"/campaigns/{campaign.slug}/sessions",
        json=payload,
        headers=_auth_headers(dm_user.id),
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_list_sessions_includes_latest_run(api_client, db_session, settings_overrides):
    settings_overrides(auth_enabled=True)
    campaign = create_campaign(db_session, slug="alpha")
    user = create_user(db_session, display_name="DM")
    create_membership(db_session, campaign=campaign, user=user, role="dm")
    session_obj = create_session(db_session, campaign=campaign, slug="session_1")
    run = create_run(db_session, campaign=campaign, session_obj=session_obj, status="completed")
    db_session.commit()

    response = api_client.get(
        f"/campaigns/{campaign.slug}/sessions",
        headers=_auth_headers(user.id),
    )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload[0]["latest_run_id"] == run.id
    assert payload[0]["latest_run_status"] == "completed"


def test_list_sessions_surfaces_partial_status(api_client, db_session, settings_overrides):
    settings_overrides(auth_enabled=True)
    campaign = create_campaign(db_session, slug="alpha")
    user = create_user(db_session, display_name="DM")
    create_membership(db_session, campaign=campaign, user=user, role="dm")
    session_obj = create_session(db_session, campaign=campaign, slug="session_2")
    create_run(db_session, campaign=campaign, session_obj=session_obj, status="partial")
    db_session.commit()

    response = api_client.get(
        f"/campaigns/{campaign.slug}/sessions",
        headers=_auth_headers(user.id),
    )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload[0]["latest_run_status"] == "partial"


def test_list_entities_returns_entities(api_client, db_session, settings_overrides):
    settings_overrides(auth_enabled=True)
    campaign = create_campaign(db_session, slug="alpha")
    user = create_user(db_session, display_name="DM")
    create_membership(db_session, campaign=campaign, user=user, role="dm")
    create_entity(db_session, campaign=campaign, name="Goblin", entity_type="monster")
    db_session.commit()

    response = api_client.get(
        f"/campaigns/{campaign.slug}/entities",
        headers=_auth_headers(user.id),
    )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload[0]["name"] == "Goblin"


def test_admin_metrics_and_runs_require_dm(api_client, db_session, settings_overrides):
    settings_overrides(auth_enabled=True)
    campaign = create_campaign(db_session, slug="alpha")
    dm_user = create_user(db_session, display_name="DM")
    player = create_user(db_session, display_name="Player")
    create_membership(db_session, campaign=campaign, user=dm_user, role="dm")
    create_membership(db_session, campaign=campaign, user=player, role="player")
    session_obj = create_session(db_session, campaign=campaign, slug="session_1")
    create_run(db_session, campaign=campaign, session_obj=session_obj, status="partial")
    db_session.commit()

    response = api_client.get(
        f"/campaigns/{campaign.slug}/admin/metrics",
        headers=_auth_headers(player.id),
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN

    response = api_client.get(
        f"/campaigns/{campaign.slug}/admin/metrics",
        headers=_auth_headers(dm_user.id),
    )
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["runs_by_status"]["partial"] == 1

    response = api_client.get(
        f"/campaigns/{campaign.slug}/admin/runs",
        headers=_auth_headers(dm_user.id),
    )
    assert response.status_code == status.HTTP_200_OK
    runs = response.json()
    assert runs[0]["status"] == "partial"

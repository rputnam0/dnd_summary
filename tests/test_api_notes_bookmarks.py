from __future__ import annotations

from fastapi import status

from tests.factories import create_campaign, create_membership, create_session, create_user


def _auth_headers(user_id: str) -> dict[str, str]:
    return {"X-User-Id": user_id}


def test_notes_and_bookmarks_scoped_to_user(
    api_client, db_session, settings_overrides
):
    settings_overrides(auth_enabled=True)
    campaign = create_campaign(db_session, slug="alpha")
    session_obj = create_session(db_session, campaign=campaign)
    user1 = create_user(db_session, display_name="User 1")
    user2 = create_user(db_session, display_name="User 2")
    dm_user = create_user(db_session, display_name="DM")
    create_membership(db_session, campaign=campaign, user=user1, role="player")
    create_membership(db_session, campaign=campaign, user=user2, role="player")
    create_membership(db_session, campaign=campaign, user=dm_user, role="dm")
    db_session.commit()

    note_payload = {
        "campaign_slug": "alpha",
        "session_id": session_obj.id,
        "target_type": "entity",
        "target_id": "e1",
        "body": "Note body",
    }
    response1 = api_client.post("/notes", json=note_payload, headers=_auth_headers(user1.id))
    response2 = api_client.post("/notes", json=note_payload, headers=_auth_headers(user2.id))
    assert response1.status_code == status.HTTP_200_OK
    assert response2.status_code == status.HTTP_200_OK

    list_user1 = api_client.get(
        "/notes",
        params={"campaign_slug": "alpha"},
        headers=_auth_headers(user1.id),
    )
    assert list_user1.status_code == status.HTTP_200_OK
    assert len(list_user1.json()) == 1
    assert list_user1.json()[0]["created_by"] == user1.id

    list_dm = api_client.get(
        "/notes",
        params={"campaign_slug": "alpha"},
        headers=_auth_headers(dm_user.id),
    )
    assert list_dm.status_code == status.HTTP_200_OK
    assert len(list_dm.json()) == 2

    bookmark_payload = {
        "campaign_slug": "alpha",
        "session_id": session_obj.id,
        "target_type": "event",
        "target_id": "evt-1",
    }
    response1 = api_client.post(
        "/bookmarks", json=bookmark_payload, headers=_auth_headers(user1.id)
    )
    response2 = api_client.post(
        "/bookmarks", json=bookmark_payload, headers=_auth_headers(user2.id)
    )
    assert response1.status_code == status.HTTP_200_OK
    assert response2.status_code == status.HTTP_200_OK

    list_user2 = api_client.get(
        "/bookmarks",
        params={"campaign_slug": "alpha"},
        headers=_auth_headers(user2.id),
    )
    assert list_user2.status_code == status.HTTP_200_OK
    assert len(list_user2.json()) == 1
    assert list_user2.json()[0]["created_by"] == user2.id

    list_dm_bookmarks = api_client.get(
        "/bookmarks",
        params={"campaign_slug": "alpha"},
        headers=_auth_headers(dm_user.id),
    )
    assert list_dm_bookmarks.status_code == status.HTTP_200_OK
    assert len(list_dm_bookmarks.json()) == 2

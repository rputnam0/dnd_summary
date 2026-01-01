from __future__ import annotations

from datetime import datetime

from dnd_summary.models import (
    Artifact,
    Bookmark,
    Campaign,
    CampaignMembership,
    CampaignThread,
    Entity,
    EntityAlias,
    Event,
    Mention,
    Participant,
    ParticipantCharacter,
    Quote,
    Run,
    RunStep,
    Scene,
    Session,
    SessionExtraction,
    Thread,
    ThreadUpdate,
    Utterance,
    User,
    Embedding,
)


def create_campaign(session, *, slug: str = "test-campaign", name: str = "Test Campaign"):
    campaign = Campaign(slug=slug, name=name)
    session.add(campaign)
    session.flush()
    return campaign


def create_user(session, *, display_name: str = "Test User"):
    user = User(display_name=display_name)
    session.add(user)
    session.flush()
    return user


def create_membership(session, *, campaign: Campaign, user: User, role: str = "player"):
    membership = CampaignMembership(campaign_id=campaign.id, user_id=user.id, role=role)
    session.add(membership)
    session.flush()
    return membership


def create_session(
    session,
    *,
    campaign: Campaign,
    slug: str = "session_1",
    session_number: int | None = 1,
):
    session_obj = Session(
        campaign_id=campaign.id,
        slug=slug,
        session_number=session_number,
    )
    session.add(session_obj)
    session.flush()
    return session_obj


def create_run(
    session,
    *,
    campaign: Campaign,
    session_obj: Session,
    transcript_hash: str = "hash",
    status: str = "completed",
):
    run = Run(
        campaign_id=campaign.id,
        session_id=session_obj.id,
        transcript_hash=transcript_hash,
        status=status,
        finished_at=datetime.utcnow(),
    )
    session.add(run)
    session.flush()
    return run


def create_participant(
    session,
    *,
    campaign: Campaign,
    display_name: str = "Alice",
):
    participant = Participant(campaign_id=campaign.id, display_name=display_name)
    session.add(participant)
    session.flush()
    return participant


def create_utterance(
    session,
    *,
    session_obj: Session,
    participant: Participant,
    start_ms: int = 0,
    end_ms: int = 1000,
    text: str = "Hello",
    utterance_id: str | None = None,
):
    utterance = Utterance(
        id=utterance_id,
        session_id=session_obj.id,
        participant_id=participant.id,
        start_ms=start_ms,
        end_ms=end_ms,
        speaker_raw=participant.display_name,
        text=text,
    )
    session.add(utterance)
    session.flush()
    return utterance


def create_entity(
    session,
    *,
    campaign: Campaign,
    name: str = "Goblin",
    entity_type: str = "monster",
):
    entity = Entity(campaign_id=campaign.id, canonical_name=name, entity_type=entity_type)
    session.add(entity)
    session.flush()
    return entity


def create_entity_alias(session, *, entity: Entity, alias: str = "Green Menace"):
    alias_row = EntityAlias(entity_id=entity.id, alias=alias)
    session.add(alias_row)
    session.flush()
    return alias_row


def create_mention(
    session,
    *,
    run: Run,
    session_obj: Session,
    text: str = "Goblin",
    entity_type: str = "monster",
    evidence: list[dict] | None = None,
):
    mention = Mention(
        run_id=run.id,
        session_id=session_obj.id,
        text=text,
        entity_type=entity_type,
        evidence=evidence or [],
    )
    session.add(mention)
    session.flush()
    return mention


def create_event(
    session,
    *,
    run: Run,
    session_obj: Session,
    summary: str = "Fight",
    event_type: str = "combat",
    evidence: list[dict] | None = None,
    entities: list[str] | None = None,
):
    event = Event(
        run_id=run.id,
        session_id=session_obj.id,
        event_type=event_type,
        summary=summary,
        start_ms=0,
        end_ms=1000,
        evidence=evidence or [],
        entities=entities or [],
    )
    session.add(event)
    session.flush()
    return event


def create_scene(
    session,
    *,
    run: Run,
    session_obj: Session,
    summary: str = "Scene",
    evidence: list[dict] | None = None,
    participants: list[str] | None = None,
):
    scene = Scene(
        run_id=run.id,
        session_id=session_obj.id,
        summary=summary,
        start_ms=0,
        end_ms=1000,
        evidence=evidence or [],
        participants=participants or [],
    )
    session.add(scene)
    session.flush()
    return scene


def create_thread(
    session,
    *,
    run: Run,
    session_obj: Session,
    title: str = "Quest",
    kind: str = "quest",
    status: str = "active",
    evidence: list[dict] | None = None,
):
    thread = Thread(
        run_id=run.id,
        session_id=session_obj.id,
        title=title,
        kind=kind,
        status=status,
        evidence=evidence or [],
    )
    session.add(thread)
    session.flush()
    return thread


def create_thread_update(
    session,
    *,
    run: Run,
    session_obj: Session,
    thread: Thread,
    update_type: str = "progress",
    note: str = "Did something",
    evidence: list[dict] | None = None,
):
    update = ThreadUpdate(
        run_id=run.id,
        session_id=session_obj.id,
        thread_id=thread.id,
        update_type=update_type,
        note=note,
        evidence=evidence or [],
    )
    session.add(update)
    session.flush()
    return update


def create_quote(
    session,
    *,
    run: Run,
    session_obj: Session,
    utterance_id: str,
    char_start: int | None = None,
    char_end: int | None = None,
    clean_text: str | None = None,
):
    quote = Quote(
        run_id=run.id,
        session_id=session_obj.id,
        utterance_id=utterance_id,
        char_start=char_start,
        char_end=char_end,
        clean_text=clean_text,
    )
    session.add(quote)
    session.flush()
    return quote


def create_session_extraction(
    session,
    *,
    run: Run,
    session_obj: Session,
    kind: str,
    payload: dict,
    model: str = "test-model",
):
    extraction = SessionExtraction(
        run_id=run.id,
        session_id=session_obj.id,
        kind=kind,
        model=model,
        prompt_id="test",
        prompt_version="1",
        payload=payload,
    )
    session.add(extraction)
    session.flush()
    return extraction


def create_artifact(
    session,
    *,
    run: Run,
    session_obj: Session,
    kind: str = "summary_text",
    path: str = "/tmp/summary.txt",
):
    artifact = Artifact(
        run_id=run.id,
        session_id=session_obj.id,
        kind=kind,
        path=path,
    )
    session.add(artifact)
    session.flush()
    return artifact


def create_bookmark(
    session,
    *,
    campaign: Campaign,
    session_obj: Session | None,
    target_type: str = "event",
    target_id: str = "target",
    created_by: str | None = None,
):
    bookmark = Bookmark(
        campaign_id=campaign.id,
        session_id=session_obj.id if session_obj else None,
        target_type=target_type,
        target_id=target_id,
        created_by=created_by,
    )
    session.add(bookmark)
    session.flush()
    return bookmark


def create_campaign_thread(
    session,
    *,
    campaign: Campaign,
    canonical_title: str = "Quest",
    kind: str = "quest",
    status: str = "active",
):
    thread = CampaignThread(
        campaign_id=campaign.id,
        canonical_title=canonical_title,
        kind=kind,
        status=status,
    )
    session.add(thread)
    session.flush()
    return thread


def create_run_step(
    session,
    *,
    run: Run,
    session_obj: Session,
    name: str = "step",
    status: str = "running",
):
    step = RunStep(
        run_id=run.id,
        session_id=session_obj.id,
        name=name,
        status=status,
    )
    session.add(step)
    session.flush()
    return step


def create_embedding(
    session,
    *,
    campaign: Campaign,
    target_type: str,
    target_id: str,
    embedding: list[float],
    content: str = "content",
    session_id: str | None = None,
    run_id: str | None = None,
    model: str = "text-embedding-004",
    version: str = "v1",
    provider: str | None = None,
    dimensions: int | None = None,
    normalized: bool | None = None,
):
    row = Embedding(
        campaign_id=campaign.id,
        session_id=session_id,
        run_id=run_id,
        target_type=target_type,
        target_id=target_id,
        content=content,
        embedding=embedding,
        model=model,
        version=version,
        provider=provider,
        dimensions=dimensions,
        normalized=normalized,
    )
    session.add(row)
    session.flush()
    return row

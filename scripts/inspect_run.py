from __future__ import annotations

import argparse
import json

from dnd_summary.db import get_session
from dnd_summary.models import (
    Artifact,
    Campaign,
    Event,
    Mention,
    Quote,
    Run,
    Scene,
    Session,
    SessionExtraction,
    Thread,
    ThreadUpdate,
)


def _dump(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect a session run in the DB.")
    parser.add_argument("--campaign", required=True, help="Campaign slug.")
    parser.add_argument("--session", required=True, help="Session slug.")
    args = parser.parse_args()

    with get_session() as session:
        session_obj = (
            session.query(Session)
            .join(Campaign, Session.campaign_id == Campaign.id)
            .filter(Campaign.slug == args.campaign, Session.slug == args.session)
            .first()
        )
        if not session_obj:
            raise SystemExit("Session not found.")

        run = (
            session.query(Run)
            .filter_by(session_id=session_obj.id)
            .order_by(Run.created_at.desc())
            .first()
        )
        if not run:
            raise SystemExit("Run not found.")

        mentions = session.query(Mention).filter_by(run_id=run.id).all()
        scenes = session.query(Scene).filter_by(run_id=run.id).all()
        events = session.query(Event).filter_by(run_id=run.id).all()
        threads = session.query(Thread).filter_by(run_id=run.id).all()
        updates = session.query(ThreadUpdate).filter_by(run_id=run.id).all()
        quotes = session.query(Quote).filter_by(run_id=run.id).all()
        artifacts = session.query(Artifact).filter_by(run_id=run.id).all()
        extractions = session.query(SessionExtraction).filter_by(run_id=run.id).all()

        print(f"run_id={run.id}")
        print(f"session_id={session_obj.id}")
        print(f"transcript_hash={run.transcript_hash}")
        print(f"mentions={len(mentions)} scenes={len(scenes)} events={len(events)}")
        print(f"threads={len(threads)} updates={len(updates)} quotes={len(quotes)}")
        print(f"artifacts={len(artifacts)} extractions={len(extractions)}")

        print("\nSample mentions:")
        for mention in mentions[:5]:
            print(
                _dump(
                    {
                        "text": mention.text,
                        "entity_type": mention.entity_type,
                        "confidence": mention.confidence,
                    }
                )
            )

        print("\nSample events:")
        for event in events[:3]:
            print(
                _dump(
                    {
                        "event_type": event.event_type,
                        "summary": event.summary,
                        "entities": event.entities,
                        "evidence": event.evidence,
                    }
                )
            )

        print("\nThreads + updates:")
        for thread in threads:
            thread_updates = [u for u in updates if u.thread_id == thread.id]
            print(
                _dump(
                    {
                        "title": thread.title,
                        "status": thread.status,
                        "updates": [
                            {
                                "update_type": u.update_type,
                                "note": u.note,
                                "related_event_ids": u.related_event_ids,
                            }
                            for u in thread_updates
                        ],
                    }
                )
            )

        print("\nArtifacts:")
        for artifact in artifacts:
            print(_dump({"kind": artifact.kind, "path": artifact.path}))

        print("\nExtractions:")
        for extraction in extractions:
            print(_dump({"kind": extraction.kind, "prompt_id": extraction.prompt_id}))


if __name__ == "__main__":
    main()

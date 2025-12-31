from __future__ import annotations

import argparse
import json

from dnd_summary.db import get_session
from dnd_summary.models import (
    Artifact,
    Campaign,
    Event,
    LLMCall,
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
        llm_calls = session.query(LLMCall).filter_by(run_id=run.id).all()
        quality = next(
            (e for e in extractions if e.kind == "quality_report"),
            None,
        )

        print(f"run_id={run.id}")
        print(f"session_id={session_obj.id}")
        print(f"transcript_hash={run.transcript_hash}")
        print(f"mentions={len(mentions)} scenes={len(scenes)} events={len(events)}")
        print(f"threads={len(threads)} updates={len(updates)} quotes={len(quotes)}")
        print(f"artifacts={len(artifacts)} extractions={len(extractions)}")
        print(f"llm_calls={len(llm_calls)}")

        if quality:
            print("\nQuality report:")
            print(_dump(quality.payload))

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

        print("\nSample quotes:")
        for quote in quotes[:3]:
            print(
                _dump(
                    {
                        "speaker": quote.speaker,
                        "clean_text": quote.clean_text,
                        "note": quote.note,
                    }
                )
            )

        print("\nSample events:")
        for event in events[:3]:
            evidence_count = len(event.evidence or [])
            span_count = sum(
                1
                for ev in (event.evidence or [])
                if ev.get("char_start") is not None and ev.get("char_end") is not None
            )
            print(
                _dump(
                    {
                        "event_type": event.event_type,
                        "summary": event.summary,
                        "entities": event.entities,
                        "evidence_count": evidence_count,
                        "evidence_with_spans": span_count,
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

        if llm_calls:
            failures = [call for call in llm_calls if call.status != "success"]
            avg_latency = sum(call.latency_ms for call in llm_calls) / len(llm_calls)
            by_kind: dict[str, int] = {}
            for call in llm_calls:
                by_kind[call.kind] = by_kind.get(call.kind, 0) + 1
            print("\nLLM calls:")
            print(
                _dump(
                    {
                        "avg_latency_ms": round(avg_latency, 2),
                        "failures": len(failures),
                        "by_kind": by_kind,
                    }
                )
            )


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse

from dnd_summary.db import get_session
from dnd_summary.models import CampaignThread, Run, Thread


def _normalize_thread_title(title: str) -> str:
    return " ".join(title.lower().split())


def _get_campaign_thread(
    session,
    *,
    campaign_id: str,
    thread: Thread,
    by_id: dict[str, CampaignThread],
    by_key: dict[tuple[str, str], CampaignThread],
) -> tuple[CampaignThread | None, bool]:
    canonical_title = _normalize_thread_title(thread.title or "")
    if thread.campaign_thread_id:
        existing = by_id.get(thread.campaign_thread_id)
        if not existing:
            existing = (
                session.query(CampaignThread)
                .filter_by(id=thread.campaign_thread_id)
                .one_or_none()
            )
            if existing:
                by_id[existing.id] = existing
                by_key[(existing.campaign_id, existing.canonical_title)] = existing
        return existing, False

    if not canonical_title:
        return None, False

    key = (campaign_id, canonical_title)
    existing = by_key.get(key)
    if not existing:
        existing = (
            session.query(CampaignThread)
            .filter_by(campaign_id=campaign_id, canonical_title=canonical_title)
            .one_or_none()
        )
        if existing:
            by_id[existing.id] = existing
            by_key[key] = existing
    if existing:
        return existing, False

    campaign_thread = CampaignThread(
        campaign_id=campaign_id,
        canonical_title=canonical_title,
        kind=thread.kind,
        status=thread.status,
        summary=thread.summary,
    )
    session.add(campaign_thread)
    session.flush()
    by_id[campaign_thread.id] = campaign_thread
    by_key[key] = campaign_thread
    return campaign_thread, True


def backfill_threads(session, threads: list[tuple[Thread, Run]], dry_run: bool) -> tuple[int, int]:
    by_id: dict[str, CampaignThread] = {}
    by_key: dict[tuple[str, str], CampaignThread] = {}
    created = 0
    updated = 0

    for thread, run in threads:
        campaign_thread, created_flag = _get_campaign_thread(
            session,
            campaign_id=run.campaign_id,
            thread=thread,
            by_id=by_id,
            by_key=by_key,
        )
        if not campaign_thread:
            continue
        if created_flag:
            created += 1
        campaign_thread.kind = thread.kind
        campaign_thread.status = thread.status
        campaign_thread.summary = thread.summary or campaign_thread.summary

        if thread.campaign_thread_id != campaign_thread.id:
            thread.campaign_thread_id = campaign_thread.id
            updated += 1

    if dry_run:
        session.rollback()
    return created, updated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", dest="campaign", default=None)
    parser.add_argument("--session", dest="session", default=None)
    parser.add_argument("--run", dest="run", default=None)
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with get_session() as session:
        query = (
            session.query(Thread, Run)
            .join(Run, Run.id == Thread.run_id)
            .order_by(Run.created_at.asc(), Thread.created_at.asc())
        )
        if args.run:
            query = query.filter(Thread.run_id == args.run)
        if args.session:
            query = query.filter(Thread.session_id == args.session)
        if args.campaign:
            query = query.filter(Run.campaign_id == args.campaign)
        rows = query.all()
        if not rows:
            print("No threads found for backfill.")
            return
        created, updated = backfill_threads(session, rows, args.dry_run)
        print(f"campaign_threads_created={created} threads_updated={updated}")
        if args.dry_run and args.commit:
            print("Refusing to commit with --dry-run.")
            session.rollback()
        elif args.commit:
            session.commit()
        else:
            session.rollback()


if __name__ == "__main__":
    main()

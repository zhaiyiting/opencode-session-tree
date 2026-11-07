import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from .load import RawData, TextEvent


@dataclass
class Thread:
    root_id: str
    title: str
    prompt: str
    updated: int
    model: Optional[str]
    agent: Optional[str]
    message_count: int
    events: list[TextEvent] = field(default_factory=list)
    fork_ids: list[str] = field(default_factory=list)
    subagent_ids: list[str] = field(default_factory=list)
    fork_titles: dict[str, str] = field(default_factory=dict)
    subagent_titles: dict[str, str] = field(default_factory=dict)
    subagent_agents: dict[str, str] = field(default_factory=dict)
    family_ids: list[str] = field(default_factory=list)
    user_text: str = ""
    assistant_text: str = ""


def _normalize_prompt(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _first_user_event(events: list[TextEvent]) -> Optional[TextEvent]:
    for event in events:
        if event.role == "user":
            return event
    return None


def _latest_assistant(events: list[TextEvent]) -> Optional[TextEvent]:
    assistants = [e for e in events if e.role == "assistant"]
    return max(assistants, key=lambda e: e.message_time) if assistants else None


def build_threads(raw: RawData) -> list[Thread]:
    by_session = defaultdict(list)
    for event in raw.texts:
        by_session[event.session_id].append(event)

    # 1. split into fork families
    families: dict[tuple, list[str]] = defaultdict(list)
    for sid, row in raw.sessions.items():
        if row.parent_id:
            continue
        events = sorted(by_session.get(sid, []), key=lambda e: (e.message_time, e.part_time))
        first = _first_user_event(events)
        if first is None:
            key = ("__no_user__", sid)
        else:
            key = (_normalize_prompt(first.text), first.message_time)
        families[key].append(sid)

    def pick_root(members: list[str]) -> str:
        return min(members, key=lambda sid: (raw.sessions[sid].time_created, sid))

    # 2. build a thread per family, using root + forks for its text
    thread_by_session: dict[str, Thread] = {}
    threads: list[Thread] = []
    for members in families.values():
        root_id = pick_root(members)
        family_ids = sorted(members, key=lambda sid: (raw.sessions[sid].time_created, sid))
        family_events = []
        for sid in family_ids:
            family_events.extend(
                sorted(by_session.get(sid, []), key=lambda e: (e.message_time, e.part_time))
            )
        family_events.sort(key=lambda e: (e.message_time, e.part_time))

        root = raw.sessions[root_id]
        first = _first_user_event(family_events)
        assistant = _latest_assistant(family_events)
        thread = Thread(
            root_id=root_id,
            title=root.title,
            prompt=first.text if first else "",
            updated=max(raw.sessions[sid].time_updated for sid in family_ids),
            model=(assistant.model if assistant else None) or root.model,
            agent=(assistant.agent if assistant else None) or root.agent,
            message_count=len(family_events),
            events=family_events,
            fork_ids=[sid for sid in family_ids if sid != root_id],
            fork_titles={
                sid: raw.sessions[sid].title
                for sid in family_ids if sid != root_id
            },
            family_ids=family_ids,
            user_text="\n".join(e.text for e in family_events if e.role == "user"),
            assistant_text="\n".join(e.text for e in family_events if e.role == "assistant"),
        )
        threads.append(thread)
        for sid in family_ids:
            thread_by_session[sid] = thread

    # 3. attach subagents to their parent's thread
    for sid, row in raw.sessions.items():
        if not row.parent_id:
            continue
        parent_thread = thread_by_session.get(row.parent_id)
        if parent_thread is None:
            events = sorted(
                by_session.get(sid, []), key=lambda e: (e.message_time, e.part_time)
            )
            first = _first_user_event(events)
            thread = Thread(
                root_id=sid,
                title=row.title,
                prompt=first.text if first else "",
                updated=row.time_updated,
                model=row.model,
                agent=row.agent,
                message_count=len(events),
                events=events,
                family_ids=[sid],
                user_text="\n".join(e.text for e in events if e.role == "user"),
                assistant_text="\n".join(e.text for e in events if e.role == "assistant"),
            )
            threads.append(thread)
            thread_by_session[sid] = thread
        else:
            parent_thread.subagent_ids.append(sid)
            parent_thread.subagent_titles[sid] = row.title
            parent_thread.subagent_agents[sid] = row.agent or ""
            thread_by_session[sid] = parent_thread

    # 4. deterministic order
    return sorted(threads, key=lambda t: (raw.sessions[t.root_id].time_created, t.root_id))


def thread_order(threads: list[Thread]) -> list[str]:
    return [t.root_id for t in sorted(threads, key=lambda t: (t.updated, t.root_id))]

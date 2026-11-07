from .load import RawData


def _walk(node):
    for thread in node.get("threads", []):
        yield from thread["forks"]
        yield from thread["subagents"]
        yield thread
    for child in node.get("children", []):
        yield from _walk(child)


def validate_payload(payload: dict, raw: RawData) -> list[str]:
    errors = []
    seen = []
    for group in payload["groups"]:
        for item in _walk(group):
            seen.append(item["id"])
    missing = sorted(set(raw.sessions) - set(seen))
    extra = sorted(set(seen) - set(raw.sessions))
    duplicates = sorted({sid for sid in seen if seen.count(sid) > 1})
    if missing:
        errors.append(f"missing sessions: {missing}")
    if extra:
        errors.append(f"unknown sessions: {extra}")
    if duplicates:
        errors.append(f"duplicate sessions: {duplicates}")
    for group in payload["groups"]:
        if group.get("threadCount", 0) == 0:
            errors.append(f"empty group: {group.get('label')}")
    total_threads = sum(group.get("threadCount", 0) for group in payload["groups"])
    if total_threads:
        for group in payload["groups"]:
            share = group.get("threadCount", 0) / total_threads
            if share > 0.4:
                errors.append(
                    f"group holds {share:.0%} of threads: {group.get('label')}"
                )
    return errors

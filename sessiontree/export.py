from .cluster import Node, node_thread_count
from .lineage import Thread


def _session_count(node: Node, threads: dict[str, Thread]) -> int:
    if node.thread_ids:
        return sum(
            1 + len(threads[tid].fork_ids) + len(threads[tid].subagent_ids)
            for tid in node.thread_ids
        )
    return sum(_session_count(child, threads) for child in node.children)


def _thread(tid: str, threads: dict[str, Thread]) -> dict:
    thread = threads[tid]
    return {
        "id": thread.root_id,
        "title": thread.title,
        "prompt": thread.prompt,
        "updated": thread.updated,
        "messages": thread.message_count,
        "model": thread.model,
        "agent": thread.agent,
        "forks": [
            {"id": sid, "title": thread.fork_titles.get(sid, sid)}
            for sid in thread.fork_ids
        ],
        "subagents": [
            {"id": sid, "title": thread.subagent_titles.get(sid, sid)}
            for sid in thread.subagent_ids
        ],
    }


def _node(node: Node, threads: dict[str, Thread]) -> dict:
    payload = {
        "label": node.label,
        "keywords": node.keywords,
        "threadCount": node_thread_count(node),
        "sessionCount": _session_count(node, threads),
    }
    if node.children:
        payload["children"] = [_node(child, threads) for child in node.children]
    else:
        payload["threads"] = [_thread(tid, threads) for tid in node.thread_ids]
    return payload


def to_payload(nodes: list[Node], threads: dict[str, Thread], generated_at: str) -> dict:
    return {
        "generatedAt": generated_at,
        "groups": [_node(node, threads) for node in nodes],
    }

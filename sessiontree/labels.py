from collections import defaultdict

from .cluster import Node
from .lineage import Thread


def _terms(node: Node, vectors, threads, exclude: set[str]) -> list[str]:
    if node.thread_ids:
        ids = node.thread_ids
    else:
        ids = []
        stack = list(node.children)
        while stack:
            current = stack.pop()
            if current.thread_ids:
                ids.extend(current.thread_ids)
            stack.extend(current.children)
    acc = defaultdict(float)
    for tid in ids:
        for term, value in vectors.get(tid, {}).items():
            if term not in exclude:
                acc[term] += value
    return [term for term, _ in sorted(acc.items(), key=lambda kv: (-kv[1], kv[0]))][:3]


def _fallback_title(node: Node, threads: dict[str, Thread]) -> str:
    ids = list(node.thread_ids)
    stack = list(node.children)
    while stack and not ids:
        current = stack.pop()
        ids.extend(current.thread_ids)
        stack.extend(current.children)
    return threads[ids[0]].title if ids else "Untitled group"


def assign_labels(nodes: list[Node], vectors, threads) -> None:
    def visit(node: Node, inherited: set[str]):
        if node.is_general:
            return
        terms = _terms(node, vectors, threads, inherited)
        node.keywords = terms
        node.label = " / ".join(terms) if terms else _fallback_title(node, threads)
        for child in node.children:
            visit(child, inherited | set(terms))

    for node in nodes:
        visit(node, set())

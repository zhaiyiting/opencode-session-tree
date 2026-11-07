import random
from collections import defaultdict
from dataclasses import dataclass, field

GENERAL_LABEL = "General / Uncategorized"


@dataclass
class Node:
    label: str = ""
    keywords: list[str] = field(default_factory=list)
    thread_ids: list[str] = field(default_factory=list)
    children: list["Node"] = field(default_factory=list)
    is_general: bool = False


def node_thread_count(node: Node) -> int:
    if node.thread_ids:
        return len(node.thread_ids)
    return sum(node_thread_count(child) for child in node.children)


def cos(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(value * b.get(term, 0.0) for term, value in a.items())


def agglomerate(ids: list[str], vectors: dict[str, dict[str, float]], k: int) -> list[list[str]]:
    """Spherical k-means over normalized vectors.

    The plan specified average linkage, but on the real DB it chained into one
    137-thread group. k-means keeps groups balanced and produces recognizable
    topics; the name is kept for the API the rest of the tool consumes.
    """
    ids = sorted(ids)
    if k <= 1 or len(ids) <= 1:
        return [ids]

    k = min(k, len(ids))
    best = None
    for seed in range(25):
        random.seed(seed)
        centroids = [dict(vectors[i]) for i in random.sample(ids, k)]
        assign = None
        for _ in range(50):
            new = [
                max(range(k), key=lambda c: cos(vectors[i], centroids[c]))
                for i in ids
            ]
            if new == assign:
                break
            assign = new
            for c in range(k):
                acc = defaultdict(float)
                for sid, a in zip(ids, assign):
                    if a == c:
                        for term, value in vectors[sid].items():
                            acc[term] += value
                norm = sum(v * v for v in acc.values()) ** 0.5 or 1.0
                centroids[c] = {term: v / norm for term, v in acc.items()}
        score = sum(cos(vectors[i], centroids[assign[idx]]) for idx, i in enumerate(ids))
        if best is None or score > best[0]:
            best = (score, assign)

    groups = defaultdict(list)
    for sid, a in zip(ids, best[1]):
        groups[a].append(sid)
    return sorted((sorted(g) for g in groups.values()), key=lambda g: g[0])


def _make_node(ids, vectors, subgroups, depth, max_depth):
    node = Node()
    if len(ids) <= 1 or depth >= max_depth or len(ids) <= 6:
        node.thread_ids = sorted(ids)
        return node
    k = min(subgroups, len(ids))
    children = [
        _make_node(cluster, vectors, subgroups, depth + 1, max_depth)
        for cluster in agglomerate(ids, vectors, k)
    ]
    children = [c for c in children if c.thread_ids or c.children]
    if len(children) == 1:
        return children[0]
    node.children = children
    return node


def build_tree(ids, vectors, general_ids, groups=10, subgroups=3, max_depth=3) -> list[Node]:
    ids = sorted(i for i in ids if i in vectors)
    nodes = []
    if ids:
        k = min(groups, len(ids))
        for cluster in agglomerate(ids, vectors, k):
            nodes.append(_make_node(cluster, vectors, subgroups, 1, max_depth))
    general = Node(thread_ids=sorted(general_ids), is_general=True)
    general.label = GENERAL_LABEL
    nodes.append(general)
    return nodes

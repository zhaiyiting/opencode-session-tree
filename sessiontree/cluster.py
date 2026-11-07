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
    ids = sorted(ids)
    if k <= 1 or len(ids) <= 1:
        return [ids]

    # precompute pairwise cosine once, then merge with average-linkage
    # (Lance-Williams update) so the run stays O(n^2), not O(n^3)
    n = len(ids)
    sim = {}
    for i in range(n):
        for j in range(i + 1, n):
            sim[(i, j)] = cos(vectors[ids[i]], vectors[ids[j]])

    def get(a, b):
        return sim[(a, b) if a < b else (b, a)]

    clusters = {i: [ids[i]] for i in range(n)}
    sizes = {i: 1 for i in range(n)}
    alive = set(range(n))
    while len(alive) > k:
        best = None
        keys = sorted(alive)
        for x in range(len(keys)):
            for y in range(x + 1, len(keys)):
                score = get(keys[x], keys[y])
                if best is None or score > best[0]:
                    best = (score, keys[x], keys[y])
        _, a, b = best
        sa, sb = sizes[a], sizes[b]
        clusters[a].extend(clusters.pop(b))
        alive.remove(b)
        for c in sorted(alive):
            if c == a:
                continue
            merged = (sa * get(a, c) + sb * get(b, c)) / (sa + sb)
            key = (a, c) if a < c else (c, a)
            sim[key] = merged
        sizes[a] = sa + sb
        del sizes[b]
    return sorted((sorted(c) for c in clusters.values()), key=lambda c: c[0])


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

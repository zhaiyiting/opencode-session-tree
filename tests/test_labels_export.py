import unittest

from sessiontree.cluster import Node
from sessiontree.export import to_payload
from sessiontree.labels import assign_labels
from sessiontree.lineage import Thread

def make_thread(root_id, title="A title", forks=0, subs=0):
    return Thread(
        root_id=root_id, title=title, prompt="p", updated=1,
        model="m", agent="a", message_count=3,
        fork_ids=[f"{root_id}_f{i}" for i in range(forks)],
        subagent_ids=[f"{root_id}_s{i}" for i in range(subs)],
        family_ids=[root_id], user_text="u" * 40, assistant_text="",
    )

class LabelExportTest(unittest.TestCase):
    def test_label_uses_top_terms_and_avoids_parent_terms(self):
        child = Node(thread_ids=["r1"])
        parent = Node(children=[child])
        vectors = {"r1": {"malloc": 0.8, "arena": 0.6, "jemalloc": 0.2}}
        threads = {"r1": make_thread("r1", title="Fallback")}
        assign_labels([parent], vectors, threads)
        self.assertEqual(parent.keywords, ["malloc", "arena", "jemalloc"])
        self.assertEqual(parent.label, "malloc / arena / jemalloc")
        self.assertEqual(child.label, "Fallback")

    def test_payload_counts_sessions_and_threads(self):
        node = Node(label="memory", keywords=["malloc"], thread_ids=[])
        node.children = [Node(label="mimalloc", thread_ids=["r1"])]
        threads = {"r1": make_thread("r1", forks=2, subs=3)}
        payload = to_payload([node], threads, "2026-11-07T00:00:00Z")
        group = payload["groups"][0]
        self.assertEqual(group["threadCount"], 1)
        self.assertEqual(group["sessionCount"], 6)
        thread = group["children"][0]["threads"][0]
        self.assertEqual(thread["id"], "r1")
        self.assertEqual(len(thread["forks"]), 2)
        self.assertEqual(len(thread["subagents"]), 3)

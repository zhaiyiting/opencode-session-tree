import unittest

from sessiontree.cluster import agglomerate, build_tree, cos, node_thread_count

def vec(**terms):
    total = sum(v * v for v in terms.values()) ** 0.5
    return {k: v / total for k, v in terms.items()}

class ClusterTest(unittest.TestCase):
    def setUp(self):
        self.vectors = {
            "a1": vec(malloc=3, arena=2),
            "a2": vec(malloc=2, arena=3),
            "a3": vec(malloc=3, heap=1),
            "b1": vec(bread=3, sourdough=2),
            "b2": vec(bread=2, sourdough=3),
            "b3": vec(bread=1, yeast=3),
            "g1": vec(),
        }

    def test_cosine(self):
        self.assertAlmostEqual(cos(self.vectors["a1"], self.vectors["a1"]), 1.0)
        self.assertAlmostEqual(cos(self.vectors["a1"], self.vectors["b1"]), 0.0)

    def test_agglomerate_separates_two_topics(self):
        clusters = agglomerate(["a1", "a2", "a3", "b1", "b2", "b3"], self.vectors, 2)
        got = sorted(sorted(c) for c in clusters)
        self.assertEqual(got, [["a1", "a2", "a3"], ["b1", "b2", "b3"]])

    def test_general_is_last_and_not_clustered(self):
        nodes = build_tree(["a1", "a2", "a3", "b1", "b2", "b3"], self.vectors, ["g1"], groups=2)
        self.assertTrue(nodes[-1].is_general)
        self.assertEqual(nodes[-1].thread_ids, ["g1"])
        self.assertEqual(sum(node_thread_count(n) for n in nodes), 7)

    def test_depth_limit_and_single_child_flatten(self):
        ids = list(self.vectors)[:6]
        nodes = build_tree(ids, self.vectors, [], groups=2, subgroups=3, max_depth=2)
        def depth(node):
            return 1 if not node.children else 1 + max(depth(c) for c in node.children)
        self.assertLessEqual(max(depth(n) for n in nodes), 2)
        for node in nodes:
            self.assertFalse(node.children and node.thread_ids)

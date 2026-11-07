import os
import tempfile
import unittest

from sessiontree.features import build_vectors, is_general, tokenize
from sessiontree.lineage import build_threads
from sessiontree.load import load_raw
from tests.fixture_db import make_db

class TokenizeTest(unittest.TestCase):
    def test_ascii_and_cjk_tokens(self):
        tokens = tokenize("Explain mimalloc 内存池 and arenas")
        self.assertIn("explain", tokens)
        self.assertIn("mimalloc", tokens)
        self.assertIn("内存", tokens)
        self.assertNotIn("and", tokens)

    def test_short_and_url_tokens_are_dropped(self):
        tokens = tokenize("go to https://example.com and read a b c")
        self.assertNotIn("https", tokens)
        self.assertNotIn("example.com", tokens)
        self.assertNotIn("go", tokens)

class VectorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db = os.path.join(self.tmp.name, "opencode.db")
        make_db(db)
        self.threads = {t.root_id: t for t in build_threads(load_raw(db))}
        self.vectors, self.general = build_vectors(list(self.threads.values()))

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_thread_is_general(self):
        self.assertTrue(is_general(self.threads["s_empty"]))
        self.assertIn("s_empty", self.general)
        self.assertNotIn("s_empty", self.vectors)

    def test_vectors_are_normalized_and_skip_common_terms(self):
        vec = self.vectors["s_root1"]
        norm = sum(v * v for v in vec.values()) ** 0.5
        self.assertAlmostEqual(norm, 1.0, places=5)
        self.assertNotIn("the", vec)

    def test_family_text_includes_forks_and_excludes_subagents(self):
        self.assertIn("arenas", self.vectors["s_root1"])
        self.assertNotIn("scan", self.vectors["s_root1"])

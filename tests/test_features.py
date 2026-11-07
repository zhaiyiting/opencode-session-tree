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

    def test_thread_whose_terms_are_all_filtered_goes_general(self):
        from sessiontree.lineage import Thread
        from sessiontree.load import TextEvent
        event = TextEvent(
            session_id="only", message_id="m1", role="user",
            text="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", message_time=1,
            part_time=1, model=None, agent=None,
        )
        thread = Thread(
            root_id="only", title="x", prompt=event.text, updated=1,
            model=None, agent=None, message_count=1, events=[event],
            family_ids=["only"], user_text=event.text,
        )
        vectors, general = build_vectors([thread])
        self.assertEqual(vectors, {})
        self.assertEqual(general, ["only"])

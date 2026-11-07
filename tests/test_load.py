import os
import stat
import tempfile
import unittest

from sessiontree.load import load_raw
from tests.fixture_db import make_db

class LoadRawTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "opencode.db")
        make_db(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_reads_sessions_and_text_parts_only(self):
        raw = load_raw(self.db)
        self.assertEqual(len(raw.sessions), 9)
        self.assertEqual(raw.sessions["s_root1"].title, "Memory pool A")
        self.assertEqual(raw.sessions["s_child1"].parent_id, "s_root1")
        texts = {(e.session_id, e.text) for e in raw.texts}
        self.assertIn(("s_root1", "explain malloc and arenas in detail"), texts)
        self.assertFalse(any(e.session_id == "s_empty" for e in raw.texts))
        self.assertEqual({e.role for e in raw.texts}, {"user", "assistant"})

    def test_opens_database_read_only(self):
        os.chmod(self.db, stat.S_IRUSR)
        raw = load_raw(self.db)
        self.assertEqual(raw.sessions["s_root2"].directory, "/work/b")

import os
import tempfile
import unittest

from sessiontree.lineage import build_threads
from sessiontree.load import load_raw
from tests.fixture_db import make_db

class LineageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db = os.path.join(self.tmp.name, "opencode.db")
        make_db(db)
        self.threads = {t.root_id: t for t in build_threads(load_raw(db))}

    def tearDown(self):
        self.tmp.cleanup()

    def test_fork_family_becomes_one_thread(self):
        thread = self.threads["s_root1"]
        self.assertEqual(thread.fork_ids, ["s_fork1"])
        self.assertEqual(sorted(thread.family_ids), ["s_fork1", "s_root1"])
        self.assertEqual(len(thread.events), 4)
        self.assertEqual(thread.message_count, 4)
        self.assertIn("malloc", thread.user_text)

    def test_subagent_attaches_to_parent_thread(self):
        self.assertEqual(self.threads["s_root1"].subagent_ids, ["s_child1"])
        self.assertNotIn("s_child1", self.threads)

    def test_orphan_forks_form_one_thread_with_earliest_as_root(self):
        thread = self.threads["s_orphan_a"]
        self.assertEqual(thread.fork_ids, ["s_orphan_b"])

    def test_same_prompt_at_different_times_stays_separate(self):
        self.assertIn("s_sameprompt", self.threads)
        self.assertIn("s_other_prompt", self.threads)
        self.assertNotIn("s_sameprompt", self.threads["s_other_prompt"].fork_ids)

    def test_empty_session_becomes_its_own_thread(self):
        thread = self.threads["s_empty"]
        self.assertEqual(thread.prompt, "")
        self.assertEqual(thread.events, [])

    def test_missing_parent_becomes_its_own_thread(self):
        raw = load_raw(os.path.join(self.tmp.name, "opencode.db"))
        raw.sessions["s_child1"] = type(raw.sessions["s_child1"])(
            id="s_child1", parent_id="s_deleted", title="orphan child",
            directory="/work/a", time_created=1200, time_updated=1200,
            agent="build", model="test-model")
        threads = {t.root_id: t for t in build_threads(raw)}
        self.assertIn("s_child1", threads)
        self.assertEqual(threads["s_child1"].subagent_ids, [])

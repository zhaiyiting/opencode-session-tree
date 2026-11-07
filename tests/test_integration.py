import json
import os
import subprocess
import tempfile
import unittest

from tests.fixture_db import make_db, make_single_db

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class IntegrationTest(unittest.TestCase):
    def test_cli_generates_html_and_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "opencode.db")
            out = os.path.join(tmp, "out")
            make_db(db)
            with open(db, "rb") as fh:
                before = fh.read()
            result = subprocess.run(
                ["/usr/bin/python3", os.path.join(ROOT, "session_tree.py"),
                 "--db", db, "--out", out, "--groups", "2"],
                capture_output=True, text=True, cwd=ROOT,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(os.path.exists(os.path.join(out, "session-tree.html")))
            with open(os.path.join(out, "groups.json")) as fh:
                payload = json.load(fh)
            ids = []

            def walk(node):
                for thread in node.get("threads", []):
                    ids.append(thread["id"])
                    ids.extend(f["id"] for f in thread["forks"])
                    ids.extend(s["id"] for s in thread["subagents"])
                for child in node.get("children", []):
                    walk(child)

            for group in payload["groups"]:
                walk(group)
            self.assertEqual(sorted(ids), sorted([
                "s_root1", "s_fork1", "s_root2", "s_child1", "s_empty",
                "s_orphan_a", "s_orphan_b", "s_sameprompt", "s_other_prompt",
            ]))
            with open(db, "rb") as fh:
                after = fh.read()
            self.assertEqual(after, before)
            self.assertIn("6 threads, 9 sessions", result.stdout)

    def test_single_session_survives_term_filtering(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "opencode.db")
            out = os.path.join(tmp, "out")
            make_single_db(db)
            result = subprocess.run(
                ["/usr/bin/python3", os.path.join(ROOT, "session_tree.py"),
                 "--db", db, "--out", out, "--groups", "2"],
                capture_output=True, text=True, cwd=ROOT,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with open(os.path.join(out, "groups.json")) as fh:
                payload = json.load(fh)
            ids = []

            def walk(node):
                for thread in node.get("threads", []):
                    ids.append(thread["id"])
                for child in node.get("children", []):
                    walk(child)

            for group in payload["groups"]:
                walk(group)
            self.assertEqual(ids, ["only"])
            self.assertEqual(payload["groups"][-1]["label"], "General / Uncategorized")

import json
import os
import re
import subprocess
import tempfile
import unittest

from sessiontree.render import render_html

PAYLOAD = {
    "generatedAt": "2026-11-07T00:00:00Z",
    "groups": [
        {"label": "alpha", "keywords": [], "threadCount": 2, "sessionCount": 2,
         "threads": [
             {"id": "ses_z", "title": "zebra project", "prompt": "zebra", "updated": 1,
              "messages": 1, "model": "m", "agent": "build", "forks": [], "subagents": []},
             {"id": "ses_q", "title": "quartz work", "prompt": "quartz", "updated": 1,
              "messages": 1, "model": "m", "agent": "build", "forks": [], "subagents": []},
         ]},
    ],
}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS = os.path.join(ROOT, "tests", "js_search_harness.js")


def run_search(query):
    page = render_html(PAYLOAD)
    script = re.search(r"<script>(.*)</script>", page, re.S).group(1)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(script)
        path = fh.name
    try:
        result = subprocess.run(
            ["node", HARNESS, path, query],
            capture_output=True, text=True, check=True,
        )
        return json.loads(result.stdout)
    finally:
        os.unlink(path)


class SearchJsTest(unittest.TestCase):
    def test_thread_match_keeps_ancestor_groups_visible(self):
        state = run_search("zebra")
        self.assertFalse(state["z"])
        self.assertFalse(state["a"], "ancestor group must stay visible")
        self.assertTrue(state["q"])

    def test_no_match_hides_every_thread_and_group(self):
        state = run_search("nomatch")
        self.assertTrue(state["a"])
        self.assertTrue(state["z"])
        self.assertTrue(state["q"])

    def test_group_label_match_keeps_group_visible(self):
        state = run_search("alpha")
        self.assertFalse(state["a"])
        self.assertTrue(state["z"])

import json
import unittest

from sessiontree.render import render_html

PAYLOAD = {
    "generatedAt": "2026-11-07T00:00:00Z",
    "groups": [
        {"label": "memory", "keywords": ["malloc"], "threadCount": 1, "sessionCount": 2,
         "children": [
             {"label": "mimalloc", "keywords": ["arena"], "threadCount": 1, "sessionCount": 2,
              "threads": [{
                  "id": "ses_1", "title": "<script>alert(1)</script> 内存",
                  "prompt": "explain malloc & arenas", "updated": 1, "messages": 5,
                  "model": "m", "agent": "build",
                  "forks": [{"id": "ses_2", "title": "fork title"}],
                  "subagents": [{"id": "ses_3", "title": "sub title", "agent": "explore"}],
              }]}
         ]}
    ],
}

class RenderTest(unittest.TestCase):
    def setUp(self):
        self.html = render_html(PAYLOAD)

    def test_escapes_html_and_keeps_cjk(self):
        self.assertNotIn("<script>alert(1)</script>", self.html)
        self.assertIn("&lt;script&gt;", self.html)
        self.assertIn("内存", self.html)

    def test_is_offline_and_has_controls(self):
        self.assertNotIn("http://", self.html.lower())
        self.assertNotIn("https://", self.html.lower())
        self.assertIn('id="search"', self.html)
        self.assertIn('id="hide-subagents"', self.html)
        self.assertIn('id="hide-forks"', self.html)
        self.assertIn("opencode -s ses_1", self.html)

    def test_thread_detail_shows_date_agent_and_timestamps(self):
        self.assertRegex(self.html, r"\d+d ago")
        self.assertIn("agent: build", self.html)
        self.assertIn("1970-01-01", self.html)
        self.assertIn("explore", self.html)

    def test_payload_is_embedded_for_search(self):
        self.assertIn("ses_1", self.html)
        self.assertIn("General / Uncategorized", render_html({"generatedAt": "", "groups": []}))

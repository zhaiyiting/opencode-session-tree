import unittest

from sessiontree.load import RawData, SessionRow
from sessiontree.validate import validate_payload


def make_raw(n):
    sessions = {
        f"s{i}": SessionRow(
            id=f"s{i}", parent_id=None, title="t", directory="/d",
            time_created=i, time_updated=i, agent="a", model="m",
        )
        for i in range(n)
    }
    return RawData(sessions=sessions, texts=[])


def thread(i):
    return {"id": f"s{i}", "forks": [], "subagents": []}


class ValidateTest(unittest.TestCase):
    def test_warns_when_one_group_holds_most_threads(self):
        payload = {"groups": [{"label": "big", "threadCount": 6,
                               "threads": [thread(i) for i in range(6)]}]}
        errors = validate_payload(payload, make_raw(6))
        self.assertTrue(any("of threads" in e for e in errors), errors)

    def test_no_warning_for_balanced_groups(self):
        payload = {"groups": [
            {"label": "a", "threadCount": 2, "threads": [thread(i) for i in range(2)]},
            {"label": "b", "threadCount": 2, "threads": [thread(i) for i in range(2, 4)]},
            {"label": "c", "threadCount": 2, "threads": [thread(i) for i in range(4, 6)]},
        ]}
        errors = validate_payload(payload, make_raw(6))
        self.assertEqual(errors, [])

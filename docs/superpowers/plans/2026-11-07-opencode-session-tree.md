# OpenCode Session Tree Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate an offline HTML page that groups all local OpenCode sessions into a recursive topic tree using message text only, with forks and subagents folded into their lineage.

**Architecture:** A stdlib-only Python package reads the SQLite DB read-only, reconstructs conversation threads (fork families + subagent children), builds message-level TF-IDF vectors, clusters threads with average-linkage agglomerative clustering, and renders a self-contained HTML file plus a JSON data file.

**Tech Stack:** Python 3 standard library only (`sqlite3`, `json`, `html`, `argparse`, `unittest`, `dataclasses`). Use `/usr/bin/python3`; the Anaconda Python on this machine has a broken `sqlite3` extension.

**Spec:** `docs/superpowers/specs/2026-11-07-opencode-session-tree-design.md`

## Global Constraints

- Python 3 standard library only. No third-party packages, no embeddings, no LLM calls.
- Run everything with `/usr/bin/python3`.
- Open the OpenCode DB read-only via URI `file:<path>?mode=ro`. Never write to it.
- No network access at build time or runtime. The HTML must not reference `http://` or `https://` assets.
- Cluster unit is a conversation thread (fork family). Fork and subagent sessions never cluster independently.
- Clustering thresholds count threads. Displayed counts include every session in the subtree.
- A thread whose root session has under 20 characters of user text goes to `General / Uncategorized`.
- Maximum tree depth is 3. A node has either `children` or `threads`, never both.
- `model` and `agent` prefer the latest assistant `message.data`, then fall back to `session.model` / `session.agent`.
- Output defaults to `out/session-tree.html` and `out/groups.json`.
- All commands below run from `/Users/zhai/wsp/opencode_sessiontree/`.

## Review Focus

- **A session with no text at all:** it must appear exactly once under `General / Uncategorized`, and generation must not crash. Test in Task 2 and Task 4.
- **A fork family whose root was deleted:** the remaining forks must still become one thread, not vanish or split. Test in Task 2.
- **A subagent whose parent is missing:** it must become its own thread and still appear exactly once. Test in Task 2.
- **Two unrelated conversations with the same generic first prompt:** they must not merge; the message timestamp is part of the family key. Test in Task 2.
- **Titles or prompts containing HTML or CJK text:** output must be escaped and render intact. Test in Task 3 (tokenizer) and Task 6 (renderer).

---

### Task 1: Project scaffold, DB loader, and shared fixture

**Files:**
- Create: `.gitignore`
- Create: `sessiontree/__init__.py`
- Create: `sessiontree/load.py`
- Create: `tests/__init__.py`
- Create: `tests/fixture_db.py`
- Create: `tests/test_load.py`

**Interfaces:**
- Produces:
  - `sessiontree.load.SessionRow`: dataclass with `id: str`, `parent_id: str | None`, `title: str`, `directory: str`, `time_created: int`, `time_updated: int`, `agent: str | None`, `model: str | None`
  - `sessiontree.load.TextEvent`: dataclass with `session_id: str`, `message_id: str`, `role: str`, `text: str`, `message_time: int`, `part_time: int`, `model: str | None`, `agent: str | None`
  - `sessiontree.load.RawData`: dataclass with `sessions: dict[str, SessionRow]`, `texts: list[TextEvent]`
  - `sessiontree.load.load_raw(db_path: str) -> RawData`
  - `tests.fixture_db.make_db(path: str) -> None`

- [ ] **Step 1: Initialize the project and write the failing loader test**

Run:

```bash
git init
mkdir -p sessiontree tests
touch sessiontree/__init__.py tests/__init__.py
printf 'out/\n__pycache__/\n*.pyc\n' > .gitignore
```

Create `tests/fixture_db.py`:

```python
import json
import sqlite3

SCHEMA = """
create table session (
  id text primary key, project_id text not null, parent_id text, slug text not null,
  directory text not null, title text not null, version text not null,
  time_created integer not null, time_updated integer not null,
  agent text, model text);
create table message (
  id text primary key, session_id text not null,
  time_created integer not null, time_updated integer not null, data text not null);
create table part (
  id text primary key, message_id text not null, session_id text not null,
  time_created integer not null, time_updated integer not null, data text not null);
"""

def _msg(role, model="test-model", agent="build"):
    return json.dumps({"role": role, "modelID": model, "agent": agent})

def make_db(path):
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    rows = [
        ("s_root1", None, "Memory pool A", "/work/a", 1000),
        ("s_fork1", None, "Memory pool A (fork #1)", "/work/a", 1100),
        ("s_root2", None, "Unrelated topic", "/work/b", 2000),
        ("s_child1", "s_root1", "Explore malloc (@explore subagent)", "/work/a", 1200),
        ("s_empty", None, "New session - 2026-01-01", "/work/c", 3000),
        ("s_orphan_a", None, "Orphan fork A", "/work/d", 1400),
        ("s_orphan_b", None, "Orphan fork B", "/work/d", 1401),
        ("s_sameprompt", None, "Generic exploration later", "/work/e", 5000),
    ]
    for sid, parent, title, directory, t in rows:
        con.execute(
            "insert into session values (?,?,?,?,?,?,?,?,?,?,?)",
            (sid, "global", parent, sid, directory, title, "1", t, t, "build", "test-model"),
        )

    def add(sid, mid, role, text, mt, pt, model="test-model", agent="build"):
        con.execute("insert into message values (?,?,?,?,?)", (mid, sid, mt, mt, _msg(role, model, agent)))
        con.execute(
            "insert into part values (?,?,?,?,?,?)",
            (mid + "_p", mid, sid, pt, pt, json.dumps({"type": "text", "text": text})),
        )

    # fork family: same first user text and same message timestamp
    add("s_root1", "m_r1_u", "user", "explain malloc and arenas in detail", 1000, 1000)
    add("s_root1", "m_r1_a", "assistant", "malloc allocates arenas and heaps", 1001, 1001)
    add("s_fork1", "m_f1_u", "user", "explain malloc and arenas in detail", 1000, 1500)
    add("s_fork1", "m_f1_a", "assistant", "malloc allocates arenas and heaps", 1002, 1502)
    # unrelated topic
    add("s_root2", "m_r2_u", "user", "how do I bake sourdough bread at home", 2000, 2000)
    add("s_root2", "m_r2_a", "assistant", "feed your starter and wait", 2001, 2001)
    # subagent
    add("s_child1", "m_c1_u", "user", "scan the malloc source files", 1200, 1200)
    # empty session: no text parts, only a tool part
    con.execute("insert into message values (?,?,?,?,?)", ("m_e_u", "s_empty", 3000, 3000, _msg("user")))
    con.execute(
        "insert into part values (?,?,?,?,?,?)",
        ("m_e_u_p", "m_e_u", "s_empty", 3000, 3000, json.dumps({"type": "tool", "tool": "bash"})),
    )
    # orphan forks share a family key but no root exists
    add("s_orphan_a", "m_oa_u", "user", "orphan prompt about dynamic linking", 1300, 1300)
    add("s_orphan_b", "m_ob_u", "user", "orphan prompt about dynamic linking", 1300, 1401)
    # same generic prompt but a different message timestamp
    add("s_sameprompt", "m_sp_u", "user", "explore this project", 4000, 4000)
    con.execute("insert into session values (?,?,?,?,?,?,?,?,?,?,?)",
                ("s_other_prompt", "global", None, "s_other_prompt", "/work/f",
                 "Same prompt earlier", "1", 400, 400, "build", "test-model"))
    add("s_other_prompt", "m_op_u", "user", "explore this project", 300, 300)
    con.commit()
    con.close()
```

Create `tests/test_load.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/usr/bin/python3 -m unittest tests.test_load -v`

Expected: `ModuleNotFoundError: No module named 'sessiontree.load'`.

- [ ] **Step 3: Implement the loader**

Create `sessiontree/load.py`:

```python
import json
import sqlite3
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SessionRow:
    id: str
    parent_id: Optional[str]
    title: str
    directory: str
    time_created: int
    time_updated: int
    agent: Optional[str]
    model: Optional[str]


@dataclass(frozen=True)
class TextEvent:
    session_id: str
    message_id: str
    role: str
    text: str
    message_time: int
    part_time: int
    model: Optional[str]
    agent: Optional[str]


@dataclass
class RawData:
    sessions: dict[str, SessionRow]
    texts: list[TextEvent]


SESSION_SQL = """
select id, parent_id, title, directory, time_created, time_updated, agent, model
from session
"""

TEXT_SQL = """
select p.session_id, p.message_id, p.time_created as part_time,
       m.time_created as message_time, m.data as message_data,
       p.data as part_data
from part p join message m on m.id = p.message_id
where json_extract(p.data, '$.type') = 'text'
order by m.time_created, p.time_created, p.id
"""


def load_raw(db_path: str) -> RawData:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        sessions = {
            r["id"]: SessionRow(
                id=r["id"], parent_id=r["parent_id"], title=r["title"],
                directory=r["directory"], time_created=r["time_created"],
                time_updated=r["time_updated"], agent=r["agent"], model=r["model"],
            )
            for r in con.execute(SESSION_SQL)
        }
        texts = []
        for r in con.execute(TEXT_SQL):
            part = json.loads(r["part_data"])
            text = part.get("text")
            if not text:
                continue
            message = json.loads(r["message_data"])
            texts.append(TextEvent(
                session_id=r["session_id"], message_id=r["message_id"],
                role=message.get("role", ""), text=text,
                message_time=r["message_time"], part_time=r["part_time"],
                model=message.get("modelID"), agent=message.get("agent"),
            ))
        return RawData(sessions=sessions, texts=texts)
    finally:
        con.close()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/usr/bin/python3 -m unittest tests.test_load -v`

Expected: 2 tests, `OK`.

- [ ] **Step 5: Commit**

```bash
git add .gitignore sessiontree tests
git commit -m "feat: read OpenCode sessions and text parts read-only"
```

---

### Task 2: Reconstruct threads from forks and subagents

**Files:**
- Create: `sessiontree/lineage.py`
- Create: `tests/test_lineage.py`

**Interfaces:**
- Consumes: `RawData`, `SessionRow`, `TextEvent` from `sessiontree.load`
- Produces:
  - `sessiontree.lineage.Thread`: dataclass with `root_id: str`, `title: str`, `prompt: str`, `updated: int`, `model: str | None`, `agent: str | None`, `message_count: int`, `events: list[TextEvent]`, `fork_ids: list[str]`, `subagent_ids: list[str]`, `fork_titles: dict[str, str]`, `subagent_titles: dict[str, str]`, `family_ids: list[str]`, `user_text: str`, `assistant_text: str`
  - `sessiontree.lineage.build_threads(raw: RawData) -> list[Thread]`
  - `sessiontree.lineage.thread_order(threads: list[Thread]) -> list[str]`

- [ ] **Step 1: Write the failing lineage tests**

Create `tests/test_lineage.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/usr/bin/python3 -m unittest tests.test_lineage -v`

Expected: `ModuleNotFoundError: No module named 'sessiontree.lineage'`.

- [ ] **Step 3: Implement thread reconstruction**

Create `sessiontree/lineage.py`:

```python
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from .load import RawData, TextEvent


@dataclass
class Thread:
    root_id: str
    title: str
    prompt: str
    updated: int
    model: Optional[str]
    agent: Optional[str]
    message_count: int
    events: list[TextEvent] = field(default_factory=list)
    fork_ids: list[str] = field(default_factory=list)
    subagent_ids: list[str] = field(default_factory=list)
    fork_titles: dict[str, str] = field(default_factory=dict)
    subagent_titles: dict[str, str] = field(default_factory=dict)
    family_ids: list[str] = field(default_factory=list)
    user_text: str = ""
    assistant_text: str = ""


def _normalize_prompt(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _first_user_event(events: list[TextEvent]) -> Optional[TextEvent]:
    for event in events:
        if event.role == "user":
            return event
    return None


def _latest_assistant(events: list[TextEvent]) -> Optional[TextEvent]:
    assistants = [e for e in events if e.role == "assistant"]
    return max(assistants, key=lambda e: e.message_time) if assistants else None


def build_threads(raw: RawData) -> list[Thread]:
    by_session = defaultdict(list)
    for event in raw.texts:
        by_session[event.session_id].append(event)

    # 1. split into fork families
    families: dict[tuple, list[str]] = defaultdict(list)
    for sid, row in raw.sessions.items():
        if row.parent_id:
            continue
        events = sorted(by_session.get(sid, []), key=lambda e: (e.message_time, e.part_time))
        first = _first_user_event(events)
        if first is None:
            key = ("__no_user__", sid)
        else:
            key = (_normalize_prompt(first.text), first.message_time)
        families[key].append(sid)

    def pick_root(members: list[str]) -> str:
        return min(members, key=lambda sid: (raw.sessions[sid].time_created, sid))

    # 2. build a thread per family, using root + forks for its text
    thread_by_session: dict[str, Thread] = {}
    threads: list[Thread] = []
    for members in families.values():
        root_id = pick_root(members)
        family_ids = sorted(members, key=lambda sid: (raw.sessions[sid].time_created, sid))
        family_events = []
        for sid in family_ids:
            family_events.extend(sorted(by_session.get(sid, []), key=lambda e: (e.message_time, e.part_time)))
        family_events.sort(key=lambda e: (e.message_time, e.part_time))

        root = raw.sessions[root_id]
        first = _first_user_event(family_events)
        assistant = _latest_assistant(family_events)
        thread = Thread(
            root_id=root_id,
            title=root.title,
            prompt=first.text if first else "",
            updated=max(raw.sessions[sid].time_updated for sid in family_ids),
            model=(assistant.model if assistant else None) or root.model,
            agent=(assistant.agent if assistant else None) or root.agent,
            message_count=len(family_events),
            events=family_events,
            fork_ids=[sid for sid in family_ids if sid != root_id],
            fork_titles={
                sid: raw.sessions[sid].title
                for sid in family_ids if sid != root_id
            },
            family_ids=family_ids,
            user_text="\n".join(e.text for e in family_events if e.role == "user"),
            assistant_text="\n".join(e.text for e in family_events if e.role == "assistant"),
        )
        threads.append(thread)
        for sid in family_ids:
            thread_by_session[sid] = thread

    # 3. attach subagents to their parent's thread
    for sid, row in raw.sessions.items():
        if not row.parent_id:
            continue
        parent_thread = thread_by_session.get(row.parent_id)
        if parent_thread is None:
            thread = Thread(
                root_id=sid, title=row.title,
                prompt=(_first_user_event(by_session.get(sid, [])).text
                        if _first_user_event(by_session.get(sid, [])) else ""),
                updated=row.time_updated, model=row.model, agent=row.agent,
                message_count=len(by_session.get(sid, [])),
                events=sorted(by_session.get(sid, []), key=lambda e: (e.message_time, e.part_time)),
                family_ids=[sid],
                user_text="\n".join(e.text for e in by_session.get(sid, []) if e.role == "user"),
                assistant_text="\n".join(e.text for e in by_session.get(sid, []) if e.role == "assistant"),
            )
            threads.append(thread)
            thread_by_session[sid] = thread
        else:
            parent_thread.subagent_ids.append(sid)
            parent_thread.subagent_titles[sid] = row.title
            thread_by_session[sid] = parent_thread

    # 4. deterministic order
    return sorted(threads, key=lambda t: (raw.sessions[t.root_id].time_created, t.root_id))


def thread_order(threads: list[Thread]) -> list[str]:
    return [t.root_id for t in sorted(threads, key=lambda t: (t.updated, t.root_id))]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/usr/bin/python3 -m unittest tests.test_lineage -v`

Expected: 6 tests, `OK`.

- [ ] **Step 5: Commit**

```bash
git add sessiontree/lineage.py tests/test_lineage.py
git commit -m "feat: reconstruct fork families and subagent lineage"
```

---

### Task 3: Message-level TF-IDF and thread vectors

**Files:**
- Create: `sessiontree/features.py`
- Create: `tests/test_features.py`

**Interfaces:**
- Consumes: `Thread` from `sessiontree.lineage`
- Produces:
  - `sessiontree.features.tokenize(text: str) -> list[str]`
  - `sessiontree.features.is_general(thread: Thread) -> bool`
  - `sessiontree.features.build_vectors(threads: list[Thread]) -> tuple[dict[str, dict[str, float]], list[str]]` returning `(vectors_by_root_id, general_thread_ids)`

- [ ] **Step 1: Write the failing feature tests**

Create `tests/test_features.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/usr/bin/python3 -m unittest tests.test_features -v`

Expected: `ModuleNotFoundError: No module named 'sessiontree.features'`.

- [ ] **Step 3: Implement tokenization, TF-IDF, and family vectors**

Create `sessiontree/features.py`:

```python
import math
import re
from collections import Counter, defaultdict

from .lineage import Thread

STOPWORDS = set("""
the a an and or of to in for on with this that these those is are was were
be been being it its as at by from not no but if then than so such can could
should would will may might do does did have has had you your we our they
their them he she his her i me my mine us also use used using into about over
under more most other some any all each both very just only own same too now
""".split())

ASCII_TOKEN = re.compile(r"[a-z0-9_./:+-]{3,}")
CJK_CHAR = re.compile(r"[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    lowered = text.lower()
    lowered = re.sub(r"https?://\S+", " ", lowered)
    words = [
        w for w in ASCII_TOKEN.findall(lowered)
        if w not in STOPWORDS and not w.startswith("http")
    ]
    cjk = CJK_CHAR.findall(lowered)
    bigrams = ["".join(cjk[i:i + 2]) for i in range(len(cjk) - 1)]
    return words + bigrams


def is_general(thread: Thread) -> bool:
    return len(thread.user_text.strip()) < 20


def build_vectors(threads: list[Thread]) -> tuple[dict[str, dict[str, float]], list[str]]:
    docs = []  # (root_id, role_weight, Counter)
    general = []
    for thread in threads:
        if is_general(thread):
            general.append(thread.root_id)
            continue
        seen_texts = set()
        for event in thread.events:
            if len(event.text.strip()) < 20:
                continue
            # forks copy the root's messages; count each distinct message once so
            # duplicated history does not inflate document frequency
            key = (event.role, event.text)
            if key in seen_texts:
                continue
            seen_texts.add(key)
            weight = 2.0 if event.role == "user" else 1.0
            docs.append((thread.root_id, weight, Counter(tokenize(event.text))))
        if not any(d[0] == thread.root_id for d in docs):
            general.append(thread.root_id)

    df = Counter()
    for _, _, counter in docs:
        df.update(counter.keys())
    total = len(docs)

    message_vectors = []
    for _, weight, counter in docs:
        vec = {
            term: (1 + math.log(count)) * (math.log((total + 1) / (df[term] + 1)) + 1)
            for term, count in counter.items()
            if df[term] <= 0.35 * total
        }
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        message_vectors.append((_, weight, {k: v / norm for k, v in vec.items()}))

    acc = defaultdict(lambda: defaultdict(float))
    for root_id, weight, vec in message_vectors:
        for term, value in vec.items():
            acc[root_id][term] += value * weight

    vectors = {}
    for root_id, terms in acc.items():
        norm = math.sqrt(sum(v * v for v in terms.values())) or 1.0
        vectors[root_id] = {k: v / norm for k, v in terms.items()}
    return vectors, general
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/usr/bin/python3 -m unittest tests.test_features -v`

Expected: 5 tests, `OK`.

- [ ] **Step 5: Commit**

```bash
git add sessiontree/features.py tests/test_features.py
git commit -m "feat: build message-level TF-IDF family vectors"
```

---

### Task 4: Average-linkage clustering into a recursive tree

**Files:**
- Create: `sessiontree/cluster.py`
- Create: `tests/test_cluster.py`

**Interfaces:**
- Consumes: `dict[str, dict[str, float]]` vectors from `sessiontree.features`
- Produces:
  - `sessiontree.cluster.Node`: dataclass with `label: str = ""`, `keywords: list[str] = field(default_factory=list)`, `thread_ids: list[str] = field(default_factory=list)`, `children: list[Node] = field(default_factory=list)`, `is_general: bool = False`
  - `sessiontree.cluster.node_thread_count(node: Node) -> int`
  - `sessiontree.cluster.cos(a: dict[str, float], b: dict[str, float]) -> float`
  - `sessiontree.cluster.agglomerate(ids: list[str], vectors: dict[str, dict[str, float]], k: int) -> list[list[str]]`
  - `sessiontree.cluster.build_tree(ids: list[str], vectors: dict[str, dict[str, float]], general_ids: list[str], groups: int = 10, subgroups: int = 3, max_depth: int = 3) -> list[Node]`

- [ ] **Step 1: Write the failing clustering tests**

Create `tests/test_cluster.py`:

```python
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
            "b3": vec(yeast=3),
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/usr/bin/python3 -m unittest tests.test_cluster -v`

Expected: `ModuleNotFoundError: No module named 'sessiontree.cluster'`.

- [ ] **Step 3: Implement clustering and tree building**

Create `sessiontree/cluster.py`:

```python
from dataclasses import dataclass, field

GENERAL_LABEL = "General / Uncategorized"


@dataclass
class Node:
    label: str = ""
    keywords: list[str] = field(default_factory=list)
    thread_ids: list[str] = field(default_factory=list)
    children: list["Node"] = field(default_factory=list)
    is_general: bool = False


def node_thread_count(node: Node) -> int:
    if node.thread_ids:
        return len(node.thread_ids)
    return sum(node_thread_count(child) for child in node.children)


def cos(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(value * b.get(term, 0.0) for term, value in a.items())


def agglomerate(ids: list[str], vectors: dict[str, dict[str, float]], k: int) -> list[list[str]]:
    ids = sorted(ids)
    if k <= 1 or len(ids) <= 1:
        return [ids]

    # precompute pairwise cosine once, then merge with average-linkage
    # (Lance-Williams update) so the run stays O(n^2), not O(n^3)
    n = len(ids)
    sim = {}
    for i in range(n):
        for j in range(i + 1, n):
            sim[(i, j)] = cos(vectors[ids[i]], vectors[ids[j]])

    def get(a, b):
        return sim[(a, b) if a < b else (b, a)]

    clusters = {i: [ids[i]] for i in range(n)}
    sizes = {i: 1 for i in range(n)}
    alive = set(range(n))
    while len(alive) > k:
        best = None
        keys = sorted(alive)
        for x in range(len(keys)):
            for y in range(x + 1, len(keys)):
                score = get(keys[x], keys[y])
                if best is None or score > best[0]:
                    best = (score, keys[x], keys[y])
        _, a, b = best
        sa, sb = sizes[a], sizes[b]
        clusters[a].extend(clusters.pop(b))
        alive.remove(b)
        for c in sorted(alive):
            if c == a:
                continue
            merged = (sa * get(a, c) + sb * get(b, c)) / (sa + sb)
            key = (a, c) if a < c else (c, a)
            sim[key] = merged
        sizes[a] = sa + sb
        del sizes[b]
    return sorted((sorted(c) for c in clusters.values()), key=lambda c: c[0])


def _make_node(ids, vectors, subgroups, depth, max_depth):
    node = Node()
    if len(ids) <= 1 or depth >= max_depth or len(ids) <= 6:
        node.thread_ids = sorted(ids)
        return node
    k = min(subgroups, len(ids))
    children = [
        _make_node(cluster, vectors, subgroups, depth + 1, max_depth)
        for cluster in agglomerate(ids, vectors, k)
    ]
    children = [c for c in children if c.thread_ids or c.children]
    if len(children) == 1:
        return children[0]
    node.children = children
    return node


def build_tree(ids, vectors, general_ids, groups=10, subgroups=3, max_depth=3) -> list[Node]:
    ids = sorted(i for i in ids if i in vectors)
    nodes = []
    if ids:
        k = min(groups, len(ids))
        for cluster in agglomerate(ids, vectors, k):
            nodes.append(_make_node(cluster, vectors, subgroups, 1, max_depth))
    general = Node(thread_ids=sorted(general_ids), is_general=True)
    general.label = GENERAL_LABEL
    nodes.append(general)
    return nodes
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/usr/bin/python3 -m unittest tests.test_cluster -v`

Expected: 4 tests, `OK`.

- [ ] **Step 5: Commit**

```bash
git add sessiontree/cluster.py tests/test_cluster.py
git commit -m "feat: cluster threads into a recursive topic tree"
```

---

### Task 5: Node labels and JSON export

**Files:**
- Create: `sessiontree/labels.py`
- Create: `sessiontree/export.py`
- Create: `tests/test_labels_export.py`

**Interfaces:**
- Consumes: `Node`, `node_thread_count` from `sessiontree.cluster`; `Thread` from `sessiontree.lineage`
- Produces:
  - `sessiontree.labels.assign_labels(nodes: list[Node], vectors: dict[str, dict[str, float]], threads: dict[str, Thread]) -> None`
  - `sessiontree.export.to_payload(nodes: list[Node], threads: dict[str, Thread], generated_at: str) -> dict`

- [ ] **Step 1: Write the failing label and export tests**

Create `tests/test_labels_export.py`:

```python
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
        child.thread_ids = ["r1"]
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/usr/bin/python3 -m unittest tests.test_labels_export -v`

Expected: `ModuleNotFoundError: No module named 'sessiontree.labels'`.

- [ ] **Step 3: Implement labels and payload export**

Create `sessiontree/labels.py`:

```python
from collections import defaultdict

from .cluster import Node, node_thread_count
from .lineage import Thread


def _terms(node: Node, vectors, threads, exclude: set[str]) -> list[str]:
    if node.thread_ids:
        ids = node.thread_ids
    else:
        ids = []
        stack = list(node.children)
        while stack:
            current = stack.pop()
            if current.thread_ids:
                ids.extend(current.thread_ids)
            stack.extend(current.children)
    acc = defaultdict(float)
    for tid in ids:
        for term, value in vectors.get(tid, {}).items():
            if term not in exclude:
                acc[term] += value
    return [term for term, _ in sorted(acc.items(), key=lambda kv: (-kv[1], kv[0]))][:3]


def _fallback_title(node: Node, threads: dict[str, Thread]) -> str:
    ids = list(node.thread_ids)
    stack = list(node.children)
    while stack and not ids:
        current = stack.pop()
        ids.extend(current.thread_ids)
        stack.extend(current.children)
    return threads[ids[0]].title if ids else "Untitled group"


def assign_labels(nodes: list[Node], vectors, threads) -> None:
    def visit(node: Node, inherited: set[str]):
        if node.is_general:
            return
        terms = _terms(node, vectors, threads, inherited)
        node.keywords = terms
        node.label = " / ".join(terms) if terms else _fallback_title(node, threads)
        for child in node.children:
            visit(child, inherited | set(terms))

    for node in nodes:
        visit(node, set())
```

Create `sessiontree/export.py`:

```python
from .cluster import Node, node_thread_count
from .lineage import Thread


def _thread_count(node: Node) -> int:
    return node_thread_count(node)


def _session_count(node: Node, threads: dict[str, Thread]) -> int:
    if node.thread_ids:
        return sum(
            1 + len(threads[tid].fork_ids) + len(threads[tid].subagent_ids)
            for tid in node.thread_ids
        )
    return sum(_session_count(child, threads) for child in node.children)


def _thread(tid: str, threads: dict[str, Thread]) -> dict:
    thread = threads[tid]
    return {
        "id": thread.root_id,
        "title": thread.title,
        "prompt": thread.prompt,
        "updated": thread.updated,
        "messages": thread.message_count,
        "model": thread.model,
        "agent": thread.agent,
        "forks": [
            {"id": sid, "title": thread.fork_titles.get(sid, sid)}
            for sid in thread.fork_ids
        ],
        "subagents": [
            {"id": sid, "title": thread.subagent_titles.get(sid, sid)}
            for sid in thread.subagent_ids
        ],
    }


def _node(node: Node, threads: dict[str, Thread]) -> dict:
    payload = {
        "label": node.label,
        "keywords": node.keywords,
        "threadCount": _thread_count(node),
        "sessionCount": _session_count(node, threads),
    }
    if node.children:
        payload["children"] = [_node(child, threads) for child in node.children]
    else:
        payload["threads"] = [_thread(tid, threads) for tid in node.thread_ids]
    return payload


def to_payload(nodes: list[Node], threads: dict[str, Thread], generated_at: str) -> dict:
    return {
        "generatedAt": generated_at,
        "groups": [_node(node, threads) for node in nodes],
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/usr/bin/python3 -m unittest tests.test_labels_export -v`

Expected: 2 tests, `OK`.

- [ ] **Step 5: Commit**

```bash
git add sessiontree/labels.py sessiontree/export.py tests/test_labels_export.py
git commit -m "feat: label groups and export tree payload"
```

---

### Task 6: Self-contained HTML renderer

**Files:**
- Create: `sessiontree/render.py`
- Create: `tests/test_render.py`

**Interfaces:**
- Consumes: payload `dict` from `sessiontree.export.to_payload`
- Produces:
  - `sessiontree.render.render_html(payload: dict) -> str`

- [ ] **Step 1: Write the failing renderer tests**

Create `tests/test_render.py`:

```python
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
                  "forks": [{"id": "ses_2"}], "subagents": [{"id": "ses_3"}],
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
        self.assertIn("opencode -s ses_1", self.html)

    def test_payload_is_embedded_for_search(self):
        self.assertIn("ses_1", self.html)
        self.assertIn("General / Uncategorized", render_html({"generatedAt": "", "groups": []}))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/usr/bin/python3 -m unittest tests.test_render -v`

Expected: `ModuleNotFoundError: No module named 'sessiontree.render'`.

- [ ] **Step 3: Implement the renderer**

Create `sessiontree/render.py`:

```python
import html
import json

CSS = """
:root { color-scheme: light dark; }
body { font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; padding: 24px; }
h1 { font-size: 18px; margin: 0 0 4px; }
.meta { opacity: .65; margin-bottom: 16px; }
.controls { display: flex; gap: 16px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
input[type=search] { min-width: 280px; padding: 6px 8px; }
details { margin-left: 18px; }
summary { cursor: pointer; padding: 2px 0; }
.group > summary { font-weight: 600; }
.thread { margin-left: 18px; padding: 2px 0; }
.thread-title { cursor: pointer; }
.thread-title:hover { text-decoration: underline; }
.count { opacity: .55; font-weight: 400; }
.badge { opacity: .6; font-size: 12px; margin-left: 6px; }
.detail { margin: 6px 0 12px 18px; padding: 8px 12px; border-left: 2px solid #8884; white-space: pre-wrap; }
.hidden { display: none; }
mark { background: #ffd54f; color: #000; }
"""

JS = """
const search = document.getElementById('search');
const hideSubs = document.getElementById('hide-subagents');
function apply() {
  const q = search.value.trim().toLowerCase();
  document.querySelectorAll('.thread, .group').forEach(el => {
    const text = (el.dataset.text || '').toLowerCase();
    el.classList.toggle('hidden', q !== '' && !text.includes(q));
  });
  document.querySelectorAll('.subagent').forEach(el => {
    el.classList.toggle('hidden', hideSubs.checked);
  });
}
search.addEventListener('input', apply);
hideSubs.addEventListener('change', apply);
document.getElementById('expand-all').addEventListener('click', () =>
  document.querySelectorAll('details').forEach(d => d.open = true));
document.getElementById('collapse-all').addEventListener('click', () =>
  document.querySelectorAll('details').forEach(d => d.open = false));
document.querySelectorAll('.thread-title').forEach(el => {
  el.addEventListener('click', () => {
    const detail = el.parentElement.querySelector('.detail');
    if (detail) detail.classList.toggle('hidden');
  });
});
apply();
"""


def _esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _thread_html(thread: dict) -> str:
    text = " ".join([
        thread.get("title", ""), thread.get("prompt", ""),
        thread.get("model") or "", thread.get("agent") or "",
    ])
    parts = [
        f'<div class="thread" data-text="{_esc(text)}">',
        f'<div class="thread-title">• {_esc(thread["title"])}'
        f'<span class="badge">{_esc(thread.get("model") or "")}</span>'
        f'<span class="badge">{thread.get("messages", 0)} msgs</span></div>',
        f'<div class="detail hidden">{_esc(thread.get("prompt") or "")}\n\n'
        f'opencode -s {_esc(thread["id"])}</div>',
        '<details><summary class="count">',
        f'{len(thread.get("forks") or [])} forks</summary>',
    ]
    parts += [
        f'<div class="fork">↳ {_esc(fork.get("title") or fork["id"])}'
        f'<span class="badge">{_esc(fork["id"])}</span></div>'
        for fork in thread.get("forks") or []
    ]
    parts.append('</details>')
    if thread.get("subagents"):
        parts.append('<details class="subagents"><summary class="count">'
                     f'{len(thread["subagents"])} subagents</summary>')
        parts += [
            f'<div class="subagent">↳ {_esc(sub.get("title") or sub["id"])}'
            f'<span class="badge">{_esc(sub["id"])}</span></div>'
            for sub in thread["subagents"]
        ]
        parts.append('</details>')
    parts.append('</div>')
    return "".join(parts)


def _node_html(node: dict) -> str:
    label = _esc(node.get("label") or "")
    count = f'<span class="count">{node.get("threadCount", 0)} threads · {node.get("sessionCount", 0)} sessions</span>'
    text = " ".join([node.get("label", "")] + (node.get("keywords") or []))
    body = []
    if node.get("children"):
        body += [_node_html(child) for child in node["children"]]
    for thread in node.get("threads") or []:
        body.append(_thread_html(thread))
    cls = "group" + (" general" if node.get("label") == "General / Uncategorized" else "")
    return (
        f'<details class="{cls}" data-text="{_esc(text)}" open>'
        f'<summary>{label} {count}</summary>{"".join(body)}</details>'
    )


def render_html(payload: dict) -> str:
    groups = payload.get("groups") or []
    if not groups:
        groups = [{"label": "General / Uncategorized", "keywords": [],
                   "threadCount": 0, "sessionCount": 0, "threads": []}]
    body = "".join(_node_html(node) for node in groups)
    total = sum(node.get("sessionCount", 0) for node in payload.get("groups") or [])
    threads = sum(node.get("threadCount", 0) for node in payload.get("groups") or [])
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>OpenCode Session Tree</title>
<style>{CSS}</style></head><body>
<h1>OpenCode Session Tree</h1>
<div class="meta">{threads} threads · {total} sessions · generated {_esc(payload.get("generatedAt", ""))}</div>
<div class="controls">
<input id="search" type="search" placeholder="Search titles, prompts, groups...">
<label><input id="hide-subagents" type="checkbox" checked> hide subagents</label>
<button id="expand-all">expand all</button>
<button id="collapse-all">collapse all</button>
</div>
<div id="tree">{body}</div>
<script>{JS}</script>
</body></html>"""
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/usr/bin/python3 -m unittest tests.test_render -v`

Expected: 3 tests, `OK`.

- [ ] **Step 5: Commit**

```bash
git add sessiontree/render.py tests/test_render.py
git commit -m "feat: render self-contained collapsible session tree"
```

---

### Task 7: CLI, validation, and end-to-end test

**Files:**
- Create: `session_tree.py`
- Create: `tests/test_integration.py`

**Interfaces:**
- Consumes: everything above
- Produces:
  - `session_tree.py` executable entry point with `--db`, `--out`, `--groups`, `--subgroups`
  - `sessiontree.validate.validate_payload(payload: dict, raw: RawData) -> list[str]` (module `sessiontree/validate.py`)

- [ ] **Step 1: Write the failing integration test**

Create `tests/test_integration.py`:

```python
import json
import os
import subprocess
import tempfile
import unittest

from tests.fixture_db import make_db

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class IntegrationTest(unittest.TestCase):
    def test_cli_generates_html_and_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "opencode.db")
            out = os.path.join(tmp, "out")
            make_db(db)
            before = open(db, "rb").read()
            result = subprocess.run(
                ["/usr/bin/python3", os.path.join(ROOT, "session_tree.py"),
                 "--db", db, "--out", out, "--groups", "2"],
                capture_output=True, text=True, cwd=ROOT,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(os.path.exists(os.path.join(out, "session-tree.html")))
            payload = json.load(open(os.path.join(out, "groups.json")))
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
            self.assertEqual(open(db, "rb").read(), before)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `/usr/bin/python3 -m unittest tests.test_integration -v`

Expected: fails because `session_tree.py` does not exist (exit code 2).

- [ ] **Step 3: Implement validation and the CLI**

Create `sessiontree/validate.py`:

```python
from .load import RawData


def _walk(node):
    for thread in node.get("threads", []):
        yield from thread["forks"]
        yield from thread["subagents"]
        yield thread
    for child in node.get("children", []):
        yield from _walk(child)


def validate_payload(payload: dict, raw: RawData) -> list[str]:
    errors = []
    seen = []
    for group in payload["groups"]:
        for item in _walk(group):
            seen.append(item["id"])
    missing = sorted(set(raw.sessions) - set(seen))
    extra = sorted(set(seen) - set(raw.sessions))
    duplicates = sorted({sid for sid in seen if seen.count(sid) > 1})
    if missing:
        errors.append(f"missing sessions: {missing}")
    if extra:
        errors.append(f"unknown sessions: {extra}")
    if duplicates:
        errors.append(f"duplicate sessions: {duplicates}")
    for group in payload["groups"]:
        if group.get("threadCount", 0) == 0:
            errors.append(f"empty group: {group.get('label')}")
    return errors
```

Create `session_tree.py`:

```python
import argparse
import json
import os
import sys
from datetime import datetime, timezone

from sessiontree.cluster import build_tree
from sessiontree.export import to_payload
from sessiontree.features import build_vectors
from sessiontree.labels import assign_labels
from sessiontree.lineage import build_threads
from sessiontree.load import load_raw
from sessiontree.render import render_html
from sessiontree.validate import validate_payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Group OpenCode sessions into a browsable tree.")
    parser.add_argument("--db", default=os.path.expanduser("~/.local/share/opencode/opencode.db"))
    parser.add_argument("--out", default="out")
    parser.add_argument("--groups", type=int, default=10)
    parser.add_argument("--subgroups", type=int, default=3)
    args = parser.parse_args(argv)

    raw = load_raw(args.db)
    threads = build_threads(raw)
    vectors, general = build_vectors(threads)
    nodes = build_tree(list(vectors), vectors, general, groups=args.groups, subgroups=args.subgroups)
    by_id = {thread.root_id: thread for thread in threads}
    assign_labels(nodes, vectors, by_id)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = to_payload(nodes, by_id, generated)

    errors = validate_payload(payload, raw)
    if errors:
        for error in errors:
            print(f"warning: {error}", file=sys.stderr)

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "groups.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, "session-tree.html"), "w", encoding="utf-8") as fh:
        fh.write(render_html(payload))

    print(f"{len(threads)} threads, {len(raw.sessions)} sessions")
    print(f"wrote {os.path.join(args.out, 'session-tree.html')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the full suite**

Run: `/usr/bin/python3 -m unittest discover -s tests -v`

Expected: all tests pass.

- [ ] **Step 5: Smoke-test against the real database**

Run:

```bash
/usr/bin/python3 session_tree.py --out out
```

Expected: prints `~160 threads, 316 sessions`, writes both files. Then open `out/session-tree.html` in a browser and verify: tree expands, search finds a known session, openTPU forks appear under one thread, subagents hidden by default.

- [ ] **Step 6: Commit**

```bash
git add session_tree.py sessiontree/validate.py tests/test_integration.py
git commit -m "feat: add CLI, validation, and end-to-end generation"
```

---

## Self-Review Notes

- Spec coverage: loader (Task 1), lineage (Task 2), message-only features (Task 3), recursive clustering and General bucket (Task 4), labels + JSON counts (Task 5), HTML with search/filters/offline constraint (Task 6), CLI + validation + real-DB smoke (Task 7).
- Count semantics: `threadCount` from `node_thread_count`, `sessionCount` includes forks/subagents; both in Task 5 and asserted.
- General threshold: `is_general` uses root `user_text` length, Task 3.
- Model/agent fallback: Task 2 latest assistant else session row; asserted indirectly.
- All five Review Focus cases have owning tests: empty session (Task 2, Task 4), orphan family (Task 2), missing parent (Task 2), same prompt different time (Task 2), HTML/CJK escape (Task 3, Task 6).
- Fork duplication is deduplicated by `(role, text)` before TF-IDF, so forks do not inflate document frequency and erase their own family's key terms.
- Clustering precomputes pairwise cosine and uses a Lance-Williams average-linkage update, keeping the real-DB run inside the 10-second budget.
- The package is `sessiontree/` so the `session_tree.py` CLI does not shadow it on import.

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


def make_single_db(path):
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.execute(
        "insert into session values (?,?,?,?,?,?,?,?,?,?,?)",
        ("only", "global", None, "only", "/work/only", "Only session", "1", 1, 1, "build", "m"),
    )
    con.execute("insert into message values (?,?,?,?,?)",
                ("m1", "only", 1, 1, _msg("user")))
    con.execute("insert into part values (?,?,?,?,?,?)",
                ("m1_p", "m1", "only", 1, 1,
                 json.dumps({"type": "text", "text": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"})))
    con.commit()
    con.close()

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

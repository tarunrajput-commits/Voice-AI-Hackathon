"""Event store keyed by GLID – live activity only.

Holds the bot's conversation write-backs, callback / meeting requests, and anything POSTed to /api/events
(in production: CDC / Kafka from the source systems). `glid` is the actor; `counterpart_glid` is the other
party when there is one (e.g. the seller on an enquiry). The CSV dump is NOT copied here – the runtime
pipeline reads it straight from the files (context_layer/csv_index.py).
"""
import json
import sqlite3
import threading
import time
from datetime import datetime, timezone

from config import DB_PATH, DATA_DIR

_lock = threading.Lock()
_conn = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    glid TEXT NOT NULL,
    counterpart_glid TEXT,
    role TEXT,                 -- buyer | seller | NULL (applies to both views)
    source TEXT NOT NULL,      -- logical source system (enquiries, calls, kyc, ...)
    type TEXT NOT NULL,
    ts TEXT NOT NULL,          -- when the activity happened (ISO, UTC)
    ingested_at REAL NOT NULL, -- epoch seconds when we received it (freshness clock starts here)
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_glid ON events(glid, ts);
CREATE INDEX IF NOT EXISTS ix_cp ON events(counterpart_glid, ts);
CREATE INDEX IF NOT EXISTS ix_type ON events(glid, type);
CREATE TABLE IF NOT EXISTS identities (   -- channel identity -> GLID (never written to .md files)
    channel_id TEXT PRIMARY KEY,
    glid TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS subjects (     -- which (glid, role) files exist, and why
    glid TEXT NOT NULL,
    role TEXT NOT NULL,
    origin TEXT,
    PRIMARY KEY (glid, role)
);
"""


def conn():
    global _conn
    if _conn is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
    return _conn


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def insert_event(glid, source, type_, payload, ts=None, counterpart_glid=None, role=None):
    ingested = time.time()
    with _lock:
        cur = conn().execute(
            "INSERT INTO events (glid, counterpart_glid, role, source, type, ts, ingested_at, payload)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (str(glid), str(counterpart_glid) if counterpart_glid else None, role, source, type_,
             ts or now_iso(), ingested, json.dumps(payload, ensure_ascii=False)),
        )
        conn().commit()
        return {"id": cur.lastrowid, "ingested_at": ingested}


def query(sql, args=()):
    with _lock:
        rows = conn().execute(sql, args).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if "payload" in d:
            d["payload"] = json.loads(d["payload"])
        out.append(d)
    return out


def map_identity(channel_id, glid):
    with _lock:
        conn().execute("INSERT OR REPLACE INTO identities VALUES (?,?)", (channel_id, str(glid)))
        conn().commit()


def glid_for(channel_id):
    rows = query("SELECT glid FROM identities WHERE channel_id=?", (channel_id,))
    return rows[0]["glid"] if rows else None

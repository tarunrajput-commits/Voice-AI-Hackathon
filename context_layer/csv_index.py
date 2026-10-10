"""Read one GLID's rows straight from the dataset CSV files, in milliseconds.

A one-time scan records the byte span of every CSV record and indexes it by the file's GLID
column(s): {file: {glid: [(start, end), ...]}}. At runtime we open each file, seek to those spans
and parse only those rows – no database in between, the CSV files stay the source of truth.

The index (~a few MB) is cached in data/csv_index.pkl and rebuilt automatically when any CSV
changes size or modification time. Multi-line quoted fields are handled (record boundaries are
found by tracking quote parity, RFC 4180).
"""
import csv
import io
import os
import pickle
import threading
import time
from collections import defaultdict

from config import DATA_DIR
from context_layer import dataset

INDEX_PATH = DATA_DIR / "csv_index.pkl"
_index = None
_lock = threading.Lock()


def _signature():
    sig = {}
    for name in dataset.FILES:
        p = dataset.DATASET_DIR / name
        st = p.stat()
        sig[name] = (st.st_size, int(st.st_mtime))
    return sig


def _records(path):
    """Yield (start, end) byte spans of CSV records (after the header) and the header line."""
    with open(path, "rb") as f:
        header = f.readline()
        pos = f.tell()
        start, in_quote = pos, False
        for line in f:
            pos += len(line)
            if line.count(b'"') % 2:
                in_quote = not in_quote
            if not in_quote:
                yield start, pos
                start = pos
    return header


def build(progress=print):
    t = time.time()
    idx = {"signature": _signature(), "files": {}, "headers": {}}
    for name, (keys, _) in dataset.FILES.items():
        path = dataset.DATASET_DIR / name
        with open(path, "rb") as f:
            idx["headers"][name] = f.readline().decode("utf-8")
        cols = next(csv.reader([idx["headers"][name]]))
        key_pos = [cols.index(k) for k in keys]
        spans = defaultdict(list)
        with open(path, "rb") as f:
            for start, end in _records(path):
                f.seek(start)
                row = next(csv.reader([f.read(end - start).decode("utf-8")]), None)
                if not row:
                    continue
                for kp in set(key_pos):
                    if kp < len(row) and row[kp]:
                        spans[row[kp]].append((start, end))
        idx["files"][name] = {g: sorted(set(v)) for g, v in spans.items()}
        progress(f"indexed {name}: {sum(len(v) for v in idx['files'][name].values())} rows, {len(idx['files'][name])} GLIDs")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = INDEX_PATH.with_suffix(".tmp")
    with open(tmp, "wb") as f:
        pickle.dump(idx, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, INDEX_PATH)
    progress(f"csv index built in {time.time() - t:.1f}s")
    return idx


def index():
    global _index
    with _lock:
        if _index is None:
            if INDEX_PATH.exists():
                with open(INDEX_PATH, "rb") as f:
                    cand = pickle.load(f)
                if cand.get("signature") == _signature():
                    _index = cand
            if _index is None:
                _index = build()
    return _index


def read(glid):
    """All events for one GLID, parsed directly from the CSV files. Returns (events, rows_read)."""
    glid = str(glid)
    idx, events, n, call_ts, turn_rows = index(), [], 0, {}, []
    for name, (_, conv) in dataset.FILES.items():
        spans = idx["files"][name].get(glid)
        if not spans:
            continue
        cols = next(csv.reader([idx["headers"][name]]))
        with open(dataset.DATASET_DIR / name, "rb") as f:
            for start, end in spans:
                f.seek(start)
                vals = next(csv.reader(io.StringIO(f.read(end - start).decode("utf-8"))), None)
                if not vals:
                    continue
                n += 1
                row = dict(zip(cols, vals))
                if conv is None:
                    turn_rows.append(row)
                    continue
                e = conv(row)
                if e:
                    events.append(e)
                    if conv is dataset.c_vani:
                        call_ts[e[6]["attempt_id"]] = e[5]
    events += dataset.turns_events(turn_rows, call_ts)
    return events, n


def has(glid):
    return any(glid in files for files in index()["files"].values())

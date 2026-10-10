"""Hybrid refresh (runtime-only files: only GLIDs that have been used have a file).

Event-driven: every ingested event enqueues the files it affects; a worker thread rebuilds the ones
that exist, offline (no API calls), after a short debounce.
Scheduled: a sweep rebuilds every existing file periodically so lookback windows age out and pull-only
sources (APIs without change events) are picked up even when no event arrives.
"""
import queue
import threading
import time

from config import DEBOUNCE_MS, SWEEP_INTERVAL_S
from context_layer import builder, gc_api, pipeline, sources, store

_q = queue.Queue()
_started = False


def ingest(glid, source, type_, payload, ts=None, counterpart_glid=None, role=None):
    """Write an event and schedule rebuilds of every file it affects."""
    ev = store.insert_event(glid, source, type_, payload, ts=ts, counterpart_glid=counterpart_glid, role=role)
    targets = sources.affected_files({"glid": str(glid), "counterpart_glid": counterpart_glid and str(counterpart_glid),
                                      "type": type_, "role": role})
    for t in targets:
        _q.put((t, ev["ingested_at"]))
    return {**ev, "targets": sorted(targets)}


def refresh_gc(glid, wait=False):
    """Pull the live Global Context snapshot for a GLID, cache it, and rebuild its files.
    The freshness clock starts when the snapshot lands (fetch completed)."""
    def run():
        try:
            data = gc_api.fetch(glid)
        except Exception as e:
            print(f"gc refresh {glid} failed: {e}")
            return None
        gc_api.save(glid, data)
        landed = time.time()
        for t in sources.affected_files({"glid": str(glid), "type": "gc_snapshot"}):
            _q.put((t, landed))
        return data["_fetch"]
    if wait:
        return run()
    threading.Thread(target=run, daemon=True).start()
    return None


def _worker():
    while True:
        first = _q.get()
        pending = {first[0]: first[1]}
        deadline = time.time() + DEBOUNCE_MS / 1000
        while True:                                    # debounce window
            try:
                t, ing = _q.get(timeout=max(0, deadline - time.time()))
                pending[t] = min(pending.get(t, ing), ing)
            except queue.Empty:
                break
        for (glid, role), ing in pending.items():
            if not _exists(glid, role):        # no file = GLID not in use; it will be built fresh when it is
                continue
            try:
                pipeline.rebuild(glid, role, trigger_at=ing, reason="event")
            except Exception as e:
                print(f"rebuild {glid}/{role} failed: {e}")


def _exists(glid, role):
    return builder.path_for(glid, role).exists()


def existing_files():
    return [(p.parent.name, p.stem) for p in sorted(builder.CONTEXT_DIR.glob("*/*.md"))]


def rebuild_all(reason="sweep"):
    """Scheduled sweep: re-render every existing file offline so lookback windows and relative dates stay right."""
    return [pipeline.rebuild(g, r, reason=reason) for g, r in existing_files()]


def refresh_stale_gc(glids):
    """Sweep helper: re-pull live snapshots that are older than the TTL (only for GLIDs we were asked to keep warm)."""
    for g in glids:
        if gc_api.is_stale(g):
            refresh_gc(g, wait=True)


def _sweeper(extra_tasks):
    while True:
        time.sleep(SWEEP_INTERVAL_S)
        rebuild_all()
        for task in extra_tasks:
            try:
                task()
            except Exception:
                pass


def start(extra_tasks=()):
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_worker, daemon=True, name="refresh-worker").start()
    threading.Thread(target=_sweeper, args=(list(extra_tasks),), daemon=True, name="refresh-sweeper").start()

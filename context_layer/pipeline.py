"""Context layer pipeline (runtime, per GLID): API first, then CSV, API wins on conflicts.

    run(glid, role)
      1. APIs  (in parallel, time-boxed)
               a. Global Context: generateContextUID(glid) -> mapping_id -> getContext(mapping_id)   account state
               b. sellerproductslisting(gluserid=glid, product_filter=ALL, pg_type=1, ordering=4)    live catalogue
      2. CSV   that GLID's rows read straight from the 11 dataset CSVs (byte-offset index)  history
      3. LIVE  events not in the CSVs: this bot's conversation write-backs, POSTed activity
      4. MERGE field-level: catalogue fields catalog API > GC API > CSV; other fields GC API > CSV
               (conflicts listed in the front matter); CSV fills what the API doesn't return
      5. BUILD deterministic render -> size cap -> atomic write contexts/<glid>/<role>.md

Every step is timed. If the API fails or exceeds its time budget, the pipeline continues with
the last cached snapshot (or CSV only) and says so in the result and the file's front matter.

Used by: GET /api/context/runtime/<glid>, session start (console / WhatsApp), incoming calls.
Files exist only for GLIDs that have been used (runtime-only, nothing is pre-built). rebuild() refreshes an
existing file offline (no API calls) after new activity and in the periodic sweep.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from context_layer import builder, catalog_api, csv_index, gc_api, skill, sources, store

_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="ctx")
_inflight = {}            # (glid, role) -> Future: concurrent requests for the same file share one run
_lock = threading.Lock()


def _live_events(glid):
    """Events that are not in the CSV export (bot write-backs, activity POSTed after the export)."""
    return store.query("SELECT * FROM events WHERE (glid=? OR counterpart_glid=?) AND source NOT LIKE 'dataset.%' "
                       "ORDER BY ts", (glid, glid))


def _run(glid, role, api_budget_s, use_cached_api, offline=False, trigger_at=None, reason="runtime"):
    t0 = time.time()
    timings, degraded = {}, []

    # 1. APIs first – Global Context + seller products listing, in parallel, within one time budget
    api_status, gc_raw, cat_status, cat = "skipped", None, "skipped", None
    fut_gc = None if (offline or (use_cached_api and not gc_api.is_stale(glid))) else _pool.submit(gc_api.fetch, glid)
    fut_cat = None if (role != "seller" or offline or (use_cached_api and not catalog_api.is_stale(glid))) \
        else _pool.submit(catalog_api.fetch, glid)
    deadline = t0 + api_budget_s
    if fut_gc is None:
        gc_raw = gc_api.cached(glid)
        api_status = ("cached" if gc_raw else "not fetched") + (" (offline rebuild)" if offline else " (fresh)")
    else:
        try:
            gc_raw = fut_gc.result(timeout=max(0.05, deadline - time.time()))
            gc_api.save(glid, gc_raw)
            f = gc_raw["_fetch"]
            api_status = "live" + (" (mapping_id reused)" if f.get("mapping_reused") else "")
            timings.update({"api_generateContextUID_ms": f["uid_ms"], "api_getContext_ms": f["ctx_ms"]})
        except Exception as e:  # timeout / token expired / API down: never block, fall back to last snapshot
            gc_raw = gc_api.cached(glid)
            api_status = f"failed ({type(e).__name__}: {str(e)[:60]}) – " + ("using last snapshot" if gc_raw else "CSV only")
            degraded.append("gc_api")
    if role == "seller":
        if fut_cat is None:
            cat = catalog_api.cached(glid)
            cat_status = ("cached" if cat else "not fetched") + (" (offline rebuild)" if offline else " (fresh)")
        else:
            try:
                cat = fut_cat.result(timeout=max(0.05, deadline - time.time()))
                catalog_api.save(glid, cat)
                cat_status = "live"
                timings["catalog_api_ms"] = cat["_fetch"]["ms"]
            except catalog_api.CatalogError as e:
                cat = None
                cat_status = "no catalogue" if "204" in str(e) else f"failed ({str(e)[:60]})"
                if "204" not in str(e):
                    degraded.append("catalog_api")
            except Exception as e:
                cat = catalog_api.cached(glid)
                cat_status = f"failed ({type(e).__name__}) – " + ("using last snapshot" if cat else "none")
                degraded.append("catalog_api")
    timings["apis_ms"] = round((time.time() - t0) * 1000)

    # 2. CSV
    t1 = time.time()
    try:
        csv_events, rows = csv_index.read(glid)
    except Exception as e:
        csv_events, rows = [], 0
        degraded.append(f"csv ({type(e).__name__})")
    timings["csv_ms"] = round((time.time() - t1) * 1000, 1)

    # 3. live events
    t2 = time.time()
    live = _live_events(glid)
    timings["live_events_ms"] = round((time.time() - t2) * 1000, 1)

    # 4 + 5. merge (inside the renderer via context_layer.merge) and build
    t3 = time.time()
    data = sources.from_events(glid, role, csv_events, live, gc_raw, cat)
    last_event = max([e[5] for e in csv_events] + [e["ts"] for e in live], default=None)
    fetched = (gc_raw or {}).get("_fetch", {}).get("fetched_at")
    short = lambda st: st.split(" (")[0].split(" –")[0]            # "live" | "cached" | "failed" | "no catalogue"
    note = f"apis_first+csv (gc={short(api_status)}, catalog={short(cat_status)}, csv_rows={rows}, live={len(live)})"
    rec = builder.write(glid, role, data, t3, degraded, last_event, fetched, trigger_ingested_at=trigger_at or t0,
                        reason=reason, pipeline_note=note)
    timings["merge_build_ms"] = round((time.time() - t3) * 1000, 1)
    timings["total_ms"] = round((time.time() - t0) * 1000)

    known = bool(rows or live or gc_api.extract(gc_raw) or (cat or {}).get("counts"))
    return {"glid": glid, "role": role, "md": builder.read(glid, role), "api": api_status, "catalog_api": cat_status, "csv_rows": rows,
            "live_events": len(live), "timings": timings, "known_user": known, "chars": rec["chars"],
            "conflicts_resolved": [{"field": f, "used": f"{ws}={wv}", "overridden": f"{ls}={lv}"}
                                   for f, ws, wv, ls, lv in data.get("_conflicts", [])],
            "field_sources": data.get("_field_sources", {}), "degraded": degraded, "trigger_at": t0}


def rebuild(glid, role, trigger_at=None, reason="event"):
    """Offline rebuild (no API calls): last saved API snapshots + CSV + live events. Used after new activity
    arrives and by the periodic sweep. Only for files that already exist (i.e. GLIDs that have been used)."""
    return _run(str(glid), role, 0, True, offline=True, trigger_at=trigger_at, reason=reason)


def run(glid, role="seller", api_budget_s=None, use_cached_api=False):
    """Blocking. Concurrent runs for the same (glid, role) share one execution.
    use_cached_api=False (default) always hits the API first, as the pipeline specifies."""
    st = skill.settings()                     # re-reads skill.md if it changed: lookbacks, size cap, API budget
    api_budget_s = api_budget_s or st["api_budget_s"]
    key = (str(glid), role)
    with _lock:
        fut = _inflight.get(key)
        if fut is None or fut.done():
            fut = _pool.submit(_run, str(glid), role, api_budget_s, use_cached_api)
            _inflight[key] = fut
    return fut.result()

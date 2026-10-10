"""Writes one context file: render prepared source data -> enforce size cap -> atomic write -> log freshness.
The data is prepared by context_layer/pipeline.py (APIs first, then CSV, then live events)."""
import json
import os
import time
from datetime import datetime, timezone

import config
from config import CAPS, CONTEXT_DIR, DATA_LABEL, FRESHNESS_LOG, LOOKBACK_DAYS
from context_layer import dataset
from context_layer.render import render_buyer, render_seller

# progressively tighter layouts, used only when a file would exceed MAX_FILE_CHARS
_SHRINK = [
    ({}, 140),
    ({"conversations": 3, "enquiries": 3, "care": 5, "searches": 4, "requirements": 3, "sellers": 3}, 120),
    ({"conversations": 3, "enquiries": 2, "care": 4, "facts": 8, "open_threads": 3, "searches": 3, "requirements": 3,
      "sellers": 3}, 100),
    ({"conversations": 2, "enquiries": 2, "care": 4, "facts": 6, "open_threads": 3, "searches": 3, "requirements": 2,
      "sellers": 2, "catalog_detail": 0}, 80),
    ({"conversations": 1, "enquiries": 1, "care": 3, "facts": 5, "open_threads": 3, "searches": 2, "requirements": 2,
      "sellers": 2, "catalog_detail": 0}, 70),
]

def seller_names():
    """seller GLID -> company name, so buyer.md can name the sellers a buyer contacted."""
    return {g: p["company"] for g, p in dataset.profiles().items() if p["company"]}


def _short(v):
    v = str(v).replace(";", ",").replace("]", ")")
    return v if len(v) <= 40 else v[:39] + "…"


def path_for(glid, role):
    return CONTEXT_DIR / str(glid) / f"{role}.md"


def _iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def write(glid, role, data, t0, degraded, last_event, gc_fetched, trigger_ingested_at=None, reason="manual",
          pipeline_note=None):
    """Render prepared source data -> enforce size cap -> front matter -> atomic write -> freshness log."""
    for overrides, width in _SHRINK:
        caps = {**CAPS, **overrides}
        if role == "buyer":
            body, cold = render_buyer(glid, data, caps=caps, width=width, seller_names=seller_names())
        else:
            body, cold = render_seller(glid, data, caps=caps, width=width)
        generated = time.time()
        freshness_ms = round((generated - trigger_ingested_at) * 1000, 1) if trigger_ingested_at else None

        lb = {"buyer": ["buyer_activity", "wa_chat", "call_extractions", "enquiries", "conversations"],
              "seller": ["enquiries", "pns_calls", "buyleads", "wa_chat", "vani_calls", "exec_calls", "whatsapp", "conversations"]}[role]
        fm = ["---",
              f"schema: {role}.v2",
              f"glid: \"{glid}\"",
              f"role: {role}",
              f"generated_at: {_iso(generated)}",
              f"freshness_ms: {freshness_ms if freshness_ms is not None else 'n/a'}",
              f"build_ms: {round((generated - t0) * 1000, 1)}",
              f"sources: {{events_until: {last_event[:10] if last_event else 'none'}, "
              f"live_api: {_iso(gc_fetched) if gc_fetched else 'not fetched'}, "
              f"catalog_api: {_iso(data['catalog']['_fetch']['fetched_at']) if isinstance(data.get('catalog'), dict) and data['catalog'].get('_fetch') else 'not fetched'}}}",
              *([f"pipeline: {pipeline_note}"] if pipeline_note else []),
              "lookback_days: {" + ", ".join(f"{k}: {LOOKBACK_DAYS[k]}" for k in lb) + "}",
              "merge: {policy: catalog_api > gc_api > csv, fields: {" + ", ".join(
                  f"{src}: {sum(1 for v in data.get('_field_sources', {}).values() if v == src)}" for src in ("catalog", "api", "dataset")) + "}}",
              "conflicts_resolved: [" + "; ".join(f"{f}: {ws}={_short(wv)} over {ls}={_short(lv)}"
                                                 for f, ws, wv, ls, lv in data.get("_conflicts", [])[:3]) + "]",
              f"cold_start: {str(cold).lower()}",
              f"degraded: [{', '.join(degraded)}]",
              f"data: {DATA_LABEL}",
              "---", ""]
        if len("\n".join(fm)) + len(body) <= config.MAX_FILE_CHARS:      # the cap covers the whole file the bot reads
            break

    text = "\n".join(fm) + body

    out = path_for(glid, role)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".md.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, out)                          # atomic: readers never see a half-written file

    rec = {"glid": glid, "role": role, "reason": reason, "chars": len(text), "build_ms": round((generated - t0) * 1000, 1),
           "freshness_ms": freshness_ms, "generated_at": _iso(generated)}
    if reason != "bulk":
        with open(FRESHNESS_LOG, "a") as f:
            f.write(json.dumps(rec) + "\n")
    return rec


def read(glid, role):
    p = path_for(glid, role)
    return p.read_text(encoding="utf-8") if p.exists() else None

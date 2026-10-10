"""Source selection for one (GLID, role): applies each source's lookback window and shapes the data the
renderer expects. Input comes from the runtime pipeline (context_layer/pipeline.py): the GLID's CSV rows,
its live events, and the API snapshots. A failing source never breaks a file (pipeline marks it degraded).
"""
from datetime import datetime, timedelta, timezone

from config import LOOKBACK_DAYS
from context_layer import gc_api

IST = timezone(timedelta(hours=5, minutes=30))


def _since(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def from_events(glid, role, csv_events, live_events, gc_raw, catalog_snap=None):
    """Everything the renderer needs for one (GLID, role), inside each source's lookback window, computed from
    csv_events (tuples straight from the CSV files) + live_events (event-store rows: bot write-backs,
    callback/meeting requests, POSTed activity) + gc_raw (Global Context API) + catalog_snap (products API)."""
    glid = str(glid)
    rows = [{"glid": str(g), "counterpart_glid": str(c) if c else None, "role": r, "source": s, "type": t, "ts": ts,
             "payload": p} for g, c, r, s, t, ts, p in csv_events]
    rows += live_events
    rows.sort(key=lambda x: x["ts"])

    def own(type_, days=None, r=None):
        since = _since(days) if days else ""
        return [x for x in rows if x["glid"] == glid and x["type"] == type_ and x["ts"] >= since
                and (r is None or x["role"] in (r, None))]

    def received(type_, days):
        since = _since(days)
        return [x for x in rows if x["counterpart_glid"] == glid and x["type"] == type_ and x["ts"] >= since]

    prof = own("seller_profile")
    common = {"profile": prof[-1]["payload"] if prof else {}, "gc": gc_api.extract(gc_raw),
              "wa_chat": own("wa_chat", LOOKBACK_DAYS["wa_chat"], role),
              "call_extractions": own("call_extraction", LOOKBACK_DAYS["call_extractions"], role),
              "conversations": own("conversation", LOOKBACK_DAYS["conversations"], role),
              "requests": own("callback_request", LOOKBACK_DAYS["conversations"], role)
              + own("meeting_request", LOOKBACK_DAYS["conversations"], role)}
    if role == "seller":
        return {**common, "catalog": catalog_snap or {},
                "enquiries": received("enquiry", LOOKBACK_DAYS["enquiries"]),
                "enquiry_messages": own("enquiry_message", LOOKBACK_DAYS["enquiry_messages"]),
                "pns_calls": received("pns_call", LOOKBACK_DAYS["pns_calls"]),
                "buyleads": own("buylead_bought", LOOKBACK_DAYS["buyleads"]),
                "whatsapp": own("wa_message", LOOKBACK_DAYS["whatsapp"]),
                "vani_calls": own("vani_call", LOOKBACK_DAYS["vani_calls"]),
                "vani_turns": own("vani_turns", LOOKBACK_DAYS["vani_calls"]),
                "exec_calls": own("exec_call", LOOKBACK_DAYS["exec_calls"])}
    acts = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS["buyer_activity"])
    for a in ((gc_raw or {}).get("activitydetails") or {}).get("BUYER_ACTIVITY") or []:
        try:
            ts = datetime.strptime(a["ACTIVITY_TIME"], "%Y%m%d%H%M%S").replace(tzinfo=IST).astimezone(timezone.utc)
        except (KeyError, ValueError):
            continue
        if ts >= cutoff:
            acts.append({"ts": ts.isoformat(timespec="seconds"), "type": a.get("ACTIVITY_TYPE"),
                         "category": a.get("CATEGORY_NAME") if a.get("CATEGORY_NAME") not in ("-", "") else "",
                         "keyword": a.get("KEYWORD") if a.get("KEYWORD") not in ("-", "") else "",
                         "seller_glid": a.get("SELLER_GLUSR_ID") if a.get("SELLER_GLUSR_ID") not in ("0", "") else ""})
    return {**common, "buyer_activity": sorted(acts, key=lambda x: x["ts"]),
            "enquiries_sent": own("enquiry", LOOKBACK_DAYS["enquiries"]),
            "calls_made": own("pns_call", LOOKBACK_DAYS["pns_calls"])}


def affected_files(event):
    """Which (glid, role) files must be rebuilt when this event arrives."""
    g, cp, t, role = event["glid"], event.get("counterpart_glid"), event["type"], event.get("role")
    out = set()
    if t in ("enquiry", "pns_call"):            # buyer acted on a seller: both views change
        out.add((g, "buyer"))
        if cp:
            out.add((cp, "seller"))
    elif t == "gc_snapshot":                    # live API refresh touches both files of the GLID
        out.update({(g, "buyer"), (g, "seller")})
    elif role in ("buyer", "seller"):
        out.add((g, role))
    else:
        out.update({(g, "buyer"), (g, "seller")})
    return out

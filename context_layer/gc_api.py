"""IndiaMART Global Context API client (live seller account snapshot).

Two-step protocol:
  1. POST /generateContextUID {mapping_type:1, mapping_value:<glid>, source_id, empid, ak} -> data.mapping_id   (~5 s)
  2. GET  /x/getContext?mapping_id=<id>                                                    -> data.{sections}   (~80 ms)

The snapshot is *state*, not events, and the API is pull-only, so it is refreshed (a) on demand
when a session starts and the cached copy is older than GC_API_TTL_S, (b) by the scheduled sweep,
(c) via POST /api/gc/refresh/<glid>. Raw responses are cached under data/gc_cache/ (gitignored:
they contain PII such as email/address that never reaches the .md files – see `extract`).
"""
import json
import os
import time
from pathlib import Path

import httpx

from config import DATA_DIR

BASE = os.environ.get("GC_API_BASE", "http://merp.intermesh.net/go/api/globalcontext/v1")
EMPID = int(os.environ.get("GC_API_EMPID", "0") or 0)
XFF = os.environ.get("GC_API_XFF", "")
AK = os.environ.get("GC_API_AK", "")
TTL_S = int(os.environ.get("GC_API_TTL_S", "3600"))
CACHE = DATA_DIR / "gc_cache"


class GCError(Exception):
    pass


def _headers():
    return {"content-type": "application/json", **({"X-Forwarded-For": XFF} if XFF else {})}


_mapping = {}                                       # glid -> (mapping_id, created_at)
MAPPING_TTL_S = int(os.environ.get("GC_MAPPING_TTL_S", "600"))


def generate_mapping_id(glid, timeout=20):
    """Step 1: POST generateContextUID -> mapping_id (uuid)."""
    if not AK:
        raise GCError("GC_API_AK not set in .env")
    r = httpx.post(f"{BASE}/generateContextUID", headers=_headers(), timeout=timeout,
                   json={"mapping_type": 1, "mapping_value": str(glid), "source_id": 1, "empid": EMPID, "ak": AK})
    j = r.json()
    mid = (j.get("data") or {}).get("mapping_id")
    if not mid:
        raise GCError(f"generateContextUID failed: {j.get('message') or r.status_code} (token expired?)")
    _mapping[str(glid)] = (mid, time.time())
    return mid


def get_context(mapping_id, timeout=20):
    """Step 2: GET x/getContext?mapping_id=<uuid> -> data (dict); {} when the mapping is unknown/expired."""
    r = httpx.get(f"{BASE}/x/getContext", params={"mapping_id": mapping_id}, headers=_headers(), timeout=timeout)
    j = r.json()
    return j.get("data") or {}, j.get("message", "")


def fetch(glid, timeout=20):
    """Live call: generateContextUID -> getContext. A mapping_id is reused for MAPPING_TTL_S (saves step 1)
    and regenerated automatically if getContext says it is unknown/expired. Raises GCError."""
    glid = str(glid)
    t0 = time.time()
    cached_mid = _mapping.get(glid)
    reused = bool(cached_mid and time.time() - cached_mid[1] < MAPPING_TTL_S)
    mid = cached_mid[0] if reused else generate_mapping_id(glid, timeout)
    t1 = time.time()
    data, msg = get_context(mid, timeout)
    if not data and reused:                         # stale mapping: regenerate once
        mid, reused = generate_mapping_id(glid, timeout), False
        t1 = time.time()
        data, msg = get_context(mid, timeout)
    if not data:
        raise GCError(f"getContext: {msg}")
    data["_fetch"] = {"uid_ms": 0 if reused else round((t1 - t0) * 1000), "ctx_ms": round((time.time() - t1) * 1000),
                      "mapping_id": mid, "mapping_reused": reused, "fetched_at": time.time()}
    return data


def save(glid, data):
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{glid}.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False))
    os.replace(tmp, p)


def cached(glid):
    p = CACHE / f"{glid}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def age_s(glid):
    c = cached(glid)
    return time.time() - c["_fetch"]["fetched_at"] if c else None


def is_stale(glid):
    a = age_s(glid)
    return a is None or a > TTL_S


# ---------------------------------------------------------------------------------------------
# Normalisation: whitelist of fields the bot may use. Email, address, phone, account-manager
# email / empid, ticket free-text and GST/PAN numbers are deliberately NOT extracted.
# ---------------------------------------------------------------------------------------------
def _g(d, *path, default=None):
    for p in path:
        if not isinstance(d, dict):
            return default
        d = d.get(p)
    return default if d in (None, "", [], {}) else d


def extract(data):
    if not data:
        return {}
    k = data.get("kycdetails") or {}
    if not (k.get("company_name") or k.get("first_name")):   # unknown GLID: API returns an empty shell
        return {}
    act = data.get("activitydetails") or {}
    l4w = act.get("last_4_week") or {}
    lm = act.get("last_month") or {}
    t = data.get("ticketsdetails") or {}
    con = data.get("connectdetails") or {}
    bl = data.get("BLdetails") or {}

    wip = []
    for tk in (k.get("WIP_TICKET_BUCKET") or []) + (t.get("WIP_OPS_TICKETS") or []):
        if tk.get("TYPE"):
            wip.append({"type": tk["TYPE"], "since": tk.get("CUSTOMER_TICKET_ISSUEDATE", "")})
    nach = (k.get("nach_status") or [{}])[0] if k.get("nach_status") else {}

    mcats = []
    for m in act.get("top3mcat_data") or []:
        try:
            mcats += [x["mcat_name"] for x in json.loads(m.get("mcat_list") or "[]")]
        except Exception:
            pass
    md0 = (act.get("top3mcat_data") or [{}])[0]

    connects = []
    for c in con.get("connect_30D") or []:
        connects.append({"date": c.get("call_answered_date", ""), "status": c.get("call_sts_update", ""),
                         "summary": c.get("call_answered_summary", ""), "meeting": c.get("meet_sts_update", "")})

    wa = []
    for key in ("LAST_WA9696_CHAT", "LAST_WA8181_CHAT"):
        for m in act.get(key) or []:
            wa.append(m)

    lcd = (k.get("last_call_details") or [{}])[0] if k.get("last_call_details") else {}

    return {
        "fetched_at": (data.get("_fetch") or {}).get("fetched_at"),
        "last_call_comment": lcd.get("COMMENTS", ""),
        "last_call_date": lcd.get("ENTERED_ON", ""),
        "upload_time": _g(k, "upload_metadata", "upload_time"),
        "first_name": k.get("first_name") or "",
        "company": k.get("company_name") or "",
        "city": k.get("city") or "",
        "company_type": k.get("company_type") or "",
        "customer_type": k.get("customer_type") or "",            # Paid / Free
        "highest_service": k.get("highest_service") or "",
        "payment_plan": k.get("payment_plan") or "",
        "renewal_date": k.get("renewal_date") or "",
        "renewal_status": k.get("renewal_status") or "",
        "nach": nach.get("DIS_TEXT", ""),
        "service_vintage": k.get("SERVICE_VINTAGE") or "",
        "registered_since": k.get("registered_since_with_indiamart") or "",
        "listing_status": k.get("glusr_usr_listing_status") or "",
        "email_verified": k.get("input_email_verification_status") == "Verified",
        "address_verified": bool(k.get("address_verification_status")),
        "high_churn": bool(k.get("high_churn")),
        "high_risk": k.get("high_risk_suspected") == "Yes",
        "account_manager": (k.get("account_manager_bd") or {}).get("name", "").split(" ")[0],
        "approved_products": k.get("approved_product_count") or "",
        "rating_count": k.get("rating_count") or 0,
        "wip_tickets": wip,
        "tickets_7d": _g(t, "last_7_days", "total_ticket_count", default=0),
        "negative_feedback_90d": (_g(t, "last_8_to_90_days", "negative_feedback_count", default=0) or 0)
                                 + (_g(t, "last_7_days", "negative_feedback_count", default=0) or 0),
        "irate_90d": _g(t, "last_8_to_90_days", "irate_complaint_count", default=0),
        "enq_30d": act.get("enq_last_30_days", 0), "enq_90d": act.get("enq_last_90_days", 0),
        "pns_30d": act.get("pns_received_30_days", 0), "pns_90d": act.get("pns_received_90_days", 0),
        "pns_picked_4w": l4w.get("pns_call_picked", 0), "pns_received_4w": l4w.get("pns_call_received", 0),
        "bl_consumed_4w": l4w.get("bl_cons", 0), "bl_credits_4w": l4w.get("bl_credits_alctd", 0),
        "bl_active_days_4w": l4w.get("bl_active_days", 0),
        "bl_not_interested_4w": l4w.get("blni", 0),
        "prd_without_price": lm.get("prd_without_price", l4w.get("prd_without_price", 0)),
        "prd_without_photo": lm.get("prd_without_photo", l4w.get("prd_without_photo", 0)),
        "prd_without_ctg": lm.get("prd_without_ctg_mapping", 0),
        "cq_score": lm.get("cq_score"),
        "location_pref": lm.get("location_preference") or "",
        "top_mcats": mcats[:3],
        "market_total_bl": md0.get("total_bl"), "market_local_bl": md0.get("local_bl"),
        "market_paid_sellers": md0.get("total_paid_sellers"),
        "competitor_count": len(act.get("top3mcat_competitors") or []),
        "bl_available": bl.get("bl_available_pref_city") or bl.get("BL_available_gl_city") or 0,
        "exec_connects_30d": connects,
        "last_call_summary": con.get("last_call_summary") or "",
        "proposals_sent": con.get("proposals_sent_counts", 0),
        "wa_chats": wa[:5],
        "last_lead_title": _g(act, "LAST_LEAD", "TITLE", default=""),
        "last_lead_date": _g(act, "LAST_LEAD", "DATE_R", default=""),
        "last_enquiry_product": _g(act, "LAST_ENQUIRY", "PRODUCT_NAME", default=""),
    }
